from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.tools import run_llm_cost_report


class RunLlmCostReportTests(unittest.TestCase):
    def _write_jsonl(self, records: list[dict[str, object]]) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "llm_cost.jsonl"
        path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
            encoding="utf-8",
        )
        return path

    def _event(
        self,
        *,
        lane: str = "rss_fetcher_grounded",
        call_site: str = "rss_fetcher.generate_article_with_gemini",
        model: str = "gemini-2.5-flash",
        timestamp: str = "2026-04-28T09:00:00+09:00",
        cost: float = 1.25,
        input_chars: int = 100,
        output_chars: int = 80,
    ) -> dict[str, object]:
        return {
            "event": "llm_cost",
            "lane": lane,
            "call_site": call_site,
            "post_id": 1234,
            "source_url_hash": "hash-1",
            "content_hash": "content-1",
            "model": model,
            "input_chars": input_chars,
            "output_chars": output_chars,
            "token_in_estimate": 25,
            "token_out_estimate": 20,
            "token_source": "char_div_4",
            "estimated_cost_jpy": cost,
            "cache_hit": False,
            "skip_reason": None,
            "success": True,
            "error_class": None,
            "timestamp": timestamp,
        }

    def test_aggregate_by_lane_groups_calls_and_sums_cost(self):
        rows = run_llm_cost_report.aggregate_events(
            [
                self._event(lane="rss_fetcher_grounded", cost=1.25),
                self._event(lane="rss_fetcher_grounded", cost=0.75),
                self._event(lane="draft_body_editor", cost=0.50),
            ],
            ("lane",),
        )

        self.assertEqual(len(rows), 2)
        grounded = next(row for row in rows if row.group == ("rss_fetcher_grounded",))
        self.assertEqual(grounded.calls, 2)
        self.assertEqual(grounded.total_cost_jpy, 2.0)

    def test_aggregate_by_call_site_and_model(self):
        rows = run_llm_cost_report.aggregate_events(
            [
                self._event(call_site="a", model="m1", cost=1.0),
                self._event(call_site="a", model="m1", cost=2.0),
                self._event(call_site="a", model="m2", cost=3.0),
            ],
            ("call_site", "model"),
        )

        self.assertEqual(len(rows), 2)
        row = next(item for item in rows if item.group == ("a", "m1"))
        self.assertEqual(row.calls, 2)
        self.assertEqual(row.total_cost_jpy, 3.0)

    def test_filter_since_24h_excludes_older_events(self):
        events = [
            self._event(timestamp="2026-04-28T09:00:00+09:00"),
            self._event(timestamp="2026-04-26T09:00:00+09:00"),
        ]
        filtered = run_llm_cost_report.filter_events_since(
            events,
            run_llm_cost_report.parse_since_window("24h"),
            now=datetime(2026, 4, 28, 1, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["timestamp"], "2026-04-28T09:00:00+09:00")

    def test_invalid_event_records_are_skipped(self):
        path = self._write_jsonl(
            [
                {"event": "other", "timestamp": "2026-04-28T09:00:00+09:00"},
                self._event(),
            ]
        )

        events = run_llm_cost_report.load_llm_cost_events(path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "llm_cost")

    def test_empty_input_returns_empty_table(self):
        path = self._write_jsonl([])
        events = run_llm_cost_report.load_llm_cost_events(path)
        rows = run_llm_cost_report.aggregate_events(events, ("lane",))
        rendered = run_llm_cost_report.format_tsv(rows, ("lane",))
        self.assertEqual(events, [])
        self.assertEqual(rows, [])
        self.assertEqual(
            rendered,
            "lane\tcalls\ttotal_cost_jpy\tavg_input_chars\tavg_output_chars",
        )


if __name__ == "__main__":
    unittest.main()
