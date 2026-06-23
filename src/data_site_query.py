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
import html as _html
import logging
import os
import re
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
# 選手 pillar の顔写真 = 正本マッピング config/player_eyecatch_map.json ({正規化name: {id, title}})。
# 旧実装は「最新タグ記事の eyecatch 流用」で対戦相手のチームマーク等が混入していたため、
# この curated map を最優先にする。map に無い player は巨人マークに fallback (対戦相手は出さない)。
_EYECATCH_MAP_PATH = Path(__file__).resolve().parents[1] / "config" / "player_eyecatch_map.json"
_GIANTS_MARK_MEDIA_ID = 63578  # yoshilover / 巨人 brand mark (player 写真が無い時の安全 fallback)
_EYECATCH_MAP_CACHE: Optional[dict] = None


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

# 退団選手の自動除外 (self-heal): config (data_site_player_class.json) が手動正本で
# 退団検知に穴があるため、 publish 時に NPB 公式現役名簿で player_class を濾過する。
# config に居ても NPB 公式に居ない選手 (例: 移籍/引退済) はページ生成・index から外す。
# NPB fetch 失敗時や名簿が薄すぎる時は濾過しない (= 既存 config を尊重、安全側)。
_LIVE_ROSTER_FLOOR = 80  # raw NPB 名簿がこの数未満なら fetch 不全とみなし濾過しない
_npb_active_names_cache: Optional[frozenset] = None
_npb_active_names_fetched = False


def _live_filter_enabled() -> bool:
    return (os.environ.get("DATA_SITE_ROSTER_LIVE_FILTER", "1").strip() or "1") != "0"


def _current_npb_norm_names() -> Optional[frozenset]:
    """NPB 公式 現役名簿 (支配下+育成) の正規化名 set。

    濾過の権威は giants_roster.json でも loader merge 結果でもなく、 NPB 公式 raw
    fetch のみ (両者は退団選手を残す union のため)。 fetch 失敗・名簿薄 (< floor)・
    flag OFF なら None を返し、 呼び出し側は濾過を skip する。"""
    global _npb_active_names_cache, _npb_active_names_fetched
    if _npb_active_names_fetched:
        return _npb_active_names_cache
    _npb_active_names_fetched = True
    if not _live_filter_enabled():
        _npb_active_names_cache = None
        return None
    try:
        from src import giants_roster_loader as _grl

        raw = _grl._fetch_npb_roster()
        names = {_norm_name(str(e.get("name") or "")) for e in (raw or [])}
        names.discard("")
        if len(names) < _LIVE_ROSTER_FLOOR:
            LOG.warning("NPB roster fetch too thin (%d < %d) — skip live filter",
                        len(names), _LIVE_ROSTER_FLOOR)
            _npb_active_names_cache = None
        else:
            _npb_active_names_cache = frozenset(names)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("NPB roster fetch failed — skip live filter: %r", exc)
        _npb_active_names_cache = None
    return _npb_active_names_cache


def _apply_live_roster_filter(classes: dict) -> dict:
    """player_class から NPB 公式現役名簿に居ない選手を除外する (退団 self-heal)。"""
    npb = _current_npb_norm_names()
    if not npb:
        return classes
    dropped: list[str] = []
    for section in ("shihai", "ikusei"):
        bucket = classes.get(section) or {}
        for pos, names in list(bucket.items()):
            kept = [n for n in names if _norm_name(n) in npb]
            if len(kept) != len(names):
                dropped.extend(n for n in names if _norm_name(n) not in npb)
            bucket[pos] = kept
        classes[section] = bucket
    if dropped:
        LOG.warning("live roster filter dropped %d departed player(s): %s",
                    len(dropped), ", ".join(dropped))
    return classes


