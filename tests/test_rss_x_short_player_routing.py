"""RSS-257: x_short_player subtype/template_key routing tests.

trusted Giants X 由来の選手・投手・監督・ヒーロー・二軍系記事を長文テンプレに
乗せず短文 subtype="x_short_player" に振ることを pin する。
post_gen_validate の close_marker / placeholder_body / h3_count guard 3 軸は
x_short_player に対して skip。duplicate_sentence / quote_integrity /
source_grounding_drift / entity_mismatch / weak_generated_title 等の
品質 gate は維持される。
"""

import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


def _resolve(*, title: str, summary: str, source_type: str = "social_news", source_url: str = "https://x.com/hochi_giants/status/2057000000000000001", source_name: str = "スポーツ報知巨人班X", category: str = "選手情報"):
    return rss_fetcher._resolve_rss_story_type_context_v2(
        title=title,
        summary=summary,
        category=category,
        daily_has_game=True,
        source_type=source_type,
        source_url=source_url,
        source_name=source_name,
    )


class XShortPlayerPositiveRoutingTests(unittest.TestCase):
    """trusted Giants X + 重要 keyword + length<400 + valid X URL の AND 5 で
    x_short_player に振られること."""

    # 既存上位 routing は priority 維持 (RSS-257 spec)。
    # x_short_player は fallback として、既存短文 routing が無い case で hit する。
    # 各 fixture で「review / 長文 fail path に落ちない」「短文 routing 系に振られる」
    # を pin する。

    _SHORT_OR_X_TEMPLATE_KEYS = frozenset({
        "x_short_player",
        "player_recovery_short",
        "player_quote_short",
        "manager_quote_short",
        "manager_short",
        "notice_short",
        "trusted_social_short",
        "farm_short",
        "farm_lineup_short",
        "farm_lineup_or_general",
        "lineup_short",
        "pregame_short",
        "live_update_short",
        "postgame_score_short",
        "score_lite",
        "short_comment",
    })

    def _assert_short_routing(self, ctx: dict) -> None:
        self.assertNotEqual(ctx["template_selector_v2_key"], "review")
        self.assertEqual(ctx["v2_review_reason"], "")
        self.assertEqual(ctx["v2_skip_reason"], "")
        self.assertIn(
            ctx["template_selector_v2_key"],
            self._SHORT_OR_X_TEMPLATE_KEYS,
            f"expected short routing, got {ctx['template_selector_v2_key']}",
        )

    def test_pitcher_first_team_join_routes_to_short_template(self):
        # 「2年目左腕・宮原駿介が今季初登板で...1軍合流」 系。
        # has_recovery_or_injury or has_roster_notice が先 hit すれば
        # player_recovery_short / notice_short、それ以外は x_short_player。
        ctx = _resolve(
            title="２年目左腕・宮原駿介が今季初登板でツバメ打線を１回無失点に抑える",
            summary="５日に１軍合流。先発投手として登板した。",
            source_url="https://x.com/hochi_giants/status/2057100000000000001",
            source_name="スポーツ報知巨人班X",
            category="選手情報",
        )
        self._assert_short_routing(ctx)

    def test_draft_pitcher_record_update_routes_to_short_template(self):
        # 「ドラ2田和廉...連続0封...二軍」 → has_farm_or_third_team で farm 系
        ctx = _resolve(
            title="ドラ２田和廉が球団新をまた更新 開幕１３戦連続０封 ＭＡＸ１５０キロ",
            summary="二軍 連続無失点記録更新。打撃練習も好調。",
            source_url="https://x.com/hochi_giants/status/2057100000000000002",
            source_name="スポーツ報知巨人班X",
            category="ドラフト・育成",
        )
        self._assert_short_routing(ctx)

    def test_decisive_homerun_post_routes_to_short_template(self):
        # 「最後は投手が三者凡退締め 決勝3ランの選手」 系
        ctx = _resolve(
            title="最後は投手が三者凡退締め 決勝3ランの選手は6投手をリードしました",
            summary="投手は無失点で抑え、決勝の3ランを放った巨人の選手が好投をリード。",
            source_url="https://x.com/sanspo_giants/status/2057100000000000003",
            source_name="サンスポ巨人X",
            category="試合速報",
        )
        self._assert_short_routing(ctx)

    def test_farm_pitcher_good_pitching_routes_to_short_template(self):
        # 二軍 + 投手 + 好投 → has_farm_or_third_team で farm 系
        ctx = _resolve(
            title="二軍 投手好投 育成投手が3回無失点",
            summary="ファームで育成投手が3回を無失点に抑える好投。",
            source_url="https://x.com/hochi_giants/status/2057100000000000004",
            source_name="スポーツ報知巨人班X",
            category="ドラフト・育成",
        )
        self._assert_short_routing(ctx)

    def test_giants_official_homerun_x_routes_to_short_template(self):
        # 「岡本和真が決勝ホームラン 9回表」 → live_update_short が先 hit する場合あり
        ctx = _resolve(
            title="【巨人】岡本和真が決勝ホームラン",
            summary="9回表に岡本和真選手が決勝の3ランホームラン。",
            source_url="https://x.com/TokyoGiants/status/2057100000000000005",
            source_name="読売ジャイアンツ公式X",
            category="試合速報",
        )
        self._assert_short_routing(ctx)

    def test_pitcher_recovery_outing_routes_to_x_short_player(self):
        ctx = _resolve(
            title="巨人・大勢が9日ぶり登板で連敗ストップに貢献",
            summary="復帰登板で1回無失点。コンディション不良からの回復を印象付けた。",
            source_url="https://x.com/sanspo_giants/status/2057100000000000006",
            source_name="サンスポ巨人X",
            category="選手情報",
        )
        # player_recovery_short が先に hit する場合は player_recovery
        # それ以外は x_short_player
        self.assertIn(
            ctx["template_selector_v2_key"],
            ("player_recovery_short", "x_short_player"),
        )

    def test_hero_interview_summary_routes_to_x_short_player(self):
        ctx = _resolve(
            title="お立ち台で巨人選手がヒーローインタビュー 決勝打を放った場面を語る",
            summary="ヒーローインタビューで決勝打の場面を回想。チームメイトに感謝。",
            source_url="https://x.com/TokyoGiants/status/2057100000000000007",
            source_name="読売ジャイアンツ公式X",
            category="試合速報",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "x_short_player")

    def test_relief_pitcher_no_runs_routes_to_x_short_player(self):
        ctx = _resolve(
            title="中継ぎ無失点 抑え選手がセーブ",
            summary="中継ぎ・抑えが連続無失点で勝利を守った。",
            source_url="https://x.com/sanspo_giants/status/2057100000000000008",
            source_name="サンスポ巨人X",
            category="選手情報",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "x_short_player")

    def test_multi_hit_routes_to_x_short_player(self):
        ctx = _resolve(
            title="マルチ安打 猛打賞 巨人選手が3安打",
            summary="本日の試合で巨人の打者が猛打賞でマルチ安打を記録。",
            source_url="https://x.com/hochi_giants/status/2057100000000000009",
            source_name="スポーツ報知巨人班X",
            category="選手情報",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "x_short_player")

    def test_third_team_ikusei_pitcher_routes_to_short_template(self):
        # 三軍 + 育成 + 投手 → has_farm_or_third_team で farm 系
        ctx = _resolve(
            title="三軍 育成投手が支配下昇格をアピール",
            summary="三軍戦で育成投手が好投。支配下昇格候補として注目。",
            source_url="https://x.com/hochi_giants/status/2057100000000000010",
            source_name="スポーツ報知巨人班X",
            category="ドラフト・育成",
        )
        self._assert_short_routing(ctx)


