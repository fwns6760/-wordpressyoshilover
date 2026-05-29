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
    """WP tag 検索で player name に一致する tag id を返す.

    2026-05-28 PM3 fix: roster の name は 「松本 剛」「赤星 優志」 等 全角空白を
    含む形式があるが、 WP tag は person_tag_router が登録時に空白除去版で作る
    ことが多い。 完全一致 → 空白除去一致 → contains 一致 の 3 段 fallback で
    miss を減らす。
    """
    creds = _wp_creds()
    if not creds:
        return None
    base, auth = creds
    target_raw = (player_name or "").strip()
    target_nosp = target_raw.replace(" ", "").replace("　", "")
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/tags",
            params={"search": target_raw, "per_page": 20, "_fields": "id,name"},
            auth=auth,
            timeout=15,
        )
        if not r.ok:
            return None
        tags = r.json() or []
        # 1. 完全一致
        for tag in tags:
            if str(tag.get("name", "")).strip() == target_raw:
                return int(tag.get("id"))
        # 2. 空白除去 一致 (松本 剛 ⇔ 松本剛)
        for tag in tags:
            name_nosp = str(tag.get("name", "")).strip().replace(" ", "").replace("　", "")
            if name_nosp == target_nosp:
                return int(tag.get("id"))
        # 3. search が空白入りで hit せず、 空白除去版で再検索
        if " " in target_raw or "　" in target_raw:
            r2 = requests.get(
                base + "/wp-json/wp/v2/tags",
                params={"search": target_nosp, "per_page": 20, "_fields": "id,name"},
                auth=auth,
                timeout=15,
            )
            if r2.ok:
                for tag in (r2.json() or []):
                    name_nosp = str(tag.get("name", "")).strip().replace(" ", "").replace("　", "")
                    if name_nosp == target_nosp:
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


@dataclass
class LineupSlotStat:
    """打順別 集計 (1.0a metric pack #1)。 slot_order = 1-9、 0 / NULL は代打等。"""
    slot_order: int
    games: int
    ab: int
    hits: int
    rbi: int

    @property
    def avg(self) -> Optional[float]:
        return (self.hits / self.ab) if self.ab > 0 else None


@dataclass
class OpponentSplitStat:
    """vs 各球団 集計 (1.0a metric pack #2)。"""
    opponent: str
    games: int
    ab: int
    hits: int
    rbi: int

    @property
    def avg(self) -> Optional[float]:
        return (self.hits / self.ab) if self.ab > 0 else None


@dataclass
class VenueSplitStat:
    """本拠地 / ビジター 別 集計 (Phase 1.0c metric pack #2 venue)。

    venue は '本拠地' (giants home) / 'ビジター' (giants away)。 巨人 home/away
    は game_id (NPB.jp box score code `{home}-{away}-{no}`) から判定。
    """
    venue: str
    games: int
    ab: int
    hits: int
    rbi: int

    @property
    def avg(self) -> Optional[float]:
        return (self.hits / self.ab) if self.ab > 0 else None


@dataclass
class StreakInfo:
    """連続記録 (Phase 1.0b1)。 active = 現在進行中、 season_max = 今シーズン最長."""
    active: int  # 現在連続中 (直近試合から遡って continuous)
    season_max: int  # 今シーズン最長 streak


@dataclass
class PitchingStatsSeason:
    """投手 season summary (Phase 1.5+α)。 全 0 なら data なし扱い."""
    games: int = 0
    wins: int = 0
    losses: int = 0
    saves: int = 0  # save_pitcher 出現回数 (pitching_logs に save column ない為、 games join で算出)
    ip: float = 0.0  # 投球回 (NPB 表記 0.1 / 0.2 を 1/3 / 2/3 として加算)
    k: int = 0
    bb: int = 0
    h_allowed: int = 0
    hr_allowed: int = 0
    er: int = 0
    pitches: int = 0

    @property
    def era(self) -> Optional[float]:
        return (self.er * 9.0 / self.ip) if self.ip > 0 else None

    @property
    def whip(self) -> Optional[float]:
        return ((self.h_allowed + self.bb) / self.ip) if self.ip > 0 else None

    @property
    def k_per_9(self) -> Optional[float]:
        return (self.k * 9.0 / self.ip) if self.ip > 0 else None

    @property
    def bb_per_9(self) -> Optional[float]:
        return (self.bb * 9.0 / self.ip) if self.ip > 0 else None


