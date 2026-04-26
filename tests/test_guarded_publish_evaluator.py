import unittest
from datetime import datetime
from unittest import mock

from src.guarded_publish_evaluator import evaluate_raw_posts, scan_wp_drafts


FIXED_NOW = datetime.fromisoformat("2026-04-25T21:00:00+09:00")


def _post(
    post_id,
    title,
    body_html,
    *,
    featured_media=10,
    modified="2026-04-25T18:00:00",
    date="2026-04-25T17:00:00",
    meta=None,
):
    payload = {
        "id": post_id,
        "title": {"raw": title},
        "content": {"raw": body_html},
        "featured_media": featured_media,
        "modified": modified,
        "date": date,
        "categories": [],
        "tags": [],
    }
    if meta is not None:
        payload["meta"] = meta
    return payload


class GuardedPublishEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.clean_post = _post(
            101,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.repairable_post = _post(
            102,
            "巨人はどう動く？阿部監督の狙いはどこ",
            (
                "<p>巨人が阪神戦へ向けて調整した。スポーツ報知によると、阿部監督が打線の状態を確認した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.heading_and_devlog_post = _post(
            103,
            "巨人が中日に5-1で勝利",
            (
                "<p>巨人が中日に5-1で勝利した。スポーツ報知によると、戸郷が7回1失点で今季3勝目を挙げた。</p>"
                "<p>岡本が先制打を放ち、序盤から主導権を握った。</p>"
                "<p>継投も安定し、終盤まで流れを渡さなかった。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
                "<h3>戸郷が7回1失点で今季3勝目となったことを球団が試合後に発表した</h3>"
                "<pre>"
                "python3 -m src.tools.run_guarded_publish_evaluator\n"
                "commit_hash=abc12345\n"
                "changed_files=2\n"
                "tokens used: 10\n"
                "git diff --stat\n"
                "</pre>"
            ),
        )
        self.hard_stop_post = _post(
            104,
            "巨人の主力が故障で離脱",
            (
                "<p>巨人の主力にケガの症状が出たと報じられた。スポーツ報知によると、診断結果が待たれている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.hard_stop_plus_repairable_post = _post(
            105,
            "巨人はどう動く？主力が故障で離脱",
            (
                "<p>巨人の主力にケガの症状が出たと報じられた。スポーツ報知によると、診断結果が待たれている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.site_component_post = _post(
            106,
            "巨人が広島に2-1で勝利",
            (
                "<p>巨人が広島に2-1で勝利した。スポーツ報知によると、赤星が7回1失点と好投した。</p>"
                "<p>序盤から丁寧に試合を運んだ。</p>"
                "<p>【関連記事】</p>"
                "<p>終盤は継投で逃げ切った。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.weak_source_post = _post(
            107,
            "巨人がヤクルトに6-2で勝利",
            (
                "<p>巨人がヤクルトに6-2で勝利した。先発投手が試合を作り、打線も終盤に加点した。</p>"
                "<p>参照元: https://example.com/source</p>"
            ),
            featured_media=0,
        )
        self.ranking_post = _post(
            108,
            "巨人の記録メモ",
            (
                "<p>巨人の記録メモを整理した。スポーツ報知によると、打線の積み上げが続いている。</p>"
                "<p>NPB通算 1234</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.lineup_hochi_post = _post(
            109,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。スポーツ報知によると、1番丸、4番岡本で先発する。</p>"
                "<p>参照元: スポーツ報知 https://hochi.news/articles/20260425-OHT1T51000.html</p>"
            ),
            meta={
                "article_subtype": "lineup",
                "candidate_key": "lineup_notice:20260425-g-t:starting",
                "game_id": "20260425-g-t",
                "_yoshilover_source_url": "https://hochi.news/articles/20260425-OHT1T51000.html",
            },
        )
        self.lineup_other_post = _post(
            110,
            "巨人スタメン 1番丸 4番岡本",
            (
                "<p>巨人のスタメンが発表された。スポニチによると、1番丸、4番岡本で先発する。</p>"
                "<p>参照元: スポニチ https://www.sponichi.co.jp/baseball/news/2026/04/25/kiji.html</p>"
            ),
            meta={
                "article_subtype": "lineup",
                "candidate_key": "lineup_notice:20260425-g-t:starting",
                "game_id": "20260425-g-t",
                "_yoshilover_source_url": "https://www.sponichi.co.jp/baseball/news/2026/04/25/kiji.html",
            },
        )

    def _evaluate(self, posts):
        return evaluate_raw_posts(posts, window_hours=96, max_pool=100, now=FIXED_NOW)

    def test_clean_post_returns_publishable_true_and_cleanup_required_false(self):
        report = self._evaluate([self.clean_post])

        self.assertEqual(report["summary"]["clean_count"], 1)
        self.assertEqual(report["summary"]["repairable_count"], 0)
        self.assertEqual(report["summary"]["hard_stop_count"], 0)
        entry = report["green"][0]
        self.assertEqual(entry["category"], "clean")
        self.assertTrue(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertEqual(entry["repairable_flags"], [])

    def test_repairable_only_post_returns_publishable_true_and_cleanup_required_true(self):
        report = self._evaluate([self.repairable_post])

        self.assertEqual(report["summary"]["clean_count"], 0)
        self.assertEqual(report["summary"]["repairable_count"], 1)
        self.assertEqual(report["summary"]["hard_stop_count"], 0)
        entry = report["yellow"][0]
        self.assertEqual(entry["category"], "repairable")
        self.assertTrue(entry["publishable"])
        self.assertTrue(entry["cleanup_required"])
        self.assertIn("ai_tone_heading_or_lead", entry["repairable_flags"])
        self.assertIn("speculative_title", entry["yellow_reasons"])

    def test_hard_stop_only_post_returns_publishable_false(self):
        report = self._evaluate([self.hard_stop_post])

        self.assertEqual(report["summary"]["clean_count"], 0)
        self.assertEqual(report["summary"]["repairable_count"], 0)
        self.assertEqual(report["summary"]["hard_stop_count"], 1)
        entry = report["red"][0]
        self.assertEqual(entry["category"], "hard_stop")
        self.assertFalse(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertEqual(
            entry["reasons"],
            [{"flag": "injury_death", "category": "hard_stop"}],
        )

    def test_hard_stop_plus_repairable_returns_publishable_false(self):
        report = self._evaluate([self.hard_stop_plus_repairable_post])

        self.assertEqual(report["summary"]["hard_stop_count"], 1)
        entry = report["red"][0]
        self.assertFalse(entry["publishable"])
        self.assertFalse(entry["cleanup_required"])
        self.assertIn("injury_death", entry["hard_stop_flags"])
        self.assertIn("ai_tone_heading_or_lead", entry["repairable_flags"])
        self.assertIn("speculative_title", entry["yellow_reasons"])

    def test_summary_includes_hard_stop_repairable_clean_counts(self):
        report = self._evaluate(
            [
                self.clean_post,
                self.repairable_post,
                self.heading_and_devlog_post,
                self.hard_stop_post,
                self.site_component_post,
                self.weak_source_post,
                self.ranking_post,
            ]
        )

        self.assertEqual(report["summary"]["green_count"], 1)
        self.assertEqual(report["summary"]["yellow_count"], 4)
        self.assertEqual(report["summary"]["red_count"], 2)
        self.assertEqual(report["summary"]["clean_count"], 1)
        self.assertEqual(report["summary"]["repairable_count"], 4)
        self.assertEqual(report["summary"]["hard_stop_count"], 2)
        self.assertEqual(report["summary"]["publishable_count"], 5)
        self.assertEqual(report["summary"]["soft_cleanup_count"], 4)

    def test_cleanup_candidate_detects_heading_sentence_h3_and_dev_log_contamination(self):
        report = self._evaluate([self.heading_and_devlog_post])

        self.assertEqual(report["summary"]["cleanup_count"], 1)
        cleanup_entry = report["cleanup_candidates"][0]
        self.assertEqual(cleanup_entry["post_id"], 103)
        self.assertEqual(cleanup_entry["post_judgment"], "repairable")
        self.assertEqual(
            sorted(cleanup_entry["cleanup_types"]),
            ["dev_log_contamination", "heading_sentence_as_h3"],
        )

    def test_site_component_reasons_keep_legacy_yellow_reason_but_use_repairable_flag(self):
        report = self._evaluate([self.site_component_post])

        entry = report["yellow"][0]
        self.assertIn("site_component_mixed_into_body", entry["repairable_flags"])
        self.assertIn("site_component_mixed_into_body_middle", entry["yellow_reasons"])

    def test_missing_featured_media_and_weak_source_display_are_repairable(self):
        report = self._evaluate([self.weak_source_post])

        entry = report["yellow"][0]
        self.assertIn("missing_featured_media", entry["repairable_flags"])
        self.assertIn("weak_source_display", entry["repairable_flags"])
        self.assertIn("missing_primary_source", entry["yellow_reasons"])

    def test_lineup_duplicate_absorbed_by_hochi_keeps_legacy_red_flag(self):
        report = self._evaluate([self.lineup_hochi_post, self.lineup_other_post])

        self.assertEqual(report["summary"]["green_count"], 1)
        self.assertEqual(report["summary"]["red_count"], 1)
        red_entry = report["red"][0]
        self.assertIn("lineup_duplicate_excessive", red_entry["hard_stop_flags"])
        self.assertIn("lineup_duplicate_absorbed_by_hochi", red_entry["red_flags"])
        self.assertEqual(red_entry["representative_post_id"], 109)

    def test_scan_wp_drafts_only_reads_wordpress(self):
        wp_client = mock.Mock()
        wp_client.list_posts.return_value = [self.clean_post]
        wp_client.update_post_fields = mock.Mock()
        wp_client.update_post_status = mock.Mock()
        wp_client.get_post = mock.Mock()

        report = scan_wp_drafts(wp_client, window_hours=96, max_pool=10, now=FIXED_NOW)

        self.assertEqual(report["summary"]["green_count"], 1)
        wp_client.list_posts.assert_called_once_with(
            status="draft",
            per_page=10,
            orderby="modified",
            order="desc",
            context="edit",
        )
        wp_client.update_post_fields.assert_not_called()
        wp_client.update_post_status.assert_not_called()
        wp_client.get_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
