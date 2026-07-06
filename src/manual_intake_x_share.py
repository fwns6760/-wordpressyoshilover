"""manual_intake_x_share.py — 手動アプリの「記事をXで共有」ロジック (2026-07-06 user GO)。

狙い (user 決定):
- 記事URLをおりポスに貼ると X の外部リンク抑制でインプが下がる
- おりポス = フック1行 (ヨシラバーの見立て) + 記事タイトル（媒体名） + 要約 (URLなし)
  + アイキャッチ画像のネイティブ添付 (2026-07-06 v2「記事のポストと分かる形」)
- タイトル行は code で literal 組み立て (LLM はフック/要約/リプの3部品のみ生成)
- リプ = 記事の続きのような1〜2文 + 記事URL (URLはリプに退避)
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
        "- 「〜ですね」「〜してほしい」「注目です」等の優等生・実況文体は禁止。",
        "- フック内でも選手はフルネーム (井上温大 / 坂本勇人)。姓だけは禁止。",
        "",
        "【要約 (SUMMARY)】",
        "- 45〜70字、1〜2文。タイトルが約束している中身 (理由・背景・根拠) への答えを"
        "記事本文から拾い、読んだだけで完結させる。",
        "- 記事に無い数字・事実は書かない。煽り・ポエム禁止。",
        "",
        "【リプ (REPLY、おりポスへの返信。末尾に記事URLが自動で付く)】",
        "- 40〜80字、1〜2文。おりポスの続きとして自然に読める文。",
        "- 記事にしか無い残りの要素 (経緯・追加データ・次の見どころ) を1つ示す。",
        "- 『こちら』『チェック』のような誘導語だけにしない。URL は書かない。",
        "- 「今後も止まりません」「目が離せません」のような誇張・ポエム・煽り締めは禁止。"
        "事実と観察で締める。",
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


def _assemble_main(title_line: str, hook: str, summary: str) -> str:
    """フック → タイトル行 → 要約。超過時は要約を文単位で切り詰めてから間引く。"""
    if hook and summary:
        head = f"{hook}\n\n{title_line}\n\n"
        trimmed = _trim_to_budget_sentences(
            summary, _X_WEIGHTED_LIMIT - x_weighted_len(head)
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
        if text and x_weighted_len(text) <= _X_WEIGHTED_LIMIT:
            return text
    # title_line 単体でも超過する異常系: 文字境界で切り詰め
    text = title_line
    while text and x_weighted_len(text + "…") > _X_WEIGHTED_LIMIT:
        text = text[:-1]
    return f"{text}…" if text else title_line


def _build_drafts_fallback(title_line: str, body: str) -> tuple[str, str]:
    """LLM なし fallback: タイトル（媒体名）+ 記事冒頭1文 (数字捏造リスクゼロ)。"""
    lead_sentences = [s.strip() for s in re.split(r"[。\n]", body) if s.strip()][:2]
    main_text = title_line
    if lead_sentences:
        main_text = f"{title_line}\n{lead_sentences[0]}。"
    if x_weighted_len(main_text) > _X_WEIGHTED_LIMIT:
        main_text = _assemble_main(title_line, "", "")
    reply_body = "試合の流れと背景も含めて記事にまとめています。"
    return main_text, reply_body


def post_thread(
    main_text: str,
    reply_text: str,
    *,
    image_url: str = "",
) -> dict:
    """おりポス (画像付き) → 自分へのリプ (URL付き) の連続投稿。

    画像 upload 失敗は致命にしない (画像なしで本文投稿を続行し、結果に明記)。
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
    reply_resp = client.create_tweet(
        text=reply_text, in_reply_to_tweet_id=main_id
    )
    reply_id = _tweet_id(reply_resp)
    LOG.info(
        "x_share thread posted main_id=%s reply_id=%s image=%s",
        main_id, reply_id, image_attached,
    )
    return {
        "ok": True,
        "main_tweet_id": main_id,
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
