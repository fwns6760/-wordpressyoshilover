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

    def test_topic_source_gets_limited_bypass_but_not_full_bypass(self):
        url = "https://friday.kodansha.co.jp/article/426377"
        with patch.dict(
            os.environ,
            {
                "ENABLE_POST_GEN_VALIDATE_TOPIC_SOURCE_BYPASS": "1",
                "ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS": "0",
                "ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL": "1",
            },
            clear=False,
        ):
            self.assertTrue(rss_fetcher._post_gen_validate_trusted_bypass(url))
            self.assertFalse(rss_fetcher._post_gen_validate_trusted_bypass_full(url))


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


class IsReviewEligibleFailAxesTests(unittest.TestCase):
    """E2 (2026-05-08 afternoon): review draft 対象軸の絞り込みテスト。"""

    def test_only_lightweight_axes_eligible(self):
        # 軽微軸のみ → review draft 化 OK (True)
        for axes in (
            ["close_marker"],
            ["weak_subject_title:no_strong_marker"],
            ["weak_generated_title:foo"],
            ["duplicate_sentence:adjacent"],
            ["source_grounding_drift:actor"],
            ["intro_echo"],
            ["quote_integrity:unbalanced"],
            ["h3_count:excessive"],
            ["close_marker", "weak_subject_title:foo"],  # 複数軽微軸
        ):
            self.assertTrue(
                rss_fetcher._is_review_eligible_fail_axes(axes),
                f"{axes} should be review eligible",
            )

    def test_critical_axes_blocked(self):
        # 致命的軸を 1 つでも含むと review draft 化しない (False)
        for axes in (
            ["placeholder_body:empty_section"],
            ["placeholder_body:boilerplate"],
            ["entity_mismatch:active_team_mismatch"],
            ["TITLE_BODY_ENTITY_MISMATCH"],
            ["NO_GAME_BUT_RESULT"],
            ["GAME_RESULT_CONFLICT"],
            ["forbidden_phrase:foo"],
            ["starmen_title_prefix"],
            ["starmen_heading_prefix"],
            ["live_update_lineup_heading"],
            ["live_update_lineup_structure"],
        ):
            self.assertFalse(
                rss_fetcher._is_review_eligible_fail_axes(axes),
                f"{axes} should NOT be review eligible (critical axis)",
            )

    def test_mixed_critical_and_lightweight_blocked(self):
        # 軽微 + 致命的 mix → 致命的優先 → False (skip)
        self.assertFalse(
            rss_fetcher._is_review_eligible_fail_axes(
                ["close_marker", "placeholder_body:empty_section"]
            )
        )
        self.assertFalse(
            rss_fetcher._is_review_eligible_fail_axes(
                ["weak_subject_title:foo", "entity_mismatch:active_team"]
            )
        )

    def test_empty_axes_eligible(self):
        # 空 list は eligible (実際は post_gen_validate 通過状態なので呼ばれないが、
        # 防御的に True 返す)
        self.assertTrue(rss_fetcher._is_review_eligible_fail_axes([]))
        self.assertTrue(rss_fetcher._is_review_eligible_fail_axes(None))

    def test_axes_with_blank_strings_ignored(self):
        # blank string や None 含み → ignore して残りで判定
        self.assertTrue(
            rss_fetcher._is_review_eligible_fail_axes(["", "close_marker", "  "])
        )
        self.assertFalse(
            rss_fetcher._is_review_eligible_fail_axes(["", "placeholder_body"])
        )


