"""data/leaders ページ template (巨人選手内 各種記録ランキング、Phase B 452)。

本塁打/打点/安打/盗塁/打率/奪三振/勝利/防御率 を選手内ランキングで表示。
SEO: 「巨人 本塁打 ランキング」「巨人 打点 トップ」等の項目×ランキング ロングテール。
"""

from __future__ import annotations

import html as _html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"

# 表示順 + 単位ラベル
_BAT_KEYS = ["本塁打", "打点", "安打", "打率", "盗塁"]
_PIT_KEYS = ["奪三振", "勝利", "防御率"]


def _esc(t: str) -> str:
    return _html.escape(str(t or ""), quote=True)


def render_leaders_title() -> str:
    return "巨人 選手別ランキング 2026【本塁打・打点・防御率ほか】 | 巨人データ"


def render_leaders_excerpt(leaders: dict) -> str:
    hr = leaders.get("本塁打") or []
    top = f"本塁打{hr[0].display}の{_short(hr[0].player)}" if hr else "各種記録"
    return (f"読売ジャイアンツ2026の選手別ランキング。{top}など、本塁打・打点・安打・打率・"
            "盗塁・奪三振・勝利・防御率をチーム内順位で。大手にない巨人専用リーダーボード。")


def _short(name: str) -> str:
    return name.replace(" ", "")


def _rank_block(title: str, entries: list) -> str:
    if not entries:
        return ""
    rows = "".join(
        '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;'
        f'border-bottom:1px solid #f0f0f0;">'
        f'<span style="width:24px;color:#888;font-weight:700;text-align:center;">{i}</span>'
        f'<span style="flex:1;">{_esc(_short(e.player))}</span>'
        f'<span style="font-weight:700;color:#c0392b;">{_esc(e.display)}</span></div>'
        for i, e in enumerate(entries, 1)
    )
    return (
        '<section class="ys-card" style="margin:0 0 14px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">巨人 {_esc(title)} ランキング</h2>'
        f'{rows}</section>'
    )


def render_leaders_html(leaders: dict) -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>選手別ランキング</span></nav>'
    )
    bat = "".join(_rank_block(k, leaders.get(k) or []) for k in _BAT_KEYS)
    pit = "".join(_rank_block(k, leaders.get(k) or []) for k in _PIT_KEYS)
    return (
        '<div style="font-family:sans-serif;max-width:640px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 選手別ランキング 2026</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 14px;">今季の巨人選手内の各種記録トップ。打率は30打数以上、防御率は10回以上。</p>'
        '<h2 style="font-size:15px;color:#5d4037;margin:10px 0 8px;">― 打撃 ―</h2>'
        f'{bat}'
        '<h2 style="font-size:15px;color:#5d4037;margin:16px 0 8px;">― 投手 ―</h2>'
        f'{pit}'
        f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
        '</div>'
    )
