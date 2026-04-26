"""CLI for building and optionally sending one X dry-run mail digest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

if __package__ in {None, ""}:  # pragma: no cover - direct script execution support
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src.wp_client import WPClient  # noqa: E402
from src.x_dry_run_mail_builder import (  # noqa: E402
    DEFAULT_LIMIT,
    XDryRunMailBuild,
    XDryRunMailSendResult,
    build_x_dry_run_mail,
    send_x_dry_run_mail,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build X dry-run mail for recent published posts.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of recent published posts to inspect.")
    parser.add_argument(
        "--live-mail",
        action="store_true",
        help="Actually send mail through the existing mail bridge. Default is stdout only.",
    )
    parser.add_argument("--format", choices=("json", "human"), default="human", help="Output format.")
    return parser.parse_args(argv)


def _result_to_dict(result: XDryRunMailSendResult | None) -> dict[str, object] | None:
    if result is None:
        return None
    return result.to_dict()


def _render_human(payload: XDryRunMailBuild, result: XDryRunMailSendResult | None) -> str:
    lines = [f"[subject] {payload.subject}", "", payload.body_text.rstrip()]
    if result is not None:
        lines.extend(
            [
                "",
                (
                    f"[result] status={result.status} reason={result.reason} "
                    f"recipients={result.recipients} item_count={result.item_count}"
                ),
            ]
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        payload = build_x_dry_run_mail(WPClient(), limit=args.limit)
        result = send_x_dry_run_mail(payload, dry_run=False) if args.live_mail else None

        if args.format == "json":
            output = payload.to_dict()
            output["live_mail"] = bool(args.live_mail)
            output["mail_result"] = _result_to_dict(result)
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(_render_human(payload, result), end="")
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
