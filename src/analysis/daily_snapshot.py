"""414 axis E4 + E5: daily snapshot infrastructure for lineup change + promotion diff.

user 仕様 2026-05-20: 試合前注目テーマに「打順変更」「昇格選手」 を含めたい。
両方 「前日 → 今日」 の diff が必要。 schema 変更 / DB 拡張なしで GCS JSONL に
日次 snapshot を保存し、 翌日 read して compare する。

ファイル構成 (GCS bucket = INSIGHT_GCS_BUCKET):
- daily_snapshot/lineup_YYYY-MM-DD.json — 今日のスタメン 9 名 list
- daily_snapshot/roster_active_YYYY-MM-DD.json — 今日 active=True 選手 set

caller (run_x_post_mail.py / fetcher) が任意のタイミングで save、 別 caller (Gemini Flash Lite
branding pre-game theme builder) が翌日 load + diff 計算。 GCS 失敗時は silent
fallback (空文字 / 空 set)、 既存 mail 挙動維持。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

JST = timezone(timedelta(hours=9))


def _lineup_snapshot_blob_path(date_str: str) -> str:
    return f"daily_snapshot/lineup_{date_str}.json"


def _roster_active_snapshot_blob_path(date_str: str) -> str:
    return f"daily_snapshot/roster_active_{date_str}.json"


def _get_storage_client():
    from google.cloud import storage  # noqa: WPS433
    return storage.Client()


def save_lineup_snapshot(
    bucket_name: str,
    date_str: str,
    lineup_names: list[str],
    *,
    logger=None,
) -> bool:
    """今日のスタメン 9 名 list を GCS に save (上書き OK).

    Returns True on success, False on any error (silent skip)。
    """
    if not bucket_name or not date_str or not lineup_names:
        return False
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(_lineup_snapshot_blob_path(date_str))
        payload = {
            "date": date_str,
            "lineup": [str(n).strip() for n in lineup_names if str(n).strip()],
            "saved_at_jst": datetime.now(JST).isoformat(),
        }
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.info("save_lineup_snapshot_skip date=%s reason=%r", date_str, exc)
        return False


def load_lineup_snapshot(
    bucket_name: str,
    date_str: str,
    *,
    logger=None,
) -> list[str]:
    """指定日の lineup snapshot を読み出す. 不在 / 失敗時は空 list."""
    if not bucket_name or not date_str:
        return []
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(_lineup_snapshot_blob_path(date_str))
        if not blob.exists():
            return []
        text = blob.download_as_text()
        payload = json.loads(text)
        return [
            str(n).strip() for n in (payload.get("lineup") or []) if str(n).strip()
        ]
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.info("load_lineup_snapshot_skip date=%s reason=%r", date_str, exc)
        return []


def save_roster_active_snapshot(
    bucket_name: str,
    date_str: str,
    active_player_names: list[str],
    *,
    logger=None,
) -> bool:
    """今日 active=True (支配下選手) name list を GCS に save."""
    if not bucket_name or not date_str:
        return False
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(_roster_active_snapshot_blob_path(date_str))
        payload = {
            "date": date_str,
            "active_players": sorted(
                {str(n).strip() for n in active_player_names if str(n).strip()}
            ),
            "saved_at_jst": datetime.now(JST).isoformat(),
        }
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.info("save_roster_active_snapshot_skip date=%s reason=%r", date_str, exc)
        return False


def load_roster_active_snapshot(
    bucket_name: str,
    date_str: str,
    *,
    logger=None,
) -> set[str]:
    """指定日の roster active snapshot を読み出す. 不在 / 失敗時は空 set."""
    if not bucket_name or not date_str:
        return set()
    try:
        client = _get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(_roster_active_snapshot_blob_path(date_str))
        if not blob.exists():
            return set()
        text = blob.download_as_text()
        payload = json.loads(text)
        return {
            str(n).strip() for n in (payload.get("active_players") or []) if str(n).strip()
        }
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger.info("load_roster_active_snapshot_skip date=%s reason=%r", date_str, exc)
        return set()


def compute_lineup_change_summary(
    today_lineup: list[str],
    yesterday_lineup: list[str],
) -> str:
    """打順変更 summary を 1 行に整形.

    順序 (打順) の差異 + 入れ替わり選手を簡潔に。 yesterday 不在 / 同一なら空文字。
    例: 「打順変更: 3番 坂本 → 泉口、 ベンチ入り: 増田陸」
    """
    today = [str(n).strip() for n in (today_lineup or []) if str(n).strip()]
    yesterday = [str(n).strip() for n in (yesterday_lineup or []) if str(n).strip()]
    if not yesterday or not today:
        return ""
    if today == yesterday:
        return ""
    today_set = set(today)
    yesterday_set = set(yesterday)
    added = today_set - yesterday_set
    removed = yesterday_set - today_set
    parts: list[str] = []
    order_changes: list[str] = []
    common = today_set & yesterday_set
    today_index = {n: i for i, n in enumerate(today)}
    yesterday_index = {n: i for i, n in enumerate(yesterday)}
    for name in common:
        if today_index[name] != yesterday_index[name]:
            order_changes.append(
                f"{yesterday_index[name] + 1}番→{today_index[name] + 1}番 {name}"
            )
        if len(order_changes) >= 3:
            break
    if order_changes:
        parts.append("打順変更: " + " / ".join(order_changes))
    if added:
        parts.append("スタメン入り: " + ", ".join(sorted(added)[:3]))
    if removed:
        parts.append("外れ: " + ", ".join(sorted(removed)[:3]))
    return "、 ".join(parts)


def compute_promotion_summary(
    today_active: set[str],
    yesterday_active: set[str],
) -> str:
    """昇格 / 抹消 summary を 1 行に整形.

    yesterday 不在 / 同一なら空文字。
    例: 「昇格: 松浦慶斗、 抹消: 田中千晴」
    """
    today_set = {str(n).strip() for n in (today_active or set()) if str(n).strip()}
    yesterday_set = {str(n).strip() for n in (yesterday_active or set()) if str(n).strip()}
    if not yesterday_set or not today_set:
        return ""
    if today_set == yesterday_set:
        return ""
    promoted = today_set - yesterday_set
    demoted = yesterday_set - today_set
    parts: list[str] = []
    if promoted:
        parts.append("昇格: " + ", ".join(sorted(promoted)[:5]))
    if demoted:
        parts.append("抹消: " + ", ".join(sorted(demoted)[:5]))
    return "、 ".join(parts)


def build_lineup_change_string(
    bucket_name: str,
    today_lineup: list[str],
    *,
    now_jst: Optional[datetime] = None,
    logger=None,
) -> str:
    """414 axis E4 helper: 前日 lineup を GCS から load → diff summary を返す."""
    if not bucket_name or not today_lineup:
        return ""
    if now_jst is None:
        now_jst = datetime.now(JST)
    yesterday = (now_jst.date() - timedelta(days=1)).isoformat()
    yesterday_lineup = load_lineup_snapshot(bucket_name, yesterday, logger=logger)
    return compute_lineup_change_summary(today_lineup, yesterday_lineup)


def build_promotion_string(
    bucket_name: str,
    today_active: set[str],
    *,
    now_jst: Optional[datetime] = None,
    logger=None,
) -> str:
    """414 axis E5 helper: 前日 active snapshot を GCS から load → diff summary を返す."""
    if not bucket_name or not today_active:
        return ""
    if now_jst is None:
        now_jst = datetime.now(JST)
    yesterday = (now_jst.date() - timedelta(days=1)).isoformat()
    yesterday_active = load_roster_active_snapshot(bucket_name, yesterday, logger=logger)
    return compute_promotion_summary(today_active, yesterday_active)