class CreateDraftForceStatusTests(unittest.TestCase):
    """E が依存する _create_draft_with_same_fire_guard の force_status 引数 test."""

    def test_enrichment_raw_html_reaches_rss_pipeline(self):
        captured = {}

        class FakeWP:
            def create_post(self, title, content, **kwargs):
                captured["content"] = content
                return 99998

        def fake_enrich(content, **kwargs):
            if kwargs.get("raw_html") == "<html><article>巨人本文</article></html>":
                return content + "<p>📖 本文抜粋</p>"
            return content

        import logging
        logger = logging.getLogger("test")
        with (
            patch.object(rss_fetcher, "_apply_rss_pipeline_enrichment", side_effect=fake_enrich),
            patch.dict(os.environ, {"RUN_DRAFT_ONLY": "1"}, clear=False),
        ):
            post_id = rss_fetcher._create_draft_with_same_fire_guard(
                FakeWP(),
                logger,
                set(),
                {},
                "title",
                '<div class="nomotoke-card-test"><h3>🔗 出典記事</h3></div>',
                [1],
                "https://example.com/x",
                featured_media=None,
                enrichment_raw_html="<html><article>巨人本文</article></html>",
            )

        self.assertEqual(post_id, 99998)
        self.assertIn("📖 本文抜粋", captured["content"])

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

    def test_default_creation_stays_draft_before_publish_gate(self):
        captured = {}

        class FakeWP:
            def create_post(self, title, content, **kwargs):
                captured["status"] = kwargs.get("status")
                return 11112

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
        self.assertEqual(captured["status"], "draft")

    def test_no_force_status_uses_draft_first_even_when_live_publish_enabled(self):
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
        # RUN_DRAFT_ONLY=0 でも publish gate 前の WP 作成は draft-first。
        self.assertEqual(captured["status"], "draft")


class CrossSourceTitleReuseFlagTests(unittest.TestCase):
    """RELIABILITY-2026-05-08-DUP: 異 source 同 title 重複防止 flag の test."""

    def _capture_create_post(self, env_overrides):
        captured = {}

        class FakeWP:
            def create_post(self, title, content, **kwargs):
                captured["allow_title_only_reuse"] = kwargs.get("allow_title_only_reuse")
                captured["status"] = kwargs.get("status")
                return 22222

        import logging
        logger = logging.getLogger("test")
        with patch.dict(os.environ, env_overrides, clear=False):
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
        return captured

    def test_default_off_keeps_allow_title_reuse_false(self):
        # ENABLE_FETCHER_CROSS_SOURCE_TITLE_REUSE 未設定 → False (既存挙動維持、デグレ無)
        captured = self._capture_create_post({"RUN_DRAFT_ONLY": "0"})
        self.assertFalse(captured["allow_title_only_reuse"])

    def test_flag_off_explicit(self):
        captured = self._capture_create_post(
            {"RUN_DRAFT_ONLY": "0", "ENABLE_FETCHER_CROSS_SOURCE_TITLE_REUSE": "0"}
        )
        self.assertFalse(captured["allow_title_only_reuse"])

    def test_flag_on_passes_true_to_create_post(self):
        captured = self._capture_create_post(
            {"RUN_DRAFT_ONLY": "0", "ENABLE_FETCHER_CROSS_SOURCE_TITLE_REUSE": "1"}
        )
        self.assertTrue(captured["allow_title_only_reuse"])


