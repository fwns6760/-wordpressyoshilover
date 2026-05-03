from __future__ import annotations

import copy
import html
import os
import re
from datetime import datetime
from functools import lru_cache
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

import requests

from src.baseball_numeric_fact_consistency import JST, extract_dates, extract_scores
from src.body_validator import POSTGAME_DECISIVE_EVENT_RE


ENABLE_POSTGAME_STRICT_FACT_RECOVERY_ENV = "ENABLE_POSTGAME_STRICT_FACT_RECOVERY"
TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
WHITELISTED_NEWS_DOMAINS = (
    "nikkansports.com",
    "hochi.news",
    "hochi.co.jp",
    "sports.hochi.co.jp",
    "baseballking.jp",
    "full-count.jp",
)

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_PARAGRAPH_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_SENTENCE_SPLIT_RE = re.compile(r"[。！？\n]+")
_META_DESCRIPTION_PATTERNS = (
    re.compile(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\'][^>]+content=["\'](?P<content>[^"\']*)["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta[^>]+content=["\'](?P<content>[^"\']*)["\'][^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\']',
        re.IGNORECASE,
    ),
)
_DECISIVE_EVENT_RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"適時(?:二塁|三塁)?打"), "decisive_hit", "適時打"),
    (re.compile(r"\d+号ソロ"), "home_run_solo", "本塁打"),
    (re.compile(r"\d+号3ラン"), "home_run_3run", "本塁打"),
    (re.compile(r"決勝打"), "winning_hit", "決勝打"),
    (re.compile(r"決勝点"), "winning_run", "勝ち越し"),
    (re.compile(r"完投勝利"), "complete_game", "好投"),
    (re.compile(r"逆転"), "comeback", "勝ち越し"),
)
_CANONICAL_EVENT_TYPES = {
    "decisive_hit": "batting",
    "home_run_solo": "batting",
    "home_run_3run": "batting",
    "winning_hit": "batting",
    "winning_run": "other",
    "complete_game": "pitching",
    "comeback": "other",
}


def postgame_strict_fact_recovery_enabled(*, env: Mapping[str, str] | None = None) -> bool:
    current_env = env if env is not None else os.environ
    return str(current_env.get(ENABLE_POSTGAME_STRICT_FACT_RECOVERY_ENV, "")).strip().lower() in TRUTHY_ENV_VALUES


def recover_postgame_strict_payload(
    payload: Mapping[str, Any] | None,
    *,
    source_text: str,
    source_url: str,
    published_at: datetime | None,
    validation_errors: Sequence[str] | None = None,
    fetch_source_material: Callable[[str], str] | None = None,
) -> tuple[dict[str, Any], str]:
    repaired = copy.deepcopy(dict(payload or {}))
    merged_source_text = _with_published_metadata(source_text, published_at)
    _prefill_required_facts(repaired, merged_source_text, published_at)
    _recover_decisive_event(repaired, merged_source_text)

    errors = tuple(str(item or "").strip() for item in (validation_errors or ()) if str(item or "").strip())
    if "required_facts_missing:giants_score" not in errors:
        return repaired, merged_source_text
    if not _is_whitelisted_news_domain(source_url):
        return repaired, merged_source_text

    fetcher = fetch_source_material or _fetch_postgame_source_material
    source_slice = str(fetcher(source_url) or "").strip()
    if not source_slice:
        return repaired, merged_source_text

    merged_source_text = _merge_source_segments(merged_source_text, "[recovery_source_slice]", source_slice)
    _prefill_required_facts(repaired, merged_source_text, published_at)
    _recover_decisive_event(repaired, merged_source_text)
    return repaired, merged_source_text


def _with_published_metadata(source_text: str, published_at: datetime | None) -> str:
    merged_source_text = str(source_text or "").strip()
    if not published_at:
        return merged_source_text
    if "published_day_label:" in merged_source_text and "published_date:" in merged_source_text:
        return merged_source_text

    local_dt = published_at if published_at.tzinfo is None else published_at.astimezone(JST)
    metadata = (
        f"published_at: {published_at.isoformat()}",
        f"published_date: {local_dt.year}年{local_dt.month}月{local_dt.day}日",
        f"published_day_label: {local_dt.month}月{local_dt.day}日",
    )
    return _merge_source_segments(merged_source_text, *metadata)


