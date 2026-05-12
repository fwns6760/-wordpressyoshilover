"""Bug reproduction: 巨人公式X / スポニチ emoji-form lineup tweets are
dropped into prose-only body with no structured table.

Production sample id=65900 (2026-05-10) source ``📰 巨人公式 / 巨人公式X``:

  【二軍】巨人 vs ロッテ オーエンススタジアム江戸川🏟️ 13時試合開始⚾
  1️⃣ 三塚(D) 2️⃣ 小濱⑹ 3️⃣ 皆川⑼ 4️⃣ 萩尾⑺ 5️⃣ 荒巻⑶ 6️⃣ 浅野⑻
  7️⃣ 山瀬⑵ 8️⃣ 郡⑸ 9️⃣ 湯浅⑷ 🅿️ マタ GIANTS TVでLIVE配信。

Format (NOMOTOKE-LINEUP-FROM-EMOJI-001 Phase 2B):
- keycap emoji ``1️⃣..9️⃣`` = batting order
- name (kanji / katakana, 1-8 chars)
- defensive position appended as:
  - ``(D)``     = DH
  - ``⑴-⑼``    = circled-number for 投/捕/一/二/三/遊/左/中/右
- ``🅿️ <name>`` = pitcher (no batting order)

Phase 2A (`bc5c603`) + Phase 2A-1 (`8d47ea7`) only handle 報知 compact
form (``D東妻 7萩尾...``). This emoji format falls through to prose-only
body. Phase 2B adds an emoji-form parser sharing the same roster /
opponent infrastructure so 巨人公式X 2軍 tweets also render as
「📋 巨人スタメン」 + 「📋 <opponent>スタメン」 split tables.

Source allowlist for the emoji parser:
- ``巨人公式X`` / ``TokyoGiants``
- ``スポニチ野球記者X`` / ``SponichiYakyu`` (in case the same emoji
  format appears there)
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


# Production-shaped fixture (verified 2026-05-12 against id=65900).
EMOJI_FARM_LINEUP = (
    "【二軍】巨人 vs ロッテ オーエンススタジアム江戸川🏟️ 13時試合開始⚾ "
    "1️⃣ 三塚(D) 2️⃣ 小濱⑹ 3️⃣ 皆川⑼ 4️⃣ 萩尾⑺ 5️⃣ 荒巻⑶ "
    "6️⃣ 浅野⑻ 7️⃣ 山瀬⑵ 8️⃣ 郡⑸ 9️⃣ 湯浅⑷ 🅿️ マタ"
)


class EmojiLineupTableTests(unittest.TestCase):
    """Phase 2B bug reproduction. RED 前提 (実装前)。"""

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
        yahoo_lineup_rows: list[dict] | None = None,
    ) -> tuple[str, str]:
        # Production has ENABLE_RSS_TEMPLATE_ROUTING_V2=1 (verified
        # 2026-05-12). The v2 routing detects keycap-emoji lineups via
        # _has_social_lineup_shorthand_signal and classifies them as
        # body_subtype="farm_lineup". v1 routing requires the "スタメン"
        # keyword which the emoji fixture lacks, so without this env
        # patch the test would simulate v1 behaviour and miss prod parity.
        patches = [
            patch.dict(os.environ, {"ENABLE_RSS_TEMPLATE_ROUTING_V2": "1"}),
            patch.object(
                rss_fetcher,
                "fetch_today_giants_lineup_stats_from_yahoo",
                return_value=yahoo_lineup_rows or [],
            ),
        ]
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

    def test_emoji_farm_lineup_emits_giants_table_heading(self):
        """巨人公式X 2軍 emoji lineup → body に「巨人スタメン」 heading 含む。"""
        blocks, _ai_body = self._build(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            url="https://twitter.com/TokyoGiants/status/2050000000000000001",
            source_name="巨人公式X",
            category="ドラフト・育成",
        )
        self.assertIn(
            "巨人スタメン",
            blocks,
            "巨人公式X 2軍 emoji lineup で「巨人スタメン」 heading が出ない",
        )

    def test_emoji_farm_lineup_opponent_extracted_at_parse_layer(self):
        """巨人公式X 2軍 emoji lineup は 巨人 batter のみ列挙する convention
        のため、render 段では opponent table が空に suppress される(正常)。

        ただし parser layer では opponent_team_name を ``vs ロッテ`` から抽出
        できているべき。ここでは parser を直接呼んで抽出値を検証する。
        """
        from src.source_emoji_lineup_extractor import parse_emoji_lineup
        result = parse_emoji_lineup(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            source_name="巨人公式X",
        )
        self.assertIsNotNone(result, "emoji parser returned None")
        self.assertEqual(
            result.get("opponent_team_name"),
            "ロッテ",
            "opponent_team_name が `vs ロッテ` から抽出されていない",
        )

    def test_emoji_farm_lineup_emits_single_giants_table_when_opponent_absent(self):
        """巨人公式X 2軍 emoji は通常 巨人 batter のみ → 1 table のみ。

        opponent rows が空のとき opponent table は emit されないことを
        確認(double-render / 空 table render 防止)。
        """
        blocks, _ai_body = self._build(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            url="https://twitter.com/TokyoGiants/status/2050000000000000001",
            source_name="巨人公式X",
            category="ドラフト・育成",
        )
        self.assertEqual(
            blocks.count("nomotoke-card-lineup-table"),
            1,
            "巨人 batter のみの emoji fixture で table が 2 つ出ている",
        )
        self.assertNotIn(
            "ロッテスタメン",
            blocks,
            "opponent rows 空なのに ロッテスタメン heading が出ている",
        )

    def test_emoji_farm_lineup_emits_lineup_table_marker(self):
        """emoji lineup → body に ``nomotoke-card-lineup-table`` marker が含まれる。"""
        blocks, _ai_body = self._build(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            url="https://twitter.com/TokyoGiants/status/2050000000000000001",
            source_name="巨人公式X",
            category="ドラフト・育成",
        )
        self.assertIn(
            "nomotoke-card-lineup-table",
            blocks,
            "emoji lineup body に table marker が無い",
        )

    def test_emoji_farm_lineup_player_names_present(self):
        """emoji parse 後の主要選手名が body に含まれる。"""
        blocks, _ai_body = self._build(
            title=EMOJI_FARM_LINEUP,
            summary=EMOJI_FARM_LINEUP,
            url="https://twitter.com/TokyoGiants/status/2050000000000000001",
            source_name="巨人公式X",
            category="ドラフト・育成",
        )
        for name in ("三塚", "小濱", "皆川", "萩尾", "マタ"):
            self.assertIn(name, blocks, f"player name '{name}' missing from body")

    def test_non_emoji_source_unchanged(self):
        """巨人公式X clean 形(``1番（中）...``)では emoji parser 不発火、
        既存 ``source_x_lineup_extractor`` の path を踏む。"""
        clean_form = (
            "本日のスタメンが発表されました "
            "1番（中）丸 2番（二）吉川 3番（一）岡本 4番（指）ダルベック "
            "5番（左）キャベッジ 6番（三）増田 7番（右）萩尾 8番（捕）大城 "
            "9番（投）戸郷"
        )
        blocks, _ai_body = self._build(
            title=clean_form,
            summary=clean_form,
            url="https://twitter.com/TokyoGiants/status/2050000000000000002",
            source_name="巨人公式X",
            category="試合速報",
        )
        # 巨人公式X clean 形は本 Phase 2B の対象外、emoji parser が None を返すべき
        self.assertNotIn(
            "nomotoke-card-lineup-table",
            blocks,
            "clean 形 (1番(中)...) で emoji parser が誤発火している",
        )


if __name__ == "__main__":
    unittest.main()
