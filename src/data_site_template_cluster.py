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
    # NPB 公式由来の登録ポジション区分 (投手/捕手/内野手/外野手)。 支配下選手の
    # 4 表分割に使う (roster.position は stale なため不使用)。 staff は空。
    position_group: str = ""
    # staff (監督・コーチ) の 軍 level (一軍/二軍/三軍/巡回)。 player は空。
    military: str = ""
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


def _build_search_html() -> str:
    """460: 選手名インクリメンタル検索 box (client-side、 progressive enhancement)。

    全テーブル (打者/投手/監督コーチ/育成/OB) の選手リンク行を選手名で絞り込む。
    JS が無効/未対応でも全リストはそのまま表示される (劣化しない)。
    検索対象は ``section[class*="ys-cluster"][class*="-table"]`` 内の ``/data/`` リンク
    のみ (intro のナビ link は対象外)。
    """
    return (
        '<section class="ys-cluster-search" '
        'style="margin:0 0 18px;">'
        '<input type="search" id="ys-player-search" autocomplete="off" '
        'placeholder="🔍 選手名で検索（例: 戸郷 / 坂本 / 岡本）" '
        'style="width:100%;box-sizing:border-box;padding:12px 14px;font-size:15px;'
        'border:2px solid #ffd9bf;border-radius:10px;outline:none;color:#1a1a1a;" '
        'aria-label="選手名で検索">'
        '<p id="ys-search-empty" hidden '
        'style="font-size:13px;color:#888;margin:8px 2px 0;">該当する選手が見つかりません。</p>'
        '</section>'
        '<script>(function(){'
        'var box=document.getElementById("ys-player-search");if(!box)return;'
        'var empty=document.getElementById("ys-search-empty");'
        'var links=[].slice.call(document.querySelectorAll('
        '\'section[class*="ys-cluster"][class*="-table"] a[href^="/data/"]\'));'
        'var items=links.map(function(a){'
        'var row=a.closest("tr")||a;'
        'return{el:row,nm:(row.textContent||"").replace(/\\s+/g,"")};});'
        'function norm(s){return(s||"").replace(/\\s+/g,"");}'
        'box.addEventListener("input",function(){'
        'var q=norm(this.value);var vis=0;'
        'items.forEach(function(it){'
        'var hit=!q||it.nm.indexOf(q)>=0;'
        'it.el.style.display=hit?"":"none";if(hit)vis++;});'
        'if(empty)empty.hidden=!(q&&vis===0);});'
        '})();</script>'
    )


