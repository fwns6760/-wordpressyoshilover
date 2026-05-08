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
- Returns ``None`` whenever detection or media lookup fails *and* both
  the diversified player pool and the team-generic fallback are empty.

Resolution order (detect_person)
================================

1. alias map (e.g. 阿部監督 → 阿部慎之助)
2. full-name match against allowlist + extras (longest first)
3. unique last-name fallback (only when the surname maps to exactly one
   person in the pool — avoids "吉川" → ambiguous)
4. nickname map (マー君 → 田中将大)

Resolution order (resolve_eyecatch_from_title)
==============================================

1. per-person cache hit / remote /media lookup
2. diversified player pool — pick a known-good cached player image
   deterministically by title hash so different articles get different
   thumbnails (avoids the "全部 原辰徳" complaint while keeping fm>0).
   Disable via ``PLAYER_EYECATCH_POOL_FALLBACK_DISABLED=1``.
3. team-generic fallback (env ``PLAYER_EYECATCH_TEAM_FALLBACK_ID``;
   default None — leaves featured_media unset).
"""

from __future__ import annotations

import hashlib
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

# Team-generic fallback used when no per-person match is found.
#
# 2026-05-08 PM: default を None に変更 (RELIABILITY-2026-05-08-H)。
# 経緯: id=29270 → id=23981 と切替えてきたが、いずれも特定 player の article-
# side photo であり、player 名抽出できない記事 (broadcast / 観戦 guide / 公示 /
# review draft 等) で「全部 原辰徳」表示されて user 体感悪化。team fallback
# を default 無効化、env で override 可能。中立的 team logo 画像を WP media に
# upload した上で env を設定する運用が望ましい。
#
# (履歴)
#   id=29270 (旧旧、2026-05-04 頃): 原辰徳-titled slot だが画像実体は別人
#   id=23981 (旧、2026-05-04 頃): 原辰徳監督の article-side image
#   default None (本変更): 全 player 名なし記事で thumbnail 0 になる、
#     env で id 指定すれば従来挙動復帰
_TEAM_FALLBACK_MEDIA_ID_ENV = "PLAYER_EYECATCH_TEAM_FALLBACK_ID"
_TEAM_FALLBACK_MEDIA_ID_DEFAULT: Optional[int] = None

# Diversified player pool fallback — when per-person resolution misses,
# pick another known-good player image from the cache (keyed by title
# hash for stable per-article assignment). Set to "1" to disable.
_POOL_FALLBACK_DISABLED_ENV = "PLAYER_EYECATCH_POOL_FALLBACK_DISABLED"

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


def _pool_fallback_enabled() -> bool:
    raw = os.environ.get(_POOL_FALLBACK_DISABLED_ENV, "").strip().lower()
    return raw not in {"1", "true", "yes"}


def _diversified_player_fallback(title: str) -> Optional[int]:
    """Pick a known-good player image deterministically by title hash.

    The pool is the set of cached entries that resolved to a real
    media_id. Empty pool returns ``None`` so the caller can fall through
    to the team-generic fallback.

    Same title → same image (idempotent re-publishes).
    Different titles → spread across the pool (avoids "全部 原辰徳").
    """
    if not _pool_fallback_enabled():
        return None
    title_n = _normalize_title(title)
    if not title_n:
        return None
    cache = _load_cache()
    pool: list[tuple[str, int]] = []
    for name, entry in cache.items():
        if isinstance(entry, dict):
            mid = entry.get("id")
            if isinstance(mid, int) and mid > 0:
                pool.append((str(name), mid))
    if not pool:
        return None
    # Sort by name so order is stable across runs (dict iteration order
    # is insertion-order in CPython 3.7+, but cache file rewrites can
    # reorder entries — sort defensively).
    pool.sort(key=lambda x: x[0])
    digest = hashlib.md5(title_n.encode("utf-8")).digest()
    idx = int.from_bytes(digest[:4], "big") % len(pool)
    chosen_name, chosen_id = pool[idx]
    logger.info(
        json.dumps(
            {
                "event": "eyecatch_diversified_pool_used",
                "title": title_n[:80],
                "chosen_name": chosen_name,
                "chosen_media_id": chosen_id,
                "pool_size": len(pool),
            },
            ensure_ascii=False,
        )
    )
    return chosen_id


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
      3. diversified player pool — pick from cached hits by title hash
         (only when ``use_team_fallback`` is True)
      4. team-generic fallback (when ``use_team_fallback`` is True)

    Returns ``None`` only when steps 1-3 miss *and* the team fallback is
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
        diversified = _diversified_player_fallback(title)
        if diversified:
            return diversified
        return _team_fallback_media_id()
    return None
