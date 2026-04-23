"""Smoke tests for the 046-A1 first-wave dry-run CLI."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "first_wave"


class RunFirstWaveDryRunTests(unittest.TestCase):
    def test_cli_prints_stdout_evidence_for_fixture_routes(self) -> None:
        fixed = FIXTURE_DIR / "lineup_notice_fixed_primary.json"
        deferred = FIXTURE_DIR / "postgame_result_deferred_pickup.json"

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.tools.run_first_wave_dry_run",
                "--assert-expected",
                str(fixed),
                str(deferred),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        lines = completed.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            lines[0],
            "route=fixed_primary subtype=lineup_notice "
            "candidate_key=lineup_notice:20260421-g-t:starting "
            "source_kind=team_x trust_tier=T2",
        )
        self.assertEqual(
            lines[1],
            "route=deferred_pickup subtype=postgame_result "
            "candidate_key=postgame_result:20260421-g-t:win "
            "source_kind=major_rss trust_tier=T2",
        )


if __name__ == "__main__":
    unittest.main()
