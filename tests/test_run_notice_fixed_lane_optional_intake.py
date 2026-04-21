"""Tests for optional collector intake wiring in ``src.tools.run_notice_fixed_lane``."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools import run_notice_fixed_lane as lane


class _FakeWPClient:
    SOURCE_URL_META_KEY = lane.WPClient.SOURCE_URL_META_KEY

    def __init__(self) -> None:
        self.api = "https://example.com/wp-json/wp/v2"
        self.auth = ("user", "pass")
        self.headers = {"Content-Type": "application/json"}

    def _raise_for_status(self, resp, action: str) -> None:  # pragma: no cover - not used in patched paths
        if resp.status_code >= 400:
            raise RuntimeError(f"{action}:{resp.status_code}")

    def resolve_category_id(self, name: str) -> int:
        mapping = {
            "試合速報": 663,
            "ドラフト・育成": 666,
            "球団情報": 669,
            "選手情報": 664,
            "読売ジャイアンツ": 999,
        }
        return mapping.get(name, 0)


class OptionalIntake045Tests(unittest.TestCase):
    def _write_log(self, payloads: list[dict]) -> str:
        tmpdir = tempfile.mkdtemp(prefix="rss_fetcher_")
        self.addCleanup(lambda: shutil.rmtree(tmpdir, ignore_errors=True))
        path = Path(tmpdir) / "rss_fetcher.log"
        lines = []
        for idx, payload in enumerate(payloads, start=1):
            stamp = f"2026-04-21 07:0{idx}:00"
            lines.append(f"{stamp} [INFO] {json.dumps(payload, ensure_ascii=False)}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    def test_optional_intake_file_routes_fixed_family_into_draft_create_path(self):
        intake_file = self._write_log(
            [
                {
                    "event": "title_template_selected",
                    "source_url": "https://www.giants.jp/game/2026/04/21/preview/",
                    "article_subtype": "pregame",
                    "template": "game_pregame_venue",
                    "original_title": "【4/21予告先発】 巨人 vs 阪神 東京ドーム",
                    "rewritten_title": "巨人阪神戦 東京ドームで何を見たいか",
                }
            ]
        )

        with patch.object(lane, "WPClient", _FakeWPClient), patch.object(
            lane,
            "_run_wp_post_dry_run",
            return_value="pass",
        ), patch.object(lane, "_fetch_latest_notice_candidate") as fetch_mock, patch.object(
            lane,
            "_find_duplicate_posts",
            return_value=[],
        ), patch.object(
            lane,
            "_resolve_category_ids",
            return_value=[663, 999],
        ), patch.object(
            lane,
            "_resolve_tag_ids",
            return_value=[777],
        ), patch.object(
            lane,
            "_create_notice_draft",
            return_value=63175,
        ) as create_mock:
            code, summary = lane.run(["--intake-file", intake_file])

        self.assertEqual(code, lane.EXIT_OK)
        self.assertEqual(summary["canary_post_id"], 63175)
        self.assertIn(lane.ROUTE_FIXED_PRIMARY, summary["route_outcomes"])
        fetch_mock.assert_not_called()
        create_mock.assert_called_once()
        candidate = create_mock.call_args.args[1]
        self.assertEqual(candidate.family, "probable_pitcher")
        self.assertEqual(candidate.metadata["candidate_key"], "probable_pitcher:20260421-g-t")

    def test_optional_intake_file_routes_parity_family_to_deferred_pickup(self):
        intake_file = self._write_log(
            [
                {
                    "event": "title_template_selected",
                    "source_url": "https://twitter.com/hochi_giants/status/2044690907186987488",
                    "article_subtype": "lineup",
                    "template": "game_lineup",
                    "original_title": "甲子園 スタメン 【巨人】 【阪神】 8松本 8近本 9佐々木 4中野",
                    "rewritten_title": "巨人スタメン 甲子園でどこを動かしたか",
                }
            ]
        )

        with patch.object(lane, "WPClient", _FakeWPClient), patch.object(
            lane,
            "_run_wp_post_dry_run",
            return_value="pass",
        ), patch.object(lane, "_fetch_latest_notice_candidate") as fetch_mock, patch.object(
            lane,
            "_create_notice_draft",
        ) as create_mock:
            code, summary = lane.run(
                [
                    "--intake-file",
                    intake_file,
                    "--intake-source",
                    lane.INTAKE_SOURCE_RSS_FETCHER_LOG,
                ]
            )

        self.assertEqual(code, lane.EXIT_OK)
        self.assertIsNone(summary["canary_post_id"])
        self.assertIn(lane.ROUTE_DEFERRED_PICKUP, summary["route_outcomes"])
        fetch_mock.assert_not_called()
        create_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
