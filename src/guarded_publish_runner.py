from __future__ import annotations

import html
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from src.pre_publish_fact_check import extractor
from src.title_body_nucleus_validator import validate_title_body_nucleus
from src.wp_client import WPClient


ROOT = Path(__file__).resolve().parent.parent
JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
DEFAULT_MAX_BURST = 20
MAX_BURST_HARD_CAP = 30
DAILY_CAP_HARD_CAP = 100
POSTCHECK_BATCH_SIZE = 10
DEFAULT_BACKUP_DIR = ROOT / "logs" / "cleanup_backup"
DEFAULT_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
DEFAULT_YELLOW_LOG_PATH = ROOT / "logs" / "guarded_publish_yellow_log.jsonl"
DEFAULT_CLEANUP_LOG_PATH = ROOT / "logs" / "guarded_publish_cleanup_log.jsonl"

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
SOURCE_LABEL_RE = re.compile(r"(引用元|出典|参考|参照元|source)\s*[:：]", re.I)
SOURCE_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
H3_RE = re.compile(r"(?is)<h3\b[^>]*>(.*?)</h3>")
PRE_BLOCK_RE = re.compile(r"(?is)<pre\b[^>]*>(.*?)</pre>")
CODE_BLOCK_RE = re.compile(r"(?is)<code\b[^>]*>(.*?)</code>")
PARAGRAPH_BLOCK_RE = re.compile(r"(?is)<(p|li)\b[^>]*>.*?</\1>")
HEADING_SENTENCE_END_RE = re.compile(
    r"(した|している|していた|と語った|と話した|を確認した|を記録した|と発表した|となった|を達成した)$"
)
PLAYER_HEURISTIC_RE = re.compile(
    r"([一-龯々]{2,4}(?:投手|捕手|内野手|外野手|選手|監督)?|[A-Za-z]{2,}[0-9]*|[一-龯々]{2,4}[A-Za-z0-9]+)"
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


def _load_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("guarded publish input must be a JSON object")
    return payload


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


def _post_record_with_content(post: dict[str, Any], body_html: str) -> dict[str, Any]:
    synthetic = dict(post)
    synthetic["content"] = {"raw": body_html, "rendered": body_html}
    return extractor.extract_post_record(synthetic)


def _post_cleanup_check(post: dict[str, Any], cleaned_html: str) -> tuple[bool, str]:
    original_record = extractor.extract_post_record(post)
    cleaned_record = _post_record_with_content(post, cleaned_html)
    if not _strip_html(cleaned_html):
        return False, "body_empty"
    prose_chars = _prose_char_count(str(cleaned_record.get("body_text") or ""))
    if prose_chars < 100:
        return False, "prose_lt_100"

    title = str(cleaned_record.get("title") or "")
    subtype = extractor.infer_subtype(title)
    nucleus = validate_title_body_nucleus(title, cleaned_html, subtype)
    title_subject = nucleus.title_subject
    if title_subject:
        before_present = _subject_present_in_body(title_subject, str(original_record.get("body_text") or ""))
        after_present = _subject_present_in_body(title_subject, str(cleaned_record.get("body_text") or ""))
        if before_present and not after_present:
            return False, "title_subject_missing"

    before_has_source = bool(
        original_record.get("source_block") or SOURCE_LABEL_RE.search(str(original_record.get("body_text") or ""))
    )
    after_has_source = bool(
        cleaned_record.get("source_block") or SOURCE_LABEL_RE.search(str(cleaned_record.get("body_text") or ""))
    )
    if before_has_source and not after_has_source:
        return False, "source_anchor_missing"
    before_hosts = {
        urlparse(str(url)).hostname
        for url in (original_record.get("source_urls") or [])
        if urlparse(str(url)).hostname
    }
    after_hosts = {
        urlparse(str(url)).hostname
        for url in (cleaned_record.get("source_urls") or [])
        if urlparse(str(url)).hostname
    }
    if before_hosts and not before_hosts.intersection(after_hosts):
        return False, "source_url_missing"
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


def _build_plan(
    post: dict[str, Any],
    *,
    judgment: str,
    yellow_reasons: Sequence[str] | None,
    repairable_flags: Sequence[str] | None,
    cleanup_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    title, body_html = _preflight_post(post)
    cleaned_html = body_html
    cleanup_actions: list[dict[str, str]] = []
    cleanup_types = [str(value) for value in ((cleanup_candidate or {}).get("cleanup_types") or [])]
    repairable_flags_list = list(dict.fromkeys(str(value) for value in (repairable_flags or []) if str(value)))
    cleanup_required = bool(repairable_flags_list)

    if "heading_sentence_as_h3" in cleanup_types:
        cleaned_html, heading_actions = _replace_heading_sentence_h3(cleaned_html)
        if not heading_actions:
            raise CandidateRefusedError("cleanup_ambiguous", "heading_sentence_as_h3_missing")
        cleanup_actions.extend(heading_actions)

    if "dev_log_contamination" in cleanup_types:
        cleaned_html, dev_actions = _remove_dev_log_contamination(cleaned_html)
        cleanup_actions.extend(dev_actions)

    cleanup_check = "not_required"
    cleanup_success: bool | None = None
    if cleanup_required:
        ok, cleanup_check = _post_cleanup_check(post, cleaned_html)
        if not ok:
            raise CandidateRefusedError("post_cleanup_abort", cleanup_check)
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
        "publish_link": str((post or {}).get("link") or ""),
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


def _history_attempted_post_ids(rows: Sequence[dict[str, Any]]) -> set[int]:
    attempted: set[int] = set()
    for row in rows:
        if str(row.get("status") or "") not in {"sent", "refused"}:
            continue
        try:
            attempted.add(int(row.get("post_id")))
        except (TypeError, ValueError):
            continue
    return attempted


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
                }
            )
    return entries


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
    }


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
    if plan["cleanup_required"]:
        _append_jsonl(
            yellow_log_path,
            {
                "post_id": plan["post_id"],
                "ts": ts,
                "title": plan["title"],
                "applied_flags": list(plan["repairable_flags"]),
                "yellow_reasons": list(plan["yellow_reasons"]),
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

    report = _load_report(input_from)
    now_jst = _now_jst(now)
    now_iso = now_jst.isoformat()
    history_rows = _read_jsonl(history_path)
    attempted_post_ids = _history_attempted_post_ids(history_rows)
    daily_sent_count = _daily_sent_count(history_rows, now_jst.date())

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

    for entry in _iter_publishable_entries(report):
        post_id = entry["post_id"]
        if post_id in attempted_post_ids:
            continue

        if planned_count >= int(max_burst):
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
                    "cleanup_plan": [],
                    "post_cleanup_check": "pending_live_verify",
                    "publish_link": str((post or {}).get("link") or ""),
                    "post": post,
                }
            else:
                plan = _build_plan(
                    post,
                    judgment=entry["judgment"],
                    yellow_reasons=entry["yellow_reasons"],
                    repairable_flags=entry["repairable_flags"],
                    cleanup_candidate=entry["cleanup_candidate"],
                )
        except CandidateRefusedError as exc:
            refused.append(
                {
                    "post_id": post_id,
                    "reason": exc.reason,
                    "hold_reason": "cleanup_failed_post_condition" if entry["cleanup_required"] else exc.reason,
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
                    hold_reason="cleanup_failed_post_condition" if entry["cleanup_required"] else exc.reason,
                )
                live_history_rows.append(row)
                executed.append(
                    {
                        "post_id": post_id,
                        "status": "refused",
                        "backup_path": None,
                        "publish_link": str((post or {}).get("link") or ""),
                        "hold_reason": "cleanup_failed_post_condition" if entry["cleanup_required"] else exc.reason,
                    }
                )
            continue

        proposed_internal.append(plan)
        proposed_public.append(_public_plan(plan))
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
                    cleanup_candidate=plan["cleanup_candidate"],
                )
                cleanup_success = live_plan["cleanup_success"]
                if live_plan["requires_content_update"]:
                    get_wp().update_post_fields(
                        live_plan["post_id"],
                        status="publish",
                        content=live_plan["cleaned_html"],
                    )
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
                hold_reason = "cleanup_failed_post_condition" if plan["cleanup_required"] else exc.reason
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
            "max_burst": int(max_burst),
        },
        "proposed": proposed_public,
        "refused": refused,
        "summary": summary,
    }
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
