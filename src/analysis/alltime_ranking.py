"""全史ランキング計算(共有部品)— 巨人に在籍した選手の NPB通算記録を横断ランキング。

設計: spec/data-articles-no1-design.md §7.2(共有部品、1度作って2用途)。
- 用途1: /data/ranking 通算タブ(サイト、top-N 表示)。
- 用途2: ④ 通算ランキング変動(記事、前日 snapshot と比較して順位上昇を検知)。

データ源(いずれも **NPB通算**、球団限定ではない点に注意 → 表記は「NPB通算」):
- OB: config/ob_legends_full.json の stats[name].npb(hr/hits/rbi/w/k)。年度別が無く
  球団限定は算出不可なので NPB通算で揃える。
- 現役: npb_career cache(467)の通算 total(本塁打/安打/打点/勝利/三振)。

ランキング対象 stat は OB と現役の両方で取れる 5 種に限定:
  打者 本塁打 / 安打 / 打点、 投手 勝利 / 奪三振。
"""
from __future__ import annotations

import json as _json
import os as _os
from pathlib import Path as _Path
from typing import Any, Optional

from src.npb_career_scraper import _career_int

_OB_FULL_PATH = _Path(__file__).resolve().parents[2] / "config" / "ob_legends_full.json"

# 順位 band(④ がまたぎ検知に使う)。
RANK_BANDS = [10, 20, 50, 100]

# stat_key -> (表示名, OB npb field, 現役 cache total 列, 選手種別)
STAT_SPECS: dict[str, dict[str, str]] = {
    "hr": {"label": "本塁打", "ob_field": "hr", "cur_col": "本塁打", "kind": "batter"},
    "hits": {"label": "安打", "ob_field": "hits", "cur_col": "安打", "kind": "batter"},
    "rbi": {"label": "打点", "ob_field": "rbi", "cur_col": "打点", "kind": "batter"},
    "win": {"label": "勝利", "ob_field": "w", "cur_col": "勝利", "kind": "pitcher"},
    "so": {"label": "奪三振", "ob_field": "k", "cur_col": "三振", "kind": "pitcher"},
}


def load_ob_stats() -> dict[str, dict]:
    try:
        return (_json.loads(_OB_FULL_PATH.read_text(encoding="utf-8")) or {}).get(
            "stats", {}
        ) or {}
    except Exception:
        return {}


def _current_entries(career_cache: dict[str, Any], spec: dict) -> dict[str, dict]:
    """現役 cache から (name -> {value, slug}) を spec の stat 列で抽出。"""
    from src.data_site_slug import player_slug

    out: dict[str, dict] = {}
    if not career_cache:
        return out
    ids = career_cache.get("ids") or {}
    rev: dict[str, str] = {}
    for name, npb_id in ids.items():
        rev.setdefault(str(npb_id), name)
    want_pitcher = spec["kind"] == "pitcher"
    for npb_id, p in (career_cache.get("players") or {}).items():
        if not isinstance(p, dict) or not p:
            continue
        if bool(p.get("is_pitcher")) != want_pitcher:
            continue
        name = rev.get(str(npb_id))
        if not name:
            continue
        table = (p.get("pitching") if want_pitcher else p.get("batting")) or {}
        v = _career_int((table.get("total") or {}).get(spec["cur_col"]))
        if v is None:
            continue
        out[name] = {"value": v, "slug": player_slug(name)}
    return out


def build_rankings(
    ob_stats: Optional[dict[str, dict]] = None,
    career_cache: Optional[dict[str, Any]] = None,
) -> dict[str, list[dict[str, Any]]]:
    """stat_key -> 降順ランキング list[{rank, name, value, is_current, slug}]。

    同名(現役 ⇄ OB)が衝突した場合は現役を優先(上書き)。
    """
    if ob_stats is None:
        ob_stats = load_ob_stats()
    rankings: dict[str, list[dict[str, Any]]] = {}
    for key, spec in STAT_SPECS.items():
        entries: dict[str, dict] = {}
        want_pitcher = spec["kind"] == "pitcher"
        for name, s in ob_stats.items():
            if bool(s.get("type") == "pitcher") != want_pitcher:
                continue
            v = _career_int((s.get("npb") or {}).get(spec["ob_field"]))
            if v is None:
                continue
            entries[name] = {"value": v, "is_current": False, "slug": s.get("slug")}
        for name, cur in _current_entries(career_cache or {}, spec).items():
            entries[name] = {
                "value": cur["value"],
                "is_current": True,
                "slug": cur["slug"],
            }
        ranked = sorted(entries.items(), key=lambda kv: -kv[1]["value"])
        rows: list[dict[str, Any]] = []
        for i, (name, e) in enumerate(ranked, 1):
            rows.append(
                {
                    "rank": i,
                    "name": name,
                    "value": e["value"],
                    "is_current": e["is_current"],
                    "slug": e["slug"],
                }
            )
        rankings[key] = rows
    return rankings


def current_player_ranks(
    rankings: dict[str, list[dict[str, Any]]]
) -> dict[str, dict[str, dict[str, Any]]]:
    """現役選手の順位 snapshot。stat_key -> name -> {rank, value, slug, below_name}。

    below_name = 1 つ下の順位の選手名(= 順位が上がった時に「抜いた相手」候補)。
    """
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for key, rows in rankings.items():
        cur: dict[str, dict[str, Any]] = {}
        for idx, row in enumerate(rows):
            if not row["is_current"]:
                continue
            below = rows[idx + 1]["name"] if idx + 1 < len(rows) else None
            cur[row["name"]] = {
                "rank": row["rank"],
                "value": row["value"],
                "slug": row["slug"],
                "below_name": below,
            }
        out[key] = cur
    return out


# ─── snapshot 永続(④ の前日比較用、GCS object）─────────────────────────
_LOCAL_SNAP = "/tmp/insight_cache/alltime_rank_snapshot.json"
_SNAP_OBJECT = "alltime_rank_snapshot.json"


def _gcs_bucket() -> str:
    return (_os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()


def load_snapshot() -> Optional[dict[str, Any]]:
    """前回 snapshot を GCS から(無ければ local、どちらも無ければ None)。"""
    bucket = _gcs_bucket()
    if bucket:
        try:
            from google.cloud import storage  # type: ignore

            blob = storage.Client().bucket(bucket).blob(_SNAP_OBJECT)
            if blob.exists():
                return _json.loads(blob.download_as_text())
        except Exception:
            pass
    try:
        with open(_LOCAL_SNAP, encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return None


def save_snapshot(snapshot: dict[str, Any]) -> bool:
    """今回 snapshot を GCS(+local)へ。例外は飲み込む(publish 非ブロック)。"""
    payload = _json.dumps(snapshot, ensure_ascii=False)
    ok = False
    bucket = _gcs_bucket()
    if bucket:
        try:
            from google.cloud import storage  # type: ignore

            storage.Client().bucket(bucket).blob(_SNAP_OBJECT).upload_from_string(
                payload, content_type="application/json"
            )
            ok = True
        except Exception:
            ok = False
    try:
        _os.makedirs(_os.path.dirname(_LOCAL_SNAP), exist_ok=True)
        with open(_LOCAL_SNAP, "w", encoding="utf-8") as fh:
            fh.write(payload)
    except Exception:
        pass
    return ok