def load_player_class() -> dict:
    """NPB 公式由来の支配下/育成 ポジション分類 (config/data_site_player_class.json)。

    giants_roster.json の role/position が stale なため、 data-site の登録ポジション
    分類はこの正本を優先する。 戻り値は {'shihai': {pos:[name]}, 'ikusei': {pos:[name]}}。
    publish 時は NPB 公式現役名簿で濾過し、 退団選手を自動除外する (_apply_live_roster_filter)。
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
    classes = {"shihai": data.get("shihai") or {}, "ikusei": data.get("ikusei") or {}}
    _player_class_cache = _apply_live_roster_filter(classes)
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


# Tier0 網羅: ob_legends_full.json(手動21名 + Wikipedia自動抽出710名 = 731名)を正本に。
# ob_legends.json は手動curatedの入力(build script が full へ merge)。full が無ければ curated に fallback。
_OB_LEGENDS_FULL_PATH = Path(__file__).resolve().parents[1] / "config" / "ob_legends_full.json"
_OB_LEGENDS_CURATED_PATH = Path(__file__).resolve().parents[1] / "config" / "ob_legends.json"
_OB_LEGENDS_PATH = _OB_LEGENDS_FULL_PATH if _OB_LEGENDS_FULL_PATH.exists() else _OB_LEGENDS_CURATED_PATH
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


_current_roster_names_cache: Optional[set] = None


def _current_roster_names() -> set:
    """現役roster (現役選手・監督・コーチ) の正規化名 set。 OB 名鑑から除外する用。"""
    global _current_roster_names_cache
    if _current_roster_names_cache is not None:
        return _current_roster_names_cache
    names = set()
    if _ROSTER_PATH.exists():
        try:
            for row in _json.loads(_ROSTER_PATH.read_text(encoding="utf-8")):
                n = _norm_name(str(row.get("name", "") or ""))
                if n:
                    names.add(n)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("roster parse error (current names): %r", exc)
    _current_roster_names_cache = names
    return names


def load_ob_names() -> list[str]:
    """OB の表示名 list (config order)。 個別ページ対象。

    現役roster (現役選手・監督・コーチ) に在籍する名前は除外する。 退団選手が現コーチを
    兼ねる場合 (内海哲也 等) を OB として二重掲載せず、 現役側 (監督・コーチ表) で扱う。
    """
    cur = _current_roster_names()
    return [n for n in (load_ob_legends().get("order") or []) if _norm_name(n) not in cur]


def ob_legend(name: str) -> Optional[dict]:
    """1 OB の profile dict。 無ければ None。"""
    return load_ob_legends().get("stats", {}).get(_norm_name(name))


def load_ob_legend_entries() -> list[dict]:
    """OB・レジェンドを config order で full profile dict のリストに (legends hub 用)。"""
    out = []
    for n in load_ob_names():
        e = ob_legend(n)
        if e:
            e = dict(e); e.setdefault("display_name", n)
            out.append(e)
    return out


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


def _wp_creds(*, warn: bool = True) -> tuple[str, HTTPBasicAuth] | None:
    """WP_URL / WP_USER / WP_APP_PASSWORD env から WP REST 認証情報。"""
    base = os.environ.get("WP_URL", "").strip().rstrip("/")
    user = os.environ.get("WP_USER", "").strip()
    pw = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and pw):
        if warn:
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


def _load_eyecatch_map() -> dict:
    """config/player_eyecatch_map.json を load (cache)。 {正規化name: {id, title}}。"""
    global _EYECATCH_MAP_CACHE
    if _EYECATCH_MAP_CACHE is not None:
        return _EYECATCH_MAP_CACHE
    data: dict = {}
    try:
        raw = _json.loads(_EYECATCH_MAP_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            # key を空白除去で正規化し直して引きやすくする (元 key は表記名)。
            for name, entry in raw.items():
                key = str(name).replace(" ", "").replace("　", "")
                if key:
                    data[key] = entry
    except Exception as exc:  # noqa: BLE001
        LOG.warning("eyecatch map load error: %r", exc)
    _EYECATCH_MAP_CACHE = data
    return data


def mapped_player_media_id(player_name: str) -> Optional[int]:
    """curated eyecatch map から player の featured_media id を返す。 無ければ None。"""
    key = str(player_name or "").replace(" ", "").replace("　", "")
    entry = _load_eyecatch_map().get(key)
    if isinstance(entry, dict) and entry.get("id"):
        try:
            return int(entry["id"])
        except (TypeError, ValueError):
            return None
    return None


def _media_source_url(media_id: int, base: str, auth: HTTPBasicAuth | None = None) -> str:
    """media id の source_url を返す。 失敗時 空文字。"""
    try:
        kwargs = {
            "params": {"_fields": "source_url"},
            "timeout": 15,
        }
        if auth is not None:
            kwargs["auth"] = auth
        mr = requests.get(
            base + f"/wp-json/wp/v2/media/{int(media_id)}",
            **kwargs,
        )
        if mr.ok:
            return str((mr.json() or {}).get("source_url", "")).strip()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_media_source_url err media=%s: %r", media_id, exc)
    return ""


def find_player_featured_image_url(player_name: str) -> str:
    """選手 pillar 上部の顔写真 URL を返す。

    ① curated eyecatch map (config/player_eyecatch_map.json) の選手写真を最優先。
    ② map に無ければ 巨人マーク (_GIANTS_MARK_MEDIA_ID) に fallback。
    旧実装の「最新タグ記事 eyecatch 流用」は対戦相手のチームマーク等が混入するため廃止。
    """
    creds = _wp_creds(warn=False)
    if creds:
        base, auth = creds
    else:
        base = os.environ.get("WP_URL", "").strip().rstrip("/") or "https://yoshilover.com"
        auth = None
    mid = mapped_player_media_id(player_name)
    if mid:
        url = _media_source_url(mid, base, auth)
        if url:
            return url
    # fallback: 巨人マーク (対戦相手マーク / 無関係画像は出さない)
    return _media_source_url(_GIANTS_MARK_MEDIA_ID, base, auth)


def find_player_featured_media_id(player_name: str) -> Optional[int]:
    """data ページ自身の WP featured_media (= og:image) に set する attachment id。

    ① curated eyecatch map の選手写真 id を最優先 (ページ本文の写真と一致)。
    ② map に無ければ 巨人マーク id に fallback。 SEO SIMPLE PACK が featured image を
    og:image に使うため、 SNS 共有でも対戦相手マークでなく選手写真/巨人マークになる。
    """
    mid = mapped_player_media_id(player_name)
    if mid:
        return mid
    return _GIANTS_MARK_MEDIA_ID


@dataclass
class BattingStatsSeason:
    """打撃 season summary。 全 None なら data 無し (insight.db 未収録 / 出場 0)。"""
    games: int = 0
    ab: int = 0
    hits: int = 0
    rbi: int = 0
    runs: int = 0
    sb: int = 0
    hr: int = 0

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


def _ichigun_official_enabled() -> bool:
    return (os.environ.get("DATA_SITE_ICHIGUN_OFFICIAL", "1").strip() or "1") != "0"


def fetch_batting_stats_season(player_canonical: str) -> Optional[BattingStatsSeason]:
    """今季 一軍 打撃 season summary を返す.

    正本は NPB 公式 一軍 個人打撃成績 (シーズン合計)。 insight.db は box score 積み上げで
    試合取込漏れ (例: 宇都宮葵星 6試合2打数 が 0 になる) があるため、 公式合計を優先する。
    公式に居ない / fetch 失敗時のみ insight.db SUM に fallback。 どちらも無ければ None
    (template は placeholder)。 env DATA_SITE_ICHIGUN_OFFICIAL=0 で公式 source を無効化。
    """
    if _ichigun_official_enabled():
        try:
            from src.data_site_ichigun_stats import giants_ichigun_batting_map

            rec = giants_ichigun_batting_map().get(_norm_name(player_canonical))
            if rec and rec.get("games"):
                return BattingStatsSeason(
                    games=int(rec.get("games") or 0),
                    ab=int(rec.get("ab") or 0),
                    hits=int(rec.get("hits") or 0),
                    rbi=int(rec.get("rbi") or 0),
                    runs=int(rec.get("runs") or 0),
                    sb=int(rec.get("sb") or 0),
                    hr=int(rec.get("hr") or 0),
                )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("ichigun official batting fetch failed player=%s: %r",
                        player_canonical, exc)
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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','') AND team_name = '巨人'
                """,
                (player_canonical,),
            )
            row = cur.fetchone()
            # 本塁打は列が無く atbats_json (打席結果 cell) から導出する
            # (fetch_team_leaders の 本塁打 board と同方式: 「本」 を含む cell を数える)。
            cur.execute(
                """
                SELECT atbats_json FROM batting_logs
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','')
                  AND team_name = '巨人' AND atbats_json IS NOT NULL
                """,
                (player_canonical,),
            )
            hr = 0
            for (aj,) in cur.fetchall():
                if not aj:
                    continue
                try:
                    hr += sum(1 for c in _json.loads(aj) if "本" in str(c))
                except Exception:  # noqa: BLE001
                    pass
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
        hr=hr,
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
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','') AND b.team_name = '巨人'
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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','') AND team_name = '巨人' AND slot_order IS NOT NULL AND slot_order > 0
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
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','') AND b.team_name = '巨人'
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
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','') AND b.team_name = '巨人'
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
class GameDetail:
    """1 試合の巨人 box score (data/game ページ用、Phase B 452)。"""
    game_id: str
    game_date: str
    opponent: str
    home_away: str
    giants_score: Optional[int]
    opp_score: Optional[int]
    result: str
    summary: str
    batting: list[tuple]   # (slot, position, name, AB, R, H, RBI)
    pitching: list[tuple]  # (name, IP, H, K, BB, ER, mark)


def fetch_game_detail(game_id: str) -> Optional[GameDetail]:
    """巨人 1 試合の box score(打順別打撃 + 投手)を返す。巨人戦でなければ None。"""
    venue = giants_venue_from_game_id(game_id)
    if venue is None:
        return None
    path = _ensure_insight_db_local()
    if not path:
        return None
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            g = cur.execute(
                "SELECT game_date,opponent,giants_score,opp_score,result,COALESCE(one_line_summary,'') "
                "FROM games WHERE game_id=?", (game_id,)).fetchone()
            if not g:
                return None
            bat = cur.execute(
                "SELECT slot_order,position,player_display,COALESCE(AB,0),COALESCE(R,0),"
                "COALESCE(H,0),COALESCE(RBI,0) FROM batting_logs "
                "WHERE game_id=? AND team_role='giants' ORDER BY slot_order, is_sub", (game_id,)).fetchall()
            pit = cur.execute(
                "SELECT player_display,COALESCE(IP,0.0),COALESCE(H_allowed,0),COALESCE(K,0),"
                "COALESCE(BB,0),COALESCE(ER,0),COALESCE(result_mark,'') FROM pitching_logs "
                "WHERE game_id=? AND team_role='giants' ORDER BY appearance_order", (game_id,)).fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_game_detail err %s: %r", game_id, exc)
        return None
    res_jp = {"win": "勝", "loss": "負", "draw": "分", "tie": "分"}.get(str(g[4] or "").lower(), "")
    return GameDetail(
        game_id=game_id, game_date=str(g[0])[:10], opponent=str(g[1] or ""),
        home_away="本拠地" if venue == "home" else "ビジター",
        giants_score=int(g[2]) if g[2] is not None else None,
        opp_score=int(g[3]) if g[3] is not None else None,
        result=res_jp, summary=str(g[5] or ""),
        batting=[tuple(r) for r in bat], pitching=[tuple(r) for r in pit],
    )


def game_slug(game_id: str) -> str:
    """game_id → 安定 slug。例 '2026-05-31:f-g-03' → 'game-2026-05-31-f-g-03'。"""
    return "game-" + game_id.replace(":", "-")


_CENTRAL_TEAM_JP = {"g": "巨人", "t": "阪神", "db": "DeNA", "c": "広島", "s": "ヤクルト", "d": "中日"}


