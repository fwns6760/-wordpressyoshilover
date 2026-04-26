from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from src import guarded_publish_runner as cleanup_runner
from src.pre_publish_fact_check import extractor


ROOT = Path(__file__).resolve().parent.parent
JST = ZoneInfo("Asia/Tokyo")
DEFAULT_MAX_BURST = 10
DEFAULT_BACKUP_DIR = ROOT / "logs" / "published_cleanup_backup"
DEFAULT_LEDGER_PATH = ROOT / "logs" / "published_cleanup_apply_ledger.jsonl"


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _load_json(path: str | Path) -> Any:
    return json.loads(_path(path).read_text(encoding="utf-8"))


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
                raise ValueError(f"ledger row must be an object: {target}:{index}")
            rows.append(payload)
    return rows


def _append_jsonl(path: str | Path, payload: dict[str, Any]) -> None:
    target = _path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_proposal_rows(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, dict):
        raw_rows = payload.get("cleanup_proposals")
        if raw_rows is None:
            raise ValueError("proposal JSON must contain cleanup_proposals")
        scan_meta = dict(payload.get("scan_meta") or {})
    elif isinstance(payload, list):
        raw_rows = payload
        scan_meta = {}
    else:
        raise ValueError("proposal JSON must be an object or list")

    if not isinstance(raw_rows, list):
        raise ValueError("cleanup_proposals must be a list")

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw_rows, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"cleanup proposal must be an object: {path}:{index}")
        try:
            post_id = int(item["post_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"cleanup proposal missing valid post_id: {path}:{index}") from exc
        rows.append(
            {
                "post_id": post_id,
                "title": str(item.get("title") or ""),
                "repairable_flags": _proposal_flags(item),
                "proposed_cleanups": list(item.get("proposed_cleanups") or []),
            }
        )
    return rows, scan_meta


def _proposal_flags(proposal: dict[str, Any]) -> list[str]:
    raw_flags = proposal.get("repairable_flags")
    flags: list[str] = []
    if isinstance(raw_flags, list):
        flags.extend(str(flag).strip() for flag in raw_flags if str(flag).strip())
    if not flags:
        for item in proposal.get("proposed_cleanups") or []:
            if not isinstance(item, dict):
                continue
            flag = str(item.get("flag") or "").strip()
            if flag:
                flags.append(flag)
    return list(dict.fromkeys(flags))


def _applied_post_ids(rows: Sequence[dict[str, Any]]) -> set[int]:
    applied: set[int] = set()
    for row in rows:
        if str(row.get("status") or "") != "applied":
            continue
        try:
            applied.add(int(row["post_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return applied


def _build_ledger_row(
    *,
    post_id: int,
    ts: str,
    status: str,
    live: bool,
    cleanup_flags: Sequence[str],
    backup_path: str | None = None,
    error: str | None = None,
    verify_result: str | None = None,
    content_changed: bool | None = None,
) -> dict[str, Any]:
    return {
        "post_id": int(post_id),
        "ts": ts,
        "status": status,
        "live": bool(live),
        "cleanup_flags": list(cleanup_flags),
        "backup_path": backup_path,
        "error": error,
        "verify_result": verify_result,
        "content_changed": content_changed,
    }


def _build_result_item(
    *,
    proposal: dict[str, Any],
    status: str,
    live: bool,
    cleanup_actions: Sequence[dict[str, Any]] | None = None,
    backup_path: str | None = None,
    error: str | None = None,
    verify_result: str | None = None,
    content_changed: bool | None = None,
) -> dict[str, Any]:
    return {
        "post_id": int(proposal["post_id"]),
        "title": str(proposal.get("title") or ""),
        "status": status,
        "live": bool(live),
        "repairable_flags": list(proposal.get("repairable_flags") or []),
        "cleanup_actions": list(cleanup_actions or []),
        "backup_path": backup_path,
        "error": error,
        "verify_result": verify_result,
        "content_changed": content_changed,
    }


def _apply_cleanup_flags(post: dict[str, Any], cleanup_flags: Sequence[str]) -> tuple[str, list[dict[str, Any]], bool]:
    record = extractor.extract_post_record(post)
    original_html = str(record.get("body_html") or "")
    cleaned_html = original_html
    actions: list[dict[str, Any]] = []
    content_changed = False

    for flag in cleanup_flags:
        current_html = cleaned_html
        if flag == "heading_sentence_as_h3":
            cleaned_html, new_actions = cleanup_runner._replace_heading_sentence_h3(cleaned_html)
        elif flag == "weird_heading_label":
            cleaned_html, new_actions = cleanup_runner._remove_weird_heading_labels(cleaned_html)
        elif flag == "dev_log_contamination":
            cleaned_html, new_actions = cleanup_runner._remove_dev_log_contamination(cleaned_html)
        elif flag == "site_component_mixed_into_body":
            cleaned_html, new_actions = cleanup_runner._remove_site_component_mixed_into_body(cleaned_html)
        elif flag == "light_structure_break":
            cleaned_html, new_actions = cleanup_runner._remove_light_structure_breaks(cleaned_html)
        elif flag == "weak_source_display":
            cleaned_html, new_actions = cleanup_runner._append_weak_source_display(cleaned_html, post)
        elif flag == "long_body":
            cleaned_html, new_actions = cleanup_runner._compress_long_body(cleaned_html, post)
        elif flag in cleanup_runner.REPAIRABLE_FLAG_ACTION_MAP:
            cleaned_html, new_actions = cleanup_runner._warning_only_flag_cleanup(
                flag,
                post,
                cleaned_html,
                reason=f"unsupported_for_published_cleanup_apply:{flag}",
            )
        else:
            raise cleanup_runner.CandidateRefusedError("cleanup_action_unmapped", f"cleanup_action_unmapped:{flag}")
        actions.extend(new_actions)
        if cleaned_html != current_html:
            content_changed = True

    return cleaned_html, actions, content_changed and cleaned_html != original_html


def _summarize(executed: Sequence[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(executed),
        "applied": 0,
        "dry_run": 0,
        "held": 0,
        "skipped": 0,
    }
    for item in executed:
        status = str(item.get("status") or "")
        if status in summary:
            summary[status] += 1
    return summary


def run_published_cleanup_apply(
    proposals_from: str | Path,
    *,
    wp_client: Any,
    max_burst: int = DEFAULT_MAX_BURST,
    live: bool = False,
    backup_dir: str | Path = DEFAULT_BACKUP_DIR,
    ledger_path: str | Path = DEFAULT_LEDGER_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    if int(max_burst) <= 0:
        raise ValueError("max_burst must be > 0")

    current_now = _now_jst(now)
    ts = current_now.isoformat()
    proposal_rows, scan_meta = _load_proposal_rows(proposals_from)
    prior_rows = _read_jsonl(ledger_path)
    already_applied = _applied_post_ids(prior_rows)
    seen_input_post_ids: set[int] = set()

    executed: list[dict[str, Any]] = []

    for index, proposal in enumerate(proposal_rows):
        post_id = int(proposal["post_id"])
        cleanup_flags = list(proposal.get("repairable_flags") or [])

        if index >= int(max_burst):
            error = "burst_cap"
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="skipped",
                live=live,
                cleanup_flags=cleanup_flags,
                error=error,
                content_changed=False,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="skipped",
                    live=live,
                    error=error,
                    content_changed=False,
                )
            )
            continue

        if post_id in seen_input_post_ids:
            error = "duplicate_input_post_id"
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="skipped",
                live=live,
                cleanup_flags=cleanup_flags,
                error=error,
                content_changed=False,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="skipped",
                    live=live,
                    error=error,
                    content_changed=False,
                )
            )
            continue
        seen_input_post_ids.add(post_id)

        if post_id in already_applied:
            error = "already_applied"
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="skipped",
                live=live,
                cleanup_flags=cleanup_flags,
                error=error,
                content_changed=False,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="skipped",
                    live=live,
                    error=error,
                    content_changed=False,
                )
            )
            continue

        if not cleanup_flags:
            error = "no_cleanup_flags"
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="skipped",
                live=live,
                cleanup_flags=cleanup_flags,
                error=error,
                content_changed=False,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="skipped",
                    live=live,
                    error=error,
                    content_changed=False,
                )
            )
            continue

        post = dict(wp_client.get_post(post_id) or {})
        status = str(post.get("status") or "").strip().lower()
        if status != "publish":
            error = f"status_not_publish:{status or 'missing'}"
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="held",
                live=live,
                cleanup_flags=cleanup_flags,
                error=error,
                content_changed=False,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="held",
                    live=live,
                    error=error,
                    content_changed=False,
                )
            )
            continue

        cleanup_actions: list[dict[str, Any]] = []
        try:
            cleaned_html, cleanup_actions, content_changed = _apply_cleanup_flags(post, cleanup_flags)
        except cleanup_runner.CandidateRefusedError as exc:
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="held",
                live=live,
                cleanup_flags=cleanup_flags,
                error=exc.detail,
                content_changed=False,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="held",
                    live=live,
                    cleanup_actions=cleanup_actions,
                    error=exc.detail,
                    content_changed=False,
                )
            )
            continue

        if not content_changed:
            error = "no_content_changes"
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="skipped",
                live=live,
                cleanup_flags=cleanup_flags,
                error=error,
                content_changed=False,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="skipped",
                    live=live,
                    cleanup_actions=cleanup_actions,
                    error=error,
                    content_changed=False,
                )
            )
            continue

        verify_ok, verify_result = cleanup_runner._post_cleanup_check(post, cleaned_html)
        if not verify_ok:
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="held",
                live=live,
                cleanup_flags=cleanup_flags,
                error="verify_failed",
                verify_result=verify_result,
                content_changed=True,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="held",
                    live=live,
                    cleanup_actions=cleanup_actions,
                    error="verify_failed",
                    verify_result=verify_result,
                    content_changed=True,
                )
            )
            continue

        if not live:
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="dry_run",
                live=False,
                cleanup_flags=cleanup_flags,
                verify_result=verify_result,
                content_changed=True,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="dry_run",
                    live=False,
                    cleanup_actions=cleanup_actions,
                    verify_result=verify_result,
                    content_changed=True,
                )
            )
            continue

        try:
            backup_path = cleanup_runner.create_publish_backup(post, backup_dir, now=current_now)
        except cleanup_runner.BackupError as exc:
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="held",
                live=True,
                cleanup_flags=cleanup_flags,
                error="backup_failed",
                verify_result=verify_result,
                content_changed=True,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="held",
                    live=True,
                    cleanup_actions=cleanup_actions,
                    error=f"backup_failed:{exc}",
                    verify_result=verify_result,
                    content_changed=True,
                )
            )
            continue

        try:
            wp_client.update_post_fields(post_id, content=cleaned_html)
        except Exception as exc:
            ledger_row = _build_ledger_row(
                post_id=post_id,
                ts=ts,
                status="held",
                live=True,
                cleanup_flags=cleanup_flags,
                backup_path=str(backup_path),
                error="wp_update_failed",
                verify_result=verify_result,
                content_changed=True,
            )
            _append_jsonl(ledger_path, ledger_row)
            executed.append(
                _build_result_item(
                    proposal=proposal,
                    status="held",
                    live=True,
                    cleanup_actions=cleanup_actions,
                    backup_path=str(backup_path),
                    error=f"wp_update_failed:{exc}",
                    verify_result=verify_result,
                    content_changed=True,
                )
            )
            continue
        ledger_row = _build_ledger_row(
            post_id=post_id,
            ts=ts,
            status="applied",
            live=True,
            cleanup_flags=cleanup_flags,
            backup_path=str(backup_path),
            verify_result=verify_result,
            content_changed=True,
        )
        _append_jsonl(ledger_path, ledger_row)
        executed.append(
            _build_result_item(
                proposal=proposal,
                status="applied",
                live=True,
                cleanup_actions=cleanup_actions,
                backup_path=str(backup_path),
                verify_result=verify_result,
                content_changed=True,
            )
        )

    return {
        "scan_meta": {
            "input_path": str(_path(proposals_from)),
            "source_scan_meta": scan_meta,
            "ts": ts,
            "live": bool(live),
            "max_burst": int(max_burst),
            "proposals_total": len(proposal_rows),
            "ledger_path": str(_path(ledger_path)),
            "backup_dir": str(_path(backup_dir)),
        },
        "executed": executed,
        "summary": _summarize(executed),
    }


