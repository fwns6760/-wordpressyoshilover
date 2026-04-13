"""
rss_fetcher.py — RSSHub経由でXアカウント投稿を自動取得してWP下書き生成

使用例:
    python3 src/rss_fetcher.py --dry-run   # 取得確認のみ（WP投稿しない）
    python3 src/rss_fetcher.py             # 実行（WP下書き生成）
"""

import sys
import os
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# vendorディレクトリをパスに追加（サーバー環境用）
ROOT = Path(__file__).parent.parent
_vendor = str(ROOT / 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)
sys.path.insert(0, str(Path(__file__).parent))

import feedparser
import re as _re

from wp_client import WPClient
from wp_draft_creator import build_oembed_block, load_posted_urls, save_posted_url
from x_post_generator import build_post as build_x_post_text


# ──────────────────────────────────────────────────────────
# Yahoo リアルタイム検索からXポスト取得
# ──────────────────────────────────────────────────────────
def fetch_yahoo_realtime_entries(keyword: str) -> list:
    """Yahoo リアルタイム検索から巨人関連の人気Xポストを取得。feedparser互換の形式で返す。"""
    import urllib.request, urllib.parse, json as _json
    try:
        q = urllib.parse.quote(keyword)
        url = f"https://search.yahoo.co.jp/realtime/search?p={q}&ei=UTF-8"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        import re as _re
        json_match = _re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, _re.DOTALL)
        if not json_match:
            return []
        data = _json.loads(json_match.group(1))
        page_data   = data["props"]["pageProps"]["pageData"]
        entries_raw = page_data["timeline"]["entry"]
        # bestTweet（Yahoo選定の最バズ投稿）を先頭に追加
        bt = page_data.get("bestTweet", {})
        bt_text = bt.get("displayText", "")
        bt_text = _re.sub(r'\s*(START|END)\s*', ' ', bt_text).strip()
        if bt_text and len(bt_text) > 15 and bt.get("url"):
            entries_raw = [{"displayText": bt_text, "url": bt["url"],
                            "rt": bt.get("rt", 999), "like": bt.get("like", 999)}] + list(entries_raw)
        # RT・Like数でスコアリングして人気順にソート
        scored = []
        for e in entries_raw:
            text = e.get("displayText", "") or e.get("text", "")
            text = _re.sub(r'\s*(START|END)\s*', ' ', text).strip()
            tweet_url = e.get("url", "")
            rt   = e.get("rt", 0) or 0
            like = e.get("like", 0) or 0
            score = rt * 3 + like  # RTを重視
            if not text or len(text) < 15 or not tweet_url:
                continue
            scored.append((score, {
                "title": text[:80],
                "summary": text,
                "link": tweet_url,
                "rt": rt,
                "like": like,
                "published_parsed": None,
            }))
        # スコア上位10件のみ返す
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:10]]
    except Exception as e:
        return []


# ──────────────────────────────────────────────────────────
# OG画像取得
# ──────────────────────────────────────────────────────────
def fetch_og_image(url: str) -> str:
    """記事URLからOGP画像URLを取得。取得できなければ空文字を返す。"""
    imgs = fetch_article_images(url, max_images=1)
    return imgs[0] if imgs else ""


def fetch_article_images(url: str, max_images: int = 3) -> list:
    """記事ページから写真URLを最大 max_images 枚スクレイピングして返す。
    og:image を先頭に、本文中の <img> から大きそうなものを追加する。"""
    try:
        import urllib.request, urllib.parse
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=12) as res:
            html = res.read(200000).decode("utf-8", errors="ignore")

        seen = set()
        images = []

        def _add(img_url: str):
            if not img_url or img_url in seen:
                return
            # 絶対URLに変換
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                parsed = urllib.parse.urlparse(url)
                img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
            elif not img_url.startswith("http"):
                return
            # アイコン・バナー・広告っぽいものを除外
            low = img_url.lower()
            if any(ng in low for ng in ["logo", "icon", "banner", "ad", "button",
                                         "sprite", "blank", "noimage", "no_image",
                                         "spacer", "pixel", "tracking", "1x1"]):
                return
            # 小さい画像を除外（URLにサイズ情報がある場合）
            size_m = _re.search(r'[_\-x](\d+)[_\-x](\d+)', low)
            if size_m:
                w, h = int(size_m.group(1)), int(size_m.group(2))
                if w < 300 or h < 150:
                    return
            seen.add(img_url)
            images.append(img_url)

        # 1. og:image（最優先）
        for pat in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        ]:
            m = _re.search(pat, html)
            if m:
                _add(m.group(1))
                break

        # 2. 本文エリアの <img> タグ（article / main / section 内を優先）
        # 記事本文っぽいブロックを切り出す
        article_html = html
        for area_pat in [
            r'<article[^>]*>(.*?)</article>',
            r'<div[^>]+class=["\'][^"\']*(?:article|content|body|main)[^"\']*["\'][^>]*>(.*?)</div>',
        ]:
            am = _re.search(area_pat, html, _re.DOTALL | _re.IGNORECASE)
            if am:
                article_html = am.group(1)
                break

        for img_m in _re.finditer(
            r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)["\']',
            article_html, _re.IGNORECASE
        ):
            _add(img_m.group(1))
            if len(images) >= max_images:
                break

        # 3. 本文外でも足りなければ全体から補完
        if len(images) < max_images:
            for img_m in _re.finditer(
                r'<img[^>]+src=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']',
                html, _re.IGNORECASE
            ):
                _add(img_m.group(1))
                if len(images) >= max_images:
                    break

        return images[:max_images]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────
# Yahoo リアルタイム検索でファン反応を取得（記事に組み込む用）
# ──────────────────────────────────────────────────────────
def fetch_fan_reactions_from_yahoo(title: str) -> list:
    """記事タイトルからキーワードを抽出し、Yahoo リアルタイム検索でファン投稿を最大5件取得。"""
    import urllib.request, urllib.parse, json as _json, re as _re

    # 選手名・チーム名など短いキーワードを抽出（【】を除去して最初の15文字）
    clean = _re.sub(r'[【】「」\[\]]', '', title)
    # 巨人＋最初の名詞っぽい部分
    keyword = "巨人 " + clean[:20]

    try:
        q = urllib.parse.quote(keyword)
        url = f"https://search.yahoo.co.jp/realtime/search?p={q}&ei=UTF-8"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")

        json_match = _re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, _re.DOTALL)
        if not json_match:
            return []
        data = _json.loads(json_match.group(1))
        page_data = data["props"]["pageProps"]["pageData"]
        entries = page_data.get("timeline", {}).get("entry", [])

        reactions = []
        for e in entries[:20]:
            text = e.get("displayText", "") or e.get("text", "")
            text = _re.sub(r'\s*(START|END)\s*', ' ', text).strip()
            # 短すぎ・URL多い・宣伝っぽいものを除外
            if len(text) < 20 or len(text) > 120:
                continue
            if text.count("http") > 1:
                continue
            if any(ng in text for ng in ["フォロー", "RT", "プレゼント", "キャンペーン", "告知"]):
                continue
            reactions.append(text)
            if len(reactions) >= 5:
                break

        return reactions
    except Exception:
        return []


