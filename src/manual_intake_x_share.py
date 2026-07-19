"""manual_intake_x_share.py — 手動アプリの「記事をXで共有」ロジック (2026-07-06 user GO)。

狙い (user 決定):
- 記事URLをおりポスに貼ると X の外部リンク抑制でインプが下がる
- おりポス = フック1行 (ヨシラバーの見立て) + 記事タイトル（媒体名） + 要約 (URLなし)
  + アイキャッチ画像のネイティブ添付 (2026-07-06 v2「記事のポストと分かる形」)
- タイトル行は code で literal 組み立て (LLM はフック/要約/リプの3部品のみ生成)
- リプ = 記事にしか無い要素のチラ見せ + 「続きは記事で」系の自然な誘導 + 記事URL
  (URLはリプに退避。2026-07-10 user「クリック率が悪い」→ 誘導の一言を必須化)
- 「続きはこちら」だけの空チラ見せは禁止 (おりポス単体で読み物として成立させる)
- フック生成が弱い時 (echo / 文体NG / 字数) はタイトル先頭型へ自動フォールバック

構成:
- list_recent_published()   最近の公開記事 (WP REST)
- fetch_article_material()  記事本文 + アイキャッチURL
- build_share_drafts()      型判定 (comment/data/news) + おりポス案 / リプ案 (flash-lite)
- post_thread()             media upload → おりポス → 自分へのリプ (in_reply_to)

安全側:
- 記事に無い数字は _extract_unverified_numbers で棄却 (LLM 失敗時は deterministic fallback)
- LLM 生成部 (フック/要約/リプ) に URL / ハッシュタグ / 媒体名を入れない
  (媒体名は code 組み立ての「タイトル（媒体名）」行のみ)
- X の weighted 文字数 (CJK=2, URL=23) を事前チェックして API エラーを防ぐ
"""

from __future__ import annotations

import io
import logging
import os
import re
from html import unescape
from typing import Optional

LOG = logging.getLogger("manual_intake_x_share")

_TAG_RE = re.compile(r"(?is)<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<[^>]+>")
_WS_RE = re.compile(r"[ \t　]+")
_URL_RE = re.compile(r"https?://\S+")
# X の t.co 換算 (URL は一律 23 weighted units)
_X_URL_WEIGHT = 23
_X_WEIGHTED_LIMIT = 280


def _main_weighted_limit() -> int:
    """おりポス (main) の weighted 上限。

    2026-07-07 user「オリポスながめ。プレミアプランだし」「キーワードをたくさん
    入れないと」: アカウントは X Premium なので main は長文ポスト前提
    (2026-07-19 default 1400 weighted ≈ 全角700字、user「長くてよい」)。リプは従来 280 のまま。
    env X_SHARE_MAIN_WEIGHTED_LIMIT で調整可 (280 に戻せば旧挙動)。
    """
    raw = (os.environ.get("X_SHARE_MAIN_WEIGHTED_LIMIT") or "").strip()
    try:
        return max(280, int(raw)) if raw else 1400
    except ValueError:
        return 1400

# 型ごとのフック指示 (おりポス1行目 = ヨシラバーの見立て)。
_HOOK_STYLE = {
    "comment": "セリフの意味・裏側を一言で突く (なぜその発言が出たか、何が変わったのか)。",
    "data": "その数字が示す意味を言い切る (すごさ・異常さ・流れの変化)。",
    "news": "この動きが巨人に何をもたらすかを一言で言い切る。",
}

# 出典媒体名の判定 (title 行の「（媒体名）」用)。domain 優先、text 内 literal は補助。
_MEDIA_DOMAIN_MAP = [
    ("hochi.news", "スポーツ報知"),
    ("sanspo.com", "サンスポ"),
    ("nikkansports.com", "日刊スポーツ"),
    ("sponichi.co.jp", "スポニチ"),
    ("daily.co.jp", "デイリースポーツ"),
    ("chunichi.co.jp", "中日スポーツ"),
    ("tokyo-sports.co.jp", "東スポ"),
    ("yomiuri.co.jp", "読売新聞"),
    ("full-count.jp", "Full-Count"),
    ("baseballking.jp", "BASEBALL KING"),
    ("news.yahoo.co.jp", "Yahoo!ニュース"),
    ("npb.jp", "NPB公式"),
]
_MEDIA_TEXT_NAMES = [
    "スポーツ報知", "サンスポ", "日刊スポーツ", "スポニチ",
    "デイリースポーツ", "中日スポーツ", "東スポ", "読売新聞",
]


