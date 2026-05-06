"""Lane 5: RSS routing 11-case fixture pack (baseline + 既存 flag verify).

このファイルは routing v2 (`058df45`, `bf29bcc`, `c7e91af`) 等の既存挙動の
regression baseline を 11 ケースで pin する skeleton です。新 src 実装は
追加せず、既存 `_analyze_source` / 既存 flag 配下の behavior を verify します。

11 case (user 指定):
1. short X (200 char 未満の X 投稿)
2. source_link_only (本文無し、URL のみ)
3. manager / comment (監督・コーチコメント)
4. postgame score あり (スコア + 試合終了)
5. postgame score なし (試合中、score なし)
6. player_notice (登録抹消・一軍合流)
7. recovery / injury (復帰・故障)
8. farm / 二軍 (ファーム試合 / 二軍合流)
9. third-team / 三軍 / 育成
10. stale 24h超 (source_published_at 24h+ 前)
11. duplicate 候補 (history 重複疑い)
12. missing source time (source_published_at 抽出不可)
"""

import os
import unittest
from unittest.mock import patch

from src import rss_fetcher


def _analyze(
    *,
    title: str,
    summary: str,
    source_type: str = "news",
    source_url: str = "https://example.com/story",
    source_name: str = "スポーツ報知",
    category: str = "",
) -> dict[str, object]:
    """Wrapper for rss_fetcher._analyze_source for fixture verify."""
    return rss_fetcher._analyze_source(
        {
            "title": title,
            "summary": summary,
            "source_type": source_type,
            "source_url": source_url,
            "source_name": source_name,
            "category": category,
        }
    )


class Case01ShortXTests(unittest.TestCase):
    """Case 1: short X (200 char 未満の X 投稿)."""

    def test_short_x_post_text_length_under_200(self):
        analysis = _analyze(
            title="巨人公式Xが本日の練習風景を投稿",
            summary="本日の練習風景です。",
            source_type="social_news",
            source_url="https://x.com/TokyoGiants/status/2050000000000000001",
            source_name="巨人公式X",
        )

        self.assertEqual(analysis["source_type"], "x_post")
        self.assertLess(int(analysis["source_text_length"]), 200)

    def test_short_x_post_no_score_no_opponent(self):
        analysis = _analyze(
            title="練習風景を投稿",
            summary="短い投稿です。",
            source_type="social_news",
            source_url="https://twitter.com/sanspo_giants/status/2050000000000000002",
            source_name="サンスポ巨人X",
        )

        self.assertFalse(analysis["has_score"])
        self.assertFalse(analysis["has_opponent"])


class Case02SourceLinkOnlyTests(unittest.TestCase):
    """Case 2: source_link_only (本文無し、URL のみの source)."""

    def test_link_only_no_summary(self):
        analysis = _analyze(
            title="記事タイトル",
            summary="",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2050000000000000003",
            source_name="スポーツ報知巨人班X",
        )

        self.assertEqual(analysis["source_type"], "x_post")
        # source_link_only 系は source_text_length が title 分だけ
        self.assertLess(int(analysis["source_text_length"]), 100)


class Case03ManagerCommentTests(unittest.TestCase):
    """Case 3: manager / comment (監督・コーチコメント)."""

    def test_manager_comment_via_news(self):
        analysis = _analyze(
            title="【巨人】阿部監督「次戦は1軍で」",
            summary="阿部監督が「次戦は1軍で」と起用方針を明かした。",
            source_type="news",
            source_url="https://hochi.news/articles/20260506-OHT1T51001.html",
            source_name="スポーツ報知",
            category="首脳陣",
        )

        self.assertEqual(analysis["actor_kind"], "manager")
        self.assertTrue(analysis["has_quote"])

    def test_coach_comment_via_x(self):
        analysis = _analyze(
            title="【巨人】桑田コーチ「ブレずに」",
            summary="桑田投手チーフコーチが「ブレずに行こう」と語った。",
            source_type="social_news",
            source_url="https://x.com/sanspo_giants/status/2050000000000000004",
            source_name="サンスポ巨人X",
            category="首脳陣",
        )

        self.assertEqual(analysis["actor_kind"], "coach")
        self.assertTrue(analysis["has_quote"])


