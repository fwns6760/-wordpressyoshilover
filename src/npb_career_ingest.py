"""ticket 467 — NPB career cache の日次 ingest + 読み込み (GCS JSON object)。

設計判断 (race 回避):
  career データは ``insight.db`` に同梱しない。insight-nightly が 1 日複数回
  download→modify→upload するため、別 writer が同じ insight.db を触ると upload race で
  片方が clobber される。よって career cache は **独立 GCS object** ``npb_career.json`` に置き、
  単一 writer (本 ingest) だけが書く。publisher は read のみ。

運用 (network 負荷、ticket 467 §設計上の注意):
  pillar publish は 1 run で 100+ 選手を render する。career を毎 publish 毎選手 scrape すると
  NPB 過負荷。よって本 module は **日次 1 回だけ** scrape する (staleness gate)。
  publisher は publish 開始時に ``load_or_refresh`` を 1 回呼ぶ。cache が新しければ scrape を skip。
  scrape の失敗は publish を一切ブロックしない (全て try/except、 失敗時は旧 cache を維持)。

JSON 構造:
  {
    "generated_at": "2026-06-02T06:01:00+00:00",
    "ids": {"戸郷翔征": "41045138", ...},        # name -> npb_id
    "players": {"41045138": {<parse_player_career 結果>}, ...}
  }
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.npb_career_scraper import (
    fetch_giants_roster_ids,
    fetch_player_career,
)

LOG = logging.getLogger("npb_career_ingest")

_LOCAL_CACHE = "/tmp/insight_cache/npb_career.json"
_CACHE_OBJECT = "npb_career.json"
_DEFAULT_MAX_AGE_HOURS = 20.0
_FETCH_SLEEP_SEC = 0.4  # NPB への礼儀 (115 名 ≈ 50s)


def _gcs_bucket() -> str:
    return (os.environ.get("INSIGHT_GCS_BUCKET") or "").strip()


def _gcs_object_name() -> str:
    prefix = (os.environ.get("INSIGHT_GCS_PREFIX") or "").strip().strip("/")
    return f"{prefix}/{_CACHE_OBJECT}" if prefix else _CACHE_OBJECT


def _download_cache(local_path: str = _LOCAL_CACHE) -> Optional[Dict[str, Any]]:
    """GCS から npb_career.json を local に落として dict 返す。無ければ None。"""
    bucket = _gcs_bucket()
    if not bucket:
        # local fallback (dev)
        if os.path.exists(local_path):
            try:
                with open(local_path, encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                return None
        return None
    try:
        from google.cloud import storage  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        LOG.warning("storage import failed: %r", exc)
        return None
    try:
        client = storage.Client()
        blob = client.bucket(bucket).blob(_gcs_object_name())
        if not blob.exists():
            return None
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(local_path)
        with open(local_path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("career cache download failed: %r", exc)
        return None


def _upload_cache(cache: Dict[str, Any], local_path: str = _LOCAL_CACHE) -> bool:
    try:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("career cache local write failed: %r", exc)
        return False
    bucket = _gcs_bucket()
    if not bucket:
        return True  # dev: local only
    try:
        from google.cloud import storage  # noqa: WPS433

        client = storage.Client()
        blob = client.bucket(bucket).blob(_gcs_object_name())
        blob.upload_from_filename(local_path, content_type="application/json")
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.warning("career cache upload failed: %r", exc)
        return False


def _cache_age_hours(cache: Optional[Dict[str, Any]]) -> Optional[float]:
    if not cache:
        return None
    raw = cache.get("generated_at")
    if not raw:
        return None
    try:
        gen = _dt.datetime.fromisoformat(raw)
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=_dt.timezone.utc)
        delta = _dt.datetime.now(_dt.timezone.utc) - gen
        return delta.total_seconds() / 3600.0
    except Exception:
        return None


def refresh_cache(
    active_names: List[str],
    prev: Optional[Dict[str, Any]] = None,
    sleep_sec: float = _FETCH_SLEEP_SEC,
) -> Dict[str, Any]:
    """巨人ロスターの全選手 career を scrape して cache dict を組む (日次 1 回想定)。

    - name->id は NPB ロスターから取得。
    - active_names のうち id 解決できた選手を 1 名ずつ fetch。
    - fetch 失敗の選手は prev cache の payload を温存 (取りこぼし最小化)。
    """
    prev = prev or {}
    prev_players: Dict[str, Any] = dict(prev.get("players") or {})
    ids = fetch_giants_roster_ids()
    if not ids:
        LOG.warning("roster ids empty — keep previous career cache")
        return prev or {"generated_at": _now_iso(), "ids": {}, "players": {}}

    players: Dict[str, Any] = {}
    fetched = 0
    for name in active_names:
        from src.npb_career_scraper import _normalize_name  # local import (private helper)

        npb_id = ids.get(_normalize_name(name))
        if not npb_id:
            continue
        payload = None
        try:
            payload = fetch_player_career(npb_id, timeout=12.0)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("career fetch error name=%s id=%s: %r", name, npb_id, exc)
        if payload and (payload.get("batting") or payload.get("pitching")):
            players[npb_id] = payload
            fetched += 1
        elif npb_id in prev_players:
            players[npb_id] = prev_players[npb_id]  # 温存
        if sleep_sec:
            time.sleep(sleep_sec)

    LOG.info("career cache refreshed: fetched=%d total=%d ids=%d", fetched, len(players), len(ids))
    return {"generated_at": _now_iso(), "ids": ids, "players": players}


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def load_or_refresh(
    active_names: List[str],
    max_age_hours: float = _DEFAULT_MAX_AGE_HOURS,
) -> Dict[str, Any]:
    """publisher が publish 開始時に 1 回呼ぶ。新しければ scrape skip、古ければ refresh+upload。

    例外は決して送出しない (publish 非ブロック)。常に dict を返す (最悪 {} 同等)。
    """
    try:
        cache = _download_cache() or {}
    except Exception:  # noqa: BLE001
        cache = {}
    # dry-run / test では NPB scrape を一切行わない (既存 cache のみ使用)。
    if str(os.environ.get("DATA_SITE_DRY_RUN", "")).strip().lower() in {"1", "true", "yes", "on"}:
        LOG.info("dry-run: skip career scrape, use existing cache (players=%d)",
                 len((cache or {}).get("players") or {}))
        return cache
    age = _cache_age_hours(cache)
    if cache and age is not None and age < max_age_hours:
        LOG.info("career cache fresh (age=%.1fh) — skip scrape", age)
        return cache
    LOG.info("career cache stale (age=%s) — refreshing", age)
    try:
        refreshed = refresh_cache(active_names, prev=cache)
        # players が空に転落した場合は旧 cache を温存 (退行防止)
        if not refreshed.get("players") and cache.get("players"):
            LOG.warning("refresh produced 0 players — keep previous cache")
            return cache
        _upload_cache(refreshed)
        return refreshed
    except Exception as exc:  # noqa: BLE001
        LOG.warning("career cache refresh failed, using previous: %r", exc)
        return cache


def career_payload_for(cache: Dict[str, Any], player_name: str) -> Optional[Dict[str, Any]]:
    """cache から player_name の career payload を引く。無ければ None。"""
    if not cache:
        return None
    from src.npb_career_scraper import _normalize_name

    ids = cache.get("ids") or {}
    players = cache.get("players") or {}
    npb_id = ids.get(_normalize_name(player_name))
    if not npb_id:
        return None
    return players.get(npb_id)


def main(argv: Optional[List[str]] = None) -> int:
    """standalone ingest entrypoint (任意。通常は publisher 内 load_or_refresh で十分)。

    強制 refresh: ``python -m src.npb_career_ingest <name1> <name2> ...``
    引数無しは roster target を data_site_publisher から取得。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    names = list(argv or [])
    if not names:
        try:
            from src.data_site_publisher import load_data_site_target_names

            names = list(load_data_site_target_names())
        except Exception as exc:  # noqa: BLE001
            LOG.error("could not load target names: %r", exc)
            return 1
    cache = refresh_cache(names, prev=_download_cache() or {})
    ok = _upload_cache(cache)
    LOG.info("ingest done players=%d upload_ok=%s", len(cache.get("players") or {}), ok)
    return 0 if ok else 1


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
