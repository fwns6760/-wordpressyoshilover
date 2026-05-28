"""Data site Phase 1.0 用 read-only クエリ (ticket 444).

- roster (config/giants_roster.json) から player info 取得
- WP REST から該当 player tag の関連記事 (Topic) 取得 (10-20 件)

Phase 1.0 では insight.db 接続は省略 (placeholder)、 Phase 1.5 以降で stats 接続。
"""

from __future__ import annotations

import json as _json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth


LOG = logging.getLogger(__name__)

_ROSTER_PATH = Path(__file__).resolve().parents[1] / "config" / "giants_roster.json"
_PHASE1_PLAYERS_PATH = Path(__file__).resolve().parents[1] / "config" / "data_site_phase1_players.json"


@dataclass
class RosterPlayer:
    """roster (giants_roster.json) の active player 抜粋。"""
    name: str
    position: str
    jersey_number: str
    role: str
    aliases: list[str]


def load_phase1_player_names() -> list[str]:
    """config/data_site_phase1_players.json から 対象 player canonical name list を返す."""
    if not _PHASE1_PLAYERS_PATH.exists():
        LOG.warning("phase1 player config missing: %s", _PHASE1_PLAYERS_PATH)
        return []
    try:
        data = _json.loads(_PHASE1_PLAYERS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("phase1 player config parse error: %r", exc)
        return []
    return [p["name"] for p in (data.get("players") or []) if p.get("name")]


def load_roster_player(canonical_name: str) -> Optional[RosterPlayer]:
    """roster から canonical name で 1 player を引く。 半角/全角空白を正規化して照合。"""
    if not _ROSTER_PATH.exists():
        return None
    try:
        roster = _json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("roster parse error: %r", exc)
        return None
    target = canonical_name.replace(" ", "").replace("　", "")
    for row in roster:
        name = str(row.get("name", "") or "").replace(" ", "").replace("　", "")
        if name != target:
            continue
        return RosterPlayer(
            name=str(row.get("name") or "").strip(),
            position=str(row.get("position") or "").strip(),
            jersey_number=str(row.get("jersey_number") or "").strip(),
            role=str(row.get("role") or "player").strip(),
            aliases=list(row.get("aliases") or []),
        )
    return None


def _wp_creds() -> tuple[str, HTTPBasicAuth] | None:
    """WP_URL / WP_USER / WP_APP_PASSWORD env から WP REST 認証情報。"""
    base = os.environ.get("WP_URL", "").strip().rstrip("/")
    user = os.environ.get("WP_USER", "").strip()
    pw = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and pw):
        LOG.warning("WP REST creds missing (WP_URL/WP_USER/WP_APP_PASSWORD)")
        return None
    return base, HTTPBasicAuth(user, pw)


def find_player_tag_id(player_name: str) -> Optional[int]:
    """WP tag 検索で player name に一致する tag id を返す (person_tag_router が routing 済の前提)."""
    creds = _wp_creds()
    if not creds:
        return None
    base, auth = creds
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/tags",
            params={"search": player_name, "per_page": 20, "_fields": "id,name"},
            auth=auth,
            timeout=15,
        )
        if not r.ok:
            return None
        for tag in (r.json() or []):
            if str(tag.get("name", "")).strip() == player_name:
                return int(tag.get("id"))
        return None
    except Exception as exc:  # noqa: BLE001
        LOG.warning("find_player_tag_id err player=%s: %r", player_name, exc)
        return None


def fetch_related_topic_links(player_name: str, limit: int = 20) -> list[tuple[str, str]]:
    """player tag を持つ 既存 publish 記事 link を最大 limit 件返す (Pillar → Topic link 用).

    Returns: [(post_link, post_title), ...]
    """
    creds = _wp_creds()
    if not creds:
        return []
    base, auth = creds
    tag_id = find_player_tag_id(player_name)
    if tag_id is None:
        LOG.info("no_player_tag player=%s", player_name)
        return []
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/posts",
            params={
                "tags": tag_id,
                "status": "publish",
                "per_page": limit,
                "orderby": "date",
                "order": "desc",
                "_fields": "id,title,link",
            },
            auth=auth,
            timeout=30,
        )
        if not r.ok:
            return []
        out: list[tuple[str, str]] = []
        for post in (r.json() or []):
            link = str(post.get("link", "")).strip()
            title = str((post.get("title") or {}).get("rendered", "")).strip()
            if link and title:
                out.append((link, title))
        return out
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_related_topic_links err player=%s: %r", player_name, exc)
        return []


def find_player_featured_image_url(player_name: str) -> str:
    """player tag を持つ 直近 publish 記事の featured_media URL を返す (Pillar 上部 写真用).

    無ければ空文字 (template 側で team mark fallback)。
    """
    creds = _wp_creds()
    if not creds:
        return ""
    base, auth = creds
    tag_id = find_player_tag_id(player_name)
    if tag_id is None:
        return ""
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/posts",
            params={
                "tags": tag_id,
                "status": "publish",
                "per_page": 5,
                "orderby": "date",
                "order": "desc",
                "_fields": "id,featured_media",
            },
            auth=auth,
            timeout=30,
        )
        if not r.ok:
            return ""
        for post in (r.json() or []):
            fm = post.get("featured_media")
            if not fm:
                continue
            mr = requests.get(
                base + f"/wp-json/wp/v2/media/{int(fm)}",
                params={"_fields": "source_url"},
                auth=auth,
                timeout=15,
            )
            if mr.ok:
                url = str((mr.json() or {}).get("source_url", "")).strip()
                if url:
                    return url
        return ""
    except Exception as exc:  # noqa: BLE001
        LOG.warning("find_player_featured_image_url err player=%s: %r", player_name, exc)
        return ""


__all__ = [
    "RosterPlayer",
    "load_phase1_player_names",
    "load_roster_player",
    "find_player_tag_id",
    "fetch_related_topic_links",
    "find_player_featured_image_url",
]
