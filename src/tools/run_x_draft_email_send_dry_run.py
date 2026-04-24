"""Dry-run CLI for ticket 074 X draft digest email adapter."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

if __package__ in {None, ""}:  # pragma: no cover - direct script execution support
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src.x_draft_email_sender import (  # noqa: E402
    XDraftEmailRequest,
    XDraftEmailResult,
    count_items,
    send,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one X draft digest mail in dry-run by default.")
    parser.add_argument("--body-text-path", required=True, help="Path to X draft body text.")
    parser.add_argument("--body-html-path", help="Optional path to X draft HTML body.")
    parser.add_argument("--subject-datetime", help="Override subject datetime in JST.")
    parser.add_argument("--item-count", type=int, help="Override detected digest item count.")
    parser.add_argument("--to", help="Override recipients as comma-separated email addresses.")
    parser.add_argument("--send", action="store_true", help="Actually send mail. Default is dry-run.")
    return parser.parse_args(argv)


def _parse_override_recipients(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _request_line(
    *,
    body_text_path: str,
    body_text_len: int,
    body_html_path: str | None,
    subject_datetime: str | None,
    item_count_override: int | None,
    override_recipients: list[str] | None,
) -> str:
    body_html = "yes" if body_html_path else "no"
    subject_override = subject_datetime if subject_datetime else "none"
    item_count_text = item_count_override if item_count_override is not None else "none"
    to_override = override_recipients if override_recipients is not None else "none"
    return (
        f"[request] body_text_path={body_text_path!r} body_text_len={body_text_len} "
        f"body_html={body_html} subject_override={subject_override} "
        f"item_count_override={item_count_text} to_override={to_override}"
    )


def _subject_line(result: XDraftEmailResult) -> str:
    if result.status == "suppressed" or result.subject is None:
        return "[subject] <skipped>"
    return f"[subject] {result.subject!r}"


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        try:
            body_text = Path(args.body_text_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            body_text = ""
        if args.body_html_path:
            Path(args.body_html_path).read_text(encoding="utf-8")
        override_recipients = _parse_override_recipients(args.to)
        request = XDraftEmailRequest(
            body_text_path=args.body_text_path,
            body_html_path=args.body_html_path,
            override_subject_datetime=args.subject_datetime,
            override_recipient=override_recipients,
            item_count_override=args.item_count,
        )
        print(
            _request_line(
                body_text_path=request.body_text_path,
                body_text_len=len(body_text),
                body_html_path=request.body_html_path,
                subject_datetime=request.override_subject_datetime,
                item_count_override=request.item_count_override,
                override_recipients=override_recipients,
            )
        )
        inferred_item_count = request.item_count_override if request.item_count_override is not None else count_items(body_text)
        print(f"[item_count] {max(inferred_item_count, 0)}")
        result = send(request, dry_run=not args.send)
        print(_subject_line(result))
        print(
            f"[result] status={result.status} reason={result.reason} "
            f"recipients={result.recipients} item_count={result.item_count}"
        )
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[result] status=error error_type={type(exc).__name__} message={exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
