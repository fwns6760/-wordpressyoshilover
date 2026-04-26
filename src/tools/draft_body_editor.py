"""Draft body editor v1.

Side-lane CLI that asks Gemini 2.5 Flash to improve a WordPress draft body
along 1-2 quality axes, then enforces three hard guards (source grounding,
subtype heading invariance, scope invariance).

The script never calls the WordPress REST API. The caller (Claude Code) is
responsible for selecting drafts, assembling the source block, and executing
the PUT with the script's ``--out`` result.

Exit codes:
    0  -- all guards passed; new body written to --out
    10 -- Guard A (source grounding) failed
    11 -- Guard B (subtype heading invariance) failed
    12 -- Guard C (scope invariance) failed
    20 -- Gemini API failure
    30 -- input validation failure
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Sequence
from uuid import uuid4

from src import repair_provider_ledger


VALID_SUBTYPES = ("pregame", "postgame", "lineup", "manager", "farm")

VALID_FAIL_AXES = ("density", "title", "core", "time", "tone", "source")

FAIL_AXIS_JA = {
    "density": "情報密度",
    "title": "title-body 整合",
    "core": "1 記事 1 核",
    "time": "時系列",
    "tone": "AI tone",
    "source": "出典充足",
}

TEAM_NAMES = (
    "巨人", "読売", "ジャイアンツ",
    "阪神", "タイガース",
    "中日", "ドラゴンズ",
    "DeNA", "ベイスターズ",
    "ヤクルト", "スワローズ",
    "広島", "カープ",
    "ソフトバンク", "ホークス",
    "日本ハム", "ファイターズ",
    "ロッテ", "マリーンズ",
    "西武", "ライオンズ",
    "楽天", "イーグルス",
    "オリックス", "バファローズ",
)

BALLPARK_NAMES = (
    "東京ドーム",
    "横浜スタジアム",
    "神宮",
    "甲子園",
    "バンテリン",
    "京セラ",
    "PayPayドーム",
    "エスコンフィールド",
    "ZOZOマリン",
    "ベルーナドーム",
    "楽天モバイルパーク",
    "マツダスタジアム",
)

NUMERIC_PATTERNS = {
    "batting_avg": re.compile(r"(?<!\d)(?:\d+)?\.\d{3}"),
    "era": re.compile(r"(?<!\d)\d+\.\d{2}(?!\d)"),
    "score": re.compile(r"\d+[-−－]\d+"),
    "innings": re.compile(r"\d+回"),
    "pitch_count": re.compile(r"\d+球"),
    "hr_number": re.compile(r"\d+号"),
    "date_md": re.compile(r"\d+月\d+日"),
    "date_slash": re.compile(r"\d+/\d+"),
    "day_of_week": re.compile(r"[月火水木金土日]曜"),
}

HEADING_PATTERN = re.compile(r"【[^】]+】")

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.5-flash:generateContent?key={key}"
)
GEMINI_MAX_OUTPUT_TOKENS = 1400
GEMINI_TEMPERATURE = 0.2
GEMINI_TIMEOUT_SEC = 60
GEMINI_RETRY = 1

CURRENT_BODY_MAX_CHARS = 1200
CHAR_RATIO_MIN = 0.6
CHAR_RATIO_MAX = 1.4
_PROSE_SEPARATOR_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


class GeminiAPIError(RuntimeError):
    """Raised when the Gemini REST call cannot be completed."""


class _ProseTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_text_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style"}:
            self._skip_text_depth += 1
            return
        if normalized in _PROSE_SEPARATOR_TAGS:
            self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style"}:
            if self._skip_text_depth:
                self._skip_text_depth -= 1
            return
        if normalized in _PROSE_SEPARATOR_TAGS:
            self._chunks.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in _PROSE_SEPARATOR_TAGS:
            self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_text_depth:
            return
        self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def _extract_prose_text(body_html: str) -> str:
    body_html = body_html or ""
    if not body_html:
        return ""

    parser = _ProseTextExtractor()
    try:
        parser.feed(body_html)
        parser.close()
    except Exception:
        return body_html
    return re.sub(r"\s+", " ", parser.get_text()).strip()


def _lookup_required_headings(subtype: str) -> tuple[str, ...]:
    """Resolve the canonical heading tuple for a subtype.

    Delegates to the production constants in ``src.rss_fetcher`` so the
    editor always matches whatever the main pipeline enforces.
    """
    from src import rss_fetcher

    game_map = getattr(rss_fetcher, "GAME_REQUIRED_HEADINGS", {})
    if subtype in game_map:
        return tuple(game_map[subtype])
    if subtype == "manager":
        return tuple(getattr(rss_fetcher, "MANAGER_REQUIRED_HEADINGS", ()))
    if subtype == "farm":
        farm_map = getattr(rss_fetcher, "FARM_REQUIRED_HEADINGS", {})
        if "farm" in farm_map:
            return tuple(farm_map["farm"])
    raise ValueError(f"no required headings registered for subtype={subtype!r}")


def build_prompt(
    subtype: str,
    fail_axes: Sequence[str],
    current_body: str,
    source_block: str,
    headings: Sequence[str],
) -> str:
    fail_ja = "、".join(FAIL_AXIS_JA[axis] for axis in fail_axes)
    heading_list = "\n".join(headings)
    return (
        "あなたは野球メディア「ヨシラバー」の編集アシスタントです。\n"
        "タスクは下書き本文の改善のみです。新しい事実を書き足してはいけません。\n"
        "\n"
        "入力:\n"
        f"- subtype: {subtype}\n"
        "- 現本文:\n"
        f"{current_body}\n"
        "- 出典資料（この中にある事実のみ使ってよい）:\n"
        f"{source_block}\n"
        f"- 改善すべき点（最大2つ）: {fail_ja}\n"
        "\n"
        "厳守ルール:\n"
        f"1. subtype = {subtype} の見出し構成は以下の順序・文言で必ず維持する"
        "（追加・削除・順序変更・文言変更禁止）:\n"
        f"{heading_list}\n"
        "2. 出典資料と現本文に書かれていない固有名詞・数値・日付・選手名・発言を一切追加しない。\n"
        "3. title / カテゴリ / タグに触れる記述を書かない。\n"
        "4. 文字数は現本文の 0.7〜1.3 倍に収める。\n"
        "5. ブロックコメント `<!-- wp:... -->` はそのまま残す。\n"
        "6. 直接話法（「...」付き発言）は出典に一字一句あるものだけ残す。"
        "改変・要約は地の文にする。\n"
        f"7. 改善は {fail_ja} に集中し、それ以外の書き換えは最小にする。\n"
        "8. 出力は改善後の本文のみ。前置き・後書き・説明・コードブロックは書かない。\n"
        "\n"
        "出力: 改善後の本文"
    )


def _parse_retry_after_seconds(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return max(float(int(text)), 0.0)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        return None
    return max(retry_at.timestamp() - time.time(), 0.0)


def _compute_retry_sleep(attempt: int, max_delay: int) -> float:
    return min((2 ** attempt) + random.uniform(0, 1), max_delay)


def call_gemini(
    prompt: str,
    api_key: str,
    *,
    timeout: int = GEMINI_TIMEOUT_SEC,
    retry: int = GEMINI_RETRY,
) -> str:
    """Call Gemini 2.5 Flash via the REST API and return the text response."""
    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
                "temperature": GEMINI_TEMPERATURE,
            },
        }
    ).encode("utf-8")
    url = GEMINI_URL_TEMPLATE.format(key=api_key)

    last_err: Exception | None = None
    attempts = retry + 1
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as res:
                data = json.load(res)
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                raise GeminiAPIError(f"HTTP {e.code}") from e
            last_err = e
            if attempt >= retry:
                break
            headers = getattr(e, "headers", None) or getattr(e, "hdrs", None)
            retry_after = _parse_retry_after_seconds(
                headers.get("Retry-After") if headers else None
            )
            time.sleep(
                retry_after
                if retry_after is not None
                else _compute_retry_sleep(attempt, 60)
            )
            continue
        except (urllib.error.URLError, TimeoutError, socket.timeout) as e:
            last_err = e
            if attempt >= retry:
                break
            time.sleep(_compute_retry_sleep(attempt, 60))
            continue

        try:
            parts = data["candidates"][0]["content"].get("parts", [])
        except (KeyError, IndexError, TypeError) as e:
            raise GeminiAPIError(f"response parse error: {e}") from e

        text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
        return text

    raise GeminiAPIError(f"all {attempts} attempts failed: {last_err!r}")


def guard_a_source_grounding(
    new_body: str,
    current_body: str,
    source_block: str,
) -> list[str]:
    """Reject tokens that appear in new_body but neither in current_body nor source_block."""
    violations: list[str] = []
    allowed = current_body + "\n" + source_block

    for team in TEAM_NAMES:
        if team in new_body and team not in allowed:
            violations.append(f"team name not in source: {team}")

    for park in BALLPARK_NAMES:
        if park in new_body and park not in allowed:
            violations.append(f"ballpark not in source: {park}")

    for label, pattern in NUMERIC_PATTERNS.items():
        for match in pattern.finditer(new_body):
            token = match.group(0)
            if token not in allowed:
                violations.append(f"{label} literal not in source: {token}")

    return violations


def guard_b_heading_invariant(
    new_body: str,
    expected_headings: Sequence[str],
) -> list[str]:
    found = tuple(HEADING_PATTERN.findall(new_body))
    expected = tuple(expected_headings)
    if found != expected:
        return [
            "heading sequence mismatch: "
            f"expected={list(expected)} got={list(found)}"
        ]
    return []


def guard_c_scope_invariant(new_body: str, current_body: str) -> list[str]:
    violations: list[str] = []
    if len(current_body) == 0:
        return ["current_body is empty; cannot evaluate scope"]
    ratio = len(new_body) / len(current_body)
    if ratio < CHAR_RATIO_MIN or ratio > CHAR_RATIO_MAX:
        violations.append(
            f"char ratio out of range [{CHAR_RATIO_MIN}, {CHAR_RATIO_MAX}]: {ratio:.3f}"
        )
    if new_body.count("<!-- wp:") != current_body.count("<!-- wp:"):
        violations.append(
            "block open comment count mismatch: "
            f"current={current_body.count('<!-- wp:')} new={new_body.count('<!-- wp:')}"
        )
    if new_body.count("<!-- /wp:") != current_body.count("<!-- /wp:"):
        violations.append(
            "block close comment count mismatch: "
            f"current={current_body.count('<!-- /wp:')} new={new_body.count('<!-- /wp:')}"
        )
    return violations


def _emit_violations(prefix: str, violations: Iterable[str]) -> None:
    for v in violations:
        print(f"[{prefix}] {v}", file=sys.stderr)


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv()


def _path_to_file_uri(path: str) -> str:
    return Path(path).resolve().as_uri()


def _emit_repair_provider_ledger(
    *,
    post_id: int,
    subtype: str,
    fail_axes: Sequence[str],
    dry_run: bool,
    current_body: str,
    source_block: str,
    out_path: str,
    new_body: str,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    hard_stop_flags_resolved: bool,
    no_new_forbidden_claim: bool,
    quality_flags: Sequence[str] = (),
    error_code: str | None = None,
) -> None:
    body_len_before = len(current_body)
    body_len_after = len(new_body)
    body_len_delta_pct = repair_provider_ledger.compute_body_len_delta_pct(
        body_len_before,
        body_len_after,
    )
    input_hash = repair_provider_ledger.compute_input_hash(
        {
            "post_id": post_id,
            "subtype": subtype,
            "fail_axes": list(fail_axes),
            "dry_run": dry_run,
            "current_body": current_body,
            "source_block": source_block,
        }
    )
    entry = repair_provider_ledger.RepairLedgerEntry(
        schema_version=repair_provider_ledger.SCHEMA_VERSION,
        run_id=str(uuid4()),
        lane="repair",
        provider="gemini",
        model="gemini-2.5-flash",
        source_post_id=post_id,
        input_hash=input_hash,
        output_hash=repair_provider_ledger.compute_output_hash(new_body),
        artifact_uri=_path_to_file_uri(out_path),
        status=status,
        strict_pass=False,
        error_code=error_code,
        idempotency_key=repair_provider_ledger.make_idempotency_key(
            post_id,
            input_hash,
            "gemini",
        ),
        created_at=finished_at.isoformat(),
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        metrics={
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_ms": max(int((finished_at - started_at).total_seconds() * 1000), 0),
            "body_len_before": body_len_before,
            "body_len_after": body_len_after,
            "body_len_delta_pct": body_len_delta_pct,
        },
        provider_meta={
            "raw_response_size": len(new_body.encode("utf-8")),
            "fallback_from": None,
            "fallback_reason": None,
            "quality_flags": list(quality_flags),
        },
    )
    entry.strict_pass = repair_provider_ledger.judge_strict_pass(
        entry,
        hard_stop_flags_resolved=hard_stop_flags_resolved,
        fact_check_pass=True,
        no_new_forbidden=no_new_forbidden_claim,
        body_len_delta_pct=body_len_delta_pct,
    )
    writer = repair_provider_ledger.JsonlLedgerWriter(
        repair_provider_ledger.resolve_jsonl_ledger_path(now=finished_at)
    )
    try:
        writer.write(entry)
    except (
        repair_provider_ledger.LedgerLockError,
        repair_provider_ledger.LedgerWriteError,
        ValueError,
        OSError,
    ) as exc:
        print(f"[ledger] repair_provider_ledger emit failed: {exc}", file=sys.stderr)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="draft_body_editor",
        description="Improve a WordPress draft body via Gemini 2.5 Flash (guards only; no WP PUT).",
    )
    parser.add_argument("--post-id", type=int, required=True, help="WordPress post id (for logging)")
    parser.add_argument(
        "--subtype",
        required=True,
        help=f"Article subtype ({'|'.join(VALID_SUBTYPES)})",
    )
    parser.add_argument(
        "--fail",
        required=True,
        help=f"Comma-separated fail axes (1-2 of: {','.join(VALID_FAIL_AXES)})",
    )
    parser.add_argument("--current-body", required=True, help="Path to current draft body text")
    parser.add_argument("--source-block", required=True, help="Path to source block assembled by Claude")
    parser.add_argument("--out", required=True, help="Destination path for the improved body")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run guards but do not write the output file",
    )
    return parser.parse_args(argv)


def _validate_inputs(args: argparse.Namespace) -> tuple[list[str], str, str] | None:
    """Return (fail_axes, current_body, source_block) on success, or None and print errors."""
    if args.subtype not in VALID_SUBTYPES:
        print(
            f"invalid subtype: {args.subtype!r} (must be one of {VALID_SUBTYPES})",
            file=sys.stderr,
        )
        return None

    fail_axes = [s.strip() for s in args.fail.split(",") if s.strip()]
    if not 1 <= len(fail_axes) <= 2:
        print(
            f"--fail must contain 1 or 2 axes; got {len(fail_axes)} ({fail_axes!r})",
            file=sys.stderr,
        )
        return None
    for axis in fail_axes:
        if axis not in VALID_FAIL_AXES:
            print(
                f"invalid fail axis: {axis!r} (must be one of {VALID_FAIL_AXES})",
                file=sys.stderr,
            )
            return None

    try:
        with open(args.current_body, encoding="utf-8") as f:
            current_body = f.read()
        with open(args.source_block, encoding="utf-8") as f:
            source_block = f.read()
    except OSError as e:
        print(f"failed to read input files: {e}", file=sys.stderr)
        return None

    if not current_body.strip():
        print("current_body is empty", file=sys.stderr)
        return None
    prose_body = _extract_prose_text(current_body)
    if len(prose_body) > CURRENT_BODY_MAX_CHARS:
        print(
            f"current_body exceeds {CURRENT_BODY_MAX_CHARS} prose chars (got {len(prose_body)})",
            file=sys.stderr,
        )
        return None
    if not source_block.strip():
        print("source_block is empty", file=sys.stderr)
        return None

    return fail_axes, current_body, source_block


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    validated = _validate_inputs(args)
    if validated is None:
        return 30
    fail_axes, current_body, source_block = validated

    try:
        headings = _lookup_required_headings(args.subtype)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 30

    _load_dotenv_if_available()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("GEMINI_API_KEY is not set", file=sys.stderr)
        return 20

    prompt = build_prompt(args.subtype, fail_axes, current_body, source_block, headings)
    started_at = repair_provider_ledger._now_jst()

    try:
        new_body = call_gemini(prompt, api_key)
    except GeminiAPIError as e:
        _emit_repair_provider_ledger(
            post_id=args.post_id,
            subtype=args.subtype,
            fail_axes=fail_axes,
            dry_run=bool(args.dry_run),
            current_body=current_body,
            source_block=source_block,
            out_path=args.out,
            new_body="",
            status="failed",
            started_at=started_at,
            finished_at=repair_provider_ledger._now_jst(),
            hard_stop_flags_resolved=False,
            no_new_forbidden_claim=False,
            quality_flags=["gemini_api_error"],
            error_code="gemini_api_error",
        )
        print(f"Gemini API failed: {e}", file=sys.stderr)
        return 20

    if not new_body.strip():
        _emit_repair_provider_ledger(
            post_id=args.post_id,
            subtype=args.subtype,
            fail_axes=fail_axes,
            dry_run=bool(args.dry_run),
            current_body=current_body,
            source_block=source_block,
            out_path=args.out,
            new_body=new_body,
            status="failed",
            started_at=started_at,
            finished_at=repair_provider_ledger._now_jst(),
            hard_stop_flags_resolved=False,
            no_new_forbidden_claim=False,
            quality_flags=["empty_body"],
            error_code="gemini_empty_body",
        )
        print("Gemini returned empty body", file=sys.stderr)
        return 20

    violations_a = guard_a_source_grounding(new_body, current_body, source_block)
    violations_b = guard_b_heading_invariant(new_body, headings)
    violations_c = guard_c_scope_invariant(new_body, current_body)
    quality_flags: list[str] = []
    if violations_a:
        quality_flags.append("guard_a_source_grounding")
    if violations_b:
        quality_flags.append("guard_b_heading_invariant")
    if violations_c:
        quality_flags.append("guard_c_scope_invariant")

    if violations_a:
        _emit_repair_provider_ledger(
            post_id=args.post_id,
            subtype=args.subtype,
            fail_axes=fail_axes,
            dry_run=bool(args.dry_run),
            current_body=current_body,
            source_block=source_block,
            out_path=args.out,
            new_body=new_body,
            status="failed",
            started_at=started_at,
            finished_at=repair_provider_ledger._now_jst(),
            hard_stop_flags_resolved=not (violations_b or violations_c),
            no_new_forbidden_claim=False,
            quality_flags=quality_flags,
            error_code="guard_a_source_grounding",
        )
        _emit_violations("Guard A", violations_a)
        return 10

    if violations_b:
        _emit_repair_provider_ledger(
            post_id=args.post_id,
            subtype=args.subtype,
            fail_axes=fail_axes,
            dry_run=bool(args.dry_run),
            current_body=current_body,
            source_block=source_block,
            out_path=args.out,
            new_body=new_body,
            status="failed",
            started_at=started_at,
            finished_at=repair_provider_ledger._now_jst(),
            hard_stop_flags_resolved=False,
            no_new_forbidden_claim=True,
            quality_flags=quality_flags,
            error_code="guard_b_heading_invariant",
        )
        _emit_violations("Guard B", violations_b)
        return 11

    if violations_c:
        _emit_repair_provider_ledger(
            post_id=args.post_id,
            subtype=args.subtype,
            fail_axes=fail_axes,
            dry_run=bool(args.dry_run),
            current_body=current_body,
            source_block=source_block,
            out_path=args.out,
            new_body=new_body,
            status="failed",
            started_at=started_at,
            finished_at=repair_provider_ledger._now_jst(),
            hard_stop_flags_resolved=False,
            no_new_forbidden_claim=True,
            quality_flags=quality_flags,
            error_code="guard_c_scope_invariant",
        )
        _emit_violations("Guard C", violations_c)
        return 12

    if args.dry_run:
        _emit_repair_provider_ledger(
            post_id=args.post_id,
            subtype=args.subtype,
            fail_axes=fail_axes,
            dry_run=bool(args.dry_run),
            current_body=current_body,
            source_block=source_block,
            out_path=args.out,
            new_body=new_body,
            status="shadow_only",
            started_at=started_at,
            finished_at=repair_provider_ledger._now_jst(),
            hard_stop_flags_resolved=True,
            no_new_forbidden_claim=True,
        )
        print("[dry-run] guards passed; --out not written", file=sys.stderr)
    else:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(new_body)
        except OSError as e:
            _emit_repair_provider_ledger(
                post_id=args.post_id,
                subtype=args.subtype,
                fail_axes=fail_axes,
                dry_run=bool(args.dry_run),
                current_body=current_body,
                source_block=source_block,
                out_path=args.out,
                new_body=new_body,
                status="failed",
                started_at=started_at,
                finished_at=repair_provider_ledger._now_jst(),
                hard_stop_flags_resolved=False,
                no_new_forbidden_claim=True,
                quality_flags=["write_output_failed"],
                error_code="write_output_failed",
            )
            print(f"failed to write --out: {e}", file=sys.stderr)
            return 30
        _emit_repair_provider_ledger(
            post_id=args.post_id,
            subtype=args.subtype,
            fail_axes=fail_axes,
            dry_run=bool(args.dry_run),
            current_body=current_body,
            source_block=source_block,
            out_path=args.out,
            new_body=new_body,
            status="success",
            started_at=started_at,
            finished_at=repair_provider_ledger._now_jst(),
            hard_stop_flags_resolved=True,
            no_new_forbidden_claim=True,
        )

    result = {
        "post_id": args.post_id,
        "subtype": args.subtype,
        "fail": fail_axes,
        "chars_before": len(current_body),
        "chars_after": len(new_body),
        "guards": "pass",
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
