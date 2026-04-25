from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlsplit

try:
    from source_id import normalize_url
    from title_validator import starts_with_starmen_prefix
except ImportError:  # pragma: no cover - package import for tests
    from src.source_id import normalize_url
    from src.title_validator import starts_with_starmen_prefix


_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_YAHOO_GAME_RE = re.compile(r"/npb/game/([0-9]+)/", re.IGNORECASE)
_LINEUP_CANDIDATE_KEY_RE = re.compile(r"^lineup_notice:([^:]+):([^:]+)$", re.IGNORECASE)
_HOCHI_DOMAINS = {"hochi.co.jp", "hochi.news", "sports.hochi.co.jp"}
_HOCHI_HANDLES = {"hochi_giants", "sportshochi", "hochi_baseball"}
_HOCHI_NAME_MARKERS = (
    "スポーツ報知",
    "報知新聞",
    "報知新聞社",
    "報知巨人班x",
    "スポーツ報知巨人班x",
    "スポーツ報知巨人担当",
    "sportshochi",
    "sportshochinews",
    "hochi_giants",
    "hochi_baseball",
    "sportshochi",
)


def is_hochi_source(source_url: str, source_name: str, source_domain: str) -> bool:
    domain = _canonical_domain(source_domain or source_url)
    if _matches_domain(domain, _HOCHI_DOMAINS):
        return True

    handle = _x_handle(source_url)
    if handle in _HOCHI_HANDLES:
        return True

    normalized_name = _normalize_key(source_name)
    if any(_normalize_key(marker) in normalized_name for marker in _HOCHI_NAME_MARKERS):
        return True

    normalized_domain = _normalize_key(source_domain)
    return any(_normalize_key(marker) in normalized_domain for marker in _HOCHI_NAME_MARKERS)


def extract_game_id(post_data: dict[str, Any]) -> str | None:
    for value in _candidate_values(post_data, "game_id"):
        normalized = _normalize_token(value)
        if normalized:
            return normalized

    candidate_key = _first_text(_candidate_values(post_data, "candidate_key"))
    if candidate_key:
        match = _LINEUP_CANDIDATE_KEY_RE.match(candidate_key)
        if match:
            return _normalize_token(match.group(1)) or None

    for url in _collect_source_urls(post_data):
        normalized_url = normalize_url(url)
        parsed = urlsplit(normalized_url)
        match = _YAHOO_GAME_RE.search(parsed.path or "")
        if match:
            return match.group(1)
    return None


def validate_lineup_prefix(title: str, subtype: str) -> str | None:
    if not starts_with_starmen_prefix(title or ""):
        return None
    normalized_subtype = _normalize_subtype(subtype)
    if normalized_subtype in {"lineup", "lineup_notice"}:
        return None
    return "lineup_prefix_misuse"


