"""Dry-run CLI for ticket 073 morning analyst digest email adapter."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

if __package__ in {None, ""}:  # pragma: no cover - direct script execution support
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src.morning_analyst_email_sender import (  # noqa: E402
    AnalystEmailRequest,
    AnalystEmailResult,
    build_subject,
    load_digest_meta,
    send,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one morning analyst digest mail in dry-run by default.")
    parser.add_argument("--digest-path", required=True, help="Path to analyst digest JSON.")
    parser.add_argument("--body-text-path", required=True, help="Path to analyst text body.")
    parser.add_argument("--body-html-path", help="Optional path to analyst HTML body.")
    parser.add_argument("--subject-date", help="Override digest window.latest_date in the subject.")
    parser.add_argument("--to", help="Override recipients as comma-separated email addresses.")
    parser.add_argument("--send", action="store_true", help="Actually send mail. Default is dry-run.")
    return parser.parse_args(argv)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _parse_override_recipients(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _request_line(
    *,
    digest_path: str,
    body_text_len: int,
    body_html_path: str | None,
    subject_date: str | None,
    override_recipients: list[str] | None,
) -> str:
    body_html = "yes" if body_html_path else "no"
    subject_override = subject_date if subject_date else "none"
    to_override = override_recipients if override_recipients is not None else "none"
    return (
        f"[request] digest_path={digest_path!r} body_text_len={body_text_len} "
        f"body_html={body_html} subject_date_override={subject_override} "
        f"to_override={to_override}"
    )


def _meta_line(digest_path: str) -> str:
    try:
        meta = load_digest_meta(digest_path)
    except (FileNotFoundError, ValueError, KeyError):
        return "[meta] <skipped>"
    return (
        f"[meta] latest_date={meta.latest_date!r} comparison_ready={_bool_text(meta.comparison_ready)} "
        f"status={meta.status!r}"
    )


def _subject_line(request: AnalystEmailRequest, result: AnalystEmailResult) -> str:
    if result.status == "suppressed" or result.subject is None:
        return "[subject] <skipped>"
    meta = load_digest_meta(request.digest_json_path)
    subject = build_subject(meta, request.override_subject_date)
    return f"[subject] {subject!r}"


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        body_text = Path(args.body_text_path).read_text(encoding="utf-8")
        if args.body_html_path:
            Path(args.body_html_path).read_text(encoding="utf-8")
        override_recipients = _parse_override_recipients(args.to)
        request = AnalystEmailRequest(
            digest_json_path=args.digest_path,
            body_text_path=args.body_text_path,
            body_html_path=args.body_html_path,
            override_subject_date=args.subject_date,
            override_recipient=override_recipients,
        )
        print(
            _request_line(
                digest_path=request.digest_json_path,
                body_text_len=len(body_text),
                body_html_path=request.body_html_path,
                subject_date=args.subject_date,
                override_recipients=override_recipients,
            )
        )
        print(_meta_line(request.digest_json_path))
        result = send(request, dry_run=not args.send)
        print(_subject_line(request, result))
        print(f"[result] status={result.status} reason={result.reason} recipients={result.recipients}")
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[result] status=error error_type={type(exc).__name__} message={exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
