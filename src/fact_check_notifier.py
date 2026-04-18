"""
fact_check_notifier.py -- acceptance_fact_check の結果を HTML メールで通知する

使用例:
    python3 -m src.fact_check_notifier --send
    python3 -m src.fact_check_notifier --since yesterday --limit 20
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import smtplib
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

import acceptance_fact_check
import acceptance_auto_fix

JST = timezone(timedelta(hours=9))
TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_FACT_CHECK_EMAIL = "fwns6760@gmail.com"
DEFAULT_GMAIL_APP_PASSWORD_SECRET = "yoshilover-gmail-app-password"
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465
MAX_FINDINGS_PER_REPORT = 3
DEFAULT_CLOUD_RUN_SERVICE = "yoshilover-fetcher"
OPERATION_SUMMARY_LOOKBACK_HOURS = 48
OPERATION_SUMMARY_WINDOW_HOURS = 24


@dataclass
class OperationsSummary:
    drafts_created: int = 0
    created_subtype_counts: dict[str, int] = field(default_factory=dict)
    publish_count: int | None = None
    skip_duplicate: int = 0
    skip_filter: int = 0
    error_count: int = 0
    x_post_count: int = 0
    fetch_error: str = ""


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _log_event(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def _now_jst() -> datetime:
    return datetime.now(JST)


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _normalize_since_filter(value: str | None) -> str:
    return acceptance_fact_check._normalize_since_filter(value)


def _target_date_label(since: str) -> str:
    normalized = _normalize_since_filter(since)
    today = _now_jst().date()
    if normalized == "today":
        target = today
    elif normalized == "yesterday":
        target = today - timedelta(days=1)
    elif normalized == "all":
        target = today
    else:
        target = datetime.strptime(normalized, "%Y-%m-%d").date()
    return target.strftime("%m/%d")


def _target_hour_label(now: datetime | None = None) -> str:
    target = (now or _now_jst()).astimezone(JST).replace(minute=0, second=0, microsecond=0)
    return target.strftime("%m/%d %H:00")


def _split_reports(reports: list[acceptance_fact_check.PostReport]) -> dict[str, list[acceptance_fact_check.PostReport]]:
    return {
        "red": [report for report in reports if report.result == "red"],
        "yellow": [report for report in reports if report.result == "yellow"],
        "green": [report for report in reports if report.result == "green"],
    }


def _summary_counts(reports: list[acceptance_fact_check.PostReport]) -> dict[str, int]:
    buckets = _split_reports(reports)
    return {
        "checked": len(reports),
        "red": len(buckets["red"]),
        "yellow": len(buckets["yellow"]),
        "green": len(buckets["green"]),
    }


def _reports_in_last_hour(
    reports: list[acceptance_fact_check.PostReport],
    *,
    now: datetime | None = None,
) -> list[acceptance_fact_check.PostReport]:
    current = (now or _now_jst()).astimezone(JST)
    window_start = current - timedelta(hours=1)
    recent_reports: list[acceptance_fact_check.PostReport] = []
    for report in reports:
        modified_at = _parse_iso_datetime(report.modified)
        if modified_at is None:
            continue
        if window_start <= modified_at <= current:
            recent_reports.append(report)
    return recent_reports


def _should_send_email(
    reports: list[acceptance_fact_check.PostReport],
    posts_in_last_hour: list[acceptance_fact_check.PostReport],
) -> tuple[bool, str]:
    if posts_in_last_hour:
        return True, "hourly_window_has_posts"
    if any(report.result == "red" for report in reports):
        return True, "red_present"
    return False, "no_change_no_red"


def build_email_subject(
    reports: list[acceptance_fact_check.PostReport],
    *,
    since: str = "yesterday",
    now: datetime | None = None,
) -> str:
    counts = _summary_counts(reports)
    del since
    return f"ヨシラバー {_target_hour_label(now)} 🔴{counts['red']} 🟡{counts['yellow']} ✅{counts['green']}"


def _report_label(report: acceptance_fact_check.PostReport) -> str:
    return f"{report.primary_category}/{report.article_subtype}"


def _finding_label(finding: acceptance_fact_check.Finding) -> str:
    return acceptance_fact_check._result_icon(finding.severity)


def _render_report_card(report: acceptance_fact_check.PostReport, *, highlight: str) -> str:
    findings_html: list[str] = []
    for finding in report.findings[:MAX_FINDINGS_PER_REPORT]:
        evidence = (
            f'<div style="margin-top:4px;font-size:12px;color:#666;">根拠: '
            f'<a href="{html.escape(finding.evidence_url)}">{html.escape(finding.evidence_url)}</a></div>'
            if finding.evidence_url
            else ""
        )
        findings_html.append(
            (
                '<li style="margin-bottom:8px;">'
                f'<strong>{_finding_label(finding)} {html.escape(finding.field)}</strong>: '
                f'{html.escape(finding.message)}'
                f'<div style="margin-top:4px;">修正方向: {html.escape(finding.proposal)}</div>'
                f"{evidence}"
                "</li>"
            )
        )
    findings_block = (
        '<ul style="padding-left:20px;margin:8px 0 0;">' + "".join(findings_html) + "</ul>"
        if findings_html
        else '<div style="margin-top:8px;color:#2e7d32;">重大な差分は検出されませんでした。</div>'
    )
    return (
        f'<div style="border:1px solid #ddd;border-left:4px solid {highlight};'
        'border-radius:8px;padding:12px 14px;margin:12px 0;background:#fff;">'
        f'<div style="font-size:14px;color:#666;">post_id={report.post_id} / {html.escape(_report_label(report))}</div>'
        f'<div style="font-size:16px;font-weight:700;margin-top:4px;">{html.escape(report.title)}</div>'
        f'<div style="margin-top:8px;"><a href="{html.escape(report.edit_url)}">WPで開く</a></div>'
        f"{findings_block}"
        "</div>"
    )


def _render_green_list(reports: list[acceptance_fact_check.PostReport]) -> str:
    if not reports:
        return '<p style="margin:8px 0 0;">該当なし</p>'
    items = "".join(
        (
            '<li style="margin-bottom:8px;">'
            f'post_id={report.post_id} '
            f'<a href="{html.escape(report.edit_url)}">{html.escape(report.title)}</a>'
            f' <span style="color:#666;">({html.escape(_report_label(report))})</span>'
            "</li>"
        )
        for report in reports
    )
    return f'<ul style="padding-left:20px;margin:8px 0 0;">{items}</ul>'


def _next_actions_html(counts: dict[str, int]) -> str:
    lines: list[str] = []
    if counts["red"]:
        lines.append("🔴記事は公開せず、WPリンクから本文とタイトルを修正する")
    if counts["yellow"]:
        lines.append("🟡記事は source と draft を見比べて human review する")
    if counts["green"]:
        lines.append("✅記事は publish 候補として受け入れ試験へ回す")
    if not lines:
        lines.append("対象 draft がありません。次回 run を待つ")
    items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    return f'<ul style="padding-left:20px;margin:8px 0 0;">{items}</ul>'


def _format_created_subtype_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "なし"
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{name}={count}" for name, count in ordered)


def _publish_summary_text(summary: OperationsSummary) -> str:
    if summary.publish_count is None:
        return "0件（Phase C 未解放）"
    return f"{summary.publish_count}件"


def _operations_summary_text(summary: OperationsSummary) -> list[str]:
    lines = [
        "📊 直近24h運用サマリ",
        "─────────────",
    ]
    if summary.fetch_error:
        lines.append(f"集計取得失敗: {summary.fetch_error}")
        return lines
    lines.extend(
        [
            f"📥 作成: {summary.drafts_created}件（{_format_created_subtype_counts(summary.created_subtype_counts)}）",
            f"📤 公開: {_publish_summary_text(summary)}",
            f"🔄 スキップ: 重複={summary.skip_duplicate} / フィルタ={summary.skip_filter} / エラー={summary.error_count}",
            f"🐦 Xポスト: {summary.x_post_count}件",
        ]
    )
    return lines


def _operations_summary_html(summary: OperationsSummary) -> str:
    if summary.fetch_error:
        body = (
            '<div style="color:#b06000;font-weight:700;">'
            f'集計取得失敗: {html.escape(summary.fetch_error)}'
            "</div>"
        )
    else:
        rows = [
            f"📥 作成: {summary.drafts_created}件（{html.escape(_format_created_subtype_counts(summary.created_subtype_counts))}）",
            f"📤 公開: {html.escape(_publish_summary_text(summary))}",
            f"🔄 スキップ: 重複={summary.skip_duplicate} / フィルタ={summary.skip_filter} / エラー={summary.error_count}",
            f"🐦 Xポスト: {summary.x_post_count}件",
        ]
        body = "".join(
            f'<div style="margin:4px 0;font-size:14px;">{html.escape(row)}</div>'
            for row in rows
        )
    return (
        '<div style="border:1px solid #ddd;border-left:4px solid #1a73e8;'
        'border-radius:8px;padding:12px 14px;margin:12px 0;background:#fff;">'
        '<div style="font-size:16px;font-weight:700;margin-bottom:8px;">📊 直近24h運用サマリ</div>'
        f"{body}"
        "</div>"
    )


def _render_fix_summary_card(title: str, items: list[acceptance_auto_fix.AutoFixDecision], *, accent: str) -> str:
    if not items:
        return "<p style=\"margin:8px 0 0;\">該当なし</p>"
    rows: list[str] = []
    for item in items:
        causes = ", ".join(item.causes[:3]) if item.causes else "none"
        notes = f"<div style=\"margin-top:4px;color:#666;\">{html.escape(' / '.join(item.notes[:2]))}</div>" if item.notes else ""
        rows.append(
            (
                '<li style="margin-bottom:10px;">'
                f'<strong>post_id={item.post_id}</strong> '
                f'<a href="{html.escape(item.edit_url)}">{html.escape(item.title)}</a>'
                f' <span style="color:#666;">({html.escape(item.primary_category)}/{html.escape(item.article_subtype)})</span>'
                f'<div style="margin-top:4px;">cause: {html.escape(causes)}</div>'
                f"{notes}"
                "</li>"
            )
        )
    return (
        f'<div style="border:1px solid #ddd;border-left:4px solid {accent};border-radius:8px;'
        'padding:12px 14px;margin:12px 0;background:#fff;">'
        f'<ul style="padding-left:20px;margin:0;">{"".join(rows)}</ul>'
        "</div>"
    )


def build_email_html(
    reports: list[acceptance_fact_check.PostReport],
    *,
    since: str = "yesterday",
    fix_summary: acceptance_auto_fix.AutoFixSummary | None = None,
    operations_summary: OperationsSummary | None = None,
    now: datetime | None = None,
) -> str:
    counts = _summary_counts(reports)
    grouped = _split_reports(reports)
    if fix_summary is None:
        fix_summary = acceptance_auto_fix.analyze_reports(reports, fetch_post_state=False)
    if operations_summary is None:
        operations_summary = OperationsSummary()
    red_section = (
        "".join(_render_report_card(report, highlight="#d93025") for report in grouped["red"])
        if grouped["red"]
        else '<p style="color:#188038;font-weight:700;">🔴 重大な事実誤りは検出されませんでした。</p>'
    )
    yellow_section = (
        "".join(_render_report_card(report, highlight="#f9ab00") for report in grouped["yellow"])
        if grouped["yellow"]
        else "<p>🟡 要確認はありません。</p>"
    )
    green_section = _render_green_list(grouped["green"])
    return f"""\
