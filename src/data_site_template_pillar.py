"""Pillar page (per-player static page) template (data-site Phase 1.0 / ticket 444).

Pillar URL: yoshilover.com/data/{player-slug}/
内容: H1 + featured 写真 + (当日 / 直近5試合 / 月間 / season / vs他球団 / 関連player)
      data sections + 関連 Topic (既存記事) link block + Cluster back link
      + JSON-LD (SportsPlayer + Person + BreadcrumbList)

Phase 1.0 simplification:
- 当日試合 / vs 他球団 / 関連 player 比較 は insight.db 接続後に充実化 (本 phase は
  「データ準備中」 placeholder section にして、 構造だけ確立)
- 関連 Topic link は WP REST query で実取得
- featured_media は呼び出し元が attachment_id を渡す前提
"""

from __future__ import annotations

import html as _html
import json as _json
from dataclasses import dataclass, field


@dataclass
class PillarPlayerInfo:
    """1 Pillar page を作るのに必要な最小情報。"""

    name: str               # canonical 表記 (例: 吉川尚輝)
    slug: str               # URL slug (例: yoshikawa-naoki)
    position: str           # 内野手 / 外野手 / 投手 / 監督 / コーチ
    jersey_number: str      # 背番号 文字列 (例: "2" / "92")
    role: str = "player"    # player / manager / coach
    featured_image_url: str = ""   # H1 直下に出す写真 URL (空なら team mark)
    short_review: str = ""  # AI 短評 200-500 字 (空なら section omit)
    related_topic_links: list[tuple[str, str]] = field(default_factory=list)
    # related_topic_links = [(url, title), ...] (既存記事の link、 関連 Topic = Pillar → Topic)


CLUSTER_URL = "https://yoshilover.com/data/"
SITE_BASE = "https://yoshilover.com"


def _esc(text: str) -> str:
    """HTML escape helper (空文字 safe)。"""
    return _html.escape(str(text or ""), quote=True)


def _build_breadcrumb_html(name: str) -> str:
    """Pillar 上部の breadcrumb (Home → 選手データ → {player})。"""
    return (
        '<nav class="ys-breadcrumb" aria-label="breadcrumb" '
        'style="font-size:12px;color:#666;margin:0 0 12px;">'
        '<a href="https://yoshilover.com/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › '
        f'<span>{_esc(name)}</span>'
        '</nav>'
    )


def _build_featured_image_html(player: PillarPlayerInfo) -> str:
    if not player.featured_image_url:
        return ""
    return (
        '<div class="ys-pillar-featured" style="text-align:center;margin:0 0 16px;">'
        f'<img src="{_esc(player.featured_image_url)}" '
        f'alt="{_esc(player.name)}選手" '
        'style="max-width:480px;width:100%;height:auto;border-radius:8px;'
        'box-shadow:0 2px 6px rgba(0,0,0,0.1);" />'
        '</div>'
    )


def _build_short_review_html(player: PillarPlayerInfo) -> str:
    if not player.short_review:
        return ""
    return (
        '<section class="ys-pillar-review" '
        'style="background:#fff8e1;border-left:3px solid #f57f17;'
        'padding:12px 16px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:15px;margin:0 0 6px;color:#5d4037;">短評</h2>'
        f'<p style="font-size:13px;line-height:1.6;margin:0;">{_esc(player.short_review)}</p>'
        '</section>'
    )


def _build_data_placeholder_html() -> str:
    """Phase 1.0: insight.db 未接続のため placeholder section、 構造のみ確立。"""
    return (
        '<section class="ys-pillar-stats" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 10px;">直近5試合・月間・通算データ</h2>'
        '<p style="font-size:13px;color:#888;margin:0;">'
        'データ集計準備中 — 試合データの永続 baseline 表示は Phase 1.5 以降に追加予定。'
        '</p>'
        '</section>'
    )