def render_human_report(report: dict[str, Any]) -> str:
    scan_meta = report["scan_meta"]
    summary = report["summary"]
    lines = [
        "Published Cleanup Apply Runner",
        (
            f"proposals={scan_meta['proposals_total']} live={str(scan_meta['live']).lower()} "
            f"max_burst={scan_meta['max_burst']} ts={scan_meta['ts']}"
        ),
        "",
        "Summary",
        f"total={summary['total']}",
        f"applied={summary['applied']}",
        f"dry_run={summary['dry_run']}",
        f"held={summary['held']}",
        f"skipped={summary['skipped']}",
        "",
        "Executed",
    ]
    if not report["executed"]:
        lines.append("- none")
    else:
        for item in report["executed"]:
            lines.append(
                f"- {item['post_id']} | {item['status']} | "
                f"{','.join(item['repairable_flags']) or '-'} | "
                f"{item.get('verify_result') or item.get('error') or '-'}"
            )
    return "\n".join(lines) + "\n"


def dump_report(report: dict[str, Any], *, fmt: str) -> str:
    if fmt == "human":
        return render_human_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


__all__ = [
    "DEFAULT_BACKUP_DIR",
    "DEFAULT_LEDGER_PATH",
    "DEFAULT_MAX_BURST",
    "dump_report",
    "render_human_report",
    "run_published_cleanup_apply",
]
