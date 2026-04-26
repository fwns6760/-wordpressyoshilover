from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.sns_topic_fire_intake import dump_sns_topic_fire_report, evaluate_sns_topic_fire_batch


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_sns_topic_fire_intake",
        description="Dry-run SNS topic fire intake without emitting raw SNS post text or account identifiers.",
    )
    parser.add_argument("--fixture", required=True, help="Path to a JSON or JSONL fixture file.")
    parser.add_argument("--format", choices=("json", "human"), default="json", help="Output format.")
    parser.add_argument("--output", help="Optional output path. Defaults to stdout.")
    return parser.parse_args(argv)


def _load_fixture(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raw = Path(path).read_text(encoding="utf-8")
    suffix = Path(path).suffix.lower()
    if suffix == ".jsonl":
        return _load_jsonl_fixture(raw, path)
    return _load_json_fixture(raw, path)


def _load_json_fixture(raw: str, path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid json: {exc.msg}") from exc

    if isinstance(payload, list):
        return _validate_rows(payload, path, bucket="signals"), []
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: fixture root must be an object or array")

    signals = payload.get("signals", payload.get("items", []))
    rss_index = payload.get("rss_index", payload.get("rss", []))
    return _validate_rows(signals, path, bucket="signals"), _validate_rows(rss_index, path, bucket="rss_index")


def _load_jsonl_fixture(raw: str, path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    signals: list[dict[str, Any]] = []
    rss_index: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid json: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_no}: jsonl row must be an object")
        bucket = str(payload.get("bucket") or payload.get("kind") or "signal").strip().lower()
        row = dict(payload)
        row.pop("bucket", None)
        row.pop("kind", None)
        if bucket == "rss":
            rss_index.append(row)
        else:
            signals.append(row)
    return signals, rss_index


def _validate_rows(value: Any, path: str, *, bucket: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{path}: {bucket} must be a list")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: {bucket}[{index}] must be an object")
        rows.append(item)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        signals, rss_index = _load_fixture(args.fixture)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    candidates = evaluate_sns_topic_fire_batch(signals, rss_index)
    rendered = dump_sns_topic_fire_report(candidates, fmt=args.format)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
