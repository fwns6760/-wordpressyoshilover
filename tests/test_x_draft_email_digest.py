import unittest

from src.x_draft_email_digest import build_x_draft_email_digest, candidate_key_from_article, normalize_candidate_key


class XDraftEmailDigestTests(unittest.TestCase):
    def _article(self, index=0, **overrides):
        article = {
            "news_family": "試合結果",
            "entity_primary": f"巨人{index}",
            "event_nucleus": f"巨人 3-{index} 阪神",
            "source_tier": "fact",
            "safe_fact": f"巨人が阪神に3-{index}で勝利しました。",
            "title": f"巨人、阪神に3-{index}で勝利",
            "published_url": f"https://yoshilover.com/archives/065-{index}/",
            "source_ref": "https://www.giants.jp/game/20260423/result/",
        }
        article.update(overrides)
        return article

    def test_candidate_key_normalization_removes_spaces_and_unifies_width(self):
        key = normalize_candidate_key(" 試合　結果 ", " Ｇｉａｎｔｓ ", " ３－２　勝利 ")

        self.assertEqual(key, ("試合結果", "giants", "3-2勝利"))

    def test_candidate_key_from_article_uses_contract_tuple(self):
        key = candidate_key_from_article(
            {
                "news_family": "コメント",
                "entity_primary": "阿部 監督",
                "event_nucleus": " 試合後 コメント ",
            }
        )

        self.assertEqual(key, ("コメント", "阿部監督", "試合後コメント"))

    def test_duplicate_candidate_key_keeps_first_and_excludes_later(self):
        articles = [
            self._article(1, entity_primary="岡本", event_nucleus="登録"),
            self._article(2, entity_primary="岡 本", event_nucleus=" 登　録 "),
            self._article(3, entity_primary="坂本", event_nucleus="登録"),
        ]

        result = build_x_draft_email_digest(articles)

        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(result.excluded_count, 1)
        self.assertEqual(result.excluded[0].hard_fail_tags, ("CANDIDATE_KEY_DUPLICATE",))
        self.assertIn("岡本", result.candidates[0].candidate_key[1])
        self.assertIn("坂本", result.candidates[1].candidate_key[1])

    def test_digest_applies_five_candidate_limit_after_valid_items(self):
        articles = [self._article(i) for i in range(6)]

        result = build_x_draft_email_digest(articles, max_candidates=5)

        self.assertEqual(len(result.candidates), 5)
        self.assertEqual(result.excluded_count, 1)
        self.assertEqual(result.excluded[0].hard_fail_tags, ("OVER_LIMIT",))

    def test_digest_excludes_hard_fail_and_keeps_soft_warning(self):
        articles = [
            self._article(1, published_url="", source_ref=""),
            self._article(2, published_url="https://yoshilover.com/?p=123&preview=true", source_ref="https://yoshilover.com/?p=123"),
        ]

        result = build_x_draft_email_digest(articles)

        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].warnings, ("SOURCE_REF_MISSING",))
        self.assertEqual(result.excluded_count, 1)
        self.assertIn("DRAFT_URL_LEAK", result.excluded[0].hard_fail_tags)


if __name__ == "__main__":
    unittest.main()
