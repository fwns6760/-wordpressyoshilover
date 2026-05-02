from __future__ import annotations

import html
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from src import guarded_publish_evaluator as publish_evaluator
from src.lineup_source_priority import extract_game_id
from src.pre_publish_fact_check import extractor
from src.title_body_nucleus_validator import validate_title_body_nucleus
from src.wp_client import WPClient


ROOT = Path(__file__).resolve().parent.parent
JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
DEFAULT_MAX_BURST = 3
MAX_BURST_HARD_CAP = 30
DAILY_CAP_HARD_CAP = 100
DEFAULT_MAX_PUBLISH_PER_HOUR = 10
BACKLOG_FRESHNESS_CUTOFF_HOURS = 6
BACKLOG_NARROW_GAME_CONTEXT_SUBTYPES = frozenset(
    {
        "postgame",
        "game_result",
        "roster",
        "injury",
        "registration",
        "recovery",
        "notice",
        "player_notice",
        "player_recovery",
    }
)
BACKLOG_NARROW_QUOTE_COMMENT_SUBTYPES = frozenset(
    {
        "comment",
        "speech",
        "manager",
        "program",
        "off_field",
        "farm_feature",
    }
)
BACKLOG_NARROW_ALLOWLIST = BACKLOG_NARROW_GAME_CONTEXT_SUBTYPES | BACKLOG_NARROW_QUOTE_COMMENT_SUBTYPES
BACKLOG_NARROW_UNRESOLVED_SUBTYPES = frozenset({"default", "other"})
BACKLOG_NARROW_UNRESOLVED_AGE_LIMIT_HOURS = 24
BACKLOG_NARROW_FARM_RESULT_SUBTYPES = frozenset({"farm_result"})
BACKLOG_NARROW_FARM_RESULT_AGE_LIMIT_HOURS = 24
BACKLOG_NARROW_AGE_BUFFER_HOURS = 12
BACKLOG_NARROW_BLOCKED_SUBTYPES = frozenset(
    {
        "lineup",
        "pregame",
        "probable_starter",
        "farm_lineup",
    }
)
SAME_SOURCE_URL_DUPLICATE_HOLD_WINDOW_HOURS = 6
POSTCHECK_BATCH_SIZE = 10
DEFAULT_BACKUP_DIR = ROOT / "logs" / "cleanup_backup"
DEFAULT_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
DEFAULT_YELLOW_LOG_PATH = ROOT / "logs" / "guarded_publish_yellow_log.jsonl"
DEFAULT_CLEANUP_LOG_PATH = ROOT / "logs" / "guarded_publish_cleanup_log.jsonl"
DEFAULT_MIN_PROSE_AFTER_CLEANUP = 50
REFUSED_DEDUP_WINDOW_HOURS = 24
TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
POST_CLEANUP_STRICT_ENV_BY_FLAG = {
    "title_subject_missing": "STRICT_TITLE_SUBJECT",
    "source_anchor_missing": "STRICT_SOURCE_ANCHOR",
    "source_url_missing": "STRICT_SOURCE_HOSTS",
}
POST_CLEANUP_WARNING_REASON_BY_FLAG = {
    "title_subject_missing": "warning_only:post_cleanup_title_subject_relaxed",
    "source_anchor_missing": "warning_only:post_cleanup_source_anchor_relaxed",
    "source_url_missing": "warning_only:post_cleanup_source_hosts_relaxed",
}
RELAXED_FOR_BREAKING_BOARD_REASON = "warning_only:relaxed_for_breaking_board"

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
SOURCE_LABEL_RE = re.compile(r"(引用元|出典|参考|参照元|source)\s*[:：]", re.I)
SOURCE_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
H3_RE = re.compile(r"(?is)<h3\b[^>]*>(.*?)</h3>")
PRE_BLOCK_RE = re.compile(r"(?is)<pre\b[^>]*>(.*?)</pre>")
CODE_BLOCK_RE = re.compile(r"(?is)<code\b[^>]*>(.*?)</code>")
PARAGRAPH_BLOCK_RE = re.compile(r"(?is)<(p|li)\b[^>]*>.*?</\1>")
HTML_BLOCK_RE = re.compile(r"(?is)<(?P<tag>p|h[1-6]|pre|blockquote|ul|ol|div)\b[^>]*>.*?</(?P=tag)>")
RELATED_POSTS_BLOCK_RE = re.compile(
    r'(?is)<div\b[^>]*class=["\'][^"\']*yoshilover-related-posts[^"\']*["\'][^>]*>.*?</div>'
)
SITE_COMPONENT_LABEL_TAG_RE = re.compile(
    r"(?is)<(?P<tag>p|div|h[1-6])\b[^>]*>\s*(?P<label>【関連記事】|💬\s*[^<]{0,120})\s*</(?P=tag)>"
)
LIGHT_STRUCTURE_BREAK_RE = re.compile(r"(?is)<p\b[^>]*>\s*(?:&nbsp;|\s|<br\s*/?>)*</p>|(?:<br\s*/?>\s*){2,}")
HEADING_SENTENCE_END_RE = re.compile(
    r"(した|している|していた|と語った|と話した|を確認した|を記録した|と発表した|となった|を達成した)$"
)
TRAILING_TITLE_PUNCT_RE = re.compile(r"[!！?？。．・…~〜ー\-]+$")
PLAYER_HEURISTIC_RE = re.compile(
    r"([一-龯々]{2,4}(?:投手|捕手|内野手|外野手|選手|監督)?|[A-Za-z]{2,}[0-9]*|[一-龯々]{2,4}[A-Za-z0-9]+)"
)
QUOTE_LIKE_DUPLICATE_SUBTYPE_EXACT = frozenset(
    {"comment", "manager", "player", "social", "player_comment", "manager_comment", "coach_comment"}
)

TEAM_ALIASES = ("読売ジャイアンツ", "ジャイアンツ", "巨人")
POSITION_SUFFIXES = ("投手", "捕手", "内野手", "外野手", "選手")
SITE_COMPONENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"💬\s*[^。\n]{0,120}"),
    re.compile(r"【関連記事】"),
    re.compile(r"💬\s*ファンの声"),
)


class GuardedPublishAbortError(RuntimeError):
    pass


class CandidateRefusedError(RuntimeError):
    def __init__(self, reason: str, detail: str | None = None):
        self.reason = reason
        self.detail = detail or reason
        super().__init__(self.detail)


class BackupError(RuntimeError):
    pass


def _cleanup_action_payload(action_type: str, before: Any, after: Any, *, reason: str) -> dict[str, str]:
    before_text = str(before or "")
    after_text = str(after or "")
    return {
        "type": action_type,
        "before": _collapse_snippet(before_text),
        "after": _collapse_snippet(after_text),
        "reason": reason,
        "preview_diff": _preview_diff(before_text, after_text),
    }


def _load_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("guarded publish input must be a JSON object")
    return payload


