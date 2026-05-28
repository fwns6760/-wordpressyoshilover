"""Cluster page (`/data/`) template (data-site Phase 1.0 / ticket 444).

Cluster URL: yoshilover.com/data/
内容: 巨人選手 全員 hub、 各 Pillar への internal link 表
      + JSON-LD (CollectionPage + ItemList of SportsPlayer)

Phase 1.0 では 3 player のみ表示、 Phase 1.5/1 で拡張。
"""

from __future__ import annotations

import html as _html
import json as _json
from dataclasses import dataclass


SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = f"{SITE_BASE}/data/"


@dataclass
class ClusterPlayerEntry:
    """Cluster 表 1 行分の情報。"""
    name: str
    slug: str
    position: str
    jersey_number: str
    role: str = "player"
    # Phase 1.0 batting stats (insight.db SUM、 data 無ければ "-" 表示)
    season_games: int = 0
    season_hits: int = 0
    season_rbi: int = 0
    season_avg: float | None = None
    has_stats: bool = False
    # Phase 1.5+pitch (投手 stats、 position=投手 のみ意味あり)
    pitch_games: int = 0
    pitch_wins: int = 0
    pitch_losses: int = 0
    pitch_ip: float = 0.0
    pitch_k: int = 0
    pitch_era: float | None = None
    has_pitching_stats: bool = False


def _esc(text: str) -> str:
    return _html.escape(str(text or ""), quote=True)


def _build_intro_html() -> str:
    return (
        '<section class="ys-cluster-intro" '
        'style="background:#fff8e1;border-left:3px solid #f57f17;'
        'padding:14px 18px;margin:0 0 20px;border-radius:4px;">'
        '<h2 style="font-size:17px;margin:0 0 10px;color:#5d4037;">巨人選手データ</h2>'
        '<p style="font-size:13px;line-height:1.7;margin:0;color:#444;">'
        '読売ジャイアンツの 1 軍・2 軍 active 選手の永続データページ集です。 '
        '各選手の打率・防御率・直近 5 試合・関連記事を、 毎朝 6 時に最新化しています。'
        '</p></section>'
    )


def _jersey_sort_key(p: ClusterPlayerEntry) -> tuple[int, str]:
    """背番号を数字昇順で並べる。 数字でなければ末尾 (999999)。"""
    try:
        return (int(p.jersey_number), p.name)
    except (ValueError, TypeError):
        return (999999, p.name or "")


def _fmt_avg(avg: float | None) -> str:
    if avg is None:
        return "-"
    return f"{avg:.3f}".lstrip("0") if avg < 1 else f"{avg:.3f}"


def _fmt_era(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v:.2f}"


def _fmt_ip(ip: float) -> str:
    if ip <= 0:
        return "-"
    return f"{ip:.1f}"


def _build_batter_table_html(players: list[ClusterPlayerEntry]) -> str:
    """打者 (position != 投手) のみ含む table。 背番号順。"""
    batters = [p for p in players if (p.position or "") != "投手"]
    if not batters:
        return ""
    sorted_players = sorted(batters, key=_jersey_sort_key)
    rows = []
    for p in sorted_players:
        pillar_url = f"/data/{p.slug}/"
        pos = p.position or "-"
        jersey = p.jersey_number or "-"
        avg = _fmt_avg(p.season_avg)
        games = str(p.season_games) if p.has_stats else "-"
        hits = str(p.season_hits) if p.has_stats else "-"
        rbi = str(p.season_rbi) if p.has_stats else "-"
        rows.append(
            f'<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:8px 10px;text-align:center;color:#555;font-weight:600;">{_esc(jersey)}</td>'
            f'<td style="padding:8px 10px;"><a href="{_esc(pillar_url)}" '
            'style="color:#1976d2;text-decoration:none;font-weight:600;">'
            f'{_esc(p.name)}</a></td>'
            f'<td style="padding:8px 10px;font-size:13px;color:#666;">{_esc(pos)}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{games}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{hits}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#1976d2;font-weight:600;">{avg}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{rbi}</td>'
            '</tr>'
        )
    return (
        '<section class="ys-cluster-batter-table" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">野手 一覧 ({len(sorted_players)} 名 / 背番号順)</h2>'
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:left;">'
        '<th style="padding:10px;text-align:center;">背番号</th>'
        '<th style="padding:10px;">名前</th>'
        '<th style="padding:10px;">ポジション</th>'
        '<th style="padding:10px;text-align:center;">試合</th>'
        '<th style="padding:10px;text-align:center;">安打</th>'
        '<th style="padding:10px;text-align:center;">打率</th>'
        '<th style="padding:10px;text-align:center;">打点</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</div></section>'
    )


