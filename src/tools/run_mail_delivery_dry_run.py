"""Dry-run CLI for the shared mail delivery bridge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from src.mail_delivery_bridge import MailRequest, send


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build one mail delivery request and send in dry-run by default.")
    parser.add_argument("--to", action="append", required=True, help="Recipient email address. Repeatable.")
    parser.add_argument("--subject", required=True, help="Mail subject.")
    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body-text", help="Plain text body.")
    body_group.add_argument("--body-text-path", help="Path to UTF-8 text body.")
    parser.add_argument("--body-html-path", help="Path to UTF-8 HTML body.")
    parser.add_argument("--sender", help="Optional From header override.")
    parser.add_argument("--reply-to", help="Optional Reply-To header.")
    parser.add_argument("--send", action="store_true", help="Actually send mail. Default is dry-run.")
    return parser.parse_args(argv)


def _read_optional_path(path: str | None) -> str | None:
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8")


def _body_text_from_args(args: argparse.Namespace) -> str:
    if args.body_text_path:
        return Path(args.body_text_path).read_text(encoding="utf-8")
    return args.body_text or ""


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        text_body = _body_text_from_args(args)
        html_body = _read_optional_path(args.body_html_path)
        request = MailRequest(
            to=list(args.to),
            subject=args.subject,
            text_body=text_body,
            html_body=html_body,
            sender=args.sender,
            reply_to=args.reply_to,
        )
        has_html = "yes" if html_body and html_body.strip() else "no"
        print(
            f"[request] to={request.to!r} subject={request.subject!r} "
            f"body_text_len={len(request.text_body)} has_html={has_html}"
        )
        result = send(request, dry_run=not args.send)
        print(f"[result] status={result.status} reason={result.reason}")
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[result] status=error error_type={type(exc).__name__} message={exc}")
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
