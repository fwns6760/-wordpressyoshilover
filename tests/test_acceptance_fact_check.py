import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from src import acceptance_fact_check

JST = timezone(timedelta(hours=9))


class AcceptanceFactCheckTests(unittest.TestCase):
    def _make_post(self, title: str, content_html: str, categories=None) -> dict:
        return {
            "id": 62538,
            "status": "draft",
            "date": "2026-04-17T21:01:00",
            "modified": "2026-04-17T21:01:00",
            "title": {"raw": title},
            "content": {"raw": content_html},
            "categories": categories or [663],
        }

    @patch.object(
        acceptance_fact_check,
        "_source_reference_facts",
        return_value={
            "snapshots": [
                {
                    "url": "https://example.com/source",
                    "title": "巨人ヤクルト戦 神宮18:00試合開始",
                    "description": "",
                    "text": "巨人ヤクルト戦 神宮18:00試合開始",
                }
            ],
            "opponent": "ヤクルト",
            "venue": "神宮",
            "time": "18:00",
            "score": "",
            "subject": "",
        },
    )
    @patch.object(
        acceptance_fact_check,
        "_fetch_game_reference",
        return_value={
            "game_id": "2026041701",
            "opponent": "ヤクルト",
            "venue": "神宮",
            "time": "18:00",
            "score": "",
            "lineup_rows": [],
            "evidence_urls": ["https://baseball.yahoo.co.jp/npb/game/2026041701/top"],
        },
    )
    def test_build_post_report_flags_opponent_mismatch_in_title(self, *_mocks):
        post = self._make_post(
            "巨人DeNA戦 神宮18:00試合開始 先発は戸郷翔征",
            '<p>📰 参照元: <a href="https://example.com/source">スポーツ報知 巨人</a></p>',
        )

        report = acceptance_fact_check.build_post_report(post, {663: "試合速報"}, {}, "https://yoshilover.com")

        self.assertEqual(report.result, "red")
        finding = next(item for item in report.findings if item.field == "opponent")
        self.assertEqual(finding.current, "DeNA")
        self.assertEqual(finding.expected, "ヤクルト")
        self.assertEqual(finding.cause, "title_rewrite_mismatch")

    @patch.object(
        acceptance_fact_check,
        "_source_reference_facts",
        return_value={
            "snapshots": [
                {
                    "url": "https://example.com/postgame",
                    "title": "巨人がヤクルトに4-3で勝利",
                    "description": "",
                    "text": "巨人がヤクルトに4-3で勝利",
                }
            ],
            "opponent": "ヤクルト",
            "venue": "神宮",
            "time": "",
            "score": "4-3",
            "subject": "",
        },
    )
    @patch.object(
        acceptance_fact_check,
        "_fetch_game_reference",
        return_value={
            "game_id": "2026041701",
            "opponent": "ヤクルト",
            "venue": "神宮",
            "time": "",
            "score": "4-3",
            "lineup_rows": [],
            "evidence_urls": ["https://baseball.yahoo.co.jp/npb/game/2026041701/score"],
        },
    )
    def test_build_post_report_flags_score_mismatch_for_postgame(self, *_mocks):
        post = self._make_post(
            "巨人がヤクルトに5-3で勝利 決勝打は吉川尚輝",
            '<p>📰 参照元: <a href="https://example.com/postgame">スポーツ報知 巨人</a></p>',
        )

        report = acceptance_fact_check.build_post_report(post, {663: "試合速報"}, {}, "https://yoshilover.com")

        finding = next(item for item in report.findings if item.field == "score")
        self.assertEqual(finding.current, "5-3")
        self.assertEqual(finding.expected, "4-3")
        self.assertEqual(finding.fix_type, "direct_edit")

    @patch.object(
        acceptance_fact_check,
        "_source_reference_facts",
        return_value={
            "snapshots": [
                {
                    "url": "https://example.com/lineup",
                    "title": "巨人スタメン 1番丸 2番泉口 3番吉川",
                    "description": "",
                    "text": "巨人スタメン 1番丸 2番泉口 3番吉川",
                }
            ],
            "opponent": "ヤクルト",
            "venue": "神宮",
            "time": "18:00",
            "score": "",
            "subject": "",
        },
    )
    @patch.object(
        acceptance_fact_check,
        "_fetch_game_reference",
        return_value={
            "game_id": "2026041701",
            "opponent": "ヤクルト",
            "venue": "神宮",
            "time": "18:00",
            "score": "",
            "lineup_rows": [
                {"order": "1", "name": "丸佳浩", "position": "中"},
                {"order": "2", "name": "泉口友汰", "position": "遊"},
                {"order": "3", "name": "吉川尚輝", "position": "二"},
            ],
            "evidence_urls": ["https://baseball.yahoo.co.jp/npb/game/2026041701/top"],
        },
    )
    def test_build_post_report_flags_lineup_mismatch(self, *_mocks):
        content_html = """
        <p>📰 参照元: <a href="https://example.com/lineup">巨人公式</a></p>
        <table>
          <tr><td>1</td><td>中</td><td>佐々木俊輔</td><td>.281</td></tr>
          <tr><td>2</td><td>左</td><td>キャベッジ</td><td>.302</td></tr>
          <tr><td>3</td><td>遊</td><td>泉口友汰</td><td>.260</td></tr>
        </table>
        """
        post = self._make_post("巨人スタメン発表", content_html)

        report = acceptance_fact_check.build_post_report(post, {663: "試合速報"}, {}, "https://yoshilover.com")

        finding = next(item for item in report.findings if item.field == "lineup")
        self.assertEqual(finding.severity, "red")
        self.assertIn("1番佐々木俊輔", finding.current)
        self.assertIn("1番丸佳浩", finding.expected)

    def test_build_post_report_warns_when_source_reference_is_missing(self):
        post = self._make_post("巨人メモ", "<p>本文だけで参照元なし</p>", categories=[8])

        report = acceptance_fact_check.build_post_report(post, {8: "選手情報"}, {}, "https://yoshilover.com")

        self.assertEqual(report.result, "yellow")
        finding = next(item for item in report.findings if item.field == "source_reference")
        self.assertEqual(finding.cause, "source_reference_missing")

    @patch.object(
        acceptance_fact_check,
        "_source_reference_facts",
        return_value={"snapshots": [], "opponent": "", "venue": "", "time": "", "score": "", "subject": ""},
    )
    @patch.object(
        acceptance_fact_check,
        "_fetch_url_snapshot",
        side_effect=[
            {"url": "https://twitter.com/hochi_giants/status/1", "ok": False, "status_code": 404, "title": "", "description": "", "text": ""},
        ],
    )
    def test_build_post_report_flags_b5_quote_404(self, *_mocks):
        post = self._make_post(
            "報知が阿部監督コメントを報道",
            """
            <p>📰 参照元: <a href="https://example.com/source">スポーツ報知 巨人</a></p>
            <blockquote><a href="https://twitter.com/hochi_giants/status/1">tweet</a></blockquote>
            """,
            categories=[665],
        )

        report = acceptance_fact_check.build_post_report(post, {665: "首脳陣"}, {}, "https://yoshilover.com")

        finding = next(item for item in report.findings if item.field == "b5_quote")
        self.assertEqual(finding.cause, "b5_quote_reference_broken")
        self.assertEqual(finding.fix_type, "remove_or_replace_embed")

    def test_matches_category_filter_accepts_article_subtype(self):
        audited = {"primary_category": "試合速報", "article_subtype": "postgame", "source_bucket": "news"}

        self.assertTrue(acceptance_fact_check._matches_category_filter(audited, "postgame"))
        self.assertTrue(acceptance_fact_check._matches_category_filter(audited, "試合速報"))
        self.assertFalse(acceptance_fact_check._matches_category_filter(audited, "manager"))

    def test_matches_since_filter_supports_yesterday(self):
        yesterday = (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%dT06:55:00+09:00")
        post = self._make_post("巨人メモ", "<p>本文</p>")
        post["modified"] = yesterday

        self.assertTrue(acceptance_fact_check._matches_since_filter(post, "yesterday"))
        self.assertFalse(acceptance_fact_check._matches_since_filter(post, "today"))


if __name__ == "__main__":
    unittest.main()
