"""③ 今日は何の日(OB)— OB の誕生日が当日に一致する記事を生成。

設計: spec/data-articles-no1-design.md §2 ③。
- データ: config/ob_legends_full.json(birth / npb / years / honors / slug / type)。
- トリガ: 今日(JST)の月日 == OB の生年月日の月日。
- ゲート: 看板級OB(honors有 or 通算閾値)に限定し、1日 max_articles 本まで
  (無名選手の誕生日乱発=thin/spam を回避)。
- 出力: data-insight と同じ {title, body_md, body_html, slug, player} 形式。
  publish 連携・X 解放は別途(X 自動投稿は §11 user 判断)。
"""
from __future__ import annotations

import datetime as dt
import json as _json
import os as _os
from pathlib import Path as _Path
from typing import Any, Optional

from src.analysis import ranking_article_publisher as _rap

SITE_DATA_BASE = "https://yoshilover.com/data"
JST = dt.timezone(dt.timedelta(hours=9))
_OB_FULL_PATH = _Path(__file__).resolve().parents[2] / "config" / "ob_legends_full.json"


def load_ob_stats() -> dict[str, dict]:
    """config/ob_legends_full.json の stats(name -> entry)。無ければ空。"""
    try:
        return (_json.loads(_OB_FULL_PATH.read_text(encoding="utf-8")) or {}).get("stats", {}) or {}
    except Exception:
        return {}


def today_jst() -> dt.date:
    # Date.now 系は使えない環境があるため呼び出し側で差し替え可能にしておく。
    return dt.datetime.now(JST).date()


def _birth_md(birth: str) -> Optional[tuple[int, int]]:
    """'1957-07-16' -> (7, 16)。失敗時 None。"""
    try:
        parts = str(birth).split("-")
        return int(parts[1]), int(parts[2])
    except (IndexError, ValueError, TypeError):
        return None


def _is_notable(entry: dict) -> bool:
    """看板級OBか(誕生日記事に値するか)。"""
    if entry.get("honors"):
        return True
    npb = entry.get("npb") or {}
    if entry.get("type") == "pitcher":
        return (npb.get("games") or 0) >= 200 or (npb.get("w") or 0) >= 50
    return (npb.get("games") or 0) >= 500 or (npb.get("hr") or 0) >= 100


def _career_magnitude(entry: dict) -> int:
    """並び替え用の重み(看板度)。honors数 + 通算規模。"""
    npb = entry.get("npb") or {}
    base = 100000 * len(entry.get("honors") or [])
    if entry.get("type") == "pitcher":
        return base + (npb.get("w") or 0) * 100 + (npb.get("games") or 0)
    return base + (npb.get("hr") or 0) * 100 + (npb.get("games") or 0)


def _career_line(entry: dict) -> str:
    npb = entry.get("npb") or {}
    if entry.get("type") == "pitcher":
        bits = []
        if npb.get("games") is not None:
            bits.append(f"{npb['games']}登板")
        if npb.get("w") is not None:
            bits.append(f"{npb['w']}勝")
        if npb.get("era") is not None:
            bits.append(f"防御率{npb['era']}")
        if npb.get("k") is not None:
            bits.append(f"{npb['k']}奪三振")
        return " / ".join(bits)
    bits = []
    if npb.get("games") is not None:
        bits.append(f"{npb['games']}試合")
    if npb.get("avg") is not None:
        bits.append(f"打率{npb['avg']}")
    if npb.get("hits") is not None:
        bits.append(f"{npb['hits']}安打")
    if npb.get("hr") is not None:
        bits.append(f"{npb['hr']}本塁打")
    if npb.get("rbi") is not None:
        bits.append(f"{npb['rbi']}打点")
    return " / ".join(bits)


def _headline_stat(entry: dict) -> str:
    npb = entry.get("npb") or {}
    if entry.get("type") == "pitcher":
        if npb.get("w") is not None:
            return f"通算{npb['w']}勝"
        if npb.get("k") is not None:
            return f"通算{npb['k']}奪三振"
    else:
        if npb.get("hr") is not None:
            return f"通算{npb['hr']}本塁打"
        if npb.get("hits") is not None:
            return f"通算{npb['hits']}安打"
    return "巨人OB"


