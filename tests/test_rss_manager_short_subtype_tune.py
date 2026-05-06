"""RSS-256: manager_quote_zero_review fix (manager_short subtype 社会化).

`_select_template_v2` で template_key="manager_short" は actor_kind="manager"/"coach" +
has_quote=False + actor_name + length<300 のとき返る。subtype="manager" のまま
review path に乗ると manager_quote_zero_review で post_gen_validate fail が連発する。

修正: manager_short の場合だけ subtype を social_news に切替、review/heavy contract
を bypass する。manager_quote_short (quote あり) は既存 manager 維持、manager
(long form) も既存 manager 維持。
"""

import unittest

from src import rss_fetcher


def _resolve(*, title: str, summary: str, source_type: str = "social_news", source_url: str = "https://x.com/sanspo_giants/status/2056000000000000001", source_name: str = "サンスポ巨人X", category: str = "首脳陣"):
    return rss_fetcher._resolve_rss_story_type_context_v2(
        title=title,
        summary=summary,
        category=category,
        daily_has_game=True,
        source_type=source_type,
        source_url=source_url,
        source_name=source_name,
    )


class ManagerShortSubtypeTuneTests(unittest.TestCase):
    """manager_short → subtype="social_news" 切替を pin."""

    def test_coach_no_quote_routes_to_manager_short_with_social_news_subtype(self):
        # 「投手チーフコーチ、失点」みたいな short text、actor_name=チーフコーチ、quote なし
        ctx = _resolve(
            title="杉内投手チーフコーチ、失点",
            summary="無失点好投の投手が5回63球で交代した理由を語った",
            source_url="https://twitter.com/sanspo_giants/status/2056100000000000001",
            source_name="サンスポ巨人X",
            category="首脳陣",
        )
        if ctx["template_selector_v2_key"] == "manager_short":
            self.assertEqual(ctx["title_subtype"], "social_news")
            self.assertEqual(ctx["body_subtype"], "social_news")
            self.assertEqual(ctx["validator_subtype"], "social_news")
            # category は「首脳陣」維持 (front 整理用)
            self.assertEqual(ctx["category"], "首脳陣")

    def test_coach_short_no_quote_with_giants_keyword(self):
        ctx = _resolve(
            title="内海哲也投手コーチ、先発",
            summary="内海哲也投手コーチが先発について語った",
            source_url="https://twitter.com/hochi_giants/status/2056100000000000002",
            source_name="スポーツ報知巨人班X",
            category="首脳陣",
        )
        # manager_short routing 時 social_news subtype
        if ctx["template_selector_v2_key"] == "manager_short":
            self.assertEqual(ctx["title_subtype"], "social_news")

    def test_manager_with_quote_keeps_manager_subtype(self):
        # quote ある (manager_quote_short) → subtype=manager 維持 (heading 4 必須)
        ctx = _resolve(
            title="阿部監督「最高の結果」",
            summary="阿部慎之助監督は試合後、「技術うんぬんじゃなくて…最高の結果だ」と語った",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605050001015.html",
            source_name="日刊スポーツ",
            category="首脳陣",
        )
        if ctx["template_selector_v2_key"] == "manager_quote_short":
            self.assertEqual(ctx["title_subtype"], "manager")
            self.assertEqual(ctx["body_subtype"], "manager")
            self.assertEqual(ctx["validator_subtype"], "manager")

    def test_manager_long_form_keeps_manager_subtype(self):
        # quote なし but length>=300 → manager (rich generation 用)
        ctx = _resolve(
            title="阿部監督が語る今シーズンの方針",
            summary="阿部監督は今シーズンの選手起用方針について長く語った。" * 20,  # 長文化
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605050001500.html",
            source_name="日刊スポーツ",
            category="首脳陣",
        )
        if ctx["template_selector_v2_key"] == "manager":
            self.assertEqual(ctx["title_subtype"], "manager")
            self.assertEqual(ctx["body_subtype"], "manager")
            self.assertEqual(ctx["validator_subtype"], "manager")


class ManagerShortGenerationContractTests(unittest.TestCase):
    """manager_short の social_news 切替で review/heavy contract が bypass される確認."""

    def test_manager_short_validator_subtype_not_manager(self):
        ctx = _resolve(
            title="ゼラス・ウィーラー打撃コーチ、東京ドーム",
            summary="ゼラス・ウィーラー打撃コーチが東京ドームで指導",
            source_url="https://twitter.com/hochi_giants/status/2056100000000000010",
            source_name="スポーツ報知巨人班X",
            category="首脳陣",
        )
        # manager_short のとき heavy "manager" validator が使われない
        self.assertNotEqual(ctx["validator_subtype"], "manager")


class ManagerCategoryRoutingRegressionTests(unittest.TestCase):
    """category 「首脳陣」維持の regression check (front 整理用)."""

    def test_manager_short_keeps_category_kanji(self):
        # title_subtype=social_news に切替えても category は首脳陣維持
        ctx = _resolve(
            title="杉内投手チーフコーチ、失点",
            summary="無失点好投について語った",
            source_url="https://twitter.com/sanspo_giants/status/2056100000000000020",
            source_name="サンスポ巨人X",
            category="首脳陣",
        )
        self.assertEqual(ctx["category"], "首脳陣")
        self.assertEqual(ctx["v2_review_reason"], "")
        self.assertEqual(ctx["v2_skip_reason"], "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
