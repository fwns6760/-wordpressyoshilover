"""② 節目カウントダウン — 現役選手の通算記録が節目に接近したら記事化。

設計: spec/data-articles-no1-design.md §2 ②。
- データ: npb_career cache(467, npb_career.json)の通算 total(現役 65 名）。
- トリガ: 通算が次の節目まで 残り <= window(打者 30 / 投手 10)かつ 残り > 0。
- ゲート: 閾値・window 内のみ。乱発しない(career 節目は本来希少)。
- タイトル: case C 拡張 ``【巨人データ】{player} 通算{value}{unit}、{milestone}{unit}まであと{n}``。
- dedup: title に残り数を含めるため、title 再利用で「残り変化時のみ再掲」が自然成立。
  career 節目は低頻度なので 7 日 cooldown は自然充足。既定 draft、X 解放は §11 user 判断。
- 出力: data-insight と同じ {title, body_md, body_html, slug, player} 形式。

新タイプのため env DATA_INSIGHT_CAREER_MILESTONE=1 gate(default OFF)。
"""
from __future__ import annotations

import os as _os
from typing import Any, Optional

from src.analysis import ranking_article_publisher as _rap
from src.data_site_slug import player_slug
from src.npb_career_scraper import (
    _BAT_MILESTONES,
    _PIT_MILESTONES,
    _MILESTONE_LABEL,
    _career_int,
    _normalize_name,
)

SITE_DATA_BASE = "https://yoshilover.com/data"

# 接近とみなす残り幅(設計 §2②: 打者 <=30 / 投手 <=10)。
BAT_WINDOW = 30
PIT_WINDOW = 10

# 節目の意味づけ(名球会など)。無ければ generic 文。
_MILESTONE_MEANING: dict[tuple[str, int], str] = {
    ("安打", 2000): "名球会入りの資格となる通算2000安打",
    ("勝", 200): "名球会入りの資格となる通算200勝",
    ("セーブ", 250): "名球会入りの資格となる通算250セーブ",
    ("本塁打", 500): "球史でも限られた打者しか届かない通算500本塁打",
    ("本塁打", 400): "長距離砲の証となる通算400本塁打",
}


def enabled() -> bool:
    """env DATA_INSIGHT_CAREER_MILESTONE=1 で有効(新タイプのため default OFF)。"""
    return (_os.environ.get("DATA_INSIGHT_CAREER_MILESTONE", "0") or "0").strip() in (
        "1",
        "true",
        "True",
    )


def load_career_cache() -> dict[str, Any]:
    """npb_career cache を read(scrape はしない、publish 非ブロック)。無ければ {}。"""
    try:
        from src.npb_career_ingest import _download_cache

        return _download_cache() or {}
    except Exception:
        return {}


def _name_by_id(cache: dict[str, Any]) -> dict[str, str]:
    """npb_id -> 表示名(ids map の逆引き)。"""
    ids = cache.get("ids") or {}
    out: dict[str, str] = {}
    for name, npb_id in ids.items():
        # 同一 id に複数表記が来た場合は最初を採用(安定)。
        out.setdefault(str(npb_id), name)
    return out


def _stat_years_tail(table: dict, col: str, n: int = 3) -> list[tuple[str, int]]:
    """直近 n 年の (年度, その年の col 値)。pace 推定・推移表に使う。"""
    rows = list((table or {}).get("years") or [])
    rows = sorted(rows, key=lambda r: str(r.get("年度") or ""))
    out: list[tuple[str, int]] = []
    for r in rows[-n:]:
        v = _career_int(r.get(col))
        out.append((str(r.get("年度") or "").strip(), v if v is not None else 0))
    return out


def _pace_phrase(remaining: int, recent: list[tuple[str, int]]) -> str:
    """直近年平均ペースから到達見込みの一言。"""
    vals = [v for _, v in recent if v is not None]
    if not vals:
        return "通算記録の大台が射程に入った。"
    avg = sum(vals) / len(vals)
    if avg <= 0:
        return "今季のペース次第で大台が見えてくる。"
    if remaining <= avg:
        return "現在のペースなら今季中の到達も十分に見込める。"
    if remaining <= avg * 2:
        return "このペースなら来季にかけての到達が射程に入る。"
    return "中長期の射程だが、大台が確実に近づいている。"


