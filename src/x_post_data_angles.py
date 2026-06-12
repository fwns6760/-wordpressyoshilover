"""データ角度 v2 — ML的に見える驚き角度 + 話題選手連動 (2026-06-11 user 全部GO)。

user: 「ファンが驚く機械学習的なデータはとれるの？」「その試合で話題になった選手が
インプとれそう」→ 4 角度を全部実装。

角度 (公開 X 自動投稿はしない、候補=メールまで。全て env flag gate / default OFF):
1. build_win_correlation_candidates — 選手の活躍有無 × チーム勝率 (条件付き勝率)。
   例「キャベッジが打点を挙げた試合 9勝2敗(.818) / なし 14勝17敗(.452)」
2. build_opponent_split_candidates — 対戦カード別打率の「キラー」angle。
   例「泉口友汰 対阪神 .412 (シーズン .298)」
3. build_alltime_chase_candidates — 歴代巨人在籍 (OB 878 名 + 現役) NPB通算
   ランキングで「あと○本で△△に並ぶ」接近 angle (alltime_ranking 共有部品)。
4. boost_topical_candidates — RSSHub 巨人系 X feed の直近言及回数で
   「今夜の話題選手」をスコア化し、 該当 focus_player の候補を先頭へ。

データ源は insight.db (NPB 公式 box 集計) / ob_legends_full.json / npb_career
cache / 自前 RSSHub のみ。 新規 API 課金なし、 LLM 不使用 (たんぱく事実型)。
サバメトリクス指数は使わない (勝敗・打率・本数のみ = わかりやすさ基準)。
"""
from __future__ import annotations

import logging
import sqlite3 as _sqlite3
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

JST = ZoneInfo("Asia/Tokyo")

_WIN_CORR_METRIC = "勝利相関"
_OPP_SPLIT_METRIC = "対戦別split"
_ALLTIME_METRIC = "歴代通算チェイス"
_WEEKLY_MVP_METRIC = "週間MVP"
_LEGEND_COMPARE_METRIC = "新旧比較"

# alltime_ranking.STAT_SPECS のうち X 候補にする stat と単位表記
_ALLTIME_UNITS = {"hr": "本", "hits": "本", "rbi": "打点", "win": "勝", "so": "個"}


def _fmt3(v: float) -> str:
    """0.818 → '.818' (打率/勝率の慣用表記)。"""
    return f"{v:.3f}".lstrip("0") if v < 1 else f"{v:.3f}"


def _candidate_cls():
    from src.x_post_mail_lane import Candidate
    return Candidate


def _try_png(template_key: str, data: dict) -> bytes:
    """カード PNG を生成。 失敗は空 bytes (caller は画像なしで候補継続)。"""
    try:
        from src.x_post_image_gen_v2 import generate_png
        return generate_png(template_key, data) or b""
    except Exception as exc:  # noqa: BLE001
        logger.info("data_angles image skip template=%s: %r", template_key, exc)
        return b""


def _current_hit_streak(db_path: str, canon: str) -> int:
    """出場試合 (AB>0) ベースの現在の連続安打試合数。 取れなければ 0。

    mainportalhuge 型の「6試合連続ヒット」記録文脈 (2026-06-11 user
    「【選手名】は分かりやすい」「試合後に単発」)。 read-only。
    """
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT COALESCE(b.H,0) FROM batting_logs b "
                "JOIN games g USING(game_id) "
                "WHERE b.team_name='巨人' AND b.player_canonical=? "
                " AND COALESCE(b.AB,0) > 0 "
                "ORDER BY g.game_date DESC",
                (canon,),
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.info("hit_streak skip %s: %r", canon, exc)
        return 0
    streak = 0
    for (h,) in rows:
        if int(h or 0) > 0:
            streak += 1
        else:
            break
    return streak


def _streak_line(db_path: str, canon: str, *, min_streak: int = 3) -> str:
    """記録文脈 1 行 (連続安打 3 試合以上の時だけ)。 無ければ空文字。"""
    n = _current_hit_streak(db_path, canon)
    return f"📝{n}試合連続安打中\n" if n >= min_streak else ""


# ─── 1. 勝利相関 (条件付き勝率) ──────────────────────────────────────


