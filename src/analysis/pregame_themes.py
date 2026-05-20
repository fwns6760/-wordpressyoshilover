"""414 axis E: 試合前「今日の注目テーマ」 自動セット (7 テーマ).

user 仕様 2026-05-20 chat:
- 今日の先発
- 昨日の流れ
- 注目選手
- 打順変更
- 昇格選手
- 相手投手との相性
- 巨人ファンが反応しそうな話題

各テーマは insight.db / Tavily / fan_voice_pool / sports_fetcher 等から取得。
Phase 1 では DB-based (E2 昨日の流れ / E6 相手投手相性) を実装、 残りは
caller が補完 (focused_players / lineup_history / roster_history / fan_voice_snippets
等を kwarg で渡せる)。

caller (build_gemma_branding_candidate) は build_pregame_themes() を呼び、 返却
dict を prompt の「今日の注目テーマ」 section に整形して注入する。 試合日 + 試合
前 (17時以前) のみ使う想定 (Gemma 出力の現在化 hint)。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional


JST = timezone(timedelta(hours=9))


def _yesterday_str(now_jst: datetime) -> str:
    return (now_jst.date() - timedelta(days=1)).isoformat()


def _query_yesterday_summary(db_path: str, yesterday: str) -> str:
    """E2: 昨日試合の 1 行要約 (opponent / score / result / winning_pitcher)."""
    if not db_path:
        return ""
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT opponent, giants_score, opp_score, result, "
                "winning_pitcher, losing_pitcher, save_pitcher, one_line_summary "
                "FROM games WHERE game_date = ? "
                "ORDER BY ingested_at DESC LIMIT 1",
                (yesterday,),
            )
            row = cur.fetchone()
        finally:
            con.close()
    except Exception:
        return ""
    if not row:
        return ""
    opponent, gs, ops, result, wp_, lp, sv, summary = row
    parts: list[str] = [f"昨日 ({yesterday}) 巨人 vs {opponent}"]
    if gs is not None and ops is not None:
        parts.append(f"{gs}-{ops}")
    if result:
        result_jp = {"win": "勝利", "loss": "敗戦", "draw": "引分"}.get(
            str(result).lower(), str(result)
        )
        parts.append(f"({result_jp})")
    if wp_:
        parts.append(f"勝: {wp_}")
    if lp:
        parts.append(f"負: {lp}")
    if sv:
        parts.append(f"S: {sv}")
    if summary:
        parts.append(f"-- {summary}")
    return " ".join(parts)


def _query_opponent_pitcher_matchup(
    db_path: str,
    opponent_pitcher_canonical: str,
    *,
    window_days: int = 60,
    now_jst: Optional[datetime] = None,
) -> str:
    """E6: 相手投手との相性. 直近 window_days 内、 巨人打者の対投手 stat 集計.

    pitching_logs (opponent 投手 in giants game) と batting_logs (giants 打者 in
    同 game_id) を JOIN して、 巨人打者 collective の AB / H / RBI 等を返す。
    cup-of-coffee な相手投手 (試合 1 つ) でも書ける形で 1 行要約。
    """
    if not db_path or not opponent_pitcher_canonical:
        return ""
    if now_jst is None:
        now_jst = datetime.now(JST)
    cutoff = (now_jst.date() - timedelta(days=window_days)).isoformat()
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(DISTINCT pl.game_id) AS games, "
                "  SUM(bl.AB) AS ab, SUM(bl.H) AS h, SUM(bl.RBI) AS rbi "
                "FROM pitching_logs pl "
                "JOIN games g ON pl.game_id = g.game_id "
                "JOIN batting_logs bl ON bl.game_id = pl.game_id "
                "  AND bl.team_name = '巨人' "
                "WHERE pl.player_canonical = ? "
                "  AND g.game_date >= ? "
                "  AND pl.team_name != '巨人'",
                (opponent_pitcher_canonical, cutoff),
            )
            row = cur.fetchone()
        finally:
            con.close()
    except Exception:
        return ""
    if not row:
        return ""
    games, ab, h, rbi = row
    games = int(games or 0)
    if games == 0:
        return f"対 {opponent_pitcher_canonical}: 直近 {window_days} 日 対戦記録なし"
    parts = [f"対 {opponent_pitcher_canonical} (直近 {games} 試合)"]
    if ab is not None and ab > 0:
        avg = (h or 0) / ab
        parts.append(f"巨人打撃 AB{ab} H{h or 0} ({avg:.3f}) RBI{rbi or 0}")
    return " ".join(parts)


def build_pregame_themes(
    db_path: str,
    *,
    now_jst: Optional[datetime] = None,
    starting_pitcher_today: str = "",
    focused_players: Optional[list[str]] = None,
    lineup_change_summary: str = "",
    promotion_summary: str = "",
    opponent_pitcher_canonical: str = "",
    fan_voice_snippet: str = "",
) -> dict[str, str]:
    """414 axis E: 試合前 7 テーマ自動セット.

    Returns dict with keys (空文字なら caller skip):
        starting_pitcher (E1) / yesterday_summary (E2) / focused_players (E3) /
        lineup_change (E4) / promotion (E5) / opponent_matchup (E6) /
        fan_voice (E7)

    DB-based (E2/E6) は本 helper が直接 SQL を引く。 caller-supplied
    (E1/E3/E4/E5/E7) は kwarg で渡す。 渡されない or 空なら空文字。
    """
    if now_jst is None:
        now_jst = datetime.now(JST)
    yesterday = _yesterday_str(now_jst)
    themes: dict[str, str] = {
        "starting_pitcher": str(starting_pitcher_today or "").strip(),
        "yesterday_summary": _query_yesterday_summary(db_path, yesterday),
        "focused_players": ", ".join(
            str(p).strip() for p in (focused_players or []) if str(p).strip()
        ),
        "lineup_change": str(lineup_change_summary or "").strip(),
        "promotion": str(promotion_summary or "").strip(),
        "opponent_matchup": _query_opponent_pitcher_matchup(
            db_path,
            opponent_pitcher_canonical,
            now_jst=now_jst,
        ),
        "fan_voice": str(fan_voice_snippet or "").strip(),
    }
    return themes


def format_pregame_themes_for_prompt(themes: dict[str, str]) -> str:
    """Helper to format dict into prompt section. 空文字 entry は skip."""
    label_map = {
        "starting_pitcher": "今日の先発",
        "yesterday_summary": "昨日の流れ",
        "focused_players": "注目選手",
        "lineup_change": "打順変更",
        "promotion": "昇格選手",
        "opponent_matchup": "相手投手との相性",
        "fan_voice": "ファン反応 (参考)",
    }
    order = (
        "starting_pitcher",
        "yesterday_summary",
        "focused_players",
        "lineup_change",
        "promotion",
        "opponent_matchup",
        "fan_voice",
    )
    lines: list[str] = ["【今日の注目テーマ (試合前 context)】"]
    has_any = False
    for key in order:
        value = themes.get(key) or ""
        if not value:
            continue
        lines.append(f"- {label_map[key]}: {value}")
        has_any = True
    if not has_any:
        return ""
    return "\n".join(lines)