def _build_intro_html() -> str:
    return (
        '<section class="ys-cluster-intro" '
        'style="background:#fff8e1;border-left:3px solid #f57f17;'
        'padding:14px 18px;margin:0 0 20px;border-radius:4px;">'
        '<h2 style="font-size:17px;margin:0 0 10px;color:#5d4037;">巨人選手データ</h2>'
        '<p style="font-size:13px;line-height:1.7;margin:0;color:#444;">'
        '読売ジャイアンツの 1 軍・2 軍 active 選手の永続データページ集です。 '
        '各選手の打率・防御率・直近 5 試合・関連記事を、 毎朝 6 時に最新化しています。'
        '</p>'
        '<p style="font-size:13px;margin:10px 0 0;">'
        '<a href="/data/ranking/" style="color:#e25400;font-weight:600;text-decoration:none;">🏆 選手ランキング</a>'
        '　/　'
        '<a href="/data/team/" style="color:#e25400;font-weight:600;text-decoration:none;">📊 チーム成績・順位</a>'
        '　/　'
        '<a href="/data/record/" style="color:#e25400;font-weight:600;text-decoration:none;">🏛 記録室</a>'
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


def _is_staff_entry(p: ClusterPlayerEntry) -> bool:
    """監督 / コーチ entry (野手・投手 表から除外、 staff 表へ)。"""
    return (p.role or "").strip() in ("manager", "coach")


def _group_of(p: ClusterPlayerEntry) -> str:
    """entry の登録ポジション区分。 position_group 優先、 無ければ position から推定。"""
    if p.position_group:
        return p.position_group
    pos = (p.position or "").strip()
    if pos in ("投手", "捕手", "内野手", "外野手"):
        return pos
    # 旧 "打者" 等の汎用値や空は内野手扱いに寄せる (production では position_group が必ず入る)
    return "内野手"


def _build_batter_group_table_html(players: list[ClusterPlayerEntry], group: str, css: str) -> str:
    """捕手 / 内野手 / 外野手 の登録区分別 table (打撃列)。 背番号順。"""
    members = [p for p in players if not _is_staff_entry(p) and _group_of(p) == group]
    if not members:
        return ""
    sorted_players = sorted(members, key=_jersey_sort_key)
    rows = []
    for p in sorted_players:
        pillar_url = f"/data/{p.slug}/"
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
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{games}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{hits}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#1976d2;font-weight:600;">{avg}</td>'
            f'<td style="padding:8px 10px;text-align:center;color:#555;">{rbi}</td>'
            '</tr>'
        )
    return (
        f'<section class="ys-cluster-{css}-table" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">{group} 一覧 ({len(sorted_players)} 名 / 背番号順)</h2>'
        '<div style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:left;">'
        '<th style="padding:10px;text-align:center;">背番号</th>'
        '<th style="padding:10px;">名前</th>'
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
    """投手 (登録区分=投手、 staff 除く) のみ含む table。 背番号順。"""
    pitchers = [p for p in players if not _is_staff_entry(p) and _group_of(p) == "投手"]
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


_MILITARY_ORDER = ("一軍", "二軍", "三軍", "巡回")


def _build_staff_table_html(players: list[ClusterPlayerEntry]) -> str:
    """監督・コーチ 一覧 table。 軍 (一軍/二軍/三軍/巡回) で小見出し分け、 役職 + name link。"""
    staff = [p for p in players if _is_staff_entry(p)]
    if not staff:
        return ""
    by_mil: dict[str, list[ClusterPlayerEntry]] = {}
    for p in staff:
        by_mil.setdefault(p.military or "一軍", []).append(p)
    blocks = []
    for mil in _MILITARY_ORDER:
        members = by_mil.get(mil)
        if not members:
            continue
        members_sorted = sorted(
            members,
            key=lambda p: (0 if (p.role or "") == "manager" else 1,) + _jersey_sort_key(p),
        )
        rows = []
        for p in members_sorted:
            pillar_url = f"/data/{p.slug}/"
            jersey = p.jersey_number or "-"
            pos = p.position or ("監督" if (p.role or "") == "manager" else "コーチ")
            rows.append(
                f'<tr style="border-bottom:1px solid #eee;">'
                f'<td style="padding:8px 10px;text-align:center;color:#555;font-weight:600;">{_esc(jersey)}</td>'
                f'<td style="padding:8px 10px;"><a href="{_esc(pillar_url)}" '
                'style="color:#1976d2;text-decoration:none;font-weight:600;">'
                f'{_esc(p.name)}</a></td>'
                f'<td style="padding:8px 10px;font-size:13px;color:#666;">{_esc(pos)}</td>'
                '</tr>'
            )
        blocks.append(
            f'<h3 style="font-size:14px;margin:14px 0 6px;color:#5d4037;">{mil} ({len(members_sorted)} 名)</h3>'
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="background:#fafafa;text-align:left;">'
            '<th style="padding:8px 10px;text-align:center;">背番号</th>'
            '<th style="padding:8px 10px;">名前</th>'
            '<th style="padding:8px 10px;">役職</th>'
            '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
        )
    return (
        '<section class="ys-cluster-staff-table" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 4px;">監督・コーチ 一覧 ({len(staff)} 名)</h2>'
        '<div style="overflow-x:auto;">'
        f'{"".join(blocks)}'
        '</div></section>'
    )


def _build_ikusei_table_html(ikusei_entries: list[tuple[str, str]]) -> str:
    """育成選手 一覧 table (氏名 + ポジション)。 個別ページは作らないため link なし。"""
    if not ikusei_entries:
        return ""
    rows = []
    for name, pos in ikusei_entries:
        rows.append(
            f'<tr style="border-bottom:1px solid #eee;">'
            f'<td style="padding:8px 10px;font-weight:600;color:#5d4037;">{_esc(name)}</td>'
            f'<td style="padding:8px 10px;font-size:13px;color:#666;">{_esc(pos)}</td>'
            '</tr>'
        )
    return (
        '<section class="ys-cluster-ikusei-table" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">育成選手 一覧 ({len(ikusei_entries)} 名)</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 10px;">支配下登録選手とは別枠の育成契約選手。 '
        '一軍出場記録が積み上がり次第、 個別データページを追加予定。</p>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:left;">'
        '<th style="padding:10px;">名前</th>'
        '<th style="padding:10px;">ポジション</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table></section>'
    )


def _build_ob_table_html(ob_entries: list[tuple[str, str]]) -> str:
    """OB・レジェンド: トップに全名を並べず、 50音 名鑑 (/data/legends/) への導線カードにする。

    686名を /data に直貼りすると一覧性が崩れる (見づらい) ため、 トップは「歴代在籍選手名鑑」
    への入口に集約し、 ブラウズ・通算成績は 50音 名鑑側へ誘導する。
    """
    if not ob_entries:
        return ""
    n = len(ob_entries)
    return (
        '<section class="ys-cluster-ob-table" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 20px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">歴代在籍選手名鑑 ({n} 名)</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 12px;">読売ジャイアンツ歴代の名選手を50音で一覧。 '
        '打者は打率・出塁率・OPS、 投手は防御率・WHIP まで通算成績を掲載しています。</p>'
        '<a href="/data/legends/" '
        'style="display:block;text-align:center;padding:14px;background:#e65100;color:#fff;'
        'border-radius:6px;text-decoration:none;font-size:15px;font-weight:700;">'
        f'🎖 歴代在籍選手 通算成績名鑑(50音)で {n} 名を見る →</a>'
        '</section>'
    )


def _build_player_table_html(
    players: list[ClusterPlayerEntry],
    ikusei_entries: list[tuple[str, str]] | None = None,
    ob_entries: list[tuple[str, str]] | None = None,
) -> str:
    """支配下 4 区分 (投手/捕手/内野手/外野手) + 育成枠 + 監督・コーチ + OB に分離。"""
    if not players and not ikusei_entries and not ob_entries:
        return '<p style="font-size:13px;color:#888;margin:0;">対象選手データを準備中です。</p>'
    return (
        _build_pitcher_table_html(players)
        + "\n"
        + _build_batter_group_table_html(players, "捕手", "catcher")
        + "\n"
        + _build_batter_group_table_html(players, "内野手", "infielder")
        + "\n"
        + _build_batter_group_table_html(players, "外野手", "outfielder")
        + "\n"
        + _build_ikusei_table_html(ikusei_entries or [])
        + "\n"
        + _build_staff_table_html(players)
        + "\n"
        + _build_ob_table_html(ob_entries or [])
        + '<p style="font-size:11px;color:#999;margin:8px 0 0;">'
        '※ stats は insight.db (NPB official box score 由来)、 毎朝 6:00 + 試合後 17:30 / 23:00 JST 更新。 「-」 はデータ集計中。'
        '</p>'
    )


def _build_footnote_html(players_count: int) -> str:
    return (
        '<section class="ys-cluster-footnote" style="font-size:12px;color:#888;margin:24px 0 0;">'
        f'<p style="margin:0;">読売ジャイアンツの支配下選手・監督・コーチ {players_count} 名分の'
        '個別データページを公開中です（育成選手は一覧のみ、 一軍出場後に個別ページ追加予定）。</p>'
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


def _build_hot_html(hot: dict | None) -> str:
    """今日の注目 (直近5試合HOT、 460)。 server-rendered (JS不要・WP安全)。"""
    b = (hot or {}).get("batter") or []
    p = (hot or {}).get("pitcher") or []
    if not b and not p:
        return ""
    from src.data_site_slug import player_slug  # lazy import (循環回避)

    def _line(name, disp, rk, tot):
        try:
            href = f"/data/{player_slug(name)}/"
        except Exception:  # noqa: BLE001
            href = ""
        nm = (f'<a href="{href}" style="color:#1a1a1a;text-decoration:none;font-weight:600;">{_esc(name)}</a>'
              if href else f'<strong>{_esc(name)}</strong>')
        rks = f'<span style="color:#888;font-size:12px;">（リーグ{rk}位）</span>' if rk else ""
        return f'<li style="padding:5px 0;border-bottom:1px solid #fff0e6;">{nm} {_esc(disp)} {rks}</li>'

    items = "".join(_line(*x) for x in (b + p))
    return (
        '<section style="background:#fff8f2;border:1px solid #ffd9bf;border-radius:12px;padding:14px;margin:0 0 16px;">'
        '<h2 style="font-size:16px;margin:0 0 6px;color:#e25400;">📈 直近5試合の注目選手</h2>'
        '<p style="font-size:12px;color:#777;margin:0 0 8px;">毎朝更新。 今ホットな巨人の選手。</p>'
        f'<ul style="list-style:none;padding:0;margin:0;font-size:14px;">{items}</ul>'
        '</section>'
    )


def render_cluster_html(
    players: list[ClusterPlayerEntry],
    ikusei_entries: list[tuple[str, str]] | None = None,
    ob_entries: list[tuple[str, str]] | None = None,
    hot: dict | None = None,
) -> str:
    """Cluster page の WP post.content として入る HTML を返す.

    players = 支配下選手 + 監督・コーチ (個別ページあり)。 ikusei_entries =
    育成選手 [(name, position)] (育成枠の一覧のみ、 個別ページなし)。 ob_entries =
    OB・レジェンド [(slug, name)] (個別 profile ページあり)。
    """
    sections = [
        _build_intro_html(),
        _build_search_html(),
        _build_hot_html(hot),
        _build_player_table_html(players, ikusei_entries, ob_entries),
        _build_footnote_html(len(players)),
        _build_jsonld(players),
    ]
    return "\n".join(s for s in sections if s)


# SEO long-tail 用シーズン表記。 毎シーズンこの 1 行を置換するだけ。
# data_site_template_pillar.SEASON_LABEL と同期すること。
SEASON_LABEL = "2026年"


def render_cluster_title() -> str:
    # 「巨人 2026 選手 打率」 等の long-tail を拾うためシーズン年を前寄せ。
    return f"巨人選手データ {SEASON_LABEL} - 全選手の打率・防御率・成績一覧 | ヨシラバー"


__all__ = [
    "ClusterPlayerEntry",
    "render_cluster_html",
    "render_cluster_title",
    "CLUSTER_URL",
    "SITE_BASE",
]
