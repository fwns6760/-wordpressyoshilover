"""data/team ページ template (球団成績・セ内順位、Phase B 452)。

セ・リーグ6球団の 打率/防御率/本塁打 ランキングを巨人ハイライトで表示。
検証済み team_ranking_publisher の集計を data_site_query.fetch_team_rankings 経由で利用。
SEO: 「巨人 球団打率 順位」「セ・リーグ 防御率 ランキング」等。
"""

from __future__ import annotations

import html as _html

SITE_BASE = "https://yoshilover.com"
CLUSTER_URL = "https://yoshilover.com/data/"
_METRIC_ORDER = ["打率", "本塁打", "防御率"]


def _esc(t: str) -> str:
    return _html.escape(str(t or ""), quote=True)


def render_team_title() -> str:
    return "巨人 球団成績・セ・リーグ順位 2026【打率・防御率・本塁打】 | 巨人データ"


def render_team_excerpt(rankings: dict) -> str:
    parts = []
    for m in _METRIC_ORDER:
        for tj, disp, rk, is_g in rankings.get(m, []):
            if is_g:
                parts.append(f"{m}セ{rk}位")
                break
    head = "・".join(parts) if parts else "球団成績"
    return (f"読売ジャイアンツ2026の球団成績とセ・リーグ内順位。{head}。"
            "打率・本塁打・防御率を6球団で比較した巨人専用のチームデータ。")


def _rank_block(metric: str, rows: list) -> str:
    if not rows:
        return ""
    body = "".join(
        '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;'
        f'border-bottom:1px solid #f0f0f0;{"background:#fff3e0;font-weight:700;" if is_g else ""}">'
        f'<span style="width:24px;color:#888;text-align:center;">{rk}</span>'
        f'<span style="flex:1;">{_esc(tj)}{"（巨人）" if is_g else ""}</span>'
        f'<span style="color:#c0392b;font-weight:700;">{_esc(disp)}</span></div>'
        for (tj, disp, rk, is_g) in rows
    )
    return (
        '<section class="ys-card" style="margin:0 0 14px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">セ・リーグ 球団{_esc(metric)} ランキング</h2>'
        f'{body}</section>'
    )


def _build_team_record_card(rec: dict) -> str:
    """巨人 チーム成績カード (459、 games 由来)。 順位/GB は standings 未populate のため非掲載。"""
    if not rec or (rec.get("wins", 0) + rec.get("losses", 0) + rec.get("draws", 0)) == 0:
        return ""
    wp = rec.get("win_pct")
    wp_s = (f"{wp:.3f}"[1:] if (wp is not None and wp < 1) else (f"{wp:.3f}" if wp is not None else "-"))
    rd = rec.get("run_diff", 0)
    rd_s = f"+{rd}" if rd > 0 else str(rd)
    kind, n = rec.get("streak_kind", ""), rec.get("streak", 0)
    streak_s = (f"{n}連勝" if kind == "W" else (f"{n}連敗" if kind == "L" else "-"))
    hw, hl = rec.get("home", (0, 0))
    aw, al = rec.get("away", (0, 0))
    td = 'style="padding:6px;"'
    tdb = 'style="padding:6px;font-weight:600;"'
    return (
        '<div style="background:#fff;border:1px solid #ffe0cc;border-radius:12px;padding:16px;margin:0 0 16px;">'
        '<h2 style="font-size:16px;margin:0 0 10px;">巨人 チーム成績 '
        '<span style="font-size:11px;color:#e25400;">毎日更新</span></h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;text-align:center;"><tbody>'
        f'<tr><td {td}>勝-敗-分</td><td {tdb}>{rec["wins"]}-{rec["losses"]}-{rec["draws"]}</td>'
        f'<td {td}>勝率</td><td {tdb}>{wp_s}</td></tr>'
        f'<tr><td {td}>得点-失点</td><td {td}>{rec["runs_for"]}-{rec["runs_against"]}</td>'
        f'<td {td}>得失点差</td><td {tdb}>{rd_s}</td></tr>'
        f'<tr><td {td}>連勝/連敗</td><td {td}>{streak_s}</td>'
        f'<td {td}>本拠地/ビジター</td><td {td}>{hw}勝{hl}敗 / {aw}勝{al}敗</td></tr>'
        '</tbody></table></div>'
    )


