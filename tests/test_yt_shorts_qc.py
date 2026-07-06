"""Tests for yt_shorts_qc (MP4実測品質ゲート) + 読み辞書拡充 (2026-07-06 user指示)。

- 尺は台本文字数ではなく実測秒で判定 (evaluate_qc は純関数でテスト)
- NG条件: 想定尺超過 / 短すぎ / 音声途中切れ / 締め欠落 / 末尾無音 / テンポ / 残漢字名
- 読み辞書: NPB baked 全ロースター + 手動 OVERRIDES (山﨑伊織=やまさき修正含む)
"""

from __future__ import annotations

import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from src.yt_shorts_qc import ShortsQCReport, evaluate_qc, probe_media_seconds

_OK_NARRATION = "とごうしょうせいが好投。巨人データはヨシラバーで毎日更新中。"


def _eval(**kw):
    base = dict(
        video_seconds=30.0,
        audio_seconds=29.0,
        tts_text=_OK_NARRATION,
        frame_count=5,
        min_seconds=15.0,
        max_seconds=58.5,
    )
    base.update(kw)
    return evaluate_qc(**base)


class EvaluateQCTests(unittest.TestCase):
    def test_pass_case(self):
        report = _eval()
        self.assertTrue(report.ok, report.issues)
        self.assertEqual(report.issues, ())

    def test_over_max_seconds_ng(self):
        report = _eval(video_seconds=61.0, audio_seconds=60.5)
        self.assertFalse(report.ok)
        self.assertTrue(any("想定尺超過" in i for i in report.issues))
        self.assertTrue(report.fixes)

    def test_under_min_seconds_ng(self):
        report = _eval(video_seconds=8.0, audio_seconds=7.5)
        self.assertFalse(report.ok)
        self.assertTrue(any("短すぎ" in i for i in report.issues))

    def test_audio_truncated_ng(self):
        # 音声が動画より長い = ffmpeg -t で途中切れ (締め欠落)
        report = _eval(video_seconds=58.0, audio_seconds=63.0)
        self.assertFalse(report.ok)
        self.assertTrue(any("途中で切れている" in i for i in report.issues))

    def test_long_trailing_silence_ng(self):
        report = _eval(video_seconds=40.0, audio_seconds=20.0)
        self.assertFalse(report.ok)
        self.assertTrue(any("無音が長い" in i for i in report.issues))

    def test_slow_tempo_per_frame_ng(self):
        report = _eval(video_seconds=50.0, audio_seconds=49.0, frame_count=4)
        self.assertFalse(report.ok)
        self.assertTrue(any("テンポ" in i for i in report.issues))

    def test_missing_closing_brand_ng(self):
        report = _eval(tts_text="とごうしょうせいが好投。以上です。")
        self.assertFalse(report.ok)
        self.assertTrue(any("ヨシラバー表記" in i for i in report.issues))

    def test_kanji_player_name_left_in_tts_ng(self):
        # 読み辞書に登録済みの名前が漢字のまま残っている = 変換漏れ
        report = _eval(
            tts_text="坂本勇人が決めた。巨人データはヨシラバーで毎日更新中。"
        )
        self.assertFalse(report.ok)
        self.assertTrue(any("漢字のまま" in i for i in report.issues))

    def test_zero_video_seconds_ng(self):
        report = _eval(video_seconds=0.0)
        self.assertFalse(report.ok)
        self.assertTrue(any("実測できない" in i for i in report.issues))

    def test_summary_format(self):
        report = ShortsQCReport(
            ok=False, issues=("x",), fixes=("y",), video_seconds=1.0, audio_seconds=2.0
        )
        self.assertIn("QC NG", report.summary())


class ProbeTests(unittest.TestCase):
    def test_wav_fallback_without_ffprobe(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "a.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(24000)
                w.writeframes(b"\x00\x00" * 48000)  # 2.0s
            seconds = probe_media_seconds(path, ffprobe_bin="no-such-ffprobe-bin")
            self.assertAlmostEqual(seconds, 2.0, places=2)

    def test_missing_file_returns_zero(self):
        self.assertEqual(probe_media_seconds("/no/such/file.mp4"), 0.0)


class NameReadingTests(unittest.TestCase):
    def test_yamasaki_reading_fixed(self):
        # NPB公式 pc_v_kana = やまさき (やまざきは誤読、2026-07-06 修正)
        from src.yt_shorts_script import _apply_name_readings

        self.assertEqual(_apply_name_readings("山﨑伊織"), "やまさきいおり")
        self.assertEqual(_apply_name_readings("山崎伊織"), "やまさきいおり")

    def test_user_priority_names(self):
        from src.yt_shorts_script import _apply_name_readings

        cases = {
            "坂本勇人": "さかもとはやと",
            "吉川尚輝": "よしかわなおき",
            "大勢": "たいせい",
            "戸郷翔征": "とごうしょうせい",
            "岡本和真": "おかもとかずま",
            "菅野智之": "すがのともゆき",
            "松井秀喜": "まついひでき",
            "原辰徳": "はらたつのり",
            "高橋由伸": "たかはしよしのぶ",
        }
        for kanji, kana in cases.items():
            self.assertEqual(_apply_name_readings(kanji), kana, kanji)

    def test_baked_full_roster_loaded(self):
        from src.yt_shorts_script import ALL_NAME_READINGS

        # baked (93名) + 手動 OVERRIDES で 100 以上。未登録名の漢字素通りを防ぐ網
        self.assertGreaterEqual(len(ALL_NAME_READINGS), 100)
        self.assertEqual(ALL_NAME_READINGS.get("門脇誠"), "かどわきまこと")


if __name__ == "__main__":
    unittest.main()
