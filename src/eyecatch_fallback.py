"""Structured eyecatch fallback for Draft-only notice lanes.

The renderer stays pure: it derives SVG bytes from existing candidate facts
without fetching remote resources or mutating global state. Uploading the SVG
into WordPress is handled by the caller.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Any, Mapping


SVG_CONTENT_TYPE = "image/svg+xml"
_IMAGE_METADATA_KEYS = (
    "featured_media",
    "featured_image",
    "featured_image_id",
    "featured_image_url",
    "featured_image_urls",
    "image_url",
    "image_urls",
    "hero_image_url",
    "hero_image",
    "media_url",
    "thumbnail_url",
    "thumbnail_urls",
    "og_image_url",
    "og_image",
    "eyecatch",
    "eyecatch_url",
    "eyecatch_image_url",
)
_TEAM_CODE_NAMES = {
    "t": "阪神",
    "db": "DeNA",
    "c": "広島",
    "d": "中日",
    "s": "ヤクルト",
    "b": "オリックス",
    "m": "ロッテ",
    "e": "楽天",
    "h": "ソフトバンク",
    "f": "日本ハム",
    "l": "西武",
    "ht": "ハヤテ",
}
_TEAM_DISPLAY_NAMES = tuple(
    dict.fromkeys(
        [
            "巨人",
            "阪神",
            "DeNA",
            "中日",
            "広島",
            "ヤクルト",
            "オリックス",
            "ロッテ",
            "楽天",
            "ソフトバンク",
            "日本ハム",
            "西武",
            "ハヤテ",
        ]
    )
)
_SCORE_TOKEN_RE = re.compile(r"(\d{1,2})\s*[-－–]\s*(\d{1,2})")
_TIME_RE = re.compile(r"(\d{1,2}:\d{2})")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[\s　]+")


@dataclass(frozen=True)
class StructuredEyecatch:
    layout_key: str
    label: str
    headline: str
    detail_lines: tuple[str, ...]
    filename: str
    content_type: str
    image_bytes: bytes


def build_structured_eyecatch(candidate: Any) -> StructuredEyecatch | None:
    metadata = _candidate_metadata(candidate)
    if has_existing_eyecatch(metadata):
        return None

    family = str(metadata.get("family") or metadata.get("article_type") or getattr(candidate, "family", "")).strip()
    title = str(getattr(candidate, "title", "") or "").strip()
    body_html = str(getattr(candidate, "body_html", "") or "").strip()

    layout = _build_layout(family, title=title, body_html=body_html, metadata=metadata)
    if layout is None:
        return None

    svg_text = _render_svg(layout["label"], layout["headline"], layout["detail_lines"], accent=layout["accent"])
    filename = _build_filename(candidate, layout["layout_key"])
    return StructuredEyecatch(
        layout_key=layout["layout_key"],
        label=layout["label"],
        headline=layout["headline"],
        detail_lines=tuple(layout["detail_lines"]),
        filename=filename,
        content_type=SVG_CONTENT_TYPE,
        image_bytes=svg_text.encode("utf-8"),
    )


def maybe_generate_structured_eyecatch_media(wp: Any, candidate: Any) -> int:
    uploader = getattr(wp, "upload_generated_image", None)
    if uploader is None:
        return 0
    structured = build_structured_eyecatch(candidate)
    if structured is None:
        return 0
    return int(
        uploader(
            structured.image_bytes,
            filename=structured.filename,
            content_type=structured.content_type,
        )
        or 0
    )


def has_existing_eyecatch(metadata: Mapping[str, Any] | None) -> bool:
    metadata = metadata or {}
    for key in _IMAGE_METADATA_KEYS:
        if _has_image_value(metadata.get(key)):
            return True
    return False


def _candidate_metadata(candidate: Any) -> dict[str, Any]:
    metadata = getattr(candidate, "metadata", {}) or {}
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _has_image_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_has_image_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_image_value(item) for item in value)
    return False


def _build_layout(family: str, *, title: str, body_html: str, metadata: Mapping[str, Any]) -> dict[str, Any] | None:
    if family == "program_notice":
        program_name = _extract_program_name(title, body_html, str(metadata.get("program_slug") or ""))
        air_date = _format_compact_date(str(metadata.get("air_date") or ""))
        time_text = _extract_time_text(title, body_html)
        when = f"{air_date} {time_text}".strip() if air_date else time_text
        return _layout(
            layout_key="fact_notice_program",
            label="番組情報",
            headline=program_name or title,
            detail_lines=(f"放送日時 {when}" if when else air_date or _strip_html(body_html),),
            accent="#f5811f",
        )
    if family == "transaction_notice":
        subject = _display_subjects(str(metadata.get("subject") or ""))
        notice_kind = _display_notice_kind(str(metadata.get("notice_kind") or ""))
        notice_date = _format_compact_date(str(metadata.get("notice_date") or ""))
        return _layout(
            layout_key="fact_notice_transaction",
            label="公示",
            headline=subject or title,
            detail_lines=tuple(line for line in (notice_kind, notice_date) if line),
            accent="#6b7280",
        )
    if family == "probable_pitcher":
        matchup = _extract_matchup(title, body_html, str(metadata.get("game_id") or ""))
        pitchers = _extract_pitcher_line(title, body_html)
        return _layout(
            layout_key="pregame_probable_pitcher",
            label="予告先発",
            headline=matchup or title,
            detail_lines=(f"先発投手 {pitchers}" if pitchers else _first_nonempty(title, _strip_html(body_html)),),
            accent="#003da5",
        )
    if family == "comment_notice":
        speaker = str(metadata.get("speaker") or "").strip()
        short_heading = _extract_comment_heading(title, speaker)
        return _layout(
            layout_key="comment_notice",
            label="コメント",
            headline=speaker or title,
            detail_lines=(short_heading or title,),
            accent="#f59e0b",
        )
    if family == "injury_notice":
        subject = str(metadata.get("subject") or "").strip()
        status = _display_injury_status(str(metadata.get("injury_status") or ""))
        return _layout(
            layout_key="injury_notice",
            label="故障情報",
            headline=subject or title,
            detail_lines=(status or title,),
            accent="#dc2626",
        )
    if family == "postgame_result":
        matchup = _extract_matchup(title, body_html, str(metadata.get("game_id") or ""))
        score = _extract_score_text(title, body_html)
        if not score:
            score = _display_result_token(str(metadata.get("result_token") or ""))
        return _layout(
            layout_key="postgame_result",
            label="試合結果",
            headline=matchup or title,
            detail_lines=(score or _first_nonempty(title, _strip_html(body_html)),),
            accent="#ea580c",
        )
    return None


def _layout(*, layout_key: str, label: str, headline: str, detail_lines: tuple[str, ...] | list[str], accent: str) -> dict[str, Any] | None:
    headline = _normalize_display_text(headline)
    lines = tuple(_normalize_display_text(line) for line in detail_lines if _normalize_display_text(line))
    if not headline:
        return None
    return {
        "layout_key": layout_key,
        "label": label,
        "headline": headline,
        "detail_lines": lines[:3],
        "accent": accent,
    }


def _build_filename(candidate: Any, layout_key: str) -> str:
    metadata = _candidate_metadata(candidate)
    seed = str(metadata.get("candidate_key") or getattr(candidate, "title", "") or layout_key)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"structured-eyecatch-{layout_key}-{digest}.svg"


def _strip_html(value: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html.unescape(value or ""))
    return _normalize_display_text(text)


def _normalize_display_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", html.unescape(value or "")).strip()


def _extract_program_name(title: str, body_html: str, program_slug: str) -> str:
    cleaned_title = re.sub(r"^\[[^\]]+\]\s*", "", title or "").strip()
    cleaned_title = re.sub(r"\s*(放送予定|配信予定|番組情報)$", "", cleaned_title).strip()
    if cleaned_title:
        return cleaned_title
    program_map = {
        "giants-tv": "ジャイアンツTV",
    }
    if program_slug in program_map:
        return program_map[program_slug]
    body_text = _strip_html(body_html)
    return body_text.split(" ", 1)[0] if body_text else ""


def _extract_time_text(title: str, body_html: str) -> str:
    combined = "\n".join(part for part in (title, _strip_html(body_html)) if part)
    match = _TIME_RE.search(combined)
    return match.group(1) if match else ""


def _format_compact_date(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 8:
        return ""
    return f"{digits[0:4]}.{digits[4:6]}.{digits[6:8]}"


def _display_subjects(subject: str) -> str:
    names = [name.strip() for name in subject.split("+") if name.strip()]
    return " / ".join(names)


def _display_notice_kind(value: str) -> str:
    mapping = {
        "register": "出場選手登録",
        "deregister": "登録抹消",
        "register_deregister": "登録 / 抹消",
    }
    return mapping.get((value or "").strip(), _normalize_display_text(value))


def _extract_matchup(title: str, body_html: str, game_id: str) -> str:
    combined = "\n".join(part for part in (title, _strip_html(body_html)) if part)
    team_names = [name for name in _TEAM_DISPLAY_NAMES if name in combined and name != "巨人"]
    if team_names:
        return f"巨人 vs {team_names[0]}"
    opponent = _opponent_from_game_id(game_id)
    if opponent:
        return f"巨人 vs {opponent}"
    return ""


def _opponent_from_game_id(game_id: str) -> str:
    suffix = str(game_id or "").split("-g-")[-1]
    suffix = suffix.split("-", 1)[0]
    return _TEAM_CODE_NAMES.get(suffix, "")


def _extract_pitcher_line(title: str, body_html: str) -> str:
    combined = "\n".join(part for part in (title, _strip_html(body_html)) if part)
    candidates: list[str] = []
    for pattern in (
        re.compile(r"[#＃]([一-龥ぁ-んァ-ヶA-Za-z・]{2,12})"),
        re.compile(r"([一-龥ぁ-んァ-ヶA-Za-z・]{2,12})投手"),
    ):
        for match in pattern.finditer(combined):
            name = match.group(1).strip()
            if _is_probable_name(name) and name not in candidates:
                candidates.append(name)
    return " / ".join(candidates[:2])


def _is_probable_name(value: str) -> bool:
    blocked = {
        "ジャイアンツ",
        "東京ドーム",
        "甲子園",
        "試合開始予定",
        "予告先発",
        "巨人",
        "阪神",
        "DeNA",
    }
    if value in blocked:
        return False
    return len(value) >= 2


def _extract_comment_heading(title: str, speaker: str) -> str:
    trimmed = title.strip()
    if speaker:
        trimmed = trimmed.replace(speaker, "").strip(" 　-:：")
    if trimmed in {"", "コメント"}:
        return title.strip()
    return trimmed


def _display_injury_status(value: str) -> str:
    mapping = {
        "upper_body": "上半身の状態",
        "lower_body": "下半身の状態",
        "condition_check": "状態確認中",
        "rehab": "リハビリ段階",
        "return": "復帰見込み",
        "absence": "離脱情報",
    }
    normalized = (value or "").strip()
    if normalized in mapping:
        return mapping[normalized]
    return normalized.replace("_", " ").strip()


def _extract_score_text(title: str, body_html: str) -> str:
    combined = "\n".join(part for part in (title, _strip_html(body_html)) if part)
    match = _SCORE_TOKEN_RE.search(combined)
    if not match:
        return ""
    return f"{match.group(1)} - {match.group(2)}"


def _display_result_token(value: str) -> str:
    mapping = {
        "win": "勝利",
        "lose": "敗戦",
        "draw": "引き分け",
    }
    return mapping.get((value or "").strip(), "")


def _first_nonempty(*values: str) -> str:
    for value in values:
        normalized = _normalize_display_text(value)
        if normalized:
            return normalized
    return ""


def _render_svg(label: str, headline: str, detail_lines: tuple[str, ...], *, accent: str) -> str:
    label_lines = _wrap_text(label, max_chars=8, max_lines=1)
    headline_lines = _wrap_text(headline, max_chars=16, max_lines=2)
    detail_wrapped: list[str] = []
    for detail in detail_lines[:3]:
        detail_wrapped.extend(_wrap_text(detail, max_chars=24, max_lines=2))
    detail_wrapped = detail_wrapped[:4]

    line_y = 290
    detail_markup: list[str] = []
    for line in detail_wrapped:
        detail_markup.append(
            f'<text x="92" y="{line_y}" class="detail">{html.escape(line)}</text>'
        )
        line_y += 58

    headline_markup: list[str] = []
    headline_y = 190
    for line in headline_lines:
        headline_markup.append(
            f'<text x="92" y="{headline_y}" class="headline">{html.escape(line)}</text>'
        )
        headline_y += 70

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="structured eyecatch">'
        "<defs>"
        '<linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#111827" />'
        '<stop offset="100%" stop-color="#1f2937" />'
        "</linearGradient>"
        "</defs>"
        "<style>"
        ".label{font-family:'Noto Sans JP','Hiragino Sans','Yu Gothic',sans-serif;font-size:38px;font-weight:700;fill:#111827;}"
        ".headline{font-family:'Noto Sans JP','Hiragino Sans','Yu Gothic',sans-serif;font-size:58px;font-weight:700;fill:#f9fafb;}"
        ".detail{font-family:'Noto Sans JP','Hiragino Sans','Yu Gothic',sans-serif;font-size:42px;font-weight:500;fill:#e5e7eb;}"
        ".subtle{font-family:'Noto Sans JP','Hiragino Sans','Yu Gothic',sans-serif;font-size:28px;font-weight:700;fill:#374151;letter-spacing:6px;}"
        "</style>"
        '<rect width="1200" height="630" fill="url(#bg)" />'
        '<rect x="72" y="70" width="250" height="74" rx="37" fill="'
        + accent
        + '" />'
        + "".join(
            f'<text x="106" y="118" class="label">{html.escape(line)}</text>'
            for line in label_lines
        )
        + '<rect x="72" y="500" width="1056" height="4" fill="'
        + accent
        + '" opacity="0.85" />'
        + '<text x="92" y="560" class="subtle">YOMIURI GIANTS</text>'
        + "".join(headline_markup)
        + "".join(detail_markup)
        + "</svg>"
    )


def _wrap_text(text: str, *, max_chars: int, max_lines: int) -> list[str]:
    normalized = _normalize_display_text(text)
    if not normalized:
        return []
    lines: list[str] = []
    current = ""
    for char in normalized:
        if len(current) >= max_chars:
            lines.append(current)
            current = char
            if len(lines) == max_lines:
                break
            continue
        current += char
    if len(lines) < max_lines and current:
        lines.append(current)
    if len(lines) == max_lines and len("".join(lines)) < len(normalized):
        lines[-1] = lines[-1][:-1] + "…"
    return lines