@dataclass
class PitchingGameRow:
    """1 試合分の投手成績 (直近 5 試合用)。"""
    game_date: str
    opponent: str
    result_mark: str
    ip: float
    h_allowed: int
    k: int
    bb: int
    er: int
    pitches: int


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


def fetch_lineup_slot_stats(player_canonical: str) -> list[LineupSlotStat]:
    """打順別 (1-9) 集計を返す。 大手未掲載 metric (rev4 Phase 1.0a #1)。

    batting_logs.slot_order GROUP BY、 NULL / 0 は除外 (代打等は別 metric)。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT slot_order,
                       COUNT(DISTINCT game_id) as g,
                       COALESCE(SUM(AB), 0) as ab,
                       COALESCE(SUM(H), 0) as h,
                       COALESCE(SUM(RBI), 0) as rbi
                FROM batting_logs
                WHERE player_canonical = ? AND slot_order IS NOT NULL AND slot_order > 0
                GROUP BY slot_order
                ORDER BY slot_order
                """,
                (player_canonical,),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_lineup_slot_stats err player=%s: %r", player_canonical, exc)
        return []
    return [
        LineupSlotStat(
            slot_order=int(r[0]),
            games=int(r[1] or 0),
            ab=int(r[2] or 0),
            hits=int(r[3] or 0),
            rbi=int(r[4] or 0),
        )
        for r in rows
    ]


def fetch_opponent_split_stats(player_canonical: str) -> list[OpponentSplitStat]:
    """vs 各球団 集計を返す。 大手未掲載 metric (rev4 Phase 1.0a #2)。

    batting_logs JOIN games で opponent GROUP BY、 自軍同士 (巨人 vs 巨人 紅白戦
    等) は通常 data 無いので無視。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT g.opponent,
                       COUNT(DISTINCT b.game_id) as g,
                       COALESCE(SUM(b.AB), 0) as ab,
                       COALESCE(SUM(b.H), 0) as h,
                       COALESCE(SUM(b.RBI), 0) as rbi
                FROM batting_logs b
                JOIN games g ON b.game_id = g.game_id
                WHERE b.player_canonical = ?
                  AND g.opponent IS NOT NULL AND g.opponent <> ''
                GROUP BY g.opponent
                ORDER BY g.opponent
                """,
                (player_canonical,),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_opponent_split_stats err player=%s: %r", player_canonical, exc)
        return []
    return [
        OpponentSplitStat(
            opponent=str(r[0]),
            games=int(r[1] or 0),
            ab=int(r[2] or 0),
            hits=int(r[3] or 0),
            rbi=int(r[4] or 0),
        )
        for r in rows
    ]


def giants_venue_from_game_id(game_id: str) -> Optional[str]:
    """game_id から 巨人視点の home/away を返す ('home' / 'away' / None)。

    game_id 形式 = `YYYY-MM-DD:{home}-{away}-{game_no}` (NPB.jp box score code、
    例: `2026-03-27:g-t-01` = 巨人 home vs 阪神 / `2026-03-31:d-g-01` = 中日 home,
    巨人 away)。 NPB.jp の URL code は home-away 順 (公式)。 巨人 code = 'g'。

    巨人が含まれない (= 巨人戦でない) game_id は None。
    """
    if not game_id or ":" not in game_id:
        return None
    code = game_id.partition(":")[2]
    parts = code.split("-")
    if len(parts) < 2:
        return None
    home, away = parts[0], parts[1]
    if home == "g":
        return "home"
    if away == "g":
        return "away"
    return None