def compute_lineup_dedup(post_pool: list[dict[str, Any]]) -> dict[str, Any]:
    representatives: list[dict[str, Any]] = []
    duplicate_absorbed: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    prefix_violations: list[dict[str, Any]] = []
    by_post_id: dict[int, dict[str, Any]] = {}
    by_game_id: dict[str, dict[str, Any]] = {}

    lineup_candidates: list[_LineupCandidate] = []
    for post_data in post_pool:
        candidate = _coerce_candidate(post_data)
        prefix_reason = validate_lineup_prefix(candidate.title, candidate.subtype)
        if prefix_reason:
            decision = candidate.as_decision(
                status="prefix_violation",
                reason=prefix_reason,
            )
            prefix_violations.append(decision)
            if candidate.post_id is not None:
                by_post_id[candidate.post_id] = decision
            continue
        if not candidate.is_lineup_candidate or not candidate.game_id:
            continue
        lineup_candidates.append(candidate)

    groups: dict[str, list[_LineupCandidate]] = {}
    for candidate in lineup_candidates:
        groups.setdefault(candidate.game_id, []).append(candidate)

    for game_id in sorted(groups):
        group = groups[game_id]
        hochi_candidates = [candidate for candidate in group if candidate.is_hochi]
        if hochi_candidates:
            representative = max(hochi_candidates, key=_hochi_priority)
            representative_decision = representative.as_decision(
                status="representative",
                reason="lineup_primary_hochi",
            )
            representatives.append(representative_decision)
            if representative.post_id is not None:
                by_post_id[representative.post_id] = representative_decision

            absorbed_items: list[dict[str, Any]] = []
            for candidate in group:
                if candidate.identity == representative.identity:
                    continue
                decision = candidate.as_decision(
                    status="duplicate_absorbed",
                    reason="lineup_duplicate_absorbed_by_hochi",
                    representative_post_id=representative.post_id,
                    representative_source_url=representative.source_url,
                )
                absorbed_items.append(decision)
                duplicate_absorbed.append(decision)
                if candidate.post_id is not None:
                    by_post_id[candidate.post_id] = decision
            by_game_id[game_id] = {
                "game_id": game_id,
                "representative": representative_decision,
                "duplicate_absorbed": absorbed_items,
                "deferred": [],
            }
            continue

        deferred_items: list[dict[str, Any]] = []
        for candidate in group:
            decision = candidate.as_decision(
                status="deferred",
                reason="lineup_no_hochi_source",
            )
            deferred_items.append(decision)
            deferred.append(decision)
            if candidate.post_id is not None:
                by_post_id[candidate.post_id] = decision
        by_game_id[game_id] = {
            "game_id": game_id,
            "representative": None,
            "duplicate_absorbed": [],
            "deferred": deferred_items,
        }

    return {
        "representatives": representatives,
        "duplicate_absorbed": duplicate_absorbed,
        "deferred": deferred,
        "prefix_violations": prefix_violations,
        "by_post_id": by_post_id,
        "by_game_id": by_game_id,
        "summary": {
            "representative_count": len(representatives),
            "duplicate_absorbed_count": len(duplicate_absorbed),
            "deferred_count": len(deferred),
            "prefix_violation_count": len(prefix_violations),
        },
    }


class _LineupCandidate:
    def __init__(
        self,
        *,
        post_id: int | None,
        title: str,
        subtype: str,
        candidate_key: str,
        game_id: str,
        source_url: str,
        source_name: str,
        source_domain: str,
        is_hochi: bool,
        modified: str,
    ) -> None:
        self.post_id = post_id
        self.title = title
        self.subtype = subtype
        self.candidate_key = candidate_key
        self.game_id = game_id
        self.source_url = source_url
        self.source_name = source_name
        self.source_domain = source_domain
        self.is_hochi = is_hochi
        self.modified = modified
        self.identity = (
            self.post_id,
            self.candidate_key,
            self.source_url,
            self.title,
        )

    @property
    def is_lineup_candidate(self) -> bool:
        if self.candidate_key.startswith("lineup_notice:"):
            return True
        normalized_subtype = _normalize_subtype(self.subtype)
        return normalized_subtype in {"lineup", "lineup_notice"}

    def as_decision(
        self,
        *,
        status: str,
        reason: str,
        representative_post_id: int | None = None,
        representative_source_url: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "post_id": self.post_id,
            "title": self.title,
            "subtype": self.subtype,
            "candidate_key": self.candidate_key,
            "game_id": self.game_id,
            "source_url": self.source_url,
            "source_name": self.source_name,
            "source_domain": self.source_domain,
            "is_hochi_source": self.is_hochi,
            "modified": self.modified,
            "status": status,
            "reason": reason,
        }
        if representative_post_id is not None:
            payload["representative_post_id"] = representative_post_id
        if representative_source_url:
            payload["representative_source_url"] = representative_source_url
        return payload