def _build_pitcher_table_html(players: list[ClusterPlayerEntry]) -> str:
    """投手 (position == 投手) のみ含む table。 背番号順。"""
    pitchers = [p for p in players if (p.position or "") == "投手"]
    if not pitchers:
        return ""
    sorted_players = sorted(pitchers, key=_jersey_sort_key)
    rows = []
    for p in sorted_players:
        pillar_url = f"/data/{p.slug}/"
        jersey = p.jersey_number or "-"
        games = str(p.pitch_games) if p.has_pitching_stats else "-"
        wl = f"{p.pitch_wins}-{p.pitch_losses}" if p.has_pitching_stats else "-"
        ip = _fmt_ip(p.pitch_ip) if p.has_pitching_stats else "-"
        era = _fmt_era(p.pitch_era)
        k = str(p.pitch_k) if p.has_pitching_stats else "-"
        rows.append(
            f'<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:8px 10px;text-align:center;color:#555;font-weight:600;">{_esc(jersey)}</td>'
            f'<td style="padding:8px 10px;"><a href="{_esc(pillar_url)}" '
            'style="color:#1976d2;text-decoration:none;font-weight:600;">'
            f'{_esc(p.name)}</a></td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{games}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{wl}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{ip}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#1976d2;font-weight:600;">{era}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{k}</td>'
            '</tr>'
        )
    return (
        '<section class="ys-cluster-pitcher-table" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">投手 一覧 ({len(sorted_players)} 名 / 背番号順)</h2>'
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:left;">'
        '<th style="padding:10px;text-align:center;">背番号</th>'
        '<th style="padding:10px;">名前</th>'
        '<th style="padding:10px;text-align:center;">登板</th>'
        '<th style="padding:10px;text-align:center;">勝-敗</th>'
        '<th style="padding:10px;text-align:center;">投球回</th>'
        '<th style="padding:10px;text-align:center;">防御率</th>'
        '<th style="padding:10px;text-align:center;">奪三振</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</div></section>'
    )


def _build_player_table_html(players: list[ClusterPlayerEntry]) -> str:
    """野手 + 投手 の 2 表に分離。 空 list は placeholder."""
    if not players:
        return '<p style="font-size:13px;color:#888;margin:0;">対象選手データを準備中です。</p>'
    return (
        _build_batter_table_html(players)
        + "\n"
        + _build_pitcher_table_html(players)
        + '<p style="font-size:11px;color:#999;margin:8px 0 0;">'
        '※ stats は insight.db (NPB official box score 由来)、 毎朝 6:00 + 試合後 17:30 / 23:00 JST 更新。 「-」 はデータ集計中。'
        '</p>'
    )


def _build_footnote_html(players_count: int) -> str:
    return (
        '<section class="ys-cluster-footnote" style="font-size:12px;color:#888;margin:24px 0 0;">'
        f'<p style="margin:0;">現在 {players_count} 名分の個別ページを公開中 '
        '(Phase 1.0 MVP)。 順次拡大予定 (Phase 1.5: 一軍 30 名、 Phase 1 full: 110 名)。</p>'
        '</section>'
    )


def _build_jsonld(players: list[ClusterPlayerEntry]) -> str:
    item_list = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "巨人選手データ",
        "url": CLUSTER_URL,
        "isPartOf": {
            "@type": "WebSite",
            "name": "ヨシラバー｜読売ジャイアンツ速報掲示板",
            "url": SITE_BASE + "/",
        },
        "mainEntity": {
            "@type": "ItemList",
            "name": "巨人選手データ 一覧",
            "numberOfItems": len(players),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "item": {
                        "@type": "SportsPlayer",
                        "name": p.name,
                        "url": f"{SITE_BASE}/data/{p.slug}/",
                        "memberOf": {
                            "@type": "SportsTeam",
                            "name": "読売ジャイアンツ",
                        },
                    },
                }
                for i, p in enumerate(players)
            ],
        },
    }
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": "巨人選手データ", "item": CLUSTER_URL},
        ],
    }
    return (
        f'<script type="application/ld+json">{_json.dumps(item_list, ensure_ascii=False)}</script>\n'
        f'<script type="application/ld+json">{_json.dumps(breadcrumb, ensure_ascii=False)}</script>'
    )


def render_cluster_html(players: list[ClusterPlayerEntry]) -> str:
    """Cluster page の WP post.content として入る HTML を返す."""
    sections = [
        _build_intro_html(),
        _build_player_table_html(players),
        _build_footnote_html(len(players)),
        _build_jsonld(players),
    ]
    return "\n".join(s for s in sections if s)


def render_cluster_title() -> str:
    return "巨人選手データ - 全選手の打率・防御率・関連記事 一覧 | ヨシラバー"


__all__ = [
    "ClusterPlayerEntry",
    "render_cluster_html",
    "render_cluster_title",
    "CLUSTER_URL",
    "SITE_BASE",
]
