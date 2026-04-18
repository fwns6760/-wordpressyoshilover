"""
acceptance_auto_fix.py -- acceptance_fact_check の結果を自動修正候補へ整理する

使用例:
    python3 -m src.acceptance_auto_fix --post-id 62527 --post-id 62518
    python3 -m src.acceptance_auto_fix --category postgame --limit 10

注意:
    --apply は将来実装予定。今日は dry-run のみ対応。
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).parent.parent
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

import acceptance_fact_check
from wp_client import WPClient

JST = timezone(timedelta(hours=9))
SAFE_FIELDS = {"opponent", "venue", "subject"}
SAFE_AUTOFIX_TYPES = {"title_replace", "body_replace"}


@dataclass
class ProposedEdit:
    target: str
    find: str
    replace: str
    occurrences: int
    before: str
    after: str
    diff: str


@dataclass
class AutoFixDecision:
    post_id: int
    title: str
    status: str
    primary_category: str
    article_subtype: str
    modified: str
    edit_url: str
    decision: str
    causes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    proposed_edits: list[ProposedEdit] = field(default_factory=list)


@dataclass
class AutoFixSummary:
    checked_posts: int
    autofix_candidates: list[AutoFixDecision]
    rejects: list[AutoFixDecision]
    manual_reviews: list[AutoFixDecision]
    no_action: list[AutoFixDecision]


def _today_label() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def _markdown_path_for_date(date_label: str) -> Path:
    return ROOT / "docs" / "fix_logs" / f"{date_label}.md"


def _ensure_fix_log_dirs() -> None:
    (ROOT / "docs" / "fix_logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "fix_logs" / "snapshots").mkdir(parents=True, exist_ok=True)


def _collect_reports(
    *,
    post_ids: list[int],
    category: str,
    limit: int,
    status: str,
    since: str,
    wp: WPClient | None = None,
) -> list[acceptance_fact_check.PostReport]:
    wp_client = wp or WPClient()
    if post_ids:
        reports: list[acceptance_fact_check.PostReport] = []
        for post_id in post_ids:
            reports.extend(
                acceptance_fact_check.collect_reports(
                    post_id=post_id,
                    status=status,
                    since=since,
                    wp=wp_client,
                )
            )
        return reports
    return acceptance_fact_check.collect_reports(
        category=category,
        limit=limit,
        status=status,
        since=since,
        wp=wp_client,
    )


def _fetch_editable_post(wp: WPClient, post_id: int) -> dict[str, Any]:
    resp = requests.get(
        f"{wp.api}/posts/{post_id}",
        params={"context": "edit"},
        auth=wp.auth,
        timeout=30,
    )
    wp._raise_for_status(resp, f"記事取得 post_id={post_id} context=edit")
    return resp.json()


def _extract_raw_title(post: dict[str, Any]) -> str:
    title_data = post.get("title") or {}
    return title_data.get("raw") or title_data.get("rendered") or ""


def _extract_raw_content(post: dict[str, Any]) -> str:
    content_data = post.get("content") or {}
    return content_data.get("raw") or content_data.get("rendered") or ""


def _markdown_code_diff(before: str, after: str) -> str:
    before_lines = before.splitlines() or [before]
    after_lines = after.splitlines() or [after]
    diff = "\n".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )
    return diff or "(no diff)"


def _target_text(post: dict[str, Any], target: str) -> str:
    if target == "title":
        return _extract_raw_title(post)
    return _extract_raw_content(post)


def _build_proposed_edit(post: dict[str, Any], finding: acceptance_fact_check.Finding) -> tuple[ProposedEdit | None, str | None]:
    action = finding.auto_fix or {}
    action_type = action.get("type", "")
    if action_type not in SAFE_AUTOFIX_TYPES:
        return None, f"unsupported_auto_fix:{action_type or 'missing'}"
    if finding.field not in SAFE_FIELDS:
        return None, f"field_not_whitelisted:{finding.field}"

    target = "title" if action_type == "title_replace" else "content"
    source_text = _target_text(post, target)
    needle = str(action.get("find", ""))
    replacement = str(action.get("replace", ""))
    if not needle:
        return None, "missing_find_text"
    occurrences = source_text.count(needle)
    if occurrences != 1:
        return None, f"match_count={occurrences}"

    updated = source_text.replace(needle, replacement, 1)
    return (
        ProposedEdit(
            target=target,
            find=needle,
            replace=replacement,
            occurrences=occurrences,
            before=source_text,
            after=updated,
            diff=_markdown_code_diff(source_text, updated),
        ),
        None,
    )


def _evaluate_report(
    report: acceptance_fact_check.PostReport,
    *,
    wp: WPClient | None = None,
    fetch_post_state: bool,
) -> AutoFixDecision:
    post_state: dict[str, Any] | None = None
    if fetch_post_state:
        if wp is None:
            raise ValueError("wp is required when fetch_post_state=True")
        post_state = _fetch_editable_post(wp, report.post_id)
    elif report.status != "draft":
        # メール集計など fetch を省く時でも publish を候補にしない。
        return AutoFixDecision(
            post_id=report.post_id,
            title=report.title,
            status=report.status,
            primary_category=report.primary_category,
            article_subtype=report.article_subtype,
            modified=report.modified,
            edit_url=report.edit_url,
            decision="reject",
            causes=["non_draft_status"],
            notes=["publish 済み記事には触れない"],
            findings=[asdict(item) for item in report.findings],
        )

    effective_status = (post_state or {}).get("status", report.status or "").lower()
    if effective_status != "draft":
        return AutoFixDecision(
            post_id=report.post_id,
            title=report.title,
            status=effective_status or report.status,
            primary_category=report.primary_category,
            article_subtype=report.article_subtype,
            modified=(post_state or {}).get("modified", report.modified),
            edit_url=report.edit_url,
            decision="reject",
            causes=["non_draft_status"],
            notes=["publish 済み記事には触れない"],
            findings=[asdict(item) for item in report.findings],
        )

    red_findings = [finding for finding in report.findings if finding.severity == "red"]
    yellow_findings = [finding for finding in report.findings if finding.severity == "yellow"]

    proposed_edits: list[ProposedEdit] = []
    notes: list[str] = []
    causes: list[str] = []
    blocking_issue = False

    if post_state is not None:
        current_modified = (post_state.get("modified") or report.modified or "").strip()
        if current_modified and report.modified and current_modified != report.modified:
            blocking_issue = True
            notes.append("modified_after_snapshot: dry-run時点のmodifiedと現在値が不一致")
            causes.append("modified_after_snapshot")

    for finding in red_findings:
        causes.append(finding.cause)
        if finding.fix_type != "direct_edit":
            blocking_issue = True
            notes.append(f"non_direct_edit:{finding.field}")
            continue
        if not finding.auto_fix:
            blocking_issue = True
            notes.append(f"missing_auto_fix:{finding.field}")
            continue
        if post_state is None:
            proposed_edits.append(
                ProposedEdit(
                    target="title" if finding.auto_fix.get("type") == "title_replace" else "content",
                    find=str(finding.auto_fix.get("find", "")),
                    replace=str(finding.auto_fix.get("replace", "")),
                    occurrences=0,
                    before="",
                    after="",
                    diff="",
                )
            )
            continue
        edit, block_reason = _build_proposed_edit(post_state, finding)
        if block_reason:
            blocking_issue = True
            notes.append(f"{finding.field}:{block_reason}")
            continue
        if edit:
            proposed_edits.append(edit)

    if red_findings:
        if proposed_edits and not blocking_issue:
            decision = "autofix_candidate"
        else:
            decision = "reject"
    elif yellow_findings:
        decision = "manual_review"
        causes.extend(finding.cause for finding in yellow_findings)
    else:
        decision = "no_action"

    return AutoFixDecision(
        post_id=report.post_id,
        title=report.title,
        status=effective_status or report.status,
        primary_category=report.primary_category,
        article_subtype=report.article_subtype,
        modified=(post_state or {}).get("modified", report.modified),
        edit_url=report.edit_url,
        decision=decision,
        causes=list(dict.fromkeys(filter(None, causes))),
        notes=list(dict.fromkeys(filter(None, notes))),
        findings=[asdict(item) for item in report.findings],
        proposed_edits=proposed_edits,
    )


def analyze_reports(
    reports: list[acceptance_fact_check.PostReport],
    *,
    wp: WPClient | None = None,
    fetch_post_state: bool = True,
) -> AutoFixSummary:
    wp_client = wp or (WPClient() if fetch_post_state else None)
    decisions = [
        _evaluate_report(report, wp=wp_client, fetch_post_state=fetch_post_state)
        for report in reports
    ]
    return AutoFixSummary(
        checked_posts=len(decisions),
        autofix_candidates=[item for item in decisions if item.decision == "autofix_candidate"],
        rejects=[item for item in decisions if item.decision == "reject"],
        manual_reviews=[item for item in decisions if item.decision == "manual_review"],
        no_action=[item for item in decisions if item.decision == "no_action"],
    )


def _render_finding_lines(findings: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for finding in findings:
        lines.append(
            f"- `{finding['field']}` / `{finding['cause']}`: {finding['message']}"
        )
        if finding.get("proposal"):
            lines.append(f"  - proposal: {finding['proposal']}")
    return lines or ["- 重大な差分なし"]


def _render_edit_lines(edits: list[ProposedEdit]) -> list[str]:
    lines: list[str] = []
    for edit in edits:
        lines.append(f"- target: `{edit.target}` / `{edit.find}` → `{edit.replace}`")
        lines.append("```diff")
        lines.append(edit.diff)
        lines.append("```")
    return lines or ["- 具体diffなし"]


def build_markdown_report(
    summary: AutoFixSummary,
    *,
    date_label: str,
    source_scope: str,
    generated_at: str,
) -> str:
    lines = [
        f"# Acceptance Auto Fix Dry Run - {date_label}",
        "",
        f"- generated_at: `{generated_at}`",
        f"- source_scope: `{source_scope}`",
        f"- checked_posts: `{summary.checked_posts}`",
        f"- autofix_candidates: `{len(summary.autofix_candidates)}`",
        f"- rejects: `{len(summary.rejects)}`",
        f"- manual_reviews: `{len(summary.manual_reviews)}`",
        f"- no_action: `{len(summary.no_action)}`",
        "",
        "## 自動修正候補",
        "",
    ]
    if not summary.autofix_candidates:
        lines.append("該当なし")
    for item in summary.autofix_candidates:
        lines.extend(
            [
                f"### post_id {item.post_id} / {item.primary_category} / {item.article_subtype}",
                f"- title: {item.title}",
                f"- action: 自動修正候補",
                f"- causes: {', '.join(item.causes) or 'none'}",
                f"- edit_url: {item.edit_url}",
                "- findings:",
                *_render_finding_lines(item.findings),
                "- diffs:",
                *_render_edit_lines(item.proposed_edits),
                "",
            ]
        )

    lines.extend(["## 差し戻し推奨", ""])
    if not summary.rejects:
        lines.append("該当なし")
    for item in summary.rejects:
        lines.extend(
            [
                f"### post_id {item.post_id} / {item.primary_category} / {item.article_subtype}",
                f"- title: {item.title}",
                f"- action: 差し戻し推奨",
                f"- causes: {', '.join(item.causes) or 'none'}",
                f"- edit_url: {item.edit_url}",
            ]
        )
        if item.notes:
            lines.append(f"- notes: {' / '.join(item.notes)}")
        lines.append("- findings:")
        lines.extend(_render_finding_lines(item.findings))
        if item.proposed_edits:
            lines.append("- 参考diff:")
            lines.extend(_render_edit_lines(item.proposed_edits))
        lines.append("")

    lines.extend(["## 手動確認必要", ""])
    if not summary.manual_reviews:
        lines.append("該当なし")
    for item in summary.manual_reviews:
        lines.extend(
            [
                f"### post_id {item.post_id} / {item.primary_category} / {item.article_subtype}",
                f"- title: {item.title}",
                f"- action: 手動確認必要",
                f"- causes: {', '.join(item.causes) or 'none'}",
                f"- edit_url: {item.edit_url}",
                "- findings:",
                *_render_finding_lines(item.findings),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(markdown: str, *, date_label: str) -> Path:
    _ensure_fix_log_dirs()
    path = _markdown_path_for_date(date_label)
    path.write_text(markdown, encoding="utf-8")
    return path


def _summary_to_json(summary: AutoFixSummary) -> str:
    payload = {
        "checked_posts": summary.checked_posts,
        "autofix_candidates": [asdict(item) for item in summary.autofix_candidates],
        "rejects": [asdict(item) for item in summary.rejects],
        "manual_reviews": [asdict(item) for item in summary.manual_reviews],
        "no_action": [asdict(item) for item in summary.no_action],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="acceptance_fact_check の結果から自動修正候補を dry-run で整理する")
    parser.add_argument("--post-id", dest="post_ids", type=int, action="append", default=[], help="対象 post_id を追加")
    parser.add_argument("--category", default="", help="primary category または article_subtype で絞る")
    parser.add_argument("--limit", type=int, default=10, help="対象件数")
    parser.add_argument("--status", default="draft", help="取得する投稿 status")
    parser.add_argument("--since", default="today", help="today / yesterday / YYYY-MM-DD / all")
    parser.add_argument("--max", type=int, default=5, help="将来 apply する際の上限。dry-runでは表示用")
    parser.add_argument("--apply", action="store_true", help="将来の apply 実行用。今日は未実装")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    parser.add_argument("--no-write-log", action="store_true", help="docs/fix_logs への出力を抑止")
    args = parser.parse_args()

    if args.apply:
        raise SystemExit("--apply is not implemented yet. use dry-run only for now.")

    wp = WPClient()
    reports = _collect_reports(
        post_ids=args.post_ids,
        category=args.category,
        limit=args.limit,
        status=args.status,
        since=args.since,
        wp=wp,
    )
    summary = analyze_reports(reports, wp=wp, fetch_post_state=True)
    date_label = _today_label()
    generated_at = datetime.now(JST).isoformat(timespec="seconds")
    source_scope = (
        "post_ids=" + ",".join(str(post_id) for post_id in args.post_ids)
        if args.post_ids
        else f"category={args.category or 'all'} limit={args.limit}"
    )
    markdown = build_markdown_report(
        summary,
        date_label=date_label,
        source_scope=source_scope,
        generated_at=generated_at,
    )
    if not args.no_write_log:
        path = write_markdown_report(markdown, date_label=date_label)
        print(f"wrote_log={path}")
    if args.json:
        print(_summary_to_json(summary))
        return
    print(markdown)


if __name__ == "__main__":
    main()