def _coerce_candidate(post_data: dict[str, Any]) -> _LineupCandidate:
    post_id = _coerce_post_id(_first_text(_candidate_values(post_data, "post_id", "id")))
    title = _title_value(post_data)
    subtype = _resolve_subtype(post_data, title)
    candidate_key = _first_text(_candidate_values(post_data, "candidate_key"))
    game_id = extract_game_id(post_data) or ""
    source_urls = _collect_source_urls(post_data)
    source_names = _collect_source_names(post_data)
    source_url = source_urls[0] if source_urls else ""
    source_name = source_names[0] if source_names else ""
    source_domain = _canonical_domain(_first_text(_candidate_values(post_data, "source_domain")) or source_url)
    source_candidates = _source_context_candidates(post_data, source_urls, source_names)
    is_hochi = any(is_hochi_source(url, name, domain) for url, name, domain in source_candidates)
    modified = _first_text(_candidate_values(post_data, "modified", "modified_at"))
    return _LineupCandidate(
        post_id=post_id,
        title=title,
        subtype=subtype,
        candidate_key=candidate_key,
        game_id=game_id,
        source_url=source_url,
        source_name=source_name,
        source_domain=source_domain,
        is_hochi=is_hochi,
        modified=modified,
    )


def _source_context_candidates(
    post_data: dict[str, Any],
    source_urls: list[str],
    source_names: list[str],
) -> list[tuple[str, str, str]]:
    source_domains = [
        _canonical_domain(value)
        for value in _candidate_values(post_data, "source_domain")
        if _canonical_domain(value)
    ]
    if not source_domains and source_urls:
        source_domains = [_canonical_domain(source_urls[0])]

    candidates: list[tuple[str, str, str]] = []
    max_len = max(len(source_urls), len(source_names), len(source_domains), 1)
    for index in range(max_len):
        url = source_urls[index] if index < len(source_urls) else (source_urls[0] if source_urls else "")
        name = source_names[index] if index < len(source_names) else (source_names[0] if source_names else "")
        domain = source_domains[index] if index < len(source_domains) else (source_domains[0] if source_domains else _canonical_domain(url))
        key = (url, name, domain)
        if key not in candidates:
            candidates.append(key)
    if not candidates:
        candidates.append(("", "", ""))
    return candidates


