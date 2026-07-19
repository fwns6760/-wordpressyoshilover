"""「意外な数字」YouTube Shorts — スプリット上振れフォーマット (2026-07-19 user GO)。

曜日別 / 月別 / 相手別 / 交流戦別のスプリット集計 (Phase B 452、大手未掲載) から
「通算とかけ離れて良い数字」を見つけて 1 本にする。組み合わせが多く
ネタ切れしにくいのが狙い (同じ案ばかり問題の根治枠)。

安全設計:
- 表面化するのは上振れ (hot) のみ。下振れ (苦手) は選手を貶す絵になり得る
  ため出さない (公開運用制約: 選手への敬意 / 事実でもネガ演出をしない)。
- 数字は全て insight.db 由来で assert_number_guard により捏造防止。
- サンプル僅少の偶然を「意外な数字」と呼ばない (bucket/season 両方に AB 下限)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping, Optional

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

SPLIT_SOURCE_URL = "https://yoshilover.com/data/notable?v=yt"

# 「意外」と言い切るための下限。bucket が小さすぎる偶然は採用しない。
DEFAULT_MIN_BUCKET_AB = 20
DEFAULT_MIN_SEASON_AB = 80
# 通算との乖離 (打率差) がこれ未満なら「意外」ではない。
DEFAULT_MIN_GAP = 0.060

# kind 表示 (ナレーション側の言い回し)。
_KIND_PHRASES = {
    "曜日別": "{bucket}の試合",
    "月別": "{bucket}",
    "相手別": "{bucket}戦",
    "交流戦": "交流戦",
}

SPLIT_OPINION_POOL = (
    "この数字、覚えておいて損はない。",
    "次の試合、この数字を思い出してほしい。",
    "データで見ると、選手の顔がもう一つ見えてくる。",
)


def _avg_display(hits: int, ab: int) -> str:
    if ab <= 0:
        return "-"
    return f".{int(round(hits / ab * 1000)):03d}"


@dataclass(frozen=True)
class SplitSurpriseTopic:
    player: str
    kind: str            # 曜日別 / 月別 / 相手別 / 交流戦
    bucket: str          # 例: 火曜日 / 7月 / 対中日 / 交流戦
    bucket_games: int
    bucket_ab: int
    bucket_hits: int
    season_ab: int
    season_hits: int
    as_of: str = ""
    image_url: str = ""
    credit: str = ""
    source_url: str = SPLIT_SOURCE_URL
    raw_item: dict[str, Any] = field(default_factory=dict)

    @property
    def topic_key(self) -> str:
        base = "|".join(["yt_shorts_split", self.player, self.kind, self.bucket, self.as_of])
        return re.sub(r"\s+", "", base)

    @property
    def bucket_avg_display(self) -> str:
        return _avg_display(self.bucket_hits, self.bucket_ab)

    @property
    def season_avg_display(self) -> str:
        return _avg_display(self.season_hits, self.season_ab)

    @property
    def gap(self) -> float:
        if self.bucket_ab <= 0 or self.season_ab <= 0:
            return 0.0
        return (self.bucket_hits / self.bucket_ab) - (self.season_hits / self.season_ab)

    @property
    def bucket_phrase(self) -> str:
        template = _KIND_PHRASES.get(self.kind, "{bucket}")
        return template.format(bucket=self.bucket)


def find_surprise_topics(
    entries: list[Mapping[str, Any]],
    *,
    as_of: str = "",
    min_bucket_ab: int = DEFAULT_MIN_BUCKET_AB,
    min_season_ab: int = DEFAULT_MIN_SEASON_AB,
    min_gap: float = DEFAULT_MIN_GAP,
    source_url: str = SPLIT_SOURCE_URL,
) -> list[SplitSurpriseTopic]:
    """選手ごとの split 集計から上振れ (hot) の「意外な数字」候補を返す (gap 降順)。

    entries の各要素:
      {"player": str,
       "season": {"ab": int, "hits": int},
       "splits": {kind: [{"label": str, "games": int, "ab": int, "hits": int}, ...]}}

    下振れ (bucket < season) は敬意の観点で採用しない。
    """
    topics: list[SplitSurpriseTopic] = []
    for entry in entries:
        player = str(entry.get("player") or "").strip()
        season = entry.get("season") or {}
        season_ab = int(season.get("ab") or 0)
        season_hits = int(season.get("hits") or 0)
        if not player or season_ab < min_season_ab:
            continue
        season_avg = season_hits / season_ab
        for kind, buckets in (entry.get("splits") or {}).items():
            for bucket in buckets or []:
                ab = int(bucket.get("ab") or 0)
                hits = int(bucket.get("hits") or 0)
                label = str(bucket.get("label") or "").strip()
                if not label or ab < min_bucket_ab:
                    continue
                gap = hits / ab - season_avg
                if gap < min_gap:
                    continue  # 下振れ/微差は出さない (hot only)
                topics.append(
                    SplitSurpriseTopic(
                        player=player,
                        kind=str(kind),
                        bucket=label,
                        bucket_games=int(bucket.get("games") or 0),
                        bucket_ab=ab,
                        bucket_hits=hits,
                        season_ab=season_ab,
                        season_hits=season_hits,
                        as_of=as_of,
                        source_url=source_url,
                    )
                )
    return sorted(topics, key=lambda t: (-t.gap, t.player, t.kind, t.bucket))


def _avg_speech(display: str) -> str:
    return DECIMAL_RE.sub(_baseball_average_reading, display)


def _allowed_numbers(topic: SplitSurpriseTopic) -> tuple[str, ...]:
    parts = [
        topic.season_avg_display,
        topic.bucket_avg_display,
        str(topic.bucket_games),
        str(topic.bucket_ab),
        str(topic.bucket_hits),
        topic.bucket,  # "7月" 等、bucket 名自体の数字も許可
    ]
    return tuple(dict.fromkeys(extract_number_tokens(" ".join(parts))))


def _opinion(topic: SplitSurpriseTopic) -> str:
    seed = sum(ord(ch) for ch in (topic.player + topic.kind + topic.bucket))
    return SPLIT_OPINION_POOL[seed % len(SPLIT_OPINION_POOL)]


def build_split_script(topic: SplitSurpriseTopic) -> ShortsScript:
    allowed = _allowed_numbers(topic)
    phrase = topic.bucket_phrase

    narration_parts = [
        f"知ってました？巨人、{topic.player}の意外な数字。",
        f"今シーズン通算の打率は、{_avg_speech(topic.season_avg_display)}。",
        f"ところが{phrase}に限ると、{topic.bucket_games}試合で打率{_avg_speech(topic.bucket_avg_display)}。",
        _opinion(topic),
        BRAND_CLOSING_LINE,
    ]
    narration = "\n".join(part for part in narration_parts if part.strip())
    assert_number_guard(narration, allowed)

    title = f"{topic.player}、{phrase}だと打率{topic.bucket_avg_display}｜巨人の意外な数字"
    desc_factual = (
        f"{topic.player} 通算打率{topic.season_avg_display} → {phrase} "
        f"{topic.bucket_games}試合 {topic.bucket_ab}打数{topic.bucket_hits}安打 "
        f"打率{topic.bucket_avg_display}"
    )
    assert_number_guard(title + "\n" + desc_factual, allowed)
    desc_branding = (
        "\n\n"
        "巨人特化メディア「ヨシラバー」が、大手が載せない切り口の巨人データを毎日発信。\n\n"
        f"▼巨人の全選手データ(毎日更新)\n{DATA_URL}\n\n"
        f"▼巨人ニュース・速報\n{SITE_URL}\n\n"
        f"▼X(旧Twitter)でも毎日発信\n{X_HANDLE}\n\n"
        "音声: VOICEVOX 青山龍星\n\n"
        + " ".join((*BASE_HASHTAGS, "#意外な数字"))
    )
    description = desc_factual + desc_branding

    captions = (
        ScriptCaption(0.0, 2.6, f"{topic.player}の意外な数字"),
        ScriptCaption(2.6, 8.8, f"通算 打率{topic.season_avg_display}"),
        ScriptCaption(8.8, 16.2, f"{phrase} 打率{topic.bucket_avg_display}"),
        ScriptCaption(16.2, 22.4, f"{topic.bucket_games}試合 {topic.bucket_ab}打数{topic.bucket_hits}安打"),
        ScriptCaption(22.4, 27.0, "巨人データはヨシラバーで毎日更新中"),
    )
    assert_number_guard("\n".join(c.text for c in captions), allowed)

    tags = " ".join(BASE_HASHTAGS[:4])
    x_post = "\n".join(
        [
            f"知ってました？{topic.player}、{phrase}だと打率{topic.bucket_avg_display}",
            "",
            f"通算 {topic.season_avg_display} → {phrase} {topic.bucket_avg_display}"
            f"（{topic.bucket_games}試合 {topic.bucket_ab}打数{topic.bucket_hits}安打）",
            "",
            "意外な数字、動画でどうぞ👇",
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
    "DEFAULT_MIN_BUCKET_AB",
    "DEFAULT_MIN_GAP",
    "DEFAULT_MIN_SEASON_AB",
    "SPLIT_SOURCE_URL",
    "SplitSurpriseTopic",
    "build_split_script",
    "find_surprise_topics",
]
