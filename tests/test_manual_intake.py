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

from contextlib import ExitStack
import json
import re
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.tools import manual_intake as mi

YAHOO_POSTGAME_FIXTURE = (
    Path(__file__).parent / "fixtures" / "yahoo_game" / "2026_05_04_giants_swallows.html"
)


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

    def test_react_helmet_attribute_first_meta(self):
        # NTV (news.ntv.co.jp) ships React Helmet markup where every
        # meta tag carries data-react-helmet="true" as the first
        # attribute. The legacy ``<meta\s+property=`` patterns failed
        # to match this shape and returned empty meta, which propagated
        # up as missing_title_or_summary for any NTV URL.
        html_text = (
            '<html><head>'
            '<meta data-react-helmet="true" property="og:title" '
            'content="ナショナルズのウッドが激走で満塁ホームラン"/>'
            '<meta data-react-helmet="true" property="og:description" '
            'content="◇MLB ナショナルズ9-6メッツ"/>'
            '<meta data-react-helmet="true" property="og:image" '
            'content="https://news.ntv.co.jp/gimage/.../hero.jpg?w=1200"/>'
            '</head></html>'
        )
        m = mi._parse_og_meta(html_text)
        self.assertEqual(
            m["title"], "ナショナルズのウッドが激走で満塁ホームラン"
        )
        self.assertEqual(m["summary"], "◇MLB ナショナルズ9-6メッツ")
        self.assertEqual(
            m["image"], "https://news.ntv.co.jp/gimage/.../hero.jpg?w=1200"
        )

    def test_react_helmet_title_tag_with_attribute(self):
        # When og: meta is absent, the fallback regex must still match
        # ``<title data-react-helmet="true">...</title>`` — the React
        # Helmet shape adds a data-* attribute that the original
        # ``<title>(...)</title>`` literal did not allow.
        html_text = (
            '<html><head>'
            '<title data-react-helmet="true">日テレNEWS NNN タイトル</title>'
            '</head></html>'
        )
        m = mi._parse_og_meta(html_text)
        self.assertEqual(m["title"], "日テレNEWS NNN タイトル")


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
        self.assertEqual(out.get("wp_status"), "draft")

    # 6b. publish mode calls create_post(status="publish")
    def test_6b_publish_calls_create_post_with_status_publish(self):
        wp = MagicMock()
        wp.create_post = MagicMock(return_value=78)
        code, out = mi.run_manual_intake(
            url="https://x.com/foo/status/1",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="publish",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        wp.create_post.assert_called_once()
        kwargs = wp.create_post.call_args.kwargs
        self.assertEqual(kwargs.get("status"), "publish")
        self.assertEqual(kwargs.get("caller"), "manual_intake")
        self.assertEqual(out["post_id"], 78)
        self.assertEqual(out.get("wp_status"), "publish")

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
                "--article-type",
                "監督談話",
            ]
        )
        self.assertEqual(ns.memo, "宮原昇格")
        self.assertEqual(ns.mode, "dry-run")
        self.assertEqual(ns.title, "T")
        self.assertEqual(ns.summary, "S")
        self.assertEqual(ns.source_published_at, "2026-05-07T18:30:00+09:00")
        self.assertEqual(ns.article_type, "監督談話")

    def test_parser_default_article_type_is_auto(self):
        p = mi._build_arg_parser()
        ns = p.parse_args(["https://x.com/foo/status/1"])
        self.assertEqual(ns.article_type, mi.ARTICLE_TYPE_AUTO)

    def test_parser_rejects_invalid_article_type(self):
        p = mi._build_arg_parser()
        with self.assertRaises(SystemExit):
            p.parse_args(
                ["https://x.com/foo/status/1", "--article-type", "存在しない"]
            )

    def test_parser_rejects_invalid_mode(self):
        # 'publish' is now a valid CLI mode (status=publish path).
        # 'bogus' stands in as the rejection sentinel.
        p = mi._build_arg_parser()
        with self.assertRaises(SystemExit):
            p.parse_args(["https://x.com/foo/status/1", "--mode", "bogus"])

    def test_parser_accepts_publish_mode(self):
        p = mi._build_arg_parser()
        args = p.parse_args(["https://x.com/foo/status/1", "--mode", "publish"])
        self.assertEqual(args.mode, "publish")


class ArticleTypeNormalizationTests(unittest.TestCase):
    def test_empty_defaults_to_auto(self):
        self.assertEqual(
            mi._normalize_article_type(""), (mi.ARTICLE_TYPE_AUTO, "")
        )
        self.assertEqual(
            mi._normalize_article_type("  "), (mi.ARTICLE_TYPE_AUTO, "")
        )

    def test_known_values_pass_through(self):
        for value in mi.ARTICLE_TYPE_OVERRIDES.keys():
            with self.subTest(value=value):
                norm, err = mi._normalize_article_type(value)
                self.assertEqual(norm, value)
                self.assertEqual(err, "")

    def test_unknown_returns_error(self):
        for bad in ("Auto", "AUTO", "試合", "ニュース速報", "x"):
            with self.subTest(bad=bad):
                norm, err = mi._normalize_article_type(bad)
                self.assertEqual(norm, "")
                self.assertEqual(err, "invalid_article_type")

    def test_choices_tuple_includes_auto_and_overrides(self):
        self.assertIn(mi.ARTICLE_TYPE_AUTO, mi.ARTICLE_TYPE_CHOICES)
        for value in mi.ARTICLE_TYPE_OVERRIDES.keys():
            self.assertIn(value, mi.ARTICLE_TYPE_CHOICES)
        # 21 total: auto + 20 overrides (11 original + 6 for unused WP
        # categories + 3 for ticket / scorebook routes — ticket 416).
        self.assertEqual(len(mi.ARTICLE_TYPE_CHOICES), 21)

    def test_new_routes_cover_missing_wp_categories(self):
        # 不足していた 3 category に少なくとも 1 route が存在することを保証
        # (config/categories.json の WP id 666 / 667 / 668)。
        category_set = {meta[0] for meta in mi.ARTICLE_TYPE_OVERRIDES.values()}
        for cat in ("ドラフト・育成", "OB・解説者", "補強・移籍"):
            self.assertIn(cat, category_set, f"missing route for {cat}")

    def test_ticket_416_routes_present(self):
        # ticket 416: 3 種 (チケット情報 / チケット交換 / スコアブック) が
        # 既存 WP category 内に route されることを保証。
        self.assertEqual(
            mi.ARTICLE_TYPE_OVERRIDES["チケット情報"],
            ("球団情報", "ticket", "nomotoke_card_short_news_url_v1"),
        )
        self.assertEqual(
            mi.ARTICLE_TYPE_OVERRIDES["チケット交換"],
            ("球団情報", "ticket_trade", "nomotoke_card_short_news_url_v1"),
        )
        self.assertEqual(
            mi.ARTICLE_TYPE_OVERRIDES["スコアブック"],
            ("試合速報", "scorebook", "nomotoke_card_short_news_url_v1"),
        )

    def test_ticket_416_not_in_article_style_manual_types(self):
        # 416 新 3 種は short-news 風 layout、 article-style への昇格は不要。
        for new_type in ("チケット情報", "チケット交換", "スコアブック"):
            self.assertNotIn(
                new_type,
                mi.ARTICLE_STYLE_MANUAL_TYPES,
                f"{new_type} should not be in ARTICLE_STYLE_MANUAL_TYPES",
            )


class AutoGuessTicket416KeywordTests(unittest.TestCase):
    """ticket 416 で追加された 3 種 (チケット情報 / チケット交換 /
    スコアブック) の auto_guess 検出。"""

    def _guess(self, title: str, summary: str = "") -> str:
        return mi._auto_guess_article_type(url="", title=title, summary=summary)

    def test_scorebook(self):
        self.assertEqual(self._guess("巨人 vs DeNA 5月22日 スコアブック詳細"), "スコアブック")
        self.assertEqual(self._guess("ジャイアンツ スコアシート 第3戦"), "スコアブック")
        self.assertEqual(self._guess("スコア表で振り返る 巨人 5-3 阪神"), "スコアブック")

    def test_ticket_info(self):
        self.assertEqual(self._guess("巨人 シーズンチケット先行販売開始"), "チケット情報")
        self.assertEqual(self._guess("ファンクラブチケット 5月販売スケジュール"), "チケット情報")
        self.assertEqual(self._guess("ジャイアンツ チケット予約 開始"), "チケット情報")

    def test_ticket_trade(self):
        self.assertEqual(self._guess("巨人戦チケット 公式リセール 受付"), "チケット交換")
        self.assertEqual(self._guess("チケットトレード 5月東京ドーム"), "チケット交換")
        self.assertEqual(self._guess("ファン同士で譲渡できる新サービス"), "チケット交換")

    def test_priority_does_not_break_existing_score_path(self):
        # 「スコアブック」 keyword が無い 通常の試合結果は scorebook に
        # 化けず 既存 試合結果 path を維持。
        self.assertEqual(self._guess("巨人 5-3 阪神 試合終了"), "試合結果")

    def test_priority_does_not_break_ticket_keyword_in_team_news(self):
        # rss_fetcher 側で「チケット」 keyword が 球団情報 routing に使われて
        # いるが、 manual_intake._auto_guess_article_type は単独「チケット」
        # を hit させない (複合語限定) ので、 generic 「チケット」 を含む文は
        # 既存 fallback (コラム) に落ちる。
        self.assertEqual(self._guess("巨人ニュース まとめ"), "コラム")