def fetch_venue_split_stats(player_canonical: str) -> list[VenueSplitStat]:
    """本拠地 / ビジター 別 打撃集計を返す。 大手未掲載 metric (Phase 1.0c venue)。

    巨人 home/away は games.home_away column に依存せず game_id から判定する
    (column は全件 'unknown' だが game_id の NPB.jp code は信頼できる)。 本拠地 →
    ビジター の固定順で返し、 該当 0 試合の venue は省く。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT game_id,
                       COALESCE(AB, 0), COALESCE(H, 0), COALESCE(RBI, 0)
                FROM batting_logs
                WHERE player_canonical = ?
                """,
                (player_canonical,),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_venue_split_stats err player=%s: %r", player_canonical, exc)
        return []
    # venue ('home'/'away') ごとに game 数 + 打数 + 安打 + 打点 を集計。
    buckets: dict[str, dict[str, set | int]] = {
        "home": {"games": set(), "ab": 0, "hits": 0, "rbi": 0},
        "away": {"games": set(), "ab": 0, "hits": 0, "rbi": 0},
    }
    for game_id, ab, h, rbi in rows:
        venue = giants_venue_from_game_id(str(game_id or ""))
        if venue not in buckets:
            continue
        b = buckets[venue]
        b["games"].add(game_id)  # type: ignore[union-attr]
        b["ab"] = int(b["ab"]) + int(ab or 0)  # type: ignore[arg-type]
        b["hits"] = int(b["hits"]) + int(h or 0)  # type: ignore[arg-type]
        b["rbi"] = int(b["rbi"]) + int(rbi or 0)  # type: ignore[arg-type]
    label = {"home": "本拠地", "away": "ビジター"}
    out: list[VenueSplitStat] = []
    for key in ("home", "away"):
        b = buckets[key]
        n_games = len(b["games"])  # type: ignore[arg-type]
        if n_games == 0:
            continue
        out.append(
            VenueSplitStat(
                venue=label[key],
                games=n_games,
                ab=int(b["ab"]),  # type: ignore[arg-type]
                hits=int(b["hits"]),  # type: ignore[arg-type]
                rbi=int(b["rbi"]),  # type: ignore[arg-type]
            )
        )
    return out


def _compute_streak(values: list[int]) -> StreakInfo:
    """0/1 配列から active streak (先頭から連続 1) と season max を計算.

    values は 直近試合が先頭 (descending date)、 古い試合が末尾。 簡潔のため
    1 つの pass で active と max を同時計算する。
    """
    active = 0
    for v in values:
        if v >= 1:
            active += 1
        else:
            break
    season_max = 0
    cur = 0
    for v in values:
        if v >= 1:
            cur += 1
            if cur > season_max:
                season_max = cur
        else:
            cur = 0
    return StreakInfo(active=active, season_max=season_max)


