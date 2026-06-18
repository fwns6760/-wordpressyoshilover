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

import functools as _functools
import html as _html
import json as _json
import os as _os
from dataclasses import dataclass, field
from typing import Optional

from src.player_data_prose import build_player_prose as _build_player_prose


@dataclass
class PillarPlayerInfo:
    """1 Pillar page を作るのに必要な最小情報。"""

    name: str               # canonical 表記 (例: 吉川尚輝)
    slug: str               # URL slug (例: yoshikawa-naoki)
    position: str           # 内野手 / 外野手 / 投手 / 監督 / コーチ
    jersey_number: str      # 背番号 文字列 (例: "2" / "92")
    role: str = "player"    # player / manager / coach
    featured_image_url: str = ""   # H1 直下に出す写真 URL (空なら team mark)
    featured_media_id: Optional[int] = None  # WP featured_media id (SNS 共有 og:image 用、 None なら未設定)
    short_review: str = ""  # AI 短評 200-500 字 (空なら section omit)
    related_topic_links: list[tuple[str, str]] = field(default_factory=list)
    # related_topic_links = [(url, title), ...] (既存記事の link、 関連 Topic = Pillar → Topic)
    # prosports.yoshilover.com の同一選手 人物・家族記事への相互リンク [(url, title), ...]
    prosports_links: list[tuple[str, str]] = field(default_factory=list)
    # 監督・コーチ の現役選手時代 NPB 通算成績 (config/coach_career_stats.json 由来、 無ければ None)
    career_stats: Optional[dict] = None
    # 関連選手 (同じ登録ポジションの他選手) [(slug, name), ...] — spoke↔spoke 内部リンク用
    related_players: list[tuple[str, str]] = field(default_factory=list)
    # OB・レジェンド profile (config/ob_legends.json 由来、 無ければ None)
    ob_profile: Optional[dict] = None
    # 467: NPB 公式 career page 由来の網羅データ (npb_career_scraper.parse_player_career 結果)
    # {"profile": {...}, "is_pitcher": bool, "batting": {...}, "pitching": {...}} / 無ければ None
    npb_career: Optional[dict] = None

    # Phase 1.0 stats (insight.db 由来、 None なら placeholder)
    season_games: int = 0
    season_ab: int = 0
    season_hits: int = 0
    season_rbi: int = 0
    season_runs: int = 0
    season_sb: int = 0
    season_hr: int = 0
    season_avg: Optional[float] = None
    # 453: NPB 全 12 球団内 順位バッジ [(label, value_str, rank, total), ...]
    metric_ranks: list[tuple] = field(default_factory=list)
    recent_games: list[tuple[str, str, int, int, int]] = field(default_factory=list)
    # recent_games = [(game_date, opponent, ab, hits, rbi), ...]
    has_stats: bool = False  # False なら 「データ集計中」 placeholder
    # Phase 1.0a 大手未掲載 metric pack
    lineup_slot_stats: list[tuple[int, int, int, int, int, Optional[float]]] = field(default_factory=list)
    # lineup_slot_stats = [(slot, G, AB, H, RBI, AVG), ...] (slot 1-9)
    opponent_split_stats: list[tuple[str, int, int, int, int, Optional[float]]] = field(default_factory=list)
    # opponent_split_stats = [(opp, G, AB, H, RBI, AVG), ...]
    venue_split_stats: list[tuple[str, int, int, int, int, Optional[float]]] = field(default_factory=list)
    # venue_split_stats = [(venue, G, AB, H, RBI, AVG), ...] (本拠地 / ビジター)
    inning_split_stats: list[tuple[str, int, int, Optional[float]]] = field(default_factory=list)
    # inning_split_stats = [(phase, AB, H, AVG), ...] (序盤 1-3回 / 中盤 4-6回 / 終盤 7-9回)
    # 457: 得点圏 (RISP) [(label, AB, H, AVG), ...]
    risp_split_stats: list[tuple[str, int, int, Optional[float]]] = field(default_factory=list)
    # 457: 対左/右投手 [(label, AB, H, AVG), ...]
    vs_lr_split_stats: list[tuple[str, int, int, Optional[float]]] = field(default_factory=list)
    # 461: セイバーメトリクス [(label, 値str, league_rank, league_total), ...]
    sabermetric_stats: list[tuple] = field(default_factory=list)
    # Phase B (452): 曜日別 / 月別 / 交流戦別 = [(label, G, AB, H, AVG), ...]
    weekday_split_stats: list[tuple[str, int, int, int, Optional[float]]] = field(default_factory=list)
    month_split_stats: list[tuple[str, int, int, int, Optional[float]]] = field(default_factory=list)
    interleague_split_stats: list[tuple[str, int, int, int, Optional[float]]] = field(default_factory=list)
    # Phase 1.0b1 streak (現在 active + 自己最長 season)
    hit_streak_active: int = 0
    hit_streak_season_max: int = 0
    contribution_streak_active: int = 0
    contribution_streak_season_max: int = 0
    # Phase 1.5+α 投手 stats (position=投手 のみ。 None なら placeholder)
    pitch_games: int = 0
    pitch_wins: int = 0
    pitch_losses: int = 0
    pitch_ip: float = 0.0
    pitch_k: int = 0
    pitch_bb: int = 0
    pitch_h_allowed: int = 0
    pitch_hr_allowed: int = 0
    pitch_er: int = 0
    pitch_era: Optional[float] = None
    pitch_whip: Optional[float] = None
    pitch_k_per_9: Optional[float] = None
    pitch_bb_per_9: Optional[float] = None
    # 二軍（ファーム）今季成績 (NPB公式 idb1_g/idp1_g 由来)。 無ければ None。
    farm_batting: Optional[dict] = None
    farm_pitching: Optional[dict] = None
    has_pitching_stats: bool = False
    recent_pitching_games: list[tuple[str, str, str, float, int, int, int, int]] = field(default_factory=list)
    # recent_pitching_games = [(date, opp, result_mark, ip, h, k, bb, er), ...]
    # 456: 投手 split [(label, G, IP, K, ER, ERA), ...]
    pitch_opponent_split_stats: list[tuple[str, int, float, int, int, Optional[float]]] = field(default_factory=list)
    pitch_venue_split_stats: list[tuple[str, int, float, int, int, Optional[float]]] = field(default_factory=list)
    pitch_weekday_split_stats: list[tuple[str, int, float, int, int, Optional[float]]] = field(default_factory=list)
    pitch_month_split_stats: list[tuple[str, int, float, int, int, Optional[float]]] = field(default_factory=list)
    pitch_interleague_split_stats: list[tuple[str, int, float, int, int, Optional[float]]] = field(default_factory=list)


CLUSTER_URL = "https://yoshilover.com/data"
SITE_BASE = "https://yoshilover.com"


def _esc(text: str) -> str:
    """HTML escape helper (空文字 safe)。"""
    return _html.escape(str(text or ""), quote=True)