def _build_related_topic_html(player: PillarPlayerInfo) -> str:
    if not player.related_topic_links:
        return (
            '<section class="ys-pillar-topics" '
            'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
            f'<h2 style="font-size:16px;margin:0 0 10px;">{_esc(player.name)} 関連記事</h2>'
            '<p style="font-size:13px;color:#888;margin:0;">関連記事準備中。</p>'
            '</section>'
        )
    items = "\n".join(
        f'<li style="margin:6px 0;"><a href="{_esc(url)}" style="color:#1976d2;text-decoration:none;">{_esc(title)}</a></li>'
        for url, title in player.related_topic_links[:20]
    )
    return (
        '<section class="ys-pillar-topics" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">{_esc(player.name)} 関連記事 ({len(player.related_topic_links)} 件)</h2>'
        f'<ul style="font-size:13px;line-height:1.7;margin:0;padding-left:20px;">{items}</ul>'
        '</section>'
    )


def _build_back_link_html() -> str:
    return (
        '<div class="ys-pillar-back" style="margin:24px 0 0;text-align:center;">'
        f'<a href="{CLUSTER_URL}" '
        'style="display:inline-block;padding:10px 24px;background:#ff6f00;color:#fff;'
        'text-decoration:none;border-radius:6px;font-size:14px;font-weight:600;">'
        '← 巨人選手データ 一覧に戻る</a>'
        '</div>'
    )


def _build_jsonld(player: PillarPlayerInfo) -> str:
    """SportsPlayer + Person + BreadcrumbList を組み合わせ JSON-LD 出力。"""
    canonical = f"{SITE_BASE}/data/{player.slug}/"
    sports_player = {
        "@context": "https://schema.org",
        "@type": "SportsPlayer",
        "name": player.name,
        "nationality": "JP" if player.role == "player" and "・" not in player.name else None,
        "memberOf": {
            "@type": "SportsTeam",
            "name": "読売ジャイアンツ",
            "url": "https://www.giants.jp/",
        },
        "jobTitle": _job_title_for(player),
        "url": canonical,
    }
    if player.featured_image_url:
        sports_player["image"] = player.featured_image_url
    # nationality None は出力前に除外 (schema 不要 key)
    sports_player = {k: v for k, v in sports_player.items() if v is not None}
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE_BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": "巨人選手データ", "item": CLUSTER_URL},
            {"@type": "ListItem", "position": 3, "name": player.name, "item": canonical},
        ],
    }
    return (
        f'<script type="application/ld+json">{_json.dumps(sports_player, ensure_ascii=False)}</script>\n'
        f'<script type="application/ld+json">{_json.dumps(breadcrumb, ensure_ascii=False)}</script>'
    )


def _job_title_for(player: PillarPlayerInfo) -> str:
    if player.role == "manager":
        return "監督"
    if player.role == "coach":
        return f"コーチ ({player.position})" if player.position else "コーチ"
    return f"プロ野球選手 ({player.position})" if player.position else "プロ野球選手"


def render_pillar_html(player: PillarPlayerInfo) -> str:
    """Pillar page の WP post.content として入る HTML を返す.

    WP page template は別途調整 (theme 側で <header>/<footer> 入る)、
    本関数は post.content (= 本文) のみ返す。
    """
    if not player.name or not player.slug:
        raise ValueError("PillarPlayerInfo.name and .slug are required")
    sections = [
        _build_breadcrumb_html(player.name),
        _build_featured_image_html(player),
        _build_short_review_html(player),
        _build_data_placeholder_html(),
        _build_related_topic_html(player),
        _build_back_link_html(),
        _build_jsonld(player),
    ]
    return "\n".join(s for s in sections if s)


def render_pillar_title(player: PillarPlayerInfo) -> str:
    """WP page.title = SEO 検索表示用。"""
    pos = f"（{player.position}・背番号{player.jersey_number}）" if player.position and player.jersey_number else ""
    return f"{player.name}{pos} データ - 直近成績・関連記事 | 巨人選手データ"


__all__ = [
    "PillarPlayerInfo",
    "render_pillar_html",
    "render_pillar_title",
    "CLUSTER_URL",
    "SITE_BASE",
]
