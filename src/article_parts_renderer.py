from __future__ import annotations

from html import escape
from typing import Literal, NotRequired, TypedDict


class SourceAttribution(TypedDict):
    source_name: str
    source_url: str


class ArticlePartsBase(TypedDict):
    title: str
    fact_lead: str
    body_core: list[str]
    game_context: str
    source_attribution: SourceAttribution


class ArticleParts(ArticlePartsBase, total=False):
    fan_view: NotRequired[str | None]


def _escape_text(value: str | None) -> str:
    return escape((value or "").strip(), quote=False)


def _paragraph(text: str | None) -> str:
    safe = _escape_text(text)
    if not safe:
        return ""
    return f"<!-- wp:paragraph -->\n<p>{safe}</p>\n<!-- /wp:paragraph -->\n\n"


def _heading(level: int, text: str) -> str:
    safe = _escape_text(text)
    return (
        f'<!-- wp:heading {{"level":{level}}} -->\n'
        f"<h{level}>{safe}</h{level}>\n"
        f"<!-- /wp:heading -->\n\n"
    )


def _source_block(parts: ArticleParts) -> str:
    attribution = parts["source_attribution"]
    source_name = _escape_text(attribution.get("source_name") or "スポーツニュース")
    title = _escape_text(parts["title"])
    source_url = escape((attribution.get("source_url") or "").strip(), quote=True)
    link_html = ""
    if source_url:
        link_html = (
            '<div style="margin-top:10px;">'
            f'<a href="{source_url}" style="color:#fff;font-size:0.84em;font-weight:700;text-decoration:underline;" '
            'target="_blank" rel="noopener noreferrer">記事元を読む</a>'
            "</div>"
        )
    return (
        "<!-- wp:html -->\n"
        '<div class="yoshilover-article-source" '
        'style="background:linear-gradient(135deg,#001e62 0%,#e8272a 100%);border-radius:10px;padding:18px 20px;margin:0 0 16px 0;">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        '<span style="background:rgba(255,255,255,0.2);color:#fff;font-size:0.78em;font-weight:800;padding:4px 10px;border-radius:20px;letter-spacing:0.05em;">'
        f"📰 {source_name}"
        "</span>"
        '<span style="color:rgba(255,255,255,0.82);font-size:0.72em;font-weight:700;letter-spacing:0.08em;">⚾ POSTGAME</span>'
        "</div>"
        f'<div style="color:#fff;font-size:1.1em;font-weight:900;line-height:1.4;">{title}</div>'
        f"{link_html}"
        "</div>\n"
        "<!-- /wp:html -->\n\n"
    )


def render_postgame(parts: ArticleParts) -> str:
    html_parts = [
        _source_block(parts),
        _paragraph(parts["fact_lead"]),
        _heading(2, "試合概要"),
    ]

    for paragraph in parts["body_core"]:
        rendered = _paragraph(paragraph)
        if rendered:
            html_parts.append(rendered)

    html_parts.extend(
        [
            _heading(2, "試合展開"),
            _paragraph(parts["game_context"]),
        ]
    )

    fan_view = parts.get("fan_view")
    if fan_view:
        html_parts.append(_paragraph(fan_view))

    return "".join(html_parts)


def render_article_parts(parts: ArticleParts, subtype: Literal["postgame"]) -> str:
    if subtype != "postgame":
        raise ValueError(f"unsupported subtype: {subtype}")
    return render_postgame(parts)
