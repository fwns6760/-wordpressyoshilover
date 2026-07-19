"""意外な数字 (スプリット上振れ) Shorts フォーマットのテスト (2026-07-19)。

- 上振れ (hot) だけ採用、下振れ・微差・サンプル僅少は出さない
- gap 降順で並ぶ
- 台本/字幕/X 文は number guard を通る (捏造防止)
- split フレーム描画 5 枚 (render smoke)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.yt_shorts_split import (
    build_split_script,
    find_surprise_topics,
)
from src.yt_shorts_script import verify_number_guard


def _entry(player="泉口友汰", season_ab=300, season_hits=75, buckets=None, kind="曜日別"):
    return {
        "player": player,
        "season": {"ab": season_ab, "hits": season_hits},
        "splits": {kind: buckets or []},
    }


class FindSurpriseTopicsTests(unittest.TestCase):
    def test_hot_bucket_is_selected(self):
        # 通算 .250、火曜日 .400 (25打数10安打) → gap +0.150 で採用
        entries = [
            _entry(buckets=[{"label": "火曜日", "games": 8, "ab": 25, "hits": 10}])
        ]
        topics = find_surprise_topics(entries, as_of="2026-07-19")
        self.assertEqual(len(topics), 1)
        self.assertEqual(topics[0].bucket, "火曜日")
        self.assertEqual(topics[0].bucket_avg_display, ".400")
        self.assertEqual(topics[0].season_avg_display, ".250")

    def test_cold_bucket_is_never_surfaced(self):
        # 下振れ (.100) は事実でも出さない (選手への敬意)
        entries = [
            _entry(buckets=[{"label": "水曜日", "games": 8, "ab": 30, "hits": 3}])
        ]
        self.assertEqual(find_surprise_topics(entries, as_of="2026-07-19"), [])

    def test_small_sample_bucket_is_skipped(self):
        # 10打数5安打 (.500) はサンプル僅少なので「意外な数字」と呼ばない
        entries = [
            _entry(buckets=[{"label": "日曜日", "games": 3, "ab": 10, "hits": 5}])
        ]
        self.assertEqual(find_surprise_topics(entries, as_of="2026-07-19"), [])

    def test_small_season_sample_is_skipped(self):
        entries = [
            _entry(
                season_ab=40,
                season_hits=10,
                buckets=[{"label": "火曜日", "games": 8, "ab": 25, "hits": 12}],
            )
        ]
        self.assertEqual(find_surprise_topics(entries, as_of="2026-07-19"), [])

    def test_topics_sorted_by_gap_desc(self):
        entries = [
            _entry(
                player="A選手",
                buckets=[{"label": "火曜日", "games": 8, "ab": 25, "hits": 9}],  # .360 gap .110
            ),
            _entry(
                player="B選手",
                buckets=[{"label": "対中日", "games": 10, "ab": 40, "hits": 18}],  # .450 gap .200
                kind="相手別",
            ),
        ]
        topics = find_surprise_topics(entries, as_of="2026-07-19")
        self.assertEqual([t.player for t in topics], ["B選手", "A選手"])


class SplitScriptTests(unittest.TestCase):
    def _topic(self):
        entries = [
            _entry(buckets=[{"label": "火曜日", "games": 8, "ab": 25, "hits": 10}])
        ]
        return find_surprise_topics(entries, as_of="2026-07-19")[0]

    def test_script_passes_number_guard(self):
        script = build_split_script(self._topic())
        for blob in (
            script.narration,
            script.title,
            "\n".join(c.text for c in script.captions),
            script.x_post.replace("[Shorts URL]", ""),
        ):
            ok, leaked = verify_number_guard(blob, script.allowed_numbers)
            self.assertTrue(ok, leaked)

    def test_narration_reads_averages_in_warihunrin(self):
        script = build_split_script(self._topic())
        self.assertIn("二割五分", script.narration)  # .250
        self.assertIn("四割", script.narration)      # .400

    def test_weekday_phrase_in_title(self):
        script = build_split_script(self._topic())
        self.assertIn("火曜日の試合", script.title)

    def test_month_bucket_numbers_are_allowed(self):
        # "7月" の 7 が bucket 名として allowed に入る
        entries = [
            _entry(
                buckets=[{"label": "7月", "games": 12, "ab": 40, "hits": 16}],
                kind="月別",
            )
        ]
        topic = find_surprise_topics(entries, as_of="2026-07-19")[0]
        script = build_split_script(topic)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)


class SplitRenderTests(unittest.TestCase):
    def test_render_frames_creates_five_pngs(self):
        from src.yt_shorts_render import render_frames

        entries = [
            _entry(buckets=[{"label": "火曜日", "games": 8, "ab": 25, "hits": 10}])
        ]
        topic = find_surprise_topics(entries, as_of="2026-07-19")[0]
        script = build_split_script(topic)
        with tempfile.TemporaryDirectory() as tmp:
            frames = render_frames(topic, script, Path(tmp), fmt="split")
            self.assertEqual(len(frames), 5)
            for frame in frames:
                self.assertTrue(Path(frame).exists())
                self.assertGreater(Path(frame).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
