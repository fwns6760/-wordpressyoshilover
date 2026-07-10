"""starter_matchup_post.py — 予告先発予習 + スタメン発表ポスト (2026-07-10 user GO)。

狙い = 予測可能な検索需要の先回り (トレンド後追いの逆):
- A: 「巨人 先発」「<投手名>」の検索は前日夜〜試合前に必ず増える。予告先発が
  出た時点で両先発の成績つき予習ポスト候補を出す (朝/昼/試合前の最大3回)。
- C: 「巨人 スタメン」は毎日夕方に検索が跳ねる。発表を検知した便で打順+守備+
  フルネーム9人を列挙するポスト候補を出す (1ポストで9選手分の検索面)。

事実性: 数字・名前は Yahoo 試合ページの literal のみ。A の締めだけ LLM
(fact 外の数字・選手名は既存 gate で棄却)、C は deterministic。文体は です・ます調。
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Optional

LOG = logging.getLogger("starter_matchup_post")

_WEEKDAYS_JA = ("月", "火", "水", "木", "金", "土", "日")


# ---------------------------------------------------------------------------
# A: 予告先発
# ---------------------------------------------------------------------------


def parse_probable_starters(html: str) -> list[dict[str, str]]:
    """Yahoo 試合 top ページの予告先発 section を parse。

    各 dict: {team, name, era, games, wins, losses}。取れなければ []。
    """
    idx = (html or "").find("予告先発")
    if idx < 0:
        return []
    section = html[idx:idx + 6000]
    tokens = [t.strip() for t in re.split(r"<[^>]+>", section) if t.strip()]
    out: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("右投", "左投", "右", "左") and i + 1 < len(tokens):
            nm = tokens[i + 1]
            # 選手名 (日本語 or 外国人カナ)。数字・ラベルは除外
            if not re.fullmatch(r"[\d.\-]+", nm) and nm not in ("防御率", "登板"):
                if cur.get("name"):
                    out.append(cur)
                cur = {"name": nm.replace(" ", "").replace("　", "")}
        elif tok == "今季" and cur.get("name"):
            vals = tokens[i + 1:i + 5]
            if len(vals) == 4:
                cur.update({
                    "era": vals[0], "games": vals[1],
                    "wins": vals[2], "losses": vals[3],
                })
        i += 1
    if cur.get("name"):
        out.append(cur)
    return out[:2]


def _fetch_matchup() -> dict[str, Any]:
    """{opp, venue, giants: {...}, opponent: {...}}。失敗/未発表は {}。"""
    try:
        import urllib.request as ur

        from src.rss_fetcher import _find_giants_game_info_yahoo

        gid, opp, venue = _find_giants_game_info_yahoo(None)
        if not gid:
            return {}
        req = ur.Request(
            f"https://baseball.yahoo.co.jp/npb/game/{gid}/top",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        html = ur.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        starters = parse_probable_starters(html)
        if len(starters) != 2:
            return {}
        # Yahoo の並びは away → home。巨人側は roster 名で同定する。
        from src.live_game_watch import giants_fullname_map

        fmap = giants_fullname_map()
        giants_names = set(fmap.values()) | set(fmap.keys())

        def _is_giants(nm: str) -> bool:
            return nm in giants_names or any(
                nm.startswith(s) for s in fmap.keys()
            )

        if _is_giants(starters[0]["name"]):
            g, o = starters[0], starters[1]
        else:
            g, o = starters[1], starters[0]
        g["name"] = fmap.get(g["name"], g["name"])
        return {"opp": opp or "", "venue": venue or "", "giants": g, "opponent": o}
    except Exception as exc:  # noqa: BLE001
        LOG.info("starter_matchup fetch skip: %r", exc)
        return {}


def _time_bucket(hour: int) -> str:
    if hour < 12:
        return "am"
    if hour < 15:
        return "pm"
    return "pregame"


def _stat_line(p: dict[str, str]) -> str:
    parts = []
    if p.get("era") and p["era"] != "-":
        parts.append(f"防御率{p['era']}")
    if p.get("games") and p["games"] != "-":
        parts.append(f"{p['games']}登板")
    if p.get("wins") is not None and p.get("losses") is not None:
        parts.append(f"{p.get('wins', '-')}勝{p.get('losses', '-')}敗")
    return "・".join(parts)


def build_starter_matchup_candidate(
    *,
    now: datetime,
    gemini_api_key: str = "",
    dedup_set: Optional[set[str]] = None,
    matchup: Optional[dict[str, Any]] = None,
) -> Any:
    """予告先発予習ポスト候補 (朝/昼/試合前の最大3回)。素材なしは None。"""
    if matchup is None:
        matchup = _fetch_matchup()
    if not matchup:
        return None
    g, o = matchup["giants"], matchup["opponent"]
    date_label = f"{now.month}/{now.day}({_WEEKDAYS_JA[now.weekday()]})"
    signature = "startermatch|" + hashlib.sha1(
        f"{now.strftime('%Y%m%d')}|{_time_bucket(now.hour)}|{g['name']}".encode("utf-8")
    ).hexdigest()[:16]
    if dedup_set is not None and signature in dedup_set:
        return None
    opp = matchup.get("opp") or "相手"
    venue = f"・{matchup['venue']}" if matchup.get("venue") else ""
    g_line = f"巨人の先発: {g['name']}" + (
        f"（今季 {_stat_line(g)}）" if _stat_line(g) else ""
    )
    o_line = f"相手の先発: {o['name']}（{opp}" + (
        f"・今季 {_stat_line(o)}）" if _stat_line(o) else "）"
    )
    fact = f"{date_label} {opp}戦{venue}。{g_line}。{o_line}"
    comment = _matchup_comment(fact, gemini_api_key)
    if not comment:
        comment = f"{g['name']}の立ち上がりに注目です。"
    post_text = "\n".join([
        f"本日の巨人戦、予告先発です。",
        "",
        f"🆚 {date_label} {opp}戦（{matchup.get('venue') or '球場未取得'}）",
        g_line,
        o_line,
        "",
        comment,
    ])
    from src.x_post_mail_lane import Candidate

    LOG.info("starter_matchup built g=%s o=%s", g["name"], o["name"])
    return Candidate(
        title=f"⚾予告先発予習｜{g['name']} vs {o['name']}（{opp}）",
        metric="STARTER_MATCHUP",
        period_label="先発予習",
        draft_text=f"数字は Yahoo 試合ページの literal。{fact}",
        char_count=len(post_text),
        signature=signature,
        post_text=post_text,
        focus_player=g["name"],
        source_material_type="starter_matchup",
    )


def _matchup_comment(fact: str, gemini_api_key: str) -> str:
    if not gemini_api_key:
        return ""
    try:
        from src.x_post_branding_gen import build_quote_rt_comment

        return (
            build_quote_rt_comment(
                fact, "", "",
                gemini_api_key=gemini_api_key,
                subject="今日の巨人戦の予告先発マッチアップ",
                db_fact="", require_db_fact=False,
                budget_site="starter_matchup",
                extra_voice_note=(
                    "予告先発の予習ポストの締め。マッチアップの見どころを1〜2文、"
                    "60〜110字。fact にある数字・選手名だけ使い、新しい数字・"
                    "選手名・過去対戦の内容は作らない。文体は必ず です・ます調。"
                ),
            ) or ""
        ).strip()
    except Exception as exc:  # noqa: BLE001
        LOG.info("starter_matchup comment skip: %r", exc)
        return ""


# ---------------------------------------------------------------------------
# C: スタメン発表
# ---------------------------------------------------------------------------


def build_lineup_announce_candidate(
    *,
    now: datetime,
    dedup_set: Optional[set[str]] = None,
    lineup_rows: Optional[list[dict]] = None,
    opp: str = "",
) -> Any:
    """スタメン発表ポスト候補 (発表検知時 1 回、変更があれば再度)。

    9 人フルネーム列挙 = 「巨人 スタメン」+ 各選手名の検索面を 1 ポストで取る。
    deterministic (LLM なし)。未発表 (rows 9 人未満) は None。
    """
    if lineup_rows is None:
        lineup_rows, opp = _fetch_lineup_and_opp()
    rows = [r for r in (lineup_rows or []) if str(r.get("name") or "").strip()]
    if len(rows) < 9:
        if rows:
            LOG.info("lineup_announce skip: rows=%d (<9)", len(rows))
        return None
    rows = rows[:9]
    fullnames = _canonical_names([str(r.get("name")) for r in rows])
    lineup_key = "|".join(
        f"{r.get('order')}{r.get('position')}{nm}"
        for r, nm in zip(rows, fullnames)
    )
    signature = "lineupann|" + hashlib.sha1(
        f"{now.strftime('%Y%m%d')}|{lineup_key}".encode("utf-8")
    ).hexdigest()[:16]
    if dedup_set is not None and signature in dedup_set:
        return None
    date_label = f"{now.month}/{now.day}({_WEEKDAYS_JA[now.weekday()]})"
    lines = [
        f"{r.get('order')}({r.get('position')}) {nm}"
        for r, nm in zip(rows, fullnames)
    ]
    cleanup = next(
        (nm for r, nm in zip(rows, fullnames) if str(r.get("order")) == "4"), ""
    )
    close = (
        f"本日は{cleanup}が4番に入っています。" if cleanup else "本日の並びです。"
    )
    opp_label = f"（{opp}戦）" if opp else ""
    post_text = "\n".join([
        f"巨人のスタメンが発表されました{opp_label}。{date_label}",
        "",
        *lines,
        "",
        close,
    ])
    from src.x_post_mail_lane import Candidate

    LOG.info("lineup_announce built players=%d opp=%s", len(rows), opp or "-")
    return Candidate(
        title=f"📋スタメン発表｜{date_label}{opp_label}",
        metric="LINEUP_ANNOUNCE",
        period_label="スタメン",
        draft_text="Yahoo 試合ページのスタメン literal。9人フルネーム列挙で検索面を確保。",
        char_count=len(post_text),
        signature=signature,
        post_text=post_text,
        focus_player=fullnames[3] if len(fullnames) > 3 else "",
        source_material_type="lineup_announce",
    )


def _fetch_lineup_and_opp() -> tuple[list[dict], str]:
    try:
        from src.rss_fetcher import (
            _find_giants_game_info_yahoo,
            fetch_giants_lineup_stats_from_yahoo,
        )

        gid, opp, _venue = _find_giants_game_info_yahoo(None)
        if not gid:
            return [], ""
        return (
            fetch_giants_lineup_stats_from_yahoo(game_id=gid, opponent=opp or ""),
            opp or "",
        )
    except Exception as exc:  # noqa: BLE001
        LOG.info("lineup_announce fetch skip: %r", exc)
        return [], ""


def _canonical_names(names: list[str]) -> list[str]:
    """Yahoo 表記 (姓 or 姓 名) を roster フルネーム (敬称なし・スペースなし) へ。

    解決できない名前 (相手投手等は来ない想定だが) はスペース除去のみ。
    """
    try:
        from src.x_post_mail_lane import (
            _load_giants_player_aliases,
            _normalize_player_name,
        )

        aliases = _load_giants_player_aliases()
        out = []
        for nm in names:
            key = _normalize_player_name(nm)
            canonical = aliases.get(key) or nm
            out.append(str(canonical).replace(" ", "").replace("　", ""))
        return out
    except Exception:  # noqa: BLE001
        return [nm.replace(" ", "").replace("　", "") for nm in names]
