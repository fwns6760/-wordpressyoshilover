"""Orchestrator for YouTube Shorts Phase 1.5.

Default execution is dry-run.  Use ``--live`` to upload the generated MP4 to
GCS and send the approval mail.  YouTube upload is opt-in via
``--youtube-private-upload`` and remains private until the approval button is
used.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
import html
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping

from src.mail_delivery_bridge import MailRequest, send as bridge_send
from src.yt_shorts_render import RenderedShort, render_short
from src.yt_shorts_script import ShortsScript, build_script
from src.yt_shorts_topic import (
    DEFAULT_SOURCE_URL,
    ShortsTopic,
    list_topics_from_notable_data,
    select_topic_from_notable_data,
    topic_from_notable_item,
)
from src.yt_shorts_youtube import YouTubeUploadResult, upload_private_video
from src.yt_shorts_youtube_token import build_yt_shorts_publish_url


JST = timezone(timedelta(hours=9))
DEFAULT_OUTPUT_DIR = Path("/tmp/yt_shorts")
DEFAULT_BUCKET_PREFIX = "yt_shorts"
LOG = logging.getLogger(__name__)
PLAYER_IMAGE_ENV = "YT_SHORTS_PLAYER_IMAGE_URL"
EXCLUDE_PLAYERS_ENV = "YT_SHORTS_EXCLUDE_PLAYERS"
TARGET_PLAYERS_ENV = "YT_SHORTS_TARGET_PLAYERS"
PLAYER_COOLDOWN_DAYS_ENV = "YT_SHORTS_PLAYER_COOLDOWN_DAYS"
DEFAULT_PLAYER_COOLDOWN_DAYS = 7
# Wider than the public /data/notable page (16): the Shorts selector needs a
# deep, diverse candidate pool so the player cooldown has room to rotate and
# does not keep falling back to the same hot streak leader every run.
DEFAULT_NOTABLE_LIMIT = 40
TARGET_PLAYER_NOTABLE_LIMIT = 80


@dataclass(frozen=True)
class ShortsRunResult:
    status: str
    dry_run: bool
    topic_key: str = ""
    title: str = ""
    output_dir: str = ""
    video_path: str = ""
    gcs_uri: str = ""
    signed_url: str = ""
    mail_status: str = ""
    reason: str = ""
    tts_mode: str = ""
    youtube_video_id: str = ""
    youtube_watch_url: str = ""
    youtube_studio_url: str = ""
    youtube_publish_url: str = ""
    youtube_upload_status: str = ""


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_recipients(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\s]+", value or "") if part.strip()]


def _split_csvish(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;、\n]+", value or "") if part.strip()]


def _normalize_player_name(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").replace("　", " ").strip())


def _mail_recipients() -> list[str]:
    return (
        _split_recipients(os.environ.get("YT_SHORTS_MAIL_TO", ""))
        or _split_recipients(os.environ.get("MAIL_BRIDGE_TO", ""))
        or _split_recipients(os.environ.get("FACT_CHECK_EMAIL_TO", ""))
        or ["fwns6760@gmail.com"]
    )


def _approval_base_url() -> str:
    return (
        os.environ.get("YT_SHORTS_APPROVAL_BASE_URL", "").strip().rstrip("/")
        or os.environ.get("FETCHER_PUBLIC_BASE_URL", "").strip().rstrip("/")
    )


def _now_jst() -> datetime:
    return datetime.now(JST)


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip("-")
    return cleaned[:96] or "short"


def _load_notable_data_from_repo(limit: int = DEFAULT_NOTABLE_LIMIT) -> dict[str, Any]:
    # Import lazily because data_site_publisher has a broad dependency surface.
    from src.data_site_publisher import _build_notable_data_from_targets

    # latest_game_only=False so season-to-date leaders (not just players who
    # appeared in the latest game) widen the pool; without this the eligible
    # set collapses to a few hot players and the cooldown cannot rotate.
    data = _build_notable_data_from_targets(limit=limit, latest_game_only=False)
    return dict(data or {})


def _load_notable_data_from_json(path: Path | str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("topic JSON must be an object")
    return data


def _load_notable_data_from_json_inline(raw_json: str) -> dict[str, Any]:
    data = json.loads(raw_json)
    if not isinstance(data, dict):
        raise ValueError("topic JSON inline value must be an object")
    return data


def _player_image_url(topic: ShortsTopic) -> str:
    raw = topic.raw_item or {}
    env_url = os.environ.get(PLAYER_IMAGE_ENV, "").strip()
    if env_url:
        return env_url
    value = str(raw.get("player_image_url") or "").strip()
    if value:
        return value
    try:
        from src.data_site_query import (
            find_player_featured_image_url,
            mapped_player_media_id,
        )

        if mapped_player_media_id(topic.player) is None:
            LOG.info("yt_shorts_player_image_unmapped player=%s", topic.player)
            return ""
        return str(find_player_featured_image_url(topic.player) or "").strip()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("yt_shorts_player_image_url_failed player=%s err=%r", topic.player, exc)
        return ""


def _with_player_image(topic: ShortsTopic) -> ShortsTopic:
    url = _player_image_url(topic)
    if not url:
        return topic
    raw = dict(topic.raw_item or {})
    raw["player_image_url"] = url
    return replace(topic, raw_item=raw)


def _without_excluded_topics(
    notable_data: Mapping[str, Any],
    excluded_topic_keys: set[str],
    excluded_players: set[str] | None = None,
    target_players: set[str] | None = None,
) -> dict[str, Any]:
    excluded_players = excluded_players or set()
    target_players = target_players or set()
    if not excluded_topic_keys and not excluded_players and not target_players:
        return dict(notable_data)
    data = dict(notable_data)
    as_of = str(data.get("as_of") or "")
    filtered_items: list[Any] = []
    for item in data.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        topic = topic_from_notable_item(item, as_of=as_of, source_url=DEFAULT_SOURCE_URL)
        if topic is None:
            filtered_items.append(item)
            continue
        if topic.topic_key in excluded_topic_keys:
            continue
        if _normalize_player_name(topic.player) in excluded_players:
            continue
        if target_players and _normalize_player_name(topic.player) not in target_players:
            continue
        filtered_items.append(item)
    data["items"] = filtered_items
    return data


def _gcs_client():
    from google.cloud import storage

    return storage.Client()


def _history_blob_name(date_key: str, fmt: str = "data") -> str:
    # data は後方互換のため従来パス。legend 等は format を suffix にして
    # 同じ日に複数フォーマット (data + legend) の履歴/daily-cap を独立管理する。
    if fmt and fmt != "data":
        return f"{DEFAULT_BUCKET_PREFIX}/history/{date_key}-{fmt}.json"
    return f"{DEFAULT_BUCKET_PREFIX}/history/{date_key}.json"


def _load_history(bucket_name: str, date_key: str, fmt: str = "data") -> dict[str, Any] | None:
    if not bucket_name:
        return None
    try:
        bucket = _gcs_client().bucket(bucket_name)
        blob = bucket.blob(_history_blob_name(date_key, fmt))
        if not blob.exists():
            return None
        payload = blob.download_as_text(encoding="utf-8")
        data = json.loads(payload)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _recent_used(
    bucket_name: str,
    current: datetime,
    lookback_days: int,
    fmt: str = "data",
) -> tuple[set[str], set[str]]:
    """直近 ``lookback_days`` 日の history を読み、使用済みの

    (正規化 player 名 set, topic_key set) を返す。同じ選手ばかりになるのを防ぐ
    クールダウン用。 history が無い日は無視。
    """
    players: set[str] = set()
    topic_keys: set[str] = set()
    if not bucket_name or lookback_days <= 0:
        return players, topic_keys
    # offset 0 = 当日 (同日 re-run で直前の選手も除外)、1..N = 過去日。
    for offset in range(0, lookback_days + 1):
        day = (current - timedelta(days=offset)).strftime("%Y-%m-%d")
        hist = _load_history(bucket_name, day, fmt)
        if not hist:
            continue
        tk = str(hist.get("topic_key") or "").strip()
        if tk:
            topic_keys.add(tk)
        # player フィールド優先。無い古い履歴は topic_key から選手名を復元
        # (topic_key 形式: "yt_shorts|YYYY-MM-DD|<player>|<label>|<value>")。
        player_raw = str(hist.get("player") or "")
        if not player_raw and tk:
            parts = tk.split("|")
            if len(parts) >= 3:
                player_raw = parts[2]
        player = _normalize_player_name(player_raw)
        if player:
            players.add(player)
    return players, topic_keys


def _recent_used_offsets(
    bucket_name: str,
    current: datetime,
    lookback_days: int,
    fmt: str = "data",
) -> dict[str, int]:
    """直近 ``lookback_days`` 日の history から {正規化player名: 最小offset(=直近使用)}。

    cooldown で候補が枯渇した時に「最も久しく使っていない選手」を選ぶための
    least-recently-used 判定に使う。 history が無い日は無視。
    """
    offsets: dict[str, int] = {}
    if not bucket_name or lookback_days <= 0:
        return offsets
    for offset in range(0, lookback_days + 1):
        day = (current - timedelta(days=offset)).strftime("%Y-%m-%d")
        hist = _load_history(bucket_name, day, fmt)
        if not hist:
            continue
        player_raw = str(hist.get("player") or "")
        if not player_raw:
            tk = str(hist.get("topic_key") or "")
            parts = tk.split("|")
            if len(parts) >= 3:
                player_raw = parts[2]
        player = _normalize_player_name(player_raw)
        if player and player not in offsets:
            offsets[player] = offset  # 最初に当たった offset = 最も新しい使用
    return offsets


def _write_history(bucket_name: str, date_key: str, payload: Mapping[str, Any], fmt: str = "data") -> None:
    if not bucket_name:
        return
    bucket = _gcs_client().bucket(bucket_name)
    blob = bucket.blob(_history_blob_name(date_key, fmt))
    blob.upload_from_string(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        content_type="application/json; charset=utf-8",
    )


def _upload_artifacts(
    *,
    bucket_name: str,
    run_id: str,
    rendered: RenderedShort,
    topic: ShortsTopic,
    script: ShortsScript,
) -> tuple[str, str]:
    bucket = _gcs_client().bucket(bucket_name)
    prefix = f"{DEFAULT_BUCKET_PREFIX}/runs/{run_id}"
    video_blob = bucket.blob(f"{prefix}/short.mp4")
    video_blob.upload_from_filename(str(rendered.video_path), content_type="video/mp4")

    metadata = {
        "topic": asdict(topic),
        "script": {
            "title": script.title,
            "description": script.description,
            "narration": script.narration,
            "captions": [asdict(caption) for caption in script.captions],
            "allowed_numbers": list(script.allowed_numbers),
        },
        "render": {
            "duration_seconds": rendered.duration_seconds,
            "tts_mode": rendered.tts_mode,
        },
        "video_gcs_uri": f"gs://{bucket_name}/{video_blob.name}",
    }
    bucket.blob(f"{prefix}/metadata.json").upload_from_string(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        content_type="application/json; charset=utf-8",
    )

    signed_url = ""
    try:
        signed_url = video_blob.generate_signed_url(
            version="v4",
            expiration=timedelta(days=7),
            method="GET",
        )
    except Exception as exc:  # noqa: BLE001
        LOG.warning("yt_shorts_signed_url_failed err=%r", exc)
    return f"gs://{bucket_name}/{video_blob.name}", signed_url


def _mail_bodies(
    topic: ShortsTopic,
    script: ShortsScript,
    *,
    signed_url: str,
    gcs_uri: str,
    youtube_watch_url: str = "",
    youtube_studio_url: str = "",
    youtube_publish_url: str = "",
    youtube_video_id: str = "",
) -> tuple[str, str]:
    source_json = json.dumps(topic.raw_item, ensure_ascii=False, indent=2)
    youtube_lines = ""
    if youtube_video_id:
        youtube_lines = (
            f"YouTube video_id: {youtube_video_id}\n"
            f"YouTube確認: {youtube_watch_url or '(not available)'}\n"
            f"YouTube Studio: {youtube_studio_url or '(not available)'}\n"
            f"公開ボタン: {youtube_publish_url or '(approval URL not configured)'}\n"
        )
    text = (
        "YouTube Shorts 承認待ち\n\n"
        f"タイトル: {script.title}\n"
        f"動画URL: {signed_url or '(dry-run / no upload)'}\n"
        f"GCS: {gcs_uri or '(dry-run / no upload)'}\n"
        f"{youtube_lines}"
        f"元データ: {topic.source_url}\n\n"
        "台本:\n"
        f"{script.narration}\n\n"
        "概要欄:\n"
        f"{script.description}\n\n"
        "X再投稿文(コピペ用):\n"
        f"{script.x_post}\n\n"
        "元データJSON:\n"
        f"{source_json}\n"
    )
    youtube_button_html = ""
    if youtube_watch_url or youtube_studio_url or youtube_publish_url:
        watch_button = (
            f'<a href="{html.escape(youtube_watch_url)}" '
            'style="display:inline-block;background:#111;color:#fff;padding:10px 14px;'
            'border-radius:6px;text-decoration:none;font-weight:700;margin-right:8px;">YouTubeで確認</a>'
            if youtube_watch_url
            else ""
        )
        studio_button = (
            f'<a href="{html.escape(youtube_studio_url)}" '
            'style="display:inline-block;background:#fff;color:#111;padding:9px 13px;'
            'border-radius:6px;text-decoration:none;font-weight:700;border:1px solid #111;margin-right:8px;">Studioで編集</a>'
            if youtube_studio_url
            else ""
        )
        publish_button = (
            f'<a href="{html.escape(youtube_publish_url)}" '
            'style="display:inline-block;background:#1b8a3e;color:#fff;padding:10px 14px;'
            'border-radius:6px;text-decoration:none;font-weight:700;">公開する</a>'
            if youtube_publish_url
            else ""
        )
        note = (
            '<p style="font-size:12px;color:#777;margin-top:8px;">'
            'YouTube確認リンクは、チャンネル所有者としてログインしているブラウザで確認してください。'
            '</p>'
            if youtube_watch_url
            else ""
        )
        youtube_button_html = (
            '<h2 style="font-size:16px;margin-top:18px;">YouTube</h2>'
            f'<p style="margin:8px 0;">{watch_button}{studio_button}{publish_button}</p>'
            f'{note}'
        )
    mp4_button_html = (
        f'<p><a href="{html.escape(signed_url)}" '
        'style="display:inline-block;background:#ff7a1a;color:#fff;padding:10px 14px;'
        'border-radius:6px;text-decoration:none;font-weight:700;">MP4を開く</a></p>'
        if signed_url
        else ""
    )
    html_body = (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;line-height:1.7;">'
        '<h1 style="font-size:20px;margin:0 0 12px;">YouTube Shorts 承認待ち</h1>'
        f'<p><strong>タイトル:</strong> {html.escape(script.title)}</p>'
        f"{mp4_button_html}"
        f"{youtube_button_html}"
        f'<p style="font-size:13px;color:#666;">GCS: {html.escape(gcs_uri or "(dry-run / no upload)")}</p>'
        f'<p style="font-size:13px;color:#666;">元データ: <a href="{html.escape(topic.source_url)}">{html.escape(topic.source_url)}</a></p>'
        '<h2 style="font-size:16px;margin-top:18px;">台本</h2>'
        f'<pre style="white-space:pre-wrap;background:#fafafa;border:1px solid #eee;padding:12px;">{html.escape(script.narration)}</pre>'
        '<h2 style="font-size:16px;margin-top:18px;">概要欄</h2>'
        f'<pre style="white-space:pre-wrap;background:#fafafa;border:1px solid #eee;padding:12px;">{html.escape(script.description)}</pre>'
        '<h2 style="font-size:16px;margin-top:18px;">X再投稿文(コピペ用)</h2>'
        f'<pre style="white-space:pre-wrap;background:#fff8e1;border:1px solid #ffe082;padding:12px;">{html.escape(script.x_post)}</pre>'
        '<h2 style="font-size:16px;margin-top:18px;">元データ</h2>'
        f'<pre style="white-space:pre-wrap;background:#fafafa;border:1px solid #eee;padding:12px;">{html.escape(source_json)}</pre>'
        "</div>"
    )
    return text, html_body


def send_approval_mail(
    topic: ShortsTopic,
    script: ShortsScript,
    *,
    signed_url: str,
    gcs_uri: str,
    youtube_watch_url: str = "",
    youtube_studio_url: str = "",
    youtube_publish_url: str = "",
    youtube_video_id: str = "",
    dry_run: bool,
) -> str:
    text, html_body = _mail_bodies(
        topic,
        script,
        signed_url=signed_url,
        gcs_uri=gcs_uri,
        youtube_watch_url=youtube_watch_url,
        youtube_studio_url=youtube_studio_url,
        youtube_publish_url=youtube_publish_url,
        youtube_video_id=youtube_video_id,
    )
    result = bridge_send(
        MailRequest(
            to=_mail_recipients(),
            subject=f"【YT Shorts承認】{script.title}",
            text_body=text,
            html_body=html_body,
            metadata={"lane": "yt_shorts", "topic_key": topic.topic_key},
        ),
        dry_run=dry_run,
    )
    return result.status


def _failure_mail(subject: str, message: str, *, dry_run: bool) -> str:
    result = bridge_send(
        MailRequest(
            to=_mail_recipients(),
            subject=subject,
            text_body=message,
            html_body=f"<pre>{html.escape(message)}</pre>",
            metadata={"lane": "yt_shorts", "kind": "failure"},
        ),
        dry_run=dry_run,
    )
    return result.status


def _cooldown_days_env() -> int:
    try:
        return int(os.environ.get(PLAYER_COOLDOWN_DAYS_ENV, str(DEFAULT_PLAYER_COOLDOWN_DAYS)))
    except ValueError:
        return DEFAULT_PLAYER_COOLDOWN_DAYS


def _load_legend_entries_from_repo() -> list[dict[str, Any]]:
    from src.data_site_query import load_ob_legend_entries

    return list(load_ob_legend_entries() or [])


def _select_legend_topic(
    *,
    bucket: str,
    current: datetime,
    cooldown_days: int,
    live: bool,
    legend_entries: list[dict[str, Any]] | None,
):
    """記録の強い順 + cooldown(直近使用除外)+ 枯渇時 LRU でレジェンド主役を選ぶ。"""
    from src.yt_shorts_legend import LEGEND_SOURCE_URL, list_legend_topics

    candidates = list_legend_topics(legend_entries, source_url=LEGEND_SOURCE_URL)
    if not candidates:
        return None
    cooldown_players: set[str] = set()
    cooldown_topic_keys: set[str] = set()
    if live and bucket:
        cooldown_players, cooldown_topic_keys = _recent_used(bucket, current, cooldown_days, "legend")
    filtered = [
        t
        for t in candidates
        if _normalize_player_name(t.player) not in cooldown_players
        and t.topic_key not in cooldown_topic_keys
    ]
    if filtered:
        return filtered[0]
    if live and bucket and (cooldown_players or cooldown_topic_keys):
        LOG.warning("yt_shorts_legend_cooldown_exhausted: pick least-recently-used")
        last_offset = _recent_used_offsets(bucket, current, cooldown_days, "legend")
        never_used = cooldown_days + 1
        candidates.sort(
            key=lambda t: (
                -last_offset.get(_normalize_player_name(t.player), never_used),
                -t.priority,
                t.player,
            )
        )
    return candidates[0]


def _finish_run(
    *,
    topic,
    script: ShortsScript,
    rendered: RenderedShort,
    run_dir: Path,
    run_id: str,
    bucket: str,
    live: bool,
    dry_run: bool,
    send_mail: bool,
    youtube_private_upload: bool,
    current: datetime,
    date_key: str,
    fmt: str,
    youtube_tags: tuple[str, ...],
) -> ShortsRunResult:
    """upload → (YouTube private) → history → 承認mail → result。data/legend 共通。"""
    gcs_uri = ""
    signed_url = ""
    if live:
        gcs_uri, signed_url = _upload_artifacts(
            bucket_name=bucket,
            run_id=run_id,
            rendered=rendered,
            topic=topic,
            script=script,
        )

    youtube_result: YouTubeUploadResult | None = None
    youtube_publish_url = ""
    if live and youtube_private_upload:
        youtube_result = upload_private_video(
            rendered.video_path,
            title=script.title,
            description=script.description,
            tags=youtube_tags,
            category_id=os.environ.get("YT_SHORTS_YOUTUBE_CATEGORY_ID", "17").strip() or "17",
            privacy_status=os.environ.get("YT_SHORTS_YOUTUBE_INITIAL_PRIVACY", "private").strip()
            or "private",
        )
        youtube_publish_url = (
            build_yt_shorts_publish_url(youtube_result.video_id, _approval_base_url()) or ""
        )

    if live and bucket:
        _write_history(
            bucket,
            date_key,
            {
                "status": "youtube_private_uploaded" if youtube_result else "uploaded",
                "topic_key": topic.topic_key,
                "player": topic.player,
                "title": script.title,
                "gcs_uri": gcs_uri,
                "youtube_video_id": youtube_result.video_id if youtube_result else "",
                "youtube_watch_url": youtube_result.watch_url if youtube_result else "",
                "youtube_studio_url": youtube_result.studio_url if youtube_result else "",
                "signed_url_created_at": current.isoformat(),
                "mail_status": "",
                "tts_mode": rendered.tts_mode,
                "format": fmt,
            },
            fmt,
        )

    mail_status = ""
    if send_mail:
        mail_status = send_approval_mail(
            topic,
            script,
            signed_url=signed_url,
            gcs_uri=gcs_uri,
            youtube_watch_url=youtube_result.watch_url if youtube_result else "",
            youtube_studio_url=youtube_result.studio_url if youtube_result else "",
            youtube_publish_url=youtube_publish_url,
            youtube_video_id=youtube_result.video_id if youtube_result else "",
            dry_run=dry_run,
        )

    if live and bucket:
        _write_history(
            bucket,
            date_key,
            {
                "status": "sent"
                if mail_status == "sent"
                else ("youtube_private_uploaded" if youtube_result else "uploaded"),
                "topic_key": topic.topic_key,
                "player": topic.player,
                "title": script.title,
                "gcs_uri": gcs_uri,
                "youtube_video_id": youtube_result.video_id if youtube_result else "",
                "youtube_watch_url": youtube_result.watch_url if youtube_result else "",
                "youtube_studio_url": youtube_result.studio_url if youtube_result else "",
                "youtube_publish_url": youtube_publish_url,
                "youtube_upload_status": youtube_result.privacy_status if youtube_result else "",
                "signed_url_created_at": current.isoformat(),
                "mail_status": mail_status,
                "tts_mode": rendered.tts_mode,
                "format": fmt,
            },
            fmt,
        )

    return ShortsRunResult(
        status="ok",
        dry_run=dry_run,
        topic_key=topic.topic_key,
        title=script.title,
        output_dir=str(run_dir),
        video_path=str(rendered.video_path),
        gcs_uri=gcs_uri,
        signed_url=signed_url,
        mail_status=mail_status,
        tts_mode=rendered.tts_mode,
        youtube_video_id=youtube_result.video_id if youtube_result else "",
        youtube_watch_url=youtube_result.watch_url if youtube_result else "",
        youtube_studio_url=youtube_result.studio_url if youtube_result else "",
        youtube_publish_url=youtube_publish_url,
        youtube_upload_status=youtube_result.privacy_status if youtube_result else "",
    )


def run(
    *,
    live: bool = False,
    notable_data: Mapping[str, Any] | None = None,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    allow_silent_tts: bool = False,
    send_mail: bool = True,
    voicevox_base_url: str = "",
    speaker: int = 13,
    bucket_name: str = "",
    youtube_private_upload: bool = False,
    ignore_daily_cap: bool = False,
    exclude_players: list[str] | None = None,
    target_players: list[str] | None = None,
    now: datetime | None = None,
    ffmpeg_bin: str = "ffmpeg",
    fmt: str = "data",
    legend_entries: list[dict[str, Any]] | None = None,
) -> ShortsRunResult:
    dry_run = not live
    current = (now or _now_jst()).astimezone(JST)
    date_key = current.strftime("%Y-%m-%d")
    bucket = bucket_name or os.environ.get("YT_SHORTS_GCS_BUCKET") or os.environ.get("INSIGHT_GCS_BUCKET") or ""

    if live and not bucket:
        raise RuntimeError("YT_SHORTS_GCS_BUCKET or INSIGHT_GCS_BUCKET is required in live mode")

    history: dict[str, Any] | None = None
    if live and bucket:
        history = _load_history(bucket, date_key, fmt)
        if history and history.get("status") in {"uploaded", "youtube_private_uploaded", "sent"}:
            if not ignore_daily_cap:
                return ShortsRunResult(
                    status="skipped",
                    dry_run=dry_run,
                    topic_key=str(history.get("topic_key") or ""),
                    title=str(history.get("title") or ""),
                    gcs_uri=str(history.get("gcs_uri") or ""),
                    youtube_video_id=str(history.get("youtube_video_id") or ""),
                    youtube_watch_url=str(history.get("youtube_watch_url") or ""),
                    youtube_studio_url=str(history.get("youtube_studio_url") or ""),
                    reason="daily_cap_already_used",
                )
            LOG.warning(
                "yt_shorts_ignore_daily_cap date=%s previous_topic=%s",
                date_key,
                history.get("topic_key"),
            )

    if fmt == "legend":
        cooldown_days = _cooldown_days_env()
        if legend_entries is None:
            legend_entries = _load_legend_entries_from_repo()
        topic = _select_legend_topic(
            bucket=bucket,
            current=current,
            cooldown_days=cooldown_days,
            live=live,
            legend_entries=legend_entries,
        )
        if topic is None:
            if live and send_mail:
                _failure_mail(
                    "【YT Shorts失敗】レジェンド候補なし",
                    "巨人レジェンドの候補データがありません。",
                    dry_run=False,
                )
            return ShortsRunResult(status="no_topic", dry_run=dry_run, reason="empty_legend_data")
        from src.yt_shorts_legend import build_legend_script

        script = build_legend_script(topic)
        run_id = f"{date_key}-{_safe_id(topic.topic_key)}"
        run_dir = Path(output_dir) / run_id
        rendered = render_short(
            topic,
            script,
            run_dir,
            voicevox_base_url=voicevox_base_url or os.environ.get("VOICEVOX_BASE_URL", ""),
            speaker=speaker,
            allow_silent_tts=allow_silent_tts,
            ffmpeg_bin=ffmpeg_bin,
            fmt="legend",
        )
        return _finish_run(
            topic=topic,
            script=script,
            rendered=rendered,
            run_dir=run_dir,
            run_id=run_id,
            bucket=bucket,
            live=live,
            dry_run=dry_run,
            send_mail=send_mail,
            youtube_private_upload=youtube_private_upload,
            current=current,
            date_key=date_key,
            fmt="legend",
            youtube_tags=("巨人", "ジャイアンツ", "ヨシラバー", "巨人レジェンド", "shorts"),
        )

    excluded_players = {
        _normalize_player_name(name)
        for name in [*_split_csvish(os.environ.get(EXCLUDE_PLAYERS_ENV, "")), *(exclude_players or [])]
        if _normalize_player_name(name)
    }
    target_player_names = {
        _normalize_player_name(name)
        for name in [*_split_csvish(os.environ.get(TARGET_PLAYERS_ENV, "")), *(target_players or [])]
        if _normalize_player_name(name)
    }
    if notable_data is None:
        notable_limit = TARGET_PLAYER_NOTABLE_LIMIT if target_player_names else DEFAULT_NOTABLE_LIMIT
        data = dict(_load_notable_data_from_repo(limit=notable_limit))
    else:
        data = dict(notable_data)
    excluded_topic_keys: set[str] = set()
    if ignore_daily_cap and history:
        previous_topic_key = str(history.get("topic_key") or "").strip()
        if previous_topic_key:
            excluded_topic_keys.add(previous_topic_key)
    # 選手クールダウン: 直近 N 日に使った選手 / topic を除外し「同じ選手ばかり」を防ぐ。
    # target_players 明示時はユーザ意図優先でクールダウンを掛けない。
    cooldown_players: set[str] = set()
    cooldown_topic_keys: set[str] = set()
    cooldown_days = DEFAULT_PLAYER_COOLDOWN_DAYS
    if live and bucket and not target_player_names:
        try:
            cooldown_days = int(
                os.environ.get(PLAYER_COOLDOWN_DAYS_ENV, str(DEFAULT_PLAYER_COOLDOWN_DAYS))
            )
        except ValueError:
            cooldown_days = DEFAULT_PLAYER_COOLDOWN_DAYS
        cooldown_players, cooldown_topic_keys = _recent_used(bucket, current, cooldown_days)
        if cooldown_players or cooldown_topic_keys:
            LOG.info(
                "yt_shorts_player_cooldown days=%d recent_players=%d recent_topics=%d",
                cooldown_days, len(cooldown_players), len(cooldown_topic_keys),
            )
    base_data = dict(data)
    data = _without_excluded_topics(
        base_data,
        excluded_topic_keys | cooldown_topic_keys,
        excluded_players | cooldown_players,
        target_player_names,
    )
    topic = select_topic_from_notable_data(data, source_url=DEFAULT_SOURCE_URL)
    if topic is None and (cooldown_players or cooldown_topic_keys):
        # クールダウンで候補が全滅。「全解除して最上位を再選定」だと直近に使った
        # 選手をそのまま選び直して "毎回同じ選手" になるため、最も久しく使って
        # いない選手 (least-recently-used) を優先して選ぶ。
        LOG.warning("yt_shorts_cooldown_exhausted: pick least-recently-used player")
        fallback = _without_excluded_topics(
            base_data, excluded_topic_keys, excluded_players, target_player_names
        )
        candidates = list_topics_from_notable_data(fallback, source_url=DEFAULT_SOURCE_URL)
        if candidates:
            last_offset = _recent_used_offsets(bucket, current, cooldown_days)
            never_used = cooldown_days + 1  # 履歴に無い = 最も優先
            candidates.sort(
                key=lambda t: (
                    -last_offset.get(_normalize_player_name(t.player), never_used),
                    -t.priority,
                    t.player,
                    t.label,
                )
            )
            topic = candidates[0]
    if topic is None:
        if live and send_mail:
            _failure_mail("【YT Shorts失敗】候補なし", "YouTube Shorts の候補データがありません。", dry_run=False)
        return ShortsRunResult(status="no_topic", dry_run=dry_run, reason="empty_notable_data")
    topic = _with_player_image(topic)

    script = build_script(topic)
    run_id = f"{date_key}-{_safe_id(topic.topic_key)}"
    run_dir = Path(output_dir) / run_id
    rendered = render_short(
        topic,
        script,
        run_dir,
        voicevox_base_url=voicevox_base_url or os.environ.get("VOICEVOX_BASE_URL", ""),
        speaker=speaker,
        allow_silent_tts=allow_silent_tts,
        ffmpeg_bin=ffmpeg_bin,
    )

    return _finish_run(
        topic=topic,
        script=script,
        rendered=rendered,
        run_dir=run_dir,
        run_id=run_id,
        bucket=bucket,
        live=live,
        dry_run=dry_run,
        send_mail=send_mail,
        youtube_private_upload=youtube_private_upload,
        current=current,
        date_key=date_key,
        fmt="data",
        youtube_tags=("巨人", "ジャイアンツ", "ヨシラバー", "shorts"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one yoshilover YouTube Shorts candidate.")
    parser.add_argument("--live", action="store_true", help="Upload to GCS and send a real approval mail.")
    parser.add_argument("--topic-json", help="Use a notable-data JSON fixture instead of live repo data.")
    parser.add_argument("--topic-json-inline", help="Use a notable-data JSON object string instead of live repo data.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--allow-silent-tts", action="store_true", default=_env_flag("YT_SHORTS_ALLOW_SILENT_TTS"))
    parser.add_argument("--no-mail", action="store_true", help="Generate/upload without sending approval mail.")
    parser.add_argument("--voicevox-url", default=os.environ.get("VOICEVOX_BASE_URL", ""))
    parser.add_argument("--speaker", type=int, default=int(os.environ.get("YT_SHORTS_VOICEVOX_SPEAKER", "13") or 13))
    parser.add_argument("--bucket", default=os.environ.get("YT_SHORTS_GCS_BUCKET", ""))
    parser.add_argument("--ffmpeg-bin", default=os.environ.get("YT_SHORTS_FFMPEG_BIN", "ffmpeg"))
    parser.add_argument(
        "--ignore-daily-cap",
        action="store_true",
        default=_env_flag("YT_SHORTS_IGNORE_DAILY_CAP"),
        help="In live mode, allow an extra same-day video and exclude the previous same-day topic.",
    )
    parser.add_argument(
        "--exclude-player",
        action="append",
        default=[],
        help="Exclude a player from one-off topic selection. Repeat or comma-separate names.",
    )
    parser.add_argument(
        "--player",
        action="append",
        default=[],
        help="Target a player for one-off topic selection. Repeat or comma-separate names.",
    )
    parser.add_argument(
        "--youtube-private-upload",
        action="store_true",
        default=_env_flag("YT_SHORTS_YOUTUBE_PRIVATE_UPLOAD"),
        help="In live mode, upload the MP4 to YouTube as private before sending approval mail.",
    )
    parser.add_argument(
        "--format",
        choices=["data", "legend", "both"],
        default=(os.environ.get("YT_SHORTS_FORMAT", "data") or "data"),
        help="Which Shorts format(s) to generate. 'both' = data + 巨人レジェンド記録室.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.topic_json and args.topic_json_inline:
        parser.error("--topic-json and --topic-json-inline are mutually exclusive")
    notable_data = (
        _load_notable_data_from_json_inline(args.topic_json_inline)
        if args.topic_json_inline
        else (_load_notable_data_from_json(args.topic_json) if args.topic_json else None)
    )
    formats = ["data", "legend"] if args.format == "both" else [args.format]
    single = len(formats) == 1
    results: list[dict[str, Any]] = []
    exit_code = 0
    ok_states = {"ok", "skipped", "no_topic"}
    for fmt in formats:
        try:
            result = run(
                live=args.live,
                notable_data=notable_data if fmt == "data" else None,
                output_dir=args.output_dir,
                allow_silent_tts=args.allow_silent_tts,
                send_mail=not args.no_mail,
                voicevox_base_url=args.voicevox_url,
                speaker=args.speaker,
                bucket_name=args.bucket,
                youtube_private_upload=args.youtube_private_upload,
                ignore_daily_cap=args.ignore_daily_cap,
                exclude_players=[name for raw in args.exclude_player for name in _split_csvish(raw)],
                target_players=[name for raw in args.player for name in _split_csvish(raw)],
                ffmpeg_bin=args.ffmpeg_bin,
                fmt=fmt,
            )
        except Exception as exc:  # noqa: BLE001
            if args.live and not args.no_mail:
                try:
                    _failure_mail(
                        "【YT Shorts失敗】生成エラー",
                        f"YouTube Shorts ({fmt}) 生成に失敗しました。\n\nerror={exc!r}",
                        dry_run=False,
                    )
                except Exception:
                    pass
            if single:
                print(json.dumps({"status": "error", "error": repr(exc)}, ensure_ascii=False), file=sys.stderr)
                return 1
            results.append({"format": fmt, "status": "error", "error": repr(exc)})
            exit_code = 1
            continue

        if single:
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            return 0 if result.status in ok_states else 1
        results.append({"format": fmt, **asdict(result)})
        if result.status not in ok_states:
            exit_code = 1

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ShortsRunResult",
    "run",
    "send_approval_mail",
    "main",
]
