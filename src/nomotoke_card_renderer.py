"""Nomotoke-style card renderer (10-template version).

This module implements the structural pattern of ten nomotoke-style article
cards. Phase 1 shipped 4 renderers; this revision (NOMOTOKE-SHAPE-001) extends
them to the unified 10-renderer set:

1.  ``nomotoke_card_lineup_v1``           スタメン発表
2.  ``nomotoke_card_live_at_bats_v1``     全打席結果速報
3.  ``nomotoke_card_postgame_v1``         試合結果・打席結果
4.  ``nomotoke_card_official_notice_v1``  NPB公示
5.  ``nomotoke_card_pregame_pitcher_v1``  予告先発
6.  ``nomotoke_card_broadcast_v1``        中継情報
7.  ``nomotoke_card_video_v1``            動画
8.  ``nomotoke_card_player_stats_v1``     個人成績
9.  ``nomotoke_card_manager_comment_v1``  監督談話
10. ``nomotoke_card_player_comment_v1``   選手コメント

Hard rules (NOMOTOKE-SHAPE-001):

- STRUCTURE only is borrowed. No specific phrasing (e.g. ``ｶｯﾀｶﾞﾈｰ`` /
  ``ﾏｹﾀｶﾞﾈｰ``) is copied. The renderer **rejects** input strings that contain
  those phrasings as defense in depth.
- Source-only facts: the renderer never invents data not present in ``data``.
  No HTTP I/O. No Gemini call. No auto-summarization.
- HTML escape: every untrusted string is escaped via ``html.escape``.
- Unsafe URLs (``javascript:`` / non-http(s)) are dropped, not rendered.
- Output is gated by the existing default-OFF env flag
  ``ENABLE_NOMOTOKE_CARD_TEMPLATES`` (see ``select_renderer``).

This module is **stdlib-only** and adds no new dependency.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse


ENABLE_FLAG = "ENABLE_NOMOTOKE_CARD_TEMPLATES"

TEMPLATE_KEY_LINEUP = "nomotoke_card_lineup_v1"
TEMPLATE_KEY_LIVE_AT_BATS = "nomotoke_card_live_at_bats_v1"
TEMPLATE_KEY_POSTGAME = "nomotoke_card_postgame_v1"
TEMPLATE_KEY_OFFICIAL_NOTICE = "nomotoke_card_official_notice_v1"
TEMPLATE_KEY_PREGAME_PITCHER = "nomotoke_card_pregame_pitcher_v1"
TEMPLATE_KEY_BROADCAST = "nomotoke_card_broadcast_v1"
TEMPLATE_KEY_VIDEO = "nomotoke_card_video_v1"
TEMPLATE_KEY_PLAYER_STATS = "nomotoke_card_player_stats_v1"
TEMPLATE_KEY_MANAGER_COMMENT = "nomotoke_card_manager_comment_v1"
TEMPLATE_KEY_PLAYER_COMMENT = "nomotoke_card_player_comment_v1"
TEMPLATE_KEY_SHORT_NEWS_URL = "nomotoke_card_short_news_url_v1"


# Categories per the unified table.
_CATEGORY_GAME = "試合速報"
_CATEGORY_NOTICE = "公示"
_CATEGORY_BROADCAST = "中継"
_CATEGORY_VIDEO = "動画"
_CATEGORY_PLAYER_STATS = "個人成績"
_CATEGORY_MANAGER_COMMENT = "監督談話"
_CATEGORY_PLAYER_COMMENT = "選手コメント"
_CATEGORY_NEWS = "ニュース"


_TEMPLATE_CATEGORY: Dict[str, str] = {
    TEMPLATE_KEY_LINEUP: _CATEGORY_GAME,
    TEMPLATE_KEY_LIVE_AT_BATS: _CATEGORY_GAME,
    TEMPLATE_KEY_POSTGAME: _CATEGORY_GAME,
    TEMPLATE_KEY_OFFICIAL_NOTICE: _CATEGORY_NOTICE,
    TEMPLATE_KEY_PREGAME_PITCHER: _CATEGORY_GAME,
    TEMPLATE_KEY_BROADCAST: _CATEGORY_BROADCAST,
    TEMPLATE_KEY_VIDEO: _CATEGORY_VIDEO,
    TEMPLATE_KEY_PLAYER_STATS: _CATEGORY_PLAYER_STATS,
    TEMPLATE_KEY_MANAGER_COMMENT: _CATEGORY_MANAGER_COMMENT,
    TEMPLATE_KEY_PLAYER_COMMENT: _CATEGORY_PLAYER_COMMENT,
    TEMPLATE_KEY_SHORT_NEWS_URL: _CATEGORY_NEWS,
}


# Forbidden nomotoke-specific phrasings (defense in depth).
_FORBIDDEN_PHRASINGS = ("ｶｯﾀｶﾞﾈｰ", "ﾏｹﾀｶﾞﾈｰ", "ｶﾞﾈｰ", "ﾄﾞﾝﾏｲ")


# Embed whitelist (host names, lowercased) for the video renderer.
_VIDEO_EMBED_HOST_WHITELIST = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
        "x.com",
        "twitter.com",
        "dazn.com",
        "sp.dazn.com",
    }
)


# Quote-length cap for comment-style cards (Japanese characters).
_QUOTE_SHORT_MAX_CHARS = 100


# Common footer (constant) — appended to every card.
_COMMON_FOOTER_HTML = (
    '<hr class="nomotoke-card-divider">'
    '<p class="nomotoke-card-footer">'
    "この記事へのコメント・反応はコメント欄からお願いします。"
    "</p>"
)


# Allowed stat kinds.
_STAT_KIND_LABELS: Dict[str, str] = {
    "batting": "打撃",
    "pitching": "投手",
}


# ---------------------------------------------------------------------------
# Flag gating
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Return True when the env flag is set to a truthy value."""
    raw = os.environ.get(ENABLE_FLAG, "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def require_enabled() -> None:
    """Raise RuntimeError if the env flag is OFF."""
    if not is_enabled():
        raise RuntimeError(
            f"{ENABLE_FLAG} is OFF; nomotoke card templates are disabled"
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _esc(value: Any) -> str:
    """HTML-escape any value as text. None / non-str become ''."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _safe_url(value: Any) -> str:
    """Return an HTML-escaped URL only if it is http(s); else ''."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered.startswith("javascript:") or lowered.startswith("data:"):
        return ""
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return ""
    return html.escape(raw, quote=True)


def _check_forbidden_phrasings(data: Dict[str, Any]) -> None:
    """Raise ValueError if any string field contains forbidden phrasings."""

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            for bad in _FORBIDDEN_PHRASINGS:
                if bad in obj:
                    raise ValueError("nomotoke_phrasing_detected")
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(data)


def _topic_hash(text: str) -> str:
    """Return first 12 chars of sha1(text) for dedupe_key compactness."""
    payload = (text or "").encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def _meta_block(date_label: str) -> str:
    """Render the optional meta block. Empty string when no date_label."""
    if not date_label:
        return ""
    return f'<p class="nomotoke-meta">{_esc(date_label)}</p>'


def _source_block(source_url: str, source_label: Optional[str] = None) -> str:
    """Render the source block. Empty string when no safe source_url."""
    safe = _safe_url(source_url)
    if not safe:
        return ""
    label = (source_label or "").strip() or str(source_url).strip()
    return (
        '<p class="nomotoke-source">出典: '
        f'<a href="{safe}" target="_blank" rel="noopener">{_esc(label)}</a>'
        "</p>"
    )


def _related_links_block(links: Any) -> str:
    """Render the optional related_links block. Empty string when nothing safe."""
    if not isinstance(links, list) or not links:
        return ""
    items: List[str] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        url = _safe_url(link.get("url"))
        if not url:
            continue
        label_raw = link.get("label")
        label = _esc(label_raw) if label_raw else url
        items.append(f'<li><a href="{url}">{label}</a></li>')
    if not items:
        return ""
    return (
        "<h3>関連リンク</h3>"
        '<ul class="nomotoke-related-links">'
        + "".join(items)
        + "</ul>"
    )


def _result_payload(
    template_key: str,
    title: str,
    body_main: str,
    *,
    date_label: str,
    source_url: str,
    source_label: Optional[str],
    related_links: Any,
    closing_html: str,
    tags: List[str],
    dedupe_key: str,
) -> Dict[str, Any]:
    """Assemble the full content_html and final result dict."""
    parts: List[str] = []
    meta = _meta_block(date_label)
    if meta:
        parts.append(meta)
    src = _source_block(source_url, source_label)
    if src:
        parts.append(src)
    if body_main:
        parts.append(body_main)
    rl = _related_links_block(related_links)
    if rl:
        parts.append(rl)
    if closing_html:
        parts.append(closing_html)
    parts.append(_COMMON_FOOTER_HTML)
    content_html = "".join(parts)

    cleaned: List[str] = []
    seen = set()
    for t in tags:
        if not t:
            continue
        s = str(t).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)

    return {
        "template_key": template_key,
        "title": title,
        "content_html": content_html,
        "category": _TEMPLATE_CATEGORY.get(template_key, ""),
        "tags": cleaned,
        "source_url": str(source_url or ""),
        "dedupe_key": dedupe_key,
        "skip_reason": "",
        "validation_ok": True,
    }


def _skip(template_key: str, reason: str, source_url: str = "") -> Dict[str, Any]:
    return {
        "template_key": template_key,
        "title": "",
        "content_html": "",
        "category": _TEMPLATE_CATEGORY.get(template_key, ""),
        "tags": [],
        "source_url": str(source_url or ""),
        "dedupe_key": "",
        "skip_reason": reason,
        "validation_ok": False,
    }


def _render_lineup_table(rows: Iterable[Dict[str, Any]]) -> str:
    """Render a starting-lineup table.

    Columns: 打順 / 守備 / 選手名 / 打率 / 先発投手防御率
    """
    head = (
        "<table><thead><tr>"
        "<th>打順</th><th>守備</th><th>選手名</th>"
        "<th>打率</th><th>先発投手防御率</th>"
        "</tr></thead><tbody>"
    )
    body_rows: List[str] = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td>{_esc(row.get('order', ''))}</td>"
            f"<td>{_esc(row.get('position', ''))}</td>"
            f"<td>{_esc(row.get('player_name', ''))}</td>"
            f"<td>{_esc(row.get('batting_average', ''))}</td>"
            f"<td>{_esc(row.get('starter_era', ''))}</td>"
            "</tr>"
        )
    return head + "".join(body_rows) + "</tbody></table>"