def _candidate_values(post_data: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        values.extend(_value_candidates(post_data, key))
    return values


def _value_candidates(post_data: dict[str, Any], key: str) -> list[str]:
    values: list[str] = []
    for container_key in ("", "meta", "metadata"):
        container: Any
        if container_key:
            container = post_data.get(container_key)
        else:
            container = post_data
        if not isinstance(container, dict) or key not in container:
            continue
        value = container.get(key)
        if isinstance(value, list):
            values.extend(_clean_text(item) for item in value if _clean_text(item))
        elif isinstance(value, dict):
            for nested_key in ("raw", "rendered", "name", "url"):
                nested_value = _clean_text(value.get(nested_key))
                if nested_value:
                    values.append(nested_value)
        else:
            cleaned = _clean_text(value)
            if cleaned:
                values.append(cleaned)
    return values


def _title_value(post_data: dict[str, Any]) -> str:
    for key in ("title",):
        for value in _value_candidates(post_data, key):
            if value:
                return value
    return ""


def _body_html_value(post_data: dict[str, Any]) -> str:
    content = post_data.get("content")
    if isinstance(content, dict):
        for key in ("raw", "rendered"):
            value = _clean_text(content.get(key), preserve_html=True)
            if value:
                return value
    if isinstance(content, str):
        return content
    for key in ("body_html",):
        value = _first_text(_candidate_values(post_data, key))
        if value:
            return value
    return ""


def _collect_source_urls(post_data: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("source_url", "_yoshilover_source_url", "yl_source_url", "source_urls"):
        for value in _candidate_values(post_data, key):
            urls.extend(_extract_urls(value))

    for key in ("source_bundle", "source_links", "trigger_only_sources"):
        for container_key in ("", "meta", "metadata"):
            container = post_data if not container_key else post_data.get(container_key)
            if not isinstance(container, dict):
                continue
            items = container.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = _clean_text(item.get("url"))
                if url:
                    urls.extend(_extract_urls(url))

    body_html = _body_html_value(post_data)
    for url in _URL_RE.findall(body_html):
        urls.append(url)
    return _dedupe_urls(urls)


def _collect_source_names(post_data: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("source_name", "source_ref", "quote_source"):
        names.extend(_candidate_values(post_data, key))

    source_block = _first_text(_candidate_values(post_data, "source_block"))
    if not source_block:
        source_block = _extract_source_block_from_body(_body_html_value(post_data))
    if source_block:
        cleaned = _strip_html(source_block)
        cleaned = re.sub(r"^(?:参照元|出典)\s*[：:]\s*", "", cleaned).strip()
        cleaned = _URL_RE.sub("", cleaned).strip(" /／|・")
        if cleaned:
            names.append(cleaned)

    for key in ("source_bundle", "source_links", "trigger_only_sources"):
        for container_key in ("", "meta", "metadata"):
            container = post_data if not container_key else post_data.get(container_key)
            if not isinstance(container, dict):
                continue
            items = container.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = _clean_text(item.get("name"))
                if name:
                    names.append(name)
    return _dedupe_texts(names)


def _resolve_subtype(post_data: dict[str, Any], title: str) -> str:
    for value in _candidate_values(post_data, "article_subtype", "subtype", "family", "inferred_subtype"):
        normalized = _normalize_subtype(value)
        if normalized:
            return normalized
    if starts_with_starmen_prefix(title):
        return "lineup"
    return ""


def _normalize_subtype(value: str) -> str:
    return _clean_text(value).lower()


def _hochi_priority(candidate: _LineupCandidate) -> tuple[int, int, str, int]:
    domain_score = 0
    if _matches_domain(candidate.source_domain, _HOCHI_DOMAINS):
        domain_score = 2
    elif _x_handle(candidate.source_url) in _HOCHI_HANDLES:
        domain_score = 1
    return (
        1 if candidate.is_hochi else 0,
        domain_score,
        candidate.modified,
        candidate.post_id or 0,
    )


def _canonical_domain(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    parsed = None
    try:
        normalized = normalize_url(text if "://" in text or text.startswith("//") else f"https://{text}")
        parsed = urlsplit(normalized)
    except Exception:  # pragma: no cover - defensive fallback
        parsed = urlsplit(text if "://" in text or text.startswith("//") else f"https://{text}")
    host = (parsed.hostname or "").lower().strip(".")
    for prefix in ("www.", "m.", "news."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _x_handle(source_url: str) -> str:
    text = _clean_text(source_url)
    if not text:
        return ""
    parsed = urlsplit(normalize_url(text if "://" in text or text.startswith("//") else f"https://{text}"))
    host = (parsed.hostname or "").lower()
    if host not in {"x.com", "twitter.com"}:
        return ""
    path = [part for part in parsed.path.split("/") if part]
    if not path:
        return ""
    return path[0].lower()


def _matches_domain(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains if host)


def _extract_urls(value: str) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    matches = _URL_RE.findall(text)
    return matches or ([text] if text.startswith("http") else [])


def _strip_html(value: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", value or ""))


def _extract_source_block_from_body(body_html: str) -> str:
    body_text = _strip_html(body_html)
    for line in body_text.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("参照元") or cleaned.startswith("出典"):
            return cleaned
    return ""


def _normalize_key(value: str) -> str:
    return re.sub(r"[\s\u3000/／|・:：()\[\]【】「」『』'\"._-]+", "", _clean_text(value)).lower()


def _normalize_token(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", _clean_text(value)).lower()


def _clean_text(value: Any, *, preserve_html: bool = False) -> str:
    if value is None:
        return ""
    text = str(value)
    if not preserve_html:
        text = html.unescape(text)
    return text.strip()


def _first_text(values: list[str]) -> str:
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return ""


def _dedupe_urls(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        normalized = normalize_url(cleaned)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        key = _normalize_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped


def _coerce_post_id(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
