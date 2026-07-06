"""Tests for セグメント同期TTS (2026-07-06 Shorts品質改善②)。

字幕フレームと音声を1:1同期し、比例伸縮方式のズレ・締め切れを構造的に無くす。
- build_script: 5フレームと1:1の narration_segments を持つ
- prepare_audio_segmented: セグメント実尺 + GAP = フレーム尺、無音paddingで連結
- 不成立時 (segments無し / VOICEVOX無し) は None で旧経路 fallback
"""

from __future__ import annotations

import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.yt_shorts_render import (
    MIN_SEGMENT_FRAME_SECONDS,
    SEGMENT_GAP_SECONDS,
    _concat_wavs_with_padding,
    prepare_audio_segmented,
)
from src.yt_shorts_script import build_script
from src.yt_shorts_topic import ShortsTopic


def _topic() -> ShortsTopic:
    return ShortsTopic(
        player="門脇誠",
        slug="kadowaki-makoto",
        label="連続試合安打",
        value="6試合",
        note="今季最長6試合",
        category="streak",
        as_of="2026-07-06",
        title="門脇誠、連続試合安打6試合",
        hook="門脇誠、6試合連続安打。",
    )


def _write_wav(path: Path, seconds: float, rate: int = 24000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


class BuildScriptSegmentsTests(unittest.TestCase):
    def test_five_segments_matching_frames(self):
        script = build_script(_topic())
        self.assertEqual(len(script.narration_segments), 5)
        # narration はセグメントの join と一致 (数値ガード・読み変換の整合)
        self.assertEqual(script.narration, "\n".join(script.narration_segments))
        # 締めのブランド行は最終セグメント
        self.assertIn("ヨシラバー", script.narration_segments[-1])
        # 選手名は かな 変換済み (TTS に漢字名を渡さない)
        self.assertNotIn("門脇誠", script.narration)
        self.assertIn("かどわきまこと", script.narration_segments[0])


class ConcatPaddingTests(unittest.TestCase):
    def test_concat_pads_each_segment_to_frame_duration(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            paths = []
            for i, sec in enumerate((1.0, 2.0)):
                p = base / f"s{i}.wav"
                _write_wav(p, sec)
                paths.append(p)
            out = _concat_wavs_with_padding(paths, (3.0, 4.0), base / "out.wav")
            self.assertAlmostEqual(_wav_seconds(out), 7.0, places=2)

    def test_format_mismatch_raises(self):
        with TemporaryDirectory() as td:
            base = Path(td)
            a, b = base / "a.wav", base / "b.wav"
            _write_wav(a, 1.0, rate=24000)
            _write_wav(b, 1.0, rate=44100)
            with self.assertRaises(ValueError):
                _concat_wavs_with_padding([a, b], (2.0, 2.0), base / "o.wav")


class PrepareAudioSegmentedTests(unittest.TestCase):
    def test_returns_none_without_segments_or_url(self):
        script = build_script(_topic())
        with TemporaryDirectory() as td:
            self.assertIsNone(
                prepare_audio_segmented(script, Path(td), voicevox_base_url="")
            )
            bare = script.__class__(**{**script.__dict__, "narration_segments": ()})
            self.assertIsNone(
                prepare_audio_segmented(bare, Path(td), voicevox_base_url="http://vv")
            )

    def test_frame_durations_follow_segment_audio(self):
        script = build_script(_topic())
        seg_secs = (2.5, 1.0, 3.0, 2.0, 1.2)
        calls = {"i": 0}

        def fake_synth(text, output_wav, *, base_url, speaker=13, **_kw):
            _write_wav(Path(output_wav), seg_secs[calls["i"]])
            calls["i"] += 1
            return Path(output_wav)

        with TemporaryDirectory() as td, patch(
            "src.yt_shorts_render.synthesize_voicevox", side_effect=fake_synth
        ):
            result = prepare_audio_segmented(
                script, Path(td), voicevox_base_url="http://vv"
            )
            self.assertIsNotNone(result)
            audio_path, durations = result
            expected = tuple(
                max(MIN_SEGMENT_FRAME_SECONDS, round(s + SEGMENT_GAP_SECONDS, 3))
                for s in seg_secs
            )
            self.assertEqual(durations, expected)
            # 連結音声の実尺 = フレーム尺合計 (各セグメントがフレーム頭から鳴る)
            self.assertAlmostEqual(_wav_seconds(audio_path), sum(expected), places=1)


if __name__ == "__main__":
    unittest.main()


class RefinementTests(unittest.TestCase):
    """洗練②③ (2026-07-06 user GO): 数字ドン prehook + カード切替 pop SE。"""

    def test_prehook_frame_renders(self):
        from src.yt_shorts_render import render_prehook_frame
        from src.yt_shorts_topic import ShortsTopic

        t = ShortsTopic(player="泉口友汰", slug="izuguchi-yuta", label="連続試合安打",
                        value="7試合", note="", category="streak", as_of="2026-07-06",
                        title="t", hook="h")
        with TemporaryDirectory() as td:
            path = render_prehook_frame(t, Path(td))
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 10000)

    def test_prepend_silence_extends_duration(self):
        from src.yt_shorts_render import _prepend_silence

        with TemporaryDirectory() as td:
            src = Path(td) / "n.wav"
            _write_wav(src, 2.0)
            out = _prepend_silence(src, 0.7)
            self.assertAlmostEqual(_wav_seconds(out), 2.7, places=2)

    def test_pop_se_bounded(self):
        from src.yt_shorts_render import _pop_se_samples

        samples = _pop_se_samples(24000)
        self.assertLess(max(abs(v) for v in samples), 32768 * 0.3)
        self.assertLess(len(samples), 24000 // 2)

    def test_concat_with_se_keeps_length(self):
        import os
        from unittest.mock import patch as _patch

        with TemporaryDirectory() as td:
            base = Path(td)
            paths = []
            for i in range(2):
                p2 = base / f"s{i}.wav"
                _write_wav(p2, 1.0)
                paths.append(p2)
            with _patch.dict(os.environ, {"YT_SHORTS_SEGMENT_SE": "1"}):
                out = _concat_wavs_with_padding(paths, (2.0, 2.0), base / "o.wav")
            self.assertAlmostEqual(_wav_seconds(out), 4.0, places=2)
