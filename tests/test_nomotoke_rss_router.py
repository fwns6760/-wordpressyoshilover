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

    def test_manager_not_in_allowlist_falls_back_to_short_news(self):
        r = route_rss_entry_to_nomotoke_card(
            _entry(
                title="巨人 関連: 中日・立浪監督「打線再編」",
                summary="",
                link="https://twitter.com/SponichiYakyu/status/9",
            ),
            source_name="SponichiYakyu",
            source_url="https://twitter.com/SponichiYakyu/status/9",
        )
        self.assertTrue(r.matched)
        # Not in allowlist -> not manager_comment. Falls back to short_news_url.
        self.assertEqual(r.template_key, TEMPLATE_KEY_SHORT_NEWS_URL)
        self.assertIn("manager_not_in_allowlist", r.extracted_facts.get("fallback_from", ""))

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


if __name__ == "__main__":
    unittest.main()
