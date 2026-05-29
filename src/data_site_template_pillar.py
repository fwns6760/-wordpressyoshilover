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

import html as _html
import json as _json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PillarPlayerInfo:
    """1 Pillar page を作るのに必要な最小情報。"""

    name: str               # canonical 表記 (例: 吉川尚輝)
    slug: str               # URL slug (例: yoshikawa-naoki)
    position: str           # 内野手 / 外野手 / 投手 / 監督 / コーチ
    jersey_number: str      # 背番号 文字列 (例: "2" / "92")
    role: str = "player"    # player / manager / coach
    featured_image_url: str = ""   # H1 直下に出す写真 URL (空なら team mark)
    short_review: str = ""  # AI 短評 200-500 字 (空なら section omit)
    related_topic_links: list[tuple[str, str]] = field(default_factory=list)
    # related_topic_links = [(url, title), ...] (既存記事の link、 関連 Topic = Pillar → Topic)

    # Phase 1.0 stats (insight.db 由来、 None なら placeholder)
    season_games: int = 0
    season_ab: int = 0
    season_hits: int = 0
    season_rbi: int = 0
    season_runs: int = 0
    season_sb: int = 0
    season_avg: Optional[float] = None
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
    has_pitching_stats: bool = False
    recent_pitching_games: list[tuple[str, str, str, float, int, int, int, int]] = field(default_factory=list)
    # recent_pitching_games = [(date, opp, result_mark, ip, h, k, bb, er), ...]


CLUSTER_URL = "https://yoshilover.com/data/"
SITE_BASE = "https://yoshilover.com"


def _esc(text: str) -> str:
    """HTML escape helper (空文字 safe)。"""
    return _html.escape(str(text or ""), quote=True)


def _build_breadcrumb_html(name: str) -> str:
    """Pillar 上部の breadcrumb (Home → 選手データ → {player})。"""
    return (
        '<nav class="ys-breadcrumb" aria-label="breadcrumb" '
        'style="font-size:12px;color:#666;margin:0 0 12px;">'
        '<a href="https://yoshilover.com/" style="color:#666;">Home</a> › '
        f'<a href="{CLUSTER_URL}" style="color:#666;">巨人選手データ</a> › '
        f'<span>{_esc(name)}</span>'
        '</nav>'
    )


def _build_featured_image_html(player: PillarPlayerInfo) -> str:
    if not player.featured_image_url:
        return ""
    return (
        '<div class="ys-pillar-featured" style="text-align:center;margin:0 0 16px;">'
        f'<img src="{_esc(player.featured_image_url)}" '
        f'alt="{_esc(player.name)}選手" '
        'style="max-width:480px;width:100%;height:auto;border-radius:8px;'
        'box-shadow:0 2px 6px rgba(0,0,0,0.1);" />'
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
            '<section class="ys-pillar-stats-season" '
            'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
            '<h2 style="font-size:16px;margin:0 0 10px;">今シーズン 通算 (打撃)</h2>'
            '<p style="font-size:13px;color:#888;margin:0;">'
            f'{_esc(player.name)}選手の今シーズン 一軍出場記録は、 現時点で集計対象となる box score 上に確認できていません。'
            ' 出場が記録され次第、 毎朝 6:00 + 試合後 17:30 / 23:00 JST に自動反映されます。'
            '</p>'
            '</section>'
        )
    avg = _fmt_avg(player.season_avg)
    return (
        '<section class="ys-pillar-stats-season" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 10px;">今シーズン 通算 (打撃)</h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:14px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:8px 6px;">試合</th>'
        '<th style="padding:8px 6px;">打数</th>'
        '<th style="padding:8px 6px;">安打</th>'
        '<th style="padding:8px 6px;">打率</th>'
        '<th style="padding:8px 6px;">打点</th>'
        '<th style="padding:8px 6px;">得点</th>'
        '<th style="padding:8px 6px;">盗塁</th>'
        '</tr></thead>'
        '<tbody><tr style="text-align:center;">'
        f'<td style="padding:8px 6px;">{player.season_games}</td>'
        f'<td style="padding:8px 6px;">{player.season_ab}</td>'
        f'<td style="padding:8px 6px;">{player.season_hits}</td>'
        f'<td style="padding:8px 6px;font-weight:600;color:#1976d2;">{avg}</td>'
        f'<td style="padding:8px 6px;">{player.season_rbi}</td>'
        f'<td style="padding:8px 6px;">{player.season_runs}</td>'
        f'<td style="padding:8px 6px;">{player.season_sb}</td>'
        '</tr></tbody></table>'
        '<p style="font-size:11px;color:#999;margin:8px 0 0;">'
        '※ insight.db 集計 (NPB official box score 由来)、 毎朝 6:00 JST 更新'
        '</p></section>'
    )


