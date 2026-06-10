"""Templates for /data/farm/ topic cluster.

Pages:
- /data/farm/                 hub
- /data/farm/schedule/        2gun schedule/results
- /data/farm/spring-education/
- /data/farm/autumn-education/
- /data/farm/team/
- /data/farm/players/
- /data/farm/titles/
- /data/farm/championship/
"""

from __future__ import annotations

import html as _html
import json as _json

from src.data_site_farm_source import (
    FARM_SOURCE_URLS,
    FarmGameRow,
    FarmGenericRow,
    FarmPlayerStat,
)
from src.data_site_slug import player_slug


SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = f"{SITE_BASE}/data"
FARM_URL = f"{SITE_BASE}/data/farm"

FARM_CHILDREN = [
    ("schedule", "2軍試合日程・結果", "試合予定・スコア・継投を確認"),
    ("spring-education", "春季教育リーグ", "開幕前の若手・調整登板を確認"),
    ("autumn-education", "秋季教育リーグ", "フェニックスリーグなど秋の実戦"),
    ("team", "2軍年度別チーム成績", "順位・勝敗・打撃/投手の年表"),
    ("players", "2軍個人成績", "打者・投手の今季成績"),
    ("titles", "2軍タイトルホルダー", "歴代受賞者と今季リーダー"),
    ("championship", "ファーム日本選手権", "出場年・結果・日本一履歴"),
]


def _esc(text: str) -> str:
    return _html.escape(str(text or ""), quote=True)


def _child_url(slug: str) -> str:
    return f"{FARM_URL}/{slug}"


def _nav(active: str = "") -> str:
    links = [
        f'<a href="{FARM_URL}" style="{_nav_style(active == "hub")}">2軍トップ</a>'
    ]
    for slug, label, _desc in FARM_CHILDREN:
        links.append(f'<a href="{_child_url(slug)}" style="{_nav_style(active == slug)}">{_esc(label)}</a>')
    return (
        '<nav class="ys-farm-nav" style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 16px;">'
        + "".join(links)
        + "</nav>"
    )


def _nav_style(active: bool) -> str:
    if active:
        return (
            "display:inline-block;padding:8px 10px;border-radius:999px;"
            "background:#e65100;color:#fff;text-decoration:none;font-size:12px;font-weight:700;"
        )
    return (
        "display:inline-block;padding:8px 10px;border-radius:999px;"
        "background:#fff3e0;color:#a94400;text-decoration:none;font-size:12px;font-weight:700;"
    )


def _breadcrumb(label: str) -> str:
    return (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › '
        f'<a href="{FARM_URL}" style="color:#666;">2軍ファーム</a> › '
        f'<span>{_esc(label)}</span></nav>'
    )


def _source_note(url: str, label: str = "my favorite giants") -> str:
    return (
        '<p style="font-size:11px;color:#888;margin:10px 0 0;">'
        f'参考データ: <a href="{_esc(url)}" rel="nofollow noopener" target="_blank">{_esc(label)}</a>。'
        'ヨシラバー側で見やすく再整理しています。</p>'
    )


def _shell(title: str, lead: str, body: str, *, active: str, source_url: str = "") -> str:
    src = _source_note(source_url) if source_url else ""
    return (
        '<div class="ys-farm" style="font-family:sans-serif;max-width:760px;">'
        f'{_breadcrumb(title)}'
        f'{_nav(active)}'
        f'<h1 style="font-size:22px;line-height:1.35;margin:0 0 6px;">{_esc(title)}</h1>'
        f'<p style="font-size:13px;color:#666;line-height:1.7;margin:0 0 16px;">{_esc(lead)}</p>'
        f'{body}'
        f'{src}'
        f'<p style="margin:18px 0 0;"><a href="{FARM_URL}">← 2軍ファームトップへ戻る</a></p>'
        '</div>'
    )


def _score_badge(score: str) -> str:
    if not score:
        return '<span style="color:#888;">-</span>'
    color = "#1b7f3b" if score.startswith("○") else ("#777" if score.startswith("●") else "#b0860b")
    return f'<span style="font-weight:800;color:{color};">{_esc(score)}</span>'