class AutoGuessArticleTypeNewKeywordTests(unittest.TestCase):
    """Cover the 6 new article_type detections added for the unused
    WP categories (ドラフト・育成 / OB・解説者 / 補強・移籍)."""

    def _guess(self, title: str, summary: str = "") -> str:
        return mi._auto_guess_article_type(url="", title=title, summary=summary)

    def test_draft_pick(self):
        self.assertEqual(self._guess("巨人ドラフト1位指名は石塚裕惺"), "ドラフト")
        self.assertEqual(self._guess("ドラフト会議で巨人が交渉権獲得"), "ドラフト")

    def test_farm(self):
        self.assertEqual(self._guess("巨人2軍が首位に浮上"), "2軍・育成")
        self.assertEqual(self._guess("ファーム 育成選手 三塚琉生がプロ初HR"), "2軍・育成")
        self.assertEqual(self._guess("巨人3軍 紅白戦の結果"), "2軍・育成")

    def test_foreign_player(self):
        self.assertEqual(self._guess("巨人が新外国人キャベッジ獲得"), "助っ人")
        self.assertEqual(self._guess("助っ人ハワード 来日2年目"), "助っ人")

    def test_trade(self):
        self.assertEqual(self._guess("巨人と楽天がトレード成立"), "トレード")

    def test_ob(self):
        self.assertEqual(self._guess("巨人OB桑田氏が古巣にエール"), "OB情報")
        self.assertEqual(self._guess("元巨人 上原浩治氏が解説"), "OB情報")
        self.assertEqual(self._guess("引退発表 阿部慎之助"), "OB情報")

    def test_transfer_generic(self):
        self.assertEqual(self._guess("FA宣言した山田太郎が巨人入団"), "補強・移籍")
        self.assertEqual(self._guess("巨人 ルシアーノ獲得を発表"), "補強・移籍")

    def test_existing_paths_unchanged(self):
        # 既存 path が回帰していないこと(代表 3 件のみ check)。
        self.assertEqual(self._guess("巨人 5-3 阪神 試合終了"), "試合結果")
        self.assertEqual(
            mi._auto_guess_article_type(
                url="https://www.youtube.com/watch?v=abc", title=""
            ),
            "動画",
        )
        self.assertEqual(self._guess("公示 出場選手登録 田中将大"), "公示")


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
        # NOMOTOKE-INTAKE-JSONLD-EMIT-001: the published_at ISO string
        # IS expected to appear inside the JSON-LD schema (search-engine
        # metadata, invisible to readers). Strip the ``<script>`` block
        # before asserting the date is not in the user-visible body.
        visible_body = re.sub(
            r'<script[^>]*type="application/ld\+json"[^>]*>.*?</script>',
            "",
            content,
            flags=re.DOTALL,
        )
        self.assertNotIn("2026-05-07T18:30:00+09:00", visible_body)
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

    def test_auto_article_type_uses_existing_detector(self):
        # _resolve_routing_lightweight is patched in _IntakeBaseTest to return
        # ("選手情報", "manual_intake"); auto routing keeps that
        # category / subtype but NOMOTOKE-INTAKE-AUTO-ROUTE-001 now
        # upgrades the template_key to a nomotoke template (here:
        # ``nomotoke_card_short_news_url_v1`` because the title carries
        # 「試合速報」 + score + 「巨人」) so the body still receives
        # the full enrichment treatment instead of bare fallback.
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 410

        wp = MagicMock()
        wp.create_post = fake_create
        code, out = mi.run_manual_intake(
            url="https://hochi.news/articles/auto.html",
            title_override="巨人 試合速報 0-5 ヤクルト",
            summary_override="ヤクルト戦敗戦",
            mode="draft",
            article_type=mi.ARTICLE_TYPE_AUTO,
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(out["article_type"], mi.ARTICLE_TYPE_AUTO)
        self.assertEqual(out["article_type_source"], "auto_detected")
        self.assertEqual(out["category"], "選手情報")
        self.assertEqual(out["subtype"], "manual_intake")
        self.assertEqual(
            out["template_key"], "nomotoke_card_short_news_url_v1"
        )
        self.assertEqual(out["article_type_guess"], "試合速報")
        self.assertEqual(out["category_ids"], [664])
        self.assertEqual(captured.get("categories"), [664])

    def test_article_type_override_pins_category_subtype_template(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 411

        wp = MagicMock()
        wp.create_post = fake_create
        code, out = mi.run_manual_intake(
            url="https://hochi.news/articles/postgame.html",
            title_override="巨人 試合終了 5-2 ヤクルト",
            summary_override="勝利",
            mode="draft",
            article_type="試合結果",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(out["article_type"], "試合結果")
        self.assertEqual(out["article_type_source"], "user_override")
        self.assertEqual(out["category"], "試合速報")
        self.assertEqual(out["subtype"], "game_result")
        # NOMOTOKE-INTAKE-TEMPLATE-001: article_type now maps to nomotoke
        # template_key, not the legacy "manual_intake" sentinel.
        self.assertEqual(out["template_key"], "nomotoke_card_short_news_url_v1")
        # 試合速報 -> category_id 663 per config/categories.json
        self.assertEqual(out["category_ids"], [663])
        # WP receives the resolved category_id list, NOT the name.
        self.assertEqual(captured.get("categories"), [663])
        self.assertNotIn("試合速報", str(captured.get("categories")))

    def test_article_type_override_dry_run_resolves_category_ids(self):
        code, out = mi.run_manual_intake(
            url="https://hochi.news/articles/manager.html",
            title_override="阿部監督が打線について語る",
            summary_override="2軍からの昇格",
            mode="dry-run",
            article_type="監督談話",
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(out["category"], "首脳陣")
        self.assertEqual(out["subtype"], "manager")
        # 首脳陣 -> 665
        self.assertEqual(out["category_ids"], [665])

    def test_unknown_article_type_returns_exit_16_no_wp(self):
        wp_factory = MagicMock()
        code, out = mi.run_manual_intake(
            url="https://hochi.news/articles/x.html",
            title_override="巨人 試合終了 0-5 ヤクルト",
            summary_override="ヤクルト戦敗戦",
            mode="draft",
            article_type="not_a_real_type",
            wp_client_factory=wp_factory,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_INVALID_ARTICLE_TYPE)
        self.assertEqual(out["reason"], "validation_failed")
        self.assertEqual(out["skip_reason"], "invalid_article_type")
        wp_factory.assert_not_called()

    def test_article_type_override_does_not_alter_x_url_normalization(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 412

        wp = MagicMock()
        wp.create_post = fake_create
        code, out = mi.run_manual_intake(
            url="https://x.com/TokyoGiants/status/9999",
            title_override="巨人 試合終了 0-5 ヤクルト",
            mode="draft",
            article_type="試合結果",
            wp_client_factory=lambda: wp,
            rate_limit_lockfile=self.lockfile,
        )
        self.assertEqual(code, mi.EXIT_OK)
        self.assertEqual(out["source_kind"], "x")
        self.assertEqual(
            captured.get("source_url"),
            "https://twitter.com/TokyoGiants/status/9999",
        )
        self.assertEqual(out["category"], "試合速報")
        # Body still embed-only — no source-fact inflation from article_type.
        content = captured.get("content", "")
        self.assertIn("twitter-tweet", content)

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


class ManualIntakeColumnOutputRegressionTests(_IntakeBaseTest):
    def _fake_fetch_meta(
        self,
        *,
        title: str = "巨人・坂本勇人、節目を迎える現在地",
        summary: str = "巨人・坂本勇人の現在地を出典記事の内容に沿って整理する。",
        image: str = "https://example.com/sakamoto-hero.jpg",
    ):
        raw_html = (
            "<html><head>"
            f'<meta property="og:title" content="{title}">'
            f'<meta property="og:description" content="{summary}">'
            f'<meta property="og:image" content="{image}">'
            "</head><body></body></html>"
        )

        def fake_fetch(_url: str) -> dict[str, str]:
            return {
                "title": title,
                "summary": summary,
                "image": image,
                "_html": raw_html,
            }

        return fake_fetch

    def test_column_manual_intake_does_not_put_reader_ui_before_article_body(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 66257

        def fake_renderer(data):
            return {
                "validation_ok": True,
                "content_html": (
                    '<div class="nomotoke-card-short-news">'
                    f'<p class="nomotoke-lead">{data["summary"]}</p>'
                    "<h3>🔗 出典記事</h3>"
                    f'<p>記事全文は <a href="{data["source_url"]}">'
                    f'{data["title"]}</a> をご覧ください。</p>'
                    "</div>"
                ),
            }

        wp = MagicMock()
        wp.create_post = fake_create
        with ExitStack() as stack:
            stack.enter_context(
                patch("src.nomotoke_card_renderer.select_renderer", return_value=fake_renderer)
            )
            stack.enter_context(
                patch.object(
                    mi,
                    "_build_recent_games_block",
                    return_value='<aside class="nomotoke-recent-games">recent</aside>',
                )
            )
            stack.enter_context(
                patch.object(
                    mi,
                    "_build_standings_block",
                    return_value='<aside class="nomotoke-standings">standings</aside>',
                )
            )
            stack.enter_context(
                patch.object(
                    mi,
                    "_build_next_game_block",
                    return_value='<aside class="nomotoke-next-game">next</aside>',
                )
            )
            stack.enter_context(
                patch.object(
                    mi,
                    "_build_x_embeds_block_safe",
                    return_value='<aside class="nomotoke-x-embeds">x</aside>',
                )
            )
            stack.enter_context(patch.object(mi, "_build_related_articles_block", return_value=""))
            stack.enter_context(patch.object(mi, "_build_player_stats_block", return_value=""))
            stack.enter_context(patch.object(mi, "_build_author_other_articles_block", return_value=""))
            stack.enter_context(patch.object(mi, "_build_trust_badge_block", return_value=""))
            stack.enter_context(patch.object(mi, "_build_tag_chip_block", return_value=""))
            stack.enter_context(patch.object(mi, "_build_jsonld_article_schema", return_value=""))
            stack.enter_context(
                patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, []))
            )
            stack.enter_context(patch.object(mi, "_build_toc_block", return_value=""))
            stack.enter_context(
                patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html)
            )
            stack.enter_context(
                patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html)
            )
            code, out = mi.run_manual_intake(
                url="https://www.jprime.jp/articles/-/41583?display=b",
                mode="draft",
                article_type="コラム",
                wp_client_factory=lambda: wp,
                rate_limit_lockfile=self.lockfile,
                fetch_meta=self._fake_fetch_meta(),
            )

        self.assertEqual(code, mi.EXIT_OK, out)
        content = captured.get("content", "")
        self.assertEqual(out["category"], "コラム")
        self.assertEqual(captured.get("categories"), [670])
        self.assertIn('class="nomotoke-hero"', content)
        self.assertIn('class="nomotoke-lead"', content)
        self.assertLess(content.index('class="nomotoke-hero"'), content.index('class="nomotoke-lead"'))
        self.assertNotIn("この記事にコメントする", content[: content.index('class="nomotoke-hero"')])
        self.assertNotIn("nomotoke-share-buttons", content[: content.index('class="nomotoke-hero"')])
        self.assertEqual(content.count("nomotoke-share-buttons"), 1)
        self.assertNotIn("nomotoke-recent-games", content)
        self.assertNotIn("nomotoke-standings", content)
        self.assertNotIn("nomotoke-next-game", content)
        self.assertNotIn("nomotoke-x-embeds", content)

    def test_column_manual_intake_uses_og_image_as_featured_media(self):
        captured: dict = {}
        calls: list[tuple[str, str]] = []

        class FakeWP:
            def find_uploaded_media_id_for_url(self, image_url: str) -> int:
                return 0

            def upload_image_from_url(
                self,
                image_url: str,
                filename: str | None = None,
                source_url: str = "",
            ) -> int:
                calls.append((image_url, source_url))
                return 321

            def create_post(self, **kwargs):
                captured.update(kwargs)
                return 66257

        with (
            patch.object(mi, "_try_render_via_nomotoke", return_value="<p>本文</p>"),
            patch.object(mi, "_check_rate_limit", return_value=(True, 0)),
        ):
            code, out = mi.run_manual_intake(
                url="https://www.jprime.jp/articles/-/41583?display=b",
                mode="draft",
                article_type="コラム",
                wp_client_factory=FakeWP,
                rate_limit_lockfile=self.lockfile,
                fetch_meta=self._fake_fetch_meta(
                    image="https://example.com/source-eyecatch.jpg"
                ),
            )

        self.assertEqual(code, mi.EXIT_OK, out)
        self.assertEqual(
            calls,
            [
                (
                    "https://example.com/source-eyecatch.jpg",
                    "https://www.jprime.jp/articles/-/41583?display=b",
                )
            ],
        )
        self.assertEqual(captured.get("featured_media"), 321)


class PlayerStatsTableBlockTests(unittest.TestCase):
    def test_build_player_stats_block_renders_batter_table_with_sb(self):
        stats_lookup = {
            "浅野翔吾": {
                "kind": "batting",
                "record": {
                    "__rendered_name__": "浅野 翔吾",
                    "打率": ".280",
                    "本塁打": "2",
                    "打点": "14",
                    "盗塁": "5",
                },
            }
        }
        roster_entry = {"jersey_number": "51", "position": "外野手"}

        with (
            patch.object(
                mi, "_scan_giants_player_names_in_text", return_value=["浅野翔吾"]
            ),
            patch.object(mi, "_get_player_stats_lookup", return_value=stats_lookup),
            patch(
                "src.nomotoke_card_renderer._lookup_roster_by_name",
                return_value=roster_entry,
            ),
        ):
            block = mi._build_player_stats_block("浅野翔吾が打撃好調")

        self.assertIn('class="nomotoke-player-stats"', block)
        self.assertIn("浅野 翔吾", block)
        self.assertIn("<table", block)
        self.assertIn("<th>打率</th>", block)
        self.assertIn("<th>本塁打</th>", block)
        self.assertIn("<th>打点</th>", block)
        self.assertIn("<th>盗塁</th>", block)
        self.assertIn("<td>.280</td>", block)
        self.assertIn("<td>2</td>", block)
        self.assertIn("<td>14</td>", block)
        self.assertIn("<td>5</td>", block)

    def test_build_player_stats_block_renders_pitcher_table_with_strikeouts(self):
        stats_lookup = {
            "戸郷翔征": {
                "kind": "pitching",
                "record": {
                    "__rendered_name__": "戸郷 翔征",
                    "勝": "3",
                    "敗": "1",
                    "防御率": "2.50",
                    "奪三振": "41",
                },
            }
        }
        roster_entry = {"jersey_number": "20", "position": "投手"}

        with (
            patch.object(
                mi, "_scan_giants_player_names_in_text", return_value=["戸郷翔征"]
            ),
            patch.object(mi, "_get_player_stats_lookup", return_value=stats_lookup),
            patch(
                "src.nomotoke_card_renderer._lookup_roster_by_name",
                return_value=roster_entry,
            ),
        ):
            block = mi._build_player_stats_block("戸郷翔征が先発")

        self.assertIn("戸郷 翔征", block)
        self.assertIn("<table", block)
        self.assertIn("<th>勝</th>", block)
        self.assertIn("<th>敗</th>", block)
        self.assertIn("<th>防御率</th>", block)
        self.assertIn("<th>奪三振</th>", block)
        self.assertIn("<td>3</td>", block)
        self.assertIn("<td>1</td>", block)
        self.assertIn("<td>2.50</td>", block)
        self.assertIn("<td>41</td>", block)

    def test_build_player_stats_block_pitcher_table_does_not_show_batter_headers(self):
        stats_lookup = {
            "戸郷翔征": {
                "kind": "pitching",
                "record": {
                    "__rendered_name__": "戸郷 翔征",
                    "勝": "3",
                    "敗": "1",
                    "防御率": "2.50",
                    "奪三振": "41",
                },
            }
        }
        roster_entry = {"jersey_number": "20", "position": "投手"}

        with (
            patch.object(
                mi, "_scan_giants_player_names_in_text", return_value=["戸郷翔征"]
            ),
            patch.object(mi, "_get_player_stats_lookup", return_value=stats_lookup),
            patch(
                "src.nomotoke_card_renderer._lookup_roster_by_name",
                return_value=roster_entry,
            ),
        ):
            block = mi._build_player_stats_block("戸郷翔征が先発")

        self.assertNotIn("<th>打率</th>", block)
        self.assertNotIn("<th>本塁打</th>", block)
        self.assertNotIn("<th>打点</th>", block)
        self.assertNotIn("<th>盗塁</th>", block)

    def test_build_player_stats_block_without_stats_row_keeps_roster_only(self):
        roster_entry = {"jersey_number": "51", "position": "外野手"}

        with (
            patch.object(
                mi, "_scan_giants_player_names_in_text", return_value=["浅野翔吾"]
            ),
            patch.object(mi, "_get_player_stats_lookup", return_value={}),
            patch(
                "src.nomotoke_card_renderer._lookup_roster_by_name",
                return_value=roster_entry,
            ),
        ):
            block = mi._build_player_stats_block("浅野翔吾が調整")

        self.assertIn("浅野翔吾", block)
        self.assertNotIn("<table", block)
        self.assertNotIn("奪三振", block)
        self.assertNotIn("盗塁", block)

    def test_scan_giants_player_names_does_not_use_surname_only_for_tanaka(self):
        names = mi._scan_giants_player_names_in_text("【巨人】田中投手が次回登板へ向けて調整")

        self.assertEqual(names, [])

    def test_scan_giants_player_names_keeps_full_tanaka_entity_only(self):
        names = mi._scan_giants_player_names_in_text(
            "【巨人】田中将大「打線を線にしない」阪神戦へ向けて調整"
        )

        normalized = {mi._normalize_player_name_for_match(name) for name in names}
        self.assertIn("田中将大", normalized)
        self.assertNotIn("田中瑛斗", normalized)

    def test_build_player_stats_block_does_not_mix_tanaka_same_surname(self):
        stats_lookup = {
            "田中将大": {
                "kind": "pitching",
                "record": {
                    "__rendered_name__": "田中 将大",
                    "勝": "2",
                    "敗": "1",
                    "防御率": "3.21",
                    "奪三振": "18",
                },
            },
            "田中瑛斗": {
                "kind": "pitching",
                "record": {
                    "__rendered_name__": "田中 瑛斗",
                    "勝": "0",
                    "敗": "0",
                    "防御率": "4.50",
                    "奪三振": "5",
                },
            },
        }

        with patch.object(mi, "_get_player_stats_lookup", return_value=stats_lookup):
            block = mi._build_player_stats_block(
                "【巨人】田中将大「打線を線にしない」阪神戦へ向けて調整"
            )

        self.assertIn("田中 将大", block)
        self.assertNotIn("田中 瑛斗", block)


class ManualIntakeSourceOgDescriptionDensityTests(_IntakeBaseTest):
    def _patch_reader_enrichment(self, stack: ExitStack) -> None:
        for name in (
            "_build_related_articles_block",
            "_build_recent_games_block",
            "_build_matchup_record_block",
            "_build_standings_block",
            "_build_next_game_block",
            "_build_trust_badge_block",
            "_build_author_other_articles_block",
            "_build_recent_notice_timeline_block",
            "_build_other_games_block",
            "_build_x_embeds_block_safe",
            "_build_player_stats_block",
            "_build_share_buttons_block",
            "_build_meta_header_bar",
            "_build_toc_block",
            "_build_tag_chip_block",
            "_build_jsonld_article_schema",
        ):
            stack.enter_context(patch.object(mi, name, return_value=""))
        stack.enter_context(
            patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, []))
        )
        stack.enter_context(
            patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html)
        )
        stack.enter_context(
            patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html)
        )
        stack.enter_context(patch.object(mi, "_check_rate_limit", return_value=(True, 0)))

    def _fetch_meta(self, *, title: str, summary: str, og_description: str):
        raw_html = (
            "<html><head>"
            f'<meta property="og:title" content="{title}">'
            f'<meta property="og:description" content="{og_description}">'
            "</head><body></body></html>"
        )

        def fetch(_url: str) -> dict[str, str]:
            return {
                "title": title,
                "summary": summary,
                "_html": raw_html,
            }

        return fetch

    def test_matching_og_description_supplies_missing_news_facts(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 910

        wp = MagicMock()
        wp.create_post = fake_create
        title = "【巨人】ヤクルト戦 試合速報"
        summary = "試合速報"
        og_description = (
            "巨人は5-2でヤクルトに勝利。"
            "東京ドームでの一戦で中盤に勝ち越した。"
        )

        with ExitStack() as stack:
            self._patch_reader_enrichment(stack)
            code, out = mi.run_manual_intake(
                url="https://hochi.news/articles/source-og-density.html",
                mode="draft",
                article_type="ニュース",
                wp_client_factory=lambda: wp,
                rate_limit_lockfile=self.lockfile,
                fetch_meta=self._fetch_meta(
                    title=title,
                    summary=summary,
                    og_description=og_description,
                ),
            )

        self.assertEqual(code, mi.EXIT_OK, out)
        content = captured.get("content", "")
        self.assertEqual(out["template_key"], "nomotoke_card_short_news_url_v1")
        self.assertIn("巨人は5-2でヤクルトに勝利。", content)
        self.assertIn("東京ドーム", content)
        self.assertIn("<td>5-2</td>", content)

    def test_unrelated_og_description_is_not_used_for_news_facts(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 911

        wp = MagicMock()
        wp.create_post = fake_create
        title = "【巨人】ヤクルト戦 試合速報"
        summary = "試合速報"
        unrelated = (
            "【巨人】ヒヤリ…大城卓三のヘルメットにバット直撃。"
            "中日戦の9回にプレーを続行した。"
        )

        with ExitStack() as stack:
            self._patch_reader_enrichment(stack)
            code, out = mi.run_manual_intake(
                url="https://hochi.news/articles/source-og-unrelated.html",
                mode="draft",
                article_type="ニュース",
                wp_client_factory=lambda: wp,
                rate_limit_lockfile=self.lockfile,
                fetch_meta=self._fetch_meta(
                    title=title,
                    summary=summary,
                    og_description=unrelated,
                ),
            )

        self.assertEqual(code, mi.EXIT_OK, out)
        content = captured.get("content", "")
        self.assertNotIn("大城卓三", content)
        self.assertNotIn("中日戦", content)


class EmojiDecorationSafetyTests(unittest.TestCase):
    def test_apply_rss_pipeline_enrichment_returns_body_when_emoji_step_fails(self):
        base_html = (
            '<div class="nomotoke-card-short-news">'
            '<p class="nomotoke-lead">東京ドームで勝利</p>'
            "<h3>🔗 出典記事</h3>"
            '<p>記事全文は <a href="https://example.com/source">出典</a> '
            "をご覧ください。</p>"
            "</div>"
        )
        with (
            patch.object(mi, "_build_recent_games_block", return_value=""),
            patch.object(mi, "_build_x_embeds_block", return_value=""),
            patch.object(mi, "_build_standings_block", return_value=""),
            patch.object(mi, "_build_next_game_block", return_value=""),
            patch.object(mi, "_build_trust_badge_block", return_value=""),
            patch.object(
                mi, "_inject_toc_anchors", side_effect=lambda html: (html, [])
            ),
            patch.object(mi, "_build_toc_block", return_value=""),
            patch.object(mi, "_build_meta_header_bar", return_value=""),
            patch.object(mi, "_build_share_buttons_block", return_value=""),
            patch.object(
                mi,
                "_wrap_first_roster_names_in_lead",
                side_effect=lambda html: html,
            ),
            patch.object(mi, "_build_tag_chip_block", return_value=""),
            patch.object(mi, "_build_jsonld_article_schema", return_value=""),
            patch.object(
                mi,
                "_decorate_body_with_emoji",
                side_effect=RuntimeError("emoji explode"),
            ),
        ):
            out = mi.apply_rss_pipeline_enrichment(
                base_html,
                title="",
                source_url="https://example.com/source",
                summary="",
                source_name="スポーツ報知",
            )
        self.assertIn('class="nomotoke-card-short-news"', out)
        self.assertIn("東京ドームで勝利", out)
        self.assertIn("🔗 出典記事", out)


class PostgameExpansionTests(unittest.TestCase):
    def test_build_lineup_block_renders_tables_with_team_labels(self):
        block = mi._build_lineup_block(
            [{"order": "1", "position": "中", "name": "丸佳浩"}],
            [{"order": "1", "position": "中", "name": "西川遥輝"}],
            home_label="巨人",
            away_label="ヤクルト",
        )

        self.assertIn('class="nomotoke-lineup"', block)
        self.assertIn("<table", block)
        self.assertIn("巨人", block)
        self.assertIn("ヤクルト", block)
        self.assertIn("<th>打順</th>", block)
        self.assertIn("<th>位置</th>", block)
        self.assertIn("<th>選手名</th>", block)

    def test_extract_yahoo_result_pitchers_from_html(self):
        html_text = YAHOO_POSTGAME_FIXTURE.read_text(encoding="utf-8")

        rows = mi._extract_yahoo_result_pitchers_from_yahoo_html(html_text)

        self.assertEqual(rows[0]["label"], "勝利投手")
        self.assertEqual(rows[0]["team"], "ヤクルト")
        self.assertEqual(rows[0]["player"], "奥川")
        self.assertEqual(rows[0]["record"], "1勝2敗0S")
        self.assertEqual(rows[1]["label"], "敗戦投手")
        self.assertEqual(rows[1]["team"], "巨人")
        self.assertEqual(rows[1]["player"], "戸郷")
        self.assertEqual(rows[1]["record"], "0勝1敗0S")
        self.assertEqual(rows[2]["label"], "セーブ")
        self.assertEqual(rows[2]["player"], "-")

    def test_build_x_embeds_block_postgame_allows_up_to_five_matches(self):
        pool = [
            {
                "url": f"https://x.com/example/status/{index}",
                "text": f"巨人 阪神 試合結果 {index}",
                "pubdate": f"Sat, 10 May 2026 12:0{index}:00 +0900",
            }
            for index in range(6)
        ]

        with patch.object(mi, "_get_x_embed_pool", return_value=pool):
            block = mi._build_x_embeds_block(
                "巨人が阪神に勝利",
                "阪神戦の試合結果",
                template_key="nomotoke_card_postgame_v1",
            )

        self.assertEqual(block.count("twitter-tweet"), 5)

    def test_apply_rss_pipeline_enrichment_postgame_adds_result_pitchers_and_lineup_tables(self):
        raw_html = YAHOO_POSTGAME_FIXTURE.read_text(encoding="utf-8")
        base_html = (
            '<div class="nomotoke-card-postgame">'
            '<p class="nomotoke-lead">ヤクルト戦敗戦</p>'
            "<h3>🔗 出典記事</h3>"
            '<p>記事全文は <a href="https://example.com/source">出典</a> '
            "をご覧ください。</p>"
            "</div>"
        )

        with (
            patch.object(mi, "_build_related_articles_block", return_value=""),
            patch.object(mi, "_build_recent_games_block", return_value=""),
            patch.object(mi, "_build_matchup_record_block", return_value=""),
            patch.object(mi, "_build_standings_block", return_value=""),
            patch.object(mi, "_build_next_game_block", return_value=""),
            patch.object(mi, "_build_trust_badge_block", return_value=""),
            patch.object(mi, "_build_other_games_block", return_value=""),
            patch.object(mi, "_build_x_embeds_block", return_value=""),
            patch.object(mi, "_build_share_buttons_block", return_value=""),
            patch.object(mi, "_build_meta_header_bar", return_value=""),
            patch.object(mi, "_build_toc_block", return_value=""),
            patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, [])),
            patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html),
            patch.object(mi, "_build_tag_chip_block", return_value=""),
            patch.object(mi, "_build_jsonld_article_schema", return_value=""),
            patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html),
        ):
            rendered = mi.apply_rss_pipeline_enrichment(
                base_html,
                title="【試合結果】巨人 1-5 ヤクルト",
                source_url="https://baseball.yahoo.co.jp/npb/game/2021029183/index",
                template_key="nomotoke_card_postgame_v1",
                summary="ヤクルト戦敗戦",
                source_name="Yahoo!スポーツ",
                raw_html=raw_html,
            )

        self.assertIsInstance(rendered, str)
        self.assertIn("責任投手", rendered)
        self.assertIn("今日のスタメン", rendered)
        self.assertIn("奥川", rendered)
        self.assertIn("戸郷 翔征", rendered)
        self.assertIn("<table", rendered)

    def test_apply_rss_pipeline_enrichment_postgame_returns_body_when_x_embed_step_fails(self):
        raw_html = YAHOO_POSTGAME_FIXTURE.read_text(encoding="utf-8")
        base_html = (
            '<div class="nomotoke-card-postgame">'
            '<p class="nomotoke-lead">ヤクルト戦敗戦</p>'
            "<h3>🔗 出典記事</h3>"
            '<p>記事全文は <a href="https://example.com/source">出典</a> '
            "をご覧ください。</p>"
            "</div>"
        )

        with (
            patch.object(mi, "_build_related_articles_block", return_value=""),
            patch.object(mi, "_build_recent_games_block", return_value=""),
            patch.object(mi, "_build_matchup_record_block", return_value=""),
            patch.object(mi, "_build_standings_block", return_value=""),
            patch.object(mi, "_build_next_game_block", return_value=""),
            patch.object(mi, "_build_trust_badge_block", return_value=""),
            patch.object(mi, "_build_other_games_block", return_value=""),
            patch.object(mi, "_build_x_embeds_block", side_effect=RuntimeError("x embed explode")),
            patch.object(mi, "_build_share_buttons_block", return_value=""),
            patch.object(mi, "_build_meta_header_bar", return_value=""),
            patch.object(mi, "_build_toc_block", return_value=""),
            patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, [])),
            patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html),
            patch.object(mi, "_build_tag_chip_block", return_value=""),
            patch.object(mi, "_build_jsonld_article_schema", return_value=""),
            patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html),
        ):
            rendered = mi.apply_rss_pipeline_enrichment(
                base_html,
                title="【試合結果】巨人 1-5 ヤクルト",
                source_url="https://baseball.yahoo.co.jp/npb/game/2021029183/index",
                template_key="nomotoke_card_postgame_v1",
                summary="ヤクルト戦敗戦",
                source_name="Yahoo!スポーツ",
                raw_html=raw_html,
            )

        self.assertIsInstance(rendered, str)
        self.assertIn("🔗 出典記事", rendered)
        self.assertIn("責任投手", rendered)


