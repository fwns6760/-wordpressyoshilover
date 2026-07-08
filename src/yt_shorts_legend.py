"""「巨人レジェンド記録室」YouTube Shorts のトピック選定と台本生成。

主ブランド (2026-06-13 user 確定): 現役データ速報は補助、巨人レジェンドを記録で
再評価する Shorts が主軸。著作権ハードルール (§18) のため選手写真は使わず、
config/ob_legends*.json の記録データを rights-clean なデータカードで見せる。

固定オープニング「巨人レジェンド記録室！」/ 固定締め「あなたにとってこの選手は
巨人歴代何位？」/ 数字は npb 記録・在籍年・honors から抽出した allowed のみ
(assert_number_guard で捏造防止)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from src.yt_shorts_script import (
    BASE_HASHTAGS,
    BRAND_CLOSING_LINE,
    DATA_URL,
    SITE_URL,
    X_HANDLE,
    ScriptCaption,
    ShortsScript,
    _baseball_average_reading,
    _decimal_point_reading,
    _hashtag_player,
    DECIMAL_RE,
    assert_number_guard,
    extract_number_tokens,
)
from src.yt_shorts_topic import DEFAULT_SOURCE_URL


LEGEND_SOURCE_URL = "https://yoshilover.com/data/record?v=yt"
LEGEND_OPENING = "巨人レジェンド記録室！"
LEGEND_CLOSING = "あなたにとってこの選手は、巨人歴代何位の選手ですか？"
BRAND_LINE = "巨人の歴史を、記録で語る。"

# 記録の強さで採点する時の最低ライン (記録が薄い OB を主役回から外す)。
MIN_BATTER_HR = 150
MIN_BATTER_HITS = 1200
MIN_PITCHER_WINS = 100
MIN_PITCHER_K = 1200

# short_opinion プール (数字なし=量産AIに見えない一言)。name で deterministic rotate。
LEGEND_OPINION_POOL: tuple[str, ...] = (
    "巨人の歴史に名前が残る選手。",
    "記録で見ても、やっぱり別格。",
    "今振り返っても色褪せない数字。",
    "巨人ファンなら一度は語りたくなる存在。",
    "その凄みは、記録が物語ります。",
    "時代を越えて語り継がれる一人。",
)


@dataclass(frozen=True)
class LegendRecord:
    label: str
    value: str


@dataclass(frozen=True)
class LegendTopic:
    player: str            # display_name
    slug: str
    player_type: str       # "batter" / "pitcher"
    years: str
    teams: str
    giants_context: str
    records: tuple[LegendRecord, ...]
    honors: tuple[str, ...]
    opinion: str
    priority: float = 0.0
    source_url: str = LEGEND_SOURCE_URL
    raw_item: dict[str, Any] = field(default_factory=dict)
    as_of: str = ""        # レジェンドは timeless。記録日 chrome は出さない。
    image_url: str = ""    # Commons の free ライセンス写真(無ければ空 → 記録カード)。
    credit: str = ""       # 写真クレジット(CC 帰属表示)。

    @property
    def topic_key(self) -> str:
        # 日付に依存しない安定キー。同じレジェンドの重複を cooldown で弾くため。
        base = "|".join(["yt_shorts_legend", self.slug or self.player])
        return re.sub(r"\s+", "", base)


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _legend_opinion(player: str) -> str:
    seed = sum(ord(ch) for ch in (player or "x"))
    return LEGEND_OPINION_POOL[seed % len(LEGEND_OPINION_POOL)]


def _giants_context(years: str, teams: str) -> str:
    years = (years or "").strip()
    teams = (teams or "").strip()
    if years and teams:
        return f"{years}年、{teams}でプレー。"
    if teams:
        return f"{teams}でプレー。"
    if years:
        return f"{years}年に活躍。"
    return "巨人の歴史を彩った一人。"


def _records_for_entry(entry: dict[str, Any]) -> list[LegendRecord]:
    npb = entry.get("npb") or {}
    ptype = str(entry.get("type") or "batter")
    out: list[LegendRecord] = []
    if ptype == "pitcher":
        wins = _to_int(npb.get("w"))
        if wins is not None:
            out.append(LegendRecord("通算勝利", f"{wins}勝"))
        era = str(npb.get("era") or "").strip()
        if era:
            out.append(LegendRecord("防御率", era))
        k = _to_int(npb.get("k"))
        if k is not None:
            out.append(LegendRecord("通算奪三振", f"{k}"))
    else:
        hr = _to_int(npb.get("hr"))
        if hr is not None:
            out.append(LegendRecord("通算本塁打", f"{hr}本"))
        hits = _to_int(npb.get("hits"))
        if hits is not None:
            out.append(LegendRecord("通算安打", f"{hits}"))
        avg = str(npb.get("avg") or "").strip()
        if avg:
            out.append(LegendRecord("通算打率", avg))
        rbi = _to_int(npb.get("rbi"))
        if rbi is not None and len(out) < 3:
            out.append(LegendRecord("通算打点", f"{rbi}"))
    return out


def _priority_for_entry(entry: dict[str, Any]) -> float | None:
    """記録の強さで採点。最低ラインに満たない OB は None (主役回から除外)。"""
    npb = entry.get("npb") or {}
    ptype = str(entry.get("type") or "batter")
    has_honors = bool(entry.get("honors"))
    score = 0.0
    if ptype == "pitcher":
        wins = _to_int(npb.get("w")) or 0
        k = _to_int(npb.get("k")) or 0
        if wins < MIN_PITCHER_WINS and k < MIN_PITCHER_K:
            return None
        score = wins * 3.0 + k / 20.0
    else:
        hr = _to_int(npb.get("hr")) or 0
        hits = _to_int(npb.get("hits")) or 0
        if hr < MIN_BATTER_HR and hits < MIN_BATTER_HITS:
            return None
        score = hr * 2.0 + hits / 10.0
    # 殿堂級 (curated honors 付き) を優先して主役に。
    if has_honors:
        score += 1000.0
    return score


def legend_topic_from_entry(
    entry: dict[str, Any],
    *,
    source_url: str = LEGEND_SOURCE_URL,
) -> LegendTopic | None:
    name = str(entry.get("display_name") or "").strip()
    if not name:
        return None
    priority = _priority_for_entry(entry)
    if priority is None:
        return None
    records = _records_for_entry(entry)
    if len(records) < 2:
        return None
    years = str(entry.get("years") or "").strip()
    teams = str(entry.get("teams") or "").strip()
    honors = tuple(str(h).strip() for h in (entry.get("honors") or []) if str(h).strip())
    return LegendTopic(
        player=name,
        slug=str(entry.get("slug") or "").strip(),
        player_type=str(entry.get("type") or "batter"),
        years=years,
        teams=teams,
        giants_context=_giants_context(years, teams),
        records=tuple(records),
        honors=honors,
        opinion=_legend_opinion(name),
        priority=priority,
        source_url=source_url,
        raw_item=dict(entry),
    )


def list_legend_topics(
    entries: list[dict[str, Any]] | None,
    *,
    source_url: str = LEGEND_SOURCE_URL,
) -> list[LegendTopic]:
    """OB profile entries を主役向きの順 (記録が強い順) に並べて返す。"""
    topics: list[LegendTopic] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        topic = legend_topic_from_entry(entry, source_url=source_url)
        if topic is not None:
            topics.append(topic)
    return sorted(topics, key=lambda t: (-t.priority, t.player))


def select_legend_topic(
    entries: list[dict[str, Any]] | None,
    *,
    source_url: str = LEGEND_SOURCE_URL,
) -> LegendTopic | None:
    topics = list_legend_topics(entries, source_url=source_url)
    return topics[0] if topics else None


def _allowed_numbers(topic: LegendTopic) -> tuple[str, ...]:
    # 在籍年 / 記録値 / honors の数字はすべて出典由来 = allowed。
    source_text = " ".join(
        [topic.years, topic.giants_context]
        + [f"{r.label}{r.value}" for r in topic.records]
        + list(topic.honors)
        + [str((topic.raw_item.get("npb") or {}).get(k) or "") for k in ("games", "hr", "hits", "rbi", "avg", "w", "era", "k", "l")]
    )
    return tuple(dict.fromkeys(extract_number_tokens(source_text)))


def _speech_value(record: LegendRecord) -> str:
    """記録値を TTS が自然に読める文へ。打率/防御率の小数は読み下す。"""
    value = record.value
    if record.label == "通算打率":
        return DECIMAL_RE.sub(_baseball_average_reading, value)
    if record.label == "防御率":
        return DECIMAL_RE.sub(_decimal_point_reading, value)
    return value


def _reading_name(topic: LegendTopic) -> str:
    """narration 用の読み。data に kana があれば優先 (VOICEVOX 誤読対策)。"""
    kana = str(topic.raw_item.get("kana") or "").strip()
    return kana or topic.player


def build_legend_script(topic: LegendTopic) -> ShortsScript:
    allowed = _allowed_numbers(topic)
    reading = _reading_name(topic)

    record_speech = "、".join(f"{r.label}、{_speech_value(r)}" for r in topic.records[:3])
    narration_parts = [
        LEGEND_OPENING,
        f"今日の主役は、{reading}。",
        topic.giants_context,
        f"巨人時代の主な記録は、{record_speech}。",
        f"数字で見ても、やっぱり{topic.opinion}",
        # QC の締めヨシラバー必須 gate (yt_shorts_qc) 対応。エンゲージ質問
        # (LEGEND_CLOSING) を最後に残すため、ブランド締めはその直前に置く。
        BRAND_CLOSING_LINE,
        LEGEND_CLOSING,
    ]
    narration = "\n".join(part for part in narration_parts if part.strip())
    assert_number_guard(narration, allowed)

    title = f"巨人レジェンド記録室｜{topic.player}"
    desc_factual = f"{topic.player}｜{topic.giants_context}"
    assert_number_guard(title + "\n" + desc_factual, allowed)
    honor_block = ""
    if topic.honors:
        honor_block = "\n".join(f"・{h}" for h in topic.honors[:4]) + "\n\n"
    credit_block = (topic.credit.strip() + "\n\n") if topic.credit.strip() else ""
    desc_branding = (
        "\n\n"
        f"{BRAND_LINE}\n"
        "巨人特化メディア「ヨシラバー」が、巨人レジェンドを記録で再評価する Shorts。\n\n"
        + credit_block
        + honor_block
        + f"▼巨人の記録室・選手データ\n{DATA_URL}\n\n"
        f"▼巨人ニュース・速報\n{SITE_URL}\n\n"
        f"▼X(旧Twitter)でも毎日発信\n{X_HANDLE}\n\n"
        "音声: VOICEVOX 青山龍星\n\n"
        + " ".join((*BASE_HASHTAGS, "#巨人レジェンド", f"#{_hashtag_player(topic.player)}"))
    )
    # 固定ブランディング文(@handle / 導線 / クレジット)は捏造数字ではないので
    # ガード外。事実数字 (記録・在籍年・honors) は title/desc_factual/narration で検証済み。
    description = desc_factual + desc_branding

    rec = topic.records
    captions = (
        ScriptCaption(0.0, 2.2, LEGEND_OPENING),
        ScriptCaption(2.2, 8.4, f"今日の主役 {topic.player}"),
        ScriptCaption(8.4, 14.8, f"{rec[0].label} {rec[0].value}"),
        ScriptCaption(14.8, 21.0, f"{rec[1].label} {rec[1].value}"),
        ScriptCaption(21.0, 27.0, "巨人歴代何位？"),
    )
    assert_number_guard("\n".join(c.text for c in captions), allowed)

    tags = " ".join(BASE_HASHTAGS[:4])
    x_post = "\n".join(
        [
            f"【巨人レジェンド記録室】{topic.player}",
            "",
            topic.giants_context,
            f"{rec[0].label} {rec[0].value} / {rec[1].label} {rec[1].value}",
            "",
            topic.opinion,
            "あなたにとって巨人歴代何位？ Shorts👇",
            "[Shorts URL]",
            "",
            f"巨人の記録室 → {DATA_URL}",
            tags + " #巨人レジェンド",
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
    "LEGEND_CLOSING",
    "LEGEND_OPENING",
    "LEGEND_SOURCE_URL",
    "LegendRecord",
    "LegendTopic",
    "build_legend_script",
    "legend_topic_from_entry",
    "list_legend_topics",
    "select_legend_topic",
]
