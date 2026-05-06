"""Nomotoke-style card renderer (Phase 1: 4 templates).

Phase 1 implements the structural pattern of four nomotoke-style article cards:

1. lineup_card  (docx 5.1)         スタメン発表
2. postgame_card (docx 5.4)        試合結果・打席結果
3. official_notice_card (docx 5.3) NPB公示
4. pregame_pitcher_card (docx 5.5) 予告先発

Hard rules (NOMOTOKE-TEMPLATE-001 Phase 1):

- STRUCTURE only is borrowed. No specific phrasing (e.g. ``ｶｯﾀｶﾞﾈｰ`` /
  ``ﾏｹﾀｶﾞﾈｰ``) is copied. The renderer **rejects** input strings that contain
  those phrasings as defense in depth.
- Source-only facts: the renderer never invents data not present in ``data``.
- HTML escape: every untrusted string is escaped via ``html.escape``.
- Unsafe URLs (``javascript:`` / non-http(s)) are dropped, not rendered.
- Output is gated by the new default-OFF env flag
  ``ENABLE_NOMOTOKE_CARD_TEMPLATES`` (see ``select_renderer``).

This module is **stdlib-only** and adds no new dependency.
"""

from __future__ import annotations

import html
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional


ENABLE_FLAG = "ENABLE_NOMOTOKE_CARD_TEMPLATES"

TEMPLATE_KEY_LINEUP = "nomotoke_card_lineup_v1"
TEMPLATE_KEY_POSTGAME = "nomotoke_card_postgame_v1"
TEMPLATE_KEY_OFFICIAL_NOTICE = "nomotoke_card_official_notice_v1"
TEMPLATE_KEY_PREGAME_PITCHER = "nomotoke_card_pregame_pitcher_v1"


# Forbidden nomotoke-specific phrasings (defense in depth)
_FORBIDDEN_PHRASINGS = ("ｶｯﾀｶﾞﾈｰ", "ﾏｹﾀｶﾞﾈｰ", "ｶﾞﾈｰ", "ﾄﾞﾝﾏｲ")


# ---------------------------------------------------------------------------
# Flag gating
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Return True when the env flag is set to a truthy value."""
    raw = os.environ.get(ENABLE_FLAG, "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def require_enabled() -> None:
    """Raise RuntimeError if the env flag is OFF.

    Used by ``select_renderer`` to prevent accidental use before the flag is
    explicitly enabled. Renderer functions themselves do not gate (so unit
    tests can exercise them directly).
    """
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


def _skip(template_key: str, reason: str) -> Dict[str, Any]:
    return {
        "template_key": template_key,
        "title": "",
        "content_html": "",
        "tags": [],
        "skip_reason": reason,
        "validation_ok": False,
    }


def _ok(
    template_key: str,
    title: str,
    content_html: str,
    tags: List[str],
) -> Dict[str, Any]:
    # Filter empty / dedupe while preserving order.
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
        "tags": cleaned,
        "skip_reason": "",
        "validation_ok": True,
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


def _render_inning_table(
    teams: List[Dict[str, Any]],
) -> str:
    """Render the inning-score table.

    Each entry in ``teams`` is ``{"name": str, "innings": [...], "total": int|str}``.
    The number of inning columns is the max length of ``innings`` across teams.
    """
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
        # pad to inning_count columns
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
    """Render a ``<ul>`` of safe links. Empty/unsafe ones are skipped.

    Returns '' if no safe link exists.
    """
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


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_lineup_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a スタメン発表 card (docx 5.1)."""
    template_key = TEMPLATE_KEY_LINEUP
    _check_forbidden_phrasings(data)

    team_name = (data.get("team_name") or "").strip()
    if not team_name:
        return _skip(template_key, "missing_team_name")

    own_lineup = data.get("own_lineup") or []
    if not isinstance(own_lineup, list) or not own_lineup:
        return _skip(template_key, "missing_lineup_rows")

    date_label = (data.get("date_label") or "").strip()
    league_label = (data.get("league_label") or "").strip()
    home = (data.get("home") or "").strip()
    away = (data.get("away") or "").strip()
    opponent_name = (data.get("opponent_name") or "").strip()
    if not (date_label and league_label and home and away):
        return _skip(template_key, "missing_matchup_header")

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

    related_links = data.get("related_links") or []
    if isinstance(related_links, list) and related_links:
        link_html = _render_link_list(related_links)
        if link_html:
            parts.append("<h3>関連リンク</h3>")
            parts.append(link_html)

    parts.append("<p>この日のスタメンです。</p>")

    own_starter_name = ""
    starter_obj = data.get("own_starter") or {}
    if isinstance(starter_obj, dict):
        own_starter_name = (starter_obj.get("name") or "").strip()

    tags = ["スタメン", team_name, opponent_name, own_starter_name]

    return _ok(template_key, title, "".join(parts), tags)


