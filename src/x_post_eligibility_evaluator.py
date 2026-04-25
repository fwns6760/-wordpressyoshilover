from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from src import guarded_publish_evaluator as publish_gate
from src.lineup_source_priority import compute_lineup_dedup
from src.pre_publish_fact_check import extractor
from src.title_body_nucleus_validator import validate_title_body_nucleus


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_LIMIT = 50
HUMAN_PREVIEW_LIMIT = 5
NO_LIMIT_WINDOW_HOURS = 24 * 365 * 20

WHY_ELIGIBLE_ALL_GREEN = "all_green_and_x_red_pass"

REFUSE_WP_GATE_YELLOW_PREFIX = "wp_gate_yellow_"
REFUSE_WP_GATE_RED_PREFIX = "wp_gate_red_"
REFUSE_X_SIDE_PRIMARY_SOURCE_WEAK = "x_side_red_primary_source_weak"
REFUSE_X_SIDE_SPECULATIVE_TITLE = "x_side_red_speculative_title"
REFUSE_X_SIDE_TITLE_BODY_MISMATCH = "x_side_red_title_body_mismatch"
REFUSE_X_SIDE_INJURY_DEATH = "x_side_red_injury_death"
REFUSE_X_SIDE_RECENT_DUPLICATE = "x_side_red_recent_x_duplicate_24h"
REFUSE_X_SIDE_417_EQUIVALENT = "x_side_red_same_risk_417"
REFUSE_X_SIDE_RANKING_LIST = "x_side_red_ranking_list_weak_verification"
REFUSE_X_SIDE_QUOTE_HEAVY_WEAK_SOURCE = "x_side_red_quote_heavy_weak_source"

X_DOMAINS = {
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}
QUOTE_RE = re.compile(r"「[^」]{3,80}」")
PLAYER_TOKEN_RE = re.compile(r"([一-龯々]{2,5})(?:投手|捕手|内野手|外野手|選手|監督)?")
PLAYER_TOKEN_STOPWORDS = {
    "巨人",
    "ジャイアンツ",
    "読売",
    "東京",
    "先発",
    "スタメン",
    "試合",
    "結果",
    "勝利",
    "敗戦",
    "引退",
    "登録",
    "抹消",
    "公示",
    "報知",
    "日刊",
    "スポニチ",
    "デイリー",
    "読売新聞",
    "スポーツ報知",
}
BASE_REFUSE_ORDER = (
    REFUSE_X_SIDE_PRIMARY_SOURCE_WEAK,
    REFUSE_X_SIDE_QUOTE_HEAVY_WEAK_SOURCE,
    REFUSE_X_SIDE_417_EQUIVALENT,
    REFUSE_X_SIDE_RECENT_DUPLICATE,
    REFUSE_X_SIDE_SPECULATIVE_TITLE,
    REFUSE_X_SIDE_TITLE_BODY_MISMATCH,
    REFUSE_X_SIDE_INJURY_DEATH,
    REFUSE_X_SIDE_RANKING_LIST,
)
CLEANUP_REASON_MAP = {
    "heading_sentence_as_h3": "x_side_red_cleanup_heading_sentence_as_h3",
    "dev_log_contamination": "x_side_red_cleanup_dev_log_contamination",
    "weird_heading_label": "x_side_red_cleanup_weird_heading_label",
    "site_component_mixed_into_body_middle": "x_side_red_cleanup_site_component_middle",
    "site_component_mixed_into_body_tail": "x_side_red_cleanup_site_component_tail",
}


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _parse_datetime(value: Any, *, fallback_now: datetime | None = None) -> datetime:
    if not value:
        return _now_jst(fallback_now)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _normalize_title_key(title: str) -> str:
    return re.sub(r"\s+", "", title or "").strip().lower()