# ──────────────────────────────────────────────────────────
# GrokでリアルなXファン反応を取得
# ──────────────────────────────────────────────────────────
def _parse_responses_api_text(data: dict) -> str:
    """Responses API（/v1/responses）のレスポンスからテキストを抽出。
    ツール使用時は output に custom_tool_call が混在するため type==message を探す。"""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    return content.get("text", "").strip()
    return ""


def fetch_fan_reactions_with_grok(title: str) -> list:
    """Grok Responses APIでXの巨人ファン反応を最大10件取得。失敗時は空リストを返す。"""
    import urllib.request, urllib.error
    api_key = os.environ.get("GROK_API_KEY", "")
    if not api_key:
        return []

    # 検索クエリ用にタイトルを短縮
    import re
    query = re.sub(r'【.*?】', '', title).strip()[:30]

    from datetime import datetime, timedelta
    today_dt  = datetime.now()
    from_date = today_dt.strftime("%Y-%m-%d")
    to_date   = today_dt.strftime("%Y-%m-%d")

    payload = json.dumps({
        "model": "grok-4-1-fast-reasoning",
        "input": [
            {
                "role": "user",
                "content": (
                    f"「{query}」に関して、Xに投稿された巨人ファンの本音コメントを10件探してください。\n"
                    "各コメントを以下の形式で返してください（説明不要）：\n"
                    "@アカウント名: コメント内容\n"
                    "@アカウント名: コメント内容\n"
                    "喜び・悔しさ・驚き・批判など感情が多様になるよう選んでください。実際の投稿を優先してください。"
                )
            }
        ],
        "tools": [{"type": "x_search", "from_date": from_date, "to_date": to_date}]
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://api.x.ai/v1/responses",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "x-grok-conv-id": "aa574b0b-75da-4897-98cb-97ad85daed6c"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.load(res)
        text = _parse_responses_api_text(data)
        if not text:
            return []
        import re as _re2
        def _clean(s: str) -> str:
            # [[数字]](URL) 形式の引用リンクを除去
            return _re2.sub(r'\[\[\d+\]\]\([^)]+\)', '', s).strip()

        # 「・」で始まる行を優先、なければ非空行を抽出
        # @handle: text 形式を優先パース
        import re as _re3
        handle_lines = [_clean(line.strip()) for line in text.split("\n")
                        if _re3.match(r'^@\S+[:：]', line.strip())]
        if handle_lines:
            return [l for l in handle_lines if l][:10]
        bullet_lines = [_clean(line.lstrip("・").strip()) for line in text.split("\n") if line.strip().startswith("・")]
        if bullet_lines:
            return [l for l in bullet_lines if l][:10]
        # フォールバック: 20文字以上の行をファン反応として取得
        plain_lines = [_clean(line.strip()) for line in text.split("\n") if len(line.strip()) > 20]
        return [l for l in plain_lines if l][:10]
    except Exception as e:
        return []


# ──────────────────────────────────────────────────────────
# ハルシネーションチェック（生成後の数値をWeb検索で事実確認）
# ──────────────────────────────────────────────────────────
def _fact_check_article(title: str, article_text: str, api_key: str) -> str:
    """生成記事の統計数値をGemini 2.0 Flash + Google Searchで事実確認・修正する。"""
    import re
    from datetime import date
    logger = logging.getLogger("rss_fetcher")

    # 数値が含まれるか確認（打率・防御率・本塁打・勝率など）
    has_stats = bool(re.search(r'(?:\.\d{2,3}|[0-9]+本|[0-9]+勝|[0-9]+敗|[0-9]+打点|防御率|打率|出塁率|OPS|WAR|wRC)', article_text))
    if not has_stats:
        logger.info("ハルシネーションチェック: 数値なし → スキップ")
        return article_text

    if not shutil.which("gemini"):
        logger.info("ハルシネーションチェック: Gemini CLI なし → スキップ")
        return article_text

    today_str = date.today().strftime("%Y年%m月%d日")
    check_prompt = f"""以下の野球記事（読売ジャイアンツ関連）をWeb検索で最新データと照合し、数字を正確にして充実させてください。

タイトル: {title}

記事本文:
{article_text}

【照合・修正ルール（厳守）】
1. npb.jp・baseball.yahoo.co.jp・1point02.jpをWeb検索して{today_str}現在のデータを取得する
2. 記事内の数字をWeb検索結果と照合し、間違いは正しい数字に修正する
3. 「〜とみられる」「〜程度」の箇所は、Web検索で確認できれば正確な数字に置き換え「（npb.jp）」等の出典を付ける
4. 数字が少ない箇所は、Web検索で見つけたデータを追加し出典を付けて充実させる
5. 岡本和真は2025年オフにMLB移籍済み → 2026年巨人の成績には絶対に登場させない
6. 完全に事実と異なる文章は削除または修正する
7. 修正後の記事本文のみ出力（説明コメント不要）
8. 元の文体・見出し構成は保持する
9. HTMLタグなし・本文のみ出力"""

    try:
        logger.info("ハルシネーションチェック開始（Gemini 2.0 Flash + Google Search）...")
        import urllib.request as _ureq
        payload = json.dumps({
            "contents": [{"parts": [{"text": check_prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.1}
        }).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        req = _ureq.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with _ureq.urlopen(req, timeout=30) as res:
            data = json.load(res)
        checked = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if checked and len(checked) > 100:
            logger.info(f"ハルシネーションチェック完了（{len(article_text)}→{len(checked)}文字）")
            article_text = checked
        else:
            logger.warning("チェック結果が短すぎる → 元の記事を維持")
    except Exception as e:
        logger.warning(f"ハルシネーションチェック失敗 → 元の記事を維持: {e}")

    return article_text


# ──────────────────────────────────────────────────────────
# Geminiでニュース解説記事を生成
# ──────────────────────────────────────────────────────────
def generate_article_with_gemini(title: str, summary: str, category: str, real_reactions: list = None) -> str:
    """Geminiで巨人ファン向け解説記事を生成。失敗時は空文字を返す。"""
    import urllib.request, urllib.error
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""

    import re
    from datetime import date
    today_str = date.today().strftime("%Y年%m月%d日")
    summary_clean = re.sub(r"<[^>]+>", "", summary).strip()[:400]

    # ファン反応（呼び出し元から渡された場合はそれを使う、なければ取得）
    if real_reactions is None:
        real_reactions = fetch_fan_reactions_from_yahoo(title)
    if real_reactions:
        fan_voices = "\n".join(f"「{r}」" for r in real_reactions[:3])
        fan_section = f"※以下は実際のXユーザーの声（記事には含めなくてよい、雰囲気の参考のみ）\n{fan_voices}"
    else:
        fan_section = ""

    data_sources = f"""【STEP1: まず以下のサイトをWeb検索して{today_str}現在の最新データを取得せよ】
① npb.jp → 今季個人成績・チーム成績・順位表（最優先）
② baseball.yahoo.co.jp/npb → スポーツナビ選手成績（必ずスポナビの数字を使う）
③ 1point02.jp → セイバーメトリクス（wRC+・WAR・FIP等）
④ baseballking.jp / full-count.jp → 最新ニュース・コメント
⑤ nikkansports.com / hochi.news → 試合速報・選手コメント
【STEP2: 取得したデータをもとに記事を書く（順位・成績は上記Web検索結果の最新値を使う）】"""

    # タイトル・要約から勝敗を判定してプロンプトに明示
    import re as _re2
    score_match = _re2.search(r'(\d{1,2})[－\-–](\d{1,2})', title + " " + summary_clean)
    win_loss_hint = ""
    if score_match:
        g_score = int(score_match.group(1))
        o_score = int(score_match.group(2))
        if "巨人" in (title + summary_clean)[:20]:
            if g_score > o_score:
                win_loss_hint = f"※この試合は巨人が{g_score}-{o_score}で【勝利】した試合です。"
            elif g_score < o_score:
                win_loss_hint = f"※この試合は巨人が{g_score}-{o_score}で【敗戦】した試合です。負け試合として正直に書くこと。"
            else:
                win_loss_hint = f"※この試合は{g_score}-{o_score}の【引き分け】です。"
    elif any(w in (title + summary_clean) for w in ["勝利", "白星", "連勝", "サヨナラ勝"]):
        win_loss_hint = "※この試合は巨人が【勝利】した試合です。"
    elif any(w in (title + summary_clean) for w in ["敗れ", "敗戦", "連敗", "黒星", "完封負"]):
        win_loss_hint = "※この試合は巨人が【敗戦】した試合です。負け試合として正直に書くこと。前向きに美化しない。"

    # カテゴリ別プロンプト
    category_prompts = {
        "試合速報": f"""あなたは読売ジャイアンツの現実的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データ豊富な試合分析記事を日本語で書いてください。

{win_loss_hint}
【重要】勝ち試合は喜びを、負け試合は課題・問題点を正直に書く。結果に反した美化・提灯記事は厳禁。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・今試合のスコア・投球回・奪三振・失点
・先発投手の今季防御率・WHIP・通算成績
・打者のヒット数・打率・得点圏打率
・今季チーム順位・勝敗・得失点差
・セ・リーグ他球団との比較データ1つ以上

{fan_section}

【構成】
・見出し3〜4個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""",

        "選手情報": f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データ豊富な選手分析コラムを日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・対象選手の今季打率・出塁率・長打率・OPS（または防御率・WHIP・K/9）
・昨季との比較（数値の変化を具体的に）
・チーム内ランキングでの位置（「チーム〇位」等）
・セイバーメトリクス指標1つ以上（wRC+・WAR・FIPなど）
・同ポジション他球団選手との比較1名以上

{fan_section}

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""",

        "補強・移籍": f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データ豊富な補強分析記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・補強選手の直近2〜3年の成績（打率・本塁打・OPS等）
・チームの現状弱点データ（この補強が必要な理由）
・補強前後の想定スタメン・戦力比較
・過去の類似補強選手との成績比較
・チーム順位・得点力・防御力の現状数値

{fan_section}

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""",

        "首脳陣": f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データで裏付けた采配分析記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・今季チーム成績（勝率・得点・失点・防御率）
・問題の采配に関連する選手成績データ
・阿部監督の今季起用パターン・采配傾向
・セ・リーグ順位表と得失点差
・過去の同時期との比較データ

{fan_section}

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""",
    }

    prompt = category_prompts.get(category, f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データ豊富な分析記事を日本語で書いてください。

{data_sources}

タイトル: {title}
カテゴリ: {category}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・関連選手の今季成績（打率・本塁打・OPS or 防御率・WHIP等）
・昨季との比較データ
・チーム順位・勝敗・得失点差
・セ・リーグ他球団との比較1つ以上

{fan_section}

【構成】
・見出し3〜4個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""")

    logger = logging.getLogger("rss_fetcher")

    # Gemini 2.0 Flash + Google Search グラウンディング（Web検索付きAPI・CLIより高速）
    payload_grounded = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.7}
    }).encode("utf-8")

    logger.info("Gemini 2.5 Flash + Google Search 検索付きで記事生成中（最大2回試行）...")
    for attempt in range(2):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=payload_grounded, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as res:
                data = json.load(res)
            # Google Searchツール使用時はpartsが複数になることがある。テキストのみ結合
            parts = data["candidates"][0]["content"].get("parts", [])
            raw_text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
            if raw_text and len(raw_text) > 150:
                logger.info(f"Gemini 2.5 Flash（Google検索付き）生成成功 {len(raw_text)}文字")
                return raw_text
            logger.warning(f"Gemini応答が短すぎる（{len(raw_text)}文字）、リトライ {attempt+1}/2")
        except Exception as e:
            logger.warning(f"Gemini 2.5 Flash失敗 試行{attempt+1}/2: {e}")

    logger.error("Gemini 2.5 Flash（Google検索付き）が2回とも失敗 → 記事生成スキップ")
    return ""


# ──────────────────────────────────────────────────────────
# Grokで記事生成（Web検索＋X検索を1回で完結）
# ──────────────────────────────────────────────────────────
def generate_article_with_grok(title: str, summary: str, category: str, win_loss_hint: str = "") -> tuple:
    """Grok 4-1-fast で記事生成 + Xファンの声取得を同時に行う。
    Returns: (article_text, fan_reactions_list)"""
    import urllib.request, urllib.error
    from dotenv import load_dotenv
    from datetime import date
    import re
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("GROK_API_KEY", "")
    logger = logging.getLogger("rss_fetcher")
    if not api_key:
        return "", []

    today_str = date.today().strftime("%Y年%m月%d日")
    summary_clean = re.sub(r"<[^>]+>", "", summary).strip()[:400]

    query_short = re.sub(r'【.*?】', '', title).strip()[:20]
    # ファン界隈のニックネームを含めた複合クエリ（週次更新推奨）
    nickname_query = "(芽ネギ OR 大王 OR 若大将 OR たけまる OR 門脇 OR 大勢 OR 戸郷 OR マタ OR 中山礼都 OR 吉川尚輝) 巨人"
    prompt = f"""読売ジャイアンツの熱狂的ファンブログ記事を書いてください。今日は{today_str}。

{win_loss_hint}タイトル: {title}
要約: {summary_clean}

Web検索でnpb.jp・スポーツナビの最新成績を調べ、X検索で「{query_short} 巨人」および「{nickname_query}」のファンの声を15件以上探してください。ニックネームで呼ばれている投稿も積極的に拾ってください。

【絶対ルール】
・文体は「ですます調」（〜です、〜ます）で統一する
・---SUMMARY---は「今日のジャイアンツ」として3〜4文のオリジナル要約。試合の核心・選手名・監督コメントを盛り込み読者が続きを読みたくなる文章にする
・---ARTICLE---の最初の見出しは必ず「■今日のジャイアンツ」にする
・その下に続く見出しは【】か■で始め選手名を入れる（逆転型・数字比較型・ファン共感型どれでも可）
・最初の段落はファン目線で興奮気味に描写。「画面の前で思わずガッツポーズしました！」など共感フレーズを1つ入れる
・本文は500〜700文字。各段落は3文以内でテンポよく
・成績数字は（npb.jp）など出典付き。不明は「〜とみられます」
・負け試合は正直に課題を書く。前向きに美化しない
・岡本和真は2025年オフMLB移籍済み → 2026年巨人成績に登場させない
・---STATS---はその試合・選手の記録を箇条書きで5〜8件（試合結果・安打数・投球内容・チーム成績など）
・---IMPRESSION---は300文字のブロガー感想（ですます調・最後は「コメント欄で教えてください！」）
・「ファンの声」「Xより」などの見出しは---ARTICLE---内に書かない（---FANS---に書く）

---SUMMARY---
（2〜3文の要約）
---ARTICLE---
（上記ルール厳守で記事本文のみ。説明不要）
---FANS---
（X検索で見つけた実際のコメント。形式：@アカウント名: コメント内容。1行1件。15件以上。喜び・悔しさ・驚き・批判など感情を多様に選ぶ）
---STATS---
（試合・選手の記録を箇条書きで8〜12件。形式：・項目: 値。試合日・球場・スコア・安打数・先発投手・登板回・失点・勝敗・チーム成績・打率・関連選手成績を含める）
---IMPRESSION---
（300文字の感想。ですます調）"""

    # X検索の日付範囲（当日のみ。当日0件なら前日も含む）
    today = datetime.now()
    from_date = today.strftime("%Y-%m-%d")   # 今日
    to_date   = today.strftime("%Y-%m-%d")

    base_payload = {
        "input": [{"role": "user", "content": prompt}],
        "tools": [
            {"type": "web_search"},
            {
                "type": "x_search",
                "from_date": from_date,
                "to_date": to_date
            }
        ]
    }

    # reasoning優先（ツール呼び出しに強い）、失敗時はnon-reasoningにフォールバック
    models_to_try = ["grok-4-1-fast-reasoning", "grok-4-1-fast-non-reasoning"]
    logger.info("Grok Responses API (Web+X検索) で記事生成中...")
    for model_name in models_to_try:
        payload_obj = dict(base_payload)
        payload_obj["model"] = model_name
        payload_current = json.dumps(payload_obj).encode("utf-8")
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    "https://api.x.ai/v1/responses",
                    data=payload_current,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}", "x-grok-conv-id": "aa574b0b-75da-4897-98cb-97ad85daed6c"}
                )
                with urllib.request.urlopen(req, timeout=90) as res:
                    data = json.load(res)
                text = _parse_responses_api_text(data)

                # セクション分割: SUMMARY / ARTICLE / FANS / STATS / IMPRESSION
                def _extract(t, marker):
                    """---MARKER--- の次から次のセパレータまでを抽出"""
                    import re as _r
                    m = _r.search(rf'---{marker}---\s*(.*?)(?=---[A-Z]+---|$)', t, _r.DOTALL)
                    return m.group(1).strip() if m else ""

                summary_text  = _extract(text, "SUMMARY")
                article_text  = _extract(text, "ARTICLE")
                fans_raw      = _extract(text, "FANS")
                stats_text    = _extract(text, "STATS")
                impression    = _extract(text, "IMPRESSION")

                # ARTICLE が取れなければ全体を記事として扱う
                if not article_text:
                    article_text = text

                import re as _r2
                fan_reactions = [l.strip() for l in fans_raw.split("\n")
                                 if l.strip() and len(l.strip()) > 10][:15]

                if article_text and len(article_text) > 150:
                    logger.info(f"Grok ({model_name}) 生成成功 記事{len(article_text)}文字 ファン声{len(fan_reactions)}件")
                    return article_text, fan_reactions, summary_text, stats_text, impression
                logger.warning(f"Grok ({model_name}) 応答が短すぎる（{len(article_text)}文字）、リトライ {attempt+1}/2")
            except Exception as e:
                logger.warning(f"Grok ({model_name}) 失敗 試行{attempt+1}/2: {e}")

    logger.error("Grok全モデル失敗 → Geminiにフォールバック")
    return "", [], "", "", ""


