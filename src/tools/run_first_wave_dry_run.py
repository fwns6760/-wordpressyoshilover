"""Fixture dry-run CLI for 046-A1 first-wave pickup promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from src.first_wave_promotion import PromotionDecision, judge_first_wave_batch


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "first_wave"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    fixture_paths = _resolve_fixture_paths(args.fixtures)
    if not fixture_paths:
        raise SystemExit("no first-wave fixtures found")

    exit_code = 0
    for path in fixture_paths:
        fixture = _load_fixture(path)
        decisions = judge_first_wave_batch(
            fixture["candidates"],
            existing_candidate_keys=fixture.get("existing_candidate_keys", ()),
        )
        for decision in decisions:
            print(decision.evidence_line())
        if args.assert_expected and not _matches_expected(fixture, decisions):
            exit_code = 1
    return exit_code


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixtures",
        nargs="*",
        help="Fixture JSON files. Defaults to tests/fixtures/first_wave/*.json.",
    )
    parser.add_argument(
        "--assert-expected",
        action="store_true",
        help="Return non-zero when fixture expected_route/expected_routes do not match.",
    )
    return parser.parse_args(argv)


def _resolve_fixture_paths(values: Sequence[str]) -> list[Path]:
    if values:
        return sorted(Path(value) for value in values)
    return sorted(DEFAULT_FIXTURE_DIR.glob("*.json"))


def _load_fixture(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, list):
        return {"candidates": data}
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        raise ValueError(f"invalid first-wave fixture: {path}")
    return data


def _matches_expected(fixture: dict[str, Any], decisions: Sequence[PromotionDecision]) -> bool:
    expected_routes = fixture.get("expected_routes")
    if expected_routes is None and fixture.get("expected_route"):
        expected_routes = [fixture["expected_route"]]
    if expected_routes is None:
        return True
    actual_routes = [decision.route for decision in decisions]
    return list(expected_routes) == actual_routes


if __name__ == "__main__":
    raise SystemExit(main())
