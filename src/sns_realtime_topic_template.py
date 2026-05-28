"""sns_realtime_topic_template — トレンド section + 一軍/二軍/三軍 section + 出典 footer.

ticket 445: SNS リアルタイム話題 daily aggregation.
"""

from __future__ import annotations

import html as _html
from typing import Dict, List, Tuple


def render_trend_chips(counts: Dict[str, int], min_count: int = 2, top_n: int = 15) -> str:
    items = [(n, c) for n, c in counts.items() if c >= min_count]
    items.sort(key=lambda t: (-t[1], t[0]))
    items = items[:top_n]
    if not items:
        return ""
    chips: List[str] = []
    for name, count in items:
        safe = _html.escape(name)
        chips.append(
            '<span class="yoshilover-trend-chip" '
            'style="display:inline-block;padding:6px 12px;margin:4px;'
            'background:#fff4e6;border:1px solid #ff6f00;border-radius:16px;'
            'color:#222;font-weight:600;font-size:14px;">'
            f'#{safe} <span style="color:#ff6f00;">{count}</span>'
            '</span>'
        )
    return (
        '<!-- wp:html -->\n'
        '<h2>今日のトレンド</h2>\n'
        '<div class="yoshilover-trend-list" style="margin:16px 0;line-height:2.2;">'
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
        '(1 日 4 回 10/13/17/21 JST、過去 24h の投稿を集約)</p>'
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
