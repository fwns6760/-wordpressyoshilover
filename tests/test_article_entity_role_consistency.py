import unittest

from src.article_entity_role_consistency import (
    detect_awkward_role_phrasing,
    safe_rewrite_role_phrasing,
)


class ArticleEntityRoleConsistencyTests(unittest.TestCase):
    def test_detect_awkward_pitcher_phrase(self):
        hits = detect_awkward_role_phrasing("戸郷翔征投手となって7回2失点と好投した。")

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["match"], "戸郷翔征投手となって")
        self.assertEqual(hits[0]["name"], "戸郷翔征")
        self.assertEqual(hits[0]["role"], "投手")
        self.assertEqual(hits[0]["connector"], "となって")

    def test_detect_awkward_manager_phrase(self):
        hits = detect_awkward_role_phrasing("阿部慎之助監督となり打線の状態を確認した。")

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["match"], "阿部慎之助監督となり")
        self.assertEqual(hits[0]["name"], "阿部慎之助")
        self.assertEqual(hits[0]["role"], "監督")
        self.assertEqual(hits[0]["connector"], "となり")

    def test_detect_awkward_coach_phrase(self):
        hits = detect_awkward_role_phrasing("村田コーチとなって調整方針を説明した。")

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["match"], "村田コーチとなって")
        self.assertEqual(hits[0]["name"], "村田")
        self.assertEqual(hits[0]["role"], "コーチ")

    def test_safe_rewrite_pitcher(self):
        rewritten, rewrite_count, skipped = safe_rewrite_role_phrasing(
            "戸郷翔征投手となって7回2失点と好投した。"
        )

        self.assertEqual(rewritten, "戸郷翔征投手が7回2失点と好投した。")
        self.assertEqual(rewrite_count, 1)
        self.assertEqual(skipped, [])

    def test_safe_rewrite_manager(self):
        rewritten, rewrite_count, skipped = safe_rewrite_role_phrasing(
            "阿部慎之助監督となり打線の状態を確認した。"
        )

        self.assertEqual(rewritten, "阿部慎之助監督が打線の状態を確認した。")
        self.assertEqual(rewrite_count, 1)
        self.assertEqual(skipped, [])

    def test_no_false_positive_for_natural_phrase(self):
        hits = detect_awkward_role_phrasing("戸郷翔征投手が7回2失点と好投した。")

        self.assertEqual(hits, [])

    def test_no_false_positive_for_generic_role_subject(self):
        hits = detect_awkward_role_phrasing("先発投手となって試合を作った。")

        self.assertEqual(hits, [])

    def test_no_match_for_short_name(self):
        hits = detect_awkward_role_phrasing("阿投手となって7回を投げた。")

        self.assertEqual(hits, [])

    def test_multiple_awkward_in_one_paragraph(self):
        hits = detect_awkward_role_phrasing(
            "戸郷翔征投手となって7回2失点と好投し、阿部慎之助監督となり打線の状態を確認した。"
        )

        self.assertEqual(len(hits), 2)
        self.assertEqual([hit["match"] for hit in hits], ["戸郷翔征投手となって", "阿部慎之助監督となり"])

    def test_safe_rewrite_skips_sentence_end_case(self):
        rewritten, rewrite_count, skipped = safe_rewrite_role_phrasing(
            "巨人が調整した。阿部慎之助監督となって。"
        )

        self.assertEqual(rewritten, "巨人が調整した。阿部慎之助監督となって。")
        self.assertEqual(rewrite_count, 0)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["match"], "阿部慎之助監督となって")
        self.assertEqual(skipped[0]["reason"], "sentence_end")


if __name__ == "__main__":
    unittest.main()