def _render_inning_table(teams: List[Dict[str, Any]]) -> str:
    """Render the inning-score table."""
    inning_count = 0
    for t in teams:
        innings = t.get("innings") or []
        if isinstance(innings, list):
            inning_count = max(inning_count, len(innings))
    head_cells = "".join(f"<th>{i + 1}</th>" for i in range(inning_count))
    head = (
        "<table><thead><tr>"
        f"<th>チーム</th>{head_cells}<th>計</th>"
        "</tr></thead><tbody>"
    )
    body_rows: List[str] = []
    for t in teams:
        innings = t.get("innings") or []
        cells = "".join(f"<td>{_esc(v)}</td>" for v in innings)
        if len(innings) < inning_count:
            cells += "<td></td>" * (inning_count - len(innings))
        body_rows.append(
            "<tr>"
            f"<td>{_esc(t.get('name', ''))}</td>"
            f"{cells}"
            f"<td>{_esc(t.get('total', ''))}</td>"
            "</tr>"
        )
    return head + "".join(body_rows) + "</tbody></table>"


def _render_atbat_table(rows: Iterable[Dict[str, Any]]) -> str:
    head = (
        "<table><thead><tr>"
        "<th>選手名</th><th>打順</th><th>打席結果</th>"
        "</tr></thead><tbody>"
    )
    body_rows: List[str] = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td>{_esc(row.get('player_name', ''))}</td>"
            f"<td>{_esc(row.get('order', ''))}</td>"
            f"<td>{_esc(row.get('result', ''))}</td>"
            "</tr>"
        )
    return head + "".join(body_rows) + "</tbody></table>"


def _render_pitching_table(rows: Iterable[Dict[str, Any]]) -> str:
    head = (
        "<table><thead><tr>"
        "<th>投手</th><th>イニング</th><th>失点</th><th>主な結果</th>"
        "</tr></thead><tbody>"
    )
    body_rows: List[str] = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td>{_esc(row.get('pitcher_name', ''))}</td>"
            f"<td>{_esc(row.get('innings', ''))}</td>"
            f"<td>{_esc(row.get('runs', ''))}</td>"
            f"<td>{_esc(row.get('summary', ''))}</td>"
            "</tr>"
        )
    return head + "".join(body_rows) + "</tbody></table>"