class SourceBodyExcerptExpansionTests(_IntakeBaseTest):
    def _source_html(self, body: str) -> str:
        return (
            '<html><head><script type="application/ld+json">'
            + json.dumps(
                {
                    "@type": "NewsArticle",
                    "articleBody": body,
                    "headline": "巨人ニュース",
                },
                ensure_ascii=False,
            )
            + "</script></head><body></body></html>"
        )

    def _fake_fetch(self, *, title: str, summary: str, body: str):
        raw_html = self._source_html(body)

        def fetch(_url: str) -> dict[str, str]:
            return {
                "title": title,
                "summary": summary,
                "_html": raw_html,
            }

        return fetch

    def _fake_fetch_without_article_body(self, *, title: str, summary: str):
        def fetch(_url: str) -> dict[str, str]:
            return {
                "title": title,
                "summary": summary,
                "_html": "<html><body><p>短い案内だけ</p></body></html>",
            }

        return fetch

    def _run_article_type_with_source_excerpt(
        self,
        article_type: str,
        *,
        url: str = "https://hochi.news/articles/source-body.html",
        title: str = "巨人の練習で若手が存在感",
        summary: str = "巨人の練習で若手が存在感を見せた。",
        body: str = (
            "巨人の練習で若手が存在感を見せた。"
            "打撃練習では逆方向への強い打球が目立ち、首脳陣も状態の良さを確認した。"
            "守備練習でも軽快な動きを見せ、今後の一軍争いへ向けてアピールを続けている。"
        ),
        manual_facts: dict[str, str] | None = None,
    ) -> str:
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 900

        def fake_renderer(data):
            return {
                "validation_ok": True,
                "content_html": (
                    '<div class="nomotoke-card-test">'
                    f'<p class="nomotoke-lead">{data.get("title") or summary}</p>'
                    "<h3>🔗 出典記事</h3>"
                    '<p>記事全文は <a href="https://example.com/source">出典</a> '
                    "をご覧ください。</p>"
                    "</div>"
                ),
            }

        wp = MagicMock()
        wp.create_post = fake_create
        with ExitStack() as stack:
            stack.enter_context(patch("src.nomotoke_card_renderer.select_renderer", return_value=fake_renderer))
            for name in (
                "_build_related_articles_block",
                "_build_recent_games_block",
                "_build_matchup_record_block",
                "_build_standings_block",
                "_build_next_game_block",
                "_build_trust_badge_block",
                "_build_author_other_articles_block",
                "_build_recent_notice_timeline_block",
                "_build_other_games_block",
                "_build_x_embeds_block_safe",
                "_build_player_stats_block",
                "_build_share_buttons_block",
                "_build_meta_header_bar",
                "_build_toc_block",
                "_build_tag_chip_block",
                "_build_jsonld_article_schema",
            ):
                stack.enter_context(patch.object(mi, name, return_value=""))
            stack.enter_context(
                patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, []))
            )
            stack.enter_context(
                patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html)
            )
            stack.enter_context(
                patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html)
            )
            stack.enter_context(patch.object(mi, "_check_rate_limit", return_value=(True, 0)))
            code, out = mi.run_manual_intake(
                url=url,
                mode="draft",
                article_type=article_type,
                wp_client_factory=lambda: wp,
                rate_limit_lockfile=self.lockfile,
                fetch_meta=self._fake_fetch(title=title, summary=summary, body=body),
                source_published_at="2026-05-10T12:00:00+09:00",
                manual_facts=manual_facts or {},
            )

        self.assertEqual(code, mi.EXIT_OK, out)
        return captured.get("content", "")

    def test_source_body_excerpt_renders_for_all_manual_article_types(self):
        cases = [
            ("試合結果", {}),
            ("試合速報", {}),
            ("予告先発", {"pitcher_a": "戸郷翔征", "pitcher_b": "才木浩人"}),
            ("公示", {"registered": "浅野翔吾"}),
            ("監督談話", {"manager_name": "阿部", "quote": "状態は上がっている"}),
            ("選手コメント", {"player_name": "浅野翔吾", "quote": "準備してきた"}),
            (
                "動画",
                {"player_name": "浅野翔吾", "play_summary": "打撃練習で快音"},
                "https://www.youtube.com/watch?v=abcdef12345",
            ),
            ("成績", {}),
            ("番組情報", {}),
            ("コラム", {}),
            ("ニュース", {}),
        ]

        for case in cases:
            if len(case) == 3:
                article_type, manual_facts, url = case
            else:
                article_type, manual_facts = case
                url = "https://hochi.news/articles/source-body.html"
            with self.subTest(article_type=article_type):
                content = self._run_article_type_with_source_excerpt(
                    article_type,
                    url=url,
                    manual_facts=manual_facts,
                )
                self.assertIn("📖 本文抜粋", content)
                self.assertIn("首脳陣も状態の良さを確認した", content)

    def test_source_body_excerpt_uses_600_char_limit(self):
        long_body = (
            "巨人の練習で若手が存在感を見せた。"
            + "一軍首脳陣は打撃練習でのタイミング、守備練習での初動、走塁練習での判断を順に確認した。"
            * 12
            + "ブルペンでの確認内容も共有された。"
            "記事後半には別メニュー調整の詳細も記されている。"
        )

        content = self._run_article_type_with_source_excerpt(
            "ニュース",
            body=long_body,
        )

        self.assertIn("📖 本文抜粋", content)
        self.assertIn("ブルペンでの確認内容も共有された", content)

    def test_source_body_excerpt_is_added_when_renderer_falls_back(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 901

        wp = MagicMock()
        wp.create_post = fake_create
        with ExitStack() as stack:
            for name in (
                "_build_related_articles_block",
                "_build_recent_games_block",
                "_build_standings_block",
                "_build_next_game_block",
                "_build_trust_badge_block",
                "_build_x_embeds_block_safe",
                "_build_player_stats_block",
                "_build_share_buttons_block",
                "_build_meta_header_bar",
                "_build_toc_block",
                "_build_tag_chip_block",
                "_build_jsonld_article_schema",
            ):
                stack.enter_context(patch.object(mi, name, return_value=""))
            stack.enter_context(
                patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, []))
            )
            stack.enter_context(
                patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html)
            )
            stack.enter_context(
                patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html)
            )
            stack.enter_context(patch.object(mi, "_check_rate_limit", return_value=(True, 0)))
            code, out = mi.run_manual_intake(
                url="https://hochi.news/articles/fallback.html",
                mode="draft",
                article_type="監督談話",
                wp_client_factory=lambda: wp,
                rate_limit_lockfile=self.lockfile,
                fetch_meta=self._fake_fetch(
                    title="阿部監督が若手について語る",
                    summary="阿部監督が若手について語った。",
                    body=(
                        "阿部監督が若手について語った。"
                        "練習後には打撃内容を評価し、今後の起用にも含みを持たせた。"
                    ),
                ),
            )

        self.assertEqual(code, mi.EXIT_OK, out)
        content = captured.get("content", "")
        self.assertIn("阿部監督が若手について語った", content)
        self.assertIn("📖 本文抜粋", content)
        self.assertIn("打撃内容を評価", content)

    def test_source_body_missing_keeps_original_fallback_body(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 902

        wp = MagicMock()
        wp.create_post = fake_create
        with ExitStack() as stack:
            for name in (
                "_build_related_articles_block",
                "_build_recent_games_block",
                "_build_standings_block",
                "_build_next_game_block",
                "_build_trust_badge_block",
                "_build_x_embeds_block_safe",
                "_build_player_stats_block",
                "_build_share_buttons_block",
                "_build_meta_header_bar",
                "_build_toc_block",
                "_build_tag_chip_block",
                "_build_jsonld_article_schema",
            ):
                stack.enter_context(patch.object(mi, name, return_value=""))
            stack.enter_context(
                patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, []))
            )
            stack.enter_context(
                patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html)
            )
            stack.enter_context(
                patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html)
            )
            stack.enter_context(patch.object(mi, "_check_rate_limit", return_value=(True, 0)))
            code, out = mi.run_manual_intake(
                url="https://hochi.news/articles/no-body.html",
                mode="draft",
                article_type="監督談話",
                wp_client_factory=lambda: wp,
                rate_limit_lockfile=self.lockfile,
                fetch_meta=self._fake_fetch_without_article_body(
                    title="阿部監督が若手について語る",
                    summary="阿部監督が若手について語った。",
                ),
            )

        self.assertEqual(code, mi.EXIT_OK, out)
        content = captured.get("content", "")
        self.assertIn("阿部監督が若手について語った", content)
        self.assertIn("🔗 出典記事", content)
        self.assertNotIn("📖 本文抜粋", content)

    def test_source_body_excerpt_skips_unrelated_article_body(self):
        content = self._run_article_type_with_source_excerpt(
            "ニュース",
            title="田中瑛斗、支配下登録後初の一軍マウンドへ",
            summary="巨人の田中瑛斗投手が支配下登録後初めて一軍で登板する見込み。",
            body=(
                "【巨人】ヒヤリ…大城卓三のヘルメットにバット直撃。"
                "打席後にトレーナーが状態を確認し、ベンチも一時騒然となった。"
            ),
        )

        self.assertNotIn("📖 本文抜粋", content)
        self.assertNotIn("大城卓三", content)

    def test_rss_pipeline_source_body_excerpt_skips_unrelated_article_body(self):
        base_html = (
            '<div class="nomotoke-card-short-news">'
            '<p class="nomotoke-lead">田中瑛斗、支配下登録後初の一軍マウンドへ</p>'
            "<h3>🔗 出典記事</h3>"
            '<p>記事全文は <a href="https://example.com/source">出典</a> をご覧ください。</p>'
            "</div>"
        )
        raw_html = self._source_html(
            "【巨人】ヒヤリ…大城卓三のヘルメットにバット直撃。"
            "打席後にトレーナーが状態を確認し、ベンチも一時騒然となった。"
        )

        with ExitStack() as stack:
            for name in (
                "_build_related_articles_block",
                "_build_recent_games_block",
                "_build_standings_block",
                "_build_next_game_block",
                "_build_trust_badge_block",
                "_build_x_embeds_block_safe",
                "_build_player_stats_block",
                "_build_share_buttons_block",
                "_build_meta_header_bar",
                "_build_toc_block",
                "_build_tag_chip_block",
                "_build_jsonld_article_schema",
            ):
                stack.enter_context(patch.object(mi, name, return_value=""))
            stack.enter_context(
                patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, []))
            )
            stack.enter_context(
                patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html)
            )
            stack.enter_context(
                patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html)
            )
            content = mi.apply_rss_pipeline_enrichment(
                base_html,
                title="田中瑛斗、支配下登録後初の一軍マウンドへ",
                source_url="https://hochi.news/articles/source-body.html",
                summary="巨人の田中瑛斗投手が支配下登録後初めて一軍で登板する見込み。",
                source_name="スポーツ報知",
                raw_html=raw_html,
            )

        self.assertIn("🔗 出典記事", content)
        self.assertNotIn("📖 本文抜粋", content)
        self.assertNotIn("大城卓三", content)

    def test_rss_pipeline_source_body_excerpt_skips_66331_cross_article_body(self):
        base_html = (
            '<div class="nomotoke-card-short-news">'
            '<p class="nomotoke-lead">巨人はここまで３６試合で１８勝１８敗、'
            "勝率５割でセ・リーグ３位。</p>"
            "<h3>🔗 出典記事</h3>"
            '<p>記事全文は <a href="https://hochi.news/articles/20260511-OHT1T51228.html">'
            "【巨人】交流戦まで残り１０試合　岐阜、福井で勝率５割から貯金アップ目指す"
            "</a> をご覧ください。</p>"
            "</div>"
        )
        raw_html = self._source_html(
            "【巨人】ヒヤリ…大城卓三のヘルメットにバット直撃。"
            "中日対巨人 9回裏中日1死一、三塁、木下拓哉の空振りしたバットが"
            "大城卓三の頭に当たりコーチらが駆けつけるもプレーを続行した。"
        )

        with ExitStack() as stack:
            for name in (
                "_build_related_articles_block",
                "_build_recent_games_block",
                "_build_standings_block",
                "_build_next_game_block",
                "_build_trust_badge_block",
                "_build_x_embeds_block_safe",
                "_build_player_stats_block",
                "_build_share_buttons_block",
                "_build_meta_header_bar",
                "_build_toc_block",
                "_build_tag_chip_block",
                "_build_jsonld_article_schema",
            ):
                stack.enter_context(patch.object(mi, name, return_value=""))
            stack.enter_context(
                patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, []))
            )
            stack.enter_context(
                patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html)
            )
            stack.enter_context(
                patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html)
            )
            content = mi.apply_rss_pipeline_enrichment(
                base_html,
                title="【巨人】交流戦まで残り１０試合　岐阜、福井で勝率５割から貯金アップ目指す",
                source_url="https://hochi.news/articles/20260511-OHT1T51228.html",
                summary="巨人はここまで３６試合で１８勝１８敗、勝率５割でセ・リーグ３位。",
                source_name="スポーツ報知 巨人 tag",
                raw_html=raw_html,
            )

        self.assertIn("🔗 出典記事", content)
        self.assertNotIn("📖 本文抜粋", content)
        self.assertNotIn("大城卓三", content)

    def test_rss_pipeline_source_body_excerpt_ignores_polluted_summary_for_66369(self):
        base_html = (
            '<div class="nomotoke-card-short-news">'
            '<p class="nomotoke-lead">巨人は中日戦で今季最多の９得点を挙げた。</p>'
            "<h3>🔗 出典記事</h3>"
            '<p>記事全文は <a href="https://hochi.news/articles/20260511-OHT1T51208.html">'
            "【YouTube】忖度なしに意見述べます…「昔、原監督や由伸監督は～」"
            "などと１９年の記者経験が…"
            "</a> をご覧ください。</p>"
            "</div>"
        )
        raw_html = self._source_html(
            "【巨人】ヒヤリ…大城卓三のヘルメットにバット直撃。"
            "＜中日4－9巨人＞◇10日◇バンテリンドーム。"
            "中日対巨人 9回裏中日1死一、三塁、木下拓哉の空振りしたバットが"
            "大城卓三の頭に当たりコーチらが駆けつけるもプレーを続行した。"
        )

        with ExitStack() as stack:
            for name in (
                "_build_related_articles_block",
                "_build_recent_games_block",
                "_build_standings_block",
                "_build_next_game_block",
                "_build_trust_badge_block",
                "_build_x_embeds_block_safe",
                "_build_player_stats_block",
                "_build_share_buttons_block",
                "_build_meta_header_bar",
                "_build_toc_block",
                "_build_tag_chip_block",
                "_build_jsonld_article_schema",
            ):
                stack.enter_context(patch.object(mi, name, return_value=""))
            stack.enter_context(
                patch.object(mi, "_inject_toc_anchors", side_effect=lambda html: (html, []))
            )
            stack.enter_context(
                patch.object(mi, "_wrap_first_roster_names_in_lead", side_effect=lambda html: html)
            )
            stack.enter_context(
                patch.object(mi, "_decorate_body_with_emoji_safe", side_effect=lambda html: html)
            )
            content = mi.apply_rss_pipeline_enrichment(
                base_html,
                title=(
                    "【YouTube】忖度なしに意見述べます…「昔、原監督や由伸監督は～」"
                    "などと１９年の記者経験が…"
                ),
                source_url="https://hochi.news/articles/20260511-OHT1T51208.html",
                summary="＜中日4－9巨人＞◇10日◇バンテリンドーム。巨人は今季最多９得点。",
                source_name="スポーツ報知",
                raw_html=raw_html,
            )

        self.assertIn("🔗 出典記事", content)
        self.assertNotIn("📖 本文抜粋", content)
        self.assertNotIn("大城卓三", content)


