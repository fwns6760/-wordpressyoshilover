"""
acceptance_fact_check.py -- draft 記事の事実確認と修正提案を行う

使用例:
    python3 -m src.acceptance_fact_check --post-id 62538
    python3 -m src.acceptance_fact_check --category postgame --limit 10
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).parent.parent
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from draft_audit import (
    _strip_html as _strip_html_fragment,
    audit_post,
    extract_source_links,
    load_source_catalog,
)
from rss_fetcher import (
    NPB_TEAM_MARKERS,
    TITLE_VENUE_MARKERS,
    _detect_article_subtype,
    _extract_notice_subject_and_type,
    _extract_recovery_subject,
    _extract_subject_label,
)
from sports_fetcher import get_game_result, get_starters
from wp_client import WPClient

JST = timezone(timedelta(hours=9))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
MAX_SOURCE_SNAPSHOTS = 2
MAX_TWEET_URL_CHECKS = 3
TEAM_ALIASES = {
    "横浜DeNAベイスターズ": "DeNA",
    "ベイスターズ": "DeNA",
    "東京ヤクルトスワローズ": "ヤクルト",
    "阪神タイガース": "阪神",
    "中日ドラゴンズ": "中日",
    "広島東洋カープ": "広島",
    "福岡ソフトバンクホークス": "ソフトバンク",
    "北海道日本ハムファイターズ": "日本ハム",
    "千葉ロッテマリーンズ": "ロッテ",
    "東北楽天ゴールデンイーグルス": "楽天",
    "オリックス・バファローズ": "オリックス",
    "埼玉西武ライオンズ": "西武",
}
VENUE_ALIASES = {
    "みずほPayPayドーム福岡": "PayPay",
    "PayPayドーム": "PayPay",
    "明治神宮野球場": "神宮",
    "阪神甲子園球場": "甲子園",
    "横浜スタジアム": "横浜",
    "バンテリンドーム ナゴヤ": "バンテリン",
    "MAZDA Zoom-Zoom スタジアム広島": "マツダ",
    "ZOZOマリンスタジアム": "ZOZOマリン",
    "楽天モバイルパーク宮城": "楽天モバイル",
    "京セラドーム大阪": "京セラ",
    "エスコンフィールドHOKKAIDO": "エスコン",
}
TEAM_PATTERN = tuple(dict.fromkeys([*NPB_TEAM_MARKERS, *TEAM_ALIASES.keys()]))
VENUE_PATTERN = tuple(
    dict.fromkeys([*TITLE_VENUE_MARKERS, *VENUE_ALIASES.keys(), "東京ドーム", "神宮", "甲子園", "横浜"])
)
TEAM_MATCH_RE = re.compile(
    "|".join(re.escape(marker) for marker in sorted(TEAM_PATTERN, key=len, reverse=True))
)
HISTORICAL_GAME_REF_RE = re.compile(
    rf"(?:\d{{1,2}}月)?\d{{1,2}}日(?:{ '|'.join(re.escape(marker) for marker in sorted(TEAM_PATTERN, key=len, reverse=True)) })戦"
)
SCORE_RE = re.compile(r"(\d{1,2})[－\-–](\d{1,2})")
TIME_RE = re.compile(r"([01]?\d|2[0-3]):([0-5]\d)")
DATE_RE = re.compile(r"(?:(\d{1,2})月(\d{1,2})日|(\d{1,2})/(\d{1,2}))")
GAME_ID_RE = re.compile(r"/npb/game/(\d+)/(?:score|top)")
META_RE = re.compile(r'<meta[^>]+(?:property|name)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']+)["\']', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
TWITTER_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/[^\s\"'<>]+/status/\d+", re.I)
LINEUP_ROW_RE = re.compile(
    r"<tr>\s*<td>(\d)</td>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>(?:\s*<td>([^<]+)</td>)?",
    re.I | re.S,
)
NPB_DATE_ROW_START_RE = re.compile(r'<tr id="date(?P<date>\d{4})"[^>]*>', re.I)
NPB_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
NPB_TEAM1_RE = re.compile(r'<div class="team1">(.*?)</div>', re.I | re.S)
NPB_TEAM2_RE = re.compile(r'<div class="team2">(.*?)</div>', re.I | re.S)
NPB_PLACE_RE = re.compile(r'<div class="place">(.*?)</div>', re.I | re.S)
NPB_TIME_RE = re.compile(r'<div class="time">(.*?)</div>', re.I | re.S)
NPB_SCORE1_RE = re.compile(r'<div class="score1">(.*?)</div>', re.I | re.S)
NPB_SCORE2_RE = re.compile(r'<div class="score2">(.*?)</div>', re.I | re.S)


@dataclass
class Finding:
    severity: str
    field: str
    current: str
    expected: str
    evidence_url: str
    message: str
    cause: str
    proposal: str
    fix_type: str = ""
    auto_fix: dict[str, Any] = field(default_factory=dict)


@dataclass
class PostReport:
    post_id: int
    title: str
    status: str
    primary_category: str
    article_subtype: str
    modified: str
    edit_url: str
    result: str
    findings: list[Finding]
    source_urls: list[str]


def _strip_html_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_strip_html_fragment(value or ""))).strip()


def _normalize_team(value: str) -> str:
    text = re.sub(r"\s+", "", html.unescape((value or "").strip()))
    if not text:
        return ""
    return TEAM_ALIASES.get(text, text)


def _normalize_venue(value: str) -> str:
    text = re.sub(r"\s+", "", html.unescape((value or "").strip()))
    if not text:
        return ""
    return VENUE_ALIASES.get(text, text)


def _normalize_time(value: str) -> str:
    match = TIME_RE.search(value or "")
    if not match:
        return ""
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def _normalize_score(value: str) -> str:
    match = SCORE_RE.search(value or "")
    if not match:
        return ""
    return f"{int(match.group(1))}-{int(match.group(2))}"


def _find_first_marker(text: str, markers: tuple[str, ...], *, normalize=None, exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    for marker in markers:
        if marker in text:
            value = normalize(marker) if normalize else marker
            if value and value not in exclude:
                return value
    return ""


def _extract_team_mentions(text: str) -> list[str]:
    found: list[str] = []
    for match in TEAM_MATCH_RE.finditer(text or ""):
        normalized = _normalize_team(match.group(0))
        if normalized and normalized not in found:
            found.append(normalized)
    return found


def _extract_opponent(text: str) -> str:
    historical_spans = [match.span() for match in HISTORICAL_GAME_REF_RE.finditer(text or "")]
    for match in TEAM_MATCH_RE.finditer(text or ""):
        normalized = _normalize_team(match.group(0))
        if not normalized or normalized in {"巨人", "読売ジャイアンツ"}:
            continue
        if any(start <= match.start() and match.end() <= end for start, end in historical_spans):
            continue
        return normalized
    return ""


def _extract_venue(text: str) -> str:
    return _find_first_marker(text, VENUE_PATTERN, normalize=_normalize_venue)


def _extract_time(text: str) -> str:
    return _normalize_time(text)


def _extract_score(text: str) -> str:
    return _normalize_score(text)


def _extract_lineup_rows_from_html(content_html: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for order, position, name, avg in LINEUP_ROW_RE.findall(content_html or ""):
        rows.append(
            {
                "order": order.strip(),
                "position": _strip_html_text(position),
                "name": _strip_html_text(name),
                "avg": _strip_html_text(avg),
            }
        )
    deduped: list[dict[str, str]] = []
    seen = set()
    for row in rows:
        key = (row["order"], row["name"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[:9]


def _extract_tweet_urls(content_html: str) -> list[str]:
    urls: list[str] = []
    for url in TWITTER_URL_RE.findall(content_html or ""):
        normalized = url.replace("https://x.com/", "https://twitter.com/")
        if normalized not in urls:
            urls.append(normalized)
    return urls


def _extract_date_hint(text: str, fallback_date: date) -> date:
    match = DATE_RE.search(text or "")
    if not match:
        return fallback_date
    month = match.group(1) or match.group(3)
    day = match.group(2) or match.group(4)
    try:
        return date(fallback_date.year, int(month), int(day))
    except Exception:
        return fallback_date


def _post_local_date(post: dict) -> date:
    raw = post.get("modified") or post.get("date") or ""
    if not raw:
        return datetime.now(JST).date()
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(JST).date()
    if parsed.tzinfo:
        return parsed.astimezone(JST).date()
    return parsed.date()


def _extract_subject(title: str, summary_text: str, category: str, article_subtype: str) -> tuple[str, str]:
    if article_subtype == "notice":
        subject, notice_type = _extract_notice_subject_and_type(title, summary_text)
        return subject, notice_type
    if article_subtype == "recovery":
        return _extract_recovery_subject(title, summary_text), ""
    return _extract_subject_label(title, summary_text, category), ""


def _extract_post_facts(post: dict, audited: dict) -> dict[str, Any]:
    title = post.get("title", {}).get("raw") or post.get("title", {}).get("rendered") or ""
    content_html = post.get("content", {}).get("raw") or post.get("content", {}).get("rendered") or ""
    plain = _strip_html_text(content_html)
    target_date = _extract_date_hint(f"{title} {plain}", _post_local_date(post))
    subject, notice_type = _extract_subject(title, plain, audited["primary_category"], audited["article_subtype"])
    return {
        "title": title,
        "plain_text": plain,
        "target_date": target_date,
        "opponent": _extract_opponent(f"{title} {plain}"),
        "venue": _extract_venue(f"{title} {plain}"),
        "time": _extract_time(f"{title} {plain}"),
        "score": _extract_score(f"{title} {plain}"),
        "lineup_rows": _extract_lineup_rows_from_html(content_html),
        "tweet_urls": _extract_tweet_urls(content_html),
        "subject": subject,
        "notice_type": notice_type,
        "source_links": extract_source_links(content_html),
    }


@lru_cache(maxsize=128)
def _fetch_url_snapshot(url: str) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "status_code": 0,
            "error": str(exc),
            "title": "",
            "description": "",
            "text": "",
            "html": "",
        }

    html_text = response.text or ""
    meta = {key.lower(): value for key, value in META_RE.findall(html_text)}
    title_match = TITLE_RE.search(html_text)
    page_title = _strip_html_text(meta.get("og:title") or meta.get("twitter:title") or (title_match.group(1) if title_match else ""))
    description = _strip_html_text(meta.get("description") or meta.get("og:description") or meta.get("twitter:description") or "")
    text = _strip_html_text(html_text)[:4000]
    return {
        "url": url,
        "ok": response.status_code < 400,
        "status_code": response.status_code,
        "title": page_title,
        "description": description,
        "text": text,
        "html": html_text,
    }


def _source_reference_facts(source_links: list[dict[str, str]]) -> dict[str, Any]:
    merged_text = ""
    snapshots = []
    field_evidence_urls: dict[str, str] = {}
    for item in source_links[:MAX_SOURCE_SNAPSHOTS]:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        snapshot = _fetch_url_snapshot(url)
        snapshots.append(snapshot)
        snapshot_text = " ".join([snapshot.get("title", ""), snapshot.get("description", ""), snapshot.get("text", "")[:800]])
        merged_text += " " + snapshot_text
        if "opponent" not in field_evidence_urls and _extract_opponent(snapshot_text):
            field_evidence_urls["opponent"] = snapshot.get("url", "")
        if "time" not in field_evidence_urls and _extract_time(snapshot_text):
            field_evidence_urls["time"] = snapshot.get("url", "")
    merged_text = merged_text.strip()
    return {
        "snapshots": snapshots,
        "opponent": _extract_opponent(merged_text),
        "time": _extract_time(merged_text),
        "venue": "",
        "score": "",
        "subject": merged_text,
        "field_evidence_urls": field_evidence_urls,
    }


@lru_cache(maxsize=64)
def _find_yahoo_game_id(target_date: str, opponent_hint: str = "") -> str:
    date_token = target_date.replace("-", "")
    urls = [
        "https://baseball.yahoo.co.jp/npb/teams/1/schedule/",
        f"https://baseball.yahoo.co.jp/npb/schedule/?year={date_token[:4]}&month={date_token[4:6]}",
    ]
    candidate_ids: list[str] = []
    for url in urls:
        snapshot = _fetch_url_snapshot(url)
        for game_id in GAME_ID_RE.findall(snapshot.get("html", "")):
            if game_id not in candidate_ids:
                candidate_ids.append(game_id)
    for game_id in candidate_ids:
        if date_token and date_token in game_id:
            if opponent_hint:
                score_snapshot = _fetch_url_snapshot(f"https://baseball.yahoo.co.jp/npb/game/{game_id}/score")
                if opponent_hint in " ".join([score_snapshot.get("title", ""), score_snapshot.get("text", "")]):
                    return game_id
            else:
                return game_id
    return candidate_ids[0] if candidate_ids else ""


def _extract_npb_schedule_day_html(html_text: str, dt: date) -> str:
    marker = f'date{dt.month:02d}{dt.day:02d}'
    start = html_text.find(marker)
    if start == -1:
        return ""
    row_start = html_text.rfind("<tr", 0, start)
    if row_start == -1:
        return ""
    next_match = NPB_DATE_ROW_START_RE.search(html_text, row_start + 1)
    row_end = next_match.start() if next_match else len(html_text)
    return html_text[row_start:row_end]


def _parse_npb_schedule_rows(day_html: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row_html in NPB_ROW_RE.findall(day_html or ""):
        team1_match = NPB_TEAM1_RE.search(row_html)
        team2_match = NPB_TEAM2_RE.search(row_html)
        place_match = NPB_PLACE_RE.search(row_html)
        if not team1_match or not team2_match or not place_match:
            continue
        row = {
            "team1": _normalize_team(_strip_html_text(team1_match.group(1))),
            "team2": _normalize_team(_strip_html_text(team2_match.group(1))),
            "place": _normalize_venue(_strip_html_text(place_match.group(1))),
            "time": "",
            "score": "",
        }
        time_match = NPB_TIME_RE.search(row_html)
        if time_match:
            row["time"] = _normalize_time(_strip_html_text(time_match.group(1)))
        score1_match = NPB_SCORE1_RE.search(row_html)
        score2_match = NPB_SCORE2_RE.search(row_html)
        score1 = _normalize_score(_strip_html_text(score1_match.group(1))) if score1_match else ""
        score2 = _normalize_score(_strip_html_text(score2_match.group(1))) if score2_match else ""
        if score1 and score2:
            row["score"] = f"{score1}-{score2}"
        elif score1_match and score2_match:
            raw1 = _strip_html_text(score1_match.group(1))
            raw2 = _strip_html_text(score2_match.group(1))
            if raw1.isdigit() and raw2.isdigit():
                row["score"] = f"{int(raw1)}-{int(raw2)}"
        rows.append(row)
    return rows


def _select_npb_schedule_row(rows: list[dict[str, str]], opponent_hint: str = "") -> dict[str, str]:
    normalized_hint = _normalize_team(opponent_hint)
    giants_names = {"巨人", "読売ジャイアンツ"}
    for row in rows:
        teams = {row.get("team1", ""), row.get("team2", "")}
        if not teams & giants_names:
            continue
        if normalized_hint and normalized_hint not in teams:
            continue
        return row
    for row in rows:
        teams = {row.get("team1", ""), row.get("team2", "")}
        if teams & giants_names:
            return row
    return {}


@lru_cache(maxsize=64)
def _fetch_npb_schedule_snapshot(target_date: str, opponent_hint: str = "") -> dict[str, Any]:
    dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    url = f"https://npb.jp/games/{dt.year}/schedule_{dt.month:02d}_detail.html"
    snapshot = _fetch_url_snapshot(url)
    day_html = _extract_npb_schedule_day_html(snapshot.get("html", ""), dt)
    rows = _parse_npb_schedule_rows(day_html)
    selected = _select_npb_schedule_row(rows, opponent_hint=opponent_hint)
    score = ""
    if selected.get("score"):
        if selected.get("team1") in {"巨人", "読売ジャイアンツ"}:
            score = selected["score"]
        else:
            first, second = selected["score"].split("-", 1)
            score = f"{second}-{first}"
    opponent = ""
    if selected:
        if selected.get("team1") in {"巨人", "読売ジャイアンツ"}:
            opponent = selected.get("team2", "")
        else:
            opponent = selected.get("team1", "")
    return {
        "url": url,
        "rows": rows,
        "opponent": opponent,
        "venue": selected.get("place", ""),
        "time": selected.get("time", ""),
        "score": score,
    }


@lru_cache(maxsize=64)
def _fetch_game_reference(target_date: str, opponent_hint: str = "") -> dict[str, Any]:
    npb = _fetch_npb_schedule_snapshot(target_date, opponent_hint=opponent_hint)
    game_id = _find_yahoo_game_id(target_date, opponent_hint=opponent_hint)
    if not game_id:
        return {
            "game_id": "",
            "opponent": npb.get("opponent", ""),
            "venue": npb.get("venue", ""),
            "time": npb.get("time", ""),
            "score": npb.get("score", ""),
            "lineup_rows": [],
            "evidence_urls": [npb["url"]],
            "evidence_by_field": {
                "opponent": npb["url"],
                "venue": npb["url"],
                "time": npb["url"],
                "score": npb["url"],
                "lineup": npb["url"],
            },
        }

    starters = get_starters(game_id)
    result = get_game_result(game_id)
    opponent = _normalize_team(starters.get("opponent_name") or npb.get("opponent", ""))
    venue = _normalize_venue(npb.get("venue", ""))
    time_label = _normalize_time(npb.get("time", ""))
    score = ""
    if result.get("giants_score") and result.get("opponent_score"):
        score = f"{result['giants_score']}-{result['opponent_score']}"
    return {
        "game_id": game_id,
        "opponent": opponent,
        "venue": venue,
        "time": time_label,
        "score": score or npb.get("score", ""),
        "lineup_rows": starters.get("giants", []),
        "evidence_urls": [
            f"https://baseball.yahoo.co.jp/npb/game/{game_id}/top",
            f"https://baseball.yahoo.co.jp/npb/game/{game_id}/score",
            npb["url"],
        ],
        "evidence_by_field": {
            "opponent": f"https://baseball.yahoo.co.jp/npb/game/{game_id}/top",
            "venue": npb["url"],
            "time": npb["url"],
            "score": f"https://baseball.yahoo.co.jp/npb/game/{game_id}/score" if score else npb["url"],
            "lineup": f"https://baseball.yahoo.co.jp/npb/game/{game_id}/top",
        },
    }


def _normalized_field_value(field: str, value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if field == "opponent":
        return _normalize_team(raw)
    if field == "venue":
        return _normalize_venue(raw)
    if field == "time":
        return _normalize_time(raw)
    if field == "score":
        return _normalize_score(raw)
    return raw


def _compare_value(field: str, current: str, expected: str) -> bool:
    current_norm = _normalized_field_value(field, current)
    expected_norm = _normalized_field_value(field, expected)
    return bool(current_norm and expected_norm and current_norm != expected_norm)


def _build_scalar_autofix(field: str, current: str, expected: str, title: str, body: str) -> tuple[str, str, dict[str, Any]]:
    if field == "b5_quote":
        return ("remove_or_replace_embed", "壊れている B.5 引用 URL を差し替えまたは削除する", {})
    if current and current in title:
        return (
            "direct_edit",
            f"WP title の `{current}` を `{expected}` に置換する",
            {"type": "title_replace", "find": current, "replace": expected},
        )
    if current and current in body:
        return (
            "direct_edit",
            f"本文内の `{current}` を `{expected}` に置換する",
            {"type": "body_replace", "find": current, "replace": expected},
        )
    if field == "lineup":
        return ("regenerate", "スタメン表と本文を正しいデータで再生成する", {})
    return ("regenerate", f"{field} を正しい値で再生成する", {})


def _infer_cause(field: str, current: str, expected: str, *, title: str, body: str, source_text: str, subtype: str) -> str:
    if field == "b5_quote":
        return "b5_quote_reference_broken"
    if current and current in title and expected and expected in source_text:
        return "title_rewrite_mismatch"
    if expected and expected in source_text:
        return "generation_hallucination"
    if subtype in {"notice", "recovery"} and field in {"subject", "notice_type"}:
        return "entity_or_notice_detection_mismatch"
    if subtype in {"postgame", "lineup", "pregame"} and field in {"opponent", "venue", "time", "score"}:
        return "game_fact_alignment_failure"
    return "needs_manual_review"


def _append_scalar_finding(
    findings: list[Finding],
    *,
    field: str,
    current: str,
    expected: str,
    evidence_url: str,
    title: str,
    body: str,
    source_text: str,
    subtype: str,
) -> None:
    if not current or not expected or not _compare_value(field, current, expected):
        return
    fix_type, proposal, auto_fix = _build_scalar_autofix(field, current, expected, title, body)
    findings.append(
        Finding(
            severity="red",
            field=field,
            current=current,
            expected=expected,
            evidence_url=evidence_url,
            message=f"{field} が不一致: 記事では `{current}`、根拠側では `{expected}`",
            cause=_infer_cause(field, current, expected, title=title, body=body, source_text=source_text, subtype=subtype),
            proposal=proposal,
            fix_type=fix_type,
            auto_fix=auto_fix,
        )
    )


def _append_warning(findings: list[Finding], *, field: str, message: str, evidence_url: str, proposal: str, cause: str) -> None:
    findings.append(
        Finding(
            severity="yellow",
            field=field,
            current="",
            expected="",
            evidence_url=evidence_url,
            message=message,
            cause=cause,
            proposal=proposal,
            fix_type="manual_review",
        )
    )


def _pick_game_reference_value(field: str, reference: dict[str, Any], source_facts: dict[str, Any]) -> tuple[str, str]:
    reference_value = (reference.get(field) or "").strip()
    if reference_value:
        evidence_by_field = reference.get("evidence_by_field", {})
        return reference_value, evidence_by_field.get(field, reference.get("evidence_urls", [""])[0] if reference.get("evidence_urls") else "")
    source_value = (source_facts.get(field) or "").strip()
    if source_value:
        return source_value, source_facts.get("field_evidence_urls", {}).get(field, "")
    return "", ""


def _check_game_facts(findings: list[Finding], post_facts: dict[str, Any], audited: dict[str, Any], source_facts: dict[str, Any]) -> None:
    subtype = audited["article_subtype"]
    if subtype not in {"postgame", "lineup", "pregame"}:
        return

    target_date = post_facts["target_date"].isoformat()
    reference = _fetch_game_reference(target_date, opponent_hint=post_facts.get("opponent", ""))
    source_text = " ".join(
        [snap.get("title", "") + " " + snap.get("description", "") for snap in source_facts.get("snapshots", [])]
    )
    opponent_expected, opponent_evidence = _pick_game_reference_value("opponent", reference, source_facts)
    venue_expected, venue_evidence = _pick_game_reference_value("venue", reference, source_facts)
    time_expected, time_evidence = _pick_game_reference_value("time", reference, source_facts)
    score_expected, score_evidence = _pick_game_reference_value("score", reference, source_facts)

    _append_scalar_finding(
        findings,
        field="opponent",
        current=post_facts.get("opponent", ""),
        expected=opponent_expected,
        evidence_url=opponent_evidence,
        title=post_facts["title"],
        body=post_facts["plain_text"],
        source_text=source_text,
        subtype=subtype,
    )
    _append_scalar_finding(
        findings,
        field="venue",
        current=post_facts.get("venue", ""),
        expected=venue_expected,
        evidence_url=venue_evidence,
        title=post_facts["title"],
        body=post_facts["plain_text"],
        source_text=source_text,
        subtype=subtype,
    )
    if subtype == "pregame":
        _append_scalar_finding(
            findings,
            field="time",
            current=post_facts.get("time", ""),
            expected=time_expected,
            evidence_url=time_evidence,
            title=post_facts["title"],
            body=post_facts["plain_text"],
            source_text=source_text,
            subtype=subtype,
        )
    if subtype == "postgame":
        _append_scalar_finding(
            findings,
            field="score",
            current=post_facts.get("score", ""),
            expected=score_expected,
            evidence_url=score_evidence,
            title=post_facts["title"],
            body=post_facts["plain_text"],
            source_text=source_text,
            subtype=subtype,
        )
    if subtype == "lineup" and post_facts.get("lineup_rows") and reference.get("lineup_rows"):
        current_rows = post_facts["lineup_rows"][:3]
        expected_rows = reference["lineup_rows"][:3]
        current_compact = ", ".join(f"{row['order']}番{row['name']}" for row in current_rows)
        expected_compact = ", ".join(f"{row['order']}番{row['name']}" for row in expected_rows)
        if current_compact and expected_compact and current_compact != expected_compact:
            fix_type, proposal, auto_fix = _build_scalar_autofix(
                "lineup",
                current_compact,
                expected_compact,
                post_facts["title"],
                post_facts["plain_text"],
            )
            findings.append(
                Finding(
                    severity="red",
                    field="lineup",
                    current=current_compact,
                    expected=expected_compact,
                    evidence_url=reference.get("evidence_by_field", {}).get(
                        "lineup",
                        reference.get("evidence_urls", [""])[0] if reference.get("evidence_urls") else "",
                    ),
                    message=f"スタメン上位打順が不一致: 記事 `{current_compact}` / 公式 `{expected_compact}`",
                    cause="game_fact_alignment_failure",
                    proposal=proposal,
                    fix_type=fix_type,
                    auto_fix=auto_fix,
                )
            )


def _check_subject_facts(findings: list[Finding], post_facts: dict[str, Any], audited: dict[str, Any], source_facts: dict[str, Any]) -> None:
    subtype = audited["article_subtype"]
    if subtype not in {"notice", "recovery", "manager", "player", "social"}:
        return
    source_text = " ".join(
        [snap.get("title", "") + " " + snap.get("description", "") + " " + snap.get("text", "")[:400] for snap in source_facts.get("snapshots", [])]
    )
    evidence_url = source_facts.get("snapshots", [{}])[0].get("url", "") if source_facts.get("snapshots") else ""
    subject = (post_facts.get("subject") or "").strip()
    if subject and source_text and subject not in source_text:
        fix_type, proposal, auto_fix = _build_scalar_autofix(
            "subject",
            subject,
            "",
            post_facts["title"],
            post_facts["plain_text"],
        )
        findings.append(
            Finding(
                severity="yellow",
                field="subject",
                current=subject,
                expected="source title/text を確認",
                evidence_url=evidence_url,
                message=f"記事の主語 `{subject}` を source で直接確認できない",
                cause=_infer_cause(
                    "subject",
                    subject,
                    "",
                    title=post_facts["title"],
                    body=post_facts["plain_text"],
                    source_text=source_text,
                    subtype=subtype,
                ),
                proposal=proposal or "source 記事で対象選手・発言主を再確認する",
                fix_type=fix_type or "manual_review",
                auto_fix=auto_fix,
            )
        )
    if subtype == "notice" and post_facts.get("notice_type"):
        notice_type = post_facts["notice_type"]
        if source_text and notice_type not in source_text:
            _append_warning(
                findings,
                field="notice_type",
                message=f"公示種別 `{notice_type}` を source で直接確認できない",
                evidence_url=evidence_url,
                proposal="公示種別を source 記事と NPB 公示で再確認する",
                cause="entity_or_notice_detection_mismatch",
            )


def _check_tweet_urls(findings: list[Finding], post_facts: dict[str, Any]) -> None:
    urls = post_facts.get("tweet_urls", [])[:MAX_TWEET_URL_CHECKS]
    for url in urls:
        snapshot = _fetch_url_snapshot(url)
        if snapshot.get("status_code") == 404:
            fix_type, proposal, auto_fix = _build_scalar_autofix("b5_quote", url, "", post_facts["title"], post_facts["plain_text"])
            findings.append(
                Finding(
                    severity="red",
                    field="b5_quote",
                    current=url,
                    expected="存在するポスト URL",
                    evidence_url=url,
                    message=f"B.5 引用 URL が 404: {url}",
                    cause="b5_quote_reference_broken",
                    proposal=proposal,
                    fix_type=fix_type,
                    auto_fix=auto_fix,
                )
            )
        elif not snapshot.get("ok"):
            _append_warning(
                findings,
                field="b5_quote",
                message=f"B.5 引用 URL の存在確認に失敗: {url}",
                evidence_url=url,
                proposal="URL を手動確認し、必要なら差し替える",
                cause="needs_manual_review",
            )


def _overall_result(findings: list[Finding]) -> str:
    severities = {finding.severity for finding in findings}
    if "red" in severities:
        return "red"
    if "yellow" in severities:
        return "yellow"
    return "green"


def _result_icon(result: str) -> str:
    return {"green": "✅", "yellow": "🟡", "red": "🔴"}.get(result, "🟡")


def build_post_report(post: dict, category_map: dict[int, str], source_catalog: dict[str, dict], base_url: str) -> PostReport:
    audited = audit_post(post, category_map, source_catalog, base_url)
    post_facts = _extract_post_facts(post, audited)
    source_facts = _source_reference_facts(post_facts["source_links"])

    findings: list[Finding] = []
    _check_game_facts(findings, post_facts, audited, source_facts)
    _check_subject_facts(findings, post_facts, audited, source_facts)
    _check_tweet_urls(findings, post_facts)

    if not post_facts["source_links"]:
        _append_warning(
            findings,
            field="source_reference",
            message="参照元リンクが本文に見つからない",
            evidence_url="",
            proposal="source_url を再確認し、参照元ブロックを補う",
            cause="source_reference_missing",
        )

    return PostReport(
        post_id=int(audited["id"]),
        title=audited["title"],
        status=audited["status"],
        primary_category=audited["primary_category"],
        article_subtype=audited["article_subtype"],
        modified=audited["modified"],
        edit_url=audited["edit_url"],
        result=_overall_result(findings),
        findings=findings,
        source_urls=[item.get("url", "") for item in post_facts["source_links"] if item.get("url")],
    )


def _matches_category_filter(audited: dict, requested: str) -> bool:
    target = (requested or "").strip().lower()
    if not target:
        return True
    return target in {
        str(audited.get("primary_category", "")).lower(),
        str(audited.get("article_subtype", "")).lower(),
        str(audited.get("source_bucket", "")).lower(),
    }


def _normalize_since_filter(value: str | None) -> str:
    normalized = (value or "today").strip().lower()
    if not normalized:
        return "today"
    if normalized in {"today", "yesterday", "all"}:
        return normalized
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError:
        return "today"


def _matches_since_filter(post: dict, since_filter: str) -> bool:
    target = _normalize_since_filter(since_filter)
    if target == "all":
        return True

    post_date = _post_local_date(post)
    today = datetime.now(JST).date()
    if target == "today":
        expected_date = today
    elif target == "yesterday":
        expected_date = today - timedelta(days=1)
    else:
        expected_date = date.fromisoformat(target)
    return post_date == expected_date


def _select_posts(args: argparse.Namespace, wp: WPClient) -> tuple[list[dict], dict[int, str], dict[str, dict]]:
    categories = wp.get_categories()
    category_map = {int(row["id"]): row["name"] for row in categories}
    source_catalog = load_source_catalog()

    if args.post_id:
        return [wp.get_post(args.post_id)], category_map, source_catalog

    posts = wp.list_posts(
        status=args.status,
        per_page=max(args.limit * 3, 20),
        page=1,
        orderby="modified",
        order="desc",
        context="edit",
        fields=["id", "date", "modified", "status", "title", "content", "categories", "link"],
    )
    selected: list[dict] = []
    since_filter = _normalize_since_filter(getattr(args, "since", "today"))
    for post in posts:
        if not _matches_since_filter(post, since_filter):
            continue
        audited = audit_post(post, category_map, source_catalog, wp.base_url)
        if not _matches_category_filter(audited, args.category):
            continue
        selected.append(post)
        if len(selected) >= args.limit:
            break
    return selected, category_map, source_catalog


def collect_reports(
    *,
    post_id: int | None = None,
    category: str = "",
    limit: int = 10,
    status: str = "draft",
    since: str = "today",
    wp: WPClient | None = None,
) -> list[PostReport]:
    args = argparse.Namespace(
        post_id=post_id,
        category=category,
        limit=limit,
        status=status,
        since=since,
    )
    wp_client = wp or WPClient()
    posts, category_map, source_catalog = _select_posts(args, wp_client)
    return [build_post_report(post, category_map, source_catalog, wp_client.base_url) for post in posts]


def _render_text_report(reports: list[PostReport]) -> str:
    lines: list[str] = []
    lines.append(f"checked_posts: {len(reports)}")
    for report in reports:
        lines.append("")
        lines.append(
            f"{_result_icon(report.result)} post_id={report.post_id} "
            f"{report.primary_category}/{report.article_subtype} {report.title}"
        )
        if report.edit_url:
            lines.append(f"  edit: {report.edit_url}")
        if not report.findings:
            lines.append("  ✅ 重大な事実差分は検出されませんでした")
            continue
        for finding in report.findings:
            lines.append(f"  {_result_icon(finding.severity)} {finding.field}: {finding.message}")
            if finding.evidence_url:
                lines.append(f"    evidence: {finding.evidence_url}")
            if finding.proposal:
                lines.append(f"    proposal: {finding.proposal}")
            if finding.cause:
                lines.append(f"    cause: {finding.cause}")
    return "\n".join(lines)


def _report_to_json(reports: list[PostReport]) -> str:
    payload = [
        {
            **asdict(report),
            "findings": [asdict(finding) for finding in report.findings],
        }
        for report in reports
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="draft 記事の事実確認と修正提案を行う")
    parser.add_argument("--post-id", type=int, help="単一 post_id を監査")
    parser.add_argument("--category", default="", help="primary category または article_subtype で絞る")
    parser.add_argument("--limit", type=int, default=10, help="監査件数")
    parser.add_argument("--status", default="draft", help="取得する投稿 status")
    parser.add_argument("--since", default="today", help="today / yesterday / YYYY-MM-DD / all")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    args = parser.parse_args()

    reports = collect_reports(
        post_id=args.post_id,
        category=args.category,
        limit=args.limit,
        status=args.status,
        since=args.since,
    )

    if args.json:
        print(_report_to_json(reports))
        return
    print(_render_text_report(reports))


if __name__ == "__main__":
    main()