def _game_cards(rows: list[FarmGameRow], *, limit: int = 12) -> str:
    if not rows:
        return '<p style="font-size:13px;color:#888;">データ取得待ちです。更新後にここへ反映します。</p>'
    cards = []
    for r in rows[:limit]:
        meta = " / ".join(x for x in [r.competition, r.home_away, r.venue] if x)
        sub = " / ".join(x for x in [f"通算 {r.record}" if r.record else "", f"安打 {r.hits}" if r.hits else "", r.homers] if x)
        cards.append(
            '<article style="border:1px solid #eee;border-radius:8px;padding:10px 12px;background:#fff;margin:0 0 8px;">'
            '<div style="display:flex;gap:10px;align-items:center;justify-content:space-between;">'
            f'<strong style="font-size:14px;">{_esc(r.date_label)}({ _esc(r.weekday) }) vs {_esc(r.opponent)}</strong>'
            f'{_score_badge(r.score)}'
            '</div>'
            f'<div style="font-size:12px;color:#777;margin-top:4px;">{_esc(meta)}</div>'
            f'<div style="font-size:12px;color:#555;margin-top:4px;">{_esc(r.pitchers)}</div>'
            f'<div style="font-size:12px;color:#777;margin-top:3px;">{_esc(sub)}</div>'
            '</article>'
        )
    return "".join(cards)


def _count_results(rows: list[FarmGameRow]) -> tuple[int, int, int]:
    w = sum(1 for r in rows if r.score.startswith("○"))
    l = sum(1 for r in rows if r.score.startswith("●"))
    d = sum(1 for r in rows if r.score.startswith("△"))
    return w, l, d


def _stat_card(label: str, value: str, note: str = "") -> str:
    return (
        '<div style="background:#fff;border:1px solid #eee;border-radius:8px;padding:12px;">'
        f'<div style="font-size:12px;color:#777;">{_esc(label)}</div>'
        f'<div style="font-size:24px;font-weight:800;color:#e65100;line-height:1.2;">{_esc(value)}</div>'
        f'<div style="font-size:11px;color:#888;">{_esc(note)}</div>'
        '</div>'
    )


def render_farm_hub_html(rows: list[FarmGameRow], batting: list[FarmPlayerStat], pitching: list[FarmPlayerStat]) -> str:
    w, l, d = _count_results([r for r in rows if r.competition == "ファーム公式戦"])
    recent = list(reversed(rows[-6:])) if rows else []
    cards = "".join(
        '<a href="{url}" style="display:block;background:#fff;border:1px solid #eee;border-radius:8px;'
        'padding:12px;text-decoration:none;color:#1a1a1a;">'
        '<strong style="display:block;font-size:14px;margin-bottom:4px;color:#e65100;">{label}</strong>'
        '<span style="font-size:12px;color:#666;line-height:1.5;">{desc}</span></a>'.format(
            url=_child_url(slug), label=_esc(label), desc=_esc(desc)
        )
        for slug, label, desc in FARM_CHILDREN
    )
    top_batter = batting[0] if batting else None
    top_pitcher = pitching[0] if pitching else None
    summary = (
        '<section style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 16px;">'
        f'{_stat_card("ファーム公式戦", f"{w}勝{l}敗{d}分", "2軍公式戦のみ")}'
        f'{_stat_card("打率上位", top_batter.name if top_batter else "-", top_batter.avg if top_batter else "")}'
        f'{_stat_card("防御率上位", top_pitcher.name if top_pitcher else "-", top_pitcher.era if top_pitcher else "")}'
        '</section>'
    )
    body = (
        f'{summary}'
        '<section style="margin:0 0 16px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;">2軍データメニュー</h2>'
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;">{cards}</div>'
        '</section>'
        '<section style="margin:0 0 16px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;">直近の2軍試合</h2>'
        f'{_game_cards(recent, limit=6)}'
        '</section>'
        f'<section style="margin:0 0 16px;background:#fff8f2;border:1px solid #ffd9bf;border-radius:8px;padding:12px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">SNSで2軍・3軍の話題を見る</h2>'
        f'<p style="font-size:13px;color:#666;margin:0 0 8px;">試合中の反応や若手選手の話題はリアルタイムページで追えます。</p>'
        f'<a href="{SITE_BASE}/giants-sns-realtime-farm/" style="font-weight:700;color:#e65100;">2軍・3軍 SNSリアルタイムへ →</a>'
        '</section>'
    )
    return _shell(
        "巨人 2軍ファームデータ",
        "試合日程・結果、教育リーグ、年度別成績、個人成績、タイトルホルダー、ファーム日本選手権をまとめた2軍データの入口です。",
        body,
        active="hub",
        source_url=FARM_SOURCE_URLS["hub"],
    ) + _jsonld()


