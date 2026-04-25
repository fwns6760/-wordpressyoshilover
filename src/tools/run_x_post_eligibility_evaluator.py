from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIMIT = 50


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _make_wp_client():
    _load_dotenv_if_available()
    from src.wp_client import WPClient

    return WPClient()


def evaluate_published_posts(*args, **kwargs):
    from src.x_post_eligibility_evaluator import evaluate_published_posts as impl

    return impl(*args, **kwargs)


def scan_wp_published_posts(*args, **kwargs):
    from src.x_post_eligibility_evaluator import scan_wp_published_posts as impl

    return impl(*args, **kwargs)


def write_report(*args, **kwargs):
    from src.x_post_eligibility_evaluator import write_report as impl

    return impl(*args, **kwargs)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_x_post_eligibility_evaluator",
        description="Read-only evaluator for published WordPress posts that are safe to turn into X post candidates.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Number of published posts to scan.")
    parser.add_argument("--orderby", default="modified", help="WordPress orderby value. Default: modified.")
    parser.add_argument("--order", choices=("asc", "desc"), default="desc", help="WordPress order direction.")
    parser.add_argument("--format", choices=("json", "human"), default="human", help="Output format.")
    parser.add_argument("--output", help="Write the rendered report to this path instead of stdout.")
    parser.add_argument("--fixture", help="JSON fixture path for in-memory evaluation mode.")
    return parser.parse_args(argv)


def _parse_optional_now(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _load_fixture(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], datetime | None]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload], [], None
    if not isinstance(payload, dict):
        raise ValueError("fixture must be a JSON object or array")

    posts = payload.get("posts")
    if posts is None:
        posts = payload.get("raw_posts")
    if posts is None:
        posts = payload.get("wp_posts")
    if posts is None:
        raise ValueError("fixture must include posts/raw_posts/wp_posts")
    if not isinstance(posts, list):
        raise ValueError("fixture posts must be a JSON array")

    history = payload.get("recent_x_history") or payload.get("history") or []
    if not isinstance(history, list):
        raise ValueError("fixture history must be a JSON array")

    return [dict(item) for item in posts], [dict(item) for item in history], _parse_optional_now(payload.get("now"))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.limit <= 0:
        print("--limit must be > 0", file=sys.stderr)
        return 1

    try:
        if args.fixture:
            posts, recent_x_history, fixture_now = _load_fixture(args.fixture)
            report = evaluate_published_posts(
                posts,
                limit=args.limit,
                orderby=args.orderby,
                order=args.order,
                recent_x_history=recent_x_history,
                now=fixture_now,
            )
        else:
            report = scan_wp_published_posts(
                _make_wp_client(),
                limit=args.limit,
                orderby=args.orderby,
                order=args.order,
            )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    rendered = write_report(report, fmt=args.format, output_path=args.output)
    if not args.output:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