<!doctype html>
<html lang="ja">
  <body style="margin:0;padding:16px;background:#f5f5f0;color:#222;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <div style="max-width:720px;margin:0 auto;background:#ffffff;border-radius:12px;padding:20px;">
      <h1 style="font-size:22px;margin:0 0 12px;">{html.escape(build_email_subject(reports, since=since, now=now))}</h1>
      <p style="margin:0 0 16px;font-size:15px;">
        サマリ: <strong>🔴{counts['red']}件</strong> / <strong>🟡{counts['yellow']}件</strong> /
        <strong>✅{counts['green']}件</strong> / checked={counts['checked']}
      </p>
      {_operations_summary_html(operations_summary)}

      <h2 style="font-size:18px;border-left:4px solid #1a73e8;padding-left:10px;">自動修正候補</h2>
      {_render_fix_summary_card("自動修正候補", fix_summary.autofix_candidates, accent="#1a73e8")}

      <h2 style="font-size:18px;border-left:4px solid #d93025;padding-left:10px;">差し戻し推奨</h2>
      {_render_fix_summary_card("差し戻し推奨", fix_summary.rejects, accent="#d93025")}

      <h2 style="font-size:18px;border-left:4px solid #f9ab00;padding-left:10px;">手動確認必要</h2>
      {_render_fix_summary_card("手動確認必要", fix_summary.manual_reviews, accent="#f9ab00")}

      <h2 style="font-size:18px;border-left:4px solid #d93025;padding-left:10px;">🔴 要対応</h2>
      {red_section}

      <h2 style="font-size:18px;border-left:4px solid #f9ab00;padding-left:10px;">🟡 要確認</h2>
      {yellow_section}

      <h2 style="font-size:18px;border-left:4px solid #188038;padding-left:10px;">✅ 公開候補</h2>
      {green_section}

      <h2 style="font-size:18px;border-left:4px solid #1a73e8;padding-left:10px;">次のアクション</h2>
      {_next_actions_html(counts)}
    </div>
  </body>
