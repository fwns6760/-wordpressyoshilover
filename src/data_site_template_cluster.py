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


def _build_player_table_html(players: list[ClusterPlayerEntry]) -> str:
    if not players:
        return '<p style="font-size:13px;color:#888;margin:0;">対象選手データを準備中です。</p>'
    rows = []
    for p in players:
        pillar_url = f"/data/{p.slug}/"
        role_label = {"player": "選手", "manager": "監督", "coach": "コーチ"}.get(p.role, "選手")
        jersey = f"背番号 {p.jersey_number}" if p.jersey_number else "-"
        pos = p.position or "-"
        rows.append(
            f'<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:10px 12px;"><a href="{_esc(pillar_url)}" '
            'style="color:#1976d2;text-decoration:none;font-weight:600;">'
            f'{_esc(p.name)}</a></td>'
            f'<td style="padding:10px 12px;font-size:13px;color:#666;">{_esc(role_label)}</td>'
            f'<td style="padding:10px 12px;font-size:13px;color:#666;">{_esc(pos)}</td>'
            f'<td style="padding:10px 12px;font-size:13px;color:#666;">{_esc(jersey)}</td>'
            '</tr>'
        )
    return (
        '<section class="ys-cluster-table" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">選手一覧 ({len(players)} 名)</h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:14px;">'
        '<thead><tr style="background:#fafafa;text-align:left;">'
        '<th style="padding:10px 12px;">名前</th>'
        '<th style="padding:10px 12px;">役割</th>'
        '<th style="padding:10px 12px;">ポジション</th>'
        '<th style="padding:10px 12px;">背番号</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</section>'
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
