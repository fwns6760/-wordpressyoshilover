"""「巨人データ・ランキング」YouTube Shorts のトピック選定と台本生成。

data フォーマット(選手1人の注目データ)とは別角度の補助フォーマット。
チーム内リーダーボード(本塁打/打点/安打/盗塁/打率/奪三振/勝利/防御率)の
TOP3 を rights-clean なデータカードで見せる。数字はすべて leaders 由来
(自社 insight.db 集計)= assert_number_guard で捏造防止。
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
    _apply_name_readings,
    _baseball_average_reading,
    _decimal_point_reading,
    _hashtag_player,
    assert_number_guard,
    extract_number_tokens,
)

RANKING_SOURCE_URL = "https://yoshilover.com/data/notable?v=yt"
RANKING_OPENING = "巨人データ・ランキング！"

# leaders dict のキー順(優先度 = 引きの強さ)。打撃カウント系を上に。
STAT_ORDER: tuple[str, ...] = (
    "本塁打",
    "打点",
    "打率",
    "安打",
    "盗塁",
    "勝利",
    "奪三振",
    "防御率",
)
# value が 割分厘 読み(打率・出塁率 等)/ 小数点 読み(防御率)の指標。
RATIO_STATS = {"打率", "出塁率", "長打率"}
DECIMAL_STATS = {"防御率"}

# 締めの一言プール(数字なし=量産AIに見えない巨人目線の所感)。stat で rotate。
RANKING_OPINION_POOL: tuple[str, ...] = (
    "今の巨人を支えているのは、この顔ぶれ。",
    "数字で見ると、チームの形が見えてきます。",
    "ランキングの裏に、巨人の積み上げあり。",
    "この並び、巨人ファンなら納得のはず。",
    "上位3人、これからの巨人を引っ張る存在。",
)


@dataclass(frozen=True)
class RankingEntry:
    rank: int
    player: str
    display: str


@dataclass(frozen=True)
class RankingTopic:
    stat: str
    entries: tuple[RankingEntry, ...]
    as_of: str = ""
    player: str = ""        # history / run_id 用ラベル(選手単独ではないので stat 名)
    opinion: str = ""
    priority: float = 0.0
    source_url: str = RANKING_SOURCE_URL
    raw_item: dict[str, Any] = field(default_factory=dict)

    @property
    def topic_key(self) -> str:
        base = "|".join(["yt_shorts_ranking", self.as_of, self.stat])
        return re.sub(r"\s+", "", base)


def _ranking_opinion(stat: str) -> str:
    seed = sum(ord(ch) for ch in (stat or "x"))
    return RANKING_OPINION_POOL[seed % len(RANKING_OPINION_POOL)]


def _entries_from_rows(rows: Any) -> list[RankingEntry]:
    out: list[RankingEntry] = []
    for idx, row in enumerate(rows or []):
        if not isinstance(row, Mapping):
            continue
        player = str(row.get("player") or "").strip()
        display = str(row.get("display") or "").strip()
        if not player or not display:
            continue
        out.append(RankingEntry(rank=idx + 1, player=player, display=display))
    return out


def ranking_topic_from_stat(
    stat: str,
    rows: Any,
    *,
    as_of: str = "",
    source_url: str = RANKING_SOURCE_URL,
) -> RankingTopic | None:
    stat = str(stat or "").strip()
    if not stat:
        return None
    entries = _entries_from_rows(rows)
    if len(entries) < 2:  # TOP2 未満は1本のランキングとして成立しない
        return None
    # priority は STAT_ORDER の並び(引きの強い指標を上に)。未知 stat は末尾。
    try:
        order_score = float(len(STAT_ORDER) - STAT_ORDER.index(stat))
    except ValueError:
        order_score = 0.0
    return RankingTopic(
        stat=stat,
        entries=tuple(entries[:3]),
        as_of=str(as_of or "").strip(),
        player=f"{stat}ランキング",
        opinion=_ranking_opinion(stat),
        priority=order_score,
        source_url=source_url,
        raw_item={"stat": stat, "entries": [
            {"rank": e.rank, "player": e.player, "display": e.display} for e in entries[:3]
        ]},
    )


def list_ranking_topics(
    leaders: Mapping[str, Any] | None,
    *,
    as_of: str = "",
    source_url: str = RANKING_SOURCE_URL,
) -> list[RankingTopic]:
    """leaders dict ({stat: [{player,display,slug}]}) から stat ごとの topic を返す。

    引きの強い指標順(STAT_ORDER)で並べる。呼び出し側が日替わり rotate を掛ける。
    """
    topics: list[RankingTopic] = []
    for stat, rows in (leaders or {}).items():
        topic = ranking_topic_from_stat(stat, rows, as_of=as_of, source_url=source_url)
        if topic is not None:
            topics.append(topic)
    return sorted(topics, key=lambda t: (-t.priority, t.stat))


def _display_speech(stat: str, display: str) -> str:
    """記録値を TTS が自然に読める文へ。打率は割分厘、防御率は小数点読み。"""
    if stat in RATIO_STATS:
        return DECIMAL_RE.sub(_baseball_average_reading, display)
    if stat in DECIMAL_STATS:
        return DECIMAL_RE.sub(_decimal_point_reading, display)
    return display


def _allowed_numbers(topic: RankingTopic) -> tuple[str, ...]:
    source = " ".join(
        [str(e.rank) for e in topic.entries]
        + [e.display for e in topic.entries]
    )
    return tuple(dict.fromkeys(extract_number_tokens(source)))


def build_ranking_script(topic: RankingTopic) -> ShortsScript:
    allowed = _allowed_numbers(topic)
    stat = topic.stat

    entry_lines = [
        f"{e.rank}位、{e.player}。{stat}、{_display_speech(stat, e.display)}。"
        for e in topic.entries
    ]
    narration_parts = [
        RANKING_OPENING,
        f"今日のテーマは、巨人の{stat}ランキング。",
        *entry_lines,
        topic.opinion,
        BRAND_CLOSING_LINE,
    ]
    narration = "\n".join(part for part in narration_parts if part.strip())
    assert_number_guard(narration, allowed)
    narration = _apply_name_readings(narration)

    title = f"巨人{stat}ランキング｜ヨシラバー"
    top = topic.entries[0]
    desc_factual = f"巨人の{stat}ランキング・トップは{top.player}（{top.display}）。"
    assert_number_guard(title + "\n" + desc_factual, allowed)
    rank_block = "\n".join(f"{e.rank}位 {e.player} {e.display}" for e in topic.entries)
    assert_number_guard(rank_block, allowed)
    desc_branding = (
        "\n\n"
        f"{rank_block}\n\n"
        "巨人特化メディア「ヨシラバー」が、巨人の注目データを毎日Shortsでお届け。\n"
        "「巨人といえばヨシラバー」を目指して、ファン目線で発信しています。\n\n"
        f"▼巨人の全選手データ(毎日更新)\n{DATA_URL}\n\n"
        f"▼巨人ニュース・速報\n{SITE_URL}\n\n"
        f"▼X(旧Twitter)でも毎日発信\n{X_HANDLE}\n\n"
        "音声: VOICEVOX 青山龍星\n\n"
        + " ".join((*BASE_HASHTAGS, f"#巨人{_hashtag_player(stat)}"))
    )
    description = desc_factual + desc_branding

    e = topic.entries
    captions = (
        ScriptCaption(0.0, 2.2, RANKING_OPENING),
        ScriptCaption(2.2, 8.4, f"巨人 {stat} ランキング"),
        ScriptCaption(8.4, 14.8, f"1位 {e[0].player} {e[0].display}"),
        ScriptCaption(14.8, 21.0, f"2位 {e[1].player} {e[1].display}"),
        ScriptCaption(21.0, 27.0, "巨人データはヨシラバーで毎日更新中"),
    )
    assert_number_guard("\n".join(c.text for c in captions), allowed)

    tags = " ".join(BASE_HASHTAGS[:4])
    x_post = "\n".join(
        [
            f"【巨人{stat}ランキング】",
            "",
            *[f"{e_.rank}位 {e_.player} {e_.display}" for e_ in topic.entries],
            "",
            topic.opinion,
            "Shortsにまとめました👇",
            "[Shorts URL]",
            "",
            f"巨人の全選手データ → {DATA_URL}",
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
    "RANKING_OPENING",
    "RANKING_SOURCE_URL",
    "STAT_ORDER",
    "RankingEntry",
    "RankingTopic",
    "build_ranking_script",
    "list_ranking_topics",
    "ranking_topic_from_stat",
]