</html>
"""


def build_email_text(
    reports: list[acceptance_fact_check.PostReport],
    *,
    since: str = "yesterday",
    fix_summary: acceptance_auto_fix.AutoFixSummary | None = None,
    operations_summary: OperationsSummary | None = None,
    now: datetime | None = None,
) -> str:
    counts = _summary_counts(reports)
    grouped = _split_reports(reports)
    if fix_summary is None:
        fix_summary = acceptance_auto_fix.analyze_reports(reports, fetch_post_state=False)
    if operations_summary is None:
        operations_summary = OperationsSummary()
    lines = [
        build_email_subject(reports, since=since, now=now),
        f"サマリ: 🔴{counts['red']}件 / 🟡{counts['yellow']}件 / ✅{counts['green']}件 / checked={counts['checked']}",
        "",
        *_operations_summary_text(operations_summary),
        "",
        "自動修正候補",
    ]
    if not fix_summary.autofix_candidates:
        lines.append("該当なし")
    for item in fix_summary.autofix_candidates:
        lines.append(f"- post_id={item.post_id} {item.title}")
        lines.append(f"  {item.edit_url}")
        if item.causes:
            lines.append(f"  cause: {', '.join(item.causes[:3])}")
    lines.extend(["", "差し戻し推奨"])
    if not fix_summary.rejects:
        lines.append("該当なし")
    for item in fix_summary.rejects:
        lines.append(f"- post_id={item.post_id} {item.title}")
        lines.append(f"  {item.edit_url}")
        if item.causes:
            lines.append(f"  cause: {', '.join(item.causes[:3])}")
        if item.notes:
            lines.append(f"  notes: {' / '.join(item.notes[:2])}")
    lines.extend(["", "手動確認必要"])
    if not fix_summary.manual_reviews:
        lines.append("該当なし")
    for item in fix_summary.manual_reviews:
        lines.append(f"- post_id={item.post_id} {item.title}")
        lines.append(f"  {item.edit_url}")
        if item.causes:
            lines.append(f"  cause: {', '.join(item.causes[:3])}")
    lines.extend(["", "🔴 要対応"])
    if not grouped["red"]:
        lines.append("重大な事実誤りは検出されませんでした。")
    for report in grouped["red"]:
        lines.append(f"- post_id={report.post_id} {report.title}")
        lines.append(f"  {report.edit_url}")
        for finding in report.findings[:MAX_FINDINGS_PER_REPORT]:
            lines.append(f"  {_finding_label(finding)} {finding.message}")
            if finding.proposal:
                lines.append(f"    修正方向: {finding.proposal}")
    lines.extend(["", "🟡 要確認"])
    if not grouped["yellow"]:
        lines.append("要確認はありません。")
    for report in grouped["yellow"]:
        lines.append(f"- post_id={report.post_id} {report.title}")
        lines.append(f"  {report.edit_url}")
        for finding in report.findings[:MAX_FINDINGS_PER_REPORT]:
            lines.append(f"  {_finding_label(finding)} {finding.message}")
            if finding.proposal:
                lines.append(f"    判断材料: {finding.proposal}")
    lines.extend(["", "✅ 公開候補"])
    if not grouped["green"]:
        lines.append("該当なし")
    for report in grouped["green"]:
        lines.append(f"- post_id={report.post_id} {report.title}")
        lines.append(f"  {report.edit_url}")
    return "\n".join(lines)


def _project_id() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.environ.get("GCP_PROJECT", "").strip()
        or os.environ.get("GCLOUD_PROJECT", "").strip()
        or ""
    )


def _logging_service_name() -> str:
    return os.environ.get("K_SERVICE", "").strip() or DEFAULT_CLOUD_RUN_SERVICE


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_log_payload(entry: dict[str, Any]) -> dict[str, Any]:
    json_payload = entry.get("jsonPayload")
    if isinstance(json_payload, dict):
        return json_payload
    text_payload = entry.get("textPayload", "")
    if not isinstance(text_payload, str) or not text_payload.strip():
        return {}
    try:
        parsed = json.loads(text_payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _merge_counter_values(target: dict[str, int], values: Any) -> None:
    if not isinstance(values, dict):
        return
    for key, raw_value in values.items():
        target[str(key)] = target.get(str(key), 0) + _coerce_int(raw_value)


def _sum_cumulative_metric(
    series: list[tuple[datetime, int]],
    *,
    window_start: datetime,
) -> int:
    ordered = sorted(series, key=lambda item: item[0])
    total = 0
    previous_value: int | None = None
    previous_date: date | None = None
    for timestamp, current_value in ordered:
        local_date = timestamp.astimezone(JST).date()
        if previous_value is None or previous_date != local_date or current_value < previous_value:
            delta = current_value
        else:
            delta = current_value - previous_value
        if timestamp >= window_start:
            total += max(delta, 0)
        previous_value = current_value
        previous_date = local_date
    return total


def _fetch_logging_entries(
    filter_text: str,
    *,
    max_entries: int = 200,
) -> list[dict[str, Any]]:
    from google.auth import default as google_auth_default
    from google.auth.transport.requests import AuthorizedSession

    project_id = _project_id()
    credentials, discovered_project = google_auth_default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    project_id = project_id or discovered_project or ""
    if not project_id:
        raise RuntimeError("logging project id is not available")

    session = AuthorizedSession(credentials)
    url = "https://logging.googleapis.com/v2/entries:list"
    entries: list[dict[str, Any]] = []
    page_token = ""
    while True:
        request_payload: dict[str, Any] = {
            "resourceNames": [f"projects/{project_id}"],
            "filter": filter_text,
            "orderBy": "timestamp desc",
            "pageSize": min(100, max_entries - len(entries)),
        }
        if page_token:
            request_payload["pageToken"] = page_token
        response = session.post(url, json=request_payload, timeout=20)
        if response.status_code >= 400:
            raise RuntimeError(f"logging read failed: {response.status_code} {response.text[:200]}")
        data = response.json()
        page_entries = data.get("entries", [])
        if isinstance(page_entries, list):
            entries.extend(entry for entry in page_entries if isinstance(entry, dict))
        if len(entries) >= max_entries:
            return entries[:max_entries]
        page_token = data.get("nextPageToken", "")
        if not page_token:
            return entries


def _load_recent_operations_summary(now: datetime | None = None) -> OperationsSummary:
    current = (now or _now_jst()).astimezone(JST)
    summary_window_start = current - timedelta(hours=OPERATION_SUMMARY_WINDOW_HOURS)
    lookup_window_start = current - timedelta(hours=OPERATION_SUMMARY_LOOKBACK_HOURS)
    service_name = _logging_service_name()
    filter_text = "\n".join(
        [
            'resource.type="cloud_run_revision"',
            f'resource.labels.service_name="{service_name}"',
            f'timestamp>="{lookup_window_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}"',
            "(",
            '  jsonPayload.event="rss_fetcher_run_summary"',
            '  OR jsonPayload.event="rss_fetcher_flow_summary"',
            '  OR textPayload:"rss_fetcher_run_summary"',
            '  OR textPayload:"rss_fetcher_flow_summary"',
            ")",
        ]
    )
    try:
        entries = _fetch_logging_entries(filter_text)
    except Exception as exc:
        return OperationsSummary(fetch_error=f"{type(exc).__name__}: {exc}")

    summary = OperationsSummary()
    x_post_series: list[tuple[datetime, int]] = []
    publish_count_found = False
    for entry in entries:
        payload = _extract_log_payload(entry)
        event = payload.get("event")
        timestamp = _parse_iso_datetime(str(entry.get("timestamp", "")))
        if not event or timestamp is None:
            continue

        if event == "rss_fetcher_run_summary":
            x_post_series.append((timestamp, _coerce_int(payload.get("x_post_count", 0))))
            if timestamp < summary_window_start:
                continue
            summary.drafts_created += _coerce_int(payload.get("drafts_created", 0))
            summary.skip_duplicate += _coerce_int(payload.get("skip_duplicate", 0))
            summary.skip_filter += _coerce_int(payload.get("skip_filter", 0))
            summary.error_count += _coerce_int(payload.get("error_count", 0))
            for key in ("publish_count", "published_count"):
                if key in payload:
                    if summary.publish_count is None:
                        summary.publish_count = 0
                    summary.publish_count += _coerce_int(payload.get(key, 0))
                    publish_count_found = True
        elif event == "rss_fetcher_flow_summary":
            if timestamp < summary_window_start:
                continue
            _merge_counter_values(summary.created_subtype_counts, payload.get("created_subtype_counts"))
            for key in ("publish_count", "published_count"):
                if key in payload:
                    if summary.publish_count is None:
                        summary.publish_count = 0
                    summary.publish_count += _coerce_int(payload.get(key, 0))
                    publish_count_found = True

    if not publish_count_found:
        summary.publish_count = None
    summary.x_post_count = _sum_cumulative_metric(x_post_series, window_start=summary_window_start)
    return summary


def _fetch_secret_from_secret_manager(secret_name: str) -> str:
    from google.auth import default as google_auth_default
    from google.auth.transport.requests import AuthorizedSession

    project_id = _project_id()
    credentials, discovered_project = google_auth_default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    project_id = project_id or discovered_project or ""
    if not project_id:
        raise RuntimeError("secret manager project id is not available")

    session = AuthorizedSession(credentials)
    url = (
        f"https://secretmanager.googleapis.com/v1/projects/{project_id}/secrets/"
        f"{secret_name}/versions/latest:access"
    )
    response = session.get(url, timeout=20)
    if response.status_code >= 400:
        raise RuntimeError(f"secret access failed: {response.status_code} {response.text[:200]}")
    payload = response.json().get("payload", {})
    encoded = payload.get("data", "")
    if not encoded:
        raise RuntimeError(f"secret {secret_name} latest version is empty")
    return base64.b64decode(encoded).decode("utf-8")


def _load_gmail_app_password() -> str:
    direct = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if direct:
        return direct
    secret_name = os.environ.get("GMAIL_APP_PASSWORD_SECRET_NAME", "").strip() or DEFAULT_GMAIL_APP_PASSWORD_SECRET
    try:
        return _fetch_secret_from_secret_manager(secret_name).strip()
    except Exception as exc:
        _log_event(
            "fact_check_secret_unavailable",
            secret_name=secret_name,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return ""


def _smtp_config() -> tuple[str, int]:
    host = os.environ.get("FACT_CHECK_SMTP_HOST", "").strip() or DEFAULT_SMTP_HOST
    try:
        port = int(os.environ.get("FACT_CHECK_SMTP_PORT", "").strip() or str(DEFAULT_SMTP_PORT))
    except ValueError:
        port = DEFAULT_SMTP_PORT
    return host, port


def _decode_smtp_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _serialize_refused_recipients(refused: Any) -> dict[str, list[Any]]:
    if not isinstance(refused, dict):
        return {}
    serialized: dict[str, list[Any]] = {}
    for recipient, response in refused.items():
        if isinstance(response, tuple) and len(response) >= 2:
            code, message = response[0], response[1]
        else:
            code, message = 0, response
        serialized[str(recipient)] = [int(code), _decode_smtp_value(message)]
    return serialized


def _serialize_smtp_response(code: Any, message: Any) -> list[Any]:
    try:
        numeric_code = int(code)
    except Exception:
        numeric_code = 0
    return [numeric_code, _decode_smtp_value(message)]


def send_email(
    *,
    subject: str,
    html_body: str,
    text_body: str,
    to_email: str,
    from_email: str,
) -> dict[str, Any]:
    password = _load_gmail_app_password()
    if not password:
        preview = {
            "mode": "demo",
            "subject": subject,
            "to_email": to_email,
            "from_email": from_email,
            "text_preview": text_body[:1200],
        }
        _log_event("fact_check_email_demo", **preview)
        print(text_body, flush=True)
        return preview

    message_id = make_msgid(domain="yoshilover.com")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Message-ID"] = message_id
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    host, port = _smtp_config()
    with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
        smtp.login(from_email, password)
        refused = smtp.send_message(msg)
        smtp_response = _serialize_smtp_response(*smtp.noop())
    return {
        "mode": "smtp",
        "subject": subject,
        "to_email": to_email,
        "from_email": from_email,
        "message_id": message_id,
        "refused_recipients": _serialize_refused_recipients(refused),
        "smtp_response": smtp_response,
    }


def run_notification(
    *,
    post_id: int | None = None,
    category: str = "",
    limit: int = 20,
    status: str = "draft",
    since: str = "yesterday",
    send: bool = True,
) -> dict[str, Any]:
    normalized_since = _normalize_since_filter(since)
    current_time = _now_jst()
    reports = acceptance_fact_check.collect_reports(
        post_id=post_id,
        category=category,
        limit=limit,
        status=status,
        since=normalized_since,
    )
    counts = _summary_counts(reports)
    posts_in_last_hour = _reports_in_last_hour(reports, now=current_time)
    should_send, reason = _should_send_email(reports, posts_in_last_hour)
    subject = build_email_subject(reports, since=normalized_since, now=current_time)
    payload = {
        "since": normalized_since,
        "post_id": post_id,
        "category": category,
        "limit": limit,
        "status": status,
        "checked_posts": counts["checked"],
        "red": counts["red"],
        "yellow": counts["yellow"],
        "green": counts["green"],
        "subject": subject,
        "reason": reason,
        "should_send": should_send,
        "posts_in_last_hour_count": len(posts_in_last_hour),
        "sent": False,
        "delivery_mode": "none",
        "html_body": "",
        "text_body": "",
        "autofix_summary": {
            "autofix_candidates": [],
            "rejects": [],
            "manual_reviews": [],
            "no_action": [],
        },
        "operations_summary": asdict(OperationsSummary()),
        "reports": [
            asdict(report)
            for report in reports
        ],
    }
    _log_event(
        "fact_check_notify_started",
        since=normalized_since,
        checked_posts=counts["checked"],
        red=counts["red"],
        yellow=counts["yellow"],
        green=counts["green"],
        reason=reason,
        posts_in_last_hour_count=len(posts_in_last_hour),
        send=send,
    )
    if not send or should_send:
        fix_summary = acceptance_auto_fix.analyze_reports(reports, fetch_post_state=True)
        operations_summary = _load_recent_operations_summary(current_time)
        payload["autofix_summary"] = {
            "autofix_candidates": [asdict(item) for item in fix_summary.autofix_candidates],
            "rejects": [asdict(item) for item in fix_summary.rejects],
            "manual_reviews": [asdict(item) for item in fix_summary.manual_reviews],
            "no_action": [asdict(item) for item in fix_summary.no_action],
        }
        payload["operations_summary"] = asdict(operations_summary)
        payload["html_body"] = build_email_html(
            reports,
            since=normalized_since,
            fix_summary=fix_summary,
            operations_summary=operations_summary,
            now=current_time,
        )
        payload["text_body"] = build_email_text(
            reports,
            since=normalized_since,
            fix_summary=fix_summary,
            operations_summary=operations_summary,
            now=current_time,
        )

    if not send:
        return payload

    if not should_send:
        payload["delivery_mode"] = "skipped"
        _log_event(
            "fact_check_email_skipped",
            since=normalized_since,
            checked_posts=counts["checked"],
            red=counts["red"],
            yellow=counts["yellow"],
            green=counts["green"],
            reason=reason,
            posts_in_last_hour_count=len(posts_in_last_hour),
            subject=subject,
        )
        return payload

    to_email = os.environ.get("FACT_CHECK_EMAIL_TO", "").strip() or DEFAULT_FACT_CHECK_EMAIL
    from_email = os.environ.get("FACT_CHECK_EMAIL_FROM", "").strip() or DEFAULT_FACT_CHECK_EMAIL
    try:
        delivery = send_email(
            subject=subject,
            html_body=payload["html_body"],
            text_body=payload["text_body"],
            to_email=to_email,
            from_email=from_email,
        )
    except Exception as exc:
        payload["error"] = str(exc)
        _log_event(
            "fact_check_email_failed",
            since=normalized_since,
            checked_posts=counts["checked"],
            red=counts["red"],
            yellow=counts["yellow"],
            green=counts["green"],
            reason=reason,
            posts_in_last_hour_count=len(posts_in_last_hour),
            error_type=type(exc).__name__,
            error=str(exc),
            to_email=to_email,
        )
        raise

    payload["delivery_mode"] = delivery.get("mode", "smtp")
    payload["sent"] = payload["delivery_mode"] == "smtp"
    if payload["sent"]:
        _log_event(
            "fact_check_email_sent",
            since=normalized_since,
            checked_posts=counts["checked"],
            red=counts["red"],
            yellow=counts["yellow"],
            green=counts["green"],
            reason=reason,
            posts_in_last_hour_count=len(posts_in_last_hour),
            to_email=to_email,
            subject=subject,
            message_id=delivery.get("message_id"),
            refused_recipients=delivery.get("refused_recipients", {}),
            smtp_response=delivery.get("smtp_response"),
        )
    else:
        _log_event(
            "fact_check_email_demo_ready",
            since=normalized_since,
            checked_posts=counts["checked"],
            red=counts["red"],
            yellow=counts["yellow"],
            green=counts["green"],
            reason=reason,
            posts_in_last_hour_count=len(posts_in_last_hour),
            to_email=to_email,
            subject=subject,
        )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="acceptance_fact_check の結果を HTML メールで通知する")
    parser.add_argument("--post-id", type=int, help="単一 post_id だけ通知")
    parser.add_argument("--category", default="", help="primary category または article_subtype で絞る")
    parser.add_argument("--limit", type=int, default=20, help="対象件数")
    parser.add_argument("--status", default="draft", help="取得する投稿 status")
    parser.add_argument("--since", default="yesterday", help="today / yesterday / YYYY-MM-DD / all")
    parser.add_argument("--send", action="store_true", help="実際にメール送信する")
    parser.add_argument("--json", action="store_true", help="JSON で結果を出力")
    args = parser.parse_args()

    payload = run_notification(
        post_id=args.post_id,
        category=args.category,
        limit=args.limit,
        status=args.status,
        since=args.since,
        send=args.send,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(payload["subject"])
    print(payload["text_body"])


if __name__ == "__main__":
    main()
