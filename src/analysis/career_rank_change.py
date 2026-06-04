"""④ 通算ランキング変動 — 現役が全史 NPB通算ランキングで順位を上げたら記事化。

設計: spec/data-articles-no1-design.md §2④。共有部品 alltime_ranking を消費。
- トリガ: 現役の順位が前回 snapshot より上昇し、かつ
  (順位 band[10,20,50,100] をまたいだ OR 今回順位 <= 50)= 全史上位の動きのみ。
- 「抜いた相手」= 今回 1 つ下の順位の選手(順位上昇時に追い抜いた人)。
- タイトル case C 拡張: ``【巨人データ】{player} NPB通算{label}{value}、歴代{rank}位に浮上({抜いた相手}を抜く)``。
- dedup: title に順位を含めるため title 再利用で「順位変化時のみ再掲」が自然成立。
- 初回 run は前回 snapshot 無し → 記事 0(baseline 保存のみ)。
- 既定 draft、X 解放は §11 user 判断。env DATA_INSIGHT_RANK_CHANGE=1 gate(default OFF)。
"""
from __future__ import annotations

import os as _os
from typing import Any, Optional

from src.analysis import alltime_ranking as _ar
from src.analysis import ranking_article_publisher as _rap

SITE_DATA_BASE = "https://yoshilover.com/data"

# 今回順位がこれ以下なら band 非またぎでも記事化(全史上位の動きは常に価値)。
TOP_RANK_ALWAYS = 50


def enabled() -> bool:
    return (_os.environ.get("DATA_INSIGHT_RANK_CHANGE", "0") or "0").strip() in (
        "1",
        "true",
        "True",
    )


def _crossed_band(prev_rank: int, today_rank: int) -> Optional[int]:
    """prev_rank(大) -> today_rank(小)で band[10,20,50,100]をまたいだ最小 band。"""
    for b in sorted(_ar.RANK_BANDS):
        if prev_rank > b >= today_rank:
            return b
    return None


def detect_rank_changes(
    today_ranks: dict[str, dict[str, dict[str, Any]]],
    prev_snapshot: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    """今回 current_player_ranks と前回 snapshot を比較し、上昇イベントを抽出。"""
    if not prev_snapshot:
        return []
    prev_ranks = prev_snapshot.get("ranks") or {}
    changes: list[dict[str, Any]] = []
    for stat_key, players in today_ranks.items():
        prev_players = prev_ranks.get(stat_key) or {}
        for name, info in players.items():
            prev = prev_players.get(name)
            if not prev:
                continue
            today_rank = info["rank"]
            prev_rank = prev.get("rank")
            if prev_rank is None or today_rank >= prev_rank:
                continue  # 上昇していない
            band = _crossed_band(prev_rank, today_rank)
            if band is None and today_rank > TOP_RANK_ALWAYS:
                continue  # 上位でもなく band もまたいでいない → skip
            changes.append(
                {
                    "stat_key": stat_key,
                    "label": _ar.STAT_SPECS[stat_key]["label"],
                    "name": name,
                    "slug": info.get("slug"),
                    "value": info["value"],
                    "today_rank": today_rank,
                    "prev_rank": prev_rank,
                    "passed": info.get("below_name"),
                    "band": band,
                }
            )
    # 上位(順位が小さい)順に優先。
    changes.sort(key=lambda c: c["today_rank"])
    return changes


def build_article(change: dict[str, Any]) -> Optional[dict[str, str]]:
    name = change["name"]
    label = change["label"]
    value = change["value"]
    rank = change["today_rank"]
    passed = change.get("passed")
    slug = change.get("slug") or ""
    link = f"{SITE_DATA_BASE}/{slug}/" if slug else SITE_DATA_BASE
    passed_suffix = f"({passed}を抜く)" if passed else ""
    title = f"【巨人データ】{name} NPB通算{label}{value}、歴代{rank}位に浮上{passed_suffix}"

    band = change.get("band")
    band_line = (
        f"歴代{band}位以内に到達した。" if band else "巨人の歴史でも上位に食い込む数字だ。"
    )
    passed_line = (
        f"{passed} を抜いて歴代{rank}位。" if passed else f"歴代{rank}位に浮上。"
    )

    body_md = f"""# {title}

## ひとこと

巨人 **{name}** の NPB通算{label}が **{value}** に到達し、巨人に在籍した選手の全史ランキングで **歴代{rank}位** に浮上した。
{passed_line}{band_line}

## この記録について

| 項目 | 内容 |
|---|---|
| 選手 | {name}(巨人) |
| NPB通算{label} | {value} |
| 全史順位 | 歴代{rank}位 |
| 直前順位 | 歴代{change['prev_rank']}位 |
| データ元 | NPB 公式 / 巨人OB 通算記録 |

※ ランキングは巨人に在籍した選手の **NPB通算**(全球団含む)記録で集計。

[{name} の通算成績・年度別データを見る →]({link})
"""
    return {
        "title": title,
        "body_md": body_md,
        "body_html": _rap.markdown_to_html(body_md),
        "slug": slug,
        "player": name,
    }


def run_and_publish(
    wp: Any,
    *,
    ob_stats: Optional[dict[str, dict]] = None,
    career_cache: Optional[dict[str, Any]] = None,
    max_articles: int = 3,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """全史ランキング算出 → 前回 snapshot と比較 → 上昇を記事化 → snapshot 更新。

    初回(前回 snapshot 無し)は baseline 保存のみで記事 0。
    """
    if status is None:
        status = (
            _os.environ.get("DATA_INSIGHT_RANK_CHANGE_STATUS", "draft") or "draft"
        ).strip()
    if career_cache is None:
        try:
            from src.analysis.career_milestone import load_career_cache

            career_cache = load_career_cache()
        except Exception:
            career_cache = {}

    rankings = _ar.build_rankings(ob_stats, career_cache)
    today_ranks = _ar.current_player_ranks(rankings)
    prev = _ar.load_snapshot()
    changes = detect_rank_changes(today_ranks, prev)

    results: list[dict[str, Any]] = []
    cat = None
    try:
        cat = wp.resolve_category_id("コラム")
    except Exception:
        cat = None
    for change in changes[:max_articles]:
        art = build_article(change)
        if not art:
            continue
        try:
            pid = wp.create_post(
                title=art["title"],
                content=art["body_html"],
                categories=[cat] if cat else None,
                status=status,
                allow_title_only_reuse=True,
                caller="career_rank_change",
            )
            results.append({"player": art["player"], "post_id": pid, "status": status})
        except Exception as exc:  # noqa: BLE001
            results.append({"player": art["player"], "error": f"{type(exc).__name__}:{exc}"})

    # snapshot 更新(記事化の有無に関わらず最新順位を保存)。
    _ar.save_snapshot({"ranks": today_ranks})
    return {"published": results, "changes_detected": len(changes), "had_prev": bool(prev)}
