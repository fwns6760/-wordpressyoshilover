import logging
import unittest

from src import rss_fetcher
from src.title_player_name_backfiller import backfill_title_player_name


class TitlePlayerNameBackfillTests(unittest.TestCase):
    def test_lineup_title_backfills_name_from_source_body(self):
        result = backfill_title_player_name(
            existing_title='巨人スタメン が「2番・二塁」で今季初先発',
            source_title='巨人スタメン が「2番・二塁」で今季初先発',
            body="吉川尚輝が「2番・二塁」で今季初先発となった。",
            metadata={"role": "選手"},
        )

        self.assertEqual(result.title, '吉川尚輝が「2番・二塁」で今季初先発')
        self.assertTrue(result.changed)
        self.assertEqual(result.review_reason, "")

    def test_comment_title_backfills_speaker_and_quote(self):
        result = backfill_title_player_name(
            existing_title="投手コメント整理",
            source_title='山田太郎投手「真っすぐで押せた」試合後コメント',
            body='山田太郎投手が試合後に「真っすぐで押せた」と振り返った。',
            metadata={"speaker": "山田太郎"},
        )

        self.assertEqual(result.title, '山田太郎投手「真っすぐで押せた」試合後コメント')
        self.assertEqual(result.review_reason, "")

    def test_unresolved_title_returns_source_title_and_review_reason(self):
        result = backfill_title_player_name(
            existing_title="選手、登録抹消 関連情報",
            source_title="選手、登録抹消 関連情報",
            body="球団が登録抹消を発表した。",
        )

        self.assertEqual(result.title, "選手、登録抹消 関連情報")
        self.assertEqual(result.review_reason, "title_player_name_unresolved")

    def test_generic_one_word_titles_backfill_or_emit_review_reason(self):
        cases = [
            {
                "title": "選手",
                "body": "吉川尚輝選手がスタメン入りした。",
                "metadata": {},
                "expected_title": "吉川尚輝",
                "expected_reason": "",
            },
            {
                "title": "投手",
                "body": "山田太郎投手がブルペン入りした。",
                "metadata": {"speaker": "山田太郎"},
                "expected_title": "山田太郎投手",
                "expected_reason": "",
            },
            {
                "title": "チーム",
                "body": "球団がコメントを発表した。",
                "metadata": {},
                "expected_title": "チーム",
                "expected_reason": "title_player_name_unresolved",
            },
        ]

        for case in cases:
            with self.subTest(title=case["title"]):
                result = backfill_title_player_name(
                    existing_title=case["title"],
                    source_title=case["title"],
                    body=case["body"],
                    metadata=case["metadata"],
                )
                self.assertEqual(result.title, case["expected_title"])
                self.assertEqual(result.review_reason, case["expected_reason"])

    def test_player_role_generic_title_backfills_from_source_body(self):
        cases = [
            {
                "title": "外野手が打撃練習で快音",
                "source_title": "外野手が打撃練習で快音",
                "body": "浅野翔吾外野手が打撃練習で快音を響かせた。",
                "expected": "浅野翔吾が打撃練習で快音",
            },
            {
                "title": "捕手、母の日仕様の用具を準備",
                "source_title": "捕手、母の日仕様の用具を準備",
                "body": "山瀬慎之助捕手、母の日仕様の用具を準備した。",
                "expected": "山瀬慎之助、母の日仕様の用具を準備",
            },
        ]

        for case in cases:
            with self.subTest(title=case["title"]):
                result = backfill_title_player_name(
                    existing_title=case["title"],
                    source_title=case["source_title"],
                    body=case["body"],
                    metadata={"role": "選手"},
                )

                self.assertEqual(result.title, case["expected"])
                self.assertEqual(result.review_reason, "")

    def test_x_post_hashtag_player_name_replaces_generic_player_word_without_suffix(self):
        result = backfill_title_player_name(
            existing_title="選手、昇格・復帰 関連情報",
            source_title="スポーツ報知巨人班Xが若手選手の調整を紹介",
            body="ジャイアンツ球場 #浦田俊輔 選手が一軍合流へ向けて調整を続けている。",
            summary="ジャイアンツ球場 #浦田俊輔 選手が一軍合流へ向けて調整を続けている。",
            metadata={"role": "選手"},
        )

        self.assertEqual(result.title, "浦田俊輔、昇格・復帰 関連情報")
        self.assertNotIn("選手", result.title)
        self.assertEqual(result.review_reason, "")

    def test_x_post_body_name_replaces_generic_compound_player_title(self):
        result = backfill_title_player_name(
            existing_title="実施選手、昇格・復帰 関連情報",
            source_title="サンスポ巨人Xが選手の復帰調整を紹介",
            body="#平山功太 選手が右アキレス腱炎からの復帰を目指してブルペン投球を実施。",
            summary="#平山功太 選手が右アキレス腱炎からの復帰を目指してブルペン投球を実施。",
            metadata={"role": "選手"},
        )

        self.assertEqual(result.title, "平山功太、昇格・復帰 関連情報")
        self.assertNotIn("実施選手", result.title)
        self.assertEqual(result.review_reason, "")

    def test_fetcher_adapter_uses_x_post_name_and_does_not_leave_player_word(self):
        final_title, comparison_title = rss_fetcher._apply_title_player_name_backfill(
            rewritten_title="選手、昇格・復帰 関連情報",
            source_title="スポーツ報知巨人班Xが若手選手の調整を紹介",
            source_body="ジャイアンツ球場 #浦田俊輔 選手が一軍合流へ向けて調整を続けている。",
            summary="ジャイアンツ球場 #浦田俊輔 選手が一軍合流へ向けて調整を続けている。",
            category="選手情報",
            article_subtype="player",
            logger=logging.getLogger("rss_fetcher"),
            source_name="スポーツ報知巨人班X",
            source_url="https://twitter.com/hochi_giants/status/1",
        )

        self.assertEqual(final_title, "浦田俊輔、昇格・復帰 関連情報")
        self.assertNotIn("選手", final_title)
        self.assertEqual(comparison_title, "スポーツ報知巨人班Xが若手選手の調整を紹介")

    def test_fetcher_adapter_uses_x_post_name_for_generic_compound_player_title(self):
        final_title, comparison_title = rss_fetcher._apply_title_player_name_backfill(
            rewritten_title="実施選手、昇格・復帰 関連情報",
            source_title="サンスポ巨人Xが選手の復帰調整を紹介",
            source_body="#平山功太 選手が右アキレス腱炎からの復帰を目指してブルペン投球を実施。",
            summary="#平山功太 選手が右アキレス腱炎からの復帰を目指してブルペン投球を実施。",
            category="選手情報",
            article_subtype="player",
            logger=logging.getLogger("rss_fetcher"),
            source_name="サンスポ巨人X",
            source_url="https://x.com/sanspo_giants/status/1",
        )

        self.assertEqual(final_title, "平山功太、昇格・復帰 関連情報")
        self.assertNotIn("実施選手", final_title)
        self.assertEqual(comparison_title, "サンスポ巨人Xが選手の復帰調整を紹介")

    def test_unknown_media_like_source_title_does_not_become_player_name(self):
        result = backfill_title_player_name(
            existing_title="選手、昇格・復帰 関連情報",
            source_title="ベースボールキングXが若手選手の調整を紹介",
            body="ジャイアンツ球場 #浦田俊輔 選手が一軍合流へ向けて調整を続けている。",
            summary="ジャイアンツ球場 #浦田俊輔 選手が一軍合流へ向けて調整を続けている。",
            metadata={"role": "選手"},
        )

        self.assertEqual(result.title, "浦田俊輔、昇格・復帰 関連情報")
        self.assertNotIn("ベースボールキング", result.title)
        self.assertNotIn("選手", result.title)
        self.assertEqual(result.review_reason, "")

    def test_manager_and_coach_generic_title_backfills_matching_role_only(self):
        cases = [
            {
                "title": "監督が若手起用を説明",
                "source_title": "監督が若手起用を説明",
                "body": "阿部監督が若手起用を説明した。",
                "metadata": {"speaker": "阿部", "role": "監督"},
                "expected_title": "阿部監督が若手起用を説明",
                "expected_reason": "",
            },
            {
                "title": "コーチ、守備練習を確認",
                "source_title": "コーチ、守備練習を確認",
                "body": "川相コーチ、守備練習を確認した。",
                "metadata": {"speaker": "川相", "role": "コーチ"},
                "expected_title": "川相コーチ、守備練習を確認",
                "expected_reason": "",
            },
            {
                "title": "コーチは増田陸選手の捕球練習を確認",
                "source_title": "コーチは増田陸選手の捕球練習を確認",
                "body": "増田陸選手の捕球練習を確認した。",
                "metadata": {},
                "expected_title": "コーチは増田陸選手の捕球練習を確認",
                "expected_reason": "title_player_name_unresolved",
            },
        ]

        for case in cases:
            with self.subTest(title=case["title"]):
                result = backfill_title_player_name(
                    existing_title=case["title"],
                    source_title=case["source_title"],
                    body=case["body"],
                    metadata=case["metadata"],
                )

                self.assertEqual(result.title, case["expected_title"])
                self.assertEqual(result.review_reason, case["expected_reason"])

    def test_multiple_candidates_choose_unique_frequency_leader(self):
        result = backfill_title_player_name(
            existing_title='巨人スタメン が「2番・二塁」で今季初先発',
            source_title='巨人スタメン が「2番・二塁」で今季初先発',
            body="吉川尚輝と門脇誠がスタメン入りし、吉川尚輝が2番二塁で今季初先発となった。",
            metadata={"role": "選手"},
        )

        self.assertEqual(result.title, '吉川尚輝が「2番・二塁」で今季初先発')
        self.assertNotIn("門脇誠", result.title)

    def test_multiple_candidates_tie_uses_neutral_subject_without_player_word(self):
        result = backfill_title_player_name(
            existing_title="選手、昇格・復帰 関連情報",
            source_title="複数選手の調整を紹介",
            body="#浦田俊輔 選手と #増田陸 選手が一軍合流へ向けて調整を続けている。",
            summary="#浦田俊輔 選手と #増田陸 選手が一軍合流へ向けて調整を続けている。",
            metadata={"role": "選手"},
        )

        self.assertEqual(result.title, "巨人、昇格・復帰 関連情報")
        self.assertNotIn("浦田俊輔", result.title)
        self.assertNotIn("増田陸", result.title)
        self.assertNotIn("選手", result.title)
        self.assertEqual(result.review_reason, "")

    def test_fetcher_adapter_uses_comparison_title_for_unresolved_case(self):
        final_title, comparison_title = rss_fetcher._apply_title_player_name_backfill(
            rewritten_title="投手コメント整理",
            source_title="投手コメント整理",
            source_body="投手の談話を整理した。",
            summary="投手の談話を整理した。",
            category="選手情報",
            article_subtype="player",
            logger=logging.getLogger("rss_fetcher"),
            source_name="報知 巨人",
            source_url="https://example.com/story",
        )

        fallback = rss_fetcher._maybe_route_weak_subject_title_review(
            article_subtype="player",
            rewritten_title=final_title,
            original_title=comparison_title,
            source_name="報知 巨人",
            logger=logging.getLogger("rss_fetcher"),
        )

        self.assertEqual(final_title, "投手コメント整理")
        self.assertEqual(comparison_title, "投手コメント整理")
        self.assertIsNone(fallback)

    def test_fetcher_adapter_uses_safe_title_for_nameless_social_orphan_particle(self):
        source_title = "巨人は「母の日」に投打の新星が恩返し がV2点三塁打！ が15戦連続無失点！"
        final_title, comparison_title = rss_fetcher._apply_title_player_name_backfill(
            rewritten_title=source_title,
            source_title=source_title,
            source_body="巨人は母の日に投打の新星が恩返し。V2点三塁打と15戦連続無失点が伝えられた。",
            summary="巨人は母の日に投打の新星が恩返し。V2点三塁打と15戦連続無失点が伝えられた。",
            category="試合速報",
            article_subtype="x_short_player",
            logger=logging.getLogger("rss_fetcher"),
            source_name="サンスポ巨人X",
            source_url="https://x.com/sanspo_giants/status/2057100000000012345",
        )

        self.assertEqual(final_title, "巨人「母の日」に投打で話題 サンスポ巨人Xが投稿")
        self.assertEqual(comparison_title, source_title)
        self.assertNotIn(" がV", final_title)
        self.assertNotIn(" が15戦", final_title)


if __name__ == "__main__":
    unittest.main()
