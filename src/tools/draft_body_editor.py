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
    13 -- post-check numeric fact consistency failed
    20 -- Gemini API failure
    30 -- input validation failure
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import inspect
import json
import logging
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
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from src import llm_call_dedupe
from src import llm_cost_emitter
from src import repair_provider_ledger


ROOT = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger("draft_body_editor")
PUBLISH_NOTICE_QUEUE_PATH = ROOT / "logs" / "publish_notice_queue.jsonl"
INGEST_VISIBILITY_FIX_V1_ENV = "ENABLE_INGEST_VISIBILITY_FIX_V1"
_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
_REPAIR_SKIP_RECORD_TYPE = "repair_skip"
_REPAIR_SKIP_LAYER = "repair_lane"
_REPAIR_SKIP_SUBJECT_PREFIX = "【要review｜repair_skip】"


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
SOURCE_SCORE_PATTERN = re.compile(r"(?<!\d)\d{1,2}[-−－]\d{1,2}(?!\d)")
SOURCE_DATE_YMD_PATTERN = re.compile(r"(?<!\d)\d{4}年\d{1,2}月\d{1,2}日")
SOURCE_PLAYER_ROLE_PATTERN = re.compile(
    r"(?P<name>[一-龯々]{2,6}(?:[ぁ-んァ-ヴー]{0,4})?)"
    r"(?=(?:投手|捕手|内野手|外野手|選手|監督|コーチ))"
)
SOURCE_PITCHER_STAT_PATTERN = re.compile(
    r"[^\n。]*"
    r"(?:\d+回\s*\d+(?:安打|被安打)\s*\d+失点|\d+被?安打(?:\s*\d+失点)?)"
    r"[^\n。]*"
)
SOURCE_PLAYER_STOPWORDS = frozenset(
    {
        *TEAM_NAMES,
        "投手",
        "捕手",
        "内野手",
        "外野手",
        "選手",
        "監督",
        "コーチ",
        "試合",
        "打線",
        "チーム",
        "東京ドーム",
        "スポーツ報知",
        "日刊スポーツ",
        "スポニチ",
    }
)

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


@dataclass(frozen=True)
class _PostCheckReport:
    severity: str
    flags: tuple[str, ...]
    details: dict[str, Any]


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


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _format_fact_values(values: Iterable[str], *, limit: int = 6) -> str:
    deduped = _dedupe_preserve_order(values)
    if not deduped:
        return "<none>"
    display = deduped[:limit]
    if len(deduped) > limit:
        display.append(f"... (+{len(deduped) - limit} more)")
    return ", ".join(display)


def _extract_source_player_names(source_block: str) -> list[str]:
    names = [
        match.group("name")
        for match in SOURCE_PLAYER_ROLE_PATTERN.finditer(source_block or "")
    ]
    return [
        name for name in _dedupe_preserve_order(names)
        if name not in SOURCE_PLAYER_STOPWORDS
    ]


def _extract_source_pitcher_stats(source_block: str) -> list[str]:
    snippets = []
    for match in SOURCE_PITCHER_STAT_PATTERN.finditer(source_block or ""):
        snippet = re.sub(r"\s+", " ", match.group(0)).strip(" ・\n\t")
        if snippet:
            snippets.append(snippet)
    return _dedupe_preserve_order(snippets)


def _build_source_anchor_facts_block(source_block: str) -> str:
    source_text = source_block or ""
    score_literals = _dedupe_preserve_order(
        match.group(0) for match in SOURCE_SCORE_PATTERN.finditer(source_text)
    )
    date_literals = _dedupe_preserve_order(
        [match.group(0) for match in SOURCE_DATE_YMD_PATTERN.finditer(source_text)]
        + [match.group(0) for match in NUMERIC_PATTERNS["date_md"].finditer(source_text)]
        + [match.group(0) for match in NUMERIC_PATTERNS["date_slash"].finditer(source_text)]
    )
    player_names = _extract_source_player_names(source_text)
    pitcher_stats = _extract_source_pitcher_stats(source_text)
    return "\n".join(
        (
            "[FACTS]",
            "- source/meta 固定ルール: 以下の値は改変しない。以下にない値は新規作成しない。",
            f"- score_literals: {_format_fact_values(score_literals)}",
            f"- player_name_candidates: {_format_fact_values(player_names)}",
            f"- pitcher_stat_snippets: {_format_fact_values(pitcher_stats)}",
            f"- date_literals: {_format_fact_values(date_literals)}",
            "[/FACTS]",
        )
    )


