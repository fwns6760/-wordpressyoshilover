"""
audit_notify.py -- 直近更新記事を監査して問題がある時だけメール通知する
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

import acceptance_fact_check
import draft_audit
import fact_check_notifier
from wp_client import WPClient

JST = timezone(timedelta(hours=9))
TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_WINDOW_MINUTES = 60
MAX_POST_PAGES = 5
POSTS_PER_PAGE = 100
MAX_EXCERPT_CHARS = 200
STATUS_TO_AUDIT = ("draft", "publish")
AUDIT_AXES = (
    "title_body_mismatch",
    "thin_body",
    "no_opinion",
    "no_eyecatch",
    "pipeline_error",
)
AUDIT_AXIS_LABELS = {
    "title_body_mismatch": "タイトル矛盾",
    "thin_body": "薄さ",
    "no_opinion": "意見なし",
    "no_eyecatch": "アイキャッチ",
    "pipeline_error": "pipeline",
}
TITLE_MISMATCH_FIELDS = {"opponent", "venue", "time", "score", "lineup", "subject", "notice_type"}
THIN_BODY_THRESHOLDS = {
    "postgame": 280,
    "lineup": 280,
    "column": 350,
    "manager": 350,
}
OPINION_MARKERS = (
    "と思います",
    "と思う",
    "と感じます",
    "と感じました",
    "と見ています",
    "ではないでしょうか",
    "でしょう",
    "ですね",
    "個人的に",
    "期待したい",
    "期待しています",
    "不安",
    "注目です",
    "気になります",
    "見たいところです",
)
OPINION_MARKER_STEMS = (
    "見たい",
    "気になる",
    "気になり",
    "注目した",
    "注目し",
    "期待し",
    "期待した",
    "と感じ",
    "と思い",
    "と思う",
    "ではないでしょうか",
    "でしょう",
    "ですね",
    "個人的",
    "不安",
)
PIPELINE_ERROR_EVENTS = {
    "featured_media_lookup_failed",
    "x_post_ai_failed",
}


@dataclass
class AuditFinding:
    post_id: int
    title: str
    status: str
    primary_category: str
    article_subtype: str
    edit_url: str
    axis: str
    excerpt: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "status": self.status,
            "primary_category": self.primary_category,
            "article_subtype": self.article_subtype,
            "edit_url": self.edit_url,
            "axis": self.axis,
            "excerpt": self.excerpt,
        }


class _CoreBodyHTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._skip_div_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_div_depth:
            if tag == "div":
                self._skip_div_depth += 1
            return
        attrs_map = {key: value or "" for key, value in attrs}
        classes = set((attrs_map.get("class") or "").split())
        if tag == "div" and "yoshilover-related-posts" in classes:
            self._skip_div_depth = 1
            return
        self._parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if self._skip_div_depth:
            if tag == "div":
                self._skip_div_depth -= 1
            return
        self._parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_div_depth:
            return
        self._parts.append(self.get_starttag_text())

    def handle_data(self, data: str) -> None:
        if not self._skip_div_depth:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self._skip_div_depth:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip_div_depth:
            self._parts.append(f"&#{name};")

    def get_html(self) -> str:
        return "".join(self._parts)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


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


def _normalize_window_minutes(value: int | str | None) -> int:
    try:
        normalized = int(value or DEFAULT_WINDOW_MINUTES)
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_MINUTES
    return normalized if normalized > 0 else DEFAULT_WINDOW_MINUTES


def _post_title(post: dict[str, Any]) -> str:
    title_data = post.get("title") or {}
    return (title_data.get("raw") or title_data.get("rendered") or "").strip()


def _post_content_html(post: dict[str, Any]) -> str:
    content_data = post.get("content") or {}
    return content_data.get("raw") or content_data.get("rendered") or ""


def _post_time_candidates(post: dict[str, Any]) -> list[datetime]:
    values = []
    for field in ("date", "modified"):
        parsed = _parse_iso_datetime(str(post.get(field) or ""))
        if parsed is not None:
            values.append(parsed)
    return values


def _post_is_in_window(post: dict[str, Any], *, window_start: datetime, current: datetime) -> bool:
    return any(window_start <= stamp <= current for stamp in _post_time_candidates(post))


def _post_sort_key(post: dict[str, Any]) -> datetime:
    values = _post_time_candidates(post)
    return max(values) if values else datetime.min.replace(tzinfo=JST)


def _strip_related_posts_section(content_html: str) -> str:
    parser = _CoreBodyHTMLStripper()
    parser.feed(content_html or "")
    parser.close()
    return parser.get_html()


def _core_body_text(content_html: str) -> str:
    return acceptance_fact_check._strip_html_text(_strip_related_posts_section(content_html or ""))


def _truncate_text(value: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _excerpt_from_post(post: dict[str, Any]) -> str:
    return _truncate_text(_core_body_text(_post_content_html(post)))


def _list_recent_posts(
    wp: WPClient,
    *,
    window_minutes: int,
    now: datetime,
) -> list[dict[str, Any]]:
    window_start = now - timedelta(minutes=window_minutes)
    fields = ["id", "date", "modified", "status", "title", "content", "categories", "link", "featured_media"]
    selected: dict[int, dict[str, Any]] = {}

    for status in STATUS_TO_AUDIT:
        for page in range(1, MAX_POST_PAGES + 1):
            posts = wp.list_posts(
                status=status,
                per_page=POSTS_PER_PAGE,
                page=page,
                orderby="modified",
                order="desc",
                context="edit",
                fields=fields,
            )
            if not posts:
                break

            page_has_recent_posts = False
            for post in posts:
                post_id = int(post.get("id") or 0)
                if not post_id:
                    continue
                if _post_is_in_window(post, window_start=window_start, current=now):
                    selected[post_id] = post
                    page_has_recent_posts = True

            if len(posts) < POSTS_PER_PAGE:
                break

            oldest = _parse_iso_datetime(str(posts[-1].get("modified") or posts[-1].get("date") or ""))
            if oldest is not None and oldest < window_start and not page_has_recent_posts:
                break

    return sorted(selected.values(), key=_post_sort_key, reverse=True)


def _build_category_map(wp: WPClient) -> dict[int, str]:
    return {int(row["id"]): row["name"] for row in wp.get_categories()}


def _thin_body_threshold(primary_category: str, article_subtype: str) -> int:
    subtype = (article_subtype or "").strip().lower()
    if subtype in THIN_BODY_THRESHOLDS:
        return THIN_BODY_THRESHOLDS[subtype]
    if (primary_category or "").strip() == "コラム":
        return THIN_BODY_THRESHOLDS["column"]
    return 0


def _build_finding(
    *,
    axis: str,
    audited: dict[str, Any],
    excerpt: str,
    post_id: int | None = None,
    title: str | None = None,
    status: str | None = None,
    edit_url: str | None = None,
    primary_category: str | None = None,
    article_subtype: str | None = None,
) -> AuditFinding:
    return AuditFinding(
        post_id=int(post_id if post_id is not None else audited.get("id") or 0),
        title=title if title is not None else str(audited.get("title") or ""),
        status=status if status is not None else str(audited.get("status") or ""),
        primary_category=primary_category if primary_category is not None else str(audited.get("primary_category") or ""),
        article_subtype=article_subtype if article_subtype is not None else str(audited.get("article_subtype") or ""),
        edit_url=edit_url if edit_url is not None else str(audited.get("edit_url") or ""),
        axis=axis,
        excerpt=excerpt,
    )


def _title_body_mismatch_finding(
    audited: dict[str, Any],
    report: acceptance_fact_check.PostReport,
    excerpt: str,
) -> AuditFinding | None:
    for finding in report.findings:
        if finding.field in TITLE_MISMATCH_FIELDS:
            return _build_finding(axis="title_body_mismatch", audited=audited, excerpt=excerpt)
    return None


def _thin_body_finding(audited: dict[str, Any], post: dict[str, Any], excerpt: str) -> AuditFinding | None:
    threshold = _thin_body_threshold(str(audited.get("primary_category") or ""), str(audited.get("article_subtype") or ""))
    if not threshold:
        return None
    if len(_core_body_text(_post_content_html(post))) >= threshold:
        return None
    return _build_finding(axis="thin_body", audited=audited, excerpt=excerpt)


def _no_opinion_finding(audited: dict[str, Any], post: dict[str, Any], excerpt: str) -> AuditFinding | None:
    core_text = _core_body_text(_post_content_html(post))
    if not core_text:
        return _build_finding(axis="no_opinion", audited=audited, excerpt=excerpt)
    if any(marker in core_text for marker in OPINION_MARKERS) or any(
        stem in core_text for stem in OPINION_MARKER_STEMS
    ):
        return None
    return _build_finding(axis="no_opinion", audited=audited, excerpt=excerpt)


def _no_eyecatch_finding(audited: dict[str, Any], post: dict[str, Any], excerpt: str) -> AuditFinding | None:
    if int(post.get("featured_media") or 0) > 0:
        return None
    return _build_finding(axis="no_eyecatch", audited=audited, excerpt=excerpt)


def _service_logging_filter(window_start: datetime, *clauses: str) -> str:
    service_name = fact_check_notifier._logging_service_name()
    parts = [
        'resource.type="cloud_run_revision"',
        f'resource.labels.service_name="{service_name}"',
        f'timestamp>="{window_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}"',
    ]
    parts.extend(clause for clause in clauses if clause)
    return "\n".join(parts)


def _fetch_pipeline_error_post_events(window_start: datetime) -> dict[int, str]:
    filter_text = _service_logging_filter(
        window_start,
        "(",
        '  jsonPayload.event="featured_media_lookup_failed"',
        '  OR jsonPayload.event="x_post_ai_failed"',
        '  OR textPayload:"featured_media_lookup_failed"',
        '  OR textPayload:"x_post_ai_failed"',
        ")",
    )
    try:
        entries = fact_check_notifier._fetch_logging_entries(filter_text, max_entries=200)
    except Exception:
        return {}

    by_post_id: dict[int, str] = {}
    for entry in entries:
        payload = fact_check_notifier._extract_log_payload(entry)
        event = str(payload.get("event") or "")
        if event not in PIPELINE_ERROR_EVENTS:
            continue
        try:
            post_id = int(payload.get("post_id") or 0)
        except (TypeError, ValueError):
            post_id = 0
        if post_id > 0 and post_id not in by_post_id:
            by_post_id[post_id] = event
    return by_post_id


def _fetch_pipeline_error_count(window_start: datetime) -> int:
    filter_text = _service_logging_filter(
        window_start,
        "(",
        '  jsonPayload.event="rss_fetcher_run_summary"',
        '  OR textPayload:"rss_fetcher_run_summary"',
        ")",
    )
    try:
        entries = fact_check_notifier._fetch_logging_entries(filter_text, max_entries=120)
    except Exception:
        return 0

    error_count = 0
    for entry in entries:
        payload = fact_check_notifier._extract_log_payload(entry)
        if payload.get("event") != "rss_fetcher_run_summary":
            continue
        error_count += fact_check_notifier._coerce_int(payload.get("error_count", 0))
    return error_count


def _build_pipeline_error_findings(
    *,
    posts_by_id: dict[int, dict[str, Any]],
    audited_by_id: dict[int, dict[str, Any]],
    excerpts_by_id: dict[int, str],
    window_minutes: int,
    now: datetime,
) -> list[AuditFinding]:
    window_start = now - timedelta(minutes=window_minutes)
    post_events = _fetch_pipeline_error_post_events(window_start)
    findings: list[AuditFinding] = []
    for post_id, _event in sorted(post_events.items()):
        if post_id not in posts_by_id or post_id not in audited_by_id:
            continue
        findings.append(
            _build_finding(
                axis="pipeline_error",
                audited=audited_by_id[post_id],
                excerpt=excerpts_by_id.get(post_id, ""),
            )
        )

    if findings:
        return findings

    error_count = _fetch_pipeline_error_count(window_start)
    if error_count <= 0:
        return []

    return [
        AuditFinding(
            post_id=0,
            title=f"Cloud Run pipeline summary (last {window_minutes}m)",
            status="system",
            primary_category="system",
            article_subtype="",
            edit_url="",
            axis="pipeline_error",
            excerpt=f"直近{window_minutes}分の rss_fetcher_run_summary で error_count={error_count}",
        )
    ]


def _counts_payload(findings: list[AuditFinding]) -> dict[str, int]:
    counts = Counter(finding.axis for finding in findings)
    return {axis: counts.get(axis, 0) for axis in AUDIT_AXES}


def _group_findings(findings: list[AuditFinding]) -> dict[str, list[AuditFinding]]:
    grouped: dict[str, list[AuditFinding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.axis].append(finding)
    for axis in AUDIT_AXES:
        grouped[axis].sort(key=lambda item: (item.post_id == 0, item.post_id, item.title))
    return grouped


def _build_mail_subject(counts: dict[str, int], total: int) -> str:
    return (
        f"[yoshilover] 問題 {total} 件（"
        f"タイトル矛盾 {counts['title_body_mismatch']} / "
        f"薄さ {counts['thin_body']} / "
        f"意見なし {counts['no_opinion']} / "
        f"アイキャッチ {counts['no_eyecatch']} / "
        f"pipeline {counts['pipeline_error']}）"
    )


def _finding_line_label(finding: AuditFinding) -> str:
    category = finding.primary_category or "unknown"
    subtype = finding.article_subtype or "-"
    return f"post_id={finding.post_id} [{finding.status}] {category}/{subtype} {finding.title}"


def _build_mail_text(findings: list[AuditFinding], *, counts: dict[str, int], total: int, window_minutes: int) -> str:
    grouped = _group_findings(findings)
    lines = [
        _build_mail_subject(counts, total),
        f"window_minutes: {window_minutes}",
        "counts:",
    ]
    for axis in AUDIT_AXES:
        lines.append(f"- {axis}: {counts[axis]}")

    for axis in AUDIT_AXES:
        lines.extend(["", f"[{AUDIT_AXIS_LABELS[axis]}] {counts[axis]}件"])
        if not grouped[axis]:
            lines.append("該当なし")
            continue
        for finding in grouped[axis]:
            lines.append(f"- {_finding_line_label(finding)}")
            if finding.edit_url:
                lines.append(f"  {finding.edit_url}")
            if finding.excerpt:
                lines.append(f"  抜粋: {finding.excerpt}")
    return "\n".join(lines)


def _build_mail_html(findings: list[AuditFinding], *, counts: dict[str, int], total: int, window_minutes: int) -> str:
    grouped = _group_findings(findings)
    summary_rows = "".join(
        f'<li><strong>{html.escape(AUDIT_AXIS_LABELS[axis])}</strong>: {counts[axis]}件</li>'
        for axis in AUDIT_AXES
    )
    sections: list[str] = []
    for axis in AUDIT_AXES:
        items = grouped[axis]
        if not items:
            body = "<p style=\"margin:8px 0 0;\">該当なし</p>"
        else:
            rows = []
            for finding in items:
                link_html = (
                    f'<div style="margin-top:4px;"><a href="{html.escape(finding.edit_url)}">WPで開く</a></div>'
                    if finding.edit_url
                    else ""
                )
                excerpt_html = (
                    f'<div style="margin-top:6px;color:#444;">{html.escape(finding.excerpt)}</div>'
                    if finding.excerpt
                    else ""
                )
                rows.append(
                    "<li style=\"margin-bottom:12px;\">"
                    f"<strong>{html.escape(_finding_line_label(finding))}</strong>"
                    f"{link_html}{excerpt_html}</li>"
                )
            body = f'<ul style="padding-left:20px;margin:8px 0 0;">{"".join(rows)}</ul>'
        sections.append(
            '<div style="margin-top:18px;">'
            f'<h2 style="font-size:18px;border-left:4px solid #1a73e8;padding-left:10px;">{html.escape(AUDIT_AXIS_LABELS[axis])} ({counts[axis]}件)</h2>'
            f"{body}</div>"
        )

    return f"""\
