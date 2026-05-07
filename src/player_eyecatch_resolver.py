"""Player eyecatch resolver — auto-pick a featured_media for a WP post by
detecting a 巨人 player / coach / manager name in the article title and
matching it against an image already in the WP media library.

Cost / safety
=============

- Pure offline name detection. No new external API.
- WP /media search is only invoked once per name per lifetime (results
  are cached in ``config/player_eyecatch_map.json``).
- Cache miss without a matching image is also cached (as ``None``) to
  avoid retrying the same hopeless lookup on every article.
- Returns ``None`` whenever detection or media lookup fails — the caller
  must treat that as "leave featured_media unset" (= site default).

Resolution order
================

1. alias map (e.g. 阿部監督 → 阿部慎之助)
2. full-name match against allowlist + extras (longest first)
3. unique last-name fallback (only when the surname maps to exactly one
   person in the pool — avoids "吉川" → ambiguous)
4. nickname map (マー君 → 田中将大)
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Lazy-imported to avoid circular import at module load time.
_PLAYER_NAMES_CACHE: tuple[tuple[str, ...], dict[str, str]] | None = None


def _load_giants_name_pool() -> tuple[tuple[str, ...], dict[str, str]]:
    """Return ``(name_pool_sorted_desc, nicknames)`` from
    nomotoke_rss_router + the static extras list below."""
    global _PLAYER_NAMES_CACHE
    if _PLAYER_NAMES_CACHE is not None:
        return _PLAYER_NAMES_CACHE
    try:
        from src.nomotoke_rss_router import (
            GIANTS_PLAYER_ALLOWLIST,
            GIANTS_PLAYER_NICKNAMES,
        )
    except Exception:
        GIANTS_PLAYER_ALLOWLIST = ()
        GIANTS_PLAYER_NICKNAMES = {}

    extras = [
        "石塚裕惺", "田和廉", "平山功太", "小濱佑斗", "田中瑛斗",
        "三塚琉生", "佐々木俊輔", "増田陸", "泉口友汰", "松本剛",
        "宮原駿介", "森田駿哉",
        "阿部慎之助", "元木大介", "村田善則",
        "翁田大勢", "ウィットリー",
    ]
    pool = sorted(
        set(GIANTS_PLAYER_ALLOWLIST) | set(extras),
        key=lambda x: -len(x),
    )
    _PLAYER_NAMES_CACHE = (tuple(pool), dict(GIANTS_PLAYER_NICKNAMES))
    return _PLAYER_NAMES_CACHE


_ALIAS_MAP = {
    "阿部監督": "阿部慎之助",
    "大勢": "翁田大勢",
}

# Team-generic fallback used when no per-person match is found. The image
# is the user-curated 原辰徳 photo in the WP media library — picked by
# the operator as the safest "巨人 generic" eyecatch in lieu of a real
# team logo. Override at deploy time via the env var when needed.
_TEAM_FALLBACK_MEDIA_ID_ENV = "PLAYER_EYECATCH_TEAM_FALLBACK_ID"
_TEAM_FALLBACK_MEDIA_ID_DEFAULT = 29270

_CACHE_PATH_ENV = "PLAYER_EYECATCH_MAP_PATH"
_DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent / "config" / "player_eyecatch_map.json"
_CACHE_LOCK = threading.Lock()


def _cache_path() -> Path:
    override = os.environ.get(_CACHE_PATH_ENV, "").strip()
    return Path(override) if override else _DEFAULT_CACHE_PATH


def _load_cache() -> dict:
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("player_eyecatch_cache_unreadable: %s", exc)
        return {}


def _save_cache(data: dict) -> None:
    p = _cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("player_eyecatch_cache_write_failed: %s", exc)


def _normalize_title(t: str) -> str:
    if not isinstance(t, str):
        return ""
    return t.replace("　", " ").strip()


def detect_person(title: str) -> Optional[str]:
    """Return the canonical 巨人 person name found in *title*, or None.

    Skip detection when the title looks like a generic team-level article
    (postgame results, broadcast, official notices, event announcements).
    """
    title_n = _normalize_title(title)
    if not title_n:
        return None

    pool, nicknames = _load_giants_name_pool()

    # Alias first (e.g. 阿部監督 → 阿部慎之助).
    for alias, real in _ALIAS_MAP.items():
        if alias in title_n:
            return real

    # Direct full-name match (longest first via pool sort).
    for name in pool:
        if name in title_n:
            return name

    # Unique-surname fallback — only fires when the 2-char surname maps
    # to exactly one person in the pool.
    surname_index: dict[str, list[str]] = {}
    for name in pool:
        if len(name) >= 2:
            surname_index.setdefault(name[:2], []).append(name)
    for surname, cands in surname_index.items():
        if len(cands) == 1 and surname in title_n:
            return cands[0]

    for nn, real in nicknames.items():
        if nn in title_n:
            return real

    return None


def _media_search(name: str, wp_url: str, auth: Tuple[str, str], timeout: int = 10):
    """Search the WP media library for *name* and return the first hit
    whose title contains *name*. Returns ``{'id': int, 'title': str}`` or
    ``None``."""
    import requests

    try:
        resp = requests.get(
            f"{wp_url.rstrip('/')}/wp-json/wp/v2/media",
            params={
                "search": name,
                "per_page": 5,
                "_fields": "id,title,slug",
            },
            auth=auth,
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("player_eyecatch_media_search_failed name=%s err=%s", name, exc)
        return None
    if resp.status_code >= 400:
        return None
    try:
        hits = resp.json()
    except Exception:
        return None
    for h in hits or []:
        title = (h.get("title") or {}).get("rendered", "") or ""
        if name in title:
            return {"id": int(h["id"]), "title": title[:80]}
    return None


def _team_fallback_media_id() -> Optional[int]:
    raw = os.environ.get(_TEAM_FALLBACK_MEDIA_ID_ENV, "").strip()
    if raw == "0":
        # Operator-disabled fallback.
        return None
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning("invalid_team_fallback_id_env: %s", raw)
    return _TEAM_FALLBACK_MEDIA_ID_DEFAULT


def resolve_eyecatch_from_title(
    title: str,
    *,
    wp_url: str | None = None,
    auth: Tuple[str, str] | None = None,
    allow_remote_lookup: bool = True,
    use_team_fallback: bool = True,
) -> Optional[int]:
    """Resolve a featured_media ID for the given *title*.

    Resolution order:
      1. per-person cache hit
      2. per-person remote /media lookup (cached on first miss)
      3. team-generic fallback (when ``use_team_fallback`` is True)

    Returns ``None`` only when steps 1-2 miss *and* the team fallback is
    disabled / unset.
    """
    name = detect_person(title)
    if name:
        with _CACHE_LOCK:
            cache = _load_cache()
            cached = cache.get(name, "__missing__")
            if cached == "__missing__":
                cached = None
                cache_miss = True
            else:
                cache_miss = False
            if cache_miss and allow_remote_lookup and wp_url and auth:
                cached = _media_search(name, wp_url, auth)
                cache[name] = cached
                _save_cache(cache)

        if isinstance(cached, dict) and cached.get("id"):
            return int(cached["id"])

    if use_team_fallback:
        return _team_fallback_media_id()
    return None