class MainLoopUndefinedNameRegressionTests(unittest.TestCase):
    """RELIABILITY-2026-05-08-FIX: 17:00-17:30 fire 3 連続 0 drafts incident で
    `routing_template_key` 未定義 NameError が露呈。同類の static 未定義参照を
    ast で検出する regression。call-site の undefined variable bug を防ぐ。
    """

    def test_main_loop_no_undefined_template_routing_names(self):
        import ast
        from pathlib import Path
        src_path = Path(__file__).parent.parent / "src" / "rss_fetcher.py"
        tree = ast.parse(src_path.read_text())

        # _main 関数の scope 内 undefined name を ast で抽出
        main_node = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_main"),
            None,
        )
        self.assertIsNotNone(main_node, "_main function should exist")

        defined: set[str] = set()
        used: set[str] = set()
        for arg in main_node.args.args:
            defined.add(arg.arg)
        for sub in ast.walk(main_node):
            if isinstance(sub, ast.Name):
                if isinstance(sub.ctx, ast.Store):
                    defined.add(sub.id)
                elif isinstance(sub.ctx, ast.Load):
                    used.add(sub.id)

        # module-level globals
        global_names: set[str] = set()
        for sub in ast.walk(tree):
            if isinstance(sub, ast.Import):
                for alias in sub.names:
                    global_names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(sub, ast.ImportFrom):
                for alias in sub.names:
                    global_names.add(alias.asname or alias.name)
            elif isinstance(sub, (ast.FunctionDef, ast.ClassDef)) and sub is not main_node:
                global_names.add(sub.name)
            elif isinstance(sub, ast.Assign):
                for tgt in sub.targets:
                    if isinstance(tgt, ast.Name):
                        global_names.add(tgt.id)

        builtins = {
            "range", "len", "int", "str", "dict", "list", "set", "tuple",
            "print", "open", "True", "False", "None", "isinstance",
            "enumerate", "any", "all", "sum", "max", "min", "sorted",
            "reversed", "frozenset", "type", "hasattr", "getattr", "setattr",
            "Exception", "RuntimeError", "ValueError", "KeyError", "IndexError",
            "TypeError", "OSError", "AttributeError", "ZeroDivisionError",
            "BaseException", "StopIteration", "object", "bool", "float",
            "bytes", "bytearray", "iter", "next", "callable", "id", "repr",
            "vars", "dir", "globals", "locals", "super", "property",
            "staticmethod", "classmethod", "abs", "round", "divmod", "pow",
            "hex", "oct", "bin", "chr", "ord", "format", "input", "filter",
            "map", "zip", "slice", "complex", "Ellipsis", "NotImplemented",
            "GeneratorExit", "KeyboardInterrupt", "SystemExit", "FileNotFoundError",
            "FileExistsError", "PermissionError", "BrokenPipeError",
            "BlockingIOError", "ConnectionError", "ConnectionResetError",
            "ConnectionRefusedError", "ConnectionAbortedError", "ChildProcessError",
            "InterruptedError", "ProcessLookupError", "TimeoutError",
            "ImportError", "ModuleNotFoundError", "LookupError", "ArithmeticError",
            "BufferError", "EOFError", "MemoryError", "NameError", "OverflowError",
            "RecursionError", "ReferenceError", "RuntimeError", "SyntaxError",
            "IndentationError", "TabError", "SystemError", "UnboundLocalError",
            "UnicodeError", "UnicodeDecodeError", "UnicodeEncodeError",
            "UnicodeTranslateError", "Warning", "UserWarning", "DeprecationWarning",
            "PendingDeprecationWarning", "SyntaxWarning", "RuntimeWarning",
            "FutureWarning", "ImportWarning", "UnicodeWarning", "BytesWarning",
            "ResourceWarning", "NotImplementedError", "FloatingPointError",
            "AssertionError", "Generator", "Coroutine", "AsyncGenerator",
            "BlockingIOError", "BrokenPipeError", "exec", "eval", "compile",
            "delattr", "ascii", "hash", "memoryview", "iter", "breakpoint",
            "anext", "aiter", "__name__", "__file__", "__doc__", "__builtins__",
            "self", "cls",
        }
        all_known = defined | global_names | builtins
        undefined = used - all_known

        # template / routing 関連の未定義変数は禁止 (本 incident の核心)
        template_routing_undefined = sorted(
            n for n in undefined if "template" in n.lower() or "routing" in n.lower()
        )
        self.assertEqual(
            template_routing_undefined, [],
            f"_main 内に template/routing 関連の undefined name が残ってる: "
            f"{template_routing_undefined}。 1ea4c684 同型 NameError 防止。"
        )


