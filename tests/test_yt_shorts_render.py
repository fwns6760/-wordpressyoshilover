import tempfile
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from src.yt_shorts_render import (
    DEFAULT_DYNAMIC_AUDIO_FILTER,
    DEFAULT_FRAME_DURATIONS,
    _apply_voice_style,
    OPENING_PLAYER_VISUAL_BOX,
    STANDARD_PLAYER_VISUAL_BOX,
    compose_video,
    render_frames,
    write_pop_bgm_wav,
    write_silent_wav,
)
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
    def test_default_frame_durations_target_twenty_seven_seconds(self):
        self.assertEqual(sum(DEFAULT_FRAME_DURATIONS), 27.0)

    def test_render_frames_creates_five_pngs(self):
        topic = _topic()
        script = build_script(topic)
        with tempfile.TemporaryDirectory() as tmp:
            frames = render_frames(topic, script, Path(tmp))

            self.assertEqual(len(frames), 5)
            self.assertTrue(all(path.exists() for path in frames))
            self.assertTrue(all(path.suffix == ".png" for path in frames))

    def test_render_frames_uses_player_image_url_on_every_frame_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "player.png"
            Image.new("RGB", (320, 240), "#12aa44").save(photo)
            topic = ShortsTopic(
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
                raw_item={"player_image_url": str(photo)},
            )
            script = build_script(topic)

            frames = render_frames(topic, script, root)

            self.assertEqual(len(frames), 5)
            sample_points = (
                (180, 420),
                (180, 420),
                (180, 420),
                (180, 420),
                (180, 420),
            )
            for frame_path, point in zip(frames, sample_points):
                with Image.open(frame_path) as frame:
                    red, green, blue = frame.getpixel(point)
                self.assertGreater(green, red, frame_path)
                self.assertGreater(green, blue, frame_path)

    def test_first_frame_uses_larger_player_visual_than_following_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "player.png"
            Image.new("RGB", (320, 240), "#12aa44").save(photo)
            topic = ShortsTopic(
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
                raw_item={"player_image_url": str(photo)},
            )
            script = build_script(topic)

            frames = render_frames(topic, script, root)

            self.assertGreater(OPENING_PLAYER_VISUAL_BOX[2], STANDARD_PLAYER_VISUAL_BOX[2])
            self.assertGreater(OPENING_PLAYER_VISUAL_BOX[3], STANDARD_PLAYER_VISUAL_BOX[3])
            with Image.open(frames[0]) as first, Image.open(frames[1]) as second:
                first_red, first_green, first_blue = first.getpixel((12, 620))
                second_red, second_green, second_blue = second.getpixel((12, 620))
            self.assertGreater(first_green, first_red)
            self.assertGreater(first_green, first_blue)
            self.assertFalse(second_green > second_red and second_green > second_blue)

    def test_generic_article_image_fields_are_not_used_as_player_photo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            photo = root / "article-scene.png"
            Image.new("RGB", (320, 240), "#12aa44").save(photo)
            topic = ShortsTopic(
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
                raw_item={"featured_image_url": str(photo), "image_url": str(photo), "photo_url": str(photo)},
            )
            script = build_script(topic)

            frames = render_frames(topic, script, root)

            with Image.open(frames[0]) as frame:
                red, green, blue = frame.getpixel((180, 420))
            self.assertFalse(green > red and green > blue)

    def test_write_silent_wav_creates_audio_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_silent_wav(Path(tmp) / "silent.wav", duration_seconds=1.0)

            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)

    def test_write_pop_bgm_wav_creates_audio_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_pop_bgm_wav(Path(tmp) / "bgm.wav", duration_seconds=1.0)

            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 10000)

    def test_compose_video_invokes_ffmpeg_with_motion_inputs(self):
        # Motion path: each still is a -loop input run through a zoompan
        # (Ken Burns) chain instead of a held concat-demuxer frame.
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
            self.assertEqual(cmd.count("-loop"), 5)
            self.assertNotIn("-shortest", cmd)
            self.assertIn("-filter_complex", cmd)
            filter_complex = cmd[cmd.index("-filter_complex") + 1]
            self.assertIn("zoompan", filter_complex)
            self.assertIn("concat=n=5", filter_complex)
            self.assertEqual(cmd[cmd.index("-map") + 1], "[vout]")
            self.assertIn("-t", cmd)
            # First -t values are per-loop input durations; the output -t is last.
            output_t_index = len(cmd) - 1 - cmd[::-1].index("-t")
            self.assertEqual(cmd[output_t_index + 1], "27.000")
            self.assertEqual(cmd[cmd.index("-preset") + 1], "veryfast")
            self.assertEqual(cmd[cmd.index("-threads") + 1], "1")

    def test_compose_video_applies_audio_filter_when_supplied(self):
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
                compose_video(
                    tuple(frames),
                    audio,
                    root / "out.mp4",
                    ffmpeg_bin="ffmpeg-test",
                    audio_filter=DEFAULT_DYNAMIC_AUDIO_FILTER,
                )

            cmd = run.call_args.args[0]
            # Audio now rides the same filter_complex graph as the video.
            self.assertNotIn("-af", cmd)
            filter_complex = cmd[cmd.index("-filter_complex") + 1]
            self.assertIn(f"[5:a]{DEFAULT_DYNAMIC_AUDIO_FILTER},apad=whole_dur=27.000[aout]", filter_complex)
            self.assertEqual(cmd[cmd.index("-map", cmd.index("-map") + 1) + 1], "[aout]")

    def test_compose_video_mixes_bgm_with_narration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = []
            for idx in range(5):
                frame = root / f"frame_{idx}.png"
                frame.write_bytes(b"png")
                frames.append(frame)
            audio = root / "a.wav"
            audio.write_bytes(b"wav")
            bgm = root / "bgm.wav"
            bgm.write_bytes(b"bgm")

            with mock.patch("subprocess.run") as run:
                compose_video(
                    tuple(frames),
                    audio,
                    root / "out.mp4",
                    ffmpeg_bin="ffmpeg-test",
                    audio_filter=DEFAULT_DYNAMIC_AUDIO_FILTER,
                    bgm_path=bgm,
                )

            cmd = run.call_args.args[0]
            self.assertIn(str(bgm), cmd)
            self.assertIn("-filter_complex", cmd)
            self.assertIn("amix=inputs=2", cmd[cmd.index("-filter_complex") + 1])
            self.assertIn("duration=longest", cmd[cmd.index("-filter_complex") + 1])
            self.assertIn("apad=whole_dur=27.000", cmd[cmd.index("-filter_complex") + 1])
            self.assertIn("-map", cmd)
            self.assertNotIn("-af", cmd)

    def test_compose_video_keeps_full_frame_duration_when_audio_is_shorter(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg/ffprobe not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = []
            for idx in range(5):
                frame = root / f"frame_{idx}.png"
                Image.new("RGB", (320, 480), (20 * idx, 80, 120)).save(frame)
                frames.append(frame)
            audio = write_silent_wav(root / "short.wav", duration_seconds=0.2)
            out = compose_video(tuple(frames), audio, root / "out.mp4", durations=(0.25, 0.25, 0.25, 0.25, 0.25))

            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    str(out),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertGreaterEqual(float(probe.stdout.strip()), 1.2)

    def test_apply_voice_style_sets_dynamic_voicevox_params(self):
        query = {
            "speedScale": 1.0,
            "intonationScale": 1.0,
            "volumeScale": 1.0,
            "prePhonemeLength": 0.1,
            "postPhonemeLength": 0.1,
        }

        styled = _apply_voice_style(query, style="dynamic")

        self.assertEqual(styled["speedScale"], 1.12)
        self.assertEqual(styled["intonationScale"], 1.22)
        self.assertEqual(styled["volumeScale"], 1.08)
        self.assertEqual(styled["prePhonemeLength"], 0.06)
        self.assertEqual(styled["postPhonemeLength"], 0.08)

    def test_apply_voice_style_plain_keeps_query(self):
        query = {"speedScale": 1.0}

        self.assertIs(_apply_voice_style(query, style="plain"), query)
        self.assertEqual(query["speedScale"], 1.0)


class FitDurationsToAudioTests(unittest.TestCase):
    def test_short_audio_keeps_base_duration(self):
        from src.yt_shorts_render import _fit_durations_to_audio

        self.assertEqual(
            _fit_durations_to_audio(DEFAULT_FRAME_DURATIONS, 20.0), DEFAULT_FRAME_DURATIONS
        )

    def test_long_audio_stretches_to_cover_narration(self):
        from src.yt_shorts_render import _fit_durations_to_audio

        out = _fit_durations_to_audio(DEFAULT_FRAME_DURATIONS, 34.0)
        self.assertEqual(len(out), len(DEFAULT_FRAME_DURATIONS))
        self.assertGreaterEqual(sum(out), 34.0)

    def test_pathological_audio_is_capped(self):
        from src.yt_shorts_render import _fit_durations_to_audio, MAX_SHORT_SECONDS

        out = _fit_durations_to_audio(DEFAULT_FRAME_DURATIONS, 200.0)
        self.assertLessEqual(sum(out), MAX_SHORT_SECONDS + 0.01)


if __name__ == "__main__":
    unittest.main()
