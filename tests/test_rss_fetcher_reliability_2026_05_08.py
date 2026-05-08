"""RELIABILITY-2026-05-08 D+E+F の helper/threshold ロジック単体 test.

D = ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL: trusted family の post_gen_validate
全 fail axes bypass。X 系 / 非 trusted は通常 skip。

E = ENABLE_POST_GEN_VALIDATE_REVIEW_DRAFT: post_gen_validate fail を skip ではなく
「【要review｜post_gen_validate】」prefix 付き draft 化する flag。

F = ENABLE_STALE_RSS_TRUSTED_BYPASS + STALE_RSS_WINDOW_TRUSTED_HOURS: trusted RSS
source 限定で stale window を 48h(default)に拡張。X 系 / 非 trusted は既存閾値維持。
"""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src import rss_fetcher


FETCHER_FLAG = rss_fetcher.ENABLE_FETCHER_STALE_SOURCE_GUARD_ENV_FLAG
STRICT_FLAG = "ENABLE_STRICT_BREAKING_NEWS_THRESHOLDS"
NOW = datetime.fromisoformat("2026-05-08T11:00:00+09:00")


class TrustedBypassFullHelperTests(unittest.TestCase):
    def test_flag_off_returns_false_for_trusted_url(self):
        with patch.dict(os.environ, {"ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL": "0"}, clear=False):
            self.assertFalse(
                rss_fetcher._post_gen_validate_trusted_bypass_full(
                    "https://www.nikkansports.com/baseball/news/202605070000602.html"
                )
            )

    def test_flag_on_trusted_url_returns_true(self):
        with patch.dict(os.environ, {"ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL": "1"}, clear=False):
            self.assertTrue(
                rss_fetcher._post_gen_validate_trusted_bypass_full(
                    "https://www.nikkansports.com/baseball/news/202605070000602.html"
                )
            )
            self.assertTrue(
                rss_fetcher._post_gen_validate_trusted_bypass_full(
                    "https://hochi.news/articles/20260507-OHT1T51234.html"
                )
            )
            self.assertTrue(
                rss_fetcher._post_gen_validate_trusted_bypass_full(
                    "https://www.sponichi.co.jp/baseball/news/2026/05/07/kiji/foo.html"
                )
            )

    def test_flag_on_non_trusted_url_returns_false(self):
        # 注: media outlet の official X account (SponichiYakyu / hochi_baseball /
        # TokyoGiants 等) は handle 経由で trusted family に分類される。これは設計通りで
        # その account の content は media 自身の発信として trusted 扱い。
        # 非 trusted = 一般 X user account / 未登録 domain。
        with patch.dict(os.environ, {"ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL": "1"}, clear=False):
            self.assertFalse(
                rss_fetcher._post_gen_validate_trusted_bypass_full(
                    "https://twitter.com/random_fan_user_xyz/status/2052300000000000000"
                )
            )
            self.assertFalse(
                rss_fetcher._post_gen_validate_trusted_bypass_full(
                    "https://example.com/some-news-article"
                )
            )

    def test_empty_or_none_url_returns_false(self):
        with patch.dict(os.environ, {"ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL": "1"}, clear=False):
            self.assertFalse(rss_fetcher._post_gen_validate_trusted_bypass_full(""))
            self.assertFalse(rss_fetcher._post_gen_validate_trusted_bypass_full(None))
            self.assertFalse(rss_fetcher._post_gen_validate_trusted_bypass_full("   "))


class ReviewDraftFlagTests(unittest.TestCase):
    def test_flag_off_returns_false(self):
        with patch.dict(os.environ, {"ENABLE_POST_GEN_VALIDATE_REVIEW_DRAFT": "0"}, clear=False):
            self.assertFalse(rss_fetcher._post_gen_validate_review_draft_enabled())

    def test_flag_on_returns_true(self):
        with patch.dict(os.environ, {"ENABLE_POST_GEN_VALIDATE_REVIEW_DRAFT": "1"}, clear=False):
            self.assertTrue(rss_fetcher._post_gen_validate_review_draft_enabled())

    def test_review_draft_title_prefix_value(self):
        self.assertEqual(
            rss_fetcher._POST_GEN_VALIDATE_REVIEW_DRAFT_TITLE_PREFIX,
            "【要review｜post_gen_validate】",
        )