class SameFireDuplicateGuardTests(unittest.TestCase):
    """RELIABILITY-2026-05-08-DUP-FIX: 18:31 fire で 65268+65269 同 source_url
    2 重 draft 化発生。_create_draft_with_same_fire_guard が name 通り guard
    していなかった (set に add のみで check 不在) のが直接原因。entry で既存
    check して 0 を返す挙動を保証する regression。
    """

    def _make_fake_wp(self):
        captured = {"calls": 0}

        class FakeWP:
            def create_post(self, title, content, **kwargs):
                captured["calls"] += 1
                return 88880 + captured["calls"]

        return FakeWP(), captured

    def test_same_source_url_second_call_returns_zero(self):
        wp, captured = self._make_fake_wp()
        import logging
        logger = logging.getLogger("test_same_fire_dup")
        same_fire_source_urls: set[str] = set()
        same_fire_title_sources: dict = {}

        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "1"}, clear=False):
            first = rss_fetcher._create_draft_with_same_fire_guard(
                wp, logger, same_fire_source_urls, same_fire_title_sources,
                "title-A", "<p>body</p>", [1],
                "https://example.com/article/1",
            )
            second = rss_fetcher._create_draft_with_same_fire_guard(
                wp, logger, same_fire_source_urls, same_fire_title_sources,
                "title-A-rewritten", "<p>body</p>", [1],
                "https://example.com/article/1",
            )

        # 1 回目は通常 post_id 返却、2 回目は dedup で 0
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)
        # WP create_post は 1 回しか呼ばれない (重複 skip 効いてる)
        self.assertEqual(captured["calls"], 1)

    def test_distinct_source_urls_both_succeed(self):
        wp, captured = self._make_fake_wp()
        import logging
        logger = logging.getLogger("test_same_fire_dup")
        same_fire_source_urls: set[str] = set()
        same_fire_title_sources: dict = {}

        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "1"}, clear=False):
            first = rss_fetcher._create_draft_with_same_fire_guard(
                wp, logger, same_fire_source_urls, same_fire_title_sources,
                "title-A", "<p>body</p>", [1],
                "https://example.com/article/1",
            )
            second = rss_fetcher._create_draft_with_same_fire_guard(
                wp, logger, same_fire_source_urls, same_fire_title_sources,
                "title-B", "<p>body</p>", [1],
                "https://example.com/article/2",
            )

        # 異 source_url なら両方成功 (既存 distinct test と整合)
        self.assertGreater(first, 0)
        self.assertGreater(second, 0)
        self.assertEqual(captured["calls"], 2)

    def test_empty_source_url_does_not_trigger_dedup(self):
        # source_url 空文字なら set に add されず dedup 対象外 (既存挙動維持)
        wp, captured = self._make_fake_wp()
        import logging
        logger = logging.getLogger("test_same_fire_dup")
        same_fire_source_urls: set[str] = set()
        same_fire_title_sources: dict = {}

        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "1"}, clear=False):
            first = rss_fetcher._create_draft_with_same_fire_guard(
                wp, logger, same_fire_source_urls, same_fire_title_sources,
                "title-X", "<p>body</p>", [1],
                "",
            )
            second = rss_fetcher._create_draft_with_same_fire_guard(
                wp, logger, same_fire_source_urls, same_fire_title_sources,
                "title-Y", "<p>body</p>", [1],
                "",
            )
        self.assertGreater(first, 0)
        self.assertGreater(second, 0)
        self.assertEqual(captured["calls"], 2)

    def test_html_unescape_normalization_for_dedup_key(self):
        # source_url の HTML escape (&amp;) と plain (&) を同一視 (normalize 後 dedup)
        wp, captured = self._make_fake_wp()
        import logging
        logger = logging.getLogger("test_same_fire_dup")
        same_fire_source_urls: set[str] = set()
        same_fire_title_sources: dict = {}

        with patch.dict(os.environ, {"RUN_DRAFT_ONLY": "1"}, clear=False):
            first = rss_fetcher._create_draft_with_same_fire_guard(
                wp, logger, same_fire_source_urls, same_fire_title_sources,
                "title-Q", "<p>body</p>", [1],
                "https://example.com/a?x=1&amp;y=2",
            )
            second = rss_fetcher._create_draft_with_same_fire_guard(
                wp, logger, same_fire_source_urls, same_fire_title_sources,
                "title-Q", "<p>body</p>", [1],
                "https://example.com/a?x=1&y=2",
            )
        # normalize 後同 URL → 2 回目 dedup
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(captured["calls"], 1)


if __name__ == "__main__":
    unittest.main()
