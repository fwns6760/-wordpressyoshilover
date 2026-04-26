from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.sns_topic_source_recheck import dump_sns_topic_source_recheck_report, evaluate_sns_topic_source_recheck_batch


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.tools.run_sns_topic_source_recheck",
        description="Mock-only source recheck for SNS topic candidates with no live HTTP and no WP write.",
    )
    parser.add_argument("--fixture", required=True, help="Path to a JSON fixture file.")
    parser.add_argument("--format", choices=("json", "human"), default="json", help="Output format.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Remain in mock-only mode. Default: on.")
    parser.add_argument("--output", help="Optional output path. Defaults to stdout.")
    return parser.parse_args(argv)


def _load_fixture(path: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    raw = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid json: {exc.msg}") from exc

    if isinstance(payload, list):
        return _validate_candidates(payload, path), {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: fixture root must be an object or array")

    candidate_rows = payload.get("results", payload.get("candidates", payload.get("items", [])))
    resolver_rows = payload.get("resolver_results", payload.get("resolver", {}))
    return _validate_candidates(candidate_rows, path), _validate_resolver_results(resolver_rows, path)


def _validate_candidates(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{path}: candidates must be a list")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path}: candidates[{index}] must be an object")
        rows.append(dict(item))
    return rows


def _validate_resolver_results(value: Any, path: str) -> dict[str, dict[str, Any]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: resolver_results must be an object keyed by topic_key")

    rows: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        if not isinstance(item, dict):
            raise ValueError(f"{path}: resolver_results[{key!r}] must be an object")
        rows[str(key)] = dict(item)
    return rows


def _fixture_resolver(resolver_rows: Mapping[str, Mapping[str, Any]]):
    def _resolver(candidate: Mapping[str, Any]) -> dict[str, Any]:
        topic_key = str(candidate.get("topic_key") or "")
        row = resolver_rows.get(topic_key, {})
        return {
            "official": bool(row.get("official")),
            "rss_match": bool(row.get("rss_match")),
            "rumor_risk": bool(row.get("rumor_risk")),
            "source_urls": row.get("source_urls") or [],
        }

    return _resolver


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        candidates, resolver_rows = _load_fixture(args.fixture)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    decisions = evaluate_sns_topic_source_recheck_batch(candidates, _fixture_resolver(resolver_rows))
    rendered = dump_sns_topic_source_recheck_report(decisions, fmt=args.format)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
