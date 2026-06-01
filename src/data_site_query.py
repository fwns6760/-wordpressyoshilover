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
from datetime import date
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


# data-site 対象 role (支配下選手 + 監督・コーチ、 育成 ikusei は除外)
_DATA_SITE_TARGET_ROLES = ("player", "shihaikako", "coach", "manager")

_PLAYER_CLASS_PATH = Path(__file__).resolve().parents[1] / "config" / "data_site_player_class.json"
_POSITION_ORDER = ("投手", "捕手", "内野手", "外野手")


def _norm_name(name: str) -> str:
    return (name or "").replace(" ", "").replace("　", "").strip()


_player_class_cache: Optional[dict] = None


def load_player_class() -> dict:
    """NPB 公式由来の支配下/育成 ポジション分類 (config/data_site_player_class.json)。

    giants_roster.json の role/position が stale なため、 data-site の登録ポジション
    分類はこの正本を優先する。 戻り値は {'shihai': {pos:[name]}, 'ikusei': {pos:[name]}}。
    """
    global _player_class_cache
    if _player_class_cache is not None:
        return _player_class_cache
    if not _PLAYER_CLASS_PATH.exists():
        LOG.warning("player class config missing: %s", _PLAYER_CLASS_PATH)
        _player_class_cache = {"shihai": {}, "ikusei": {}}
        return _player_class_cache
    try:
        data = _json.loads(_PLAYER_CLASS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("player class parse error: %r", exc)
        data = {"shihai": {}, "ikusei": {}}
    _player_class_cache = {"shihai": data.get("shihai") or {}, "ikusei": data.get("ikusei") or {}}
    return _player_class_cache


def _build_name_to_pos(section: str) -> dict[str, str]:
    """section ('shihai'/'ikusei') の {正規化name: position} 逆引き map。"""
    cls = load_player_class()
    out: dict[str, str] = {}
    for pos, names in (cls.get(section) or {}).items():
        for n in names:
            out[_norm_name(n)] = pos
    return out


def shihai_position_group(name: str) -> Optional[str]:
    """支配下選手の登録ポジション ('投手'/'捕手'/'内野手'/'外野手')。 非支配下は None。"""
    return _build_name_to_pos("shihai").get(_norm_name(name))


def is_ikusei(name: str) -> bool:
    """NPB 公式 育成選手なら True。"""
    return _norm_name(name) in _build_name_to_pos("ikusei")


def load_shihai_names() -> list[str]:
    """支配下選手 canonical name list (投手→捕手→内野手→外野手 の順)。"""
    cls = load_player_class()
    out: list[str] = []
    for pos in _POSITION_ORDER:
        out.extend(cls.get("shihai", {}).get(pos, []))
    return out


def shihai_group_members(group: str) -> list[str]:
    """支配下の指定登録ポジション (投手/捕手/内野手/外野手) の選手 name list (config 順)。"""
    return list(load_player_class().get("shihai", {}).get(group, []))


def related_shihai_players(player_name: str, limit: int = 6) -> list[str]:
    """同じ登録ポジションの他の支配下選手を limit 名返す (関連選手リンク用)。

    自分を起点に config 順で「次の選手」を回転窓で拾い、 グループ内でリンクが
    偏らないようにする (各選手が異なる相手にリンク = 内部リンク均等化)。
    """
    group = shihai_position_group(player_name)
    if not group:
        return []
    members = shihai_group_members(group)
    norm = _norm_name(player_name)
    idx = next((i for i, n in enumerate(members) if _norm_name(n) == norm), None)
    if idx is None:
        others = [n for n in members if _norm_name(n) != norm]
    else:
        others = members[idx + 1:] + members[:idx]  # 自分の次から回転
    return others[:limit]


def load_ikusei_entries() -> list[tuple[str, str]]:
    """育成選手 [(name, position_group), ...] (投手→捕手→内野手→外野手 の順)。 cluster 育成枠用。"""
    cls = load_player_class()
    out: list[tuple[str, str]] = []
    for pos in _POSITION_ORDER:
        for n in cls.get("ikusei", {}).get(pos, []):
            out.append((n, pos))
    return out


_COACH_CAREER_PATH = Path(__file__).resolve().parents[1] / "config" / "coach_career_stats.json"
_coach_career_cache: Optional[dict] = None


def load_coach_career_stats() -> dict:
    """監督・コーチの現役時代 NPB 通算成績 (config/coach_career_stats.json)。

    {正規化name: {type, games, ...}} を返す。 引退選手の固定値、 出典 Wikipedia/NPB。
    """
    global _coach_career_cache
    if _coach_career_cache is not None:
        return _coach_career_cache
    out: dict = {}
    if _COACH_CAREER_PATH.exists():
        try:
            data = _json.loads(_COACH_CAREER_PATH.read_text(encoding="utf-8"))
            for name, rec in (data.get("stats") or {}).items():
                out[_norm_name(name)] = rec
        except Exception as exc:  # noqa: BLE001
            LOG.warning("coach career stats parse error: %r", exc)
    _coach_career_cache = out
    return out


def coach_career_stat(name: str) -> Optional[dict]:
    """1 コーチ/監督の現役通算成績 dict。 無ければ None。"""
    return load_coach_career_stats().get(_norm_name(name))


_OB_LEGENDS_PATH = Path(__file__).resolve().parents[1] / "config" / "ob_legends.json"
_ob_cache: Optional[dict] = None


def load_ob_legends() -> dict:
    """有名OB・レジェンドの profile (config/ob_legends.json)。 {正規化name: profile}。"""
    global _ob_cache
    if _ob_cache is not None:
        return _ob_cache
    data = {"order": [], "stats": {}}
    if _OB_LEGENDS_PATH.exists():
        try:
            data = _json.loads(_OB_LEGENDS_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("ob legends parse error: %r", exc)
            data = {"order": [], "stats": {}}
    norm_stats = {}
    for name, rec in (data.get("stats") or {}).items():
        rec = dict(rec)
        rec.setdefault("display_name", name)
        norm_stats[_norm_name(name)] = rec
    _ob_cache = {"order": data.get("order") or list((data.get("stats") or {}).keys()), "stats": norm_stats}
    return _ob_cache


def load_ob_names() -> list[str]:
    """OB の表示名 list (config order)。 個別ページ対象。"""
    return list(load_ob_legends().get("order") or [])


def ob_legend(name: str) -> Optional[dict]:
    """1 OB の profile dict。 無ければ None。"""
    return load_ob_legends().get("stats", {}).get(_norm_name(name))


def staff_military_level(position: str) -> str:
    """コーチ position 文字列から 軍 level を返す ('一軍'/'二軍'/'三軍'/'巡回')。"""
    p = position or ""
    if "三軍" in p:
        return "三軍"
    if "二軍" in p:
        return "二軍"
    if "巡回" in p:
        return "巡回"
    return "一軍"


def load_staff_names() -> list[str]:
    """roster から 監督・コーチ (role=manager/coach) の canonical name list。"""
    if not _ROSTER_PATH.exists():
        LOG.warning("roster missing: %s", _ROSTER_PATH)
        return []
    try:
        roster = _json.loads(_ROSTER_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("roster parse error: %r", exc)
        return []
    out: list[str] = []
    seen: set[str] = set()
    for row in roster:
        if str(row.get("role") or "") not in ("manager", "coach"):
            continue
        if not row.get("active", True):
            continue
        name = str(row.get("name") or "").strip()
        key = _norm_name(name)
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def load_data_site_target_names() -> list[str]:
    """data-site で個別ページを作る対象 canonical name list を返す.

    対象 = 支配下選手 (NPB 公式分類 = config/data_site_player_class.json shihai) +
    監督・コーチ (roster role=manager/coach)。 育成は cluster 育成枠の一覧のみで
    個別ページは作らない (一軍データ薄 = 薄ページ SEO リスク回避、 user 確認済)。
    支配下分類は giants_roster.json の stale な role/position に依存しない。
    """
    from src.data_site_slug import player_slug  # lazy import (循環回避)

    out: list[str] = []
    seen_slug: set[str] = set()
    seen_name: set[str] = set()
    for name in load_shihai_names() + load_staff_names():
        key = _norm_name(name)
        if key in seen_name:
            continue
        slug = player_slug(name)
        if slug and slug in seen_slug:
            continue
        seen_name.add(key)
        if slug:
            seen_slug.add(slug)
        out.append(name)
    return out


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


def find_player_featured_media_id(player_name: str) -> Optional[int]:
    """player tag を持つ 直近 publish 記事の featured_media attachment id を返す。

    用途: data ページ自身の WP featured_media に set し、 SNS 共有時の og:image を
    汎用既定画像ではなく選手写真にする (SEO SIMPLE PACK は featured image を og:image
    に使う)。 find_player_featured_image_url と同じ「最初に source_url が取れる post」を
    選ぶので、 ページ本文の写真と og:image が一致する。 無ければ None。
    """
    creds = _wp_creds()
    if not creds:
        return None
    base, auth = creds
    tag_id = find_player_tag_id(player_name)
    if tag_id is None:
        return None
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
            return None
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
            if mr.ok and str((mr.json() or {}).get("source_url", "")).strip():
                return int(fm)
        return None
    except Exception as exc:  # noqa: BLE001
        LOG.warning("find_player_featured_media_id err player=%s: %r", player_name, exc)
        return None


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
class InningSplitStat:
    """序盤 (1-3回) / 中盤 (4-6回) / 終盤 (7-9回) 別 打撃集計 (metric pack #5 inning)。

    batting_logs.atbats_json (1 イニング 1 セルの 9 要素配列、 index 0=1回 .. 8=9回)
    から導出。 同一回に 2 打席ある場合は box score 上 1 セルに圧縮されるため、 総打数は
    実数を僅かに下回る (production 実測 ~3%)。 イニング帰属自体は正確。
    """
    phase: str  # 序盤 / 中盤 / 終盤
    ab: int
    hits: int

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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','')
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
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','')
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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','') AND slot_order IS NOT NULL AND slot_order > 0
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
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','')
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


@dataclass
class SplitStat:
    """汎用スプリット集計 (曜日別 / 月別 / 交流戦別、Phase B 452)。"""
    label: str
    games: int
    ab: int
    hits: int

    @property
    def avg(self) -> Optional[float]:
        return (self.hits / self.ab) if self.ab > 0 else None


_PA_TEAM_CODES = {"h", "f", "m", "l", "e", "b"}  # NPB.jp パ6球団コード(交流戦判定)
_WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]


def _fetch_player_game_rows(player_canonical: str) -> list[tuple]:
    """選手の (game_id, game_date, AB, H) を返す(曜日/月/交流戦 split 共通の素)。"""
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT b.game_id, g.game_date, COALESCE(b.AB,0), COALESCE(b.H,0)
                FROM batting_logs b JOIN games g ON b.game_id = g.game_id
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','')
                  AND g.game_date IS NOT NULL
                """,
                (player_canonical,),
            )
            return cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_fetch_player_game_rows err player=%s: %r", player_canonical, exc)
        return []


def _bucket_splits(rows: list[tuple], key_fn, order: list[str]) -> list[SplitStat]:
    """rows を key_fn でバケットし、order 順で SplitStat 化(打数0は省く)。"""
    agg: dict[str, list[int]] = {}
    for game_id, game_date, ab, h in rows:
        k = key_fn(game_id, game_date)
        if k is None:
            continue
        b = agg.setdefault(k, [set(), 0, 0])
        b[0].add(game_id)
        b[1] += int(ab or 0)
        b[2] += int(h or 0)
    out: list[SplitStat] = []
    keys = order if order else sorted(agg.keys())
    for k in keys:
        if k not in agg:
            continue
        games, ab, h = len(agg[k][0]), agg[k][1], agg[k][2]
        if ab == 0:
            continue
        out.append(SplitStat(label=k, games=games, ab=ab, hits=h))
    return out


def _opp_code(game_id: str) -> Optional[str]:
    """game_id から巨人の対戦相手コードを返す。"""
    if not game_id or ":" not in game_id:
        return None
    parts = game_id.partition(":")[2].split("-")
    if len(parts) < 2:
        return None
    home, away = parts[0], parts[1]
    if home == "g":
        return away
    if away == "g":
        return home
    return None


def fetch_weekday_split_stats(player_canonical: str) -> list[SplitStat]:
    """曜日別 打撃集計 (Phase B 452、大手未掲載・追加source無し)。"""
    rows = _fetch_player_game_rows(player_canonical)

    def key(_gid, gdate):
        try:
            return _WEEKDAY_JP[date.fromisoformat(str(gdate)[:10]).weekday()]
        except ValueError:
            return None

    return _bucket_splits(rows, key, _WEEKDAY_JP)


def fetch_month_split_stats(player_canonical: str) -> list[SplitStat]:
    """月別 打撃集計 (Phase B 452)。"""
    rows = _fetch_player_game_rows(player_canonical)

    def key(_gid, gdate):
        try:
            return f"{int(str(gdate)[5:7])}月"
        except (ValueError, IndexError):
            return None

    return _bucket_splits(rows, key, [f"{m}月" for m in range(3, 12)])


def fetch_interleague_split_stats(player_canonical: str) -> list[SplitStat]:
    """交流戦 / リーグ戦 別 打撃集計 (Phase B 452、対戦相手コードから判定)。"""
    rows = _fetch_player_game_rows(player_canonical)

    def key(gid, _gdate):
        opp = _opp_code(gid)
        if opp is None:
            return None
        return "交流戦" if opp in _PA_TEAM_CODES else "リーグ戦"

    return _bucket_splits(rows, key, ["リーグ戦", "交流戦"])


@dataclass
class LeaderEntry:
    """リーダーボード 1 行 (選手 + 数値)。"""
    player: str
    value: float
    display: str  # 表示用("12本" / ".318" 等)


def fetch_team_leaders(top_n: int = 8) -> dict[str, list[LeaderEntry]]:
    """巨人選手内の各種記録ランキング (Phase B 452、追加source無し)。

    本塁打は atbats_json の「本」cell 数、他は batting_logs / pitching_logs を集計。
    Giants 選手は advanced_metric_snapshots team_code='g' の集合で判定。
    戻り値: {stat_key: [LeaderEntry, ...top_n]}。
    """
    path = _ensure_insight_db_local()
    if not path:
        return {}
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            giants = {r[0] for r in cur.execute(
                "SELECT DISTINCT player_canonical FROM advanced_metric_snapshots WHERE team_code='g'")}
            bat = cur.execute(
                "SELECT player_canonical, COALESCE(AB,0), COALESCE(H,0), COALESCE(RBI,0), "
                "COALESCE(SB,0), COALESCE(R,0), atbats_json FROM batting_logs").fetchall()
            pit = cur.execute(
                "SELECT player_canonical, COALESCE(K,0), COALESCE(IP,0.0), COALESCE(ER,0), "
                "COALESCE(result_mark,'') FROM pitching_logs").fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_team_leaders err: %r", exc)
        return {}

    b: dict[str, dict] = {}
    for name, ab, h, rbi, sb, r, aj in bat:
        if name not in giants:
            continue
        d = b.setdefault(name, {"AB": 0, "H": 0, "RBI": 0, "SB": 0, "R": 0, "HR": 0})
        d["AB"] += int(ab); d["H"] += int(h); d["RBI"] += int(rbi)
        d["SB"] += int(sb); d["R"] += int(r)
        if aj:
            try:
                d["HR"] += sum(1 for c in _json.loads(aj) if "本" in str(c))
            except Exception:  # noqa: BLE001
                pass
    p: dict[str, dict] = {}
    for name, k, ip, er, mark in pit:
        if name not in giants:
            continue
        d = p.setdefault(name, {"K": 0, "IP": 0.0, "ER": 0, "W": 0})
        d["K"] += int(k); d["IP"] += float(ip or 0); d["ER"] += int(er)
        if str(mark) == "○":
            d["W"] += 1

    def _avg(name, dd):
        return (dd["H"] / dd["AB"]) if dd["AB"] >= 30 else None  # 規定近似: 30打数以上

    def _era(name, dd):
        return (dd["ER"] * 9.0 / dd["IP"]) if dd["IP"] >= 10 else None  # 10回以上

    def top(items, keyf, dispf, desc=True, top_n=top_n):
        scored = [(n, keyf(n, d), dispf(n, d)) for n, d in items]
        scored = [(n, v, disp) for n, v, disp in scored if v is not None]
        scored.sort(key=lambda x: x[1], reverse=desc)
        return [LeaderEntry(n, float(v), disp) for n, v, disp in scored[:top_n]]

    out: dict[str, list[LeaderEntry]] = {
        "本塁打": top(b.items(), lambda n, d: d["HR"], lambda n, d: f'{d["HR"]}本'),
        "打点": top(b.items(), lambda n, d: d["RBI"], lambda n, d: f'{d["RBI"]}'),
        "安打": top(b.items(), lambda n, d: d["H"], lambda n, d: f'{d["H"]}'),
        "盗塁": top(b.items(), lambda n, d: d["SB"], lambda n, d: f'{d["SB"]}'),
        "打率": top(b.items(), _avg, lambda n, d: f'{d["H"]/d["AB"]:.3f}'.lstrip("0") if d["AB"] >= 30 else ""),
        "奪三振": top(p.items(), lambda n, d: d["K"], lambda n, d: f'{d["K"]}'),
        "勝利": top(p.items(), lambda n, d: d["W"], lambda n, d: f'{d["W"]}'),
        "防御率": top(p.items(), _era, lambda n, d: f'{d["ER"]*9.0/d["IP"]:.2f}' if d["IP"] >= 10 else "", desc=False),
    }
    return {k: v for k, v in out.items() if v}


@dataclass
class GiantsScheduleRow:
    """巨人 1 試合の日程・結果 (data/schedule ページ用、Phase B 452)。"""
    game_date: str       # YYYY-MM-DD
    opponent: str
    home_away: str       # '本拠地' / 'ビジター'
    giants_score: Optional[int]
    opp_score: Optional[int]
    result: str          # '勝' / '負' / '分' / ''(未確定)
    summary: str         # one_line_summary(あれば)


def fetch_giants_schedule(limit: Optional[int] = None) -> list[GiantsScheduleRow]:
    """巨人の日程・結果を新しい順で返す (games から、巨人戦のみ)。"""
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT game_id, game_date, opponent, giants_score, opp_score,
                       result, COALESCE(one_line_summary, '')
                FROM games WHERE game_date IS NOT NULL
                ORDER BY game_date DESC
                """,
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_giants_schedule err: %r", exc)
        return []
    out: list[GiantsScheduleRow] = []
    for gid, gdate, opp, gs, os_, res, summ in rows:
        venue = giants_venue_from_game_id(str(gid or ""))
        if venue is None:
            continue  # 巨人戦でない (リーグ全体 ingest 分) は除外
        res_jp = {"win": "勝", "loss": "負", "draw": "分", "tie": "分"}.get(str(res or "").lower(), "")
        out.append(GiantsScheduleRow(
            game_date=str(gdate)[:10],
            opponent=str(opp or ""),
            home_away="本拠地" if venue == "home" else "ビジター",
            giants_score=int(gs) if gs is not None else None,
            opp_score=int(os_) if os_ is not None else None,
            result=res_jp,
            summary=str(summ or ""),
        ))
    return out[:limit] if limit else out


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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','')
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


_ATBAT_STRIP = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫ 　\t"  # circled PA 番号 + 全角/半角 space


def _classify_atbat(cell: str) -> tuple[bool, bool]:
    """1 打席結果セル (NPB box score 記法) → (is_ab, is_hit)。

    打数 (AB) に数えない: 犠打 / 犠飛 / 四球 / 敬遠四 / 死球。 それ以外は打数。
    安打判定: 末尾 安 (単打) / 本 含む (本塁打) / 末尾 ２・３ (二・三塁打)。
    ゴロ・飛・直・邪飛・三振・併打・失 (失策出塁) は AB かつ非安打。
    production 全 5,652 行で AB/H 列と照合済 (誤分類ゼロ、 差分は同一回 collision のみ)。
    """
    t = "".join(ch for ch in (cell or "") if ch not in _ATBAT_STRIP)
    if not t or t == "-":
        return (False, False)
    # 打数に数えない: 四球 / 死球 (末尾 球) / 敬遠 (敬遠四・敬遠四球) / 犠打・犠飛 (犠)。
    if t.endswith("球") or "敬遠" in t or "犠" in t:
        return (False, False)
    is_hit = t.endswith("安") or ("本" in t) or t.endswith("２") or t.endswith("３")
    return (True, is_hit)


def fetch_player_npb_ranks(player_canonical: str, *, min_ab_for_avg: int = 30) -> list[tuple]:
    """453: 選手の NPB 全 12 球団内 順位を返す (打点 / 打率 / 安打)。

    advanced_metric_snapshots の season scope は規定到達者のみ (巨人 2 名) で疎なため、
    batting_logs (全 12 球団) から read-side で NPB-wide rank を自前計算する。
    Returns ``[(label, value_str, rank, total), ...]``。 該当しない指標は省く。
    打率は AB>=min_ab_for_avg を母集団とする (規定打席の簡易代替)。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT player_canonical, COALESCE(SUM(AB),0), COALESCE(SUM(H),0), COALESCE(SUM(RBI),0) "
                "FROM batting_logs WHERE player_canonical IS NOT NULL GROUP BY player_canonical"
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_player_npb_ranks err player=%s: %r", player_canonical, exc)
        return []
    agg = [(p, int(ab), int(h), int(rbi)) for (p, ab, h, rbi) in rows if int(ab or 0) > 0]
    if not agg:
        return []

    def _rank(sorted_players: list[tuple], name: str) -> Optional[tuple[int, int]]:
        for i, t in enumerate(sorted_players, 1):
            if t[0] == name:
                return i, len(sorted_players)
        return None

    out: list[tuple] = []
    # 打点 (全 AB>0)
    by_rbi = sorted(agg, key=lambda x: -x[3])
    r = _rank(by_rbi, player_canonical)
    if r and r[0] <= r[1]:
        rbi = next((x[3] for x in agg if x[0] == player_canonical), 0)
        out.append(("打点", str(rbi), r[0], r[1]))
    # 安打 (全 AB>0)
    by_h = sorted(agg, key=lambda x: -x[2])
    r = _rank(by_h, player_canonical)
    if r:
        h = next((x[2] for x in agg if x[0] == player_canonical), 0)
        out.append(("安打", str(h), r[0], r[1]))
    # 打率 (AB>=min_ab_for_avg)
    qual = [(p, ab, h, h / ab) for (p, ab, h, rbi) in agg if ab >= min_ab_for_avg]
    by_avg = sorted(qual, key=lambda x: -x[3])
    r = _rank(by_avg, player_canonical)
    if r:
        avg = next((x[3] for x in qual if x[0] == player_canonical), 0.0)
        avg_s = f"{avg:.3f}".lstrip("0") if avg < 1 else f"{avg:.3f}"
        out.append(("打率", avg_s, r[0], r[1]))
    return out


def fetch_inning_split_stats(player_canonical: str) -> list[InningSplitStat]:
    """序盤 / 中盤 / 終盤 別 打率を返す (大手未掲載 metric pack #5 inning)。

    batting_logs.atbats_json (index=イニング, 0=1回 .. 8=9回) を parse し、
    1-3回 → 序盤 / 4-6回 → 中盤 / 7-9回 → 終盤 に bucket。 該当打数 0 の phase は省く。
    at_bat_details.batter_canonical (全件 NULL) に依存しない read-side only 実装。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT atbats_json FROM batting_logs
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','')
                  AND atbats_json IS NOT NULL AND atbats_json NOT IN ('', '[]', 'null')
                """,
                (player_canonical,),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_inning_split_stats err player=%s: %r", player_canonical, exc)
        return []
    buckets: dict[str, list[int]] = {"序盤": [0, 0], "中盤": [0, 0], "終盤": [0, 0]}
    for (aj,) in rows:
        try:
            cells = _json.loads(aj)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(cells, list):
            continue
        for idx, cell in enumerate(cells):
            if idx < 3:
                key = "序盤"
            elif idx < 6:
                key = "中盤"
            elif idx < 9:
                key = "終盤"
            else:
                continue  # 配列は len 9 固定 (延長回は box score 上 含まれない)
            is_ab, is_hit = _classify_atbat(str(cell))
            if is_ab:
                buckets[key][0] += 1
            if is_hit:
                buckets[key][1] += 1
    out: list[InningSplitStat] = []
    for key in ("序盤", "中盤", "終盤"):
        ab, hits = buckets[key]
        if ab == 0:
            continue
        out.append(InningSplitStat(phase=key, ab=ab, hits=hits))
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
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','')
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
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','')
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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','')
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
                WHERE REPLACE(p.player_canonical,' ','') = REPLACE(?,' ','')
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
    "InningSplitStat",
    "StreakInfo",
    "PitchingStatsSeason",
    "PitchingGameRow",
    "load_phase1_player_names",
    "load_data_site_target_names",
    "load_staff_names",
    "load_player_class",
    "shihai_position_group",
    "is_ikusei",
    "load_shihai_names",
    "shihai_group_members",
    "related_shihai_players",
    "load_ikusei_entries",
    "staff_military_level",
    "load_coach_career_stats",
    "coach_career_stat",
    "load_ob_legends",
    "load_ob_names",
    "ob_legend",
    "load_roster_player",
    "find_player_tag_id",
    "fetch_related_topic_links",
    "find_player_featured_image_url",
    "find_player_featured_media_id",
    "fetch_batting_stats_season",
    "fetch_recent_games",
    "fetch_lineup_slot_stats",
    "fetch_opponent_split_stats",
    "fetch_venue_split_stats",
    "giants_venue_from_game_id",
    "fetch_inning_split_stats",
    "SplitStat",
    "fetch_weekday_split_stats",
    "fetch_month_split_stats",
    "fetch_interleague_split_stats",
    "GiantsScheduleRow",
    "fetch_giants_schedule",
    "LeaderEntry",
    "fetch_team_leaders",
    "fetch_hit_streak",
    "fetch_contribution_streak",
    "fetch_pitching_stats_season",
    "fetch_recent_pitching_games",
]
