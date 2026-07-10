"""morning_digest_post.py — 毎朝の巨人データ定点ポスト (2026-07-10 user)。

user が示した金融アカの型 (売買代金上位の定点ポスト → 解説 → 自分の立場で
締め) の野球翻訳。「トレンドの順位とその他。カードも使ってる」:

- 関心ランキング = スポーツ媒体 X での巨人選手言及数 TOP5 (野球版・売買代金上位)
- 検索急上昇の野球ワード (Google Trends)
- 解説 + ヨシラバーの立場 (データ辛口×巨人愛) で締め — LLM、数字ガードつき
- カード: draft_text に 437 のランキング行 format (`1位 名前（巨人）… 🟧巨人🟧`)
  を入れることで既存の候補カード PNG 生成に自動で乗せる

数字は RSSHub 言及数と Google Trends の literal のみ (捏造ゼロ)。
1 日 1 本 (signature = 日付)。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

LOG = logging.getLogger("morning_digest_post")

_WEEKDAYS_JA = ("月", "火", "水", "木", "金", "土", "日")
_TOP_N = 5


def build_morning_digest_candidate(
    *,
    now: datetime,
    gemini_api_key: str = "",
    dedup_set: Optional[set[str]] = None,
    buzz_counts: Optional[dict[str, int]] = None,
    trend_keywords: Optional[list[str]] = None,
) -> Any:
    """毎朝 1 本の定点ポスト候補。素材不足 (話題選手 3 人未満) / dedup 済みは None。

    ``buzz_counts`` / ``trend_keywords`` は test 注入用。None なら実 fetch。
    2026-07-10 user「毎時で出したい」: signature を 日+時 にして毎時 1 本。
    """
    signature = "morndigest|" + hashlib.sha1(
        now.strftime("%Y%m%d-%H").encode("utf-8")
    ).hexdigest()[:16]
    if dedup_set is not None and signature in dedup_set:
        return None

    if buzz_counts is None:
        buzz_counts = _fetch_buzz_counts()
    ranked = sorted(
        (buzz_counts or {}).items(), key=lambda kv: kv[1], reverse=True
    )[:_TOP_N]
    if len(ranked) < 3:
        LOG.info("morning_digest skip: buzz names=%d (<3)", len(ranked))
        return None

    if trend_keywords is None:
        trend_keywords = _fetch_baseball_trends()

    date_label = f"{now.month}/{now.day}({_WEEKDAYS_JA[now.weekday()]})"
    greeting = (
        "おはようございます。" if 5 <= now.hour <= 10
        else "こんばんは。" if now.hour >= 18
        else ""
    )
    header = f"{greeting}{date_label} {now.hour}時の巨人データ定点観測🐰"
    section = "【いま話題の巨人選手 TOP5】(スポーツ媒体Xでの言及数)"
    plain_lines = [f"{i}位 {name}" for i, (name, _c) in enumerate(ranked, 1)]
    card_lines = [
        f"{i}位 {name}（巨人）言及{cnt}件 🟧巨人🟧"
        for i, (name, cnt) in enumerate(ranked, 1)
    ]
    trend_line = (
        "【検索で急上昇中の野球ワード】" + " / ".join(trend_keywords[:5])
        if trend_keywords else ""
    )

    fact = (
        f"{date_label}のスポーツ媒体Xでの巨人選手言及数ランキング: "
        + "、".join(f"{i}位 {n} ({c}件)" for i, (n, c) in enumerate(ranked, 1))
        + (("。検索急上昇の野球ワード: " + "、".join(trend_keywords[:5]))
           if trend_keywords else "")
    )
    comment = _build_digest_comment(fact, gemini_api_key)
    if not comment:
        # LLM 不達でも定点データ自体に価値があるので deterministic 締めで成立させる
        top_name = ranked[0][0]
        comment = (
            f"言及が集まる場所は、ファンの目線が集まる場所。今日は{top_name}から"
            "目が離せない一日になりそう。"
        )

    body_parts = [header, "", section, *plain_lines]
    if trend_line:
        body_parts += ["", trend_line]
    body_parts += ["", comment]
    post_text = "\n".join(body_parts)

    from src.x_post_mail_lane import Candidate

    draft = "\n".join([
        f"毎朝の定点ポスト ({date_label})。言及数 = RSSHub 経由のスポーツ媒体X実測。",
        *card_lines,
        f"検索急上昇: {' / '.join(trend_keywords[:5])}" if trend_keywords else "",
        "(カードは上のランキング行から自動生成)",
    ])
    LOG.info(
        "morning_digest built names=%d trends=%d", len(ranked), len(trend_keywords or [])
    )
    return Candidate(
        title=f"📊{now.hour}時の定点観測｜話題選手TOP5｜{ranked[0][0]}",
        metric="MORNING_DIGEST",
        period_label="毎朝定点",
        draft_text=draft,
        char_count=len(post_text),
        signature=signature,
        post_text=post_text,
        focus_player=ranked[0][0],
        source_material_type="morning_digest",
    )


def _fetch_buzz_counts() -> dict[str, int]:
    """スポーツ媒体 X の巨人選手言及数 (RSSHub、失敗は {})。"""
    try:
        from src import video_radar as vr
        from src.x_post_mail_lane import (
            _load_giants_member_aliases,
            _load_giants_player_aliases,
            detect_giants_player_name,
        )

        alias_map = {
            **_load_giants_player_aliases(),
            **_load_giants_member_aliases(),
        }
        return vr.fetch_buzzing_players(
            detect_player_fn=lambda t: detect_giants_player_name(
                t, alias_map=alias_map
            ),
            min_mentions=1,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.info("morning_digest buzz skip: %r", exc)
        return {}


def _fetch_baseball_trends() -> list[str]:
    try:
        from src import search_trend_note as stn

        trends = stn.fetch_jp_trends()
        roster = stn._giants_name_tokens()
        out = []
        for t in trends:
            kw = t.get("keyword") or ""
            if any(mk in kw for mk in stn._BASEBALL_MARKERS) or any(
                tok in kw for tok in roster
            ):
                out.append(kw)
        return out
    except Exception as exc:  # noqa: BLE001
        LOG.info("morning_digest trends skip: %r", exc)
        return []


def _build_digest_comment(fact: str, gemini_api_key: str) -> str:
    """解説+締めの 2〜3 文 (LLM)。失敗は ""。"""
    if not gemini_api_key:
        return ""
    try:
        from src.x_post_branding_gen import build_quote_rt_comment

        return (
            build_quote_rt_comment(
                fact, "", "",
                gemini_api_key=gemini_api_key,
                subject="今朝の巨人関心データ定点観測",
                db_fact="", require_db_fact=False,
                budget_site="morning_digest",
                extra_voice_note=(
                    "毎朝の定点データポストの締め。上のランキングの読み解き"
                    " (どこに関心が集まっているか、なぜか) を1〜2文 + ヨシラバー"
                    "の立場 (データは辛口・巨人愛は本物) の一言で締める。"
                    "2〜3文、80〜140字。ランキングの数字・選手名は fact に"
                    "あるものだけ使い、新しい数字・選手名は作らない。"
                ),
            ) or ""
        ).strip()
    except Exception as exc:  # noqa: BLE001
        LOG.info("morning_digest comment skip: %r", exc)
        return ""
