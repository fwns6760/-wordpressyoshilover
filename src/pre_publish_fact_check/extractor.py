from __future__ import annotations

import html
import re
from typing import Any


URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SOURCE_BLOCK_RE = re.compile(r"(参照元\s*[：:]\s*[\s\S]*)$", re.MULTILINE)
SCORE_RE = re.compile(r"\d+-\d+")
COACH_COMMENT_C_RE = re.compile(r"(?<![A-Za-zＡ-Ｚａ-ｚ])(?:Ｃ|C)(?![A-Za-zＡ-Ｚａ-ｚ])")
PITCHER_FOCUS_K_RE = re.compile(r"(?:[0-9０-９]+[KＫ]|(?<![A-Za-zＡ-Ｚａ-ｚ])(?:K|Ｋ)(?![A-Za-zＡ-Ｚａ-ｚ]))")

FARM_KEYWORDS = ("二軍", "2軍", "２軍", "ファーム")
ROSTER_MOVE_KEYWORDS = ("昇格", "合流", "帯同")
ROSTER_MOVE_EXCLUSION_KEYWORDS = ("抹消", "故障", "離脱")
BATTER_FOCUS_KEYWORDS = ("猛打賞", "マルチ安打", "適時打", "決勝打", "初安打")
PITCHER_FOCUS_KEYWORDS = ("完封", "降板", "奪三振", "無失点", "先発投手")
PROMOTIONAL_EVENT_KEYWORDS = ("Ｔシャツ", "グッズ", "ＣＬＵＢ ＧＩＡＮＴＳ", "CLUB GIANTS", "会員限定", "販売開始")
QUOTE_CHARS = ("「", "」", "『", "』")


def _title_value(post: dict[str, Any]) -> str:
    title = (post or {}).get("title")
    if isinstance(title, dict):
        raw = title.get("raw")
        if raw:
            return str(raw)
        rendered = title.get("rendered")
        if rendered:
            return html.unescape(str(rendered))
    if isinstance(title, str):
        return html.unescape(title)
    return ""


def _body_html_value(post: dict[str, Any]) -> str:
    content = (post or {}).get("content")
    if isinstance(content, dict):
        raw = content.get("raw")
        if raw:
            return str(raw)
        rendered = content.get("rendered")
        if rendered:
            return str(rendered)
    if isinstance(content, str):
        return content
    return ""


def _body_text_value(body_html: str) -> str:
    text = TAG_RE.sub("\n", body_html or "")
    text = html.unescape(text).replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _extract_source_urls(body_html: str) -> list[str]:
    urls: list[str] = []
    for url in URL_RE.findall(body_html or ""):
        if url not in urls:
            urls.append(url)
    return urls


def _extract_source_block(body_html: str) -> str | None:
    body_text = _body_text_value(body_html)
    match = SOURCE_BLOCK_RE.search(body_text)
    if not match:
        return None
    return match.group(1).strip() or None


def _contains_any(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)


def _has_quote_signal(value: str) -> bool:
    return any(quote in value for quote in QUOTE_CHARS)


def _is_coach_comment_title(value: str) -> bool:
    if not _has_quote_signal(value):
        return False
    return "監督" in value or "コーチ" in value or bool(COACH_COMMENT_C_RE.search(value))


def _is_roster_move_title(value: str) -> bool:
    if not _contains_any(value, ROSTER_MOVE_KEYWORDS):
        return False
    return not _contains_any(value, ROSTER_MOVE_EXCLUSION_KEYWORDS)


def _is_pitcher_focus_title(value: str) -> bool:
    return _contains_any(value, PITCHER_FOCUS_KEYWORDS) or bool(PITCHER_FOCUS_K_RE.search(value))


def infer_subtype(title: str) -> str:
    value = title or ""
    if value.startswith("巨人スタメン"):
        return "lineup"
    if "予告先発" in value:
        return "probable_starter"
    if _contains_any(value, FARM_KEYWORDS):
        return "farm"
    if _is_roster_move_title(value):
        return "notice"
    if "公示" in value:
        return "notice"
    if _is_coach_comment_title(value):
        return "comment"
    if value.startswith("【コメント】") or ("コメント" in value and "試合" in value):
        return "comment"
    if "故障" in value or "離脱" in value or "登録抹消" in value:
        return "injury"
    if _contains_any(value, BATTER_FOCUS_KEYWORDS):
        return "postgame"
    if _is_pitcher_focus_title(value):
        return "postgame"
    if "試合終了" in value or "勝利" in value or "敗戦" in value or SCORE_RE.search(value):
        return "postgame"
    if value.startswith("明日") or value.startswith("試合前"):
        return "pregame"
    if "テレビ" in value or "ラジオ" in value or "出演" in value or "放送" in value:
        return "program"
    if _contains_any(value, PROMOTIONAL_EVENT_KEYWORDS):
        return "off_field"
    return "other"


def extract_post_record(post: dict[str, Any]) -> dict[str, Any]:
    title = _title_value(post)
    body_html = _body_html_value(post)
    categories = (post or {}).get("categories") or []
    tags = (post or {}).get("tags") or []
    return {
        "post_id": int((post or {}).get("id")),
        "title": title,
        "body_html": body_html,
        "body_text": _body_text_value(body_html),
        "source_urls": _extract_source_urls(body_html),
        "source_block": _extract_source_block(body_html),
        "created_at": str((post or {}).get("date") or ""),
        "modified_at": str((post or {}).get("modified") or ""),
        "categories": [int(value) for value in categories],
        "tags": [int(value) for value in tags],
        "inferred_subtype": infer_subtype(title),
    }


def _fetch_latest_drafts(wp_client, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    posts: list[dict[str, Any]] = []
    per_page = min(limit, 50)
    page = 1
    while len(posts) < limit:
        page_posts = wp_client.list_posts(
            status="draft",
            per_page=per_page,
            page=page,
            orderby="modified",
            order="desc",
            context="edit",
        )
        if not page_posts:
            break
        posts.extend(page_posts)
        if len(page_posts) < per_page:
            break
        page += 1
    return posts[:limit]


def extract_posts(
    wp_client,
    *,
    post_id: int | None = None,
    latest_drafts: int | None = None,
) -> list[dict[str, Any]]:
    if (post_id is None) == (latest_drafts is None):
        raise ValueError("exactly one of post_id or latest_drafts is required")
    if post_id is not None:
        return [extract_post_record(wp_client.get_post(post_id))]
    return [extract_post_record(post) for post in _fetch_latest_drafts(wp_client, int(latest_drafts or 0))]