def x_weighted_len(text: str) -> int:
    """X の weighted 文字数。CJK 等の全角圏は 2、それ以外 1、URL は一律 23。"""
    total = 0
    rest = text or ""
    for m in _URL_RE.finditer(rest):
        total += _X_URL_WEIGHT
    rest = _URL_RE.sub("", rest)
    for ch in rest:
        o = ord(ch)
        # CJK / かな / 全角記号圏はおおむね U+1100 以上 (X の cjk 判定の近似)
        total += 2 if o >= 0x1100 else 1
    return total


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    text = unescape(text)
    text = _WS_RE.sub(" ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def list_recent_published(limit: int = 10) -> list[dict]:
    """最近の公開記事 (id / title / link / date / featured_media)。"""
    from src.wp_client import WPClient

    wp = WPClient()
    posts = wp.list_posts(
        status="publish",
        per_page=max(1, min(limit, 20)),
        orderby="date",
        order="desc",
        context=None,
        fields=["id", "title", "link", "date", "featured_media"],
    )
    out = []
    for p in posts or []:
        title = p.get("title")
        if isinstance(title, dict):
            title = title.get("rendered") or ""
        out.append({
            "id": p.get("id"),
            "title": _strip_html(str(title or "")),
            "link": p.get("link") or "",
            "date": p.get("date") or "",
            "featured_media": p.get("featured_media") or 0,
        })
    return out


# 2026-07-07 user GO「今日の試合スレ (mail→アプリ→ボタン1回で3連投稿)」:
# 最新公開記事のうちタイトルが試合結果型のものを自動で拾う (userの記事選択を不要化)。
_POSTGAME_TITLE_RE = re.compile(
    r"(勝利|快勝|完封|完投|サヨナラ|逆転勝|辛勝|惜敗|敗戦|完敗|零封|連勝|連敗"
    r"|引き分け|ドロー|(?<![0-9])[0-9]{1,2}\s*[-−ー－]\s*[0-9]{1,2}(?![0-9]))"
)


def _looks_postgame(title: str) -> bool:
    """試合結果タイトル判定。実戦済みの title_validator 判定を主、 regex を従で併用
    (全角数字は NFKC 正規化してから regex を当てる)。"""
    import unicodedata as _ud

    normalized = _ud.normalize("NFKC", title or "")
    try:
        from src.title_validator import _has_postgame_signal

        if _has_postgame_signal(title or ""):
            return True
    except Exception:  # noqa: BLE001 - regex fallback
        pass
    return bool(_POSTGAME_TITLE_RE.search(normalized))


def find_latest_postgame() -> dict:
    """最新の公開済み試合結果 (postgame) 記事 1 件。見つからなければ {}。"""
    for p in list_recent_published(limit=10):
        if _looks_postgame(p.get("title") or ""):
            return p
    return {}


def build_thread_drafts(material: dict, *, gemini_api_key: str = "") -> dict:
    """試合後スレ 3 部品: ①おりポス(既存機構) ②ヒーローdata リプ ③URLリプ。

    ②は insight.db の verified 数字のみ (取れなければ空 = 2連にフォールバック)。
    """
    drafts = build_share_drafts(material, gemini_api_key=gemini_api_key)
    drafts["data_text"] = _build_hero_data_text(material)
    return drafts


def _build_hero_data_text(material: dict) -> str:
    """タイトル/冒頭から主役選手を検出し、 insight.db verified 数字で 1 リプ分。

    検出失敗 / DB 不達 / fact なしは空文字 (スレは 2 連で成立させる)。
    数字は build_db_fact_line (read-only SELECT) 由来のみ = 捏造リスクゼロ。
    """
    title = str(material.get("title") or "")
    head = str(material.get("body_text") or "")[:300]
    try:
        from src.x_post_mail_lane import detect_giants_player_name

        player = detect_giants_player_name(f"{title} {head}")
    except Exception as exc:  # noqa: BLE001
        LOG.info("x_share thread player detect skip: %r", exc)
        player = ""
    if not player:
        return ""
    try:
        from src import manual_intake_insight_query as miq

        db = miq.ensure_local_db()
        db_path = str(db.get("path") or "") if db.get("ok") else ""
    except Exception as exc:  # noqa: BLE001
        LOG.info("x_share thread insight db skip: %r", exc)
        db_path = ""
    if not db_path:
        return ""
    try:
        from src.x_post_branding_gen import build_db_fact_line

        fact = build_db_fact_line(player, db_path)
    except Exception as exc:  # noqa: BLE001
        LOG.info("x_share thread db fact skip: %r", exc)
        fact = ""
    fact = (fact or "").strip()
    if not fact:
        return ""
    text = f"今日の{player}、数字で見るとこう👇\n{fact}"
    # リプは 280 weighted 上限。超過時は fact 行を後ろから削る。
    while x_weighted_len(text) > 280 and "\n" in text:
        text = text.rsplit("\n", 1)[0]
    if x_weighted_len(text) > 280:
        return ""
    return text


def fetch_article_material(post_id: int) -> dict:
    """記事本文 (plain text) + link + アイキャッチ画像URL。"""
    from src.wp_client import WPClient

    wp = WPClient()
    post = wp.get_post(int(post_id))
    title = post.get("title")
    if isinstance(title, dict):
        title = title.get("rendered") or ""
    content = post.get("content")
    if isinstance(content, dict):
        content = content.get("rendered") or content.get("raw") or ""
    body_text = _strip_html(str(content or ""))
    image_url = ""
    fm = post.get("featured_media") or 0
    if fm:
        try:
            media = wp.get_media(int(fm))
            image_url = str(media.get("source_url") or "")
        except Exception as exc:  # noqa: BLE001 - 画像なしで続行
            LOG.info("x_share media fetch skip post=%s: %r", post_id, exc)
    return {
        "post_id": int(post_id),
        "title": _strip_html(str(title or "")),
        "link": post.get("link") or "",
        "status": str(post.get("status") or ""),
        "body_text": body_text,
        "image_url": image_url,
        "media_name": _detect_media_name(str(content or ""), body_text),
    }


def _detect_media_name(content_html: str, body_text: str) -> str:
    """出典媒体名。一次媒体 domain → 出典ブロック内 literal → Yahoo の順。

    literal 名の全文スキャンは禁止 (本文の関連記事等で誤媒体を拾う。
    2026-07-06 post 102501 で「東スポ」誤判定の実測)。「出典」直後 120 字のみ見る。
    """
    yahoo = ""
    for domain, name in _MEDIA_DOMAIN_MAP:
        if domain in content_html:
            if name == "Yahoo!ニュース":
                yahoo = name
                continue
            return name
    source_scope = " ".join(
        m.group(1) for m in re.finditer(r"出典[::]?\s*(.{0,120})", body_text)
    )
    for name in _MEDIA_TEXT_NAMES:
        if name in source_scope:
            return name
    return yahoo


def classify_share_type(title: str, body_text: str) -> str:
    """記事種別 → 投稿の型 (comment / data / news)。"""
    try:
        from src.x_post_mail_lane import _classify_news_material

        material, _label = _classify_news_material(title or "", (body_text or "")[:200])
        if material == "comment":
            return "comment"
        if material == "record":
            return "data"
    except Exception:  # noqa: BLE001 - fallback heuristics
        pass
    head = f"{title} {(body_text or '')[:400]}"
    if "『" in head or "」と" in head or "コメント" in head:
        return "comment"
    if re.search(r"(通算|連続|節目|記録|\d+号|\d+勝|\d+安打|\d+奪三振)", head):
        return "data"
    return "news"


def _forbidden_in_post(text: str) -> str:
    if _URL_RE.search(text):
        return "url"
    if re.search(r"[#＃]\S+", text):
        return "hashtag"
    if re.search(r"(報知|サンスポ|スポニチ|日刊スポーツ|デイリー|東スポ|読売新聞|スポーツ報知)", text):
        return "media_name"
    return ""


def build_share_drafts(
    material: dict,
    *,
    gemini_api_key: str = "",
) -> dict:
    """おりポス案 + リプ案。LLM 失敗時は deterministic fallback。

    おりポス構成 (2026-07-06 v2): フック \n\n タイトル（媒体名） \n\n 要約。
    タイトル行は code で literal 組み立て、LLM はフック/要約/リプのみ。
    """
    title = material.get("title") or ""
    body = material.get("body_text") or ""
    link = material.get("link") or ""
    media_name = material.get("media_name") or ""
    title_line = f"{title.strip()}（{media_name}）" if media_name else title.strip()
    share_type = classify_share_type(title, body)
    main_text = ""
    reply_body = ""
    used_llm = False
    if gemini_api_key:
        try:
            hook, summary, reply_body = _build_drafts_llm(
                title, body, share_type, gemini_api_key=gemini_api_key
            )
            if hook and summary and reply_body:
                main_text = _assemble_main(title_line, hook, summary)
                used_llm = True
        except Exception as exc:  # noqa: BLE001
            LOG.warning("x_share llm draft failed: %r", exc)
    if not main_text:
        main_text, reply_body = _build_drafts_fallback(title_line, body)
    # 2026-07-19 user「リプの考えは捨てる」: おりポス単発運用のため、
    # リプ欄への誘導行 (_REPLY_POINTER) は付けない。reply_text は
    # 任意で手動リプする時のコピー元としてのみ残す。
    reply_text = f"{reply_body}\n{link}".strip()
    return {
        "ok": True,
        "post_status": material.get("status") or "",
        "share_type": share_type,
        "main_text": main_text,
        "reply_text": reply_text,
        "article_url": link,
        "image_url": material.get("image_url") or "",
        "used_llm": used_llm,
        "main_weighted": x_weighted_len(main_text),
        "reply_weighted": x_weighted_len(reply_text),
    }


def _build_drafts_llm(
    title: str, body: str, share_type: str, *, gemini_api_key: str
) -> tuple[str, str, str]:
    """(hook, summary, reply_body)。全ゲート通過分のみ返す (不合格は空 tuple)。"""
    from google import genai

    from src.x_post_branding_gen import (
        _X_POST_DATA_LLM_MODEL,
        _extract_unverified_numbers,
        _x_post_generate_content,
    )

    # 【関連記事】以降は別話題のタイトル群 = hallucination 源なので LLM に渡さない
    lead = body.split("【関連記事】")[0][:2500]
    verified_text = f"{title} {lead}"
    hook_style = _HOOK_STYLE.get(share_type, _HOOK_STYLE["news"])
    prompt = "\n".join([
        "あなたは読売ジャイアンツ専門メディア「ヨシラバー」のX担当編集者です。",
        "自社記事のX共有ポストの部品を3つ作ってください。",
        "投稿はこちらで次の形に組み立てます (タイトル行はこちらで入れるので書かない):",
        "",
        "<フック 1行>",
        "<記事タイトル（媒体名）>",
        "<要約 1〜2文>",
        "",
        "【フック (HOOK)】",
        f"- 15〜28字、1文。タイムラインで手を止めさせる「ヨシラバーの見立て」。{hook_style}",
        "- 断定で言い切る。タイトルの言葉をそのまま繰り返さない。要約の先取りもしない。",
        "- 狙いはバズ。実測で一番伸びるのは「争点を立てて立場を言い切る」型"
        " (例: レギュラー争い・起用論で どちらが今勝っているかを明言)。"
        "無難なまとめ・両論併記・当たり障りのない感想のフックは禁止。",
        "- 「〜ですね」「〜してほしい」「注目です」等の優等生・実況文体は禁止。",
        "- フック内でも選手はフルネーム (井上温大 / 坂本勇人)。姓だけは禁止。",
        "",
        "【本文 (SUMMARY)】",
        "- 300〜600字。プレミアム長文ポスト前提 (2026-07-19 user「もう少し長くてよい」)。**発言引用が主役** "
        "(雑誌・インタビュー記事の共有が中心のため、読者が読みたいのは本人の言葉)。",
        "- 記事中で**一番強い発言を1個だけ**『』で**一文丸ごと長めに**そのまま引用する"
        " (語尾の改変・切り貼りで意味を変えるのは禁止。要約引用も禁止)。",
        "- 引用は**感情が動く発言**を最優先で選ぶ (悔しさ・本音・宣言・喜び・怒り)。"
        "ビジネス論・処世訓・優等生コメントは伸びない (実測) ので選ばない。",
        "- 記事に争点・対立構図があるなら最初の段落で構図を立てる (誰と誰が何を"
        "争っているか、何が懸かった場面か)。立場は事実と発言の選び方で示す"
        " (記事に無い断定・捏造はしない)。",
        "- ★2個目以降の発言は本文に載せない (記事側に残す = 読者が記事を開く理由)。"
        "残りの発言が記事にあることは、内容を明かさず存在だけ匂わせてよい"
        " (例:「〜については本人がさらに踏み込んで語っている」)。",
        "- 地の文は引用をつなぐ最小限にする (誰が・どんな流れ・何についての発言か)。"
        "記者の地の文をコピーするのは禁止 (引用してよいのは『』の発言のみ)。",
        "- 発言が無い記事 (データ・戦評など) では引用を作らず、記事中の数字・成績・"
        "スコアをそのまま具体的に載せる (記事に無い数字・事実は書かない)。",
        "- 登場する選手・監督・コーチは全員フルネーム敬称なしで名指しする"
        " (検索で見つかるためのキーワード。「巨人」または「ジャイアンツ」も本文に自然に1回入れる)。",
        "- 読みやすさ: 1〜2文ごとに空行 (\\n\\n) で段落を分ける。引用『』は地の文に"
        "埋めず改行して独立させる。一番強い発言・事実を最初の段落に置き、"
        "スマホで流し読みしても目が止まる形にする。",
        "- 煽り・ポエム・「〜に注目」等の実況文体は禁止。事実と発言で書く。",
        "",
        "【リプ (REPLY、おりポスへの返信。末尾に記事URLが自動で付く)】",
        "- 50〜100字、1〜2文。おりポスの続きとして自然に読める文。",
        "- 前半: 記事にしか無い残りの要素を1つ、答え・結末・発言の中身そのものは"
        "書かずに具体的に予告する (「何について語ったか」までは書き、「何と言ったか」"
        "は記事側に残す)。**本文に載せなかった2個目以降の発言があるなら、それを"
        "最優先で予告する**。読者が記事を開かないと解消しないフックにする。",
        "- 後半: その続き・詳細が下の記事に載っていることが伝わる一言で自然に締める"
        " (例:「〜までの一部始終は記事で」「〜の中身も記事にまとめた」。"
        "毎回同じ言い回しは避けて記事の中身に合わせて変える)。",
        "- チラ見せの無い『続きはこちら』『チェック』だけの誘導文は禁止。URL は書かない。",
        "- 「今後も止まりません」「目が離せません」のような誇張・ポエム・煽り締めは禁止。",
        "",
        "【共通・日本語品質】",
        "- 完結した自然な日本語。翻訳調・不自然な体言止めの連発・意味の通らない比喩は禁止。",
        "- URL・ハッシュタグ・媒体名・絵文字は書かない。",
        "- 選手はフルネーム敬称なし (坂本勇人 / 岡本和真)。",
        "",
        "出力形式 (この3行ラベルを必ず使う):",
        "HOOK: <フック>",
        "SUMMARY: <要約 (改行は\\nで)>",
        "REPLY: <リプ本文>",
        "",
        f"記事タイトル: {title}",
        "記事本文:",
        lead,
    ])
    client = genai.Client(api_key=gemini_api_key)
    for attempt in range(2):
        response = _x_post_generate_content(
            client,
            model=_X_POST_DATA_LLM_MODEL,
            contents=prompt if attempt == 0 else (
                prompt + "\n\n※前回は形式違反・タイトルの繰り返し・記事に無い数字の"
                "いずれかがあった。ラベル形式と各ルールを厳守。"
            ),
            config={"temperature": 0.6},
        )
        raw = (getattr(response, "text", None) or "").strip()
        hook, summary, reply_body = _parse_labeled_output(raw)
        if not hook or not summary or not reply_body:
            continue
        combined = f"{hook}\n{summary}\n{reply_body}"
        if _extract_unverified_numbers(combined, verified_text):
            LOG.info("x_share draft gate_fail=unverified_numbers attempt=%d", attempt + 1)
            continue
        if _forbidden_in_post(combined):
            LOG.info(
                "x_share draft gate_fail=%s attempt=%d",
                _forbidden_in_post(combined), attempt + 1,
            )
            continue
        if _hook_echoes_title(hook, title):
            LOG.info("x_share draft gate_fail=hook_echoes_title attempt=%d", attempt + 1)
            continue
        if len(hook) > 40:
            LOG.info("x_share draft gate_fail=hook_too_long attempt=%d", attempt + 1)
            continue
        LOG.info(
            "x_share draft built type=%s hook_len=%d summary_len=%d reply_len=%d",
            share_type, len(hook), len(summary), len(reply_body),
        )
        return hook, summary, reply_body
    return "", "", ""


def _parse_labeled_output(raw: str) -> tuple[str, str, str]:
    """HOOK / SUMMARY / REPLY の3ラベルを取り出す。HOOK とリプは1行に潰す。"""
    out = {}
    for label in ("HOOK", "SUMMARY", "REPLY"):
        m = re.search(rf"{label}:\s*(.+?)(?=\n[A-Z]+:|\Z)", raw, re.DOTALL)
        if m:
            out[label] = m.group(1).strip().replace("\\n", "\n")
    hook = " ".join(out.get("HOOK", "").split())
    summary = out.get("SUMMARY", "").strip()
    reply_body = " ".join(out.get("REPLY", "").split())
    return hook, summary, reply_body


def _hook_echoes_title(hook: str, title: str) -> bool:
    """フックがタイトルの言い直しになっていないか (10字窓の一致で判定)。"""
    h = re.sub(r"\s", "", hook or "")
    t = re.sub(r"\s", "", title or "")
    if not h:
        return True
    for i in range(max(1, len(h) - 9)):
        window = h[i:i + 10]
        if len(window) == 10 and window in t:
            return True
    return False


def _trim_to_budget_sentences(text: str, budget: int) -> str:
    """weighted budget に収まるまで末尾の文から削る。"""
    if x_weighted_len(text) <= budget:
        return text
    sentences = [s for s in re.split(r"(?<=。)", text) if s]
    while sentences:
        sentences.pop()
        candidate = "".join(sentences).strip()
        if candidate and x_weighted_len(candidate) <= budget:
            return candidate
    return ""


# 2026-07-14 user「おりポスとリプにして明らかにクリック減った。工夫できない」:
# URL はリプ欄にあるのに、本文からリプ欄への誘導が無く、リプを開かない読者には
# 導線ゼロだった。本文の最終行で必ずリプ欄を指す (URL は本文に書かない = リーチ維持)。
_REPLY_POINTER = "続きはリプ欄の記事から"


def _assemble_main(title_line: str, hook: str, summary: str) -> str:
    """フック → タイトル行 → 本文。超過時は本文を文単位で切り詰めてから間引く。

    上限は _main_weighted_limit() (Premium 長文、default 900 weighted)。
    (2026-07-19 リプ誘導行の付与を廃止したため、予約は本文分のみ。)
    """
    limit = _main_weighted_limit()
    if hook and summary:
        head = f"{hook}\n\n{title_line}\n\n"
        trimmed = _trim_to_budget_sentences(
            summary,
            limit - x_weighted_len(head),
        )
        if trimmed != summary:
            LOG.info("x_share assemble summary_trimmed to fit weighted limit")
        summary = trimmed
    candidates = [
        "\n\n".join(p for p in (hook, title_line, summary) if p),
        "\n".join(p for p in (hook, title_line, summary) if p),
        "\n\n".join(p for p in (hook, title_line) if p),
        title_line,
    ]
    for text in candidates:
        if text and x_weighted_len(text) <= limit:
            return text
    # title_line 単体でも超過する異常系: 文字境界で切り詰め
    text = title_line
    while text and x_weighted_len(text + "…") > limit:
        text = text[:-1]
    return f"{text}…" if text else title_line


def _build_drafts_fallback(title_line: str, body: str) -> tuple[str, str]:
    """LLM なし fallback: タイトル（媒体名）+ 記事冒頭数文 (数字捏造リスクゼロ)。

    2026-07-07 長文化: Premium 上限内で記事冒頭 3 文まで載せる (キーワード・
    情報量を確保。文はすべて記事 literal なので検証不要)。
    """
    lead_sentences = [s.strip() for s in re.split(r"[。\n]", body) if s.strip()][:3]
    main_text = title_line
    if lead_sentences:
        lead_block = "。".join(lead_sentences) + "。"
        main_text = f"{title_line}\n{lead_block}"
    if x_weighted_len(main_text) > _main_weighted_limit():
        main_text = _assemble_main(title_line, "", "")
    reply_body = "ここに載せきれなかった経緯や数字は、下の記事で全部読めます。"
    return main_text, reply_body


def post_thread(
    main_text: str,
    reply_text: str,
    *,
    image_url: str = "",
    data_text: str = "",
) -> dict:
    """おりポス (画像付き) → [dataリプ] → 自分へのリプ (URL付き) の連続投稿。

    画像 upload 失敗は致命にしない (画像なしで本文投稿を続行し、結果に明記)。
    ``data_text`` (2026-07-07 試合後スレ): 非空なら main と URL リプの間に
    1 本挟み、 main→data→reply の直列ツリーにする。
    """
    from src import x_api_client as _xc

    client = _xc.get_client()
    media_ids: Optional[list] = None
    image_attached = False
    image_error = ""
    if image_url:
        try:
            media_ids = [_upload_media_from_url(image_url)]
            image_attached = True
        except Exception as exc:  # noqa: BLE001 - 画像なしで続行
            LOG.warning("x_share media upload failed: %r", exc)
            image_error = repr(exc)
            media_ids = None
    main_kwargs = {"text": main_text}
    if media_ids:
        main_kwargs["media_ids"] = media_ids
    main_resp = client.create_tweet(**main_kwargs)
    main_id = _tweet_id(main_resp)
    if not main_id:
        raise RuntimeError(f"main tweet id missing: {main_resp!r}")
    parent_id = main_id
    data_id = ""
    if (data_text or "").strip():
        data_resp = client.create_tweet(
            text=data_text, in_reply_to_tweet_id=parent_id
        )
        data_id = _tweet_id(data_resp)
        if data_id:
            parent_id = data_id
    reply_resp = client.create_tweet(
        text=reply_text, in_reply_to_tweet_id=parent_id
    )
    reply_id = _tweet_id(reply_resp)
    LOG.info(
        "x_share thread posted main_id=%s data_id=%s reply_id=%s image=%s",
        main_id, data_id or "-", reply_id, image_attached,
    )
    return {
        "ok": True,
        "main_tweet_id": main_id,
        "data_tweet_id": data_id,
        "reply_tweet_id": reply_id,
        "image_attached": image_attached,
        "image_error": image_error,
    }


def _tweet_id(resp) -> str:
    try:
        data = getattr(resp, "data", None) or {}
        if isinstance(data, dict):
            return str(data.get("id") or "")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _upload_media_from_url(image_url: str) -> int:
    """アイキャッチ画像を取得して v1.1 media/upload へ。5MB 超は縮小せず拒否。"""
    import os

    import requests
    import tweepy

    resp = requests.get(image_url, timeout=15)
    resp.raise_for_status()
    blob = resp.content
    if not blob:
        raise RuntimeError("empty image body")
    if len(blob) > 5 * 1024 * 1024:
        raise RuntimeError(f"image too large: {len(blob)} bytes")
    auth = tweepy.OAuth1UserHandler(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    api = tweepy.API(auth)
    filename = image_url.rsplit("/", 1)[-1] or "eyecatch.jpg"
    media = api.media_upload(filename=filename, file=io.BytesIO(blob))
    media_id = getattr(media, "media_id", None)
    if not media_id:
        raise RuntimeError(f"media_id missing: {media!r}")
    return int(media_id)
