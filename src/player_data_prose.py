"""選手ページの split データを「indexされる解説文」に変換する(SEO 強化)。

baseballdata 等の大手は数表のみで文章が薄い。Pillar は split が豊富だが表中心で、
Google が拾える本文テキストが少ない。本モジュールは PillarPlayerInfo の各 split
(本拠地/ビジター・対左右・月別・得点圏・対戦球団・打順・連続)から、数値をそのまま
使った解説文を**決定的に**生成する(LLM 不使用=事実安全・API コスト0)。

数字は player の split に入っている値だけを使い、新しい数字は作らない。
"""

from __future__ import annotations

from typing import Any, List, Optional


def _avg(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"{v:.3f}".lstrip("0") if v < 1 else f"{v:.3f}"


def _best(rows: List[tuple], *, label_idx: int, avg_idx: int, ab_idx: int,
          min_ab: int = 10) -> Optional[tuple]:
    """AB>=min_ab の行で打率最大の (label, avg) を返す。"""
    best = None
    for r in rows or []:
        try:
            ab = int(r[ab_idx]); avg = r[avg_idx]
        except (IndexError, TypeError, ValueError):
            continue
        if ab < min_ab or avg is None:
            continue
        if best is None or avg > best[1]:
            best = (r[label_idx], float(avg))
    return best


def _pair_avgs(rows: List[tuple], *, label_idx: int, avg_idx: int) -> dict:
    out = {}
    for r in rows or []:
        try:
            if r[avg_idx] is not None:
                out[str(r[label_idx])] = float(r[avg_idx])
        except (IndexError, TypeError, ValueError):
            continue
    return out


def build_player_prose(player: Any) -> str:
    """player の split から SEO 用の解説段落(HTML)を組み立てる。データが無ければ ""。"""
    name = getattr(player, "name", "") or ""
    if not name:
        return ""
    sentences: List[str] = []

    avg = getattr(player, "season_avg", None)
    g = getattr(player, "season_games", 0)
    hr = getattr(player, "season_hr", 0)
    rbi = getattr(player, "season_rbi", 0)
    if avg is not None and g:
        sentences.append(
            f"{name}の今シーズンの一軍打撃成績は{g}試合で打率{_avg(avg)}、"
            f"本塁打{hr}本、打点{rbi}。"
        )

    # 本拠地 / ビジター
    venue = _pair_avgs(getattr(player, "venue_split_stats", []), label_idx=0, avg_idx=5)
    home = next((venue[k] for k in venue if "本拠" in k or "ホーム" in k), None)
    away = next((venue[k] for k in venue if "ビジ" in k or "敵地" in k), None)
    if home is not None and away is not None:
        edge = "本拠地に強く" if home > away else "ビジターでより打率を残し"
        sentences.append(
            f"本拠地では打率{_avg(home)}、ビジターでは{_avg(away)}と、{edge}ている。"
        )

    # 対左 / 対右投手
    lr = _pair_avgs(getattr(player, "vs_lr_split_stats", []), label_idx=0, avg_idx=3)
    left = next((lr[k] for k in lr if "左" in k), None)
    right = next((lr[k] for k in lr if "右" in k), None)
    if left is not None and right is not None:
        edge = "左投手に強い" if left > right else "右投手をより得意とする"
        sentences.append(
            f"対左投手は打率{_avg(left)}、対右投手は{_avg(right)}で、{edge}タイプ。"
        )

    # 得点圏
    risp = _pair_avgs(getattr(player, "risp_split_stats", []), label_idx=0, avg_idx=3)
    risp_val = next((v for k, v in risp.items() if "得点圏" in k or "圏" in k), None)
    if risp_val is None and risp:
        risp_val = list(risp.values())[0]
    if risp_val is not None:
        sentences.append(f"チャンスでの得点圏打率は{_avg(risp_val)}。")

    # 一番得意な月
    bm = _best(getattr(player, "month_split_stats", []), label_idx=0, avg_idx=4, ab_idx=2)
    if bm:
        sentences.append(f"月別では{bm[0]}の打率{_avg(bm[1])}が最も高い。")

    # 一番得意な対戦球団
    bo = _best(getattr(player, "opponent_split_stats", []), label_idx=0, avg_idx=5, ab_idx=3)
    if bo:
        sentences.append(f"対戦球団別では{bo[0]}戦で打率{_avg(bo[1])}と特に好成績。")

    # 連続記録
    hs = getattr(player, "hit_streak_active", 0) or 0
    if hs >= 3:
        sentences.append(f"現在{hs}試合連続安打中。")

    if len(sentences) < 2:
        return ""  # データが薄い時は出さない

    body = "".join(f"<p>{s}</p>" for s in sentences)
    return (
        '<h2 style="font-size:16px;margin:18px 0 8px;">'
        f"{name} 今季成績の傾向（データ分析）</h2>{body}"
    )