# ──────────────────────────────────────────────────────────
# ニュース記事ブロックHTML生成
# ──────────────────────────────────────────────────────────
_last_ai_body = ""  # 最後に生成されたAI記事本文（Xポスト生成に再利用）

def build_news_block(title: str, summary: str, url: str, source_name: str, category: str = "コラム", og_image_url: str = "", media_id: int = 0, extra_images: list = None) -> str:
    global _last_ai_body
    import re
    summary_clean = re.sub(r"<[^>]+>", "", summary).strip()

    # 勝敗ヒント（generate_article_with_gemini と同じロジック）
    import re as _re2
    score_match = _re2.search(r'(\d{1,2})[－\-–](\d{1,2})', title + " " + summary_clean)
    win_loss_hint = ""
    if score_match:
        g, o = int(score_match.group(1)), int(score_match.group(2))
        if "巨人" in (title + summary_clean)[:20]:
            if g > o:   win_loss_hint = f"※この試合は巨人が{g}-{o}で【勝利】した試合です。"
            elif g < o: win_loss_hint = f"※この試合は巨人が{g}-{o}で【敗戦】した試合です。負け試合として正直に書くこと。前向きに美化しない。"
    elif any(w in (title + summary_clean) for w in ["勝利", "白星", "連勝", "サヨナラ勝"]):
        win_loss_hint = "※この試合は巨人が【勝利】した試合です。"
    elif any(w in (title + summary_clean) for w in ["敗れ", "敗戦", "連敗", "黒星", "完封負"]):
        win_loss_hint = "※この試合は巨人が【敗戦】した試合です。負け試合として正直に書くこと。前向きに美化しない。"

    # Grok（Web+X検索）で記事生成とファンの声を同時取得
    ai_body, real_reactions, summary_block, stats_block, impression_block = generate_article_with_grok(title, summary_clean, category, win_loss_hint)

    # Grokが失敗した場合はGeminiにフォールバック
    if not ai_body:
        real_reactions_yahoo = fetch_fan_reactions_from_yahoo(title)
        ai_body = generate_article_with_gemini(title, summary_clean, category, real_reactions=real_reactions_yahoo)
        real_reactions = real_reactions_yahoo
        summary_block = ""
        stats_block = ""
        impression_block = ""

    _last_ai_body = ai_body  # Xポスト生成で再利用できるよう保存

    import re as _re3

    def _comment_button(small: bool = False) -> str:
        label = "みなさんの意見はコメント欄で教えてください！"
        if small:
            return (
                f'<!-- wp:buttons {{"layout":{{"type":"flex","justifyContent":"center"}}}} -->\n'
                f'<div class="wp-block-buttons">\n'
                f'<!-- wp:button {{"className":"is-style-outline"}} -->\n'
                f'<div class="wp-block-button is-style-outline"><a class="wp-block-button__link wp-element-button" href="#respond" style="font-size:0.85em;padding:8px 20px;color:#F5811F;border-color:#F5811F;">💬 {label}</a></div>\n'
                f'<!-- /wp:button -->\n'
                f'</div>\n'
                f'<!-- /wp:buttons -->\n\n'
            )
        return (
            f'<!-- wp:separator -->\n'
            f'<hr class="wp-block-separator has-alpha-channel-opacity"/>\n'
            f'<!-- /wp:separator -->\n\n'
            f'<!-- wp:buttons {{"layout":{{"type":"flex","justifyContent":"center"}}}} -->\n'
            f'<div class="wp-block-buttons">\n'
            f'<!-- wp:button -->\n'
            f'<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="#respond" style="background-color:#F5811F;color:#fff;font-size:1.05em;padding:12px 28px;">💬 {label}</a></div>\n'
            f'<!-- /wp:button -->\n'
            f'</div>\n'
            f'<!-- /wp:buttons -->\n\n'
        )

    def _x_card(reaction: str) -> str:
        """@handle: text 形式をXカード風HTML blockに変換。"""
        m = _re3.match(r'^(@\S+)[:：]\s*(.+)$', reaction.strip())
        if m:
            handle = m.group(1)
            text = m.group(2).strip()
            initials = handle[1:3].upper() if len(handle) > 1 else "G"
        else:
            handle = "@giants_fan"
            text = reaction.strip()
            initials = "G"
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_handle = handle.replace("&", "&amp;")
        # @ を除いたハンドル文字列を表示名として使う（"巨人ファン"固定をやめる）
        display_name = handle.lstrip("@")
        colors = ["#e8272a", "#001e62", "#c9a227", "#e8272a", "#001e62"]
        color = colors[hash(handle) % len(colors)]
        return (
            f'<!-- wp:html -->\n'
            f'<div style="border:1px solid #cfd9de;border-radius:12px;padding:16px;margin:8px 0;background:#fff;">'
            f'<div style="display:flex;align-items:center;margin-bottom:10px;">'
            f'<div style="width:40px;height:40px;border-radius:50%;background:{color};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.9em;margin-right:10px;flex-shrink:0;">{initials}</div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="font-weight:bold;font-size:0.9em;">{display_name}</div>'
            f'<div style="color:#536471;font-size:0.8em;">{safe_handle}</div>'
            f'</div>'
            f'<div style="color:#000;font-weight:900;font-size:1.1em;">𝕏</div>'
            f'</div>'
            f'<p style="margin:0;font-size:0.92em;line-height:1.7;">{safe_text}</p>'
            f'</div>\n'
            f'<!-- /wp:html -->\n\n'
        )

    def _sep():
        return (
            f'<!-- wp:separator -->\n'
            f'<hr class="wp-block-separator has-alpha-channel-opacity"/>\n'
            f'<!-- /wp:separator -->\n\n'
        )

    def _para(text: str) -> str:
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return (
            f'<!-- wp:paragraph -->\n<p>{safe}</p>\n<!-- /wp:paragraph -->\n\n'
            f'<!-- wp:spacer {{"height":"8px"}} -->\n'
            f'<div style="height:8px" aria-hidden="true" class="wp-block-spacer"></div>\n'
            f'<!-- /wp:spacer -->\n\n'
        )

    blocks = ""

    # ──────────────────────────────────────────────────────────
    # ① 記事の要約（タイトル付き）
    # ──────────────────────────────────────────────────────────
    summary_text_to_show = summary_block if summary_block else summary_clean[:200] + "…"
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_source = source_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if source_name else "スポーツニュース"
    blocks += (
        f'<!-- wp:html -->\n'
        f'<div style="background:linear-gradient(135deg,#001e62 0%,#e8272a 100%);border-radius:10px;padding:18px 20px;margin:0 0 4px 0;">'
          f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
            f'<span style="background:rgba(255,255,255,0.2);color:#fff;font-size:0.78em;font-weight:800;padding:4px 10px;border-radius:20px;letter-spacing:0.05em;">📰 {safe_source}</span>'
            f'<span style="color:rgba(255,255,255,0.7);font-size:0.72em;">⚾ TODAY\'S GIANTS</span>'
          f'</div>'
          f'<div style="color:#fff;font-size:1.1em;font-weight:900;line-height:1.4;">{safe_title}</div>'
        f'</div>\n'
        f'<!-- /wp:html -->\n\n'
    )
    # OGP画像があれば要約の上に表示（ソース記事のその時の写真）
    if og_image_url:
        safe_og = og_image_url.replace("&", "&amp;")
        blocks += (
            f'<!-- wp:image {{"sizeSlug":"large","linkDestination":"none"}} -->\n'
            f'<figure class="wp-block-image size-large">'
            f'<img src="{safe_og}" alt="{safe_title}" style="border-radius:8px;"/>'
            f'</figure>\n'
            f'<!-- /wp:image -->\n\n'
        )
    blocks += _para(summary_text_to_show) + _sep()

    # ──────────────────────────────────────────────────────────
    # ② 今日の記録（要約の直下・ファンの声より上）
    # ──────────────────────────────────────────────────────────
    if stats_block:
        blocks += (
            f'<!-- wp:heading {{"level":3}} -->\n'
            f'<h3>📊 今日の記録</h3>\n'
            f'<!-- /wp:heading -->\n\n'
        )
        stat_items = [l.lstrip("・").strip() for l in stats_block.split("\n") if l.strip() and len(l.strip()) > 3]
        if stat_items:
            li_html = "\n".join(f"<li>{s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</li>" for s in stat_items)
            blocks += f'<!-- wp:list -->\n<ul class="wp-block-list">\n{li_html}\n</ul>\n<!-- /wp:list -->\n\n'
        # 記録の直下に小さめのコメントボタン①
        blocks += _comment_button(small=True)
        blocks += _sep()

    # ──────────────────────────────────────────────────────────
    # ③ ファンの声（Xカード 最大15件）
    # ──────────────────────────────────────────────────────────
    if real_reactions:
        blocks += (
            f'<!-- wp:heading {{"level":3}} -->\n'
            f'<h3>💬 ファンの声（Xより）</h3>\n'
            f'<!-- /wp:heading -->\n\n'
        )
        for reaction in real_reactions[:15]:
            blocks += _x_card(reaction)
        blocks += _sep()

    # ──────────────────────────────────────────────────────────
    # ④ 記事本文（■今日のジャイアンツ から始まる）
    # ──────────────────────────────────────────────────────────
    if ai_body:
        ai_body = _re3.sub(r'\[\[\d+\]\]\([^)]+\)', '', ai_body)
        ai_body = _re3.sub(r'（\d+文字）', '', ai_body)
        first_line = ai_body.strip().split('\n')[0].strip()
        clean_title = _re3.sub(r'[【】\s]', '', title)
        clean_first = _re3.sub(r'[【】\s]', '', first_line)
        if clean_title and clean_first and (clean_title in clean_first or clean_first in clean_title):
            ai_body = '\n'.join(ai_body.strip().split('\n')[1:]).strip()
        ai_body = _re3.sub(r'.*ファンの声.*\n?', '', ai_body)
        ai_body = _re3.sub(r'.*Xより.*\n?', '', ai_body)

        img_pool = list(extra_images) if extra_images else []
        para_count = 0
        for p in [p.strip() for p in ai_body.split("\n") if p.strip()]:
            if p.startswith("【") or p.startswith("■") or p.startswith("▶"):
                blocks += f'<!-- wp:heading {{"level":3}} -->\n<h3>{p}</h3>\n<!-- /wp:heading -->\n\n'
            elif "コメント" in p and ("意見" in p or "教えてください" in p):
                pass
            else:
                blocks += _para(p)
                para_count += 1
                # 2段落ごとに次の写真を1枚差し込む（臨場感アップ）
                if para_count % 2 == 0 and img_pool:
                    img_url = img_pool.pop(0).replace("&", "&amp;")
                    blocks += (
                        f'<!-- wp:image {{"sizeSlug":"large","linkDestination":"none"}} -->\n'
                        f'<figure class="wp-block-image size-large">'
                        f'<img src="{img_url}" alt="{safe_title}" style="border-radius:8px;width:100%;"/>'
                        f'</figure>\n'
                        f'<!-- /wp:image -->\n\n'
                    )
    else:
        blocks += _para(summary_clean[:200] + "…")

    # ──────────────────────────────────────────────────────────
    # ⑤ 感想（約300文字）
    # ──────────────────────────────────────────────────────────
    if impression_block:
        blocks += _sep()
        blocks += (
            f'<!-- wp:heading {{"level":3}} -->\n'
            f'<h3>⚾ 今日の感想</h3>\n'
            f'<!-- /wp:heading -->\n\n'
            + _para(impression_block)
        )

    # ⑥ コメントボタン
    blocks += _comment_button()

    # 出典（一次情報リンク付き）
    blocks += (
        f'<!-- wp:paragraph -->\n'
        f'<p style="font-size:0.8em;color:#999;">'
        f'📊 データ出典: '
        f'<a href="https://npb.jp/bis/2026/stats/bat_c.html" target="_blank" rel="noopener noreferrer">NPB公式（打撃成績）</a> / '
        f'<a href="https://baseball.yahoo.co.jp/npb/standings/" target="_blank" rel="noopener noreferrer">スポーツナビ（順位表）</a> / '
        f'<a href="{url}" target="_blank" rel="noopener noreferrer">元記事</a>'
        f'</p>\n'
        f'<!-- /wp:paragraph -->'
    )
    return blocks