def _load_verdict_rows(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("verdict JSON must be a list")
    rows: list[dict[str, Any]] = []
    seen_post_ids: set[int] = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"verdict row must be an object: {path}:{index}")
        try:
            post_id = int(item["post_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"verdict row missing valid post_id: {path}:{index}") from exc
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict not in {"ok", "ng"}:
            raise ValueError(f"verdict row must use ok|ng: {path}:{index}")
        if post_id in seen_post_ids:
            raise ValueError(f"duplicate verdict post_id={post_id}: {path}:{index}")
        raw_reasons = item.get("reasons")
        if raw_reasons is None:
            reasons: list[str] = []
        elif isinstance(raw_reasons, list):
            reasons = [str(reason).strip() for reason in raw_reasons if str(reason).strip()]
        else:
            reason_text = str(raw_reasons).strip()
            reasons = [reason_text] if reason_text else []
        rows.append(
            {
                "post_id": post_id,
                "verdict": verdict,
                "reasons": reasons,
            }
        )
        seen_post_ids.add(post_id)
    return rows


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _now_utc(now: datetime | None = None) -> datetime:
    return _now_jst(now).astimezone(UTC)


def _env_int(name: str, *, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    raw_value = str(os.environ.get(name, "")).strip()
    if not raw_value:
        value = int(default)
    else:
        try:
            value = int(raw_value)
        except ValueError as exc:
            raise GuardedPublishAbortError(f"{name} must be an integer") from exc
    if value < int(minimum):
        raise GuardedPublishAbortError(f"{name} must be >= {int(minimum)}")
    if maximum is not None and value > int(maximum):
        raise GuardedPublishAbortError(f"{name} must be <= {int(maximum)}")
    return value


def _effective_max_burst_per_run(requested_max_burst: int) -> int:
    raw_configured = str(os.environ.get("MAX_BURST_PER_RUN", "")).strip()
    if not raw_configured:
        return int(requested_max_burst)
    configured = _env_int(
        "MAX_BURST_PER_RUN",
        default=DEFAULT_MAX_BURST,
        minimum=1,
        maximum=MAX_BURST_HARD_CAP,
    )
    requested = int(requested_max_burst)
    if requested == DEFAULT_MAX_BURST:
        return configured
    return min(requested, configured)


def _max_publish_per_hour(requested_max_burst: int) -> int:
    raw_configured = str(os.environ.get("MAX_PUBLISH_PER_HOUR", "")).strip()
    if not raw_configured and int(requested_max_burst) != DEFAULT_MAX_BURST:
        return DAILY_CAP_HARD_CAP
    return _env_int("MAX_PUBLISH_PER_HOUR", default=DEFAULT_MAX_PUBLISH_PER_HOUR, minimum=1)


def _parse_iso_to_jst(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _strip_html(value: str) -> str:
    text = TAG_RE.sub("\n", value or "")
    text = html.unescape(text).replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _collapse_snippet(value: Any, *, limit: int = 200) -> str:
    text = WHITESPACE_RE.sub(" ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _preview_diff(before: str, after: str) -> str:
    return f"{_collapse_snippet(before)} -> {_collapse_snippet(after)}"


def _normalize_subject_token(subject: str | None) -> str:
    value = html.unescape(str(subject or ""))
    value = WHITESPACE_RE.sub("", value)
    for suffix in POSITION_SUFFIXES:
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value.strip()


def _subject_present_in_body(subject: str | None, body_text: str) -> bool:
    normalized_body = WHITESPACE_RE.sub("", html.unescape(body_text or ""))
    token = _normalize_subject_token(subject)
    if not token:
        return True
    if token in TEAM_ALIASES or any(alias in token for alias in TEAM_ALIASES):
        return any(alias in normalized_body for alias in TEAM_ALIASES)
    if token.endswith("監督"):
        base = token[: -2]
        return token in normalized_body or bool(base and base in normalized_body)
    return token in normalized_body


def _prose_char_count(body_text: str) -> int:
    chunks: list[str] = []
    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if SOURCE_LABEL_RE.search(line):
            continue
        if SOURCE_URL_RE.fullmatch(line):
            continue
        if any(pattern.search(line) for pattern in SITE_COMPONENT_PATTERNS):
            continue
        chunks.append(line)
    return len("".join(chunks))


def _min_prose_after_cleanup() -> int:
    return int(os.environ.get("MIN_PROSE_AFTER_CLEANUP", str(DEFAULT_MIN_PROSE_AFTER_CLEANUP)))


def _env_truthy(name: str) -> bool:
    value = str(os.environ.get(name) or "").strip().lower()
    return value in TRUTHY_ENV_VALUES


def _log_event(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), file=sys.stderr, flush=True)


def _post_record_with_content(post: dict[str, Any], body_html: str) -> dict[str, Any]:
    synthetic = dict(post)
    synthetic["content"] = {"raw": body_html, "rendered": body_html}
    return extractor.extract_post_record(synthetic)


def _post_cleanup_check(post: dict[str, Any], cleaned_html: str) -> tuple[bool, str]:
    original_record = extractor.extract_post_record(post)
    cleaned_record = _post_record_with_content(post, cleaned_html)
    warning_flags: list[str] = []
    if not _strip_html(cleaned_html):
        return False, "body_empty"
    prose_chars = _prose_char_count(str(cleaned_record.get("body_text") or ""))
    if prose_chars < _min_prose_after_cleanup():
        return False, "prose_lt_100"

    title = str(cleaned_record.get("title") or "")
    subtype = extractor.infer_subtype(title)
    nucleus = validate_title_body_nucleus(title, cleaned_html, subtype)
    title_subject = nucleus.title_subject
    if title_subject:
        before_present = _subject_present_in_body(title_subject, str(original_record.get("body_text") or ""))
        after_present = _subject_present_in_body(title_subject, str(cleaned_record.get("body_text") or ""))
        if before_present and not after_present:
            if _env_truthy(POST_CLEANUP_STRICT_ENV_BY_FLAG["title_subject_missing"]):
                return False, "title_subject_missing"
            warning_flags.append("title_subject_missing")

    before_has_source = bool(
        original_record.get("source_block") or SOURCE_LABEL_RE.search(str(original_record.get("body_text") or ""))
    )
    after_has_source = bool(
        cleaned_record.get("source_block") or SOURCE_LABEL_RE.search(str(cleaned_record.get("body_text") or ""))
    )
    if before_has_source and not after_has_source:
        if _env_truthy(POST_CLEANUP_STRICT_ENV_BY_FLAG["source_anchor_missing"]):
            return False, "source_anchor_missing"
        warning_flags.append("source_anchor_missing")
    before_hosts = {
        urlparse(str(url)).hostname
        for url in (original_record.get("source_urls") or [])
        if urlparse(str(url)).hostname
    }
    if after_has_source:
        after_hosts = {
            urlparse(str(url)).hostname
            for url in (cleaned_record.get("source_urls") or [])
            if urlparse(str(url)).hostname
        }
        if before_hosts and not before_hosts.intersection(after_hosts):
            if _env_truthy(POST_CLEANUP_STRICT_ENV_BY_FLAG["source_url_missing"]):
                return False, "source_url_missing"
            warning_flags.append("source_url_missing")
    if warning_flags:
        return True, "warning_only:" + "|".join(warning_flags)
    return True, "ok"


def _heading_sentence_match(inner_html: str) -> bool:
    heading_text = _strip_html(inner_html)
    if len(heading_text) < 30:
        return False
    has_sentence_signal = bool("。" in heading_text or HEADING_SENTENCE_END_RE.search(heading_text))
    if not has_sentence_signal:
        return False
    return bool(re.search(r"[0-9０-９]", heading_text) or PLAYER_HEURISTIC_RE.search(heading_text))


def _replace_heading_sentence_h3(body_html: str) -> tuple[str, list[dict[str, str]]]:
    actions: list[dict[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        inner_html = match.group(1)
        if not _heading_sentence_match(inner_html):
            return match.group(0)
        before = match.group(0)
        after = f"<p>{inner_html}</p>"
        actions.append(
            {
                "type": "heading_sentence_as_h3",
                "before": _collapse_snippet(before),
                "after": _collapse_snippet(after),
                "reason": "30+ chars + sentence signal + numeric_or_subject cue",
                "preview_diff": _preview_diff(before, after),
            }
        )
        return after

    return H3_RE.sub(repl, body_html or ""), actions


def _dev_line_categories(line: str) -> set[str]:
    categories: set[str] = set()
    if "Traceback (most recent call last)" in line or re.search(r"^[A-Za-z_]+Error:\s", line):
        categories.add("traceback")
    if any(token in line for token in ("python3 -m", "git diff", "git log", "git push")):
        categories.add("command")
    if any(token in line for token in ("wsl.exe", "cmd /c", "bash -lc")):
        categories.add("shell")
    if any(token in line for token in ("--full-auto", "--skip-git-repo-check")):
        categories.add("flag")
    if any(token in line for token in ("commit_hash", "task_id", "bg_id")) or re.search(r"bg_[a-z0-9]{8}", line):
        categories.add("meta_id")
    if any(token in line for token in ("[scan] emitted=", "[result] post_id=", "status=sent", "status=suppressed")):
        categories.add("result")
    lowered = line.lower()
    if "tokens used" in lowered or "changed_files" in line or "open_questions" in line:
        categories.add("agent_meta")
    if re.search(r"\b(Codex|Claude)\b", line):
        categories.add("agent_name")
    return categories


def _detect_dev_log_blocks(body_html: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clear_blocks: list[dict[str, Any]] = []
    scattered_blocks: list[dict[str, Any]] = []

    for pattern, block_type in ((PRE_BLOCK_RE, "pre_block"), (CODE_BLOCK_RE, "code_block")):
        for match in pattern.finditer(body_html or ""):
            block_lines = [line.strip() for line in _strip_html(match.group(1)).splitlines() if line.strip()]
            if not block_lines:
                continue
            categories = {"code_block"}
            for line in block_lines:
                categories.update(_dev_line_categories(line))
            detail = {
                "block_type": block_type,
                "categories": sorted(categories),
                "line_count": len(block_lines),
                "raw_html": match.group(0),
                "preview": "\n".join(block_lines[:5]).strip(),
            }
            if len(categories) >= 2:
                clear_blocks.append(detail)
            else:
                scattered_blocks.append(detail)

    paragraph_matches = list(PARAGRAPH_BLOCK_RE.finditer(body_html or ""))
    run: list[re.Match[str]] = []
    run_categories: set[str] = set()
    run_lines: list[str] = []

    def flush_run() -> None:
        nonlocal run, run_categories, run_lines
        if not run:
            return
        detail = {
            "block_type": "line_block",
            "categories": sorted(run_categories),
            "line_count": len(run),
            "raw_html": (body_html or "")[run[0].start() : run[-1].end()],
            "preview": "\n".join(run_lines[:5]).strip(),
        }
        if len(run) >= 5 and len(run_categories) >= 2:
            clear_blocks.append(detail)
        elif run_categories:
            scattered_blocks.append(detail)
        run = []
        run_categories = set()
        run_lines = []

    for match in paragraph_matches:
        text = _strip_html(match.group(0))
        categories = _dev_line_categories(text)
        if categories:
            run.append(match)
            run_categories.update(categories)
            run_lines.append(text)
            continue
        flush_run()
    flush_run()
    return clear_blocks, scattered_blocks


def _remove_dev_log_contamination(body_html: str) -> tuple[str, list[dict[str, str]]]:
    clear_blocks, scattered_blocks = _detect_dev_log_blocks(body_html)
    if scattered_blocks and not clear_blocks:
        raise CandidateRefusedError("cleanup_ambiguous", "dev_log_contamination_scattered")
    if not clear_blocks:
        raise CandidateRefusedError("cleanup_ambiguous", "dev_log_contamination_missing_clear_block")

    cleaned = body_html
    actions: list[dict[str, str]] = []
    removed = False
    for block in clear_blocks:
        raw_html = str(block.get("raw_html") or "")
        if not raw_html or raw_html not in cleaned:
            continue
        cleaned = cleaned.replace(raw_html, "", 1)
        removed = True
        actions.append(
            {
                "type": "dev_log_contamination",
                "before": _collapse_snippet(raw_html),
                "after": "(deleted)",
                "reason": (
                    f"{block['block_type']} clear block: line_count={block['line_count']} "
                    f"categories={','.join(block['categories'])}"
                ),
                "preview_diff": _preview_diff(raw_html, "(deleted)"),
            }
        )

    if not removed:
        raise CandidateRefusedError("cleanup_ambiguous", "dev_log_contamination_missing_block")

    remaining_clear, remaining_scattered = _detect_dev_log_blocks(cleaned)
    if remaining_clear or remaining_scattered:
        raise CandidateRefusedError("cleanup_ambiguous", "dev_log_contamination_residual")
    return cleaned, actions


def _append_weak_source_display(body_html: str, post: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    record = _post_record_with_content(post, body_html)
    source_urls = [str(url).strip() for url in (record.get("source_urls") or []) if str(url).strip()]
    if not source_urls:
        raise CandidateRefusedError("cleanup_ambiguous", "weak_source_display_missing_source_url")

    source_url = source_urls[0]
    appended_line = f"出典: {source_url}"
    body_text = _strip_html(body_html)
    if appended_line in body_text:
        return body_html, [
            _cleanup_action_payload(
                "weak_source_display",
                appended_line,
                appended_line,
                reason="warning_only:explicit_source_anchor_already_present",
            )
        ]

    anchor_html = html.escape(source_url, quote=True)
    appended_html = f'<p>出典: <a href="{anchor_html}">{html.escape(source_url)}</a></p>'
    before = body_html.rstrip()
    joiner = "\n" if before else ""
    cleaned = f"{before}{joiner}{appended_html}"
    return cleaned, [
        _cleanup_action_payload(
            "weak_source_display",
            body_html[-200:],
            appended_html,
            reason="append explicit source anchor using first extracted source URL",
        )
    ]


def _remove_light_structure_breaks(body_html: str) -> tuple[str, list[dict[str, str]]]:
    cleaned = re.sub(r"(?is)<p\b[^>]*>\s*(?:&nbsp;|\s|<br\s*/?>)*</p>", "", body_html or "")
    cleaned = re.sub(r"(?is)(?:<br\s*/?>\s*){2,}", "<br />", cleaned)
    if cleaned == (body_html or ""):
        return body_html, [
            _cleanup_action_payload(
                "light_structure_break",
                _collapse_snippet(body_html),
                _collapse_snippet(body_html),
                reason="warning_only:structure_break_already_normalized",
            )
        ]
    return cleaned, [
        _cleanup_action_payload(
            "light_structure_break",
            body_html,
            cleaned,
            reason="remove empty paragraphs and collapse repeated br tags",
        )
    ]


def _remove_site_component_mixed_into_body(body_html: str) -> tuple[str, list[dict[str, str]]]:
    actions: list[dict[str, str]] = []
    cleaned = body_html or ""

    def remove_related(match: re.Match[str]) -> str:
        raw_html = match.group(0)
        actions.append(
            _cleanup_action_payload(
                "site_component_mixed_into_body",
                raw_html,
                "(deleted)",
                reason="remove related-posts component block",
            )
        )
        return ""

    cleaned = RELATED_POSTS_BLOCK_RE.sub(remove_related, cleaned)

    def remove_label(match: re.Match[str]) -> str:
        raw_html = match.group(0)
        actions.append(
            _cleanup_action_payload(
                "site_component_mixed_into_body",
                raw_html,
                "(deleted)",
                reason="remove standalone site component label from article body",
            )
        )
        return ""

    cleaned = SITE_COMPONENT_LABEL_TAG_RE.sub(remove_label, cleaned)
    if actions:
        return cleaned, actions
    return body_html, [
        _cleanup_action_payload(
            "site_component_mixed_into_body",
            _collapse_snippet(body_html),
            _collapse_snippet(body_html),
            reason="warning_only:site_component_label_not_found_after_prior_cleanup",
        )
    ]


def _remove_weird_heading_labels(body_html: str) -> tuple[str, list[dict[str, str]]]:
    hits = publish_evaluator._weird_heading_labels(body_html)
    if not hits:
        return body_html, [
            _cleanup_action_payload(
                "weird_heading_label",
                _collapse_snippet(body_html),
                _collapse_snippet(body_html),
                reason="warning_only:weird_heading_not_found_after_prior_cleanup",
            )
        ]

    remaining_by_heading: dict[str, int] = {}
    for hit in hits:
        heading = str(hit.get("heading") or "")
        remaining_by_heading[heading] = remaining_by_heading.get(heading, 0) + 1

    actions: list[dict[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        heading_text = _strip_html(match.group(1))
        remaining = remaining_by_heading.get(heading_text, 0)
        if remaining <= 0:
            return match.group(0)
        remaining_by_heading[heading_text] = remaining - 1
        raw_html = match.group(0)
        actions.append(
            _cleanup_action_payload(
                "weird_heading_label",
                raw_html,
                "(deleted)",
                reason="remove mismatched helper heading label",
            )
        )
        return ""

    cleaned = H3_RE.sub(repl, body_html or "")
    if not actions:
        raise CandidateRefusedError("cleanup_ambiguous", "weird_heading_label_missing")
    return cleaned, actions


def _warning_only_ai_tone_cleanup(post: dict[str, Any], body_html: str) -> tuple[str, list[dict[str, str]]]:
    record = _post_record_with_content(post, body_html)
    lead = "\n".join(line.strip() for line in str(record.get("body_text") or "").splitlines()[:3] if line.strip())
    preview = f"{record.get('title') or ''} // {lead}".strip(" /")
    return body_html, [
        _cleanup_action_payload(
            "ai_tone_heading_or_lead",
            preview,
            preview,
            reason="warning_only:no_safe_regex_cleanup_in_141",
        )
    ]


def _warning_only_flag_cleanup(
    flag: str,
    post: dict[str, Any],
    body_html: str,
    *,
    reason: str,
) -> tuple[str, list[dict[str, str]]]:
    record = _post_record_with_content(post, body_html)
    preview = f"{record.get('title') or ''} // {str(record.get('body_text') or '').splitlines()[0] if str(record.get('body_text') or '').splitlines() else ''}".strip(
        " /"
    )
    return body_html, [_cleanup_action_payload(flag, preview, preview, reason=reason)]


def _post_cleanup_warning_actions(
    cleanup_check: str,
    post: dict[str, Any],
    body_html: str,
) -> list[dict[str, str]]:
    if not cleanup_check.startswith("warning_only:"):
        return []
    flags = [flag for flag in cleanup_check.removeprefix("warning_only:").split("|") if flag]
    actions: list[dict[str, str]] = []
    for flag in flags:
        _, flag_actions = _warning_only_flag_cleanup(
            flag,
            post,
            body_html,
            reason=POST_CLEANUP_WARNING_REASON_BY_FLAG.get(flag, "warning_only:post_cleanup_relaxed"),
        )
        actions.extend(flag_actions)
    return actions


def _merge_meta(post: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict((post or {}).get("meta") or {})
    merged.update(updates)
    return merged


def _current_article_subtype(post: dict[str, Any]) -> str:
    meta = dict((post or {}).get("meta") or {})
    for candidate in (meta.get("article_subtype"), (post or {}).get("article_subtype")):
        value = str(candidate or "").strip().lower()
        if value:
            return value
    return ""


def _resolved_subtype_meta_updates(post: dict[str, Any], resolved_subtype: str | None) -> dict[str, Any]:
    normalized = str(resolved_subtype or "").strip().lower()
    if not normalized:
        return {}
    current = _current_article_subtype(post)
    if current and current not in publish_evaluator.UNKNOWN_SUBTYPE_VALUES:
        return {}
    if current == normalized:
        return {}
    return {"article_subtype": normalized}


def _resolve_subtype_cleanup(post: dict[str, Any], body_html: str) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    record = extractor.extract_post_record(post)
    resolution = publish_evaluator.resolve_guarded_publish_subtype(post, record)
    meta = dict((post or {}).get("meta") or {})
    existing = str(meta.get("article_subtype") or (post or {}).get("article_subtype") or "").strip().lower()
    resolved = str(resolution.get("resolved_subtype") or "").strip().lower()
    if not resolved or resolved in publish_evaluator.UNKNOWN_SUBTYPE_VALUES:
        raise CandidateRefusedError("cleanup_ambiguous", "subtype_unresolved_no_resolution")
    action = _cleanup_action_payload(
        "subtype_unresolved",
        existing or "(empty)",
        resolved,
        reason=f"set meta.article_subtype from {resolution.get('resolution_source') or 'fallback'}",
    )
    return body_html, [action], {"article_subtype": resolved}


def _is_source_like_block(block_html: str) -> bool:
    block_text = _strip_html(block_html)
    return bool(SOURCE_LABEL_RE.search(block_text) or SOURCE_URL_RE.fullmatch(block_text))


def _compress_long_body(body_html: str, post: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    record = _post_record_with_content(post, body_html)
    prose_chars = _prose_char_count(str(record.get("body_text") or ""))
    if prose_chars <= 5000:
        return body_html, [
            _cleanup_action_payload(
                "long_body",
                f"prose_chars={prose_chars}",
                f"prose_chars={prose_chars}",
                reason="warning_only:below_5000_safe_trim_threshold",
            )
        ]

    blocks = [match.group(0) for match in HTML_BLOCK_RE.finditer(body_html or "")]
    if not blocks:
        raise CandidateRefusedError("cleanup_ambiguous", "long_body_no_html_blocks")

    source_blocks = [block for block in blocks if _is_source_like_block(block)]
    prose_blocks = [block for block in blocks if block not in source_blocks]
    if len(prose_blocks) <= 1:
        raise CandidateRefusedError("cleanup_ambiguous", "long_body_not_enough_blocks")

    keep_target = max(100, int(prose_chars * 0.7))
    kept_blocks: list[str] = []
    kept_chars = 0
    for index, block in enumerate(prose_blocks):
        block_chars = len(_strip_html(block))
        if kept_blocks and kept_chars >= keep_target:
            break
        kept_blocks.append(block)
        kept_chars += block_chars
        if index == 0 and kept_chars >= keep_target:
            break

    if len(kept_blocks) >= len(prose_blocks):
        return body_html, [
            _cleanup_action_payload(
                "long_body",
                f"prose_chars={prose_chars}",
                f"prose_chars={prose_chars}",
                reason="warning_only:no_trimmable_tail_detected",
            )
        ]

    removed_blocks = prose_blocks[len(kept_blocks) :]
    cleaned = "".join(kept_blocks + source_blocks)
    removed_preview = _strip_html("".join(removed_blocks))
    return cleaned, [
        _cleanup_action_payload(
            "long_body",
            removed_preview,
            "(trimmed trailing 30% prose tail)",
            reason=f"trim trailing prose tail above 5000 chars (before={prose_chars}, kept~{kept_chars})",
        )
    ]


def _record_has_minimum_source(record: dict[str, Any]) -> bool:
    return bool(record.get("source_block") or record.get("source_urls"))


def _cleanup_failure_fallback(
    post: dict[str, Any],
    original_html: str,
    cleanup_check: str,
) -> tuple[str, list[dict[str, str]], list[str], bool] | None:
    if cleanup_check in {"body_empty", "title_subject_missing", "source_anchor_missing", "source_url_missing"}:
        return None
    original_record = _post_record_with_content(post, original_html)
    if _prose_char_count(str(original_record.get("body_text") or "")) <= 0:
        return None
    if not _record_has_minimum_source(original_record):
        return None
    _, fallback_actions = _warning_only_flag_cleanup(
        "cleanup_failed_post_condition",
        post,
        original_html,
        reason=f"warning_only:cleanup_failed_post_condition_fallback:{cleanup_check}",
    )
    warning_line = f"[Warning] cleanup_failed_post_condition fallback: {cleanup_check}"
    return original_html, fallback_actions, [warning_line], False


def _preflight_post(post: dict[str, Any]) -> tuple[str, str]:
    record = extractor.extract_post_record(post)
    status = str((post or {}).get("status") or "").strip().lower()
    if status != "draft":
        raise CandidateRefusedError("preflight:not_draft", f"preflight:not_draft:{status or 'missing'}")
    title = str(record.get("title") or "").strip()
    body_html = str(record.get("body_html") or "").strip()
    if not title:
        raise CandidateRefusedError("preflight:empty_title")
    if not body_html:
        raise CandidateRefusedError("preflight:empty_content")
    return title, body_html


REPAIRABLE_FLAG_ACTION_MAP = {
    "heading_sentence_as_h3": "h3_to_p_demotion",
    "weird_heading_label": "remove_weird_heading_label",
    "dev_log_contamination": "remove_dev_log_block",
    "site_component_mixed_into_body": "remove_site_component_block",
    "ai_tone_heading_or_lead": "warning_only_ai_tone",
    "light_structure_break": "normalize_structure_break",
    "weak_source_display": "append_source_anchor",
    "subtype_unresolved": "set_meta_article_subtype",
    "long_body": "trim_trailing_prose_tail",
    "missing_primary_source": "warning_only_missing_primary_source",
    "missing_featured_media": "warning_only_missing_featured_media",
    "title_body_mismatch_partial": "warning_only_partial_mismatch",
    "numerical_anomaly_low_severity": "warning_only_low_severity_numeric",
    "stale_for_breaking_board": "freshness_audit_only_no_op",
    "expired_lineup_or_pregame": "freshness_audit_only_no_op",
    "expired_game_context": "freshness_audit_only_no_op",
    "injury_death": "user_overide_full_publish_no_op",
    "lineup_duplicate_excessive": "user_overide_full_publish_no_op",
}


def _build_plan(
    post: dict[str, Any],
    *,
    judgment: str,
    yellow_reasons: Sequence[str] | None,
    repairable_flags: Sequence[str] | None,
    cleanup_required: bool,
    cleanup_candidate: dict[str, Any] | None,
    resolved_subtype: str | None = None,
    freshness_source: str | None = None,
) -> dict[str, Any]:
    title, body_html = _preflight_post(post)
    cleaned_html = body_html
    cleanup_actions: list[dict[str, str]] = []
    repairable_flags_list = list(dict.fromkeys(str(value) for value in (repairable_flags or []) if str(value)))
    meta_updates: dict[str, Any] = {}
    warning_lines: list[str] = []
    resolved_subtype_value = str(resolved_subtype or "").strip().lower()

    meta_updates.update(_resolved_subtype_meta_updates(post, resolved_subtype_value))
    if "subtype_unresolved" in repairable_flags_list and resolved_subtype_value:
        warning_lines.append(f"[Warning] subtype unresolved; using {resolved_subtype_value} fallback")

    for flag in repairable_flags_list:
        if flag in publish_evaluator.NO_CLEANUP_REQUIRED_FLAGS:
            continue
        action_name = REPAIRABLE_FLAG_ACTION_MAP.get(flag)
        if action_name is None:
            raise CandidateRefusedError("cleanup_action_unmapped", f"cleanup_action_unmapped:{flag}")

        if flag in publish_evaluator.RELAXED_FOR_BREAKING_BOARD_FLAGS and len(repairable_flags_list) == 1:
            cleaned_html, relaxed_actions = _warning_only_flag_cleanup(
                flag,
                post,
                cleaned_html,
                reason=RELAXED_FOR_BREAKING_BOARD_REASON,
            )
            cleanup_actions.extend(relaxed_actions)
            continue

        if flag == "heading_sentence_as_h3":
            cleaned_html, heading_actions = _replace_heading_sentence_h3(cleaned_html)
            if not heading_actions:
                raise CandidateRefusedError("cleanup_ambiguous", "heading_sentence_as_h3_missing")
            cleanup_actions.extend(heading_actions)
            continue

        if flag == "weird_heading_label":
            cleaned_html, weird_actions = _remove_weird_heading_labels(cleaned_html)
            cleanup_actions.extend(weird_actions)
            continue

        if flag == "dev_log_contamination":
            cleaned_html, dev_actions = _remove_dev_log_contamination(cleaned_html)
            cleanup_actions.extend(dev_actions)
            continue

        if flag == "site_component_mixed_into_body":
            cleaned_html, site_actions = _remove_site_component_mixed_into_body(cleaned_html)
            cleanup_actions.extend(site_actions)
            continue

        if flag == "ai_tone_heading_or_lead":
            cleaned_html, ai_actions = _warning_only_ai_tone_cleanup(post, cleaned_html)
            cleanup_actions.extend(ai_actions)
            continue

        if flag == "light_structure_break":
            cleaned_html, structure_actions = _remove_light_structure_breaks(cleaned_html)
            cleanup_actions.extend(structure_actions)
            continue

        if flag == "weak_source_display":
            cleaned_html, source_actions = _append_weak_source_display(cleaned_html, post)
            cleanup_actions.extend(source_actions)
            continue

        if flag == "subtype_unresolved":
            cleaned_html, subtype_actions, subtype_meta_updates = _resolve_subtype_cleanup(post, cleaned_html)
            cleanup_actions.extend(subtype_actions)
            meta_updates.update(subtype_meta_updates)
            continue

        if flag == "long_body":
            cleaned_html, long_body_actions = _compress_long_body(cleaned_html, post)
            cleanup_actions.extend(long_body_actions)
            continue

        if flag == "missing_primary_source":
            cleaned_html, legacy_actions = _warning_only_flag_cleanup(
                flag,
                post,
                cleaned_html,
                reason="warning_only:legacy_repairable_missing_primary_source",
            )
            cleanup_actions.extend(legacy_actions)
            continue

        if flag == "missing_featured_media":
            cleaned_html, legacy_actions = _warning_only_flag_cleanup(
                flag,
                post,
                cleaned_html,
                reason="warning_only:legacy_repairable_missing_featured_media",
            )
            cleanup_actions.extend(legacy_actions)
            continue

        if flag == "title_body_mismatch_partial":
            cleaned_html, legacy_actions = _warning_only_flag_cleanup(
                flag,
                post,
                cleaned_html,
                reason="warning_only:legacy_repairable_title_body_mismatch_partial",
            )
            cleanup_actions.extend(legacy_actions)
            continue

        if flag == "numerical_anomaly_low_severity":
            cleaned_html, legacy_actions = _warning_only_flag_cleanup(
                flag,
                post,
                cleaned_html,
                reason="warning_only:legacy_repairable_numerical_anomaly_low_severity",
            )
            cleanup_actions.extend(legacy_actions)
            continue

        if action_name == "freshness_audit_only_no_op":
            cleaned_html, freshness_actions = _warning_only_flag_cleanup(
                flag,
                post,
                cleaned_html,
                reason="warning_only:freshness_audit_only_no_op",
            )
            cleanup_actions.extend(freshness_actions)
            continue

    cleanup_check = "not_required"
    cleanup_success: bool | None = None
    if cleanup_required:
        ok, cleanup_check = _post_cleanup_check(post, cleaned_html)
        if not ok:
            fallback = _cleanup_failure_fallback(post, body_html, cleanup_check)
            if fallback is None:
                raise CandidateRefusedError("post_cleanup_abort", cleanup_check)
            cleaned_html, cleanup_actions, fallback_warning_lines, cleanup_success = fallback
            warning_lines.extend(fallback_warning_lines)
            cleanup_check = f"warning_only:cleanup_failed_post_condition:{cleanup_check}"
        else:
            cleanup_actions.extend(_post_cleanup_warning_actions(cleanup_check, post, cleaned_html))
            cleanup_success = True

    return {
        "post_id": int((post or {}).get("id")),
        "title": title,
        "judgment": judgment,
        "yellow_reasons": list(yellow_reasons or []),
        "repairable_flags": repairable_flags_list,
        "cleanup_required": cleanup_required,
        "cleanup_success": cleanup_success,
        "cleanup_candidate": cleanup_candidate,
        "cleanup_actions": cleanup_actions,
        "cleanup_plan": [{"type": action["type"], "preview_diff": action["preview_diff"]} for action in cleanup_actions],
        "post_cleanup_check": cleanup_check,
        "cleaned_html": cleaned_html,
        "requires_content_update": cleaned_html != body_html,
        "resolved_subtype": resolved_subtype_value,
        "warning_lines": warning_lines,
        "meta_updates": dict(meta_updates),
        "requires_meta_update": bool(meta_updates),
        "update_fields": {
            **({"content": cleaned_html} if cleaned_html != body_html else {}),
            **({"meta": _merge_meta(post, meta_updates)} if meta_updates else {}),
        },
        "publish_link": str((post or {}).get("link") or ""),
        "freshness_source": str(freshness_source or "").strip(),
        "post": post,
        "original_html": body_html,
    }


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = _path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open(encoding="utf-8") as handle:
        for index, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"jsonl row must be an object: {target}:{index}")
            rows.append(payload)
    return rows


def _append_jsonl(path: str | Path, payload: dict[str, Any]) -> None:
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _history_attempted_post_ids(rows: Sequence[dict[str, Any]], *, now: datetime | None = None) -> set[int]:
    attempted: set[int] = set()
    refused_cutoff = _now_jst(now) - timedelta(hours=REFUSED_DEDUP_WINDOW_HOURS)
    for row in rows:
        status = str(row.get("status") or "")
        if status == "sent":
            try:
                attempted.add(int(row.get("post_id")))
            except (TypeError, ValueError):
                continue
            continue
        if status != "refused":
            continue
        ts = _parse_iso_to_jst(row.get("ts"))
        if ts is not None and ts < refused_cutoff:
            continue
        try:
            attempted.add(int(row.get("post_id")))
        except (TypeError, ValueError):
            continue
    return attempted


def _latest_history_row_for_post_id(
    rows: Sequence[dict[str, Any]],
    *,
    post_id: int,
) -> dict[str, Any] | None:
    target_post_id = int(post_id)
    for row in reversed(rows):
        try:
            row_post_id = int(row.get("post_id"))
        except (TypeError, ValueError):
            continue
        if row_post_id == target_post_id:
            return row
    return None


def _history_state_matches(
    row: dict[str, Any] | None,
    *,
    status: str,
    judgment: str,
    hold_reason: str,
) -> bool:
    if row is None:
        return False
    return (
        str(row.get("status") or "") == status
        and str(row.get("judgment") or "") == judgment
        and str(row.get("hold_reason") or "") == hold_reason
    )


def _daily_sent_count(rows: Sequence[dict[str, Any]], day: date) -> int:
    count = 0
    for row in rows:
        if str(row.get("status") or "") != "sent":
            continue
        ts = _parse_iso_to_jst(row.get("ts"))
        if ts is None or ts.date() != day:
            continue
        count += 1
    return count


def _hourly_sent_count(rows: Sequence[dict[str, Any]], now: datetime) -> int:
    cutoff = _now_jst(now) - timedelta(hours=1)
    current_now = _now_jst(now)
    count = 0
    for row in rows:
        if str(row.get("status") or "") != "sent":
            continue
        ts = _parse_iso_to_jst(row.get("ts"))
        if ts is None or ts < cutoff or ts > current_now:
            continue
        count += 1
    return count


def _build_backup_payload(post: dict[str, Any], *, fetched_at: datetime) -> dict[str, Any]:
    return {
        "id": post.get("id"),
        "status": post.get("status"),
        "title": post.get("title"),
        "content": post.get("content"),
        "excerpt": post.get("excerpt"),
        "meta": post.get("meta"),
        "modified": post.get("modified"),
        "link": post.get("link"),
        "fetched_at": fetched_at.astimezone(UTC).isoformat(),
    }


def create_publish_backup(
    post: dict[str, Any],
    backup_dir: str | Path,
    *,
    now: datetime | None = None,
) -> Path:
    current_jst = _now_jst(now)
    current_utc = current_jst.astimezone(UTC)
    target_dir = _path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{int((post or {}).get('id'))}_{current_utc.strftime('%Y%m%dT%H%M%S')}.json"
    destination = target_dir / filename
    temp_path = destination.with_name(f"{destination.name}.tmp")
    payload = _build_backup_payload(post, fetched_at=current_utc)
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    except Exception as exc:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise BackupError(f"failed to write backup: {destination}") from exc
    return destination


def _iter_publishable_entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    cleanup_map = {
        int(candidate["post_id"]): candidate
        for candidate in (report.get("cleanup_candidates") or [])
        if isinstance(candidate, dict) and "post_id" in candidate
    }
    entries: list[dict[str, Any]] = []
    for judgment in ("green", "yellow"):
        for entry in report.get(judgment, []) or []:
            if not isinstance(entry, dict):
                continue
            post_id = int(entry["post_id"])
            entries.append(
                {
                    "post_id": post_id,
                    "title": str(entry.get("title") or ""),
                    "judgment": judgment,
                    "yellow_reasons": list(entry.get("yellow_reasons") or []),
                    "repairable_flags": list(entry.get("repairable_flags") or entry.get("soft_cleanup_flags") or []),
                    "cleanup_required": bool(entry.get("cleanup_required")),
                    "cleanup_candidate": cleanup_map.get(post_id),
                    "resolved_subtype": str(entry.get("resolved_subtype") or entry.get("subtype") or ""),
                    "content_date": str(entry.get("content_date") or ""),
                    "freshness_age_hours": entry.get("freshness_age_hours"),
                    "freshness_source": str(entry.get("freshness_source") or ""),
                    "backlog_only": bool(entry.get("backlog_only")),
                    "modified": str(entry.get("modified") or ""),
                }
            )
    return entries


def _entry_freshness_age_hours(entry: dict[str, Any], *, now: datetime) -> float | None:
    raw_age_hours = entry.get("freshness_age_hours")
    try:
        if raw_age_hours is not None:
            age_hours = float(raw_age_hours)
            if age_hours >= 0:
                return age_hours
    except (TypeError, ValueError):
        pass

    for key in ("created_at", "date", "modified"):
        parsed = _parse_iso_to_jst(entry.get(key))
        if parsed is None:
            continue
        delta = _now_jst(now) - parsed
        return max(0.0, delta.total_seconds() / 3600.0)
    return None


def _entry_subtype(entry: dict[str, Any]) -> str:
    return str(entry.get("resolved_subtype") or entry.get("subtype") or "").strip().lower()


def _resolve_freshness_threshold(subtype: str) -> float | None:
    normalized = str(subtype or "").strip().lower()
    if not normalized:
        return None
    try:
        threshold_hours = float(publish_evaluator._freshness_threshold_hours(normalized))
    except (TypeError, ValueError):
        return None
    if threshold_hours < 0:
        return None
    return threshold_hours


def _backlog_narrow_publish_context(entry: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    subtype = _entry_subtype(entry)
    if not subtype:
        return None
    if subtype in BACKLOG_NARROW_BLOCKED_SUBTYPES:
        return None
    age_hours = _entry_freshness_age_hours(entry, now=now)
    if age_hours is None:
        return None
    if subtype in BACKLOG_NARROW_UNRESOLVED_SUBTYPES:
        if age_hours >= float(BACKLOG_NARROW_UNRESOLVED_AGE_LIMIT_HOURS):
            return None
        return {
            "subtype": subtype,
            "age_hours": age_hours,
            "threshold_hours": float(BACKLOG_NARROW_UNRESOLVED_AGE_LIMIT_HOURS),
            "narrow_kind": "unresolved_fallback",
        }
    if subtype in BACKLOG_NARROW_FARM_RESULT_SUBTYPES:
        threshold_hours = float(BACKLOG_NARROW_FARM_RESULT_AGE_LIMIT_HOURS)
        if age_hours >= threshold_hours:
            return None
        return {
            "subtype": subtype,
            "age_hours": age_hours,
            "threshold_hours": threshold_hours,
            "narrow_kind": "farm_result_age_within_24h",
            "reason": "farm_result_age_within_24h",
        }
    if subtype not in BACKLOG_NARROW_ALLOWLIST:
        return None
    threshold_hours = _resolve_freshness_threshold(subtype)
    if threshold_hours is None:
        return None
    if age_hours >= threshold_hours + BACKLOG_NARROW_AGE_BUFFER_HOURS:
        return None
    return {
        "subtype": subtype,
        "age_hours": age_hours,
        "threshold_hours": threshold_hours,
        "narrow_kind": "allowlist",
    }


def _backlog_narrow_publish_eligible(entry: dict[str, Any], *, now: datetime) -> bool:
    return _backlog_narrow_publish_context(entry, now=now) is not None


def _is_backlog_entry(entry: dict[str, Any], *, now: datetime) -> bool:
    if bool(entry.get("backlog_only")):
        return True
    age_hours = _entry_freshness_age_hours(entry, now=now)
    return age_hours is not None and age_hours > BACKLOG_FRESHNESS_CUTOFF_HOURS


def _normalize_hold_reason_token(value: Any) -> str:
    token = re.sub(r"[^\w]+", "_", str(value or "").strip(), flags=re.UNICODE)
    return token.strip("_").lower()


def _codex_review_ng_hold_reason(reasons: Sequence[str]) -> str:
    if not reasons:
        return "codex_review_ng"
    token = _normalize_hold_reason_token(reasons[0])
    if not token:
        return "codex_review_ng"
    return f"codex_review_ng_{token}"


def _apply_verdict_filter(
    entries: Sequence[dict[str, Any]],
    verdict_path: str | Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    verdict_by_post_id = {
        row["post_id"]: row
        for row in _load_verdict_rows(verdict_path)
    }
    approved: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for entry in entries:
        post_id = int(entry["post_id"])
        verdict = verdict_by_post_id.get(post_id)
        if verdict is None:
            held.append(
                {
                    **entry,
                    "reason": "codex_review_missing_verdict",
                    "hold_reason": "codex_review_missing_verdict",
                    "error": "codex_review_missing_verdict",
                }
            )
            continue
        if verdict["verdict"] == "ok":
            approved.append(dict(entry))
            continue
        hold_reason = _codex_review_ng_hold_reason(verdict["reasons"])
        error = "codex_review_ng"
        if verdict["reasons"]:
            error = f"{error}:{','.join(verdict['reasons'])}"
        held.append(
            {
                **entry,
                "reason": "codex_review_ng",
                "hold_reason": hold_reason,
                "error": error,
            }
        )
    return approved, held


def _iter_red_entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for entry in report.get("red", []) or []:
        if not isinstance(entry, dict):
            continue
        hard_stop_flags = list(entry.get("hard_stop_flags") or [])
        legacy_red_flags = list(entry.get("red_flags") or hard_stop_flags)
        entries.append(
            {
                "post_id": int(entry["post_id"]),
                "title": str(entry.get("title") or ""),
                "reason": "hard_stop",
                "hard_stop_flags": hard_stop_flags,
                "red_flags": legacy_red_flags,
                "hold_reason": f"hard_stop_{(hard_stop_flags or legacy_red_flags or ['unknown'])[0]}",
            }
        )
    return entries


def _review_hold_reason(review_flags: Sequence[str]) -> str:
    token = _normalize_hold_reason_token((list(review_flags) or ["review_needed"])[0])
    return f"review_{token or 'needed'}"


def _duplicate_title_value(post: dict[str, Any]) -> str:
    title = (post or {}).get("title")
    if isinstance(title, dict):
        raw = title.get("raw")
        if raw:
            return html.unescape(str(raw)).strip()
        rendered = title.get("rendered")
        if rendered:
            return html.unescape(str(rendered)).strip()
    return html.unescape(str(title or "")).strip()


def _normalize_duplicate_title(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKC", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    text = TRAILING_TITLE_PUNCT_RE.sub("", text).strip()
    return text.lower()


def _duplicate_value_candidates(post: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        for container_key in ("", "meta", "metadata"):
            container = post if not container_key else (post or {}).get(container_key)
            if not isinstance(container, dict) or key not in container:
                continue
            value = container.get(key)
            if isinstance(value, list):
                for item in value:
                    cleaned = html.unescape(str(item or "")).strip()
                    if cleaned:
                        values.append(cleaned)
            elif isinstance(value, dict):
                for nested_key in ("raw", "rendered", "name", "url"):
                    cleaned = html.unescape(str(value.get(nested_key) or "")).strip()
                    if cleaned:
                        values.append(cleaned)
            else:
                cleaned = html.unescape(str(value or "")).strip()
                if cleaned:
                    values.append(cleaned)
    return values


def _dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _extract_duplicate_source_urls(post: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    _, meta_url = WPClient._get_source_url_meta(post)
    if meta_url:
        urls.append(meta_url)
    urls.extend(_duplicate_value_candidates(post, "source_url", "_yoshilover_source_url", "yl_source_url"))
    record = extractor.extract_post_record(post)
    urls.extend(str(url).strip() for url in (record.get("source_urls") or []) if str(url).strip())
    return _dedupe_preserve_order(urls)


def _source_url_hash(url: str | None) -> str | None:
    if not url:
        return None
    return hashlib.sha256(str(url).encode("utf-8")).hexdigest()[:16]


def _extract_duplicate_source_hashes(post: dict[str, Any]) -> list[str]:
    hashes = [_source_url_hash(url) for url in _extract_duplicate_source_urls(post)]
    return [value for value in _dedupe_preserve_order([str(item or "") for item in hashes]) if value]


def _duplicate_subtype(post: dict[str, Any]) -> str:
    meta = dict((post or {}).get("meta") or {})
    for candidate in (meta.get("article_subtype"), (post or {}).get("article_subtype")):
        value = str(candidate or "").strip().lower()
        if value:
            return value
    title = _duplicate_title_value(post)
    return str(extractor.infer_subtype(title) or "").strip().lower()


def _duplicate_speaker_token(post: dict[str, Any]) -> str:
    for candidate in _duplicate_value_candidates(
        post,
        "speaker",
        "speaker_name",
        "subject_entity",
        "target_entity",
        "player",
        "player_name",
        "entity_primary",
    ):
        normalized = _normalize_duplicate_title(candidate)
        if normalized:
            return normalized
    return ""


def _same_game_subtype_speaker_key(post: dict[str, Any]) -> str:
    game_id = str(extract_game_id(post) or "").strip().lower()
    subtype = _duplicate_subtype(post)
    speaker = _duplicate_speaker_token(post)
    if not game_id or not subtype or not speaker:
        return ""
    return f"{game_id}|{subtype}|{speaker}"


def _duplicate_reference_publish_time(post: dict[str, Any]) -> datetime | None:
    for key in ("date", "date_gmt", "modified", "modified_gmt"):
        parsed = _parse_iso_to_jst((post or {}).get(key))
        if parsed is not None:
            return parsed
    return None


def _duplicate_reference_payload(post: dict[str, Any]) -> dict[str, Any]:
    post_id = int((post or {}).get("id"))
    return {
        "post_id": post_id,
        "title": _duplicate_title_value(post),
        "subtype": _duplicate_subtype(post),
        "speaker_token": _duplicate_speaker_token(post),
        "status": str((post or {}).get("status") or "").strip().lower(),
        "published_at": _duplicate_reference_publish_time(post),
    }


def _is_quote_like_duplicate_subtype(subtype: str) -> bool:
    token = str(subtype or "").strip().lower()
    if not token:
        return False
    return token in QUOTE_LIKE_DUPLICATE_SUBTYPE_EXACT or "comment" in token or "quote" in token


def _same_source_url_speaker_relaxed(
    candidate_subtype: str,
    candidate_speaker: str,
    reference_subtype: str,
    reference_speaker: str,
) -> bool:
    if not candidate_subtype or candidate_subtype != reference_subtype:
        return False
    if not _is_quote_like_duplicate_subtype(candidate_subtype):
        return False
    if not candidate_speaker or not reference_speaker:
        return False
    return candidate_speaker != reference_speaker


def _same_source_url_age_relaxed(reference: dict[str, Any], *, now: datetime) -> bool:
    published_at = reference.get("published_at")
    if not isinstance(published_at, datetime):
        return False
    return now - published_at >= timedelta(hours=SAME_SOURCE_URL_DUPLICATE_HOLD_WINDOW_HOURS)


def _same_source_url_duplicate_reference(
    post: dict[str, Any],
    references: Sequence[dict[str, Any]] | dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if isinstance(references, dict):
        reference_rows = [references]
    else:
        reference_rows = [reference for reference in (references or []) if isinstance(reference, dict)]
    if not reference_rows:
        return None

    candidate_subtype = _duplicate_subtype(post)
    candidate_speaker = _duplicate_speaker_token(post)
    current_jst = _now_jst(now)

    for reference in reference_rows:
        reference_subtype = str(reference.get("subtype") or "").strip().lower()
        if candidate_subtype and reference_subtype and candidate_subtype != reference_subtype:
            continue
        if _same_source_url_age_relaxed(reference, now=current_jst):
            continue
        reference_speaker = str(reference.get("speaker_token") or "").strip().lower()
        if _same_source_url_speaker_relaxed(
            candidate_subtype,
            candidate_speaker,
            reference_subtype,
            reference_speaker,
        ):
            continue
        return reference
    return None


def _empty_duplicate_index() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "exact_titles": {},
        "normalized_titles": {},
        "source_hashes": {},
        "game_subtype_speaker": {},
    }


def _index_duplicate_post(index: dict[str, dict[str, dict[str, Any]]], post: dict[str, Any]) -> None:
    title = _duplicate_title_value(post)
    reference = _duplicate_reference_payload(post)
    if title:
        index["exact_titles"].setdefault(title, reference)
    normalized_title = _normalize_duplicate_title(title)
    if normalized_title:
        index["normalized_titles"].setdefault(normalized_title, reference)
    for source_hash in _extract_duplicate_source_hashes(post):
        index["source_hashes"].setdefault(source_hash, []).append(reference)
    same_game_key = _same_game_subtype_speaker_key(post)
    if same_game_key:
        index["game_subtype_speaker"].setdefault(same_game_key, reference)


def _duplicate_reference(
    compared_against: str,
    duplicate_reason: str,
    reference: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any]]:
    duplicate_of_post_id: int | None = None
    if reference is not None:
        try:
            duplicate_of_post_id = int(reference.get("post_id"))
        except (TypeError, ValueError):
            duplicate_of_post_id = None
    return True, {
        "duplicate_of_post_id": duplicate_of_post_id,
        "duplicate_reason": duplicate_reason,
        "compared_against": compared_against,
    }


def _detect_duplicate_candidate(
    post: dict[str, Any],
    run_promoted_titles_set: dict[str, dict[str, dict[str, Any]]],
    wp_existing_publish_titles: dict[str, dict[str, dict[str, Any]]],
    wp_existing_draft_titles: dict[str, dict[str, dict[str, Any]]],
    wp_existing_source_urls: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
) -> tuple[bool, dict[str, Any]]:
    title = _duplicate_title_value(post)
    normalized_title = _normalize_duplicate_title(title)

    for source_hash in _extract_duplicate_source_hashes(post):
        reference = _same_source_url_duplicate_reference(post, wp_existing_source_urls.get(source_hash), now=now)
        if reference is not None:
            return _duplicate_reference("wp_publish", "same_source_url", reference)

    if title:
        if title in wp_existing_publish_titles["exact_titles"]:
            return _duplicate_reference(
                "wp_publish",
                "exact_title_match_publish",
                wp_existing_publish_titles["exact_titles"].get(title),
            )
        if title in wp_existing_draft_titles["exact_titles"]:
            return _duplicate_reference(
                "wp_draft",
                "exact_title_match_draft",
                wp_existing_draft_titles["exact_titles"].get(title),
            )
        if title in run_promoted_titles_set["exact_titles"]:
            return _duplicate_reference(
                "run_internal",
                "run_internal_dup",
                run_promoted_titles_set["exact_titles"].get(title),
            )

    if normalized_title:
        if normalized_title in wp_existing_publish_titles["normalized_titles"]:
            return _duplicate_reference(
                "wp_publish",
                "normalized_title_match_publish",
                wp_existing_publish_titles["normalized_titles"].get(normalized_title),
            )
        if normalized_title in wp_existing_draft_titles["normalized_titles"]:
            return _duplicate_reference(
                "wp_draft",
                "normalized_title_match_draft",
                wp_existing_draft_titles["normalized_titles"].get(normalized_title),
            )
        if normalized_title in run_promoted_titles_set["normalized_titles"]:
            return _duplicate_reference(
                "run_internal",
                "normalized_title_match_run_internal",
                run_promoted_titles_set["normalized_titles"].get(normalized_title),
            )

    same_game_key = _same_game_subtype_speaker_key(post)
    if same_game_key:
        if same_game_key in wp_existing_publish_titles["game_subtype_speaker"]:
            return _duplicate_reference(
                "wp_publish",
                "same_game_subtype_speaker",
                wp_existing_publish_titles["game_subtype_speaker"].get(same_game_key),
            )
        if same_game_key in wp_existing_draft_titles["game_subtype_speaker"]:
            return _duplicate_reference(
                "wp_draft",
                "same_game_subtype_speaker",
                wp_existing_draft_titles["game_subtype_speaker"].get(same_game_key),
            )
        if same_game_key in run_promoted_titles_set["game_subtype_speaker"]:
            return _duplicate_reference(
                "run_internal",
                "same_game_subtype_speaker",
                run_promoted_titles_set["game_subtype_speaker"].get(same_game_key),
            )

    return False, {
        "duplicate_of_post_id": None,
        "duplicate_reason": "",
        "compared_against": "",
    }


def _duplicate_guard_posts(
    wp_client: Any,
    *,
    status: str,
    exclude_post_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    rows = wp_client.list_posts(
        status=status,
        per_page=100,
        page=1,
        orderby="modified",
        order="desc",
        context="edit",
        fields=["id", "title", "slug", "content", "meta", "status", "date", "modified"],
    )
    excluded = exclude_post_ids or set()
    return [
        row
        for row in rows
        if isinstance(row, dict) and int(row.get("id") or 0) not in excluded
    ]


def _build_duplicate_index(posts: Sequence[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    index = _empty_duplicate_index()
    for post in posts:
        _index_duplicate_post(index, post)
    return index


def _iter_review_entries(report: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for entry in report.get("review", []) or []:
        if not isinstance(entry, dict):
            continue
        review_flags = list(entry.get("review_flags") or [])
        entries.append(
            {
                "post_id": int(entry["post_id"]),
                "title": str(entry.get("title") or ""),
                "reason": "review",
                "review_flags": review_flags,
                "hold_reason": _review_hold_reason(review_flags),
            }
        )
    return entries


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "post_id": plan["post_id"],
        "title": plan["title"],
        "judgment": plan["judgment"],
        "cleanup_required": bool(plan["cleanup_required"]),
        "cleanup_plan": plan["cleanup_plan"],
        "post_cleanup_check": plan["post_cleanup_check"],
        "repairable_flags": list(plan["repairable_flags"]),
    }
    if plan["judgment"] == "yellow":
        payload["yellow_reasons"] = list(plan["yellow_reasons"])
    if plan.get("resolved_subtype"):
        payload["resolved_subtype"] = str(plan["resolved_subtype"])
    return payload


def _history_row(
    *,
    post_id: int,
    judgment: str,
    status: str,
    ts: str,
    backup_path: str | None,
    error: str | None,
    publishable: bool | None = None,
    cleanup_required: bool | None = None,
    cleanup_success: bool | None = None,
    hold_reason: str | None = None,
    is_backlog: bool | None = None,
    freshness_source: str | None = None,
    duplicate_of_post_id: int | None = None,
    duplicate_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "post_id": post_id,
        "ts": ts,
        "status": status,
        "backup_path": backup_path,
        "error": error,
        "judgment": judgment,
        "publishable": publishable,
        "cleanup_required": cleanup_required,
        "cleanup_success": cleanup_success,
        "hold_reason": hold_reason,
        "is_backlog": None if is_backlog is None else bool(is_backlog),
        "freshness_source": str(freshness_source or "").strip() or None,
        "duplicate_of_post_id": duplicate_of_post_id,
        "duplicate_reason": str(duplicate_reason or "").strip() or None,
    }


def _hold_reason_for_candidate_error(cleanup_required: bool, exc: CandidateRefusedError) -> str:
    if exc.reason == "cleanup_action_unmapped":
        return "cleanup_action_unmapped"
    if cleanup_required:
        return "cleanup_failed_post_condition"
    return exc.reason


def _postcheck_batch(wp_client: Any, post_ids: Sequence[int]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for post_id in post_ids:
        post = wp_client.get_post(post_id)
        status = str((post or {}).get("status") or "").strip().lower()
        results.append(
            {
                "post_id": int(post_id),
                "status": status,
                "ok": status == "publish",
            }
        )
    return {
        "post_ids": [int(post_id) for post_id in post_ids],
        "results": results,
        "all_ok": all(item["ok"] for item in results),
    }


def _write_live_success_logs(
    *,
    plan: dict[str, Any],
    ts: str,
    yellow_log_path: str | Path,
    cleanup_log_path: str | Path,
) -> None:
    manual_x_post_block_reason = "roster_movement_yellow" if "roster_movement_yellow" in plan["repairable_flags"] else None
    warning_lines: list[str] = list(plan.get("warning_lines") or [])
    if manual_x_post_block_reason == "roster_movement_yellow":
        roster_warning = "[Warning] roster movement 系記事、X 自動投稿対象外"
        if roster_warning not in warning_lines:
            warning_lines.append(roster_warning)
    if plan["judgment"] == "yellow":
        _append_jsonl(
            yellow_log_path,
            {
                "post_id": plan["post_id"],
                "ts": ts,
                "title": plan["title"],
                "applied_flags": list(plan["repairable_flags"]),
                "yellow_reasons": list(plan["yellow_reasons"]),
                "cleanup_required": bool(plan["cleanup_required"]),
                "warning_lines": warning_lines,
                "manual_x_post_blocked": manual_x_post_block_reason is not None,
                "manual_x_post_block_reason": manual_x_post_block_reason,
                "freshness_source": str(plan.get("freshness_source") or "").strip() or None,
                "publish_link": plan["publish_link"],
            },
        )
    if plan["cleanup_required"]:
        _append_jsonl(
            cleanup_log_path,
            {
                "post_id": plan["post_id"],
                "ts": ts,
                "before_excerpt": _collapse_snippet(_strip_html(plan["original_html"])),
                "after_excerpt": _collapse_snippet(_strip_html(plan["cleaned_html"])),
                "applied_flags": list(plan["repairable_flags"]),
                "cleanups": [
                    {
                        "type": action["type"],
                        "before": action["before"],
                        "after": action["after"],
                        "reason": action["reason"],
                    }
                    for action in plan["cleanup_actions"]
                ],
                "publish_link": plan["publish_link"],
            },
        )


def run_guarded_publish(
    *,
    input_from: str | Path,
    filter_verdict: str | Path | None = None,
    live: bool = False,
    max_burst: int = DEFAULT_MAX_BURST,
    daily_cap_allow: bool = False,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    yellow_log_path: str | Path = DEFAULT_YELLOW_LOG_PATH,
    cleanup_log_path: str | Path = DEFAULT_CLEANUP_LOG_PATH,
    wp_client: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if int(max_burst) <= 0:
        raise GuardedPublishAbortError("--max-burst must be > 0")
    if int(max_burst) > MAX_BURST_HARD_CAP:
        raise GuardedPublishAbortError(f"--max-burst must be <= {MAX_BURST_HARD_CAP}")
    if live and not daily_cap_allow:
        raise GuardedPublishAbortError("--live requires --daily-cap-allow")
    effective_max_burst = _effective_max_burst_per_run(int(max_burst))

    report = _load_report(input_from)
    now_jst = _now_jst(now)
    now_iso = now_jst.isoformat()
    history_rows = _read_jsonl(history_path)
    attempted_post_ids = _history_attempted_post_ids(history_rows, now=now_jst)
    daily_sent_count = _daily_sent_count(history_rows, now_jst.date())
    hourly_sent_count = _hourly_sent_count(history_rows, now_jst)
    max_publish_per_hour = _max_publish_per_hour(int(max_burst))
    idempotent_history_enabled = _env_truthy("ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY")

    refused: list[dict[str, Any]] = []
    proposed_public: list[dict[str, Any]] = []
    proposed_internal: list[dict[str, Any]] = []
    executed: list[dict[str, Any]] = []
    live_history_rows: list[dict[str, Any]] = []
    postcheck_batches: list[dict[str, Any]] = []
    wp: Any | None = None
    planned_count = 0

    def get_wp() -> Any:
        nonlocal wp
        if wp is None:
            wp = wp_client or WPClient()
        return wp

    for red_entry in _iter_red_entries(report):
        if red_entry["post_id"] in attempted_post_ids:
            continue
        if daily_sent_count + planned_count >= DAILY_CAP_HARD_CAP:
            refused.append({"post_id": red_entry["post_id"], "reason": "daily_cap"})
            if live:
                row = _history_row(
                    post_id=red_entry["post_id"],
                    judgment="hard_stop",
                    status="skipped",
                    ts=now_iso,
                    backup_path=None,
                    error="daily_cap",
                    publishable=False,
                    cleanup_required=False,
                    cleanup_success=False,
                    hold_reason="daily_cap",
                )
                live_history_rows.append(row)
                executed.append(
                    {
                        "post_id": red_entry["post_id"],
                        "status": "skipped",
                        "backup_path": None,
                        "publish_link": "",
                    }
                )
            continue
        refused.append(
            {
                "post_id": red_entry["post_id"],
                "reason": red_entry["reason"],
                "hold_reason": red_entry["hold_reason"],
            }
        )
        if live:
            detail = ",".join(red_entry["hard_stop_flags"] or red_entry["red_flags"]) or "hard_stop"
            row = _history_row(
                post_id=red_entry["post_id"],
                judgment="hard_stop",
                status="refused",
                ts=now_iso,
                backup_path=None,
                error=f"hard_stop:{detail}",
                publishable=False,
                cleanup_required=False,
                cleanup_success=False,
                hold_reason=red_entry["hold_reason"],
            )
            live_history_rows.append(row)
            executed.append(
                {
                    "post_id": red_entry["post_id"],
                    "status": "refused",
                    "backup_path": None,
                    "publish_link": "",
                }
            )

    for review_entry in _iter_review_entries(report):
        if review_entry["post_id"] in attempted_post_ids:
            continue
        refused.append(
            {
                "post_id": review_entry["post_id"],
                "reason": review_entry["reason"],
                "hold_reason": review_entry["hold_reason"],
            }
        )
        if live:
            detail = ",".join(review_entry["review_flags"]) or "review"
            row = _history_row(
                post_id=review_entry["post_id"],
                judgment="review",
                status="refused",
                ts=now_iso,
                backup_path=None,
                error=f"review:{detail}",
                publishable=False,
                cleanup_required=False,
                cleanup_success=False,
                hold_reason=review_entry["hold_reason"],
            )
            live_history_rows.append(row)
            executed.append(
                {
                    "post_id": review_entry["post_id"],
                    "status": "refused",
                    "backup_path": None,
                    "publish_link": "",
                    "hold_reason": review_entry["hold_reason"],
                }
            )

    publishable_entries = [
        entry
        for entry in _iter_publishable_entries(report)
        if int(entry["post_id"]) not in attempted_post_ids
    ]
    held_entries: list[dict[str, Any]] = []
    if filter_verdict is not None:
        publishable_entries, held_entries = _apply_verdict_filter(publishable_entries, filter_verdict)

    for held_entry in held_entries:
        is_backlog = _is_backlog_entry(held_entry, now=now_jst)
        refused.append(
            {
                "post_id": held_entry["post_id"],
                "reason": held_entry["reason"],
                "hold_reason": held_entry["hold_reason"],
            }
        )
        if live:
            row = _history_row(
                post_id=held_entry["post_id"],
                judgment=held_entry["judgment"],
                status="skipped",
                ts=now_iso,
                backup_path=None,
                error=held_entry["error"],
                publishable=True,
                cleanup_required=bool(held_entry["cleanup_required"]),
                cleanup_success=False,
                hold_reason=held_entry["hold_reason"],
                is_backlog=is_backlog,
                freshness_source=str(held_entry.get("freshness_source") or ""),
            )
            live_history_rows.append(row)
            executed.append(
                {
                    "post_id": held_entry["post_id"],
                    "status": "skipped",
                    "backup_path": None,
                    "publish_link": "",
                    "hold_reason": held_entry["hold_reason"],
                }
            )

    filtered_publishable_entries: list[dict[str, Any]] = []
    for entry in publishable_entries:
        if not bool(entry.get("backlog_only")):
            filtered_publishable_entries.append(entry)
            continue
        backlog_context = _backlog_narrow_publish_context(entry, now=now_jst)
        if backlog_context is not None:
            entry["_backlog_narrow_context"] = backlog_context
            _log_event(
                "backlog_narrow_publish_eligible",
                post_id=entry["post_id"],
                subtype=backlog_context["subtype"],
                age_hours=backlog_context["age_hours"],
                threshold_hours=backlog_context["threshold_hours"],
                narrow_kind=backlog_context["narrow_kind"],
            )
            filtered_publishable_entries.append(entry)
            continue
        refused.append(
            {
                "post_id": entry["post_id"],
                "reason": "backlog_only",
                "hold_reason": "backlog_only",
            }
        )
        if live:
            latest_history_row = _latest_history_row_for_post_id(history_rows, post_id=int(entry["post_id"]))
            if idempotent_history_enabled and _history_state_matches(
                latest_history_row,
                status="skipped",
                judgment=str(entry["judgment"]),
                hold_reason="backlog_only",
            ):
                _log_event(
                    "guarded_publish_idempotent_history_skip",
                    post_id=entry["post_id"],
                    reason="unchanged_backlog_only",
                    status="skipped",
                    judgment=entry["judgment"],
                    hold_reason="backlog_only",
                )
            else:
                row = _history_row(
                    post_id=entry["post_id"],
                    judgment=entry["judgment"],
                    status="skipped",
                    ts=now_iso,
                    backup_path=None,
                    error="backlog_only",
                    publishable=True,
                    cleanup_required=bool(entry["cleanup_required"]),
                    cleanup_success=False,
                    hold_reason="backlog_only",
                    is_backlog=True,
                    freshness_source=str(entry.get("freshness_source") or ""),
                )
                live_history_rows.append(row)
            executed.append(
                {
                    "post_id": entry["post_id"],
                    "status": "skipped",
                    "backup_path": None,
                    "publish_link": "",
                    "hold_reason": "backlog_only",
                }
            )
    publishable_entries = filtered_publishable_entries

    fresh_entries = [
        entry
        for entry in publishable_entries
        if not _is_backlog_entry(entry, now=now_jst) or _backlog_narrow_publish_eligible(entry, now=now_jst)
    ]
    backlog_entries = [
        entry
        for entry in publishable_entries
        if _is_backlog_entry(entry, now=now_jst) and not _backlog_narrow_publish_eligible(entry, now=now_jst)
    ]
    deferred_backlog_entries = backlog_entries if fresh_entries else []
    publishable_entries = fresh_entries if fresh_entries else backlog_entries
    run_promoted_titles_set = _empty_duplicate_index()
    wp_existing_publish_titles = _empty_duplicate_index()
    wp_existing_draft_titles = _empty_duplicate_index()
    wp_existing_source_urls: dict[str, dict[str, Any]] = {}

    for backlog_entry in deferred_backlog_entries:
        refused.append(
            {
                "post_id": backlog_entry["post_id"],
                "reason": "backlog_deferred_for_fresh",
                "hold_reason": "backlog_deferred_for_fresh",
            }
        )
        if live:
            row = _history_row(
                post_id=backlog_entry["post_id"],
                judgment=backlog_entry["judgment"],
                status="skipped",
                ts=now_iso,
                backup_path=None,
                error="backlog_deferred_for_fresh",
                publishable=True,
                cleanup_required=bool(backlog_entry["cleanup_required"]),
                cleanup_success=False,
                hold_reason="backlog_deferred_for_fresh",
                is_backlog=True,
                freshness_source=str(backlog_entry.get("freshness_source") or ""),
            )
            live_history_rows.append(row)
            executed.append(
                {
                    "post_id": backlog_entry["post_id"],
                    "status": "skipped",
                    "backup_path": None,
                    "publish_link": "",
                    "hold_reason": "backlog_deferred_for_fresh",
                }
            )

    if publishable_entries:
        candidate_post_ids = {int(entry["post_id"]) for entry in publishable_entries}
        wp_existing_publish_titles = _build_duplicate_index(
            _duplicate_guard_posts(get_wp(), status="publish")
        )
        wp_existing_draft_titles = _build_duplicate_index(
            _duplicate_guard_posts(get_wp(), status="draft", exclude_post_ids=candidate_post_ids)
        )
        wp_existing_source_urls = dict(wp_existing_publish_titles["source_hashes"])

    for entry in publishable_entries:
        post_id = entry["post_id"]
        is_backlog = _is_backlog_entry(entry, now=now_jst)
        if post_id in attempted_post_ids:
            continue

        if hourly_sent_count + planned_count >= max_publish_per_hour:
            refused.append({"post_id": post_id, "reason": "hourly_cap"})
            if live:
                row = _history_row(
                    post_id=post_id,
                    judgment=entry["judgment"],
                    status="skipped",
                    ts=now_iso,
                    backup_path=None,
                    error="hourly_cap",
                    publishable=True,
                    cleanup_required=bool(entry["cleanup_required"]),
                    cleanup_success=False,
                    hold_reason="hourly_cap",
                    is_backlog=is_backlog,
                    freshness_source=str(entry.get("freshness_source") or ""),
                )
                live_history_rows.append(row)
                executed.append(
                    {
                        "post_id": post_id,
                        "status": "skipped",
                        "backup_path": None,
                        "publish_link": "",
                    }
                )
            continue

        if planned_count >= effective_max_burst:
            refused.append({"post_id": post_id, "reason": "burst_cap"})
            if live:
                row = _history_row(
                    post_id=post_id,
                    judgment=entry["judgment"],
                    status="skipped",
                    ts=now_iso,
                    backup_path=None,
                    error="burst_cap",
                    publishable=True,
                    cleanup_required=bool(entry["cleanup_required"]),
                    cleanup_success=False,
                    hold_reason="burst_cap",
                    is_backlog=is_backlog,
                    freshness_source=str(entry.get("freshness_source") or ""),
                )
                live_history_rows.append(row)
                executed.append(
                    {
                        "post_id": post_id,
                        "status": "skipped",
                        "backup_path": None,
                        "publish_link": "",
                    }
                )
            continue

        if daily_sent_count + planned_count >= DAILY_CAP_HARD_CAP:
            refused.append({"post_id": post_id, "reason": "daily_cap"})
            if live:
                row = _history_row(
                    post_id=post_id,
                    judgment=entry["judgment"],
                    status="skipped",
                    ts=now_iso,
                    backup_path=None,
                    error="daily_cap",
                    publishable=True,
                    cleanup_required=bool(entry["cleanup_required"]),
                    cleanup_success=False,
                    hold_reason="daily_cap",
                    is_backlog=is_backlog,
                    freshness_source=str(entry.get("freshness_source") or ""),
                )
                live_history_rows.append(row)
                executed.append(
                    {
                        "post_id": post_id,
                        "status": "skipped",
                        "backup_path": None,
                        "publish_link": "",
                    }
                )
            continue

        post = get_wp().get_post(post_id)
        try:
            if live:
                title, _ = _preflight_post(post)
                plan = {
                    "post_id": post_id,
                    "title": title,
                    "judgment": entry["judgment"],
                    "yellow_reasons": list(entry["yellow_reasons"]),
                    "repairable_flags": list(entry["repairable_flags"]),
                    "cleanup_required": bool(entry["cleanup_required"]),
                    "cleanup_candidate": entry["cleanup_candidate"],
                    "resolved_subtype": str(entry.get("resolved_subtype") or ""),
                    "cleanup_plan": [],
                    "post_cleanup_check": "pending_live_verify",
                    "warning_lines": [],
                    "meta_updates": {},
                    "requires_meta_update": False,
                    "update_fields": {},
                    "publish_link": str((post or {}).get("link") or ""),
                    "freshness_source": str(entry.get("freshness_source") or ""),
                    "post": post,
                }
            else:
                plan = _build_plan(
                    post,
                    judgment=entry["judgment"],
                    yellow_reasons=entry["yellow_reasons"],
                    repairable_flags=entry["repairable_flags"],
                    cleanup_required=bool(entry["cleanup_required"]),
                    cleanup_candidate=entry["cleanup_candidate"],
                    resolved_subtype=str(entry.get("resolved_subtype") or ""),
                    freshness_source=str(entry.get("freshness_source") or ""),
                )
        except CandidateRefusedError as exc:
            hold_reason = _hold_reason_for_candidate_error(bool(entry["cleanup_required"]), exc)
            refused.append(
                {
                    "post_id": post_id,
                    "reason": exc.reason,
                    "hold_reason": hold_reason,
                }
            )
            if live:
                row = _history_row(
                    post_id=post_id,
                    judgment=entry["judgment"],
                    status="refused",
                    ts=now_iso,
                    backup_path=None,
                    error=exc.detail,
                    publishable=True,
                    cleanup_required=bool(entry["cleanup_required"]),
                    cleanup_success=False,
                    hold_reason=hold_reason,
                    is_backlog=is_backlog,
                    freshness_source=str(entry.get("freshness_source") or ""),
                )
                live_history_rows.append(row)
                executed.append(
                    {
                        "post_id": post_id,
                        "status": "refused",
                        "backup_path": None,
                        "publish_link": str((post or {}).get("link") or ""),
                        "hold_reason": hold_reason,
                    }
                )
            continue

        is_duplicate, duplicate_info = _detect_duplicate_candidate(
            post,
            run_promoted_titles_set,
            wp_existing_publish_titles,
            wp_existing_draft_titles,
            wp_existing_source_urls,
            now=now,
        )
        if is_duplicate:
            duplicate_reason = str(duplicate_info.get("duplicate_reason") or "duplicate_candidate")
            duplicate_of_post_id = duplicate_info.get("duplicate_of_post_id")
            hold_reason = _review_hold_reason([f"duplicate_candidate:{duplicate_reason}"])
            refused.append(
                {
                    "post_id": post_id,
                    "reason": "review",
                    "hold_reason": hold_reason,
                    "duplicate_of_post_id": duplicate_of_post_id,
                    "duplicate_reason": duplicate_reason,
                }
            )
            if live:
                row = _history_row(
                    post_id=post_id,
                    judgment=entry["judgment"],
                    status="refused",
                    ts=now_iso,
                    backup_path=None,
                    error=f"review:duplicate_candidate:{duplicate_reason}",
                    publishable=True,
                    cleanup_required=bool(entry["cleanup_required"]),
                    cleanup_success=False,
                    hold_reason=hold_reason,
                    is_backlog=is_backlog,
                    freshness_source=str(entry.get("freshness_source") or ""),
                    duplicate_of_post_id=duplicate_of_post_id,
                    duplicate_reason=duplicate_reason,
                )
                live_history_rows.append(row)
                executed.append(
                    {
                        "post_id": post_id,
                        "status": "refused",
                        "backup_path": None,
                        "publish_link": str((post or {}).get("link") or ""),
                        "hold_reason": hold_reason,
                        "duplicate_of_post_id": duplicate_of_post_id,
                        "duplicate_reason": duplicate_reason,
                    }
                )
            continue

        proposed_internal.append(plan)
        proposed_public.append(_public_plan(plan))
        _index_duplicate_post(run_promoted_titles_set, post)
        planned_count += 1

    if live:
        for row in live_history_rows:
            _append_jsonl(history_path, row)

        pending_postcheck_ids: list[int] = []
        for plan in proposed_internal:
            backup_path: str | None = None
            status = "sent"
            error: str | None = None
            hold_reason: str | None = None
            cleanup_success: bool | None = None
            try:
                backup = create_publish_backup(plan["post"], backup_dir, now=now_jst)
                backup_path = str(backup)
                live_plan = _build_plan(
                    plan["post"],
                    judgment=plan["judgment"],
                    yellow_reasons=plan["yellow_reasons"],
                    repairable_flags=plan["repairable_flags"],
                    cleanup_required=bool(plan["cleanup_required"]),
                    cleanup_candidate=plan["cleanup_candidate"],
                    resolved_subtype=str(plan.get("resolved_subtype") or ""),
                    freshness_source=str(plan.get("freshness_source") or ""),
                )
                cleanup_success = live_plan["cleanup_success"]
                if live_plan["update_fields"]:
                    get_wp().update_post_fields(live_plan["post_id"], status="publish", **live_plan["update_fields"])
                else:
                    get_wp().update_post_status(live_plan["post_id"], "publish")
                _write_live_success_logs(
                    plan=live_plan,
                    ts=now_iso,
                    yellow_log_path=yellow_log_path,
                    cleanup_log_path=cleanup_log_path,
                )
                pending_postcheck_ids.append(int(live_plan["post_id"]))
                if len(pending_postcheck_ids) >= POSTCHECK_BATCH_SIZE:
                    postcheck_batches.append(_postcheck_batch(get_wp(), pending_postcheck_ids))
                    pending_postcheck_ids = []
                plan = live_plan
            except BackupError as exc:
                status = "refused"
                error = str(exc)
                hold_reason = "cleanup_backup_failed"
                cleanup_success = False
            except CandidateRefusedError as exc:
                status = "refused"
                error = exc.detail
                hold_reason = _hold_reason_for_candidate_error(bool(plan["cleanup_required"]), exc)
                cleanup_success = False
            except Exception as exc:
                status = "refused"
                error = str(exc)
                hold_reason = "cleanup_failed_post_condition" if plan["cleanup_required"] else "publish_failed"
                cleanup_success = False
            finally:
                row = _history_row(
                    post_id=plan["post_id"],
                    judgment=plan["judgment"],
                    status=status,
                    ts=now_iso,
                    backup_path=backup_path,
                    error=error,
                    publishable=True,
                    cleanup_required=bool(plan["cleanup_required"]),
                    cleanup_success=cleanup_success if plan["cleanup_required"] else None,
                    hold_reason=hold_reason,
                    is_backlog=is_backlog,
                    freshness_source=str(plan.get("freshness_source") or ""),
                )
                _append_jsonl(history_path, row)
                executed.append(
                    {
                        "post_id": plan["post_id"],
                        "status": status,
                        "backup_path": backup_path,
                        "publish_link": plan["publish_link"],
                        "hold_reason": hold_reason,
                    }
                )

        if pending_postcheck_ids:
            postcheck_batches.append(_postcheck_batch(get_wp(), pending_postcheck_ids))

    summary = {
        "proposed_count": len(proposed_public),
        "refused_count": len(refused),
        "would_publish": len(proposed_public) if not live else sum(1 for item in executed if item["status"] == "sent"),
        "would_skip": len(refused) if not live else sum(1 for item in executed if item["status"] != "sent"),
        "postcheck_batch_count": len(postcheck_batches),
    }
    payload: dict[str, Any] = {
        "scan_meta": {
            "input_from": str(input_from),
            "ts": now_iso,
            "live": live,
            "max_burst": int(effective_max_burst),
            "max_publish_per_hour": int(max_publish_per_hour),
        },
        "proposed": proposed_public,
        "refused": refused,
        "summary": summary,
    }
    if filter_verdict is not None:
        payload["scan_meta"]["filter_verdict"] = str(filter_verdict)
    if live:
        payload["executed"] = executed
        payload["postcheck_batches"] = postcheck_batches
    return payload


def dump_guarded_publish_report(report: dict[str, Any], *, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n"

    lines = [
        "Guarded Publish Runner",
        (
            f"live={report['scan_meta']['live']}  max_burst={report['scan_meta']['max_burst']}  "
            f"ts={report['scan_meta']['ts']}"
        ),
        f"input_from={report['scan_meta']['input_from']}",
        "",
        (
            "summary: "
            f"proposed={report['summary']['proposed_count']} "
            f"refused={report['summary']['refused_count']} "
            f"publish={report['summary']['would_publish']} "
            f"skip={report['summary']['would_skip']}"
        ),
        "",
        "Proposed",
    ]
    if not report["proposed"]:
        lines.append("- none")
    else:
        for item in report["proposed"]:
            lines.append(f"- {item['post_id']} | {item['judgment']} | {item['title']}")
            if item.get("cleanup_plan"):
                for cleanup in item["cleanup_plan"]:
                    lines.append(f"  cleanup={cleanup['type']} :: {cleanup['preview_diff']}")

    lines.extend(["", "Refused"])
    if not report["refused"]:
        lines.append("- none")
    else:
        for item in report["refused"]:
            lines.append(f"- {item['post_id']} | {item['reason']}")

    if report.get("executed") is not None:
        lines.extend(["", "Executed"])
        if not report["executed"]:
            lines.append("- none")
        else:
            for item in report["executed"]:
                lines.append(
                    f"- {item['post_id']} | {item['status']} | backup={item['backup_path'] or 'null'}"
                )
    return "\n".join(lines) + "\n"


__all__ = [
    "BackupError",
    "CandidateRefusedError",
    "DAILY_CAP_HARD_CAP",
    "DEFAULT_MAX_BURST",
    "DEFAULT_BACKUP_DIR",
    "DEFAULT_CLEANUP_LOG_PATH",
    "DEFAULT_HISTORY_PATH",
    "DEFAULT_YELLOW_LOG_PATH",
    "GuardedPublishAbortError",
    "MAX_BURST_HARD_CAP",
    "create_publish_backup",
    "dump_guarded_publish_report",
    "run_guarded_publish",
]