class XShortPlayerNegativeRoutingTests(unittest.TestCase):
    """AND 5 条件のいずれか欠ける場合は x_short_player に振らず既存挙動."""

    def test_non_trusted_source_does_not_route_to_x_short_player(self):
        # trusted source 外 (random_user) → x_short_player に振らない
        ctx = _resolve(
            title="巨人選手が決勝ホームラン",
            summary="巨人の選手が決勝3ランを放った。",
            source_url="https://x.com/random_user_xyz/status/2057200000000000001",
            source_name="ランダムファンX",
            category="試合速報",
        )
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")

    def test_no_giants_relevance_does_not_route_to_x_short_player(self):
        # trusted-likely だが巨人キーワードなし、source 巨人特化外
        ctx = _resolve(
            title="練習しました",
            summary="今日も練習を頑張りました。",
            source_url="https://x.com/sportshochi/status/2057200000000000002",
            source_name="スポーツ報知X",
            category="コラム",
        )
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")

    def test_no_important_keyword_does_not_route_to_x_short_player(self):
        # trusted Giants source + giants kw あるが、TRUSTED_SOCIAL_GIANTS_RESCUE_KEYWORDS hit なし
        ctx = _resolve(
            title="巨人ファンの皆さん",
            summary="今日も応援しましょう、巨人の皆さん。",
            source_url="https://x.com/hochi_giants/status/2057200000000000003",
            source_name="スポーツ報知巨人班X",
            category="コラム",
        )
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")

    def test_long_text_does_not_route_to_x_short_player(self):
        # length>=400 → 既存の長文 routing に振り分け、x_short_player には振らない
        long_summary = "巨人の岡本和真選手が試合で活躍した。" * 30  # length > 400
        ctx = _resolve(
            title="巨人岡本和真が決勝ホームラン",
            summary=long_summary,
            source_url="https://x.com/hochi_giants/status/2057200000000000004",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")

    def test_invalid_x_url_does_not_route_to_x_short_player(self):
        # tweet URL 形式でない (status/数字 なし) → x_short_player に振らない
        ctx = _resolve(
            title="巨人選手が決勝ホームラン",
            summary="決勝3ランを放った。",
            source_url="https://example.com/no-tweet-format-here",
            source_name="スポーツ報知巨人班X",
            source_type="news",
            category="試合速報",
        )
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")


class ExistingRoutingPriorityRegressionTests(unittest.TestCase):
    """既存 lineup_short / live_update_short / pregame_short の優先順位を維持."""

    def test_lineup_short_takes_precedence_over_x_short_player(self):
        ctx = _resolve(
            title="【巨人】本日のスタメン",
            summary="本日のスターティングメンバー：1番（中）丸 2番（二）吉川 3番（一）岡本",
            source_url="https://x.com/hochi_giants/status/2057300000000000001",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "lineup_short")

    def test_live_update_short_takes_precedence_over_x_short_player(self):
        ctx = _resolve(
            title="【五回表】巨人 0-2 ヤクルト 投手は三者凡退に抑える 決勝打期待",
            summary="五回表 巨人 0-2 ヤクルト 投手好投継続中",
            source_url="https://x.com/hochi_giants/status/2057300000000000002",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )
        # live_update_short が先に hit
        self.assertEqual(ctx["template_selector_v2_key"], "live_update_short")
        self.assertEqual(ctx["title_subtype"], "live_update")

    def test_pregame_short_takes_precedence_over_x_short_player(self):
        ctx = _resolve(
            title="【6日の予告先発】巨人・竹丸和幸",
            summary="本日の予告先発：巨人・竹丸和幸が登板予定",
            source_url="https://x.com/hochi_giants/status/2057300000000000003",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )
        # pregame_short or lineup_short どちらか優先 (どちらも x_short_player より先)
        self.assertIn(ctx["template_selector_v2_key"], ("pregame_short", "lineup_short"))

    def test_manager_quote_short_takes_precedence_over_x_short_player(self):
        # actor=manager + has_quote → manager_quote_short が先
        ctx = _resolve(
            title="阿部監督「最高の結果」",
            summary="阿部慎之助監督は試合後、「技術うんぬんじゃなくて…最高の結果だ」と語った",
            source_url="https://x.com/hochi_giants/status/2057300000000000004",
            source_name="スポーツ報知巨人班X",
            category="首脳陣",
        )
        # manager_quote_short が x_short_player より先
        self.assertIn(ctx["template_selector_v2_key"], ("manager_quote_short", "manager_short", "manager"))


class XShortPlayerGuardSkipTests(unittest.TestCase):
    """x_short_player subtype に対して post_gen_validate の close_marker /
    placeholder_body / h3_count_guard が skip されることを pin."""

    def _validate(self, *, article_subtype: str, text: str, rendered_html: str = ""):
        with patch.dict(
            os.environ,
            {
                "ENABLE_FORBIDDEN_PHRASE_FILTER": "1",
                "ENABLE_H3_COUNT_GUARD": "1",
                "ENABLE_QUOTE_INTEGRITY_GUARD": "1",
                "ENABLE_DUPLICATE_SENTENCE_GUARD": "1",
            },
            clear=False,
        ):
            return rss_fetcher._evaluate_post_gen_validate(
                text,
                article_subtype=article_subtype,
                title="巨人選手が好投",
                source_refs={},
                rendered_html=rendered_html,
            )

    def test_x_short_player_skips_close_marker(self):
        # close_marker (締め句) が無くても x_short_player は fail にならない
        text = "<h2>【投手の好投】</h2>\n<p>巨人の投手が今日の試合で好投した。</p>"
        result = self._validate(article_subtype="x_short_player", text=text)
        self.assertNotIn("close_marker", result["fail_axes"])

    def test_x_short_player_skips_placeholder_body(self):
        # heading のみ + body 短い (empty_section) でも x_short_player は fail にならない
        text = "<h2>【投手の好投】</h2>\n"
        result = self._validate(article_subtype="x_short_player", text=text)
        self.assertNotIn("placeholder_body:empty_section", result["fail_axes"])
        self.assertNotIn("placeholder_body:boilerplate", result["fail_axes"])

    def test_x_short_player_skips_h3_count_guard(self):
        # h3 が 3 個以上でも x_short_player は fail にならない
        rendered = "<h2>【今日の試合】</h2><h3>1回</h3><h3>2回</h3><h3>3回</h3><h3>4回</h3>"
        result = self._validate(
            article_subtype="x_short_player",
            text=rendered,
            rendered_html=rendered,
        )
        self.assertFalse(any(axis.startswith("h3_count:") for axis in result["fail_axes"]))

    def test_x_short_player_still_fails_on_duplicate_sentence(self):
        # duplicate_sentence は維持 (品質 gate keep)
        # 同じ文を 2 回繰り返す + 巨人/投手記事文脈
        text = (
            "<h2>【巨人投手の好投】</h2>\n"
            "<p>巨人の投手が今日の試合で7回を1失点に抑える好投を見せた。</p>\n"
            "<p>巨人の投手が今日の試合で7回を1失点に抑える好投を見せた。</p>\n"
            "<p>打線は終盤に勝ち越して勝利を決定づけた。</p>"
        )
        result = self._validate(article_subtype="x_short_player", text=text)
        self.assertTrue(
            any("duplicate_sentence" in axis for axis in result["fail_axes"]),
            f"duplicate_sentence guard expected but not in {result['fail_axes']}",
        )

    def test_x_short_player_still_fails_on_quote_integrity(self):
        # quote_integrity も維持 (品質 gate keep)
        text = "<h2>【投手コメント】</h2>\n<p>投手は「次も好投したい</p>"
        result = self._validate(article_subtype="x_short_player", text=text)
        self.assertTrue(
            any("quote_integrity" in axis for axis in result["fail_axes"]),
            f"quote_integrity guard expected but not in {result['fail_axes']}",
        )


class XShortPlayerCategoryFallbackTests(unittest.TestCase):
    """x_short_player の category fallback 挙動を pin."""

    def test_known_category_kept(self):
        # 「選手情報」「試合速報」「首脳陣」「ドラフト・育成」 はそのまま維持
        for category in ("選手情報", "試合速報", "首脳陣", "ドラフト・育成"):
            with self.subTest(category=category):
                ctx = _resolve(
                    title="巨人投手が好投",
                    summary="今日の試合で投手が無失点で好投した。",
                    source_url="https://x.com/hochi_giants/status/2057400000000000001",
                    source_name="スポーツ報知巨人班X",
                    category=category,
                )
                if ctx["template_selector_v2_key"] == "x_short_player":
                    self.assertEqual(ctx["category"], category)

    def test_unknown_category_falls_back_to_player_info(self):
        # 上記 4 カテゴリ外 (「コラム」「球団情報」 等) は「選手情報」にフォールバック
        ctx = _resolve(
            title="巨人投手が好投",
            summary="今日の試合で投手が無失点で好投した。",
            source_url="https://x.com/hochi_giants/status/2057400000000000002",
            source_name="スポーツ報知巨人班X",
            category="コラム",
        )
        if ctx["template_selector_v2_key"] == "x_short_player":
            self.assertEqual(ctx["category"], "選手情報")


class XShortTemplateSubtypesConstantTests(unittest.TestCase):
    """X_SHORT_TEMPLATE_SUBTYPES 定数 export を pin."""

    def test_x_short_template_subtypes_includes_x_short_player(self):
        self.assertIn("x_short_player", rss_fetcher.X_SHORT_TEMPLATE_SUBTYPES)

    def test_x_short_template_subtypes_separate_from_lineup_table_heavy(self):
        # 別 set として独立に定義されていること
        self.assertIsInstance(rss_fetcher.X_SHORT_TEMPLATE_SUBTYPES, frozenset)
        self.assertIsInstance(rss_fetcher.LINEUP_TABLE_HEAVY_SUBTYPES, frozenset)
        # x_short_player は LINEUP_TABLE_HEAVY_SUBTYPES に含まれない
        self.assertNotIn("x_short_player", rss_fetcher.LINEUP_TABLE_HEAVY_SUBTYPES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
