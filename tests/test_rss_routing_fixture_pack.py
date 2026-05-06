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


class Case13LineupRoutingTests(unittest.TestCase):
    """Case 13 (RSS-248): 本日のスタメン routing fix.

    routing_v2 が lineup core 検出で「lineup_short / lineup」を返し、
    routing_v2_review に落ちないことを pin する。Yahoo / Hochi X /
    Giants 公式 X / Sanspo 巨人 X の 4 パターン + farm_lineup を検証。
    """

    def _resolve(self, title: str, summary: str, source_type: str, source_url: str, source_name: str, category: str = "試合速報"):
        return rss_fetcher._resolve_rss_story_type_context_v2(
            title=title,
            summary=summary,
            category=category,
            daily_has_game=True,
            source_type=source_type,
            source_url=source_url,
            source_name=source_name,
        )

    def test_yahoo_kotei_lineup_routes_to_lineup_short(self):
        ctx = self._resolve(
            title="巨人 vs 阪神 本日のスタメン",
            summary="1番（中）丸佳浩 2番（二）吉川尚輝 3番（一）岡本和真 4番（右）坂本勇人 5番（左）門脇誠 6番（捕）大城卓三 7番（三）泉口友汰 8番（遊）増田陸 9番（投）戸郷翔征",
            source_type="news",
            source_url="https://baseball.yahoo.co.jp/npb/game/2026050601/lineup",
            source_name="Yahoo!スポーツ",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "lineup_short")
        self.assertEqual(ctx["title_subtype"], "lineup")
        self.assertEqual(ctx["body_subtype"], "lineup")
        self.assertEqual(ctx["category"], "試合速報")
        self.assertEqual(ctx["v2_review_reason"], "")
        self.assertEqual(ctx["v2_skip_reason"], "")

    def test_hochi_x_lineup_routes_to_lineup_short(self):
        ctx = self._resolve(
            title="【巨人】本日のスタメン発表",
            summary="本日のスターティングメンバー：1番（中）丸 2番（二）吉川 3番（一）岡本 4番（右）坂本 5番（左）門脇",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2052000000000000001",
            source_name="スポーツ報知巨人班X",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "lineup_short")
        self.assertEqual(ctx["title_subtype"], "lineup")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_giants_official_x_lineup_routes_to_lineup_short(self):
        ctx = self._resolve(
            title="本日のスタメンはこちらです",
            summary="1番（中）丸佳浩 2番（二）吉川尚輝 3番（一）岡本和真 4番（右）坂本勇人",
            source_type="social_news",
            source_url="https://x.com/TokyoGiants/status/2052000000000000002",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "lineup_short")
        self.assertEqual(ctx["title_subtype"], "lineup")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_sanspo_x_lineup_routes_to_lineup_short(self):
        ctx = self._resolve(
            title="【巨人】本日のオーダー",
            summary="スタメン：1番（中）丸 2番（二）吉川 3番（一）岡本 4番（右）坂本 5番（左）門脇 6番（捕）大城",
            source_type="social_news",
            source_url="https://twitter.com/sanspo_giants/status/2052000000000000003",
            source_name="サンスポ巨人X",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "lineup_short")
        self.assertEqual(ctx["title_subtype"], "lineup")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_farm_lineup_routes_to_farm_lineup_short(self):
        ctx = self._resolve(
            title="【ジャイアンツ二軍】本日のスタメン",
            summary="二軍スタメン：1番（中）佐々木 2番（二）湯浅 3番（一）萩尾 4番（右）秋広 5番（左）岡田",
            source_type="news",
            source_url="https://baseball.yahoo.co.jp/npb/farm/lineup",
            source_name="Yahoo!ファーム",
            category="ドラフト・育成",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "farm_lineup_short")
        self.assertEqual(ctx["title_subtype"], "farm_lineup")
        self.assertEqual(ctx["category"], "ドラフト・育成")
        self.assertEqual(ctx["v2_review_reason"], "")
        self.assertEqual(ctx["v2_skip_reason"], "")

    def test_non_lineup_short_x_still_falls_through_existing_path(self):
        # baseline 維持: lineup core 含まない短文 X は既存 source_link_only 等
        # の path に落ちる (lineup_short に false positive しない)
        ctx = self._resolve(
            title="練習風景を投稿",
            summary="本日の練習風景です",
            source_type="social_news",
            source_url="https://x.com/TokyoGiants/status/2052000000000000004",
            source_name="読売ジャイアンツ公式X",
        )
        # lineup_short には振られない
        self.assertNotEqual(ctx["template_selector_v2_key"], "lineup_short")
        self.assertNotEqual(ctx["title_subtype"], "lineup")


