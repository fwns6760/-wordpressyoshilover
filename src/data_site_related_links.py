"""データページ共通の内部リンク (関連データ) + 構造化データ helper。

巨人データの feature ページ (rotation / open-games / roster-moves / tickets) が
相互リンクと Dataset 構造化データを共有するための小モジュール。
"""
from __future__ import annotations

import html as _html
import json as _json

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data"

# (slug, label) — データサイトの主要ページ。内部リンク網の核。
_DATA_PAGES = [
    ("rotation", "先発ローテーション成績"),
    ("open-games", "オープン戦成績"),
    ("roster-moves", "出場選手登録・抹消"),
    ("batting-ranking", "打撃成績ランキング"),
    ("pitching-ranking", "投手成績ランキング"),
    ("team", "セ・リーグ順位表"),
    ("jersey-numbers", "歴代背番号"),
    ("draft", "歴代ドラフト"),
    ("tickets", "チケット情報"),
]


def _esc(t) -> str:
    return _html.escape(str(t if t is not None else ""), quote=True)


def related_data_links_html(current_slug: str) -> str:
    """「関連データ」内部リンクブロック (current ページ自身は除外)。"""
    chips = [
        f'<a href="/data" style="display:inline-block;padding:6px 12px;margin:3px;'
        'border:1px solid #cfe0f5;border-radius:16px;background:#f4f8fe;color:#1565c0;'
        'text-decoration:none;font-size:13px;font-weight:700;">📊 巨人選手データ一覧</a>'
    ]
    for slug, label in _DATA_PAGES:
        if slug == current_slug:
            continue
        chips.append(
            f'<a href="/data/{_esc(slug)}" style="display:inline-block;padding:6px 12px;margin:3px;'
            'border:1px solid #e3e8ef;border-radius:16px;background:#fff;color:#1f5aa8;'
            f'text-decoration:none;font-size:13px;font-weight:600;">{_esc(label)}</a>'
        )
    return (
        '<section style="margin:26px 0 0;padding:14px;border-top:2px solid #eef0f3;">'
        '<h2 style="font-size:15px;margin:0 0 8px;color:#333;">関連する巨人データ</h2>'
        '<div>' + "".join(chips) + "</div></section>"
    )


def dataset_jsonld(*, name: str, description: str, slug: str,
                   temporal: str = "", keywords: list[str] | None = None) -> str:
    """Dataset 構造化データ (JSON-LD)。Google データセット検索の対象になり得る。"""
    data = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": name,
        "description": description,
        "url": f"{CLUSTER_URL}/{slug}",
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "ヨシラバー", "url": SITE_BASE + "/"},
        "about": {"@type": "SportsTeam", "name": "読売ジャイアンツ"},
        "inLanguage": "ja",
    }
    if temporal:
        data["temporalCoverage"] = temporal
    if keywords:
        data["keywords"] = keywords
    return (
        '<script type="application/ld+json">'
        + _json.dumps(data, ensure_ascii=False)
        + "</script>"
    )