def find_approaching(cache: dict[str, Any]) -> list[dict[str, Any]]:
    """cache から接近中(残り window 内）の節目候補を抽出。残りが小さい順。"""
    if not cache:
        return []
    players = cache.get("players") or {}
    names = _name_by_id(cache)
    out: list[dict[str, Any]] = []
    for npb_id, p in players.items():
        if not isinstance(p, dict) or not p:
            continue
        name = names.get(str(npb_id))
        if not name:
            continue
        is_pitcher = bool(p.get("is_pitcher"))
        table = (p.get("pitching") if is_pitcher else p.get("batting")) or {}
        total = table.get("total") or {}
        if not total:
            continue
        milestones, window = (
            (_PIT_MILESTONES, PIT_WINDOW) if is_pitcher else (_BAT_MILESTONES, BAT_WINDOW)
        )
        for col, thresholds in milestones.items():
            current = _career_int(total.get(col))
            if current is None:
                continue
            nxt = next((t for t in sorted(thresholds) if t > current), None)
            if nxt is None:
                continue
            remaining = nxt - current
            if not (0 < remaining <= window):
                continue
            unit = _MILESTONE_LABEL.get(col, col)
            out.append(
                {
                    "name": name,
                    "slug": player_slug(name),
                    "col": col,
                    "unit": unit,
                    "current": current,
                    "milestone": nxt,
                    "remaining": remaining,
                    "is_pitcher": is_pitcher,
                    "recent": _stat_years_tail(table, col),
                }
            )
    # 残りが小さい(到達が近い)順 → 同点は通算値が大きい順。
    out.sort(key=lambda c: (c["remaining"], -c["current"]))
    return out


def build_milestone_article(cand: dict[str, Any]) -> Optional[dict[str, str]]:
    name = cand["name"]
    unit = cand["unit"]
    current = cand["current"]
    milestone = cand["milestone"]
    remaining = cand["remaining"]
    slug = cand.get("slug") or _normalize_name(name)
    link = f"{SITE_DATA_BASE}/{slug}/"
    title = f"【巨人データ】{name} 通算{current}{unit}、{milestone}{unit}まであと{remaining}"
    meaning = _MILESTONE_MEANING.get(
        (unit, milestone), f"球史に名を刻む通算{milestone}{unit}"
    )
    pace = _pace_phrase(remaining, cand.get("recent") or [])

    recent = cand.get("recent") or []
    trend_rows = ["| 年度 | " + unit + " |", "|---|---|"]
    for yr, v in recent:
        if yr:
            trend_rows.append(f"| {yr} | {v} |")
    trend_md = "\n".join(trend_rows) if len(trend_rows) > 2 else ""

    body_md = f"""# {title}

## ひとこと

巨人 **{name}** の通算{unit}が **{current}** に到達。次の大台 **{milestone}{unit}まであと{remaining}** に迫った。
{pace}

## 直近の推移

{trend_md if trend_md else f"通算{current}{unit}（NPB 公式）。"}

## この節目の意味

{meaning}。到達すれば巨人の歴史にまた一つ記録が加わる。

## 出典・データについて

| 項目 | 内容 |
|---|---|
| 選手 | {name}(巨人) |
| 通算{unit} | {current} |
| 次の節目 | {milestone}{unit}(あと{remaining}) |
| データ元 | NPB 公式 |

[{name} の通算成績・年度別データを見る →]({link})
"""
    return {
        "title": title,
        "body_md": body_md,
        "body_html": _rap.markdown_to_html(body_md),
        "slug": slug,
        "player": name,
    }


def generate_articles(
    cache: Optional[dict[str, Any]] = None,
    *,
    max_articles: int = 3,
) -> list[dict[str, str]]:
    """接近中の節目を残りが近い順に max_articles 本。"""
    if cache is None:
        cache = load_career_cache()
    cands = find_approaching(cache)
    out: list[dict[str, str]] = []
    for cand in cands[:max_articles]:
        art = build_milestone_article(cand)
        if art:
            out.append(art)
    return out


def publish_approaching_milestone_articles(
    wp: Any,
    *,
    cache: Optional[dict[str, Any]] = None,
    max_articles: int = 3,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """接近中の節目記事を WP へ。dedup は title 再利用(残り数込み）に委ねる。

    status 未指定は env DATA_INSIGHT_CAREER_MILESTONE_STATUS(default 'draft')。
    新タイプのため安全側(draft)が既定、X 自動投稿は §11 user 判断。
    """
    if status is None:
        status = (
            _os.environ.get("DATA_INSIGHT_CAREER_MILESTONE_STATUS", "draft") or "draft"
        ).strip()
    arts = generate_articles(cache, max_articles=max_articles)
    cat = None
    try:
        cat = wp.resolve_category_id("コラム")
    except Exception:
        cat = None
    results: list[dict[str, Any]] = []
    for a in arts:
        try:
            pid = wp.create_post(
                title=a["title"],
                content=a["body_html"],
                categories=[cat] if cat else None,
                status=status,
                allow_title_only_reuse=True,
                caller="career_milestone",
            )
            results.append({"player": a["player"], "post_id": pid, "status": status})
        except Exception as exc:  # noqa: BLE001
            results.append({"player": a["player"], "error": f"{type(exc).__name__}:{exc}"})
    return results
