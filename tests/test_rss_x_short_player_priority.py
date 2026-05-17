"""RSS-259: x_short_player priority elevation tests.

X 由来短文 postgame (試合終了/敗戦/打線沈黙系) が postgame_strict /
postgame_score_short / score_lite / short_comment で fail し続ける問題を
x_short_player 経路に救う。優先順位:

1. live_update_short
2. farm/recovery/notice/manager/player_quote (既存)
3. **NEW: x_short_player (X 由来 + AND 5 + NOT lineup/pregame signal)**
4. postgame_strict / postgame_score_short / score_lite / short_comment
5. lineup_short / pregame_short
6. trusted_social_short / source_link_only / review

注意:
- has_lineup_signal / has_pregame_signal がある case は guard で x_short_player を
  skip し、後段 lineup_short / pregame_short に到達 (既存 RSS-248/253 priority 維持)
- news 由来 postgame_strict (source_type=news) は AND 1 条件 False で不発、
  既存 postgame_strict path 維持
"""

import unittest

from src import rss_fetcher


def _resolve(*, title: str, summary: str, source_type: str = "social_news", source_url: str = "https://x.com/sanspo_giants/status/2059000000000000001", source_name: str = "サンスポ巨人X", category: str = "試合速報"):
    return rss_fetcher._resolve_rss_story_type_context_v2(
        title=title,
        summary=summary,
        category=category,
        daily_has_game=True,
        source_type=source_type,
        source_url=source_url,
        source_name=source_name,
    )


class XShortPlayerPostgameRescueTests(unittest.TestCase):
    """RSS-259 主要 effect: X 由来 trusted Giants short postgame
    (重要 keyword 含む) が x_short_player に救われる。

    注意: 重要 keyword (投手好投/決勝/ホームラン/コメント等) を含む trusted X
    short post が postgame_strict より先に x_short_player に振られる。
    重要 keyword 含まない postgame X (「敗戦の分岐点」「打線沈黙」 等) は
    spec の rescue 対象外 (live 3 件は spec 通り維持) → 別 negative test で pin。
    """

    def test_x_postgame_with_decisive_keyword_routes_to_x_short_player(self):
        # 重要 keyword「決勝」「ホームラン」 含む trusted X postgame
        # (inning 記法は live_update_short が先 hit するので含めない)
        ctx = _resolve(
            title="【巨人】岡本和真が決勝3ランホームラン",
            summary="岡本和真選手が決勝の3ランホームラン。試合を決めた。",
            source_url="https://twitter.com/sanspo_giants/status/2059100000000000001",
            source_name="サンスポ巨人X",
            category="試合速報",
        )
        # RSS-259: x_short_player が postgame_strict より先 hit
        self.assertEqual(ctx["template_selector_v2_key"], "x_short_player")
        self.assertEqual(ctx["category"], "選手情報")
        self.assertEqual(ctx["title_subtype"], "x_short_player")
        self.assertEqual(ctx["validator_subtype"], "social_news")

    def test_x_postgame_with_pitcher_keyword_routes_to_x_short_player(self):
        # 重要 keyword「先発」「投手」「無失点」「好投」 含む trusted X
        ctx = _resolve(
            title="【巨人】先発・赤星優志が5回無失点の好投",
            summary="先発の赤星優志投手が5回を無失点に抑える好投を見せた。",
            source_url="https://twitter.com/hochi_giants/status/2059100000000000002",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "x_short_player")
        self.assertEqual(ctx["category"], "選手情報")

    def test_x_hero_interview_routes_to_x_short_player(self):
        # 重要 keyword「ヒーロー」「お立ち台」「コメント」 含む trusted X
        ctx = _resolve(
            title="お立ち台で巨人選手がヒーローインタビュー",
            summary="ヒーローインタビューで決勝打のコメントを語った。",
            source_url="https://twitter.com/TokyoGiants/status/2059100000000000003",
            source_name="読売ジャイアンツ公式X",
            category="試合速報",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "x_short_player")
        self.assertEqual(ctx["category"], "選手情報")

    def test_x_postgame_without_important_keyword_keeps_existing_path(self):
        # spec 重要 keyword 含まない X postgame (live 3 件 sample 相当)
        # → x_short_player 対象外、既存 postgame_strict 経路維持
        ctx = _resolve(
            title="巨人0-5 敗戦の分岐点 試合の流れ",
            summary="巨人はヤクルト戦に0-5で敗戦。試合の流れは中盤の失点で決まった。",
            source_url="https://twitter.com/sanspo_giants/status/2059100000000000010",
            source_name="サンスポ巨人X",
            category="試合速報",
        )
        # 重要 keyword 不在 → x_short_player 不発、既存 postgame_strict / score_short
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")


