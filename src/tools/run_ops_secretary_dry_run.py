"""Dry-run CLI for ticket 070 ops secretary status digest content."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.ops_secretary_status import format_digest_human, format_digest_json, render_ops_status_digest


def _load_fixture(path: str | None, *, from_stdin: bool) -> dict[str, Any]:
    if from_stdin:
        payload = json.loads(sys.stdin.read())
    elif path is not None:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        raise ValueError("--fixture or --stdin is required")
    if not isinstance(payload, dict):
        raise ValueError("fixture must be a JSON object")
    return dict(payload)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render one ops secretary status digest body without sending mail.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="Path to JSON fixture.")
    source.add_argument("--stdin", action="store_true", help="Read JSON fixture from stdin.")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    parser.add_argument("--strict", action="store_true", help="Reject forbidden fields instead of redacting them.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    snapshot = _load_fixture(args.fixture, from_stdin=args.stdin)
    digest = render_ops_status_digest(snapshot, strict=args.strict)
    if args.format == "json":
        print(json.dumps(format_digest_json(digest), ensure_ascii=False, indent=2))
    else:
        print(format_digest_human(digest))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