def fetch_team_rankings(scope: str = "season") -> dict[str, list[tuple]]:
    """セ・リーグ6球団の 打率/防御率/本塁打 ランキング (Phase B 452)。

    既存の検証済み `team_ranking_publisher` の aggregator を reuse(独自集計でなく)。
    戻り値: {metric_label: [(team_jp, value_display, rank, is_giants), ...]}。
    """
    path = _ensure_insight_db_local()
    if not path:
        return {}
    try:
        from src.analysis import team_ranking_publisher as tr
    except Exception as exc:  # noqa: BLE001
        LOG.warning("team_ranking_publisher import fail: %r", exc)
        return {}
    specs = [
        ("打率", tr.aggregate_team_avg, True, lambda v: f"{v:.3f}".lstrip("0")),
        ("防御率", tr.aggregate_team_era, False, lambda v: f"{v:.2f}"),
        ("本塁打", tr.aggregate_team_hr, True, lambda v: f"{int(v)}本"),
    ]
    out: dict[str, list[tuple]] = {}
    try:
        with sqlite3.connect(path) as conn:
            for label, fn, desc, disp in specs:
                try:
                    rows = fn(conn, scope=scope) or []
                except Exception as exc:  # noqa: BLE001
                    LOG.warning("team agg %s err: %r", label, exc)
                    continue
                rows = [r for r in rows if r.get("team") in _CENTRAL_TEAM_JP]
                rows.sort(key=lambda r: r["value"], reverse=desc)
                out[label] = [
                    (_CENTRAL_TEAM_JP[r["team"]], disp(r["value"]), i, r["team"] == "g")
                    for i, r in enumerate(rows, 1)
                ]
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_team_rankings err: %r", exc)
        return {}
    return out


@dataclass
class LeaderEntry:
    """リーダーボード 1 行 (選手 + 数値)。"""
    player: str
    value: float
    display: str  # 表示用("12本" / ".318" 等)


@dataclass
class SurpriseStatEntry:
    """ファンが驚きやすい上位データ 1 行。"""
    player: str
    label: str
    value: str
    note: str
    priority: float = 0.0


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


_SURPRISE_METRICS: dict[str, tuple[str, str]] = {
    "OPS": ("打撃総合力", "OPS"),
    "OBP": ("出塁力", "出塁率"),
    "SLG": ("長打力", "長打率"),
    "ISO": ("純長打力", "ISO"),
    "wOBA": ("攻撃貢献", "wOBA"),
    "BABIP": ("打球結果", "BABIP"),
    "ERA": ("失点抑止", "防御率"),
    "WHIP": ("走者を出さない力", "WHIP"),
    "FIP": ("投球内容", "FIP"),
    "K_per_9": ("奪三振力", "K/9"),
    "K_BB": ("制球と奪三振", "K/BB"),
    "UZR_proxy": ("守備貢献", "守備指標"),
    "FIELDING_PCT": ("堅実守備", "守備率"),
}


def _scope_label(scope: str) -> str:
    return {
        "season": "今季",
        "last_30d": "直近1ヶ月",
    }.get(scope, scope)


def _surprise_min_sample(metric: str, scope: str) -> int:
    if scope == "season":
        return 30 if metric not in {"ERA", "WHIP", "FIP", "K_per_9", "K_BB"} else 10
    return 20 if metric not in {"ERA", "WHIP", "FIP", "K_per_9", "K_BB"} else 5