def _render_link_list(links: Iterable[Dict[str, Any]]) -> str:
    """Render a ``<ul>`` of safe links. Empty/unsafe ones are skipped."""
    items: List[str] = []
    for link in links or []:
        url = _safe_url(link.get("url"))
        if not url:
            continue
        label = _esc(link.get("label") or url)
        items.append(f'<li><a href="{url}">{label}</a></li>')
    if not items:
        return ""
    return "<ul>" + "".join(items) + "</ul>"


def _render_broadcast_table(rows: Iterable[Dict[str, Any]]) -> str:
    head = (
        "<table><thead><tr>"
        "<th>媒体</th><th>チャンネル</th><th>放送時間</th>"
        "<th>解説</th><th>実況</th>"
        "</tr></thead><tbody>"
    )
    body_rows: List[str] = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td>{_esc(row.get('media', ''))}</td>"
            f"<td>{_esc(row.get('channel', ''))}</td>"
            f"<td>{_esc(row.get('time', ''))}</td>"
            f"<td>{_esc(row.get('commentator', ''))}</td>"
            f"<td>{_esc(row.get('play_by_play', ''))}</td>"
            "</tr>"
        )
    return head + "".join(body_rows) + "</tbody></table>"


def _render_stats_table(
    columns: Iterable[str], rows: Iterable[Dict[str, Any]]
) -> str:
    columns_list = [str(c) for c in columns]
    head_cells = "".join(f"<th>{_esc(c)}</th>" for c in columns_list)
    head = f"<table><thead><tr>{head_cells}</tr></thead><tbody>"
    body_rows: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = "".join(
            f"<td>{_esc(row.get(col, ''))}</td>" for col in columns_list
        )
        body_rows.append(f"<tr>{cells}</tr>")
    return head + "".join(body_rows) + "</tbody></table>"


def _filter_safe_iframe(embed_html: str) -> str:
    """Return embed_html unchanged if it contains exactly one <iframe>
    whose src host is whitelisted; else ''."""
    if not embed_html or not isinstance(embed_html, str):
        return ""
    matches = re.findall(
        r"<iframe\b[^>]*\bsrc\s*=\s*[\"\']([^\"\']+)[\"\'][^>]*>",
        embed_html,
        flags=re.IGNORECASE,
    )
    if len(matches) != 1:
        return ""
    src = matches[0].strip()
    if not (src.lower().startswith("http://") or src.lower().startswith("https://")):
        return ""
    try:
        host = urlparse(src).hostname or ""
    except ValueError:
        return ""
    if host.lower() not in _VIDEO_EMBED_HOST_WHITELIST:
        return ""
    # Defensive: forbid <script> inside the embed.
    if re.search(r"<\s*script", embed_html, flags=re.IGNORECASE):
        return ""
    return embed_html


# ---------------------------------------------------------------------------
# Renderers — existing 4 (extended)
# ---------------------------------------------------------------------------