def _post_check_repaired_body(
    source_text: str,
    new_body: str,
    metadata: Mapping[str, object] | None,
    publish_time_iso: str | None,
) -> _PostCheckReport:
    from src.baseball_numeric_fact_consistency import check_consistency

    metadata = dict(metadata or {})
    subtype = str(metadata.get("subtype") or metadata.get("article_subtype") or "")
    call_kwargs: dict[str, object] = {
        "source_text": source_text,
        "generated_body": new_body,
        "x_candidates": (),
        "metadata": metadata,
        "publish_time_iso": str(publish_time_iso or ""),
    }
    if "subtype" in inspect.signature(check_consistency).parameters:
        call_kwargs["subtype"] = subtype
    raw_report = check_consistency(**call_kwargs)
    if isinstance(raw_report, _PostCheckReport):
        return raw_report

    severity = str(getattr(raw_report, "severity", "pass") or "pass")
    hard_stop_flags = tuple(str(flag) for flag in (getattr(raw_report, "hard_stop_flags", ()) or ()))
    review_flags = tuple(str(flag) for flag in (getattr(raw_report, "review_flags", ()) or ()))
    x_candidate_suppress_flags = tuple(
        str(flag) for flag in (getattr(raw_report, "x_candidate_suppress_flags", ()) or ())
    )
    flags = tuple(str(flag) for flag in (getattr(raw_report, "flags", ()) or ()))
    if not flags:
        if severity in {"hard_stop", "mismatch"}:
            flags = hard_stop_flags
        elif severity == "review":
            flags = review_flags
        elif severity == "x_candidate_suppress":
            flags = x_candidate_suppress_flags
    return _PostCheckReport(
        severity=severity,
        flags=flags,
        details={
            "hard_stop_flags": hard_stop_flags,
            "review_flags": review_flags,
            "x_candidate_suppress_flags": x_candidate_suppress_flags,
        },
    )


