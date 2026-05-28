"""sns_realtime_topic_template — 巨人 SNS リアルタイム design template.

ticket 445: 巨人ブランド (黒 + オレンジ) + Yahoo リアルタイム式 UI。
- hero banner (gradient + ライブ更新中 pulse + stats)
- ranking trend chips (top 3 は gold / silver / bronze)
- feed card (oEmbed を Giants frame で包む)
- 出典 footer
"""

from __future__ import annotations

import html as _html
import json as _json
from typing import Callable, Dict, List, Optional, Tuple

# CSS 一式 (1 page = 1 inline <style>、 class prefix `ysn-` で theme conflict 回避)
_CSS = """
<style>
.ysn-wrap { font-family: -apple-system, "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif; max-width: 760px; margin: 0 auto; }
.ysn-hero { background: linear-gradient(135deg, #000 0%, #1a1a1a 55%, #FF6F00 100%); color: #fff; padding: 22px 20px; border-radius: 12px; margin: 16px 0 24px; position: relative; overflow: hidden; }
.ysn-hero::before { content: ""; position: absolute; top: -20px; right: -20px; width: 180px; height: 180px; background: rgba(255, 111, 0, 0.18); border-radius: 50%; }
.ysn-hero-badge { display: inline-block; background: #FF6F00; color: #000; font-weight: 900; padding: 4px 12px; border-radius: 4px; font-size: 13px; letter-spacing: 1px; }
.ysn-hero-title { font-size: 26px; margin: 8px 0 6px; color: #fff; font-weight: 800; line-height: 1.3; }
.ysn-hero-section { color: #FFB74D; font-size: 18px; margin-left: 4px; }
.ysn-hero-meta { font-size: 13px; opacity: 0.9; margin-top: 4px; }
.ysn-pulse { color: #FF1744; animation: ysn-pulse 1.4s infinite; font-size: 14px; vertical-align: middle; }
@keyframes ysn-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.25; } }
.ysn-live { font-weight: 700; color: #FFB74D; margin: 0 8px 0 4px; }
.ysn-updated { color: #ccc; }
.ysn-stats { display: flex; gap: 24px; margin-top: 14px; position: relative; z-index: 1; }
.ysn-stat { background: rgba(255,255,255,0.1); padding: 8px 14px; border-radius: 8px; backdrop-filter: blur(4px); }
.ysn-stat-num { font-size: 24px; font-weight: 800; color: #FFB74D; line-height: 1; }
.ysn-stat-label { display: block; font-size: 11px; opacity: 0.85; margin-top: 2px; }
.ysn-h2 { font-size: 18px; font-weight: 800; margin: 28px 0 12px; padding: 0 0 6px; border-bottom: 3px solid #FF6F00; color: #000; display: flex; align-items: center; gap: 8px; }
.ysn-h2-icon { font-size: 22px; }
.ysn-trend-sub { font-size: 12px; color: #666; margin: 0 0 12px; }
.ysn-chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 8px; }
.ysn-chip { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px 6px 6px; background: #fff4e6; border: 1.5px solid #FF6F00; border-radius: 28px; text-decoration: none; color: #000; font-weight: 600; font-size: 13px; transition: all 0.15s; }
.ysn-chip:hover { background: #FF6F00; color: #fff; transform: translateY(-1px); }
.ysn-chip:hover .ysn-rank { background: #fff; color: #FF6F00; }
.ysn-rank { background: #000; color: #fff; min-width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; padding: 0 4px; }
.ysn-chip-name { padding-left: 2px; }
.ysn-chip-count { color: #FF6F00; font-weight: 800; }
.ysn-chip-delta { font-size: 11px; }
.ysn-delta-hot { color: #d32f2f; font-weight: 800; }
.ysn-delta-up { color: #FF6F00; }
.ysn-delta-down { color: #999; }
.ysn-chip-1 { background: linear-gradient(135deg, #FFE082, #FFB300); border-color: #FF8F00; }
.ysn-chip-1 .ysn-rank { background: #B8860B; }
.ysn-chip-2 { background: linear-gradient(135deg, #ECEFF1, #B0BEC5); border-color: #78909C; }
.ysn-chip-2 .ysn-rank { background: #546E7A; }
.ysn-chip-3 { background: linear-gradient(135deg, #FFCCBC, #D4A373); border-color: #BF360C; }
.ysn-chip-3 .ysn-rank { background: #8D4925; }
.ysn-feed { margin-top: 8px; }
.ysn-card { background: #fff; border: 1px solid #e0e0e0; border-left: 4px solid #FF6F00; border-radius: 8px; padding: 4px 4px 0; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.ysn-card .yoshilover-x-embed { margin: 4px auto !important; }
.ysn-source { margin-top: 32px; padding: 16px; background: #f7f7f7; border-radius: 8px; font-size: 13px; color: #555; }
.ysn-source-title { font-weight: 700; color: #000; margin: 0 0 6px; }
.ysn-source-handles { display: flex; flex-wrap: wrap; gap: 8px; }
.ysn-source-handle { background: #fff; border: 1px solid #ddd; padding: 4px 10px; border-radius: 14px; font-size: 12px; color: #1da1f2; }
.ysn-source-foot { font-size: 11px; color: #888; margin-top: 8px; }
@media (max-width: 540px) {
  .ysn-hero-title { font-size: 22px; }
  .ysn-stats { gap: 12px; }
  .ysn-stat-num { font-size: 20px; }
}
</style>
""".strip()