def fetch_surprise_stats(top_n: int = 8) -> list[SurpriseStatEntry]:
    """ファンが驚きやすいリーグ上位データを抽出する。

    /data/ranking/ 用。直近5試合・連続記録は別扱いにし、ここでは season /
    last_30d のリーグ上位率を使う。last_30d は長期欠場選手を freshness gate で
    落とす。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    metric_names = tuple(_SURPRISE_METRICS.keys())
    placeholders = ",".join("?" for _ in metric_names)
    rows: list[tuple] = []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT player_canonical, metric_name, metric_value, sample_size,
                       league_rank, league_total, scope
                FROM advanced_metric_snapshots a
                WHERE team_code='g'
                  AND scope IN ('season', 'last_30d')
                  AND metric_name IN ({placeholders})
                  AND metric_value IS NOT NULL
                  AND league_rank IS NOT NULL
                  AND league_total IS NOT NULL
                  AND snapshot_date = (
                    SELECT MAX(snapshot_date) FROM advanced_metric_snapshots b
                    WHERE b.scope = a.scope AND b.metric_name = a.metric_name
                  )
                """,
                metric_names,
            )
            rows = cur.fetchall()
            out: list[SurpriseStatEntry] = []
            seen: set[tuple[str, str]] = set()
            for name, metric, value, sample, rank, total, scope in rows:
                metric = str(metric or "")
                scope = str(scope or "")
                try:
                    rank_i, total_i = int(rank), int(total)
                    sample_i = int(sample or 0)
                except (TypeError, ValueError):
                    continue
                if rank_i <= 0 or total_i <= 0:
                    continue
                if sample_i < _surprise_min_sample(metric, scope):
                    continue
                if scope == "last_30d":
                    table = "pitching_logs" if metric in {"ERA", "WHIP", "FIP", "K_per_9", "K_BB"} else "batting_logs"
                    if not _player_recent_enough(conn, table, str(name)):
                        continue
                rank_pct = rank_i / total_i
                if rank_i > 10 and rank_pct > 0.20:
                    continue
                key = (str(name), metric)
                if key in seen:
                    continue
                seen.add(key)
                theme, label = _SURPRISE_METRICS[metric]
                scope_ja = _scope_label(scope)
                priority = (1.0 - rank_pct) + (0.15 if scope == "season" else 0.0)
                out.append(
                    SurpriseStatEntry(
                        player=str(name),
                        label=f"{theme}（{label}）",
                        value=_fmt_sabr(metric, value),
                        note=f"{scope_ja}・リーグ{rank_i}/{total_i}位・サンプル{sample_i}",
                        priority=priority,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_surprise_stats err: %r", exc)
        return []
    out.sort(key=lambda e: (-e.priority, e.player, e.label))
    return out[:top_n]


def _career_int(s) -> Optional[int]:
    try:
        v = re.sub(r"[^0-9\-]", "", str(s))
        return int(v) if v not in ("", "-") else None
    except (TypeError, ValueError):
        return None


def _career_ip(s) -> Optional[float]:
    """NPB 投球回 '924.2' (= 924 と 2/3) を ranking 用 float に。"""
    try:
        whole, _, frac = str(s).strip().partition(".")
        w = int(whole) if whole else 0
        f = int(frac) if frac else 0
        return float(w) + (f / 3.0)
    except (TypeError, ValueError):
        return None


def build_career_leaders(career_cache: dict, top_n: int = 10) -> dict[str, list[LeaderEntry]]:
    """468-1: 現役巨人選手の NPB 通算成績ランキング (467 career cache 由来、追加 fetch 無し)。

    career cache = npb_career_ingest の {ids:{name:id}, players:{id:payload}}。
    各選手の通算 (total) 行を集計して、打撃 5 種 + 投手 5 種のランキングを返す。
    率系 (打率/防御率) は規定数 (打数/投球回) 未満を除外し小標本上位を防ぐ。
    戻り値: {category: [LeaderEntry, ... top_n]}。
    """
    players = (career_cache or {}).get("players") or {}
    ids = (career_cache or {}).get("ids") or {}
    id2name = {str(v): k for k, v in ids.items()}

    bat: list[tuple[str, dict]] = []
    pit: list[tuple[str, dict]] = []
    for npb_id, payload in players.items():
        if not isinstance(payload, dict):
            continue
        name = id2name.get(str(npb_id))
        if not name:
            continue
        b = (payload.get("batting") or {}).get("total")
        if isinstance(b, dict) and b:
            bat.append((name, b))
        p = (payload.get("pitching") or {}).get("total")
        if isinstance(p, dict) and p and payload.get("is_pitcher"):
            pit.append((name, p))

    def _board(rows, col, *, reverse=True, fmt=None, min_col=None, min_val=0):
        out = []
        for name, tot in rows:
            v = _career_int(tot.get(col))
            if v is None:
                continue
            if min_col is not None:
                m = _career_int(tot.get(min_col))
                if m is None or m < min_val:
                    continue
            out.append((name, v, tot))
        out.sort(key=lambda x: x[1], reverse=reverse)
        return [
            LeaderEntry(player=n, value=float(v), display=(fmt(v, tot) if fmt else str(v)))
            for n, v, tot in out[:top_n]
        ]

    def _rate_board(rows, col, *, reverse, min_col, min_val):
        out = []
        for name, tot in rows:
            raw = str(tot.get(col, "")).strip()
            try:
                rv = float(raw)
            except (TypeError, ValueError):
                continue
            m = _career_int(tot.get(min_col))
            if m is None or m < min_val:
                continue
            out.append((name, rv, raw))
        out.sort(key=lambda x: x[1], reverse=reverse)
        return [LeaderEntry(player=n, value=rv, display=raw) for n, rv, raw in out[:top_n]]

    def _ip_board(rows):
        out = []
        for name, tot in rows:
            ipv = _career_ip(tot.get("投球回"))
            if ipv is None:
                continue
            out.append((name, ipv, str(tot.get("投球回", "")).strip()))
        out.sort(key=lambda x: x[1], reverse=True)
        return [LeaderEntry(player=n, value=v, display=f"{disp}回") for n, v, disp in out[:top_n]]

    leaders: dict[str, list[LeaderEntry]] = {
        "通算安打": _board(bat, "安打", fmt=lambda v, t: f"{v}"),
        "通算本塁打": _board(bat, "本塁打", fmt=lambda v, t: f"{v}本"),
        "通算打点": _board(bat, "打点", fmt=lambda v, t: f"{v}"),
        "通算盗塁": _board(bat, "盗塁", fmt=lambda v, t: f"{v}"),
        "通算打率": _rate_board(bat, "打率", reverse=True, min_col="打数", min_val=1000),
        "通算勝利": _board(pit, "勝利", fmt=lambda v, t: f"{v}勝"),
        "通算セーブ": _board(pit, "セーブ", fmt=lambda v, t: f"{v}S"),
        "通算奪三振": _board(pit, "三振", fmt=lambda v, t: f"{v}"),
        "通算投球回": _ip_board(pit),
        "通算防御率": _rate_board(pit, "防御率", reverse=False, min_col="登板", min_val=50),
    }
    return {k: v for k, v in leaders.items() if v}


def build_alltime_leaders(career_cache: dict, top_n: int = 10) -> dict[str, list[LeaderEntry]]:
    """全史(OB684 + 現役)NPB通算ランキング top-N。共有部品 alltime_ranking を消費。

    OB は年度別不在で球団限定不可のため NPB通算で揃える(表記も NPB通算)。現役選手は
    display に ★現役 マーカー。戻り値 {category_label: [LeaderEntry, ...top_n]}。
    """
    try:
        from src.analysis import alltime_ranking as _ar
    except Exception:  # noqa: BLE001
        return {}
    units = {"hr": "本", "hits": "安打", "rbi": "打点", "win": "勝", "so": "奪三振"}
    try:
        rankings = _ar.build_rankings(None, career_cache)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("build_alltime_leaders failed: %r", exc)
        return {}
    out: dict[str, list[LeaderEntry]] = {}
    for key, rows in rankings.items():
        label = _ar.STAT_SPECS[key]["label"]
        unit = units.get(key, "")
        entries = [
            LeaderEntry(
                player=r["name"],
                value=float(r["value"]),
                display=f"{r['value']}{unit}{' ★現役' if r['is_current'] else ''}",
            )
            for r in rows[:top_n]
        ]
        if entries:
            out[label] = entries
    return out


# 記録室の「クラブ」定義: (stat_key, 閾値, クラブ名)。閾値以上の在籍者を全員掲載。
_RECORD_CLUBS: list[tuple[str, int, str]] = [
    ("hits", 2000, "名球会 — 通算2000安打クラブ"),
    ("hr", 300, "通算300本塁打クラブ"),
    ("rbi", 1000, "通算1000打点クラブ"),
    ("win", 200, "名球会 — 通算200勝クラブ"),
    ("so", 2000, "通算2000奪三振クラブ"),
]


def build_record_room(career_cache: dict) -> dict[str, list[LeaderEntry]]:
    """記録室ハブ: 巨人在籍者(OB684 + 現役)の通算節目クラブ会員一覧。

    共有部品 alltime_ranking を閾値 filter。各クラブは閾値以上の全員を値降順で。
    現役は ★現役 マーカー。NPB通算で集計(球団限定不可のため、表記も NPB通算)。
    戻り値: {club_label: [LeaderEntry]}(会員 0 のクラブは省略)。
    """
    try:
        from src.analysis import alltime_ranking as _ar
    except Exception:  # noqa: BLE001
        return {}
    units = {"hr": "本", "hits": "安打", "rbi": "打点", "win": "勝", "so": "奪三振"}
    try:
        rankings = _ar.build_rankings(None, career_cache)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("build_record_room failed: %r", exc)
        return {}
    out: dict[str, list[LeaderEntry]] = {}
    for key, threshold, label in _RECORD_CLUBS:
        unit = units.get(key, "")
        members = [
            LeaderEntry(
                player=r["name"],
                value=float(r["value"]),
                display=f"{r['value']}{unit}{' ★現役' if r['is_current'] else ''}",
            )
            for r in rankings.get(key, [])
            if r["value"] >= threshold
        ]
        if members:
            out[label] = members
    return out


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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','') AND team_name = '巨人'
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


def fetch_pitcher_npb_ranks(player_canonical: str, *, min_ip_for_era: float = 20.0) -> list[tuple]:
    """投手の NPB 全 12 球団内 順位を返す (防御率 / 奪三振 / 勝利)。

    fetch_player_npb_ranks(打者) の投手版。pitching_logs (全 12 球団) を read-side で
    集計し NPB-wide rank を自前計算する。
    Returns ``[(label, value_str, rank, total), ...]``。防御率は IP>=min_ip_for_era を
    母集団とする (規定投球回の簡易代替)。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT player_canonical, COALESCE(SUM(IP),0), COALESCE(SUM(ER),0), "
                "COALESCE(SUM(K),0), COALESCE(SUM(CASE WHEN result_mark='勝' THEN 1 ELSE 0 END),0) "
                "FROM pitching_logs WHERE player_canonical IS NOT NULL GROUP BY player_canonical"
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_pitcher_npb_ranks err player=%s: %r", player_canonical, exc)
        return []
    agg = [(p, float(ip), int(er), int(k), int(w)) for (p, ip, er, k, w) in rows if float(ip or 0) > 0]
    if not agg:
        return []

    def _rank(sorted_players: list[tuple], name: str) -> Optional[tuple[int, int]]:
        for i, t in enumerate(sorted_players, 1):
            if t[0] == name:
                return i, len(sorted_players)
        return None

    out: list[tuple] = []
    # 防御率 (IP>=min_ip_for_era、 小さいほど上位)
    qual = [(p, ip, er * 9.0 / ip) for (p, ip, er, k, w) in agg if ip >= min_ip_for_era]
    by_era = sorted(qual, key=lambda x: x[2])
    r = _rank(by_era, player_canonical)
    if r:
        era = next((x[2] for x in qual if x[0] == player_canonical), 0.0)
        out.append(("防御率", f"{era:.2f}", r[0], r[1]))
    # 奪三振 (全 IP>0、 多いほど上位)
    by_k = sorted(agg, key=lambda x: -x[3])
    r = _rank(by_k, player_canonical)
    if r:
        k = next((x[3] for x in agg if x[0] == player_canonical), 0)
        out.append(("奪三振", str(k), r[0], r[1]))
    # 勝利 (全 IP>0、 多いほど上位)
    by_w = sorted(agg, key=lambda x: -x[4])
    r = _rank(by_w, player_canonical)
    if r and r[0] <= r[1]:
        w = next((x[4] for x in agg if x[0] == player_canonical), 0)
        out.append(("勝利", str(w), r[0], r[1]))
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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','') AND team_name = '巨人'
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


def _count_giants_games_after(conn: sqlite3.Connection, game_date: str) -> int:
    """Count completed Giants games after ``game_date`` using batting log presence.

    Future schedule rows may already exist in ``games``. Counting rows that also have
    Giants batting logs keeps the freshness gate tied to actually played games.
    """
    if not game_date:
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(DISTINCT g.game_id)
        FROM games g
        JOIN batting_logs b ON b.game_id = g.game_id AND b.team_name = '巨人'
        WHERE g.game_date > ?
          AND (g.game_id LIKE '%:g-%' OR g.game_id LIKE '%-g-%')
        """,
        (game_date,),
    )
    return int(cur.fetchone()[0] or 0)


def _streak_with_freshness(
    conn: sqlite3.Connection,
    rows: list[tuple[int, str]],
    missed_game_limit: int = 2,
) -> StreakInfo:
    """Compute streak and suppress active streaks after extended absence."""
    info = _compute_streak([int(v or 0) for v, _date in rows])
    if not rows or info.active <= 0:
        return info
    latest_player_game = str(rows[0][1] or "")[:10]
    try:
        missed_games = _count_giants_games_after(conn, latest_player_game)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("streak freshness gate failed latest=%s: %r", latest_player_game, exc)
        return info
    if missed_games > missed_game_limit:
        return StreakInfo(active=0, season_max=info.season_max)
    return info


def _latest_player_log_date(conn: sqlite3.Connection, table: str, player_canonical: str) -> str:
    if table not in {"batting_logs", "pitching_logs"}:
        return ""
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT MAX(g.game_date)
        FROM {table} l
        JOIN games g ON l.game_id = g.game_id
        WHERE REPLACE(l.player_canonical,' ','') = REPLACE(?,' ','')
          AND l.team_name = '巨人'
        """,
        (player_canonical,),
    )
    return str(cur.fetchone()[0] or "")[:10]


def fetch_latest_giants_game_date() -> str:
    """Return the latest completed Giants game date backed by batting logs."""
    path = _ensure_insight_db_local()
    if not path:
        return ""
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT MAX(g.game_date)
                FROM games g
                JOIN batting_logs b ON b.game_id = g.game_id AND b.team_name = '巨人'
                WHERE g.game_id LIKE '%:g-%' OR g.game_id LIKE '%-g-%'
                """
            )
            return str(cur.fetchone()[0] or "")[:10]
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_latest_giants_game_date err: %r", exc)
        return ""