def _build_style_block() -> str:
    """巨人=オレンジ強めの scoped デザインシステム CSS。 ページ先頭に 1 度だけ注入。

    全 data ページの視覚的 identity (ブランド)。 .ys-data 配下のみに効くよう scope。
    inline style 廃止と併せて、 カード型・オレンジ基調・モバイル最優先・split バー可視化。
    """
    return (
        "<style>\n"
        ".ys-data{--o:#ff6a00;--od:#e25400;--ol:#fff3ea;--ink:#1a1a1a;--mut:#6f6f6f;"
        "max-width:760px;margin:0 auto;color:var(--ink);"
        "font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Yu Gothic',sans-serif;line-height:1.6;}\n"
        ".ys-data *{box-sizing:border-box;}\n"
        ".ys-data .ys-bc{font-size:12px;color:var(--mut);margin:0 0 10px;}\n"
        ".ys-data .ys-bc a{color:var(--mut);text-decoration:none;}\n"
        ".ys-data .ys-lead{font-size:14px;line-height:1.75;color:#333;margin:0 0 14px;"
        "padding:10px 14px;background:var(--ol);border-radius:8px;border-left:4px solid var(--o);}\n"
        ".ys-data .ys-feat{text-align:center;margin:0 0 18px;}\n"
        ".ys-data .ys-feat img{max-width:480px;width:100%;height:auto;border-radius:12px;"
        "box-shadow:0 4px 14px rgba(226,84,0,.18);border:3px solid #fff;outline:1px solid #ffd9bf;}\n"
        ".ys-data .ys-card{background:#fff;border:1px solid #ffe0cc;border-radius:12px;"
        "padding:16px;margin:0 0 16px;box-shadow:0 2px 8px rgba(0,0,0,.04);}\n"
        ".ys-data .ys-card h2{font-size:17px;font-weight:800;margin:0 0 4px;color:var(--ink);"
        "padding-left:12px;border-left:5px solid var(--o);display:flex;align-items:center;gap:8px;}\n"
        ".ys-data .ys-tag{font-size:10px;font-weight:700;color:#fff;background:var(--o);"
        "padding:2px 8px;border-radius:999px;letter-spacing:.02em;}\n"
        ".ys-data .ys-note{font-size:12px;color:var(--mut);margin:6px 0 12px;line-height:1.6;}\n"
        ".ys-data .ys-foot{font-size:11px;color:#aaa;margin:10px 0 0;}\n"
        ".ys-data table{width:100%;border-collapse:collapse;font-size:13px;}\n"
        ".ys-data thead th{background:var(--od);color:#fff;padding:9px 6px;font-weight:700;text-align:center;}\n"
        ".ys-data thead th:first-child{border-top-left-radius:8px;}\n"
        ".ys-data thead th:last-child{border-top-right-radius:8px;}\n"
        ".ys-data tbody td{padding:9px 6px;text-align:center;border-bottom:1px solid #f2e6dd;}\n"
        ".ys-data tbody tr:nth-child(even){background:var(--ol);}\n"
        ".ys-data .ys-k{font-weight:700;color:var(--od);}\n"
        ".ys-data .ys-avg{font-weight:800;color:var(--o);font-variant-numeric:tabular-nums;}\n"
        ".ys-data .ys-hero{display:flex;flex-wrap:wrap;gap:10px;margin:4px 0 0;}\n"
        ".ys-data .ys-hero .b{flex:1;min-width:74px;text-align:center;background:var(--ol);"
        "border-radius:10px;padding:10px 6px;}\n"
        ".ys-data .ys-hero .b .v{font-size:22px;font-weight:800;color:var(--od);line-height:1.1;font-variant-numeric:tabular-nums;}\n"
        ".ys-data .ys-hero .b.main .v{color:var(--o);font-size:26px;}\n"
        ".ys-data .ys-hero .b .l{font-size:11px;color:var(--mut);margin-top:3px;}\n"
        ".ys-data .ys-bars{margin:4px 0 0;}\n"
        ".ys-data .ys-bar{display:flex;align-items:center;gap:10px;margin:0 0 8px;}\n"
        ".ys-data .ys-bar .nm{width:84px;font-size:13px;font-weight:700;color:var(--ink);flex:none;}\n"
        ".ys-data .ys-bar .tr{flex:1;background:#f1e7df;border-radius:999px;height:22px;position:relative;overflow:hidden;}\n"
        ".ys-data .ys-bar .fl{height:100%;background:linear-gradient(90deg,var(--o),var(--od));border-radius:999px;min-width:2px;}\n"
        ".ys-data .ys-bar .vl{width:74px;font-size:13px;font-weight:800;color:var(--od);text-align:right;flex:none;font-variant-numeric:tabular-nums;}\n"
        ".ys-data .ys-bar .sub{font-size:10px;color:var(--mut);font-weight:500;}\n"
        "@media(max-width:520px){.ys-data table{font-size:12px;}.ys-data thead th,.ys-data tbody td{padding:7px 3px;}"
        ".ys-data .ys-bar .nm{width:62px;font-size:12px;}.ys-data .ys-bar .vl{width:60px;}}\n"
        "</style>"
    )


def _build_lead_html(player: "PillarPlayerInfo") -> str:
    """ページ冒頭の lead 文 (SNS 共有 og:description / SEO meta description 用)。

    SEO SIMPLE PACK は固定ページの description を WP excerpt ではなく本文先頭テキストから
    自動生成する。 そのため breadcrumb より前に clean な 1 文を置き、 共有プレビューが
    「Home › 巨人選手データ › …数字羅列」 ではなく説明文で始まるようにする。
    """
    lead = render_pillar_excerpt(player)
    if not lead:
        return ""
    return f'<p class="ys-lead">{_esc(lead)}</p>'


def _build_breadcrumb_html(name: str) -> str:
    """Pillar 上部の breadcrumb (Home → 選手データ → {player})。"""
    return (
        '<nav class="ys-bc" aria-label="breadcrumb">'
        '<a href="https://yoshilover.com/">Home</a> › '
        f'<a href="{CLUSTER_URL}">巨人選手データ</a> › '
        f'<span>{_esc(name)}</span>'
        '</nav>'
    )