class PreviewOnlySourceFallbackTests(unittest.TestCase):
    """402: AERA Digital / 日経 (有料) / WEDGE 等の "続きを読む" 型 preview-
    only サイトで article-body が短すぎる場合に og:description (summary) を
    本文抜粋 block の fallback として注入する path の regression test。"""

    _RENDERED_PRE_INJECT = (
        '<p class="nomotoke-lead">lead text</p>\n'
        "<h3>🔗 出典記事</h3>\n"
        '<p>記事全文は <a href="https://example.com/x">元記事</a></p>'
    )

    def test_meta_fallback_injects_excerpt_block_when_body_too_short(self):
        # body extractor returns < 40 chars (AERA preview "...続きを読む" の
        # 内側 1 fragment しか取れない)、og:description (summary) は 120+ 字
        # の preview 段落を持つケース。fallback で excerpt block が入る。
        raw_html = (
            "<html><body>"
            '<div class="article-body">投手は「消耗品」</div>'
            "</body></html>"
        )
        long_summary = (
            "プロ野球界における先週最大のニュースと言えば、やはりDeNAと"
            "ソフトバンクのトレードになるだろう。DeNAからは山本祐大、"
            "ソフトバンクからは尾形崇斗と井上朋也が移籍することになった。"
        )
        out = mi._maybe_insert_source_body_excerpt(
            self._RENDERED_PRE_INJECT,
            raw_html=raw_html,
            source_url="https://dot.asahi.com/articles/-/282931",
            title="巨人は野手に余剰戦力 トレード候補を考える",
            source_name="dot.asahi.com",
            summary=long_summary,
        )
        self.assertIn("nomotoke-source-excerpt__body", out)
        self.assertIn("DeNAとソフトバンクのトレード", out)

    def test_no_fallback_when_extractor_returns_normal_body(self):
        # extractor が普通に取れる場合 (報知 / スポニチ等の long body) は
        # 通常経路で excerpt が入り、fallback path は通らない (= summary
        # を使わない)。回帰防止。
        raw_html = (
            "<html><body>"
            '<div class="article-body">'
            "<p>巨人の戸郷翔征投手が7回無失点と好投。"
            "今シーズン最長の7回115球で5安打無失点、今季初勝利を挙げた。"
            "二軍生活での苦労が報われた瞬間だった。</p>"
            "</div>"
            "</body></html>"
        )
        out = mi._maybe_insert_source_body_excerpt(
            self._RENDERED_PRE_INJECT,
            raw_html=raw_html,
            source_url="https://hochi.news/articles/foo.html",
            title="巨人 戸郷 7回無失点で初勝利",
            source_name="hochi.news",
            summary="まったく違う要約 (ignored)",
        )
        self.assertIn("nomotoke-source-excerpt__body", out)
        self.assertIn("戸郷翔征", out)
        # body の方が入ってる (summary は使われない)
        self.assertNotIn("まったく違う要約", out)

    def test_skip_when_both_extractor_and_summary_too_short(self):
        # extractor も summary も短すぎる場合は何も注入しない (回帰防止)。
        raw_html = "<html><body><p>短い</p></body></html>"
        out = mi._maybe_insert_source_body_excerpt(
            self._RENDERED_PRE_INJECT,
            raw_html=raw_html,
            source_url="https://example.com/x",
            title="短い記事",
            source_name="example.com",
            summary="短い",
        )
        self.assertNotIn("nomotoke-source-excerpt__body", out)