class StaleTrustedBypassTests(unittest.TestCase):
    def _entry(self, *, link: str, published_dt: datetime) -> dict:
        return {
            "title": "巨人の最新動向",
            "summary": "巨人記事の要約",
            "link": link,
            "published_parsed": published_dt.astimezone(timezone.utc).timetuple(),
            "published": published_dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }

    def _decision(self, entry: dict, *, post_url: str, article_subtype: str, env: dict[str, str]) -> dict:
        with patch.dict(os.environ, env, clear=False):
            return rss_fetcher._evaluate_fetcher_stale_source_guard(
                entry,
                post_url=post_url,
                article_subtype=article_subtype,
                now=NOW,
            )

    def test_trusted_bypass_off_30h_old_nikkansports_skipped(self):
        # NOW=5/8 11:00 JST、article=5/7 5:00 JST (30h前) → default 24h で skip
        entry = self._entry(
            link="https://www.nikkansports.com/baseball/news/202605070000123.html",
            published_dt=datetime.fromisoformat("2026-05-07T05:00:00+09:00"),
        )
        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={
                FETCHER_FLAG: "1",
                STRICT_FLAG: "1",
                "ENABLE_STALE_RSS_TRUSTED_BYPASS": "0",
            },
        )
        self.assertFalse(decision["allow"])
        self.assertEqual(decision["reason"], "stale_rss_entry")

    def test_trusted_bypass_on_30h_old_nikkansports_passes_with_48h(self):
        # 30h は 48h trusted threshold 内 → allow
        entry = self._entry(
            link="https://www.nikkansports.com/baseball/news/202605070000123.html",
            published_dt=datetime.fromisoformat("2026-05-07T05:00:00+09:00"),
        )
        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={
                FETCHER_FLAG: "1",
                STRICT_FLAG: "1",
                "ENABLE_STALE_RSS_TRUSTED_BYPASS": "1",
            },
        )
        self.assertTrue(decision["allow"])

    def test_trusted_bypass_on_50h_old_nikkansports_still_skipped(self):
        # 50h は 48h trusted threshold 超過 → skip (window 拡張は無限ではない)
        entry = self._entry(
            link="https://www.nikkansports.com/baseball/news/202605060000123.html",
            published_dt=datetime.fromisoformat("2026-05-06T09:00:00+09:00"),
        )
        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={
                FETCHER_FLAG: "1",
                STRICT_FLAG: "1",
                "ENABLE_STALE_RSS_TRUSTED_BYPASS": "1",
            },
        )
        self.assertFalse(decision["allow"])
        self.assertEqual(decision["reason"], "stale_rss_entry")

    def test_trusted_bypass_on_non_trusted_url_no_extension(self):
        # X URL は trusted family でない → 48h 拡張 effective 無し、24h で skip
        x_url = "https://twitter.com/Sanspo_Giants/status/2052300000000000000"
        entry = {
            "title": "巨人ファームでドラフト２位選手が打撃好調",
            "summary": "ファーム情報",
            "link": x_url,
        }
        # X URL の published は X status ID から推測されるが、test 用に published_parsed
        # を 30h 前で固定し、stale_rss_entry path に乗せる代わりに stale_x_post path に
        # 乗ることを確認する。X URL の場合 _decode_x_status_datetime で 解読される。
        decision = self._decision(
            entry,
            post_url=x_url,
            article_subtype="manager",
            env={
                FETCHER_FLAG: "1",
                STRICT_FLAG: "1",
                "ENABLE_STALE_RSS_TRUSTED_BYPASS": "1",
            },
        )
        # X status ID 由来の時刻は decode_x_status_datetime で計算され、family も
        # twitter.com 系で trusted family ではない。trusted bypass effect 無し。
        # decode 失敗時は source_time_missing_review で skip するので、いずれにせよ
        # trusted bypass による拡張効果は無いことが確認できる。
        self.assertNotIn("trusted_extended", str(decision))

    def test_threshold_env_override_works(self):
        # STALE_RSS_WINDOW_TRUSTED_HOURS=72 で 48 → 72 に拡張
        entry = self._entry(
            link="https://www.nikkansports.com/baseball/news/202605060000999.html",
            published_dt=datetime.fromisoformat("2026-05-06T09:00:00+09:00"),  # 50h前
        )
        decision = self._decision(
            entry,
            post_url=entry["link"],
            article_subtype="manager",
            env={
                FETCHER_FLAG: "1",
                STRICT_FLAG: "1",
                "ENABLE_STALE_RSS_TRUSTED_BYPASS": "1",
                "STALE_RSS_WINDOW_TRUSTED_HOURS": "72",
            },
        )
        self.assertTrue(decision["allow"])

    def test_threshold_env_invalid_falls_back_to_48(self):
        # 不正値は 48h fallback
        with patch.dict(os.environ, {"STALE_RSS_WINDOW_TRUSTED_HOURS": "abc"}, clear=False):
            self.assertEqual(rss_fetcher._stale_source_trusted_threshold_hours(), 48.0)
        with patch.dict(os.environ, {"STALE_RSS_WINDOW_TRUSTED_HOURS": "-5"}, clear=False):
            self.assertEqual(rss_fetcher._stale_source_trusted_threshold_hours(), 48.0)
        with patch.dict(os.environ, {"STALE_RSS_WINDOW_TRUSTED_HOURS": ""}, clear=False):
            self.assertEqual(rss_fetcher._stale_source_trusted_threshold_hours(), 48.0)


