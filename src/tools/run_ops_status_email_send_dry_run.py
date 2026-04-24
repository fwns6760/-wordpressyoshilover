"""Dry-run CLI for ticket 075 ops status email adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

if __package__ in {None, ""}:  # pragma: no cover - direct script execution support
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src.ops_status_email_sender import (  # noqa: E402
    OpsStatusEmailRequest,
    OpsStatusEmailResult,
    send,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one ops status digest mail in dry-run by default.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot-path", help="Path to snapshot JSON.")
    source.add_argument("--stdin", action="store_true", help="Read snapshot JSON from stdin.")
    parser.add_argument("--body-html-path", help="Optional path to HTML body.")
    parser.add_argument("--subject-datetime", help="Override subject datetime in JST.")
    parser.add_argument("--to", help="Override recipients as comma-separated email addresses.")
    parser.add_argument("--strict", action="store_true", help="Reject forbidden fields instead of redacting them.")
    parser.add_argument("--send", action="store_true", help="Actually send mail. Default is dry-run.")
    return parser.parse_args(argv)


def _parse_override_recipients(value: str | None) -> list[str] | None:
    if value is None:
        return None
    recipients = [item.strip() for item in value.split(",") if item.strip()]
    return recipients or []


def _read_snapshot_from_stdin() -> dict[str, Any]:
    payload = json.loads(sys.stdin.read())
    if not isinstance(payload, dict):
        raise TypeError("snapshot must be a JSON object")
    return payload


def _read_snapshot_from_path(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("snapshot must be a JSON object")
    return payload


def _read_optional_body_html(path: str | None) -> str | None:
    if path is None:
        return None
    return Path(path).read_text(encoding="utf-8")


def _request_line(
    *,
    source: str,
    body_html_path: str | None,
    subject_datetime: str | None,
    override_recipients: list[str] | None,
    strict: bool,
) -> str:
    body_html = "yes" if body_html_path else "no"
    subject_override = subject_datetime if subject_datetime else "none"
    to_override = override_recipients if override_recipients is not None else "none"
    return (
        f"[request] source={source} body_html={body_html} "
        f"subject_override={subject_override} to_override={to_override} "
        f"strict={'true' if strict else 'false'}"
    )


def _subject_line(result: OpsStatusEmailResult | None) -> str:
    if result is None or result.subject is None:
        return "[subject] <skipped>"
    return f"[subject] {result.subject!r}"


def _result_line(result: OpsStatusEmailResult) -> str:
    return f"[result] status={result.status} reason={result.reason} recipients={result.recipients}"


def _body_preview_line(result: OpsStatusEmailResult | None) -> str:
    if result is None or not result.body_text_preview:
        return "[body_preview] <skipped>"
    preview = result.body_text_preview.replace("\n", "\\n")
    return f"[body_preview] {preview}"


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        override_recipients = _parse_override_recipients(args.to)
        source = "stdin" if args.stdin else str(args.snapshot_path)
        print(
            _request_line(
                source=source,
                body_html_path=args.body_html_path,
                subject_datetime=args.subject_datetime,
                override_recipients=override_recipients,
                strict=args.strict,
            )
        )

        body_html = _read_optional_body_html(args.body_html_path)
        if args.stdin:
            try:
                snapshot = _read_snapshot_from_stdin()
            except (json.JSONDecodeError, TypeError):
                result = OpsStatusEmailResult(
                    status="suppressed",
                    reason="INVALID_SNAPSHOT",
                    subject=None,
                    recipients=[],
                    body_text_preview=None,
                    bridge_result=None,
                )
                print(_subject_line(result))
                print(_result_line(result))
                print(_body_preview_line(result))
                return 0
        else:
            snapshot_path = Path(args.snapshot_path)
            if not snapshot_path.exists():
                result = OpsStatusEmailResult(
                    status="suppressed",
                    reason="MISSING_SNAPSHOT",
                    subject=None,
                    recipients=[],
                    body_text_preview=None,
                    bridge_result=None,
                )
                print(_subject_line(result))
                print(_result_line(result))
                print(_body_preview_line(result))
                return 0
            try:
                snapshot = _read_snapshot_from_path(str(snapshot_path))
            except (json.JSONDecodeError, TypeError):
                result = OpsStatusEmailResult(
                    status="suppressed",
                    reason="INVALID_SNAPSHOT",
                    subject=None,
                    recipients=[],
                    body_text_preview=None,
                    bridge_result=None,
                )
                print(_subject_line(result))
                print(_result_line(result))
                print(_body_preview_line(result))
                return 0

        request = OpsStatusEmailRequest(
            snapshot=snapshot,
            body_html=body_html,
            override_subject_datetime=args.subject_datetime,
            override_recipient=override_recipients,
            strict=args.strict,
        )
        result = send(request, dry_run=not args.send)
        print(_subject_line(result))
        print(_result_line(result))
        print(_body_preview_line(result))
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[result] status=error error_type={type(exc).__name__} message={exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