def render_lineup_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a スタメン発表 card (docx 5.1)."""
    template_key = TEMPLATE_KEY_LINEUP
    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    team_name = (data.get("team_name") or "").strip()
    if not team_name:
        return _skip(template_key, "missing_team_name", source_url_raw)

    own_lineup = data.get("own_lineup") or []
    if not isinstance(own_lineup, list) or not own_lineup:
        return _skip(template_key, "missing_lineup_rows", source_url_raw)

    date_label = (data.get("date_label") or "").strip()
    league_label = (data.get("league_label") or "").strip()
    home = (data.get("home") or "").strip()
    away = (data.get("away") or "").strip()
    opponent_name = (data.get("opponent_name") or "").strip()
    if not (date_label and league_label and home and away):
        return _skip(template_key, "missing_matchup_header", source_url_raw)

    title = (
        f"{date_label} {league_label}「{home}vs.{away}」 "
        f"{team_name}、スタメン発表！！！"
    )

    parts: List[str] = []
    parts.append(
        f"<p>■ {_esc(date_label)} {_esc(league_label)}"
        f"「{_esc(home)}vs.{_esc(away)}」</p>"
    )

    live_url = _safe_url(data.get("live_url"))
    if live_url:
        parts.append(f'<p><a href="{live_url}">全打席速報はこちら</a></p>')

    parts.append(f"<h3>{_esc(team_name)} スタメン</h3>")
    parts.append(_render_lineup_table(own_lineup))

    opponent_lineup = data.get("opponent_lineup") or []
    if isinstance(opponent_lineup, list) and opponent_lineup:
        opp_heading = opponent_name or "相手"
        parts.append(f"<h3>{_esc(opp_heading)} スタメン</h3>")
        parts.append(_render_lineup_table(opponent_lineup))

    own_starter_name = ""
    starter_obj = data.get("own_starter") or {}
    if isinstance(starter_obj, dict):
        own_starter_name = (starter_obj.get("name") or "").strip()

    closing_html = "<p>この日のスタメンです。</p>"

    # dedupe_key shape: lineup:{date}:{home}:{away}
    if not (date_label and home and away):
        return _skip(
            template_key, "missing_dedupe_key_inputs", source_url_raw
        )
    dedupe_key = f"lineup:{date_label}:{home}:{away}"

    tags = ["スタメン", team_name, opponent_name, own_starter_name]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def render_postgame_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 試合結果・打席結果 card (docx 5.4)."""
    template_key = TEMPLATE_KEY_POSTGAME
    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    team_name = (data.get("team_name") or "").strip()
    if not team_name:
        return _skip(template_key, "missing_team_name", source_url_raw)

    score = (data.get("score") or "").strip()
    if not score:
        return _skip(template_key, "missing_score", source_url_raw)

    result = (data.get("result") or "").strip()
    result_label_map = {
        "win": "勝利",
        "loss": "敗戦",
        "draw": "引き分け",
        "勝利": "勝利",
        "敗戦": "敗戦",
        "引き分け": "引き分け",
    }
    result_label = result_label_map.get(result)
    if not result_label:
        return _skip(template_key, "missing_result", source_url_raw)

    date_label = (data.get("date_label") or "").strip()
    league_label = (data.get("league_label") or "").strip()
    home = (data.get("home") or "").strip()
    away = (data.get("away") or "").strip()
    if not (date_label and league_label and home and away):
        return _skip(template_key, "missing_matchup_header", source_url_raw)

    inning_score = data.get("inning_score") or []
    if not isinstance(inning_score, list) or not inning_score:
        return _skip(template_key, "missing_inning_score", source_url_raw)

    one_line_summary = (data.get("one_line_summary") or "").strip()

    title = (
        f"{date_label} {league_label}「{home}vs.{away}」"
        f"【試合結果、打席結果】 {team_name}、{score}で{result_label}！！！"
    )
    if one_line_summary:
        title = f"{title} {one_line_summary}"

    parts: List[str] = []
    parts.append(
        f"<p>■ {_esc(date_label)} {_esc(league_label)}"
        f"「{_esc(home)}vs.{_esc(away)}」</p>"
    )
    parts.append("<h3>試合スコア</h3>")
    parts.append(_render_inning_table(inning_score))

    atbat_results = data.get("atbat_results") or []
    if isinstance(atbat_results, list) and atbat_results:
        parts.append("<h3>打席結果</h3>")
        parts.append(_render_atbat_table(atbat_results))

    pitching_results = data.get("pitching_results") or []
    if isinstance(pitching_results, list) and pitching_results:
        parts.append("<h3>投球結果</h3>")
        parts.append(_render_pitching_table(pitching_results))

    opposing_pitcher = (data.get("opposing_pitcher") or "").strip()
    if opposing_pitcher:
        parts.append(f"<p>対戦投手: {_esc(opposing_pitcher)}</p>")

    opponent_lineup = data.get("opponent_lineup") or []
    if isinstance(opponent_lineup, list) and opponent_lineup:
        parts.append("<h3>相手スタメン</h3>")
        parts.append(_render_lineup_table(opponent_lineup))

    closing_map = {
        "勝利": "<p>勝ちました。</p>",
        "敗戦": "<p>悔しい敗戦です。</p>",
        "引き分け": "<p>引き分けでした。</p>",
    }
    closing_html = closing_map[result_label]

    if not (date_label and home and away):
        return _skip(
            template_key, "missing_dedupe_key_inputs", source_url_raw
        )
    dedupe_key = f"postgame:{date_label}:{home}:{away}"

    tags = ["試合結果", team_name, result_label]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def render_official_notice_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a NPB公示 card (docx 5.3)."""
    template_key = TEMPLATE_KEY_OFFICIAL_NOTICE
    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    team_name = (data.get("team_name") or "").strip()
    if not team_name:
        return _skip(template_key, "missing_team_name", source_url_raw)

    action = (data.get("action") or "").strip()
    action_label_map = {
        "register": "登録",
        "remove": "抹消",
        "swap": "入れ替え",
        "登録": "登録",
        "抹消": "抹消",
        "入れ替え": "入れ替え",
    }
    action_label = action_label_map.get(action)
    if not action_label:
        return _skip(template_key, "missing_action", source_url_raw)

    date_label = (data.get("date_label") or "").strip()
    if not date_label:
        return _skip(template_key, "missing_date_label", source_url_raw)

    registered = data.get("registered") or []
    removed = data.get("removed") or []
    if not isinstance(registered, list):
        registered = []
    if not isinstance(removed, list):
        removed = []
    if not (registered or removed):
        return _skip(template_key, "missing_player_lists", source_url_raw)

    title = f"【公示】{date_label}のプロ野球公示 {team_name}が{action_label}"

    parts: List[str] = []

    official_url = _safe_url(data.get("official_url"))
    if official_url:
        url_label = _esc(data.get("official_url_label") or "NPB公示ページ")
        parts.append(
            f'<p>NPB公式公示: <a href="{official_url}">{url_label}</a></p>'
        )

    if registered:
        parts.append("<h3>登録選手</h3>")
        parts.append(
            "<ul>"
            + "".join(f"<li>{_esc(name)}</li>" for name in registered if name)
            + "</ul>"
        )

    if removed:
        parts.append("<h3>抹消選手</h3>")
        parts.append(
            "<ul>"
            + "".join(f"<li>{_esc(name)}</li>" for name in removed if name)
            + "</ul>"
        )

    current_count = data.get("current_count")
    remaining_slots = data.get("remaining_slots")
    if current_count is not None and remaining_slots is not None:
        parts.append(
            f"<p>現在の登録人数: {_esc(current_count)}人 / "
            f"残り枠: {_esc(remaining_slots)}枠</p>"
        )

    note = (data.get("note") or "").strip()
    if note:
        parts.append(f"<p>{_esc(note)}</p>")

    summary_names = [n for n in list(registered) + list(removed) if n][:3]
    names_summary = "、".join(_esc(n) for n in summary_names)
    closing_html = ""
    if names_summary:
        closing_html = f"<p>{names_summary}が{action_label}です。</p>"

    if not (date_label and team_name):
        return _skip(
            template_key, "missing_dedupe_key_inputs", source_url_raw
        )
    dedupe_key = f"announce:{date_label}:{team_name}"

    tags = ["公示", team_name, action_label]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def render_pregame_pitcher_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 予告先発 card (docx 5.5)."""
    template_key = TEMPLATE_KEY_PREGAME_PITCHER
    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    date_label = (data.get("date_label") or "").strip()
    if not date_label:
        return _skip(template_key, "missing_date_label", source_url_raw)

    matchups = data.get("matchups") or []
    if not isinstance(matchups, list) or not matchups:
        return _skip(template_key, "missing_matchups", source_url_raw)

    title = f"{date_label}の予告先発が発表される！！！"

    parts: List[str] = []

    official_url = _safe_url(data.get("official_url"))
    if official_url:
        parts.append(
            f'<p>NPB公式予告先発: <a href="{official_url}">{official_url}</a></p>'
        )

    for m in matchups:
        if not isinstance(m, dict):
            continue
        team_a = _esc(m.get("team_a", ""))
        pitcher_a = _esc(m.get("pitcher_a", ""))
        team_b = _esc(m.get("team_b", ""))
        pitcher_b = _esc(m.get("pitcher_b", ""))
        parts.append(
            f"<p>{team_a}：{pitcher_a} / {team_b}：{pitcher_b}</p>"
        )

    broadcast_links = data.get("broadcast_links") or []
    if isinstance(broadcast_links, list) and broadcast_links:
        link_html = _render_link_list(broadcast_links)
        if link_html:
            parts.append("<h3>中継情報</h3>")
            parts.append(link_html)

    primary_pitcher = ""
    first = matchups[0] if isinstance(matchups[0], dict) else {}
    primary_pitcher = (first.get("pitcher_a") or "").strip()
    closing_html = ""
    if primary_pitcher:
        closing_html = f"<p>{_esc(primary_pitcher)}が先発です。</p>"

    if not date_label:
        return _skip(
            template_key, "missing_dedupe_key_inputs", source_url_raw
        )
    dedupe_key = f"pregame:{date_label}"

    tags = ["予告先発", primary_pitcher]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


