import unittest

from src.x_draft_email_validator import (
    has_draft_url_leak,
    is_assertive_official_fact,
    validate_candidate,
    validate_digest_candidates,
)


class XDraftEmailValidatorTests(unittest.TestCase):
    def _candidate(self, **overrides):
        candidate = {
            "recommended_account": "official",
            "source_tier": "fact",
            "safe_fact": "巨人が阪神に3-2で勝利しました。",
            "official_draft": "巨人が阪神に3-2で勝利しました。\n巨人、阪神に3-2で勝利\nhttps://yoshilover.com/archives/065/",
            "official_alt": "巨人、阪神に3-2で勝利。巨人が阪神に3-2で勝利しました。\nhttps://yoshilover.com/archives/065/",
            "inner_angle": "ファン目線では、この情報をどう受け止めるかを短く添える。事実説明は公式欄に任せる。",
            "risk_note": "",
            "source_ref": "https://www.giants.jp/game/20260423/result/",
        }
        candidate.update(overrides)
        return candidate

    def test_draft_url_leak_is_hard_fail(self):
        candidate = self._candidate(source_ref="https://yoshilover.com/?p=123&preview=true")

        result = validate_candidate(candidate)

        self.assertTrue(has_draft_url_leak(candidate["source_ref"]))
        self.assertIn("DRAFT_URL_LEAK", result.hard_fail_tags)

    def test_ungrounded_official_fact_is_hard_fail_for_topic(self):
        candidate = self._candidate(
            source_tier="topic",
            official_draft="巨人が阪神に3-2で勝利しました。",
            risk_note="一次確認待ち。",
        )

        result = validate_candidate(candidate)

        self.assertTrue(is_assertive_official_fact(candidate["official_draft"]))
        self.assertIn("UNGROUNDED_OFFICIAL_FACT", result.hard_fail_tags)

    def test_official_inner_cross_contamination_detects_official_tone_leak(self):
        candidate = self._candidate(official_draft="個人的には最高の勝利でした。\nhttps://yoshilover.com/archives/065/")

        result = validate_candidate(candidate)

        self.assertIn("OFFICIAL_INNER_CROSS_CONTAMINATION", result.hard_fail_tags)

    def test_official_inner_cross_contamination_detects_inner_fact_assertion(self):
        candidate = self._candidate(inner_angle="巨人が3-2で勝利しました。中の人としても触れたい。")

        result = validate_candidate(candidate)

        self.assertIn("OFFICIAL_INNER_CROSS_CONTAMINATION", result.hard_fail_tags)

    def test_missing_risk_note_is_hard_fail_for_topic_and_reaction(self):
        for tier in ("topic", "reaction"):
            with self.subTest(tier=tier):
                candidate = self._candidate(
                    source_tier=tier,
                    official_draft="一次確認待ちの話題です。公式投稿前に事実確認してください。",
                    risk_note="",
                )

                result = validate_candidate(candidate)

                self.assertIn("MISSING_RISK_NOTE", result.hard_fail_tags)

    def test_candidate_key_duplicate_is_hard_fail_after_first(self):
        first = self._candidate()
        second = self._candidate(official_alt="別案です。")

        results = validate_digest_candidates(
            [first, second],
            [("postgame", "giants", "3-2"), ("postgame", "giants", "3-2")],
        )

        self.assertTrue(results[0].ok)
        self.assertIn("CANDIDATE_KEY_DUPLICATE", results[1].hard_fail_tags)

    def test_over_limit_is_hard_fail_for_sixth_included_candidate(self):
        candidates = [self._candidate(official_alt=f"別案 {i}") for i in range(6)]
        keys = [("family", "entity", str(i)) for i in range(6)]

        results = validate_digest_candidates(candidates, keys, max_candidates=5)

        self.assertTrue(all(result.ok for result in results[:5]))
        self.assertIn("OVER_LIMIT", results[5].hard_fail_tags)

    def test_official_alt_identical_to_draft_is_soft_fail(self):
        draft = "巨人が阪神に3-2で勝利しました。"
        result = validate_candidate(self._candidate(official_draft=draft, official_alt=draft))

        self.assertIn("OFFICIAL_ALT_IDENTICAL_TO_DRAFT", result.soft_fail_tags)
        self.assertTrue(result.ok)

    def test_safe_fact_excess_length_is_soft_fail(self):
        result = validate_candidate(self._candidate(safe_fact="あ" * 201))

        self.assertIn("SAFE_FACT_EXCESS_LENGTH", result.soft_fail_tags)
        self.assertTrue(result.ok)

    def test_source_ref_missing_is_soft_fail(self):
        result = validate_candidate(self._candidate(source_ref=""))

        self.assertIn("SOURCE_REF_MISSING", result.soft_fail_tags)
        self.assertTrue(result.ok)

    def test_fact_assertion_is_allowed_for_fact_source(self):
        result = validate_candidate(self._candidate())

        self.assertTrue(result.ok)
        self.assertEqual(result.hard_fail_tags, ())

    def test_topic_and_reaction_hedged_text_pass_with_risk_note(self):
        for tier in ("topic", "reaction"):
            with self.subTest(tier=tier):
                result = validate_candidate(
                    self._candidate(
                        source_tier=tier,
                        official_draft="一次確認待ちの話題です。公式投稿前に事実確認してください。",
                        official_alt="公式で触れる場合は、一次ソース確認後に短く紹介する。",
                        risk_note="一次情報で再確認する。",
                    )
                )

                self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
