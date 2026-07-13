"""巨人発メジャーリーガー (岡本和真 / 菅野智之) の MLB 成績取得。

source = MLB 公式 Stats API (statsapi.mlb.com、無料・API key 不要)。
対象は元巨人 OB の MLB 選手のみ (MLB 記事化 policy: 元巨人のみ OK、大谷等は扱わない)。
取得失敗時は players が欠けた dict を返し、呼び出し側 (data_site_publisher) は
players が空なら upsert を skip して前回内容を維持する (fail-safe)。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

LOG = logging.getLogger(__name__)

_API_BASE = "https://statsapi.mlb.com/api/v1"
_JST = timezone(timedelta(hours=9))

# 元巨人 OB の MLB 現役 (mlb_id は statsapi people/search で確認済み 2026-06-12)
MLB_ALUMNI = [
    {"mlb_id": 672960, "name": "岡本和真", "group": "hitting", "slug": "okamoto-kazuma"},
    {"mlb_id": 608372, "name": "菅野智之", "group": "pitching", "slug": "sugano-tomoyuki"},
]

# playLog event code → 日本語 (statsapi の event 値、未知 code は raw 表示)
_PA_EVENT_JA = {
    "single": "単打",
    "double": "二塁打",
    "triple": "三塁打",
    "home_run": "本塁打",
    "walk": "四球",
    "intent_walk": "敬遠",
    "hit_by_pitch": "死球",
    "strikeout": "三振",
    "strikeout_double_play": "三振併殺",
    "field_out": "凡退",
    "force_out": "凡退",
    "grounded_into_double_play": "併殺打",
    "double_play": "併殺",
    "sac_fly": "犠飛",
    "sac_bunt": "犠打",
    "field_error": "失策出塁",
    "fielders_choice": "野選",
    "fielders_choice_out": "野選",
    "catcher_interf": "打撃妨害",
}


def pa_event_ja(code: str) -> str:
    return _PA_EVENT_JA.get(str(code or "").strip(), str(code or "").strip())

_TEAM_JA = {
    "New York Yankees": "ヤンキース",
    "Boston Red Sox": "レッドソックス",
    "Toronto Blue Jays": "ブルージェイズ",
    "Baltimore Orioles": "オリオールズ",
    "Tampa Bay Rays": "レイズ",
    "Cleveland Guardians": "ガーディアンズ",
    "Minnesota Twins": "ツインズ",
    "Detroit Tigers": "タイガース",
    "Chicago White Sox": "ホワイトソックス",
    "Kansas City Royals": "ロイヤルズ",
    "Houston Astros": "アストロズ",
    "Seattle Mariners": "マリナーズ",
    "Texas Rangers": "レンジャーズ",
    "Los Angeles Angels": "エンゼルス",
    "Athletics": "アスレチックス",
    "Oakland Athletics": "アスレチックス",
    "Atlanta Braves": "ブレーブス",
    "Philadelphia Phillies": "フィリーズ",
    "New York Mets": "メッツ",
    "Miami Marlins": "マーリンズ",
    "Washington Nationals": "ナショナルズ",
    "Milwaukee Brewers": "ブルワーズ",
    "Chicago Cubs": "カブス",
    "St. Louis Cardinals": "カージナルス",
    "Cincinnati Reds": "レッズ",
    "Pittsburgh Pirates": "パイレーツ",
    "Los Angeles Dodgers": "ドジャース",
    "San Diego Padres": "パドレス",
    "San Francisco Giants": "ジャイアンツ",
    "Arizona Diamondbacks": "ダイヤモンドバックス",
    "Colorado Rockies": "ロッキーズ",
}


def team_ja(name_en: str) -> str:
    return _TEAM_JA.get(str(name_en or "").strip(), str(name_en or "").strip())


def _get_json(url: str) -> dict:
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


def _extract_player(stats_payload: dict, info_payload: dict, spec: dict) -> dict | None:
    """statsapi の生 payload から表示用 entry を組む (純粋関数、 test 可)。"""
    people = (info_payload or {}).get("people") or []
    team_en = ((people[0].get("currentTeam") or {}).get("name") or "") if people else ""
    season_stat: dict = {}
    last_split: dict | None = None
    for s in (stats_payload or {}).get("stats") or []:
        type_name = ((s.get("type") or {}).get("displayName") or "")
        splits = s.get("splits") or []
        if type_name == "season" and splits:
            season_stat = splits[0].get("stat") or {}
        elif type_name == "gameLog" and splits:
            last_split = splits[-1]
    if not season_stat:
        return None
    entry: dict = {
        "name": spec["name"],
        "slug": str(spec.get("slug") or ""),
        "group": spec["group"],
        "team": team_ja(team_en),
    }
    if spec["group"] == "hitting":
        entry["season"] = {
            "games": int(season_stat.get("gamesPlayed") or 0),
            "avg": str(season_stat.get("avg") or ""),
            "hr": int(season_stat.get("homeRuns") or 0),
            "rbi": int(season_stat.get("rbi") or 0),
            "ops": str(season_stat.get("ops") or ""),
            "hits": int(season_stat.get("hits") or 0),
        }
    else:
        entry["season"] = {
            "games": int(season_stat.get("gamesPlayed") or 0),
            "wins": int(season_stat.get("wins") or 0),
            "losses": int(season_stat.get("losses") or 0),
            "era": str(season_stat.get("era") or ""),
            "ip": str(season_stat.get("inningsPitched") or ""),
            "so": int(season_stat.get("strikeOuts") or 0),
        }
    if last_split:
        g = last_split.get("stat") or {}
        last: dict = {
            "date": str(last_split.get("date") or ""),
            "opponent": team_ja((last_split.get("opponent") or {}).get("name") or ""),
        }
        if spec["group"] == "hitting":
            last["ab"] = int(g.get("atBats") or 0)
            last["hits"] = int(g.get("hits") or 0)
            last["hr"] = int(g.get("homeRuns") or 0)
            last["rbi"] = int(g.get("rbi") or 0)
        else:
            last["ip"] = str(g.get("inningsPitched") or "")
            last["runs"] = int(g.get("runs") or g.get("earnedRuns") or 0)
            last["so"] = int(g.get("strikeOuts") or 0)
            last["hits"] = int(g.get("hits") or 0)
        entry["last_game"] = last
    return entry


def _game_row(split: dict, group: str) -> dict:
    g = split.get("stat") or {}
    row: dict = {
        "date": str(split.get("date") or ""),
        "opponent": team_ja((split.get("opponent") or {}).get("name") or ""),
        "home": bool(split.get("isHome")),
    }
    if group == "hitting":
        row.update({
            "ab": int(g.get("atBats") or 0),
            "hits": int(g.get("hits") or 0),
            "hr": int(g.get("homeRuns") or 0),
            "rbi": int(g.get("rbi") or 0),
        })
    else:
        decision = "○" if int(g.get("wins") or 0) else ("●" if int(g.get("losses") or 0) else "－")
        row.update({
            "ip": str(g.get("inningsPitched") or ""),
            "hits": int(g.get("hits") or 0),
            "runs": int(g.get("runs") or 0),
            "so": int(g.get("strikeOuts") or 0),
            "bb": int(g.get("baseOnBalls") or 0),
            "pitches": int(g.get("numberOfPitches") or 0),
            "decision": decision,
        })
    return row


def _season_summary(stat: dict, group: str) -> dict:
    if group == "hitting":
        return {
            "games": int(stat.get("gamesPlayed") or 0),
            "avg": str(stat.get("avg") or ""),
            "hr": int(stat.get("homeRuns") or 0),
            "rbi": int(stat.get("rbi") or 0),
            "ops": str(stat.get("ops") or ""),
            "hits": int(stat.get("hits") or 0),
        }
    return {
        "games": int(stat.get("gamesPlayed") or 0),
        "wins": int(stat.get("wins") or 0),
        "losses": int(stat.get("losses") or 0),
        "era": str(stat.get("era") or ""),
        "ip": str(stat.get("inningsPitched") or ""),
        "so": int(stat.get("strikeOuts") or 0),
    }


def fetch_mlb_player_detail(spec: dict) -> dict | None:
    """1選手のメジャー移籍後全試合 + 直近試合の打席ログ (打者のみ) を取得する。

    返り値: {name, slug, group, team, debut, seasons: [{season, summary, games}] 新しい順,
            pa_log: {date, opponent, events: [日本語結果]}}  (取得失敗は None)
    """
    group = spec["group"]
    try:
        info = _get_json(f"{_API_BASE}/people/{spec['mlb_id']}?hydrate=currentTeam")
        person = (info.get("people") or [{}])[0]
        debut = str(person.get("mlbDebutDate") or "")
        team_en = (person.get("currentTeam") or {}).get("name") or ""
        debut_year = int(debut[:4]) if len(debut) >= 4 else datetime.now(_JST).year
        current_year = datetime.now(_JST).year
        seasons: list[dict] = []
        for year in range(current_year, debut_year - 1, -1):
            d = _get_json(
                f"{_API_BASE}/people/{spec['mlb_id']}/stats"
                f"?stats=season,gameLog&group={group}&season={year}"
            )
            season_stat: dict = {}
            games: list[dict] = []
            for s in d.get("stats") or []:
                type_name = ((s.get("type") or {}).get("displayName") or "")
                splits = s.get("splits") or []
                if type_name == "season" and splits:
                    season_stat = splits[0].get("stat") or {}
                elif type_name == "gameLog" and splits:
                    games = [_game_row(sp, group) for sp in splits]
            if games:
                seasons.append({
                    "season": year,
                    "summary": _season_summary(season_stat, group),
                    "games": list(reversed(games)),  # 新しい試合を上に
                })
        if not seasons:
            return None
        detail: dict = {
            "name": spec["name"],
            "slug": spec["slug"],
            "group": group,
            "team": team_ja(team_en),
            "debut": debut,
            "seasons": seasons,
        }
        if group == "hitting" and seasons[0]["games"]:
            last_date = seasons[0]["games"][0]["date"]
            try:
                pl = _get_json(
                    f"{_API_BASE}/people/{spec['mlb_id']}/stats"
                    f"?stats=playLog&group=hitting&season={seasons[0]['season']}"
                )
                splits = ((pl.get("stats") or [{}])[0]).get("splits") or []
                events = [
                    pa_event_ja((((sp.get("stat") or {}).get("play") or {}).get("details") or {}).get("event") or "")
                    for sp in splits
                    if str(sp.get("date") or "") == last_date
                ]
                events = [e for e in events if e]
                if events:
                    detail["pa_log"] = {
                        "date": last_date,
                        "opponent": seasons[0]["games"][0]["opponent"],
                        "events": events,
                    }
            except Exception as exc:  # noqa: BLE001
                LOG.warning("mlb playLog fetch failed player=%s: %r", spec["name"], exc)
        return detail
    except Exception as exc:  # noqa: BLE001
        LOG.warning("mlb player detail fetch failed player=%s: %r", spec["name"], exc)
        return None


def format_mlb_alumni_fact_line(entry: dict) -> str:
    """1選手 entry (``_extract_player`` 形) を X 投稿用の verified fact line に。

    MLB 文脈であることを必ず明示する (元巨人 OB だが 2026 巨人成績ではない)。
    値が無い part は skip。空 entry / season 無しは空 string を返す (caller は
    空なら従来の Giants DB fact にフォールバック)。
    """
    if not entry:
        return ""
    name = str(entry.get("name") or "").strip()
    season = entry.get("season") or {}
    if not name or not season:
        return ""
    team = str(entry.get("team") or "").strip()
    team_tag = f"MLB {team}" if team else "MLB"
    lines: list[str] = []
    if entry.get("group") == "hitting":
        parts: list[str] = []
        if season.get("avg"):
            parts.append(f"打率{season['avg']}")
        if season.get("hr"):
            parts.append(f"{season['hr']}本塁打")
        if season.get("rbi"):
            parts.append(f"{season['rbi']}打点")
        if season.get("ops"):
            parts.append(f"OPS{season['ops']}")
        head = f"- {name} ({team_tag}) 今季{int(season.get('games') or 0)}試合"
        lines.append(head + ("：" + " ".join(parts) if parts else ""))
        lg = entry.get("last_game") or {}
        if lg:
            opp = str(lg.get("opponent") or "").strip()
            lg_head = f"- 直近({lg.get('date','')}" + (f" 対{opp}" if opp else "") + ")"
            lg_parts: list[str] = []
            if lg.get("ab") is not None and lg.get("hits") is not None:
                lg_parts.append(f"{lg['ab']}打数{lg['hits']}安打")
            if lg.get("hr"):
                lg_parts.append(f"{lg['hr']}本塁打")
            if lg.get("rbi"):
                lg_parts.append(f"{lg['rbi']}打点")
            if lg_parts:
                lines.append(lg_head + "：" + " ".join(lg_parts))
    else:
        parts = []
        if season.get("wins") is not None and season.get("losses") is not None:
            parts.append(f"{season['wins']}勝{season['losses']}敗")
        if season.get("era"):
            parts.append(f"防御率{season['era']}")
        if season.get("ip"):
            parts.append(f"{season['ip']}回")
        if season.get("so"):
            parts.append(f"{season['so']}奪三振")
        head = f"- {name} ({team_tag}) 今季{int(season.get('games') or 0)}試合"
        lines.append(head + ("：" + " ".join(parts) if parts else ""))
        lg = entry.get("last_game") or {}
        if lg:
            opp = str(lg.get("opponent") or "").strip()
            lg_head = f"- 直近({lg.get('date','')}" + (f" 対{opp}" if opp else "") + ")"
            lg_parts = []
            if lg.get("ip"):
                lg_parts.append(f"{lg['ip']}回")
            if lg.get("runs") is not None:
                lg_parts.append(f"{lg['runs']}失点")
            if lg.get("so"):
                lg_parts.append(f"{lg['so']}奪三振")
            if lg_parts:
                lines.append(lg_head + "：" + " ".join(lg_parts))
    return "\n".join(lines)


def _name_key(name: str) -> str:
    return "".join(str(name or "").split())


def mlb_alumni_fact_line(player_name: str, data: dict) -> str:
    """``fetch_mlb_alumni_data`` の返り値から player_name 一致選手の fact line を返す。

    一致無し / data 空は空 string。 名前は空白無視で比較する。
    """
    if not player_name or not data:
        return ""
    key = _name_key(player_name)
    for entry in data.get("players") or []:
        if _name_key(entry.get("name")) == key:
            return format_mlb_alumni_fact_line(entry)
    return ""


def fetch_mlb_alumni_data(season: int | None = None, specs: list[dict] | None = None) -> dict:
    """全対象選手の今季成績 + 直近試合を取得する。失敗選手は除外。

    ``specs`` (2026-07-13 朝のMLB定点ポスト用): 対象選手 spec list を差し替え可
    (default は従来の MLB_ALUMNI = 記事化 policy の元巨人のみ)。X 定点ポストは
    大谷を加えた別 list を渡す (記事側の policy は不変)。
    """
    season = season or datetime.now(_JST).year
    players: list[dict] = []
    for spec in (specs if specs is not None else MLB_ALUMNI):
        try:
            stats = _get_json(
                f"{_API_BASE}/people/{spec['mlb_id']}/stats"
                f"?stats=season,gameLog&group={spec['group']}&season={season}"
            )
            info = _get_json(f"{_API_BASE}/people/{spec['mlb_id']}?hydrate=currentTeam")
        except Exception as exc:  # noqa: BLE001
            LOG.warning("mlb alumni fetch failed player=%s: %r", spec["name"], exc)
            continue
        entry = _extract_player(stats, info, spec)
        if entry:
            players.append(entry)
    dates = [p.get("last_game", {}).get("date") for p in players if p.get("last_game")]
    return {
        "season": season,
        "as_of": max([d for d in dates if d], default=""),
        "players": players,
    }
