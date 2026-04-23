from __future__ import annotations

import unittest

from src import eyecatch_fallback


class EyecatchFallbackContractTests(unittest.TestCase):
    def _draft(self, title: str, meta: dict, body_html: str = "") -> dict:
        return {
            "status": "draft",
            "title": {"raw": title},
            "content": {"raw": body_html},
            "meta": {"candidate_key": title, **meta},
        }

    def test_six_subtype_layouts_resolve_from_subtype_and_tags(self):
        cases = [
            (
                "program",
                self._draft(
                    "ジャイアンツTV 18:00 放送予定",
                    {"subtype": "fact_notice", "tags": ["番組"], "program_name": "ジャイアンツTV", "air_date": "20260421"},
                    "<p>18:00 放送予定</p>",
                ),
                "fact_notice_program",
                "番組情報",
                ["ジャイアンツTV", "2026.04.21", "18:00"],
            ),
            (
                "transaction",
                self._draft(
                    "【公示】山瀬慎之助を登録、丸佳浩を抹消",
                    {"subtype": "fact_notice", "tags": ["公示"], "players": ["山瀬慎之助", "丸佳浩"], "notice_kind": "register_deregister"},
                ),
                "fact_notice_transaction",
                "公示",
                ["山瀬慎之助", "丸佳浩", "登録 / 抹消"],
            ),
            (
                "probable_starter",
                self._draft(
                    "予告先発 巨人 vs 阪神",
                    {"subtype": "probable_starter", "matchup": "巨人 vs 阪神", "probable_starters": ["田中将大", "才木浩人"]},
                ),
                "probable_starter",
                "予告先発",
                ["巨人 vs 阪神", "田中将大", "才木浩人"],
            ),
            (
                "comment",
                self._draft(
                    "阿部慎之助監督「守備から入れた」",
                    {"subtype": "comment_notice", "speaker": "阿部慎之助監督", "scene": "試合後の一問一答"},
                ),
                "comment_notice",
                "コメント",
                ["阿部慎之助監督", "試合後の一問一答"],
            ),
            (
                "injury",
                self._draft(
                    "浅野翔吾の怪我状況",
                    {"subtype": "injury_notice", "player_name": "浅野翔吾", "status_text": "状態確認中"},
                ),
                "injury_notice",
                "怪我状況",
                ["浅野翔吾", "状態確認中"],
            ),
            (
                "postgame",
                self._draft(
                    "巨人 3-2 阪神",
                    {"subtype": "postgame", "matchup": "巨人 vs 阪神", "score": "3 - 2"},
                ),
                "postgame_result",
                "試合結果",
                ["巨人 vs 阪神", "3 - 2"],
            ),
        ]

        seen_layouts = set()
        for name, draft, layout_key, label, expected_texts in cases:
            with self.subTest(name=name):
                structured = eyecatch_fallback.generate(draft)
                self.assertIsNotNone(structured)
                assert structured is not None
                seen_layouts.add(structured.layout_key)
                self.assertEqual(structured.layout_key, layout_key)
                self.assertEqual(structured.label, label)
                rendered = structured.image_bytes.decode("utf-8")
                self.assertIn(f"structured-eyecatch-{layout_key}", structured.filename)
                for expected in expected_texts:
                    self.assertIn(expected, rendered)

        self.assertEqual(seen_layouts, set(eyecatch_fallback.LAYOUT_SPECS.keys()))

    def test_featured_image_or_og_image_skips_fallback(self):
        featured = self._draft(
            "巨人 3-2 阪神",
            {"subtype": "postgame", "matchup": "巨人 vs 阪神", "score": "3 - 2"},
        )
        featured["featured_media"] = 731
        self.assertIsNone(eyecatch_fallback.generate(featured))

        og_image = self._draft(
            "巨人 3-2 阪神",
            {"subtype": "postgame", "matchup": "巨人 vs 阪神", "score": "3 - 2", "og_image_url": "https://example.com/og.jpg"},
        )
        self.assertIsNone(eyecatch_fallback.generate(og_image))

    def test_published_post_is_not_touched(self):
        published = self._draft(
            "巨人 3-2 阪神",
            {"subtype": "postgame", "matchup": "巨人 vs 阪神", "score": "3 - 2"},
        )
        published["status"] = "publish"

        self.assertIsNone(eyecatch_fallback.generate(published))

    def test_only_bound_source_facts_are_rendered(self):
        draft = self._draft(
            "阿部慎之助監督「守備から入れた」",
            {
                "subtype": "comment_notice",
                "speaker": "阿部慎之助監督",
                "scene": "試合後コメント",
                "unrelated_fact": "東京ドームで満員",
                "phantom_player": "坂本勇人",
            },
        )

        structured = eyecatch_fallback.generate(draft)

        self.assertIsNotNone(structured)
        assert structured is not None
        rendered = structured.image_bytes.decode("utf-8")
        self.assertIn("阿部慎之助監督", rendered)
        self.assertIn("試合後コメント", rendered)
        self.assertNotIn("東京ドームで満員", rendered)
        self.assertNotIn("坂本勇人", rendered)

    def test_common_no_image_is_not_used_and_long_text_is_ellipsized(self):
        draft = self._draft(
            "非常に長い番組名が続いて一覧で折り返しても安全に見える特別中継プログラム",
            {"subtype": "fact_notice", "tags": ["番組"], "air_date": "20260421"},
            "<p>18:00 放送予定</p>",
        )

        structured = eyecatch_fallback.generate(draft)

        self.assertIsNotNone(structured)
        assert structured is not None
        rendered = structured.image_bytes.decode("utf-8")
        self.assertTrue(rendered.startswith("<svg"))
        self.assertIn("…", rendered)
        self.assertNotIn("noimage", rendered.lower())
        self.assertNotIn("no_image", rendered.lower())


if __name__ == "__main__":
    unittest.main()