def _build_recent_games_html(player: PillarPlayerInfo) -> str:
    """直近 5 試合の打撃結果表。 data 無ければ section omit。"""
    if not player.recent_games:
        return ""
    rows_html = "\n".join(
        '<tr style="text-align:center;border-bottom:1px solid #eee;">'
        f'<td style="padding:6px;">{_esc(date)}</td>'
        f'<td style="padding:6px;">{_esc(opp)}</td>'
        f'<td style="padding:6px;">{ab}</td>'
        f'<td style="padding:6px;font-weight:600;">{h}</td>'
        f'<td style="padding:6px;">{rbi}</td>'
        '</tr>'
        for (date, opp, ab, h, rbi) in player.recent_games
    )
    return (
        '<section class="ys-pillar-recent" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        f'<h2 style="font-size:16px;margin:0 0 10px;">直近 {len(player.recent_games)} 試合</h2>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:8px 6px;">日付</th>'
        '<th style="padding:8px 6px;">相手</th>'
        '<th style="padding:8px 6px;">打数</th>'
        '<th style="padding:8px 6px;">安打</th>'
        '<th style="padding:8px 6px;">打点</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</section>'
    )


def _build_lineup_slot_html(player: PillarPlayerInfo) -> str:
    """打順別 打率 (大手未掲載 metric pack #1)。"""
    if not player.lineup_slot_stats:
        return ""
    rows_html = "\n".join(
        '<tr style="text-align:center;border-bottom:1px solid #eee;">'
        f'<td style="padding:6px;font-weight:600;color:#5d4037;">{slot} 番</td>'
        f'<td style="padding:6px;">{g}</td>'
        f'<td style="padding:6px;">{ab}</td>'
        f'<td style="padding:6px;font-weight:600;">{h}</td>'
        f'<td style="padding:6px;color:#1976d2;font-weight:600;">{_fmt_avg(avg)}</td>'
        f'<td style="padding:6px;">{rbi}</td>'
        '</tr>'
        for (slot, g, ab, h, rbi, avg) in player.lineup_slot_stats
    )
    return (
        '<section class="ys-pillar-lineup-split" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 6px;">打順別 成績 <span style="font-size:11px;color:#888;font-weight:normal;">(大手未掲載)</span></h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 10px;">'
        'どの打順で起用された時に結果を残せているか、 一目で分かる split data。'
        '</p>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:8px 6px;">打順</th>'
        '<th style="padding:8px 6px;">試合</th>'
        '<th style="padding:8px 6px;">打数</th>'
        '<th style="padding:8px 6px;">安打</th>'
        '<th style="padding:8px 6px;">打率</th>'
        '<th style="padding:8px 6px;">打点</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</section>'
    )


def _build_opponent_split_html(player: PillarPlayerInfo) -> str:
    """vs 各球団 打率 (大手未掲載 metric pack #2)。"""
    if not player.opponent_split_stats:
        return ""
    rows_html = "\n".join(
        '<tr style="text-align:center;border-bottom:1px solid #eee;">'
        f'<td style="padding:6px;font-weight:600;color:#5d4037;">{_esc(opp)}</td>'
        f'<td style="padding:6px;">{g}</td>'
        f'<td style="padding:6px;">{ab}</td>'
        f'<td style="padding:6px;font-weight:600;">{h}</td>'
        f'<td style="padding:6px;color:#1976d2;font-weight:600;">{_fmt_avg(avg)}</td>'
        f'<td style="padding:6px;">{rbi}</td>'
        '</tr>'
        for (opp, g, ab, h, rbi, avg) in player.opponent_split_stats
    )
    return (
        '<section class="ys-pillar-opp-split" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 6px;">vs 各球団 成績 <span style="font-size:11px;color:#888;font-weight:normal;">(大手未掲載)</span></h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 10px;">'
        '対戦相手別の相性。 得意 / 苦手な球団が浮き出る。'
        '</p>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:8px 6px;">相手</th>'
        '<th style="padding:8px 6px;">試合</th>'
        '<th style="padding:8px 6px;">打数</th>'
        '<th style="padding:8px 6px;">安打</th>'
        '<th style="padding:8px 6px;">打率</th>'
        '<th style="padding:8px 6px;">打点</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</section>'
    )


