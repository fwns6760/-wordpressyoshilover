"""「巨人目線のセ・リーグ」YouTube Shorts のトピック選定と台本生成。

当初計画テーマ③「巨人目線のプロ野球ネタ」相当。セ・リーグ順位表(自社が
NPB 公式から取得した standings)から巨人の順位・成績・ゲーム差を、巨人目線の
敬意ある考察で1本にまとめる。他球団を煽らず、巨人ファン目線を崩さない。
数字はすべて standings 由来 = assert_number_guard で捏造防止。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from src.yt_shorts_script import (
    BASE_HASHTAGS,
    BRAND_CLOSING_LINE,
    DATA_URL,
    DECIMAL_RE,
    SITE_URL,
    X_HANDLE,
    ScriptCaption,
    ShortsScript,
    _decimal_point_reading,
    assert_number_guard,
    extract_number_tokens,
)

STANDINGS_SOURCE_URL = "https://yoshilover.com/data/notable?v=yt"
STANDINGS_OPENING = "巨人目線で見る、今のセ・リーグ。"

# 順位帯ごとの締めコメント(数字なし・巨人目線の敬意ある所感)。
STANDINGS_OPINION_LEAD = (
    "この位置を守りきれるか、ここからが巨人の本領。",
    "首位の景色、巨人ファンとしては嬉しい限り。",
)
STANDINGS_OPINION_CHASE = (
    "ここからの巨人の巻き返しに期待。",
    "差はまだ詰められる。巨人の底力を信じたい。",
    "勝負はこれから。巨人の戦いを見守ろう。",
)


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class StandingsTopic:
    rank: int
    wins: str
    losses: str
    draws: str
    pct: str
    gb: str
    team: str = "巨人"
    as_of: str = ""
    player: str = "巨人"   # history / run_id 用ラベル
    source_url: str = STANDINGS_SOURCE_URL
    raw_item: dict[str, Any] = field(default_factory=dict)

    @property
    def topic_key(self) -> str:
        base = "|".join(["yt_shorts_standings", self.as_of, str(self.rank)])
        return re.sub(r"\s+", "", base)

    @property
    def is_leading(self) -> bool:
        # gb が "-" / 空 / 0 のとき首位扱い。
        gb = (self.gb or "").strip()
        return self.rank == 1 or gb in {"", "-", "0", "0.0", ".0"}


def standings_topic_from_rows(
    rows: Any,
    *,
    as_of: str = "",
    source_url: str = STANDINGS_SOURCE_URL,
) -> StandingsTopic | None:
    """セ・リーグ順位表の行リストから巨人(is_giants)の topic を作る。"""
    giants_row: Mapping[str, Any] | None = None
    for row in rows or []:
        if isinstance(row, Mapping) and row.get("is_giants"):
            giants_row = row
            break
    if giants_row is None:
        return None
    rank = _to_int(giants_row.get("rank"))
    wins = str(giants_row.get("w") or "").strip()
    losses = str(giants_row.get("l") or "").strip()
    draws = str(giants_row.get("t") or "0").strip()
    if rank is None or not wins or not losses:
        return None
    return StandingsTopic(
        rank=rank,
        wins=wins,
        losses=losses,
        draws=draws,
        pct=str(giants_row.get("pct") or "").strip(),
        gb=str(giants_row.get("gb") or "").strip(),
        as_of=str(as_of or "").strip(),
        source_url=source_url,
        raw_item=dict(giants_row),
    )


def _opinion(topic: StandingsTopic) -> str:
    pool = STANDINGS_OPINION_LEAD if topic.is_leading else STANDINGS_OPINION_CHASE
    seed = sum(ord(ch) for ch in (topic.wins + topic.losses))
    return pool[seed % len(pool)]


def _gb_speech(gb: str) -> str:
    return DECIMAL_RE.sub(_decimal_point_reading, gb)


def _allowed_numbers(topic: StandingsTopic) -> tuple[str, ...]:
    parts = [str(topic.rank), topic.wins, topic.losses, topic.draws]
    if not topic.is_leading:
        parts.append(topic.gb)
    return tuple(dict.fromkeys(extract_number_tokens(" ".join(parts))))


def build_standings_script(topic: StandingsTopic) -> ShortsScript:
    allowed = _allowed_numbers(topic)

    record_line = f"今シーズンの成績は、{topic.wins}勝{topic.losses}敗{topic.draws}分け。"
    if topic.is_leading:
        gap_line = "巨人が、セ・リーグの首位に立っています。"
        gap_caption = "巨人 首位"
    else:
        gap_line = f"首位とのゲーム差は、{_gb_speech(topic.gb)}。"
        gap_caption = f"首位とゲーム差 {topic.gb}"

    narration_parts = [
        STANDINGS_OPENING,
        f"巨人は今、セ・リーグ{topic.rank}位。",
        record_line,
        gap_line,
        _opinion(topic),
        BRAND_CLOSING_LINE,
    ]
    narration = "\n".join(part for part in narration_parts if part.strip())
    assert_number_guard(narration, allowed)

    title = f"巨人は今セ・リーグ{topic.rank}位｜巨人目線のペナントレース"
    desc_factual = (
        f"巨人 {topic.rank}位 / {topic.wins}勝{topic.losses}敗{topic.draws}分"
        + ("" if topic.is_leading else f" / 首位とゲーム差{topic.gb}")
    )
    assert_number_guard(title + "\n" + desc_factual, allowed)
    desc_branding = (
        "\n\n"
        "巨人特化メディア「ヨシラバー」が、巨人目線でセ・リーグの今をお届け。\n"
        "他球団を煽らず、巨人ファン目線で毎日発信しています。\n\n"
        f"▼巨人の全選手データ・順位(毎日更新)\n{DATA_URL}\n\n"
        f"▼巨人ニュース・速報\n{SITE_URL}\n\n"
        f"▼X(旧Twitter)でも毎日発信\n{X_HANDLE}\n\n"
        "音声: VOICEVOX 青山龍星\n\n"
        + " ".join((*BASE_HASHTAGS, "#セリーグ", "#順位表"))
    )
    description = desc_factual + desc_branding

    captions = (
        ScriptCaption(0.0, 2.2, "巨人目線のセ・リーグ"),
        ScriptCaption(2.2, 8.4, f"巨人 セ・リーグ{topic.rank}位"),
        ScriptCaption(8.4, 14.8, f"{topic.wins}勝{topic.losses}敗{topic.draws}分"),
        ScriptCaption(14.8, 21.0, gap_caption),
        ScriptCaption(21.0, 27.0, "巨人データはヨシラバーで毎日更新中"),
    )
    assert_number_guard("\n".join(c.text for c in captions), allowed)

    tags = " ".join(BASE_HASHTAGS[:4])
    x_post = "\n".join(
        [
            f"【巨人 セ・リーグ{topic.rank}位】",
            "",
            f"{topic.wins}勝{topic.losses}敗{topic.draws}分"
            + ("（首位）" if topic.is_leading else f" / 首位とゲーム差{topic.gb}"),
            "",
            _opinion(topic),
            "巨人目線でまとめました👇",
            "[Shorts URL]",
            "",
            f"巨人の順位・データ → {DATA_URL}",
            tags,
        ]
    )

    return ShortsScript(
        title=title,
        description=description,
        narration=narration,
        captions=captions,
        allowed_numbers=allowed,
        x_post=x_post,
    )


__all__ = [
    "STANDINGS_OPENING",
    "STANDINGS_SOURCE_URL",
    "StandingsTopic",
    "build_standings_script",
    "standings_topic_from_rows",
]
