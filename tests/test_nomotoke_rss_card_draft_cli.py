"""Tests for src/tools/run_nomotoke_rss_card_draft.py — NOMOTOKE-RSS-CARD-001B.

Coverage (≥20 cases):
    - dry-run mode: WPClient.create_post is NEVER called (mock asserted)
    - draft mode: WPClient.create_post called with status="draft" + categories=list[int]
    - category NAME never reaches WPClient.create_post (kwargs assertion)
    - category_id_unresolved → skip
    - meta_policy: required_facts NOT in HTML body comment, IS in jsonl audit log
    - blocked templates rejected at --template flag and never emitted by router
    - same-run dedupe (layer 4)
    - Gemini surface mocks remain at 0 calls
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.nomotoke_rss_router import (  # noqa: E402
    RSS_ONLY_ALLOWED_TEMPLATES,
    RSS_ONLY_BLOCKED_TEMPLATES,
)
from src.tools import run_nomotoke_rss_card_draft as cli  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_fixture(tmp: Path, name: str, data: dict) -> None:
    p = tmp / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _categories_map() -> dict:
    """Real config/categories.json content."""
    return json.loads(
        (ROOT / "config" / "categories.json").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# CLI argparser tests
# ---------------------------------------------------------------------------
class CLIArgParserTests(unittest.TestCase):
    def test_default_mode_is_dry_run(self):
        p = cli._build_arg_parser()
        ns = p.parse_args([])
        self.assertEqual(ns.mode, "dry-run")

    def test_explicit_mode_draft_recognized(self):
        p = cli._build_arg_parser()
        ns = p.parse_args(["--mode", "draft"])
        self.assertEqual(ns.mode, "draft")

    def test_invalid_mode_rejected(self):
        p = cli._build_arg_parser()
        with self.assertRaises(SystemExit):
            p.parse_args(["--mode", "publish"])

    def test_blocked_template_in_allowlist_rejected(self):
        # Calling main with --template pointing at blocked template should exit 2.
        for tk in RSS_ONLY_BLOCKED_TEMPLATES[:1]:
            with patch.object(sys, "argv", ["prog", "--template", tk]):
                rc = cli.main(["--template", tk])
                self.assertEqual(rc, 2)


# ---------------------------------------------------------------------------
# Category id resolver
# ---------------------------------------------------------------------------
class CategoryResolverTests(unittest.TestCase):
    def test_short_news_url_falls_back_to_column(self):
        cmap = _categories_map()
        cid, name = cli.resolve_category_id_from_template(
            "nomotoke_card_short_news_url_v1",
            categories_map=cmap,
        )
        # ニュース category not in WP -> falls back to コラム
        self.assertEqual(name, "コラム")
        self.assertEqual(cid, cmap["コラム"])

    def test_pregame_pitcher_uses_game_category(self):
        cmap = _categories_map()
        cid, name = cli.resolve_category_id_from_template(
            "nomotoke_card_pregame_pitcher_v1",
            categories_map=cmap,
        )
        self.assertEqual(name, "試合速報")
        self.assertEqual(cid, cmap["試合速報"])

    def test_manager_comment_falls_back_to_kantoku(self):
        cmap = _categories_map()
        cid, name = cli.resolve_category_id_from_template(
            "nomotoke_card_manager_comment_v1",
            categories_map=cmap,
        )
        # 監督談話 not in WP -> falls back to 首脳陣
        self.assertEqual(name, "首脳陣")
        self.assertEqual(cid, cmap["首脳陣"])

    def test_player_comment_falls_back_to_player_info(self):
        cmap = _categories_map()
        cid, name = cli.resolve_category_id_from_template(
            "nomotoke_card_player_comment_v1",
            categories_map=cmap,
        )
        # 選手コメント not in WP -> 選手情報
        self.assertEqual(name, "選手情報")
        self.assertEqual(cid, cmap["選手情報"])

    def test_empty_map_returns_none(self):
        cid, name = cli.resolve_category_id_from_template(
            "nomotoke_card_short_news_url_v1",
            categories_map={},
        )
        self.assertIsNone(cid)
        self.assertEqual(name, "")


# ---------------------------------------------------------------------------
# WP payload structure
# ---------------------------------------------------------------------------
class WpPayloadTests(unittest.TestCase):
    def test_payload_uses_int_category_list(self):
        p = cli.build_wp_draft_payload(
            title="t",
            content_html="<p>x</p>",
            category_id=663,
            canonical_source_url="https://twitter.com/foo/status/1",
        )
        self.assertEqual(p["categories"], [663])
        self.assertIsInstance(p["categories"][0], int)
        self.assertEqual(p["status"], "draft")
        self.assertEqual(p["caller"], "nomotoke_card_draft_cli")
        self.assertEqual(p["source_lane"], "nomotoke_card")
        self.assertEqual(p["source_url"], "https://twitter.com/foo/status/1")

    def test_payload_rejects_zero_or_negative_category_id(self):
        with self.assertRaises(ValueError):
            cli.build_wp_draft_payload(
                title="t", content_html="<p>x</p>",
                category_id=0,
                canonical_source_url="https://x.com/foo/status/1",
            )
        with self.assertRaises(ValueError):
            cli.build_wp_draft_payload(
                title="t", content_html="<p>x</p>",
                category_id=-1,
                canonical_source_url="https://x.com/foo/status/1",
            )

    def test_payload_rejects_string_category(self):
        # Defensive: even if someone tries to pass a name string, raise.
        with self.assertRaises(ValueError):
            cli.build_wp_draft_payload(
                title="t", content_html="<p>x</p>",
                category_id="試合速報",  # type: ignore[arg-type]
                canonical_source_url="https://x.com/foo/status/1",
            )


# ---------------------------------------------------------------------------
# Same-run dedupe (layer 4)
# ---------------------------------------------------------------------------
class SameRunDedupeTests(unittest.TestCase):
    def test_first_call_not_duplicate(self):
        seen: set = set()
        self.assertFalse(
            cli.is_duplicate_nomotoke_card(
                seen=seen,
                source_url="https://twitter.com/foo/status/1",
                template_key="nomotoke_card_short_news_url_v1",
                title="t",
            )
        )

    def test_second_call_is_duplicate(self):
        seen: set = set()
        cli.is_duplicate_nomotoke_card(
            seen=seen,
            source_url="https://twitter.com/foo/status/1",
            template_key="nomotoke_card_short_news_url_v1",
            title="t",
        )
        self.assertTrue(
            cli.is_duplicate_nomotoke_card(
                seen=seen,
                source_url="https://twitter.com/foo/status/1",
                template_key="nomotoke_card_short_news_url_v1",
                title="t",
            )
        )

    def test_utm_normalized_url_dedupes_with_clean_url(self):
        seen: set = set()
        cli.is_duplicate_nomotoke_card(
            seen=seen,
            source_url="https://twitter.com/foo/status/1",
            template_key="nomotoke_card_short_news_url_v1",
            title="t",
        )
        self.assertTrue(
            cli.is_duplicate_nomotoke_card(
                seen=seen,
                source_url="https://twitter.com/foo/status/1?utm_source=tw",
                template_key="nomotoke_card_short_news_url_v1",
                title="t",
            )
        )


# ---------------------------------------------------------------------------
# Minimal HTML comment / meta policy
# ---------------------------------------------------------------------------
class MinimalHtmlCommentTests(unittest.TestCase):
    def test_comment_contains_only_minimal_keys(self):
        c = cli._build_minimal_html_comment(
            template_key="nomotoke_card_short_news_url_v1",
            source_url_hash="abcdef123456",
            route_id="deadbeefcafe1234",
        )
        self.assertIn("nomotoke_card_meta", c)
        self.assertIn("nomotoke_card_short_news_url_v1", c)
        self.assertIn("abcdef123456", c)
        self.assertIn("deadbeefcafe1234", c)

    def test_comment_does_not_contain_required_facts(self):
        c = cli._build_minimal_html_comment(
            template_key="x",
            source_url_hash="y",
            route_id="z",
        )
        for forbidden in ("required_facts", "extracted_facts", "tier", "confidence"):
            self.assertNotIn(forbidden, c)


# ---------------------------------------------------------------------------
# Per-entry pipeline: dry-run mode does NOT call WPClient.create_post
# ---------------------------------------------------------------------------
class DryRunNoWPCallTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.audit_path = Path(self._tmp.name) / "audit.jsonl"
        self.cmap = _categories_map()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _proc(self, *, mode: str, entry: dict, source_name: str, wp_factory=None):
        return cli._process_one_entry(
            source_name=source_name,
            entry=entry,
            template_allowlist=set(RSS_ONLY_ALLOWED_TEMPLATES),
            categories_map=self.cmap,
            same_run_dedupe=set(),
            mode=mode,
            audit_log_path=self.audit_path,
            wp_client_factory=wp_factory,
            logger=__import__("logging").getLogger("test"),
        )

    def test_dry_run_with_short_news_does_not_call_wp(self):
        wp_mock = MagicMock()
        s = self._proc(
            mode="dry-run",
            source_name="TokyoGiants",
            entry={
                "title": "巨人 試合速報 0-5 ヤクルト",
                "summary": "ヤクルト戦敗戦、9回完封負け",
                "link": "https://twitter.com/TokyoGiants/status/9001",
                "published": _now_iso(),
            },
            wp_factory=lambda: wp_mock,
        )
        self.assertTrue(s["matched"])
        self.assertEqual(s["template_key"], "nomotoke_card_short_news_url_v1")
        self.assertIsNone(s["wp_post_id"])
        wp_mock.create_post.assert_not_called()

    def test_dry_run_writes_audit_log_with_required_facts(self):
        self._proc(
            mode="dry-run",
            source_name="TokyoGiants",
            entry={
                "title": "巨人 試合速報 0-5 ヤクルト",
                "summary": "敗戦",
                "link": "https://twitter.com/TokyoGiants/status/9100",
                "published": _now_iso(),
            },
        )
        self.assertTrue(self.audit_path.exists())
        lines = [
            json.loads(ln)
            for ln in self.audit_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        self.assertTrue(any(r.get("required_facts_used") for r in lines))

    def test_audit_record_has_required_meta_keys(self):
        self._proc(
            mode="dry-run",
            source_name="TokyoGiants",
            entry={
                "title": "巨人 試合速報 0-5",
                "summary": "敗戦",
                "link": "https://twitter.com/TokyoGiants/status/9200",
                "published": _now_iso(),
            },
        )
        rec = json.loads(
            self.audit_path.read_text(encoding="utf-8").splitlines()[-1]
        )
        for key in (
            "route_id", "ts", "template_key", "source_url",
            "source_url_hash", "tier", "confidence", "extracted_facts",
            "required_facts_used", "category_id", "category_name",
            "rendered_title", "mode",
        ):
            self.assertIn(key, rec)


# ---------------------------------------------------------------------------
# Per-entry pipeline: draft mode CALLS WPClient.create_post
# ---------------------------------------------------------------------------
class DraftModeCallsWPTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.audit_path = Path(self._tmp.name) / "audit.jsonl"
        self.cmap = _categories_map()
        self.wp = MagicMock()
        self.wp.create_post = MagicMock(return_value=12345)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _proc(self, entry: dict, source_name="TokyoGiants"):
        return cli._process_one_entry(
            source_name=source_name,
            entry=entry,
            template_allowlist=set(RSS_ONLY_ALLOWED_TEMPLATES),
            categories_map=self.cmap,
            same_run_dedupe=set(),
            mode="draft",
            audit_log_path=self.audit_path,
            wp_client_factory=lambda: self.wp,
            logger=__import__("logging").getLogger("test"),
        )

    def test_draft_calls_create_post_with_status_draft(self):
        s = self._proc({
            "title": "巨人 試合速報 0-5 ヤクルト",
            "summary": "敗戦",
            "link": "https://twitter.com/TokyoGiants/status/8001",
            "published": _now_iso(),
        })
        self.assertTrue(s["matched"])
        self.assertEqual(s["wp_post_id"], 12345)
        self.wp.create_post.assert_called_once()
        kwargs = self.wp.create_post.call_args.kwargs
        self.assertEqual(kwargs["status"], "draft")
        self.assertEqual(kwargs["caller"], "nomotoke_card_draft_cli")
        self.assertEqual(kwargs["source_lane"], "nomotoke_card")

    def test_draft_categories_is_int_list(self):
        self._proc({
            "title": "巨人 試合速報 0-5 ヤクルト",
            "summary": "敗戦",
            "link": "https://twitter.com/TokyoGiants/status/8002",
            "published": _now_iso(),
        })
        kwargs = self.wp.create_post.call_args.kwargs
        cats = kwargs.get("categories")
        self.assertIsInstance(cats, list)
        self.assertEqual(len(cats), 1)
        self.assertIsInstance(cats[0], int)

    def test_draft_categories_is_never_string(self):
        # Run a few entries; assert no call ever passed a string category.
        for i in range(3):
            self._proc({
                "title": f"巨人 試合速報 {i} 0-5 ヤクルト",
                "summary": "敗戦",
                "link": f"https://twitter.com/TokyoGiants/status/710{i}",
                "published": _now_iso(),
            })
        for call in self.wp.create_post.call_args_list:
            cats = call.kwargs.get("categories")
            self.assertIsInstance(cats, list)
            for cid in cats:
                self.assertIsInstance(cid, int)
                self.assertNotIsInstance(cid, str)

    def test_draft_html_body_contains_minimal_comment(self):
        self._proc({
            "title": "巨人 試合速報 0-5 ヤクルト",
            "summary": "敗戦",
            "link": "https://twitter.com/TokyoGiants/status/8003",
            "published": _now_iso(),
        })
        body = self.wp.create_post.call_args.kwargs.get("content", "")
        self.assertIn("nomotoke_card_meta", body)
        # forbidden audit keys must NOT appear in body
        for forbidden in ("required_facts", "extracted_facts", "tier"):
            self.assertNotIn(forbidden, body)

    def test_draft_audit_log_written_with_post_id(self):
        s = self._proc({
            "title": "巨人 試合速報 0-5 ヤクルト",
            "summary": "敗戦",
            "link": "https://twitter.com/TokyoGiants/status/8004",
            "published": _now_iso(),
        })
        rec = json.loads(self.audit_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(rec["wp_post_id"], 12345)
        self.assertEqual(rec["mode"], "draft")


# ---------------------------------------------------------------------------
# Skip behavior: blocked router output / unresolved category / dedupe / etc.
# ---------------------------------------------------------------------------
class SkipBehaviorTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.audit_path = Path(self._tmp.name) / "audit.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _proc(self, *, entry, mode="dry-run", categories_map=None, dedupe=None, allowlist=None):
        return cli._process_one_entry(
            source_name="TokyoGiants",
            entry=entry,
            template_allowlist=allowlist if allowlist is not None else set(RSS_ONLY_ALLOWED_TEMPLATES),
            categories_map=categories_map if categories_map is not None else _categories_map(),
            same_run_dedupe=dedupe if dedupe is not None else set(),
            mode=mode,
            audit_log_path=self.audit_path,
            wp_client_factory=None,
            logger=__import__("logging").getLogger("test"),
        )

    def test_category_id_unresolved_when_categories_map_empty(self):
        s = self._proc(
            entry={
                "title": "巨人 試合速報 0-5",
                "summary": "敗戦",
                "link": "https://twitter.com/TokyoGiants/status/7001",
                "published": _now_iso(),
            },
            categories_map={},
        )
        self.assertEqual(s["skip_reason"], "category_id_unresolved")
        self.assertIsNone(s["wp_post_id"])

    def test_same_run_duplicate_skipped(self):
        dedupe: set = set()
        entry = {
            "title": "巨人 試合速報 0-5",
            "summary": "敗戦",
            "link": "https://twitter.com/TokyoGiants/status/7100",
            "published": _now_iso(),
        }
        s1 = self._proc(entry=entry, dedupe=dedupe)
        s2 = self._proc(entry=entry, dedupe=dedupe)
        self.assertEqual(s1["skip_reason"], "")
        self.assertEqual(s2["skip_reason"], "duplicate_same_run")

    def test_template_not_in_allowlist_skipped(self):
        # Build an allowlist that doesn't contain short_news_url, then submit
        # an entry that the router maps to short_news_url.
        s = self._proc(
            entry={
                "title": "巨人 試合速報 0-5",
                "summary": "敗戦",
                "link": "https://twitter.com/TokyoGiants/status/7200",
                "published": _now_iso(),
            },
            allowlist={"nomotoke_card_pregame_pitcher_v1"},
        )
        self.assertEqual(s["skip_reason"], "template_not_in_allowlist")

    def test_not_giants_skipped(self):
        # Use a non-tier-1 source so giants relevance check actually runs.
        s = cli._process_one_entry(
            source_name="日刊スポーツX",  # tier-3, not auto-relevant
            entry={
                "title": "東京女子プロレス 桐生真弥 王者鈴芽",
                "summary": "",
                "link": "https://twitter.com/nikkansports/status/7300",
                "published": _now_iso(),
            },
            template_allowlist=set(RSS_ONLY_ALLOWED_TEMPLATES),
            categories_map=_categories_map(),
            same_run_dedupe=set(),
            mode="dry-run",
            audit_log_path=self.audit_path,
            wp_client_factory=None,
            logger=__import__("logging").getLogger("test"),
        )
        self.assertEqual(s["skip_reason"], "not_giants_related")


# ---------------------------------------------------------------------------
# meta policy enforcement: required_facts NEVER in body, ALWAYS in jsonl
# ---------------------------------------------------------------------------
class MetaPolicyEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        self._tmp = tempfile.TemporaryDirectory()
        self.audit_path = Path(self._tmp.name) / "audit.jsonl"
        self.wp = MagicMock()
        self.wp.create_post = MagicMock(return_value=999)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_required_facts_full_text_never_in_wp_body(self):
        cli._process_one_entry(
            source_name="サンスポ巨人X",
            entry={
                "title": "巨人・阿部監督「セクレ_トtoken_xyz」",
                "summary": "",
                "link": "https://twitter.com/Sanspo_Giants/status/6001",
                "published": _now_iso(),
            },
            template_allowlist=set(RSS_ONLY_ALLOWED_TEMPLATES),
            categories_map=_categories_map(),
            same_run_dedupe=set(),
            mode="draft",
            audit_log_path=self.audit_path,
            wp_client_factory=lambda: self.wp,
            logger=__import__("logging").getLogger("test"),
        )
        body = self.wp.create_post.call_args.kwargs.get("content", "")
        # The HTML comment must NOT contain extracted_facts JSON / tier / confidence
        for forbidden in ("extracted_facts", "tier", "confidence", "required_facts_used"):
            self.assertNotIn(forbidden, body)

    def test_required_facts_full_text_present_in_jsonl(self):
        cli._process_one_entry(
            source_name="サンスポ巨人X",
            entry={
                "title": "巨人・阿部監督「反省、修正してやる」",
                "summary": "",
                "link": "https://twitter.com/Sanspo_Giants/status/6002",
                "published": _now_iso(),
            },
            template_allowlist=set(RSS_ONLY_ALLOWED_TEMPLATES),
            categories_map=_categories_map(),
            same_run_dedupe=set(),
            mode="draft",
            audit_log_path=self.audit_path,
            wp_client_factory=lambda: self.wp,
            logger=__import__("logging").getLogger("test"),
        )
        rec = json.loads(self.audit_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertIn("required_facts_used", rec)
        self.assertIn("extracted_facts", rec)
        self.assertIn("tier", rec)
        self.assertIn("confidence", rec)


# ---------------------------------------------------------------------------
# Gemini surfaces remain at zero invocations
# ---------------------------------------------------------------------------
class GeminiZeroCallTests(unittest.TestCase):
    def test_dry_run_does_not_invoke_gemini_surfaces(self):
        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            patches = []
            mocks = []
            for path in (
                "src.rss_fetcher._request_gemini_strict_text",
                "src.rss_fetcher.build_news_block",
            ):
                try:
                    p = patch(path)
                    m = p.start()
                    patches.append(p)
                    mocks.append(m)
                except Exception:
                    continue
            try:
                cli._process_one_entry(
                    source_name="TokyoGiants",
                    entry={
                        "title": "巨人 試合速報 0-5 ヤクルト",
                        "summary": "敗戦",
                        "link": "https://twitter.com/TokyoGiants/status/5001",
                        "published": _now_iso(),
                    },
                    template_allowlist=set(RSS_ONLY_ALLOWED_TEMPLATES),
                    categories_map=_categories_map(),
                    same_run_dedupe=set(),
                    mode="dry-run",
                    audit_log_path=audit_path,
                    wp_client_factory=None,
                    logger=__import__("logging").getLogger("test"),
                )
                for m in mocks:
                    m.assert_not_called()
            finally:
                for p in patches:
                    p.stop()


# ---------------------------------------------------------------------------
# CLI returns the right exit code on misuse
# ---------------------------------------------------------------------------
class CLIExitCodeTests(unittest.TestCase):
    def test_logging_source_is_rejected(self):
        # --source logging is reserved for the dry-run observability CLI.
        # Pass --mode dry-run to avoid attempting to construct a WPClient.
        rc = cli.main(["--source", "logging", "--mode", "dry-run"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