def _delta_badge(delta: int) -> str:
    if delta >= 5:
        return f'<span class="ysn-chip-delta ysn-delta-hot">↑+{delta}</span>'
    if delta >= 1:
        return f'<span class="ysn-chip-delta ysn-delta-up">↑+{delta}</span>'
    if delta < 0:
        return f'<span class="ysn-chip-delta ysn-delta-down">↓{delta}</span>'
    return ""


def render_trend_chips(
    counts: Dict[str, int],
    prev_counts: Optional[Dict[str, int]] = None,
    tag_url_for: Optional[Callable[[str], str]] = None,
    min_count: int = 2,
    top_n: int = 15,
) -> str:
    items = [(n, c) for n, c in counts.items() if c >= min_count]
    items.sort(key=lambda t: (-t[1], t[0]))
    items = items[:top_n]
    if not items:
        return ""
    prev = prev_counts or {}
    suppress_badge = not prev
    chips: List[str] = []
    for rank, (name, count) in enumerate(items, 1):
        safe = _html.escape(name)
        rank_class = f"ysn-chip-{rank}" if rank <= 3 else ""
        if suppress_badge:
            badge = ""
        else:
            delta = count - int(prev.get(name, 0))
            badge = _delta_badge(delta)
        inner = (
            f'<span class="ysn-rank">{rank}</span>'
            f'<span class="ysn-chip-name">#{safe}</span>'
            f'<span class="ysn-chip-count">{count}</span>'
            f'{badge}'
        )
        if tag_url_for:
            url = tag_url_for(name)
            chips.append(
                f'<a class="ysn-chip {rank_class}" href="{_html.escape(url)}">{inner}</a>'
            )
        else:
            chips.append(f'<span class="ysn-chip {rank_class}">{inner}</span>')
    sub = (
        ''
        if suppress_badge
        else '<p class="ysn-trend-sub">↑ = 昨日比増加 / 全 136 名 (選手 + 監督 + コーチ) から自動検出</p>'
    )
    return (
        '<section class="ysn-trend-section">\n'
        '  <h2 class="ysn-h2"><span class="ysn-h2-icon">🔥</span>今日のトレンド</h2>\n'
        + sub + '\n'
        '  <div class="ysn-chips">' + "".join(chips) + '</div>\n'
        '</section>'
    )


def render_section(level_label: str, oembed_blocks: List[str]) -> str:
    if not oembed_blocks:
        return ""
    icon = {"最新の投稿": "📱", "二軍": "⚾", "三軍": "🌱"}.get(level_label, "📱")
    cards = "\n".join(f'<div class="ysn-card">{b}</div>' for b in oembed_blocks)
    return (
        '<section class="ysn-feed">\n'
        f'  <h2 class="ysn-h2"><span class="ysn-h2-icon">{icon}</span>{_html.escape(level_label)}</h2>\n'
        f'{cards}\n'
        '</section>'
    )


def render_hero(
    page_label: str,
    updated_at: str,
    stats: Dict[str, int],
) -> str:
    posts = stats.get("posts", 0)
    trend = stats.get("trend", 0)
    return (
        '<div class="ysn-hero">\n'
        '  <div class="ysn-hero-badge">⚾ 巨人</div>\n'
        f'  <h1 class="ysn-hero-title">SNS リアルタイム'
        f'<span class="ysn-hero-section">{_html.escape(page_label)}</span></h1>\n'
        '  <div class="ysn-hero-meta">\n'
        '    <span class="ysn-pulse">●</span><span class="ysn-live">LIVE</span>\n'
        f'    <span class="ysn-updated">最終更新 {_html.escape(updated_at)} JST '
        '(10/13/17/21 JST 更新)</span>\n'
        '  </div>\n'
        '  <div class="ysn-stats">\n'
        f'    <div class="ysn-stat"><span class="ysn-stat-num">{posts}</span>'
        '<span class="ysn-stat-label">投稿/24h</span></div>\n'
        f'    <div class="ysn-stat"><span class="ysn-stat-num">{trend}</span>'
        '<span class="ysn-stat-label">話題の選手</span></div>\n'
        '  </div>\n'
        '</div>'
    )


