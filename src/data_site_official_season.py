"""Validated NPB Giants season totals for salary context and pitching summaries."""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from functools import lru_cache

import requests

from src.data_site_farm_stats import _TableExtractor

LOG = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Match NPB display spacing and name variants without a salary-lane dependency."""
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"\([^)]*\)|（[^）]*）", "", name)
    name = re.sub(r"^[A-Z][.・]", "", name)
    return re.sub(r"\s+", "", name).replace("﨑", "崎").replace("髙", "高")

FIELDS = {
    'p': {'登板': 'games', '勝利': 'wins', '敗北': 'losses', 'セーブ': 'saves',
          '三振': 'k', '四球': 'bb', '安打': 'h_allowed', '本塁打': 'hr_allowed',
          '自責点': 'er', '投球回': 'ip', '防御率': 'era'},
    'b': {'試合': 'games', '打数': 'ab', '安打': 'hits', '本塁打': 'hr',
          '打点': 'rbi', '盗塁': 'sb', '打率': 'avg'},
}


def parse_official_season(html: str, year: int, kind: str) -> dict:
    if kind not in FIELDS:
        raise ValueError('unknown NPB statistics kind')
    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
    label = '個人投手成績' if kind == 'p' else '個人打撃成績'
    if not title or f'{year}年度 読売ジャイアンツ {label}' not in title[1]:
        raise ValueError('wrong NPB year/team/statistics')
    parser = _TableExtractor(); parser.feed(html)
    fields = FIELDS[kind]
    tables = [t for t in parser.tables if t and set(fields) | {'選手'} <= set(t[0])]
    if len(tables) != 1:
        raise ValueError('ambiguous NPB table')
    header, *rows = tables[0]
    result = {}
    for row in rows:
        if len(row) != len(header):
            raise ValueError('incomplete NPB row')
        name = normalize_name(re.sub(r'^[*+\s]+', '', row[header.index('選手')]))
        if not name or name in result:
            raise ValueError('ambiguous NPB player')
        rec = {}
        for source, field in fields.items():
            raw = re.sub(r'\s+', '', row[header.index(source)])
            if field == 'ip':
                if not re.fullmatch(r'\d+(?:\.[012])?', raw):
                    raise ValueError('invalid NPB innings')
                whole, _, third = raw.partition('.')
                rec[field] = int(whole) + int(third or 0) / 3
            elif field in ('era', 'avg'):
                if not re.fullmatch(r'(?:\d+)?\.\d{2,3}|-+', raw):
                    raise ValueError('invalid NPB rate')
                rec[field] = None if '-' in raw else raw
            else:
                if not re.fullmatch(r'\d+', raw):
                    raise ValueError('invalid NPB count')
                rec[field] = int(raw)
        if rec['games'] > 0:
            result[name] = rec
    if len(result) < 5:
        raise ValueError('NPB table unexpectedly empty')
    return result


@lru_cache(maxsize=4)
def official_season_map(year: int, kind: str) -> dict:
    url = f'https://npb.jp/bis/{year}/stats/id{kind}1_g.html'
    try:
        r = requests.get(url, headers={'Accept-Encoding': 'gzip, deflate'}, timeout=20)
        r.raise_for_status()
        return parse_official_season(r.content.decode('utf-8'), year, kind)
    except (requests.RequestException, ValueError, UnicodeError) as exc:
        LOG.warning('official season unavailable year=%d kind=%s error=%s', year, kind, type(exc).__name__)
        return {}


def comparison_snapshot(year: int, day: date) -> dict | None:
    pitching = official_season_map(year, 'p')
    batting = official_season_map(year, 'b')
    if not pitching or not batting:
        return None
    return {'year': year, 'checked_on': day.isoformat(), 'pitching': pitching, 'batting': batting,
            'sources': [f'https://npb.jp/bis/{year}/stats/id{k}1_g.html' for k in ('p', 'b')]}
