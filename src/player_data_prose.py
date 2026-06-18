"""選手ページの split データを「index される解説文」に変換する(SEO 情報量増)。

大手(baseballdata 等)は数表のみで本文が薄い。Pillar は split が豊富だが表中心で
Google が拾える本文テキストが少ない。本モジュールは PillarPlayerInfo の各 split
から数値そのままの解説文を**決定的に**生成する(LLM 不使用=事実安全・API コスト0)。

打者は本拠地/ビジター・対左右・得点圏・月別・曜日別・打順別・序中終盤・交流戦・
対戦球団(相手別=強い相手/苦手な相手)・連続記録まで文章化。投手は登板成績・
対戦球団別/本拠地別の防御率まで文章化する。数字は split のものだけを使う。
"""

from __future__ import annotations

from typing import Any, List, Optional


def _avg(v: Optional[float]) -> str:
    if v is None:
        return ""
    return f"{v:.3f}".lstrip("0") if v < 1 else f"{v:.3f}"


def _era(v: Optional[float]) -> str:
    return "" if v is None else f"{v:.2f}"


def _extreme(rows: List[tuple], *, label_idx: int, val_idx: int, ab_idx: int,
             min_ab: int = 10, want_max: bool = True) -> Optional[tuple]:
    """ab_idx>=min_ab の行で val が最大/最小の (label, val) を返す。"""
    best = None
    for r in rows or []:
        try:
            ab = int(r[ab_idx]); val = r[val_idx]
        except (IndexError, TypeError, ValueError):
            continue
        if ab < min_ab or val is None:
            continue
        v = float(val)
        if best is None or (v > best[1] if want_max else v < best[1]):
            best = (str(r[label_idx]), v)
    return best


def _pair(rows: List[tuple], *, label_idx: int, val_idx: int) -> dict:
    out = {}
    for r in rows or []:
        try:
            if r[val_idx] is not None:
                out[str(r[label_idx])] = float(r[val_idx])
        except (IndexError, TypeError, ValueError):
            continue
    return out


def _batter_sentences(p: Any, name: str) -> List[str]:
    s: List[str] = []
    avg = getattr(p, "season_avg", None)
    g = getattr(p, "season_games", 0)
    if avg is not None and g:
        s.append(f"{name}の今シーズンの一軍打撃成績は{g}試合で打率{_avg(avg)}、"
                 f"本塁打{getattr(p,'season_hr',0)}本、打点{getattr(p,'season_rbi',0)}。")

    venue = _pair(getattr(p, "venue_split_stats", []), label_idx=0, val_idx=5)
    home = next((venue[k] for k in venue if "本拠" in k or "ホーム" in k), None)
    away = next((venue[k] for k in venue if "ビジ" in k or "敵地" in k), None)
    if home is not None and away is not None:
        s.append(f"本拠地では打率{_avg(home)}、ビジターでは{_avg(away)}と、"
                 f"{'本拠地に強く' if home > away else 'ビジターでより打率を残し'}ている。")

    lr = _pair(getattr(p, "vs_lr_split_stats", []), label_idx=0, val_idx=3)
    left = next((lr[k] for k in lr if "左" in k), None)
    right = next((lr[k] for k in lr if "右" in k), None)
    if left is not None and right is not None:
        s.append(f"対左投手は打率{_avg(left)}、対右投手は{_avg(right)}で、"
                 f"{'左投手に強い' if left > right else '右投手をより得意とする'}タイプ。")

    risp = _pair(getattr(p, "risp_split_stats", []), label_idx=0, val_idx=3)
    rv = next((v for k, v in risp.items() if "圏" in k), None) or (list(risp.values())[0] if risp else None)
    if rv is not None:
        s.append(f"チャンスでの得点圏打率は{_avg(rv)}。")

    bm = _extreme(getattr(p, "month_split_stats", []), label_idx=0, val_idx=4, ab_idx=2)
    if bm:
        s.append(f"月別では{bm[0]}の打率{_avg(bm[1])}が最も高い。")

    bw = _extreme(getattr(p, "weekday_split_stats", []), label_idx=0, val_idx=4, ab_idx=2)
    if bw:
        s.append(f"曜日別では{bw[0]}に打率{_avg(bw[1])}と好調。")

    bs = _extreme(getattr(p, "lineup_slot_stats", []), label_idx=0, val_idx=5, ab_idx=2)
    if bs:
        s.append(f"打順別では{bs[0]}番で打率{_avg(bs[1])}を記録している。")

    bi = _extreme(getattr(p, "inning_split_stats", []), label_idx=0, val_idx=3, ab_idx=1)
    if bi:
        s.append(f"試合の{bi[0]}に打率{_avg(bi[1])}と最も結果を残している。")

    il = _pair(getattr(p, "interleague_split_stats", []), label_idx=0, val_idx=4)
    inter = next((il[k] for k in il if "交流" in k), None)
    league = next((il[k] for k in il if "リーグ" in k and "交流" not in k), None)
    if inter is not None and league is not None:
        s.append(f"交流戦では打率{_avg(inter)}、リーグ戦では{_avg(league)}。")

    # 相手(対戦球団)別: 得意な相手と苦手な相手の両方を書く
    strong = _extreme(getattr(p, "opponent_split_stats", []), label_idx=0, val_idx=5, ab_idx=2, want_max=True)
    weak = _extreme(getattr(p, "opponent_split_stats", []), label_idx=0, val_idx=5, ab_idx=2, want_max=False)
    if strong and weak and strong[0] != weak[0]:
        s.append(f"対戦球団別では{strong[0]}戦の打率{_avg(strong[1])}が最も高く、"
                 f"一方で{weak[0]}戦は{_avg(weak[1])}と苦戦している。")
    elif strong:
        s.append(f"対戦球団別では{strong[0]}戦で打率{_avg(strong[1])}と特に好成績。")

    hs = getattr(p, "hit_streak_active", 0) or 0
    if hs >= 3:
        s.append(f"現在{hs}試合連続安打中。")
    return s