def render_sources_footer(handles: List[str], updated_at: str) -> str:
    chips = "".join(
        f'<span class="ysn-source-handle">@{_html.escape(h)}</span>' for h in handles
    )
    return (
        '<aside class="ysn-source">\n'
        '  <p class="ysn-source-title">📡 出典 X アカウント</p>\n'
        f'  <div class="ysn-source-handles">{chips}</div>\n'
        f'  <p class="ysn-source-foot">最終更新 {_html.escape(updated_at)} JST。 過去 24h の投稿を集約、 1 日 4 回 (10/13/17/21 JST) 自動更新。</p>\n'
        '</aside>'
    )


def render_jsonld(
    page_label: str,
    page_url: str,
    updated_at_iso: str,
    posts_for_listing: List[Dict],
) -> str:
    """CollectionPage + ItemList(SocialMediaPosting) + BreadcrumbList + about:SportsTeam.

    posts_for_listing: [{url, handle}]
    updated_at_iso: ISO 8601 (e.g., 2026-05-28T17:00:00+09:00)
    """
    items = []
    for i, post in enumerate(posts_for_listing[:20], 1):
        url = post.get("url", "")
        handle = post.get("handle", "")
        if not url:
            continue
        items.append(
            {
                "@type": "ListItem",
                "position": i,
                "item": {
                    "@type": "SocialMediaPosting",
                    "url": url,
                    "author": {
                        "@type": "Organization",
                        "name": handle,
                        "url": f"https://twitter.com/{handle}",
                    },
                },
            }
        )

    collection_page = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"巨人 SNS リアルタイム {page_label}",
        "description": (
            f"巨人専門 X 公式アカウントの過去 24 時間投稿を集約 {page_label}。"
            " 1 日 4 回 (10/13/17/21 JST) 自動更新。"
        ),
        "url": page_url,
        "datePublished": updated_at_iso,
        "dateModified": updated_at_iso,
        "inLanguage": "ja",
        "isPartOf": {
            "@type": "WebSite",
            "name": "ヨシラバー",
            "url": "https://yoshilover.com/",
        },
        "about": {
            "@type": "SportsTeam",
            "name": "読売ジャイアンツ",
            "sport": "Baseball",
            "url": "https://www.giants.jp/",
        },
        "publisher": {
            "@type": "Organization",
            "name": "ヨシラバー",
            "url": "https://yoshilover.com/",
        },
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(items),
            "itemListElement": items,
        },
    }

    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "ヨシラバー",
                "item": "https://yoshilover.com/",
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": f"巨人 SNS リアルタイム {page_label}",
                "item": page_url,
            },
        ],
    }

    return (
        '<script type="application/ld+json">'
        + _json.dumps(collection_page, ensure_ascii=False, separators=(",", ":"))
        + '</script>\n'
        '<script type="application/ld+json">'
        + _json.dumps(breadcrumb, ensure_ascii=False, separators=(",", ":"))
        + '</script>'
    )


def render_page_html(
    page_label: str,
    updated_at: str,
    stats: Dict[str, int],
    trend_html: str,
    sections: List[Tuple[str, List[str]]],
    sources_handles: List[str],
    page_url: str = "",
    updated_at_iso: str = "",
    posts_for_listing: Optional[List[Dict]] = None,
) -> str:
    parts = [_CSS]
    if page_url and updated_at_iso:
        parts.append(render_jsonld(page_label, page_url, updated_at_iso, posts_for_listing or []))
    parts.append('<div class="ysn-wrap">')
    parts.append(render_hero(page_label, updated_at, stats))
    if trend_html:
        parts.append(trend_html)
    for label, blocks in sections:
        s = render_section(label, blocks)
        if s:
            parts.append(s)
    parts.append(render_sources_footer(sources_handles, updated_at))
    parts.append('</div>')
    return "\n\n".join(parts)


# 旧 API 後方互換 (build_pages から呼ばれる)
def render_full_html(
    updated_at: str,
    trend_html: str,
    sections: List[Tuple[str, List[str]]],
    sources_handles: List[str],
    page_label: str = "",
    stats: Optional[Dict[str, int]] = None,
    page_url: str = "",
    updated_at_iso: str = "",
    posts_for_listing: Optional[List[Dict]] = None,
) -> str:
    return render_page_html(
        page_label or "",
        updated_at,
        stats or {},
        trend_html,
        sections,
        sources_handles,
        page_url=page_url,
        updated_at_iso=updated_at_iso,
        posts_for_listing=posts_for_listing,
    )
