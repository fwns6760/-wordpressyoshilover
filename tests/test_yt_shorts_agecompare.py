"""同い年対決 (同年齢レジェンド対比) Shorts フォーマットのテスト (2026-07-19)。

- legend_age_compare_facts (X 角度① と共通の採点) の rows → topic 化
- 不完全 row (名前欠け / 0 本) は skip
- 台本/字幕/X 文は number guard を通る (捏造防止)
- agecompare フレーム描画 5 枚 (render smoke)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.yt_shorts_agecompare import (
    build_agecompare_script,
    topics_from_facts,
)
from src.yt_shorts_script import verify_number_guard

_FACTS = [
    {
        "player": "岡本和真",
        "age": 24,
        "cum_hr": 100,
        "beaten_name": "松井秀喜",
        "beaten_cum": 89,
        "above_name": "王貞治",
        "above_cum": 155,
    },
    {"player": "", "age": 22, "cum_hr": 10, "beaten_name": "誰か", "beaten_cum": 5},
    {"player": "若手太郎", "age": 22, "cum_hr": 10, "beaten_name": "誰か", "beaten_cum": 0},
]


class AgeCompareTopicTests(unittest.TestCase):
    def test_valid_rows_become_topics_and_invalid_skipped(self):
        topics = topics_from_facts(_FACTS, as_of="2026-07-19")
        self.assertEqual(len(topics), 1)
        t = topics[0]
        self.assertEqual(t.player, "岡本和真")
        self.assertEqual(t.beaten_cum, 89)
        self.assertEqual(t.above_name, "王貞治")

    def test_topic_key_is_stable(self):
        t = topics_from_facts(_FACTS, as_of="2026-07-19")[0]
        self.assertEqual(t.topic_key, "yt_shorts_agecompare|岡本和真|24|100")


class AgeCompareScriptTests(unittest.TestCase):
    def _topic(self, with_above=True):
        facts = [dict(_FACTS[0])]
        if not with_above:
            facts[0]["above_name"] = ""
            facts[0]["above_cum"] = 0
        return topics_from_facts(facts, as_of="2026-07-19")[0]

    def test_script_passes_number_guard(self):
        script = build_agecompare_script(self._topic())
        for blob in (
            script.narration,
            script.title,
            "\n".join(c.text for c in script.captions),
            script.x_post.replace("[Shorts URL]", ""),
        ):
            ok, leaked = verify_number_guard(blob, script.allowed_numbers)
            self.assertTrue(ok, leaked)

    def test_narration_uses_kanji_numbers_for_tts(self):
        script = build_agecompare_script(self._topic())
        # 100本 → 百本、89本 → 八十九本 (桁ごと読み防止)
        self.assertIn("百本", script.narration)
        self.assertIn("八十九本", script.narration)

    def test_above_wall_included_when_present(self):
        script = build_agecompare_script(self._topic())
        self.assertIn("王貞治", script.narration)
        self.assertIn("次は王貞治の155本", script.x_post)

    def test_no_above_wall_uses_forward_looking_close(self):
        script = build_agecompare_script(self._topic(with_above=False))
        self.assertNotIn("次の壁", script.narration)
        ok, leaked = verify_number_guard(script.narration, script.allowed_numbers)
        self.assertTrue(ok, leaked)


class AgeCompareRenderTests(unittest.TestCase):
    def test_render_frames_creates_five_pngs(self):
        from src.yt_shorts_render import render_frames

        topic = topics_from_facts(_FACTS, as_of="2026-07-19")[0]
        script = build_agecompare_script(topic)
        with tempfile.TemporaryDirectory() as tmp:
            frames = render_frames(topic, script, Path(tmp), fmt="agecompare")
            self.assertEqual(len(frames), 5)
            for frame in frames:
                self.assertTrue(Path(frame).exists())
                self.assertGreater(Path(frame).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