def _pitcher_sentences(p: Any, name: str) -> List[str]:
    s: List[str] = []
    g = getattr(p, "pitch_games", 0) or 0
    era = getattr(p, "pitch_era", None)
    if g and era is not None:
        s.append(f"{name}の今シーズンの一軍投球成績は{g}登板、"
                 f"{getattr(p,'pitch_wins',0)}勝{getattr(p,'pitch_losses',0)}敗、防御率{_era(era)}、"
                 f"{getattr(p,'pitch_ip',0)}回、奪三振{getattr(p,'pitch_k',0)}。")
    whip = getattr(p, "pitch_whip", None)
    if whip is not None:
        s.append(f"WHIPは{whip:.2f}、9回平均奪三振は{getattr(p,'pitch_k_per_9',None) or 0:.1f}。")

    # 防御率は小さいほど良い → want_max=False が「最も抑えた相手」
    strong = _extreme(getattr(p, "pitch_opponent_split_stats", []), label_idx=0, val_idx=5, ab_idx=1,
                      min_ab=2, want_max=False)
    weak = _extreme(getattr(p, "pitch_opponent_split_stats", []), label_idx=0, val_idx=5, ab_idx=1,
                    min_ab=2, want_max=True)
    if strong and weak and strong[0] != weak[0]:
        s.append(f"対戦球団別では{strong[0]}戦で防御率{_era(strong[1])}と最も安定し、"
                 f"{weak[0]}戦は{_era(weak[1])}と苦しんでいる。")

    venue = _pair(getattr(p, "pitch_venue_split_stats", []), label_idx=0, val_idx=5)
    home = next((venue[k] for k in venue if "本拠" in k or "ホーム" in k), None)
    away = next((venue[k] for k in venue if "ビジ" in k or "敵地" in k), None)
    if home is not None and away is not None:
        s.append(f"本拠地では防御率{_era(home)}、ビジターでは{_era(away)}。")
    return s


def build_player_prose(player: Any) -> str:
    """player の split から SEO 用の解説段落(HTML)を組み立てる。薄い時は ""。"""
    name = getattr(player, "name", "") or ""
    if not name:
        return ""
    # 投手で打撃 split が無ければ投手文、それ以外は打者文
    sentences = _batter_sentences(player, name)
    if len(sentences) < 2:
        sentences = _pitcher_sentences(player, name)
    if len(sentences) < 2:
        return ""
    body = "".join(f"<p>{s}</p>" for s in sentences)
    return ('<h2 style="font-size:16px;margin:18px 0 8px;">'
            f"{name} 今季成績の傾向（データ分析）</h2>{body}")
