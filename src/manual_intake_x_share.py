"""manual_intake_x_share.py — 手動アプリの「記事をXで共有」ロジック (2026-07-06 user GO)。

狙い (user 決定):
- 記事URLをおりポスに貼ると X の外部リンク抑制でインプが下がる
- おりポス = 記事の価値を出し切る本文 (URLなし) + アイキャッチ画像のネイティブ添付
- リプ = 記事の続きのような1〜2文 + 記事URL (URLはリプに退避)
- 「続きはこちら」だけの空チラ見せは禁止 (おりポス単体で読み物として成立させる)

構成:
- list_recent_published()   最近の公開記事 (WP REST)
- fetch_article_material()  記事本文 + アイキャッチURL
- build_share_drafts()      型判定 (comment/data/news) + おりポス案 / リプ案 (flash-lite)
- post_thread()             media upload → おりポス → 自分へのリプ (in_reply_to)

安全側:
- 記事に無い数字は _extract_unverified_numbers で棄却 (LLM 失敗時は deterministic fallback)
- 本文に URL / ハッシュタグ / 媒体名を入れない
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

# 型ごとの LLM 指示 (おりポス)。共通: URLなし / ハッシュタグなし / 媒体名なし /
# 記事に無い数字禁止 / 選手はフルネーム敬称なし / 空チラ見せ禁止。
_MAIN_STYLE = {
    "comment": (
        "型: 選手・首脳陣コメント記事。\n"
        "- 1行目: 発言が出た状況を短く (〜30字)。\n"
        "- 2行目以降: 本人のセリフを『』で出し切る (記事内の発言を literal に、"
        "長すぎる時は文の切れ目で自然に短縮)。\n"
        "- 最後に1行だけヨシラバーの評価・読みを足す (数字根拠か観察、優等生締め禁止)。"
    ),
    "data": (
        "型: データ・記録記事。\n"
        "- 1行目: 一番強い数字・記録を言い切る (選手フルネーム + 数字)。\n"
        "- 2〜3行目: その数字が何を意味するかを淡白に (記事記載の事実のみ)。\n"
        "- 煽り・ポエム禁止。数字は記事にあるものだけ。"
    ),
    "news": (
        "型: ニュース・速報記事。\n"
        "- 事実を2〜3行でたんぱくに伝える (誰が・何を)。\n"
        "- 最後に1行だけヨシラバーの一言 (巨人ファン視点、短く)。"
    ),
}


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
    }


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
    """おりポス案 + リプ案。LLM 失敗時は deterministic fallback。"""
    title = material.get("title") or ""
    body = material.get("body_text") or ""
    link = material.get("link") or ""
    share_type = classify_share_type(title, body)
    main_text = ""
    reply_body = ""
    used_llm = False
    if gemini_api_key:
        try:
            main_text, reply_body = _build_drafts_llm(
                title, body, share_type, gemini_api_key=gemini_api_key
            )
            used_llm = bool(main_text and reply_body)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("x_share llm draft failed: %r", exc)
    if not main_text:
        main_text, reply_body = _build_drafts_fallback(title, body, share_type)
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
) -> tuple[str, str]:
    from google import genai

    from src.x_post_branding_gen import (
        _X_POST_DATA_LLM_MODEL,
        _extract_unverified_numbers,
        _x_post_generate_content,
    )

    lead = body[:2500]
    verified_text = f"{title} {lead}"
    style = _MAIN_STYLE.get(share_type, _MAIN_STYLE["news"])
    prompt = "\n".join([
        "あなたは読売ジャイアンツ専門メディア「ヨシラバー」のX担当編集者です。",
        "下の自社記事から、X投稿のセット (おりポス + そのリプ) を作ってください。",
        "",
        "【おりポス (メイン投稿)】",
        style,
        "- 80〜130字、2〜4行。読んだだけで価値が完結する内容にする。",
        "- 『続きはこちら』『詳細は記事で』のような誘導だけの文は禁止。",
        "- URL・ハッシュタグ・媒体名・絵文字連打は禁止。絵文字は多くても1個。",
        "- 選手はフルネーム敬称なし (坂本勇人 / 岡本和真)。",
        "- 記事に無い数字・事実は書かない。",
        "",
        "【リプ (おりポスへの返信、末尾に記事URLが自動で付く)】",
        "- 40〜80字、1〜2文。おりポスの続きとして自然に読める文。",
        "- 記事にしか無い残りの要素 (背景・追加データ・次の見どころ) を1つ示す。",
        "- 『こちら』『チェック』のような誘導語だけにしない。URL は書かない。",
        "",
        "出力形式 (この2行ラベルを必ず使う):",
        "MAIN: <おりポス本文 (改行は\\nで)>",
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
                prompt + "\n\n※前回は形式違反か記事に無い数字があった。ラベル形式と数字ルールを厳守。"
            ),
            config={"temperature": 0.6},
        )
        raw = (getattr(response, "text", None) or "").strip()
        main_text, reply_body = _parse_labeled_output(raw)
        if not main_text or not reply_body:
            continue
        combined = f"{main_text}\n{reply_body}"
        if _extract_unverified_numbers(combined, verified_text):
            LOG.info("x_share draft gate_fail=unverified_numbers attempt=%d", attempt + 1)
            continue
        if _forbidden_in_post(combined):
            LOG.info(
                "x_share draft gate_fail=%s attempt=%d",
                _forbidden_in_post(combined), attempt + 1,
            )
            continue
        if x_weighted_len(main_text) > _X_WEIGHTED_LIMIT:
            LOG.info("x_share draft gate_fail=main_too_long attempt=%d", attempt + 1)
            continue
        LOG.info(
            "x_share draft built type=%s main_len=%d reply_len=%d",
            share_type, len(main_text), len(reply_body),
        )
        return main_text, reply_body
    return "", ""


def _parse_labeled_output(raw: str) -> tuple[str, str]:
    main_text, reply_body = "", ""
    m = re.search(r"MAIN:\s*(.+?)(?=\nREPLY:|\Z)", raw, re.DOTALL)
    r = re.search(r"REPLY:\s*(.+)\Z", raw, re.DOTALL)
    if m:
        main_text = m.group(1).strip().replace("\\n", "\n")
    if r:
        reply_body = r.group(1).strip().replace("\\n", "\n").splitlines()
        reply_body = " ".join(line.strip() for line in reply_body if line.strip())
    return main_text, reply_body


def _build_drafts_fallback(title: str, body: str, share_type: str) -> tuple[str, str]:
    """LLM なし fallback: 記事冒頭ベースのたんぱく版 (数字捏造リスクゼロ)。"""
    lead_sentences = [s.strip() for s in re.split(r"[。\n]", body) if s.strip()][:2]
    main_text = title.strip()
    if lead_sentences:
        main_text = f"{title.strip()}\n{lead_sentences[0]}。"
    # weighted 超過なら title のみ
    if x_weighted_len(main_text) > _X_WEIGHTED_LIMIT:
        main_text = title.strip()
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