def build_prompt(
    subtype: str,
    fail_axes: Sequence[str],
    current_body: str,
    source_block: str,
    headings: Sequence[str],
) -> str:
    fail_ja = "、".join(FAIL_AXIS_JA[axis] for axis in fail_axes)
    heading_list = "\n".join(headings)
    facts_block = _build_source_anchor_facts_block(source_block)
    return (
        "あなたは野球メディア「ヨシラバー」の編集アシスタントです。\n"
        "source/meta にある数字・選手名・スコア・日付は絶対に改変しない。\n"
        "source/meta にない数字・選手名・スコア・日付は新たに作らない。\n"
        "以下の [FACTS] を固定値として扱い、本文修正はこの範囲から逸脱しないこと。\n"
        f"{facts_block}\n"
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
    post_id: int | None = None,
    content_hash: str | None = None,
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
    input_chars = len(prompt)
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
            llm_cost_emitter.emit_llm_cost(
                lane="draft_body_editor",
                call_site="draft_body_editor.call_gemini",
                post_id=post_id,
                source_url=None,
                content_hash=content_hash,
                model="gemini-2.5-flash",
                input_chars=input_chars,
                output_chars=0,
                token_in=None,
                token_out=None,
                cache_hit=False,
                skip_reason=None,
                success=False,
                error_class=type(e).__name__,
            )
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
            llm_cost_emitter.emit_llm_cost(
                lane="draft_body_editor",
                call_site="draft_body_editor.call_gemini",
                post_id=post_id,
                source_url=None,
                content_hash=content_hash,
                model="gemini-2.5-flash",
                input_chars=input_chars,
                output_chars=0,
                token_in=None,
                token_out=None,
                cache_hit=False,
                skip_reason=None,
                success=False,
                error_class=type(e).__name__,
            )
            last_err = e
            if attempt >= retry:
                break
            time.sleep(_compute_retry_sleep(attempt, 60))
            continue

        try:
            parts = data["candidates"][0]["content"].get("parts", [])
        except (KeyError, IndexError, TypeError) as e:
            token_in, token_out = llm_cost_emitter.extract_usage_metadata(data)
            llm_cost_emitter.emit_llm_cost(
                lane="draft_body_editor",
                call_site="draft_body_editor.call_gemini",
                post_id=post_id,
                source_url=None,
                content_hash=content_hash,
                model="gemini-2.5-flash",
                input_chars=input_chars,
                output_chars=0,
                token_in=token_in,
                token_out=token_out,
                cache_hit=False,
                skip_reason=None,
                success=False,
                error_class="GeminiAPIError",
            )
            raise GeminiAPIError(f"response parse error: {e}") from e

        text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
        token_in, token_out = llm_cost_emitter.extract_usage_metadata(data)
        llm_cost_emitter.emit_llm_cost(
            lane="draft_body_editor",
            call_site="draft_body_editor.call_gemini",
            post_id=post_id,
            source_url=None,
            content_hash=content_hash,
            model="gemini-2.5-flash",
            input_chars=input_chars,
            output_chars=len(text),
            token_in=token_in,
            token_out=token_out,
            cache_hit=False,
            skip_reason=None,
            success=True,
            error_class=None,
        )
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


def _emit_llm_event(event: str, **payload: object) -> None:
    print(
        json.dumps({"event": event, **payload}, ensure_ascii=False, default=str),
        file=sys.stderr,
    )


def _ingest_visibility_fix_v1_enabled() -> bool:
    return str(os.getenv(INGEST_VISIBILITY_FIX_V1_ENV, "")).strip().lower() in _TRUTHY_ENV_VALUES


def _repair_skip_candidate_id(
    *,
    post_id: int | str | None,
    skip_reason: str,
    content_hash: str | None = None,
) -> str:
    normalized_reason = str(skip_reason or "").strip() or "unknown_skip"
    post_id_text = str(post_id).strip() if post_id is not None else ""
    if post_id_text:
        parts = [_REPAIR_SKIP_RECORD_TYPE, post_id_text, normalized_reason]
        if str(content_hash or "").strip():
            parts.append(str(content_hash).strip())
        return ":".join(parts)
    return f"{_REPAIR_SKIP_RECORD_TYPE}:global:{normalized_reason}"


def _repair_skip_subject(skip_reason: str, post_id: int | str | None) -> str:
    normalized_reason = str(skip_reason or "").strip() or "unknown_skip"
    post_id_text = str(post_id).strip() if post_id is not None else ""
    return (
        f"{_REPAIR_SKIP_SUBJECT_PREFIX}"
        f"{normalized_reason} post_id={post_id_text or 'global'} | YOSHILOVER"
    )


def emit_ingest_visibility_fix_v1(
    *,
    skip_reason: str,
    source_path: str,
    post_id: int | str | None = None,
    content_hash: str | None = None,
    provider: str | None = None,
    queue_path: str | Path | None = None,
    candidate_id: str | None = None,
) -> dict[str, object] | None:
    if not _ingest_visibility_fix_v1_enabled():
        return None

    normalized_reason = str(skip_reason or "").strip() or "unknown_skip"
    resolved_candidate_id = str(candidate_id or "").strip() or _repair_skip_candidate_id(
        post_id=post_id,
        skip_reason=normalized_reason,
        content_hash=content_hash,
    )
    recorded_at_iso = repair_provider_ledger._now_jst().isoformat()
    queue_target = Path(queue_path) if queue_path is not None else PUBLISH_NOTICE_QUEUE_PATH
    payload: dict[str, object] = {
        "path": str(source_path),
        "reason": normalized_reason,
        "candidate_id": resolved_candidate_id,
        "record_type": _REPAIR_SKIP_RECORD_TYPE,
        "skip_layer": _REPAIR_SKIP_LAYER,
    }
    if post_id is not None:
        payload["source_post_id"] = post_id
    if str(content_hash or "").strip():
        payload["content_hash"] = str(content_hash).strip()
    if str(provider or "").strip():
        payload["provider"] = str(provider).strip()

    extra_payload = {
        "notice_kind": "post_gen_validate",
        "record_type": _REPAIR_SKIP_RECORD_TYPE,
        "skip_layer": _REPAIR_SKIP_LAYER,
        "candidate_id": resolved_candidate_id,
        "source_path": str(source_path),
        "source_post_id": post_id,
        "content_hash": str(content_hash).strip() if str(content_hash or "").strip() else None,
        "provider": str(provider).strip() if str(provider or "").strip() else None,
    }
    try:
        from src import publish_notice_scanner

        publish_notice_scanner._append_queue_log(
            queue_target,
            status="queued",
            reason=normalized_reason,
            subject=_repair_skip_subject(normalized_reason, post_id),
            recipients=[],
            post_id=resolved_candidate_id,
            recorded_at_iso=recorded_at_iso,
            extra_payload={key: value for key, value in extra_payload.items() if value is not None},
        )
    except Exception as exc:
        LOGGER.warning(
            "ingest_visibility_fix_v1 queue append failed: path=%s reason=%s candidate_id=%s error=%s",
            source_path,
            normalized_reason,
            resolved_candidate_id,
            exc,
        )
        return None

    _emit_llm_event("ingest_visibility_fix_v1_emit", **payload)
    return payload


def _dedupe_record_extra(payload: dict[str, object]) -> dict[str, object]:
    return {
        "provider": payload.get("provider"),
        "model": payload.get("model"),
        "body_text": payload.get("body_text"),
        "error_code": payload.get("error_code"),
        "dry_run": payload.get("dry_run"),
        "token_in": payload.get("token_in"),
        "token_out": payload.get("token_out"),
        "cost": payload.get("cost"),
        "fallback_used": payload.get("fallback_used"),
        "wp_write_allowed": payload.get("wp_write_allowed"),
        "failure_chain": payload.get("failure_chain"),
        "reused_from_timestamp": payload.get("timestamp"),
    }


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

    prompt = build_prompt(args.subtype, fail_axes, current_body, source_block, headings)
    started_at = repair_provider_ledger._now_jst()
    content_hash = llm_call_dedupe.compute_content_hash(args.post_id, current_body)
    llm_skip_reason: str | None = None
    quality_flags: list[str] = []
    dedupe_record = llm_call_dedupe.find_recent_record(
        args.post_id,
        content_hash,
        llm_call_dedupe.DEFAULT_LEDGER_PATH,
        now=started_at,
    )

    if dedupe_record is not None:
        llm_skip_reason = "content_hash_dedupe"
        quality_flags.append(llm_skip_reason)
        llm_call_dedupe.record_call(
            args.post_id,
            content_hash,
            str(dedupe_record.get("result") or "generated"),
            llm_skip_reason,
            ledger_path=llm_call_dedupe.DEFAULT_LEDGER_PATH,
            now=started_at,
            **_dedupe_record_extra(dedupe_record),
        )
        _emit_llm_event(
            "llm_skip",
            post_id=args.post_id,
            content_hash=content_hash,
            skip_reason=llm_skip_reason,
            result=dedupe_record.get("result"),
            provider=dedupe_record.get("provider"),
            model=dedupe_record.get("model"),
        )
        llm_cost_emitter.emit_llm_cost(
            lane="draft_body_editor",
            call_site="draft_body_editor.dedupe_skip",
            post_id=args.post_id,
            source_url=None,
            content_hash=content_hash,
            model="gemini-2.5-flash",
            input_chars=len(current_body or ""),
            output_chars=0,
            token_in=0,
            token_out=0,
            cache_hit=True,
            skip_reason=llm_skip_reason,
            success=True,
            error_class=None,
        )
        new_body = str(dedupe_record.get("body_text") or "")
        if not new_body:
            error_code = str(dedupe_record.get("error_code") or "content_hash_dedupe")
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
                quality_flags=quality_flags + [error_code],
                error_code=error_code,
            )
            emit_ingest_visibility_fix_v1(
                skip_reason=llm_skip_reason,
                source_path="src/tools/draft_body_editor.py",
                post_id=args.post_id,
                content_hash=content_hash,
                provider=str(dedupe_record.get("provider") or "gemini"),
            )
            print(
                f"Gemini API skipped: {llm_skip_reason} previous_error={error_code}",
                file=sys.stderr,
            )
            return 20
    else:
        _load_dotenv_if_available()
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            print("GEMINI_API_KEY is not set", file=sys.stderr)
            return 20

        try:
            new_body = call_gemini(
                prompt,
                api_key,
                post_id=args.post_id,
                content_hash=content_hash,
            )
        except GeminiAPIError as e:
            llm_call_dedupe.record_call(
                args.post_id,
                content_hash,
                "failed",
                ledger_path=llm_call_dedupe.DEFAULT_LEDGER_PATH,
                now=started_at,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                dry_run=bool(args.dry_run),
                error_code="gemini_api_error",
                token_in=None,
                token_out=None,
                cost=None,
            )
            _emit_llm_event(
                "llm_call",
                post_id=args.post_id,
                content_hash=content_hash,
                provider="gemini",
                model="gemini-2.5-flash",
                result="failed",
                error_code="gemini_api_error",
            )
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
            llm_call_dedupe.record_call(
                args.post_id,
                content_hash,
                "failed",
                ledger_path=llm_call_dedupe.DEFAULT_LEDGER_PATH,
                now=started_at,
                provider="gemini",
                model="gemini-2.5-flash",
                body_text="",
                dry_run=bool(args.dry_run),
                error_code="gemini_empty_body",
                token_in=None,
                token_out=None,
                cost=None,
            )
            _emit_llm_event(
                "llm_call",
                post_id=args.post_id,
                content_hash=content_hash,
                provider="gemini",
                model="gemini-2.5-flash",
                result="failed",
                error_code="gemini_empty_body",
            )
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

        llm_call_dedupe.record_call(
            args.post_id,
            content_hash,
            "generated",
            ledger_path=llm_call_dedupe.DEFAULT_LEDGER_PATH,
            now=started_at,
            provider="gemini",
            model="gemini-2.5-flash",
            body_text=new_body,
            dry_run=bool(args.dry_run),
            error_code=None,
            token_in=None,
            token_out=None,
            cost=None,
        )
        _emit_llm_event(
            "llm_call",
            post_id=args.post_id,
            content_hash=content_hash,
            provider="gemini",
            model="gemini-2.5-flash",
            result="generated",
        )

    violations_a = guard_a_source_grounding(new_body, current_body, source_block)
    violations_b = guard_b_heading_invariant(new_body, headings)
    violations_c = guard_c_scope_invariant(new_body, current_body)
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

    post_check_report = _post_check_repaired_body(
        source_text=source_block,
        new_body=new_body,
        metadata={
            "post_id": args.post_id,
            "subtype": args.subtype,
            "fail_axes": tuple(fail_axes),
        },
        publish_time_iso=None,
    )
    if post_check_report.severity != "pass":
        post_check_flags = list(post_check_report.flags)
        post_check_error = post_check_flags[0] if post_check_flags else f"post_check_{post_check_report.severity}"
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
            quality_flags=quality_flags + post_check_flags + [f"post_check_{post_check_report.severity}"],
            error_code=post_check_error,
        )
        print(
            "Post-check failed: "
            f"severity={post_check_report.severity} flags={','.join(post_check_flags) or '-'}",
            file=sys.stderr,
        )
        return 13

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
            quality_flags=quality_flags,
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
            quality_flags=quality_flags,
        )

    result = {
        "post_id": args.post_id,
        "subtype": args.subtype,
        "fail": fail_axes,
        "chars_before": len(current_body),
        "chars_after": len(new_body),
        "guards": "pass",
        "dry_run": bool(args.dry_run),
        "content_hash": content_hash,
    }
    if llm_skip_reason:
        result["llm_skip_reason"] = llm_skip_reason
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