def build_win_correlation_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 2,
    min_cond_games: int = 8,
    min_total_games: int = 20,
    min_gap: float = 0.150,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = True,
    preferred_players: Optional[set[str]] = None,
) -> list:
    """「この選手が活躍した試合、巨人は強い」条件付き勝率の驚き候補。

    条件は 2 軸 (打点あり / マルチ安打) を計算し、 選手ごとに gap の大きい方を採用。
    引き分けは分母から除外 (勝敗のみ)。 insight.db read-only。
    ``preferred_players`` (今夜の話題選手 等) は閾値を満たす限り gap より優先する
    (2026-06-11 user「色々なデータを試合あとは知りたい」= 今夜の主役の驚きを先に)。
    """
    if now is None:
        now = datetime.now(JST)
    if not db_path:
        return []
    Candidate = _candidate_cls()
    conds = (
        ("rbi", "打点を挙げた試合", "b.RBI > 0"),
        ("multi_hit", "マルチ安打の試合", "b.H >= 2"),
    )
    rows_by_cond: dict[str, list[tuple]] = {}
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cur = conn.cursor()
            for key, _label, expr in conds:
                rows_by_cond[key] = cur.execute(
                    "SELECT b.player_canonical, "
                    f" SUM(CASE WHEN {expr} AND g.result='win' THEN 1 ELSE 0 END), "
                    f" SUM(CASE WHEN {expr} AND g.result='loss' THEN 1 ELSE 0 END), "
                    f" SUM(CASE WHEN NOT ({expr}) AND g.result='win' THEN 1 ELSE 0 END), "
                    f" SUM(CASE WHEN NOT ({expr}) AND g.result='loss' THEN 1 ELSE 0 END) "
                    "FROM batting_logs b JOIN games g USING(game_id) "
                    "WHERE b.team_name='巨人' AND b.player_canonical IS NOT NULL "
                    " AND COALESCE(b.AB,0) > 0 AND g.result IN ('win','loss') "
                    "GROUP BY b.player_canonical",
                ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("win_correlation query failed: %r", exc)
        return []

    best_by_player: dict[str, tuple] = {}
    for (key, label, _expr) in conds:
        for canon, cw, cl, nw, nl in rows_by_cond.get(key, []):
            cw, cl, nw, nl = int(cw or 0), int(cl or 0), int(nw or 0), int(nl or 0)
            cond_n, other_n = cw + cl, nw + nl
            if cond_n < min_cond_games or other_n <= 0:
                continue
            if cond_n + other_n < min_total_games:
                continue
            cond_rate = cw / cond_n
            other_rate = nw / other_n
            gap = cond_rate - other_rate
            if gap < min_gap:
                continue
            prev = best_by_player.get(canon)
            if prev is None or gap > prev[0]:
                best_by_player[canon] = (gap, key, label, cw, cl, nw, nl, cond_rate, other_rate)

    pref = preferred_players or set()
    out: list = []
    for canon, (gap, key, label, cw, cl, nw, nl, cr, orr) in sorted(
        best_by_player.items(), key=lambda kv: (kv[0] not in pref, -kv[1][0])
    ):
        if len(out) >= max_count:
            break
        signature = f"win_corr|{canon}|{key}"
        if dedup_set is not None and signature in dedup_set:
            logger.info("win_corr dedup skip %s", signature)
            continue
        total = cw + cl + nw + nl
        # たんぱく事実型 (主観なし、数字 = DB verified のみ)
        post = (
            f"【{canon}】{label}、巨人は強い\n"
            f"あり {cw}勝{cl}敗 (勝率{_fmt3(cr)})\n"
            f"なし {nw}勝{nl}敗 (勝率{_fmt3(orr)})\n"
            + _streak_line(db_path, canon)
            + f"今季{total}試合・勝率差+{_fmt3(gap)} #巨人 #ジャイアンツ"
        )
        fact = (
            f"{label}: {cw}勝{cl}敗 勝率{_fmt3(cr)} ｜ それ以外: {nw}勝{nl}敗 "
            f"勝率{_fmt3(orr)} ｜ 差 +{_fmt3(gap)} (今季{total}試合)"
        )
        draft = "\n".join([
            "【根拠: 勝利相関 (条件付き勝率、大手未掲載)】",
            fact,
            "出典: insight.db (NPB公式box×試合結果 join 集計)",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        image = b""
        if with_image:
            from src.x_post_image_gen_v2 import build_win_split_data
            image = _try_png("win_split", build_win_split_data(
                title=f"{canon} 勝利相関",
                subtitle=f"今季{total}試合 ・ NPB公式box集計",
                hook_line=f"★ {label}、巨人は強い ★",
                player_name=canon,
                cond_label=label,
                a_label="あり", a_record=f"{cw}勝{cl}敗", a_rate=_fmt3(cr),
                b_label="なし", b_record=f"{nw}勝{nl}敗", b_rate=_fmt3(orr),
                diff_label=f"勝率差 +{_fmt3(gap)}",
            ))
        out.append(Candidate(
            title=f"{canon} {label} 勝率{_fmt3(cr)} (なしは{_fmt3(orr)})",
            metric=_WIN_CORR_METRIC,
            period_label="今シーズン",
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player=canon,
            db_fact_line=fact,
            team_level="first",
            sample_size=total,
            sample_label=f"今季{total}試合",
            why_now="勝敗に直結する条件付き勝率 (ML的相関 angle)",
            source_material_type="win_correlation",
            image_bytes=image,
        ))
    logger.info("win_correlation: built %d candidates (max=%d)", len(out), max_count)
    return out


# ─── 2. 対戦カード別 split (キラー angle) ────────────────────────────


def build_opponent_split_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 2,
    min_opp_ab: int = 15,
    min_season_ab: int = 60,
    min_gap: float = 0.080,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = True,
    preferred_players: Optional[set[str]] = None,
) -> list:
    """「対○○キラー」対戦カード別打率の驚き候補 (シーズン比 +min_gap 以上)。

    ``preferred_players`` (今夜の話題選手 等) は閾値を満たす限り gap より優先。
    """
    if now is None:
        now = datetime.now(JST)
    if not db_path:
        return []
    Candidate = _candidate_cls()
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            cur = conn.cursor()
            season = {
                canon: (int(ab or 0), int(h or 0))
                for canon, ab, h in cur.execute(
                    "SELECT player_canonical, SUM(COALESCE(AB,0)), SUM(COALESCE(H,0)) "
                    "FROM batting_logs WHERE team_name='巨人' "
                    " AND player_canonical IS NOT NULL GROUP BY player_canonical",
                )
            }
            opp_rows = cur.execute(
                "SELECT b.player_canonical, g.opponent, SUM(COALESCE(b.AB,0)), "
                " SUM(COALESCE(b.H,0)), SUM(COALESCE(b.RBI,0)) "
                "FROM batting_logs b JOIN games g USING(game_id) "
                "WHERE b.team_name='巨人' AND b.player_canonical IS NOT NULL "
                "GROUP BY b.player_canonical, g.opponent",
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("opponent_split query failed: %r", exc)
        return []

    scored: list[tuple] = []
    for canon, opp, oab, oh, orbi in opp_rows:
        oab, oh, orbi = int(oab or 0), int(oh or 0), int(orbi or 0)
        sab, sh = season.get(canon, (0, 0))
        if oab < min_opp_ab or sab < min_season_ab:
            continue
        opp_avg = oh / oab
        season_avg = sh / sab
        gap = opp_avg - season_avg
        if gap < min_gap:
            continue
        scored.append((gap, canon, str(opp), oab, oh, orbi, opp_avg, season_avg))

    pref = preferred_players or set()
    out: list = []
    used_players: set[str] = set()
    for gap, canon, opp, oab, oh, orbi, oavg, savg in sorted(
        scored, key=lambda t: (t[1] not in pref, -t[0])
    ):
        if len(out) >= max_count:
            break
        if canon in used_players:  # 一選手一本
            continue
        signature = f"opp_split|{canon}|{opp}"
        if dedup_set is not None and signature in dedup_set:
            logger.info("opp_split dedup skip %s", signature)
            continue
        used_players.add(canon)
        post = (
            f"【{canon}】{opp}キラー\n"
            f"対{opp} {_fmt3(oavg)} ({oh}安打/{oab}打数・{orbi}打点)\n"
            f"シーズン {_fmt3(savg)} — 対{opp}で+{_fmt3(gap)}\n"
            + _streak_line(db_path, canon)
            + f"#巨人 #ジャイアンツ"
        )
        fact = (
            f"対{opp} 打率{_fmt3(oavg)} ({oh}安打/{oab}打数・{orbi}打点) ｜ "
            f"シーズン{_fmt3(savg)} ｜ 差 +{_fmt3(gap)}"
        )
        draft = "\n".join([
            "【根拠: 対戦カード別 split (大手未掲載)】",
            fact,
            "出典: insight.db (NPB公式box×対戦相手 join 集計)",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        image = b""
        if with_image:
            from src.x_post_image_gen_v2 import build_player_spotlight_data
            image = _try_png("player_spotlight", build_player_spotlight_data(
                title=f"対{opp} 打率",
                subtitle="今季 ・ NPB公式box集計",
                hook_line=f"★ {canon} {opp}キラー ★",
                player_name=canon,
                player_team="巨人",
                metric_label=f"対{opp} 打率 ({oh}安打/{oab}打数)",
                hero_value=_fmt3(oavg),
                sub_stats=[
                    {"label": "シーズン打率", "value": _fmt3(savg)},
                    {"label": f"対{opp}差", "value": f"+{_fmt3(gap)}"},
                ],
            ))
        out.append(Candidate(
            title=f"{canon} 対{opp} {_fmt3(oavg)} ({opp}キラー)",
            metric=_OPP_SPLIT_METRIC,
            period_label="今シーズン",
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player=canon,
            db_fact_line=fact,
            team_level="first",
            sample_size=oab,
            sample_label=f"対{opp} {oab}打数",
            why_now=f"対{opp}戦の前後で刺さる対戦キラー angle",
            source_material_type="opponent_split",
            image_bytes=image,
        ))
    logger.info("opponent_split: built %d candidates (max=%d)", len(out), max_count)
    return out


# ─── 3. 歴代通算チェイス (あと○本) ──────────────────────────────────


def build_alltime_chase_candidates(
    *,
    now: Optional[datetime] = None,
    max_count: int = 1,
    max_remaining: int = 8,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = True,
    rankings: Optional[dict] = None,
) -> list:
    """歴代巨人在籍 (OB+現役) NPB通算ランキングの「あと○本で△△に並ぶ」接近候補。

    alltime_ranking 共有部品 (OB=ob_legends_full.json / 現役=npb_career GCS cache)。
    cache 未取得環境では空 list (graceful)。
    """
    if now is None:
        now = datetime.now(JST)
    Candidate = _candidate_cls()
    try:
        from src.analysis import alltime_ranking as _ar
        if rankings is None:
            from src.analysis.career_milestone import load_career_cache
            rankings = _ar.build_rankings(career_cache=load_career_cache())
        stat_labels = {k: v["label"] for k, v in _ar.STAT_SPECS.items()}
    except Exception as exc:  # noqa: BLE001
        logger.info("alltime_chase data unavailable: %r", exc)
        return []

    chases: list[tuple] = []
    for stat_key, rows in (rankings or {}).items():
        unit = _ALLTIME_UNITS.get(stat_key, "")
        label = stat_labels.get(stat_key, stat_key)
        for idx, row in enumerate(rows):
            if not row.get("is_current") or idx == 0:
                continue
            above = rows[idx - 1]
            remaining = int(above["value"]) - int(row["value"])
            if remaining <= 0 or remaining > max_remaining:
                continue
            # 接近が僅差なほど上に (remaining 昇順 → 上位 rank 優先)
            chases.append((remaining, row["rank"], stat_key, label, unit, row, above))

    out: list = []
    for remaining, rank, stat_key, label, unit, row, above in sorted(chases):
        if len(out) >= max_count:
            break
        name = str(row["name"])
        signature = f"alltime_chase|{name}|{stat_key}|{row['value']}"
        if dedup_set is not None and signature in dedup_set:
            logger.info("alltime_chase dedup skip %s", signature)
            continue
        post = (
            f"【{name}】NPB通算{row['value']}{label}\n"
            f"歴代巨人在籍ランキング {rank}位\n"
            f"あと{remaining}{unit}で {above['rank']}位 {above['name']} ({above['value']}{label}) に並ぶ\n"
            f"#巨人 #ジャイアンツ"
        )
        fact = (
            f"NPB通算{label} {row['value']} (歴代巨人在籍 {rank}位) ｜ "
            f"次は {above['name']} {above['value']} ・ あと{remaining}{unit}"
        )
        draft = "\n".join([
            "【根拠: 歴代通算チェイス (OB 878名 + 現役 通算ランキング)】",
            fact,
            "出典: NPB公式 通算成績 (ob_legends_full / npb_career cache)",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        image = b""
        if with_image:
            from src.x_post_image_gen_v2 import build_player_spotlight_data
            image = _try_png("player_spotlight", build_player_spotlight_data(
                title=f"NPB通算{label} 歴代巨人在籍ランキング",
                subtitle="OB 878名 + 現役 ・ NPB公式通算",
                hook_line=f"★ あと{remaining}{unit}で {above['name']} に並ぶ ★",
                player_name=name,
                player_team=f"歴代 {rank}位",
                metric_label=f"NPB通算{label}",
                hero_value=str(row["value"]),
                sub_stats=[
                    {"label": f"次 {above['rank']}位 {above['name']}", "value": str(above["value"])},
                    {"label": "あと", "value": f"{remaining}{unit}"},
                ],
            ))
        out.append(Candidate(
            title=f"{name} 通算{label} あと{remaining}{unit}で{above['name']}",
            metric=_ALLTIME_METRIC,
            period_label="NPB通算",
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player=name,
            db_fact_line=fact,
            team_level="first",
            sample_size=int(row["value"]),
            sample_label=f"通算{row['value']}{label}",
            why_now=f"歴代記録接近 (あと{remaining}{unit}) は到達瞬間まで継続ネタ",
            source_material_type="alltime_chase",
            image_bytes=image,
        ))
    logger.info("alltime_chase: built %d candidates (max=%d)", len(out), max_count)
    return out


# ─── 4. 話題選手ブースト ─────────────────────────────────────────────


def fetch_topical_counts(
    *,
    fetch_fn: Optional[Callable[[str], str]] = None,
    handles: Optional[list[str]] = None,
    min_mentions: int = 1,
    top_n: int = 12,
    max_age_hours: float = 6.0,
    now: Optional[datetime] = None,
) -> dict[str, int]:
    """自前 RSSHub の巨人系 X feed から {選手名: 直近言及数} を返す。失敗は {}。

    video_radar.fetch_buzzing_players と違い pubDate で鮮度 gate する
    (default 6h)。「その試合で話題」のため、 昨日のバズを今夜の話題として
    拾わない。 pubDate 不明の item は判定不能なので通す (RSSHub は通常返す)。
    """
    if now is None:
        now = datetime.now(JST)
    try:
        from src import video_radar as _vr
        from src.x_post_mail_lane import (
            _load_giants_member_aliases,
            _load_giants_player_aliases,
            detect_giants_player_name,
        )
        alias_map = {**_load_giants_player_aliases(), **_load_giants_member_aliases()}
        fetch = fetch_fn or _vr._default_fetch
        handles = handles or _vr._BUZZ_HANDLES
        counts: dict[str, int] = {}
        for h in handles:
            try:
                xml = fetch(f"{_vr._RSSHUB_BASE}/twitter/user/{h}?limit=30")
            except Exception:  # noqa: BLE001
                continue
            for item in _vr._extract_rss_items(xml):
                published_at = item.get("published_at")
                if published_at is not None:
                    try:
                        age_h = (now - published_at).total_seconds() / 3600.0
                    except (TypeError, ValueError):
                        age_h = 0.0
                    if age_h > max_age_hours:
                        continue
                try:
                    p = detect_giants_player_name(
                        item.get("text", ""), alias_map=alias_map) or ""
                except Exception:  # noqa: BLE001
                    p = ""
                if p:
                    counts[p] = counts.get(p, 0) + 1
        filtered = {k: v for k, v in counts.items() if v >= min_mentions}
        return dict(sorted(filtered.items(), key=lambda kv: kv[1], reverse=True)[:top_n])
    except Exception as exc:  # noqa: BLE001
        logger.info("topical counts skip: %r", exc)
        return {}


def boost_topical_candidates(
    candidates: list,
    buzz_counts: dict[str, int],
    *,
    min_mentions: int = 2,
) -> list:
    """focus_player が「今夜の話題選手」(言及 min_mentions 以上) の候補を先頭へ。

    並びは stable sort (話題スコア降順 → 元の順序維持)。 boost された候補には
    why_now に言及数を追記し、 メールで「なぜ今これか」が分かるようにする。
    数字・本文 (post_text / db_fact_line) は一切変えない。
    """
    if not candidates or not buzz_counts:
        return candidates

    def _score(c) -> int:
        n = buzz_counts.get((getattr(c, "focus_player", "") or "").strip(), 0)
        return n if n >= min_mentions else 0

    boosted = sorted(candidates, key=_score, reverse=True)
    for c in boosted:
        n = _score(c)
        if n > 0:
            tag = f"🔥今夜の話題: 巨人系Xで{n}件言及"
            why = getattr(c, "why_now", "") or ""
            if tag not in why:
                try:
                    c.why_now = f"{tag}" + (f" ｜ {why}" if why else "")
                except Exception:  # noqa: BLE001  (frozen dataclass 等は据え置き)
                    pass
    n_boosted = sum(1 for c in boosted if _score(c) > 0)
    if n_boosted:
        logger.info("topical boost: %d/%d candidates boosted", n_boosted, len(boosted))
    return boosted


# ─── 5. 週間MVP (月曜の定番企画) ─────────────────────────────────────


def build_weekly_mvp_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 1,
    min_ab: int = 10,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = True,
    monday_only: bool = True,
) -> list:
    """月曜限定【週間MVP】= 先週 (月〜日) の巨人打者集計トップ。

    「月曜はヨシラバー週間MVP」の定番企画 (2026-06-12 user 合意の角度⑤)。
    驚きゲートではなく固定枠なので、 最低稼働 (min_ab) だけ gate する。
    本塁打は列が無く atbats_json の「本」cell 数で導出
    (data_site_query.fetch_batting_stats_season と同方式)。 insight.db read-only。
    """
    if now is None:
        now = datetime.now(JST)
    if monday_only and now.weekday() != 0:
        return []
    if not db_path:
        return []
    week_end = (now - timedelta(days=1)).date()    # 昨日 = 日曜
    week_start = (now - timedelta(days=7)).date()  # 先週月曜
    Candidate = _candidate_cls()
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT b.player_canonical, COUNT(DISTINCT b.game_id), "
                " SUM(COALESCE(b.AB,0)), SUM(COALESCE(b.H,0)), "
                " SUM(COALESCE(b.RBI,0)), SUM(COALESCE(b.R,0)) "
                "FROM batting_logs b JOIN games g USING(game_id) "
                "WHERE b.team_name='巨人' AND b.player_canonical IS NOT NULL "
                " AND g.game_date BETWEEN ? AND ? "
                "GROUP BY b.player_canonical",
                (week_start.isoformat(), week_end.isoformat()),
            ).fetchall()
            aj_rows = conn.execute(
                "SELECT b.player_canonical, b.atbats_json "
                "FROM batting_logs b JOIN games g USING(game_id) "
                "WHERE b.team_name='巨人' AND b.player_canonical IS NOT NULL "
                " AND b.atbats_json IS NOT NULL "
                " AND g.game_date BETWEEN ? AND ?",
                (week_start.isoformat(), week_end.isoformat()),
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("weekly_mvp query failed: %r", exc)
        return []

    import json as _json
    hr_by_player: dict[str, int] = {}
    for canon, aj in aj_rows:
        try:
            hr_by_player[canon] = hr_by_player.get(canon, 0) + sum(
                1 for c in _json.loads(aj) if "本" in str(c))
        except Exception:  # noqa: BLE001
            pass

    scored: list[tuple] = []
    for canon, games, ab, h, rbi, r in rows:
        ab, h, rbi, r = int(ab or 0), int(h or 0), int(rbi or 0), int(r or 0)
        if ab < min_ab:
            continue
        hr = hr_by_player.get(canon, 0)
        # 選定スコアは内部のみ (表示しない)。 打点・本塁打・安打の貢献量ベース。
        scored.append((rbi * 2 + hr * 3 + h + r, canon, int(games), ab, h, rbi, r, hr))

    out: list = []
    label_range = f"{week_start.month}/{week_start.day}〜{week_end.month}/{week_end.day}"
    for score, canon, games, ab, h, rbi, r, hr in sorted(scored, reverse=True):
        if len(out) >= max_count:
            break
        signature = f"weekly_mvp|{week_start.isoformat()}|{canon}"
        if dedup_set is not None and signature in dedup_set:
            logger.info("weekly_mvp dedup skip %s", signature)
            continue
        avg = h / ab
        hr_part = f"・{hr}本塁打" if hr else ""
        post = (
            f"【週間MVP】{canon}\n"
            f"先週の巨人 ({label_range}・{games}試合)\n"
            f"打率{_fmt3(avg)} ({h}安打/{ab}打数){hr_part}・{rbi}打点\n"
            + _streak_line(db_path, canon)
            + "#巨人 #ジャイアンツ"
        )
        fact = (
            f"週間 ({label_range}) 打率{_fmt3(avg)} ({h}安打/{ab}打数) ｜ "
            f"本塁打{hr} ｜ 打点{rbi} ｜ 得点{r}"
        )
        draft = "\n".join([
            "【根拠: 週間MVP (先週 月〜日 の巨人打者集計トップ)】",
            fact,
            "出典: insight.db (NPB公式box 週間集計)",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        image = b""
        if with_image:
            from src.x_post_image_gen_v2 import build_player_spotlight_data
            image = _try_png("player_spotlight", build_player_spotlight_data(
                title="ヨシラバー週間MVP",
                subtitle=f"{label_range} ・ NPB公式box週間集計",
                hook_line=f"★ 先週の巨人 MVP ★",
                player_name=canon,
                player_team="巨人",
                metric_label=f"週間打率 ({h}安打/{ab}打数)",
                hero_value=_fmt3(avg),
                sub_stats=[
                    {"label": "本塁打", "value": str(hr)},
                    {"label": "打点", "value": str(rbi)},
                ],
            ))
        out.append(Candidate(
            title=f"{canon} 週間MVP ({label_range})",
            metric=_WEEKLY_MVP_METRIC,
            period_label="先週 (月〜日)",
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player=canon,
            db_fact_line=fact,
            team_level="first",
            sample_size=ab,
            sample_label=f"週間{ab}打数",
            why_now="月曜定番企画 (フォロワーに待つ習慣を作る枠)",
            source_material_type="weekly_mvp",
            image_bytes=image,
        ))
    logger.info("weekly_mvp: built %d candidates (max=%d)", len(out), max_count)
    return out


# ─── 6. 新旧比較 (同年齢レジェンド対比) ──────────────────────────────


def _birth_year(raw: str) -> Optional[int]:
    """'1996年6月30日' / '1996-06-30' → 1996。 取れなければ None。"""
    import re as _re
    m = _re.search(r"(19|20)\d{2}", str(raw or ""))
    return int(m.group(0)) if m else None


def _norm_name(s: str) -> str:
    return str(s or "").replace("　", "").replace(" ", "")


def _load_legend_age_seasons() -> dict:
    """config/legend_age_seasons.json (NPB公式 verify 済み bake-in) を読む。無ければ {}。"""
    import json as _json
    from pathlib import Path as _Path
    path = _Path(__file__).resolve().parent.parent / "config" / "legend_age_seasons.json"
    try:
        return (_json.loads(path.read_text(encoding="utf-8")) or {}).get("stats") or {}
    except Exception as exc:  # noqa: BLE001
        logger.info("legend_age_seasons unavailable: %r", exc)
        return {}


def _season_hr_by_player(db_path: str) -> dict[str, int]:
    """今季の選手別本塁打 (atbats_json「本」cell 数、 既存 board と同方式)。"""
    import json as _json
    out: dict[str, int] = {}
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT player_canonical, atbats_json FROM batting_logs "
                "WHERE team_name='巨人' AND player_canonical IS NOT NULL "
                " AND atbats_json IS NOT NULL",
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.info("season hr query skip: %r", exc)
        return {}
    for canon, aj in rows:
        try:
            out[_norm_name(canon)] = out.get(_norm_name(canon), 0) + sum(
                1 for c in _json.loads(aj) if "本" in str(c))
        except Exception:  # noqa: BLE001
            pass
    return out


def build_legend_age_compare_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 1,
    max_age: int = 26,
    min_career_hr: int = 5,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = True,
    career_cache: Optional[dict] = None,
    legends: Optional[dict] = None,
) -> list:
    """「同年齢シーズン時点の通算本塁打」で現役若手 × レジェンドを対比する驚き候補。

    角度① 新旧比較 (2026-06-12 user 合意)。 年齢=その年に迎える満年齢 (年度-生年)
    で両者同一ルール比較。 現役側 = npb_career cache の過去年度 + insight.db の今季
    (career page の今季行は使わない = 二重計上防止)。 レジェンド側 =
    config/legend_age_seasons.json (NPB公式 verify 済み bake-in)。

    驚きゲート: 「レジェンドの同年齢時点 (>0本) を上回っている」若手だけ通す。
    cache 未取得環境では空 list (graceful)。
    """
    if now is None:
        now = datetime.now(JST)
    Candidate = _candidate_cls()
    if legends is None:
        legends = _load_legend_age_seasons()
    if career_cache is None:
        try:
            from src.analysis.career_milestone import load_career_cache
            career_cache = load_career_cache()
        except Exception as exc:  # noqa: BLE001
            logger.info("legend_compare career cache unavailable: %r", exc)
            career_cache = {}
    players = (career_cache or {}).get("players") or {}
    ids = (career_cache or {}).get("ids") or {}
    if not legends or not players:
        logger.info("legend_compare data unavailable (legends=%d players=%d)",
                    len(legends or {}), len(players))
        return []

    season_hr = _season_hr_by_player(db_path) if db_path else {}

    # レジェンド側: {name: {age: 同年齢シーズン終了時点の通算HR}} を事前計算
    legend_cum: dict[str, dict[int, int]] = {}
    for lname, payload in legends.items():
        by = _birth_year((payload or {}).get("birthdate") or "")
        rows = (payload or {}).get("seasons") or []
        if not by or not rows:
            continue
        cum: dict[int, int] = {}
        total = 0
        for r in sorted(rows, key=lambda r: str(r.get("年度") or "")):
            try:
                year = int(r.get("年度"))
                total += int(str(r.get("本塁打") or "0").replace(",", "") or 0)
            except (TypeError, ValueError):
                continue
            cum[year - by] = total
        legend_cum[lname] = cum

    def _cum_at(lname: str, age: int) -> int:
        ages = legend_cum.get(lname) or {}
        hit = [v for a, v in ages.items() if a <= age]
        return max(hit) if hit else 0

    scored: list[tuple] = []
    name_by_id = {str(v): k for k, v in ids.items()}
    for npb_id, payload in players.items():
        name = _norm_name(name_by_id.get(str(npb_id), ""))
        if not name:
            continue
        profile = (payload or {}).get("profile") or {}
        by = _birth_year(profile.get("birthdate") or "")
        if not by:
            continue
        age = now.year - by
        if age > max_age:
            continue
        prior = 0
        for r in ((payload or {}).get("batting") or {}).get("years") or []:
            try:
                if int(r.get("年度")) < now.year:
                    prior += int(str(r.get("本塁打") or "0").replace(",", "") or 0)
            except (TypeError, ValueError):
                continue
        cum = prior + season_hr.get(name, 0)
        if cum < min_career_hr:
            continue
        beaten = [
            (lc, ln) for ln in legend_cum
            if _norm_name(ln) != name and 0 < (lc := _cum_at(ln, age)) <= cum
        ]
        if not beaten:
            continue
        beaten_cum, beaten_name = max(beaten)
        above = [
            (lc, ln) for ln in legend_cum
            if _norm_name(ln) != name and (lc := _cum_at(ln, age)) > cum
        ]
        above_pair = min(above) if above else None
        scored.append((beaten_cum, name, age, cum, beaten_name, above_pair))

    out: list = []
    for beaten_cum, name, age, cum, beaten_name, above_pair in sorted(
            scored, reverse=True):
        if len(out) >= max_count:
            break
        signature = f"legend_compare|{name}|{age}|{cum}"
        if dedup_set is not None and signature in dedup_set:
            logger.info("legend_compare dedup skip %s", signature)
            continue
        above_line = (
            f"次は{above_pair[1]}の{age}歳時点 {above_pair[0]}本\n" if above_pair else ""
        )
        post = (
            f"【{name}】{age}歳シーズン時点 通算{cum}本塁打\n"
            f"{beaten_name}の{age}歳時点は{beaten_cum}本 — もう上回っている\n"
            + above_line
            + "#巨人 #ジャイアンツ"
        )
        fact = (
            f"通算{cum}本塁打 ({age}歳シーズン時点) ｜ "
            f"{beaten_name}の同年齢時点 {beaten_cum}本"
            + (f" ｜ 次は{above_pair[1]} {above_pair[0]}本" if above_pair else "")
        )
        draft = "\n".join([
            "【根拠: 新旧比較 (同年齢シーズン時点の通算本塁打)】",
            fact,
            "年齢=その年に迎える満年齢 (年度-生年)、 両者同一ルール",
            "出典: NPB公式 個人年度別成績 (legend_age_seasons / npb_career cache)"
            " + insight.db 今季分",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        image = b""
        if with_image:
            from src.x_post_image_gen_v2 import build_player_spotlight_data
            image = _try_png("player_spotlight", build_player_spotlight_data(
                title=f"{age}歳シーズン時点 通算本塁打",
                subtitle="新旧比較 ・ NPB公式 年度別成績",
                hook_line=f"★ {beaten_name}の同年齢を上回る ★",
                player_name=name,
                player_team="巨人",
                metric_label=f"{age}歳時点 通算本塁打",
                hero_value=f"{cum}本",
                sub_stats=[
                    {"label": f"{beaten_name} ({age}歳時点)", "value": f"{beaten_cum}本"},
                ] + ([{"label": f"{above_pair[1]} ({age}歳時点)",
                       "value": f"{above_pair[0]}本"}] if above_pair else []),
            ))
        out.append(Candidate(
            title=f"{name} {age}歳時点{cum}本 ({beaten_name}超え)",
            metric=_LEGEND_COMPARE_METRIC,
            period_label=f"{age}歳シーズン時点",
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player=name,
            db_fact_line=fact,
            team_level="first",
            sample_size=cum,
            sample_label=f"通算{cum}本塁打",
            why_now=f"レジェンド同年齢超えは続報が効く成長ストーリー枠",
            source_material_type="legend_compare",
            image_bytes=image,
        ))
    logger.info("legend_compare: built %d candidates (max=%d)", len(out), max_count)
    return out