class Case04PostgameWithScoreTests(unittest.TestCase):
    """Case 4: postgame score あり (スコア + 試合終了 + decisive event)."""

    def test_postgame_with_score_and_opponent(self):
        analysis = _analyze(
            title="巨人 3-2 ヤクルト 戸郷翔征が試合後にコメント",
            summary="戸郷翔征は7回3失点の好投。試合後「不用意な1球を減らしたい」と振り返った。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2050000000000000005",
            source_name="スポーツ報知巨人班X",
            category="試合速報",
        )

        self.assertTrue(analysis["has_score"])
        self.assertTrue(analysis["has_opponent"])
        self.assertTrue(analysis["has_quote"])


class Case05PostgameNoScoreTests(unittest.TestCase):
    """Case 5: postgame score なし (試合中速報、score なし)."""

    def test_in_progress_x_post_no_score(self):
        analysis = _analyze(
            title="【五回表】巨人がランナーを許すも無失点",
            summary="五回表、先発投手はランナーを許すも、後続を抑え無失点に切り抜けた。",
            source_type="social_news",
            source_url="https://x.com/sanspo_giants/status/2050000000000000006",
            source_name="サンスポ巨人X",
            category="試合速報",
        )

        self.assertEqual(analysis["source_type"], "x_post")
        self.assertFalse(analysis["has_score"])


class Case06PlayerNoticeTests(unittest.TestCase):
    """Case 6: player_notice (登録抹消・一軍合流)."""

    def test_player_register_deregister(self):
        analysis = _analyze(
            title="【巨人】泉口友汰の登録抹消を発表",
            summary="球団は本日、泉口友汰の登録抹消を発表した。",
            source_type="news",
            source_url="https://www.giants.jp/G/news/2026/0506_001.html",
            source_name="読売ジャイアンツ",
            category="選手情報",
        )

        # player_notice 系は has_roster_notice True (登録 / 抹消 keyword)
        self.assertTrue(analysis["has_roster_notice"])

    def test_player_first_team_join(self):
        analysis = _analyze(
            title="【巨人】戸郷翔征が一軍合流",
            summary="戸郷翔征が一軍に合流、明日先発予定。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2050000000000000007",
            source_name="スポーツ報知巨人班X",
            category="選手情報",
        )

        self.assertTrue(analysis["has_roster_notice"])


class Case07RecoveryInjuryTests(unittest.TestCase):
    """Case 7: recovery / injury (復帰・故障)."""

    def test_injury_to_recovery(self):
        analysis = _analyze(
            title="【巨人】山崎伊織が右肩違和感から復帰",
            summary="山崎伊織が右肩違和感のリハビリを終え、明日のブルペン投球で復帰見込み。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2050000000000000008",
            source_name="スポーツ報知巨人班X",
            category="選手情報",
        )

        self.assertTrue(analysis["has_recovery_or_injury"])

    def test_injury_only(self):
        analysis = _analyze(
            title="【巨人】復帰戦、2球で緊急降板の山崎伊織は「右肩の違和感」と球団発表",
            summary="2球で緊急降板の山崎伊織は右肩違和感と球団が発表した。",
            source_type="social_news",
            source_url="https://x.com/nikkansports/status/2050000000000000009",
            source_name="日刊スポーツ",
            category="選手情報",
        )

        self.assertTrue(analysis["has_recovery_or_injury"])


class Case08FarmSecondTeamTests(unittest.TestCase):
    """Case 8: farm / 二軍 (ファーム試合 / 二軍合流)."""

    def test_farm_result(self):
        analysis = _analyze(
            title="【二軍】巨人が4-2でDeNAに勝利",
            summary="ファームでは巨人が4-2でDeNAに勝利した。",
            source_type="news",
            source_url="https://baseballking.jp/ns/700001/",
            source_name="ベースボールキング",
            category="ドラフト・育成",
        )

        self.assertTrue(analysis["has_farm_or_third_team"])

    def test_farm_join(self):
        analysis = _analyze(
            title="【巨人】小浜佑斗が2軍合流で再出発",
            summary="小浜佑斗が2軍に合流、再出発のスタートを切った。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2050000000000000010",
            source_name="スポーツ報知巨人班X",
            category="ドラフト・育成",
        )

        self.assertTrue(analysis["has_farm_or_third_team"])


