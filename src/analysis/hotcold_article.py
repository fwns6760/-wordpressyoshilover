"""⑤ ホット&コールド(直近トレンド)— 直近N試合の打率がシーズン平均から急騰した
打者を「絶好調」記事化。設計: spec/data-articles-no1-design.md §2⑤。

- 検知は既存 `insight_multi_game_detector.detect_batter_recent_window_anomaly` を
  **再利用**(直近5試合 vs 過去全試合の打率 z-score、再発明しない)。
- ファンサイトの voice(巨人愛)に合わせ **HOT(絶好調)のみ記事化**。COLD(絶不調)は
  検知されるが記事化しない(否定的記事は出さない)。
- タイトル case A: ``【巨人データ】{player} 直近{N}試合 打率{value}、絶好調``。
- dedup: title に打率を含めるため title 再利用で「打率変化時のみ再掲」。既定 draft。
- env DATA_INSIGHT_HOTCOLD=1 gate(新タイプのため default OFF)、X 解放は §11。
"""
from __future__ import annotations

import os as _os
import re as _re
from typing import Any, Optional

from src.analysis import ranking_article_publisher as _rap
from src.analysis.insight_contrast_title import fmt_stat
from src.analysis import insight_multi_game_detector as _mg

SITE_DATA_BASE = "https://yoshilover.com/data"
RECENT_N = 5


def enabled() -> bool:
    return (_os.environ.get("DATA_INSIGHT_HOTCOLD", "0") or "0").strip() in (
        "1",
        "true",
        "True",
    )


def _parse_ba(s: str, key: str) -> Optional[float]:
    """'recent_ba=0.385 n=5' から float を取り出す。"""
    m = _re.search(rf"{key}=([0-9.]+)", str(s or ""))
    try:
        return float(m.group(1)) if m else None
    except (TypeError, ValueError):
        return None


def find_hot_batters(conn, *, z_threshold: float = 1.5) -> list[dict[str, Any]]:
    """Giants 打者の中で直近5試合が絶好調(z>0)の候補を z 降順で。"""
    batters, _ = _mg.all_giants_players_in_db(conn)
    out: list[dict[str, Any]] = []
    for name in batters:
        cand = _mg.detect_batter_recent_window_anomaly(
            conn, player_canonical=name, recent_n=RECENT_N, z_threshold=z_threshold
        )
        if not cand:
            continue
        if cand.get("signal_type") != "batter_recent_hot":
            continue  # COLD は記事化しない
        recent_ba = _parse_ba(cand.get("current_value"), "recent_ba")
        baseline_ba = _parse_ba(cand.get("baseline_value"), "baseline_ba")
        if recent_ba is None:
            continue
        out.append(
            {
                "player": name,
                "recent_ba": recent_ba,
                "baseline_ba": baseline_ba,
                "z": cand.get("magnitude"),
            }
        )
    out.sort(key=lambda c: -(c.get("z") or 0))
    return out


def build_article(cand: dict[str, Any]) -> Optional[dict[str, str]]:
    from src.data_site_slug import player_slug

    player = cand["player"]
    recent = fmt_stat(cand["recent_ba"], "打率")
    slug = player_slug(player)
    link = f"{SITE_DATA_BASE}/{slug}/"
    title = f"【巨人データ】{player} 直近{RECENT_N}試合 打率{recent}、絶好調"
    base = cand.get("baseline_ba")
    base_str = fmt_stat(base, "打率") if base is not None else "—"
    lift = (
        f"シーズン平均 {base_str} から大きく上振れ、最近の{RECENT_N}試合で打線を引っ張っている。"
        if base is not None
        else "直近で打撃の調子を一気に上げている。"
    )
    body_md = f"""# {title}

## ひとこと

巨人 **{player}** が直近{RECENT_N}試合で打率 **{recent}** と固め打ち。{lift}

## 直近 vs シーズン

| 区分 | 打率 |
|---|---|
| 直近{RECENT_N}試合 | **{recent}** |
| シーズン平均 | {base_str} |

## このデータについて

| 項目 | 内容 |
|---|---|
| 選手 | {player}(巨人) |
| 直近{RECENT_N}試合 打率 | {recent} |
| データ元 | NPB 公式 box score |

[{player} の詳細データ・直近成績を見る →]({link})
"""
    return {
        "title": title,
        "body_md": body_md,
        "body_html": _rap.markdown_to_html(body_md),
        "slug": slug,
        "player": player,
    }


def publish_hot_batter_articles(
    conn,
    wp: Any,
    *,
    max_articles: int = 3,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """絶好調打者を記事化(既定 draft)。dedup は title(打率込み)再利用に委ねる。"""
    if status is None:
        status = (_os.environ.get("DATA_INSIGHT_HOTCOLD_STATUS", "draft") or "draft").strip()
    cands = find_hot_batters(conn)
    cat = None
    try:
        cat = wp.resolve_category_id("コラム")
    except Exception:
        cat = None
    results: list[dict[str, Any]] = []
    for cand in cands[:max_articles]:
        art = build_article(cand)
        if not art:
            continue
        try:
            pid = wp.create_post(
                title=art["title"],
                content=art["body_html"],
                categories=[cat] if cat else None,
                status=status,
                allow_title_only_reuse=True,
                caller="hotcold_article",
            )
            results.append({"player": art["player"], "post_id": pid, "status": status})
        except Exception as exc:  # noqa: BLE001
            results.append({"player": art["player"], "error": f"{type(exc).__name__}:{exc}"})
    return results