def _build_standings_card(standings: list) -> str:
    """セ・リーグ順位表カード (459/C、 NPB公式 scrape)。 巨人行ハイライト。"""
    if not standings:
        return ""
    rows = ""
    for s in standings:
        hl = "background:#fff3e0;font-weight:700;" if s.get("is_giants") else ""
        rows += (
            f'<tr style="text-align:center;border-bottom:1px solid #f0f0f0;{hl}">'
            f'<td style="padding:6px;">{_esc(s.get("rank"))}</td>'
            f'<td style="padding:6px;text-align:left;">{_esc(s.get("team"))}</td>'
            f'<td style="padding:6px;">{_esc(s.get("g"))}</td>'
            f'<td style="padding:6px;">{_esc(s.get("w"))}</td>'
            f'<td style="padding:6px;">{_esc(s.get("l"))}</td>'
            f'<td style="padding:6px;">{_esc(s.get("t"))}</td>'
            f'<td style="padding:6px;font-weight:600;">{_esc(s.get("pct"))}</td>'
            f'<td style="padding:6px;">{_esc(s.get("gb"))}</td>'
            '</tr>'
        )
    return (
        '<section class="ys-card" style="margin:0 0 16px;">'
        '<h2 style="font-size:16px;margin:0 0 8px;">セ・リーグ順位表 '
        '<span style="font-size:11px;color:#e25400;">毎日更新</span></h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:6px;">順位</th><th style="padding:6px;">チーム</th><th style="padding:6px;">試合</th>'
        '<th style="padding:6px;">勝</th><th style="padding:6px;">敗</th><th style="padding:6px;">分</th>'
        '<th style="padding:6px;">勝率</th><th style="padding:6px;">差</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>'
        '<p style="font-size:11px;color:#999;margin:6px 0 0;">出典: NPB公式</p>'
        '</section>'
    )


def render_team_html(rankings: dict, team_record: dict = None, standings: list = None) -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>球団成績</span></nav>'
    )
    blocks = "".join(_rank_block(m, rankings.get(m) or []) for m in _METRIC_ORDER)
    record_card = _build_team_record_card(team_record or {})
    standings_card = _build_standings_card(standings or [])
    return (
        '<div style="font-family:sans-serif;max-width:640px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 球団成績・セ・リーグ順位 2026</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 14px;">セ・リーグ順位表、巨人のチーム成績、6球団の打率・本塁打・防御率ランキング。</p>'
        f'{standings_card}'
        f'{record_card}'
        f'{blocks or "<p>データ準備中</p>"}'
        f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
        '</div>'
    )


# --- 462: 選手ランキング HUB (/data/ranking、 fetch_team_leaders 由来、 pillar 回遊) ---
def render_ranking_title() -> str:
    return "巨人 選手ランキング 2026【今季&通算 本塁打・打点・打率・防御率】 | 巨人データ"


def render_ranking_excerpt(leaders: dict) -> str:
    cats = "・".join(list(leaders.keys())[:6]) if leaders else "本塁打・打点・打率"
    return (f"読売ジャイアンツ2026の選手別 球団内ランキング（{cats}）。毎日更新、"
            "各選手名から詳細データページへ。")


def _ranking_block(cat: str, entries: list) -> str:
    from src.data_site_slug import player_slug  # lazy import (循環回避)

    def _link(name: str) -> str:
        try:
            return f"/data/{player_slug(name)}/"
        except Exception:  # noqa: BLE001
            return ""

    rows = ""
    for i, e in enumerate(entries):
        href = _link(e.player)
        name_html = (f'<a href="{href}" style="flex:1;color:#1a1a1a;text-decoration:none;">{_esc(e.player)}</a>'
                     if href else f'<span style="flex:1;">{_esc(e.player)}</span>')
        rows += (
            '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid #f0f0f0;">'
            f'<span style="width:24px;color:#e25400;text-align:center;font-weight:700;">{i + 1}</span>'
            f'{name_html}'
            f'<span style="color:#c0392b;font-weight:700;">{_esc(e.display)}</span></div>'
        )
    return (
        '<section class="ys-card" style="margin:0 0 14px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">巨人 {_esc(cat)} ランキング</h2>'
        f'{rows}</section>'
    )


