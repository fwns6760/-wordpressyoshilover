"""Dry-run CLI for ticket 071 title/body nucleus alignment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from src.title_body_nucleus_validator import validate_title_body_nucleus


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run title/body nucleus validator on a JSON fixture.")
    parser.add_argument("--fixture", required=True, help="Path to JSON fixture: [{title, body, subtype, known_subjects?}]")
    parser.add_argument("--report", help="Optional JSONL output path for validator results.")
    return parser.parse_args(argv)


def _load_fixture(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("fixture must be a JSON list")
    return [dict(item) for item in payload]


def _format_ok_line(index: int, item: dict[str, Any], result: Any) -> str:
    event = result.title_event or result.body_event
    return (
        f"[ok]    idx={index}  subtype={item.get('subtype', '')}  "
        f"title_subject={result.title_subject}  body_subject={result.body_subject}  event={event}"
    )


def _format_fail_line(index: int, item: dict[str, Any], result: Any) -> str:
    if result.reason_code == "EVENT_DIVERGE":
        return (
            f"[fail]  idx={index}  subtype={item.get('subtype', '')}  "
            f"reason={result.reason_code:<17}  title_event={result.title_event}  body_event={result.body_event}"
        )
    return (
        f"[fail]  idx={index}  subtype={item.get('subtype', '')}  "
        f"reason={result.reason_code:<17}  title_subject={result.title_subject}  body_subject={result.body_subject}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        items = _load_fixture(args.fixture)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"fixture error: {exc}", file=sys.stderr)
        return 1

    aligned = 0
    report_path = Path(args.report) if args.report else None
    report_handle = report_path.open("a", encoding="utf-8") if report_path else None
    try:
        for index, item in enumerate(items):
            result = validate_title_body_nucleus(
                str(item.get("title", "")),
                str(item.get("body", "")),
                str(item.get("subtype", "")),
                known_subjects=list(item.get("known_subjects") or []),
            )
            if result.aligned:
                aligned += 1
                print(_format_ok_line(index, item, result))
            else:
                print(_format_fail_line(index, item, result))
            if report_handle is not None:
                report_handle.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")
        failed = len(items) - aligned
        print(f"[done]  total={len(items)} aligned={aligned} failed={failed}")
    finally:
        if report_handle is not None:
            report_handle.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