def _merge_source_segments(*segments: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        clean = str(segment or "").strip()
        if not clean:
            continue
        key = clean.replace(" ", "").replace("　", "")
        if key in seen:
            continue
        seen.add(key)
        merged.append(clean)
    return "\n".join(merged)


def _prefill_required_facts(payload: dict[str, Any], source_text: str, published_at: datetime | None) -> None:
    if not str(payload.get("game_date") or "").strip():
        game_date = _extract_game_date(source_text, published_at)
        if game_date:
            payload["game_date"] = game_date

    score_token = _pick_giants_score_token(source_text, prefer_team_names=not str(payload.get("opponent") or "").strip())
    if score_token is None:
        return

    if payload.get("giants_score") in (None, "") and score_token.giants_score is not None:
        payload["giants_score"] = score_token.giants_score
    if payload.get("opponent_score") in (None, "") and score_token.opponent_score is not None:
        payload["opponent_score"] = score_token.opponent_score

    if not str(payload.get("opponent") or "").strip():
        if score_token.left_team and score_token.right_team:
            if score_token.giants_side == "left":
                payload["opponent"] = score_token.right_team
            elif score_token.giants_side == "right":
                payload["opponent"] = score_token.left_team

    if not str(payload.get("result") or "").strip():
        result = score_token.giants_result
        if result == "win":
            payload["result"] = "win"
        elif result == "loss":
            payload["result"] = "loss"
        elif result == "tie":
            payload["result"] = "draw"


def _extract_game_date(source_text: str, published_at: datetime | None) -> str | None:
    publish_iso = published_at.isoformat() if published_at else None
    publish_date = None
    if published_at:
        local_dt = published_at if published_at.tzinfo is None else published_at.astimezone(JST)
        publish_date = local_dt.date().isoformat()

    resolved_dates: list[str] = []
    seen: set[str] = set()
    for token in extract_dates(source_text):
        resolved = token.resolve(publish_iso)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        resolved_dates.append(resolved)

    if not resolved_dates:
        return publish_date
    if publish_date and publish_date in seen:
        return publish_date
    for resolved in resolved_dates:
        if not publish_date or resolved <= publish_date:
            return resolved
    return resolved_dates[0]


def _pick_giants_score_token(source_text: str, *, prefer_team_names: bool) -> Any | None:
    tokens = [token for token in extract_scores(source_text) if token.giants_side in {"left", "right"}]
    if not tokens:
        return None
    if prefer_team_names:
        for token in tokens:
            if token.left_team and token.right_team:
                return token
    return tokens[0]


def _recover_decisive_event(payload: dict[str, Any], source_text: str) -> None:
    raw_events = payload.get("key_events")
    key_events = [copy.deepcopy(event) for event in raw_events] if isinstance(raw_events, list) else []
    normalized_events: list[dict[str, Any]] = []
    seen_event_keys: set[tuple[str, str]] = set()

    for event in key_events:
        if not isinstance(event, dict):
            continue
        repaired = _normalize_event_text(event)
        key = (
            _collapse_ws(str(repaired.get("text") or "")),
            _collapse_ws(str(repaired.get("evidence") or "")),
        )
        if key in seen_event_keys:
            continue
        seen_event_keys.add(key)
        normalized_events.append(repaired)

    if not _events_have_decisive_keyword(normalized_events):
        recovered = _extract_decisive_event_from_source(source_text)
        if recovered:
            key = (
                _collapse_ws(str(recovered.get("text") or "")),
                _collapse_ws(str(recovered.get("evidence") or "")),
            )
            if key not in seen_event_keys:
                normalized_events.append(recovered)

    payload["key_events"] = normalized_events


def _normalize_event_text(event: Mapping[str, Any]) -> dict[str, Any]:
    repaired = dict(event)
    evidence = _collapse_ws(str(event.get("evidence") or event.get("text") or ""))
    text = _collapse_ws(str(event.get("text") or evidence))
    match = _detect_decisive_token(evidence or text)
    if match is None:
        repaired["text"] = text
        repaired["evidence"] = evidence
        return repaired

    _rule_match, canonical_token, keyword = match
    repaired["canonical_token"] = canonical_token
    repaired["text"] = _canonicalize_event_text(text or evidence, _rule_match.group(0), canonical_token, keyword)
    repaired["evidence"] = evidence
    if not str(repaired.get("type") or "").strip():
        repaired["type"] = _CANONICAL_EVENT_TYPES.get(canonical_token, "other")
    return repaired


def _extract_decisive_event_from_source(source_text: str) -> dict[str, Any] | None:
    for sentence in _candidate_sentences(source_text):
        match = _detect_decisive_token(sentence)
        if match is None:
            continue
        rule_match, canonical_token, keyword = match
        return {
            "type": _CANONICAL_EVENT_TYPES.get(canonical_token, "other"),
            "text": _canonicalize_event_text(sentence, rule_match.group(0), canonical_token, keyword),
            "evidence": sentence,
            "canonical_token": canonical_token,
        }
    return None


def _events_have_decisive_keyword(events: Sequence[Mapping[str, Any]]) -> bool:
    for event in events:
        text = _collapse_ws(str(event.get("text") or ""))
        if text and POSTGAME_DECISIVE_EVENT_RE.search(text):
            return True
    return False


def _detect_decisive_token(text: str) -> tuple[re.Match[str], str, str] | None:
    clean = _collapse_ws(text)
    if not clean:
        return None
    for pattern, canonical_token, keyword in _DECISIVE_EVENT_RULES:
        match = pattern.search(clean)
        if match:
            return match, canonical_token, keyword
    return None


def _canonicalize_event_text(text: str, matched_phrase: str, canonical_token: str, keyword: str) -> str:
    clean = _collapse_ws(text)
    if not clean:
        return clean
    if POSTGAME_DECISIVE_EVENT_RE.search(clean):
        return clean
    if canonical_token == "decisive_hit" and matched_phrase in clean:
        return clean.replace(matched_phrase, f"{keyword}となる{matched_phrase}", 1)
    if canonical_token.startswith("home_run_") and matched_phrase in clean:
        return clean.replace(matched_phrase, f"{matched_phrase}{keyword}", 1)
    if canonical_token == "winning_run" and matched_phrase in clean:
        return clean.replace(matched_phrase, f"{keyword}となる{matched_phrase}", 1)
    if canonical_token == "complete_game" and matched_phrase in clean:
        return clean.replace(matched_phrase, f"{matched_phrase}の{keyword}", 1)
    if canonical_token == "comeback" and matched_phrase in clean:
        return clean.replace(matched_phrase, f"{matched_phrase}して{keyword}", 1)
    if keyword and keyword not in clean:
        return f"{keyword}: {clean}"
    return clean


def _candidate_sentences(source_text: str) -> list[str]:
    normalized = _strip_html_text(source_text)
    sentences: list[str] = []
    seen: set[str] = set()
    for fragment in _SENTENCE_SPLIT_RE.split(normalized):
        clean = _collapse_ws(fragment.strip(" ・\t"))
        if not clean or len(clean) < 4:
            continue
        clean = re.sub(r"^(title|summary|source_name|source_url|published_at|published_date|published_day_label)\s*:\s*", "", clean)
        if not clean or clean.startswith("[") or clean == "source_fact_block":
            continue
        if clean in seen:
            continue
        seen.add(clean)
        sentences.append(clean if clean.endswith("。") else f"{clean}。")
    return sentences


def _is_whitelisted_news_domain(source_url: str) -> bool:
    host = _source_host(source_url)
    if not host:
        return False
    return any(host == domain or host.endswith("." + domain) for domain in WHITELISTED_NEWS_DOMAINS)


def _source_host(source_url: str) -> str:
    raw = html.unescape(str(source_url or "")).strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    return parsed.netloc.lower()


@lru_cache(maxsize=64)
def _fetch_postgame_source_material(source_url: str) -> str:
    url = html.unescape(str(source_url or "")).strip()
    if not url:
        return ""
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": HTTP_USER_AGENT},
            allow_redirects=True,
        )
    except Exception:
        return ""
    if response.status_code >= 400:
        return ""
    return _extract_source_material_from_html(response.text or "")


def _extract_source_material_from_html(html_text: str) -> str:
    description = ""
    for pattern in _META_DESCRIPTION_PATTERNS:
        match = pattern.search(html_text)
        if match:
            description = _strip_html_text(match.group("content"))
            if description:
                break

    paragraphs = [
        _collapse_ws(_strip_html_text(fragment))
        for fragment in _PARAGRAPH_RE.findall(html_text or "")
    ]
    filtered_paragraphs = [paragraph for paragraph in paragraphs if len(paragraph) >= 8][:2]

    sentences: list[str] = []
    seen: set[str] = set()
    for paragraph in filtered_paragraphs:
        for fragment in _SENTENCE_SPLIT_RE.split(paragraph):
            clean = _collapse_ws(fragment.strip(" ・\t"))
            if len(clean) < 4 or clean in seen:
                continue
            seen.add(clean)
            sentences.append(clean if clean.endswith("。") else f"{clean}。")
            if len(sentences) >= 6:
                break
        if len(sentences) >= 6:
            break

    return _merge_source_segments(description, *filtered_paragraphs, *sentences)


def _strip_html_text(text: str) -> str:
    return html.unescape(_TAG_RE.sub(" ", text or "")).replace("\xa0", " ")


def _collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()
