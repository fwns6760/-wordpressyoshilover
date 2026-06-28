"""Tests for finance news SNS candidate mail lane."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.tools import finance_news_sns_candidates as fnc


RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Market source</title>
    <item>
      <title>FOMC leaves Federal funds rate unchanged as inflation remains elevated</title>
      <link>https://example.test/fomc</link>
      <description>monetary policy and inflation update</description>
      <pubDate>Tue, 16 Jun 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Consumer education event announced</title>
      <link>https://example.test/event</link>
      <description>consumer education</description>
    </item>
  </channel>
</rss>
"""


HTML_SAMPLE = """<html><head><title>TDnet-like page</title></head><body>
<a href="/disclosure/1">A社 2027年3月期 業績予想の上方修正に関するお知らせ</a>
<a href="/disclosure/2">定款一部変更に関するお知らせ</a>
<a href="javascript:void(0)">決算短信 fake</a>
</body></html>"""


class FinanceNewsCandidateTests(unittest.TestCase):
    def test_rss_candidate_scoring_and_mail_has_x_button(self) -> None:
        source = fnc.FinanceSource(
            id="fed",
            name="Federal Reserve",
            market="US_GLOBAL",
            kind="rss",
            url="https://example.test/rss.xml",
            priority="P0",
            post_lane="stock_macro_news",
            score_base=85,
            include_keywords=("FOMC", "Federal funds rate", "inflation"),
            exclude_keywords=("consumer education",),
        )
        raw = [(source, item) for item in fnc._items_from_feed_text(source, RSS_SAMPLE)]
        stats = fnc.FinanceBuildStats(loaded_sources=1)
        candidates = fnc.score_items(raw, minimum_score=75, stats=stats)

        self.assertEqual(len(candidates), 1)
        self.assertIn("FOMC", candidates[0].matched_keywords)
        self.assertIn("出所: Federal Reserve", candidates[0].post_text())

        subject, text, html = fnc.compose_mail(
            candidates,
            now=datetime(2026, 6, 16, 21, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
            stats=stats,
        )
        self.assertIn("金融SNS候補", subject)
        self.assertIn("X投稿画面", text)
        self.assertIn("X にポストする", html)

    def test_homepage_watch_anchor_to_candidate(self) -> None:
        source = fnc.FinanceSource(
            id="tdnet",
            name="TDnet",
            market="JP",
            kind="html_to_internal_rss",
            url="https://example.test/top.html",
            priority="P0",
            post_lane="jp_equity_disclosure",
            score_base=90,
            include_keywords=("業績予想", "上方修正", "決算短信"),
            exclude_keywords=("定款",),
        )
        items = fnc._items_from_homepage(source, HTML_SAMPLE)
        candidates = fnc.score_items([(source, item) for item in items], minimum_score=75)

        self.assertEqual(len(candidates), 1)
        self.assertIn("上方修正", candidates[0].title)
        self.assertEqual(candidates[0].url, "https://example.test/disclosure/1")

    def test_build_candidates_dedupes_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            source_path = tmp / "sources.json"
            ledger_path = tmp / "ledger.jsonl"
            source_path.write_text(
                json.dumps(
                    {
                        "scoring": {"minimum_score_to_mail": 75, "dedupe_window_hours": 24},
                        "sources": [
                            {
                                "id": "fed",
                                "name": "Federal Reserve",
                                "market": "US_GLOBAL",
                                "kind": "rss",
                                "url": "https://example.test/rss.xml",
                                "priority": "P0",
                                "post_lane": "stock_macro_news",
                                "score_base": 85,
                                "include_keywords": ["FOMC", "inflation"],
                                "exclude_keywords": [],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            first_now = datetime(2026, 6, 16, 21, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
            with patch.object(fnc, "_http_get", return_value=RSS_SAMPLE):
                result = fnc.build_candidates(source_path=source_path, now=first_now, ledger_path=ledger_path)
            self.assertEqual(len(result.candidates), 1)

            fnc.append_ledger(result.candidates, now=first_now, ledger_path=ledger_path)
            with patch.object(fnc, "_http_get", return_value=RSS_SAMPLE):
                second = fnc.build_candidates(source_path=source_path, now=first_now, ledger_path=ledger_path)
            self.assertEqual(second.candidates, [])
            self.assertEqual(second.stats.deduped_items, 1)


if __name__ == "__main__":
    unittest.main()