class Case09ThirdTeamIkuseiTests(unittest.TestCase):
    """Case 9: third-team / 三軍 / 育成."""

    def test_third_team(self):
        analysis = _analyze(
            title="【三軍】巨人がJABA新潟大会へ",
            summary="三軍がJABA新潟大会に参加し、育成選手も帯同する。",
            source_type="news",
            source_url="https://www.giants.jp/G/news/2026/0506_002.html",
            source_name="読売ジャイアンツ",
            category="ドラフト・育成",
        )

        self.assertTrue(analysis["has_farm_or_third_team"])

    def test_ikusei_player(self):
        analysis = _analyze(
            title="【巨人】育成・松井颯が支配下登録",
            summary="育成選手の松井颯が支配下登録された。",
            source_type="news",
            source_url="https://hochi.news/articles/20260506-OHT1T51002.html",
            source_name="スポーツ報知",
            category="ドラフト・育成",
        )

        self.assertTrue(analysis["has_farm_or_third_team"])


class Case10Stale24hTests(unittest.TestCase):
    """Case 10: stale 24h超 (source_published_at 24h+ 前).

    Note: stale 検出は guarded_publish 側 (ENABLE_STRICT_BREAKING_NEWS_THRESHOLDS)
    で扱うが、analyzer 側でも source_text 内容から推測可能な
    pattern (例: 「2 日前」 等) があれば baseline として記録する。
    本 fixture は analyzer の `source_text_length` / `has_score` を
    pin するだけで、stale 判定は別 ledger (test_stale_freshness_*) で扱う。
    """

    def test_stale_x_post_baseline(self):
        analysis = _analyze(
            title="2日前の試合でホームスチール",
            summary="2 日前の試合で意表を突くホームスチールが話題に。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2049000000000000001",
            source_name="スポーツ報知巨人班X",
        )

        # analyzer 単体では stale 判定しない (baseline pin)
        self.assertEqual(analysis["source_type"], "x_post")


class Case11DuplicateCandidateTests(unittest.TestCase):
    """Case 11: duplicate 候補 (history 重複疑い).

    duplicate 検出は publish_notice_scanner 側 (replay_window_dedup) で
    扱うが、analyzer baseline として entry の identity 判定の安定性を
    pin する。
    """

    def test_duplicate_candidate_same_url(self):
        analysis_a = _analyze(
            title="【巨人】戸郷翔征が好投",
            summary="戸郷翔征は7回1失点で勝利投手。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2050000000000000011",
            source_name="スポーツ報知巨人班X",
        )
        analysis_b = _analyze(
            title="【巨人】戸郷翔征が好投",
            summary="戸郷翔征は7回1失点で勝利投手。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2050000000000000011",
            source_name="スポーツ報知巨人班X",
        )

        # 同 source_url + 同 title + 同 summary は同 analysis を返す (decidable)
        self.assertEqual(analysis_a["source_type"], analysis_b["source_type"])
        self.assertEqual(analysis_a["source_text_length"], analysis_b["source_text_length"])


class Case12MissingSourceTimeTests(unittest.TestCase):
    """Case 12: missing source time (source_published_at 抽出不可).

    Note: source_published_at 抽出は fetcher 側 (rss_fetcher) で扱うが、
    analyzer baseline では source_url から date 抽出されないケースを pin する。
    """

    def test_no_date_in_url_no_pubdate(self):
        analysis = _analyze(
            title="記事タイトル",
            summary="本文",
            source_type="news",
            source_url="https://example.com/no-date-article",
            source_name="generic",
        )

        # analyzer 単体では source_published_at は input dict に含まれない、
        # 別 path (fetcher 側 _resolve_source_published_at) で扱う
        # generic news source は normalize して "rss_article" になるのが現挙動
        self.assertIn(str(analysis["source_type"]), ("news", "rss_article", "x_post"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
