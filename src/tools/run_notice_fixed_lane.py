"""Canary fixed-lane runner for NPB transaction notices.

This runner creates at most one Draft post per execution for the
``fact_notice`` fixed lane. It only accepts the primary NPB notice page,
checks ``candidate_id`` duplicates via WordPress REST, and never publishes.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any, Sequence

import requests

from src.source_id import source_id as build_source_id
from src.source_trust import classify_url
from src.wp_client import WPClient


NPB_NOTICE_URL = "https://npb.jp/announcement/roster/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MAX_CANARY_POSTS = 1

TARGET_SUBTYPE = "fact_notice"
TARGET_CATEGORY_NAME = "選手情報"
TARGET_TAGS = ["公示"]
TARGET_ARTICLE_TYPE = "transaction_notice"
TARGET_SOURCE_TRUST = "primary"
TARGET_BATCH_SOURCE = "sync"
TARGET_TEAM = "読売ジャイアンツ"

EXIT_OK = 0
EXIT_WP_POST_DRY_RUN_FAILED = 40
EXIT_WP_POST_FAILED = 41
EXIT_INPUT_ERROR = 42

_DATE_HEADING_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日の出場選手登録、登録抹消")
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b.*?>.*?</\1>")
_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class NoticeEntry:
    action: str
    position: str
    number: str
    player_name: str


@dataclass(frozen=True)
class NoticeCandidate:
    source_url: str
    source_id: str
    notice_date: str
    title: str
    body_html: str
    metadata: dict[str, Any]


def _emit_event(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _reason_from_response(resp: requests.Response) -> str:
    status = getattr(resp, "status_code", 0)
    if status == 401:
        return "application_password_unauthorized"
    if status == 403:
        return "wp_permission_forbidden"
    if status == 404:
        return "posts_endpoint_not_found"
    if status:
        return f"http_{status}"
    return "unknown_response"


def _request_error_reason(exc: Exception) -> str:
    name = exc.__class__.__name__
    text = str(exc).strip()
    if "NameResolutionError" in text or "Failed to resolve" in text:
        return "dns_resolution_failed"
    if text and text != name:
        normalized = re.sub(r"[^a-zA-Z0-9:_-]+", "_", text).strip("_")
        if normalized:
            return normalized[:120]
    return name


def _notice_date_label(notice_date: str) -> str:
    return f"{int(notice_date[4:6])}月{int(notice_date[6:8])}日"


def _format_name_list(entries: Sequence[NoticeEntry]) -> str:
    names = [entry.player_name for entry in entries]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}と{names[1]}"
    return f"{names[0]}ら{len(names)}人"


def _build_title(notice_date: str, registered: Sequence[NoticeEntry], deregistered: Sequence[NoticeEntry]) -> str:
    date_label = _notice_date_label(notice_date)
    if registered and deregistered:
        return (
            f"【公示】{date_label} 巨人は{_format_name_list(registered)}を登録、"
            f"{_format_name_list(deregistered)}を抹消"
        )
    if registered:
        return f"【公示】{date_label} 巨人は{_format_name_list(registered)}を出場選手登録"
    return f"【公示】{date_label} 巨人は{_format_name_list(deregistered)}を登録抹消"


def _build_candidate_id(source_url: str, notice_date: str) -> str:
    return f"{build_source_id(source_url)}:{TARGET_ARTICLE_TYPE}:{notice_date}"


def _build_summary_line(notice_date: str, registered: Sequence[NoticeEntry], deregistered: Sequence[NoticeEntry]) -> str:
    date_label = _notice_date_label(notice_date)
    if registered and deregistered:
        return (
            f"{date_label}のNPB公示で、巨人は{_format_name_list(registered)}を出場選手登録し、"
            f"{_format_name_list(deregistered)}を登録抹消しました。"
        )
    if registered:
        return f"{date_label}のNPB公示で、巨人は{_format_name_list(registered)}を出場選手登録しました。"
    return f"{date_label}のNPB公示で、巨人は{_format_name_list(deregistered)}を登録抹消しました。"


def _entry_list_html(entries: Sequence[NoticeEntry], label: str) -> str:
    if not entries:
        return f"<li>{label}: なし</li>"
    items = [
        f"<li>{label}: {entry.player_name}（{entry.position} / 背番号{entry.number}）</li>"
        for entry in entries
    ]
    return "".join(items)


def _build_body_html(
    notice_date: str,
    registered: Sequence[NoticeEntry],
    deregistered: Sequence[NoticeEntry],
    source_url: str,
    deregister_note: str = "",
) -> str:
    summary_line = _build_summary_line(notice_date, registered, deregistered)
    note_html = f"<p>{deregister_note}</p>" if deregister_note else ""
    return "".join(
        [
            f'<p>一次情報: <a href="{source_url}" target="_blank" rel="noopener noreferrer">NPB公示</a></p>',
            "<h2>【公示の要旨】</h2>",
            f"<p>{summary_line}</p>",
            "<h3>【対象選手の基本情報】</h3>",
            "<ul>",
            _entry_list_html(registered, "出場選手登録"),
            _entry_list_html(deregistered, "登録抹消"),
            "</ul>",
            "<h3>【公示の背景】</h3>",
            "<p>この固定版Draftは、NPB公示に出ている一次情報だけを先に整理したものです。</p>",
            note_html,
            "<h3>【今後の注目点】</h3>",
            "<p>起用の詳細や次の再登録タイミングは、球団発表と次の試合前情報で確認したいところです。</p>",
        ]
    )


def _html_to_lines(html_text: str) -> list[str]:
    text = _SCRIPT_STYLE_RE.sub("\n", html_text or "")
    text = _COMMENT_RE.sub("\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|ul|ol|tr|h1|h2|h3|h4|h5|h6|section|article|main|table|tbody|thead)>", "\n", text)
    text = re.sub(r"(?i)<t[dh][^>]*>", " ", text)
    text = re.sub(r"(?i)</t[dh]>", " ", text)
    text = _TAG_RE.sub("", text)
    raw_lines = unescape(text).splitlines()
    lines = []
    for raw_line in raw_lines:
        normalized = re.sub(r"[\s\u3000]+", " ", raw_line).strip()
        if normalized:
            lines.append(normalized)
    return lines


def _parse_notice_row(line: str, action: str) -> NoticeEntry | None:
    if not line.startswith(TARGET_TEAM):
        return None
    parts = line.split()
    if len(parts) < 5:
        return None
    team, position, number, *name_parts = parts
    if team != TARGET_TEAM:
        return None
    player_name = "".join(name_parts)
    if not player_name:
        return None
    return NoticeEntry(
        action=action,
        position=position,
        number=number,
        player_name=player_name,
    )


def _parse_latest_notice_from_html(html_text: str, source_url: str = NPB_NOTICE_URL) -> NoticeCandidate | None:
    lines = _html_to_lines(html_text)
    date_index = -1
    notice_date = ""
    for idx, line in enumerate(lines):
        match = _DATE_HEADING_RE.search(line)
        if not match:
            continue
        year, month, day = match.groups()
        notice_date = f"{int(year):04d}{int(month):02d}{int(day):02d}"
        date_index = idx
        break
    if date_index < 0 or not notice_date:
        raise ValueError("notice_date_not_found")

    league = ""
    current_action = ""
    registered: list[NoticeEntry] = []
    deregistered: list[NoticeEntry] = []
    deregister_note = ""

    for line in lines[date_index + 1:]:
        if line == "セントラル・リーグ":
            league = "central"
            continue
        if line == "パシフィック・リーグ":
            break
        if "出場選手一覧" in line:
            break
        if league != "central":
            continue
        if line == "出場選手登録":
            current_action = "register"
            continue
        if line in {"出場選手登録抹消", "登録抹消"}:
            current_action = "deregister"
            continue
        if line == "なし":
            continue
        if line.startswith("※"):
            if current_action == "deregister":
                deregister_note = line
            continue
        entry = _parse_notice_row(line, current_action)
        if entry is None:
            continue
        if entry.action == "register":
            registered.append(entry)
        elif entry.action == "deregister":
            deregistered.append(entry)

    if not registered and not deregistered:
        return None

    title = _build_title(notice_date, registered, deregistered)
    body_html = _build_body_html(
        notice_date=notice_date,
        registered=registered,
        deregistered=deregistered,
        source_url=source_url,
        deregister_note=deregister_note,
    )
    candidate_id = _build_candidate_id(source_url, notice_date)
    metadata: dict[str, Any] = {
        "subtype": TARGET_SUBTYPE,
        "article_subtype": TARGET_SUBTYPE,
        "article_type": TARGET_ARTICLE_TYPE,
        "category": TARGET_CATEGORY_NAME,
        "tags": list(TARGET_TAGS),
        "candidate_id": candidate_id,
        "source_trust": TARGET_SOURCE_TRUST,
        "batch_source": TARGET_BATCH_SOURCE,
        "source_id": build_source_id(source_url),
        "source_urls": [source_url],
        WPClient.SOURCE_URL_META_KEY: source_url,
    }
    return NoticeCandidate(
        source_url=source_url,
        source_id=build_source_id(source_url),
        notice_date=notice_date,
        title=title,
        body_html=body_html,
        metadata=metadata,
    )


def _fetch_latest_notice_candidate(source_url: str = NPB_NOTICE_URL) -> NoticeCandidate | None:
    if classify_url(source_url) != TARGET_SOURCE_TRUST:
        return None
    try:
        resp = requests.get(
            source_url,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(_request_error_reason(exc)) from exc
    return _parse_latest_notice_from_html(resp.text, source_url=source_url)


def _run_wp_post_dry_run(wp: WPClient, *, now: datetime | None = None) -> str:
    probe_now = now or datetime.now()
    probe_title = probe_now.strftime("canary-probe-%Y%m%d-%H%M%S")
    payload = {
        "title": probe_title,
        "content": "<p>canary probe</p>",
        "status": "draft",
    }
    try:
        resp = requests.post(
            f"{wp.api}/posts",
            json=payload,
            auth=wp.auth,
            headers=wp.headers,
            timeout=30,
        )
    except requests.RequestException as exc:
        reason = _request_error_reason(exc)
        _emit_event("wp_post_dry_run_fail", reason=reason)
        return f"fail:{reason}"

    if resp.status_code != 201:
        reason = _reason_from_response(resp)
        _emit_event("wp_post_dry_run_fail", reason=reason, status_code=resp.status_code)
        return f"fail:{reason}"

    post_id = resp.json().get("id")
    if not post_id:
        _emit_event("wp_post_dry_run_fail", reason="missing_post_id")
        return "fail:missing_post_id"

    try:
        delete_resp = requests.delete(
            f"{wp.api}/posts/{post_id}",
            params={"force": "true"},
            auth=wp.auth,
            timeout=30,
        )
        wp._raise_for_status(delete_resp, f"疎通確認後削除 post_id={post_id}")
    except Exception as exc:
        reason = _request_error_reason(exc)
        _emit_event("wp_post_dry_run_fail", reason=f"delete_failed:{reason}", post_id=post_id)
        return f"fail:delete_failed:{reason}"

    _emit_event("wp_post_dry_run_pass", post_id=post_id)
    return "pass"


def _find_duplicate_posts(wp: WPClient, candidate_id: str) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{wp.api}/posts",
        params={
            "status": "draft,publish",
            "meta_key": "candidate_id",
            "meta_value": candidate_id,
            "per_page": 100,
            "orderby": "date",
            "order": "desc",
        },
        auth=wp.auth,
        timeout=30,
    )
    wp._raise_for_status(resp, f"candidate_id重複確認 candidate_id={candidate_id}")
    rows = resp.json()
    return rows if isinstance(rows, list) else []


def _create_notice_draft(wp: WPClient, candidate: NoticeCandidate, category_id: int) -> int | None:
    payload = {
        "title": candidate.title,
        "content": candidate.body_html,
        "status": "draft",
        "categories": [category_id] if category_id else [],
        "meta": candidate.metadata,
    }
    last_reason = ""
    for attempt in range(1, 3):
        try:
            resp = requests.post(
                f"{wp.api}/posts",
                json=payload,
                auth=wp.auth,
                headers=wp.headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            last_reason = _request_error_reason(exc)
        else:
            if resp.status_code == 201:
                post_id = resp.json().get("id")
                if post_id:
                    _emit_event(
                        "canary_post_created",
                        post_id=post_id,
                        candidate_id=candidate.metadata["candidate_id"],
                        attempt=attempt,
                    )
                    return int(post_id)
                last_reason = "missing_post_id"
            else:
                last_reason = _reason_from_response(resp)
        if attempt < 2:
            _emit_event(
                "canary_post_retry",
                attempt=attempt,
                candidate_id=candidate.metadata["candidate_id"],
                reason=last_reason,
            )
    _emit_event(
        "canary_post_failed",
        candidate_id=candidate.metadata["candidate_id"],
        reason=last_reason or "unknown",
    )
    return None


def _process_candidates(
    wp: WPClient,
    candidates: Sequence[NoticeCandidate],
    *,
    category_id: int,
) -> tuple[int | None, bool]:
    created_post_id: int | None = None
    duplicate_skip = False
    for candidate in list(candidates)[:MAX_CANARY_POSTS]:
        duplicates = _find_duplicate_posts(wp, candidate.metadata["candidate_id"])
        if duplicates:
            duplicate_skip = True
            _emit_event(
                "duplicate_skip",
                candidate_id=candidate.metadata["candidate_id"],
                existing_post_ids=[row.get("id") for row in duplicates],
            )
            continue
        created_post_id = _create_notice_draft(wp, candidate, category_id)
    return created_post_id, duplicate_skip


def run(argv: Sequence[str] | None = None) -> tuple[int, dict[str, Any]]:
    del argv
    summary: dict[str, Any] = {
        "wp_post_dry_run": "fail:not_run",
        "source_fetch": "skip:not_run",
        "canary_post_id": None,
        "canary_candidate_id": None,
        "duplicate_skip": False,
        "duplicate_check_implemented": True,
        "max_canary_cap": MAX_CANARY_POSTS,
        "published_write": False,
    }

    try:
        wp = WPClient()
    except Exception as exc:
        reason = _request_error_reason(exc)
        summary["wp_post_dry_run"] = f"fail:{reason}"
        return EXIT_INPUT_ERROR, summary

    summary["wp_post_dry_run"] = _run_wp_post_dry_run(wp)
    if summary["wp_post_dry_run"] != "pass":
        return EXIT_WP_POST_DRY_RUN_FAILED, summary

    try:
        candidate = _fetch_latest_notice_candidate()
    except Exception as exc:
        reason = _request_error_reason(exc)
        _emit_event("source_fetch_fail", reason=reason)
        summary["source_fetch"] = f"fail:{reason}"
        return EXIT_OK, summary

    if candidate is None:
        _emit_event("source_fetch_skip", reason="no_giants_notice_found")
        summary["source_fetch"] = "skip:no_giants_notice_found"
        return EXIT_OK, summary

    summary["source_fetch"] = "pass"
    summary["canary_candidate_id"] = candidate.metadata["candidate_id"]

    category_id = wp.resolve_category_id(TARGET_CATEGORY_NAME)
    if not category_id:
        _emit_event("category_resolve_fail", category=TARGET_CATEGORY_NAME)
        return EXIT_INPUT_ERROR, summary

    created_post_id, duplicate_skip = _process_candidates(
        wp,
        [candidate],
        category_id=category_id,
    )
    summary["duplicate_skip"] = duplicate_skip
    if created_post_id is None:
        if duplicate_skip:
            return EXIT_OK, summary
        return EXIT_WP_POST_FAILED, summary

    summary["canary_post_id"] = created_post_id
    return EXIT_OK, summary


def main(argv: Sequence[str] | None = None) -> int:
    code, summary = run(argv)
    print(json.dumps(summary, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