class RssPipelineForceEnrichmentTests(unittest.TestCase):
    """332-QA: ENABLE_RSS_PIPELINE_FORCE_ENRICHMENT で nomotoke-card-
    marker が無い RSS Gemini body にも enrichment が走るか。"""

    _BODY_WITHOUT_MARKER = (
        '<p>戸郷翔征が無失点で投球を続けた。</p>'
        '<h3>🔗 出典記事</h3>'
        '<p><a href="https://hochi.news/articles/foo.html">出典</a></p>'
    )

    def _kwargs(self):
        return dict(
            title="【巨人】戸郷翔征が無失点投球",
            source_url="https://hochi.news/articles/foo.html",
            summary="巨人戸郷翔征投手が無失点で投球を続けた。",
            category="選手情報",
            template_key="",
            source_name="スポーツ報知",
        )

    def test_flag_off_default_returns_unchanged(self):
        from src.tools import manual_intake as mi
        import os
        os.environ.pop("ENABLE_RSS_PIPELINE_FORCE_ENRICHMENT", None)
        result = mi.apply_rss_pipeline_enrichment(self._BODY_WITHOUT_MARKER, **self._kwargs())
        # marker 無し + flag OFF → 入力そのまま (既存挙動)
        self.assertEqual(result, self._BODY_WITHOUT_MARKER)

    def test_flag_on_runs_enrichment(self):
        from src.tools import manual_intake as mi
        import os
        os.environ["ENABLE_RSS_PIPELINE_FORCE_ENRICHMENT"] = "1"
        try:
            result = mi.apply_rss_pipeline_enrichment(self._BODY_WITHOUT_MARKER, **self._kwargs())
            # marker 無し + flag ON → enrichment 適用、結果が入力より長い
            # (実 enrichment 結果は環境依存だが、最低限 input != output を期待)
            self.assertNotEqual(result, self._BODY_WITHOUT_MARKER)
            # 入力の content は保持 (置換ではなく追加)
            self.assertIn("戸郷翔征が無失点", result)
        finally:
            os.environ.pop("ENABLE_RSS_PIPELINE_FORCE_ENRICHMENT", None)

    def test_marker_present_unaffected_by_flag(self):
        from src.tools import manual_intake as mi
        body_with_marker = (
            self._BODY_WITHOUT_MARKER
            + '<hr class="nomotoke-card-divider">'
        )
        # flag OFF でも marker あれば enrichment 走る (既存挙動)
        result = mi.apply_rss_pipeline_enrichment(body_with_marker, **self._kwargs())
        self.assertIn("戸郷翔征が無失点", result)
        # 出力には何らかの追加要素 (length が入力以上)
        self.assertGreaterEqual(len(result), len(body_with_marker))