# ──────────────────────────────────────────────────────────
# 設定
# ──────────────────────────────────────────────────────────
RSS_SOURCES_FILE  = ROOT / "config" / "rss_sources.json"
KEYWORDS_FILE     = ROOT / "config" / "keywords.json"
HISTORY_FILE      = ROOT / "data"   / "rss_history.json"
GCS_BUCKET        = os.environ.get("GCS_BUCKET", "")
GCS_HISTORY_KEY   = "rss_history.json"
LOG_FILE          = ROOT / "logs"   / "rss_fetcher.log"

GIANTS_KEYWORDS = ["巨人", "ジャイアンツ", "東京ドーム", "Giants", "TokyoGiants"]

# ──────────────────────────────────────────────────────────
# ロガー設定
# ──────────────────────────────────────────────────────────
def setup_logger():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("rss_fetcher")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger

# ──────────────────────────────────────────────────────────
# 履歴管理（GCS対応：Cloud Runでも永続化）
# ──────────────────────────────────────────────────────────
def _gcs_client():
    try:
        from google.cloud import storage
        return storage.Client()
    except Exception:
        return None

def load_history() -> dict:
    if GCS_BUCKET:
        try:
            client = _gcs_client()
            if client:
                bucket = client.bucket(GCS_BUCKET)
                blob = bucket.blob(GCS_HISTORY_KEY)
                if blob.exists():
                    data = blob.download_as_text(encoding="utf-8")
                    return json.loads(data)
                return {}
        except Exception as e:
            logging.getLogger("rss_fetcher").warning(f"GCS load失敗、ローカルにフォールバック: {e}")
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(url: str, history: dict, title_norm: str = ""):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    history[url] = now_str
    if title_norm and len(title_norm) > 5:
        history[f"title_norm:{title_norm[:60]}"] = now_str
    data = json.dumps(history, ensure_ascii=False, indent=2)
    if GCS_BUCKET:
        try:
            client = _gcs_client()
            if client:
                bucket = client.bucket(GCS_BUCKET)
                blob = bucket.blob(GCS_HISTORY_KEY)
                blob.upload_from_string(data, content_type="application/json")
                return
        except Exception as e:
            logging.getLogger("rss_fetcher").warning(f"GCS save失敗、ローカルにフォールバック: {e}")
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write(data)

