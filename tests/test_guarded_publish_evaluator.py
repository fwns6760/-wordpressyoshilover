import unittest
from datetime import datetime
from unittest import mock

from src.guarded_publish_evaluator import evaluate_raw_posts, scan_wp_drafts


FIXED_NOW = datetime.fromisoformat("2026-04-25T21:00:00+09:00")


def _post(post_id, title, body_html, *, featured_media=10, modified="2026-04-25T18:00:00", date="2026-04-25T17:00:00"):
    return {
        "id": post_id,
        "title": {"raw": title},
        "content": {"raw": body_html},
        "featured_media": featured_media,
        "modified": modified,
        "date": date,
        "categories": [],
        "tags": [],
    }


class GuardedPublishEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.green_post = _post(
            101,
            "巨人が阪神に3-2で勝利",
            (
                "<p>巨人が阪神に3-2で勝利した。スポーツ報知によると、戸郷が7回2失点と好投した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.yellow_post = _post(
            102,
            "巨人がDeNAに4-1で勝利",
            (
                "<p>巨人がDeNAに4-1で勝利した。スポーツ報知によると、岡本が2安打を記録した。</p>"
                "<p>この日は中軸の反応と投手運用が噛み合い、終盤まで主導権を保った。</p>"
                "<h3>スタメン</h3>"
                "<p>阿部監督が試合後の総括を丁寧に語り、投手運用の意図も詳しく説明した。</p>"
                "<p>現地の空気感や打線のつながりも振り返った。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
                "<p>💬 ファンの声</p>"
            ),
        )
        self.speculative_post = _post(
            103,
            "巨人はどう動く？阿部監督の狙いはどこ",
            (
                "<p>巨人が阪神戦へ向けて調整した。スポーツ報知によると、阿部監督が打線の状態を確認した。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.injury_post = _post(
            104,
            "巨人の主力が故障で離脱",
            (
                "<p>巨人の主力にケガの症状が出たと報じられた。スポーツ報知によると、診断結果が待たれている。</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.ranking_post = _post(
            105,
            "巨人の記録メモ",
            (
                "<p>巨人の記録メモを整理した。スポーツ報知によると、打線の積み上げが続いている。</p>"
                "<p>NPB通算 1234</p>"
                "<p>参照元: スポーツ報知 https://example.com/source</p>"
            ),
        )
        self.site_middle_post = _post(
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
        self.cleanup_post = _post(
            107,
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
        self.missing_featured_and_source_post = _post(
            108,
            "巨人がヤクルトに6-2で勝利",
            (
                "<p>巨人がヤクルトに6-2で勝利した。先発投手が試合を作り、打線も終盤に加点した。</p>"
                "<p>参照元: https://example.com/source</p>"
            ),
            featured_media=0,
        )

    def _evaluate(self, posts):
        return evaluate_raw_posts(posts, window_hours=96, max_pool=100, now=FIXED_NOW)

    def test_green_fixture_classified_green(self):
        report = self._evaluate([self.green_post])

        self.assertEqual(report["summary"]["green_count"], 1)
        self.assertEqual(report["summary"]["yellow_count"], 0)
        self.assertEqual(report["summary"]["red_count"], 0)
        green_entry = report["green"][0]
        self.assertEqual(green_entry["post_id"], 101)
        self.assertEqual(green_entry["game_key"], "postgame/阪神/2026-04-25")
        self.assertTrue(green_entry["needs_hallucinate_re_evaluation"])

    def test_yellow_detects_weird_heading_label_and_tail_site_component(self):
        report = self._evaluate([self.yellow_post])

        self.assertEqual(report["summary"]["yellow_count"], 1)
        self.assertEqual(report["summary"]["red_count"], 0)
        yellow_entry = report["yellow"][0]
        self.assertIn("weird_heading_label", yellow_entry["yellow_reasons"])
        self.assertIn("site_component_mixed_into_body_tail", yellow_entry["yellow_reasons"])

    def test_red_detects_speculative_injury_ranking_and_site_component_middle(self):
        report = self._evaluate(
            [self.speculative_post, self.injury_post, self.ranking_post, self.site_middle_post]
        )

        self.assertEqual(report["summary"]["red_count"], 4)
        by_post_id = {entry["post_id"]: entry for entry in report["red"]}
        self.assertIn("speculative_title", by_post_id[103]["red_flags"])
        self.assertIn("injury_death", by_post_id[104]["red_flags"])
        self.assertIn("ranking_list_only", by_post_id[105]["red_flags"])
        self.assertIn("site_component_mixed_into_body_middle", by_post_id[106]["red_flags"])

    def test_cleanup_candidate_detects_heading_sentence_h3_and_dev_log_contamination(self):
        report = self._evaluate([self.cleanup_post])

        self.assertEqual(report["summary"]["green_count"], 1)
        self.assertEqual(report["summary"]["cleanup_count"], 1)
        cleanup_entry = report["cleanup_candidates"][0]
        self.assertEqual(cleanup_entry["post_id"], 107)
        self.assertEqual(cleanup_entry["post_judgment"], "green")
        self.assertEqual(
            sorted(cleanup_entry["cleanup_types"]),
            ["dev_log_contamination", "heading_sentence_as_h3"],
        )

    def test_missing_featured_media_and_primary_source_are_yellow(self):
        report = self._evaluate([self.missing_featured_and_source_post])

        self.assertEqual(report["summary"]["yellow_count"], 1)
        yellow_entry = report["yellow"][0]
        self.assertIn("missing_featured_media", yellow_entry["yellow_reasons"])
        self.assertIn("missing_primary_source", yellow_entry["yellow_reasons"])

    def test_summary_counts_are_consistent(self):
        report = self._evaluate(
            [
                self.green_post,
                self.yellow_post,
                self.speculative_post,
                self.injury_post,
                self.ranking_post,
                self.site_middle_post,
                self.cleanup_post,
            ]
        )

        self.assertEqual(report["summary"]["green_count"], 2)
        self.assertEqual(report["summary"]["yellow_count"], 1)
        self.assertEqual(report["summary"]["red_count"], 4)
        self.assertEqual(report["summary"]["cleanup_count"], 1)
        self.assertEqual(report["summary"]["publishable_count"], 3)
        self.assertEqual(report["summary"]["publishable_minus_cleanup_pending"], 2)

    def test_scan_wp_drafts_only_reads_wordpress(self):
        wp_client = mock.Mock()
        wp_client.list_posts.return_value = [self.green_post]
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
