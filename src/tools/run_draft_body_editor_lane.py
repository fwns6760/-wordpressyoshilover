"""Orchestrator for the draft-body-editor side lane.

This runner owns the lane-level workflow:
1. Fetch recent WordPress drafts across every list page.
2. Filter down to safe, editable candidates.
3. Process a conservative batch per run (recommended: 3-5 posts).
4. Build source blocks and fail axes.
5. Invoke ``src.tools.draft_body_editor`` in dry-run and real-run modes.
6. Update only ``content`` for posts that pass all guards.
7. Append JSONL session logs and emit a compact stdout summary.

It intentionally does not modify scheduler/env/secret/traffic. Those are owned
outside this runner.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from src import repair_fallback_controller
from src import repair_provider_ledger
from src.tools import draft_body_editor
from src.tools.draft_body_editor import _extract_prose_text


JST = ZoneInfo("Asia/Tokyo")
# Default edit hours align with the quality-gmail notification window.
DEFAULT_EDIT_WINDOW_START_JST = "10:00"
DEFAULT_EDIT_WINDOW_END_JST = "23:59"
LEGACY_QUIET_HOURS_JST = "18:00-21:59 JST"
DEFAULT_MAX_POSTS = 5
DEFAULT_LIST_PER_PAGE = 100
CURRENT_BODY_MAX_CHARS = 1200
ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = ROOT / "logs" / "draft_body_editor"

VALID_SUBTYPES = {"pregame", "postgame", "lineup", "manager", "farm"}
FACT_CHECK_BLOCK_VALUES = {"fail", "flagged", "pending"}
TITLE_SKIP_KEYWORDS = ("【速報】", "【LIVE】", "途中経過")
EMBED_MARKER = "<!-- wp:embed"

PRIMARY_SOURCE_DOMAINS = (
    "giants.jp",
    "npb.jp",
    "nikkansports.com",
    "sanspo.com",
    "sponichi.co.jp",
    "hochi.news",
    "nikkei.com",
    "yomiuri.co.jp",
    "daily.co.jp",
    "twitter.com",
    "x.com",
)

EXIT_WP_GET_FAILED = 40
EXIT_INPUT_ERROR = 42
EXIT_REJECT_STREAK = 43
EXIT_API_FAIL = 44
EXIT_PUT_FAIL = 45
QUEUE_FETCH_MODE = "queue_jsonl"
VALID_REPAIR_PROVIDERS = ("gemini", "codex", "openai_api")

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

NUMERIC_PATTERNS = (
    re.compile(r"\d+\.\d{3}"),
    re.compile(r"\d+\.\d{2}(?!\d)"),
    re.compile(r"\d+[-−－]\d+"),
    re.compile(r"\d+回"),
    re.compile(r"\d+球"),
    re.compile(r"\d+号"),
    re.compile(r"\d+月\d+日"),
    re.compile(r"\d+/\d+"),
    re.compile(r"[月火水木金土日]曜"),
)

HEADING_PATTERN = re.compile(r"【[^】]+】")
HREF_URL_PATTERN = re.compile(r'''href=["']([^"']+)["']''', re.IGNORECASE)
RAW_URL_PATTERN = re.compile(r'''https?://[^\s"'<>]+''', re.IGNORECASE)
SOURCE_FOOTER_URL_PATTERN = re.compile(r'参照元[:\s]*<a[^>]+href="([^"]+)"')
STRIP_HTML_PATTERN = re.compile(r"<[^>]+>")
AI_TONE_PATTERN = re.compile(r"(でしょう|かもしれません|と言えそうです|と言えるでしょう)")
KANJI_TOKEN_PATTERN = re.compile(r"[一-龥]{2,}")
KATAKANA_TOKEN_PATTERN = re.compile(r"[ァ-ヴー]{2,}")
DECORATIVE_HEADING_EMOJI = frozenset({"📊", "👀", "📌", "💬", "🔥", "⚾", "📝"})
DECORATIVE_HEADING_LABELS = frozenset({"📌 関連ポスト"})
TITLE_GENERIC_TOKENS = {
    "巨人", "読売", "ジャイアンツ",
    "試合", "結果", "勝利", "敗戦", "要点", "ポイント", "注目",
    "監督", "発言", "談話", "コメント",
    "スタメン", "先発", "オーダー",
    "変更", "登板", "二軍",
}


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_draft_body_editor_lane",
        description="Run the draft-body-editor lane against recent WordPress drafts.",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=DEFAULT_MAX_POSTS,
        help="Maximum posts to edit per run (recommended: 3-5)",
    )
    parser.add_argument(
        "--limit",
        dest="max_posts",
        type=int,
        help="Alias for --max-posts",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run the editor but do not PUT back to WordPress")
    parser.add_argument(
        "--provider",
        choices=VALID_REPAIR_PROVIDERS,
        default="gemini",
        help="Repair provider to use",
    )
    parser.add_argument(
        "--queue-path",
        default="",
        help="JSONL queue path. When omitted, fetch recent drafts from WordPress.",
    )
    parser.add_argument(
        "--ledger-path",
        default="",
        help="Override repair-provider ledger output path",
    )
    parser.add_argument("--now-iso", default="", help="Override the current JST timestamp for tests")
    parser.add_argument("--edit-window-start-jst", default="", help="Edit window start in JST (HH:MM)")
    parser.add_argument("--edit-window-end-jst", default="", help="Edit window end in JST (HH:MM)")
    return parser.parse_args(argv)


def _now_jst(now_iso: str = "") -> datetime:
    if now_iso:
        parsed = datetime.fromisoformat(now_iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=JST)
        return parsed.astimezone(JST)
    return datetime.now(JST)


def _session_log_path(now: datetime) -> Path:
    return LOG_ROOT / f"{now.date().isoformat()}.jsonl"


def _recent_log_paths(now: datetime) -> list[Path]:
    return [
        _session_log_path(now - timedelta(days=1)),
        _session_log_path(now),
    ]


def _ensure_log_dir() -> None:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)


def _append_session_log(now: datetime, record: dict[str, Any]) -> None:
    _ensure_log_dir()
    payload = dict(record)
    payload.setdefault("ts", now.isoformat())
    with _session_log_path(now).open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_recent_touched_post_ids(now: datetime) -> set[int]:
    touched: set[int] = set()
    threshold = now - timedelta(hours=24)
    for path in _recent_log_paths(now):
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    ts = datetime.fromisoformat(str(payload.get("ts", "")))
                except ValueError:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=JST)
                ts = ts.astimezone(JST)
                if ts < threshold:
                    continue
                try:
                    post_id = int(payload.get("post_id"))
                except (TypeError, ValueError):
                    continue
                touched.add(post_id)
    return touched


def _heading_sets() -> dict[str, tuple[str, ...]]:
    from src import rss_fetcher

    return {
        "pregame": tuple(rss_fetcher.GAME_REQUIRED_HEADINGS["pregame"]),
        "postgame": tuple(rss_fetcher.GAME_REQUIRED_HEADINGS["postgame"]),
        "lineup": tuple(rss_fetcher.GAME_REQUIRED_HEADINGS["lineup"]),
        "manager": tuple(rss_fetcher.MANAGER_REQUIRED_HEADINGS),
        "farm": tuple(rss_fetcher.FARM_REQUIRED_HEADINGS["farm"]),
    }


REQUIRED_HEADINGS = _heading_sets()


def _strip_html(text: str) -> str:
    text = html.unescape(text or "")
    return STRIP_HTML_PATTERN.sub(" ", text)


def _extract_content_raw(post: dict[str, Any]) -> str:
    content = (post or {}).get("content")
    if isinstance(content, dict):
        raw = content.get("raw")
        if raw:
            return str(raw)
        rendered = content.get("rendered")
        if rendered:
            return str(rendered)
    if isinstance(content, str):
        return content
    return ""


def _extract_title(post: dict[str, Any]) -> str:
    title = (post or {}).get("title")
    if isinstance(title, dict):
        for key in ("raw", "rendered"):
            value = title.get(key)
            if value:
                return html.unescape(str(value))
    if isinstance(title, str):
        return html.unescape(title)
    return ""


def _extract_meta(post: dict[str, Any]) -> dict[str, Any]:
    meta = (post or {}).get("meta")
    return meta if isinstance(meta, dict) else {}


def _parse_post_datetime(post: dict[str, Any], *fields: str) -> datetime | None:
    for field in fields:
        value = (post or {}).get(field)
        if not value:
            continue
        raw = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=JST)
        return parsed.astimezone(JST)
    return None


def _parse_hhmm(value: str) -> int:
    match = re.fullmatch(r"(\d{2}):(\d{2})", (value or "").strip())
    if not match:
        raise ValueError(f"invalid HH:MM value: {value!r}")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError(f"invalid HH:MM value: {value!r}")
    return hour * 60 + minute


def _resolve_edit_window(args: argparse.Namespace) -> tuple[int, int, str]:
    start_raw = (args.edit_window_start_jst or "").strip()
    end_raw = (args.edit_window_end_jst or "").strip()
    if bool(start_raw) != bool(end_raw):
        raise ValueError("--edit-window-start-jst and --edit-window-end-jst must be supplied together")
    if not start_raw:
        start_raw = DEFAULT_EDIT_WINDOW_START_JST
        end_raw = DEFAULT_EDIT_WINDOW_END_JST
    start_minute = _parse_hhmm(start_raw)
    end_minute = _parse_hhmm(end_raw)
    return start_minute, end_minute, f"{start_raw}-{end_raw} JST"


def _is_within_time_window(now: datetime, start_minute: int, end_minute: int) -> bool:
    current_minute = now.hour * 60 + now.minute
    if start_minute <= end_minute:
        return start_minute <= current_minute <= end_minute
    return current_minute >= start_minute or current_minute <= end_minute


def _within_edit_window(post: dict[str, Any], now: datetime) -> bool:
    modified = _parse_post_datetime(post, "modified_gmt", "modified", "date_gmt", "date")
    if modified is None:
        return False
    age = now - modified
    return timedelta(minutes=15) <= age <= timedelta(hours=72)


def _is_unresolved_and_stale(
    post: dict[str, Any],
    now: datetime,
    *,
    max_age_hours: int = 24,
) -> bool:
    if _infer_subtype(post) is not None:
        return False
    modified = _parse_post_datetime(post, "modified_gmt", "modified", "date_gmt", "date")
    if modified is None:
        return False
    return (now - modified) > timedelta(hours=max_age_hours)


def _body_headings(body: str) -> tuple[str, ...]:
    return tuple(HEADING_PATTERN.findall(_strip_html(body)))


def _strip_decorative_headings(headings: Sequence[str]) -> list[str]:
    filtered: list[str] = []
    for heading in headings:
        inner = heading.strip()
        if inner.startswith("【") and inner.endswith("】"):
            inner = inner[1:-1].strip()
        if inner in DECORATIVE_HEADING_LABELS or (inner and inner[0] in DECORATIVE_HEADING_EMOJI):
            continue
        filtered.append(heading)
    return filtered


def _infer_subtype(post: dict[str, Any]) -> str | None:
    meta = _extract_meta(post)
    meta_subtype = str(meta.get("article_subtype") or "").strip().lower()
    if meta_subtype in VALID_SUBTYPES:
        return meta_subtype

    title = _extract_title(post)
    body = _extract_content_raw(post)
    headings = _body_headings(body)

    heading_match: str | None = None
    for subtype, expected in REQUIRED_HEADINGS.items():
        if headings[: len(expected)] == expected:
            heading_match = subtype
            break

    title_match: str | None = None
    if re.search(r"スタメン|先発オーダー", title):
        title_match = "lineup"
    elif re.search(r"\d+[-−－]\d+", title):
        title_match = "postgame"
    elif re.search(r"変更|スライド登板", title):
        title_match = "pregame"
    elif re.search(r"監督.*(発言|談話|コメント)|(発言|談話|コメント).*監督", title):
        title_match = "manager"
    elif re.search(r"二軍|イースタン|ウエスタン", title):
        title_match = "farm"

    if heading_match and title_match and heading_match != title_match:
        return None
    return heading_match or title_match


def _resolved_live_update(post: dict[str, Any]) -> bool:
    meta_subtype = str(_extract_meta(post).get("article_subtype") or "").strip().lower()
    return meta_subtype == "live_update"


def _normalize_url(url: str) -> str:
    return html.unescape((url or "").strip())


def _is_primary_source_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in PRIMARY_SOURCE_DOMAINS)


def _extract_source_urls(post: dict[str, Any]) -> list[str]:
    meta = _extract_meta(post)
    urls: list[str] = []

    for key in ("source_urls", "yl_source_urls"):
        value = meta.get(key)
        if isinstance(value, list):
            urls.extend(_normalize_url(str(item)) for item in value if str(item).strip())
        elif isinstance(value, str):
            urls.extend(_normalize_url(part) for part in re.split(r"[\s,]+", value) if part.strip())

    for key in ("source_url", "_yoshilover_source_url", "yl_source_url"):
        value = meta.get(key) or post.get(key)
        if isinstance(value, str) and value.strip():
            urls.append(_normalize_url(value))

    deduped: list[str] = []
    seen = set()
    for url in urls:
        if not url or url in seen or not _is_primary_source_url(url):
            continue
        seen.add(url)
        deduped.append(url)
    if deduped:
        return deduped

    body = _extract_content_raw(post)
    match = SOURCE_FOOTER_URL_PATTERN.search(body)
    if not match:
        return []

    fallback_url = _normalize_url(match.group(1))
    if not fallback_url or not _is_primary_source_url(fallback_url):
        return []
    return [fallback_url]


def _extract_fact_tokens(text: str) -> list[str]:
    raw = _strip_html(text or "")
    tokens: list[str] = []
    seen = set()

    def _push(token: str) -> None:
        token = token.strip()
        if not token or token in seen:
            return
        seen.add(token)
        tokens.append(token)

    for team in TEAM_NAMES:
        if team in raw:
            _push(team)
    for park in BALLPARK_NAMES:
        if park in raw:
            _push(park)
    for pattern in NUMERIC_PATTERNS:
        for match in pattern.findall(raw):
            _push(match)
    for token in KANJI_TOKEN_PATTERN.findall(raw):
        _push(token)
    for token in KATAKANA_TOKEN_PATTERN.findall(raw):
        _push(token)

    return tokens


def _build_source_block(post: dict[str, Any], source_urls: Sequence[str]) -> str:
    lines = [f"・ref{i}: {url}" for i, url in enumerate(source_urls[:3], start=1)]
    for token in _extract_fact_tokens(_extract_content_raw(post))[:10]:
        lines.append(f"・{token}")
    return "\n".join(lines).strip()


def _body_sections(body: str) -> list[tuple[str, str]]:
    headings = list(HEADING_PATTERN.finditer(_strip_html(body)))
    plain = _strip_html(body)
    if not headings:
        return []
    sections: list[tuple[str, str]] = []
    for idx, match in enumerate(headings):
        start = match.end()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(plain)
        sections.append((match.group(0), plain[start:end].strip()))
    return sections


def _title_focus_token(title: str) -> str:
    stripped = re.sub(r"【[^】]+】", " ", title)
    candidates = KANJI_TOKEN_PATTERN.findall(stripped) + KATAKANA_TOKEN_PATTERN.findall(stripped)
    candidates = [token for token in candidates if token not in TITLE_GENERIC_TOKENS]
    return max(candidates, key=len, default="")


def _infer_fail_axes(post: dict[str, Any], subtype: str) -> list[str] | None:
    body = _extract_content_raw(post)
    title = _extract_title(post)
    axes: list[str] = []

    if len(AI_TONE_PATTERN.findall(_strip_html(body))) >= 2:
        axes.append("tone")

    short_sections = sum(1 for _, section in _body_sections(body) if len(section) < 30)
    if short_sections >= 2 and "density" not in axes:
        axes.append("density")

    title_token = _title_focus_token(title)
    if title_token and title_token not in _strip_html(body)[:200]:
        return None

    if not axes:
        axes.extend(["density", "source"])
    elif len(axes) == 1:
        if axes[0] != "source":
            axes.append("source")
        else:
            axes.append("density")
    return axes[:2]


def _draft_looks_editable(post: dict[str, Any], now: datetime, touched_ids: set[int]) -> tuple[bool, str]:
    if str((post or {}).get("status") or "").lower() != "draft":
        return False, "not_draft"
    try:
        post_id = int(post.get("id"))
    except (TypeError, ValueError):
        return False, "missing_post_id"
    if post_id in touched_ids:
        return False, "recently_touched"
    if not _within_edit_window(post, now):
        return False, "outside_edit_window"

    subtype = _infer_subtype(post)
    if not subtype:
        return False, "subtype_unresolved"
    if subtype not in VALID_SUBTYPES:
        return False, "subtype_unsupported"

    title = _extract_title(post)
    body = _extract_content_raw(post)
    if len(_extract_prose_text(body)) > CURRENT_BODY_MAX_CHARS:
        return False, "body_too_long"
    if EMBED_MARKER in body or EMBED_MARKER in title:
        return False, "contains_embed"
    if any(keyword in title for keyword in TITLE_SKIP_KEYWORDS):
        return False, "title_skip_keyword"

    featured_media = post.get("featured_media")
    if not featured_media:
        return False, "missing_featured_media"

    meta = _extract_meta(post)
    fact_check_status = str(meta.get("fact_check_status") or "").strip().lower()
    if fact_check_status in FACT_CHECK_BLOCK_VALUES:
        return False, "fact_check_blocked"
    if bool(meta.get("audit_flag")):
        return False, "audit_flagged"

    source_urls = _extract_source_urls(post)
    if not source_urls:
        return False, "missing_primary_source"

    fail_axes = _infer_fail_axes(post, subtype)
    if fail_axes is None:
        return False, "title_axis_scope_out"

    headings = REQUIRED_HEADINGS[subtype]
    found_headings = _body_headings(body)
    normalized_headings = tuple(_strip_decorative_headings(found_headings))
    if found_headings and normalized_headings[: len(headings)] != headings:
        return False, "heading_mismatch"

    return True, "ok"


def _list_level_looks_editable(post: dict[str, Any], now: datetime, touched_ids: set[int]) -> tuple[bool, str]:
    if str((post or {}).get("status") or "").lower() != "draft":
        return False, "not_draft"
    try:
        post_id = int(post.get("id"))
    except (TypeError, ValueError):
        return False, "missing_post_id"
    if post_id in touched_ids:
        return False, "recently_edited_by_lane"

    modified = _parse_post_datetime(post, "modified_gmt", "modified", "date_gmt", "date")
    if modified is None:
        return False, "outside_edit_window"
    age = now - modified
    if age < timedelta(minutes=15):
        return False, "recently_touched"
    if age > timedelta(hours=72):
        return False, "outside_edit_window"
    if _is_unresolved_and_stale(post, now):
        return False, "unresolved_and_stale"

    if _resolved_live_update(post):
        return False, "live_update_excluded"

    title = _extract_title(post)
    body = _extract_content_raw(post)
    if len(_extract_prose_text(body)) > CURRENT_BODY_MAX_CHARS:
        return False, "body_too_long"
    if EMBED_MARKER in body or EMBED_MARKER in title:
        return False, "contains_embed"
    if any(keyword in title for keyword in TITLE_SKIP_KEYWORDS):
        return False, "title_skip_keyword"
    if not post.get("featured_media"):
        return False, "missing_featured_media"

    meta = _extract_meta(post)
    fact_check_status = str(meta.get("fact_check_status") or "").strip().lower()
    if fact_check_status in FACT_CHECK_BLOCK_VALUES:
        return False, "fact_check_blocked"
    if bool(meta.get("audit_flag")):
        return False, "audit_flagged"
    if not _extract_source_urls(post):
        return False, "missing_primary_source"

    return True, "ok"


def _build_candidate(post: dict[str, Any]) -> dict[str, Any]:
    subtype = _infer_subtype(post)
    body = _extract_content_raw(post)
    source_urls = _extract_source_urls(post)
    fail_axes = _infer_fail_axes(post, subtype or "") or []
    return {
        "post_id": int(post["id"]),
        "title": _extract_title(post),
        "subtype": subtype,
        "current_body": body,
        "source_urls": source_urls,
        "source_block": _build_source_block(post, source_urls),
        "fail_axes": fail_axes,
        "chars_before": len(body),
    }


def _build_queue_candidate(post: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    subtype = _infer_subtype(post)
    if subtype is None:
        return None, "subtype_unresolved"
    if subtype not in VALID_SUBTYPES:
        return None, "subtype_unsupported"

    title = _extract_title(post)
    body = _extract_content_raw(post)
    if len(_extract_prose_text(body)) > CURRENT_BODY_MAX_CHARS:
        return None, "body_too_long"
    if EMBED_MARKER in body or EMBED_MARKER in title:
        return None, "contains_embed"
    if any(keyword in title for keyword in TITLE_SKIP_KEYWORDS):
        return None, "title_skip_keyword"
    if not _extract_source_urls(post):
        return None, "missing_primary_source"

    fail_axes = _infer_fail_axes(post, subtype)
    if fail_axes is None:
        return None, "title_axis_scope_out"

    headings = REQUIRED_HEADINGS[subtype]
    found_headings = _body_headings(body)
    normalized_headings = tuple(_strip_decorative_headings(found_headings))
    if found_headings and normalized_headings[: len(headings)] != headings:
        return None, "heading_mismatch"

    return _build_candidate(post), "ok"


def _editor_command(
    *,
    post_id: int,
    subtype: str,
    fail_axes: Sequence[str],
    current_path: Path,
    source_path: Path,
    out_path: Path,
    dry_run: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "src.tools.draft_body_editor",
        "--post-id",
        str(post_id),
        "--subtype",
        subtype,
        "--fail",
        ",".join(fail_axes),
        "--current-body",
        str(current_path),
        "--source-block",
        str(source_path),
        "--out",
        str(out_path),
    ]
    if dry_run:
        cmd.append("--dry-run")
    return cmd


def _resolve_ledger_path(raw_path: str, *, now: datetime) -> Path:
    if raw_path.strip():
        return Path(raw_path)
    return repair_provider_ledger.resolve_jsonl_ledger_path(now=now)


def _mirror_appended_ledger_bytes(source_path: Path, target_path: Path, start_offset: int) -> None:
    if source_path == target_path or not source_path.exists():
        return
    if start_offset < 0:
        start_offset = 0
    source_size = source_path.stat().st_size
    if source_size <= start_offset:
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with source_path.open("rb") as src:
        src.seek(start_offset)
        payload = src.read()
    if not payload:
        return
    with target_path.open("ab") as dst:
        dst.write(payload)


def _run_editor(
    candidate: dict[str, Any],
    *,
    dry_run: bool,
    ledger_path: Path,
    now: datetime,
) -> tuple[int, dict[str, Any] | None, str, str | None]:
    with tempfile.TemporaryDirectory(prefix="draft_body_editor_") as tmp:
        tmpdir = Path(tmp)
        current_path = tmpdir / "current.txt"
        source_path = tmpdir / "source.txt"
        out_path = tmpdir / "out.txt"
        current_path.write_text(candidate["current_body"], encoding="utf-8")
        source_path.write_text(candidate["source_block"], encoding="utf-8")

        cmd = _editor_command(
            post_id=candidate["post_id"],
            subtype=candidate["subtype"],
            fail_axes=candidate["fail_axes"],
            current_path=current_path,
            source_path=source_path,
            out_path=out_path,
            dry_run=dry_run,
        )

        env = os.environ.copy()
        env[repair_provider_ledger.ENV_LEDGER_DIR] = str(ledger_path.parent)
        editor_ledger_path = repair_provider_ledger.resolve_jsonl_ledger_path(
            now=now,
            sink_dir=ledger_path.parent,
        )
        ledger_offset = editor_ledger_path.stat().st_size if editor_ledger_path.exists() else 0
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(ROOT),
            env=env,
        )
        _mirror_appended_ledger_bytes(editor_ledger_path, ledger_path, ledger_offset)
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        payload = None
        if stdout:
            try:
                payload = json.loads(stdout.splitlines()[-1])
            except json.JSONDecodeError:
                payload = None
        new_body = out_path.read_text(encoding="utf-8") if out_path.exists() else None
        return completed.returncode, payload, stderr, new_body


def _format_failure_chain(
    failure_chain: Sequence[repair_fallback_controller.FailureRecord],
) -> str:
    if not failure_chain:
        return "provider failure"
    return " | ".join(
        f"{item.provider}:{item.error_class}:{item.error_message}"
        for item in failure_chain
    )


def _run_fallback_controller(
    candidate: dict[str, Any],
    *,
    provider: str,
    ledger_path: Path,
    dry_run: bool,
) -> tuple[int, dict[str, Any] | None, str, str | None]:
    headings = draft_body_editor._lookup_required_headings(candidate["subtype"])
    prompt = draft_body_editor.build_prompt(
        candidate["subtype"],
        candidate["fail_axes"],
        candidate["current_body"],
        candidate["source_block"],
        headings,
    )
    controller = repair_fallback_controller.RepairFallbackController(
        primary_provider=provider,
        fallback_provider="gemini",
        ledger_writer=repair_provider_ledger.JsonlLedgerWriter(ledger_path),
    )
    result = controller.execute(candidate, prompt)
    if result.body_text is None:
        return 20, None, _format_failure_chain(result.failure_chain), None

    new_body = result.body_text
    violations_a = draft_body_editor.guard_a_source_grounding(
        new_body,
        candidate["current_body"],
        candidate["source_block"],
    )
    if violations_a:
        return 10, None, "\n".join(violations_a), None

    violations_b = draft_body_editor.guard_b_heading_invariant(new_body, headings)
    if violations_b:
        return 11, None, "\n".join(violations_b), None

    violations_c = draft_body_editor.guard_c_scope_invariant(
        new_body,
        candidate["current_body"],
    )
    if violations_c:
        return 12, None, "\n".join(violations_c), None

    return 0, {
        "post_id": candidate["post_id"],
        "subtype": candidate["subtype"],
        "fail": list(candidate["fail_axes"]),
        "chars_before": len(candidate["current_body"]),
        "chars_after": len(new_body),
        "guards": "pass",
        "dry_run": bool(dry_run),
        "provider": result.provider,
        "fallback_used": result.fallback_used,
        "wp_write_allowed": result.wp_write_allowed,
    }, "", new_body


def _make_wp_client():
    from src.wp_client import WPClient

    _load_dotenv_if_available()
    return WPClient()


def _normalize_queue_post(payload: dict[str, Any], *, queue_path: Path, line_no: int) -> dict[str, Any]:
    post = dict(payload)
    if "id" not in post:
        if "post_id" not in post:
            raise ValueError(f"queue row missing post_id: {queue_path}:{line_no}")
        post["id"] = post["post_id"]
    try:
        post["id"] = int(post["id"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"queue row has non-numeric post_id: {queue_path}:{line_no}") from exc
    return post


def _collect_queue_candidates(
    queue_path: Path,
) -> tuple[list[dict[str, Any]], str, dict[str, int], Counter[str]]:
    candidates: list[dict[str, Any]] = []
    skip_counter: Counter[str] = Counter()
    stats = {"pages_fetched": 0, "posts_seen": 0}

    with queue_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"queue row is not valid JSON: {queue_path}:{line_no}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"queue row must be an object: {queue_path}:{line_no}")
            post = _normalize_queue_post(payload, queue_path=queue_path, line_no=line_no)
            candidates.append({
                "post_id": post["id"],
                "post": post,
            })
            stats["posts_seen"] += 1
    return candidates, QUEUE_FETCH_MODE, stats, skip_counter


def _collect_paginated_candidates(
    wp,
    *,
    now: datetime,
    touched_ids: set[int],
) -> tuple[list[dict[str, Any]] | None, str, dict[str, int], Counter[str]]:
    list_fields = ["id", "status", "modified_gmt", "modified", "title", "content", "featured_media", "meta"]
    candidates: list[dict[str, Any]] = []
    skip_counter: Counter[str] = Counter()
    stats = {"pages_fetched": 0, "posts_seen": 0}
    page = 1

    while True:
        try:
            page_posts = wp.list_posts(
                status="draft",
                per_page=DEFAULT_LIST_PER_PAGE,
                page=page,
                orderby="modified",
                order="desc",
                context="edit",
                fields=list_fields,
            )
        except Exception as e:
            if "rest_post_invalid_page_number" in str(e):
                stats["pages_fetched"] += 1
                break
            return None, "draft_list_paginated", stats, skip_counter

        stats["pages_fetched"] += 1
        if not page_posts:
            break

        stats["posts_seen"] += len(page_posts)
        for post in page_posts:
            ok, reason = _list_level_looks_editable(post, now, touched_ids)
            if not ok:
                skip_counter[reason] += 1
                continue
            modified = _parse_post_datetime(post, "modified_gmt", "modified", "date_gmt", "date")
            if modified is None:
                skip_counter["outside_edit_window"] += 1
                continue
            candidates.append({
                "post_id": int(post["id"]),
                "modified_at": modified,
            })

        page += 1

    # Ordering is intentionally applied only after every page has been collected.
    candidates.sort(key=lambda item: (item["modified_at"], item["post_id"]))
    return candidates, "draft_list_paginated", stats, skip_counter


def _put_content_only(wp, post_id: int, new_body: str) -> None:
    wp.update_post_fields(post_id, content=new_body)


def _guard_fail_label(exit_code: int) -> str:
    return {
        10: "guard_a",
        11: "guard_b",
        12: "guard_c",
    }.get(exit_code, "guard_unknown")


def _append_skip_outcome(
    outcomes: list[dict[str, Any]],
    skip_counter: Counter[str],
    *,
    post_id: int,
    reason: str,
) -> None:
    skip_counter[reason] += 1
    outcomes.append({
        "post_id": post_id,
        "verdict": "skip",
        "skip_reason": reason,
    })


def _build_aggregate_counts(
    *,
    candidates_before_filter: int,
    list_level_skips: int,
    eligible_candidates: int,
    selected_count: int,
    pages_fetched: int,
    per_post_outcomes: list[dict[str, Any]],
) -> dict[str, int]:
    verdict_counts = Counter(item.get("verdict") for item in per_post_outcomes)
    return {
        "list_seen": candidates_before_filter,
        "list_level_skips": list_level_skips,
        "eligible_after_list_filters": eligible_candidates,
        "selected_for_processing": selected_count,
        "processed": len(per_post_outcomes),
        "edited": verdict_counts["edited"],
        "guard_fail": verdict_counts["guard_fail"],
        "processed_skip": verdict_counts["skip"],
        "pages_fetched": pages_fetched,
    }


def _build_summary_payload(
    *,
    candidates: int,
    put_ok: int,
    reject: int,
    skip: int,
    stop_reason: str,
    next_run_hint: str,
    fetch_mode: str,
    candidates_before_filter: int,
    skip_reason_counts: dict[str, int],
    per_post_outcomes: list[dict[str, Any]],
    aggregate_counts: dict[str, int],
    edit_window_jst: str,
) -> dict[str, Any]:
    return {
        "candidates": candidates,
        "candidates_before_filter": candidates_before_filter,
        "skip_reason_counts": dict(skip_reason_counts),
        "put_ok": put_ok,
        "reject": reject,
        "skip": skip,
        "stop_reason": stop_reason,
        "next_run_hint": next_run_hint,
        "fetch_mode": fetch_mode,
        "per_post_outcomes": list(per_post_outcomes),
        "aggregate_counts": dict(aggregate_counts),
        "edit_window_jst": edit_window_jst,
        "current_quiet_hours_before_change": LEGACY_QUIET_HOURS_JST,
    }


def _emit_summary(now: datetime, payload: dict[str, Any]) -> None:
    _append_session_log(now, {"event": "lane_run", **payload})
    print(json.dumps(payload, ensure_ascii=False))


def _exit_code_for_stop_reason(stop_reason: str) -> int:
    return {
        "wp_init_failed": EXIT_WP_GET_FAILED,
        "wp_pagination_failed": EXIT_WP_GET_FAILED,
        "wp_get_failed": EXIT_WP_GET_FAILED,
        "input_error": EXIT_INPUT_ERROR,
        "reject_streak": EXIT_REJECT_STREAK,
        "api_fail": EXIT_API_FAIL,
        "put_fail": EXIT_PUT_FAIL,
    }.get(stop_reason, 0)


def _emit_run_result(
    now: datetime,
    *,
    candidates: list[dict[str, Any]],
    candidates_before_filter: int,
    list_skip_counter: Counter[str],
    process_skip_counter: Counter[str],
    per_post_outcomes: list[dict[str, Any]],
    put_ok: int,
    reject_count: int,
    stop_reason: str,
    next_run_hint: str,
    fetch_mode: str,
    selected_count: int,
    pages_fetched: int,
    edit_window_jst: str,
) -> None:
    total_skip_counter = list_skip_counter + process_skip_counter
    payload = _build_summary_payload(
        candidates=len(candidates),
        put_ok=put_ok,
        reject=reject_count,
        skip=sum(total_skip_counter.values()),
        stop_reason=stop_reason,
        next_run_hint=next_run_hint,
        fetch_mode=fetch_mode,
        candidates_before_filter=candidates_before_filter,
        skip_reason_counts=dict(sorted(total_skip_counter.items())),
        per_post_outcomes=per_post_outcomes,
        aggregate_counts=_build_aggregate_counts(
            candidates_before_filter=candidates_before_filter,
            list_level_skips=sum(list_skip_counter.values()),
            eligible_candidates=len(candidates),
            selected_count=selected_count,
            pages_fetched=pages_fetched,
            per_post_outcomes=per_post_outcomes,
        ),
        edit_window_jst=edit_window_jst,
    )
    _emit_summary(now, payload)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    now = _now_jst(args.now_iso)
    ledger_path = _resolve_ledger_path(args.ledger_path, now=now)
    queue_path = Path(args.queue_path) if args.queue_path.strip() else None
    per_post_outcomes: list[dict[str, Any]] = []
    empty_counter: Counter[str] = Counter()

    try:
        edit_window_start, edit_window_end, edit_window_jst = _resolve_edit_window(args)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        payload = _build_summary_payload(
            candidates=0,
            put_ok=0,
            reject=0,
            skip=0,
            stop_reason="input_error",
            next_run_hint="fix CLI args before retry",
            fetch_mode="none",
            candidates_before_filter=0,
            skip_reason_counts={},
            per_post_outcomes=[],
            aggregate_counts={
                "list_seen": 0,
                "list_level_skips": 0,
                "eligible_after_list_filters": 0,
                "selected_for_processing": 0,
                "processed": 0,
                "edited": 0,
                "guard_fail": 0,
                "processed_skip": 0,
                "pages_fetched": 0,
            },
            edit_window_jst=f"{DEFAULT_EDIT_WINDOW_START_JST}-{DEFAULT_EDIT_WINDOW_END_JST} JST",
        )
        _emit_summary(now, payload)
        return EXIT_INPUT_ERROR

    if args.max_posts <= 0:
        print("--max-posts must be a positive integer", file=sys.stderr)
        payload = _build_summary_payload(
            candidates=0,
            put_ok=0,
            reject=0,
            skip=0,
            stop_reason="input_error",
            next_run_hint="fix CLI args before retry",
            fetch_mode="none",
            candidates_before_filter=0,
            skip_reason_counts={},
            per_post_outcomes=[],
            aggregate_counts={
                "list_seen": 0,
                "list_level_skips": 0,
                "eligible_after_list_filters": 0,
                "selected_for_processing": 0,
                "processed": 0,
                "edited": 0,
                "guard_fail": 0,
                "processed_skip": 0,
                "pages_fetched": 0,
            },
            edit_window_jst=edit_window_jst,
        )
        _emit_summary(now, payload)
        return EXIT_INPUT_ERROR

    if not _is_within_time_window(now, edit_window_start, edit_window_end):
        payload = _build_summary_payload(
            candidates=0,
            put_ok=0,
            reject=0,
            skip=0,
            stop_reason="quiet_hours",
            next_run_hint="next hourly run",
            fetch_mode="none",
            candidates_before_filter=0,
            skip_reason_counts={},
            per_post_outcomes=[],
            aggregate_counts={
                "list_seen": 0,
                "list_level_skips": 0,
                "eligible_after_list_filters": 0,
                "selected_for_processing": 0,
                "processed": 0,
                "edited": 0,
                "guard_fail": 0,
                "processed_skip": 0,
                "pages_fetched": 0,
            },
            edit_window_jst=edit_window_jst,
        )
        _emit_summary(now, payload)
        return 0

    wp = None
    if queue_path is None:
        try:
            wp = _make_wp_client()
        except Exception as e:
            print(f"failed to init WP client: {e}", file=sys.stderr)
            payload = _build_summary_payload(
                candidates=0,
                put_ok=0,
                reject=0,
                skip=0,
                stop_reason="wp_init_failed",
                next_run_hint="fix WP env before retry",
                fetch_mode="none",
                candidates_before_filter=0,
                skip_reason_counts={},
                per_post_outcomes=[],
                aggregate_counts={
                    "list_seen": 0,
                    "list_level_skips": 0,
                    "eligible_after_list_filters": 0,
                    "selected_for_processing": 0,
                    "processed": 0,
                    "edited": 0,
                    "guard_fail": 0,
                    "processed_skip": 0,
                    "pages_fetched": 0,
                },
                edit_window_jst=edit_window_jst,
            )
            _emit_summary(now, payload)
            return EXIT_WP_GET_FAILED

        touched_ids = _read_recent_touched_post_ids(now)
        candidates, fetch_mode, pagination_stats, list_skip_counter = _collect_paginated_candidates(
            wp,
            now=now,
            touched_ids=touched_ids,
        )
    else:
        try:
            candidates, fetch_mode, pagination_stats, list_skip_counter = _collect_queue_candidates(queue_path)
        except (OSError, ValueError) as e:
            print(f"failed to load queue-path: {e}", file=sys.stderr)
            payload = _build_summary_payload(
                candidates=0,
                put_ok=0,
                reject=0,
                skip=0,
                stop_reason="input_error",
                next_run_hint="fix CLI args before retry",
                fetch_mode=QUEUE_FETCH_MODE,
                candidates_before_filter=0,
                skip_reason_counts={},
                per_post_outcomes=[],
                aggregate_counts={
                    "list_seen": 0,
                    "list_level_skips": 0,
                    "eligible_after_list_filters": 0,
                    "selected_for_processing": 0,
                    "processed": 0,
                    "edited": 0,
                    "guard_fail": 0,
                    "processed_skip": 0,
                    "pages_fetched": 0,
                },
                edit_window_jst=edit_window_jst,
            )
            _emit_summary(now, payload)
            return EXIT_INPUT_ERROR
    candidates_before_filter = pagination_stats["posts_seen"]
    if candidates is None:
        _emit_run_result(
            now,
            candidates=[],
            candidates_before_filter=candidates_before_filter,
            list_skip_counter=list_skip_counter,
            process_skip_counter=empty_counter,
            per_post_outcomes=[],
            put_ok=0,
            reject_count=0,
            stop_reason="wp_pagination_failed",
            next_run_hint="check WP access / pagination retry",
            fetch_mode=fetch_mode,
            selected_count=0,
            pages_fetched=pagination_stats["pages_fetched"],
            edit_window_jst=edit_window_jst,
        )
        return EXIT_WP_GET_FAILED

    selected_candidates = candidates[: args.max_posts]
    selected_count = len(selected_candidates)
    if queue_path is not None and not args.dry_run:
        try:
            wp = _make_wp_client()
        except Exception as e:
            print(f"failed to init WP client: {e}", file=sys.stderr)
            payload = _build_summary_payload(
                candidates=0,
                put_ok=0,
                reject=0,
                skip=0,
                stop_reason="wp_init_failed",
                next_run_hint="fix WP env before retry",
                fetch_mode=fetch_mode,
                candidates_before_filter=candidates_before_filter,
                skip_reason_counts={},
                per_post_outcomes=[],
                aggregate_counts={
                    "list_seen": 0,
                    "list_level_skips": 0,
                    "eligible_after_list_filters": 0,
                    "selected_for_processing": 0,
                    "processed": 0,
                    "edited": 0,
                    "guard_fail": 0,
                    "processed_skip": 0,
                    "pages_fetched": 0,
                },
                edit_window_jst=edit_window_jst,
            )
            _emit_summary(now, payload)
            return EXIT_WP_GET_FAILED

    if not candidates:
        _emit_run_result(
            now,
            candidates=candidates,
            candidates_before_filter=candidates_before_filter,
            list_skip_counter=list_skip_counter,
            process_skip_counter=empty_counter,
            per_post_outcomes=[],
            put_ok=0,
            reject_count=0,
            stop_reason="no_candidate",
            next_run_hint="next hourly run",
            fetch_mode=fetch_mode,
            selected_count=selected_count,
            pages_fetched=pagination_stats["pages_fetched"],
            edit_window_jst=edit_window_jst,
        )
        return 0

    process_skip_counter: Counter[str] = Counter()
    put_ok = 0
    reject_count = 0
    reject_streak = 0
    put_fail_count = 0
    stop_reason = "completed"

    for candidate_ref in selected_candidates:
        post_id = candidate_ref["post_id"]
        post = candidate_ref.get("post")
        if post is None:
            try:
                post = wp.get_post(post_id)
            except Exception as e:
                print(f"failed to get WP post_id={post_id}: {e}", file=sys.stderr)
                _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=post_id, reason="wp_get_failed")
                stop_reason = "wp_get_failed"
                break

        if _resolved_live_update(post):
            _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=post_id, reason="live_update_excluded")
            continue

        candidate = None
        if queue_path is None:
            ok, reason = _draft_looks_editable(post, now, set())
            if not ok:
                _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=post_id, reason=reason)
                continue
            candidate = _build_candidate(post)
        else:
            candidate, reason = _build_queue_candidate(post)
            if candidate is None:
                _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=post_id, reason=reason)
                continue

        if args.provider != "gemini":
            try:
                exec_code, exec_payload, exec_stderr, new_body = _run_fallback_controller(
                    candidate,
                    provider=args.provider,
                    ledger_path=ledger_path,
                    dry_run=bool(args.dry_run),
                )
            except (
                repair_provider_ledger.LedgerLockError,
                repair_provider_ledger.LedgerWriteError,
                ValueError,
                OSError,
            ) as e:
                print(f"failed to run fallback controller post_id={post_id}: {e}", file=sys.stderr)
                _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=post_id, reason="input_error")
                stop_reason = "input_error"
                break

            if exec_code in {10, 11, 12}:
                reject_count += 1
                per_post_outcomes.append({
                    "post_id": candidate["post_id"],
                    "verdict": "guard_fail",
                    "guard_fail": _guard_fail_label(exec_code),
                })
                _append_session_log(
                    now,
                    {
                        "event": "editor_reject",
                        "post_id": candidate["post_id"],
                        "provider": args.provider,
                        "subtype": candidate["subtype"],
                        "fail_axes": candidate["fail_axes"],
                        "editor_exit": exec_code,
                        "violation": exec_stderr,
                        "put_status": "skipped",
                    },
                )
                continue

            if exec_code == 20:
                _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=candidate["post_id"], reason="api_fail")
                _append_session_log(
                    now,
                    {
                        "event": "editor_api_fail",
                        "post_id": candidate["post_id"],
                        "provider": args.provider,
                        "subtype": candidate["subtype"],
                        "editor_exit": exec_code,
                        "violation": exec_stderr,
                        "put_status": "skipped",
                    },
                )
                stop_reason = "api_fail"
                break

            if exec_code == 30 or new_body is None or exec_payload is None:
                _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=candidate["post_id"], reason="input_error")
                _append_session_log(
                    now,
                    {
                        "event": "editor_input_error",
                        "post_id": candidate["post_id"],
                        "provider": args.provider,
                        "subtype": candidate["subtype"],
                        "editor_exit": exec_code,
                        "violation": exec_stderr or "missing_output",
                        "put_status": "skipped",
                    },
                )
                stop_reason = "input_error"
                break

            put_status = "dry_run"
            wp_write_allowed = bool(exec_payload.get("wp_write_allowed", True))
            if not args.dry_run:
                if not wp_write_allowed:
                    put_status = "shadow_only"
                else:
                    try:
                        _put_content_only(wp, candidate["post_id"], new_body)
                        put_status = "ok"
                    except Exception as e:
                        put_fail_count += 1
                        _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=candidate["post_id"], reason="put_fail")
                        _append_session_log(
                            now,
                            {
                                "event": "put_fail",
                                "post_id": candidate["post_id"],
                                "provider": args.provider,
                                "subtype": candidate["subtype"],
                                "fail_axes": candidate["fail_axes"],
                                "put_status": f"error:{type(e).__name__}",
                                "violation": str(e),
                            },
                        )
                        if put_fail_count >= 2:
                            stop_reason = "put_fail"
                            break
                        continue

            put_ok += 1
            per_post_outcomes.append({
                "post_id": candidate["post_id"],
                "verdict": "edited",
                "edited": put_status,
            })
            _append_session_log(
                now,
                {
                    "event": "put_ok" if put_status == "ok" else ("shadow_only" if put_status == "shadow_only" else "dry_run"),
                    "post_id": candidate["post_id"],
                    "provider": exec_payload.get("provider"),
                    "fallback_used": exec_payload.get("fallback_used"),
                    "subtype": candidate["subtype"],
                    "fail_axes": candidate["fail_axes"],
                    "chars_before": candidate["chars_before"],
                    "chars_after": len(new_body),
                    "guards": exec_payload.get("guards"),
                    "put_status": put_status,
                },
            )
            continue

        dry_code, _, dry_stderr, _ = _run_editor(
            candidate,
            dry_run=True,
            ledger_path=ledger_path,
            now=now,
        )
        if dry_code in {10, 11, 12}:
            reject_count += 1
            reject_streak += 1
            per_post_outcomes.append({
                "post_id": candidate["post_id"],
                "verdict": "guard_fail",
                "guard_fail": _guard_fail_label(dry_code),
            })
            _append_session_log(
                now,
                {
                    "event": "editor_reject",
                    "post_id": candidate["post_id"],
                    "subtype": candidate["subtype"],
                    "fail_axes": candidate["fail_axes"],
                    "editor_exit": dry_code,
                    "violation": dry_stderr,
                    "put_status": "skipped",
                },
            )
            if reject_streak >= 3:
                stop_reason = "reject_streak"
                break
            continue

        if dry_code == 20:
            retry_code, _, retry_stderr, _ = _run_editor(
                candidate,
                dry_run=True,
                ledger_path=ledger_path,
                now=now,
            )
            if retry_code != 0:
                _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=candidate["post_id"], reason="api_fail")
                _append_session_log(
                    now,
                    {
                        "event": "editor_api_fail",
                        "post_id": candidate["post_id"],
                        "subtype": candidate["subtype"],
                        "editor_exit": retry_code,
                        "violation": retry_stderr,
                        "put_status": "skipped",
                    },
                )
                stop_reason = "api_fail"
                break
        elif dry_code == 30:
            _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=candidate["post_id"], reason="input_error")
            _append_session_log(
                now,
                {
                    "event": "editor_input_error",
                    "post_id": candidate["post_id"],
                    "subtype": candidate["subtype"],
                    "editor_exit": dry_code,
                    "violation": dry_stderr,
                    "put_status": "skipped",
                },
            )
            stop_reason = "input_error"
            break

        reject_streak = 0

        exec_code, exec_payload, exec_stderr, new_body = _run_editor(
            candidate,
            dry_run=False,
            ledger_path=ledger_path,
            now=now,
        )
        if exec_code in {10, 11, 12}:
            reject_count += 1
            per_post_outcomes.append({
                "post_id": candidate["post_id"],
                "verdict": "guard_fail",
                "guard_fail": _guard_fail_label(exec_code),
            })
            _append_session_log(
                now,
                {
                    "event": "editor_reject",
                    "post_id": candidate["post_id"],
                    "subtype": candidate["subtype"],
                    "fail_axes": candidate["fail_axes"],
                    "editor_exit": exec_code,
                    "violation": exec_stderr,
                    "put_status": "skipped",
                },
            )
            continue

        if exec_code == 20:
            _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=candidate["post_id"], reason="api_fail")
            _append_session_log(
                now,
                {
                    "event": "editor_api_fail",
                    "post_id": candidate["post_id"],
                    "subtype": candidate["subtype"],
                    "editor_exit": exec_code,
                    "violation": exec_stderr,
                    "put_status": "skipped",
                },
            )
            stop_reason = "api_fail"
            break

        if exec_code == 30 or new_body is None or exec_payload is None:
            _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=candidate["post_id"], reason="input_error")
            _append_session_log(
                now,
                {
                    "event": "editor_input_error",
                    "post_id": candidate["post_id"],
                    "subtype": candidate["subtype"],
                    "editor_exit": exec_code,
                    "violation": exec_stderr or "missing_output",
                    "put_status": "skipped",
                },
            )
            stop_reason = "input_error"
            break

        put_status = "dry_run"
        if not args.dry_run:
            try:
                _put_content_only(wp, candidate["post_id"], new_body)
                put_status = "ok"
            except Exception as e:
                put_fail_count += 1
                _append_skip_outcome(per_post_outcomes, process_skip_counter, post_id=candidate["post_id"], reason="put_fail")
                _append_session_log(
                    now,
                    {
                        "event": "put_fail",
                        "post_id": candidate["post_id"],
                        "subtype": candidate["subtype"],
                        "fail_axes": candidate["fail_axes"],
                        "put_status": f"error:{type(e).__name__}",
                        "violation": str(e),
                    },
                )
                if put_fail_count >= 2:
                    stop_reason = "put_fail"
                    break
                continue

        put_ok += 1
        per_post_outcomes.append({
            "post_id": candidate["post_id"],
            "verdict": "edited",
            "edited": put_status,
        })
        _append_session_log(
            now,
            {
                "event": "put_ok" if put_status == "ok" else "dry_run",
                "post_id": candidate["post_id"],
                "subtype": candidate["subtype"],
                "fail_axes": candidate["fail_axes"],
                "chars_before": candidate["chars_before"],
                "chars_after": len(new_body),
                "guards": exec_payload.get("guards"),
                "put_status": put_status,
            },
        )

    next_run_hint = {
        "reject_streak": "Claude review required",
        "api_fail": "Claude review required",
        "input_error": "Claude review required",
        "put_fail": "Claude/user review required",
        "wp_get_failed": "check WP access / post detail",
    }.get(stop_reason, "next hourly run")
    _emit_run_result(
        now,
        candidates=candidates,
        candidates_before_filter=candidates_before_filter,
        list_skip_counter=list_skip_counter,
        process_skip_counter=process_skip_counter,
        per_post_outcomes=per_post_outcomes,
        put_ok=put_ok,
        reject_count=reject_count,
        stop_reason=stop_reason,
        next_run_hint=next_run_hint,
        fetch_mode=fetch_mode,
        selected_count=selected_count,
        pages_fetched=pagination_stats["pages_fetched"],
        edit_window_jst=edit_window_jst,
    )
    return _exit_code_for_stop_reason(stop_reason)


if __name__ == "__main__":
    sys.exit(main())