# ──────────────────────────────────────────────────────────
# 巨人キーワードフィルタ
# ──────────────────────────────────────────────────────────
def is_giants_related(text: str) -> bool:
    return any(kw in text for kw in GIANTS_KEYWORDS)

# ──────────────────────────────────────────────────────────
# カテゴリ自動分類
# ──────────────────────────────────────────────────────────
def classify_category(text: str, keywords: dict) -> str:
    for category, kws in keywords.items():
        if any(kw in text for kw in kws):
            return category
    return "コラム"

# ──────────────────────────────────────────────────────────
# タイトル生成（投稿内容の先頭40字）
# ──────────────────────────────────────────────────────────
def make_title(entry) -> str:
    text = entry.get("title", "") or entry.get("summary", "")
    # HTMLタグ除去
    import re
    text = re.sub(r"<[^>]+>", "", text).strip()
    text = text[:40].strip()
    return text if text else f"X投稿 {datetime.now().strftime('%Y-%m-%d')}"

# ──────────────────────────────────────────────────────────
# X投稿URLを取得（twitter.com形式に統一）
# ──────────────────────────────────────────────────────────
def get_post_url(entry) -> str:
    url = entry.get("link", "")
    return url.replace("https://x.com/", "https://twitter.com/")

# ──────────────────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="RSSHub経由でX投稿を取得してWP下書き生成")
    parser.add_argument("--dry-run", action="store_true", help="WP投稿せず結果を表示のみ")
    parser.add_argument("--limit", type=int, default=10, help="1回の実行で公開する最大記事数（デフォルト10）")
    args = parser.parse_args()

    logger = setup_logger()

    # 多重起動防止ロック
    lock_file = ROOT / "logs" / "rss_fetcher.lock"
    if lock_file.exists():
        logger.warning("=== 既に実行中のため終了（ロックファイルあり） ===")
        return
    lock_file.touch()
    try:
        _main(args, logger)
    finally:
        lock_file.unlink(missing_ok=True)

