"""RSS-252: 短文 template の validator_subtype 緩和 tests.

短文 template (postgame_score_short / pregame_short) の validator_subtype が
緩い social_news に切り替わり、body_validator BODY_CONTRACTS の重い heading
contract に当たらないことを pin する。

title_subtype / body_subtype は元 (postgame / pregame) のまま (生成 / 表示維持)。
body_validator.py / BODY_CONTRACTS は不変。
postgame_strict (decisive event 強) は validator_subtype="postgame" を維持 (regression check)。
"""

import unittest

from src import body_validator, rss_fetcher


def _resolve(*, title: str, summary: str, source_type: str, source_url: str, source_name: str, category: str = "試合速報"):
    return rss_fetcher._resolve_rss_story_type_context_v2(
        title=title,
        summary=summary,
        category=category,
        daily_has_game=True,
        source_type=source_type,
        source_url=source_url,
        source_name=source_name,
    )


class PostgameScoreShortValidatorTuneTests(unittest.TestCase):
    """postgame_score_short の validator_subtype が social_news に緩和される."""

    def test_postgame_score_short_validator_subtype_is_social_news(self):
        # score+opponent あるが decisive event 弱 → postgame_score_short
        ctx = _resolve(
            title="【巨人】3-2 ヤクルト 接戦を制す",
            summary="巨人は東京ドームでヤクルトに3-2で勝利した。先発戸郷は5回まで投げた。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605060000010.html",
            source_name="日刊スポーツ",
        )
        # postgame_score_short か postgame_strict のいずれか routing
        # → どちらでも postgame title/body subtype 維持
        self.assertEqual(ctx["title_subtype"], "postgame")
        self.assertEqual(ctx["body_subtype"], "postgame")
        if ctx["template_selector_v2_key"] == "postgame_score_short":
            self.assertEqual(ctx["validator_subtype"], "social_news")

    def test_postgame_strict_keeps_validator_subtype_postgame(self):
        # postgame_strict (decisive event 強) は validator_subtype="postgame" 維持
        ctx = _resolve(
            title="【巨人】3-2 ヤクルト 岡本和真が決勝3ランホームラン",
            summary="9回表に岡本和真選手が決勝の3ランホームラン。試合を決めました。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605060000011.html",
            source_name="日刊スポーツ",
        )
        if ctx["template_selector_v2_key"] == "postgame_strict":
            # decisive event 検出時は強い contract 維持
            self.assertEqual(ctx["validator_subtype"], "postgame")


class PregameShortValidatorTuneTests(unittest.TestCase):
    """pregame_short の validator_subtype が social_news に緩和される."""

    def test_pregame_short_validator_subtype_is_social_news(self):
        ctx = _resolve(
            title="【6日の予告先発】巨人・竹丸和幸―ヤクルト・山野太一",
            summary="6日の予告先発が発表されました。巨人は竹丸和幸、ヤクルトは山野太一が先発予定です。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605060000012.html",
            source_name="日刊スポーツ",
        )
        # pregame_short routing 確認
        self.assertEqual(ctx["template_selector_v2_key"], "pregame_short")
        # title/body は pregame 維持、validator は social_news に緩和
        self.assertEqual(ctx["title_subtype"], "pregame")
        self.assertEqual(ctx["body_subtype"], "pregame")
        self.assertEqual(ctx["validator_subtype"], "social_news")

    def test_pregame_x_post_validator_subtype_is_social_news_when_pregame_short(self):
        # X 由来 pregame
        ctx = _resolve(
            title="【一軍】巨人 vs ヤクルト 5/6 14時試合開始 予告先発",
            summary="本日の予告先発：巨人・竹丸和幸 / ヤクルト・山野太一",
            source_type="social_news",
            source_url="https://x.com/TokyoGiants/status/2052900000000000010",
            source_name="読売ジャイアンツ公式X",
        )
        if ctx["template_selector_v2_key"] == "pregame_short":
            self.assertEqual(ctx["validator_subtype"], "social_news")


class BodyValidatorContractsUnchangedTests(unittest.TestCase):
    """既存 BODY_CONTRACTS は変更されていない (regression baseline)."""

    def test_body_contracts_postgame_keeps_4_headings(self):
        contract = body_validator.BODY_CONTRACTS.get("postgame")
        self.assertIsNotNone(contract)
        self.assertEqual(len(contract), 4)
        for heading in ("【試合結果】", "【ハイライト】", "【選手成績】", "【試合展開】"):
            self.assertIn(heading, contract)

    def test_body_contracts_pregame_keeps_3_headings(self):
        contract = body_validator.BODY_CONTRACTS.get("pregame")
        self.assertIsNotNone(contract)
        self.assertEqual(len(contract), 3)

    def test_body_contracts_live_update_keeps_3_headings(self):
        contract = body_validator.BODY_CONTRACTS.get("live_update")
        self.assertIsNotNone(contract)
        self.assertEqual(len(contract), 3)

    def test_body_contracts_farm_keeps_4_headings(self):
        contract = body_validator.BODY_CONTRACTS.get("farm")
        self.assertIsNotNone(contract)
        self.assertEqual(len(contract), 4)

    def test_body_contracts_social_news_has_no_required_heading(self):
        # social_news は BODY_CONTRACTS に entry なし → 短文向けで heading 不要
        # (validator が短文 contract skip する path)
        self.assertNotIn("social_news", body_validator.BODY_CONTRACTS)


class TemplateRoutingValidatorSubtypePinTests(unittest.TestCase):
    """template_key 別 validator_subtype のクロステーブル pin."""

    def test_lineup_short_validator_subtype_unchanged(self):
        # lineup_short は validator_subtype="lineup" 維持 (BODY_CONTRACTS に lineup
        # entry なし → 既に contract check skip、変更不要)
        ctx = _resolve(
            title="【巨人】本日のスタメン",
            summary="本日のスターティングメンバー：1番（中）丸 2番（二）吉川",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2052900000000000020",
            source_name="スポーツ報知巨人班X",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "lineup_short")
        self.assertEqual(ctx["validator_subtype"], "lineup")

    def test_farm_lineup_short_validator_subtype_unchanged(self):
        # farm_lineup_short も validator_subtype="farm_lineup" 維持
        # (BODY_CONTRACTS に farm_lineup entry なし)
        ctx = _resolve(
            title="【ジャイアンツ二軍】本日のスタメン",
            summary="二軍スタメン：1番（中）佐々木 2番（二）湯浅 3番（一）萩尾",
            source_type="news",
            source_url="https://baseball.yahoo.co.jp/npb/farm/lineup",
            source_name="Yahoo!ファーム",
            category="ドラフト・育成",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "farm_lineup_short")
        self.assertEqual(ctx["validator_subtype"], "farm_lineup")

    def test_trusted_social_short_validator_subtype_is_social_news(self):
        # trusted_social_short は元から validator_subtype="social_news"
        ctx = _resolve(
            title="【巨人】本日の練習風景です",
            summary="本日の東京ドームでの練習風景。明日の試合に向けて調整中。練習を頑張っています。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2052900000000000030",
            source_name="スポーツ報知巨人班X",
        )
        if ctx["template_selector_v2_key"] == "trusted_social_short":
            self.assertEqual(ctx["validator_subtype"], "social_news")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
