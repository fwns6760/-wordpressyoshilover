"""Tests for src/tools/manual_intake.py — MANUAL-INTAKE-001 pass-1 + 002.

12 required fixtures from the 001 ticket:
1. invalid URL -> exit 10
2. X URL status_id 抽出
3. X URL でtitle/summaryなし -> exit 12
4. memo が summary / source_fact / Gemini prompt に入らない
5. dry-run で WP書込なし
6. draft mode で WPClient.create_post(status="draft") が呼ばれる
7. duplicate で exit 13
8. validation fail で exit 14
9. rate limit で exit 30
10. source_url meta が残る
11. OG/meta parse success
12. OG/meta parse fail + override title/summary success

MANUAL-INTAKE-002 additions:
- --source-published-at parse / normalize (JST / Z / naive)
- invalid date -> exit 15
- normalized timestamp reaches WP draft body
- normalized_source_published_at present in output dict
- memo never co-mingles with source_published_at into body
- X URL handles --source-published-at as timestamp metadata only
- News URL prefers CLI --source-published-at over absent OG date
- category / X normalization unchanged
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.tools import manual_intake as mi


class URLClassificationTests(unittest.TestCase):
    def test_valid_http(self):
        self.assertTrue(mi._is_valid_url("https://hochi.news/articles/123"))
        self.assertTrue(mi._is_valid_url("http://example.com"))

    def test_invalid(self):
        self.assertFalse(mi._is_valid_url(""))
        self.assertFalse(mi._is_valid_url("not-a-url"))
        self.assertFalse(mi._is_valid_url("ftp://example.com"))
        self.assertFalse(mi._is_valid_url(None))
        self.assertFalse(mi._is_valid_url(12345))

    def test_x_host_recognized(self):
        for url in [
            "https://twitter.com/foo/status/1",
            "https://x.com/foo/status/1",
            "https://mobile.x.com/foo/status/1",
            "https://www.twitter.com/foo/status/1",
        ]:
            with self.subTest(url=url):
                self.assertTrue(mi._is_x_url(url))

    def test_news_host_not_x(self):
        for url in [
            "https://hochi.news/articles/abc",
            "https://www.sanspo.com/article/x",
            "https://www.nikkansports.com/baseball/news/1.html",
        ]:
            with self.subTest(url=url):
                self.assertFalse(mi._is_x_url(url))

    def test_status_id_extract(self):
        self.assertEqual(
            mi._extract_x_status_id(
                "https://x.com/TokyoGiants/status/2051932442643296604"
            ),
            "2051932442643296604",
        )
        self.assertEqual(
            mi._extract_x_status_id(
                "https://twitter.com/foo/status/123?ref=bar"
            ),
            "123",
        )
        self.assertEqual(mi._extract_x_status_id("https://x.com/foo"), "")

    def test_x_url_normalized_to_twitter(self):
        self.assertEqual(
            mi._normalize_x_url_to_twitter(
                "https://x.com/TokyoGiants/status/123"
            ),
            "https://twitter.com/TokyoGiants/status/123",
        )
        self.assertEqual(
            mi._normalize_x_url_to_twitter(
                "https://www.x.com/foo/status/1"
            ),
            "https://twitter.com/foo/status/1",
        )


class RateLimitTests(unittest.TestCase):
    def test_allowed_until_max(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "lock.json"
            for i in range(mi.RATE_LIMIT_MAX):
                allowed, _ = mi._check_rate_limit(lock)
                self.assertTrue(allowed, f"call #{i + 1} should be allowed")
            allowed, retry = mi._check_rate_limit(lock)
            self.assertFalse(allowed)
            self.assertGreater(retry, 0)


class ParseMetaTests(unittest.TestCase):
    def test_og_title_and_description(self):
        html_text = (
            '<html><head>'
            '<meta property="og:title" content="巨人 試合速報">'
            '<meta property="og:description" content="0-5 ヤクルト戦">'
            '</head></html>'
        )
        m = mi._parse_og_meta(html_text)
        self.assertEqual(m["title"], "巨人 試合速報")
        self.assertEqual(m["summary"], "0-5 ヤクルト戦")

    def test_fallback_to_title_tag(self):
        html_text = "<html><head><title>Plain Title</title></head></html>"
        m = mi._parse_og_meta(html_text)
        self.assertEqual(m["title"], "Plain Title")
        self.assertEqual(m["summary"], "")

    def test_html_entities_decoded(self):
        html_text = '<meta property="og:title" content="A &amp; B">'
        m = mi._parse_og_meta(html_text)
        self.assertEqual(m["title"], "A & B")


class _IntakeBaseTest(unittest.TestCase):
    """Common fixtures: per-test isolated lockfile + lightweight routing patch."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.lockfile = Path(self._tmpdir.name) / "lock.json"
        self._routing_patch = patch.object(
            mi,
            "_resolve_routing_lightweight",
            return_value=("選手情報", "manual_intake"),
        )
        self._routing_patch.start()
        self._history_patch = patch.object(
            mi, "_safe_load_history", return_value={}
        )
        self._history_patch.start()

    def tearDown(self):
        self._routing_patch.stop()
        self._history_patch.stop()
        self._tmpdir.cleanup()


