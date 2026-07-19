"""「同い年対決」YouTube Shorts — 同年齢レジェンド対比フォーマット (2026-07-19 user GO)。

X 角度① (2026-06-12 合意、LIVE) の動画化。採点・gate は
x_post_data_angles.legend_age_compare_facts と完全共用 (数式は 1 箇所)。
「現役若手が、レジェンドの同年齢シーズン時点の通算本塁打をもう上回っている」
という驚きだけを扱う (レジェンドを貶す絵ではなく、若手の成長ストーリー)。
数字は NPB 公式由来 (legend_age_seasons / npb_career cache + insight.db 今季) で
assert_number_guard により捏造防止。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from src.yt_shorts_script import (
    BASE_HASHTAGS,
    BRAND_CLOSING_LINE,
    DATA_URL,
    SITE_URL,
    X_HANDLE,
    ScriptCaption,
    ShortsScript,
    _int_to_kanji,
    assert_number_guard,
    extract_number_tokens,
)

AGECOMPARE_SOURCE_URL = "https://yoshilover.com/data/notable?v=yt"


@dataclass(frozen=True)
class AgeCompareTopic:
    player: str
    age: int
    cum_hr: int
    beaten_name: str
    beaten_cum: int
    above_name: str = ""
    above_cum: int = 0
    as_of: str = ""
    image_url: str = ""
    credit: str = ""
    source_url: str = AGECOMPARE_SOURCE_URL
    raw_item: dict[str, Any] = field(default_factory=dict)

    @property
    def topic_key(self) -> str:
        base = "|".join(
            ["yt_shorts_agecompare", self.player, str(self.age), str(self.cum_hr)]
        )
        return re.sub(r"\s+", "", base)


def topics_from_facts(
    facts: list[Mapping[str, Any]],
    *,
    as_of: str = "",
    source_url: str = AGECOMPARE_SOURCE_URL,
) -> list[AgeCompareTopic]:
    """legend_age_compare_facts の rows を topic 化する (順序は facts のまま)。"""
    topics: list[AgeCompareTopic] = []
    for row in facts or []:
        player = str(row.get("player") or "").strip()
        beaten = str(row.get("beaten_name") or "").strip()
        try:
            age = int(row.get("age") or 0)
            cum = int(row.get("cum_hr") or 0)
            beaten_cum = int(row.get("beaten_cum") or 0)
        except (TypeError, ValueError):
            continue
        if not player or not beaten or age <= 0 or cum <= 0 or beaten_cum <= 0:
            continue
        topics.append(
            AgeCompareTopic(
                player=player,
                age=age,
                cum_hr=cum,
                beaten_name=beaten,
                beaten_cum=beaten_cum,
                above_name=str(row.get("above_name") or "").strip(),
                above_cum=int(row.get("above_cum") or 0),
                as_of=as_of,
                source_url=source_url,
            )
        )
    return topics


def _allowed_numbers(topic: AgeCompareTopic) -> tuple[str, ...]:
    parts = [str(topic.age), str(topic.cum_hr), str(topic.beaten_cum)]
    if topic.above_name and topic.above_cum > 0:
        parts.append(str(topic.above_cum))
    return tuple(dict.fromkeys(extract_number_tokens(" ".join(parts))))


def _kanji(number: int) -> str:
    return _int_to_kanji(number)


def build_agecompare_script(topic: AgeCompareTopic) -> ShortsScript:
    allowed = _allowed_numbers(topic)

    above_line = (
        f"次の壁は、{topic.above_name}の{_kanji(topic.age)}歳時点、{_kanji(topic.above_cum)}本。"
        if topic.above_name and topic.above_cum > 0
        else "ここからどこまで積み上げるか、楽しみしかない。"
    )
    narration_parts = [
        f"{_kanji(topic.age)}歳の{topic.player}、実はもう、あのレジェンドを超えています。",
        f"{topic.player}、{_kanji(topic.age)}歳シーズン時点の通算ホームランは、{_kanji(topic.cum_hr)}本。",
        f"{topic.beaten_name}の{_kanji(topic.age)}歳時点は、{_kanji(topic.beaten_cum)}本。",
        "同じ年齢で比べると、もう上回っている。",
        above_line,
        BRAND_CLOSING_LINE,
    ]
    narration = "\n".join(part for part in narration_parts if part.strip())
    assert_number_guard(narration, allowed)

    title = f"{topic.player}{topic.age}歳、{topic.beaten_name}の同年齢を超えた｜通算{topic.cum_hr}本"
    desc_factual = (
        f"{topic.player} {topic.age}歳シーズン時点 通算{topic.cum_hr}本塁打 / "
        f"{topic.beaten_name}の{topic.age}歳時点 {topic.beaten_cum}本"
        + (
            f" / 次は{topic.above_name} {topic.above_cum}本"
            if topic.above_name and topic.above_cum > 0
            else ""
        )
    )
    assert_number_guard(title + "\n" + desc_factual, allowed)
    desc_branding = (
        "\n\n"
        "年齢=その年に迎える満年齢 (年度-生年)、両者同一ルールで比較。\n"
        "出典: NPB公式 個人年度別成績。\n\n"
        "巨人特化メディア「ヨシラバー」が、巨人の成長ストーリーを数字で発信。\n\n"
        f"▼巨人の全選手データ(毎日更新)\n{DATA_URL}\n\n"
        f"▼巨人ニュース・速報\n{SITE_URL}\n\n"
        f"▼X(旧Twitter)でも毎日発信\n{X_HANDLE}\n\n"
        "音声: VOICEVOX 青山龍星\n\n"
        + " ".join((*BASE_HASHTAGS, "#同い年対決"))
    )
    description = desc_factual + desc_branding

    captions = (
        ScriptCaption(0.0, 2.8, f"{topic.player} 同い年対決"),
        ScriptCaption(2.8, 9.2, f"{topic.age}歳時点 通算{topic.cum_hr}本"),
        ScriptCaption(9.2, 15.6, f"{topic.beaten_name} {topic.age}歳時点 {topic.beaten_cum}本"),
        ScriptCaption(15.6, 22.2, "同じ年齢なら もう上回っている"),
        ScriptCaption(22.2, 27.0, "巨人データはヨシラバーで毎日更新中"),
    )
    assert_number_guard("\n".join(c.text for c in captions), allowed)

    tags = " ".join(BASE_HASHTAGS[:4])
    x_post = "\n".join(
        [
            f"【{topic.player}】{topic.age}歳時点 通算{topic.cum_hr}本塁打",
            "",
            f"{topic.beaten_name}の{topic.age}歳時点は{topic.beaten_cum}本 — もう上回っている",
            *(
                [f"次は{topic.above_name}の{topic.above_cum}本"]
                if topic.above_name and topic.above_cum > 0
                else []
            ),
            "",
            "同い年対決、動画でどうぞ👇",
            "[Shorts URL]",
            "",
            f"巨人の選手データ → {DATA_URL}",
            tags,
        ]
    )
    assert_number_guard(x_post.replace("[Shorts URL]", ""), allowed)

    return ShortsScript(
        title=title,
        description=description,
        narration=narration,
        captions=captions,
        allowed_numbers=allowed,
        x_post=x_post,
    )


__all__ = [
    "AGECOMPARE_SOURCE_URL",
    "AgeCompareTopic",
    "build_agecompare_script",
    "topics_from_facts",
]