def check_giants_game_today() -> tuple:
    """巨人の今日の試合があるか確認。(has_game: bool, opponent: str, venue: str) を返す。
    取得失敗時は (True, "", "") を返してフェイルオープン（スキップしない）。"""
    import urllib.request as _ur
    from datetime import date
    import re as _re

    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    # NPB公式 月別日程ページ (4月なら schedule_04_detail.html)
    month_str = today.strftime("%m")
    url = f"https://npb.jp/games/{today.year}/schedule_{month_str}_detail.html"

    try:
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ur.urlopen(req, timeout=10) as res:
            html = res.read().decode("utf-8", errors="ignore")

        # 今日の日付セクションを探す（NPBページは "M/D" 形式で日付が入る）
        # 巨人＝「読売」「Giants」「G」のいずれかが同じ行/セクションにあるか確認
        # 日付は例: "4/13" or "4月13日"
        day_pattern = f"{today.month}/{today.day}"
        day_pattern2 = f"{today.month}月{today.day}日"

        # ページ全体を日付ブロックに分割
        # 簡易：今日の日付文字列の前後500文字に巨人関連語があるか
        for pat in [day_pattern, day_pattern2]:
            idx = html.find(pat)
            while idx != -1:
                block = html[max(0, idx-50):idx+600]
                block_text = _re.sub(r'<[^>]+>', '', block)
                if any(kw in block_text for kw in ["読売", "Giants", "ジャイアンツ", "巨人"]):
                    # 中止・オフを除外
                    if any(ng in block_text for ng in ["中止", "オフ", "休み", "ノーゲーム"]):
                        return False, "", ""
                    # 対戦相手と球場を抽出（あれば）
                    opp_m = _re.search(r'(?:vs\.|対)\s*([^\s<&]{2,6})', block_text)
                    venue_m = _re.search(r'(東京ドーム|神宮|横浜|ナゴヤ|甲子園|マツダ|PayPay|バンテリン|ほっと|ZOZOマリン)', block_text)
                    opponent = opp_m.group(1) if opp_m else ""
                    venue    = venue_m.group(1) if venue_m else ""
                    return True, opponent, venue
                idx = html.find(pat, idx + 1)

        # 巨人戦が見つからなければ試合なし
        return False, "", ""

    except Exception as e:
        logging.getLogger("rss_fetcher").warning(f"試合日チェック失敗（フェイルオープン）: {e}")
        return True, "", ""  # 取得失敗時はスキップせず通常実行


