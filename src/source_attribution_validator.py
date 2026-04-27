from __future__ import annotations

import html
import re
from typing import Any

try:
    from source_trust import (
        classify_handle_family as _classify_handle_family,
        classify_url as _classify_url,
        classify_url_family as _classify_url_family,
        get_family_trust_level as _get_family_trust_level,
    )
except ImportError:  # pragma: no cover - package import for tests
    from src.source_trust import (
        classify_handle_family as _classify_handle_family,
        classify_url as _classify_url,
        classify_url_family as _classify_url_family,
        get_family_trust_level as _get_family_trust_level,
    )


SPECIAL_REQUIRED_SUBTYPES = {"live_update", "lineup", "fact_notice", "pregame"}
POSTGAME_OPTIONAL_WITH_WEB_SUBTYPES = {"postgame", "farm"}
SOURCE_KIND_LABELS = {
    "official_x": "公式X",
    "official_media_x": "公式媒体X",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[\s　/／・|]+")
_X_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/([^/]+)/status/", re.IGNORECASE)

_OFFICIAL_MARKERS = (
    "読売ジャイアンツ公式x",
    "巨人公式x",
    "ジャイアンツ公式x",
    "公式x",
    "npb公式x",
    "tokyogiants",
    "yomiuri_giants",
    "ジャイアンツタウン",
)
_MEDIA_MARKERS = (
    "スポーツ報知巨人班x",
    "報知巨人班x",
    "報知野球x",
    "スポーツ報知x",
    "スポニチx",
    "日刊スポーツx",
    "サンスポx",
    "baseballking",
    "fullcount",
    "hochi",
    "sponichi",
    "sanspo",
    "nikkansports",
)
_RECOGNIZED_WEB_TRUST_LEVELS = {"high", "mid-high", "mid"}


def _normalize_key(value: str) -> str:
    return _WS_RE.sub("", html.unescape(value or "")).lower()


def _strip_html(value: str) -> str:
    return _TAG_RE.sub(" ", html.unescape(value or ""))


def _is_x_url(url: str) -> bool:
    return bool(_X_URL_RE.search(url or ""))


def _extract_handle(url: str) -> str:
    match = _X_URL_RE.search(url or "")
    if not match:
        return ""
    handle = match.group(1).strip()
    return "@" + handle if handle else ""


def _looks_like_x_source(name: str, url: str, source_type: str) -> bool:
    normalized = _normalize_key(name)
    if source_type == "social_news":
        return True
    if _is_x_url(url):
        return True
    if normalized.endswith("x") or "公式x" in normalized or "巨人班x" in normalized or "報知野球x" in normalized:
        return True
    return False


def _resolve_source_family(url: str) -> str:
    if _is_x_url(url):
        handle = _extract_handle(url)
        family = _classify_handle_family(handle) if handle else "unknown"
        if family != "unknown":
            return family
    return _classify_url_family(url or "")


def _classify_source_kind(name: str, url: str, source_type: str) -> str:
    normalized = _normalize_key(name)
    if any(marker in normalized for marker in _MEDIA_MARKERS):
        return "official_media_x"
    if any(marker in normalized for marker in _OFFICIAL_MARKERS):
        return "official_x"

    source_family = _resolve_source_family(url or "")
    family_trust = _get_family_trust_level(source_family)
    trust_level = _classify_url(url or "")
    if _is_x_url(url):
        if source_family in {"giants_official", "npb_official"} or trust_level == "primary":
            return "official_x"
        if family_trust in {"mid", "mid-high"} or trust_level == "secondary":
            return "official_media_x"
        return "ambiguous_x" if _looks_like_x_source(name, url, source_type) else "other"

    if family_trust in _RECOGNIZED_WEB_TRUST_LEVELS or trust_level in {"primary", "secondary"}:
        return "t1_web"
    if _looks_like_x_source(name, url, source_type):
        return "ambiguous_x"
    return "other"


def _source_items(source_context: dict[str, Any] | None) -> list[dict[str, str]]:
    context = source_context or {}
    source_type = str(context.get("source_type") or "")
    items = context.get("source_links") or []
    normalized_items: list[dict[str, str]] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized_items.append(
                {
                    "name": str(item.get("name") or "").strip(),
                    "url": str(item.get("url") or "").strip(),
                    "source_type": str(item.get("source_type") or "").strip() or source_type,
                }
            )

    if not normalized_items:
        fallback_name = str(context.get("source_name") or "").strip()
        fallback_url = str(context.get("source_url") or "").strip()
        if fallback_name or fallback_url or source_type:
            normalized_items.append(
                {
                    "name": fallback_name,
                    "url": fallback_url,
                    "source_type": source_type,
                }
            )

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in normalized_items:
        key = (_normalize_key(item["name"]), item["url"], item["source_type"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _rendered_has_required_attribution(rendered_html: str, source_name: str, source_kind: str, source_url: str) -> bool:
    rendered_text = _normalize_key(_strip_html(rendered_html))
    if not rendered_text:
        return False

    tokens = []
    if source_name:
        tokens.append(_normalize_key(source_name))
    kind_label = SOURCE_KIND_LABELS.get(source_kind, "")
    if kind_label:
        tokens.append(_normalize_key(kind_label))
    handle = _extract_handle(source_url)
    if handle:
        tokens.append(_normalize_key(handle))
    return any(token and token in rendered_text for token in tokens)


def validate_source_attribution(
    article_subtype: str,
    rendered_html: str,
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items = _source_items(source_context)
    if not items:
        return {
            "required": False,
            "ok": True,
            "fail_axis": "",
            "primary_source_kind": "",
            "has_t1_web_source": False,
            "required_sources": [],
            "missing_required_sources": [],
        }

    classified_items: list[dict[str, str]] = []
    for item in items:
        source_kind = _classify_source_kind(item["name"], item["url"], item["source_type"])
        classified_items.append({**item, "kind": source_kind})

    primary = classified_items[0]
    has_t1_web_source = any(item["kind"] == "t1_web" for item in classified_items[1:])
    primary_kind = primary["kind"]
    required = False
    fail_axis = ""

    if primary_kind == "ambiguous_x":
        if article_subtype in SPECIAL_REQUIRED_SUBTYPES or primary.get("source_type") == "social_news" or not has_t1_web_source:
            fail_axis = "source_attribution_ambiguous"
    elif primary_kind in SOURCE_KIND_LABELS:
        if article_subtype in SPECIAL_REQUIRED_SUBTYPES:
            required = True
        elif article_subtype in POSTGAME_OPTIONAL_WITH_WEB_SUBTYPES:
            required = not has_t1_web_source
        else:
            required = not has_t1_web_source

    missing_required_sources: list[str] = []
    required_sources: list[str] = []
    if required:
        required_label = primary["name"] or SOURCE_KIND_LABELS.get(primary_kind, "")
        if required_label:
            required_sources.append(required_label)
        if not _rendered_has_required_attribution(rendered_html, primary["name"], primary_kind, primary["url"]):
            missing_required_sources.append(required_label or SOURCE_KIND_LABELS.get(primary_kind, ""))
            fail_axis = "source_attribution_missing"

    return {
        "required": required,
        "ok": not fail_axis,
        "fail_axis": fail_axis,
        "primary_source_kind": primary_kind,
        "has_t1_web_source": has_t1_web_source,
        "required_sources": required_sources,
        "missing_required_sources": missing_required_sources,
    }
