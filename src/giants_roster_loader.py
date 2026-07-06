"""巨人 roster loader with NPB.jp runtime fetch + JSON fallback.

Resolution order on every call (within cache TTL):

1. In-memory cache (TTL = CACHE_TTL_SECONDS, default 24h)
2. NPB.jp ``rst_g.html`` live fetch (支配下 + 育成 を 1 page から)
3. ``config/giants_roster.json`` baseline (NPB が落ちている / network 不能 時)

The shape returned matches the existing ``giants_roster.json`` consumer
expectations: a list of dicts with ``name`` / ``aliases`` / ``role`` /
``position`` / ``active`` / ``jersey_number`` keys.

This module deliberately avoids any LLM call — all classification is
string-level and runs offline once the HTML is in hand.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

NPB_ROSTER_URL = "https://npb.jp/bis/teams/rst_g.html"
NPB_FETCH_TIMEOUT_SECONDS = 8
CACHE_TTL_SECONDS = 24 * 60 * 60

_FALLBACK_JSON_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "giants_roster.json"
)

_CACHE_LOCK = threading.Lock()
_CACHE: Optional[List[Dict[str, Any]]] = None
_CACHE_AT: float = 0.0
_CACHE_SOURCE: str = ""

_SHIHAIKA_HEADER_RE = re.compile(r"■\s*支配下選手")
_IKUSEI_HEADER_RE = re.compile(r"■\s*育成選手")
_ROW_RE = re.compile(
    r'<tr class="rosterPlayer">'
    r"\s*<td>([^<]*)</td>"
    r'\s*<td class="rosterRegister">(?:<a[^>]*>)?([^<]+?)(?:</a>)?</td>',
    re.DOTALL,
)


def _normalize_full_name(raw: str) -> str:
    if not raw:
        return ""
    return raw.replace("　", " ").replace("　", " ").strip()


def _dedupe_key(raw: str) -> str:
    # Strip the legacy ``*`` prefix (operator marker for 2軍/育成 in the
    # hand-curated json) plus all whitespace so the same player is keyed
    # identically regardless of source.
    return _normalize_full_name(raw).lstrip("*").replace(" ", "").strip()


def _surname_part(full_name: str) -> str:
    cleaned = _normalize_full_name(full_name)
    if " " in cleaned:
        return cleaned.split(" ", 1)[0]
    return cleaned


def _given_part(full_name: str) -> str:
    cleaned = _normalize_full_name(full_name)
    if " " in cleaned:
        return cleaned.split(" ", 1)[1]
    return ""


def _build_aliases(full_name: str) -> List[str]:
    # Only full-name variants (with / without internal space). Surname-only
    # is intentionally NOT added — same-surname disambiguation in
    # ``manual_intake._scan_giants_player_names_in_text`` requires that
    # aliases never carry a bare surname. The lineup parsers still match
    # short tokens via the surname-prefix runtime check in
    # ``is_giants_player`` so coverage is preserved.
    aliases: List[str] = []
    seen: set[str] = set()
    cleaned = _normalize_full_name(full_name)
    nospace = cleaned.replace(" ", "")

    def add(value: str) -> None:
        v = value.strip()
        if v and v not in seen:
            seen.add(v)
            aliases.append(v)

    add(cleaned)
    add(nospace)
    return aliases


def _entry_from_npb(jersey: str, full_name: str, role: str) -> Dict[str, Any]:
    cleaned = _normalize_full_name(full_name)
    return {
        "name": cleaned,
        "aliases": _build_aliases(full_name),
        "role": role,
        "position": "",
        "jersey_number": jersey.strip(),
        "active": True,
    }


def _parse_npb_html(html: str) -> List[Dict[str, Any]]:
    if not html:
        return []
    shihaikako_match = _SHIHAIKA_HEADER_RE.search(html)
    ikusei_match = _IKUSEI_HEADER_RE.search(html)
    entries: List[Dict[str, Any]] = []
    sections: List[tuple[str, int, int]] = []
    if shihaikako_match:
        end = ikusei_match.start() if ikusei_match else len(html)
        sections.append(("shihaikako", shihaikako_match.end(), end))
    if ikusei_match:
        sections.append(("ikusei", ikusei_match.end(), len(html)))
    if not sections:
        sections.append(("unknown", 0, len(html)))
    for role, start, end in sections:
        chunk = html[start:end]
        for jersey, name in _ROW_RE.findall(chunk):
            cleaned = _normalize_full_name(name)
            if not cleaned:
                continue
            entries.append(_entry_from_npb(jersey, cleaned, role))
    return entries


def _http_get(url: str, timeout: float) -> Optional[str]:
    try:
        import vendor.requests as requests  # type: ignore[import-not-found]
    except Exception:
        try:
            import requests  # type: ignore[import-not-found]
        except Exception:
            return None
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "yoshilover-fetcher (+https://yoshilover.com)"},
        )
    except Exception:
        return None
    if getattr(resp, "status_code", 0) != 200:
        return None
    try:
        resp.encoding = "utf-8"
    except Exception:
        pass
    text = getattr(resp, "text", "")
    return text or None


def _fetch_npb_roster() -> List[Dict[str, Any]]:
    if os.environ.get("DISABLE_NPB_ROSTER_FETCH", "").strip().lower() in {"1", "true", "yes", "on"}:
        return []
    html = _http_get(NPB_ROSTER_URL, NPB_FETCH_TIMEOUT_SECONDS)
    if not html:
        return []
    return _parse_npb_html(html)


def _load_json_fallback() -> List[Dict[str, Any]]:
    try:
        with _FALLBACK_JSON_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _normalize_existing_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    name = _normalize_full_name(str(entry.get("name") or ""))
    canonical = name.lstrip("*")
    aliases = list(entry.get("aliases") or [])
    if name and name not in aliases:
        aliases.insert(0, name)
    if canonical and canonical not in aliases:
        aliases.insert(0, canonical)
    new_entry = dict(entry)
    new_entry["name"] = canonical or name
    new_entry["aliases"] = aliases
    return new_entry


def _merge_with_fallback(
    npb_entries: List[Dict[str, Any]],
    json_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for raw_entry in json_entries:
        entry = _normalize_existing_entry(raw_entry)
        key = _dedupe_key(str(entry.get("name") or ""))
        if not key:
            continue
        if key in by_key:
            existing = by_key[key]
            existing_aliases = list(existing.get("aliases") or [])
            for alias in entry.get("aliases") or []:
                if alias not in existing_aliases:
                    existing_aliases.append(alias)
            existing["aliases"] = existing_aliases
            continue
        by_key[key] = entry
    for entry in npb_entries:
        key = _dedupe_key(str(entry.get("name") or ""))
        if not key:
            continue
        if key in by_key:
            existing = by_key[key]
            existing_aliases = list(existing.get("aliases") or [])
            for alias in entry.get("aliases") or []:
                if alias not in existing_aliases:
                    existing_aliases.append(alias)
            existing["aliases"] = existing_aliases
            existing["active"] = True
            # 2026-07-06 実事故: 笹原操希の 6/25 育成→支配下昇格が静的 json の
            # 旧 role (ikusei/069) に負けて反映されず、選手検出 alias から漏れた
            # (結果、記事内「中日金丸」の「丸」で丸佳浩を誤検出)。昇格/降格と
            # 背番号は NPB live を正とする。json 手キュレーションの role 表記
            # (player 等) は支配下/育成の区分が NPB と一致する限り温存する。
            if entry.get("jersey_number"):
                existing["jersey_number"] = entry["jersey_number"]
            npb_role = str(entry.get("role") or "")
            old_role = str(existing.get("role") or "")
            _registered = {"player", "shihaikako", "manager", "coach"}
            if npb_role and (
                not old_role
                or (old_role in _registered) != (npb_role in _registered)
            ):
                existing["role"] = npb_role
        else:
            by_key[key] = entry
    return list(by_key.values())


def load_active_roster(force_refresh: bool = False) -> List[Dict[str, Any]]:
    global _CACHE, _CACHE_AT, _CACHE_SOURCE
    now = time.time()
    with _CACHE_LOCK:
        if (
            not force_refresh
            and _CACHE is not None
            and now - _CACHE_AT < CACHE_TTL_SECONDS
        ):
            return _CACHE
        json_entries = _load_json_fallback()
        npb_entries = _fetch_npb_roster()
        if npb_entries:
            merged = _merge_with_fallback(npb_entries, json_entries)
            _CACHE = merged
            _CACHE_SOURCE = "npb+fallback"
        else:
            _CACHE = json_entries
            _CACHE_SOURCE = "fallback"
        _CACHE_AT = now
        return _CACHE


def cache_source() -> str:
    return _CACHE_SOURCE


def reset_cache() -> None:
    global _CACHE, _CACHE_AT, _CACHE_SOURCE
    with _CACHE_LOCK:
        _CACHE = None
        _CACHE_AT = 0.0
        _CACHE_SOURCE = ""
