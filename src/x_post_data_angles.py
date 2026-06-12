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
    opponents: Optional[set[str]] = None,
) -> list:
    """「対○○キラー」対戦カード別打率の驚き候補 (シーズン比 +min_gap 以上)。

    ``preferred_players`` (今夜の話題選手 等) は閾値を満たす限り gap より優先。
    ``opponents`` を渡すとそのカードに限定 (試合前枠 = 今日の相手のみ、
    2026-06-12 user「試合前は関係あるものだけ」)。
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
        if opponents is not None and str(opp) not in opponents:
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
                as_of=f"{now.month}/{now.day}",
                compare_bars=[
                    {"label": f"対{opp}", "value": oavg,
                     "display": _fmt3(oavg), "highlight": True},
                    {"label": "シーズン", "value": savg, "display": _fmt3(savg)},
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
                metric_label=f"NPB通算{label} あと{remaining}{unit}",
                hero_value=str(row["value"]),
                as_of=f"{now.month}/{now.day}",
                compare_bars=[
                    {"label": str(above["name"]), "value": float(above["value"]),
                     "display": str(above["value"])},
                    {"label": str(name), "value": float(row["value"]),
                     "display": str(row["value"]), "highlight": True},
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
                as_of=f"{now.month}/{now.day}",
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
                as_of=f"{now.month}/{now.day}",
                compare_bars=[
                    {"label": name, "value": float(cum),
                     "display": f"{cum}本", "highlight": True},
                    {"label": beaten_name, "value": float(beaten_cum),
                     "display": f"{beaten_cum}本"},
                ] + ([{"label": str(above_pair[1]), "value": float(above_pair[0]),
                       "display": f"{above_pair[0]}本"}] if above_pair else []),
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


# ─── 7. あの日の巨人 (on this day) ───────────────────────────────────


_ON_THIS_DAY_METRIC = "あの日の巨人"


def _load_on_this_day() -> dict:
    """config/giants_on_this_day.json (web 裏取り済み bake-in) を読む。無ければ {}。"""
    import json as _json
    from pathlib import Path as _Path
    path = _Path(__file__).resolve().parent.parent / "config" / "giants_on_this_day.json"
    try:
        return (_json.loads(path.read_text(encoding="utf-8")) or {}).get("events") or {}
    except Exception as exc:  # noqa: BLE001
        logger.info("giants_on_this_day unavailable: %r", exc)
        return {}


def _load_ob_legends() -> dict:
    """config/ob_legends_full.json を読む。無ければ {}。"""
    import json as _json
    from pathlib import Path as _Path
    path = _Path(__file__).resolve().parent.parent / "config" / "ob_legends_full.json"
    try:
        return _json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.info("ob_legends unavailable: %r", exc)
        return {}


def build_on_this_day_candidates(
    *,
    now: Optional[datetime] = None,
    max_count: int = 1,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = False,
    events: Optional[dict] = None,
    legends: Optional[dict] = None,
) -> list:
    """【あの日の巨人】歴史 on this day。 在庫無限・毎日安定供給の枠 (角度③)。

    優先順: ①当日 MM-DD の裏取り済みイベント (giants_on_this_day.json) →
    ②OBレジェンドの「生まれた日」(ob_legends_full.json、 order 上位優先)。
    故人配慮で誕生日は「生まれた日」表記・年齢なし (祝い文言を入れない)。
    LLM 不使用・追加課金なし。 default は画像なし (歴史事実はテキストで十分)。
    """
    if now is None:
        now = datetime.now(JST)
    Candidate = _candidate_cls()
    md = f"{now.month:02d}-{now.day:02d}"
    label_date = f"{now.month}月{now.day}日"
    if events is None:
        events = _load_on_this_day()
    if legends is None:
        legends = _load_ob_legends()

    out: list = []

    def _emit(signature: str, headline: str, body_line: str, why: str,
              source_type: str, fact: str) -> None:
        if dedup_set is not None and signature in dedup_set:
            logger.info("on_this_day dedup skip %s", signature)
            return
        post = (
            f"【{label_date}】{headline}\n"
            + (f"{body_line}\n" if body_line else "")
            + "#巨人 #ジャイアンツ"
        )
        draft = "\n".join([
            "【根拠: あの日の巨人 (on this day、裏取り済み bake-in)】",
            fact,
            "出典: config/giants_on_this_day.json (source URL 併記) / "
            "ob_legends_full.json (NPB公式由来)",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        out.append(Candidate(
            title=f"あの日の巨人 {label_date}",
            metric=_ON_THIS_DAY_METRIC,
            period_label=label_date,
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player="",
            db_fact_line=fact,
            team_level="first",
            sample_size=0,
            sample_label="歴史枠",
            why_now=why,
            source_material_type=source_type,
            image_bytes=b"",
        ))

    # ① 裏取り済みイベント
    for ev in (events.get(md) or []):
        if len(out) >= max_count:
            break
        year, text = ev.get("year"), str(ev.get("text") or "").strip()
        if not year or not text:
            continue
        _emit(
            signature=f"on_this_day|{md}|{year}",
            headline=f"{year}年のきょう",
            body_line=text,
            why="歴史 on this day は毎日安定供給できる定番枠",
            source_type="on_this_day_event",
            fact=f"{year}年{label_date}: {text}",
        )

    # ② 誕生日 fallback (order 上位優先、 故人配慮で「生まれた日」・年齢なし)
    if len(out) < max_count:
        stats = (legends or {}).get("stats") or {}
        order = (legends or {}).get("order") or list(stats)
        suffix = f"-{md}"
        for name in order:
            if len(out) >= max_count:
                break
            v = stats.get(name) or {}
            birth = str(v.get("birth") or "")
            if not birth.endswith(suffix):
                continue
            npb = v.get("npb") or {}
            parts = []
            if npb.get("games"):
                parts.append(f"通算{npb['games']}試合")
            if npb.get("hr"):
                parts.append(f"{npb['hr']}本塁打")
            if npb.get("avg"):
                parts.append(f"打率{npb['avg']}")
            if npb.get("win"):
                parts.append(f"{npb['win']}勝")
            body = "・".join(parts[:3])
            _emit(
                signature=f"on_this_day|{md}|birth|{name}",
                headline=f"{birth[:4]}年、{name}が生まれた日",
                body_line=body,
                why="レジェンドの生まれた日 (歴史レジェンド層に刺さる枠)",
                source_type="on_this_day_birth",
                fact=f"{name} 生年月日 {birth} (NPB公式由来)" + (f" ｜ {body}" if body else ""),
            )

    logger.info("on_this_day: built %d candidates (max=%d)", len(out), max_count)
    return out


# ─── 8. 試合前見どころ (今日の試合プレビュー) ────────────────────────


_PREGAME_METRIC = "試合前見どころ"


def build_pregame_preview_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 1,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = False,
    upcoming_fn: Optional[Callable[[], list]] = None,
) -> list:
    """【今日の巨人】試合前プレビュー。 今日の試合に直結する数字だけを出す。

    2026-06-12 user「試合前はファンにためになるものだけ。 関係がないものを
    出すくらいなら出さない」。 gate:
    ①今日 (JST) に巨人戦がある ②試合開始前 ③insight.db の数字が 1 つ以上作れる
    — 全部満たさなければ空 list (埋め草を出さない)。
    日程/予告先発 = NPB公式 (data_site_query.fetch_giants_upcoming、 459/C 既存)。
    """
    if now is None:
        now = datetime.now(JST)
    if not db_path:
        return []
    Candidate = _candidate_cls()
    try:
        if upcoming_fn is None:
            from src.data_site_query import fetch_giants_upcoming
            upcoming_fn = fetch_giants_upcoming
        games = upcoming_fn() or []
    except Exception as exc:  # noqa: BLE001
        logger.info("pregame upcoming unavailable: %r", exc)
        return []
    if not games:
        return []
    g0 = games[0]
    if str(g0.get("date") or "") != now.date().isoformat():
        return []  # 今日の試合でない
    # 試合開始前のみ (time 例 '18:00'。 不明は 18:00 扱い)
    try:
        hh, mm = (str(g0.get("time") or "18:00").split(":") + ["0"])[:2]
        start = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except (TypeError, ValueError):
        start = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if now >= start:
        return []
    opp = str(g0.get("opp") or "").strip()
    if not opp:
        return []
    starter_g = _norm_name(str(g0.get("starter_g") or ""))
    starter_o = _norm_name(str(g0.get("starter_o") or ""))

    lines: list[str] = []
    facts: list[str] = []

    def _match_canon(rows: list, name: str) -> Optional[str]:
        for (canon,) in rows:
            c = _norm_name(canon or "")
            if c and (c == name or c.startswith(name) or name.startswith(c)):
                return canon
        return None

    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            if starter_g:
                canon_rows = conn.execute(
                    "SELECT DISTINCT player_canonical FROM pitching_logs "
                    "WHERE team_name='巨人' AND player_canonical IS NOT NULL",
                ).fetchall()
                canon = _match_canon(canon_rows, starter_g)
                if canon:
                    n, w, l, k, ip, er = conn.execute(
                        "SELECT COUNT(*), "
                        " SUM(CASE WHEN result_mark='○' THEN 1 ELSE 0 END), "
                        " SUM(CASE WHEN result_mark='●' THEN 1 ELSE 0 END), "
                        " SUM(COALESCE(K,0)), SUM(COALESCE(IP,0)), SUM(COALESCE(ER,0)) "
                        "FROM pitching_logs WHERE team_name='巨人' "
                        " AND player_canonical=? AND appearance_order=1",
                        (canon,),
                    ).fetchone()
                    if int(n or 0) > 0:
                        seg = f"今季{n}先発 {int(w or 0)}勝{int(l or 0)}敗"
                        if float(ip or 0) > 0:
                            seg += f"・防御率{9 * float(er or 0) / float(ip):.2f}"
                        seg += f"・{int(k or 0)}奪三振"
                        lines.append(f"先発 {canon}: {seg}")
                        facts.append(f"{canon} {seg}")
                        ow, ol = conn.execute(
                            "SELECT SUM(CASE WHEN p.result_mark='○' THEN 1 ELSE 0 END), "
                            " SUM(CASE WHEN p.result_mark='●' THEN 1 ELSE 0 END) "
                            "FROM pitching_logs p JOIN games g USING(game_id) "
                            "WHERE p.team_name='巨人' AND p.player_canonical=? "
                            " AND p.appearance_order=1 AND g.opponent=?",
                            (canon, opp),
                        ).fetchone()
                        if int(ow or 0) + int(ol or 0) > 0:
                            lines.append(f"対{opp} 今季{int(ow or 0)}勝{int(ol or 0)}敗")
                            facts.append(f"対{opp} {int(ow or 0)}勝{int(ol or 0)}敗")
            # 打線: 対今日の相手 今季打率トップ (10打数以上)
            top = conn.execute(
                "SELECT b.player_canonical, SUM(COALESCE(b.AB,0)), "
                " SUM(COALESCE(b.H,0)) "
                "FROM batting_logs b JOIN games g USING(game_id) "
                "WHERE b.team_name='巨人' AND b.player_canonical IS NOT NULL "
                " AND g.opponent=? GROUP BY b.player_canonical "
                "HAVING SUM(COALESCE(b.AB,0)) >= 10 "
                "ORDER BY CAST(SUM(COALESCE(b.H,0)) AS REAL)"
                "/SUM(COALESCE(b.AB,0)) DESC LIMIT 1",
                (opp,),
            ).fetchone()
            if top:
                canon_b, ab, h = top[0], int(top[1]), int(top[2])
                lines.append(f"対{opp}キーマン {canon_b}: 打率{_fmt3(h / ab)} ({h}安打/{ab}打数)")
                facts.append(f"{canon_b} 対{opp} {_fmt3(h / ab)} ({h}/{ab})")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pregame preview query failed: %r", exc)
        return []

    if not lines:
        logger.info("pregame preview: no relevant numbers — skip (埋め草を出さない)")
        return []

    vs_line = f"予告先発 {starter_g or '未発表'}" + (f" vs {starter_o}" if starter_o else "")
    place = str(g0.get("place") or "").strip()
    time_s = str(g0.get("time") or "").strip()
    head = f"今日の巨人 vs {opp}" + (f" ({place} {time_s})" if place or time_s else "")
    signature = f"pregame|{now.date().isoformat()}|{opp}"
    if dedup_set is not None and signature in dedup_set:
        logger.info("pregame dedup skip %s", signature)
        return []
    post = (
        f"【{head}】\n" + vs_line + "\n" + "\n".join(lines[:3]) + "\n#巨人 #ジャイアンツ"
    )
    draft = "\n".join([
        "【根拠: 試合前見どころ (今日の試合に直結する数字のみ)】",
        " ｜ ".join(facts),
        "出典: NPB公式 日程・予告先発 + insight.db 今季集計",
        "参照: https://yoshilover.com/data/",
        "",
        "【X 投稿案 (user が手で投稿)】",
        post,
    ])
    logger.info("pregame preview: built 1 candidate (opp=%s lines=%d)", opp, len(lines))
    return [Candidate(
        title=f"今日の巨人 vs {opp} 試合前見どころ",
        metric=_PREGAME_METRIC,
        period_label="今日の試合",
        draft_text=draft,
        char_count=len(post),
        signature=signature,
        post_text=post,
        focus_player="",
        db_fact_line=" ｜ ".join(facts),
        team_level="first",
        sample_size=len(lines),
        sample_label="試合前枠",
        why_now=f"今日の{opp}戦に直結 (試合前はためになる情報のみ)",
        source_material_type="pregame_preview",
        image_bytes=b"",
    )][:max_count]


# ─── 9. 年俸コスパ (データ×年俸クロス、 バーゲン型のみ) ─────────────


_SALARY_VALUE_METRIC = "年俸コスパ"


def _load_giants_salary_2026() -> dict[str, int]:
    """config/giants_salary.json から {正規化名: 2026年俸(万円)} (巨人現役のみ)。"""
    import json as _json
    from pathlib import Path as _Path
    path = _Path(__file__).resolve().parent.parent / "config" / "giants_salary.json"
    try:
        d = _json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        logger.info("giants_salary unavailable: %r", exc)
        return {}
    out: dict[str, int] = {}
    for p in d.get("players") or []:
        if not p.get("active"):
            continue
        for y in p.get("years") or []:
            if y.get("year") == 2026 and y.get("team") == "巨人" and y.get("salary_man"):
                out[_norm_name(p.get("name") or "")] = int(y["salary_man"])
                break
    return out


def build_salary_value_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 1,
    min_hits: int = 20,
    bargain_ratio: float = 0.5,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = False,
    salary_map: Optional[dict[str, int]] = None,
) -> list:
    """【年俸コスパ】1安打あたり◯万円の「バーゲン」若手を出す驚き候補。

    データ×年俸クロス (2026-06-12 user「これいいね」)。 **割安側のみ**:
    高年俸×不振の「割高」型は炎上リスクのため出さない (年俸絡みの negative 禁止)。
    驚きゲート: 規定 (min_hits 安打以上) の中で単価がチーム中央値の
    bargain_ratio 倍未満の選手だけ。 年俸 = 検証済み giants_salary.json (推定・公表ベース)。
    """
    if now is None:
        now = datetime.now(JST)
    if not db_path:
        return []
    Candidate = _candidate_cls()
    if salary_map is None:
        salary_map = _load_giants_salary_2026()
    if not salary_map:
        return []
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT player_canonical, SUM(COALESCE(AB,0)), SUM(COALESCE(H,0)), "
                " SUM(COALESCE(RBI,0)) "
                "FROM batting_logs WHERE team_name='巨人' "
                " AND player_canonical IS NOT NULL GROUP BY player_canonical",
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("salary_value query failed: %r", exc)
        return []

    priced: list[tuple] = []
    for canon, ab, h, rbi in rows:
        h, ab, rbi = int(h or 0), int(ab or 0), int(rbi or 0)
        if h < min_hits:
            continue
        sal = salary_map.get(_norm_name(canon))
        if not sal:
            continue
        priced.append((sal / h, canon, sal, h, ab, rbi))
    if len(priced) < 3:  # 中央値が意味を持つ最低限
        logger.info("salary_value: too few priced regulars (%d)", len(priced))
        return []
    priced.sort()
    median_unit = priced[len(priced) // 2][0]

    out: list = []
    for unit, canon, sal, h, ab, rbi in priced:
        if len(out) >= max_count:
            break
        if unit >= median_unit * bargain_ratio:
            break  # 単価昇順なので以降は全部ゲート外
        signature = f"salary_value|{canon}|{h}"
        if dedup_set is not None and signature in dedup_set:
            logger.info("salary_value dedup skip %s", signature)
            continue
        sal_disp = f"{sal / 10000:.1f}億円".replace(".0億", "億") if sal >= 10000 else f"{sal}万円"
        post = (
            f"【{canon}】今季{h}安打 (打率{_fmt3(h / ab)}・{rbi}打点)\n"
            f"推定年俸{sal_disp} — 1安打あたり約{unit:,.0f}万円\n"
            f"チーム中央値 (約{median_unit:,.0f}万円/安打) の半分以下のバーゲン\n"
            + _streak_line(db_path, canon)
            + "#巨人 #ジャイアンツ"
        )
        fact = (
            f"今季{h}安打/{ab}打数・{rbi}打点 ｜ 推定年俸{sal_disp} ｜ "
            f"1安打 約{unit:,.0f}万円 (チーム中央値 約{median_unit:,.0f}万円)"
        )
        draft = "\n".join([
            "【根拠: 年俸コスパ (データ×年俸クロス、 割安側のみ)】",
            fact,
            "出典: giants_salary.json (推定年俸、 出典note付き検証済) + insight.db 今季",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        out.append(Candidate(
            title=f"{canon} 年俸コスパ (1安打{unit:,.0f}万円)",
            metric=_SALARY_VALUE_METRIC,
            period_label="今シーズン",
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player=canon,
            db_fact_line=fact,
            team_level="first",
            sample_size=h,
            sample_label=f"今季{h}安打",
            why_now="若手バーゲンは球団の編成文脈でも語れる独自クロス",
            source_material_type="salary_value",
            image_bytes=b"",
        ))
    logger.info("salary_value: built %d candidates (max=%d)", len(out), max_count)
    return out


# ─── 10. 節目達成 + 今季初・以来 (chikupn型、 2026-06-12 user「入れます」) ──


_MILESTONE_METRIC = "節目達成"
_RARITY_METRIC = "今季初・以来"

# 通算節目 (丸い数字のみ。 到達した瞬間だけ祝う)
_MILESTONES = {
    "本塁打": (50, 100, 150, 200, 250, 300, 350, 400, 450, 500),
    "安打": (500, 1000, 1500, 2000, 2500),
    "勝利": (50, 100, 150, 200),
    "奪三振": (500, 1000, 1500, 2000),
}


def _career_prior_totals(career_cache: dict, *, before_year: int) -> dict[str, dict[str, int]]:
    """npb_career cache から {正規化名: {本塁打/安打/勝利/奪三振: before_year より前の通算}}。"""
    out: dict[str, dict[str, int]] = {}
    ids = (career_cache or {}).get("ids") or {}
    players = (career_cache or {}).get("players") or {}
    name_by_id = {str(v): k for k, v in ids.items()}
    for npb_id, payload in players.items():
        name = _norm_name(name_by_id.get(str(npb_id), ""))
        if not name:
            continue
        tot = {"本塁打": 0, "安打": 0, "勝利": 0, "奪三振": 0}
        for r in ((payload or {}).get("batting") or {}).get("years") or []:
            try:
                if int(r.get("年度")) >= before_year:
                    continue
            except (TypeError, ValueError):
                continue
            for col, key in (("本塁打", "本塁打"), ("安打", "安打")):
                try:
                    tot[key] += int(str(r.get(col) or "0").replace(",", "") or 0)
                except (TypeError, ValueError):
                    pass
        for r in ((payload or {}).get("pitching") or {}).get("years") or []:
            try:
                if int(r.get("年度")) >= before_year:
                    continue
            except (TypeError, ValueError):
                continue
            for col, key in (("勝利", "勝利"), ("三振", "奪三振")):
                try:
                    tot[key] += int(str(r.get(col) or "0").replace(",", "") or 0)
                except (TypeError, ValueError):
                    pass
        out[name] = tot
    return out


def build_milestone_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 1,
    max_age_days: int = 2,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = False,
    career_cache: Optional[dict] = None,
) -> list:
    """【通算◯◯達成🎉】直近試合で丸い節目を跨いだ巨人選手を祝う (chikupn 高梨50勝型)。

    判定 = 通算(過去年度 npb_career + 今季 insight.db) が直近試合の寄与で節目を跨いだ
    時のみ。 跨ぎ検出なので毎日は出ない (出ない日が正常)。
    """
    if now is None:
        now = datetime.now(JST)
    if not db_path:
        return []
    Candidate = _candidate_cls()
    if career_cache is None:
        try:
            from src.analysis.career_milestone import load_career_cache
            career_cache = load_career_cache()
        except Exception as exc:  # noqa: BLE001
            logger.info("milestone career cache unavailable: %r", exc)
            return []
    prior = _career_prior_totals(career_cache, before_year=now.year)
    if not prior:
        return []

    import json as _json
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            latest = conn.execute("SELECT (SELECT MAX(g.game_date) FROM games g WHERE EXISTS(SELECT 1 FROM batting_logs b2 WHERE b2.game_id=g.game_id AND b2.team_name='巨人'))").fetchone()[0]
            if not latest:
                return []
            age = (now.date() - datetime.strptime(latest, "%Y-%m-%d").date()).days
            if age > max_age_days:
                return []
            season: dict[str, dict[str, int]] = {}
            last: dict[str, dict[str, int]] = {}
            for canon, gd, aj, h in conn.execute(
                "SELECT b.player_canonical, g.game_date, b.atbats_json, "
                " COALESCE(b.H,0) FROM batting_logs b JOIN games g USING(game_id) "
                "WHERE b.team_name='巨人' AND b.player_canonical IS NOT NULL",
            ):
                n = _norm_name(canon)
                hr = 0
                try:
                    hr = sum(1 for c in _json.loads(aj or "[]") if "本" in str(c))
                except Exception:  # noqa: BLE001
                    pass
                season.setdefault(n, {"本塁打": 0, "安打": 0})
                season[n]["本塁打"] += hr
                season[n]["安打"] += int(h or 0)
                if gd == latest:
                    last.setdefault(n, {"本塁打": 0, "安打": 0})
                    last[n]["本塁打"] += hr
                    last[n]["安打"] += int(h or 0)
            p_season: dict[str, dict[str, int]] = {}
            p_last: dict[str, dict[str, int]] = {}
            for canon, gd, mark, k in conn.execute(
                "SELECT p.player_canonical, g.game_date, p.result_mark, "
                " COALESCE(p.K,0) FROM pitching_logs p JOIN games g USING(game_id) "
                "WHERE p.team_name='巨人' AND p.player_canonical IS NOT NULL",
            ):
                n = _norm_name(canon)
                w = 1 if mark == "○" else 0
                p_season.setdefault(n, {"勝利": 0, "奪三振": 0})
                p_season[n]["勝利"] += w
                p_season[n]["奪三振"] += int(k or 0)
                if gd == latest:
                    p_last.setdefault(n, {"勝利": 0, "奪三振": 0})
                    p_last[n]["勝利"] += w
                    p_last[n]["奪三振"] += int(k or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("milestone query failed: %r", exc)
        return []

    display_by_norm: dict[str, str] = {}
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            for (c,) in conn.execute(
                "SELECT DISTINCT player_canonical FROM batting_logs WHERE team_name='巨人' "
                "UNION SELECT DISTINCT player_canonical FROM pitching_logs WHERE team_name='巨人'"):
                if c:
                    display_by_norm[_norm_name(c)] = c
    except Exception:  # noqa: BLE001
        pass

    hits: list[tuple] = []
    for n, pr in prior.items():
        for stat, season_map, last_map in (
                ("本塁打", season, last), ("安打", season, last),
                ("勝利", p_season, p_last), ("奪三振", p_season, p_last)):
            s_tot = (season_map.get(n) or {}).get(stat, 0)
            l_tot = (last_map.get(n) or {}).get(stat, 0)
            if l_tot <= 0:
                continue
            total = pr.get(stat, 0) + s_tot
            before = total - l_tot
            for m in _MILESTONES[stat]:
                if before < m <= total:
                    hits.append((m, stat, n, total, s_tot))
    out: list = []
    for m, stat, n, total, s_tot in sorted(hits, reverse=True):
        if len(out) >= max_count:
            break
        name = display_by_norm.get(n, n)
        signature = f"milestone|{n}|{stat}|{m}"
        if dedup_set is not None and signature in dedup_set:
            logger.info("milestone dedup skip %s", signature)
            continue
        unit = "勝" if stat == "勝利" else ("本" if stat == "本塁打" else
                                          ("安打" if stat == "安打" else "奪三振"))
        post = (
            f"【{name}】NPB通算{m}{unit if stat != '安打' else '安打'} 達成🎉\n"
            f"通算{total}{unit if stat != '安打' else '安打'} (今季{s_tot})\n"
            f"#巨人 #ジャイアンツ"
        )
        fact = f"通算{stat} {total} (今季{s_tot}) ｜ 節目 {m} を直近試合で跨いだ"
        draft = "\n".join([
            "【根拠: 通算節目達成 (npb_career 通算 + insight.db 今季の跨ぎ検出)】",
            fact,
            "出典: NPB公式 通算 + 公式box今季集計",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        out.append(Candidate(
            title=f"{name} 通算{m}{stat} 達成",
            metric=_MILESTONE_METRIC,
            period_label="通算",
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player=name,
            db_fact_line=fact,
            team_level="first",
            sample_size=total,
            sample_label=f"通算{total}",
            why_now="節目達成は当日が一番伸びる祝い枠",
            source_material_type="milestone",
            image_bytes=b"",
        ))
    logger.info("milestone: built %d candidates (max=%d)", len(out), max_count)
    return out


def _parse_rot_ip(s: str) -> float:
    """rotation の ip 表記 ('9' / '61/3' = 6 1/3) を float に。"""
    s = str(s or "").strip()
    if not s:
        return 0.0
    try:
        if s.endswith(("0/3", "1/3", "2/3")) and len(s) >= 3:
            whole = s[:-3] or "0"
            return float(whole) + int(s[-3]) / 3.0
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _load_rotation_years() -> list:
    """config/starter_rotation_2007_2026.json (baked、 20年分) を読む。無ければ []。"""
    import json as _json
    from pathlib import Path as _Path
    path = _Path(__file__).resolve().parent.parent / "config" / "starter_rotation_2007_2026.json"
    try:
        d = _json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else (d.get("years") or [])
    except Exception as exc:  # noqa: BLE001
        logger.info("rotation history unavailable: %r", exc)
        return []


def _last_rotation_occurrence(years: list, pred, *, before_year: int) -> Optional[tuple]:
    """rotation 年度別 games から pred を満たす直近の (年, '06月05日', 投手) を返す。"""
    import re as _re
    for y in sorted(years, key=lambda v: -int(v.get("year") or 0)):
        yr = int(y.get("year") or 0)
        if yr >= before_year:
            continue
        for g in reversed(y.get("games") or []):
            try:
                if pred(g):
                    return (yr, str(g.get("date") or ""), str(g.get("pitcher") or ""))
            except Exception:  # noqa: BLE001
                continue
    return None


def build_rarity_candidates(
    db_path: str,
    *,
    now: Optional[datetime] = None,
    max_count: int = 1,
    max_age_days: int = 2,
    max_nth: int = 3,
    dedup_set: Optional[set[str]] = None,
    with_image: bool = False,
    rotation_years: Optional[list] = None,
) -> list:
    """「今季初・今季◯度目・◯◯以来」希少性 angle (chikupn の驚きの正体)。

    直近試合で起きた事象だけを対象に:
    - チーム 1試合3本塁打以上 → 今季◯度目 (max_nth 度目まで = 希少な内だけ)
    - 1イニング5得点以上 → 今季◯度目
    - 先発の完投 / 完封 → 前回を今季 insight.db → rotation 20年資産で遡って「以来」
    巨人限定。 事象が無い日は 0 件 (それが正常)。
    """
    if now is None:
        now = datetime.now(JST)
    if not db_path:
        return []
    Candidate = _candidate_cls()
    import json as _json

    found: list[dict] = []
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            latest, latest_opp = (conn.execute(
                "SELECT g.game_date, g.opponent FROM games g WHERE EXISTS("
                "SELECT 1 FROM batting_logs b2 WHERE b2.game_id=g.game_id"
                " AND b2.team_name='巨人') ORDER BY g.game_date DESC LIMIT 1"
            ).fetchone() or (None, None))
            if not latest:
                return []
            age = (now.date() - datetime.strptime(latest, "%Y-%m-%d").date()).days
            if age > max_age_days:
                return []
            label_d = f"{int(latest[5:7])}/{int(latest[8:10])}"

            # A. チーム 1試合3本塁打以上 (atbats_json「本」cell/試合)
            hr_by_game: dict[str, int] = {}
            for gid, gd, aj in conn.execute(
                "SELECT b.game_id, g.game_date, b.atbats_json "
                "FROM batting_logs b JOIN games g USING(game_id) "
                "WHERE b.team_name='巨人' AND b.atbats_json IS NOT NULL",
            ):
                try:
                    hr_by_game[gd] = hr_by_game.get(gd, 0) + sum(
                        1 for c in _json.loads(aj) if "本" in str(c))
                except Exception:  # noqa: BLE001
                    pass
            last_hr = hr_by_game.get(latest, 0)
            if last_hr >= 3:
                nth = sum(1 for gd, v in hr_by_game.items()
                          if v >= last_hr and gd <= latest)
                if nth <= max_nth:
                    nth_label = "今季初" if nth == 1 else f"今季{nth}度目"
                    found.append({
                        "key": f"team_hr{last_hr}",
                        "head": f"巨人、1試合{last_hr}本塁打",
                        "body": f"{label_d} {latest_opp}戦 — {nth_label}",
                        "fact": f"{latest} 対{latest_opp} チーム{last_hr}本塁打 ({nth_label})",
                    })

            # B. 1イニング5得点以上 (inning_scores giants 行)
            big_by_game: dict[str, int] = {}
            for gd, ij in conn.execute(
                "SELECT g.game_date, i.inning_json FROM inning_scores i "
                "JOIN games g USING(game_id) WHERE i.team_role='giants'",
            ):
                try:
                    runs = [int(x) for x in _json.loads(ij or "[]")
                            if str(x).isdigit()]
                except Exception:  # noqa: BLE001
                    continue
                if runs:
                    big_by_game[gd] = max(big_by_game.get(gd, 0), max(runs))
            last_big = big_by_game.get(latest, 0)
            if last_big >= 5:
                nth = sum(1 for gd, v in big_by_game.items()
                          if v >= last_big and gd <= latest)
                if nth <= max_nth:
                    nth_label = "今季初" if nth == 1 else f"今季{nth}度目"
                    found.append({
                        "key": f"big_inning{last_big}",
                        "head": f"巨人、1イニング{last_big}得点のビッグイニング",
                        "body": f"{label_d} {latest_opp}戦 — {nth_label}",
                        "fact": f"{latest} 対{latest_opp} 1イニング{last_big}得点 ({nth_label})",
                    })

            # C. 先発の完投 / 完封 → 「◯◯以来」 (今季 → rotation 20年遡り)
            row = conn.execute(
                "SELECT p.player_canonical, p.IP, COALESCE(p.R,0), COALESCE(p.K,0) "
                "FROM pitching_logs p JOIN games g USING(game_id) "
                "WHERE p.team_name='巨人' AND p.appearance_order=1 "
                " AND g.game_date=?", (latest,),
            ).fetchone()
            if row and float(row[1] or 0) >= 9.0:
                canon, _ip, runs_allowed, _k = row[0], row[1], int(row[2]), row[3]
                shutout = runs_allowed == 0
                # 今季の前回完投
                prev = conn.execute(
                    "SELECT g.game_date, p.player_canonical "
                    "FROM pitching_logs p JOIN games g USING(game_id) "
                    "WHERE p.team_name='巨人' AND p.appearance_order=1 "
                    " AND COALESCE(p.IP,0) >= 9 AND g.game_date < ? "
                    "ORDER BY g.game_date DESC LIMIT 1", (latest,),
                ).fetchone()
                if prev:
                    since = f"{int(prev[0][5:7])}/{int(prev[0][8:10])}の{prev[1]}以来 (今季)"
                else:
                    if rotation_years is None:
                        rotation_years = _load_rotation_years()
                    occ = _last_rotation_occurrence(
                        rotation_years,
                        lambda g: _parse_rot_ip(g.get("ip")) >= 9.0
                        and (not shutout or str(g.get("runs") or "") == "0"),
                        before_year=now.year)
                    since = (f"{occ[0]}年{occ[1]} {occ[2]}以来" if occ else "")
                word = "完封勝利" if shutout else "完投"
                found.append({
                    "key": f"complete_game|{_norm_name(canon)}",
                    "head": f"{canon}、{word}",
                    "body": (f"巨人投手の{word}は{since}" if since
                             else f"{label_d} {latest_opp}戦"),
                    "fact": f"{latest} 対{latest_opp} {canon} {word}"
                            + (f" ｜ 前回={since}" if since else ""),
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("rarity query failed: %r", exc)
        return []

    out: list = []
    for ev in found:
        if len(out) >= max_count:
            break
        signature = f"rarity|{ev['key']}|{latest}"
        if dedup_set is not None and signature in dedup_set:
            logger.info("rarity dedup skip %s", signature)
            continue
        post = (
            f"【{ev['head']}】\n{ev['body']}\n#巨人 #ジャイアンツ"
        )
        draft = "\n".join([
            "【根拠: 今季初・以来 (希少性、 insight.db + rotation 2007〜の遡り)】",
            ev["fact"],
            "出典: NPB公式box (insight.db) / 先発ローテ20年資産",
            "参照: https://yoshilover.com/data/",
            "",
            "【X 投稿案 (user が手で投稿)】",
            post,
        ])
        out.append(Candidate(
            title=ev["head"],
            metric=_RARITY_METRIC,
            period_label="直近試合",
            draft_text=draft,
            char_count=len(post),
            signature=signature,
            post_text=post,
            focus_player="",
            db_fact_line=ev["fact"],
            team_level="first",
            sample_size=0,
            sample_label="希少事象",
            why_now="「今季初/◯◯以来」の希少性は数字単体より刺さる (chikupn型)",
            source_material_type="rarity",
            image_bytes=b"",
        ))
    logger.info("rarity: built %d candidates (max=%d)", len(out), max_count)
    return out
