from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.speech_seed_intake import dump_speech_seed_report, evaluate_speech_seed_batch


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_speech_seed_intake_dry_run",
        description="Dry-run speech seed intake against RSS duplicate resistance rules.",
    )
    parser.add_argument("--input", required=True, help="Path to speech seed JSONL input.")
    parser.add_argument("--rss-index", required=True, help="Path to RSS news index JSONL input.")
    parser.add_argument("--format", choices=("json", "human"), default="json", help="Output format.")
    parser.add_argument("--output", help="Optional output path. Defaults to stdout.")
    return parser.parse_args(argv)


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - exercised through main
            raise ValueError(f"{path}:{line_no}: invalid json: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_no}: jsonl row must be an object")
        rows.append(payload)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        seeds = _load_jsonl(args.input)
        rss_index = _load_jsonl(args.rss_index)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    decisions = evaluate_speech_seed_batch(seeds, rss_index)
    rendered = dump_speech_seed_report(decisions, fmt=args.format)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
