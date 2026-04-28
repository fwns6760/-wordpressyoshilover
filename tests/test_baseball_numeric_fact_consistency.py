import unittest

from src.baseball_numeric_fact_consistency import check_consistency as _check_consistency, extract_scores


def check_consistency(*args, **kwargs):
    if "subtype" not in kwargs:
        kwargs["subtype"] = "postgame"
    return _check_consistency(*args, **kwargs)


class BaseballNumericFactConsistencyTests(unittest.TestCase):
    def test_score_1_11_is_not_normalized_to_19_1(self):
        scores = extract_scores("巨人 1-11 楽天")

        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0].pair, (1, 11))
        self.assertNotEqual(scores[0].pair, (19, 1))
        self.assertNotEqual(scores[0].pair, (11, 1))
        self.assertNotEqual(scores[0].pair, (1, 9))
        self.assertNotEqual(scores[0].pair, (9, 1))

    def test_score_mismatch_blocks_publish(self):
        report = check_consistency(
            source_text="巨人 1-11 楽天",
            generated_body="巨人が楽天に19-1で勝利した。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "hard_stop")
        self.assertIn("numeric_fact_mismatch", report.hard_stop_flags)

    def test_win_loss_conflict_blocks_publish(self):
        report = check_consistency(
            source_text="巨人 1-11 楽天",
            generated_body="巨人が楽天に勝利した。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "hard_stop")
        self.assertIn("win_loss_score_conflict", report.hard_stop_flags)

    def test_ambiguous_score_is_review_not_hard_stop(self):
        report = check_consistency(
            source_text="巨人 1-11 楽天。別稿では巨人 11-1 楽天とも記されている。",
            generated_body="巨人が楽天戦を振り返った。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "review")
        self.assertIn("score_order_mismatch_review", report.review_flags)
        self.assertEqual(report.hard_stop_flags, ())

    def test_pitcher_hits_allowed_not_confused_with_team_hits(self):
        report = check_consistency(
            source_text="先発戸郷は5回3安打2失点。巨人は11安打を放った。",
            generated_body="戸郷が11被安打で崩れた。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "hard_stop")
        self.assertIn("pitcher_team_stat_confusion", report.hard_stop_flags)

    def test_team_hits_not_written_as_pitcher_hits_allowed(self):
        report = check_consistency(
            source_text="先発戸郷は5回3安打2失点。巨人は11安打を放った。",
            generated_body="巨人は3安打2得点に終わった。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "hard_stop")
        self.assertIn("pitcher_team_stat_confusion", report.hard_stop_flags)

    def test_date_mismatch_blocks_or_reviews(self):
        report = check_consistency(
            source_text="2026年4月28日の楽天戦を振り返った。",
            generated_body="2026年4月27日の楽天戦を振り返った。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "hard_stop")
        self.assertIn("date_fact_mismatch", report.hard_stop_flags)

    def test_strict_subtype_postgame_score_mismatch_hard_stops(self):
        report = _check_consistency(
            source_text="巨人 1-11 楽天",
            generated_body="巨人が楽天に19-1で勝利した。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
            subtype="postgame",
        )

        self.assertEqual(report.severity, "hard_stop")
        self.assertIn("numeric_fact_mismatch", report.hard_stop_flags)

    def test_lenient_subtype_manager_comment_score_mismatch_reviews(self):
        report = _check_consistency(
            source_text="巨人 1-11 楽天",
            generated_body="巨人が楽天に19-1で勝利した。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
            subtype="manager_comment",
        )

        self.assertEqual(report.severity, "review")
        self.assertEqual(report.hard_stop_flags, ())
        self.assertIn("numeric_fact_mismatch", report.review_flags)

    def test_lenient_subtype_player_comment_pitcher_confusion_reviews(self):
        report = _check_consistency(
            source_text="先発戸郷は5回3安打2失点。巨人は11安打を放った。",
            generated_body="戸郷が11被安打で崩れた。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
            subtype="player_comment",
        )

        self.assertEqual(report.severity, "review")
        self.assertEqual(report.hard_stop_flags, ())
        self.assertIn("pitcher_team_stat_confusion", report.review_flags)

    def test_default_subtype_score_mismatch_reviews(self):
        report = _check_consistency(
            source_text="巨人 1-11 楽天",
            generated_body="巨人が楽天に19-1で勝利した。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
            subtype="default",
        )

        self.assertEqual(report.severity, "review")
        self.assertEqual(report.hard_stop_flags, ())
        self.assertIn("numeric_fact_mismatch", report.review_flags)

    def test_legacy_call_without_subtype_default_to_review_safe_side(self):
        report = _check_consistency(
            source_text="巨人 1-11 楽天",
            generated_body="巨人が楽天に19-1で勝利した。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "review")
        self.assertEqual(report.hard_stop_flags, ())
        self.assertIn("numeric_fact_mismatch", report.review_flags)

    def test_strict_subtype_farm_result_score_fabrication_hard_stops(self):
        report = _check_consistency(
            source_text="二軍 巨人 1-11 楽天",
            generated_body="二軍の巨人が楽天に19-1で勝利した。",
            x_candidates=[],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
            subtype="farm_result",
        )

        self.assertEqual(report.severity, "hard_stop")
        self.assertIn("numeric_fact_mismatch", report.hard_stop_flags)

    def test_x_candidate_score_mismatch_suppresses_x_only(self):
        report = check_consistency(
            source_text="巨人 1-11 楽天",
            generated_body="巨人は楽天に1-11で敗れた。",
            x_candidates=["巨人が楽天に19-1で勝利。https://yoshilover.com/post-1/"],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "x_candidate_suppress")
        self.assertEqual(report.hard_stop_flags, ())
        self.assertEqual(report.review_flags, ())
        self.assertIn("x_post_numeric_mismatch", report.x_candidate_suppress_flags)

    def test_x_candidate_unverified_player_name_suppresses_x_only(self):
        report = check_consistency(
            source_text="巨人が楽天に3-2で勝利した。",
            generated_body="巨人が楽天に3-2で勝利した。",
            x_candidates=["戸郷翔征が完投した試合を更新。https://yoshilover.com/post-1/"],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "x_candidate_suppress")
        self.assertIn("x_post_unverified_player_name", report.x_candidate_suppress_flags)

    def test_good_postgame_numeric_facts_pass(self):
        report = check_consistency(
            source_text="2026年4月28日 巨人 3-2 阪神。戸郷翔征は7回2安打1失点。巨人は11安打。",
            generated_body="4月28日、巨人が阪神に3-2で勝利した。戸郷翔征が7回2安打1失点。打線は11安打で競り勝った。",
            x_candidates=["巨人の試合結果を更新しました。巨人が阪神に3-2で勝利した。https://yoshilover.com/post-1/"],
            metadata={},
            publish_time_iso="2026-04-28T21:00:00+09:00",
        )

        self.assertEqual(report.severity, "pass")
        self.assertEqual(report.hard_stop_flags, ())
        self.assertEqual(report.review_flags, ())
        self.assertEqual(report.x_candidate_suppress_flags, ())


if __name__ == "__main__":
    unittest.main()
