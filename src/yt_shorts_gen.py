"""Orchestrator for YouTube Shorts Phase 1.

Default execution is dry-run.  Use ``--live`` to upload the generated MP4 to
GCS and send the approval mail.  The live path still does not upload to
YouTube; Phase 1 keeps publication manual.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import html
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping

from src.mail_delivery_bridge import MailRequest, send as bridge_send
from src.yt_shorts_render import RenderedShort, render_short
from src.yt_shorts_script import ShortsScript, build_script
from src.yt_shorts_topic import DEFAULT_SOURCE_URL, ShortsTopic, select_topic_from_notable_data


JST = timezone(timedelta(hours=9))
DEFAULT_OUTPUT_DIR = Path("/tmp/yt_shorts")
DEFAULT_BUCKET_PREFIX = "yt_shorts"


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


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_recipients(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\s]+", value or "") if part.strip()]


def _mail_recipients() -> list[str]:
    return (
        _split_recipients(os.environ.get("YT_SHORTS_MAIL_TO", ""))
        or _split_recipients(os.environ.get("MAIL_BRIDGE_TO", ""))
        or _split_recipients(os.environ.get("FACT_CHECK_EMAIL_TO", ""))
        or ["fwns6760@gmail.com"]
    )


def _now_jst() -> datetime:
    return datetime.now(JST)


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "-", value).strip("-")
    return cleaned[:96] or "short"


def _load_notable_data_from_repo(limit: int = 16) -> dict[str, Any]:
    # Import lazily because data_site_publisher has a broad dependency surface.
    from src.data_site_publisher import _build_notable_data_from_targets

    data = _build_notable_data_from_targets(limit=limit)
    return dict(data or {})


def _load_notable_data_from_json(path: Path | str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("topic JSON must be an object")
    return data


def _gcs_client():
    from google.cloud import storage

    return storage.Client()


def _history_blob_name(date_key: str) -> str:
    return f"{DEFAULT_BUCKET_PREFIX}/history/{date_key}.json"


def _load_history(bucket_name: str, date_key: str) -> dict[str, Any] | None:
    if not bucket_name:
        return None
    try:
        bucket = _gcs_client().bucket(bucket_name)
        blob = bucket.blob(_history_blob_name(date_key))
        if not blob.exists():
            return None
        payload = blob.download_as_text(encoding="utf-8")
        data = json.loads(payload)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_history(bucket_name: str, date_key: str, payload: Mapping[str, Any]) -> None:
    if not bucket_name:
        return
    bucket = _gcs_client().bucket(bucket_name)
    blob = bucket.blob(_history_blob_name(date_key))
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

    signed_url = video_blob.generate_signed_url(
        version="v4",
        expiration=timedelta(days=7),
        method="GET",
    )
    return f"gs://{bucket_name}/{video_blob.name}", signed_url


def _mail_bodies(topic: ShortsTopic, script: ShortsScript, *, signed_url: str, gcs_uri: str) -> tuple[str, str]:
    source_json = json.dumps(topic.raw_item, ensure_ascii=False, indent=2)
    text = (
        "YouTube Shorts 承認待ち\n\n"
        f"タイトル: {script.title}\n"
        f"動画URL: {signed_url or '(dry-run / no upload)'}\n"
        f"GCS: {gcs_uri or '(dry-run / no upload)'}\n"
        f"元データ: {topic.source_url}\n\n"
        "台本:\n"
        f"{script.narration}\n\n"
        "概要欄:\n"
        f"{script.description}\n\n"
        "元データJSON:\n"
        f"{source_json}\n"
    )
    html_body = (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;line-height:1.7;">'
        '<h1 style="font-size:20px;margin:0 0 12px;">YouTube Shorts 承認待ち</h1>'
        f'<p><strong>タイトル:</strong> {html.escape(script.title)}</p>'
        f'<p><a href="{html.escape(signed_url)}" '
        'style="display:inline-block;background:#ff7a1a;color:#fff;padding:10px 14px;'
        'border-radius:6px;text-decoration:none;font-weight:700;">MP4を開く</a></p>'
        f'<p style="font-size:13px;color:#666;">GCS: {html.escape(gcs_uri or "(dry-run / no upload)")}</p>'
        f'<p style="font-size:13px;color:#666;">元データ: <a href="{html.escape(topic.source_url)}">{html.escape(topic.source_url)}</a></p>'
        '<h2 style="font-size:16px;margin-top:18px;">台本</h2>'
        f'<pre style="white-space:pre-wrap;background:#fafafa;border:1px solid #eee;padding:12px;">{html.escape(script.narration)}</pre>'
        '<h2 style="font-size:16px;margin-top:18px;">概要欄</h2>'
        f'<pre style="white-space:pre-wrap;background:#fafafa;border:1px solid #eee;padding:12px;">{html.escape(script.description)}</pre>'
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
    dry_run: bool,
) -> str:
    text, html_body = _mail_bodies(topic, script, signed_url=signed_url, gcs_uri=gcs_uri)
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
    now: datetime | None = None,
    ffmpeg_bin: str = "ffmpeg",
) -> ShortsRunResult:
    dry_run = not live
    current = (now or _now_jst()).astimezone(JST)
    date_key = current.strftime("%Y-%m-%d")
    bucket = bucket_name or os.environ.get("YT_SHORTS_GCS_BUCKET") or os.environ.get("INSIGHT_GCS_BUCKET") or ""

    if live and not bucket:
        raise RuntimeError("YT_SHORTS_GCS_BUCKET or INSIGHT_GCS_BUCKET is required in live mode")

    if live and bucket:
        history = _load_history(bucket, date_key)
        if history and history.get("status") in {"uploaded", "sent"}:
            return ShortsRunResult(
                status="skipped",
                dry_run=dry_run,
                topic_key=str(history.get("topic_key") or ""),
                title=str(history.get("title") or ""),
                gcs_uri=str(history.get("gcs_uri") or ""),
                reason="daily_cap_already_used",
            )

    data = dict(notable_data or _load_notable_data_from_repo())
    topic = select_topic_from_notable_data(data, source_url=DEFAULT_SOURCE_URL)
    if topic is None:
        if live and send_mail:
            _failure_mail("【YT Shorts失敗】候補なし", "YouTube Shorts の候補データがありません。", dry_run=False)
        return ShortsRunResult(status="no_topic", dry_run=dry_run, reason="empty_notable_data")

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
        if bucket:
            _write_history(
                bucket,
                date_key,
                {
                    "status": "uploaded",
                    "topic_key": topic.topic_key,
                    "title": script.title,
                    "gcs_uri": gcs_uri,
                    "signed_url_created_at": current.isoformat(),
                    "mail_status": "",
                    "tts_mode": rendered.tts_mode,
                },
            )

    mail_status = ""
    if send_mail:
        mail_status = send_approval_mail(
            topic,
            script,
            signed_url=signed_url,
            gcs_uri=gcs_uri,
            dry_run=dry_run,
        )

    if live and bucket:
        _write_history(
            bucket,
            date_key,
            {
                "status": "sent" if mail_status == "sent" else "uploaded",
                "topic_key": topic.topic_key,
                "title": script.title,
                "gcs_uri": gcs_uri,
                "signed_url_created_at": current.isoformat(),
                "mail_status": mail_status,
                "tts_mode": rendered.tts_mode,
            },
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
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one yoshilover YouTube Shorts candidate.")
    parser.add_argument("--live", action="store_true", help="Upload to GCS and send a real approval mail.")
    parser.add_argument("--topic-json", help="Use a notable-data JSON fixture instead of live repo data.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--allow-silent-tts", action="store_true", default=_env_flag("YT_SHORTS_ALLOW_SILENT_TTS"))
    parser.add_argument("--no-mail", action="store_true", help="Generate/upload without sending approval mail.")
    parser.add_argument("--voicevox-url", default=os.environ.get("VOICEVOX_BASE_URL", ""))
    parser.add_argument("--speaker", type=int, default=int(os.environ.get("YT_SHORTS_VOICEVOX_SPEAKER", "13") or 13))
    parser.add_argument("--bucket", default=os.environ.get("YT_SHORTS_GCS_BUCKET", ""))
    parser.add_argument("--ffmpeg-bin", default=os.environ.get("YT_SHORTS_FFMPEG_BIN", "ffmpeg"))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    notable_data = _load_notable_data_from_json(args.topic_json) if args.topic_json else None
    try:
        result = run(
            live=args.live,
            notable_data=notable_data,
            output_dir=args.output_dir,
            allow_silent_tts=args.allow_silent_tts,
            send_mail=not args.no_mail,
            voicevox_base_url=args.voicevox_url,
            speaker=args.speaker,
            bucket_name=args.bucket,
            ffmpeg_bin=args.ffmpeg_bin,
        )
    except Exception as exc:  # noqa: BLE001
        if args.live and not args.no_mail:
            try:
                _failure_mail(
                    "【YT Shorts失敗】生成エラー",
                    f"YouTube Shorts 生成に失敗しました。\n\nerror={exc!r}",
                    dry_run=False,
                )
            except Exception:
                pass
        print(json.dumps({"status": "error", "error": repr(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status in {"ok", "skipped", "no_topic"} else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ShortsRunResult",
    "run",
    "send_approval_mail",
    "main",
]
