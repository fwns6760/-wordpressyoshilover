from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.lineup_source_priority import compute_lineup_dedup
from src.pre_publish_fact_check import extractor
from src.title_body_nucleus_validator import validate_title_body_nucleus


JST = ZoneInfo("Asia/Tokyo")

PRIMARY_SRC_RE = re.compile(
    r"(Yahoo!プロ野球|報知|スポーツナビ|日刊スポーツ|スポニチ|デイリー|サンケイ|スポーツ報知|読売新聞)"
)
SPECULATIVE_TITLE_RE = re.compile(
    r"(どう見[るた]|どこを|どこへ|どこか|見たい|見せ[るたい]|予想|気になる|狙いはどこ|何を|どんな|"
    r"どう並べ|どう動く|どう攻め|どう戦|誰だ|どう打|どう起用|どうな[るた]|なぜ|何が|[？?]|"
    r"ポイント[はが]|順調ならば|週明けにも.*か$)"
)
INJURY_DEATH_RE = re.compile(
    r"(故障|離脱|登録抹消|抹消|コンディション不良|アクシデント|復帰|亡くな|天国|死去|【コメント】|引退|交代|診断|症状|ケガ)"
)
RANKING_LIST_ONLY_RE = re.compile(r"(①.*②|⑤|通算安打.*：|順位.*ranking|NPB通算)", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
H3_RE = re.compile(r"(?is)<h3\b[^>]*>(.*?)</h3>")
NEXT_HEADING_RE = re.compile(r"(?is)<h[1-6]\b[^>]*>")
PRE_BLOCK_RE = re.compile(r"(?is)<pre\b[^>]*>(.*?)</pre>")
CODE_BLOCK_RE = re.compile(r"(?is)<code\b[^>]*>(.*?)</code>")
HEADING_SENTENCE_END_RE = re.compile(
    r"(した|している|していた|と語った|と話した|を確認した|を記録した|と発表した|となった|を達成した)$"
)
PLAYER_HEURISTIC_RE = re.compile(r"([一-龯々]{2,4}(?:投手|捕手|内野手|外野手|選手|監督)?|[A-Za-z]{2,}[0-9]*|[一-龯々]{2,4}[A-Za-z0-9]+)")

SITE_COMPONENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fan_voice", re.compile(r"💬\s*[^。\n]{0,120}")),
    ("related_articles", re.compile(r"【関連記事】")),
    ("fan_voice_label", re.compile(r"💬\s*ファンの声")),
)

LABEL_EXPECTATIONS: dict[str, tuple[re.Pattern[str], ...]] = {
    "試合結果": (re.compile(r"(勝利|敗戦|引き分け|[0-9０-９]+\s*[-－ー]\s*[0-9０-９]+)"),),
    "スタメン": (re.compile(r"(スタメン|先発|オーダー|[1-9１-９]番)"),),
    "出典": (PRIMARY_SRC_RE, re.compile(r"https?://")),
    "関連情報": (re.compile(r"(関連|関連記事|あわせて読みたい|過去記事)"),),
    "ファンの声": (re.compile(r"(ファンの声|SNS|X|コメント)"),),
    "コメント": (re.compile(r"(コメント|語った|話した|発言|述べた)"),),
    "2軍戦": (re.compile(r"(二軍|2軍|２軍|ファーム)"),),
    "今日のポイント": (re.compile(r"(ポイント|注目|鍵|見どころ)"),),
}

OPPONENT_CANONICAL = {
    "DeNA": "DeNA",
    "ＤｅＮＡ": "DeNA",
    "横浜": "DeNA",
    "阪神": "阪神",
    "ヤクルト": "ヤクルト",
    "中日": "中日",
    "広島": "広島",
    "西武": "西武",
    "日本ハム": "日本ハム",
    "楽天": "楽天",
    "ロッテ": "ロッテ",
    "ソフトバンク": "ソフトバンク",
    "オリックス": "オリックス",
}
OPPONENT_RE = re.compile("|".join(re.escape(token) for token in OPPONENT_CANONICAL))


def _strip_html(value: str) -> str:
    text = TAG_RE.sub("\n", value or "")
    text = html.unescape(text).replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _parse_wp_datetime(value: str, *, fallback_now: datetime | None = None) -> datetime:
    if not value:
        return _now_jst(fallback_now)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _normalize_title_key(title: str) -> str:
    return re.sub(r"\s+", "", title or "").strip().lower()


