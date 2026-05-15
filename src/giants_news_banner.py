"""赤紫グラデの GIANTS NEWS DIGEST banner を 1 か所で emit する helper.

公開済 post の content 先頭に置く「📰 出典 / ⚾ KICKER / タイトル」の
グラデ block を全 article-build 経路で同一の HTML として吐くため、
5 経路 (build_news_block 本線 / digest 置換 / oembed passthrough /
非 X URL passthrough / data_post_generator) が本 module の
``giants_news_banner_html`` を呼ぶ。

byte-for-byte 互換 (元の rss_fetcher.py:17557-17568 と同一の出力) を
unit test で保証している。挙動を変えるな (HTML diff = post 全件に影響)。
"""

from __future__ import annotations


_KICKER_BY_CATEGORY: dict[str, str] = {
    "試合速報": "GIANTS GAME NOTE",
    "選手情報": "GIANTS PLAYER WATCH",
    "首脳陣": "GIANTS MANAGER NOTE",
    "補強・移籍": "GIANTS ROSTER WATCH",
    "球団情報": "GIANTS FRONT NOTE",
    "ドラフト・育成": "GIANTS FARM WATCH",
    "OB・解説者": "GIANTS VOICE CHECK",
}


def summary_kicker(category: str) -> str:
    """Banner ⚾ アイコン直後に出す KICKER ラベル。

    category が mapping に無ければ ``GIANTS NEWS DIGEST``。
    """
    return _KICKER_BY_CATEGORY.get(category or "", "GIANTS NEWS DIGEST")


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def giants_news_banner_html(
    title: str,
    source_label: str,
    category: str,
) -> str:
    """赤紫グラデ banner を Gutenberg wp:html block として返す。

    ``source_label`` は既に joined / sanitize 済の文字列を想定
    (多 source の場合は呼び出し側で `' / '` で連結してから渡す)。
    空文字なら ``スポーツニュース`` で fallback。
    """
    safe_title = _esc(title)
    safe_source = _esc(source_label) if source_label else "スポーツニュース"
    kicker = summary_kicker(category)
    return (
        '<!-- wp:html -->\n'
        '<div style="background:linear-gradient(135deg,#001e62 0%,#e8272a 100%);border-radius:10px;padding:18px 20px;margin:0 0 4px 0;">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        f'<span style="background:rgba(255,255,255,0.2);color:#fff;font-size:0.78em;font-weight:800;padding:4px 10px;border-radius:20px;letter-spacing:0.05em;">📰 {safe_source}</span>'
        f'<span style="color:rgba(255,255,255,0.82);font-size:0.72em;font-weight:700;letter-spacing:0.08em;">⚾ {kicker}</span>'
        '</div>'
        f'<div style="color:#fff;font-size:1.1em;font-weight:900;line-height:1.4;">{safe_title}</div>'
        '</div>\n'
        '<!-- /wp:html -->\n\n'
    )


__all__ = ["summary_kicker", "giants_news_banner_html"]
