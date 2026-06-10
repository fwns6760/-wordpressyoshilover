"""data/tickets page template (巨人 チケット情報・購入リンク集)。

スクレイプ系ではなく、公式・主要プレイガイドへの厳選リンク集 (user 指示「リンクで」)。
リンク先 URL は全て 200 を実取得して確認済み (2026-06-09)。
アフィリエイト等の第三者収益リンクは載せない。
"""
from __future__ import annotations

import html as _html

from src.data_site_internal_link import breadcrumb_jsonld
from src.data_site_related_links import related_data_links_html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"
SLUG = "tickets"

# (section_title, note, [(label, url, desc), ...])
_SECTIONS = [
    (
        "🟧 巨人公式で買う",
        "確実なのは公式。一軍・ファームの最新の発売日や席種・価格は公式ページが一次情報です。",
        [
            ("一軍チケット情報（公式）", "https://www.giants.jp/ticket/first-team/",
             "東京ドーム主催試合の席種・価格・発売スケジュール"),
            ("チケット購入ガイド（公式）", "https://www.giants.jp/guide/ticket/",
             "買い方・引換・QRチケットなど購入方法の総合案内"),
            ("ファーム（2軍）チケット（公式受付）",
             "https://w1.orange.onlineticket.jp/sf/giants-ticket/web/cg-yg-farm",
             "ジャイアンツ球場などファーム公式戦のチケット"),
            ("CLUB GIANTS（ファンクラブ・先行販売）", "https://www.giants.jp/G/G-Po/",
             "会員向けの先行販売・優先購入"),
        ],
    ),
    (
        "🎫 主要プレイガイドで探す",
        "公式が完売・対象外のときはプレイガイドも。各サイトで「巨人」「読売ジャイアンツ」で検索。",
        [
            ("チケットぴあ", "https://t.pia.jp/", "「巨人」で検索して対象試合を探す"),
            ("イープラス（e+）", "https://eplus.jp/", "プロ野球カテゴリ／キーワード検索"),
            ("楽天チケット", "https://ticket.rakuten.co.jp/", "楽天IDで購入・ポイント利用"),
        ],
    ),
    (
        "🏟 会場・観戦の情報",
        "座席表・アクセス・観戦ルールなど、行く前にチェック。",
        [
            ("東京ドーム 公式サイト", "https://www.tokyo-dome.co.jp/dome/",
             "座席表・アクセス・場内案内"),
            ("試合観戦契約約款（公式）", "https://www.giants.jp/misc/kansen-yakkan/",
             "持ち込み・撮影など観戦時のルール"),
        ],
    ),
]


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def render_tickets_title() -> str:
    return "巨人 チケット情報・購入リンク【公式・プレイガイドまとめ】 | 巨人データ"


def render_tickets_excerpt() -> str:
    return (
        "読売ジャイアンツ（巨人）のチケットを買うための公式・主要プレイガイドのリンクをまとめました。"
        "一軍・ファームの公式購入ページ、チケットぴあ・イープラス・楽天チケット、東京ドームの座席・"
        "観戦情報まで、巨人観戦の入口をワンページに。"
    )


def _link_card(label: str, url: str, desc: str) -> str:
    return (
        f'<a href="{_esc(url)}" target="_blank" rel="noopener nofollow" '
        'style="display:block;border:1px solid #e3e8ef;border-radius:10px;padding:12px 14px;'
        'margin:0 0 10px;text-decoration:none;background:#fff;">'
        f'<span style="display:block;font-size:15px;font-weight:800;color:#1565c0;">'
        f'{_esc(label)} <span style="font-size:11px;color:#999;font-weight:600;">↗</span></span>'
        f'<span style="display:block;font-size:12px;color:#666;margin-top:3px;line-height:1.6;">'
        f'{_esc(desc)}</span></a>'
    )


def _section(title: str, note: str, links: list) -> str:
    cards = "".join(_link_card(*l) for l in links)
    return (
        '<section style="margin:0 0 20px;">'
        f'<h2 style="font-size:17px;margin:0 0 4px;">{_esc(title)}</h2>'
        f'<p style="font-size:12px;color:#777;margin:0 0 10px;line-height:1.6;">{_esc(note)}</p>'
        f"{cards}</section>"
    )


def render_tickets_html() -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>チケット情報</span></nav>'
    )
    intro = (
        '<h1 style="font-size:21px;margin:0 0 4px;">巨人 チケット情報・購入リンク</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 14px;line-height:1.7;">'
        "読売ジャイアンツ（巨人）の試合チケットを買うための、公式・主要プレイガイドへのリンクをまとめました。"
        "発売日・席種・価格などの最新情報は各公式ページが一次情報です。リンクは新しいタブで開きます。</p>"
    )
    body = "".join(_section(t, n, l) for t, n, l in _SECTIONS)
    return (
        breadcrumb_jsonld("巨人 チケット情報", SLUG)
        + '<div style="font-family:sans-serif;max-width:760px;">'
        + intro
        + nav
        + body
        + '<p style="font-size:11px;color:#999;margin:6px 0 0;line-height:1.6;">'
        "※ リンク先は各公式・運営会社のサイトです。価格・在庫・発売状況は各サイトの最新情報をご確認ください。</p>"
        + related_data_links_html(SLUG)
        + "</div>"
    )


if __name__ == "__main__":
    import sys as _sys

    _sys.stdout.write(render_tickets_html())