<!doctype html>
<html lang="ja">
  <body style="margin:0;padding:16px;background:#f5f5f0;color:#222;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
    <div style="max-width:760px;margin:0 auto;background:#fff;border-radius:12px;padding:20px;">
      <h1 style="font-size:22px;margin:0 0 12px;">{html.escape(_build_mail_subject(counts, total))}</h1>
      <p style="margin:0 0 12px;">window_minutes: {window_minutes}</p>
      <ul style="padding-left:20px;margin:0 0 12px;">{summary_rows}</ul>
      {"".join(sections)}
    </div>
  </body>
</html>
"""


def run_audit_notification(
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    send: bool = True,
    now: datetime | None = None,
    wp: WPClient | None = None,
) -> dict[str, Any]:
    current = (now or _now_jst()).astimezone(JST)
    normalized_window = _normalize_window_minutes(window_minutes)
    wp_client = wp or WPClient()
    category_map = _build_category_map(wp_client)
    source_catalog = draft_audit.load_source_catalog()
    posts = _list_recent_posts(wp_client, window_minutes=normalized_window, now=current)

    audited_by_id: dict[int, dict[str, Any]] = {}
    excerpts_by_id: dict[int, str] = {}
    posts_by_id: dict[int, dict[str, Any]] = {int(post["id"]): post for post in posts if post.get("id")}
    findings: list[AuditFinding] = []

    for post in posts:
        post_id = int(post.get("id") or 0)
        if not post_id:
            continue
        audited = draft_audit.audit_post(post, category_map, source_catalog, wp_client.base_url)
        audited_by_id[post_id] = audited
        excerpt = _excerpt_from_post(post)
        excerpts_by_id[post_id] = excerpt

        try:
            report = acceptance_fact_check.build_post_report(post, category_map, source_catalog, wp_client.base_url)
        except Exception as exc:
            findings.append(
                _build_finding(
                    axis="pipeline_error",
                    audited=audited,
                    excerpt=_truncate_text(f"audit build failed: {type(exc).__name__}: {exc}"),
                )
            )
            report = None

        if report is not None:
            mismatch_finding = _title_body_mismatch_finding(audited, report, excerpt)
            if mismatch_finding is not None:
                findings.append(mismatch_finding)

        thin_body_finding = _thin_body_finding(audited, post, excerpt)
        if thin_body_finding is not None:
            findings.append(thin_body_finding)

        no_opinion_finding = _no_opinion_finding(audited, post, excerpt)
        if no_opinion_finding is not None:
            findings.append(no_opinion_finding)

        no_eyecatch_finding = _no_eyecatch_finding(audited, post, excerpt)
        if no_eyecatch_finding is not None:
            findings.append(no_eyecatch_finding)

    findings.extend(
        _build_pipeline_error_findings(
            posts_by_id=posts_by_id,
            audited_by_id=audited_by_id,
            excerpts_by_id=excerpts_by_id,
            window_minutes=normalized_window,
            now=current,
        )
    )

    findings.sort(key=lambda item: (AUDIT_AXES.index(item.axis), item.post_id == 0, item.post_id, item.title))
    counts = _counts_payload(findings)
    payload = {
        "window_minutes": normalized_window,
        "counts": counts,
        "total": len(findings),
        "mail_sent": False,
        "findings": [finding.as_payload() for finding in findings],
    }
    if not findings or not send:
        fact_check_notifier._log_event(
            "audit_notify_completed",
            window_minutes=normalized_window,
            counts=counts,
            total=len(findings),
            mail_sent=False,
            opinion_check_mode="gemini" if _env_flag("AUDIT_OPINION_USE_LLM", False) else "rule",
        )
        return payload

    subject = _build_mail_subject(counts, len(findings))
    text_body = _build_mail_text(findings, counts=counts, total=len(findings), window_minutes=normalized_window)
    html_body = _build_mail_html(findings, counts=counts, total=len(findings), window_minutes=normalized_window)
    to_email = os.environ.get("FACT_CHECK_EMAIL_TO", "").strip() or fact_check_notifier.DEFAULT_FACT_CHECK_EMAIL
    from_email = os.environ.get("FACT_CHECK_EMAIL_FROM", "").strip() or fact_check_notifier.DEFAULT_FACT_CHECK_EMAIL
    delivery = fact_check_notifier.send_email(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        to_email=to_email,
        from_email=from_email,
    )
    payload["mail_sent"] = delivery.get("mode") == "smtp"
    fact_check_notifier._log_event(
        "audit_notify_completed",
        window_minutes=normalized_window,
        counts=counts,
        total=len(findings),
        mail_sent=payload["mail_sent"],
        opinion_check_mode="gemini" if _env_flag("AUDIT_OPINION_USE_LLM", False) else "rule",
        delivery_mode=delivery.get("mode", "unknown"),
        message_id=delivery.get("message_id", ""),
        refused_recipients=delivery.get("refused_recipients", {}),
        smtp_response=delivery.get("smtp_response", []),
    )
    return payload
