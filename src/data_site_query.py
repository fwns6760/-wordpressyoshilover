"""Data site Phase 1.0 用 read-only クエリ (ticket 444).

- roster (config/giants_roster.json) から player info 取得
- WP REST から該当 player tag の関連記事 (Topic) 取得 (10-20 件)
- insight.db (GCS cache) から打撃 stats season summary + 直近 5 試合 取得

Phase 1.0 (rev2 2026-05-28 PM3): insight.db batting_logs を SUM して大手相当の
打撃 stats (試合 / 打率 / 安打 / 打点 / 得点 / 盗塁) を出す。 投手 stats は
Phase 1.5 で 別 source (pitching_logs) を扱う。 insight.db に未収録 player は
None を返し、 template 側で「データ集計中」 placeholder。
"""

from __future__ import annotations

import json as _json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
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


@dataclass
class BattingStatsSeason:
    """打撃 season summary。 全 None なら data 無し (insight.db 未収録 / 出場 0)。"""
    games: int = 0
    ab: int = 0
    hits: int = 0
    rbi: int = 0
    runs: int = 0
    sb: int = 0

    @property
    def avg(self) -> Optional[float]:
        return (self.hits / self.ab) if self.ab > 0 else None


@dataclass
class BattingGameRow:
    """1 試合分の打撃結果 (直近 5 試合表示用)。"""
    game_date: str
    opponent: str
    ab: int
    hits: int
    rbi: int
    runs: int = 0
    sb: int = 0


def _insight_db_path() -> str:
    """env INSIGHT_DB_PATH (override) or default cache path."""
    explicit = os.environ.get("INSIGHT_DB_PATH", "").strip()
    return explicit or "/tmp/insight_cache/insight.db"


def _ensure_insight_db_local() -> Optional[str]:
    """GCS から insight.db を local cache に download (TTL 1h)、 path を返す.

    既に local file あれば再 download せず、 missing で download 失敗時は None。
    呼び出し元は None なら stats なし扱い (template placeholder)。
    """
    path = _insight_db_path()
    if os.path.exists(path):
        return path
    bucket = (os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()
    if not bucket:
        LOG.warning("INSIGHT_GCS_BUCKET env unset and no local insight.db cache; stats unavailable")
        return None
    try:
        # Lazy import to avoid hard dependency at module load
        from google.cloud import storage  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        LOG.warning("google-cloud-storage import failed: %r", exc)
        return None
    prefix = (os.environ.get("INSIGHT_GCS_PREFIX") or "").strip().strip("/")
    object_name = f"{prefix}/insight.db" if prefix else "insight.db"
    try:
        client = storage.Client()
        bucket_obj = client.bucket(bucket)
        blob = bucket_obj.blob(object_name)
        if not blob.exists():
            LOG.warning("insight.db blob missing in GCS: bucket=%s name=%s", bucket, object_name)
            return None
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(path)
        return path
    except Exception as exc:  # noqa: BLE001
        LOG.warning("insight.db download failed: %r", exc)
        return None


def fetch_batting_stats_season(player_canonical: str) -> Optional[BattingStatsSeason]:
    """insight.db batting_logs を SUM して season summary を返す.

    未収録 (rows=0 or player table 不在) なら None を返し、 template は placeholder。
    """
    path = _ensure_insight_db_local()
    if not path:
        return None
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(DISTINCT game_id) as g,
                       COALESCE(SUM(AB), 0) as ab,
                       COALESCE(SUM(H), 0) as h,
                       COALESCE(SUM(RBI), 0) as rbi,
                       COALESCE(SUM(R), 0) as r,
                       COALESCE(SUM(SB), 0) as sb
                FROM batting_logs
                WHERE player_canonical = ?
                """,
                (player_canonical,),
            )
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_batting_stats_season err player=%s: %r", player_canonical, exc)
        return None
    if not row or not row[0]:
        return None
    return BattingStatsSeason(
        games=int(row[0]),
        ab=int(row[1] or 0),
        hits=int(row[2] or 0),
        rbi=int(row[3] or 0),
        runs=int(row[4] or 0),
        sb=int(row[5] or 0),
    )


def fetch_recent_games(player_canonical: str, limit: int = 5) -> list[BattingGameRow]:
    """直近 limit 試合の打撃結果。 insight.db batting_logs JOIN games。"""
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT g.game_date, g.opponent,
                       COALESCE(b.AB, 0), COALESCE(b.H, 0),
                       COALESCE(b.RBI, 0), COALESCE(b.R, 0),
                       COALESCE(b.SB, 0)
                FROM batting_logs b
                JOIN games g ON b.game_id = g.game_id
                WHERE b.player_canonical = ?
                ORDER BY g.game_date DESC
                LIMIT ?
                """,
                (player_canonical, int(limit)),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_recent_games err player=%s: %r", player_canonical, exc)
        return []
    return [
        BattingGameRow(
            game_date=str(r[0] or ""),
            opponent=str(r[1] or ""),
            ab=int(r[2] or 0),
            hits=int(r[3] or 0),
            rbi=int(r[4] or 0),
            runs=int(r[5] or 0),
            sb=int(r[6] or 0),
        )
        for r in rows
    ]


__all__ = [
    "RosterPlayer",
    "BattingStatsSeason",
    "BattingGameRow",
    "load_phase1_player_names",
    "load_roster_player",
    "find_player_tag_id",
    "fetch_related_topic_links",
    "find_player_featured_image_url",
    "fetch_batting_stats_season",
    "fetch_recent_games",
]
