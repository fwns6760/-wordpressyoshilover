"""414 axis C8: 1軍 active filter (insight.db games-based).

user 報告 2026-05-20 chat: 「山瀬 (2軍中心) が 1軍 ranking に出る」 への fix。

DB schema (data/insight/schema.sql) に 1軍/2軍 field 不在、 roster JSON にも
tier field 不在のため、 games 出場履歴から 1軍 active 状態を推定する。

games.source_kind は ``"npb_box" | "yahoo_box" | "fixture"`` (1軍 NPB box 想定)
なので、 batting_logs / pitching_logs に出場記録ある = 1軍 game に出た選手。
ただし cup-of-coffee (一時 1軍登録 1-2 試合) は ranking に出るには不十分な
sample なので、 ``min_games`` で gate する。

Caller (将来):
- ``src/x_post_mail_lane.py:pick_candidates`` で ranking pool filter
- ``src/analysis/ranking_article_publisher.py`` の aggregate_* で WHERE EXISTS 注入
- (本 commit では helper の land のみ、 caller wire は別 commit)

DB 不在 / 例外時は **True を返す** (silent fallback、 既存挙動維持 = filter で消さない)。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional


def is_first_team_active(
    player_canonical: str,
    db_path: str,
    *,
    window_days: int = 14,
    min_games: int = 3,
    now_jst: Optional[datetime] = None,
) -> bool:
    """直近 ``window_days`` 日で 1軍 NPB games に ``min_games`` 試合以上出場した player なら True.

    batting_logs と pitching_logs の両方を確認、 どちらかで出場あれば True
    (野手と投手で別 table、 OR で評価)。 cup-of-coffee は False 扱い。

    Parameters
    ----------
    player_canonical:
        roster 正規名 (``config/giants_roster.json`` の ``name`` 列に一致)
    db_path:
        ``data/insight/insight.db`` の path
    window_days:
        直近 N 日 (default 14)
    min_games:
        この window で出場必要 distinct game 数 (default 3)
    now_jst:
        現在 JST datetime (test 用、 default ``datetime.now(JST)``)

    Returns
    -------
    bool:
        True = 1軍 active (ranking 対象として OK)、 False = 2軍中心 / 不在 (filter out)
        DB 不在 / 例外時は **True** (silent fallback、 既存挙動維持)
    """
    if not player_canonical or not db_path:
        return True
    jst = timezone(timedelta(hours=9))
    if now_jst is None:
        now_jst = datetime.now(jst)
    cutoff = (now_jst.date() - timedelta(days=window_days)).isoformat()
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT COUNT(DISTINCT bl.game_id) FROM batting_logs bl "
                "JOIN games g ON bl.game_id = g.game_id "
                "WHERE bl.player_canonical = ? AND g.game_date >= ? "
                "AND bl.team_name = '巨人'",
                (player_canonical, cutoff),
            )
            row = cur.fetchone() or (0,)
            batting_count = int(row[0] or 0)
            if batting_count >= min_games:
                return True
            cur.execute(
                "SELECT COUNT(DISTINCT pl.game_id) FROM pitching_logs pl "
                "JOIN games g ON pl.game_id = g.game_id "
                "WHERE pl.player_canonical = ? AND g.game_date >= ? "
                "AND pl.team_name = '巨人'",
                (player_canonical, cutoff),
            )
            row = cur.fetchone() or (0,)
            pitching_count = int(row[0] or 0)
            return pitching_count >= min_games
        finally:
            con.close()
    except Exception:
        # 例外時は filter で消さない (silent fallback、 既存挙動維持)
        return True


def filter_first_team_active_players(
    player_canonicals: list[str],
    db_path: str,
    *,
    window_days: int = 14,
    min_games: int = 3,
    now_jst: Optional[datetime] = None,
) -> list[str]:
    """``is_first_team_active`` を list に適用して filter された結果を返す.

    caller が複数 player を一括判定する時の便利 helper。 順序は維持。
    """
    if not player_canonicals:
        return []
    return [
        name
        for name in player_canonicals
        if is_first_team_active(
            name,
            db_path,
            window_days=window_days,
            min_games=min_games,
            now_jst=now_jst,
        )
    ]
