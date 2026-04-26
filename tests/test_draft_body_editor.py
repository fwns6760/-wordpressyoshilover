"""Tests for ``src.tools.draft_body_editor`` (draft-body-editor v1).

Gemini API calls are always mocked. No network, no WP, no file system
changes outside the per-test temp directory.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import contextmanager
from typing import Iterable, Sequence
from unittest.mock import call, patch

from src.tools import draft_body_editor as dbe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PREGAME_BODY = (
    "【変更情報の要旨】\n"
    "先発投手の変更が発表されました。\n"
    "【具体的な変更内容】\n"
    "先発がスライド登板となります。\n"
    "【この変更が意味すること】\n"
    "投手陣のやり繰りに影響があります。"
)
PREGAME_SOURCE = "・先発投手の変更発表\n・スライド登板に変更"
PREGAME_NEW = (
    "【変更情報の要旨】\n"
    "先発投手の変更が発表されました。\n"
    "【具体的な変更内容】\n"
    "先発がスライド登板となります。\n"
    "【この変更が意味すること】\n"
    "投手陣のやり繰りに影響が及びます。"
)

POSTGAME_BODY = (
    "【試合結果】\n"
    "巨人が勝利しました。\n"
    "【ハイライト】\n"
    "序盤の得点が決め手でした。\n"
    "【選手成績】\n"
    "打線が好調でした。\n"
    "【試合展開】\n"
    "終盤は守備で締めました。"
)
POSTGAME_SOURCE = "・巨人が勝利\n・序盤の得点\n・打線が好調\n・終盤の守備"
POSTGAME_NEW = (
    "【試合結果】\n"
    "巨人が勝利を収めました。\n"
    "【ハイライト】\n"
    "序盤の得点が試合を決めました。\n"
    "【選手成績】\n"
    "打線が好調で流れを掴みました。\n"
    "【試合展開】\n"
    "終盤は守備で締めました。"
)

LINEUP_BODY = (
    "【試合概要】\n"
    "本日の試合が行われます。\n"
    "【スタメン一覧】\n"
    "発表されたスタメンです。\n"
    "【先発投手】\n"
    "本日の先発投手が決まりました。\n"
    "【注目ポイント】\n"
    "見どころを整理します。"
)
LINEUP_SOURCE = "・本日のスタメン発表\n・先発投手決定"
LINEUP_NEW = LINEUP_BODY.replace("見どころを整理します。", "見どころを押さえます。")

MANAGER_BODY = (
    "【発言の要旨】\n"
    "監督の発言をまとめます。\n"
    "【発言内容】\n"
    "選手起用について話しました。\n"
    "【文脈と背景】\n"
    "試合前の会見での発言です。\n"
    "【次の注目】\n"
    "次戦に向けた準備に注目です。"
)
MANAGER_SOURCE = "・監督発言\n・選手起用について\n・試合前会見"
MANAGER_NEW = MANAGER_BODY.replace(
    "次戦に向けた準備に注目です。",
    "次戦に向けた準備段階に注目です。",
)

FARM_BODY = (
    "【二軍結果・活躍の要旨】\n"
    "二軍の試合結果です。\n"
    "【ファームのハイライト】\n"
    "注目された場面を整理します。\n"
    "【二軍個別選手成績】\n"
    "選手の成績をまとめます。\n"
    "【一軍への示唆】\n"
    "一軍への影響を考えます。"
)
FARM_SOURCE = "・二軍の結果\n・注目場面\n・一軍への影響"
FARM_NEW = FARM_BODY.replace(
    "一軍への影響を考えます。",
    "一軍への影響について整理します。",
)


SUBTYPE_FIXTURES = {
    "pregame": (PREGAME_BODY, PREGAME_SOURCE, PREGAME_NEW),
    "postgame": (POSTGAME_BODY, POSTGAME_SOURCE, POSTGAME_NEW),
    "lineup": (LINEUP_BODY, LINEUP_SOURCE, LINEUP_NEW),
    "manager": (MANAGER_BODY, MANAGER_SOURCE, MANAGER_NEW),
    "farm": (FARM_BODY, FARM_SOURCE, FARM_NEW),
}


def _decorated_attrs(width: int = 4) -> str:
    return " ".join(f'data-deco-{idx}="{"x" * 90}"' for idx in range(width))


def _build_full_template_postgame_body() -> str:
    attrs = _decorated_attrs()
    sections = [
        ("【試合結果】", "結果の要点を整理します。" * 16),
        ("【ハイライト】", "流れを左右した場面をまとめます。" * 14),
        ("【選手成績】", "主力選手の内容を振り返ります。" * 14),
        ("【試合展開】", "終盤までの運びを簡潔に整理します。" * 13),
    ]
    return "".join(
        f'<section class="news-block" {attrs}>'
        f'<div class="news-block__head" {attrs}><h2>{heading}</h2></div>'
        f'<div class="news-block__body" {attrs}><p>{text}</p></div>'
        f'<footer class="news-block__footer" {attrs}></footer>'
        f"</section>"
        for heading, text in sections
    )


def _build_short_notice_postgame_body() -> str:
    sections = [
        ("【試合結果】", "結果の要点です。"),
        ("【ハイライト】", "決定打の場面です。"),
        ("【選手成績】", "主力の内容です。"),
        ("【試合展開】", "終盤の流れです。"),
    ]
    return "".join(
        f"<article><h2>{heading}</h2><p>{text}</p></article>"
        for heading, text in sections
    )


class _FakeGeminiResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def _gemini_response(text: str) -> _FakeGeminiResponse:
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": text}]}}
        ]
    }
    return _FakeGeminiResponse(json.dumps(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _tmp_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


def _write(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _make_argv(
    workspace: str,
    *,
    subtype: str,
    fail: str = "density",
    current_body: str | None = None,
    source_block: str | None = None,
    post_id: int = 1234,
    extra: Iterable[str] = (),
) -> list[str]:
    default_body, default_source, _ = SUBTYPE_FIXTURES[subtype]
    current_path = _write(
        os.path.join(workspace, "current.txt"),
        current_body if current_body is not None else default_body,
    )
    source_path = _write(
        os.path.join(workspace, "source.txt"),
        source_block if source_block is not None else default_source,
    )
    out_path = os.path.join(workspace, "out.txt")
    argv = [
        "--post-id", str(post_id),
        "--subtype", subtype,
        "--fail", fail,
        "--current-body", current_path,
        "--source-block", source_path,
        "--out", out_path,
    ]
    argv.extend(extra)
    return argv


def _run_main(argv: Sequence[str], *, gemini_return: str | None = None,
              gemini_side_effect: Exception | None = None) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with patch("src.tools.draft_body_editor.call_gemini") as mock_call, \
         patch("sys.stdout", stdout), patch("sys.stderr", stderr), \
         patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
        if gemini_side_effect is not None:
            mock_call.side_effect = gemini_side_effect
        else:
            mock_call.return_value = gemini_return or ""
        exit_code = dbe.main(list(argv))
    return exit_code, stdout.getvalue(), stderr.getvalue()


# ---------------------------------------------------------------------------
# Happy path per subtype
# ---------------------------------------------------------------------------


class TestValidSubtypes(unittest.TestCase):
    def _run_subtype(self, subtype: str, *, fail: str = "density") -> None:
        _, _, new_body = SUBTYPE_FIXTURES[subtype]
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype=subtype, fail=fail)
            exit_code, stdout, stderr = _run_main(argv, gemini_return=new_body)
            self.assertEqual(exit_code, 0, msg=f"{subtype} stderr={stderr}")
            payload = json.loads(stdout.strip())
            self.assertEqual(payload["subtype"], subtype)
            self.assertEqual(payload["guards"], "pass")
            expected_fail = [s.strip() for s in fail.split(",") if s.strip()]
            self.assertEqual(payload["fail"], expected_fail)
            out_path = argv[argv.index("--out") + 1]
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, encoding="utf-8") as f:
                self.assertEqual(f.read(), new_body)

    def test_pregame_pass(self):
        self._run_subtype("pregame")

    def test_postgame_pass(self):
        self._run_subtype("postgame", fail="density,core")

    def test_lineup_pass(self):
        self._run_subtype("lineup")

    def test_manager_pass(self):
        self._run_subtype("manager", fail="tone")

    def test_farm_pass(self):
        self._run_subtype("farm", fail="source")


# ---------------------------------------------------------------------------
# Input validation (exit 30)
# ---------------------------------------------------------------------------


class TestValidation(unittest.TestCase):
    def test_invalid_subtype_unknown(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            idx = argv.index("--subtype")
            argv[idx + 1] = "mystery"
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 30)
            self.assertIn("invalid subtype", stderr)

    def test_invalid_subtype_live_update(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            idx = argv.index("--subtype")
            argv[idx + 1] = "live_update"
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 30)
            self.assertIn("invalid subtype", stderr)

    def test_fail_three_axes(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame", fail="density,core,time")
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 30)
            self.assertIn("--fail", stderr)

    def test_fail_empty(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame", fail=" , ")
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 30)
            self.assertIn("--fail", stderr)

    def test_fail_invalid_code(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame", fail="density,xxx")
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 30)
            self.assertIn("invalid fail axis", stderr)

    def test_current_body_true_prose_too_long_rejects(self):
        with _tmp_workspace() as ws:
            long_body = "【試合結果】\n" + ("あ" * 1300) + "\n【ハイライト】\n...\n【選手成績】\n...\n【試合展開】\n..."
            argv = _make_argv(ws, subtype="postgame", current_body=long_body)
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 30)
            self.assertIn("prose chars", stderr)

    def test_current_body_full_template_short_prose_passes(self):
        with _tmp_workspace() as ws:
            current_body = _build_full_template_postgame_body()
            self.assertGreater(len(current_body), dbe.CURRENT_BODY_MAX_CHARS)
            self.assertLess(len(dbe._extract_prose_text(current_body)), dbe.CURRENT_BODY_MAX_CHARS)
            argv = _make_argv(ws, subtype="postgame", current_body=current_body)
            code, stdout, stderr = _run_main(argv, gemini_return=current_body)
            self.assertEqual(code, 0, msg=stderr)
            payload = json.loads(stdout.strip())
            self.assertEqual(payload["guards"], "pass")

    def test_current_body_short_notice_passes(self):
        with _tmp_workspace() as ws:
            current_body = _build_short_notice_postgame_body()
            self.assertLess(len(current_body), dbe.CURRENT_BODY_MAX_CHARS)
            self.assertLess(len(dbe._extract_prose_text(current_body)), dbe.CURRENT_BODY_MAX_CHARS)
            argv = _make_argv(ws, subtype="postgame", current_body=current_body)
            code, stdout, stderr = _run_main(argv, gemini_return=current_body)
            self.assertEqual(code, 0, msg=stderr)
            payload = json.loads(stdout.strip())
            self.assertEqual(payload["guards"], "pass")

    def test_current_body_empty(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame", current_body="")
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 30)
            self.assertIn("current_body is empty", stderr)

    def test_source_block_empty(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame", source_block="")
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 30)
            self.assertIn("source_block is empty", stderr)


# ---------------------------------------------------------------------------
# Guard A (exit 10)
# ---------------------------------------------------------------------------


class TestGuardA(unittest.TestCase):
    def test_team_name_not_in_source(self):
        tainted = POSTGAME_NEW.replace(
            "打線が好調で流れを掴みました。",
            "打線が好調で、阪神戦に弾みがつきました。",
        )
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=tainted)
            self.assertEqual(code, 10)
            self.assertIn("Guard A", stderr)
            self.assertIn("阪神", stderr)

    def test_score_literal_not_in_source(self):
        tainted = POSTGAME_NEW.replace(
            "巨人が勝利を収めました。",
            "巨人が3-1で勝利を収めました。",
        )
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=tainted)
            self.assertEqual(code, 10)
            self.assertIn("Guard A", stderr)
            self.assertIn("3-1", stderr)

    def test_ballpark_not_in_source(self):
        tainted = POSTGAME_NEW.replace(
            "終盤は守備で締めました。",
            "終盤は京セラで守備を固めました。",
        )
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=tainted)
            self.assertEqual(code, 10)
            self.assertIn("Guard A", stderr)
            self.assertIn("京セラ", stderr)

    def test_batting_avg_not_in_source(self):
        tainted = POSTGAME_NEW.replace(
            "打線が好調で流れを掴みました。",
            "打線が好調で、打率.312の選手が中心でした。",
        )
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=tainted)
            self.assertEqual(code, 10)
            self.assertIn("Guard A", stderr)

    def test_score_present_in_source_passes(self):
        # source explicitly contains the score -- new_body is allowed to use it.
        source = POSTGAME_SOURCE + "\n・スコアは3-1"
        body = POSTGAME_BODY.replace(
            "巨人が勝利しました。",
            "巨人が3-1で勝利しました。",
        )
        new = POSTGAME_NEW.replace(
            "巨人が勝利を収めました。",
            "巨人が3-1で勝利を収めました。",
        )
        with _tmp_workspace() as ws:
            argv = _make_argv(
                ws,
                subtype="postgame",
                current_body=body,
                source_block=source,
            )
            code, _, stderr = _run_main(argv, gemini_return=new)
            self.assertEqual(code, 0, msg=stderr)

    def test_new_player_name_is_not_hard_guarded_v1(self):
        """v1 does not dictionary-check player names -- documented behavior."""
        tainted = POSTGAME_NEW.replace(
            "打線が好調で流れを掴みました。",
            "打線が好調で流れを掴みました。鈴木健治が中心でした。",
        )
        with _tmp_workspace() as ws:
            # Guard A must not fire (no team/ballpark/numeric violation).
            # Guard C will fail because ratio drifts high; reroute by using
            # a longer current body so the ratio stays in range.
            extended_current = POSTGAME_BODY + "\n選手が中心でした。選手が中心でした。"
            extended_new = tainted + "\n選手が中心でした。"
            argv = _make_argv(
                ws,
                subtype="postgame",
                current_body=extended_current,
            )
            code, _, stderr = _run_main(argv, gemini_return=extended_new)
            # Guard A passes; the outcome is either 0 or a Guard C failure,
            # but never 10. This test asserts Guard A did not catch the name.
            self.assertNotEqual(code, 10, msg=f"expected Guard A to pass; stderr={stderr}")


# ---------------------------------------------------------------------------
# Prose extraction helper
# ---------------------------------------------------------------------------


class TestExtractProseText(unittest.TestCase):
    def test_empty_input_returns_empty_string(self):
        self.assertEqual(dbe._extract_prose_text(""), "")

    def test_plain_text_is_preserved(self):
        self.assertEqual(dbe._extract_prose_text("foo bar"), "foo bar")

    def test_adjacent_paragraphs_are_joined_with_space(self):
        self.assertEqual(dbe._extract_prose_text("<p>foo</p><p>bar</p>"), "foo bar")

    def test_script_and_style_contents_are_excluded(self):
        html = "<p>foo</p><script>alert(1)</script><style>.x{}</style><p>bar</p>"
        self.assertEqual(dbe._extract_prose_text(html), "foo bar")

    def test_consecutive_whitespace_is_normalized(self):
        html = "<div>foo \n\t bar</div><div> baz </div>"
        self.assertEqual(dbe._extract_prose_text(html), "foo bar baz")

    def test_parse_failure_falls_back_to_raw_html(self):
        html = "<p>foo</p>"
        with patch.object(dbe.HTMLParser, "feed", side_effect=RuntimeError("boom")):
            self.assertEqual(dbe._extract_prose_text(html), html)


# ---------------------------------------------------------------------------
# Guard B (exit 11)
# ---------------------------------------------------------------------------


class TestGuardB(unittest.TestCase):
    def test_heading_order_swapped(self):
        swapped = POSTGAME_NEW.replace("【試合結果】", "_TMP_")\
            .replace("【ハイライト】", "【試合結果】")\
            .replace("_TMP_", "【ハイライト】")
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=swapped)
            self.assertEqual(code, 11)
            self.assertIn("Guard B", stderr)

    def test_heading_text_altered(self):
        altered = POSTGAME_NEW.replace("【試合結果】", "【試合のポイント】")
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=altered)
            self.assertEqual(code, 11)
            self.assertIn("Guard B", stderr)

    def test_heading_added(self):
        added = POSTGAME_NEW + "\n【まとめ】\n本日の試合を総括しました。"
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=added)
            self.assertEqual(code, 11)
            self.assertIn("Guard B", stderr)

    def test_heading_removed(self):
        removed = POSTGAME_NEW.replace(
            "【試合展開】\n終盤は守備で締めました。",
            "",
        ).strip()
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=removed)
            self.assertEqual(code, 11)
            self.assertIn("Guard B", stderr)


# ---------------------------------------------------------------------------
# Guard C (exit 12)
# ---------------------------------------------------------------------------


class TestGuardC(unittest.TestCase):
    def test_output_too_long(self):
        padded = POSTGAME_NEW + ("\nおまけの文です。" * 80)
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=padded)
            self.assertEqual(code, 12)
            self.assertIn("Guard C", stderr)

    def test_output_too_short(self):
        # Keep headings intact so Guard B passes, but strip nearly all body.
        shrunk = "【試合結果】\n勝。\n【ハイライト】\n。\n【選手成績】\n。\n【試合展開】\n。"
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return=shrunk)
            self.assertEqual(code, 12)
            self.assertIn("Guard C", stderr)

    def test_block_open_comment_count_mismatch(self):
        current_with_blocks = (
            "<!-- wp:paragraph -->\n【試合結果】\n勝利。\n<!-- /wp:paragraph -->\n"
            "<!-- wp:paragraph -->\n【ハイライト】\n得点。\n<!-- /wp:paragraph -->\n"
            "<!-- wp:paragraph -->\n【選手成績】\n好調。\n<!-- /wp:paragraph -->\n"
            "<!-- wp:paragraph -->\n【試合展開】\n守備。\n<!-- /wp:paragraph -->"
        )
        new_missing_open = current_with_blocks.replace(
            "<!-- wp:paragraph -->\n【試合展開】",
            "【試合展開】",
            1,
        )
        with _tmp_workspace() as ws:
            argv = _make_argv(
                ws,
                subtype="postgame",
                current_body=current_with_blocks,
            )
            code, _, stderr = _run_main(argv, gemini_return=new_missing_open)
            self.assertEqual(code, 12)
            self.assertIn("block open comment", stderr)

    def test_block_close_comment_count_mismatch(self):
        current_with_blocks = (
            "<!-- wp:paragraph -->\n【試合結果】\n勝利。\n<!-- /wp:paragraph -->\n"
            "<!-- wp:paragraph -->\n【ハイライト】\n得点。\n<!-- /wp:paragraph -->\n"
            "<!-- wp:paragraph -->\n【選手成績】\n好調。\n<!-- /wp:paragraph -->\n"
            "<!-- wp:paragraph -->\n【試合展開】\n守備。\n<!-- /wp:paragraph -->"
        )
        new_missing_close = current_with_blocks.replace(
            "【試合展開】\n守備。\n<!-- /wp:paragraph -->",
            "【試合展開】\n守備。",
            1,
        )
        with _tmp_workspace() as ws:
            argv = _make_argv(
                ws,
                subtype="postgame",
                current_body=current_with_blocks,
            )
            code, _, stderr = _run_main(argv, gemini_return=new_missing_close)
            self.assertEqual(code, 12)
            self.assertIn("block close comment", stderr)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


class TestDryRun(unittest.TestCase):
    def test_dry_run_skips_out_write(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame", extra=["--dry-run"])
            out_path = argv[argv.index("--out") + 1]
            code, stdout, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 0, msg=stderr)
            self.assertFalse(
                os.path.exists(out_path),
                msg="dry-run must not create the --out file",
            )
            payload = json.loads(stdout.strip())
            self.assertTrue(payload["dry_run"])

    def test_non_dry_run_writes_out(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            out_path = argv[argv.index("--out") + 1]
            code, _, stderr = _run_main(argv, gemini_return=POSTGAME_NEW)
            self.assertEqual(code, 0, msg=stderr)
            self.assertTrue(os.path.exists(out_path))


# ---------------------------------------------------------------------------
# Gemini API error paths (exit 20)
# ---------------------------------------------------------------------------


class TestAPIErrors(unittest.TestCase):
    def test_gemini_raises_api_error(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(
                argv,
                gemini_side_effect=dbe.GeminiAPIError("boom"),
            )
            self.assertEqual(code, 20)
            self.assertIn("Gemini API failed", stderr)

    def test_gemini_returns_empty(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            code, _, stderr = _run_main(argv, gemini_return="   ")
            self.assertEqual(code, 20)
            self.assertIn("empty body", stderr)

    def test_missing_api_key(self):
        with _tmp_workspace() as ws:
            argv = _make_argv(ws, subtype="postgame")
            stdout = io.StringIO()
            stderr = io.StringIO()
            # Run without patching call_gemini: the missing key check
            # should fire before any API call.
            with patch("sys.stdout", stdout), patch("sys.stderr", stderr), \
                 patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False), \
                 patch("src.tools.draft_body_editor._load_dotenv_if_available"):
                code = dbe.main(list(argv))
            self.assertEqual(code, 20)
            self.assertIn("GEMINI_API_KEY", stderr.getvalue())


# ---------------------------------------------------------------------------
# call_gemini internals (retry / 4xx)
# ---------------------------------------------------------------------------


class TestCallGeminiInternals(unittest.TestCase):
    def test_timeout_retries_then_fails(self):
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch("src.tools.draft_body_editor.random.uniform", return_value=0.5), \
             patch("src.tools.draft_body_editor.time.sleep") as mock_sleep:
            mock_urlopen.side_effect = TimeoutError("slow")
            with self.assertRaises(dbe.GeminiAPIError):
                dbe.call_gemini("p", "k", timeout=1, retry=1)
            # retry=1 means 1 initial + 1 retry == 2 calls total.
            self.assertEqual(mock_urlopen.call_count, 2)
            mock_sleep.assert_called_once_with(1.5)

    def test_429_retry_after_retries_then_succeeds(self):
        http_err = urllib.error.HTTPError(
            url="https://example.invalid",
            code=429,
            msg="Too Many Requests",
            hdrs={"Retry-After": "7"},  # type: ignore[arg-type]
            fp=None,
        )
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch("src.tools.draft_body_editor.random.uniform") as mock_uniform, \
             patch("src.tools.draft_body_editor.time.sleep") as mock_sleep:
            mock_urlopen.side_effect = [http_err, _gemini_response("improved body")]

            text = dbe.call_gemini("p", "k", timeout=1, retry=1)

            self.assertEqual(text, "improved body")
            self.assertEqual(mock_urlopen.call_count, 2)
            mock_sleep.assert_called_once_with(7.0)
            mock_uniform.assert_not_called()

    def test_4xx_raises_without_retry(self):
        http_err = urllib.error.HTTPError(
            url="https://example.invalid",
            code=400,
            msg="Bad Request",
            hdrs={},  # type: ignore[arg-type]
            fp=None,
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = http_err
            with self.assertRaises(dbe.GeminiAPIError) as ctx:
                dbe.call_gemini("p", "k", timeout=1, retry=1)
            self.assertIn("HTTP 400", str(ctx.exception))
            self.assertEqual(mock_urlopen.call_count, 1)

    def test_5xx_retries_with_backoff_then_fails(self):
        http_err = urllib.error.HTTPError(
            url="https://example.invalid",
            code=503,
            msg="Unavailable",
            hdrs={},  # type: ignore[arg-type]
            fp=None,
        )
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch("src.tools.draft_body_editor.random.uniform", return_value=0.25), \
             patch("src.tools.draft_body_editor.time.sleep") as mock_sleep:
            mock_urlopen.side_effect = http_err
            with self.assertRaises(dbe.GeminiAPIError):
                dbe.call_gemini("p", "k", timeout=1, retry=2)
            self.assertEqual(mock_urlopen.call_count, 3)
            self.assertEqual(mock_sleep.call_args_list, [call(1.25), call(2.25)])


# ---------------------------------------------------------------------------
# Heading lookup (manager + farm come from separate constants)
# ---------------------------------------------------------------------------


class TestHeadingLookup(unittest.TestCase):
    def test_manager_uses_manager_required_headings(self):
        from src import rss_fetcher
        self.assertEqual(
            dbe._lookup_required_headings("manager"),
            tuple(rss_fetcher.MANAGER_REQUIRED_HEADINGS),
        )

    def test_farm_uses_farm_required_headings(self):
        from src import rss_fetcher
        self.assertEqual(
            dbe._lookup_required_headings("farm"),
            tuple(rss_fetcher.FARM_REQUIRED_HEADINGS["farm"]),
        )

    def test_pregame_uses_game_required_headings(self):
        from src import rss_fetcher
        self.assertEqual(
            dbe._lookup_required_headings("pregame"),
            tuple(rss_fetcher.GAME_REQUIRED_HEADINGS["pregame"]),
        )


if __name__ == "__main__":
    unittest.main()
