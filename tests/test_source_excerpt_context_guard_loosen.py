"""Regression tests for the 2026-05-12 narrow loosening of
``_source_excerpt_matches_context``.

Scope reduction note: the original plan was to add a summary-anchored
fallback after the title-only check fails, but
``test_rss_pipeline_source_body_excerpt_ignores_polluted_summary_for_66369``
(introduced by ef5fe7b) proved that a polluted summary regularly aligns
with a polluted excerpt, so an unconditional summary fallback re-opens
the exact bug ef5fe7b closed. The detected ``giants player anchor``
hint via ``_scan_giants_player_names_in_text`` is not reliable enough
to gate the fallback either (aliases like "原監督" / "由伸監督" are
not recognised). Until we have a smarter polluted-summary detector,
the only narrow loosen we ship is the cross-publisher URL guard. The
existing title-only behaviour from ef5fe7b is preserved.

These tests guard the new ``_excerpt_signals_cross_publisher`` helper
and confirm the title-only contract is unchanged.
"""
from __future__ import annotations

import unittest

from src.tools import manual_intake


class GuardBehaviorAfterNarrowLoosenTests(unittest.TestCase):
    """``_source_excerpt_matches_context`` behaviour after the loosen."""

    # --- positive: title-only match still works (ef5fe7b unchanged) ---
    def test_title_term_match_still_accepts(self):
        title = "【巨人】丸佳浩、若林楽人らがアメリカンノックで右へ左へ"
        excerpt = (
            "巨人の丸佳浩、若林楽人、長野久義、中山礼都ら9選手は"
            "アメリカンノックで打球の方向に応じて右へ左へ走った。"
        )
        self.assertTrue(
            manual_intake._source_excerpt_matches_context(
                excerpt,
                title=title,
                summary="",
            )
        )

    # --- existing context-drift case still rejected (no title overlap) ---
    def test_unrelated_article_still_rejected(self):
        title = "【巨人】丸佳浩がアメリカンノックで右へ左へ"
        excerpt = "中日の高橋宏斗が完投勝利を挙げた。中日ファンが盛り上がっている。"
        self.assertFalse(
            manual_intake._source_excerpt_matches_context(
                excerpt,
                title=title,
                summary="",
            )
        )

    # --- pollution guard: cross-publisher URL in excerpt → reject ---
    def test_cross_publisher_url_in_excerpt_is_rejected(self):
        """Even when title terms match, an excerpt that links to a
        different news publisher is treated as polluted and rejected."""
        title = "【巨人】丸佳浩がアメリカンノックで右へ左へ"
        excerpt = (
            "丸佳浩がアメリカンノックで動いた。"
            "詳しくは関連記事 https://www.nikkansports.com/baseball/news/123.html を参照。"
        )
        self.assertFalse(
            manual_intake._source_excerpt_matches_context(
                excerpt,
                title=title,
                summary="",
                source_url="https://hochi.news/articles/abc.html",
            )
        )

    # --- same-publisher URL is NOT pollution ---
    def test_same_publisher_url_in_excerpt_is_allowed(self):
        title = "【巨人】丸佳浩がアメリカンノックで右へ左へ"
        excerpt = (
            "丸佳浩はアメリカンノックで動いた。"
            "関連記事 https://hochi.news/articles/related-123.html"
        )
        self.assertTrue(
            manual_intake._source_excerpt_matches_context(
                excerpt,
                title=title,
                summary="",
                source_url="https://hochi.news/articles/abc.html",
            )
        )

    # --- pollution guard fires even when title only would otherwise reject ---
    def test_pollution_guard_runs_before_title_check(self):
        title = "巨人の今日のスタメン"
        excerpt = "全然関係ない本文 https://www.sponichi.co.jp/baseball/news/456.html"
        self.assertFalse(
            manual_intake._source_excerpt_matches_context(
                excerpt,
                title=title,
                summary="",
                source_url="https://hochi.news/articles/abc.html",
            )
        )

    # --- both title and summary empty → accept (cannot prove drift) ---
    def test_both_title_and_summary_empty_still_accept(self):
        excerpt = "なんらかの本文。"
        self.assertTrue(
            manual_intake._source_excerpt_matches_context(
                excerpt,
                title="",
                summary="",
            )
        )

    # --- legacy callers without source_url still work ---
    def test_legacy_call_without_source_url_still_works(self):
        title = "【巨人】丸佳浩がアメリカンノックで右へ左へ"
        excerpt = "丸佳浩がアメリカンノックで右へ左へ動いた。"
        self.assertTrue(
            manual_intake._source_excerpt_matches_context(
                excerpt,
                title=title,
                summary="",
            )
        )

    # --- title empty: summary fallback path unchanged from ef5fe7b ---
    def test_title_empty_summary_match_accepts(self):
        excerpt = "岡本和真がフリー打撃で快音"
        self.assertTrue(
            manual_intake._source_excerpt_matches_context(
                excerpt,
                title="",
                summary="岡本和真がフリー打撃で快音を響かせた",
            )
        )


class CrossPublisherPollutionHelperTests(unittest.TestCase):
    """``_excerpt_signals_cross_publisher`` helper coverage."""

    def test_detects_different_publisher_url_in_excerpt(self):
        self.assertTrue(
            manual_intake._excerpt_signals_cross_publisher(
                "本文。https://www.nikkansports.com/baseball/news/1.html もどうぞ",
                "https://hochi.news/articles/x.html",
            )
        )

    def test_same_publisher_url_is_not_signal(self):
        self.assertFalse(
            manual_intake._excerpt_signals_cross_publisher(
                "本文。https://hochi.news/articles/related.html もどうぞ",
                "https://hochi.news/articles/x.html",
            )
        )

    def test_www_prefix_is_normalized(self):
        self.assertFalse(
            manual_intake._excerpt_signals_cross_publisher(
                "本文。https://www.hochi.news/articles/related.html",
                "https://hochi.news/articles/x.html",
            )
        )

    def test_news_hochi_subdomain_normalized_to_hochi(self):
        self.assertFalse(
            manual_intake._excerpt_signals_cross_publisher(
                "本文。https://news.hochi.news/articles/related.html",
                "https://hochi.news/articles/x.html",
            )
        )

    def test_non_publisher_url_is_not_signal(self):
        # twitter / 外部 blog 等は news publisher list に該当しない
        self.assertFalse(
            manual_intake._excerpt_signals_cross_publisher(
                "本文。https://twitter.com/user/status/1",
                "https://hochi.news/articles/x.html",
            )
        )

    def test_no_url_in_excerpt(self):
        self.assertFalse(
            manual_intake._excerpt_signals_cross_publisher(
                "URL を含まない本文。",
                "https://hochi.news/articles/x.html",
            )
        )

    def test_empty_source_url(self):
        self.assertFalse(
            manual_intake._excerpt_signals_cross_publisher(
                "本文。https://www.nikkansports.com/baseball/news/1.html",
                "",
            )
        )

    def test_url_with_port(self):
        self.assertTrue(
            manual_intake._excerpt_signals_cross_publisher(
                "本文。https://www.nikkansports.com:443/baseball/news/1.html",
                "https://hochi.news/articles/x.html",
            )
        )


if __name__ == "__main__":
    unittest.main()