def fetch_hit_streak(player_canonical: str) -> StreakInfo:
    """連続安打 streak (Phase 1.0b1 metric #3)。 batting_logs.H >= 1 連続."""
    path = _ensure_insight_db_local()
    if not path:
        return StreakInfo(active=0, season_max=0)
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT b.H FROM batting_logs b
                JOIN games g ON b.game_id = g.game_id
                WHERE b.player_canonical = ?
                ORDER BY g.game_date DESC, b.game_id DESC
                """,
                (player_canonical,),
            )
            rows = [int(r[0] or 0) for r in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_hit_streak err player=%s: %r", player_canonical, exc)
        return StreakInfo(active=0, season_max=0)
    return _compute_streak(rows)


def fetch_contribution_streak(player_canonical: str) -> StreakInfo:
    """連続得点関与 streak (Phase 1.0b1 metric #4)。 R + RBI >= 1 連続.

    得点 + 打点 = チームの得点に絡んだ試合の連続。 0 安打でも犠飛 / 押し出し
    で打点付けば 1 とカウント、 守備からの得点 (R) も含めて 「得点に関与」
    した試合。
    """
    path = _ensure_insight_db_local()
    if not path:
        return StreakInfo(active=0, season_max=0)
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT (COALESCE(b.R, 0) + COALESCE(b.RBI, 0)) as contrib
                FROM batting_logs b
                JOIN games g ON b.game_id = g.game_id
                WHERE b.player_canonical = ?
                ORDER BY g.game_date DESC, b.game_id DESC
                """,
                (player_canonical,),
            )
            rows = [int(r[0] or 0) for r in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_contribution_streak err player=%s: %r", player_canonical, exc)
        return StreakInfo(active=0, season_max=0)
    return _compute_streak(rows)


def fetch_pitching_stats_season(player_canonical: str) -> Optional[PitchingStatsSeason]:
    """投手 season summary。 win/lose は result_mark で集計、 IP は NPB 0.1/0.2 形式
    (小数 = 1/3 アウト) を正しく加算。 全 0 (= 出場 0) なら None."""
    path = _ensure_insight_db_local()
    if not path:
        return None
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(DISTINCT game_id) as g,
                       SUM(CASE WHEN result_mark = '○' THEN 1 ELSE 0 END) as w,
                       SUM(CASE WHEN result_mark = '●' THEN 1 ELSE 0 END) as l,
                       COALESCE(SUM(IP), 0) as ip_raw,
                       COALESCE(SUM(K), 0) as k,
                       COALESCE(SUM(BB), 0) as bb,
                       COALESCE(SUM(H_allowed), 0) as h,
                       COALESCE(SUM(HR_allowed), 0) as hr,
                       COALESCE(SUM(ER), 0) as er,
                       COALESCE(SUM(pitches), 0) as p
                FROM pitching_logs
                WHERE player_canonical = ?
                """,
                (player_canonical,),
            )
            row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_pitching_stats_season err player=%s: %r", player_canonical, exc)
        return None
    if not row or not row[0]:
        return None
    # IP NPB 形式 (例: 7.0 / 5.1 / 5.2) → 小数 = 1/3 アウトに換算
    # SUM(IP) は文字列値の合算なので 注意。 sqlite REAL 加算は単純加算、
    # 5.1 + 5.2 = 10.3 (正しくは 10.1 = 30.1 アウト)。 厳密 計算には game 単位で
    # convert 必要。 ここでは簡易扱い (display 用、 game 単位 IP を直接 SUM)。
    ip_raw = float(row[3] or 0.0)
    ip_correct = _normalize_npb_ip_sum(ip_raw)
    return PitchingStatsSeason(
        games=int(row[0]),
        wins=int(row[1] or 0),
        losses=int(row[2] or 0),
        saves=0,  # game.save_pitcher join で別途、 今は省略
        ip=ip_correct,
        k=int(row[4] or 0),
        bb=int(row[5] or 0),
        h_allowed=int(row[6] or 0),
        hr_allowed=int(row[7] or 0),
        er=int(row[8] or 0),
        pitches=int(row[9] or 0),
    )


def _normalize_npb_ip_sum(ip_sum_raw: float) -> float:
    """SUM(IP) の小数部 (1=1/3、 2=2/3) を正しく繰り上げ。

    例: 5.1 + 5.2 = 10.3 → 10.3 を whole=10、 frac=3 と解釈、 frac>=3 なら
    whole += frac // 3、 frac = frac % 3。 結果 10 + 1 = 11.0 (= 33 アウト).
    """
    # 元 IP が complex sum (e.g. 7.0+5.1+5.2 = 17.3) で 小数 3 以上は繰り上げ
    whole = int(ip_sum_raw)
    frac_tenth = round((ip_sum_raw - whole) * 10)
    if frac_tenth >= 3:
        whole += frac_tenth // 3
        frac_tenth = frac_tenth % 3
    return float(whole) + frac_tenth / 10.0


def fetch_recent_pitching_games(player_canonical: str, limit: int = 5) -> list[PitchingGameRow]:
    """直近 limit 登板の投手成績."""
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT g.game_date, g.opponent,
                       COALESCE(p.result_mark, ''),
                       COALESCE(p.IP, 0.0),
                       COALESCE(p.H_allowed, 0),
                       COALESCE(p.K, 0),
                       COALESCE(p.BB, 0),
                       COALESCE(p.ER, 0),
                       COALESCE(p.pitches, 0)
                FROM pitching_logs p
                JOIN games g ON p.game_id = g.game_id
                WHERE p.player_canonical = ?
                ORDER BY g.game_date DESC
                LIMIT ?
                """,
                (player_canonical, int(limit)),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_recent_pitching_games err player=%s: %r", player_canonical, exc)
        return []
    return [
        PitchingGameRow(
            game_date=str(r[0] or ""),
            opponent=str(r[1] or ""),
            result_mark=str(r[2] or ""),
            ip=float(r[3] or 0.0),
            h_allowed=int(r[4] or 0),
            k=int(r[5] or 0),
            bb=int(r[6] or 0),
            er=int(r[7] or 0),
            pitches=int(r[8] or 0),
        )
        for r in rows
    ]


__all__ = [
    "RosterPlayer",
    "BattingStatsSeason",
    "BattingGameRow",
    "LineupSlotStat",
    "OpponentSplitStat",
    "VenueSplitStat",
    "StreakInfo",
    "PitchingStatsSeason",
    "PitchingGameRow",
    "load_phase1_player_names",
    "load_roster_player",
    "find_player_tag_id",
    "fetch_related_topic_links",
    "find_player_featured_image_url",
    "fetch_batting_stats_season",
    "fetch_recent_games",
    "fetch_lineup_slot_stats",
    "fetch_opponent_split_stats",
    "fetch_venue_split_stats",
    "giants_venue_from_game_id",
    "fetch_hit_streak",
    "fetch_contribution_streak",
    "fetch_pitching_stats_season",
    "fetch_recent_pitching_games",
]