class FanVoiceYahooFallbackTests(unittest.TestCase):
    """326-QA-fallback: cached X embed pool が空の時 Yahoo realtime
    fan reactions を fallback として render する。default ON。"""

    _BASE_HTML = (
        '<p class="nomotoke-lead">本文要約</p>'
        '<h3>🔗 出典記事</h3>'
        '<p><a href="https://hochi.news/articles/foo.html">出典</a></p>'
        '<hr class="nomotoke-card-divider">'
        '<div class="nomotoke-card-footer">'
        '<p class="nomotoke-cta-row"><a href="#respond">コメント</a></p>'
        '</div>'
    )

    def _kwargs(self):
        return dict(
            title="【巨人】戸郷翔征が無失点投球",
            source_url="https://hochi.news/articles/foo.html",
            summary="巨人戸郷翔征投手が無失点で投球を続けた。",
            category="選手情報",
            template_key="nomotoke_card_short_news_url_v1",
            source_name="スポーツ報知",
        )

    def test_fallback_block_helper_renders_h3_and_embeds(self):
        from src.tools import manual_intake as mi
        reactions = [
            {"url": "https://x.com/togofan/status/1"},
            {"url": "https://x.com/giants_love/status/2"},
        ]
        block = mi._build_fan_voice_yahoo_fallback_block(reactions, limit=5)
        self.assertIn("💬 ファンの声（Xより）", block)
        self.assertIn("twitter-tweet", block)
        self.assertIn("https://x.com/togofan/status/1", block)
        self.assertIn("https://x.com/giants_love/status/2", block)
        # widgets.js script は 1 度だけ
        self.assertEqual(block.count("widgets.js"), 1)

    def test_fallback_block_empty_for_no_reactions(self):
        from src.tools import manual_intake as mi
        self.assertEqual(mi._build_fan_voice_yahoo_fallback_block([], limit=5), "")
        self.assertEqual(
            mi._build_fan_voice_yahoo_fallback_block([{"url": ""}, {"url": "  "}], limit=5),
            "",
        )

    def test_fallback_fires_when_cached_pool_empty_and_flag_on(self):
        from src.tools import manual_intake as mi
        import os
        os.environ.pop("ENABLE_FAN_VOICE_YAHOO_FALLBACK", None)  # default ON
        with patch.object(mi, "_build_x_embeds_block_safe", return_value=""):
            with patch("src.rss_fetcher.fetch_fan_reactions_from_yahoo",
                       return_value=[{"url": "https://x.com/togofan/status/1"}]):
                result = mi.apply_rss_pipeline_enrichment(self._BASE_HTML, **self._kwargs())
        self.assertIn("💬 ファンの声（Xより）", result)
        self.assertIn("https://x.com/togofan/status/1", result)

    def test_fallback_skipped_when_cached_pool_provides_block(self):
        from src.tools import manual_intake as mi
        cached_block = (
            '<aside class="nomotoke-x-embeds">'
            '<p class="nomotoke-x-embeds__label">📲 関連 X 投稿</p>'
            '<blockquote class="twitter-tweet"><a href="https://x.com/cached/status/9"></a></blockquote>'
            '</aside>'
        )
        with patch.object(mi, "_build_x_embeds_block_safe", return_value=cached_block):
            with patch("src.rss_fetcher.fetch_fan_reactions_from_yahoo") as mock_fetch:
                result = mi.apply_rss_pipeline_enrichment(self._BASE_HTML, **self._kwargs())
                # cached block 採用なので Yahoo fetch は呼ばれない
                mock_fetch.assert_not_called()
        self.assertIn("https://x.com/cached/status/9", result)
        self.assertNotIn("💬 ファンの声（Xより）", result)

    def test_fallback_skipped_when_flag_off(self):
        from src.tools import manual_intake as mi
        import os
        os.environ["ENABLE_FAN_VOICE_YAHOO_FALLBACK"] = "0"
        try:
            with patch.object(mi, "_build_x_embeds_block_safe", return_value=""):
                with patch("src.rss_fetcher.fetch_fan_reactions_from_yahoo") as mock_fetch:
                    result = mi.apply_rss_pipeline_enrichment(self._BASE_HTML, **self._kwargs())
                    mock_fetch.assert_not_called()
            self.assertNotIn("💬 ファンの声（Xより）", result)
        finally:
            os.environ.pop("ENABLE_FAN_VOICE_YAHOO_FALLBACK", None)

    def test_fallback_skipped_when_yahoo_returns_zero(self):
        from src.tools import manual_intake as mi
        with patch.object(mi, "_build_x_embeds_block_safe", return_value=""):
            with patch("src.rss_fetcher.fetch_fan_reactions_from_yahoo", return_value=[]):
                result = mi.apply_rss_pipeline_enrichment(self._BASE_HTML, **self._kwargs())
        self.assertNotIn("💬 ファンの声（Xより）", result)

    def test_fallback_swallows_yahoo_exception(self):
        from src.tools import manual_intake as mi
        with patch.object(mi, "_build_x_embeds_block_safe", return_value=""):
            with patch("src.rss_fetcher.fetch_fan_reactions_from_yahoo",
                       side_effect=RuntimeError("network down")):
                # exception で記事生成が止まらないこと (fallback は黙って skip)
                result = mi.apply_rss_pipeline_enrichment(self._BASE_HTML, **self._kwargs())
        self.assertNotIn("💬 ファンの声（Xより）", result)
        self.assertIn("🔗 出典記事", result)


if __name__ == "__main__":
    unittest.main()
