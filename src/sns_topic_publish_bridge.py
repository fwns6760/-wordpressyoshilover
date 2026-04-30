"""Bridge 127 SNS topic draft proposals through the PUB-004 evaluator/runner gate."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from src.guarded_publish_evaluator import evaluate_raw_posts


ROOT = Path(__file__).resolve().parent.parent
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_EVALUATOR_WINDOW_HOURS = 24 * 365 * 10
DEFAULT_MAX_BURST = 20
DEFAULT_BACKUP_DIR = ROOT / "logs" / "cleanup_backup"
DEFAULT_HISTORY_PATH = ROOT / "logs" / "guarded_publish_history.jsonl"
DEFAULT_YELLOW_LOG_PATH = ROOT / "logs" / "guarded_publish_yellow_log.jsonl"
DEFAULT_CLEANUP_LOG_PATH = ROOT / "logs" / "guarded_publish_cleanup_log.jsonl"
HOST_SOURCE_LABELS = {
    "hochi.news": "スポーツ報知",
    "www.hochi.news": "スポーツ報知",
    "nikkansports.com": "日刊スポーツ",
    "www.nikkansports.com": "日刊スポーツ",
    "sponichi.co.jp": "スポニチ",
    "www.sponichi.co.jp": "スポニチ",
    "daily.co.jp": "デイリー",
    "www.daily.co.jp": "デイリー",
    "sanspo.com": "サンケイ",
    "www.sanspo.com": "サンケイ",
    "news.yahoo.co.jp": "Yahoo!プロ野球",
    "sports.yahoo.co.jp": "Yahoo!プロ野球",
    "baseball.yahoo.co.jp": "Yahoo!プロ野球",
    "sportsnavi.yahoo.co.jp": "スポーツナビ",
    "www.giants.jp": "読売新聞",
    "giants.jp": "読売新聞",
}
DEFAULT_SOURCE_LABEL = "スポーツ報知"


def _run_guarded_publish(**kwargs: Any) -> dict[str, Any]:
    from src.guarded_publish_runner import run_guarded_publish

    return run_guarded_publish(**kwargs)


class SyntheticDraftWPClient:
    """Mock-only WP client for bridge tests and dry/live runner reuse."""

    def __init__(self, posts: Mapping[int, Mapping[str, Any]]):
        self.posts = {int(post_id): deepcopy(dict(post)) for post_id, post in posts.items()}
        self.get_post_calls: list[int] = []
        self.update_post_fields_calls: list[dict[str, Any]] = []
        self.update_post_status_calls: list[dict[str, Any]] = []

    def get_post(self, post_id: int) -> dict[str, Any]:
        normalized = int(post_id)
        self.get_post_calls.append(normalized)
        return deepcopy(self.posts[normalized])

    def list_posts(
        self,
        *,
        status: str | Iterable[str] | None = None,
        source_url: str | None = None,
        per_page: int | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        del kwargs

        normalized_source_url = str(source_url or "").strip()
        status_set: set[str] | None
        if isinstance(status, str):
            normalized_status = status.strip().lower()
            status_set = None if not normalized_status or normalized_status == "any" else {normalized_status}
        elif status is None:
            status_set = None
        else:
            status_set = {
                str(item).strip().lower()
                for item in status
                if str(item).strip() and str(item).strip().lower() != "any"
            }
            if not status_set:
                status_set = None

        limit = None if per_page is None else max(0, int(per_page))
        rows: list[dict[str, Any]] = []
        for post_id, payload in self.posts.items():
            post_status = str(payload.get("status") or "").strip().lower()
            if status_set is not None and post_status not in status_set:
                continue

            if normalized_source_url:
                meta = payload.get("meta") or {}
                post_source_url = meta.get("source_url") or payload.get("source_url") or ""
                if str(post_source_url).strip() != normalized_source_url:
                    continue

            row = deepcopy(dict(payload))
            row.setdefault("id", int(post_id))
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
        return rows

    def update_post_fields(self, post_id: int, **fields: Any) -> None:
        normalized = int(post_id)
        self.update_post_fields_calls.append({"post_id": normalized, "fields": deepcopy(fields)})
        post = self.posts[normalized]
        if "status" in fields:
            post["status"] = fields["status"]
        if "content" in fields:
            post["content"] = {"raw": fields["content"], "rendered": fields["content"]}

    def update_post_status(self, post_id: int, status: str) -> None:
        normalized = int(post_id)
        self.update_post_status_calls.append({"post_id": normalized, "status": status})
        self.posts[normalized]["status"] = status

    def debug_snapshot(self) -> dict[str, Any]:
        return {
            "stored_post_ids": sorted(self.posts),
            "get_post_calls": list(self.get_post_calls),
            "get_post_call_count": len(self.get_post_calls),
            "update_post_fields_calls": deepcopy(self.update_post_fields_calls),
            "update_post_fields_call_count": len(self.update_post_fields_calls),
            "update_post_status_calls": deepcopy(self.update_post_status_calls),
            "update_post_status_call_count": len(self.update_post_status_calls),
        }


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"draft_proposals": payload}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: fixture root must be an object or array")
    return payload


def load_source_recheck_output(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    proposals = payload.get("draft_proposals", payload.get("drafts", payload.get("items", [])))
    if not isinstance(proposals, list):
        raise ValueError(f"{path}: draft_proposals must be a list")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(proposals, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"{path}: draft_proposals[{index}] must be an object")
        normalized.append(dict(item))

    output = dict(payload)
    output["draft_proposals"] = normalized
    return output


def _dedupe_urls(values: Sequence[Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        urls.append(text)
    return urls


def _source_label_for_url(url: str) -> str:
    host = urlparse(str(url)).hostname or ""
    return HOST_SOURCE_LABELS.get(host.lower(), DEFAULT_SOURCE_LABEL)


def _build_source_block(source_urls: Sequence[str]) -> str:
    urls = _dedupe_urls(source_urls)
    if not urls:
        return f"<p>参照元: {DEFAULT_SOURCE_LABEL}</p>"
    lines = []
    for index, url in enumerate(urls):
        label = _source_label_for_url(url)
        prefix = "参照元" if index == 0 else "関連 source"
        lines.append(f"<p>{prefix}: {label} {url}</p>")
    return "".join(lines)


def _default_body_html(proposal: Mapping[str, Any]) -> str:
    lead_hint = str(proposal.get("lead_hint") or "").strip()
    if not lead_hint:
        title_hint = str(proposal.get("title_hint") or "巨人の話題を整理").strip()
        lead_hint = f"{title_hint}について、確認済みの事実だけを整理する。"

    detail_paragraph = (
        "確認済みソースの時系列とチーム文脈が追えるように要素を並べ、"
        "未確認の反応や推測ではなく、公開済みの事実関係だけを本文に残す。"
    )
    source_block = _build_source_block(_dedupe_urls(proposal.get("source_urls") or []))
    return f"<p>{lead_hint}</p><p>{detail_paragraph}</p>{source_block}"


def _stable_mock_post_id(mock_draft_id: str) -> int:
    digest = hashlib.sha256(mock_draft_id.encode("utf-8")).hexdigest()[:12]
    return 700000000 + (int(digest, 16) % 200000000)


def _resolve_post_id(proposal: Mapping[str, Any], *, used_ids: set[int]) -> int:
    for key in ("draft_id", "post_id", "wp_draft_id"):
        value = proposal.get(key)
        try:
            post_id = int(value)
        except (TypeError, ValueError):
            continue
        if post_id > 0 and post_id not in used_ids:
            used_ids.add(post_id)
            return post_id

    mock_draft_id = str(proposal.get("mock_draft_id") or "").strip()
    if not mock_draft_id:
        seed = f"{proposal.get('topic_key', '')}:{proposal.get('title_hint', '')}"
        mock_draft_id = f"mock_draft_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    candidate = _stable_mock_post_id(mock_draft_id)
    while candidate in used_ids:
        candidate += 1
    used_ids.add(candidate)
    return candidate


def _synthetic_link(post_id: int, proposal: Mapping[str, Any]) -> str:
    slug = str(proposal.get("mock_draft_id") or f"draft-{post_id}").replace(" ", "-")
    return f"https://yoshilover.com/mock-drafts/{slug}"


def build_synthetic_post(
    proposal: Mapping[str, Any],
    *,
    used_ids: set[int],
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now_jst(now)
    post_id = _resolve_post_id(proposal, used_ids=used_ids)
    title = str(proposal.get("title_hint") or proposal.get("title") or "巨人の話題整理").strip()
    body_html = str(proposal.get("mock_body_html") or "").strip() or _default_body_html(proposal)
    source_urls = _dedupe_urls(proposal.get("source_urls") or [])
    raw_meta = proposal.get("meta")
    meta = dict(raw_meta) if isinstance(raw_meta, Mapping) else {}
    meta.setdefault("sns_topic_seed", bool(proposal.get("sns_topic_seed", True)))
    meta.setdefault("source_recheck_passed", bool(proposal.get("source_recheck_passed")))
    meta.setdefault("publish_gate_required", bool(proposal.get("publish_gate_required", True)))
    if source_urls:
        meta.setdefault("source_links", source_urls)

    featured_media = proposal.get("featured_media", 1)
    return {
        "id": post_id,
        "status": str(proposal.get("status") or "draft"),
        "title": {"raw": title, "rendered": title},
        "content": {"raw": body_html, "rendered": body_html},
        "excerpt": {"raw": "", "rendered": ""},
        "date": current.isoformat(),
        "modified": current.isoformat(),
        "link": str(proposal.get("link") or _synthetic_link(post_id, proposal)),
        "featured_media": int(featured_media) if str(featured_media).strip() else 0,
        "categories": list(proposal.get("categories") or []),
        "tags": list(proposal.get("tags") or []),
        "meta": meta,
    }


def evaluate_post(raw_post: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    report = evaluate_raw_posts(
        [deepcopy(dict(raw_post))],
        window_hours=DEFAULT_EVALUATOR_WINDOW_HOURS,
        max_pool=1,
        now=now,
    )
    for judgment, key in (("green", "green"), ("yellow", "yellow"), ("red", "red")):
        entries = report.get(key) or []
        if not entries:
            continue
        entry = deepcopy(entries[0])
        cleanup_candidate = None
        for candidate in report.get("cleanup_candidates") or []:
            if int(candidate.get("post_id") or 0) == int(entry["post_id"]):
                cleanup_candidate = deepcopy(candidate)
                break
        return {
            "judgment": judgment,
            "entry": entry,
            "cleanup_candidate": cleanup_candidate,
        }
    raise ValueError("evaluator returned no entry")


def _empty_runner_report(*, live: bool, max_burst: int, now: datetime) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scan_meta": {
            "input_from": "(bridge-empty)",
            "ts": _now_jst(now).isoformat(),
            "live": live,
            "max_burst": int(max_burst),
        },
        "proposed": [],
        "refused": [],
        "summary": {
            "proposed_count": 0,
            "refused_count": 0,
            "would_publish": 0,
            "would_skip": 0,
            "postcheck_batch_count": 0,
        },
    }
    if live:
        payload["executed"] = []
        payload["postcheck_batches"] = []
    return payload


def _build_runner_input(
    green: Sequence[Mapping[str, Any]],
    yellow: Sequence[Mapping[str, Any]],
    cleanup_candidates: Sequence[Mapping[str, Any]],
    *,
    live: bool,
    max_burst: int,
    now: datetime,
) -> dict[str, Any]:
    return {
        "scan_meta": {
            "window_hours": DEFAULT_EVALUATOR_WINDOW_HOURS,
            "max_pool": len(green) + len(yellow),
            "scanned": len(green) + len(yellow),
            "ts": _now_jst(now).isoformat(),
            "bridge_live": live,
            "bridge_max_burst": int(max_burst),
        },
        "green": [deepcopy(dict(entry)) for entry in green],
        "yellow": [deepcopy(dict(entry)) for entry in yellow],
        "red": [],
        "cleanup_candidates": [deepcopy(dict(entry)) for entry in cleanup_candidates],
        "summary": {
            "green_count": len(green),
            "yellow_count": len(yellow),
            "red_count": 0,
            "publishable_count": len(green) + len(yellow),
        },
    }


def _normalise_runner_refused(item: Mapping[str, Any]) -> dict[str, Any]:
    reason = str(item.get("reason") or "runner_refused")
    hold_reason = str(item.get("hold_reason") or reason)
    payload = {
        "post_id": int(item.get("post_id") or 0),
        "reason": reason,
        "hold_reason": hold_reason,
    }
    if item.get("title"):
        payload["title"] = str(item.get("title"))
    return payload


def _bridge_route_base(
    proposal: Mapping[str, Any],
    *,
    source_recheck_passed: bool,
) -> dict[str, Any]:
    return {
        "mock_draft_id": str(proposal.get("mock_draft_id") or ""),
        "title_hint": str(proposal.get("title_hint") or ""),
        "source_recheck_passed": bool(source_recheck_passed),
        "publish_gate_required": bool(proposal.get("publish_gate_required", True)),
        "source_urls": _dedupe_urls(proposal.get("source_urls") or []),
        "topic_category": str(proposal.get("topic_category") or ""),
    }


def run_sns_topic_publish_bridge(
    *,
    fixture_path: str | Path,
    live: bool = False,
    max_burst: int = DEFAULT_MAX_BURST,
    daily_cap_allow: bool = False,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
    history_path: str | Path = DEFAULT_HISTORY_PATH,
    yellow_log_path: str | Path = DEFAULT_YELLOW_LOG_PATH,
    cleanup_log_path: str | Path = DEFAULT_CLEANUP_LOG_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = load_source_recheck_output(fixture_path)
    proposals = list(payload.get("draft_proposals") or [])
    current = _now_jst(now)

    routed_drafts: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    runner_green: list[dict[str, Any]] = []
    runner_yellow: list[dict[str, Any]] = []
    cleanup_candidates: list[dict[str, Any]] = []
    synthetic_posts: dict[int, dict[str, Any]] = {}
    synthetic_contexts: dict[int, dict[str, Any]] = {}
    used_post_ids: set[int] = set()
    source_recheck_passed_count = 0
    hard_stop_count = 0

    for proposal in proposals:
        source_recheck_passed = bool(proposal.get("source_recheck_passed"))
        route = _bridge_route_base(proposal, source_recheck_passed=source_recheck_passed)
        if not source_recheck_passed:
            route.update(
                {
                    "evaluator_judgment": "not_evaluated",
                    "evaluator_category": "excluded",
                    "publishable": False,
                    "runner_status": "skipped_source_recheck",
                    "hold_reason": "source_recheck_failed",
                }
            )
            routed_drafts.append(route)
            refused.append(
                {
                    "mock_draft_id": route["mock_draft_id"],
                    "reason": "source_recheck_failed",
                    "hold_reason": "source_recheck_failed",
                }
            )
            continue

        source_recheck_passed_count += 1
        synthetic_post = build_synthetic_post(proposal, used_ids=used_post_ids, now=current)
        synthetic_posts[int(synthetic_post["id"])] = synthetic_post
        synthetic_contexts[int(synthetic_post["id"])] = route

        evaluated = evaluate_post(synthetic_post, now=current)
        entry = deepcopy(evaluated["entry"])
        post_id = int(entry["post_id"])
        route.update(
            {
                "post_id": post_id,
                "evaluator_judgment": evaluated["judgment"],
                "evaluator_category": str(entry.get("category") or ""),
                "publishable": bool(entry.get("publishable")),
                "cleanup_required": bool(entry.get("cleanup_required")),
                "hard_stop_flags": list(entry.get("hard_stop_flags") or []),
                "repairable_flags": list(entry.get("repairable_flags") or []),
                "yellow_reasons": list(entry.get("yellow_reasons") or []),
            }
        )

        if evaluated["judgment"] == "red":
            hard_stop_count += 1
            hold_reason = f"hard_stop_{(route['hard_stop_flags'] or ['unknown'])[0]}"
            route["runner_status"] = "refused_hard_stop"
            route["hold_reason"] = hold_reason
            refused.append(
                {
                    "post_id": post_id,
                    "mock_draft_id": route["mock_draft_id"],
                    "reason": "hard_stop",
                    "hold_reason": hold_reason,
                    "hard_stop_flags": list(route["hard_stop_flags"]),
                }
            )
        else:
            if evaluated["judgment"] == "green":
                runner_green.append(entry)
            else:
                runner_yellow.append(entry)
            if evaluated["cleanup_candidate"] is not None:
                cleanup_candidates.append(deepcopy(evaluated["cleanup_candidate"]))
            route["runner_status"] = "pending_runner"
        routed_drafts.append(route)

    mock_wp = SyntheticDraftWPClient(synthetic_posts)
    if runner_green or runner_yellow:
        runner_input = _build_runner_input(
            runner_green,
            runner_yellow,
            cleanup_candidates,
            live=live,
            max_burst=max_burst,
            now=current,
        )
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
                json.dump(runner_input, handle, ensure_ascii=False, indent=2)
                handle.flush()
                tmp_path = handle.name
            runner_report = _run_guarded_publish(
                input_from=tmp_path,
                live=live,
                max_burst=max_burst,
                daily_cap_allow=daily_cap_allow,
                backup_dir=backup_dir,
                history_path=history_path,
                yellow_log_path=yellow_log_path,
                cleanup_log_path=cleanup_log_path,
                wp_client=mock_wp,
                now=current,
            )
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)
    else:
        runner_report = _empty_runner_report(live=live, max_burst=max_burst, now=current)

    runner_proposed = {int(item["post_id"]): item for item in runner_report.get("proposed") or []}
    runner_refused = {int(item["post_id"]): item for item in runner_report.get("refused") or [] if "post_id" in item}
    runner_executed = {int(item["post_id"]): item for item in runner_report.get("executed") or [] if "post_id" in item}

    for route in routed_drafts:
        post_id = route.get("post_id")
        if not post_id:
            continue
        normalized_post_id = int(post_id)
        if normalized_post_id in runner_proposed:
            route["runner_plan"] = deepcopy(runner_proposed[normalized_post_id])
            route["runner_status"] = "would_publish" if not live else route.get("runner_status")
        if normalized_post_id in runner_refused:
            refused_item = runner_refused[normalized_post_id]
            route["runner_status"] = "would_skip" if not live else route.get("runner_status")
            route["hold_reason"] = str(refused_item.get("hold_reason") or refused_item.get("reason") or "runner_refused")
        if normalized_post_id in runner_executed:
            executed_item = runner_executed[normalized_post_id]
            route["runner_status"] = str(executed_item.get("status") or "")
            if executed_item.get("hold_reason"):
                route["hold_reason"] = str(executed_item["hold_reason"])

    final_refused = list(refused)
    for item in runner_report.get("refused") or []:
        final_refused.append(_normalise_runner_refused(item))

    sent_count = sum(1 for item in runner_report.get("executed") or [] if item.get("status") == "sent")
    summary = {
        "input_count": len(proposals),
        "source_recheck_passed_count": source_recheck_passed_count,
        "publishable_count": len(runner_green) + len(runner_yellow),
        "hard_stop_count": hard_stop_count,
        "proposed_count": len(runner_report.get("proposed") or []),
        "refused_count": len(final_refused),
        "sent_count": sent_count,
    }
    return {
        "scan_meta": {
            "fixture_path": str(fixture_path),
            "ts": current.isoformat(),
            "live": live,
            "max_burst": int(max_burst),
            "daily_cap_allow": bool(daily_cap_allow),
        },
        "routed_drafts": routed_drafts,
        "proposed": deepcopy(runner_report.get("proposed") or []),
        "refused": final_refused,
        "summary": summary,
        "runner_report": runner_report,
        "mock_wp": mock_wp.debug_snapshot(),
    }


def dump_sns_topic_publish_bridge_report(report: dict[str, Any], *, fmt: str = "json") -> str:
    if fmt == "json":
        return json.dumps(report, ensure_ascii=False, indent=2) + "\n"

    summary = report["summary"]
    scan_meta = report["scan_meta"]
    lines = [
        "SNS Topic Publish Bridge",
        f"live={scan_meta['live']}  max_burst={scan_meta['max_burst']}  ts={scan_meta['ts']}",
        "",
        (
            "summary: "
            f"input={summary['input_count']} "
            f"source_recheck_passed={summary['source_recheck_passed_count']} "
            f"publishable={summary['publishable_count']} "
            f"hard_stop={summary['hard_stop_count']} "
            f"sent={summary['sent_count']}"
        ),
        "",
        "Routed",
    ]
    if not report["routed_drafts"]:
        lines.append("- none")
    else:
        for item in report["routed_drafts"]:
            lines.append(
                "- "
                f"{item.get('mock_draft_id') or item.get('post_id')} | "
                f"{item.get('evaluator_judgment')} | publishable={item.get('publishable')} | "
                f"runner={item.get('runner_status', '-')}"
            )

    lines.extend(["", "Proposed"])
    if not report["proposed"]:
        lines.append("- none")
    else:
        for item in report["proposed"]:
            lines.append(f"- {item['post_id']} | {item['judgment']} | {item['title']}")

    lines.extend(["", "Refused"])
    if not report["refused"]:
        lines.append("- none")
    else:
        for item in report["refused"]:
            lines.append(
                f"- {item.get('post_id', item.get('mock_draft_id', '-'))} | "
                f"{item.get('reason')} | {item.get('hold_reason')}"
            )
    return "\n".join(lines) + "\n"


__all__ = [
    "DEFAULT_MAX_BURST",
    "SyntheticDraftWPClient",
    "build_synthetic_post",
    "dump_sns_topic_publish_bridge_report",
    "evaluate_post",
    "load_source_recheck_output",
    "run_sns_topic_publish_bridge",
]