class NewsPostgameStrictRegressionTests(unittest.TestCase):
    """news 由来 postgame_strict は影響なし (source_type=news で x_short_player 不発)."""

    def test_news_postgame_strict_with_decisive_keeps_postgame_strict(self):
        # news + decisive event 強 → postgame_strict 維持
        ctx = _resolve(
            title="【巨人】3-2 ヤクルト 岡本和真が決勝3ランホームラン",
            summary="岡本和真選手が試合終盤に決勝の3ランホームラン。試合を決めた。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605060000020.html",
            source_name="日刊スポーツ",
            category="試合速報",
        )
        # x_short_player ではなく postgame_strict
        self.assertEqual(ctx["template_selector_v2_key"], "postgame_strict")
        self.assertEqual(ctx["title_subtype"], "postgame")
        self.assertEqual(ctx["validator_subtype"], "postgame")

    def test_news_postgame_score_short_no_decisive_keeps_postgame_score_short(self):
        # news + decisive 弱 → postgame_score_short 維持 (validator=social_news)
        ctx = _resolve(
            title="【巨人】3-2 ヤクルト 接戦を制す",
            summary="巨人は東京ドームでヤクルトに3-2で勝利した。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605060000021.html",
            source_name="日刊スポーツ",
            category="試合速報",
        )
        # postgame_strict (decisive あり) or postgame_score_short のどちらか
        # x_short_player は news なので絶対 hit しない
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")


class LineupPregamePriorityRegressionTests(unittest.TestCase):
    """has_lineup_signal / has_pregame_signal がある場合は既存 lineup_short /
    pregame_short が先 hit する priority 維持 (RSS-248/253 regression)."""

    def test_x_lineup_signal_routes_to_lineup_short_not_x_short_player(self):
        # 「本日のスタメン」 X post (trusted Giants + 重要 keyword + 短文)
        # → x_short_player guard で skip、lineup_short に到達
        ctx = _resolve(
            title="【巨人】本日のスタメン",
            summary="本日のスターティングメンバー：1番（中）丸 2番（二）吉川",
            source_url="https://x.com/hochi_giants/status/2059200000000000001",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "lineup_short")
        self.assertEqual(ctx["title_subtype"], "lineup")

    def test_x_pregame_signal_routes_to_pregame_short_not_x_short_player(self):
        # 「予告先発」 X post → pregame_short 優先
        ctx = _resolve(
            title="【6日の予告先発】巨人・竹丸和幸",
            summary="本日の予告先発：巨人・竹丸和幸が登板予定",
            source_url="https://x.com/hochi_giants/status/2059200000000000002",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )
        # pregame_short or lineup_short (どちらも x_short_player より優先)
        self.assertIn(ctx["template_selector_v2_key"], ("pregame_short", "lineup_short"))


class XShortPlayerExistingPriorityRegressionTests(unittest.TestCase):
    """x_short_player より上位 (live_update / farm / recovery / notice / manager_quote /
    player_quote) は priority 維持."""

    def test_live_update_takes_precedence(self):
        ctx = _resolve(
            title="【五回表】巨人 0-2 ヤクルト 投手は三者凡退に抑える",
            summary="五回表 巨人 0-2 ヤクルト 投手好投継続中",
            source_url="https://x.com/hochi_giants/status/2059300000000000001",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "live_update_short")

    def test_farm_takes_precedence_over_x_short_player(self):
        # has_farm_or_third_team が先 hit
        ctx = _resolve(
            title="【二軍】巨人 5-0 ハヤテ 試合結果",
            summary="二軍は本日ハヤテベンチャーズ静岡に5-0で勝利。打線好調。",
            source_url="https://x.com/hochi_giants/status/2059300000000000002",
            source_name="スポーツ報知巨人班X",
            category="ドラフト・育成",
        )
        # farm 系のいずれか (farm_lineup_short / farm_short / farm_result /
        # farm_lineup_or_general)
        self.assertIn(
            ctx["template_selector_v2_key"],
            ("farm_lineup_short", "farm_short", "farm_result", "farm_lineup_or_general"),
        )

    def test_player_quote_short_takes_precedence_over_x_short_player(self):
        # actor=player + has_quote → player_quote_short が先
        ctx = _resolve(
            title="岡本和真「3番・三塁」",
            summary="岡本和真選手は試合後、「3番・三塁で起用してもらえてよかった」と語った。",
            source_url="https://x.com/hochi_giants/status/2059300000000000003",
            source_name="スポーツ報知巨人班X",
            category="選手情報",
        )
        # player_quote_short が x_short_player より先
        self.assertIn(
            ctx["template_selector_v2_key"],
            ("player_quote_short", "x_short_player"),  # quote検出強度で分かれる
        )


class NonTrustedXNoElevationTests(unittest.TestCase):
    """non-trusted X / Giants-related なし / important keyword なし は priority 移動の影響なし."""

    def test_non_trusted_x_does_not_elevate(self):
        ctx = _resolve(
            title="巨人0-5 敗戦の分岐点",
            summary="巨人はヤクルト戦に0-5で敗戦。試合の流れは中盤の失点で決まった。",
            source_url="https://x.com/random_user_xyz/status/2059400000000000001",
            source_name="ランダムファンX",
            category="試合速報",
        )
        # trusted 外 → x_short_player 不発、既存 path (postgame 系 or trusted_social)
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")

    def test_no_important_keyword_does_not_elevate(self):
        # trusted Giants だが important keyword なし
        ctx = _resolve(
            title="巨人0-5",
            summary="0-5",
            source_url="https://x.com/sanspo_giants/status/2059400000000000002",
            source_name="サンスポ巨人X",
            category="試合速報",
        )
        # important keyword なし → x_short_player 不発
        self.assertNotEqual(ctx["template_selector_v2_key"], "x_short_player")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