def _normalize_post_id(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _unique_strings(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _source_urls(record: Mapping[str, Any], entry: Mapping[str, Any]) -> list[str]:
    values = [str(url).strip() for url in (record.get("source_urls") or []) if str(url).strip()]
    for extra in (entry.get("source_url"),):
        if extra:
            values.append(str(extra).strip())
    return _unique_strings(values)


def _source_domains(record: Mapping[str, Any], entry: Mapping[str, Any]) -> list[str]:
    domains: list[str] = []
    for url in _source_urls(record, entry):
        hostname = (urlsplit(url).hostname or "").lower()
        if hostname:
            domains.append(hostname)
    raw_domain = str(entry.get("source_domain") or "").strip().lower()
    if raw_domain:
        domains.append(raw_domain)
    return _unique_strings(domains)


def _has_major_source_marker(record: Mapping[str, Any], entry: Mapping[str, Any]) -> bool:
    joined = "\n".join(
        [
            str(record.get("source_block") or ""),
            str(record.get("body_text") or ""),
            str(entry.get("source_name") or ""),
            str(entry.get("source_domain") or ""),
        ]
    )
    return bool(publish_gate.PRIMARY_SRC_RE.search(joined))


def _primary_source_is_weak(record: Mapping[str, Any], entry: Mapping[str, Any]) -> bool:
    domains = _source_domains(record, entry)
    has_non_x_domain = any(domain not in X_DOMAINS for domain in domains)
    has_major_marker = _has_major_source_marker(record, entry)
    twitter_only = bool(domains) and not has_non_x_domain
    if twitter_only:
        return True
    if has_non_x_domain or has_major_marker:
        return False
    return True


def _quote_count(text: str) -> int:
    return len(QUOTE_RE.findall(text or ""))


def _extract_player_tokens(*texts: str) -> set[str]:
    tokens: set[str] = set()
    for text in texts:
        for match in PLAYER_TOKEN_RE.findall(text or ""):
            candidate = str(match).strip()
            if not candidate or candidate in PLAYER_TOKEN_STOPWORDS:
                continue
            if len(candidate) < 2:
                continue
            tokens.add(candidate)
    return tokens


def _history_player_tokens(item: Mapping[str, Any]) -> set[str]:
    explicit = item.get("player_tokens")
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
        normalized = {str(value).strip() for value in explicit if str(value).strip()}
        if normalized:
            return normalized
    return _extract_player_tokens(str(item.get("title") or ""))


def _is_recent_duplicate(
    *,
    entry: Mapping[str, Any],
    record: Mapping[str, Any],
    recent_x_history: Sequence[Mapping[str, Any]],
    now: datetime,
) -> bool:
    if not recent_x_history:
        return False

    current_post_id = _normalize_post_id(entry.get("post_id"))
    current_title_key = _normalize_title_key(str(entry.get("title") or record.get("title") or ""))
    current_game_key = str(entry.get("game_key") or "")
    current_players = _extract_player_tokens(
        str(entry.get("title") or record.get("title") or ""),
        str(record.get("body_text") or "")[:200],
    )
    cutoff = _now_jst(now) - timedelta(hours=24)

    for item in recent_x_history:
        posted_at = _parse_datetime(item.get("posted_at"), fallback_now=now)
        if posted_at < cutoff:
            continue
        if current_post_id and _normalize_post_id(item.get("post_id")) == current_post_id:
            return True
        if current_game_key and str(item.get("game_key") or "") == current_game_key:
            return True
        if current_title_key and _normalize_title_key(str(item.get("title") or "")) == current_title_key:
            return True
        if current_players and current_players.intersection(_history_player_tokens(item)):
            return True
    return False


def _cleanup_refuse_reasons(cleanup_candidate: Mapping[str, Any] | None) -> list[str]:
    if not cleanup_candidate:
        return []
    cleanup_types = cleanup_candidate.get("cleanup_types") or []
    reasons = [CLEANUP_REASON_MAP[str(cleanup_type)] for cleanup_type in cleanup_types if str(cleanup_type) in CLEANUP_REASON_MAP]
    return _unique_strings(reasons)


def _x_side_refuse_reasons(
    *,
    entry: Mapping[str, Any],
    record: Mapping[str, Any],
    recent_x_history: Sequence[Mapping[str, Any]],
    now: datetime,
) -> list[str]:
    title = str(entry.get("title") or record.get("title") or "")
    body_text = str(record.get("body_text") or "")
    body_html = str(record.get("body_html") or "")
    reasons: list[str] = []

    primary_source_weak = _primary_source_is_weak(record, entry)
    quote_heavy = _quote_count(body_text) >= 2

    if primary_source_weak:
        reasons.append(REFUSE_X_SIDE_PRIMARY_SOURCE_WEAK)
    if publish_gate.SPECULATIVE_TITLE_RE.search(title):
        reasons.append(REFUSE_X_SIDE_SPECULATIVE_TITLE)
    nucleus = validate_title_body_nucleus(
        title,
        publish_gate._body_for_nucleus_validator(body_html),
        str(record.get("inferred_subtype") or ""),
    )
    if not nucleus.aligned:
        reasons.append(REFUSE_X_SIDE_TITLE_BODY_MISMATCH)
    if publish_gate.INJURY_DEATH_RE.search(title) or publish_gate.INJURY_DEATH_RE.search(body_text):
        reasons.append(REFUSE_X_SIDE_INJURY_DEATH)
    if publish_gate.RANKING_LIST_ONLY_RE.search(body_text):
        reasons.append(REFUSE_X_SIDE_RANKING_LIST)
    if quote_heavy and primary_source_weak:
        reasons.append(REFUSE_X_SIDE_QUOTE_HEAVY_WEAK_SOURCE)
        reasons.append(REFUSE_X_SIDE_417_EQUIVALENT)
    if _is_recent_duplicate(entry=entry, record=record, recent_x_history=recent_x_history, now=now):
        reasons.append(REFUSE_X_SIDE_RECENT_DUPLICATE)
    return _sort_reasons(_unique_strings(reasons))


def _sort_reasons(reasons: Sequence[str]) -> list[str]:
    order = {reason: index for index, reason in enumerate(BASE_REFUSE_ORDER)}

    def _key(value: str) -> tuple[int, str]:
        if value in order:
            return (order[value], value)
        if value.startswith(REFUSE_WP_GATE_RED_PREFIX):
            return (100, value)
        if value.startswith(REFUSE_WP_GATE_YELLOW_PREFIX):
            return (200, value)
        if value.startswith("x_side_red_cleanup_"):
            return (300, value)
        return (400, value)

    return sorted(dict.fromkeys(str(reason) for reason in reasons if str(reason)), key=_key)


def _evaluate_publish_gate(raw_posts: Sequence[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    publish_posts = [dict(raw_post) for raw_post in raw_posts if str(raw_post.get("status") or "").lower() == "publish"]
    lineup_dedup = compute_lineup_dedup(publish_posts)
    lineup_by_post_id = {
        int(post_id): decision
        for post_id, decision in lineup_dedup.get("by_post_id", {}).items()
        if str(post_id).strip()
    }

    by_post_id: dict[int, dict[str, Any]] = {}
    cleanup_by_post_id: dict[int, dict[str, Any]] = {}
    for raw_post in publish_posts:
        evaluated = publish_gate._evaluate_record(raw_post)
        evaluated = publish_gate._apply_lineup_guard(
            evaluated,
            lineup_by_post_id.get(int(evaluated["entry"]["post_id"])),
        )
        post_id = int(evaluated["entry"]["post_id"])
        record = extractor.extract_post_record(raw_post)
        by_post_id[post_id] = {
            "raw_post": raw_post,
            "record": record,
            "judgment": evaluated["judgment"],
            "entry": evaluated["entry"],
            "cleanup_candidate": evaluated["cleanup_candidate"],
        }
        if evaluated["cleanup_candidate"] is not None:
            cleanup_by_post_id[post_id] = dict(evaluated["cleanup_candidate"])
    return by_post_id, cleanup_by_post_id


def evaluate_published_posts(
    raw_posts: Sequence[dict[str, Any]],
    *,
    limit: int = DEFAULT_LIMIT,
    orderby: str = "modified",
    order: str = "desc",
    recent_x_history: Sequence[Mapping[str, Any]] | None = None,
    now: datetime | None = None,
    fetched_count: int | None = None,
) -> dict[str, Any]:
    scan_limit = max(1, int(limit))
    now_jst = _now_jst(now)
    selected_posts = [dict(raw_post) for raw_post in raw_posts if str(raw_post.get("status") or "").lower() == "publish"][:scan_limit]
    evaluated_by_post_id, cleanup_by_post_id = _evaluate_publish_gate(selected_posts)
    history = list(recent_x_history or [])

    x_eligible: list[dict[str, Any]] = []
    x_refused: list[dict[str, Any]] = []
    refuse_counter: Counter[str] = Counter()

    for raw_post in selected_posts:
        post_id = int(raw_post.get("id"))
        evaluated = evaluated_by_post_id.get(post_id)
        if evaluated is None:
            continue

        entry = dict(evaluated["entry"])
        record = dict(evaluated["record"])
        title = str(entry.get("title") or record.get("title") or "")
        link = str(raw_post.get("link") or "")
        judgment = str(evaluated["judgment"])

        if judgment == "green":
            reasons = _cleanup_refuse_reasons(cleanup_by_post_id.get(post_id))
            reasons.extend(_x_side_refuse_reasons(entry=entry, record=record, recent_x_history=history, now=now_jst))
            reasons = _sort_reasons(_unique_strings(reasons))
            if reasons:
                x_refused.append(
                    {
                        "post_id": post_id,
                        "title": title,
                        "link": link,
                        "refuse_reasons": reasons,
                    }
                )
                refuse_counter.update(reasons)
                continue

            x_eligible.append(
                {
                    "post_id": post_id,
                    "title": title,
                    "link": link,
                    "why_eligible": WHY_ELIGIBLE_ALL_GREEN,
                }
            )
            continue

        if judgment == "yellow":
            reasons = [
                f"{REFUSE_WP_GATE_YELLOW_PREFIX}{reason}"
                for reason in entry.get("yellow_reasons") or []
            ]
        else:
            reasons = [
                f"{REFUSE_WP_GATE_RED_PREFIX}{reason}"
                for reason in entry.get("red_flags") or []
            ]
        reasons = _sort_reasons(_unique_strings(reasons))
        x_refused.append(
            {
                "post_id": post_id,
                "title": title,
                "link": link,
                "refuse_reasons": reasons,
            }
        )
        refuse_counter.update(reasons)

    summary = {
        "total": len(selected_posts),
        "eligible_count": len(x_eligible),
        "refused_count": len(x_refused),
        "top_refuse_reasons": dict(refuse_counter.most_common()),
    }
    report = {
        "scan_meta": {
            "limit": scan_limit,
            "orderby": orderby,
            "order": order,
            "scanned": len(selected_posts),
            "fetched": int(fetched_count if fetched_count is not None else len(selected_posts)),
            "ts": now_jst.isoformat(),
            "window_hours": NO_LIMIT_WINDOW_HOURS,
        },
        "x_eligible": x_eligible,
        "x_refused": x_refused,
        "summary": summary,
    }
    return report


def scan_wp_published_posts(
    wp_client,
    *,
    limit: int = DEFAULT_LIMIT,
    orderby: str = "modified",
    order: str = "desc",
    recent_x_history: Sequence[Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    scan_limit = max(1, int(limit))
    posts: list[dict[str, Any]] = []
    per_page = min(scan_limit, 100)
    page = 1
    while len(posts) < scan_limit:
        page_posts = wp_client.list_posts(
            status="publish",
            per_page=per_page,
            page=page,
            orderby=orderby,
            order=order,
            context="edit",
        )
        if not page_posts:
            break
        posts.extend(page_posts)
        if len(page_posts) < per_page:
            break
        page += 1

    return evaluate_published_posts(
        posts[:scan_limit],
        limit=scan_limit,
        orderby=orderby,
        order=order,
        recent_x_history=recent_x_history,
        now=now,
        fetched_count=len(posts[:scan_limit]),
    )


def render_human_report(report: Mapping[str, Any]) -> str:
    scan_meta = report["scan_meta"]
    summary = report["summary"]
    lines = [
        "X Post Eligibility Evaluator",
        (
            f"limit={scan_meta['limit']} orderby={scan_meta['orderby']} order={scan_meta['order']} "
            f"scanned={scan_meta['scanned']} ts={scan_meta['ts']}"
        ),
        "",
        "Summary",
        "bucket    count",
        f"eligible  {summary['eligible_count']}",
        f"refused   {summary['refused_count']}",
        f"total     {summary['total']}",
        "",
        "Eligible Preview (top 5)",
    ]
    eligible = report["x_eligible"]
    if eligible:
        for entry in eligible[:HUMAN_PREVIEW_LIMIT]:
            lines.append(f"- {entry['post_id']} | {entry['title']}")
    else:
        lines.append("- none")

    lines.extend(["", "Refused Top Reasons"])
    top_refuse_reasons = summary.get("top_refuse_reasons") or {}
    if top_refuse_reasons:
        for reason, count in top_refuse_reasons.items():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def dump_report(report: Mapping[str, Any], *, fmt: str) -> str:
    if fmt == "human":
        return render_human_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report(report: Mapping[str, Any], *, fmt: str, output_path: str | None) -> str:
    rendered = dump_report(report, fmt=fmt)
    if output_path:
        Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


__all__ = [
    "DEFAULT_LIMIT",
    "WHY_ELIGIBLE_ALL_GREEN",
    "dump_report",
    "evaluate_published_posts",
    "render_human_report",
    "scan_wp_published_posts",
    "write_report",
]
