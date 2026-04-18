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
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

import acceptance_fact_check

JST = timezone(timedelta(hours=9))
TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_FACT_CHECK_EMAIL = "fwns6760@gmail.com"
DEFAULT_GMAIL_APP_PASSWORD_SECRET = "yoshilover-gmail-app-password"
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 465
MAX_FINDINGS_PER_REPORT = 3


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _log_event(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def _normalize_since_filter(value: str | None) -> str:
    return acceptance_fact_check._normalize_since_filter(value)


def _target_date_label(since: str) -> str:
    normalized = _normalize_since_filter(since)
    today = datetime.now(JST).date()
    if normalized == "today":
        target = today
    elif normalized == "yesterday":
        target = today - timedelta(days=1)
    elif normalized == "all":
        target = today
    else:
        target = datetime.strptime(normalized, "%Y-%m-%d").date()
    return target.strftime("%m/%d")


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


def build_email_subject(reports: list[acceptance_fact_check.PostReport], *, since: str = "yesterday") -> str:
    counts = _summary_counts(reports)
    return (
        f"【ヨシラバー】{_target_date_label(since)} 事実チェック結果"
        f"（🔴{counts['red']}件 / 🟡{counts['yellow']}件 / ✅{counts['green']}件）"
    )


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


def build_email_html(reports: list[acceptance_fact_check.PostReport], *, since: str = "yesterday") -> str:
    counts = _summary_counts(reports)
    grouped = _split_reports(reports)
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
      <h1 style="font-size:22px;margin:0 0 12px;">ヨシラバー 事実チェック結果 {_target_date_label(since)}</h1>
      <p style="margin:0 0 16px;font-size:15px;">
        サマリ: <strong>🔴{counts['red']}件</strong> / <strong>🟡{counts['yellow']}件</strong> /
        <strong>✅{counts['green']}件</strong> / checked={counts['checked']}
      </p>

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


def build_email_text(reports: list[acceptance_fact_check.PostReport], *, since: str = "yesterday") -> str:
    counts = _summary_counts(reports)
    grouped = _split_reports(reports)
    lines = [
        f"ヨシラバー 事実チェック結果 {_target_date_label(since)}",
        f"サマリ: 🔴{counts['red']}件 / 🟡{counts['yellow']}件 / ✅{counts['green']}件 / checked={counts['checked']}",
        "",
        "🔴 要対応",
    ]
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

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    host, port = _smtp_config()
    with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
        smtp.login(from_email, password)
        smtp.send_message(msg)
    return {"mode": "smtp", "subject": subject, "to_email": to_email, "from_email": from_email}


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
    reports = acceptance_fact_check.collect_reports(
        post_id=post_id,
        category=category,
        limit=limit,
        status=status,
        since=normalized_since,
    )
    counts = _summary_counts(reports)
    subject = build_email_subject(reports, since=normalized_since)
    html_body = build_email_html(reports, since=normalized_since)
    text_body = build_email_text(reports, since=normalized_since)
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
        "sent": False,
        "delivery_mode": "none",
        "text_body": text_body,
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
        send=send,
    )
    if not send:
        return payload

    to_email = os.environ.get("FACT_CHECK_EMAIL_TO", "").strip() or DEFAULT_FACT_CHECK_EMAIL
    from_email = os.environ.get("FACT_CHECK_EMAIL_FROM", "").strip() or DEFAULT_FACT_CHECK_EMAIL
    try:
        delivery = send_email(
            subject=subject,
            html_body=html_body,
            text_body=text_body,
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
            to_email=to_email,
            subject=subject,
        )
    else:
        _log_event(
            "fact_check_email_demo_ready",
            since=normalized_since,
            checked_posts=counts["checked"],
            red=counts["red"],
            yellow=counts["yellow"],
            green=counts["green"],
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