def _career_table_md(entry: dict) -> str:
    npb = entry.get("npb") or {}
    rows = ["| 項目 | 通算 |", "|---|---|"]
    if entry.get("type") == "pitcher":
        order = [("登板", "games"), ("勝利", "w"), ("敗戦", "l"), ("防御率", "era"), ("奪三振", "k")]
    else:
        order = [("試合", "games"), ("打率", "avg"), ("安打", "hits"), ("本塁打", "hr"), ("打点", "rbi")]
    for label, key in order:
        if npb.get(key) is not None:
            rows.append(f"| {label} | {npb[key]} |")
    return "\n".join(rows)


def build_birthday_article(name: str, entry: dict, today: dt.date) -> Optional[dict[str, str]]:
    bmd = _birth_md(entry.get("birth", ""))
    if not bmd:
        return None
    age = today.year - int(str(entry["birth"]).split("-")[0])
    slug = entry.get("slug", "")
    years = entry.get("years", "")
    honors = entry.get("honors") or []
    title = f"【巨人データ】本日{today.month}月{today.day}日は{name}の誕生日 — {_headline_stat(entry)}の巨人OB"
    link = f"{SITE_DATA_BASE}/{slug}/" if slug else SITE_DATA_BASE
    honor_md = ""
    if honors:
        honor_md = "\n\n## 主な実績\n\n" + "\n".join(f"- {h}" for h in honors)
    body_md = f"""# {title}

## ひとこと

本日{today.month}月{today.day}日は、読売ジャイアンツOB **{name}**({years})の誕生日。満{age}歳。
現役時代は {_career_line(entry)} を残した巨人の{'投の' if entry.get('type') == 'pitcher' else '打の'}記録保持者だ。

## 通算成績

{_career_table_md(entry)}{honor_md}

## このデータについて

| 項目 | 内容 |
|---|---|
| 選手 | {name}(元巨人) |
| 生年月日 | {entry.get('birth', '')} |
| 在籍 | {years} |
| データ元 | NPB 公式 / Wikipedia |

[{name} の通算成績・年度別データを見る →]({link})
"""
    return {
        "title": title,
        "body_md": body_md,
        "body_html": _rap.markdown_to_html(body_md),
        "slug": slug,
        "player": name,
    }


def generate_today_articles(
    ob_stats: dict[str, dict],
    today: Optional[dt.date] = None,
    *,
    max_articles: int = 3,
) -> list[dict[str, str]]:
    """今日(JST)が誕生日の看板OBを記事化。看板度順に max_articles 本。"""
    if today is None:
        today = today_jst()
    md = (today.month, today.day)
    cands = []
    for name, entry in ob_stats.items():
        if not isinstance(entry, dict):
            continue
        if _birth_md(entry.get("birth", "")) != md:
            continue
        if not _is_notable(entry):
            continue
        cands.append((name, entry))
    cands.sort(key=lambda ne: _career_magnitude(ne[1]), reverse=True)
    out = []
    for name, entry in cands[:max_articles]:
        art = build_birthday_article(name, entry, today)
        if art:
            out.append(art)
    return out


def enabled() -> bool:
    """env DATA_INSIGHT_OB_ANNIVERSARY=1 で有効(新タイプのため default OFF)。"""
    return (_os.environ.get("DATA_INSIGHT_OB_ANNIVERSARY", "0") or "0").strip() in ("1", "true", "True")


def publish_today_birthday_articles(
    wp: Any,
    *,
    ob_stats: Optional[dict[str, dict]] = None,
    today: Optional[dt.date] = None,
    max_articles: int = 3,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """今日の OB 誕生日記事を WP へ。日次 idempotency は title 再利用に委ねる。

    status 未指定は env DATA_INSIGHT_OB_ANNIVERSARY_STATUS(default 'draft')。
    新タイプのため安全側(draft)が既定、X 自動投稿は §11 user 判断。
    """
    if ob_stats is None:
        ob_stats = load_ob_stats()
    if status is None:
        status = (_os.environ.get("DATA_INSIGHT_OB_ANNIVERSARY_STATUS", "draft") or "draft").strip()
    arts = generate_today_articles(ob_stats, today, max_articles=max_articles)
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
                caller="ob_anniversary",
            )
            results.append({"player": a["player"], "post_id": pid, "status": status})
        except Exception as exc:  # noqa: BLE001
            results.append({"player": a["player"], "error": f"{type(exc).__name__}:{exc}"})
    return results
