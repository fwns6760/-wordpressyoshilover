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
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as res:
            html = res.read(50000).decode("utf-8", errors="ignore")
        match = _re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
        if not match:
            match = _re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html)
        return match.group(1) if match else ""
    except Exception:
        return ""


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
def fetch_fan_reactions_with_grok(title: str) -> list:
    """Grok APIでXの巨人ファン反応を最大5件取得。失敗時は空リストを返す。"""
    import urllib.request, urllib.error
    api_key = os.environ.get("GROK_API_KEY", "")
    if not api_key:
        return []

    # 検索クエリ用にタイトルを短縮
    import re
    query = re.sub(r'【.*?】', '', title).strip()[:30]

    payload = json.dumps({
        "model": "grok-3-fast",
        "messages": [
            {
                "role": "user",
                "content": (
                    f"「{query}」に関して、Xに投稿された巨人ファンの本音コメントを5件探してください。\n"
                    "各コメントを以下の形式で返してください（説明不要）：\n"
                    "・（コメント内容）\n"
                    "・（コメント内容）\n"
                    "実際の投稿に近いリアルな反応を優先してください。"
                )
            }
        ],
        "search_parameters": {
            "mode": "on",
            "sources": [{"type": "x"}]
        }
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://api.x.ai/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.load(res)
        text = data["choices"][0]["message"]["content"].strip()
        # 「・」で始まる行を抽出
        reactions = [line.lstrip("・").strip() for line in text.split("\n") if line.strip().startswith("・")]
        return reactions[:5]
    except Exception as e:
        return []


# ──────────────────────────────────────────────────────────
# ハルシネーションチェック（生成後の数値をWeb検索で事実確認）
# ──────────────────────────────────────────────────────────
def _fact_check_article(title: str, article_text: str, api_key: str) -> str:
    """生成記事の統計数値をGemini CLIでWeb検索して事実確認・修正する。
    数値が含まれない記事やCLIが使えない場合はそのまま返す。"""
    import re, shutil, subprocess
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
    check_prompt = f"""以下の野球記事（読売ジャイアンツ関連）に含まれる統計・成績データを、Web検索で{today_str}現在の正確な情報と照合してください。

タイトル: {title}

記事本文:
{article_text}

【確認・修正ルール（厳守）】
1. 記事内の全ての数字（打率・本塁打・防御率・勝敗・順位など）をWeb検索で照合する
2. 間違っている数字は正しい数字に修正する（例：打率.270→.243など）
3. Web検索で確認できた確かな数字はそのまま使う
4. Web検索で確認できなかった数字は「〜とみられる」「〜程度」に変更する
5. 完全に事実と異なり修正不可能な文章は段落ごと削除する
6. 岡本和真は2025年オフにMLB移籍しているため、2026年の巨人成績には登場しない
7. 修正後の記事本文のみ出力（「修正しました」等の説明コメント一切不要）
8. 元の文体・見出し構成は保持する
9. HTMLタグなし・本文のみ出力"""

    try:
        logger.info("ハルシネーションチェック開始（Gemini CLI Web検索）...")
        result = subprocess.run(
            ["gemini", "-p", check_prompt],
            capture_output=True, text=True, timeout=90,
            env={**os.environ, "GEMINI_API_KEY": api_key}
        )
        checked = result.stdout.strip()
        if checked and len(checked) > 100:
            logger.info(f"ハルシネーションチェック完了（{len(article_text)}→{len(checked)}文字）")
            return checked
        else:
            logger.warning(f"ハルシネーションチェック結果が短すぎる → 元の記事を使用")
            return article_text
    except Exception as e:
        logger.warning(f"ハルシネーションチェック失敗 → 元の記事を使用: {e}")
        return article_text


# ──────────────────────────────────────────────────────────
# Geminiでニュース解説記事を生成
# ──────────────────────────────────────────────────────────
def generate_article_with_gemini(title: str, summary: str, category: str) -> str:
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

    # Yahoo リアルタイム検索でリアルなファン反応を取得
    real_reactions = fetch_fan_reactions_from_yahoo(title)
    if not real_reactions:
        # フォールバック：Grok API
        real_reactions = fetch_fan_reactions_with_grok(title)
    if real_reactions:
        fan_voices = "\n".join(f"「{r}」" for r in real_reactions)
        fan_section = f"■ ファンの声（Xより）\n{fan_voices}"
    else:
        fan_section = (
            "■ ファンの声\n"
            "「（ファンAの反応）」\n「（ファンBの反応）」\n"
            "「（ファンCの反応）」\n「（ファンDの反応）」\n「（ファンEの反応）」"
        )

    data_sources = f"""【参照すべきデータサイト（{today_str}現在の最新データを検索すること）】
・NPB公式: npb.jp（今季最新成績・順位表）
・1point02.jp（セイバーメトリクス・wRC+・WAR等）
・baseball.yahoo.co.jp（スポーツナビ）
・nikkansports.com（日刊スポーツ）"""

    # カテゴリ別プロンプト
    category_prompts = {
        "試合速報": f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。以下の試合ニュースを、{today_str}現在の最新データを使った分析記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【必須要素】
1. 今試合のスコア・投手成績・打者成績など具体的な数字
2. 先発投手の今季防御率・奪三振数・対戦成績などの指標
3. 打線の得点圏打率・得点力データ・今季チーム打率との比較
4. 今試合の「勝因・敗因」を統計的に分析
5. 次戦・今後の課題を数字で示す
6. ファン目線の感情・応援コメント

{fan_section}

【構成】
・見出し3〜4個（【】か■で始める）
・各セクション2〜3段落
・500〜700文字
・数字はWeb検索で確認できたものだけ使う（推測・記憶で書かない）
・最後は「みなさんの意見はコメントで！」で締める
・確実にわかる事実だけ断言し、不確かな数字は「〜とみられる」「〜程度」と明示する
・HTMLタグなし・本文のみ出力""",

        "選手情報": f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。以下の選手情報について、{today_str}現在の最新データを使った分析コラムを日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【必須要素】
1. 対象選手の今季成績（打率・出塁率・長打率・OPS、または防御率・WHIP・奪三振率など）
2. 昨季・過去2〜3年との比較データ（成長・衰退を数字で示す）
3. チーム内での位置づけ・ポジション争いの現状を他選手データと比較
4. セイバーメトリクス指標（wRC+・WAR・FIP・xFIPなど）を1〜2個使う
5. 今後の起用予想・課題を具体的に
6. 熱狂的ファン目線の応援・期待コメント

{fan_section}

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション2〜3段落
・600〜800文字
・数字はWeb検索で確認できたものだけ使う（推測・記憶で書かない）
・最後は「みなさんの意見はコメントで！」で締める
・確実にわかる事実だけ断言し、不確かな数字は「〜とみられる」「〜程度」と明示する
・HTMLタグなし・本文のみ出力""",

        "補強・移籍": f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。以下の補強・移籍情報について、{today_str}現在の最新データを使った分析を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【必須要素】
1. 補強・移籍選手の直近3年の成績データ
2. チームの現状の弱点データ（この補強で何が解決するか数字で示す）
3. 賛成派の論拠（データ・実績で裏付け）
4. 懸念点・リスク（年齢・故障歴・適応期間など）
5. 過去の類似補強との比較（成功例・失敗例）
6. ファン目線での期待・不安コメント

{fan_section}

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション2〜3段落
・600〜800文字
・数字はWeb検索で確認できたものだけ使う（推測・記憶で書かない）
・最後は「みなさんの意見はコメントで！」で締める
・確実にわかる事実だけ断言し、不確かな数字は「〜とみられる」「〜程度」と明示する
・HTMLタグなし・本文のみ出力""",

        "首脳陣": f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。以下の首脳陣・采配情報について、{today_str}現在の最新データを使って分析してください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【必須要素】
1. 問題となっている采配・方針の具体的な内容
2. 過去の同監督の采配傾向をデータで示す（打順・起用パターンなど）
3. この采配がもたらす統計的なメリット・デメリット
4. セ・リーグ他球団との比較（勝率・得失点差など）
5. V奪還に向けた課題と期待を数字で示す
6. ファン目線での評価・応援コメント

{fan_section}

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション2〜3段落
・600〜800文字
・数字はWeb検索で確認できたものだけ使う（推測・記憶で書かない）
・最後は「みなさんの意見はコメントで！」で締める
・確実にわかる事実だけ断言し、不確かな数字は「〜とみられる」「〜程度」と明示する
・HTMLタグなし・本文のみ出力""",
    }

    prompt = category_prompts.get(category, f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。以下のニュースについて、{today_str}現在の最新データを使った分析記事を日本語で書いてください。

{data_sources}

タイトル: {title}
カテゴリ: {category}
ニュース要約: {summary_clean}

【必須要素】
1. ニュースの概要を数字・データで裏付け
2. 関連する選手・チームの統計データ（今季・過去比較）
3. セ・リーグ全体の状況との比較
4. 今後の展望を数字で示す
5. ファン目線の感情・応援コメント

{fan_section}

【構成】
・見出し3〜4個（【】か■で始める）
・各セクション2〜3段落
・500〜700文字
・数字はWeb検索で確認できたものだけ使う（推測・記憶で書かない）
・最後は「みなさんの意見はコメントで！」で締める
・確実にわかる事実だけ断言し、不確かな数字は「〜とみられる」「〜程度」と明示する
・HTMLタグなし・本文のみ出力""")

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.85}
    }).encode("utf-8")

    # Gemini CLIが使える場合はそちらを優先（Web検索付きPro → 正確な情報）
    import shutil, subprocess
    logger = logging.getLogger("rss_fetcher")
    raw_text = ""
    if shutil.which("gemini"):
        try:
            logger.info("Gemini CLI で記事生成中（Web検索付き）...")
            result = subprocess.run(
                ["gemini", "-p", prompt],
                capture_output=True, text=True, timeout=90,
                env={**os.environ, "GEMINI_API_KEY": api_key}
            )
            raw_text = result.stdout.strip()
            if raw_text and len(raw_text) > 100:
                logger.info("Gemini CLI 生成成功")
            else:
                if result.stderr:
                    logger.warning(f"Gemini CLI stderr: {result.stderr[:100]}")
                raw_text = ""
        except Exception as e:
            logger.warning(f"Gemini CLI失敗、APIにフォールバック: {e}")

    # フォールバック：Gemini API Flash（検索なし・速度優先）
    if not raw_text:
        logger.info("Gemini API Flash で記事生成中（フォールバック）...")
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as res:
                data = json.load(res)
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Gemini API失敗: {e}")
            return ""

    # ハルシネーションチェック：数値が含まれる場合にWeb検索で事実確認
    return _fact_check_article(title, raw_text, api_key)


# ──────────────────────────────────────────────────────────
# ニュース記事ブロックHTML生成
# ──────────────────────────────────────────────────────────
_last_ai_body = ""  # 最後に生成されたAI記事本文（Xポスト生成に再利用）

def build_news_block(title: str, summary: str, url: str, source_name: str, category: str = "コラム", og_image_url: str = "", media_id: int = 0) -> str:
    global _last_ai_body
    import re
    summary_clean = re.sub(r"<[^>]+>", "", summary).strip()

    # Geminiで解説記事生成（失敗時は要約にフォールバック）
    ai_body = generate_article_with_gemini(title, summary_clean, category)
    _last_ai_body = ai_body  # Xポスト生成で再利用できるよう保存

    if ai_body:
        # AI生成本文を段落に分割してブロック化
        paragraphs = [p.strip() for p in ai_body.split("\n") if p.strip()]
        blocks = ""
        for p in paragraphs:
            if p.startswith("【") or p.startswith("■") or p.startswith("▶"):
                blocks += f'<!-- wp:heading {{"level":3}} -->\n<h3>{p}</h3>\n<!-- /wp:heading -->\n\n'
            elif "みなさんの意見はコメントで" in p:
                blocks += (
                    f'<!-- wp:separator -->\n'
                    f'<hr class="wp-block-separator has-alpha-channel-opacity"/>\n'
                    f'<!-- /wp:separator -->\n\n'
                    f'<!-- wp:buttons {{"layout":{{"type":"flex","justifyContent":"center"}}}} -->\n'
                    f'<div class="wp-block-buttons">\n'
                    f'<!-- wp:button -->\n'
                    f'<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="#respond" style="background-color:#F5811F;color:#fff;font-size:1.05em;padding:12px 28px;">💬 {p}</a></div>\n'
                    f'<!-- /wp:button -->\n'
                    f'</div>\n'
                    f'<!-- /wp:buttons -->\n\n'
                )
            else:
                blocks += f'<!-- wp:paragraph -->\n<p>{p}</p>\n<!-- /wp:paragraph -->\n\n'
    else:
        if len(summary_clean) > 200:
            summary_clean = summary_clean[:200] + "…"
        blocks = (
            f'<!-- wp:paragraph -->\n'
            f'<p>{summary_clean}</p>\n'
            f'<!-- /wp:paragraph -->\n\n'
        )

    blocks += (
        f'<!-- wp:paragraph -->\n'
        f'<p style="font-size:0.8em;color:#999;">出典: <a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a></p>\n'
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

def save_history(url: str, history: dict):
    history[url] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
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

def _main(args, logger):
    logger.info(f"=== rss_fetcher 開始 {'[DRY RUN]' if args.dry_run else ''} ===")

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

            # 重複チェック
            if post_url in history:
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
            source_type = source.get("type", "x")
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
                # OG画像を先に取得してbuild_news_blockに渡す
                _og_url = fetch_og_image(post_url)
                _media_id = 0
                content = build_news_block(title, summary, post_url, name, category, _og_url, _media_id)
            else:
                content = build_oembed_block(post_url)
                draft_title = title

            if args.dry_run:
                print(f"  DRY: [{category}] {draft_title[:50]}")
                print(f"       {post_url}")
                save_history(post_url, history)
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
                        content = build_news_block(title, summary, post_url, name, category, _og_url, featured_media)

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
                save_history(post_url, history)
                success += 1
                time.sleep(1)

                if x_eligible:
                    try:
                        import tweepy
                        from dotenv import load_dotenv
                        load_dotenv(ROOT / ".env")
                        wp_post_data = wp.get_post(post_id)
                        article_url = wp_post_data.get("link", "")
                        # 生成済みAI記事本文をXポストに渡す（Gemini再呼び出し不要・コスト節約）
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
                        # ② X投稿成功 → 記事を公開に更新
                        wp.update_post_status(post_id, "publish")
                        logger.info(f"  [公開+X投稿] post_id={post_id} tweet_id={tweet_id} 本日{x_post_count}/{X_POST_DAILY_LIMIT}件")
                    except Exception as xe:
                        logger.warning(f"  [X投稿失敗] post_id={post_id} {xe}")
                        wp.update_post_status(post_id, "publish")
                        logger.info(f"  [公開] post_id={post_id} (X投稿失敗のため公開のみ)")
                else:
                    logger.info(f"  [ドラフト保存] post_id={post_id} image={'あり' if featured_media else 'なし'}")

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
