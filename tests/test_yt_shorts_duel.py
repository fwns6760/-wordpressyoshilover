"""争点対決 (定位置争い) Shorts フォーマットのテスト (2026-07-19)。

- config カード + 実成績 gate → topic 化 (成績なし/サンプル僅少は skip)
- leader は 3 指標 (打率/本塁打/打点) の多数決、同数は互角 (None)
- 台本/字幕/X 文は number guard を通る (捏造防止)
- duel フレーム描画 5 枚 (render smoke)
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from src.yt_shorts_duel import (
    DEFAULT_MIN_AB,
    build_duel_script,
    list_duel_topics,
    load_duel_config,
)
from src.yt_shorts_script import verify_number_guard


@dataclass
class _Stats:
    games: int = 0
    ab: int = 0
    hits: int = 0
    hr: int = 0
    rbi: int = 0


_STATS = {
    # 泉口リード (打率 .320 / 5本 / 30打点 vs .250 / 2本 / 18打点)
    "泉口友汰": _Stats(games=80, ab=300, hits=96, hr=5, rbi=30),
    "門脇誠": _Stats(games=70, ab=200, hits=50, hr=2, rbi=18),
    # 互角 (打率で吉川、本塁打で浦田、打点同数)
    "吉川尚輝": _Stats(games=40, ab=150, hits=45, hr=1, rbi=15),
    "浦田俊輔": _Stats(games=60, ab=180, hits=48, hr=3, rbi=15),
}

_DUELS = [
    {"slot": "遊撃 定位置争い", "players": ["泉口友汰", "門脇誠"]},
    {"slot": "二遊間 定位置争い", "players": ["吉川尚輝", "浦田俊輔"]},
    {"slot": "正捕手争い", "players": ["甲斐拓也", "岸田行倫"]},  # 成績なし → skip
]


def _stats_fn(player: str):
    return _STATS.get(player)


class DuelTopicTests(unittest.TestCase):
    def test_cards_without_stats_are_skipped(self):
        topics = list_duel_topics(_DUELS, _stats_fn, as_of="2026-07-19")
        slots = [t.slot for t in topics]
        self.assertIn("遊撃 定位置争い", slots)
        self.assertNotIn("正捕手争い", slots)

    def test_low_sample_card_is_skipped(self):
        duels = [{"slot": "テスト枠", "players": ["A選手", "B選手"]}]
        stats = {"A選手": _Stats(games=5, ab=DEFAULT_MIN_AB - 1, hits=5, hr=1, rbi=2),
                 "B選手": _Stats(games=4, ab=10, hits=3, hr=0, rbi=1)}
        topics = list_duel_topics(duels, lambda p: stats.get(p), as_of="2026-07-19")
        self.assertEqual(topics, [])

    def test_leader_is_metric_majority(self):
        topics = list_duel_topics(_DUELS, _stats_fn, as_of="2026-07-19")
        by_slot = {t.slot: t for t in topics}
        shuugeki = by_slot["遊撃 定位置争い"]
        self.assertEqual(shuugeki.leader.player, "泉口友汰")

    def test_even_duel_has_no_leader(self):
        topics = list_duel_topics(_DUELS, _stats_fn, as_of="2026-07-19")
        by_slot = {t.slot: t for t in topics}
        nijuukan = by_slot["二遊間 定位置争い"]
        # 打率 .300 (吉川) vs .267 (浦田) / HR 1 vs 3 / 打点 15 vs 15 → 1-1
        self.assertIsNone(nijuukan.leader)

    def test_avg_display_is_three_digit_ratio(self):
        topics = list_duel_topics(_DUELS, _stats_fn, as_of="2026-07-19")
        by_slot = {t.slot: t for t in topics}
        self.assertEqual(by_slot["遊撃 定位置争い"].a.avg_display, ".320")


class DuelScriptTests(unittest.TestCase):
    def _topic(self, slot="遊撃 定位置争い"):
        topics = list_duel_topics(_DUELS, _stats_fn, as_of="2026-07-19")
        return {t.slot: t for t in topics}[slot]

    def test_script_passes_number_guard(self):
        script = build_duel_script(self._topic())
        # description はブランド定型文 (@handle 等) を含むため、guard は
        # narration / captions / x_post + factual 部 (build 内 assert 済) が対象。
        for blob in (
            script.narration,
            script.title,
            "\n".join(c.text for c in script.captions),
            script.x_post.replace("[Shorts URL]", ""),
        ):
            ok, leaked = verify_number_guard(blob, script.allowed_numbers)
            self.assertTrue(ok, leaked)

    def test_leader_verdict_in_script_and_x_post(self):
        script = build_duel_script(self._topic())
        self.assertIn("数字は今、泉口友汰", script.narration)
        self.assertIn("数字は今、泉口友汰", script.x_post)

    def test_even_duel_uses_neutral_verdict(self):
        script = build_duel_script(self._topic("二遊間 定位置争い"))
        self.assertNotIn("がリード", script.narration)
        self.assertIn("互角", script.narration)

    def test_average_read_in_warihunrin(self):
        script = build_duel_script(self._topic())
        # .320 → 三割二分 (割分厘読み、TTS 用)
        self.assertIn("三割二分", script.narration)


class DuelRenderTests(unittest.TestCase):
    def test_render_frames_creates_five_pngs(self):
        from src.yt_shorts_render import render_frames

        topic = {t.slot: t for t in list_duel_topics(_DUELS, _stats_fn, as_of="2026-07-19")}[
            "遊撃 定位置争い"
        ]
        script = build_duel_script(topic)
        with tempfile.TemporaryDirectory() as tmp:
            frames = render_frames(topic, script, Path(tmp), fmt="duel")
            self.assertEqual(len(frames), 5)
            for frame in frames:
                self.assertTrue(Path(frame).exists())
                self.assertGreater(Path(frame).stat().st_size, 0)


class DuelConfigTests(unittest.TestCase):
    def test_repo_config_players_exist_in_player_class(self):
        """カード config の選手名は NPB 公式由来の選手分類 config に実在すること。"""
        import json
        from pathlib import Path as _P

        duels = load_duel_config()
        self.assertGreater(len(duels), 0)
        klass = json.loads(
            (_P(__file__).resolve().parents[1] / "config" / "data_site_player_class.json").read_text(
                encoding="utf-8"
            )
        )
        known: set[str] = set()
        for section in ("shihai", "ikusei"):
            for names in (klass.get(section) or {}).values():
                known.update(names or [])
        for duel in duels:
            for player in duel.get("players") or []:
                self.assertIn(player, known, f"{player} が player_class config に無い")


if __name__ == "__main__":
    unittest.main()