class RunManualIntakeTests(_IntakeBaseTest):
    # 1. invalid URL -> exit 10
    def test_1_invalid_url_exit_10(self):
        code, out = mi.run_manual_intake(
            url="not-a-url",
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_INVALID_URL)
        self.assertEqual(out["reason"], "invalid_url")
        self.assertFalse(out["ok"])

    # 2. X URL status_id extracted
    def test_2_x_url_status_id_extracted(self):
        wp = MagicMock()
        wp.create_post = MagicMock(return_value=42)
        code, out = mi.run_manual_intake(
            url="https://x.com/TokyoGiants/status/2051932442643296604",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="draft",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(out["status_id"], "2051932442643296604")
        self.assertEqual(out["source_kind"], "x")
        self.assertEqual(code, mi.EXIT_OK)

    # 3. X URL with no title/summary -> exit 12
    def test_3_x_url_missing_title_or_summary_exit_12(self):
        code, out = mi.run_manual_intake(
            url="https://x.com/foo/status/12345",
            mode="dry-run",
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_MISSING_TITLE_OR_SUMMARY)
        self.assertEqual(out["reason"], "missing_title_or_summary")

    # 4. memo NOT in WP body / title
    def test_4_memo_not_in_summary_or_body(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 100

        wp = MagicMock()
        wp.create_post = fake_create
        secret_memo = "MEMO_SECRET_TOKEN_XYZ123"
        code, out = mi.run_manual_intake(
            url="https://x.com/TokyoGiants/status/9999",
            title_override="巨人 試合終了 0-5 ヤクルト",
            summary_override="ヤクルト戦敗戦",
            memo=secret_memo,
            mode="draft",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertNotIn(secret_memo, captured.get("content", ""))
        self.assertNotIn(secret_memo, captured.get("title", ""))
        # output may carry memo for operator audit; that's allowed
        self.assertEqual(out.get("memo"), secret_memo)

    # 5. dry-run: WP not invoked
    def test_5_dry_run_no_wp_write(self):
        wp_factory = MagicMock()
        code, out = mi.run_manual_intake(
            url="https://x.com/foo/status/1",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="dry-run",
            wp_client_factory=wp_factory,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        wp_factory.assert_not_called()
        self.assertTrue(out["ok"])
        self.assertTrue(out["validation_ok"])
        self.assertIsNone(out["post_id"])

    # 6. draft mode calls create_post(status="draft")
    def test_6_draft_calls_create_post_with_status_draft(self):
        wp = MagicMock()
        wp.create_post = MagicMock(return_value=77)
        code, out = mi.run_manual_intake(
            url="https://x.com/foo/status/1",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="draft",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        wp.create_post.assert_called_once()
        kwargs = wp.create_post.call_args.kwargs
        self.assertEqual(kwargs.get("status"), "draft")
        self.assertEqual(kwargs.get("source_url"), "https://twitter.com/foo/status/1")
        self.assertEqual(kwargs.get("caller"), "manual_intake")
        self.assertEqual(out["post_id"], 77)

    # 7. duplicate (history) -> exit 13
    def test_7_history_duplicate_exit_13(self):
        with patch.object(mi, "_safe_load_history") as h:
            h.return_value = {"https://twitter.com/foo/status/1": {}}
            code, out = mi.run_manual_intake(
                url="https://x.com/foo/status/1",
                title_override="巨人 試合終了 0-5 ヤクルト",
                mode="dry-run",
                rate_limit_lockfile=self.lockfile,
            )
        self.assertEqual(code, mi.EXIT_DUPLICATE)
        self.assertTrue(out["duplicate"])
        self.assertEqual(out["reason"], "history_duplicate")

    # 8. validation fail (title too short) -> exit 14
    def test_8_title_too_short_exit_14(self):
        code, out = mi.run_manual_intake(
            url="https://x.com/foo/status/1",
            title_override="短い",  # 2 chars, below MIN_TITLE_CHARS
            mode="dry-run",
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_VALIDATION_FAILED)
        self.assertEqual(out["reason"], "validation_failed")
        self.assertEqual(out["skip_reason"], "title_too_short")

    # 9. rate limit -> exit 30
    def test_9_rate_limit_exit_30(self):
        now = time.time()
        self.lockfile.parent.mkdir(parents=True, exist_ok=True)
        self.lockfile.write_text(json.dumps([now] * mi.RATE_LIMIT_MAX))
        code, out = mi.run_manual_intake(
            url="https://hochi.news/x/y",
            title_override="巨人 試合終了 0-5 ヤクルト",
            summary_override="サマリー",
            mode="dry-run",
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_RATE_LIMITED)
        self.assertEqual(out["reason"], "rate_limited")
        self.assertGreater(out.get("retry_after_sec", 0), 0)

    # 10. source_url meta passed to WP
    def test_10_source_url_meta_passed(self):
        wp = MagicMock()
        wp.create_post = MagicMock(return_value=88)
        code, out = mi.run_manual_intake(
            url="https://hochi.news/articles/abc-123.html",
            title_override="巨人 試合速報 0-5 ヤクルト",
            summary_override="ヤクルト戦敗戦",
            mode="draft",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        kwargs = wp.create_post.call_args.kwargs
        self.assertEqual(
            kwargs.get("source_url"), "https://hochi.news/articles/abc-123.html"
        )
        self.assertEqual(kwargs.get("categories"), [664])
        self.assertEqual(out["source_url"], "https://hochi.news/articles/abc-123.html")

    # 11. OG/meta parse success path
    def test_11_og_parse_success_uses_fetched_meta(self):
        wp = MagicMock()
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 99

        wp.create_post = fake_create

        def fake_fetch(url, **kw):
            return {
                "title": "巨人 試合速報 6-3 ヤクルト",
                "summary": "勝利でM3 阿部監督が采配を振るった",
            }

        code, out = mi.run_manual_intake(
            url="https://hochi.news/articles/og-fetch.html",
            mode="draft",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
            fetch_meta=fake_fetch,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(out["title"], "巨人 試合速報 6-3 ヤクルト")
        self.assertIn("勝利でM3", captured.get("content", ""))
        self.assertEqual(captured.get("status"), "draft")

    # 12. OG/meta parse fail + override title/summary success
    def test_12_og_fail_with_overrides_succeeds(self):
        wp = MagicMock()
        wp.create_post = MagicMock(return_value=200)

        def fake_fetch_fail(url, **kw):
            return {"_error": "fetch_failed:HTTPError"}

        code, out = mi.run_manual_intake(
            url="https://www.sanspo.com/article/paywalled.html",
            title_override="巨人 試合速報 サンスポ独自 阿部監督コメント",
            summary_override="paywall越しの内容のはずだったが手打ちで補完",
            mode="draft",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
            fetch_meta=fake_fetch_fail,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(out["title"], "巨人 試合速報 サンスポ独自 阿部監督コメント")
        wp.create_post.assert_called_once()


class RoutingIntegrationTests(unittest.TestCase):
    def test_resolve_routing_calls_classify_category_with_keyword_only_context(self):
        fake = types.ModuleType("rss_fetcher")
        observed = {}

        def fake_classify(text, keywords, *, source_url="", logger=None):
            observed["source_url"] = source_url
            observed["logger"] = logger
            return "試合速報"

        def fake_detect(title, summary, category, has_game):
            observed["category"] = category
            return "postgame"

        fake.classify_category = fake_classify
        fake._detect_article_subtype = fake_detect

        original = sys.modules.get("rss_fetcher")
        sys.modules["rss_fetcher"] = fake
        try:
            category, subtype = mi._resolve_routing_lightweight(
                title="巨人 試合終了 0-5 ヤクルト",
                summary="ヤクルト戦敗戦",
                source_url="https://x.com/hochi_giants/status/1",
                source_kind="x",
                logger=MagicMock(),
            )
        finally:
            if original is None:
                sys.modules.pop("rss_fetcher", None)
            else:
                sys.modules["rss_fetcher"] = original

        self.assertEqual(category, "試合速報")
        self.assertEqual(subtype, "postgame")
        self.assertEqual(observed["source_url"], "https://x.com/hochi_giants/status/1")
        self.assertEqual(observed["category"], "試合速報")


class CategoryResolutionTests(unittest.TestCase):
    def test_resolve_wp_category_ids_uses_config_mapping(self):
        self.assertEqual(mi._resolve_wp_category_ids("試合速報"), [663])
        self.assertEqual(mi._resolve_wp_category_ids("選手情報"), [664])

    def test_resolve_wp_category_ids_falls_back_to_column(self):
        self.assertEqual(mi._resolve_wp_category_ids("存在しないカテゴリ"), [670])


class FetchFailureTests(_IntakeBaseTest):
    def test_news_url_fetch_fail_no_overrides_exit_11(self):
        def fake_fetch_fail(url, **kw):
            return {"_error": "fetch_failed:HTTPError"}

        code, out = mi.run_manual_intake(
            url="https://www.sanspo.com/article/paywalled.html",
            mode="dry-run",
            rate_limit_lockfile=self.lockfile,
            fetch_meta=fake_fetch_fail,
        )
        self.assertEqual(code, mi.EXIT_FETCH_FAILED)
        self.assertTrue(out["reason"].startswith("fetch_failed:"))


class CLIArgParserTests(unittest.TestCase):
    def test_parser_accepts_required_url_only(self):
        p = mi._build_arg_parser()
        ns = p.parse_args(["https://x.com/foo/status/1"])
        self.assertEqual(ns.url, "https://x.com/foo/status/1")
        self.assertEqual(ns.mode, "draft")
        self.assertEqual(ns.memo, "")
        self.assertEqual(ns.source_published_at, "")

    def test_parser_full_flags(self):
        p = mi._build_arg_parser()
        ns = p.parse_args(
            [
                "https://hochi.news/articles/x.html",
                "--memo",
                "宮原昇格",
                "--mode",
                "dry-run",
                "--title",
                "T",
                "--summary",
                "S",
                "--source-published-at",
                "2026-05-07T18:30:00+09:00",
            ]
        )
        self.assertEqual(ns.memo, "宮原昇格")
        self.assertEqual(ns.mode, "dry-run")
        self.assertEqual(ns.title, "T")
        self.assertEqual(ns.summary, "S")
        self.assertEqual(ns.source_published_at, "2026-05-07T18:30:00+09:00")

    def test_parser_rejects_invalid_mode(self):
        p = mi._build_arg_parser()
        with self.assertRaises(SystemExit):
            p.parse_args(["https://x.com/foo/status/1", "--mode", "publish"])


class SourcePublishedAtNormalizationTests(unittest.TestCase):
    def test_empty_returns_empty_no_error(self):
        self.assertEqual(mi._normalize_source_published_at(""), ("", ""))
        self.assertEqual(mi._normalize_source_published_at("   "), ("", ""))

    def test_jst_offset_preserved(self):
        norm, err = mi._normalize_source_published_at("2026-05-07T18:30:00+09:00")
        self.assertEqual(err, "")
        self.assertEqual(norm, "2026-05-07T18:30:00+09:00")

    def test_z_suffix_converted_to_jst(self):
        norm, err = mi._normalize_source_published_at("2026-05-07T09:30:00Z")
        self.assertEqual(err, "")
        # 09:30 UTC -> 18:30 JST
        self.assertEqual(norm, "2026-05-07T18:30:00+09:00")

    def test_utc_offset_converted_to_jst(self):
        norm, err = mi._normalize_source_published_at("2026-05-07T00:00:00+00:00")
        self.assertEqual(err, "")
        self.assertEqual(norm, "2026-05-07T09:00:00+09:00")

    def test_naive_treated_as_jst(self):
        norm, err = mi._normalize_source_published_at("2026-05-07T18:30:00")
        self.assertEqual(err, "")
        self.assertEqual(norm, "2026-05-07T18:30:00+09:00")

    def test_date_only_treated_as_jst_midnight(self):
        norm, err = mi._normalize_source_published_at("2026-05-07")
        self.assertEqual(err, "")
        self.assertEqual(norm, "2026-05-07T00:00:00+09:00")

    def test_invalid_returns_error(self):
        # Python 3.11+ datetime.fromisoformat accepts compact ISO forms like
        # "20260507", so the invalid fixtures here cover non-ISO strings.
        for bad in ("not-a-date", "2026/05/07", "yesterday", "tomorrow", "2026-13-40"):
            with self.subTest(bad=bad):
                norm, err = mi._normalize_source_published_at(bad)
                self.assertEqual(norm, "", f"unexpected normalized for {bad!r}: {norm!r}")
                self.assertEqual(err, "invalid_source_published_at")


class SourcePublishedAtIntakeTests(_IntakeBaseTest):
    def test_invalid_source_published_at_exit_15_no_wp(self):
        wp_factory = MagicMock()
        code, out = mi.run_manual_intake(
            url="https://x.com/foo/status/1",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="draft",
            source_published_at="not-a-date",
            wp_client_factory=wp_factory,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_INVALID_SOURCE_PUBLISHED_AT)
        self.assertEqual(out["reason"], "validation_failed")
        self.assertEqual(out["skip_reason"], "invalid_source_published_at")
        self.assertEqual(out["normalized_source_published_at"], "")
        wp_factory.assert_not_called()

    def test_normalized_source_published_at_in_output_dry_run(self):
        code, out = mi.run_manual_intake(
            url="https://x.com/foo/status/1",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="dry-run",
            source_published_at="2026-05-07T09:30:00Z",
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(
            out["normalized_source_published_at"], "2026-05-07T18:30:00+09:00"
        )

    def test_x_draft_passes_source_published_at_to_create_post_meta(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 401

        wp = MagicMock()
        wp.create_post = fake_create
        code, out = mi.run_manual_intake(
            url="https://x.com/TokyoGiants/status/12345",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="draft",
            source_published_at="2026-05-07T18:30:00+09:00",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        # Primary path: WP meta carries the timestamp.
        self.assertEqual(
            captured.get("source_published_at_iso"), "2026-05-07T18:30:00+09:00"
        )
        content = captured.get("content", "")
        # Visible body no longer carries date display — meta-only path.
        self.assertNotIn("投稿日時", content)
        self.assertNotIn("2026-05-07T18:30:00+09:00", content)
        # X URL still rendered as embed only — no X API.
        self.assertIn("twitter-tweet", content)
        self.assertEqual(
            out["normalized_source_published_at"], "2026-05-07T18:30:00+09:00"
        )
        self.assertEqual(out["source_kind"], "x")

    def test_news_draft_passes_source_published_at_to_create_post_meta(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 402

        wp = MagicMock()
        wp.create_post = fake_create
        code, out = mi.run_manual_intake(
            url="https://hochi.news/articles/abc-123.html",
            title_override="巨人 試合速報 0-5 ヤクルト",
            summary_override="ヤクルト戦敗戦",
            mode="draft",
            source_published_at="2026-05-07T18:30:00+09:00",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(
            captured.get("source_published_at_iso"), "2026-05-07T18:30:00+09:00"
        )
        content = captured.get("content", "")
        # summary must remain visible; date display is meta-only.
        self.assertIn("ヤクルト戦敗戦", content)
        self.assertNotIn("出典公開日時", content)
        self.assertNotIn("2026-05-07T18:30:00+09:00", content)
        # category routing unchanged.
        self.assertEqual(captured.get("categories"), [664])
        self.assertEqual(
            out["normalized_source_published_at"], "2026-05-07T18:30:00+09:00"
        )

    def test_memo_does_not_leak_when_source_published_at_set(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 403

        wp = MagicMock()
        wp.create_post = fake_create
        secret_memo = "MEMO_SECRET_TOKEN_002"
        code, _out = mi.run_manual_intake(
            url="https://x.com/TokyoGiants/status/55555",
            title_override="巨人 試合終了 0-5 ヤクルト",
            summary_override="ヤクルト戦敗戦",
            memo=secret_memo,
            mode="draft",
            source_published_at="2026-05-07T18:30:00+09:00",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        content = captured.get("content", "")
        title = captured.get("title", "")
        # memo never leaks into body / title / meta value.
        self.assertNotIn(secret_memo, content)
        self.assertNotIn(secret_memo, title)
        self.assertNotEqual(
            captured.get("source_published_at_iso"), secret_memo
        )
        self.assertEqual(
            captured.get("source_published_at_iso"), "2026-05-07T18:30:00+09:00"
        )

    def test_naive_source_published_at_stored_as_jst_meta(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 404

        wp = MagicMock()
        wp.create_post = fake_create
        code, out = mi.run_manual_intake(
            url="https://hochi.news/articles/naive.html",
            title_override="巨人 試合速報 0-5 ヤクルト",
            summary_override="ヤクルト戦敗戦",
            mode="draft",
            source_published_at="2026-05-07T18:30:00",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(
            out["normalized_source_published_at"], "2026-05-07T18:30:00+09:00"
        )
        self.assertEqual(
            captured.get("source_published_at_iso"), "2026-05-07T18:30:00+09:00"
        )

    def test_omitted_source_published_at_passes_none_to_create_post(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 405

        wp = MagicMock()
        wp.create_post = fake_create
        code, out = mi.run_manual_intake(
            url="https://x.com/TokyoGiants/status/77777",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="draft",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        content = captured.get("content", "")
        self.assertNotIn("投稿日時", content)
        self.assertNotIn("出典公開日時", content)
        self.assertEqual(out["normalized_source_published_at"], "")
        # When unset, WPClient receives None (no meta written).
        self.assertIsNone(captured.get("source_published_at_iso"))


if __name__ == "__main__":
    unittest.main()
