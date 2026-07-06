"""data/opening-pitchers page (巨人 歴代開幕投手 1936-2026) — 2026-07-06 user GO。

「巨人 開幕投手 歴代」は毎年2-3月に検索が跳ねる季節性の恒久資産クエリ。
データは Wikipedia「開幕投手」の巨人列 (1936-2026 全90年) を bake し、
最新年 (2026=竹丸和幸) は npb.jp 公式コラムで cross-check 済み
(config/giants_opening_pitchers.json の _note 参照)。
"""

from __future__ import annotations

import html as _html
import json as _json
import os as _os
from collections import Counter

from src.data_site_internal_link import linkify, load_slug_map

_DATA_PATH = _os.path.join(
    _os.path.dirname(__file__), "..", "config", "giants_opening_pitchers.json"
)


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def load_opening_pitchers() -> list[dict]:
    try:
        with open(_DATA_PATH, encoding="utf-8") as fh:
            data = _json.load(fh)
        return list(data.get("opening_pitchers") or [])
    except Exception:  # noqa: BLE001
        return []


def render_opening_pitchers_title(rows: list[dict]) -> str:
    if not rows:
        return "巨人 歴代開幕投手 一覧 | 巨人データ"
    first = rows[0]["year"]
    last = rows[-1]["year"]
    return f"巨人 歴代開幕投手 一覧【{first}-{last}年・全{len(rows)}年】 | 巨人データ"


def render_opening_pitchers_excerpt(rows: list[dict]) -> str:
    latest = rows[-1] if rows else {}
    return (
        f"読売ジャイアンツの歴代開幕投手を{rows[0]['year'] if rows else ''}年から全年度一覧化。"
        f"{latest.get('year','')}年は{latest.get('name','')}。最多回数ランキングつきの巨人データです。"
    )


def render_opening_pitchers_html(rows: list[dict]) -> str:
    if not rows:
        return "<p>データ準備中です。</p>"
    slug_map = load_slug_map()
    latest = rows[-1]
    counts = Counter(r["name"] for r in rows)
    top = counts.most_common(10)
    parts: list[str] = [
        f"<p>読売ジャイアンツ（巨人）の歴代開幕投手の全記録です。"
        f"{rows[0]['year']}年の{_esc(rows[0]['name'])}から{latest['year']}年の"
        f"{_esc(latest['name'])}まで、全{len(rows)}年分を一覧化しました。</p>",
        f'<h2 style="font-size:17px;">🏆 開幕投手 回数ランキング</h2>',
        "<table><thead><tr><th>順位</th><th>投手</th><th>回数</th></tr></thead><tbody>"
        + "".join(
            f"<tr><td>{i}</td><td>{linkify(name, slug_map)}</td><td>{n}回</td></tr>"
            for i, (name, n) in enumerate(top, start=1)
        )
        + "</tbody></table>",
        f'<h2 style="font-size:17px;">📅 年度別 開幕投手（{latest["year"]}年 → {rows[0]["year"]}年）</h2>',
        "<table><thead><tr><th>年</th><th>開幕投手</th></tr></thead><tbody>"
        + "".join(
            f"<tr><td>{r['year']}</td><td>{linkify(r['name'], slug_map)}</td></tr>"
            for r in reversed(rows)
        )
        + "</tbody></table>",
        '<p style="margin-top:16px;">🔄 今季の先発ローテーションは'
        '<a href="/data/rotation">先発ローテ一覧</a>、離脱状況は'
        '<a href="/data/injured">離脱選手・復帰予定</a>をご覧ください。</p>',
    ]
    return "\n".join(parts)