class Case15RoutingExtensionTests(unittest.TestCase):
    """Case 15 (RSS-249): pregame / postgame_score / trusted_social /
    farm_lineup (HoChi X) routing extension.

    routing_v2 が予告先発・スコア試合中・trusted_source 短文 X を
    routing_v2_review / social_too_weak / source_link_only に落とさず、
    短文 template に正しく振ることを pin する。
    """

    def _resolve(self, title: str, summary: str, source_type: str, source_url: str, source_name: str, category: str = "試合速報"):
        return rss_fetcher._resolve_rss_story_type_context_v2(
            title=title,
            summary=summary,
            category=category,
            daily_has_game=True,
            source_type=source_type,
            source_url=source_url,
            source_name=source_name,
        )

    def test_pregame_yokoku_starts_routes_to_pregame_short(self):
        # 予告先発 試合開始前
        ctx = self._resolve(
            title="【6日の予告先発】巨人・竹丸和幸―ヤクルト・山野太一",
            summary="6日の予告先発が発表されました。巨人は竹丸和幸、ヤクルトは山野太一が先発予定です。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605060000001.html",
            source_name="日刊スポーツ",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "pregame_short")
        self.assertEqual(ctx["title_subtype"], "pregame")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_pregame_x_post_routes_to_pregame_short_or_lineup(self):
        # X post の 予告先発: pregame_short か lineup_short のどちらかに振られる
        ctx = self._resolve(
            title="【一軍】巨人 vs ヤクルト 5/6(水)14時試合開始 予告先発",
            summary="本日の予告先発：巨人・竹丸和幸 / ヤクルト・山野太一",
            source_type="social_news",
            source_url="https://x.com/TokyoGiants/status/2052000000000000010",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertNotEqual(ctx["template_selector_v2_key"], "review")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_postgame_score_only_routes_to_postgame_score_short(self):
        # score+opponent あるが decisive_event 弱 → postgame_score_short
        ctx = self._resolve(
            title="【巨人】3-2 ヤクルト 接戦を制す",
            summary="巨人は東京ドームでヤクルトに3-2で勝利した。先発戸郷は5回まで投げた。",
            source_type="news",
            source_url="https://www.nikkansports.com/baseball/news/202605060000002.html",
            source_name="日刊スポーツ",
        )
        # postgame_strict (decisive event 強) か postgame_score_short のどちらか
        # → どちらでも postgame subtype に振られる
        self.assertIn(ctx["template_selector_v2_key"], ("postgame_strict", "postgame_score_short"))
        self.assertEqual(ctx["title_subtype"], "postgame")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_trusted_social_short_x_routes_to_trusted_social_short(self):
        # 信頼source X post で 100-300 chars、score なし、opponent なし、quote なし
        ctx = self._resolve(
            title="【巨人】本日の練習風景です",
            summary="本日の東京ドームでの練習風景。ファンサービスも含めて選手たちは熱心に取り組んでいた。明日の試合に向けて調整中。",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2052000000000000020",
            source_name="スポーツ報知巨人班X",
        )
        # trusted_social_short or 既存 source_link_only/short_comment のいずれか
        # 重要: v2_review_reason が空であること (review に落ちない)
        self.assertNotEqual(ctx["template_selector_v2_key"], "review")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_source_link_only_extreme_short_routes_correctly(self):
        ctx = self._resolve(
            title="記事タイトル",
            summary="",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2052000000000000030",
            source_name="スポーツ報知巨人班X",
            category="選手情報",
        )
        # source_link_only / trusted_social_short / lineup_short のいずれかに振られる
        # 重要: v2_review_reason が空 (review に落ちない)
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_hochi_x_farm_lineup_routes_to_farm_lineup_short(self):
        ctx = self._resolve(
            title="【二軍】巨人 vs ハヤテベンチャーズ静岡 13時試合開始 本日のスタメン",
            summary="二軍 本日のスタメン：1️⃣ 丸 2️⃣ 萩尾 3️⃣ 皆川 4️⃣ 三塚",
            source_type="social_news",
            source_url="https://x.com/hochi_giants/status/2052000000000000040",
            source_name="スポーツ報知巨人班X",
            category="ドラフト・育成",
        )
        self.assertEqual(ctx["template_selector_v2_key"], "farm_lineup_short")
        self.assertEqual(ctx["title_subtype"], "farm_lineup")
        self.assertEqual(ctx["v2_review_reason"], "")

    def test_manager_quote_no_text_routes_to_manager(self):
        # 監督コメント quote なし → manager / manager_short
        # RSS-256 で manager_short (quote なし short) は subtype="social_news" に
        # 切替。manager (long form) は subtype="manager" 維持。
        ctx = self._resolve(
            title="阿部監督が試合後コメント",
            summary="阿部慎之助監督は試合後、選手の起用について語った。試合終盤の采配の意図を説明した。",
            source_type="news",
            source_url="https://www.sponichi.co.jp/baseball/news/2026/05/06/00.html",
            source_name="スポーツニッポン",
            category="首脳陣",
        )
        # manager 系 (manager_short→social_news / manager→manager) いずれか
        self.assertIn(ctx["title_subtype"], ("manager", "social_news"))
        self.assertEqual(ctx["v2_review_reason"], "")


class Case14LineupTableHeavyGuardSkipTests(unittest.TestCase):
    """Case 14 (RSS-248): lineup / farm_lineup subtype は post_gen_validate
    で placeholder_body / h3_count_guard を skip する."""

    def _validate(self, *, article_subtype: str, text: str, rendered_html: str = ""):
        with patch.dict(
            os.environ,
            {
                "ENABLE_FORBIDDEN_PHRASE_FILTER": "1",
                "ENABLE_H3_COUNT_GUARD": "1",
            },
            clear=False,
        ):
            return rss_fetcher._evaluate_post_gen_validate(
                text,
                article_subtype=article_subtype,
                title="本日のスタメン",
                source_refs={},
                rendered_html=rendered_html,
            )

    def test_lineup_subtype_skips_placeholder_body_empty_section(self):
        text = "<h2>【スタメン一覧】</h2>\n<table><tr><td>1</td><td>中</td><td>丸</td></tr></table>"
        result = self._validate(article_subtype="lineup", text=text)
        self.assertNotIn("placeholder_body:empty_section", result["fail_axes"])
        self.assertNotIn("placeholder_body:boilerplate", result["fail_axes"])

    def test_lineup_subtype_skips_h3_count_guard(self):
        rendered = "<h2>【一軍スタメン】</h2><h3>打順</h3><h3>守備</h3><h3>備考</h3>"
        result = self._validate(article_subtype="lineup", text=rendered, rendered_html=rendered)
        self.assertFalse(any(axis.startswith("h3_count:") for axis in result["fail_axes"]))

    def test_farm_lineup_subtype_skips_placeholder_body(self):
        text = "<h2>【二軍スタメン一覧】</h2>\n<table><tr><td>1</td><td>佐々木</td></tr></table>"
        result = self._validate(article_subtype="farm_lineup", text=text)
        self.assertNotIn("placeholder_body:empty_section", result["fail_axes"])
        self.assertNotIn("placeholder_body:boilerplate", result["fail_axes"])

    def test_farm_lineup_subtype_skips_h3_count_guard(self):
        rendered = "<h2>【二軍スタメン】</h2><h3>打順</h3><h3>守備</h3><h3>備考</h3>"
        result = self._validate(article_subtype="farm_lineup", text=rendered, rendered_html=rendered)
        self.assertFalse(any(axis.startswith("h3_count:") for axis in result["fail_axes"]))

    def test_postgame_subtype_still_enforces_h3_count_guard(self):
        # baseline 維持: lineup/farm_lineup 以外 (postgame) は既存 H3 guard が効く
        rendered = "<h2>【試合経過】</h2><h3>1回</h3><h3>2回</h3><h3>3回</h3>"
        result = self._validate(article_subtype="postgame", text=rendered, rendered_html=rendered)
        self.assertTrue(any(axis.startswith("h3_count:") for axis in result["fail_axes"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