def render_postgame_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 試合結果・打席結果 card (docx 5.4)."""
    template_key = TEMPLATE_KEY_POSTGAME
    _check_forbidden_phrasings(data)

    team_name = (data.get("team_name") or "").strip()
    if not team_name:
        return _skip(template_key, "missing_team_name")

    score = (data.get("score") or "").strip()
    if not score:
        return _skip(template_key, "missing_score")

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
        return _skip(template_key, "missing_result")

    date_label = (data.get("date_label") or "").strip()
    league_label = (data.get("league_label") or "").strip()
    home = (data.get("home") or "").strip()
    away = (data.get("away") or "").strip()
    if not (date_label and league_label and home and away):
        return _skip(template_key, "missing_matchup_header")

    inning_score = data.get("inning_score") or []
    if not isinstance(inning_score, list) or not inning_score:
        return _skip(template_key, "missing_inning_score")

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
    parts.append(closing_map[result_label])

    tags = ["試合結果", team_name, result_label]

    return _ok(template_key, title, "".join(parts), tags)


def render_official_notice_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a NPB公示 card (docx 5.3)."""
    template_key = TEMPLATE_KEY_OFFICIAL_NOTICE
    _check_forbidden_phrasings(data)

    team_name = (data.get("team_name") or "").strip()
    if not team_name:
        return _skip(template_key, "missing_team_name")

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
        return _skip(template_key, "missing_action")

    date_label = (data.get("date_label") or "").strip()
    if not date_label:
        return _skip(template_key, "missing_date_label")

    registered = data.get("registered") or []
    removed = data.get("removed") or []
    if not isinstance(registered, list):
        registered = []
    if not isinstance(removed, list):
        removed = []
    if not (registered or removed):
        return _skip(template_key, "missing_player_lists")

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
    if names_summary:
        parts.append(f"<p>{names_summary}が{action_label}です。</p>")

    tags = ["公示", team_name, action_label]
    return _ok(template_key, title, "".join(parts), tags)


def render_pregame_pitcher_card(data: Dict[str, Any]) -> Dict[str, Any]:
    """Render a 予告先発 card (docx 5.5)."""
    template_key = TEMPLATE_KEY_PREGAME_PITCHER
    _check_forbidden_phrasings(data)

    date_label = (data.get("date_label") or "").strip()
    if not date_label:
        return _skip(template_key, "missing_date_label")

    matchups = data.get("matchups") or []
    if not isinstance(matchups, list) or not matchups:
        return _skip(template_key, "missing_matchups")

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
    if primary_pitcher:
        parts.append(f"<p>{_esc(primary_pitcher)}が先発です。</p>")

    tags = ["予告先発", primary_pitcher]
    return _ok(template_key, title, "".join(parts), tags)


# ---------------------------------------------------------------------------
# Renderer factory
# ---------------------------------------------------------------------------


_RENDERER_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    TEMPLATE_KEY_LINEUP: render_lineup_card,
    TEMPLATE_KEY_POSTGAME: render_postgame_card,
    TEMPLATE_KEY_OFFICIAL_NOTICE: render_official_notice_card,
    TEMPLATE_KEY_PREGAME_PITCHER: render_pregame_pitcher_card,
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