def render_farm_schedule_html(rows: list[FarmGameRow]) -> str:
    official = [r for r in rows if r.competition == "ファーム公式戦"]
    body = (
        '<section style="margin:0 0 14px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;">ファーム公式戦</h2>'
        f'{_game_cards(list(reversed(official)), limit=40)}'
        '</section>'
    )
    return _shell(
        "巨人 2軍試合日程・結果 2026",
        "ファーム公式戦のスコア、相手、球場、継投、本塁打を新しい順に確認できます。",
        body,
        active="schedule",
        source_url=FARM_SOURCE_URLS["schedule"],
    )


def render_farm_education_html(rows: list[FarmGameRow], *, kind: str) -> str:
    label = "春季教育リーグ" if kind == "spring" else "秋季教育リーグ"
    filtered = [r for r in rows if r.competition == label]
    source = FARM_SOURCE_URLS["spring"] if kind == "spring" else FARM_SOURCE_URLS["autumn"]
    body = (
        '<section style="margin:0 0 14px;">'
        f'<h2 style="font-size:17px;margin:0 0 8px;">{_esc(label)} 試合結果</h2>'
        f'{_game_cards(filtered, limit=40)}'
        '</section>'
        '<p style="font-size:12px;color:#666;">教育リーグは若手起用・調整登板の文脈が強いため、公式戦成績とは分けて見ます。</p>'
    )
    return _shell(
        f"巨人 2軍{label} 試合結果",
        "開幕前・秋季の実戦を、公式戦とは分けて確認するページです。",
        body,
        active="spring-education" if kind == "spring" else "autumn-education",
        source_url=source,
    )


def render_farm_team_html(rows: list[FarmGameRow], history_rows: list[FarmGenericRow]) -> str:
    official = [r for r in rows if r.competition == "ファーム公式戦"]
    w, l, d = _count_results(official)
    latest_history = _generic_table(history_rows[:12], ["年", "監督/順位", "試合", "勝敗", "勝率", "打率/防御率"])
    body = (
        '<section style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 16px;">'
        f'{_stat_card("2026公式戦", f"{w}勝{l}敗{d}分", "現時点の集計")}'
        f'{_stat_card("消化試合", str(w + l + d), "勝敗付き試合")}'
        '</section>'
        '<section style="margin:0 0 16px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;">年度別チーム成績</h2>'
        f'{latest_history}'
        '</section>'
    )
    return _shell(
        "巨人 2軍年度別チーム成績",
        "2軍の順位、勝敗、勝率、打撃・投手成績を年度別に見るためのページです。",
        body,
        active="team",
        source_url=FARM_SOURCE_URLS["team_history"],
    )


def _generic_table(rows: list[FarmGenericRow], headers: list[str]) -> str:
    if not rows:
        return '<p style="font-size:13px;color:#888;">データ取得待ちです。</p>'
    trs = []
    for r in rows:
        cells = list(r.cells[: len(headers)])
        cells += [""] * (len(headers) - len(cells))
        trs.append(
            '<tr style="border-bottom:1px solid #eee;">'
            + "".join(f'<td style="padding:8px 10px;font-size:12px;">{_esc(c)}</td>' for c in cells)
            + "</tr>"
        )
    return (
        '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #eee;">'
        '<thead><tr style="background:#fafafa;">'
        + "".join(f'<th style="padding:9px 10px;text-align:left;font-size:12px;">{_esc(h)}</th>' for h in headers)
        + "</tr></thead><tbody>"
        + "".join(trs)
        + "</tbody></table></div>"
    )


