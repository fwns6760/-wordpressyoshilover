import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.yt_shorts_render import DEFAULT_FRAME_DURATIONS, compose_video, render_frames, write_silent_wav
from src.yt_shorts_script import build_script
from src.yt_shorts_topic import ShortsTopic


def _topic() -> ShortsTopic:
    return ShortsTopic(
        player="泉口友汰",
        slug="izuguchi-yuta",
        label="連続試合安打",
        value="7試合",
        note="今季最長7試合",
        category="streak",
        as_of="2026-06-12",
        title="泉口友汰 連続試合安打7試合をデータで見る",
        hook="泉口友汰、連続試合安打7試合",
        priority=507,
        raw_item={"player": "泉口友汰", "label": "連続試合安打", "value": "7試合", "note": "今季最長7試合"},
    )


class YtShortsRenderTests(unittest.TestCase):
    def test_default_frame_durations_total_sixty_seconds(self):
        self.assertEqual(sum(DEFAULT_FRAME_DURATIONS), 60.0)

    def test_render_frames_creates_five_pngs(self):
        topic = _topic()
        script = build_script(topic)
        with tempfile.TemporaryDirectory() as tmp:
            frames = render_frames(topic, script, Path(tmp))

            self.assertEqual(len(frames), 5)
            self.assertTrue(all(path.exists() for path in frames))
            self.assertTrue(all(path.suffix == ".png" for path in frames))

    def test_write_silent_wav_creates_audio_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_silent_wav(Path(tmp) / "silent.wav", duration_seconds=1.0)

            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)

    def test_compose_video_invokes_ffmpeg_with_concat_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = []
            for idx in range(5):
                frame = root / f"frame_{idx}.png"
                frame.write_bytes(b"png")
                frames.append(frame)
            audio = root / "a.wav"
            audio.write_bytes(b"wav")

            with mock.patch("subprocess.run") as run:
                out = compose_video(tuple(frames), audio, root / "out.mp4", ffmpeg_bin="ffmpeg-test")

            self.assertEqual(out, root / "out.mp4")
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[0], "ffmpeg-test")
            self.assertIn("-f", cmd)
            self.assertIn("concat", cmd)


if __name__ == "__main__":
    unittest.main()