def fetch_player_latest_game_date(player_canonical: str, table: str = "batting_logs") -> str:
    """Return the latest game date for a Giants player in batting/pitching logs."""
    path = _ensure_insight_db_local()
    if not path:
        return ""
    try:
        with sqlite3.connect(path) as conn:
            return _latest_player_log_date(conn, table, player_canonical)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_player_latest_game_date err player=%s table=%s: %r", player_canonical, table, exc)
        return ""


def _player_recent_enough(
    conn: sqlite3.Connection,
    table: str,
    player_canonical: str,
    missed_game_limit: int = 2,
) -> bool:
    """Return False when a short-window ranking row is stale due to absence."""
    try:
        latest = _latest_player_log_date(conn, table, player_canonical)
        if not latest:
            return False
        return _count_giants_games_after(conn, latest) <= missed_game_limit
    except Exception as exc:  # noqa: BLE001
        LOG.warning("recent-hot freshness gate failed player=%s table=%s: %r", player_canonical, table, exc)
        return True


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
                SELECT COALESCE(b.H, 0), g.game_date
                FROM batting_logs b
                JOIN games g ON b.game_id = g.game_id
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','') AND b.team_name = '巨人'
                ORDER BY g.game_date DESC, b.game_id DESC
                """,
                (player_canonical,),
            )
            rows = [(int(r[0] or 0), str(r[1] or "")[:10]) for r in cur.fetchall()]
            return _streak_with_freshness(conn, rows)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_hit_streak err player=%s: %r", player_canonical, exc)
        return StreakInfo(active=0, season_max=0)


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
                SELECT (COALESCE(b.R, 0) + COALESCE(b.RBI, 0)) as contrib, g.game_date
                FROM batting_logs b
                JOIN games g ON b.game_id = g.game_id
                WHERE REPLACE(b.player_canonical,' ','') = REPLACE(?,' ','') AND b.team_name = '巨人'
                ORDER BY g.game_date DESC, b.game_id DESC
                """,
                (player_canonical,),
            )
            rows = [(int(r[0] or 0), str(r[1] or "")[:10]) for r in cur.fetchall()]
            return _streak_with_freshness(conn, rows)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_contribution_streak err player=%s: %r", player_canonical, exc)
        return StreakInfo(active=0, season_max=0)


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
                WHERE REPLACE(player_canonical,' ','') = REPLACE(?,' ','') AND team_name = '巨人'
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
                WHERE REPLACE(p.player_canonical,' ','') = REPLACE(?,' ','') AND p.team_name = '巨人'
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


def fetch_pitcher_opponent_split_stats(player_canonical: str) -> list[tuple]:
    """投手 vs 各球団 集計 (456 投手 split 横展開、 打者 fetch_opponent_split_stats の投手版)。

    pitching_logs JOIN games で opponent GROUP BY、 IP は NPB 0.1/0.2 形式を
    _normalize_npb_ip_sum で正規化して ERA を算出。 read-side のみ、 新 ETL 不要。
    返り値: [(opponent, G, IP, K, ER, ERA), ...] (ERA は ip=0 で None)。
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
                       COUNT(DISTINCT p.game_id) as g,
                       COALESCE(SUM(p.IP), 0) as ip_raw,
                       COALESCE(SUM(p.K), 0) as k,
                       COALESCE(SUM(p.ER), 0) as er
                FROM pitching_logs p
                JOIN games g ON p.game_id = g.game_id
                WHERE REPLACE(p.player_canonical,' ','') = REPLACE(?,' ','') AND p.team_name = '巨人'
                  AND g.opponent IS NOT NULL AND g.opponent <> ''
                GROUP BY g.opponent
                ORDER BY g.opponent
                """,
                (player_canonical,),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_pitcher_opponent_split_stats err player=%s: %r", player_canonical, exc)
        return []
    out: list[tuple] = []
    for r in rows:
        ip = _normalize_npb_ip_sum(float(r[2] or 0.0))
        er = int(r[4] or 0)
        era = (er * 9.0 / ip) if ip > 0 else None
        out.append((str(r[0]), int(r[1] or 0), ip, int(r[3] or 0), er, era))
    return out