def render_farm_players_html(batting: list[FarmPlayerStat], pitching: list[FarmPlayerStat]) -> str:
    body = (
        '<input type="search" id="ys-farm-player-search" placeholder="選手名で検索" '
        'style="width:100%;box-sizing:border-box;padding:11px 12px;border:2px solid #ffd9bf;border-radius:8px;margin:0 0 12px;">'
        '<section style="margin:0 0 16px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;">打撃成績</h2>'
        f'{_player_table(batting, "batting")}'
        '</section>'
        '<section style="margin:0 0 16px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;">投手成績</h2>'
        f'{_player_table(pitching, "pitching")}'
        '</section>'
        '<script>(function(){var q=document.getElementById("ys-farm-player-search");if(!q)return;'
        'var rows=[].slice.call(document.querySelectorAll("[data-farm-player]"));'
        'q.addEventListener("input",function(){var s=(q.value||"").replace(/\\s+/g,"");'
        'rows.forEach(function(r){var n=(r.getAttribute("data-farm-player")||"").replace(/\\s+/g,"");'
        'r.style.display=(!s||n.indexOf(s)>=0)?"":"none";});});})();</script>'
    )
    return _shell(
        "巨人 2軍個人成績 2026",
        "2軍での打撃成績・投手成績を選手名検索つきで確認できます。",
        body,
        active="players",
        source_url=FARM_SOURCE_URLS["players"],
    )


def _player_link(name: str) -> str:
    try:
        href = f"/data/{player_slug(name)}"
    except Exception:  # noqa: BLE001
        return _esc(name)
    return f'<a href="{href}" style="font-weight:700;color:#1976d2;text-decoration:none;">{_esc(name)}</a>'


def _player_table(rows: list[FarmPlayerStat], role: str) -> str:
    if not rows:
        return '<p style="font-size:13px;color:#888;">データ取得待ちです。</p>'
    if role == "batting":
        headers = ["選手", "試合", "安打", "本", "打点", "盗塁", "打率"]
        values = lambda r: [_player_link(r.name), r.games, r.hits, r.hr, r.rbi, r.sb, r.avg]
    else:
        headers = ["選手", "登板", "勝", "敗", "S", "投球回", "奪三", "防御率"]
        values = lambda r: [_player_link(r.name), r.games, r.wins, r.losses, r.saves, r.innings, r.strikeouts, r.era]
    trs = []
    for r in rows:
        vals = values(r)
        trs.append(
            f'<tr data-farm-player="{_esc(r.name)}" style="border-bottom:1px solid #eee;">'
            + "".join(f'<td style="padding:8px 10px;font-size:12px;">{v}</td>' for v in vals)
            + "</tr>"
        )
    return (
        '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #eee;">'
        '<thead><tr style="background:#fafafa;">'
        + "".join(f'<th style="padding:9px 10px;text-align:left;font-size:12px;">{_esc(h)}</th>' for h in headers)
        + "</tr></thead><tbody>"
        + "".join(trs)
        + "</tbody></table></div>"
    )


