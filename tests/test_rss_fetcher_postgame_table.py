"""Bug reproduction: 報知 / スポニチ postgame articles render only a
prose body with no structured 試合結果 table.

Production sample id=66565 (2026-05-12, hochi.news 2軍 postgame):

  【巨人】"スミ１"の完封勝利で貯金６　又木鉄平が５回無失点で３勝目…２軍・ＤｅＮＡ戦
  body: 巨人２軍はＤｅＮＡに１―０で🏆 勝利した。

Phase 2D (NOMOTOKE-LINEUP-FROM-POSTGAME-001) adds:
- ``parse_postgame_facts`` that extracts score / winning pitcher /
  result-type / opponent from prose using regex patterns.
- 1軍 postgame can additionally use the existing
  ``source_yahoo_boxscore_extractor`` to render a full inning + box
  table (the A-fallback ships first; Yahoo box integration follows).
- 2軍 postgame always uses the A-fallback (Yahoo has no farm data).

Allowlist: 報知 + sponichi + 巨人公式X (reuses the hochi extractor
infrastructure for source / roster / opponent helpers).
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


# Production-shaped fixture (verified 2026-05-12 against id=66565).
HOCHI_FARM_POSTGAME_TITLE = (
    "【巨人】\"スミ１\"の完封勝利で貯金６　又木鉄平が５回無失点で３勝目…２軍・ＤｅＮＡ戦"
)
HOCHI_FARM_POSTGAME_SUMMARY = (
    "巨人２軍はＤｅＮＡに１―０で勝利した。"
    "又木鉄平が５回無失点で３勝目を挙げた。"
)

# Constructed 1軍 postgame fixture (similar shape, hochi-style).
HOCHI_FIRST_POSTGAME_TITLE = (
    "【巨人】戸郷翔征が８回１失点の力投で４勝目　巨人が中日に５―１で快勝"
)
HOCHI_FIRST_POSTGAME_SUMMARY = (
    "巨人は中日に５―１で勝利した。戸郷翔征が８回１失点で４勝目を挙げ、エースの仕事を果たした。"
)


class PostgameTableTests(unittest.TestCase):
    """Phase 2D bug reproduction. RED 前提 (実装前)。"""

    def _build(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        source_name: str,
        category: str,
        has_game: bool = True,
        source_type: str = "social_news",
    ) -> tuple[str, str]:
        patches = [
            patch.dict(os.environ, {"ENABLE_RSS_TEMPLATE_ROUTING_V2": "1"}),
            patch.object(
                rss_fetcher,
                "fetch_today_giants_lineup_stats_from_yahoo",
                return_value=[],
            ),
        ]
        # Phase 2F: NPB fetcher mock — empty dict so the test exercises
        # the Yahoo / A-fallback path that existed before Phase 2F.
        if hasattr(rss_fetcher, "fetch_today_giants_npb_box_facts"):
            patches.append(
                patch.object(
                    rss_fetcher,
                    "fetch_today_giants_npb_box_facts",
                    return_value={},
                )
            )
        for fn_name, return_value in (
            ("fetch_fan_reactions_from_yahoo", []),
            ("_fetch_fan_reactions_from_yahoo_safe", []),
            ("generate_article_with_gemini", ""),
            ("generate_article_with_grok", ("", [], "", "", "")),
        ):
            if hasattr(rss_fetcher, fn_name):
                patches.append(patch.object(rss_fetcher, fn_name, return_value=return_value))
        for p in patches:
            p.start()
        try:
            return rss_fetcher.build_news_block(
                title=title,
                summary=summary,
                url=url,
                source_name=source_name,
                category=category,
                has_game=has_game,
                source_type=source_type,
            )
        finally:
            for p in reversed(patches):
                p.stop()

    def test_hochi_farm_postgame_emits_result_heading(self):
        """2軍 postgame で「試合結果」 heading 含む。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-farm.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            source_type="news",
        )
        self.assertIn(
            "試合結果",
            blocks,
            "2軍 postgame で「試合結果」heading が出ない",
        )

    def test_hochi_farm_postgame_emits_table_marker(self):
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-farm.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            source_type="news",
        )
        self.assertIn(
            "nomotoke-card-postgame-result",
            blocks,
            "2軍 postgame で table marker が出ない",
        )

    def test_hochi_farm_postgame_includes_score_and_winner(self):
        """body に スコア (1-0 or 1―0) と 勝利投手名 (又木鉄平 / 又木) 含む。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-farm.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            source_type="news",
        )
        # スコア(1-0 or 1―0)
        self.assertTrue(
            "1-0" in blocks or "1―0" in blocks,
            "1-0 score が body に無い",
        )
        # 勝利投手名
        self.assertIn(
            "又木",
            blocks,
            "勝利投手 又木 が body に無い",
        )

    def test_hochi_first_team_postgame_emits_table(self):
        """1軍 postgame でも table 描画(Yahoo box 不在時の A-fallback)。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FIRST_POSTGAME_TITLE,
            summary=HOCHI_FIRST_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-first.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            source_type="news",
        )
        self.assertIn(
            "nomotoke-card-postgame-result",
            blocks,
            "1軍 postgame で table が出ない",
        )
        self.assertIn("戸郷", blocks, "勝利投手 戸郷 が body に無い")

    def test_non_postgame_article_unchanged(self):
        """postgame でない記事(player comment 等)で発火しない。"""
        blocks, _ai_body = self._build(
            title="巨人・吉川尚輝が主将としての成長語る",
            summary="巨人の吉川尚輝が主将としての心構えを語った。",
            url="https://hochi.news/articles/20260512-OHT8888.html",
            source_name="スポーツ報知 巨人 tag",
            category="選手情報",
            source_type="news",
        )
        self.assertNotIn(
            "nomotoke-card-postgame-result",
            blocks,
            "non-postgame で postgame table が誤発火",
        )

    def test_non_hochi_postgame_source_unchanged(self):
        """non-hochi/sponichi/巨人公式X source では発火しない(allowlist gate)。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://example.com/articles/some.html",
            source_name="Yahoo!プロ野球",
            category="試合速報",
            source_type="news",
        )
        self.assertNotIn(
            "nomotoke-card-postgame-result",
            blocks,
            "non-allowlist source で postgame table が誤発火",
        )


class PostgameYahooBoxscoreTests(unittest.TestCase):
    """Phase 2D-B integration: when Yahoo boxscore is available, the 1軍
    postgame article should render a rich block with inning-by-inning
    score in addition to the score / 勝利投手 line.

    Mock ``fetch_today_giants_postgame_facts_from_yahoo`` so the test
    doesn't make real HTTP calls.
    """

    YAHOO_BOXSCORE_DICT = {
        "team_name": "巨人",
        "score": "5-1",
        "result": "win",
        "date_label": "2026年5月12日",
        "league_label": "セ・リーグ 8回戦",
        "home": "読売ジャイアンツ",
        "away": "中日ドラゴンズ",
        "inning_score": [
            {"name": "中日", "innings": ["0", "0", "0", "0", "1", "0", "0", "0", "0"], "total": 1},
            {"name": "巨人", "innings": ["0", "1", "0", "0", "2", "0", "2", "0", "x"], "total": 5},
        ],
        "one_line_summary": "巨人 5-1 中日",
    }

    def _build_with_yahoo(
        self,
        *,
        title: str,
        summary: str,
        url: str,
        source_name: str,
        category: str,
        yahoo_facts: dict | None,
    ) -> tuple[str, str]:
        patches = [
            patch.dict(os.environ, {"ENABLE_RSS_TEMPLATE_ROUTING_V2": "1"}),
            patch.object(
                rss_fetcher,
                "fetch_today_giants_lineup_stats_from_yahoo",
                return_value=[],
            ),
        ]
        # Phase 2F: NPB fetcher mock — empty dict so the test exercises
        # the Yahoo / A-fallback path that existed before Phase 2F.
        if hasattr(rss_fetcher, "fetch_today_giants_npb_box_facts"):
            patches.append(
                patch.object(
                    rss_fetcher,
                    "fetch_today_giants_npb_box_facts",
                    return_value={},
                )
            )
        # Phase 2D-B mock — postgame Yahoo fetcher returns the supplied dict.
        if hasattr(rss_fetcher, "fetch_today_giants_postgame_facts_from_yahoo"):
            patches.append(
                patch.object(
                    rss_fetcher,
                    "fetch_today_giants_postgame_facts_from_yahoo",
                    return_value=yahoo_facts or {},
                )
            )
        for fn_name, return_value in (
            ("fetch_fan_reactions_from_yahoo", []),
            ("_fetch_fan_reactions_from_yahoo_safe", []),
            ("generate_article_with_gemini", ""),
            ("generate_article_with_grok", ("", [], "", "", "")),
        ):
            if hasattr(rss_fetcher, fn_name):
                patches.append(patch.object(rss_fetcher, fn_name, return_value=return_value))
        for p in patches:
            p.start()
        try:
            return rss_fetcher.build_news_block(
                title=title,
                summary=summary,
                url=url,
                source_name=source_name,
                category=category,
                has_game=True,
                source_type="news",
            )
        finally:
            for p in reversed(patches):
                p.stop()

    def test_first_team_postgame_with_yahoo_emits_inning_table(self):
        """1軍 postgame + Yahoo box success → inning-by-inning table 含む。"""
        blocks, _ai_body = self._build_with_yahoo(
            title=HOCHI_FIRST_POSTGAME_TITLE,
            summary=HOCHI_FIRST_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-first.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            yahoo_facts=self.YAHOO_BOXSCORE_DICT,
        )
        self.assertIn(
            "nomotoke-card-postgame-inning",
            blocks,
            "1軍 postgame で inning table marker が出ない",
        )
        # inning header
        self.assertIn("中日", blocks)
        # date label
        self.assertIn("2026年5月12日", blocks)

    def test_first_team_postgame_with_yahoo_pitchers_emits_pitcher_table(self):
        """Phase 2E: Yahoo box に W/L/S pitcher 情報があれば pitcher table 描画。"""
        yahoo = dict(self.YAHOO_BOXSCORE_DICT)
        yahoo.update(
            {
                "winning_pitcher": {"team": "巨人", "name": "戸郷翔征", "record": "4勝2敗0S"},
                "losing_pitcher": {"team": "中日", "name": "高橋宏斗", "record": "3勝5敗0S"},
                "save_pitcher": {"team": "巨人", "name": "大勢", "record": "1勝0敗8S"},
            }
        )
        blocks, _ai_body = self._build_with_yahoo(
            title=HOCHI_FIRST_POSTGAME_TITLE,
            summary=HOCHI_FIRST_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-first.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            yahoo_facts=yahoo,
        )
        self.assertIn(
            "nomotoke-card-postgame-pitchers",
            blocks,
            "Phase 2E: pitcher table marker が出ない",
        )
        # W/L/S labels + names visible
        for token in ("勝利投手", "敗戦投手", "セーブ", "戸郷翔征", "高橋宏斗", "大勢"):
            self.assertIn(token, blocks, f"pitcher token '{token}' missing")

    def test_first_team_postgame_without_pitcher_data_skips_pitcher_table(self):
        """Phase 2E: pitcher dicts 全て空 → pitcher table は emit しない。"""
        yahoo = dict(self.YAHOO_BOXSCORE_DICT)
        yahoo.update(
            {
                "winning_pitcher": {},
                "losing_pitcher": {},
                "save_pitcher": {},
            }
        )
        blocks, _ai_body = self._build_with_yahoo(
            title=HOCHI_FIRST_POSTGAME_TITLE,
            summary=HOCHI_FIRST_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-first.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            yahoo_facts=yahoo,
        )
        # inning still rendered, but no pitcher table marker
        self.assertIn("nomotoke-card-postgame-inning", blocks)
        self.assertNotIn(
            "nomotoke-card-postgame-pitchers",
            blocks,
            "pitcher 空でも pitcher table が誤発火",
        )

    def test_first_team_postgame_yahoo_fail_uses_a_fallback(self):
        """Yahoo fetch 失敗 → A-fallback table のみ(inning table 無し)。"""
        blocks, _ai_body = self._build_with_yahoo(
            title=HOCHI_FIRST_POSTGAME_TITLE,
            summary=HOCHI_FIRST_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-first.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            yahoo_facts={},  # empty = fetch failed
        )
        # A-fallback table marker present
        self.assertIn("nomotoke-card-postgame-result", blocks)
        # rich inning table NOT present
        self.assertNotIn(
            "nomotoke-card-postgame-inning",
            blocks,
            "Yahoo 失敗時に inning table が誤って出ている",
        )

    def test_farm_postgame_skips_yahoo_and_uses_a_fallback(self):
        """2軍 postgame では Yahoo fetch を skip して A-fallback のみ。"""
        blocks, _ai_body = self._build_with_yahoo(
            title=HOCHI_FARM_POSTGAME_TITLE,
            summary=HOCHI_FARM_POSTGAME_SUMMARY,
            url="https://hochi.news/articles/20260512-OHT9999-farm.html",
            source_name="スポーツ報知 巨人 tag",
            category="試合速報",
            yahoo_facts=self.YAHOO_BOXSCORE_DICT,  # supplied but should be ignored for 2軍
        )
        self.assertIn("nomotoke-card-postgame-result", blocks)
        self.assertNotIn(
            "nomotoke-card-postgame-inning",
            blocks,
            "2軍 postgame で 1軍用 inning table が誤発火",
        )


class PostgameNPBBoxIntegrationTests(unittest.TestCase):
    """Phase 2F: NPB box facts produce the rich 4-table layout."""

    NPB_BOX_FACTS = {
        "giants_batters": [
            {"順": "1", "守備": "二", "選手": "吉川", "打数": "5", "得点": "0",
             "安打": "1", "打点": "1", "盗塁": "0",
             "atbats": ["二ゴロ", "-", "二併打", "-", "三振", "-", "二ゴロ", "-", "右前安"],
             "is_sub": False},
            {"順": "2", "守備": "左", "選手": "キャベッジ", "打数": "4", "得点": "0",
             "安打": "1", "打点": "0", "盗塁": "0",
             "atbats": ["三振", "-", "中飛", "-", "一ゴロ", "-", "投安", "-", "-"],
             "is_sub": False},
        ],
        "giants_pitchers": [
            {"選手": "森田", "投球数": "80", "打者": "21", "投球回": "4.1",
             "安打": "5", "本塁打": "1", "四球": "2", "死球": "0", "三振": "4",
             "暴投": "0", "ボーク": "0", "失点": "4", "自責点": "4"},
        ],
        "opponent_batters": [
            {"順": "1", "守備": "右", "選手": "岡林", "打数": "4", "得点": "1",
             "安打": "2", "打点": "0", "盗塁": "0",
             "atbats": ["-"] * 9, "is_sub": False},
        ],
        "opponent_pitchers": [
            {"選手": "髙橋宏", "投球数": "95", "打者": "30", "投球回": "5.0",
             "安打": "8", "本塁打": "2", "四球": "3", "死球": "0", "三振": "6",
             "暴投": "0", "ボーク": "0", "失点": "5", "自責点": "5"},
        ],
        "opponent_team_name": "中日",
        "inning_score": [
            {"name": "巨人", "innings": ["0","1","0","2","0","2","0","1","3"], "total": 9},
            {"name": "中日", "innings": ["0","0","1","2","1","0","0","0","0"], "total": 4},
        ],
    }

    def _build_with_npb(self, *, yahoo_facts=None, npb_facts=None):
        patches = [
            patch.dict(os.environ, {"ENABLE_RSS_TEMPLATE_ROUTING_V2": "1"}),
            patch.object(rss_fetcher, "fetch_today_giants_lineup_stats_from_yahoo", return_value=[]),
        ]
        if hasattr(rss_fetcher, "fetch_today_giants_npb_box_facts"):
            patches.append(
                patch.object(rss_fetcher, "fetch_today_giants_npb_box_facts",
                             return_value=npb_facts or {})
            )
        if hasattr(rss_fetcher, "fetch_today_giants_postgame_facts_from_yahoo"):
            patches.append(
                patch.object(rss_fetcher, "fetch_today_giants_postgame_facts_from_yahoo",
                             return_value=yahoo_facts or {})
            )
        for fn_name, return_value in (
            ("fetch_fan_reactions_from_yahoo", []),
            ("_fetch_fan_reactions_from_yahoo_safe", []),
            ("generate_article_with_gemini", ""),
            ("generate_article_with_grok", ("", [], "", "", "")),
        ):
            if hasattr(rss_fetcher, fn_name):
                patches.append(patch.object(rss_fetcher, fn_name, return_value=return_value))
        for p in patches:
            p.start()
        try:
            return rss_fetcher.build_news_block(
                title=HOCHI_FIRST_POSTGAME_TITLE,
                summary=HOCHI_FIRST_POSTGAME_SUMMARY,
                url="https://hochi.news/articles/20260512-OHT9999-first.html",
                source_name="スポーツ報知 巨人 tag",
                category="試合速報",
                has_game=True,
                source_type="news",
            )
        finally:
            for p in reversed(patches):
                p.stop()

    def test_npb_box_emits_batter_table_marker(self):
        blocks, _ = self._build_with_npb(npb_facts=self.NPB_BOX_FACTS)
        self.assertIn("nomotoke-card-postgame-batter", blocks)
        self.assertIn("吉川", blocks)
        self.assertIn("二ゴロ", blocks)

    def test_npb_box_emits_pitcher_detail_table_marker(self):
        blocks, _ = self._build_with_npb(npb_facts=self.NPB_BOX_FACTS)
        self.assertIn("nomotoke-card-postgame-pitcher-detail", blocks)
        self.assertIn("森田", blocks)
        self.assertIn("4.1", blocks)

    def test_npb_box_takes_priority_for_inning_but_keeps_yahoo_wls(self):
        """Phase 2G: NPB 成功時 inning は NPB が優先(Yahoo inning は描画
        されない)が、Yahoo W/L/S 投手 sub-block は併存する。"""
        yahoo = {
            "team_name": "巨人", "score": "9-4", "result": "win",
            "date_label": "2026年5月10日", "league_label": "セ・リーグ",
            "home": "中日ドラゴンズ", "away": "読売ジャイアンツ",
            "inning_score": [{"name": "巨人", "innings": ["0"]*9, "total": 9},
                            {"name": "中日", "innings": ["0"]*9, "total": 4}],
            "one_line_summary": "",
            "winning_pitcher": {"team": "巨人", "name": "戸郷", "record": "4勝2敗0S"},
        }
        blocks, _ = self._build_with_npb(npb_facts=self.NPB_BOX_FACTS, yahoo_facts=yahoo)
        # NPB block 出てる(batter / pitcher-detail / inning)
        self.assertIn("nomotoke-card-postgame-batter", blocks)
        self.assertIn("nomotoke-card-postgame-pitcher-detail", blocks)
        self.assertIn("nomotoke-card-postgame-inning", blocks)
        # Phase 2G: NPB と並走で W/L/S sub-block も出る(NPB は W/L/S summary を持たない)
        self.assertIn("nomotoke-card-postgame-pitchers", blocks)
        self.assertIn("戸郷", blocks)
        # Phase 2D-B Yahoo の試合結果 header marker は出ない(NPB が inning を支配)
        self.assertNotIn("nomotoke-card-postgame-result", blocks)

    def test_npb_box_fails_falls_back_to_yahoo(self):
        yahoo = {
            "team_name": "巨人", "score": "9-4", "result": "win",
            "date_label": "2026年5月10日", "league_label": "セ・リーグ",
            "home": "中日ドラゴンズ", "away": "読売ジャイアンツ",
            "inning_score": [{"name": "巨人", "innings": ["0"]*9, "total": 9},
                            {"name": "中日", "innings": ["0"]*9, "total": 4}],
            "one_line_summary": "",
        }
        blocks, _ = self._build_with_npb(npb_facts={}, yahoo_facts=yahoo)
        # NPB block 出ない
        self.assertNotIn("nomotoke-card-postgame-batter", blocks)
        # Yahoo inning fallback 出る
        self.assertIn("nomotoke-card-postgame-inning", blocks)


if __name__ == "__main__":
    unittest.main()