def _fetch_pitcher_game_rows(player_canonical: str) -> list[tuple]:
    """投手の (game_id, game_date, IP, K, ER) を返す(曜日/月/交流戦 split 共通の素)。"""
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT p.game_id, g.game_date, COALESCE(p.IP,0.0), COALESCE(p.K,0), COALESCE(p.ER,0)
                FROM pitching_logs p JOIN games g ON p.game_id = g.game_id
                WHERE REPLACE(p.player_canonical,' ','') = REPLACE(?,' ','') AND p.team_name = '巨人'
                  AND g.game_date IS NOT NULL
                """,
                (player_canonical,),
            )
            return cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_fetch_pitcher_game_rows err player=%s: %r", player_canonical, exc)
        return []


def _bucket_pitcher_splits(rows: list[tuple], key_fn, order: list[str]) -> list[tuple]:
    """投手 rows を key_fn でバケットし、 order 順で (label, G, IP, K, ER, ERA) 化。

    IP は raw SUM を _normalize_npb_ip_sum で正規化、 ERA を算出。 IP<=0 のバケットは省く。
    """
    agg: dict[str, list] = {}
    for game_id, game_date, ip, k, er in rows:
        key = key_fn(game_id, game_date)
        if key is None:
            continue
        b = agg.setdefault(key, [set(), 0.0, 0, 0])
        b[0].add(game_id)
        b[1] += float(ip or 0.0)
        b[2] += int(k or 0)
        b[3] += int(er or 0)
    out: list[tuple] = []
    keys = order if order else sorted(agg.keys())
    for key in keys:
        if key not in agg:
            continue
        ip = _normalize_npb_ip_sum(agg[key][1])
        if ip <= 0:
            continue
        er = agg[key][3]
        era = (er * 9.0 / ip) if ip > 0 else None
        out.append((key, len(agg[key][0]), ip, agg[key][2], er, era))
    return out


def fetch_pitcher_venue_split_stats(player_canonical: str) -> list[tuple]:
    """投手 本拠地 / ビジター 別 (456)。 home/away は game_id から判定。"""
    rows = _fetch_pitcher_game_rows(player_canonical)
    label = {"home": "本拠地", "away": "ビジター"}

    def key(gid, _gd):
        return label.get(giants_venue_from_game_id(str(gid or "")))

    return _bucket_pitcher_splits(rows, key, ["本拠地", "ビジター"])


def fetch_pitcher_weekday_split_stats(player_canonical: str) -> list[tuple]:
    """投手 曜日別 (456)。"""
    rows = _fetch_pitcher_game_rows(player_canonical)

    def key(_gid, gdate):
        try:
            return _WEEKDAY_JP[date.fromisoformat(str(gdate)[:10]).weekday()]
        except ValueError:
            return None

    return _bucket_pitcher_splits(rows, key, _WEEKDAY_JP)


def fetch_pitcher_month_split_stats(player_canonical: str) -> list[tuple]:
    """投手 月別 (456)。"""
    rows = _fetch_pitcher_game_rows(player_canonical)

    def key(_gid, gdate):
        try:
            return f"{int(str(gdate)[5:7])}月"
        except (ValueError, IndexError):
            return None

    return _bucket_pitcher_splits(rows, key, [f"{m}月" for m in range(3, 12)])


def fetch_pitcher_interleague_split_stats(player_canonical: str) -> list[tuple]:
    """投手 交流戦 / リーグ戦 別 (456、 対戦相手コードから判定)。"""
    rows = _fetch_pitcher_game_rows(player_canonical)

    def key(gid, _gd):
        opp = _opp_code(str(gid or ""))
        if opp is None:
            return None
        return "交流戦" if opp in _PA_TEAM_CODES else "リーグ戦"

    return _bucket_pitcher_splits(rows, key, ["リーグ戦", "交流戦"])


# --- 457: 得点圏 (RISP) split (at_bat_details から read-side 派生) ---
# 注: at_bat_details.batter は姓のみ表記 (「浦田」/「代打・ 浦田」)。 batter_canonical は
# ETL で None 固定のため、 選手 canonical との照合は「姓 prefix 一致 + 代打/代走 prefix 除去」
# で行う。 同姓 2 名は at_bat_details 上区別不能 (データ制約、 batter_canonical backfill が
# 恒久解だが本 ticket は read-side で先行)。 runner_state はアラビア数字表記 (1塁/2塁/満塁)。
_RISP_RE = re.compile(r"[23]塁|満塁")  # 得点圏 = 走者 2塁/3塁/満塁
_NON_AB_TOKENS = ("フォアボール", "四球", "敬遠", "デッドボール", "死球",
                  "犠牲バント", "犠打", "犠牲フライ", "犠飛", "打撃妨害")
_ATBAT_HIT_RE = re.compile(r"安打|本塁打|ホームラン|塁打|適時|タイムリー|ヒット|ツーベース|スリーベース")


def _norm_atbat_batter(batter: str) -> str:
    """at_bat_details.batter を正規化 (代打・/代走・ prefix と空白を除去)。"""
    s = str(batter or "")
    for pre in ("代打・", "代走・", "代打", "代走"):
        if s.startswith(pre):
            s = s[len(pre):]
            break
    return s.replace(" ", "").replace("　", "")


def _result_base(result_text: str) -> str:
    """result_text から （打点N）等の括弧注釈を除去。"""
    return re.sub(r"（.*?）", "", str(result_text or ""))


def is_official_at_bat(result_text: str) -> bool:
    """official 打数か (四球/敬遠/死球/犠打/犠飛/打撃妨害 は打数に含めない)。

    prod insight.db 735 PA で検証 (AB=673 / nonAB=62 / 誤分類0、 457)。 空文字は False。
    """
    base = _result_base(result_text)
    if not base.strip():
        return False
    return not any(t in base for t in _NON_AB_TOKENS)


def _is_atbat_hit(result_text: str) -> bool:
    """result_text が安打か (カタカナ NPB 語彙対応、 457)。"""
    return bool(_ATBAT_HIT_RE.search(_result_base(result_text)))


def fetch_risp_split_stats(player_canonical: str) -> list[tuple]:
    """得点圏 (走者2塁/3塁/満塁) 打撃集計を返す。 at_bat_details から read-side 派生。

    返り値: [("得点圏", AB, H, AVG)] (打数 0 なら [])。 大手未掲載 metric。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT batter, runner_state, result_text FROM at_bat_details "
                "WHERE team LIKE '%巨人%' AND batter IS NOT NULL AND batter <> ''"
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_risp_split_stats err player=%s: %r", player_canonical, exc)
        return []
    pc = str(player_canonical or "").replace(" ", "").replace("　", "")
    if not pc:
        return []
    ab = h = 0
    for batter, rstate, rtext in rows:
        nb = _norm_atbat_batter(batter)
        if not nb or not pc.startswith(nb):  # 姓 prefix 一致
            continue
        if not _RISP_RE.search(str(rstate or "")):
            continue
        if is_official_at_bat(rtext):
            ab += 1
            if _is_atbat_hit(rtext):
                h += 1
    if ab == 0:
        return []
    return [("得点圏", ab, h, (h / ab) if ab > 0 else None)]