def _build_venue_split_html(player: PillarPlayerInfo) -> str:
    """本拠地 / ビジター 別 打率 (大手未掲載 metric pack #venue)。"""
    if not player.venue_split_stats:
        return ""
    rows_html = "\n".join(
        '<tr style="text-align:center;border-bottom:1px solid #eee;">'
        f'<td style="padding:6px;font-weight:600;color:#5d4037;">{_esc(venue)}</td>'
        f'<td style="padding:6px;">{g}</td>'
        f'<td style="padding:6px;">{ab}</td>'
        f'<td style="padding:6px;font-weight:600;">{h}</td>'
        f'<td style="padding:6px;color:#1976d2;font-weight:600;">{_fmt_avg(avg)}</td>'
        f'<td style="padding:6px;">{rbi}</td>'
        '</tr>'
        for (venue, g, ab, h, rbi, avg) in player.venue_split_stats
    )
    return (
        '<section class="ys-pillar-venue-split" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 6px;">本拠地 / ビジター 別 成績 <span style="font-size:11px;color:#888;font-weight:normal;">(大手未掲載)</span></h2>'
        '<p style="font-size:12px;color:#666;margin:0 0 10px;">'
        '東京ドーム (本拠地) と 敵地 (ビジター) でどう違うか。 home / away の相性が見える split data。'
        '</p>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr style="background:#fafafa;text-align:center;">'
        '<th style="padding:8px 6px;">球場</th>'
        '<th style="padding:8px 6px;">試合</th>'
        '<th style="padding:8px 6px;">打数</th>'
        '<th style="padding:8px 6px;">安打</th>'
        '<th style="padding:8px 6px;">打率</th>'
        '<th style="padding:8px 6px;">打点</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody></table>'
        '</section>'
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
            '<h2 style="font-size:16px;margin:0 0 10px;">今シーズン 通算 (投手)</h2>'
            '<p style="font-size:13px;color:#888;margin:0;">'
            f'{_esc(player.name)}投手の今シーズン 一軍登板記録は、 現時点で集計対象となる box score 上に確認できていません。'
            ' 登板が記録され次第、 毎朝 6:00 + 試合後 17:30 / 23:00 JST に自動反映されます。'
            '</p>'
            '</section>'
        )
    return (
        '<section class="ys-pillar-pitch-season" '
        'style="background:#fff;border:1px solid #eee;padding:14px;margin:0 0 16px;border-radius:4px;">'
        '<h2 style="font-size:16px;margin:0 0 10px;">今シーズン 通算 (投手)</h2>'
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


def _is_pitcher(player: PillarPlayerInfo) -> bool:
    """position が「投手」 なら True (打撃 section omit)."""
    return (player.position or "").strip() == "投手"


def _is_staff(player: PillarPlayerInfo) -> bool:
    """監督 / コーチ なら True (stats section omit、 profile section に分岐)."""
    return (player.role or "").strip() in ("manager", "coach")


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
    canonical = f"{SITE_BASE}/data/{player.slug}/"
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


def render_pillar_html(player: PillarPlayerInfo) -> str:
    """Pillar page の WP post.content として入る HTML を返す.

    WP page template は別途調整 (theme 側で <header>/<footer> 入る)、
    本関数は post.content (= 本文) のみ返す。
    """
    if not player.name or not player.slug:
        raise ValueError("PillarPlayerInfo.name and .slug are required")
    # 監督・コーチ は profile section、 position=投手 は投手 section、 その他は打撃 section に分岐
    if _is_staff(player):
        stats_sections = [
            _build_staff_profile_html(player),
        ]
    elif _is_pitcher(player):
        stats_sections = [
            _build_pitching_season_html(player),
            _build_pitching_recent_html(player),
        ]
    else:
        stats_sections = [
            _build_season_stats_html(player),
            _build_streak_html(player),
            _build_recent_games_html(player),
            _build_lineup_slot_html(player),
            _build_opponent_split_html(player),
            _build_venue_split_html(player),
        ]
    sections = [
        _build_breadcrumb_html(player.name),
        _build_featured_image_html(player),
        _build_short_review_html(player),
        *stats_sections,
        _build_related_topic_html(player),
        _build_back_link_html(),
        _build_jsonld(player),
    ]
    return "\n".join(s for s in sections if s)


def render_pillar_title(player: PillarPlayerInfo) -> str:
    """WP page.title = SEO 検索表示用。"""
    pos = f"（{player.position}・背番号{player.jersey_number}）" if player.position and player.jersey_number else ""
    return f"{player.name}{pos} データ - 直近成績・関連記事 | 巨人選手データ"


__all__ = [
    "PillarPlayerInfo",
    "render_pillar_html",
    "render_pillar_title",
    "CLUSTER_URL",
    "SITE_BASE",
]