def _build_featured_image_html(player: PillarPlayerInfo) -> str:
    if not player.featured_image_url:
        return ""
    return (
        '<div class="ys-feat">'
        f'<img src="{_esc(player.featured_image_url)}" alt="{_esc(player.name)}選手" />'
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


def _fmt_avg(avg: Optional[float]) -> str:
    if avg is None:
        return "-"
    return f"{avg:.3f}".lstrip("0") if avg < 1 else f"{avg:.3f}"


def _build_season_stats_html(player: PillarPlayerInfo) -> str:
    """season 集計 stats を 表で表示。 data 無ければ placeholder (具体化)。"""
    if not player.has_stats or player.season_games == 0:
        return (
            '<div class="ys-card">'
            '<h2>今シーズン 一軍成績 (打撃)</h2>'
            '<p class="ys-note">'
            f'{_esc(player.name)}選手の今シーズン 一軍出場記録は、 現時点で集計対象となる box score 上に確認できていません。'
            ' 出場が記録され次第、 毎朝 6:00 + 試合後 17:30 / 23:00 JST に自動反映されます。'
            '</p></div>'
        )
    avg = _fmt_avg(player.season_avg)
    boxes = [
        ("打率", avg, True), ("安打", str(player.season_hits), False),
        ("打点", str(player.season_rbi), False), ("得点", str(player.season_runs), False),
        ("盗塁", str(player.season_sb), False), ("試合", str(player.season_games), False),
        ("打数", str(player.season_ab), False),
    ]
    hero = '<div class="ys-hero">' + "".join(
        f'<div class="b{" main" if main else ""}"><div class="v">{_esc(v)}</div><div class="l">{_esc(l)}</div></div>'
        for (l, v, main) in boxes
    ) + '</div>'
    badges = "".join(
        f'<span class="ys-tag">{_esc(label)} {rank}位/{total}人中</span>'
        for (label, _v, rank, total) in (player.metric_ranks or [])
    )
    badges_html = (
        f'<div style="margin:10px 0 0;display:flex;flex-wrap:wrap;gap:6px;">{badges}</div>'
        if badges else ""
    )
    return (
        '<div class="ys-card">'
        '<h2>今シーズン 一軍成績 (打撃) <span class="ys-tag">NPB順位</span></h2>'
        + hero + badges_html +
        '<p class="ys-foot">※ NPB 全12球団 box score 集計 / 毎朝 6:00 JST 更新。 '
        '順位は NPB 内 (打率は規定到達者中)。</p>'
        '</div>'
    )


def _build_recent_games_html(player: PillarPlayerInfo) -> str:
    """直近 5 試合の打撃結果表。 data 無ければ section omit。"""
    if not player.recent_games:
        return ""
    rows_html = "\n".join(
        '<tr>'
        f'<td>{_esc(date)}</td><td>{_esc(opp)}</td><td>{ab}</td>'
        f'<td class="ys-k">{h}</td><td>{rbi}</td>'
        '</tr>'
        for (date, opp, ab, h, rbi) in player.recent_games
    )
    return (
        '<div class="ys-card">'
        f'<h2>直近 {len(player.recent_games)} 試合</h2>'
        '<table><thead><tr>'
        '<th>日付</th><th>相手</th><th>打数</th><th>安打</th><th>打点</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</div>'
    )


def _build_lineup_slot_html(player: PillarPlayerInfo) -> str:
    """打順別 打率 (大手未掲載 metric pack #1)。"""
    if not player.lineup_slot_stats:
        return ""
    rows_html = "\n".join(
        '<tr>'
        f'<td class="ys-k">{slot} 番</td><td>{g}</td><td>{ab}</td>'
        f'<td>{h}</td><td class="ys-avg">{_fmt_avg(avg)}</td><td>{rbi}</td>'
        '</tr>'
        for (slot, g, ab, h, rbi, avg) in player.lineup_slot_stats
    )
    return (
        '<div class="ys-card">'
        '<h2>打順別 成績 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">どの打順で起用された時に結果を残せているか、 一目で分かる split data。</p>'
        '<table><thead><tr>'
        '<th>打順</th><th>試合</th><th>打数</th><th>安打</th><th>打率</th><th>打点</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</div>'
    )


def _build_opponent_split_html(player: PillarPlayerInfo) -> str:
    """vs 各球団 打率 (大手未掲載 metric pack #2)。"""
    if not player.opponent_split_stats:
        return ""
    rows_html = "\n".join(
        '<tr>'
        f'<td class="ys-k">{_esc(opp)}</td><td>{g}</td><td>{ab}</td>'
        f'<td>{h}</td><td class="ys-avg">{_fmt_avg(avg)}</td><td>{rbi}</td>'
        '</tr>'
        for (opp, g, ab, h, rbi, avg) in player.opponent_split_stats
    )
    return (
        '<div class="ys-card">'
        '<h2>vs 各球団 成績 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">対戦相手別の相性。 得意 / 苦手な球団が浮き出る。</p>'
        '<table><thead><tr>'
        '<th>相手</th><th>試合</th><th>打数</th><th>安打</th><th>打率</th><th>打点</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</div>'
    )


def _build_venue_split_html(player: PillarPlayerInfo) -> str:
    """本拠地 / ビジター 別 打率 (大手未掲載 metric pack #venue)。"""
    if not player.venue_split_stats:
        return ""
    bars = "".join(
        _split_bar(venue, avg, f"{h}/{ab}・{g}試合")
        for (venue, g, ab, h, rbi, avg) in player.venue_split_stats
    )
    return (
        '<div class="ys-card">'
        '<h2>本拠地 / ビジター 別 打率 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">東京ドーム (本拠地) と 敵地 (ビジター) でどう違うか。 home / away の相性が見える。</p>'
        f'<div class="ys-bars">{bars}</div>'
        '</div>'
    )


def _build_inning_split_html(player: PillarPlayerInfo) -> str:
    """序盤 / 中盤 / 終盤 別 打率 (大手未掲載 metric pack #5 inning)。"""
    if not player.inning_split_stats:
        return ""
    bars = "".join(_split_bar(phase, avg, f"{h}/{ab}") for (phase, ab, h, avg) in player.inning_split_stats)
    return (
        '<div class="ys-card">'
        '<h2>序盤 / 中盤 / 終盤 別 打率 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">序盤 (1〜3回) / 中盤 (4〜6回) / 終盤 (7〜9回) でどう変わるか。 '
        '立ち上がりに強いか、 終盤の勝負どころで打てるかが見える。</p>'
        f'<div class="ys-bars">{bars}</div>'
        '<p class="ys-foot">※ イニング別打席記録から集計。 同一回に2打席ある場合は1打席に圧縮されるため、 '
        '総打数は実数を僅かに下回ることがあります。</p>'
        '</div>'
    )


def _build_weekday_split_html(player: PillarPlayerInfo) -> str:
    """曜日別 打率 (Phase B 452、大手未掲載)。"""
    if not player.weekday_split_stats:
        return ""
    bars = "".join(_split_bar(f"{lbl}曜", avg, f"{h}/{ab}・{g}試合")
                   for (lbl, g, ab, h, avg) in player.weekday_split_stats)
    return (
        '<div class="ys-card">'
        '<h2>曜日別 打率 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">デーゲーム多めの土日 / ナイターの平日 でどう違うか。</p>'
        f'<div class="ys-bars">{bars}</div>'
        '</div>'
    )


def _build_month_split_html(player: PillarPlayerInfo) -> str:
    """月別 打率 (Phase B 452)。"""
    if not player.month_split_stats:
        return ""
    bars = "".join(_split_bar(lbl, avg, f"{h}/{ab}・{g}試合")
                   for (lbl, g, ab, h, avg) in player.month_split_stats)
    return (
        '<div class="ys-card">'
        '<h2>月別 打率 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">シーズンを通した調子の波。 今が上り調子か下降か。</p>'
        f'<div class="ys-bars">{bars}</div>'
        '</div>'
    )


def _build_interleague_split_html(player: PillarPlayerInfo) -> str:
    """交流戦 / リーグ戦 別 打率 (Phase B 452)。"""
    if not player.interleague_split_stats:
        return ""
    bars = "".join(_split_bar(lbl, avg, f"{h}/{ab}・{g}試合")
                   for (lbl, g, ab, h, avg) in player.interleague_split_stats)
    return (
        '<div class="ys-card">'
        '<h2>交流戦 / リーグ戦 別 打率 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">パ相手の交流戦と、 セ内のリーグ戦での違い。</p>'
        f'<div class="ys-bars">{bars}</div>'
        '</div>'
    )


def _build_sabermetrics_html(player: PillarPlayerInfo) -> str:
    """セイバーメトリクス (461、 site はライバル超えのため全指標表示)。"""
    if not player.sabermetric_stats:
        return ""
    rows_html = "\n".join(
        '<tr>'
        f'<td class="ys-k">{_esc(lbl)}</td><td class="ys-avg">{_esc(val)}</td>'
        f'<td>{("リーグ " + str(rank) + "/" + str(total) + "位") if rank else "-"}</td>'
        '</tr>'
        for (lbl, val, rank, total) in player.sabermetric_stats
    )
    return (
        '<div class="ys-card">'
        '<h2>セイバーメトリクス <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">大手メディアが出さない高度指標 (直近30日)。 リーグ内順位つきで強みが一目で分かる。</p>'
        '<table><thead><tr><th>指標</th><th>値</th><th>リーグ内順位</th></tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</div>'
    )


def _build_vs_lr_split_html(player: PillarPlayerInfo) -> str:
    """対左 / 対右投手 別 打率 (大手未掲載、 457)。"""
    if not player.vs_lr_split_stats:
        return ""
    bars = "".join(_split_bar(lbl, avg, f"{h}/{ab}") for (lbl, ab, h, avg) in player.vs_lr_split_stats)
    return (
        '<div class="ys-card">'
        '<h2>対左 / 対右投手 別 打率 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">左投手 / 右投手 でどれだけ打ち分けるか。 左右の苦手が見える。</p>'
        f'<div class="ys-bars">{bars}</div>'
        '<p class="ys-foot">※ 対戦投手の左右と打席結果から集計。 投手の判明した打席のみ対象。</p>'
        '</div>'
    )


def _build_risp_split_html(player: PillarPlayerInfo) -> str:
    """得点圏 (RISP) 打率 (大手未掲載、 457)。"""
    if not player.risp_split_stats:
        return ""
    bars = "".join(_split_bar(lbl, avg, f"{h}/{ab}") for (lbl, ab, h, avg) in player.risp_split_stats)
    return (
        '<div class="ys-card">'
        '<h2>得点圏 打率 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">走者が二塁・三塁にいる「得点圏」での打率。 チャンスでの勝負強さが見える。</p>'
        f'<div class="ys-bars">{bars}</div>'
        '<p class="ys-foot">※ 打席ごとの走者状況から集計。 四死球・犠打・犠飛・打撃妨害は打数から除外。</p>'
        '</div>'
    )


def _split_bar(name: str, avg: Optional[float], sub: str) -> str:
    """split 1 行を横棒バーで描く。 幅は打率 (.400 で満杯) に比例。"""
    a = avg or 0.0
    w = max(2.0, min(100.0, a / 0.400 * 100.0))
    return (
        '<div class="ys-bar">'
        f'<div class="nm">{_esc(name)}</div>'
        f'<div class="tr"><div class="fl" style="width:{w:.0f}%"></div></div>'
        f'<div class="vl">{_fmt_avg(avg)}<div class="sub">{_esc(sub)}</div></div>'
        '</div>'
    )


def _fmt_era(v: Optional[float]) -> str:
    if v is None:
        return "-"
    return f"{v:.2f}"


def _fmt_ip(ip: float) -> str:
    """投球回 表示 (NPB 0.1/0.2 形式)。 ip 内部は 1/3 表記の小数で持つ。"""
    if ip <= 0:
        return "-"
    return f"{ip:.1f}"


def _build_pitching_season_html(player: PillarPlayerInfo) -> str:
    """投手 season summary (position=投手 only)、 data 無ければ具体化 placeholder。"""
    if not player.has_pitching_stats or player.pitch_games == 0:
        return (
            '<section class="ys-pillar-pitch-season" '
            'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
            '<h2 style="font-size:16px;margin:0 0 10px;">今シーズン 一軍成績 (投手)</h2>'
            '<p style="font-size:13px;color:#888;margin:0;">'
            f'{_esc(player.name)}投手の今シーズン 一軍登板記録は、 現時点で集計対象となる box score 上に確認できていません。'
            ' 登板が記録され次第、 毎朝 6:00 + 試合後 17:30 / 23:00 JST に自動反映されます。'
            '</p>'
            '</section>'
        )
    _rank_badges = "".join(
        f'<span class="ys-tag">{_esc(label)} {rank}位/{total}人中</span>'
        for (label, _v, rank, total) in (player.metric_ranks or [])
    )
    _ranks_html = f'<p style="margin:0 0 8px;">{_rank_badges}</p>' if _rank_badges else ""
    return (
        '<section class="ys-pillar-pitch-season" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 10px;">今シーズン 一軍成績 (投手) '
        '<span class="ys-tag">NPB順位</span></h2>'
        f'{_ranks_html}'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:8px 4px;">登板</th>'
        '<th style="padding:8px 4px;">勝</th>'
        '<th style="padding:8px 4px;">敗</th>'
        '<th style="padding:8px 4px;">投球回</th>'
        '<th style="padding:8px 4px;">奪三振</th>'
        '<th style="padding:8px 4px;">与四球</th>'
        '<th style="padding:8px 4px;">被安打</th>'
        '<th style="padding:8px 4px;">被本塁打</th>'
        '<th style="padding:8px 4px;">自責</th>'
        '<th style="padding:8px 4px;">防御率</th>'
        '<th style="padding:8px 4px;">WHIP</th>'
        '</tr></thead>'
        '<tbody><tr style="text-align:center;">'
        f'<td style="padding:8px 4px;">{player.pitch_games}</td>'
        f'<td style="padding:8px 4px;color:#d32f2f;font-weight:600;">{player.pitch_wins}</td>'
        f'<td style="padding:8px 4px;">{player.pitch_losses}</td>'
        f'<td style="padding:8px 4px;">{_fmt_ip(player.pitch_ip)}</td>'
        f'<td style="padding:8px 4px;">{player.pitch_k}</td>'
        f'<td style="padding:8px 4px;">{player.pitch_bb}</td>'
        f'<td style="padding:8px 4px;">{player.pitch_h_allowed}</td>'
        f'<td style="padding:8px 4px;">{player.pitch_hr_allowed}</td>'
        f'<td style="padding:8px 4px;">{player.pitch_er}</td>'
        f'<td style="padding:8px 4px;color:#1976d2;font-weight:600;">{_fmt_era(player.pitch_era)}</td>'
        f'<td style="padding:8px 4px;color:#1976d2;font-weight:600;">{_fmt_era(player.pitch_whip)}</td>'
        '</tr></tbody></table>'
        '<p style="font-size:11px;color:#999;margin:8px 0 0;">'
        '※ insight.db 集計 (NPB official box score 由来)、 毎朝 6:00 + 試合後 17:30 / 23:00 JST 更新'
        '</p></section>'
    )


_FARM_PIT_ORDER = [("登板", "登板"), ("勝", "勝"), ("敗", "敗"), ("S", "S"),
                   ("H", "H"), ("投球回", "投球回"), ("奪三", "奪三振"), ("防御率", "防御率")]
_FARM_BAT_ORDER = [("試合", "試合"), ("打席", "打席"), ("打数", "打数"), ("安打", "安打"),
                   ("本", "本"), ("打点", "打点"), ("盗塁", "盗塁"), ("打率", "打率")]


def _farm_mini_table(rec: dict, order) -> str:
    cols = [(lab, rec[k]) for k, lab in order if k in rec and rec.get(k) not in (None, "")]
    if not cols:
        return ""
    ths = "".join(f'<th style="padding:7px 4px;">{_esc(lab)}</th>' for lab, _ in cols)
    tds = "".join(f'<td style="padding:7px 4px;">{_esc(v)}</td>' for _, v in cols)
    return ('<table style="width:100%;border-collapse:collapse;font-size:13px;margin:0 0 8px;">'
            f'<thead><tr style="background:#f1f8e9;text-align:center;color:#33691e;">{ths}</tr></thead>'
            f'<tbody><tr style="text-align:center;">{tds}</tr></tbody></table>')


def _build_farm_stats_html(player: PillarPlayerInfo) -> str:
    """二軍（ファーム）今季成績ブロック。 一軍と別集計であることを明示し、 わかりやすく区別表示。"""
    fp = player.farm_pitching or {}
    fb = player.farm_batting or {}
    pit_tbl = _farm_mini_table(fp, _FARM_PIT_ORDER) if fp else ""
    bat_tbl = _farm_mini_table(fb, _FARM_BAT_ORDER) if fb else ""
    if not pit_tbl and not bat_tbl:
        return ""
    parts = []
    if pit_tbl:
        parts.append('<div style="font-size:12px;color:#33691e;font-weight:700;margin:6px 0 2px;">投手成績</div>' + pit_tbl)
    if bat_tbl:
        parts.append('<div style="font-size:12px;color:#33691e;font-weight:700;margin:6px 0 2px;">打撃成績</div>' + bat_tbl)
    return (
        '<section style="background:#f9fbe7;border:1px solid #dce775;border-left:4px solid #7cb342;'
        'padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 4px;color:#33691e;">🌱 二軍（ファーム）今シーズン成績</h2>'
        '<p style="font-size:12px;color:#689f38;margin:0 0 10px;line-height:1.6;">'
        'イースタン・リーグでの今季成績です。<strong>一軍とは別集計</strong>のため、'
        '上の「一軍成績」と分けて掲載しています。</p>'
        + "".join(parts)
        + '<p style="font-size:11px;color:#999;margin:8px 0 0;">※ NPB公式 ファーム個人成績より</p>'
        '</section>'
    )


def _build_pitching_recent_html(player: PillarPlayerInfo) -> str:
    if not player.recent_pitching_games:
        return ""
    rows_html = "\n".join(
        '<tr style="text-align:center;border-bottom:1px solid #eee;">'
        f'<td style="padding:6px;">{_esc(date)}</td>'
        f'<td style="padding:6px;">{_esc(opp)}</td>'
        f'<td style="padding:6px;font-weight:600;color:#d32f2f;">{_esc(mark)}</td>'
        f'<td style="padding:6px;">{_fmt_ip(ip)}</td>'
        f'<td style="padding:6px;">{h}</td>'
        f'<td style="padding:6px;font-weight:600;">{k}</td>'
        f'<td style="padding:6px;">{bb}</td>'
        f'<td style="padding:6px;color:#1976d2;">{er}</td>'
        '</tr>'
        for (date, opp, mark, ip, h, k, bb, er) in player.recent_pitching_games
    )
    return (
        '<section class="ys-pillar-pitch-recent" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">直近 {len(player.recent_pitching_games)} 登板</h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:8px 4px;">日付</th>'
        '<th style="padding:8px 4px;">相手</th>'
        '<th style="padding:8px 4px;">結果</th>'
        '<th style="padding:8px 4px;">投球回</th>'
        '<th style="padding:8px 4px;">被安打</th>'
        '<th style="padding:8px 4px;">奪三振</th>'
        '<th style="padding:8px 4px;">与四球</th>'
        '<th style="padding:8px 4px;">自責</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</section>'
    )


def _build_pitch_opponent_split_html(player: PillarPlayerInfo) -> str:
    """投手 vs 各球団 投球成績 (456 投手 split、 打者 _build_opponent_split_html の投手版)。"""
    if not player.pitch_opponent_split_stats:
        return ""
    rows_html = "\n".join(
        '<tr>'
        f'<td class="ys-k">{_esc(opp)}</td><td>{g}</td><td>{_fmt_ip(ip)}</td>'
        f'<td>{k}</td><td>{er}</td><td class="ys-avg">{_fmt_era(era)}</td>'
        '</tr>'
        for (opp, g, ip, k, er, era) in player.pitch_opponent_split_stats
    )
    return (
        '<div class="ys-card">'
        '<h2>vs 各球団 投球成績 <span class="ys-tag">大手未掲載</span></h2>'
        '<p class="ys-note">対戦相手別の投球内容。 得意 / 苦手な球団が防御率で浮き出る。</p>'
        '<table><thead><tr>'
        '<th>相手</th><th>登板</th><th>投球回</th><th>奪三振</th><th>自責</th><th>防御率</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</div>'
    )


def _pitch_split_card(title: str, note: str, first_header: str, stats: list[tuple]) -> str:
    """投手 split 共通カード (登板/投球回/奪三振/自責/防御率)。 456。"""
    if not stats:
        return ""
    rows_html = "\n".join(
        '<tr>'
        f'<td class="ys-k">{_esc(lbl)}</td><td>{g}</td><td>{_fmt_ip(ip)}</td>'
        f'<td>{k}</td><td>{er}</td><td class="ys-avg">{_fmt_era(era)}</td>'
        '</tr>'
        for (lbl, g, ip, k, er, era) in stats
    )
    return (
        '<div class="ys-card">'
        f'<h2>{_esc(title)} <span class="ys-tag">大手未掲載</span></h2>'
        f'<p class="ys-note">{_esc(note)}</p>'
        '<table><thead><tr>'
        f'<th>{_esc(first_header)}</th><th>登板</th><th>投球回</th><th>奪三振</th><th>自責</th><th>防御率</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</div>'
    )


def _build_pitch_venue_split_html(player: PillarPlayerInfo) -> str:
    return _pitch_split_card(
        "本拠地 / ビジター 別 投球成績",
        "東京ドーム (本拠地) と 敵地 (ビジター) でどう違うか。 home / away の相性が見える。",
        "球場", player.pitch_venue_split_stats,
    )


def _build_pitch_weekday_split_html(player: PillarPlayerInfo) -> str:
    stats = [(f"{lbl}曜", g, ip, k, er, era)
             for (lbl, g, ip, k, er, era) in player.pitch_weekday_split_stats]
    return _pitch_split_card("曜日別 投球成績", "デーゲーム多めの土日 / ナイターの平日 でどう違うか。",
                             "曜日", stats)


def _build_pitch_month_split_html(player: PillarPlayerInfo) -> str:
    return _pitch_split_card("月別 投球成績", "シーズンを通した調子の波。 今が好調か不調か。",
                             "月", player.pitch_month_split_stats)


def _build_pitch_interleague_split_html(player: PillarPlayerInfo) -> str:
    return _pitch_split_card("交流戦 / リーグ戦 別 投球成績", "パ相手の交流戦と、 セ内のリーグ戦での違い。",
                             "区分", player.pitch_interleague_split_stats)


def _is_pitcher(player: PillarPlayerInfo) -> bool:
    """position が「投手」 なら True (打撃 section omit)."""
    return (player.position or "").strip() == "投手"


def _is_ob(player: PillarPlayerInfo) -> bool:
    """OB・レジェンド (ob_profile あり) なら True。"""
    return bool(player.ob_profile)


def _ob_npb_line(npb: dict, ptype: str) -> str:
    """OB の NPB 通算 stat 行。 0/欠損 field は省く。"""
    parts: list[str] = []
    if ptype == "pitcher":
        if npb.get("games"):
            parts.append(f"登板{npb['games']}")
        if npb.get("w"):
            parts.append(f"{npb['w']}勝")
        if npb.get("l"):
            parts.append(f"{npb['l']}敗")
        if npb.get("era"):
            parts.append(f"防御率{npb['era']}")
        if npb.get("k"):
            parts.append(f"奪三振{npb['k']}")
    else:
        if npb.get("games"):
            parts.append(f"{npb['games']}試合")
        if npb.get("avg"):
            parts.append(f"打率{npb['avg']}")
        if npb.get("hits"):
            parts.append(f"安打{npb['hits']}")
        if npb.get("hr"):
            parts.append(f"本塁打{npb['hr']}")
        if npb.get("rbi"):
            parts.append(f"打点{npb['rbi']}")
    return "　".join(parts)


def _ob_mlb_line(mlb: dict, ptype: str) -> str:
    """OB の MLB 行 (note があれば優先、 なければ stat)。"""
    if mlb.get("note"):
        return str(mlb["note"])
    parts: list[str] = []
    if ptype == "pitcher":
        if mlb.get("w"):
            parts.append(f"{mlb['w']}勝")
        if mlb.get("sv"):
            parts.append(f"{mlb['sv']}セーブ")
        if mlb.get("era"):
            parts.append(f"防御率{mlb['era']}")
    else:
        if mlb.get("avg"):
            parts.append(f"打率{mlb['avg']}")
        if mlb.get("hr"):
            parts.append(f"本塁打{mlb['hr']}")
        if mlb.get("rbi"):
            parts.append(f"打点{mlb['rbi']}")
    return "　".join(parts)


def _build_ob_html(player: PillarPlayerInfo) -> str:
    """OB・レジェンド profile (現役通算の看板 stat + MLB + 代表実績)。"""
    ob = player.ob_profile or {}
    ptype = ob.get("type", "batter")
    years = _esc(str(ob.get("years", "")))
    teams = _esc(str(ob.get("teams", "")))
    npb_line = _ob_npb_line(ob.get("npb") or {}, ptype)
    mlb_line = _ob_mlb_line(ob.get("mlb") or {}, ptype) if ob.get("mlb") else ""
    honors = ob.get("honors") or []
    honors_html = "".join(f'<li style="margin:4px 0;">{_esc(h)}</li>' for h in honors)
    rows = ""
    if npb_line:
        rows += (
            '<tr style="border-bottom:1px solid #eee;">'
            '<th style="padding:8px 10px;text-align:left;background:#fafafa;white-space:nowrap;">NPB通算</th>'
            f'<td style="padding:8px 10px;">{_esc(npb_line)}</td></tr>'
        )
    if mlb_line:
        rows += (
            '<tr style="border-bottom:1px solid #eee;">'
            '<th style="padding:8px 10px;text-align:left;background:#fafafa;white-space:nowrap;">MLB</th>'
            f'<td style="padding:8px 10px;">{_esc(mlb_line)}</td></tr>'
        )
    return (
        '<section class="ys-pillar-ob-profile" '
        'style="background:#fff;border:1px solid #eee;padding:16px;margin:0 0 16px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">{_esc(player.name)} '
        f'<span style="font-size:12px;color:#5d4037;font-weight:600;">（巨人OB・レジェンド{f" / {years}" if years else ""}）</span></h2>'
        + (f'<p style="font-size:12px;color:#666;margin:0 0 10px;">所属: {teams}</p>' if teams else "")
        + (f'<table style="width:100%;border-collapse:collapse;font-size:13px;margin:0 0 12px;"><tbody>{rows}</tbody></table>' if rows else "")
        + (f'<h3 style="font-size:14px;margin:0 0 6px;color:#5d4037;">代表実績</h3><ul style="font-size:13px;line-height:1.6;margin:0;padding-left:20px;">{honors_html}</ul>' if honors_html else "")
        + '</section>'
    )


def _is_staff(player: PillarPlayerInfo) -> bool:
    """監督 / コーチ なら True (stats section omit、 profile section に分岐)."""
    return (player.role or "").strip() in ("manager", "coach")


def _build_staff_career_html(player: PillarPlayerInfo) -> str:
    """監督・コーチ の現役選手時代 NPB 通算成績 (config 由来)。 無ければ空。"""
    cs = player.career_stats
    if not cs:
        return ""
    years = _esc(str(cs.get("years", "")))
    if cs.get("type") == "pitcher":
        cells = [
            ("登板", cs.get("games")),
            ("勝利", cs.get("w")),
            ("敗戦", cs.get("l")),
            ("防御率", cs.get("era")),
            ("奪三振", cs.get("k")),
        ]
    else:
        cells = [
            ("試合", cs.get("games")),
            ("打率", cs.get("avg")),
            ("安打", cs.get("hits")),
            ("本塁打", cs.get("hr")),
            ("打点", cs.get("rbi")),
        ]
        if cs.get("sb") is not None:
            cells.append(("盗塁", cs.get("sb")))
    head = "".join(f'<th style="padding:8px 6px;">{_esc(label)}</th>' for label, _ in cells)
    body = "".join(
        f'<td style="padding:8px 6px;text-align:center;'
        f'{"color:#1976d2;font-weight:600;" if label in ("打率","防御率") else "color:#555;"}">{_esc(val)}</td>'
        for label, val in cells
    )
    return (
        '<section class="ys-pillar-career-stats" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 6px;">現役時代 通算成績 <span style="font-size:11px;color:#888;font-weight:normal;">(NPB{f" {years}" if years else ""})</span></h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 10px;">選手として残した NPB 通算記録。</p>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f'<thead><tr style="background:#fafafa;text-align:center;">{head}</tr></thead>'
        f'<tbody><tr style="text-align:center;">{body}</tr></tbody></table>'
        '</section>'
    )


def _build_staff_profile_html(player: PillarPlayerInfo) -> str:
    """監督・コーチ 用 profile section (stats 無し)。 役職を主役に、 関連記事へ誘導。"""
    role_label = "監督" if (player.role or "").strip() == "manager" else "コーチ"
    position = (player.position or "").strip() or role_label
    return (
        '<section class="ys-pillar-staff-profile" '
        'style="background:#fff;border:1px solid #eee;padding:16px;margin:0 0 16px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">{_esc(player.name)} <span style="font-size:13px;color:#5d4037;font-weight:600;">（{_esc(position)}）</span></h2>'
        '<p style="font-size:13px;line-height:1.7;color:#444;margin:0 0 8px;">'
        f'読売ジャイアンツ {_esc(position)}。 試合での采配・指導や、 関連する最新ニュースをまとめています。'
        '</p>'
        '<p style="font-size:12px;color:#888;margin:0;">'
        f'※ {role_label}のため打撃・投手成績の集計対象外です。 最新の動向は下記の関連記事をご覧ください。'
        '</p>'
        '</section>'
    )


def _build_streak_html(player: PillarPlayerInfo) -> str:
    """連続記録 (Phase 1.0b1 metric pack #3/#4)。 active streak がゼロでも season_max があれば section 出す。"""
    if (player.hit_streak_active + player.hit_streak_season_max
            + player.contribution_streak_active + player.contribution_streak_season_max) == 0:
        return ""
    hit_active_html = (
        f'<span style="color:#d32f2f;font-weight:700;font-size:18px;">{player.hit_streak_active} 試合連続</span>'
        if player.hit_streak_active > 0
        else '<span style="color:#888;">途切れ</span>'
    )
    contrib_active_html = (
        f'<span style="color:#d32f2f;font-weight:700;font-size:18px;">{player.contribution_streak_active} 試合連続</span>'
        if player.contribution_streak_active > 0
        else '<span style="color:#888;">途切れ</span>'
    )
    return (
        '<section class="ys-pillar-streak" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 6px;">連続記録 <span style="font-size:11px;color:#888;font-weight:normal;">(大手未掲載)</span></h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 10px;">'
        '今シーズンの 連続安打 / 連続得点関与 を baseline で追跡。 「○○試合連続」 が記事になる前の段階で永続表示。'
        '</p>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:8px 6px;">指標</th>'
        '<th style="padding:8px 6px;">現在</th>'
        '<th style="padding:8px 6px;">今シーズン最長</th>'
        '</tr></thead>'
        '<tbody>'
        '<tr style="text-align:center;border-bottom:1px solid #eee;">'
        '<td style="padding:10px;font-weight:600;color:#5d4037;">連続安打</td>'
        f'<td style="padding:10px;">{hit_active_html}</td>'
        f'<td style="padding:10px;">{player.hit_streak_season_max} 試合</td>'
        '</tr>'
        '<tr style="text-align:center;">'
        '<td style="padding:10px;font-weight:600;color:#5d4037;">連続得点関与 <span style="font-size:11px;color:#888;">(得点 + 打点 ≥ 1)</span></td>'
        f'<td style="padding:10px;">{contrib_active_html}</td>'
        f'<td style="padding:10px;">{player.contribution_streak_season_max} 試合</td>'
        '</tr>'
        '</tbody></table>'
        '</section>'
    )


def _build_prosports_html(player: PillarPlayerInfo) -> str:
    """姉妹サイト prosports の同一選手 人物・家族記事への導線 (相互リンクの本体側)。"""
    if not player.prosports_links:
        return ""
    items = "\n".join(
        f'<li style="margin:6px 0;"><a href="{_esc(url)}" '
        f'style="color:#1976d2;text-decoration:none;">{_esc(title)}</a></li>'
        for url, title in player.prosports_links[:5]
    )
    return (
        '<section class="ys-pillar-prosports" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">📖 {_esc(player.name)}の人物・家族の読み物</h2>'
        '<p style="font-size:12px;color:#777;margin:0 0 8px;">姉妹サイト「スポーツ選手の実家や結婚家族が気になる」の人物記事。</p>'
        f'<ul style="font-size:13px;line-height:1.7;margin:0;padding-left:20px;">{items}</ul>'
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


def _build_related_players_html(player: PillarPlayerInfo) -> str:
    """関連選手 (同じ登録ポジションの他選手) への内部リンク (spoke↔spoke)。

    同ポジションの選手を横断回遊させ、 トピッククラスタの横リンクを補強する。
    """
    if not player.related_players:
        return ""
    pos = (player.position or "").strip()
    heading = f"同じ{pos}の選手" if pos else "関連選手"
    chips = "\n".join(
        f'<a href="/data/{_esc(slug)}" '
        'style="display:inline-block;margin:4px 6px 4px 0;padding:6px 12px;background:#fff8e1;'
        'border:1px solid #ffe082;border-radius:16px;color:#5d4037;text-decoration:none;font-size:13px;">'
        f'{_esc(name)}</a>'
        for slug, name in player.related_players
    )
    return (
        '<section class="ys-pillar-related-players" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">{_esc(heading)}</h2>'
        f'<div>{chips}</div>'
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
    canonical = f"{SITE_BASE}/data/{player.slug}"
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
    # エンティティ強化: ポジション (登録区分) + 背番号 を additionalProperty で明示。
    # Google の選手⇔ポジション⇔背番号 理解を助ける (knowledge graph 連携の素地)。
    add_props = []
    if player.position:
        add_props.append({"@type": "PropertyValue", "name": "ポジション", "value": player.position})
    if player.jersey_number:
        add_props.append({"@type": "PropertyValue", "name": "背番号", "value": str(player.jersey_number)})
    if add_props:
        sports_player["additionalProperty"] = add_props
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


def _build_profile_html(player: PillarPlayerInfo) -> str:
    """467: NPB 公式 career page 由来のプロフィール (生年月日 / 身長体重 / 投打 / 経歴 / ドラフト)。

    ライバル (my-favorite-giants / baseballdata) が持つ「基本情報」の核。 取れた項目だけ出す。
    """
    career = player.npb_career or {}
    prof = career.get("profile") or {}
    if not prof:
        return ""
    rows = [
        ("生年月日", prof.get("birthdate")),
        ("身長／体重", prof.get("height_weight")),
        ("投打", prof.get("bats_throws")),
        ("ポジション", prof.get("position")),
        ("経歴", prof.get("school")),
        ("ドラフト", prof.get("draft")),
    ]
    cells = "".join(
        f'<tr><th style="text-align:left;background:var(--ol);color:var(--od);'
        f'padding:8px 10px;width:96px;white-space:nowrap;border-bottom:1px solid #f2e6dd;">{_esc(label)}</th>'
        f'<td style="text-align:left;padding:8px 10px;border-bottom:1px solid #f2e6dd;">{_esc(val)}</td></tr>'
        for (label, val) in rows if val
    )
    if not cells:
        return ""
    return (
        '<div class="ys-card">'
        '<h2>プロフィール</h2>'
        '<table><tbody>' + cells + '</tbody></table>'
        '<p class="ys-foot">※ NPB 公式選手データより。</p>'
        '</div>'
    )


def _career_table_html(title: str, stats: dict, accent_cols: tuple) -> str:
    """年度別 + 通算 の横スクロール表 1 枚を組む。 stats = {columns, years, total}。"""
    columns = stats.get("columns") or []
    years = stats.get("years") or []
    total = stats.get("total")
    if not columns or (not years and not total):
        return ""
    head = "".join(f"<th>{_esc(c)}</th>" for c in columns)

    def row_html(row: dict, is_total: bool) -> str:
        tds = []
        for i, col in enumerate(columns):
            val = row.get(col, "")
            cls = ""
            if i == 0:
                cls = ' class="ys-k"'
            elif col in accent_cols:
                cls = ' class="ys-avg"'
            tds.append(f"<td{cls}>{_esc(val)}</td>")
        style = ' style="background:var(--od);color:#fff;font-weight:800;"' if is_total else ""
        return f"<tr{style}>{''.join(tds)}</tr>"

    body = "\n".join(row_html(y, False) for y in years)
    if total:
        body += "\n" + row_html(total, True)
    # 列数が多い (23-24) ため横スクロール wrapper で網羅表示。
    return (
        f'<h3 style="font-size:14px;margin:14px 0 6px;color:var(--ink);">{_esc(title)}</h3>'
        '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;">'
        '<table style="min-width:640px;white-space:nowrap;">'
        f'<thead><tr>{head}</tr></thead>'
        f'<tbody>{body}</tbody></table></div>'
    )


def _render_milestones_block(milestones: list) -> str:
    """468-2: 節目到達 list (dict: label/milestone/year/cum_games/games_unit) を 1 枚の card に。

    現役 (年度別から live 計算) と OB (precomputed JSON) で共通利用。 空なら空文字。
    """
    if not milestones:
        return ""
    items = []
    for m in milestones:
        label = _esc(str(m.get("label") or ""))
        ms = _esc(str(m.get("milestone") or ""))
        year = _esc(str(m.get("year") or ""))
        cum = _esc(str(m.get("cum_games") or ""))
        unit = _esc(str(m.get("games_unit") or "試合"))
        items.append(
            f'<li style="margin:0 0 8px;padding:0 0 0 4px;">'
            f'<b style="font-size:15px;">通算{ms}{label}</b>'
            f'<span style="color:#e25400;font-weight:600;"> — {year}年に到達</span>'
            f'<span style="color:#888;font-size:12px;">（同年終了時 通算{cum}{unit}）</span>'
            f'</li>'
        )
    return (
        '<div class="ys-card">'
        '<h2>通算節目の到達 <span class="ys-tag">マイルストーン</span></h2>'
        '<p class="ys-note">丸い通算記録に到達した年と、 そのシーズン終了時点の通算試合数。 '
        '試合単位の正確な到達日は公式記録に無いため、 年単位の到達で示しています。</p>'
        '<ul style="list-style:none;padding:0;margin:0;">' + "\n".join(items) + '</ul>'
        '</div>'
    )


def _build_career_milestones_html(player: PillarPlayerInfo) -> str:
    """468-2: 現役選手の通算節目の到達点 (年度別行から決定的に計算、 到達なしなら空)。

    計算は ``compute_career_milestones`` (年度別累計を total 行で検算) に委譲。
    """
    from src.npb_career_scraper import compute_career_milestones

    return _render_milestones_block(compute_career_milestones(player.npb_career or {}))


@_functools.lru_cache(maxsize=1)
def _load_ob_milestones_map() -> dict:
    """468-2 Phase2: レジェンドの precomputed 節目 (config/ob_career_milestones.json)。"""
    path = _os.path.join(_os.path.dirname(__file__), "..", "config", "ob_career_milestones.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return _json.load(fh).get("milestones") or {}
    except Exception:
        return {}


def _build_ob_milestones_html(player: PillarPlayerInfo) -> str:
    """468-2 Phase2: OB・レジェンドの通算節目 (precomputed、 ob_legends 通算で検算済)。"""
    return _render_milestones_block(_load_ob_milestones_map().get(player.name or "") or [])


def _build_career_history_html(player: PillarPlayerInfo) -> str:
    """467: 年度別成績 + 通算 (NPB 公式 career page、 移籍履歴含む全列網羅)。

    投手は投手成績を主、 打者/野手は打撃成績を主に出す。 投手の打撃は出さない (冗長回避)。
    """
    career = player.npb_career or {}
    if not career:
        return ""
    batting = career.get("batting") or {}
    pitching = career.get("pitching") or {}
    is_pitcher = bool(career.get("is_pitcher"))

    tables = []
    if is_pitcher and (pitching.get("years") or pitching.get("total")):
        tables.append(_career_table_html("投手成績", pitching, ("防御率",)))
    elif batting.get("years") or batting.get("total"):
        tables.append(_career_table_html("打撃成績", batting, ("打率", "出塁率", "長打率")))
    tables = [t for t in tables if t]
    if not tables:
        return ""
    return (
        '<div class="ys-card">'
        '<h2>年度別成績・通算 <span class="ys-tag">NPB全記録</span></h2>'
        '<p class="ys-note">入団からの年度別成績と通算記録 (移籍履歴を含む)。 横スクロールで全項目を表示。</p>'
        + "\n".join(tables) +
        '<p class="ys-foot">※ NPB 公式選手データより。 当該シーズン途中の数値は試合進行に応じて更新されます。</p>'
        '</div>'
    )


@_functools.lru_cache(maxsize=1)
def _salary_slugs() -> frozenset:
    """年俸ページ (/data/salary/<slug>) を持つ slug 集合 (giants_salary.json 正本)。"""
    path = _os.path.join(_os.path.dirname(__file__), "..", "config",
                         "giants_salary.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
        return frozenset(p["slug"] for p in data.get("players", []))
    except Exception:
        return frozenset()


def _build_salary_link_html(player: PillarPlayerInfo) -> str:
    """年俸推移ページへの cross link (トピクラ: pillar ↔ salary spoke 双方向)。"""
    if player.slug not in _salary_slugs():
        return ""
    return (
        '<div class="ys-card" style="font-size:13px;">'
        f'<a href="/data/salary/{_esc(player.slug)}" '
        'style="color:#e25400;font-weight:600;text-decoration:none;">'
        f'💰 {_esc(player.name)}の年俸推移（契約金・通算年俸）はこちら</a>'
        '</div>'
    )


def _build_datasite_nav_html() -> str:
    """データサイト内ナビ (トピクラ: pillar=中心 → hub/ranking/team spoke 回遊、 458 データ側)。"""
    return (
        '<div class="ys-card" style="text-align:center;font-size:13px;">'
        '<span style="color:#888;">データサイト内: </span>'
        '<a href="/data" style="color:#e25400;font-weight:600;text-decoration:none;">全選手一覧</a>　/　'
        '<a href="/data/ranking" style="color:#e25400;font-weight:600;text-decoration:none;">選手ランキング</a>　/　'
        '<a href="/data/team" style="color:#e25400;font-weight:600;text-decoration:none;">チーム成績</a>'
        '</div>'
    )


def render_pillar_html(player: PillarPlayerInfo) -> str:
    """Pillar page の WP post.content として入る HTML を返す.

    WP page template は別途調整 (theme 側で <header>/<footer> 入る)、
    本関数は post.content (= 本文) のみ返す。
    """
    if not player.name or not player.slug:
        raise ValueError("PillarPlayerInfo.name and .slug are required")
    # OB・レジェンド は OB profile、 監督・コーチ は staff profile、 投手 / 打者 に分岐
    if _is_ob(player):
        stats_sections = [
            _build_ob_html(player),
            _build_ob_milestones_html(player),
            # OB も年度別フル表を出す (npb_career を benchmark 由来で populate)。
            # ベンチマーク同等の「年度ごと」詳細。 データが無ければ空文字で安全。
            _build_career_history_html(player),
        ]
    elif _is_staff(player):
        stats_sections = [
            _build_staff_profile_html(player),
            _build_staff_career_html(player),
        ]
    elif _is_pitcher(player):
        stats_sections = [
            _build_pitching_season_html(player),
            _build_farm_stats_html(player),
            _build_pitching_recent_html(player),
            _build_pitch_opponent_split_html(player),
            _build_pitch_venue_split_html(player),
            _build_pitch_weekday_split_html(player),
            _build_pitch_month_split_html(player),
            _build_pitch_interleague_split_html(player),
            _build_sabermetrics_html(player),
            _build_career_milestones_html(player),
            _build_career_history_html(player),
        ]
    else:
        stats_sections = [
            _build_season_stats_html(player),
            _build_farm_stats_html(player),
            _build_streak_html(player),
            _build_recent_games_html(player),
            _build_lineup_slot_html(player),
            _build_opponent_split_html(player),
            _build_venue_split_html(player),
            _build_inning_split_html(player),
            _build_weekday_split_html(player),
            _build_month_split_html(player),
            _build_interleague_split_html(player),
            _build_risp_split_html(player),
            _build_vs_lr_split_html(player),
            _build_sabermetrics_html(player),
            _build_career_milestones_html(player),
            _build_career_history_html(player),
        ]
    sections = [
        _build_lead_html(player),
        _build_breadcrumb_html(player.name),
        _build_featured_image_html(player),
        _build_profile_html(player),
        _build_short_review_html(player),
        _build_player_prose(player),  # SEO: split を index される解説文に
        *stats_sections,
        _build_prosports_html(player),
        _build_related_topic_html(player),
        _build_related_players_html(player),
        _build_salary_link_html(player),
        _build_datasite_nav_html(),
        _build_back_link_html(),
        _build_jsonld(player),
    ]
    body = "\n".join(s for s in sections if s)
    # 巨人=オレンジの scoped デザインシステムでページ全体を包む (453/452 デザイン刷新)。
    return _build_style_block() + '\n<div class="ys-data">\n' + body + "\n</div>"


# SEO long-tail 用シーズン表記。 毎シーズンこの 1 行を置換するだけ
# (slug/URL は不変)。 data_site_template_cluster.SEASON_LABEL と同期すること。
SEASON_LABEL = "2026年"


def render_pillar_title(player: PillarPlayerInfo) -> str:
    """WP page.title = SEO 検索表示用。

    選手名直後に検索意図語 (シーズン年 + 成績 + 打率/防御率) を前寄せして
    「坂本勇人 2026 成績」 等の long-tail を拾う。 役割で軸を分ける:
    - 現役の監督・コーチ: 当年 (2026) 巨人組織の一員のため年を付け、 軸は
      現役時代の通算成績・プロフィール (「阿部慎之助 2026 監督」 を拾う)
    - OB・レジェンド: 歴史枠で当年シーズン非該当のため年を付けない
    - 現役選手: 年 + 成績 + 打率/防御率
    suffix は既存のブランド一貫性のため「| 巨人選手データ」 を維持。
    """
    num = f"・背番号{player.jersey_number}" if player.jersey_number else ""
    pos = player.position or ""
    bracket = f"【巨人 {pos}{num}】" if pos else "【巨人】"
    is_ob = player.role == "ob" or player.ob_profile is not None
    if is_ob:
        head = f"{player.name} 通算成績・プロフィール"
    elif player.role in ("manager", "coach"):
        head = f"{player.name} {SEASON_LABEL} 通算成績・プロフィール"
    elif "投手" in pos:
        head = f"{player.name} {SEASON_LABEL}成績・防御率"
    else:
        head = f"{player.name} {SEASON_LABEL}成績・打率"
    return f"{head}{bracket} | 巨人選手データ"


def render_pillar_excerpt(player: PillarPlayerInfo) -> str:
    """WP page.excerpt = SNS 共有 / 検索の meta description。

    SEO SIMPLE PACK は excerpt を og:description / meta description に使う。 excerpt 未設定だと
    本文 (パンくず + 成績表) から自動生成され「Home › 巨人選手データ › … 238820.227384」 等の
    崩れたプレビューになり共有 CTR を落とすため、 役割別にクリーンな 1 文を返す。
    """
    name = player.name
    pos = player.position or "選手"
    is_ob = player.role == "ob" or player.ob_profile is not None
    if is_ob:
        # ~800 OB ページが同一定型文だと重複シグナルになるため、台帳の事実
        # (在籍年 / 通算成績 / 代表実績) からページ固有の 1 文を組み立てる。
        ob = player.ob_profile or {}
        years = str(ob.get("years") or "").strip()
        npb = ob.get("npb") or {}
        parts = []
        if ob.get("type") == "pitcher":
            if npb.get("games"):
                parts.append(f'通算{npb["games"]}登板')
            if npb.get("w"):
                parts.append(f'{npb["w"]}勝')
            if npb.get("era"):
                parts.append(f'防御率{npb["era"]}')
            if npb.get("k"):
                parts.append(f'{npb["k"]}奪三振')
        else:
            if npb.get("games"):
                parts.append(f'通算{npb["games"]}試合')
            if npb.get("avg"):
                parts.append(f'打率{npb["avg"]}')
            if npb.get("hits"):
                parts.append(f'{npb["hits"]}安打')
            if npb.get("hr"):
                parts.append(f'{npb["hr"]}本塁打')
        honor = str((ob.get("honors") or [""])[0]).strip()
        kind = "投手" if ob.get("type") == "pitcher" else "野手"
        lead = f"{name}（元巨人・{kind}" + (f"、巨人在籍{years}" if years else "") + "）の選手データ。"
        if parts:
            lead += "・".join(parts) + "。"
        if honor:
            lead += f"{honor}。"
        lead += "年度別成績と関連ニュースをまとめた巨人OBデータページ。"
        return lead
    if player.role in ("manager", "coach"):
        return f"{name}（巨人{pos}）のプロフィールと現役時代の通算成績。関連ニュースもまとめた巨人選手データ。"
    if "投手" in pos and player.has_pitching_stats:
        era = f"・防御率{player.pitch_era:.2f}" if player.pitch_era is not None else ""
        return (
            f"{name}の{SEASON_LABEL}投手成績。{player.pitch_wins}勝{player.pitch_losses}敗{era}、"
            f"{player.pitch_k}奪三振。登板イニング別・対戦相手別など、大手にない巨人投手データ。"
        )
    if player.has_stats:
        avg = f"打率{_fmt_avg(player.season_avg)}・" if player.season_avg is not None else ""
        return (
            f"{name}の{SEASON_LABEL}打撃成績。{avg}{player.season_hits}安打{player.season_rbi}打点。"
            f"本拠地/ビジター別・序盤/中盤/終盤別の打率など、大手にない巨人選手データ。"
        )
    return f"{name}（巨人{pos}）の{SEASON_LABEL}成績・データページ。打撃成績や関連ニュースをまとめた巨人選手データ。"


__all__ = [
    "PillarPlayerInfo",
    "render_pillar_html",
    "render_pillar_title",
    "render_pillar_excerpt",
    "CLUSTER_URL",
    "SITE_BASE",
]
