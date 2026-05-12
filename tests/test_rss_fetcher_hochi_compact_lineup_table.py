"""Bug reproduction: 報知 X (compact ``D東妻 7萩尾3加藤...`` 形) source の
スタメン記事で本文に ``<table>`` が描画されない問題。

Production 確認: 公開記事 id=66442
(``ファーム・リーグ（Ｇタウン） スタメン 【DeNA】 【巨人】 D東妻 7萩尾3加藤 ...``)
で「【二軍スタメン一覧】」h3 の下が空のまま public publish された。

Phase 0 調査結果(``docs/work_logs/2026-05-12_hochi-sponichi-source-structured-table-rendering.md``):
- ``ARTICLE_AI_MODE=none`` 環境では LLM 不使用、``_build_safe_article_fallback``
  系 dispatcher で本文構築
- 1軍 (``article_subtype=="lineup"``) は ``fetch_today_giants_lineup_stats_from_yahoo``
  + ``_lineup_stats_block`` で 7 列 HTML table 描画される (Yahoo 依存)
- 2軍 (``article_subtype=="farm_lineup"``) は ``_build_farm_lineup_safe_fallback``
  に ``lineup_rows`` 引数なし、prose-only fallback で table 描画されない
- 報知 compact 形は構造抽出されないので 1軍でも Yahoo fetch が空ならば table 出ない

本テストは fix 前は **RED** (table marker / 選手名が body に含まれない) で固定する。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src import rss_fetcher


# --- Fixture: 公開記事 id=66442 (2026-05-12 報知 hochi_giants tweet) と同形 ---
# 元 tweet URL: https://twitter.com/hochi_giants/status/2054047155913113832
# 「ファーム・リーグ（Ｇタウン）スタメン【DeNA】 【巨人】 <DH> <pos><name>...」
# position 数字 mapping: 投=1, 捕=2, 一=3, 二=4, 三=5, 遊=6, 左=7, 中=8, 右=9
# D = 指 (DH), P = 投 (pitcher)
HOCHI_FARM_LINEUP_COMPACT = (
    "ファーム・リーグ（Ｇタウン） スタメン 【DeNA】 【巨人】 "
    "D東妻 7萩尾 3加藤 9皆川 6石上 6小濱 5宮下 5藤井 7井上 3三塚 "
    "4小田 8浅野 9梶原 Dティマ 2古市 2山瀬 8濱 4湯浅 P片山 P又木"
)

# 1軍 想定: 「巨人スタメン 中日戦」+ compact "D<name> <pos><name>..."
HOCHI_FIRST_TEAM_LINEUP_COMPACT = (
    "巨人スタメン 中日戦(バンテリンD、13:30) "
    "4吉川 7キャベッジ 9丸 5ダルベック 2大城 3増田 8平山 6浦田 1森田"
)


class HochiCompactLineupTableTests(unittest.TestCase):
    """Phase 2A bug reproduction. RED 前提 (実装前)。"""

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
        """build_news_block を mock 付きで呼び出すヘルパ。

        Yahoo fetch / Gemini / fan reactions は外部 IO を伴うので必ず mock。
        """
        patches = [
            patch.object(
                rss_fetcher,
                "fetch_today_giants_lineup_stats_from_yahoo",
                return_value=yahoo_lineup_rows or [],
            ),
        ]
        # Gemini / Grok / fan reaction 関数は環境やバージョンで存在/非存在があるので
        # getattr で防御。存在しなければ patch スキップ。
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

    def test_hochi_farm_lineup_compact_body_contains_lineup_table(self):
        """報知 X 2軍 compact 形 lineup → body に table marker が含まれる。

        実環境 id=66442 で「【二軍スタメン一覧】」h3 の下が空のまま public 化された。
        Fix 後はこの test が GREEN になる。
        """
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_LINEUP_COMPACT,
            summary=HOCHI_FARM_LINEUP_COMPACT,
            url="https://twitter.com/hochi_giants/status/2054047155913113832",
            source_name="スポーツ報知巨人班X",
            category="ドラフト・育成",
        )

        self.assertIn(
            "nomotoke-card-lineup-table",
            blocks,
            "報知 2軍 lineup body に table marker が無い (id=66442 で空 H3 のまま public 化された bug)",
        )

    def test_hochi_farm_lineup_compact_body_contains_player_names(self):
        """報知 X 2軍 compact 形 lineup の主要選手名が body に含まれる。"""
        blocks, _ai_body = self._build(
            title=HOCHI_FARM_LINEUP_COMPACT,
            summary=HOCHI_FARM_LINEUP_COMPACT,
            url="https://twitter.com/hochi_giants/status/2054047155913113832",
            source_name="スポーツ報知巨人班X",
            category="ドラフト・育成",
        )

        for name in ("東妻", "萩尾", "加藤", "皆川", "又木"):
            self.assertIn(name, blocks, f"player name '{name}' missing from body")

    def test_hochi_first_team_lineup_compact_renders_table_when_yahoo_empty(self):
        """報知 X 1軍 compact 形 lineup + Yahoo fetch 空 → body に table 含む。

        Fix 後: Yahoo stats が無くても compact 抽出できれば 3 列 table が出る。
        """
        blocks, _ai_body = self._build(
            title=HOCHI_FIRST_TEAM_LINEUP_COMPACT,
            summary=HOCHI_FIRST_TEAM_LINEUP_COMPACT,
            url="https://twitter.com/hochi_giants/status/2053999999999999999",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
            yahoo_lineup_rows=[],
        )

        self.assertIn(
            "nomotoke-card-lineup-table",
            blocks,
            "報知 1軍 lineup + Yahoo 空のとき compact 抽出 table が出ない",
        )

    def test_hochi_first_team_lineup_with_yahoo_stats_keeps_yahoo_table_only(self):
        """報知 X 1軍 + Yahoo stats あり → Yahoo の 7 列 table のみ (compact 重複描画なし)。

        既存の Yahoo path を壊さないこと。double-render 防止。
        """
        yahoo_rows = [
            {"order": "1", "position": "二", "name": "吉川 尚輝", "avg": ".206", "hr": "0", "rbi": "0", "sb": "2"},
            {"order": "2", "position": "左", "name": "キャベッジ", "avg": ".267", "hr": "5", "rbi": "11", "sb": "3"},
            {"order": "3", "position": "右", "name": "丸 佳浩", "avg": ".133", "hr": "1", "rbi": "6", "sb": "0"},
            {"order": "4", "position": "三", "name": "ダルベック", "avg": ".246", "hr": "7", "rbi": "19", "sb": "0"},
            {"order": "5", "position": "捕", "name": "大城 卓三", "avg": ".326", "hr": "3", "rbi": "9", "sb": "0"},
            {"order": "6", "position": "一", "name": "増田 陸", "avg": ".278", "hr": "2", "rbi": "10", "sb": "1"},
            {"order": "7", "position": "中", "name": "平山 功太", "avg": ".216", "hr": "1", "rbi": "6", "sb": "0"},
            {"order": "8", "position": "遊", "name": "浦田 俊輔", "avg": ".191", "hr": "0", "rbi": "3", "sb": "6"},
            {"order": "9", "position": "投", "name": "森田 駿哉", "avg": "-", "hr": "-", "rbi": "-", "sb": "-"},
        ]
        blocks, _ai_body = self._build(
            title=HOCHI_FIRST_TEAM_LINEUP_COMPACT,
            summary=HOCHI_FIRST_TEAM_LINEUP_COMPACT,
            url="https://twitter.com/hochi_giants/status/2053999999999999999",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
            yahoo_lineup_rows=yahoo_rows,
        )

        # Yahoo 7 列 table (`yoshilover-lineup-stats`) は出る (既存 path)
        self.assertIn("yoshilover-lineup-stats", blocks, "既存 Yahoo lineup-stats table が出ていない (regression)")
        # 報知 compact 由来 3 列 table (`nomotoke-card-lineup-table`) は出ない (double-render 防止)
        self.assertNotIn(
            "nomotoke-card-lineup-table",
            blocks,
            "Yahoo stats あるのに compact 由来 table も併存している (double-render)",
        )

    def test_non_hochi_source_lineup_unchanged_when_yahoo_empty(self):
        """非 hochi/sponichi source(Yahoo / 巨人公式X 等)で extractor 起動しない。

        regression: 既存 path への副作用なし。Yahoo fetch 空 + 報知でない
        source なら compact 由来 table は出ない (出力 unchanged)。
        """
        blocks, _ai_body = self._build(
            title="【巨人】今日のスタメン発表",
            summary=(
                "【巨人公式】本日のスタメンが発表されました\n"
                "1番（中）丸 2番（二）吉川 3番（一）岡本"
            ),
            url="https://twitter.com/TokyoGiants/status/2050000000000000000",
            source_name="巨人公式X",
            category="試合速報",
            yahoo_lineup_rows=[],
        )

        # 巨人公式X は本 ticket の対象外、compact 由来 table は出ない
        self.assertNotIn(
            "nomotoke-card-lineup-table",
            blocks,
            "非 hochi source (巨人公式X) で compact 由来 table が誤って出ている",
        )


if __name__ == "__main__":
    unittest.main()
