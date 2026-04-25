from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BackupError(RuntimeError):
    pass


def _title_variants(post: dict[str, Any]) -> str:
    title = (post or {}).get("title")
    if isinstance(title, dict):
        return str(title.get("raw") or title.get("rendered") or "")
    if isinstance(title, str):
        return title
    return ""


def _content_variants(post: dict[str, Any]) -> tuple[str, str]:
    content = (post or {}).get("content")
    if isinstance(content, dict):
        return (
            str(content.get("raw") or ""),
            str(content.get("rendered") or ""),
        )
    if isinstance(content, str):
        return content, content
    return "", ""


def _timestamp_for_filename(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def create_backup(
    post: dict[str, Any],
    backup_dir: str | Path,
    *,
    now: datetime | None = None,
) -> Path:
    current_time = now or datetime.now(timezone.utc)
    backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)
    post_id = int((post or {}).get("id"))
    filename = f"{post_id}_{_timestamp_for_filename(current_time)}.json"
    destination = backup_root / filename
    temp_path = destination.with_name(f"{destination.name}.tmp")
    content_raw, content_rendered = _content_variants(post)
    payload: dict[str, Any] = {
        "post_id": post_id,
        "fetched_at": current_time.astimezone(timezone.utc).isoformat(),
        "title": _title_variants(post),
        "content_raw": content_raw,
        "content_rendered": content_rendered,
        "modified": str((post or {}).get("modified") or ""),
        "status": str((post or {}).get("status") or ""),
    }
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temp_path, destination)
    except Exception as exc:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise BackupError(f"failed to write backup: {destination}") from exc
    return destination