# ---------------------------------------------------------------------------
# Renderers — 6 NEW
# ---------------------------------------------------------------------------


def render_live_at_bats_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 全打席結果速報 card (新規)."""
    template_key = TEMPLATE_KEY_LIVE_AT_BATS
    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    date_label = (data.get("date_label") or "").strip()
    league_label = (data.get("league_label") or "").strip()
    home = (data.get("home") or "").strip()
    away = (data.get("away") or "").strip()

    lineup_rows = data.get("lineup_rows") or []
    at_bats_rows = data.get("at_bats_rows") or []
    pitching_rows = data.get("pitching_rows") or []

    has_data = (
        (isinstance(lineup_rows, list) and lineup_rows)
        or (isinstance(at_bats_rows, list) and at_bats_rows)
        or (isinstance(pitching_rows, list) and pitching_rows)
    )

    if not (home and away and date_label and has_data):
        return _skip(template_key, "missing_at_bats_data", source_url_raw)

    notable_player_1 = (data.get("notable_player_1") or "").strip()
    notable_player_2 = (data.get("notable_player_2") or "").strip()
    starter = (data.get("starter") or "").strip()

    name_parts = [n for n in (notable_player_1, notable_player_2, starter) if n]
    names_segment = ""
    if name_parts:
        names_segment = "、".join(name_parts) + "らが出場！！！"

    title_core = (
        f"{date_label} {league_label}「{home}vs.{away}」"
        "【全打席結果速報】"
    )
    if names_segment:
        title = f"{title_core} {names_segment}"
    else:
        title = title_core

    parts: List[str] = []
    parts.append(
        f"<p>■ {_esc(date_label)} {_esc(league_label)}"
        f"「{_esc(home)}vs.{_esc(away)}」</p>"
    )

    own_team_label = (data.get("own_team_label") or "").strip()
    if isinstance(lineup_rows, list) and lineup_rows:
        heading = own_team_label or "スタメン"
        parts.append(f"<h3>{_esc(heading)}</h3>")
        parts.append(_render_lineup_table(lineup_rows))

    opponent_lineup = data.get("opponent_lineup_rows") or []
    if isinstance(opponent_lineup, list) and opponent_lineup:
        parts.append("<h3>相手スタメン</h3>")
        parts.append(_render_lineup_table(opponent_lineup))

    if isinstance(at_bats_rows, list) and at_bats_rows:
        parts.append("<h3>打席結果</h3>")
        parts.append(_render_atbat_table(at_bats_rows))

    if isinstance(pitching_rows, list) and pitching_rows:
        parts.append("<h3>投球結果</h3>")
        parts.append(_render_pitching_table(pitching_rows))

    broadcast_info = data.get("broadcast_info") or []
    if isinstance(broadcast_info, list) and broadcast_info:
        link_html = _render_link_list(broadcast_info)
        if link_html:
            parts.append("<h3>中継情報</h3>")
            parts.append(link_html)

    status = (data.get("status") or "").strip()
    if status == "in_progress":
        closing_html = "<p>随時更新します。</p>"
    else:
        closing_html = "<p>試合経過はこちらです。</p>"

    dedupe_key = f"live_at_bats:{date_label}:{home}:{away}"

    tags = ["全打席速報", home, away, notable_player_1, notable_player_2, starter]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def render_broadcast_info_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 中継情報 card (新規)."""
    template_key = TEMPLATE_KEY_BROADCAST
    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    date_label = (data.get("date_label") or "").strip()
    league_label = (data.get("league_label") or "").strip()
    home = (data.get("home") or "").strip()
    away = (data.get("away") or "").strip()
    broadcasts = data.get("broadcasts") or []

    if not (home and away and date_label):
        return _skip(template_key, "missing_broadcasts", source_url_raw)
    if not (isinstance(broadcasts, list) and broadcasts):
        return _skip(template_key, "missing_broadcasts", source_url_raw)

    valid_rows = [r for r in broadcasts if isinstance(r, dict)]
    if not valid_rows:
        return _skip(template_key, "missing_broadcasts", source_url_raw)

    title = (
        f"{date_label}放送 {league_label}"
        f"「{home}vs.{away}」【テレビ・ネット・ラジオ中継情報】"
    )

    parts: List[str] = []
    parts.append(
        f"<p>■ {_esc(date_label)} {_esc(league_label)}"
        f"「{_esc(home)}vs.{_esc(away)}」</p>"
    )
    parts.append("<h3>中継予定</h3>")
    parts.append(_render_broadcast_table(valid_rows))

    note = (data.get("note") or "").strip()
    if note:
        parts.append(f"<p>{_esc(note)}</p>")

    closing_html = "<p>この日の中継情報です。</p>"

    dedupe_key = f"broadcast:{date_label}:{home}:{away}"

    tags = ["中継情報", home, away]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def render_video_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 動画 card (新規)."""
    template_key = TEMPLATE_KEY_VIDEO
    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    video_url_raw = (data.get("video_url") or "").strip()
    safe_video_url = _safe_url(video_url_raw)
    team_name = (data.get("team_name") or "").strip()
    player_name = (data.get("player_name") or "").strip()
    play_summary = (data.get("play_summary") or "").strip()

    if not (safe_video_url and team_name and player_name and play_summary):
        return _skip(template_key, "missing_video_fields", source_url_raw)

    title = f"{team_name}・{player_name}、{play_summary}！！！【動画】"

    parts: List[str] = []

    embed_html_in = data.get("embed_html") or ""
    safe_embed = _filter_safe_iframe(embed_html_in) if embed_html_in else ""
    if safe_embed:
        parts.append(safe_embed)
    else:
        # fallback link.
        link_label = play_summary or video_url_raw
        parts.append(
            f'<p><a href="{safe_video_url}" target="_blank" '
            f'rel="noopener">{_esc(link_label)}</a></p>'
        )

    description = (data.get("description") or "").strip()
    if description:
        if len(description) > 120:
            cut = description.find("。")
            if cut != -1:
                description = description[: cut + 1]
            else:
                description = description[:120]
        parts.append(f"<p>{_esc(description)}</p>")

    if player_name:
        closing_html = f"<p>{_esc(player_name)}選手のプレーです。</p>"
    else:
        closing_html = "<p>注目のプレーです。</p>"

    date_label = (data.get("date_label") or "").strip()
    dedupe_key = f"video:{video_url_raw}"

    tags = ["動画", team_name, player_name]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def render_player_stats_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 個人成績 card (新規)."""
    template_key = TEMPLATE_KEY_PLAYER_STATS
    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    team_name = (data.get("team_name") or "").strip()
    player_name = (data.get("player_name") or "").strip()
    stat_kind = (data.get("stat_kind") or "").strip()
    stats_columns = data.get("stats_columns") or []
    stats_rows = data.get("stats_rows") or []
    date_label = (data.get("date_label") or "").strip()

    if not (
        team_name
        and player_name
        and stat_kind
        and isinstance(stats_columns, list)
        and stats_columns
        and isinstance(stats_rows, list)
        and stats_rows
        and date_label
    ):
        return _skip(template_key, "missing_stats_fields", source_url_raw)

    if stat_kind not in _STAT_KIND_LABELS:
        return _skip(template_key, "invalid_stat_kind", source_url_raw)

    stat_kind_label = _STAT_KIND_LABELS[stat_kind]

    title = (
        f"{team_name}・{player_name}、"
        f"今季ここまでの個人{stat_kind_label}成績は…"
    )

    parts: List[str] = []
    parts.append(f"<p>対象日時: {_esc(date_label)}</p>")
    parts.append("<h3>成績</h3>")
    parts.append(_render_stats_table(stats_columns, stats_rows))

    closing_html = f"<p>{_esc(player_name)}選手のここまでの成績です。</p>"

    dedupe_key = f"player_stats:{date_label}:{player_name}:{stat_kind}"

    tags = ["個人成績", team_name, player_name, stat_kind_label]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def _render_quote_comment_card(
    speaker_type: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Internal shared renderer for manager / player comment cards."""
    if speaker_type == "manager":
        template_key = TEMPLATE_KEY_MANAGER_COMMENT
        speaker_label_suffix = "監督"
        speaker_field = "manager_name"
        closing_role = "監督"
        dedupe_kind = "manager_comment"
        link_default_label = "試合結果はこちら"
    elif speaker_type == "player":
        template_key = TEMPLATE_KEY_PLAYER_COMMENT
        speaker_label_suffix = "選手"
        speaker_field = "player_name"
        closing_role = "選手"
        dedupe_kind = "player_comment"
        link_default_label = "試合結果はこちら"
    else:
        raise ValueError(f"unknown speaker_type: {speaker_type}")

    _check_forbidden_phrasings(data)

    source_url_raw = (data.get("source_url") or "").strip()
    source_label = data.get("source_label")

    team_name = (data.get("team_name") or "").strip()
    speaker_name = (data.get(speaker_field) or "").strip()
    topic = (data.get("topic") or "").strip()
    source_name = (data.get("source_name") or "").strip()
    published_at = (data.get("published_at") or "").strip()
    quote_short = data.get("quote_short")
    quote_short_for_title = (data.get("quote_short_for_title") or "").strip()

    # Required-field checks (taxonomy per spec).
    if not speaker_name:
        return _skip(template_key, "missing_speaker", source_url_raw)
    if not source_url_raw:
        return _skip(template_key, "missing_source_url", source_url_raw)
    # Source must be safe http(s) — drop unsafe.
    if not _safe_url(source_url_raw):
        return _skip(template_key, "missing_source_url", source_url_raw)
    if not isinstance(quote_short, str) or not quote_short.strip():
        return _skip(template_key, "missing_quote_short", source_url_raw)
    if not team_name:
        return _skip(template_key, "missing_team_name", source_url_raw)
    if not topic:
        return _skip(template_key, "missing_topic", source_url_raw)
    if not source_name:
        return _skip(template_key, "missing_source_name", source_url_raw)
    if not published_at:
        return _skip(template_key, "missing_published_at", source_url_raw)

    # Quote-length / multiline guards.
    if "\n" in quote_short:
        return _skip(
            template_key, "quote_multiline_not_allowed", source_url_raw
        )
    quote_stripped = quote_short.strip()
    if len(quote_stripped) > _QUOTE_SHORT_MAX_CHARS:
        return _skip(template_key, "quote_too_long", source_url_raw)

    # Title selection.
    title: str
    if speaker_type == "player":
        if (
            quote_short_for_title
            and len(quote_short_for_title) <= 20
        ):
            title = (
                f"{team_name}・{speaker_name}"
                f"「{quote_short_for_title}」"
            )
        else:
            title = (
                f"{team_name}・{speaker_name}、"
                f"{topic}についてコメント"
            )
    else:
        title = (
            f"{team_name}・{speaker_name}{speaker_label_suffix}、"
            f"{topic}についてコメント"
        )

    parts: List[str] = []

    date_label = (data.get("date_label") or "").strip()
    league_label = (data.get("league_label") or "").strip()
    home = (data.get("home") or "").strip()
    away = (data.get("away") or "").strip()
    if date_label and home and away:
        parts.append(
            f"<p>■ {_esc(date_label)} {_esc(league_label)}"
            f"「{_esc(home)}vs.{_esc(away)}」</p>"
        )

    # Optional internal link.
    game_link_url_raw = data.get("game_link_url")
    stats_link_url_raw = data.get("stats_link_url") if speaker_type == "player" else None
    chosen_link_url = ""
    chosen_link_label = ""
    if game_link_url_raw:
        safe = _safe_url(game_link_url_raw)
        if safe:
            chosen_link_url = safe
            chosen_link_label = (
                (data.get("game_link_label") or "").strip()
                or link_default_label
            )
    elif stats_link_url_raw:
        safe = _safe_url(stats_link_url_raw)
        if safe:
            chosen_link_url = safe
            chosen_link_label = (
                (data.get("stats_link_label") or "").strip()
                or "個人成績はこちら"
            )
    if chosen_link_url:
        parts.append(
            f'<p>関連: <a href="{chosen_link_url}">'
            f"{_esc(chosen_link_label)}</a></p>"
        )

    # Inline 出典 block (separate from the generic top source block).
    safe_source_inline = _safe_url(source_url_raw)
    if safe_source_inline:
        parts.append(
            f"<p>出典: {_esc(source_name)} ({_esc(published_at)}) ・ "
            f'<a href="{safe_source_inline}" target="_blank" '
            f'rel="noopener">元記事</a></p>'
        )

    parts.append(
        '<blockquote class="nomotoke-quote">'
        f"「{_esc(quote_stripped)}」"
        "</blockquote>"
    )

    closing_html = (
        f"<p>{_esc(speaker_name)}{closing_role}がコメントです。</p>"
    )

    topic_seed = quote_stripped if not topic else topic
    th = _topic_hash(topic_seed)
    if not date_label:
        return _skip(
            template_key, "missing_dedupe_key_inputs", source_url_raw
        )
    dedupe_key = f"{dedupe_kind}:{date_label}:{speaker_name}:{th}"

    tags = [closing_role + "コメント", team_name, speaker_name]

    return _result_payload(
        template_key,
        title,
        "".join(parts),
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=data.get("related_links"),
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def render_manager_comment_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 監督談話 card (新規)."""
    return _render_quote_comment_card("manager", data)


def render_player_comment_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 選手コメント card (新規)."""
    return _render_quote_comment_card("player", data)


_X_OR_TWITTER_HOSTS: tuple = (
    "x.com",
    "twitter.com",
    "www.x.com",
    "www.twitter.com",
    "mobile.x.com",
    "mobile.twitter.com",
)


# Source-only fact extractor: matches \d{1,2}-\d{1,2} / 対 / vs scores.
# Mirrors src.baseball_numeric_fact_consistency.SCORE_RE so a card row built
# from this regex never disagrees with the article-consistency check.
_SHORT_NEWS_SCORE_RE = re.compile(
    r"(?<!\d)(?P<left>\d{1,2})\s*(?:-|対|vs|VS)\s*(?P<right>\d{1,2})(?!\d)"
)
_SHORT_NEWS_GAME_KIND_PATTERNS: tuple = (
    ("二軍", "二軍"),
    ("ファーム", "二軍"),
    ("一軍", "一軍"),
)
_SHORT_NEWS_OUTCOME_KEYWORDS: tuple = (
    "勝利", "敗戦", "完封", "連勝", "連敗", "逆転", "サヨナラ",
    "本塁打", "完投", "ノーヒットノーラン", "引き分け",
)


def _is_x_or_twitter_host(url: str) -> bool:
    """Return True iff the URL host is an X / Twitter host (any subdomain)."""
    if not isinstance(url, str) or not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return host in _X_OR_TWITTER_HOSTS


def _x_embed_block(x_url: str, source_name: str) -> str:
    """Render a single X / Twitter post as a real tweet blockquote embed.

    A plain ``<a>`` link is no substitute for the actual tweet card on a
    のもとけ-style article. Loads ``platform.twitter.com/widgets.js`` so the
    blockquote upgrades to the rendered tweet card on page load.
    """
    safe = _safe_url(x_url)
    if not safe:
        return ""
    heading_suffix = f"({_esc(source_name)})" if source_name else ""
    return (
        f"<h3>📣 関連投稿{heading_suffix}</h3>"
        '<div class="yoshilover-x-embed" '
        'style="margin:24px auto;max-width:550px;">'
        '<blockquote class="twitter-tweet" data-dnt="true" data-lang="ja">'
        f'<a href="{safe}">{safe}</a>'
        "</blockquote></div>"
        '<script async src="https://platform.twitter.com/widgets.js" '
        'charset="utf-8"></script>'
    )


def _extract_short_news_facts(title: str, summary: str) -> Dict[str, str]:
    """Source-only structured fact extraction for short_news_url cards.

    Returns a subset of: ``score`` (e.g. ``"0-5"``), ``game_kind`` (一軍/
    二軍), ``outcome_keywords`` (joined string of detected outcome words).
    NEVER fabricates — only literal source matches are returned.
    """
    text = f"{title or ''}\n{summary or ''}"
    facts: Dict[str, str] = {}

    m = _SHORT_NEWS_SCORE_RE.search(text)
    if m:
        facts["score"] = f"{m.group('left')}-{m.group('right')}"

    for pattern, label in _SHORT_NEWS_GAME_KIND_PATTERNS:
        if pattern in text:
            facts["game_kind"] = label
            break

    outcomes = [kw for kw in _SHORT_NEWS_OUTCOME_KEYWORDS if kw in text]
    if outcomes:
        seen: List[str] = []
        for kw in outcomes:
            if kw not in seen:
                seen.append(kw)
        facts["outcome_keywords"] = "／".join(seen[:4])

    return facts


def _truncate_summary_preserving_period(text: str, cap: int) -> str:
    """Cap at ``cap`` chars; prefer last 「。」 boundary above half-cap."""
    if not text or len(text) <= cap:
        return text
    cut = text[:cap]
    last_period = cut.rfind("。")
    if last_period > cap // 2:
        return cut[: last_period + 1]
    return cut.rstrip() + "…"


def _split_related_x_and_other(related_links: Any) -> tuple:
    """Pull the first X URL out for blockquote embed; rest stays as-is."""
    x_url = ""
    other: List[Any] = []
    if isinstance(related_links, list):
        for link in related_links:
            if isinstance(link, dict):
                u = link.get("url", "")
                if _is_x_or_twitter_host(u):
                    if not x_url:
                        x_url = u
                    continue
            other.append(link)
    return x_url, other


def _short_news_fact_card_block(
    *,
    title: str,
    source_name: str,
    date_label: str,
    facts: Dict[str, str],
) -> str:
    """Render the 事実カード (fact card) table from source-only fields.

    Skipped rows for empty values; the table itself is omitted when fewer
    than two non-trivial rows are available, since a 1-row table reads as
    a stub.
    """
    rows: List[tuple] = []
    if facts.get("score"):
        rows.append(("スコア", facts["score"]))
    if facts.get("game_kind"):
        rows.append(("種別", facts["game_kind"]))
    if facts.get("outcome_keywords"):
        rows.append(("主な出来事", facts["outcome_keywords"]))
    if title:
        rows.append(("見出し", title))
    if source_name:
        rows.append(("出典", source_name))
    if date_label:
        rows.append(("公開日", date_label))

    if len(rows) < 2:
        return ""

    parts: List[str] = ["<h3>📋 事実カード</h3>"]
    parts.append('<table class="nomotoke-fact-card"><tbody>')
    for label, value in rows:
        parts.append(
            f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def _short_news_body_too_thin(
    *,
    title: str,
    summary: str,
    facts: Dict[str, str],
) -> bool:
    """Decide whether the assembled body would be only "1 sentence + link".

    Returns True when none of the following holds:
      - summary is concrete (≥ 12 chars, distinct from title)
      - at least one structured fact (score / game_kind / outcome_keywords)
        is extractable from source

    Such an article would render as little more than a URL card; the
    NOMOTOKE-BODY-FIX policy requires it to be skipped via the renderer's
    ``validation_failed:body_too_thin`` reason rather than published as a
    stub.
    """
    title = (title or "").strip()
    summary = (summary or "").strip()

    has_concrete_summary = (
        len(summary) >= 12 and summary != title and not summary.startswith(title)
    )
    has_score = bool(facts.get("score"))
    has_game_kind = bool(facts.get("game_kind"))
    has_outcomes = bool(facts.get("outcome_keywords"))

    return not (has_concrete_summary or has_score or has_game_kind or has_outcomes)


def render_short_news_url_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 短文ニュース URL カード in のもとけ structure.

    Required fields: source_url, source_name, title.
    Source-only: never invents facts beyond input. The summary is
    HTML-escaped and capped at 200 characters preserving sentence
    boundaries so a 1-line X post is never truncated mid-thought.

    Body structure (NOMOTOKE-BODY-FIX):
      1. 冒頭リード — 1〜2 文の summary (or title fallback)
      2. 事実カード — score / game_kind / outcome_keywords / 見出し / 出典 / 公開日 を
         table 化。skipped when fewer than 2 rows are extractable.
      3. 関連投稿 — X URL を tweet blockquote 埋め込み (X 単体は router 段で除外済)
      4. 出典記事 — primary source への named link
      5. 締め文 — 短いコメント誘導 1 文のみ

    Validation: if the body would be effectively "1 sentence + link"
    (no concrete summary AND no extractable facts), the renderer skips
    with ``validation_failed:body_too_thin`` so guarded-publish does not
    even see the post. publish basis / review gates / score consistency
    tokenizer are unchanged.
    """
    template_key = TEMPLATE_KEY_SHORT_NEWS_URL
    _check_forbidden_phrasings(data)

    title_raw = (data.get("title") or "").strip()
    summary_raw = (data.get("summary") or "").strip()
    source_url_raw = (data.get("source_url") or "").strip()
    source_name = (data.get("source_name") or "").strip()
    date_label = (data.get("date_label") or "").strip()
    related_links = data.get("related_links")
    source_label = (data.get("source_label") or "").strip() or source_name

    if not title_raw:
        return _skip(template_key, "missing_short_news_fields:title", source_url_raw)
    safe_source_url = _safe_url(source_url_raw)
    if not safe_source_url:
        return _skip(
            template_key, "missing_short_news_fields:source_url", source_url_raw
        )
    if not source_name:
        return _skip(
            template_key, "missing_short_news_fields:source_name", source_url_raw
        )

    facts = _extract_short_news_facts(title_raw, summary_raw)

    if _short_news_body_too_thin(
        title=title_raw, summary=summary_raw, facts=facts
    ):
        return _skip(
            template_key,
            "validation_failed:body_too_thin",
            source_url_raw,
        )

    summary_clean = _truncate_summary_preserving_period(summary_raw, 200)

    x_embed_url, other_related = _split_related_x_and_other(related_links)

    body_parts: List[str] = []

    body_parts.append(
        f'<p class="nomotoke-lead">{_esc(summary_clean or title_raw)}</p>'
    )

    fact_card = _short_news_fact_card_block(
        title=title_raw,
        source_name=source_name,
        date_label=date_label,
        facts=facts,
    )
    if fact_card:
        body_parts.append(fact_card)

    if x_embed_url:
        embed = _x_embed_block(x_embed_url, source_name)
        if embed:
            body_parts.append(embed)

    body_parts.append("<h3>🔗 出典記事</h3>")
    body_parts.append(
        f'<p>正式な内容は <a href="{safe_source_url}" target="_blank" '
        f'rel="noopener">{_esc(source_label)}</a> で確認できます。</p>'
    )

    body_main = "".join(body_parts)

    closing_html = (
        "<p>💬 ご意見・ご感想はコメント欄からお寄せください。</p>"
    )

    canonical_url_value = _hash_canonical(source_url_raw)
    dedupe_key = (
        f"short_news_url:{canonical_url_value}" if canonical_url_value else ""
    )

    tags = ["ニュース", source_name]
    if facts.get("game_kind"):
        tags.append(facts["game_kind"])

    return _result_payload(
        template_key,
        title_raw,
        body_main,
        date_label=date_label,
        source_url=source_url_raw,
        source_label=source_label,
        related_links=other_related or None,
        closing_html=closing_html,
        tags=tags,
        dedupe_key=dedupe_key,
    )


def _hash_canonical(url: str) -> str:
    """Stable 12-char sha1 prefix of a URL string. Empty for empty input."""
    if not url:
        return ""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Renderer factory
# ---------------------------------------------------------------------------


_RENDERER_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    TEMPLATE_KEY_LINEUP: render_lineup_card,
    TEMPLATE_KEY_LIVE_AT_BATS: render_live_at_bats_card,
    TEMPLATE_KEY_POSTGAME: render_postgame_card,
    TEMPLATE_KEY_OFFICIAL_NOTICE: render_official_notice_card,
    TEMPLATE_KEY_PREGAME_PITCHER: render_pregame_pitcher_card,
    TEMPLATE_KEY_BROADCAST: render_broadcast_info_card,
    TEMPLATE_KEY_VIDEO: render_video_card,
    TEMPLATE_KEY_PLAYER_STATS: render_player_stats_card,
    TEMPLATE_KEY_MANAGER_COMMENT: render_manager_comment_card,
    TEMPLATE_KEY_PLAYER_COMMENT: render_player_comment_card,
    TEMPLATE_KEY_SHORT_NEWS_URL: render_short_news_url_card,
}


def select_renderer(
    template_key: str,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Return a renderer for a known template_key.

    Raises:
        RuntimeError: when ``ENABLE_NOMOTOKE_CARD_TEMPLATES`` is OFF.
        ValueError: when ``template_key`` is unknown.
    """
    require_enabled()
    try:
        return _RENDERER_REGISTRY[template_key]
    except KeyError as exc:
        raise ValueError(f"unknown template_key: {template_key}") from exc