def _build_game_key(record: dict[str, Any]) -> str:
    lane = str(record.get("inferred_subtype") or "other")
    opening = str(record.get("body_text") or "")[:600]
    match = OPPONENT_RE.search(opening)
    opponent = OPPONENT_CANONICAL.get(match.group(0), "unknown") if match else "unknown"
    modified_at = _parse_wp_datetime(str(record.get("modified_at") or ""))
    return f"{lane}/{opponent}/{modified_at.date().isoformat()}"


def _contains_primary_source(record: dict[str, Any]) -> bool:
    body_text = str(record.get("body_text") or "")
    source_block = str(record.get("source_block") or "")
    return bool(PRIMARY_SRC_RE.search(body_text) or PRIMARY_SRC_RE.search(source_block))


def _has_featured_media(raw_post: dict[str, Any]) -> bool:
    try:
        return int(raw_post.get("featured_media") or 0) > 0
    except (TypeError, ValueError):
        return False


def _collect_site_component_flags(body_text: str) -> tuple[list[str], list[str]]:
    red_flags: list[str] = []
    yellow_reasons: list[str] = []
    total_chars = len(body_text)
    if total_chars <= 0:
        return red_flags, yellow_reasons

    positions: list[float] = []
    for _, pattern in SITE_COMPONENT_PATTERNS:
        positions.extend(match.start() / total_chars for match in pattern.finditer(body_text))
    if not positions:
        return red_flags, yellow_reasons

    if any(position < 0.7 for position in positions):
        red_flags.append("site_component_mixed_into_body_middle")
    else:
        yellow_reasons.append("site_component_mixed_into_body_tail")
    return red_flags, yellow_reasons


def _body_for_nucleus_validator(body_html: str) -> str:
    body_text = _strip_html(body_html)
    fallback_lines: list[str] = []
    for line in body_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        fallback_lines.append(stripped)
        if stripped.startswith("参照元"):
            continue
        if re.fullmatch(r"https?://[^\s]+", stripped):
            continue
        if any(pattern.search(stripped) for _, pattern in SITE_COMPONENT_PATTERNS):
            continue
        if _normalize_heading_label(stripped) in LABEL_EXPECTATIONS:
            continue
        if _dev_line_categories(stripped):
            continue
        first_sentence = re.split(r"[。！？]", stripped, maxsplit=1)[0].strip()
        return first_sentence or stripped
    return fallback_lines[0] if fallback_lines else ""