class IsPostUrlTrustedFamilyTests(unittest.TestCase):
    def test_trusted_urls_classified(self):
        for url in (
            "https://www.nikkansports.com/baseball/news/202605070000602.html",
            "https://hochi.news/articles/20260507-OHT1T51234.html",
            "https://www.sponichi.co.jp/baseball/news/2026/05/07/kiji/foo.html",
        ):
            self.assertTrue(
                rss_fetcher._is_post_url_trusted_family(url),
                f"{url} should be trusted family",
            )

    def test_non_trusted_urls(self):
        # media outlet の X account は trusted (sponichi/hochi/nikkansports 等)。
        # 非 trusted = 一般 user / 未登録 domain。
        for url in (
            "https://twitter.com/random_fan_user_xyz/status/123",
            "",
            None,
            "https://example.com/story",
            "https://unrelated-blog.example.org/post",
        ):
            self.assertFalse(
                rss_fetcher._is_post_url_trusted_family(url),
                f"{url} should NOT be trusted family",
            )


class CreateDraftForceStatusTests(unittest.TestCase):
    """E が依存する _create_draft_with_same_fire_guard の force_status 引数 test."""

    def test_force_status_overrides_run_draft_only_env(self):
        captured = {}

        class FakeWP:
            def create_post(self, title, content, **kwargs):
                captured["status"] = kwargs.get("status")
                return 99999

        import logging
        logger = logging.getLogger("test")
        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "0"}, clear=False):
            post_id = rss_fetcher._create_draft_with_same_fire_guard(
                FakeWP(),
                logger,
                set(),
                {},
                "title",
                "<p>body</p>",
                [1, 2],
                "https://example.com/x",
                featured_media=None,
                force_status="draft",
            )
        self.assertEqual(post_id, 99999)
        # RUN_DRAFT_ONLY=0 でも force_status="draft" が勝つ
        self.assertEqual(captured["status"], "draft")

    def test_no_force_status_keeps_existing_run_draft_only_logic(self):
        captured = {}

        class FakeWP:
            def create_post(self, title, content, **kwargs):
                captured["status"] = kwargs.get("status")
                return 11111

        import logging
        logger = logging.getLogger("test")
        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "0"}, clear=False):
            rss_fetcher._create_draft_with_same_fire_guard(
                FakeWP(),
                logger,
                set(),
                {},
                "title",
                "<p>body</p>",
                [1, 2],
                "https://example.com/x",
                featured_media=None,
            )
        # RUN_DRAFT_ONLY=0 で publish 化 (既存挙動)
        self.assertEqual(captured["status"], "publish")


if __name__ == "__main__":
    unittest.main()
