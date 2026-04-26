"""Dry-run smoke CLI for ticket 173 X-post queue + ledger schema."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.x_post_queue_ledger import (
    JST,
    JsonlLedgerWriter,
    JsonlQueueWriter,
    QUEUE_STATUS_EXPIRED,
    QUEUE_STATUS_QUEUED,
    QUEUE_STATUS_SKIPPED_DAILY_CAP,
    QUEUE_STATUS_SKIPPED_DUPLICATE,
    XPostQueueEntry,
    compute_candidate_hash,
    default_ttl_seconds,
    judge_daily_cap,
    judge_dedup,
    judge_ttl_expired,
)


ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
DEFAULT_QUEUE_PATH = ROOT / "logs" / "x_post_queue.jsonl"
DEFAULT_LEDGER_PATH = ROOT / "logs" / "x_post_ledger.jsonl"
DEFAULT_LIMIT = 5
DEFAULT_DAILY_CAP = 10
MAX_TEXT_LENGTH = 140


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run X-post queue smoke using guarded publish history only.")
    parser.add_argument("--dry-run", action="store_true", help="Required. This CLI never writes queue entries.")
    parser.add_argument("--history-path", default=str(DEFAULT_HISTORY_PATH))
    parser.add_argument("--queue-path", default=str(DEFAULT_QUEUE_PATH))
    parser.add_argument("--ledger-path", default=str(DEFAULT_LEDGER_PATH))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--daily-cap", type=int, default=DEFAULT_DAILY_CAP)
    parser.add_argument("--account-id", default="main")
    parser.add_argument("--breaking-excluded", action="store_true")
    parser.add_argument("--now-iso")
    return parser.parse_args(argv)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"history row must be an object: {target}:{line_no}")
            rows.append(payload)
    return rows


def _extract_rendered(value: Any) -> str:
    if isinstance(value, dict):
        rendered = value.get("rendered")
        if rendered is not None:
            return str(rendered)
    if value is None:
        return ""
    return str(value)


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _strip_html(value: str) -> str:
    text = str(value or "")
    for token in ("<br>", "<br/>", "<br />", "</p>", "</div>", "</li>", "</h2>", "</h3>"):
        text = text.replace(token, "\n")
    text = __import__("re").sub(r"<[^>]+>", " ", text)
    return _normalize_text(text)


def _load_backup_post(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"backup file not found: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"backup payload must be an object: {target}")
    return payload


def _infer_category(post: dict[str, Any]) -> str:
    meta = post.get("meta")
    subtype = ""
    if isinstance(meta, dict):
        subtype = str(meta.get("article_subtype") or meta.get("subtype") or "")
    subtype = subtype.strip().lower()
    if subtype.startswith("lineup"):
        return "lineup"
    if subtype.startswith("postgame"):
        return "postgame"
    if "comment" in subtype:
        return "comment"
    if "breaking" in subtype:
        return "breaking"
    if subtype in {"notice", "comment"}:
        return subtype
    title = _extract_rendered(post.get("title"))
    if "速報" in title:
        return "breaking"
    return "notice"


def _build_post_text(title: str, canonical_url: str) -> str:
    normalized_title = _normalize_text(title)
    base = f"{normalized_title}\n{canonical_url}".strip()
    if len(base) <= MAX_TEXT_LENGTH:
        return base
    body_budget = max(MAX_TEXT_LENGTH - len(canonical_url) - 1, 0)
    trimmed_title = normalized_title[:body_budget].rstrip()
    return f"{trimmed_title}\n{canonical_url}".strip()


def _build_body_excerpt(post: dict[str, Any]) -> str:
    excerpt = _extract_rendered(post.get("excerpt"))
    content = _extract_rendered(post.get("content"))
    first = _strip_html(excerpt) or _strip_html(content)
    return first[:240]


def _queue_entry_from_history(
    history_row: dict[str, Any],
    *,
    account_id: str,
    now_iso: str,
) -> XPostQueueEntry:
    backup = _load_backup_post(history_row["backup_path"])
    post_id = backup.get("id") or history_row.get("post_id") or ""
    canonical_url = str(backup.get("link") or f"https://yoshilover.com/?p={post_id}")
    title = _extract_rendered(backup.get("title")) or f"post-{post_id}"
    category = _infer_category(backup)
    body_excerpt = _build_body_excerpt(backup)
    candidate_hash = compute_candidate_hash(post_id, canonical_url, body_excerpt)
    source_time = history_row.get("ts") or now_iso
    ttl_seconds = default_ttl_seconds(category)
    ttl = (
        datetime.fromisoformat(str(source_time).replace("Z", "+00:00")).astimezone(JST).timestamp() + ttl_seconds
    )
    ttl_iso = datetime.fromtimestamp(ttl, JST).isoformat()
    return XPostQueueEntry(
        queue_id=str(uuid4()),
        candidate_hash=candidate_hash,
        source_post_id=post_id,
        source_canonical_url=canonical_url,
        title=title,
        post_text=_build_post_text(title, canonical_url),
        post_category=category,
        media_urls=(),
        account_id=account_id,
        ttl=ttl_iso,
        status=QUEUE_STATUS_QUEUED,
        queued_at=now_iso,
        scheduled_at=now_iso,
        posted_at=None,
        x_post_id=None,
        retry_count=0,
        last_error_code=None,
        last_error_message=None,
    )


def _history_candidates(history_rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    sent_rows = [row for row in history_rows if str(row.get("status") or "") == "sent" and row.get("backup_path")]
    return sent_rows[-max(int(limit), 0) :]


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if not args.dry_run:
            print("error: only --dry-run is supported for ticket 173", file=sys.stderr)
            return 2

        now_dt = datetime.fromisoformat(args.now_iso.replace("Z", "+00:00")).astimezone(JST) if args.now_iso else datetime.now(JST)
        now_iso = now_dt.isoformat()
        history_rows = _read_jsonl(args.history_path)
        queue_writer = JsonlQueueWriter(args.queue_path)
        ledger_writer = JsonlLedgerWriter(args.ledger_path)

        items: list[dict[str, Any]] = []
        for history_row in _history_candidates(history_rows, args.limit):
            entry = _queue_entry_from_history(history_row, account_id=args.account_id, now_iso=now_iso)
            dedup = judge_dedup(queue_writer, ledger_writer, entry.idempotency_key)
            daily_cap = judge_daily_cap(
                ledger_writer,
                entry.account_id,
                args.daily_cap,
                args.breaking_excluded,
                category=entry.post_category,
                now=now_dt,
            )
            ttl_expired = judge_ttl_expired(entry, now_dt)

            status = QUEUE_STATUS_QUEUED
            if dedup == "duplicate":
                status = QUEUE_STATUS_SKIPPED_DUPLICATE
            elif daily_cap == QUEUE_STATUS_SKIPPED_DAILY_CAP:
                status = QUEUE_STATUS_SKIPPED_DAILY_CAP
            elif ttl_expired:
                status = QUEUE_STATUS_EXPIRED

            items.append(
                {
                    "source_post_id": entry.source_post_id,
                    "status": status,
                    "dedup_judgment": dedup,
                    "daily_cap_judgment": daily_cap,
                    "ttl_expired": ttl_expired,
                    "entry": {**entry.to_dict(), "status": status},
                }
            )

        print(
            json.dumps(
                {
                    "dry_run": True,
                    "history_path": str(args.history_path),
                    "queue_path": str(args.queue_path),
                    "ledger_path": str(args.ledger_path),
                    "items": items,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except (OSError, ValueError, json.JSONDecodeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
