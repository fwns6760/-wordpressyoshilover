"""CLI entrypoint for publish-notice cron health checks."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from dotenv import load_dotenv

if __package__ in {None, ""}:  # pragma: no cover - direct script execution support
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src.publish_notice_cron_health import (  # noqa: E402
    collect_publish_notice_cron_health,
    render_human,
    render_json,
)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run health check for the publish-notice cron path.")
    parser.add_argument("--cron-log", default="logs/publish_notice_cron.log")
    parser.add_argument("--queue", default="logs/publish_notice_queue.jsonl")
    parser.add_argument("--history", default="logs/publish_notice_history.json")
    parser.add_argument("--crontab-marker", default="# 095-WSL-CRON-FALLBACK")
    parser.add_argument("--format", choices=("json", "human"), default="human")
    parser.add_argument("--output", help="Optional path to write the rendered report.")
    return parser.parse_args(argv)


def _render(snapshot: dict[str, object], output_format: str) -> str:
    if output_format == "json":
        return render_json(snapshot)
    return render_human(snapshot)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        load_dotenv()
        args = _parse_args(argv)
        snapshot = collect_publish_notice_cron_health(
            cron_log_path=args.cron_log,
            queue_path=args.queue,
            history_path=args.history,
            crontab_marker=args.crontab_marker,
        )
        rendered = _render(snapshot, args.format)
        sys.stdout.write(rendered)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"[health-check] status=error error_type={type(exc).__name__} message={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