def _load_pitcher_throws() -> dict:
    """config/npb_pitcher_throws.json を読む ({name: {team, throws: L/R}})。

    NPB_THROWS_PATH env で override 可 (test 用)。 失敗時は {}。
    """
    path = os.environ.get("NPB_THROWS_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "config", "npb_pitcher_throws.json"
    )
    try:
        with open(path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_load_pitcher_throws err: %r", exc)
        return {}


def fetch_vs_lr_split_stats(player_canonical: str) -> list[tuple]:
    """対左 / 対右投手 別 打撃集計 (457、 at_bat_details + throws map、 read-side)。

    返り値: [("対左投手", AB, H, AVG), ("対右投手", AB, H, AVG)] (AB>0 のみ)。
    current_pitcher が populate された PA のみ対象 (coverage 限定、 prod 実測 ~42%)。
    姓 prefix 一致 + 代打/代走 prefix 除去で選手を照合 (同姓は区別不能=データ制約)。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    throws = _load_pitcher_throws()
    if not throws:
        return []
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT batter, current_pitcher, result_text FROM at_bat_details "
                "WHERE team LIKE '%巨人%' AND batter IS NOT NULL AND batter <> '' "
                "AND current_pitcher IS NOT NULL AND current_pitcher <> ''"
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_vs_lr_split_stats err player=%s: %r", player_canonical, exc)
        return []
    pc = str(player_canonical or "").replace(" ", "").replace("　", "")
    if not pc:
        return []
    agg = {"L": [0, 0], "R": [0, 0]}  # hand -> [AB, H]
    for batter, pitcher, rtext in rows:
        nb = _norm_atbat_batter(batter)
        if not nb or not pc.startswith(nb):
            continue
        hand = (throws.get(pitcher or "") or {}).get("throws")
        if hand not in ("L", "R"):
            continue
        if is_official_at_bat(rtext):
            agg[hand][0] += 1
            if _is_atbat_hit(rtext):
                agg[hand][1] += 1
    label = {"L": "対左投手", "R": "対右投手"}
    out: list[tuple] = []
    for hand in ("L", "R"):
        ab, h = agg[hand]
        if ab > 0:
            out.append((label[hand], ab, h, h / ab))
    return out


# --- 461: セイバーメトリクス (advanced_metric_snapshots、 site はライバル超えのため全指標表示) ---
# whitelist の × (FIP/wOBA/ISO/WHIP 等) は「ポスト」非表示の話で、 data-site には適用しない
# (user 2026-06-01「だからサイトだから、ライバルサイトに上回るものがほしい。ポストはいらない」)。
_SABR_BATTER = [("OPS", "OPS"), ("ISO", "ISO"), ("wOBA", "wOBA"), ("BABIP", "BABIP"),
                ("BB%", "BB_pct"), ("K%", "K_pct"), ("出塁率", "OBP"), ("長打率", "SLG")]
_SABR_PITCHER = [("防御率", "ERA"), ("FIP", "FIP"), ("xFIP", "xFIP"), ("WHIP", "WHIP"),
                 ("奪三振率(K/9)", "K_per_9"), ("与四球率(BB/9)", "BB_per_9"),
                 ("被本塁打率(HR/9)", "HR_per_9"), ("K/BB", "K_BB")]


def _fmt_sabr(name: str, v) -> str:
    if v is None:
        return "-"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    if name in ("BB_pct", "K_pct"):
        return f"{v * 100:.1f}%"
    if name in ("AVG", "OBP", "SLG", "OPS", "ISO", "wOBA", "BABIP"):
        s = f"{v:.3f}"
        return s[1:] if s.startswith("0.") else s
    return f"{v:.2f}"  # ERA/FIP/xFIP/WHIP/K_per_9/BB_per_9/HR_per_9/K_BB


def fetch_sabermetrics(player_canonical: str, is_pitcher: bool) -> list[tuple]:
    """選手の最新セイバーメトリクス snapshot を返す (461)。

    返り値: [(label, 値str, league_rank, league_total), ...]。 daily snapshot の最新日を採用。
    scope は last_30d 優先、 無ければ last_5_games に fallback。
    """
    path = _ensure_insight_db_local()
    if not path:
        return []
    spec = _SABR_PITCHER if is_pitcher else _SABR_BATTER
    for scope in ("last_30d", "last_5_games"):
        try:
            with sqlite3.connect(path) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT metric_name, metric_value, league_rank, league_total "
                    "FROM advanced_metric_snapshots "
                    "WHERE REPLACE(player_canonical,' ','')=REPLACE(?,' ','') AND scope=? "
                    "AND snapshot_date=(SELECT MAX(snapshot_date) FROM advanced_metric_snapshots "
                    "  WHERE REPLACE(player_canonical,' ','')=REPLACE(?,' ','') AND scope=?)",
                    (player_canonical, scope, player_canonical, scope),
                )
                rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("fetch_sabermetrics err player=%s: %r", player_canonical, exc)
            return []
        if rows:
            by_name = {r[0]: (r[1], r[2], r[3]) for r in rows}
            out: list[tuple] = []
            for label, name in spec:
                if name in by_name:
                    v, rank, total = by_name[name]
                    out.append((label, _fmt_sabr(name, v), rank, total))
            if out:
                return out
    return []


def fetch_recent_hot(top_n: int = 3) -> dict:
    """直近5試合の注目選手 (460 今日の注目カード)。 advanced_metric_snapshots last_5_games 最新。

    返り値: {"batter": [(name, "OPS .950", rank, total), ...],
             "pitcher": [(name, "防御率 1.20", rank, total), ...]}。
    sample_size gate (打者>=8 / 投手>=5) で 1打席 .999 等のノイズを除外。 無ければ空 list。
    """
    path = _ensure_insight_db_local()
    out: dict = {"batter": [], "pitcher": []}
    if not path:
        return out
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            limit = max(int(top_n) * 4, int(top_n))
            cur.execute(
                "SELECT player_canonical, metric_value, league_rank, league_total "
                "FROM advanced_metric_snapshots WHERE team_code='g' AND scope='last_5_games' "
                "AND metric_name='OPS' AND COALESCE(sample_size,0)>=8 "
                "AND snapshot_date=(SELECT MAX(snapshot_date) FROM advanced_metric_snapshots "
                "  WHERE scope='last_5_games' AND metric_name='OPS') "
                "ORDER BY metric_value DESC LIMIT ?",
                (limit,),
            )
            for n, v, rk, tot in cur.fetchall():
                if not _player_recent_enough(conn, "batting_logs", str(n)):
                    continue
                out["batter"].append((str(n), f"OPS {_fmt_sabr('OPS', v)}", rk, tot))
                if len(out["batter"]) >= int(top_n):
                    break
            cur.execute(
                "SELECT player_canonical, metric_value, league_rank, league_total "
                "FROM advanced_metric_snapshots WHERE team_code='g' AND scope='last_5_games' "
                "AND metric_name='ERA' AND COALESCE(sample_size,0)>=5 "
                "AND snapshot_date=(SELECT MAX(snapshot_date) FROM advanced_metric_snapshots "
                "  WHERE scope='last_5_games' AND metric_name='ERA') "
                "ORDER BY metric_value ASC LIMIT ?",
                (limit,),
            )
            for n, v, rk, tot in cur.fetchall():
                if not _player_recent_enough(conn, "pitching_logs", str(n)):
                    continue
                try:
                    disp = f"防御率 {float(v):.2f}"
                except (TypeError, ValueError):
                    disp = "防御率 -"
                out["pitcher"].append((str(n), disp, rk, tot))
                if len(out["pitcher"]) >= int(top_n):
                    break
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_recent_hot err: %r", exc)
        return {"batter": [], "pitcher": []}
    return out


_CL_TEAM_SHORT = {
    "読売ジャイアンツ": "巨人", "東京ヤクルトスワローズ": "ヤクルト",
    "阪神タイガース": "阪神", "横浜DeNAベイスターズ": "DeNA",
    "広島東洋カープ": "広島", "中日ドラゴンズ": "中日",
}


def parse_npb_cl_standings(html_text: str) -> list[dict]:
    """NPB公式 std_c.html からセ・リーグ順位表を抽出 (459/C)。

    返り値: [{"rank","team","g","w","l","t","pct","gb","is_giants"}, ...] 順位順。
    最初の順位表 table の6球団行のみ (2つ目=交流戦表は seen+break で除外)。
    """
    out: list[dict] = []
    seen: set[str] = set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S):
        cells = [
            _html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        ]
        cells = [c for c in cells if c != ""]
        if not cells:
            continue
        team = cells[0]
        if team in _CL_TEAM_SHORT and team not in seen and len(cells) >= 7:
            seen.add(team)
            out.append({
                "rank": len(out) + 1,
                "team": _CL_TEAM_SHORT[team],
                "g": cells[1], "w": cells[2], "l": cells[3], "t": cells[4],
                "pct": cells[5], "gb": cells[6],
                "is_giants": team == "読売ジャイアンツ",
            })
        if len(out) >= 6:
            break
    return out


def fetch_npb_cl_standings(year: int = 2026) -> list[dict]:
    """NPB公式からセ・リーグ順位表を scrape (459/C、 standings_snapshots 空の代替)。"""
    url = f"https://npb.jp/bis/{year}/stats/std_c.html"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        r.encoding = "utf-8"
        return parse_npb_cl_standings(r.text)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_npb_cl_standings err: %r", exc)
        return []


_GIANTS_NAMES = {"巨人", "読売", "読売ジャイアンツ"}


def parse_giants_upcoming(html_text: str, year: int, today, limit: int = 6) -> list[dict]:
    """NPB月間日程 HTML から巨人の未来試合を抽出 (459/C、 純粋関数で test 可)。

    返り値: [{"date","opp","home_away","time","place"}, ...] 日付昇順、 score 未確定(未来)のみ。
    team1=本拠 / team2=ビジター(NPB日程表記)。 予告先発は本ページに無い(空)ため非掲載。
    """
    date_pos = [
        (m.start(), int(m.group(1)), int(m.group(2)))
        for m in re.finditer(r"(\d{1,2})/(\d{1,2})（[日月火水木金土]）", html_text)
    ]
    out: list[dict] = []
    for tm in re.finditer(
        r'class="team1"[^>]*>(.*?)</[^>]+>.*?class="team2"[^>]*>(.*?)</[^>]+>', html_text, re.S
    ):
        t1 = re.sub(r"<[^>]+>", "", _html.unescape(tm.group(1))).strip()
        t2 = re.sub(r"<[^>]+>", "", _html.unescape(tm.group(2))).strip()
        if t1 not in _GIANTS_NAMES and t2 not in _GIANTS_NAMES:
            continue
        mo = da = None
        for p, m_, d_ in date_pos:
            if p <= tm.start():
                mo, da = m_, d_
            else:
                break
        if mo is None:
            continue
        try:
            gd = date(year, mo, da)
        except ValueError:
            continue
        if gd < today:
            continue
        win = html_text[tm.end():tm.end() + 500]
        sc1 = re.search(r'class="score1"[^>]*>(.*?)</', win, re.S)
        score1 = re.sub(r"<[^>]+>", "", _html.unescape(sc1.group(1))).strip() if sc1 else ""
        if score1:  # 既に結果あり = 過去
            continue
        tmt = re.search(r'class="time"[^>]*>(.*?)</', win, re.S)
        plc = re.search(r'class="place"[^>]*>(.*?)</', win, re.S)
        out.append({
            "date": gd.isoformat(),
            "opp": (t2 if t1 in _GIANTS_NAMES else t1),
            "home_away": ("本拠地" if t1 in _GIANTS_NAMES else "ビジター"),
            "time": (re.sub(r"<[^>]+>", "", _html.unescape(tmt.group(1))).strip() if tmt else ""),
            "place": (re.sub(r"<[^>]+>", "", _html.unescape(plc.group(1))).strip() if plc else ""),
        })
        if len(out) >= limit:
            break
    return out


def parse_giants_starters(html_text: str) -> dict:
    """NPB本日ページから巨人戦の予告先発を抽出 (459/C、 純粋関数)。

    `<td>先発</td><td>(略) <a>投手名</a></td>` が2行=1試合。 (巨) を含むペアを巨人戦とみなす。
    返り値: {"giants": 巨人先発, "opp": 相手先発} or {}。 確定発表のみ(予測でない)。
    """
    pairs = re.findall(
        r"<td>\s*先発\s*</td>\s*<td>\s*\(([^)]{1,3})\)\s*<a[^>]*>(.*?)</a>", html_text, re.S
    )

    def _clean(s: str) -> str:
        return re.sub(r"\s+", "", _html.unescape(re.sub(r"<[^>]+>", "", s)))

    for i in range(0, len(pairs) - 1, 2):
        a1, n1 = pairs[i]
        a2, n2 = pairs[i + 1]
        if a1 == "巨" or a2 == "巨":
            if a1 == "巨":
                g, o, o_abbr = n1, n2, a2
            else:
                g, o, o_abbr = n2, n1, a1
            return {"giants": _clean(g), "opp": _clean(o), "opp_abbr": o_abbr}
    return {}


# NPB略号 → /data/schedule の opp 短縮名 (予告先発 cross-check 用、 459/C)
_NPB_ABBR_TEAM = {
    "ヤ": "ヤクルト", "神": "阪神", "デ": "DeNA", "広": "広島", "中": "中日",
    "オ": "オリックス", "ソ": "ソフトバンク", "日": "日本ハム", "楽": "楽天",
    "西": "西武", "ロ": "ロッテ",
}


def fetch_giants_starters() -> dict:
    """本日の巨人戦 予告先発を NPB公式から scrape (459/C)。"""
    try:
        year = date.today().year
    except Exception:  # noqa: BLE001
        return {}
    try:
        r = requests.get(
            f"https://npb.jp/games/{year}/", timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"},
        )
        r.raise_for_status()
        r.encoding = "utf-8"
        starters = parse_giants_starters(r.text)
        if not starters:
            LOG.info("fetch_giants_starters: no (巨) pair found (html len=%d)", len(r.text))
        return starters
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_giants_starters err: %r", exc)
        return {}


def fetch_giants_upcoming(limit: int = 6) -> list[dict]:
    """巨人の今後の試合を NPB公式月間日程から scrape (459/C)。 当月の未消化試合。"""
    try:
        today = date.today()
    except Exception:  # noqa: BLE001
        return []
    url = f"https://npb.jp/games/{today.year}/schedule_{today.month:02d}_detail.html"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        r.encoding = "utf-8"
        games = parse_giants_upcoming(r.text, today.year, today, limit=limit)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_giants_upcoming err: %r", exc)
        return []
    # 直近の試合に予告先発を付与。 日付一致でなく「相手略号が日程の相手と一致」で判定
    # (Job は UTC、 試合は JST で date.today() がズレるため日付一致は不可。 cross-check で
    #  誤ペアリング防止しつつ TZ 非依存にする)。
    if games:
        st = fetch_giants_starters()
        mapped = _NPB_ABBR_TEAM.get(st.get("opp_abbr", "")) if st else None
        LOG.info("upcoming starters: st=%s mapped=%s game0_opp=%s game0_date=%s",
                 st, mapped, games[0].get("opp"), games[0].get("date"))
        if st and mapped == games[0].get("opp"):
            games[0]["starter_g"] = st.get("giants")
            games[0]["starter_o"] = st.get("opp")
    return games


def fetch_giants_team_record() -> dict:
    """巨人 チーム成績サマリー (games から、 459)。

    返り値: {wins, losses, draws, win_pct, runs_for, runs_against, run_diff,
             streak, streak_kind ('W'/'L'/''), home (W,L), away (W,L)}。
    順位/ゲーム差は standings_snapshots が未 populate のため含めない (データ制約)。
    未来試合/予告先発も games に無いため非対応。
    """
    path = _ensure_insight_db_local()
    if not path:
        return {}
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT game_id, result, giants_score, opp_score FROM games ORDER BY game_date")
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("fetch_giants_team_record err: %r", exc)
        return {}
    g = [r for r in rows if giants_venue_from_game_id(str(r[0] or "")) is not None]
    if not g:
        return {}
    w = l = t = rf = ra = 0
    hw = hl = aw = al = 0
    seq: list[str] = []
    for gid, result, gs, os_ in g:
        venue = giants_venue_from_game_id(str(gid or ""))
        rf += int(gs or 0)
        ra += int(os_ or 0)
        if result == "win":
            w += 1
            seq.append("W")
            if venue == "home":
                hw += 1
            else:
                aw += 1
        elif result == "loss":
            l += 1
            seq.append("L")
            if venue == "home":
                hl += 1
            else:
                al += 1
        else:
            t += 1
            seq.append("T")
    streak = 0
    kind = ""
    for s in reversed(seq):
        if s == "T":
            break
        if kind == "":
            kind = s
            streak = 1
        elif s == kind:
            streak += 1
        else:
            break
    decided = w + l
    return {
        "wins": w, "losses": l, "draws": t,
        "win_pct": (w / decided) if decided > 0 else None,
        "runs_for": rf, "runs_against": ra, "run_diff": rf - ra,
        "streak": streak, "streak_kind": kind,
        "home": (hw, hl), "away": (aw, al),
    }


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
    "load_ob_legend_entries",
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
    "SurpriseStatEntry",
    "fetch_team_leaders",
    "fetch_surprise_stats",
    "fetch_team_rankings",
    "fetch_latest_giants_game_date",
    "fetch_player_latest_game_date",
    "fetch_hit_streak",
    "fetch_contribution_streak",
    "fetch_pitching_stats_season",
    "fetch_recent_pitching_games",
]
