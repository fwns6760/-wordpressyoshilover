"""sns_realtime_topic_template — トレンド section + 一軍/二軍/三軍 + 出典 footer.

ticket 445: SNS リアルタイム話題 daily aggregation.

トレンド section は 急上昇 marker (Δ vs 昨日) と tag chip link を含む。
"""

from __future__ import annotations

import html as _html
from typing import Callable, Dict, List, Optional, Tuple

_CHIP_STYLE = (
    "display:inline-block;padding:6px 12px;margin:4px;"
    "background:#fff4e6;border:1px solid #ff6f00;border-radius:16px;"
    "color:#222;font-weight:600;font-size:14px;text-decoration:none;"
)


def _delta_badge(delta: int) -> str:
    if delta >= 5:
        return f' <span style="color:#d32f2f;font-weight:700;">↑+{delta}</span>'
    if delta >= 1:
        return f' <span style="color:#ff6f00;">↑+{delta}</span>'
    if delta < 0:
        return f' <span style="color:#999;">↓{delta}</span>'
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
    # 初日 (前日 counts なし) は ↑+N badge を全 chip に出すと「全員急上昇」 で
    # 見栄え微妙、 badge 自体を抑制する。
    suppress_badge = not prev
    chips: List[str] = []
    for name, count in items:
        safe = _html.escape(name)
        if suppress_badge:
            badge = ""
        else:
            delta = count - int(prev.get(name, 0))
            badge = _delta_badge(delta)
        inner = (
            f'#{safe} <span style="color:#ff6f00;">{count}</span>{badge}'
        )
        if tag_url_for:
            url = tag_url_for(name)
            chips.append(
                f'<a class="yoshilover-trend-chip" href="{_html.escape(url)}" '
                f'style="{_CHIP_STYLE}">{inner}</a>'
            )
        else:
            chips.append(
                f'<span class="yoshilover-trend-chip" style="{_CHIP_STYLE}">{inner}</span>'
            )
    sub = (
        ''
        if suppress_badge
        else '<p style="font-size:13px;color:#666;margin:0 0 8px 0;">'
             '↑ = 昨日比増加 (全 136 名 から自動検出)</p>\n'
    )
    return (
        '<!-- wp:html -->\n'
        '<h2>今日のトレンド</h2>\n'
        + sub
        + '<div class="yoshilover-trend-list" style="margin:16px 0;line-height:2.2;">'
        + "".join(chips)
        + '</div>\n'
        '<!-- /wp:html -->'
    )


def render_section(level_label: str, oembed_blocks: List[str]) -> str:
    if not oembed_blocks:
        return ""
    return f'<h2>{_html.escape(level_label)}</h2>\n' + "\n".join(oembed_blocks)


def render_sources_footer(handles: List[str], updated_at: str) -> str:
    handles_text = " / ".join(f"@{h}" for h in handles)
    return (
        '<h2>出典 / 更新</h2>\n'
        f'<p>source: {_html.escape(handles_text)}</p>\n'
        f'<p>更新: {_html.escape(updated_at)} JST '
        '(1 日 4 回 10/13/17/21 JST、 過去 24h の投稿を集約)</p>'
    )


def render_full_html(
    updated_at: str,
    trend_html: str,
    sections: List[Tuple[str, List[str]]],
    sources_handles: List[str],
) -> str:
    parts: List[str] = []
    if trend_html:
        parts.append(trend_html)
    for label, blocks in sections:
        s = render_section(label, blocks)
        if s:
            parts.append(s)
    parts.append(render_sources_footer(sources_handles, updated_at))
    return "\n\n".join(parts)
