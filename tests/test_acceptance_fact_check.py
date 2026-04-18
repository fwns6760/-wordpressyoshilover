import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from src import acceptance_fact_check

JST = timezone(timedelta(hours=9))


class AcceptanceFactCheckTests(unittest.TestCase):
    def tearDown(self):
        acceptance_fact_check._fetch_npb_schedule_snapshot.cache_clear()
        acceptance_fact_check._fetch_game_reference.cache_clear()
        acceptance_fact_check._find_yahoo_game_id.cache_clear()

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

    @patch.object(
        acceptance_fact_check,
        "_fetch_url_snapshot",
        return_value={
            "url": "https://baseball.yahoo.co.jp/npb/game/2021038726/top",
            "ok": True,
            "status_code": 200,
            "title": "2026年4月17日 東京ヤクルトスワローズvs.読売ジャイアンツ - プロ野球 - スポーツナビ",
            "description": "プロ野球 セ・リーグ 東京ヤクルトスワローズvs.読売ジャイアンツの試合のスコア、結果、成績、動画など最新情報をお届けします。",
            "text": 'ya("init", "455de628b9d74646a383bef4947230f8", "37ced58c-4f9f-4725-97a1-572c21a9b7a9");',
            "html": "",
        },
    )
    def test_source_reference_facts_does_not_extract_score_from_uuid_noise(self, _mock_snapshot):
        facts = acceptance_fact_check._source_reference_facts(
            [{"url": "https://baseball.yahoo.co.jp/npb/game/2021038726/top"}]
        )

        self.assertEqual(facts["opponent"], "ヤクルト")
        self.assertEqual(facts["score"], "")
        self.assertEqual(facts["venue"], "")

    @patch.object(
        acceptance_fact_check,
        "_fetch_url_snapshot",
        return_value={
            "url": "https://npb.jp/games/2026/schedule_04_detail.html",
            "ok": True,
            "status_code": 200,
            "title": "",
            "description": "",
            "text": "",
            "html": """
            <table>
              <tr id="date0417">
                <th rowspan="2">4/17（金）</th>
                <td><div class="team1">ヤクルト</div><a href="/scores/2026/0417/s-g-04/"><div class="score1">2</div><div class="state">試合終了</div><div class="score2">8</div></a><div class="team2">巨人</div></td>
                <td><div class="place">神　宮</div><div class="time">18:00</div></td>
              </tr>
              <tr>
                <td><div class="team1">ソフトバンク</div><a href="/scores/2026/0417/h-b-03/"><div class="score1">3</div><div class="state">試合終了</div><div class="score2">1</div></a><div class="team2">オリックス</div></td>
                <td><div class="place">みずほPayPay</div><div class="time">18:00</div></td>
              </tr>
              <tr id="date0418">
                <th>4/18（土）</th>
                <td><div class="team1">ヤクルト</div><div class="team2">巨人</div></td>
                <td><div class="place">神　宮</div><div class="time">18:00</div></td>
              </tr>
            </table>
            """,
        },
    )
    def test_fetch_npb_schedule_snapshot_uses_target_day_row_html(self, _mock_snapshot):
        snapshot = acceptance_fact_check._fetch_npb_schedule_snapshot("2026-04-17", "ヤクルト")

        self.assertEqual(snapshot["opponent"], "ヤクルト")
        self.assertEqual(snapshot["venue"], "神宮")
        self.assertEqual(snapshot["time"], "18:00")
        self.assertEqual(snapshot["score"], "8-2")

    def test_check_game_facts_uses_source_evidence_url_when_reference_is_empty(self):
        findings = []
        post_facts = {
            "target_date": datetime(2026, 4, 17, tzinfo=JST).date(),
            "opponent": "DeNA",
            "venue": "神宮",
            "time": "17:00",
            "score": "",
            "lineup_rows": [],
            "title": "巨人DeNA戦 神宮17:00試合開始",
            "plain_text": "巨人DeNA戦 神宮17:00試合開始",
        }
        audited = {"article_subtype": "pregame"}
        source_facts = {
            "snapshots": [{"url": "https://example.com/source", "title": "巨人ヤクルト戦 神宮18:00試合開始", "description": "", "text": ""}],
            "opponent": "ヤクルト",
            "time": "18:00",
            "venue": "",
            "score": "",
            "field_evidence_urls": {"opponent": "https://example.com/source", "time": "https://example.com/source"},
        }

        with patch.object(
            acceptance_fact_check,
            "_fetch_game_reference",
            return_value={
                "game_id": "",
                "opponent": "",
                "venue": "神宮",
                "time": "",
                "score": "",
                "lineup_rows": [],
                "evidence_urls": ["https://npb.jp/games/2026/schedule_04_detail.html"],
                "evidence_by_field": {"venue": "https://npb.jp/games/2026/schedule_04_detail.html"},
            },
        ):
            acceptance_fact_check._check_game_facts(findings, post_facts, audited, source_facts)

        opponent = next(item for item in findings if item.field == "opponent")
        time = next(item for item in findings if item.field == "time")
        self.assertEqual(opponent.evidence_url, "https://example.com/source")
        self.assertEqual(time.evidence_url, "https://example.com/source")

    def test_check_game_facts_uses_reference_evidence_url_for_score(self):
        findings = []
        post_facts = {
            "target_date": datetime(2026, 4, 17, tzinfo=JST).date(),
            "opponent": "ヤクルト",
            "venue": "神宮",
            "time": "",
            "score": "5-3",
            "lineup_rows": [],
            "title": "巨人がヤクルトに5-3で勝利",
            "plain_text": "巨人がヤクルトに5-3で勝利",
        }
        audited = {"article_subtype": "postgame"}
        source_facts = {"snapshots": [], "opponent": "", "time": "", "venue": "", "score": "", "field_evidence_urls": {}}

        with patch.object(
            acceptance_fact_check,
            "_fetch_game_reference",
            return_value={
                "game_id": "2026041701",
                "opponent": "ヤクルト",
                "venue": "神宮",
                "time": "",
                "score": "4-3",
                "lineup_rows": [],
                "evidence_urls": [
                    "https://baseball.yahoo.co.jp/npb/game/2026041701/top",
                    "https://baseball.yahoo.co.jp/npb/game/2026041701/score",
                ],
                "evidence_by_field": {
                    "opponent": "https://baseball.yahoo.co.jp/npb/game/2026041701/top",
                    "venue": "https://baseball.yahoo.co.jp/npb/game/2026041701/top",
                    "score": "https://baseball.yahoo.co.jp/npb/game/2026041701/score",
                },
            },
        ):
            acceptance_fact_check._check_game_facts(findings, post_facts, audited, source_facts)

        score = next(item for item in findings if item.field == "score")
        self.assertEqual(score.evidence_url, "https://baseball.yahoo.co.jp/npb/game/2026041701/score")


if __name__ == "__main__":
    unittest.main()
