"""「定位置争い」YouTube Shorts — 争点対決フォーマット (2026-07-19 user GO)。

X 実測で最強だった「争点+立場」型 (2026-07-16 浦田vs吉川尚輝) の動画化。
対戦カードは config/yt_shorts_duels.json (curation 正本、実在選手のみ) から、
成績は insight.db の season 集計 (data_site_query) から毎回取得する。
数字は全て実データ由来で assert_number_guard により捏造防止。
立場 (どちらがリードか) は 3 指標 (打率/本塁打/打点) の多数決だけで決める。
他方を貶す断定・戦犯探しはしない (巨人ファン目線の敬意ある比較)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from src.yt_shorts_script import (
    BASE_HASHTAGS,
    BRAND_CLOSING_LINE,
    DATA_URL,
    DECIMAL_RE,
    SITE_URL,
    X_HANDLE,
    ScriptCaption,
    ShortsScript,
    _baseball_average_reading,
    assert_number_guard,
    extract_number_tokens,
)

DUEL_SOURCE_URL = "https://yoshilover.com/data/notable?v=yt"
DUEL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "yt_shorts_duels.json"

# サンプル僅少の比較は「数字で語る」体を成さないので出さない。
DEFAULT_MIN_AB = 30

# 締めの一言プール(数字なし・両者への敬意を崩さない)。
DUEL_OPINION_LEAD = (
    "ただ、この争いはまだ終わらない。",
    "とはいえ、ひっくり返るのがポジション争い。",
    "追う側の巻き返しにも期待したい。",
)
DUEL_OPINION_EVEN = (
    "数字はほぼ互角。この争い、目が離せない。",
    "甲乙つけがたい。だから面白い。",
)


@dataclass(frozen=True)
class DuelSide:
    player: str
    games: int
    ab: int
    hits: int
    hr: int
    rbi: int
    image_url: str = ""
    credit: str = ""

    @property
    def avg_display(self) -> str:
        if self.ab <= 0:
            return "-"
        avg = self.hits / self.ab
        return f".{int(round(avg * 1000)):03d}"


@dataclass(frozen=True)
class DuelTopic:
    slot: str
    a: DuelSide
    b: DuelSide
    as_of: str = ""
    source_url: str = DUEL_SOURCE_URL
    raw_item: dict[str, Any] = field(default_factory=dict)

    @property
    def player(self) -> str:
        # history / run_id 用ラベル。cooldown は両選手名を含む文字列で効かせる。
        return f"{self.a.player}×{self.b.player}"

    @property
    def topic_key(self) -> str:
        base = "|".join(["yt_shorts_duel", self.slot, self.as_of])
        return re.sub(r"\s+", "", base)

    @property
    def leader(self) -> Optional[DuelSide]:
        """3 指標 (打率/本塁打/打点) の多数決。同数なら None (互角)。"""
        a_pts = 0
        b_pts = 0
        a_avg = (self.a.hits / self.a.ab) if self.a.ab > 0 else 0.0
        b_avg = (self.b.hits / self.b.ab) if self.b.ab > 0 else 0.0
        for av, bv in ((a_avg, b_avg), (self.a.hr, self.b.hr), (self.a.rbi, self.b.rbi)):
            if av > bv:
                a_pts += 1
            elif bv > av:
                b_pts += 1
        if a_pts > b_pts:
            return self.a
        if b_pts > a_pts:
            return self.b
        return None


def load_duel_config(path: Path | str | None = None) -> list[dict[str, Any]]:
    """config/yt_shorts_duels.json の duels list を返す (無ければ空)。"""
    target = Path(path) if path else DUEL_CONFIG_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    duels = data.get("duels") if isinstance(data, Mapping) else None
    return [d for d in (duels or []) if isinstance(d, Mapping)]


def _side_from_stats(player: str, stats: Any) -> Optional[DuelSide]:
    if stats is None:
        return None
    games = int(getattr(stats, "games", 0) or 0)
    ab = int(getattr(stats, "ab", 0) or 0)
    return DuelSide(
        player=player,
        games=games,
        ab=ab,
        hits=int(getattr(stats, "hits", 0) or 0),
        hr=int(getattr(stats, "hr", 0) or 0),
        rbi=int(getattr(stats, "rbi", 0) or 0),
    )


def list_duel_topics(
    duels: list[Mapping[str, Any]],
    stats_fn: Callable[[str], Any],
    *,
    as_of: str = "",
    min_ab: int = DEFAULT_MIN_AB,
    source_url: str = DUEL_SOURCE_URL,
) -> list[DuelTopic]:
    """対戦カード config から、両選手の実成績が揃うカードだけを topic 化する。

    ``stats_fn(player)`` は BattingStatsSeason 相当 (games/ab/hits/hr/rbi) を返す。
    片方でも成績なし / 両者とも min_ab 未満のカードは skip (config は正、成績が gate)。
    """
    topics: list[DuelTopic] = []
    for duel in duels:
        players = [str(p or "").strip() for p in (duel.get("players") or [])]
        slot = str(duel.get("slot") or "").strip()
        if len(players) != 2 or not all(players) or not slot:
            continue
        try:
            side_a = _side_from_stats(players[0], stats_fn(players[0]))
            side_b = _side_from_stats(players[1], stats_fn(players[1]))
        except Exception:  # noqa: BLE001 - 1 カードの取得失敗で全体を止めない
            continue
        if side_a is None or side_b is None:
            continue
        # 少なくとも片方が規定打席相当に達していないと「争い」の絵にならない。
        if max(side_a.ab, side_b.ab) < min_ab or min(side_a.ab, side_b.ab) <= 0:
            continue
        topics.append(
            DuelTopic(slot=slot, a=side_a, b=side_b, as_of=as_of, source_url=source_url)
        )
    return topics


def _avg_speech(display: str) -> str:
    return DECIMAL_RE.sub(_baseball_average_reading, display)


def _allowed_numbers(topic: DuelTopic) -> tuple[str, ...]:
    parts: list[str] = []
    for side in (topic.a, topic.b):
        parts += [str(side.games), side.avg_display, str(side.hr), str(side.rbi)]
    return tuple(dict.fromkeys(extract_number_tokens(" ".join(parts))))


def _side_line(side: DuelSide) -> str:
    return (
        f"{side.player}。ここまで{side.games}試合、打率{_avg_speech(side.avg_display)}、"
        f"ホームラン{side.hr}本、打点{side.rbi}。"
    )


def _opinion(topic: DuelTopic, pool: tuple[str, ...]) -> str:
    seed = sum(ord(ch) for ch in (topic.a.player + topic.b.player + topic.as_of))
    return pool[seed % len(pool)]


def build_duel_script(topic: DuelTopic) -> ShortsScript:
    allowed = _allowed_numbers(topic)
    leader = topic.leader

    if leader is not None:
        verdict_line = f"数字は今、{leader.player}がリード。" + _opinion(topic, DUEL_OPINION_LEAD)
        verdict_caption = f"数字は今 {leader.player}"
    else:
        verdict_line = _opinion(topic, DUEL_OPINION_EVEN)
        verdict_caption = "数字はほぼ互角"

    narration_parts = [
        f"巨人の{topic.slot}。数字で見ると、今どうなのか。",
        _side_line(topic.a),
        _side_line(topic.b),
        verdict_line,
        BRAND_CLOSING_LINE,
    ]
    narration = "\n".join(part for part in narration_parts if part.strip())
    assert_number_guard(narration, allowed)

    title = f"{topic.a.player} vs {topic.b.player}｜巨人{topic.slot}を数字で見る"
    desc_factual = (
        f"{topic.slot}: "
        f"{topic.a.player} {topic.a.games}試合 打率{topic.a.avg_display} {topic.a.hr}本 {topic.a.rbi}打点 / "
        f"{topic.b.player} {topic.b.games}試合 打率{topic.b.avg_display} {topic.b.hr}本 {topic.b.rbi}打点"
    )
    assert_number_guard(title + "\n" + desc_factual, allowed)
    desc_branding = (
        "\n\n"
        "巨人特化メディア「ヨシラバー」が、巨人のポジション争いを数字だけで比較。\n"
        "どちらかを貶す意図はありません。両選手への敬意を込めて。\n\n"
        f"▼巨人の全選手データ(毎日更新)\n{DATA_URL}\n\n"
        f"▼巨人ニュース・速報\n{SITE_URL}\n\n"
        f"▼X(旧Twitter)でも毎日発信\n{X_HANDLE}\n\n"
        "音声: VOICEVOX 青山龍星\n\n"
        + " ".join((*BASE_HASHTAGS, "#ポジション争い"))
    )
    description = desc_factual + desc_branding

    captions = (
        ScriptCaption(0.0, 2.4, f"巨人 {topic.slot}"),
        ScriptCaption(2.4, 9.4, f"{topic.a.player} 打率{topic.a.avg_display} {topic.a.hr}本 {topic.a.rbi}打点"),
        ScriptCaption(9.4, 16.4, f"{topic.b.player} 打率{topic.b.avg_display} {topic.b.hr}本 {topic.b.rbi}打点"),
        ScriptCaption(16.4, 22.4, verdict_caption),
        ScriptCaption(22.4, 27.0, "巨人データはヨシラバーで毎日更新中"),
    )
    assert_number_guard("\n".join(c.text for c in captions), allowed)

    tags = " ".join(BASE_HASHTAGS[:4])
    stance = (
        f"数字は今、{leader.player}。" if leader is not None else "数字はほぼ互角。"
    )
    x_post = "\n".join(
        [
            f"【{topic.slot}】{topic.a.player} vs {topic.b.player}",
            "",
            f"{topic.a.player} 打率{topic.a.avg_display} {topic.a.hr}本 {topic.a.rbi}打点",
            f"{topic.b.player} 打率{topic.b.avg_display} {topic.b.hr}本 {topic.b.rbi}打点",
            "",
            stance,
            "数字で見るポジション争い👇",
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
    "DEFAULT_MIN_AB",
    "DUEL_CONFIG_PATH",
    "DUEL_SOURCE_URL",
    "DuelSide",
    "DuelTopic",
    "build_duel_script",
    "list_duel_topics",
    "load_duel_config",
]