def render_ranking_html(
    leaders: dict, career_leaders: dict = None, alltime_leaders: dict = None
) -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>選手ランキング</span></nav>'
    )
    blocks = "".join(_ranking_block(c, e) for c, e in (leaders or {}).items() if e)
    # 468-1: 現役選手の NPB 通算成績ランキング (467 career 由来)。今季ランキングの下に出す。
    career_blocks = "".join(_ranking_block(c, e) for c, e in (career_leaders or {}).items() if e)
    career_section = (
        '<h2 style="font-size:18px;margin:22px 0 4px;padding:8px 12px;background:#fff3ea;'
        'border-left:5px solid #e25400;color:#e25400;border-radius:4px;">現役選手 通算成績ランキング</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 12px;">現役巨人選手の NPB 通算記録（移籍前を含む）。'
        '率は規定到達者のみ。NPB 公式データより毎日更新。</p>'
        f'{career_blocks}'
    ) if career_blocks else ""
    # Phase1: 全史(歴代 OB + 現役)NPB通算ランキング。共有部品 alltime_ranking 由来。
    alltime_blocks = "".join(_ranking_block(c, e) for c, e in (alltime_leaders or {}).items() if e)
    alltime_section = (
        '<h2 style="font-size:18px;margin:22px 0 4px;padding:8px 12px;background:#1a1a2e;'
        'border-left:5px solid #e25400;color:#fff;border-radius:4px;">歴代（全史）通算ランキング</h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 12px;">巨人に在籍した選手の NPB 通算記録を歴代で集計。'
        'OB レジェンドと現役を横断。<b>★現役</b> は現在の巨人選手。NPB 公式 / 巨人OB 記録より。</p>'
        f'{alltime_blocks}'
    ) if alltime_blocks else ""
    return (
        '<div style="font-family:sans-serif;max-width:640px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 選手ランキング 2026（今季・通算・歴代）</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 14px;">球団内の選手別ランキング。今季成績・現役通算・歴代全史。毎日更新。各選手名から詳細データへ。</p>'
        '<h2 style="font-size:18px;margin:6px 0 8px;padding:8px 12px;background:#fff3ea;'
        'border-left:5px solid #e25400;color:#e25400;border-radius:4px;">今季成績ランキング</h2>'
        f'{blocks or "<p>データ準備中</p>"}'
        f'{career_section}'
        f'{alltime_section}'
        f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a></p>'
        '</div>'
    )


# ─── 記録室ハブ /data/record(Phase2、共有部品 alltime_ranking 由来)──────────
def render_record_title() -> str:
    return "巨人 記録室【名球会・通算2000安打・300本塁打クラブ】歴代の節目到達者 | 巨人データ"


def render_record_excerpt(record: dict) -> str:
    clubs = "・".join(list(record.keys())[:4]) if record else "名球会・通算本塁打クラブ"
    return (f"読売ジャイアンツに在籍した選手の通算節目クラブ会員一覧（{clubs}）。"
            "OB レジェンドと現役を横断、NPB 通算で集計。")


def _record_block(club: str, members: list) -> str:
    """記録室のクラブ 1 つ(h2 = クラブ名そのまま)。"""
    from src.data_site_slug import player_slug  # lazy import (循環回避)

    def _link(name: str) -> str:
        try:
            return f"/data/{player_slug(name)}/"
        except Exception:  # noqa: BLE001
            return ""

    rows = ""
    for i, e in enumerate(members):
        href = _link(e.player)
        name_html = (f'<a href="{href}" style="flex:1;color:#1a1a1a;text-decoration:none;">{_esc(e.player)}</a>'
                     if href else f'<span style="flex:1;">{_esc(e.player)}</span>')
        rows += (
            '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid #f0f0f0;">'
            f'<span style="width:24px;color:#e25400;text-align:center;font-weight:700;">{i + 1}</span>'
            f'{name_html}'
            f'<span style="color:#c0392b;font-weight:700;">{_esc(e.display)}</span></div>'
        )
    return (
        '<section class="ys-card" style="margin:0 0 16px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;padding:6px 10px;background:#1a1a2e;color:#fff;border-radius:4px;">'
        f'🏛 {_esc(club)}（{len(members)}名）</h2>'
        f'{rows}</section>'
    )


def render_record_html(record: dict) -> str:
    nav = (
        '<nav class="ys-breadcrumb" style="font-size:12px;color:#666;margin:0 0 12px;">'
        f'<a href="{SITE_BASE}/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › <span>記録室</span></nav>'
    )
    blocks = "".join(_record_block(c, m) for c, m in (record or {}).items() if m)
    return (
        '<div style="font-family:sans-serif;max-width:640px;">'
        f'{nav}'
        '<h1 style="font-size:20px;margin:0 0 4px;">巨人 記録室 — 歴代の節目到達者</h1>'
        '<p style="font-size:13px;color:#666;margin:0 0 14px;">読売ジャイアンツに在籍した選手の通算記録クラブ。'
        'OB レジェンドと現役を横断、<b>★現役</b> は現在の巨人選手。NPB 通算（全球団含む）で集計、各選手名から詳細データへ。</p>'
        f'{blocks or "<p>データ準備中</p>"}'
        f'<p style="margin-top:16px;"><a href="{CLUSTER_URL}">← 選手データ一覧へ</a> ／ '
        f'<a href="/data/ranking/">🏆 選手ランキングへ</a></p>'
        '</div>'
    )