def _main(args, logger):
    logger.info(f"=== rss_fetcher 開始 {'[DRY RUN]' if args.dry_run else ''} ===")

    # ──────────────────────────────────────────────────────────
    # 事前チェック：今日の巨人戦があるか確認
    # ──────────────────────────────────────────────────────────
    has_game, opponent, venue = check_giants_game_today()
    if not has_game:
        logger.info("本日の巨人戦なし（オフ日または中止）→ 記事生成スキップ")
        return

    logger.info(f"本日の巨人戦確認OK{(' vs ' + opponent) if opponent else ''}{(' @' + venue) if venue else ''}")

    # 設定読み込み
    with open(RSS_SOURCES_FILE, encoding="utf-8") as f:
        sources = json.load(f)
    with open(KEYWORDS_FILE, encoding="utf-8") as f:
        keywords = json.load(f)

    history = load_history()

    if not args.dry_run:
        wp = WPClient()

    total = skip_dup = skip_filter = success = error = 0
    import time

    X_POST_DAILY_LIMIT = 20
    X_POST_CATEGORIES  = {"試合速報", "補強・移籍", "選手情報", "首脳陣"}
    today_str = datetime.now().strftime("%Y-%m-%d")
    x_post_count = history.get(f"x_post_count_{today_str}", 0)

    for source in sources:
        if success >= args.limit:
            logger.info(f"上限{args.limit}件に達したため終了")
            break
        name        = source["name"]
        url         = source["url"]
        source_type = source.get("type", "news")
        logger.info(f"取得中: {name} ({url})")

        try:
            if source_type == "yahoo_realtime":
                # yahoo_realtime://キーワード 形式
                keyword = url.replace("yahoo_realtime://", "")
                entries = fetch_yahoo_realtime_entries(keyword)
            else:
                feed    = feedparser.parse(url)
                entries = feed.entries
        except Exception as e:
            logger.error(f"フィード取得失敗 {name}: {e}")
            error += 1
            continue

        logger.info(f"  {len(entries)}件取得")
        total += len(entries)

        for entry in entries:
            post_url = get_post_url(entry)
            title_text = entry.get("title", "") + " " + entry.get("summary", "")

            # 重複チェック（URL）
            if post_url in history:
                skip_dup += 1
                continue

            # 重複チェック（タイトル）- 同じニュースが別URLで来るケースを防ぐ
            import re as _re2
            entry_title_raw = entry.get("title", "").strip()
            entry_title_norm = _re2.sub(r"[\s　【】「」『』〔〕（）()・\-_]", "", entry_title_raw).lower()
            if entry_title_norm and len(entry_title_norm) > 5:
                title_key = f"title_norm:{entry_title_norm[:60]}"
                if title_key in history:
                    logger.debug(f"  [SKIP:タイトル重複] {entry_title_raw[:50]}")
                    skip_dup += 1
                    continue

            # 新鮮さフィルタ（2時間以内・日付なしも弾く）
            pub = entry.get("published_parsed") or entry.get("updated_parsed")
            if not pub:
                logger.debug(f"  [SKIP:日付なし] {post_url}")
                skip_filter += 1
                continue
            # 時間フィルターなし：GCS履歴で重複管理するため不要

            # 巨人フィルタ
            if not is_giants_related(title_text):
                logger.debug(f"  [SKIP:フィルタ] {post_url}")
                skip_filter += 1
                continue

            # カテゴリ分類
            category = classify_category(title_text, keywords)
            title    = make_title(entry)

            # 選手・監督コメントがない記事はスキップ（newsソースのみ）
            source_type = source.get("type", "news")
            if source_type == "news":
                has_comment = "「" in title_text
                if not has_comment:
                    logger.debug(f"  [SKIP:コメントなし] {title[:40]}")
                    skip_filter += 1
                    continue

            logger.info(f"  [HIT] {title[:40]} → {category}")

            # ソースタイプに応じてコンテンツ生成
            if source_type == "news":
                summary = entry.get("summary", "") or entry.get("description", "")
                draft_title = entry.get("title", title).strip()[:80]
                # 記事ページから写真を最大3枚スクレイピング
                _article_images = fetch_article_images(post_url, max_images=3)
                _og_url  = _article_images[0] if _article_images else ""
                _media_id = 0
                content = build_news_block(title, summary, post_url, name, category, _og_url, _media_id, extra_images=_article_images[1:])
            else:
                content = build_oembed_block(post_url)
                draft_title = title

            if args.dry_run:
                print(f"  DRY: [{category}] {draft_title[:50]}")
                print(f"       {post_url}")
                save_history(post_url, history, entry_title_norm)
                success += 1
                continue

            # WP自動公開
            try:
                category_id = wp.resolve_category_id(category)

                # OG画像アップロードしてアイキャッチ＋記事内画像に使用
                featured_media = 0
                if source_type == "news" and _og_url:
                    featured_media = wp.upload_image_from_url(_og_url)
                    if featured_media:
                        # media_idが確定したので記事本文の画像ブロックを更新
                        content = build_news_block(title, summary, post_url, name, category, _og_url, featured_media, extra_images=_article_images[1:])

                AUTO_POST_CATEGORY_ID = 673  # 自動投稿カテゴリ（サイトマップ除外・noindex）
                cats = [AUTO_POST_CATEGORY_ID]
                if category_id:
                    cats.append(category_id)

                # X投稿条件チェック
                x_eligible = (
                    source_type == "news"
                    and category in X_POST_CATEGORIES
                    and x_post_count < X_POST_DAILY_LIMIT
                    and featured_media
                )

                # ① まずドラフトで記事作成（URL確定のため）
                post_id = wp.create_post(
                    draft_title, content,
                    categories=cats,
                    status="draft",
                    featured_media=featured_media or None,
                )
                save_history(post_url, history, entry_title_norm)
                success += 1
                time.sleep(1)

                # ② 記事を必ず公開（X投稿の有無に関係なく）
                wp.update_post_status(post_id, "publish")

                if x_eligible:
                    try:
                        import tweepy
                        from dotenv import load_dotenv
                        load_dotenv(ROOT / ".env")
                        wp_post_data = wp.get_post(post_id)
                        article_url = wp_post_data.get("link", "")
                        tweet_text = build_x_post_text(draft_title, article_url, category, summary=_last_ai_body or summary)
                        x_client = tweepy.Client(
                            bearer_token=os.environ.get("X_BEARER_TOKEN"),
                            consumer_key=os.environ.get("X_API_KEY"),
                            consumer_secret=os.environ.get("X_API_SECRET"),
                            access_token=os.environ.get("X_ACCESS_TOKEN"),
                            access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET"),
                        )
                        resp = x_client.create_tweet(text=tweet_text)
                        tweet_id = resp.data["id"]
                        x_post_count += 1
                        history[f"x_post_count_{today_str}"] = x_post_count
                        logger.info(f"  [公開+X投稿] post_id={post_id} tweet_id={tweet_id} 本日{x_post_count}/{X_POST_DAILY_LIMIT}件")
                    except Exception as xe:
                        logger.warning(f"  [X投稿失敗] post_id={post_id} {xe}")
                        logger.info(f"  [公開済み] post_id={post_id}")
                else:
                    logger.info(f"  [公開] post_id={post_id} image={'あり' if featured_media else 'なし'}")

                if success >= args.limit:
                    break

            except Exception as e:
                logger.error(f"  [ERROR] 公開失敗: {e}")
                error += 1

    logger.info(
        f"=== 完了: 取得={total} / 投稿={success} / 重複スキップ={skip_dup} "
        f"/ フィルタスキップ={skip_filter} / エラー={error} ==="
    )


if __name__ == "__main__":
    main()
