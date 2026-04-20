"""Dry-run game_state derivation for recent draft posts."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
from wp_client import WPClient

JST = timezone(timedelta(hours=9))
DEFAULT_OUTPUT = Path("/tmp/game_state_derive_2026-04-21.md")
SOURCE_URL_KEYS = ("source_urls", "yl_source_urls", "_yoshilover_source_url", "yl_source_url", "source_url")
PRE_SUBTYPES = {"pregame", "lineup", "farm_lineup"}
LIVE_SUBTYPES = {"live_update", "live_anchor"}
POST_SUBTYPES = {"postgame"}
NULL_SUBTYPES = {"fact_notice"}
TAG_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
URL_RE = re.compile(r'https?://[^\s<>\'\"]+')
TIME_RE = re.compile(r"(?<!\d)(\d{1,2})[:時](\d{2})?(?:分)?")
START_PATTERNS = ((re.compile(r"試合開始"), "試合開始"), (re.compile(r"プレイボール"), "プレイボール"), (re.compile(r"1回[表裏]"), "1回"), (re.compile(r"初回"), "初回"))
CLOSE_PATTERNS = ((re.compile(r"試合終了"), "試合終了"), (re.compile(r"ゲームセット"), "ゲームセット"), (re.compile(r"(?:9|[1-9]\d)回(?:表|裏)?終了"), "9plus_inning_close"), (re.compile(r"延長\s*(?:10|1[1-9]|[2-9]\d)回終了"), "extra_inning_close"))
FARM_RESULT_PATTERNS = (re.compile(r"試合終了"), re.compile(r"ゲームセット"), re.compile(r"勝利|敗戦|引き分け"), re.compile(r"\d+\s*[-−－]\s*\d+"))


def infer_subtype(post: dict) -> str:
    subtype = str(_extract_meta(post).get("article_subtype") or "").strip().lower()
    if subtype:
        return subtype
    text = _clean_text(f"{_title_text(post)} {_body_text(post)}")
    if "公示" in text:
        return "fact_notice"
    if any(token in text for token in ("スタメン", "先発オーダー")):
        return "lineup"
    if re.search(r"\d+回[表裏]?|同点|勝ち越し|速報", text):
        return "live_update"
    if any(token in text for token in ("勝利", "敗戦", "引き分け", "試合終了", "ゲームセット")):
        return "postgame"
    if any(token in text for token in ("2軍", "二軍", "ファーム")):
        return "farm"
    if any(token in text for token in ("予告先発", "見どころ", "プレーボール", "試合前")):
        return "pregame"
    return ""


def detect_start_markers(text: str) -> list[str]:
    return _detect_markers(text, START_PATTERNS)


def detect_close_markers(text: str) -> list[str]:
    return _detect_markers(text, CLOSE_PATTERNS)


def should_transition_pre_to_live(game_start_time: datetime | None, observed_at: datetime | None, text: str) -> bool:
    return bool(game_start_time and observed_at and observed_at >= game_start_time and detect_start_markers(text))


def should_transition_live_to_post(game_start_time: datetime | None, last_update_at: datetime | None, now: datetime, text: str) -> bool:
    if detect_close_markers(text):
        return True
    if not game_start_time or now <= game_start_time + timedelta(hours=5):
        return False
    return last_update_at is None or last_update_at <= game_start_time + timedelta(hours=5)


def derive_game_state_for_post(post: dict, *, now: datetime | None = None) -> dict[str, object]:
    now = now or datetime.now(JST)
    subtype = infer_subtype(post)
    text = _clean_text(f"{_title_text(post)} {_body_text(post)} {' '.join(_extract_source_urls(post))}")
    row = {
        "post_id": post.get("id"),
        "subtype": subtype or None,
        "game_id": _extract_game_id(post),
        "derived_game_state": None,
        "reason_if_null": None,
        "close_marker_hits": detect_close_markers(text),
    }
    if not subtype:
        row["reason_if_null"] = "subtype_unresolved"
    elif subtype in NULL_SUBTYPES:
        row["reason_if_null"] = "subtype_no_game_state"
    elif subtype in PRE_SUBTYPES:
        row["derived_game_state"] = "pre"
    elif subtype in LIVE_SUBTYPES:
        start_time = _resolve_game_start_time(post)
        row["derived_game_state"] = "post" if should_transition_live_to_post(start_time, _modified_jst(post), now, text) else "live"
    elif subtype in POST_SUBTYPES:
        row["derived_game_state"] = "post"
    elif subtype == "farm":
        if _looks_like_farm_result(text):
            row["derived_game_state"] = "post"
        else:
            row["reason_if_null"] = "farm_not_result"
    else:
        row["reason_if_null"] = "subtype_not_supported"
    return row


def load_recent_drafts(max_posts: int, wp: WPClient | None = None) -> list[dict]:
    client = wp or WPClient()
    return client.list_posts(status="draft", per_page=max_posts, page=1, orderby="modified", order="desc", context="edit", fields=["id", "modified", "modified_gmt", "date", "date_gmt", "status", "title", "content", "meta"])


def render_report(rows: list[dict], max_posts: int) -> str:
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "max_posts": max_posts,
        "scanned_posts": len(rows),
        "derived_count": sum(1 for row in rows if row["derived_game_state"]),
        "null_count": sum(1 for row in rows if not row["derived_game_state"]),
        "state_counts": _count_by_key(rows, "derived_game_state"),
        "reason_counts": _count_by_key(rows, "reason_if_null"),
        "subtype_counts": _count_by_key(rows, "subtype"),
    }
    lines = ["# game_state dry-run", "", "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```", "", "| post_id | subtype | game_id | derived_game_state | reason_if_null | close_marker_hits |", "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        hits = "<br>".join(row["close_marker_hits"]) if row["close_marker_hits"] else "-"
        lines.append(f"| {row['post_id']} | {row['subtype'] or '-'} | {row['game_id'] or '-'} | {row['derived_game_state'] or '-'} | {row['reason_if_null'] or '-'} | {hits} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run game_state derivation without WP writes")
    parser.add_argument("--max-posts", type=int, default=30, help="Number of recent drafts to inspect")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Markdown report output path")
    args = parser.parse_args(argv)
    try:
        rows = [derive_game_state_for_post(post) for post in load_recent_drafts(args.max_posts)]
    except Exception as exc:
        print(f"derive_game_state failed: {exc}", file=sys.stderr)
        return 2
    report = render_report(rows, args.max_posts)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


def _title_text(post: dict) -> str:
    title = post.get("title") or {}
    return str(title.get("raw") or title.get("rendered") or "")


def _body_text(post: dict) -> str:
    content = post.get("content") or {}
    return str(content.get("raw") or content.get("rendered") or "")


def _extract_meta(post: dict) -> dict:
    meta = post.get("meta") or {}
    return meta if isinstance(meta, dict) else {}


def _extract_game_id(post: dict) -> str | None:
    value = _extract_meta(post).get("game_id") or post.get("game_id")
    return str(value).strip() if value else None


def _extract_source_urls(post: dict) -> list[str]:
    meta, body, urls = _extract_meta(post), _body_text(post), []
    for key in SOURCE_URL_KEYS:
        value = meta.get(key) if key in meta else post.get(key)
        if isinstance(value, list):
            urls.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            urls.extend(part for part in re.split(r"[\s,]+", str(value)) if part)
    urls.extend(HREF_RE.findall(body))
    urls.extend(URL_RE.findall(body))
    return _dedupe(html.unescape(url) for url in urls if str(url).strip())


def _resolve_game_start_time(post: dict) -> datetime | None:
    meta, reference = _extract_meta(post), _modified_jst(post)
    for key in ("game_start_time", "game_start_at", "scheduled_start_time"):
        resolved = _parse_datetime(meta.get(key), reference)
        if resolved:
            return resolved
    text = _clean_text(f"{_title_text(post)} {_body_text(post)}")
    return _parse_datetime(TIME_RE.search(text).group(0), reference or datetime.now(JST)) if re.search(r"開始|プレイボール|予定", text) and TIME_RE.search(text) else None


def _modified_jst(post: dict) -> datetime | None:
    for field, assume_utc in (("modified_gmt", True), ("date_gmt", True), ("modified", False), ("date", False)):
        raw = str(post.get(field) or "").strip()
        if not raw:
            continue
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc if assume_utc else JST)
        return parsed.astimezone(JST)
    return None


def _parse_datetime(value: object, reference: datetime | None) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        match = TIME_RE.search(raw)
        if not match:
            return None
        base = reference or datetime.now(JST)
        parsed = base.replace(hour=int(match.group(1)), minute=int(match.group(2) or "0"), second=0, microsecond=0)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value or ""))).strip()


def _detect_markers(text: str, patterns) -> list[str]:
    clean, hits = _clean_text(text), []
    for pattern, label in patterns:
        if pattern.search(clean) and label not in hits:
            hits.append(label)
    return hits


def _looks_like_farm_result(text: str) -> bool:
    clean = _clean_text(text)
    return any(pattern.search(clean) for pattern in FARM_RESULT_PATTERNS)


def _count_by_key(rows: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        if value:
            counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _dedupe(items) -> list[str]:
    seen, result = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