def render_farm_titles_html(
    batting: list[FarmPlayerStat],
    pitching: list[FarmPlayerStat],
    title_rows: list[FarmGenericRow],
) -> str:
    leader_cards = [
        _leader_card("打率", batting, lambda r: r.avg),
        _leader_card("本塁打", sorted(batting, key=lambda r: _num(r.hr), reverse=True), lambda r: f"{r.hr}本"),
        _leader_card("打点", sorted(batting, key=lambda r: _num(r.rbi), reverse=True), lambda r: f"{r.rbi}点"),
        _leader_card("防御率", pitching, lambda r: r.era),
        _leader_card("勝利", sorted(pitching, key=lambda r: _num(r.wins), reverse=True), lambda r: f"{r.wins}勝"),
        _leader_card("奪三振", sorted(pitching, key=lambda r: _num(r.strikeouts), reverse=True), lambda r: f"{r.strikeouts}奪三振"),
    ]
    body = (
        '<section style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 16px;">'
        + "".join(leader_cards)
        + "</section>"
        '<section style="margin:0 0 16px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;">歴代2軍タイトルホルダー</h2>'
        f'{_generic_table(title_rows[:16], ["年", "主要タイトル", "打撃", "投手", "備考"])}'
        '</section>'
    )
    return _shell(
        "巨人 2軍タイトルホルダー",
        "歴代の2軍タイトルホルダーと、今季チーム内リーダーをまとめて見られるページです。",
        body,
        active="titles",
        source_url=FARM_SOURCE_URLS["titles"],
    )


def _leader_card(label: str, rows: list[FarmPlayerStat], value_fn) -> str:  # noqa: ANN001
    row = rows[0] if rows else None
    if not row:
        return _stat_card(label, "-", "")
    return _stat_card(label, row.name, value_fn(row))


def _num(v: str) -> int:
    try:
        return int(str(v or "0").replace("-", "0"))
    except ValueError:
        return 0


def render_farm_championship_html(series_rows: list[FarmGenericRow]) -> str:
    body = (
        '<section style="margin:0 0 16px;">'
        '<h2 style="font-size:17px;margin:0 0 8px;">ファーム日本選手権 成績一覧</h2>'
        f'{_generic_table(series_rows[:18], ["年", "相手", "球場", "勝敗", "スコア", "備考"])}'
        '</section>'
    )
    return _shell(
        "巨人 ファーム日本選手権",
        "2軍日本一を決めるファーム日本選手権の巨人関連成績を整理するページです。",
        body,
        active="championship",
        source_url=FARM_SOURCE_URLS["championship"],
    )


def _jsonld() -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "巨人 2軍ファームデータ",
        "url": FARM_URL,
        "isPartOf": {"@type": "WebSite", "name": "ヨシラバー", "url": SITE_BASE + "/"},
        "mainEntity": {
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": label, "url": _child_url(slug)}
                for i, (slug, label, _desc) in enumerate(FARM_CHILDREN)
            ],
        },
    }
    return f'<script type="application/ld+json">{_json.dumps(payload, ensure_ascii=False)}</script>'


def render_farm_title() -> str:
    return "巨人 2軍ファームデータ 2026 - 試合日程・結果・個人成績 | ヨシラバー"


def render_farm_excerpt(rows: list[FarmGameRow]) -> str:
    w, l, d = _count_results([r for r in rows if r.competition == "ファーム公式戦"])
    return f"読売ジャイアンツ2軍ファームの試合日程・結果、年度別チーム成績、個人成績、タイトルホルダーを整理。2026年公式戦は{w}勝{l}敗{d}分。"


def render_farm_child_title(slug: str) -> str:
    labels = {s: label for s, label, _desc in FARM_CHILDREN}
    return f"巨人 {labels.get(slug, '2軍ファーム')} 2026 | ヨシラバー"


def render_farm_child_excerpt(slug: str) -> str:
    labels = {s: label for s, label, desc in FARM_CHILDREN}
    descs = {s: desc for s, label, desc in FARM_CHILDREN}
    return f"巨人2軍ファームの{labels.get(slug, 'データ')}。{descs.get(slug, 'ファーム情報を見やすく整理。')}"


__all__ = [
    "FARM_CHILDREN",
    "render_farm_child_excerpt",
    "render_farm_child_title",
    "render_farm_championship_html",
    "render_farm_education_html",
    "render_farm_excerpt",
    "render_farm_hub_html",
    "render_farm_players_html",
    "render_farm_schedule_html",
    "render_farm_team_html",
    "render_farm_title",
    "render_farm_titles_html",
]
