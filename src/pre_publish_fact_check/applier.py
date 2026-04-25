from __future__ import annotations

import difflib
import hashlib
import html
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.pre_publish_fact_check.backup import BackupError, create_backup
from src.pre_publish_fact_check.contracts import ApprovalFinding, ApprovalRecord, Operation
from src.pre_publish_fact_check.extractor import extract_post_record


def _content_hash(body_html: str) -> str:
    return hashlib.sha256((body_html or "").encode("utf-8")).hexdigest()


def _render_diff(before: str, after: str, *, post_id: int) -> str:
    lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"post-{post_id}:current",
            tofile=f"post-{post_id}:proposed",
            lineterm="",
        )
    )
    return "\n".join(lines)


def _replace_once(text: str, needle: str, replacement: str) -> tuple[str, bool]:
    if needle not in text:
        return text, False
    return text.replace(needle, replacement, 1), True


def _apply_html_operation(body_html: str, finding: ApprovalFinding) -> tuple[str, bool]:
    replacements = [
        (finding.suggested_fix.find_text, finding.suggested_fix.replace_text),
        (
            html.escape(finding.suggested_fix.find_text, quote=False),
            html.escape(finding.suggested_fix.replace_text, quote=False),
        ),
    ]
    for needle, replacement in replacements:
        updated, changed = _replace_once(body_html, needle, replacement)
        if changed:
            return updated, True
    return body_html, False


@dataclass(slots=True)
class ApplyResult:
    summary: dict[str, Any]
    diff: str


class ApplyRefusedError(RuntimeError):
    def __init__(self, message: str, *, summary: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.summary = summary or {}


def _write_post_content(wp_client, post_id: int, patched_html: str) -> None:
    wp_client.update_post_fields(post_id, content=patched_html)


def _find_record(records: list[ApprovalRecord], post_id: int) -> ApprovalRecord:
    for record in records:
        if record.post_id == post_id:
            return record
    raise ApplyRefusedError(f"post_id={post_id} not present in approval YAML")


def apply_approved_fixes(
    *,
    wp_client,
    post_id: int,
    approval_records: list[ApprovalRecord],
    backup_dir: str | Path,
    live: bool = False,
    stderr=None,
) -> ApplyResult:
    stderr = stderr or sys.stderr
    approval = _find_record(approval_records, post_id)
    approved_findings = [finding for finding in approval.findings if finding.approve]
    if not approved_findings:
        raise ApplyRefusedError("no approved findings")

    post = wp_client.get_post(post_id)
    extracted = extract_post_record(post)
    current_html = str(extracted["body_html"])
    current_text = str(extracted["body_text"])
    if _content_hash(current_html) != approval.content_hash:
        raise ApplyRefusedError("content drifted, re-extract+approve required")

    working_html = current_html
    working_text = current_text
    summary: dict[str, Any] = {
        "applied": [],
        "refused": [],
        "backup_path": None,
        "post_id": post_id,
    }

    for finding in approved_findings:
        if finding.suggested_fix.operation == Operation.NEEDS_MANUAL_REVIEW:
            summary["refused"].append(
                {"reason": "manual_review_only", "finding_index": finding.finding_index}
            )
            continue
        if finding.suggested_fix.find_text not in working_text:
            summary["refused"].append(
                {"reason": "find_text_not_found", "finding_index": finding.finding_index}
            )
            continue
        updated_html, changed = _apply_html_operation(working_html, finding)
        if not changed:
            summary["refused"].append(
                {"reason": "find_text_not_found_in_html", "finding_index": finding.finding_index}
            )
            continue
        working_html = updated_html
        working_text = extract_post_record({"id": post_id, "content": {"raw": working_html}})["body_text"]
        summary["applied"].append(
            {
                "finding_index": finding.finding_index,
                "operation": finding.suggested_fix.operation.value,
            }
        )

    if not summary["applied"]:
        raise ApplyRefusedError("no applicable approved findings", summary=summary)

    diff = _render_diff(current_text, working_text, post_id=post_id)
    if not live:
        return ApplyResult(summary=summary, diff=diff)

    try:
        backup_path = create_backup(post, backup_dir)
    except BackupError as exc:
        raise ApplyRefusedError(str(exc), summary=summary) from exc

    summary["backup_path"] = str(backup_path)
    try:
        _write_post_content(wp_client, post_id, working_html)
    except Exception as exc:
        print(
            f"WP update failed for post_id={post_id}; restore from backup if needed: {backup_path}",
            file=stderr,
        )
        raise ApplyRefusedError(f"wp write failed: {exc}", summary=summary) from exc

    return ApplyResult(summary=summary, diff=diff)
