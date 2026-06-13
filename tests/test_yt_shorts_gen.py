from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from src.yt_shorts_gen import run
from src.yt_shorts_render import RenderedShort


def _notable_data() -> dict[str, object]:
    return {
        "as_of": "2026-06-12",
        "items": [
            {
                "player": "泉口友汰",
                "slug": "izuguchi-yuta",
                "label": "連続試合安打",
                "value": "7試合",
                "note": "今季最長7試合",
                "category": "streak",
            }
        ],
    }


def _rendered(root: Path) -> RenderedShort:
    video = root / "short.mp4"
    audio = root / "narration.wav"
    metadata = root / "metadata.json"
    frames = tuple(root / f"frame_{idx}.png" for idx in range(5))
    for path in (video, audio, metadata, *frames):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    return RenderedShort(
        video_path=video,
        audio_path=audio,
        frame_paths=frames,
        metadata_path=metadata,
        duration_seconds=60.0,
        tts_mode="silent",
    )


class YtShortsGenTests(unittest.TestCase):
    def test_dry_run_renders_and_sends_dry_run_mail_without_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)) as render_short,
                mock.patch(
                    "src.yt_shorts_gen.bridge_send",
                    return_value=SimpleNamespace(status="dry_run"),
                ) as bridge_send,
                mock.patch("src.yt_shorts_gen._upload_artifacts") as upload_artifacts,
            ):
                result = run(
                    live=False,
                    notable_data=_notable_data(),
                    output_dir=root,
                    allow_silent_tts=True,
                    now=datetime(2026, 6, 13, tzinfo=timezone.utc),
                )

            self.assertEqual(result.status, "ok")
            self.assertTrue(result.dry_run)
            self.assertEqual(result.mail_status, "dry_run")
            self.assertEqual(result.tts_mode, "silent")
            render_short.assert_called_once()
            bridge_send.assert_called_once()
            upload_artifacts.assert_not_called()

    def test_live_requires_bucket_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("src.yt_shorts_gen.render_short") as render_short:
                with self.assertRaisesRegex(RuntimeError, "GCS_BUCKET"):
                    run(
                        live=True,
                        notable_data=_notable_data(),
                        output_dir=Path(tmp),
                        allow_silent_tts=True,
                        bucket_name="",
                    )

            render_short.assert_not_called()

    def test_live_daily_cap_skips_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch(
                    "src.yt_shorts_gen._load_history",
                    return_value={
                        "status": "sent",
                        "topic_key": "already",
                        "title": "already sent",
                        "gcs_uri": "gs://bucket/old.mp4",
                    },
                ),
                mock.patch("src.yt_shorts_gen.render_short") as render_short,
            ):
                result = run(
                    live=True,
                    notable_data=_notable_data(),
                    output_dir=Path(tmp),
                    allow_silent_tts=True,
                    bucket_name="bucket",
                    send_mail=False,
                )

            self.assertEqual(result.status, "skipped")
            self.assertEqual(result.reason, "daily_cap_already_used")
            self.assertEqual(result.title, "already sent")
            render_short.assert_not_called()

    def test_live_no_topic_sends_failure_mail(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch("src.yt_shorts_gen._load_history", return_value=None),
                mock.patch("src.yt_shorts_gen._failure_mail", return_value="sent") as failure_mail,
                mock.patch("src.yt_shorts_gen.render_short") as render_short,
            ):
                result = run(
                    live=True,
                    notable_data={"as_of": "2026-06-12", "items": []},
                    output_dir=Path(tmp),
                    bucket_name="bucket",
                    send_mail=True,
                )

            self.assertEqual(result.status, "no_topic")
            self.assertEqual(result.reason, "empty_notable_data")
            failure_mail.assert_called_once()
            render_short.assert_not_called()

    def test_live_records_uploaded_history_before_mail_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch("src.yt_shorts_gen._load_history", return_value=None),
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
                mock.patch(
                    "src.yt_shorts_gen._upload_artifacts",
                    return_value=("gs://bucket/run/short.mp4", "https://signed.example/short.mp4"),
                ),
                mock.patch("src.yt_shorts_gen.send_approval_mail", return_value="sent"),
                mock.patch("src.yt_shorts_gen._write_history") as write_history,
            ):
                result = run(
                    live=True,
                    notable_data=_notable_data(),
                    output_dir=root,
                    allow_silent_tts=True,
                    bucket_name="bucket",
                )

            self.assertEqual(result.status, "ok")
            self.assertEqual(result.gcs_uri, "gs://bucket/run/short.mp4")
            self.assertGreaterEqual(write_history.call_count, 2)
            first_payload = write_history.call_args_list[0].args[2]
            final_payload = write_history.call_args_list[-1].args[2]
            self.assertEqual(first_payload["status"], "uploaded")
            self.assertEqual(final_payload["status"], "sent")

    def test_live_keeps_uploaded_history_if_mail_send_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch("src.yt_shorts_gen._load_history", return_value=None),
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
                mock.patch(
                    "src.yt_shorts_gen._upload_artifacts",
                    return_value=("gs://bucket/run/short.mp4", "https://signed.example/short.mp4"),
                ),
                mock.patch("src.yt_shorts_gen.send_approval_mail", side_effect=RuntimeError("smtp down")),
                mock.patch("src.yt_shorts_gen._write_history") as write_history,
            ):
                with self.assertRaisesRegex(RuntimeError, "smtp down"):
                    run(
                        live=True,
                        notable_data=_notable_data(),
                        output_dir=root,
                        allow_silent_tts=True,
                        bucket_name="bucket",
                    )

            self.assertEqual(write_history.call_count, 1)
            self.assertEqual(write_history.call_args.args[2]["status"], "uploaded")

    def test_live_can_upload_private_youtube_before_mail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            youtube_result = SimpleNamespace(
                video_id="abc123_DEF-4",
                privacy_status="private",
                watch_url="https://www.youtube.com/watch?v=abc123_DEF-4",
                studio_url="https://studio.youtube.com/video/abc123_DEF-4/edit",
            )
            with (
                mock.patch("src.yt_shorts_gen._load_history", return_value=None),
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
                mock.patch(
                    "src.yt_shorts_gen._upload_artifacts",
                    return_value=("gs://bucket/run/short.mp4", "https://signed.example/short.mp4"),
                ),
                mock.patch("src.yt_shorts_gen.upload_private_video", return_value=youtube_result) as upload_private,
                mock.patch(
                    "src.yt_shorts_gen.build_yt_shorts_publish_url",
                    return_value="https://fetcher.example.com/yt-shorts-publish?video_id=abc123_DEF-4&token=t",
                ) as build_url,
                mock.patch("src.yt_shorts_gen.send_approval_mail", return_value="sent") as send_mail,
                mock.patch("src.yt_shorts_gen._write_history") as write_history,
            ):
                result = run(
                    live=True,
                    notable_data=_notable_data(),
                    output_dir=root,
                    allow_silent_tts=True,
                    bucket_name="bucket",
                    youtube_private_upload=True,
                )

            self.assertEqual(result.youtube_video_id, "abc123_DEF-4")
            self.assertEqual(result.youtube_upload_status, "private")
            upload_private.assert_called_once()
            build_url.assert_called_once()
            mail_kwargs = send_mail.call_args.kwargs
            self.assertEqual(mail_kwargs["youtube_video_id"], "abc123_DEF-4")
            self.assertIn("/yt-shorts-publish?", mail_kwargs["youtube_publish_url"])
            first_payload = write_history.call_args_list[0].args[2]
            self.assertEqual(first_payload["status"], "youtube_private_uploaded")
            self.assertEqual(first_payload["youtube_video_id"], "abc123_DEF-4")


if __name__ == "__main__":
    unittest.main()
