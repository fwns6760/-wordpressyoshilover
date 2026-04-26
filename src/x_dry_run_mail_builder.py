"""Build and optionally send X dry-run mail digests for recent published posts."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
import re
from typing import Any, Literal
from zoneinfo import ZoneInfo

from src.mail_delivery_bridge import MailRequest, MailResult, send as bridge_send_default
from src.publish_notice_email_sender import resolve_recipients
from src.x_published_poster import PublishedArticle
from src.x_post_eligibility_evaluator import WHY_ELIGIBLE_ALL_GREEN, evaluate_published_posts
from src.x_post_template_candidates import TemplateCandidate, generate_template_candidates


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_LIMIT = 5
TARGET_CATEGORY_NAMES = ("試合速報", "選手情報", "首脳陣")
NON_TARGET_CATEGORY_REASON = "non_target_category"
FILTER_REFUSED_REASON = "x_post_eligibility_refused"
NO_TEMPLATE_REASON = "no_accepted_template_candidate"
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class XDryRunMailItem:
    post_id: int | str
    title: str
    category: str
    canonical_url: str
    x_post_text: str
    template_type: str
    why_eligible: str = WHY_ELIGIBLE_ALL_GREEN

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "category": self.category,
            "canonical_url": self.canonical_url,
            "x_post_text": self.x_post_text,
            "template_type": self.template_type,
            "why_eligible": self.why_eligible,
        }


@dataclass(frozen=True)
class XDryRunMailSkippedPost:
    post_id: int | str
    title: str
    category_names: tuple[str, ...]
    reason: str
    detail: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "title": self.title,
            "category_names": list(self.category_names),
            "reason": self.reason,
            "detail": list(self.detail),
        }


@dataclass(frozen=True)
class XDryRunMailBuild:
    requested_limit: int
    fetched_posts: int
    built_items: tuple[XDryRunMailItem, ...]
    skipped_posts: tuple[XDryRunMailSkippedPost, ...]
    subject: str
    body_text: str

    @property
    def item_count(self) -> int:
        return len(self.built_items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_limit": self.requested_limit,
            "fetched_posts": self.fetched_posts,
            "item_count": self.item_count,
            "skipped_count": len(self.skipped_posts),
            "subject": self.subject,
            "body_text": self.body_text,
            "items": [item.to_dict() for item in self.built_items],
            "skipped_posts": [item.to_dict() for item in self.skipped_posts],
        }


@dataclass(frozen=True)
class XDryRunMailSendResult:
    status: Literal["sent", "dry_run", "suppressed"]
    reason: str | None
    subject: str | None
    recipients: list[str]
    item_count: int
    bridge_result: MailResult | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "subject": self.subject,
            "recipients": list(self.recipients),
            "item_count": self.item_count,
            "bridge_result": None
            if self.bridge_result is None
            else {
                "status": self.bridge_result.status,
                "reason": self.bridge_result.reason,
                "refused_recipients": self.bridge_result.refused_recipients,
                "smtp_response": self.bridge_result.smtp_response,
            },
        }


BridgeSend = Callable[..., MailResult]


def _now_jst(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def _normalize_text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("raw") or value.get("rendered") or ""
    return _WHITESPACE_RE.sub(" ", unescape(str(value or ""))).strip()


def _extract_rendered(value: Any) -> str:
    if isinstance(value, dict):
        rendered = value.get("rendered")
        if rendered is not None:
            return str(rendered)
        raw = value.get("raw")
        if raw is not None:
            return str(raw)
    return "" if value is None else str(value)


def _extract_first_paragraph(value: str) -> str:
    text = str(value or "")
    start = text.find("<p")
    if start < 0:
        return text
    end = text.find("</p>", start)
    if end < 0:
        return text
    return text[start : end + 4]


def _article_from_wp_post(payload: Mapping[str, Any]) -> PublishedArticle:
    return PublishedArticle(
        article_id=payload.get("id") or "",
        title=_extract_rendered(payload.get("title")),
        excerpt=_extract_rendered(payload.get("excerpt")),
        body_first_paragraph=_extract_first_paragraph(_extract_rendered(payload.get("content"))),
        canonical_url=str(payload.get("link") or ""),
        published_at=payload.get("date") or payload.get("date_gmt"),
        post_status=str(payload.get("status") or ""),
    )


def _category_name_map(wp_client: Any) -> dict[int, str]:
    category_map: dict[int, str] = {}
    for category in wp_client.get_categories():
        try:
            category_id = int(category["id"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(category.get("name") or "").strip()
        if name:
            category_map[category_id] = name
    return category_map


def _post_category_names(post: Mapping[str, Any], category_map: Mapping[int, str]) -> tuple[str, ...]:
    names: list[str] = []
    for raw_category_id in post.get("categories") or []:
        try:
            category_id = int(raw_category_id)
        except (TypeError, ValueError):
            continue
        name = str(category_map.get(category_id) or "").strip()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _target_category(category_names: Sequence[str]) -> str | None:
    for name in category_names:
        if name in TARGET_CATEGORY_NAMES:
            return name
    return None


def _refused_reason_map(report: Mapping[str, Any]) -> dict[int, tuple[str, ...]]:
    refused: dict[int, tuple[str, ...]] = {}
    for entry in report.get("x_refused") or []:
        try:
            post_id = int(entry["post_id"])
        except (KeyError, TypeError, ValueError):
            continue
        reasons = tuple(str(reason) for reason in entry.get("refuse_reasons") or [] if str(reason))
        refused[post_id] = reasons
    return refused


def _eligible_map(report: Mapping[str, Any]) -> dict[int, str]:
    eligible: dict[int, str] = {}
    for entry in report.get("x_eligible") or []:
        try:
            post_id = int(entry["post_id"])
        except (KeyError, TypeError, ValueError):
            continue
        eligible[post_id] = str(entry.get("why_eligible") or WHY_ELIGIBLE_ALL_GREEN)
    return eligible


def _select_best_candidate(candidates: Sequence[TemplateCandidate]) -> TemplateCandidate | None:
    return candidates[0] if candidates else None


def build_subject(*, limit: int = DEFAULT_LIMIT, now: datetime | None = None) -> str:
    current = _now_jst(now)
    return f"[X-DRY-RUN] X 文案 {int(limit)} 件確認 ({current.strftime('%Y-%m-%d')})"


def build_body_text(
    *,
    requested_limit: int,
    fetched_posts: int,
    items: Sequence[XDryRunMailItem],
    skipped_posts: Sequence[XDryRunMailSkippedPost],
) -> str:
    lines = [
        "X Dry Run Mail",
        f"requested_limit: {int(requested_limit)}",
        f"fetched_posts: {int(fetched_posts)}",
        f"built_posts: {len(items)}",
        f"skipped_posts: {len(skipped_posts)}",
        "x_api_calls: 0",
    ]
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                "",
                f"post {index}",
                f"post_id: {item.post_id}",
                f"title: {item.title}",
                f"category: {item.category}",
                f"template_type: {item.template_type}",
                f"why_eligible: {item.why_eligible}",
                f"url: {item.canonical_url}",
                "x_text:",
                item.x_post_text,
            ]
        )
    if skipped_posts:
        lines.extend(["", "skipped"])
        for entry in skipped_posts:
            category_text = ",".join(entry.category_names) if entry.category_names else "unknown"
            detail_text = ",".join(entry.detail) if entry.detail else "-"
            lines.append(
                f"- post_id={entry.post_id} | title={entry.title} | categories={category_text} | "
                f"reason={entry.reason} | detail={detail_text}"
            )
    lines.extend(["", "注意: X API call 0 件、live 投稿なし"])
    return "\n".join(lines) + "\n"


def build_x_dry_run_mail(
    wp_client: Any,
    *,
    limit: int = DEFAULT_LIMIT,
    now: datetime | None = None,
) -> XDryRunMailBuild:
    scan_limit = max(1, int(limit))
    posts = list(
        wp_client.list_posts(
            status="publish",
            per_page=scan_limit,
            page=1,
            orderby="date",
            order="desc",
            context="edit",
        )
    )
    category_map = _category_name_map(wp_client)
    eligibility_report = evaluate_published_posts(
        posts,
        limit=scan_limit,
        orderby="date",
        order="desc",
        now=now,
        fetched_count=len(posts),
    )
    eligible_map = _eligible_map(eligibility_report)
    refused_map = _refused_reason_map(eligibility_report)

    items: list[XDryRunMailItem] = []
    skipped_posts: list[XDryRunMailSkippedPost] = []

    for post in posts[:scan_limit]:
        post_id = post.get("id") or ""
        title = _normalize_text(post.get("title"))
        category_names = _post_category_names(post, category_map)
        target_category = _target_category(category_names)
        if target_category is None:
            skipped_posts.append(
                XDryRunMailSkippedPost(
                    post_id=post_id,
                    title=title,
                    category_names=category_names,
                    reason=NON_TARGET_CATEGORY_REASON,
                )
            )
            continue

        normalized_post_id = int(post_id)
        why_eligible = eligible_map.get(normalized_post_id)
        if why_eligible is None:
            skipped_posts.append(
                XDryRunMailSkippedPost(
                    post_id=post_id,
                    title=title,
                    category_names=category_names,
                    reason=FILTER_REFUSED_REASON,
                    detail=refused_map.get(normalized_post_id, ()),
                )
            )
            continue

        candidate_batch = generate_template_candidates(_article_from_wp_post(post))
        best_candidate = _select_best_candidate(candidate_batch.accepted)
        if best_candidate is None:
            skipped_posts.append(
                XDryRunMailSkippedPost(
                    post_id=post_id,
                    title=title,
                    category_names=category_names,
                    reason=NO_TEMPLATE_REASON,
                    detail=tuple(
                        str(candidate.refuse_reason)
                        for candidate in candidate_batch.refused
                        if candidate.refuse_reason
                    ),
                )
            )
            continue

        items.append(
            XDryRunMailItem(
                post_id=post_id,
                title=title,
                category=target_category,
                canonical_url=str(post.get("link") or ""),
                x_post_text=best_candidate.text,
                template_type=best_candidate.template_type,
                why_eligible=why_eligible,
            )
        )

    subject = build_subject(limit=scan_limit, now=now)
    body_text = build_body_text(
        requested_limit=scan_limit,
        fetched_posts=len(posts[:scan_limit]),
        items=items,
        skipped_posts=skipped_posts,
    )
    return XDryRunMailBuild(
        requested_limit=scan_limit,
        fetched_posts=len(posts[:scan_limit]),
        built_items=tuple(items),
        skipped_posts=tuple(skipped_posts),
        subject=subject,
        body_text=body_text,
    )


def _suppressed(
    reason: str,
    *,
    recipients: Sequence[str] | None = None,
    item_count: int = 0,
) -> XDryRunMailSendResult:
    return XDryRunMailSendResult(
        status="suppressed",
        reason=reason,
        subject=None,
        recipients=list(recipients or []),
        item_count=max(0, int(item_count)),
        bridge_result=None,
    )


def send_x_dry_run_mail(
    payload: XDryRunMailBuild,
    *,
    dry_run: bool = True,
    bridge_send: BridgeSend = bridge_send_default,
    override_recipient: list[str] | None = None,
) -> XDryRunMailSendResult:
    if not payload.subject.strip():
        return _suppressed("EMPTY_SUBJECT", item_count=payload.item_count)
    if not payload.body_text.strip():
        return _suppressed("EMPTY_BODY", item_count=payload.item_count)
    if payload.item_count <= 0:
        return _suppressed("NO_ITEMS", item_count=payload.item_count)

    recipients = resolve_recipients(override_recipient)
    if not recipients:
        return _suppressed("NO_RECIPIENT", recipients=recipients, item_count=payload.item_count)

    if dry_run:
        return XDryRunMailSendResult(
            status="dry_run",
            reason=None,
            subject=payload.subject,
            recipients=recipients,
            item_count=payload.item_count,
            bridge_result=None,
        )

    mail_request = MailRequest(
        to=recipients,
        subject=payload.subject,
        text_body=payload.body_text,
        metadata={
            "notice_kind": "x_dry_run",
            "item_count": payload.item_count,
            "requested_limit": payload.requested_limit,
        },
    )
    bridge_result = bridge_send(mail_request, dry_run=False)
    if bridge_result.status == "suppressed":
        return XDryRunMailSendResult(
            status="suppressed",
            reason=bridge_result.reason,
            subject=None,
            recipients=recipients,
            item_count=payload.item_count,
            bridge_result=bridge_result,
        )
    if bridge_result.status == "dry_run":
        return XDryRunMailSendResult(
            status="dry_run",
            reason=bridge_result.reason,
            subject=payload.subject,
            recipients=recipients,
            item_count=payload.item_count,
            bridge_result=bridge_result,
        )
    return XDryRunMailSendResult(
        status="sent",
        reason=bridge_result.reason,
        subject=payload.subject,
        recipients=recipients,
        item_count=payload.item_count,
        bridge_result=bridge_result,
    )


__all__ = [
    "DEFAULT_LIMIT",
    "FILTER_REFUSED_REASON",
    "JST",
    "NON_TARGET_CATEGORY_REASON",
    "NO_TEMPLATE_REASON",
    "TARGET_CATEGORY_NAMES",
    "XDryRunMailBuild",
    "XDryRunMailItem",
    "XDryRunMailSendResult",
    "XDryRunMailSkippedPost",
    "build_body_text",
    "build_subject",
    "build_x_dry_run_mail",
    "send_x_dry_run_mail",
]
