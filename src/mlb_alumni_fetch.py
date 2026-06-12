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
    {"mlb_id": 672960, "name": "岡本和真", "group": "hitting"},
    {"mlb_id": 608372, "name": "菅野智之", "group": "pitching"},
]

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


def fetch_mlb_alumni_data(season: int | None = None) -> dict:
    """全対象選手の今季成績 + 直近試合を取得する。失敗選手は除外。"""
    season = season or datetime.now(_JST).year
    players: list[dict] = []
    for spec in MLB_ALUMNI:
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
