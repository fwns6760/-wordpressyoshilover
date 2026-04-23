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
from typing import Any, Callable, Mapping, Sequence


SVG_CONTENT_TYPE = "image/svg+xml"
_DRAFT_STATUSES = {"", "draft", "pending", "future", "auto-draft"}
_IMAGE_METADATA_KEYS = (
    "featured_media",
    "featured_media_id",
    "featured_image",
    "featured_image_id",
    "featured_image_url",
    "eyecatch",
    "eyecatch_id",
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
class LayoutSpec:
    layout_key: str
    label: str
    accent: str
    extractor: Callable[[str, str, Mapping[str, Any]], tuple[str, tuple[str, ...]]]


@dataclass(frozen=True)
class StructuredEyecatch:
    layout_key: str
    label: str
    headline: str
    detail_lines: tuple[str, ...]
    filename: str
    content_type: str
    image_bytes: bytes


def _extract_program_layout(title: str, body_html: str, metadata: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    program_name = _first_nonempty(
        str(metadata.get("program_name") or ""),
        str(metadata.get("program_title") or ""),
        _extract_program_name(title, body_html, str(metadata.get("program_slug") or "")),
    )
    when = _first_nonempty(
        str(metadata.get("broadcast_datetime") or ""),
        str(metadata.get("air_datetime") or ""),
        str(metadata.get("broadcast_at") or ""),
    )
    if not when:
        air_date = _format_compact_date(str(metadata.get("air_date") or ""))
        time_text = _extract_time_text(title, body_html)
        when = f"{air_date} {time_text}".strip() if air_date else time_text
    return program_name or title, (f"放送日時 {when}" if when else "",)


def _extract_transaction_layout(title: str, body_html: str, metadata: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    subject = _first_nonempty(
        _display_name_list(metadata.get("subject")),
        _display_name_list(metadata.get("player_names")),
        _display_name_list(metadata.get("players")),
    )
    notice_kind = _display_notice_kind(str(metadata.get("notice_kind") or metadata.get("transaction_type") or ""))
    if not notice_kind:
        notice_kind = _extract_notice_kind_text(title, body_html)
    notice_date = _format_compact_date(str(metadata.get("notice_date") or metadata.get("date") or ""))
    return subject or title, tuple(line for line in (notice_kind, notice_date) if line)


def _extract_probable_starter_layout(title: str, body_html: str, metadata: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    matchup = _first_nonempty(
        str(metadata.get("matchup") or ""),
        _extract_matchup(title, body_html, str(metadata.get("game_id") or "")),
    )
    pitchers = _first_nonempty(
        _display_name_list(metadata.get("pitcher_names")),
        _display_name_list(metadata.get("probable_starters")),
        _extract_pitcher_line(title, body_html),
    )
    return matchup or title, (f"投手 {pitchers}" if pitchers else "",)


def _extract_comment_layout(title: str, body_html: str, metadata: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    speaker = str(metadata.get("speaker") or metadata.get("speaker_name") or "").strip()
    scene = _first_nonempty(
        str(metadata.get("scene") or ""),
        str(metadata.get("short_heading") or ""),
        str(metadata.get("comment_scene") or ""),
        _extract_comment_heading(title, speaker),
    )
    return speaker or title, (scene,)


def _extract_injury_layout(title: str, body_html: str, metadata: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    subject = _first_nonempty(
        str(metadata.get("player_name") or ""),
        str(metadata.get("subject") or ""),
    )
    status = _first_nonempty(
        _display_injury_status(str(metadata.get("injury_status") or "")),
        str(metadata.get("status_text") or ""),
        str(metadata.get("injury_summary") or ""),
    )
    return subject or title, (status,)


def _extract_postgame_layout(title: str, body_html: str, metadata: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    matchup = _first_nonempty(
        str(metadata.get("matchup") or ""),
        _extract_matchup(title, body_html, str(metadata.get("game_id") or "")),
    )
    score = _first_nonempty(
        str(metadata.get("score") or ""),
        _extract_score_text(title, body_html),
        _display_result_token(str(metadata.get("result_token") or "")),
    )
    return matchup or title, (score,)


LAYOUT_SPECS: dict[str, LayoutSpec] = {
    "fact_notice_program": LayoutSpec(
        layout_key="fact_notice_program",
        label="番組情報",
        accent="#f5811f",
        extractor=_extract_program_layout,
    ),
    "fact_notice_transaction": LayoutSpec(
        layout_key="fact_notice_transaction",
        label="公示",
        accent="#6b7280",
        extractor=_extract_transaction_layout,
    ),
    "probable_starter": LayoutSpec(
        layout_key="probable_starter",
        label="予告先発",
        accent="#003da5",
        extractor=_extract_probable_starter_layout,
    ),
    "comment_notice": LayoutSpec(
        layout_key="comment_notice",
        label="コメント",
        accent="#f59e0b",
        extractor=_extract_comment_layout,
    ),
    "injury_notice": LayoutSpec(
        layout_key="injury_notice",
        label="怪我状況",
        accent="#dc2626",
        extractor=_extract_injury_layout,
    ),
    "postgame_result": LayoutSpec(
        layout_key="postgame_result",
        label="試合結果",
        accent="#ea580c",
        extractor=_extract_postgame_layout,
    ),
}


def build_structured_eyecatch(candidate: Any) -> StructuredEyecatch | None:
    metadata = _candidate_metadata(candidate)
    if not _is_draft_like_candidate(candidate, metadata):
        return None
    if has_existing_eyecatch(_candidate_image_metadata(candidate, metadata)):
        return None

    title = _candidate_title(candidate)
    body_html = _candidate_body_html(candidate)

    layout = _build_layout(candidate, title=title, body_html=body_html, metadata=metadata)
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


def generate(draft: Any) -> StructuredEyecatch | None:
    """Generate a structured eyecatch for a Draft-like object if eligible."""
    return build_structured_eyecatch(draft)


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
    merged: dict[str, Any] = {}
    if isinstance(candidate, Mapping):
        for key in ("meta", "metadata"):
            value = candidate.get(key)
            if isinstance(value, Mapping):
                merged.update(dict(value))
        return merged
    metadata = getattr(candidate, "metadata", {}) or {}
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _candidate_image_metadata(candidate: Any, metadata: Mapping[str, Any]) -> dict[str, Any]:
    image_metadata = dict(metadata)
    if isinstance(candidate, Mapping):
        for key in _IMAGE_METADATA_KEYS:
            if key in candidate:
                image_metadata[key] = candidate.get(key)
        return image_metadata
    for key in _IMAGE_METADATA_KEYS:
        if hasattr(candidate, key):
            image_metadata[key] = getattr(candidate, key)
    return image_metadata


def _is_draft_like_candidate(candidate: Any, metadata: Mapping[str, Any]) -> bool:
    status = str(metadata.get("status") or "").strip().lower()
    if isinstance(candidate, Mapping):
        status = str(candidate.get("status") or status).strip().lower()
    else:
        status = str(getattr(candidate, "status", "") or status).strip().lower()
    return status in _DRAFT_STATUSES


def _candidate_title(candidate: Any) -> str:
    raw = candidate.get("title") if isinstance(candidate, Mapping) else getattr(candidate, "title", "")
    if isinstance(raw, Mapping):
        raw = raw.get("raw") or raw.get("rendered") or ""
    return _normalize_display_text(str(raw or ""))


def _candidate_body_html(candidate: Any) -> str:
    if isinstance(candidate, Mapping):
        raw = candidate.get("body_html") or candidate.get("content") or ""
    else:
        raw = getattr(candidate, "body_html", "")
    if isinstance(raw, Mapping):
        raw = raw.get("raw") or raw.get("rendered") or ""
    return str(raw or "").strip()


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


def _build_layout(candidate: Any, *, title: str, body_html: str, metadata: Mapping[str, Any]) -> dict[str, Any] | None:
    spec = _resolve_layout_spec(candidate, metadata)
    if spec is None:
        return None
    headline, detail_lines = spec.extractor(title, body_html, metadata)
    return _layout(
        layout_key=spec.layout_key,
        label=spec.label,
        headline=headline,
        detail_lines=detail_lines,
        accent=spec.accent,
    )


def _resolve_layout_spec(candidate: Any, metadata: Mapping[str, Any]) -> LayoutSpec | None:
    family = str(metadata.get("family") or metadata.get("article_type") or "").strip()
    if not family and not isinstance(candidate, Mapping):
        family = str(getattr(candidate, "family", "") or "").strip()
    subtype = str(metadata.get("subtype") or metadata.get("article_subtype") or "").strip()
    tags = _candidate_tags(candidate, metadata)

    if family == "program_notice" or (subtype == "fact_notice" and "番組" in tags):
        return LAYOUT_SPECS["fact_notice_program"]
    if family == "transaction_notice" or (subtype == "fact_notice" and "公示" in tags):
        return LAYOUT_SPECS["fact_notice_transaction"]
    if (
        family in {"probable_pitcher", "probable_starter"}
        or subtype == "probable_starter"
        or (subtype == "pregame" and "予告先発" in tags)
    ):
        return LAYOUT_SPECS["probable_starter"]
    if family == "comment_notice" or subtype == "comment_notice":
        return LAYOUT_SPECS["comment_notice"]
    if family == "injury_notice" or subtype == "injury_notice":
        return LAYOUT_SPECS["injury_notice"]
    if family in {"postgame", "postgame_result"} or subtype in {"postgame", "postgame_result"}:
        return LAYOUT_SPECS["postgame_result"]
    return None


def _candidate_tags(candidate: Any, metadata: Mapping[str, Any]) -> tuple[str, ...]:
    raw = metadata.get("tags")
    if raw is None and isinstance(candidate, Mapping):
        raw = candidate.get("tags")
    if isinstance(raw, str):
        return tuple(tag.strip() for tag in re.split(r"[,、\s]+", raw) if tag.strip())
    if isinstance(raw, Sequence):
        return tuple(str(tag).strip() for tag in raw if str(tag).strip())
    return ()


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
    seed = str(metadata.get("candidate_key") or _candidate_title(candidate) or layout_key)
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


def _display_name_list(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        names = [name.strip() for name in re.split(r"[+＋、,／/]+", value) if name.strip()]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        names = [str(name).strip() for name in value if str(name).strip()]
    else:
        names = [str(value).strip()] if str(value).strip() else []
    return " / ".join(_normalize_display_text(name) for name in names if _normalize_display_text(name))


def _display_subjects(subject: str) -> str:
    return _display_name_list(subject)


def _display_notice_kind(value: str) -> str:
    mapping = {
        "register": "出場選手登録",
        "deregister": "登録抹消",
        "register_deregister": "登録 / 抹消",
    }
    return mapping.get((value or "").strip(), _normalize_display_text(value))


def _extract_notice_kind_text(title: str, body_html: str) -> str:
    combined = "\n".join(part for part in (title, _strip_html(body_html)) if part)
    has_register = any(token in combined for token in ("登録", "昇格"))
    has_deregister = any(token in combined for token in ("抹消", "降格"))
    if has_register and has_deregister:
        return "登録 / 抹消"
    if has_register:
        return "出場選手登録"
    if has_deregister:
        return "登録抹消"
    return ""


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
        return ""
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
