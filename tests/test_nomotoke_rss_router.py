"""Tests for src/nomotoke_rss_router.py — NOMOTOKE-RSS-CARD-001A.

LOCKED quality boundary (router NEVER fires these template keys):
    - nomotoke_card_lineup_v1
    - nomotoke_card_postgame_v1
    - nomotoke_card_live_at_bats_v1
    - nomotoke_card_player_stats_v1
    - nomotoke_card_broadcast_v1
    - nomotoke_card_official_notice_v1
    - nomotoke_card_video_v1

Acceptance:
    - WP write 0 (mocked, runtime asserted)
    - Gemini call 0 (mocked, runtime asserted)
    - rss_fetcher import not triggered by importing the router
    - blocked templates absent from next_recommended_templates
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src on path (matches manual_intake / nomotoke_card_renderer pattern).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.nomotoke_rss_router import (  # noqa: E402
    MANAGER_NAME_ALLOWLIST,
    QUALITY_CEILING_BY_TEMPLATE,
    QUOTE_SHORT_MAX_CHARS,
    REQUIRED_FACTS_BY_TEMPLATE,
    RSS_ONLY_ALLOWED_TEMPLATES,
    RSS_ONLY_BLOCKED_TEMPLATES,
    SKIP_REASON_TAXONOMY,
    TEMPLATE_KEY_MANAGER_COMMENT,
    TEMPLATE_KEY_PLAYER_COMMENT,
    TEMPLATE_KEY_PREGAME_PITCHER,
    TEMPLATE_KEY_SHORT_NEWS_URL,
    derive_next_recommended,
    derive_not_suitable_for_rss,
    detect_pregame_pitcher,
    extract_manager_quote,
    extract_player_quote,
    is_giants_relevant,
    is_stale,
    normalize_canonical_url,
    route_rss_entry_to_nomotoke_card,
    source_tier,
)


def _entry(title="", summary="", link="", published=""):
    return {"title": title, "summary": summary, "link": link, "published": published}


# ---------------------------------------------------------------------------
# LOCKED quality boundary — router never fires blocked templates
# ---------------------------------------------------------------------------
class LockedBoundaryTests(unittest.TestCase):
    def _route(self, **kw):
        return route_rss_entry_to_nomotoke_card(
            _entry(**{k: kw.pop(k) for k in list(kw) if k in {"title", "summary", "link", "published"}}),
            source_name=kw.pop("source_name", "TokyoGiants"),
            source_url=kw.pop("source_url", "https://twitter.com/TokyoGiants/status/123"),
        )

    def test_router_never_fires_lineup_card(self):
        r = self._route(
            title="巨人スタメン発表 1番坂本 2番丸 3番岡本 4番中田 5番ウォーカー",
            summary="vs ヤクルト",
        )
        self.assertNotIn(r.template_key, RSS_ONLY_BLOCKED_TEMPLATES)
        self.assertNotEqual(r.template_key, "nomotoke_card_lineup_v1")

    def test_router_never_fires_postgame_full(self):
        r = self._route(
            title="【試合終了】巨人 6-3 ヤクルト 岡本2HR",
            summary="勝利",
        )
        self.assertNotIn(r.template_key, RSS_ONLY_BLOCKED_TEMPLATES)
        self.assertNotEqual(r.template_key, "nomotoke_card_postgame_v1")

    def test_router_never_fires_live_at_bats(self):
        r = self._route(
            title="巨人 5回終了 3-2 ヤクルト 岡本本塁打",
            summary="3-2 リード",
        )
        self.assertNotIn(r.template_key, RSS_ONLY_BLOCKED_TEMPLATES)

    def test_router_never_fires_player_stats(self):
        r = self._route(
            title="巨人・岡本和真 今季打撃成績 .280 12HR 35打点",
            summary="OPS .920",
        )
        self.assertNotIn(r.template_key, RSS_ONLY_BLOCKED_TEMPLATES)

    def test_router_never_fires_broadcast(self):
        r = self._route(
            title="本日 巨人vsヤクルト 中継情報 日テレ G+ ラジオ",
            summary="中継一覧",
        )
        self.assertNotIn(r.template_key, RSS_ONLY_BLOCKED_TEMPLATES)

    def test_router_never_fires_official_notice(self):
        r = self._route(
            title="【公示】巨人 田和廉を登録抹消 竹丸を登録",
            summary="NPB公示",
        )
        # Router may emit short_news_url fallback OR skip with reason.
        self.assertNotIn(r.template_key, RSS_ONLY_BLOCKED_TEMPLATES)

    def test_router_never_fires_video_without_youtube_source(self):
        r = self._route(
            title="巨人岡本ホームラン動画 公式公開",
            summary="動画",
        )
        self.assertNotIn(r.template_key, RSS_ONLY_BLOCKED_TEMPLATES)

    def test_blocked_templates_count_matches_table(self):
        # 7 blocked templates per the LOCKED table.
        self.assertEqual(len(RSS_ONLY_BLOCKED_TEMPLATES), 7)
        for tk in RSS_ONLY_BLOCKED_TEMPLATES:
            self.assertIn(tk, QUALITY_CEILING_BY_TEMPLATE)
            ceiling = QUALITY_CEILING_BY_TEMPLATE[tk]
            self.assertFalse(ceiling["allow_rss_only"])

    def test_allowed_templates_count_matches_table(self):
        self.assertEqual(len(RSS_ONLY_ALLOWED_TEMPLATES), 4)
        for tk in RSS_ONLY_ALLOWED_TEMPLATES:
            self.assertIn(tk, QUALITY_CEILING_BY_TEMPLATE)
            self.assertTrue(QUALITY_CEILING_BY_TEMPLATE[tk]["allow_rss_only"])


# ---------------------------------------------------------------------------
# Required-facts gate
# ---------------------------------------------------------------------------
class RequiredFactsGateTests(unittest.TestCase):
    def test_pregame_pitcher_skipped_when_pitcher_pair_missing(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="本日の予告先発が発表される 巨人",
                summary="",
                link="https://twitter.com/npb/status/123",
                published=(datetime.now(timezone.utc)).strftime("%a, %d %b %Y %H:%M:%S +0000"),
            ),
            source_name="NPB公式X",
            source_url="https://twitter.com/npb/status/123",
        )
        self.assertFalse(r.matched)
        self.assertEqual(
            r.skip_reason,
            "insufficient_required_facts:pregame_pitcher:pitcher_pair",
        )

    def test_pregame_pitcher_matched_when_pair_extracted(self):
        # Recent published_at avoids stale skip
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="本日の予告先発 巨人 戸郷 対 小川 ヤクルト",
                summary="",
                link="https://twitter.com/npb/status/124",
                published=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
            ),
            source_name="NPB公式X",
            source_url="https://twitter.com/npb/status/124",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_PREGAME_PITCHER)
        self.assertEqual(list(r.extracted_facts["pitcher_pair"]), ["戸郷", "小川"])

    def test_manager_comment_matched_in_allowlist(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人・阿部監督「反省、修正してやる」",
                summary="",
                link="https://twitter.com/Sanspo_Giants/status/1",
            ),
            source_name="サンスポ巨人X",
            source_url="https://twitter.com/Sanspo_Giants/status/1",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_MANAGER_COMMENT)
        self.assertEqual(r.extracted_facts["manager_name"], "阿部")

    def test_manager_comment_skipped_when_quote_empty(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人・阿部監督、リハビリについて言及",
                summary="",
                link="https://twitter.com/Sanspo_Giants/status/2",
            ),
            source_name="サンスポ巨人X",
            source_url="https://twitter.com/Sanspo_Giants/status/2",
        )
        # No quote -> falls through manager_comment; topic-only triggers manager_comment matching but quote_short empty
        # Since quote_short is empty AND manager allowlist passes, skip with insufficient_required_facts.
        self.assertFalse(r.matched)
        self.assertEqual(
            r.skip_reason,
            "insufficient_required_facts:manager_comment:quote_short",
        )

    def test_manager_not_in_allowlist_x_only_post_skipped(self):
        # NOMOTOKE-RSS-CARD-001B-XPOST-FIX: an X-only post whose manager
        # quote is not in the allowlist no longer falls back to
        # short_news_url. Without an external article URL or video URL
        # it is dropped with x_post_not_article_source.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 関連: 中日・立浪監督「打線再編」",
                summary="",
                link="https://twitter.com/SponichiYakyu/status/9",
            ),
            source_name="SponichiYakyu",
            source_url="https://twitter.com/SponichiYakyu/status/9",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "x_post_not_article_source")

    def test_manager_not_in_allowlist_with_external_url_promotes_primary(self):
        # When the X body carries an external article URL the entry is
        # rerouted to short_news_url with the external URL as primary
        # source and the X URL demoted to related_source_url / x_embed_url.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 関連: 中日・立浪監督「打線再編」",
                summary="https://hochi.news/articles/abc",
                link="https://twitter.com/SponichiYakyu/status/9",
            ),
            source_name="SponichiYakyu",
            source_url="https://twitter.com/SponichiYakyu/status/9",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_SHORT_NEWS_URL)
        self.assertIn("hochi.news", r.canonical_url)
        self.assertIn(
            "twitter.com",
            r.would_render_call["data_preview"].get("related_source_url", ""),
        )
        self.assertEqual(
            r.would_render_call["data_preview"]["source_url"],
            "https://hochi.news/articles/abc",
        )
        self.assertIn("x_embed_url", r.extracted_facts)

    def test_player_comment_matched(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人・岡本「思い切り振った」",
                summary="",
                link="https://twitter.com/hochi_giants/status/9",
            ),
            source_name="スポーツ報知巨人班X",
            source_url="https://twitter.com/hochi_giants/status/9",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_PLAYER_COMMENT)
        self.assertIn("player_name", r.extracted_facts)
        self.assertIn("quote_short", r.extracted_facts)

    def test_quote_too_long_skipped(self):
        long_quote = "あ" * (QUOTE_SHORT_MAX_CHARS + 1)
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title=f"巨人・阿部監督「{long_quote}」",
                summary="",
                link="https://twitter.com/Sanspo_Giants/status/3",
            ),
            source_name="サンスポ巨人X",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "quote_too_long")

    def test_quote_at_cap_passes(self):
        cap_quote = "あ" * QUOTE_SHORT_MAX_CHARS
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title=f"巨人・阿部監督「{cap_quote}」",
                summary="",
                link="https://twitter.com/Sanspo_Giants/status/4",
            ),
            source_name="サンスポ巨人X",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_MANAGER_COMMENT)


# ---------------------------------------------------------------------------
# Giants relevance
# ---------------------------------------------------------------------------
class GiantsRelevanceTests(unittest.TestCase):
    def test_tier1_grants_relevance(self):
        self.assertTrue(is_giants_relevant("無関係タイトル", "", "TokyoGiants"))

    def test_non_tier1_with_keyword_relevant(self):
        self.assertTrue(is_giants_relevant("巨人 試合速報", "", "SponichiYakyu"))

    def test_non_tier1_without_keyword_skipped(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="阪神・佐藤輝明「打席で集中」",
                summary="",
                link="https://twitter.com/SponichiYakyu/status/77",
            ),
            source_name="SponichiYakyu",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "not_giants_related")

    def test_unrelated_skipped(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="東京女子プロレス 桐生真弥 王者鈴芽",
                summary="",
                link="https://twitter.com/nikkansports/status/1",
            ),
            source_name="日刊スポーツX",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "not_giants_related")


# ---------------------------------------------------------------------------
# URL safety / canonical normalize / dedupe
# ---------------------------------------------------------------------------
class UrlNormalizeTests(unittest.TestCase):
    def test_unsafe_javascript_url_skipped(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(title="巨人ニュース", summary="", link="javascript:alert(1)"),
            source_name="TokyoGiants",
            source_url="javascript:alert(1)",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "unsafe_url")

    def test_normalize_strips_utm_and_ref(self):
        u = normalize_canonical_url(
            "https://hochi.news/articles/abc?utm_source=tw&utm_campaign=x&ref=123&id=42"
        )
        self.assertNotIn("utm_source", u)
        self.assertNotIn("utm_campaign", u)
        self.assertNotIn("ref=", u)
        self.assertIn("id=42", u)

    def test_normalize_x_com_to_twitter(self):
        u = normalize_canonical_url("https://x.com/TokyoGiants/status/123")
        self.assertEqual(u, "https://twitter.com/TokyoGiants/status/123")
        u2 = normalize_canonical_url("https://www.x.com/TokyoGiants/status/123")
        self.assertEqual(u2, "https://twitter.com/TokyoGiants/status/123")

    def test_normalize_strips_trailing_slash(self):
        u = normalize_canonical_url("https://example.com/path/")
        self.assertEqual(u, "https://example.com/path")

    def test_normalize_drops_fragment(self):
        u = normalize_canonical_url("https://example.com/path#frag")
        self.assertEqual(u, "https://example.com/path")

    def test_normalize_lowercases_scheme_host(self):
        u = normalize_canonical_url("HTTPS://Example.COM/path")
        self.assertEqual(u, "https://example.com/path")


# ---------------------------------------------------------------------------
# Tier mapping
# ---------------------------------------------------------------------------
class TierTests(unittest.TestCase):
    def test_tier1(self):
        self.assertEqual(source_tier("TokyoGiants"), 1)
        self.assertEqual(source_tier("巨人公式X"), 1)

    def test_tier2(self):
        self.assertEqual(source_tier("npb"), 2)
        self.assertEqual(source_tier("NPB公式X"), 2)

    def test_tier3(self):
        self.assertEqual(source_tier("SponichiYakyu"), 3)

    def test_unknown(self):
        self.assertEqual(source_tier("foobar"), 0)
        self.assertEqual(source_tier(""), 0)


# ---------------------------------------------------------------------------
# Stale check
# ---------------------------------------------------------------------------
class StaleTests(unittest.TestCase):
    def test_pregame_stale_after_36h(self):
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        )
        # Without explicit timezone marker the parser assumes UTC.
        old_iso = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.assertTrue(is_stale(old_iso, TEMPLATE_KEY_PREGAME_PITCHER))

    def test_pregame_fresh_under_36h(self):
        fresh_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertFalse(is_stale(fresh_iso, TEMPLATE_KEY_PREGAME_PITCHER))

    def test_other_templates_not_stale_capped(self):
        old_iso = (datetime.now(timezone.utc) - timedelta(hours=720)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.assertFalse(is_stale(old_iso, TEMPLATE_KEY_SHORT_NEWS_URL))


# ---------------------------------------------------------------------------
# NOMOTOKE phrasing guard
# ---------------------------------------------------------------------------
class NomotokePhrasingGuardTests(unittest.TestCase):
    def test_raises_on_forbidden_in_title(self):
        with self.assertRaises(ValueError) as ctx:
            route_rss_entry_to_nomotoke_card(
                _entry(title="巨人ヤクルト戦 ｶｯﾀｶﾞﾈｰ", link="https://x.com/foo/status/1"),
                source_name="TokyoGiants",
            )
        self.assertIn("nomotoke_phrasing_detected", str(ctx.exception))

    def test_raises_on_forbidden_in_summary(self):
        with self.assertRaises(ValueError):
            route_rss_entry_to_nomotoke_card(
                _entry(title="巨人ニュース", summary="ﾏｹﾀｶﾞﾈｰ", link="https://x.com/foo/status/2"),
                source_name="TokyoGiants",
            )


# ---------------------------------------------------------------------------
# next_recommended / not_suitable
# ---------------------------------------------------------------------------
class RecommendationTests(unittest.TestCase):
    def test_empty_when_no_hits(self):
        out = derive_next_recommended({}, {})
        self.assertEqual(out, [])

    def test_blocked_template_never_recommended_even_when_forced(self):
        # Even if we feed counts for blocked templates, output must exclude them.
        # (Defensive test — router cannot produce them but caller might.)
        forced_counts = {tk: 100 for tk in RSS_ONLY_BLOCKED_TEMPLATES}
        forced_conf = {tk: {"high": 100} for tk in RSS_ONLY_BLOCKED_TEMPLATES}
        out = derive_next_recommended(forced_counts, forced_conf)
        for tk in RSS_ONLY_BLOCKED_TEMPLATES:
            self.assertNotIn(tk, out)

    def test_recommended_requires_min_hit(self):
        counts = {TEMPLATE_KEY_MANAGER_COMMENT: 3}
        conf = {TEMPLATE_KEY_MANAGER_COMMENT: {"high": 3}}
        out = derive_next_recommended(counts, conf)
        self.assertNotIn(TEMPLATE_KEY_MANAGER_COMMENT, out)

    def test_recommended_passes_min_threshold(self):
        counts = {TEMPLATE_KEY_MANAGER_COMMENT: 10}
        conf = {TEMPLATE_KEY_MANAGER_COMMENT: {"high": 8, "low": 2}}
        out = derive_next_recommended(counts, conf)
        self.assertIn(TEMPLATE_KEY_MANAGER_COMMENT, out)

    def test_not_suitable_lists_blocked(self):
        out = derive_not_suitable_for_rss()
        for tk in RSS_ONLY_BLOCKED_TEMPLATES:
            self.assertIn(tk, out)


# ---------------------------------------------------------------------------
# Skip reason taxonomy is closed
# ---------------------------------------------------------------------------
class SkipReasonTaxonomyTests(unittest.TestCase):
    def test_taxonomy_includes_unsafe_url(self):
        self.assertIn("unsafe_url", SKIP_REASON_TAXONOMY)

    def test_taxonomy_includes_quote_too_long(self):
        self.assertIn("quote_too_long", SKIP_REASON_TAXONOMY)

    def test_taxonomy_includes_manager_not_in_allowlist(self):
        self.assertIn("manager_not_in_allowlist", SKIP_REASON_TAXONOMY)

    def test_taxonomy_includes_pregame_pair(self):
        self.assertIn(
            "insufficient_required_facts:pregame_pitcher:pitcher_pair",
            SKIP_REASON_TAXONOMY,
        )

    def test_taxonomy_includes_x_post_not_article_source(self):
        self.assertIn("x_post_not_article_source", SKIP_REASON_TAXONOMY)

    def test_taxonomy_includes_video_source_detected(self):
        self.assertIn("video_source_detected", SKIP_REASON_TAXONOMY)


# ---------------------------------------------------------------------------
# X-only post guard (NOMOTOKE-RSS-CARD-001B-XPOST-FIX)
# ---------------------------------------------------------------------------
class XPostOnlyGuardTests(unittest.TestCase):
    """An X URL alone is never a publishable short_news_url article.

    The guard reroutes / promotes / skips per the body content of the
    X post: external article URL → primary swap, official video URL →
    skip with video_source_detected, otherwise → skip with
    x_post_not_article_source. Manager / player quote branches still take
    precedence (handled in earlier branches of the router).
    """

    def test_tokyogiants_score_only_x_post_skipped(self):
        # 64798 reproduction: TokyoGiants 試合終了 X with score in title only.
        # NOMOTOKE-TEMPLATE-ROUTING-AUDIT-001 update: this title now hits
        # the earlier ``live_inning_blurb_not_article`` guard at the title
        # 【試合終了】 prefix, before reaching the x_post_not_article_source
        # branch. Either skip class is a valid "no draft" outcome — accept
        # both so the regression intent (no draft for score-only X) is
        # preserved without locking the path to a single skip reason.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="【試合終了】巨人 0-5 ヤクルト 9回は走者を出すことが出来ず試合終了",
                summary="",
                link="https://x.com/TokyoGiants/status/2051930205841936785",
            ),
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/2051930205841936785",
        )
        self.assertFalse(r.matched)
        self.assertIn(
            r.skip_reason,
            {"live_inning_blurb_not_article", "x_post_not_article_source"},
        )
        self.assertEqual(r.template_key, "")

    def test_x_post_with_giants_jp_url_promotes_primary_source(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 試合詳細はこちら https://www.giants.jp/G/game/result/2026/0506.html",
                summary="",
                link="https://x.com/TokyoGiants/status/9001",
            ),
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/9001",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_SHORT_NEWS_URL)
        self.assertIn("giants.jp", r.canonical_url)
        self.assertEqual(
            r.would_render_call["data_preview"]["source_url"],
            "https://www.giants.jp/G/game/result/2026/0506.html",
        )
        self.assertEqual(
            r.would_render_call["data_preview"]["related_source_url"],
            "https://x.com/TokyoGiants/status/9001",
        )
        self.assertEqual(
            r.extracted_facts["x_embed_url"],
            "https://x.com/TokyoGiants/status/9001",
        )
        # related_links is wired so the renderer surfaces the X URL in HTML.
        rl = r.would_render_call["data_preview"].get("related_links")
        self.assertIsInstance(rl, list)
        self.assertEqual(len(rl), 1)
        self.assertEqual(rl[0]["url"], "https://x.com/TokyoGiants/status/9001")
        self.assertIn("巨人公式X", rl[0]["label"])

    def test_x_post_with_hochi_news_url_promotes_primary_source(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 岡本 速報 https://hochi.news/articles/20260506-OHT1T51123.html",
                summary="",
                link="https://x.com/hochi_giants/status/9002",
            ),
            source_name="スポーツ報知巨人班X",
            source_url="https://x.com/hochi_giants/status/9002",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_SHORT_NEWS_URL)
        self.assertIn("hochi.news", r.canonical_url)

    def test_abe_quote_x_post_routes_to_manager_comment_not_short_news(self):
        # Manager quote branch fires BEFORE the X-only guard so this still
        # routes to manager_comment despite being an X-only post.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人・阿部監督「集中して臨むだけ」",
                summary="",
                link="https://x.com/Sanspo_Giants/status/9003",
            ),
            source_name="サンスポ巨人X",
            source_url="https://x.com/Sanspo_Giants/status/9003",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_MANAGER_COMMENT)
        self.assertEqual(r.extracted_facts["manager_name"], "阿部")

    def test_player_quote_x_post_routes_to_player_comment_not_short_news(self):
        # Player quote branch also takes precedence over the X-only guard.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人・大勢「真っ直ぐで押し切れた」",
                summary="",
                link="https://x.com/hochi_giants/status/9004",
            ),
            source_name="スポーツ報知巨人班X",
            source_url="https://x.com/hochi_giants/status/9004",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_PLAYER_COMMENT)
        self.assertEqual(r.extracted_facts["player_name"], "大勢")

    def test_x_post_with_youtube_url_skipped_as_video_source(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 ハイライト動画 https://www.youtube.com/watch?v=abc12345678",
                summary="",
                link="https://x.com/TokyoGiants/status/9005",
            ),
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/9005",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "video_source_detected")

    def test_x_post_with_giants_tv_url_skipped_as_video_source(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 試合動画 https://giants-tv.jp/p/movie/123",
                summary="",
                link="https://x.com/TokyoGiants/status/9006",
            ),
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/9006",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "video_source_detected")

    def test_external_article_url_extractor_filters_x_urls(self):
        from src.nomotoke_rss_router import (
            extract_external_article_url,
            is_x_post_url,
        )

        # Body with both an X URL (related) and a giants.jp URL (article).
        title = "巨人 速報 https://x.com/foo/status/1"
        summary = "詳細 https://www.giants.jp/G/news/2026/05/06/abc.html"
        out = extract_external_article_url(
            title, summary, exclude_canonical="https://twitter.com/foo/status/1"
        )
        self.assertIn("giants.jp", out)
        self.assertFalse(is_x_post_url(out))

    def test_external_article_url_extractor_returns_empty_when_only_x_urls(self):
        from src.nomotoke_rss_router import extract_external_article_url

        title = "巨人 試合終了 https://twitter.com/TokyoGiants/status/1"
        summary = "https://x.com/foo/status/2"
        out = extract_external_article_url(
            title, summary, exclude_canonical="https://twitter.com/TokyoGiants/status/1"
        )
        self.assertEqual(out, "")

    def test_is_x_post_url_recognizes_canonicalized_hosts(self):
        from src.nomotoke_rss_router import is_x_post_url

        self.assertTrue(
            is_x_post_url("https://twitter.com/TokyoGiants/status/1")
        )
        self.assertFalse(is_x_post_url("https://hochi.news/articles/abc"))
        self.assertFalse(is_x_post_url(""))

    def test_date_label_uses_japanese_format_no_score_pattern(self):
        # NOMOTOKE-RSS-CARD-001B-DATELABEL-FIX: date_label must not contain
        # \d{1,2}-\d{1,2} so it never registers as a phantom score in the
        # body's score-consistency check.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 試合詳細はこちら https://www.giants.jp/G/game/result/2026/0506.html",
                summary="",
                link="https://x.com/TokyoGiants/status/9100",
                published="Wed, 06 May 2026 09:30:00 +0000",
            ),
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/9100",
        )
        self.assertTrue(r.matched)
        date_label = r.would_render_call["data_preview"]["date_label"]
        self.assertEqual(date_label, "2026年5月6日")
        # The exact dash-pattern that triggered phantom (5,6) tokens on
        # 64798 / 64800 / 64801 must not appear in the date label.
        import re
        self.assertIsNone(re.search(r"\d{1,2}-\d{1,2}", date_label))

    def test_short_news_url_rendered_body_has_no_phantom_score_tokens(self):
        # End-to-end check: render a real-shaped short_news_url card and
        # confirm the body's score tokens collapse to a single legitimate
        # value — never a phantom (5, 6) from date metadata. The fact card
        # echoes the score so duplicates of the SAME pair are expected;
        # what we forbid is two DISTINCT pairs which would trigger
        # review_score_order_mismatch_review (the gate that held
        # 64798 / 64800 / 64801 before the DATELABEL-FIX).
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.baseball_numeric_fact_consistency import extract_scores
        from src.nomotoke_card_renderer import select_renderer

        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 試合詳細はこちら https://www.giants.jp/G/game/result/2026/0506.html",
                summary="巨人は0-5でヤクルトに敗戦、試合詳細は球団公式ページで公開。",
                link="https://x.com/TokyoGiants/status/9101",
                published="Wed, 06 May 2026 09:30:00 +0000",
            ),
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/9101",
        )
        self.assertTrue(r.matched)
        renderer = select_renderer(r.template_key)
        rendered = renderer(r.would_render_call["data_preview"])
        body = rendered.get("content_html", "")
        tokens = [t.pair for t in extract_scores(body)]
        # All tokens collapse to the single legitimate (0, 5) — phantom
        # (5, 6) from date metadata must NOT appear.
        self.assertGreater(len(tokens), 0)
        self.assertEqual({tuple(p) for p in tokens}, {(0, 5)})

    def test_non_x_source_short_news_url_unaffected(self):
        # Regular HTTP RSS source (non-X) still falls through to short_news_url
        # without going through the X guard.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 ニュース",
                summary="",
                link="https://hochi.news/articles/20260506-OHT1T51999.html",
            ),
            source_name="スポーツ報知 巨人",
            source_url="https://hochi.news/articles/20260506-OHT1T51999.html",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_SHORT_NEWS_URL)
        self.assertNotIn("x_embed_url", r.extracted_facts)
        self.assertNotIn(
            "related_source_url",
            r.would_render_call["data_preview"],
        )


# ---------------------------------------------------------------------------
# Real-shape fixtures (snapshot test)
# ---------------------------------------------------------------------------
class RealShapeFixtureTests(unittest.TestCase):
    FIXTURE_DIR = ROOT / "tests" / "fixtures" / "nomotoke_rss_router"

    def test_fixtures_directory_has_at_least_8_files(self):
        files = sorted(self.FIXTURE_DIR.glob("*.json"))
        self.assertGreaterEqual(len(files), 8)

    def test_each_fixture_routes_deterministically(self):
        files = sorted(self.FIXTURE_DIR.glob("*.json"))
        self.assertGreater(len(files), 0)
        for f in files:
            obj = json.loads(f.read_text(encoding="utf-8"))
            r = route_rss_entry_to_nomotoke_card(
                {
                    "title": obj.get("title", ""),
                    "summary": obj.get("summary", ""),
                    "link": obj.get("link", ""),
                    "published": obj.get("published", ""),
                },
                source_name=obj.get("source_name", ""),
                source_url=obj.get("link", ""),
            )
            # Snapshot stable shape: blocked templates never emerge.
            self.assertNotIn(
                r.template_key,
                RSS_ONLY_BLOCKED_TEMPLATES,
                f"fixture {f.name} produced blocked template {r.template_key}",
            )
            # If matched: dedupe_key non-empty, confidence in {high,medium,low}
            if r.matched:
                self.assertNotEqual(r.dedupe_key, "")
                self.assertIn(r.confidence, {"high", "medium", "low"})


# ---------------------------------------------------------------------------
# Runtime guarantees: WP write 0 / Gemini 0 / no rss_fetcher import
# ---------------------------------------------------------------------------
class RuntimeIsolationTests(unittest.TestCase):
    def test_router_module_does_not_import_rss_fetcher(self):
        # Take a snapshot before importing router again.
        before = set(sys.modules.keys())
        import importlib
        importlib.reload(sys.modules["src.nomotoke_rss_router"])
        # rss_fetcher must NOT be loaded by reloading the router.
        # (It may already exist from other tests, but the reload itself shouldn't pull it in.)
        # Best check: the router's source has no `from src.rss_fetcher` / `import rss_fetcher`.
        src_path = ROOT / "src" / "nomotoke_rss_router.py"
        text = src_path.read_text(encoding="utf-8")
        self.assertNotIn("from src.rss_fetcher", text)
        self.assertNotIn("import rss_fetcher", text)

    def test_router_does_not_call_wp_create_post(self):
        with patch("src.wp_client.WPClient.create_post") as wp_mock, patch(
            "src.nomotoke_card_renderer.select_renderer"
        ) as render_mock:
            render_mock.return_value = lambda d: {"title": "", "content_html": ""}
            r = route_rss_entry_to_nomotoke_card(
                _entry(
                    title="巨人・阿部監督「反省して修正する」",
                    link="https://twitter.com/Sanspo_Giants/status/9",
                ),
                source_name="サンスポ巨人X",
            )
            self.assertTrue(r.matched)
        wp_mock.assert_not_called()

    def test_dry_run_cli_does_not_call_wp_create_post(self):
        # Run the CLI's json-fixture pass and assert WPClient.create_post is never called.
        from src.tools import run_nomotoke_rss_card_dry_run as cli
        with tempfile.TemporaryDirectory() as tmp:
            fx_dir = Path(tmp) / "fx"
            fx_dir.mkdir()
            (fx_dir / "01_test.json").write_text(
                json.dumps({
                    "source_name": "TokyoGiants",
                    "title": "巨人 試合速報",
                    "summary": "ヤクルト戦",
                    "link": "https://twitter.com/TokyoGiants/status/1",
                    "published": "",
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch("src.wp_client.WPClient.create_post") as wp_mock:
                cli.run_json_fixture_pass(fx_dir)
                wp_mock.assert_not_called()

    def test_dry_run_cli_does_not_call_gemini(self):
        # Mock-patch every Gemini surface; assert all uncalled.
        from src.tools import run_nomotoke_rss_card_dry_run as cli
        with tempfile.TemporaryDirectory() as tmp:
            fx_dir = Path(tmp) / "fx"
            fx_dir.mkdir()
            (fx_dir / "01_test.json").write_text(
                json.dumps({
                    "source_name": "TokyoGiants",
                    "title": "巨人・阿部監督「反省」",
                    "summary": "",
                    "link": "https://twitter.com/TokyoGiants/status/1",
                    "published": "",
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            patches = []
            for path in (
                "src.rss_fetcher._request_gemini_strict_text",
                "src.rss_fetcher.build_news_block",
            ):
                try:
                    patches.append(patch(path))
                except Exception:
                    continue
            mocks = [p.start() for p in patches]
            try:
                cli.run_json_fixture_pass(fx_dir)
                for m in mocks:
                    m.assert_not_called()
            finally:
                for p in patches:
                    p.stop()


# ---------------------------------------------------------------------------
# Quality ceiling table integrity
# ---------------------------------------------------------------------------
class QualityCeilingTests(unittest.TestCase):
    def test_all_templates_in_quality_ceiling(self):
        # 10 SHAPE-001 templates + 1 short_news_url (NOMOTOKE-RSS-CARD-001A) = 11
        self.assertEqual(len(QUALITY_CEILING_BY_TEMPLATE), 11)

    def test_required_facts_for_4_allowed(self):
        for tk in RSS_ONLY_ALLOWED_TEMPLATES:
            self.assertIn(tk, REQUIRED_FACTS_BY_TEMPLATE)
            self.assertGreater(len(REQUIRED_FACTS_BY_TEMPLATE[tk]), 0)


# ---------------------------------------------------------------------------
# Manager allowlist boundary
# ---------------------------------------------------------------------------
class ManagerAllowlistTests(unittest.TestCase):
    def test_allowlist_contains_abe(self):
        self.assertIn("阿部", MANAGER_NAME_ALLOWLIST)


# ---------------------------------------------------------------------------
# Extractor unit tests
# ---------------------------------------------------------------------------
class ExtractorTests(unittest.TestCase):
    def test_extract_manager_quote_basic(self):
        m = extract_manager_quote("巨人・阿部監督「反省」", "")
        self.assertEqual(m.get("manager_name"), "阿部")
        self.assertEqual(m.get("quote_short"), "反省")

    def test_extract_manager_topic_only(self):
        m = extract_manager_quote("巨人 阿部監督が打線について言及", "")
        self.assertEqual(m.get("manager_name"), "阿部")
        self.assertEqual(m.get("quote_short"), "")

    def test_extract_player_quote_basic(self):
        p = extract_player_quote("巨人・岡本「思い切り振った」", "")
        self.assertEqual(p.get("player_name"), "岡本")
        self.assertEqual(p.get("quote_short"), "思い切り振った")

    def test_extract_player_quote_skips_when_manager_pattern(self):
        # If 監督「 appears, player extractor returns {}.
        p = extract_player_quote("巨人・阿部監督「采配について」", "")
        self.assertEqual(p, {})

    def test_detect_pregame_pitcher_keyword_only(self):
        d = detect_pregame_pitcher("本日の予告先発", "")
        self.assertEqual(d.get("keyword_present"), True)
        self.assertIsNone(d.get("pitcher_pair"))

    def test_detect_pregame_pitcher_pair(self):
        d = detect_pregame_pitcher("予告先発 戸郷 対 小川", "")
        self.assertEqual(d.get("keyword_present"), True)
        self.assertEqual(d.get("pitcher_pair"), ("戸郷", "小川"))

    def test_detect_pregame_pitcher_absent_keyword(self):
        d = detect_pregame_pitcher("巨人ニュース", "")
        self.assertEqual(d, {})


# ---------------------------------------------------------------------------
# Same-source dedupe key stability
# ---------------------------------------------------------------------------
class DedupeKeyTests(unittest.TestCase):
    def test_same_url_same_dedupe_key(self):
        url = "https://twitter.com/TokyoGiants/status/100"
        r1 = route_rss_entry_to_nomotoke_card(
            _entry(title="巨人・岡本「やる」", link=url),
            source_name="TokyoGiants",
            source_url=url,
        )
        r2 = route_rss_entry_to_nomotoke_card(
            _entry(title="巨人・岡本「やる」", link=url),
            source_name="TokyoGiants",
            source_url=url,
        )
        self.assertEqual(r1.dedupe_key, r2.dedupe_key)
        self.assertNotEqual(r1.dedupe_key, "")

    def test_url_with_utm_same_dedupe_key_as_clean(self):
        u_clean = "https://twitter.com/TokyoGiants/status/200"
        u_utm = u_clean + "?utm_source=tw&ref=abc"
        r_clean = route_rss_entry_to_nomotoke_card(
            _entry(title="巨人・岡本「やる」", link=u_clean),
            source_name="TokyoGiants",
            source_url=u_clean,
        )
        r_utm = route_rss_entry_to_nomotoke_card(
            _entry(title="巨人・岡本「やる」", link=u_utm),
            source_name="TokyoGiants",
            source_url=u_utm,
        )
        self.assertEqual(r_clean.dedupe_key, r_utm.dedupe_key)


# ---------------------------------------------------------------------------
# short_news_url title sanitizer (NOMOTOKE-RSS-CARD-001B-TITLE-FIX)
# ---------------------------------------------------------------------------
class ShortNewsTitleSanitizerTests(unittest.TestCase):
    """Locked behavior for sanitize_short_news_title — applies ONLY to
    short_news_url card titles via the router."""

    def test_strips_url_fragment(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        out = sanitize_short_news_title(
            "巨人ニュース http://example.com/foo"
        )
        self.assertNotIn("http", out)
        self.assertNotIn("example.com", out)
        self.assertIn("巨人ニュース", out)

    def test_strips_https_url_fragment(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        out = sanitize_short_news_title(
            "巨人ニュース https://t.co/abc"
        )
        self.assertNotIn("https", out)
        self.assertNotIn("t.co", out)

    def test_strips_trailing_phrases(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        for phrase in (
            "試合詳細はこちら",
            "詳細はこちら",
            "続きはこちら",
            "全文はこちら",
        ):
            out = sanitize_short_news_title(f"巨人ニュース {phrase}")
            self.assertNotIn(phrase, out, f"phrase not stripped: {phrase}")

    def test_converts_hashtag_to_plain_word(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        out = sanitize_short_news_title("巨人 #三塚琉生 選手")
        self.assertIn("三塚琉生", out)
        self.assertNotIn("#三塚琉生", out)

    def test_strips_html_tags(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        out = sanitize_short_news_title("巨人速報<br>続報")
        self.assertNotIn("<br>", out)
        self.assertIn("巨人速報", out)
        self.assertIn("続報", out)

    def test_caps_at_50_chars(self):
        from src.nomotoke_rss_router import (
            TITLE_MAX_CHARS_SHORT_NEWS,
            sanitize_short_news_title,
        )

        long_input = "巨人" * 40  # 80 chars, no period
        out = sanitize_short_news_title(long_input)
        self.assertLessEqual(len(out), TITLE_MAX_CHARS_SHORT_NEWS + 1)
        self.assertTrue(out.endswith("…"))

    def test_truncate_at_period_boundary_when_within_cap(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        # First sentence ends at <= 50 chars; truncation should land there.
        s = "巨人 0-5 ヤクルト 先発の竹丸が5失点。得点を奪うことができず惜敗"
        out = sanitize_short_news_title(s)
        self.assertTrue(out.endswith("。") or len(out) == len(s))

    def test_score_line_preserved(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        out = sanitize_short_news_title(
            "【二軍】巨人 1-6 ハヤテ ちゅ～るスタジアム清水🏟️ #三塚琉生 選手が本塁打を放つも大量失点で敗戦。 試合詳細はこちら http://x.co/a"
        )
        self.assertIn("巨人 1-6 ハヤテ", out)
        self.assertIn("三塚琉生", out)
        self.assertNotIn("試合詳細はこちら", out)
        self.assertNotIn("http", out)

    def test_empty_input_returns_empty(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        self.assertEqual(sanitize_short_news_title(""), "")
        self.assertEqual(sanitize_short_news_title(None), "")  # type: ignore[arg-type]

    def test_short_input_unchanged(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        s = "巨人 試合速報 0-5"
        self.assertEqual(sanitize_short_news_title(s), s)

    def test_full_width_space_collapsed(self):
        from src.nomotoke_rss_router import sanitize_short_news_title

        out = sanitize_short_news_title("巨人　1-6　ハヤテ")  # full-width spaces
        self.assertEqual(out, "巨人 1-6 ハヤテ")

    def test_router_emits_sanitized_title_in_data_preview(self):
        """The router must pass the sanitized title to the renderer's
        data_preview, NOT the raw RSS title."""
        from src.nomotoke_rss_router import (
            TEMPLATE_KEY_SHORT_NEWS_URL,
            route_rss_entry_to_nomotoke_card,
        )

        raw = (
            "【二軍】巨人 1-6 ハヤテ #三塚琉生 選手が本塁打を放つも大量失点で敗戦。 "
            "試合詳細はこちら http://example.com/x"
        )
        r = route_rss_entry_to_nomotoke_card(
            {"title": raw, "summary": "", "link": "https://twitter.com/TokyoGiants/status/9700"},
            source_name="TokyoGiants",
        )
        self.assertTrue(r.matched)
        self.assertEqual(r.template_key, TEMPLATE_KEY_SHORT_NEWS_URL)
        sanitized = (r.would_render_call or {}).get("data_preview", {}).get("title", "")
        self.assertNotIn("http", sanitized)
        self.assertNotIn("試合詳細はこちら", sanitized)
        self.assertNotIn("#三塚琉生", sanitized)
        self.assertIn("三塚琉生", sanitized)
        # extracted_facts captures the raw + sanitized mapping for audit
        self.assertEqual(r.extracted_facts.get("title_sanitized"), sanitized)
        self.assertIn("title_raw", r.extracted_facts)

    def test_router_does_not_apply_sanitizer_to_other_templates(self):
        """manager_comment / player_comment / pregame_pitcher data_previews
        must NOT have title_sanitized fields. Sanitizer is short_news_url-only."""
        from src.nomotoke_rss_router import (
            TEMPLATE_KEY_MANAGER_COMMENT,
            route_rss_entry_to_nomotoke_card,
        )

        r = route_rss_entry_to_nomotoke_card(
            {
                "title": "巨人・阿部監督「反省」",
                "summary": "",
                "link": "https://twitter.com/Sanspo_Giants/status/9701",
            },
            source_name="サンスポ巨人X",
        )
        self.assertEqual(r.template_key, TEMPLATE_KEY_MANAGER_COMMENT)
        self.assertNotIn("title_sanitized", r.extracted_facts)


# ---------------------------------------------------------------------------
# Phase 2C cleanup: player_quote noise rejection + RT skip
# ---------------------------------------------------------------------------
class Phase2CPlayerQuoteCleanupTests(unittest.TestCase):
    """Live X RSS feeds emit titles where the regex naively captures
    garbage as ``player_name`` / ``quote`` (event names, hashtags,
    bracketed prefixes). Phase 2C filters these so the player_comment
    template never produces nonsensical 「{garbage}選手がコメントです。」
    cards.
    """

    def test_player_name_starting_with_japanese_particle_rejected(self):
        # 「が運営するお菓子屋「#COCCOPURIO（#コッコプリオ）」」 — the regex
        # captures 「が運営するお菓子屋」 as name. Particle prefix → reject.
        f = extract_player_quote(
            "5/12にぎふしん長良川球場で開催する広島戦と共に、#吉川養鶏 が運営するお菓子屋「#COCCOPURIO（#コッコプリオ）」をちゃっかり宣伝する #吉川尚輝",
            "",
        )
        self.assertEqual(f, {})

    def test_player_quote_with_event_marker_rejected(self):
        # 「NAOKI IS BACK」 is a merchandise name, not a real quote.
        f = extract_player_quote(
            "吉川選手「NAOKI IS BACK」記念グッズ発売",
            "",
        )
        self.assertEqual(f, {})

    def test_player_quote_with_hashtag_only_quote_rejected(self):
        f = extract_player_quote(
            "選手「#ハッシュタグ」",
            "",
        )
        self.assertEqual(f, {})

    def test_bracket_prefix_stripped_from_player_name(self):
        # 「【巨人】吉川尚輝「コメント」」 → name should be 「吉川尚輝」
        f = extract_player_quote(
            "【巨人】吉川尚輝「気持ちよく振り抜けた」",
            "",
        )
        self.assertEqual(f.get("player_name"), "吉川尚輝")
        self.assertEqual(f.get("quote_short"), "気持ちよく振り抜けた")

    def test_clean_player_quote_still_passes(self):
        # The non-garbage case from the existing test corpus must still match.
        f = extract_player_quote(
            "巨人・大勢「真っ直ぐで押し切れた」",
            "",
        )
        self.assertEqual(f.get("player_name"), "大勢")
        self.assertEqual(f.get("quote_short"), "真っ直ぐで押し切れた")

    def test_player_name_with_hiragana_rejected(self):
        # Phase 2C+ stricter rule: pro baseball player names are kanji
        # surnames or katakana foreign names, never with hiragana
        # particles. 「中日戦先発ウィットリーは」 is a phrase, not a name.
        f = extract_player_quote(
            "【巨人】中日戦先発ウィットリーは「料理人」　竜打線を調理して行きたい街は合羽橋",
            "",
        )
        self.assertEqual(f, {})

    def test_player_name_phrase_with_no_in_middle_rejected(self):
        # 「脱中の山崎伊織の現状説明」 is a phrase containing 「の」 (hiragana)
        f = extract_player_quote(
            "巨人・脱中の山崎伊織の現状説明「全く投げられない状態じゃない」",
            "",
        )
        self.assertEqual(f, {})

    def test_player_name_event_phrase_rejected(self):
        # 「ファーム戦の試合後に」 — 「の」/「に」 hiragana particles in phrase
        f = extract_player_quote(
            "ファーム戦の試合後に「選手と一緒に野球体験会」⚾",
            "",
        )
        self.assertEqual(f, {})

    def test_pure_katakana_player_name_still_passes(self):
        # Foreign player names (e.g. ウィットリー alone, in a clean
        # 「巨人・ウィットリー「料理人」」 pattern) must still match.
        f = extract_player_quote(
            "巨人・ウィットリー「料理人」",
            "",
        )
        self.assertEqual(f.get("player_name"), "ウィットリー")
        self.assertEqual(f.get("quote_short"), "料理人")

    def test_rt_prefix_title_is_skipped_at_router_level(self):
        # Twitter retweet entries (title starts with ``RT @``) are not
        # original source content. Router skips with not_giants_related.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="RT 有吉ぃぃeeeee！: 【🎮エアライダー回 ・配信中！🌟】 巨人ニュース",
                summary="",
                link="https://twitter.com/yomiuri_giants/status/9001",
            ),
            source_name="読売ジャイアンツX",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "not_giants_related")

    def test_rt_space_prefix_also_skipped(self):
        # Some sources prefix with ``RT `` (space) instead of ``RT @``.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="RT 巨人公式: 試合結果 巨人 0-5 ヤクルト",
                summary="",
                link="https://twitter.com/yomiuri_giants/status/9002",
            ),
            source_name="読売ジャイアンツX",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "not_giants_related")

    def test_promo_merchandise_content_skipped(self):
        # The 64837 fixture: NAOKI IS BACK 記念グッズ受注販売.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title=(
                    "吉川選手「NAOKI IS BACK」記念グッズ発売✨ "
                    "4/29の広島戦で、今季初スタメンで初安打・初盗塁をマークした"
                    " #吉川尚輝 選手の「NAOKI IS BACK」記念グッズを、本日5/7から受注販売します👍"
                ),
                summary="",
                link="https://twitter.com/TokyoGiants/status/9501",
            ),
            source_name="巨人公式X",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "promo_or_merchandise_content")

    def test_promo_sponsorship_content_skipped(self):
        # The 64836 fixture: ちゃっかり宣伝するお菓子屋.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title=(
                    "5/12にぎふしん長良川球場で開催する広島戦と共に、"
                    "#吉川養鶏 が運営するお菓子屋「#COCCOPURIO（#コッコプリオ）」"
                    "をちゃっかり宣伝する #吉川尚輝"
                ),
                summary="",
                link="https://twitter.com/TokyoGiants/status/9502",
            ),
            source_name="巨人公式X",
        )
        self.assertFalse(r.matched)
        self.assertEqual(r.skip_reason, "promo_or_merchandise_content")

    def test_legitimate_roster_news_with_抹消_not_promo_skipped(self):
        # 公示 (roster registration removal) uses 抹消, not in the promo list.
        # It must NOT trigger promo skip.
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="【セパ公示】（７日）巨人はドラ１竹丸和幸を抹消",
                summary="",
                link="https://hochi.news/articles/example.html",
            ),
            source_name="スポーツ報知 巨人",
        )
        # Either matches short_news_url or skips with body_too_thin —
        # NEVER skips with promo_or_merchandise_content.
        self.assertNotEqual(
            r.skip_reason, "promo_or_merchandise_content"
        )

    def test_promo_taxonomy_listed(self):
        from src.nomotoke_rss_router import SKIP_REASON_TAXONOMY

        self.assertIn("promo_or_merchandise_content", SKIP_REASON_TAXONOMY)


class TemplateRoutingAuditPhase1Tests(unittest.TestCase):
    """NOMOTOKE-TEMPLATE-ROUTING-AUDIT-001: live in-game blurb skip,
    expanded promo/event keywords, and pitcher-pair regex with em-dash."""

    def test_live_inning_table_blurb_skipped(self):
        for title in (
            "【八回表】巨人 0-2 ヤクルト #竹丸和幸 投手は三者凡退に抑える！",
            "【九回裏】巨人 0-5 ヤクルト #キャベッジ 選手がライトへヒットを放つ！",
            "【一回表】巨人 0-0 ヤクルト #若林楽人 選手の内野安打",
            "【6回表】巨人 0-3 ヤクルト",
            "【十回表】延長戦",
        ):
            with self.subTest(title=title):
                r = route_rss_entry_to_nomotoke_card(
                    _entry(
                        title=title,
                        summary="",
                        link="https://x.com/TokyoGiants/status/1",
                    ),
                    source_name="巨人公式X",
                    source_url="https://x.com/TokyoGiants/status/1",
                )
                self.assertFalse(r.matched, f"{title!r} should not match")
                self.assertEqual(r.skip_reason, "live_inning_blurb_not_article")

    def test_game_boundary_blurb_skipped(self):
        for title in (
            "【試合終了】巨人 0-5 ヤクルト 9回は走者を出すことが出来ず試合終了",
            "【プレーボール】巨人 vs ヤクルト",
            "【試合開始】対ヤクルト戦",
            "【試合中止】雨天により",
        ):
            with self.subTest(title=title):
                r = route_rss_entry_to_nomotoke_card(
                    _entry(
                        title=title,
                        summary="",
                        link="https://x.com/TokyoGiants/status/2",
                    ),
                    source_name="巨人公式X",
                    source_url="https://x.com/TokyoGiants/status/2",
                )
                self.assertEqual(r.skip_reason, "live_inning_blurb_not_article")

    def test_inning_marker_inside_body_does_not_trigger_live_skip(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="【巨人】開幕後も続く競争 捕手は大城卓三が好調",
                summary="九回裏に逆転、八回裏で…",
                link="https://hochi.news/articles/12345.html",
            ),
            source_name="スポーツ報知 巨人",
        )
        self.assertNotEqual(r.skip_reason, "live_inning_blurb_not_article")

    def test_kids_event_promo_skipped(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="「春のKIDS FES」～子供たちがイベントを満喫",
                summary="5月5日のこどもの日に行われたヤクルト戦は「春のKIDS FES」として開催されました。",
                link="https://x.com/TokyoGiants/status/3",
            ),
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/3",
        )
        self.assertEqual(r.skip_reason, "promo_or_merchandise_content")

    def test_baseball_experience_event_promo_skipped(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="ファーム戦の試合後に「選手と一緒に野球体験会」",
                summary="観戦した小学生のうち希望者を対象に...",
                link="https://x.com/TokyoGiants/status/4",
            ),
            source_name="巨人公式X",
            source_url="https://x.com/TokyoGiants/status/4",
        )
        self.assertEqual(r.skip_reason, "promo_or_merchandise_content")

    def test_pitcher_pair_em_dash_extracted(self):
        from src.nomotoke_rss_router import detect_pregame_pitcher

        result = detect_pregame_pitcher(
            "【８日の予告先発】中日・柳裕也―巨人・ウィットリー、阪神・村上頌樹―ＤｅＮＡ・平良拳太郎ほか",
            "",
        )
        self.assertTrue(result.get("keyword_present"))
        pair = result.get("pitcher_pair")
        self.assertIsNotNone(pair, "pitcher_pair must extract for em-dash format")

    def test_pitcher_pair_en_dash_also_extracted(self):
        from src.nomotoke_rss_router import detect_pregame_pitcher

        result = detect_pregame_pitcher(
            "予告先発 中日・柳裕也–巨人・ウィットリー", ""
        )
        self.assertTrue(result.get("keyword_present"))
        self.assertIsNotNone(result.get("pitcher_pair"))

    def test_existing_pitcher_pair_dash_variants_still_work(self):
        from src.nomotoke_rss_router import detect_pregame_pitcher

        for sep in ("対", "vs", "VS", "×", "－"):
            with self.subTest(sep=sep):
                title = f"予告先発 中日・柳裕也{sep}巨人・ウィットリー"
                r = detect_pregame_pitcher(title, "")
                self.assertTrue(r.get("keyword_present"))
                self.assertIsNotNone(r.get("pitcher_pair"))

    def test_live_inning_taxonomy_listed(self):
        from src.nomotoke_rss_router import SKIP_REASON_TAXONOMY

        self.assertIn("live_inning_blurb_not_article", SKIP_REASON_TAXONOMY)


if __name__ == "__main__":
    unittest.main()