def _normalize_heading_label(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("：", "").replace(":", "").strip()


def _heading_sentence_as_h3_hits(body_html: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for match in H3_RE.finditer(body_html or ""):
        heading_text = _strip_html(match.group(1))
        if len(heading_text) < 30:
            continue
        has_sentence_signal = bool("。" in heading_text or HEADING_SENTENCE_END_RE.search(heading_text))
        if not has_sentence_signal:
            continue
        if not (re.search(r"[0-9０-９]", heading_text) or PLAYER_HEURISTIC_RE.search(heading_text)):
            continue
        hits.append({"type": "heading_sentence_as_h3", "heading": heading_text})
    return hits


def _weird_heading_labels(body_html: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for match in H3_RE.finditer(body_html or ""):
        heading_text = _strip_html(match.group(1))
        label = _normalize_heading_label(heading_text)
        expectations = LABEL_EXPECTATIONS.get(label)
        if expectations is None:
            continue
        next_heading = NEXT_HEADING_RE.search(body_html, match.end())
        section_html = body_html[match.end() : next_heading.start() if next_heading else len(body_html)]
        section_text = _strip_html(section_html)
        if len(section_text) < 20:
            continue
        if any(pattern.search(section_text) for pattern in expectations):
            continue
        findings.append({"type": "weird_heading_label", "heading": heading_text})
    return findings


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


def _build_block_detail(block_type: str, lines: list[str], categories: set[str]) -> dict[str, Any]:
    preview = "\n".join(lines[:5]).strip()
    return {
        "block_type": block_type,
        "line_count": len(lines),
        "categories": sorted(categories),
        "preview": preview,
    }


def _detect_dev_log_blocks(body_html: str, body_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
            detail = _build_block_detail(block_type, block_lines, categories)
            if len(block_lines) >= 5 and len(categories) >= 2:
                clear_blocks.append(detail)
            elif len(categories) >= 2 or "code_block" in categories:
                scattered_blocks.append(detail)

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    block_lines: list[str] = []
    block_categories: set[str] = set()
    for line in lines + [""]:
        categories = _dev_line_categories(line)
        if categories:
            block_lines.append(line)
            block_categories.update(categories)
            continue
        if not block_lines:
            continue
        detail = _build_block_detail("line_block", block_lines, block_categories)
        if len(block_lines) >= 5 and len(block_categories) >= 2:
            clear_blocks.append(detail)
        elif block_categories:
            scattered_blocks.append(detail)
        block_lines = []
        block_categories = set()
    return clear_blocks, scattered_blocks


def _evaluate_record(raw_post: dict[str, Any]) -> dict[str, Any]:
    record = extractor.extract_post_record(raw_post)
    title = str(record.get("title") or "")
    body_html = str(record.get("body_html") or "")
    body_text = str(record.get("body_text") or "")
    modified = str(record.get("modified_at") or "")
    game_key = _build_game_key(record)

    red_flags: list[str] = []
    yellow_reasons: list[str] = []
    cleanup_details: list[dict[str, Any]] = []

    if not _has_featured_media(raw_post):
        yellow_reasons.append("missing_featured_media")
    if not _contains_primary_source(record):
        yellow_reasons.append("missing_primary_source")
    if SPECULATIVE_TITLE_RE.search(title):
        red_flags.append("speculative_title")
    if INJURY_DEATH_RE.search(title) or INJURY_DEATH_RE.search(body_text):
        red_flags.append("injury_death")
    if RANKING_LIST_ONLY_RE.search(body_text):
        red_flags.append("ranking_list_only")

    site_red, site_yellow = _collect_site_component_flags(body_text)
    red_flags.extend(site_red)
    yellow_reasons.extend(site_yellow)

    nucleus_result = validate_title_body_nucleus(
        title,
        _body_for_nucleus_validator(body_html),
        str(record.get("inferred_subtype") or ""),
    )
    if not nucleus_result.aligned:
        red_flags.append("title_body_mismatch")

    heading_hits = _heading_sentence_as_h3_hits(body_html)
    cleanup_details.extend(heading_hits)

    weird_label_hits = _weird_heading_labels(body_html)
    if weird_label_hits:
        yellow_reasons.append("weird_heading_label")

    dev_log_blocks, scattered_dev_logs = _detect_dev_log_blocks(body_html, body_text)
    for detail in dev_log_blocks:
        cleanup_details.append({"type": "dev_log_contamination", **detail})
    if scattered_dev_logs and not dev_log_blocks:
        red_flags.append("dev_log_contamination_scattered")

    red_flags = list(dict.fromkeys(red_flags))
    yellow_reasons = list(dict.fromkeys(yellow_reasons))
    cleanup_types = list(dict.fromkeys(detail["type"] for detail in cleanup_details))

    entry = {
        "post_id": int(record["post_id"]),
        "title": title,
        "modified": modified,
        "game_key": game_key,
    }

    if red_flags:
        entry["red_flags"] = red_flags
        if "title_body_mismatch" in red_flags:
            entry["nucleus_reason_code"] = nucleus_result.reason_code
        return {
            "judgment": "red",
            "entry": entry,
            "cleanup_candidate": None,
        }

    if yellow_reasons:
        entry["yellow_reasons"] = yellow_reasons
        entry["needs_hallucinate_re_evaluation"] = True
        cleanup_candidate = None
        if cleanup_types:
            cleanup_candidate = {
                "post_id": entry["post_id"],
                "title": title,
                "game_key": game_key,
                "cleanup_types": cleanup_types,
                "details": cleanup_details,
                "post_judgment": "yellow",
            }
        return {
            "judgment": "yellow",
            "entry": entry,
            "cleanup_candidate": cleanup_candidate,
        }

    entry["needs_hallucinate_re_evaluation"] = True
    entry["reason_summary"] = "featured_media, primary_source, title_body_aligned"
    cleanup_candidate = None
    if cleanup_types:
        cleanup_candidate = {
            "post_id": entry["post_id"],
            "title": title,
            "game_key": game_key,
            "cleanup_types": cleanup_types,
            "details": cleanup_details,
            "post_judgment": "green",
        }
    return {
        "judgment": "green",
        "entry": entry,
        "cleanup_candidate": cleanup_candidate,
    }


def _lineup_red_flags(decision: dict[str, Any] | None) -> list[str]:
    if not decision:
        return []
    status = str(decision.get("status") or "").strip().lower()
    if status == "duplicate_absorbed":
        return ["lineup_duplicate_absorbed_by_hochi"]
    if status == "deferred":
        return ["lineup_no_hochi_source"]
    if status == "prefix_violation":
        return ["lineup_prefix_misuse"]
    return []


def _merge_lineup_decision(entry: dict[str, Any], decision: dict[str, Any] | None) -> dict[str, Any]:
    if not decision:
        return entry
    merged = dict(entry)
    merged["lineup_priority_status"] = decision.get("status")
    merged["lineup_priority_reason"] = decision.get("reason")
    for key in (
        "candidate_key",
        "game_id",
        "source_url",
        "source_name",
        "source_domain",
        "is_hochi_source",
        "representative_post_id",
        "representative_source_url",
        "subtype",
    ):
        value = decision.get(key)
        if value not in (None, ""):
            merged[key] = value
    return merged


def _apply_lineup_guard(
    evaluated: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    merged_entry = _merge_lineup_decision(evaluated["entry"], decision)
    extra_red_flags = _lineup_red_flags(decision)
    if not extra_red_flags:
        return {
            "judgment": evaluated["judgment"],
            "entry": merged_entry,
            "cleanup_candidate": evaluated["cleanup_candidate"],
        }

    entry = dict(merged_entry)
    existing_flags = list(entry.get("red_flags") or [])
    entry["red_flags"] = list(dict.fromkeys(existing_flags + extra_red_flags))
    entry.pop("reason_summary", None)
    cleanup_candidate = None
    return {
        "judgment": "red",
        "entry": entry,
        "cleanup_candidate": cleanup_candidate,
    }


def _published_today_keys(raw_posts: list[dict[str, Any]], *, now: datetime) -> tuple[set[str], set[str]]:
    title_keys: set[str] = set()
    game_keys: set[str] = set()
    today = _now_jst(now).date()
    for raw_post in raw_posts:
        record = extractor.extract_post_record(raw_post)
        published_at = _parse_wp_datetime(str(raw_post.get("date") or record.get("created_at") or ""), fallback_now=now)
        if published_at.date() != today:
            continue
        title_keys.add(_normalize_title_key(str(record.get("title") or "")))
        game_keys.add(_build_game_key(record))
    return title_keys, game_keys


def evaluate_raw_posts(
    raw_posts: list[dict[str, Any]],
    *,
    window_hours: int,
    max_pool: int,
    now: datetime | None = None,
    published_today_raw_posts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now_jst = _now_jst(now)
    cutoff = now_jst - timedelta(hours=max(0, int(window_hours)))
    title_keys: set[str] = set()
    game_keys: set[str] = set()
    if published_today_raw_posts:
        title_keys, game_keys = _published_today_keys(published_today_raw_posts, now=now_jst)

    green: list[dict[str, Any]] = []
    yellow: list[dict[str, Any]] = []
    red: list[dict[str, Any]] = []
    cleanup_candidates: list[dict[str, Any]] = []

    filtered: list[dict[str, Any]] = []
    for raw_post in raw_posts[: max(0, int(max_pool))]:
        record = extractor.extract_post_record(raw_post)
        modified_at = _parse_wp_datetime(str(record.get("modified_at") or ""), fallback_now=now_jst)
        if modified_at < cutoff:
            continue
        if title_keys or game_keys:
            title_key = _normalize_title_key(str(record.get("title") or ""))
            game_key = _build_game_key(record)
            if title_key in title_keys or game_key in game_keys:
                continue
        filtered.append(raw_post)

    lineup_dedup = compute_lineup_dedup(filtered)
    lineup_by_post_id = {
        int(post_id): decision
        for post_id, decision in lineup_dedup.get("by_post_id", {}).items()
        if str(post_id).strip()
    }

    for raw_post in filtered:
        evaluated = _evaluate_record(raw_post)
        decision = lineup_by_post_id.get(int(evaluated["entry"]["post_id"]))
        evaluated = _apply_lineup_guard(evaluated, decision)
        judgment = evaluated["judgment"]
        if judgment == "green":
            green.append(evaluated["entry"])
        elif judgment == "yellow":
            yellow.append(evaluated["entry"])
        else:
            red.append(evaluated["entry"])
        if evaluated["cleanup_candidate"] is not None:
            cleanup_candidates.append(evaluated["cleanup_candidate"])

    cleanup_post_ids = {candidate["post_id"] for candidate in cleanup_candidates}
    report = {
        "scan_meta": {
            "window_hours": int(window_hours),
            "max_pool": int(max_pool),
            "scanned": len(filtered),
            "ts": now_jst.isoformat(),
        },
        "green": green,
        "yellow": yellow,
        "red": red,
        "cleanup_candidates": cleanup_candidates,
        "lineup_dedup": lineup_dedup,
        "summary": {
            "green_count": len(green),
            "yellow_count": len(yellow),
            "red_count": len(red),
            "cleanup_count": len(cleanup_candidates),
            "publishable_count": len(green) + len(yellow),
            "publishable_minus_cleanup_pending": (len(green) + len(yellow)) - len(cleanup_post_ids),
            "lineup_representative_count": int(lineup_dedup["summary"]["representative_count"]),
            "lineup_duplicate_absorbed_count": int(lineup_dedup["summary"]["duplicate_absorbed_count"]),
            "lineup_deferred_count": int(lineup_dedup["summary"]["deferred_count"]),
            "lineup_prefix_violation_count": int(lineup_dedup["summary"]["prefix_violation_count"]),
        },
    }
    return report


def scan_wp_drafts(
    wp_client,
    *,
    window_hours: int,
    max_pool: int,
    exclude_published_today: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    scan_limit = max(1, min(int(max_pool), 100))
    raw_posts = wp_client.list_posts(
        status="draft",
        per_page=scan_limit,
        orderby="modified",
        order="desc",
        context="edit",
    )
    published_today_raw_posts: list[dict[str, Any]] | None = None
    if exclude_published_today:
        published_today_raw_posts = wp_client.list_posts(
            status="publish",
            per_page=scan_limit,
            orderby="date",
            order="desc",
            context="edit",
        )
    return evaluate_raw_posts(
        list(raw_posts or []),
        window_hours=window_hours,
        max_pool=scan_limit,
        now=now,
        published_today_raw_posts=list(published_today_raw_posts or []),
    )


def render_human_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    scan_meta = report["scan_meta"]
    lines = [
        "Guarded Publish Evaluator Dry Run",
        f"window_hours={scan_meta['window_hours']}  max_pool={scan_meta['max_pool']}  scanned={scan_meta['scanned']}  ts={scan_meta['ts']}",
        "",
        "Summary",
        "status   count",
        f"green    {summary['green_count']}",
        f"yellow   {summary['yellow_count']}",
        f"red      {summary['red_count']}",
        f"cleanup  {summary['cleanup_count']}",
        f"publishable {summary['publishable_count']}",
        f"publishable_minus_cleanup_pending {summary['publishable_minus_cleanup_pending']}",
    ]

    for label in ("green", "yellow", "red"):
        lines.extend(["", f"{label.title()} Preview"])
        entries = report[label]
        if not entries:
            lines.append("- none")
            continue
        for entry in entries[:5]:
            flags = entry.get("yellow_reasons") or entry.get("red_flags") or []
            suffix = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"- {entry['post_id']} | {entry['title']}{suffix}")
    return "\n".join(lines) + "\n"


def dump_report(report: dict[str, Any], *, fmt: str) -> str:
    if fmt == "human":
        return render_human_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report(report: dict[str, Any], *, fmt: str, output_path: str | None) -> str:
    rendered = dump_report(report, fmt=fmt)
    if output_path:
        Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


__all__ = [
    "dump_report",
    "evaluate_raw_posts",
    "render_human_report",
    "scan_wp_drafts",
    "write_report",
]
