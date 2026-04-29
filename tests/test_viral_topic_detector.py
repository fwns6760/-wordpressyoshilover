import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

from src import viral_topic_detector as detector
from src.tools import run_viral_topic_dry_run as dry_run


REALTIME_HTML = """
<ul>
  <li data-rank="1">
    <a href="https://search.yahoo.co.jp/realtime/search?p=%E5%B7%A8%E4%BA%BA+%E3%82%B9%E3%82%BF%E3%83%A1%E3%83%B3">巨人 スタメン</a>
    <span>20,000件</span>
  </li>
  <li data-rank="2">
    <a href="/realtime/search?p=%E6%88%B8%E9%83%B7">戸郷</a>
    <span>5,000件</span>
  </li>
</ul>
"""


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class ViralTopicDetectorTests(unittest.TestCase):
    def test_fetch_yahoo_realtime_search_returns_empty_on_timeout(self):
        with self.assertLogs("src.viral_topic_detector", level="WARNING") as captured:
            with patch("src.viral_topic_detector.requests.get", side_effect=requests.Timeout("boom")):
                rows = detector.fetch_yahoo_realtime_search_giants()

        self.assertEqual(rows, [])
        self.assertTrue(any("yahoo_realtime_search detection skipped" in line for line in captured.output))

    def test_fetch_yahoo_realtime_search_parses_html_fixture_correctly(self):
        with patch("src.viral_topic_detector.requests.get", return_value=_FakeResponse(REALTIME_HTML)):
            rows = detector.fetch_yahoo_realtime_search_giants()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["keyword"], "巨人 スタメン")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["volume"], "20,000件")
        self.assertEqual(rows[1]["keyword"], "戸郷")
        self.assertEqual(rows[1]["rank"], 2)

    def test_classify_expected_subtype_for_postgame_keyword(self):
        subtype, confidence = detector.classify_expected_subtype("巨人 3-2 阪神 勝利")

        self.assertEqual(subtype, "postgame")
        self.assertEqual(confidence, "high")

    def test_classify_expected_subtype_for_lineup_keyword(self):
        subtype, confidence = detector.classify_expected_subtype("巨人 スタメン発表")

        self.assertEqual(subtype, "lineup")
        self.assertEqual(confidence, "high")

    def test_classify_expected_subtype_for_unresolved_keyword(self):
        subtype, confidence = detector.classify_expected_subtype("大型連休の話題")

        self.assertIsNone(subtype)
        self.assertEqual(confidence, "unresolved")

    def test_cross_reference_returns_unconfirmed_when_history_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing.json"
            with patch.object(detector, "HISTORY_FILE", missing_path), patch.object(detector, "GCS_BUCKET", ""), patch.object(
                detector, "_FETCHER_HISTORY_CACHE", None
            ):
                result = detector.cross_reference_official_sources("巨人 スタメン")

        self.assertFalse(result["confirmed"])
        self.assertEqual(result["reason"], "history_unavailable")

    def test_cross_reference_returns_confirmed_when_keyword_in_history(self):
        history = {
            "entries": [
                {
                    "title": "巨人スタメン発表 坂本勇人が3番",
                    "url": "https://example.com/lineup",
                    "article_subtype": "lineup",
                    "published_at": "2099-04-29T01:00:00+09:00",
                }
            ]
        }

        result = detector.cross_reference_official_sources("巨人 スタメン", history)

        self.assertTrue(result["confirmed"])
        self.assertEqual(result["primary_source_url"], "https://example.com/lineup")
        self.assertEqual(result["primary_subtype"], "lineup")
        self.assertEqual(result["reason"], "ok")

    def test_has_spam_marker_detects_噂_らしい_やばい(self):
        samples = ("これは噂です", "そうらしい", "展開がやばい")

        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(detector.has_spam_marker(sample))

    def test_build_topic_candidate_schema_is_complete(self):
        candidate = detector.build_topic_candidate(
            {
                "keyword": "巨人 スタメン",
                "rank": 1,
                "volume": "20,000件",
                "detected_at": "2026-04-29T10:00:00+09:00",
            },
            "yahoo_realtime_search",
        )

        self.assertEqual(
            set(candidate.keys()),
            {
                "schema_version",
                "detected_at",
                "source",
                "raw_signal",
                "expected_subtype",
                "subtype_confidence",
                "source_confirmation",
                "skip_reason",
                "publish_blocked",
                "next_action",
            },
        )
        self.assertEqual(
            set(candidate["raw_signal"].keys()),
            {"keyword", "rank", "trend_volume", "title", "url", "context_excerpt"},
        )
        self.assertEqual(
            set(candidate["source_confirmation"].keys()),
            {"confirmed", "primary_source_url", "primary_subtype", "reason"},
        )
        self.assertTrue(candidate["publish_blocked"])

    def test_dry_run_entrypoint_writes_jsonl_no_publish(self):
        realtime_rows = [
            {
                "keyword": "巨人 スタメン発表",
                "rank": 1,
                "volume": "20,000件",
                "detected_at": "2026-04-29T10:00:00+09:00",
            },
            {
                "keyword": "これは噂らしい",
                "rank": 2,
                "volume": "500件",
                "detected_at": "2026-04-29T10:00:00+09:00",
            },
        ]
        ranking_rows = [
            {
                "title": "巨人 戸郷翔征が完投勝利",
                "url": "https://news.yahoo.co.jp/articles/example",
                "rank": 1,
                "detected_at": "2026-04-29T10:00:00+09:00",
            }
        ]
        history = {
            "entries": [
                {
                    "title": "巨人スタメン発表 坂本勇人が3番",
                    "url": "https://example.com/lineup",
                    "article_subtype": "lineup",
                    "published_at": "2099-04-29T01:00:00+09:00",
                },
                {
                    "title": "巨人が3-2で勝利 戸郷翔征が完投",
                    "url": "https://example.com/postgame",
                    "article_subtype": "postgame",
                    "published_at": "2099-04-29T01:05:00+09:00",
                },
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "viral"
            with patch("src.tools.run_viral_topic_dry_run.fetch_yahoo_realtime_search_giants", return_value=realtime_rows), patch(
                "src.tools.run_viral_topic_dry_run.fetch_yahoo_news_baseball_ranking", return_value=ranking_rows
            ), patch("src.tools.run_viral_topic_dry_run.load_fetcher_history", return_value=history), patch(
                "src.tools.run_viral_topic_dry_run._today_key", return_value="2026-04-29"
            ), patch("src.tools.run_viral_topic_dry_run.WPClient", create=True) as wp_client:
                code = dry_run.main(["--max-candidates", "10", "--out-dir", str(out_dir)])

            output_path = out_dir / "2026-04-29.jsonl"
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(code, 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["expected_subtype"], "lineup")
        self.assertEqual(rows[0]["next_action"], "candidate_for_existing_subtype")
        self.assertEqual(rows[1]["expected_subtype"], "postgame")
        self.assertTrue(all(row["publish_blocked"] for row in rows))
        self.assertNotIn("spam_marker", json.dumps(rows, ensure_ascii=False))
        wp_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
