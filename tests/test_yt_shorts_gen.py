import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from src.yt_shorts_gen import (
    _load_notable_data_from_json_inline,
    _mail_bodies,
    _player_image_url,
    _upload_artifacts,
    main,
    run,
)
from src.yt_shorts_render import RenderedShort
from src.yt_shorts_script import build_script
from src.yt_shorts_topic import ShortsTopic


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


def _notable_data_two_topics() -> dict[str, object]:
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
            },
            {
                "player": "岡本和真",
                "slug": "okamoto-kazuma",
                "label": "連続試合安打",
                "value": "5試合",
                "note": "復調を示す5試合",
                "category": "streak",
            },
        ],
    }


def _notable_data_three_topics() -> dict[str, object]:
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
            },
            {
                "player": "ダルベック",
                "slug": "dalbec",
                "label": "連続試合安打",
                "value": "3試合",
                "note": "今季最長6試合",
                "category": "streak",
            },
            {
                "player": "松本剛",
                "slug": "matsumoto-go",
                "label": "OPS",
                "value": ".780",
                "note": "直近1ヶ月",
                "category": "form",
            },
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
        duration_seconds=27.0,
        tts_mode="silent",
    )


def _topic() -> ShortsTopic:
    return ShortsTopic(
        player="泉口友汰",
        slug="izuguchi-yuta",
        label="連続試合安打",
        value="7試合",
        note="今季最長7試合",
        category="streak",
        as_of="2026-06-12",
        title="泉口友汰、連続試合安打7試合",
        hook="泉口友汰、7試合連続安打。",
        raw_item={"player": "泉口友汰"},
    )


class YtShortsGenTests(unittest.TestCase):
    def test_player_image_url_ignores_generic_article_images(self):
        topic = ShortsTopic(
            player="泉口友汰",
            slug="izuguchi-yuta",
            label="連続試合安打",
            value="7試合",
            note="今季最長7試合",
            category="streak",
            as_of="2026-06-12",
            title="泉口友汰、連続試合安打7試合",
            hook="泉口友汰、7試合連続安打。",
            raw_item={
                "featured_image_url": "https://example.com/scene.jpg",
                "image_url": "https://example.com/logo.jpg",
                "photo_url": "https://example.com/photo.jpg",
            },
        )

        with (
            mock.patch.dict("os.environ", {"YT_SHORTS_PLAYER_IMAGE_URL": ""}, clear=False),
            mock.patch("src.data_site_query.mapped_player_media_id", return_value=None) as mapped_media,
            mock.patch("src.data_site_query.find_player_featured_image_url") as find_url,
        ):
            url = _player_image_url(topic)

        self.assertEqual(url, "")
        mapped_media.assert_called_once_with("泉口友汰")
        find_url.assert_not_called()

    def test_player_image_url_uses_curated_media_only_when_player_is_mapped(self):
        topic = ShortsTopic(
            player="泉口友汰",
            slug="izuguchi-yuta",
            label="連続試合安打",
            value="7試合",
            note="今季最長7試合",
            category="streak",
            as_of="2026-06-12",
            title="泉口友汰、連続試合安打7試合",
            hook="泉口友汰、7試合連続安打。",
            raw_item={"featured_image_url": "https://example.com/scene.jpg"},
        )

        with (
            mock.patch.dict("os.environ", {"YT_SHORTS_PLAYER_IMAGE_URL": ""}, clear=False),
            mock.patch("src.data_site_query.mapped_player_media_id", return_value=66557),
            mock.patch(
                "src.data_site_query.find_player_featured_image_url",
                return_value="https://yoshilover.com/wp-content/uploads/player.jpg",
            ) as find_url,
        ):
            url = _player_image_url(topic)

        self.assertEqual(url, "https://yoshilover.com/wp-content/uploads/player.jpg")
        find_url.assert_called_once_with("泉口友汰")

    def test_upload_artifacts_continues_when_signed_url_fails(self):
        class FakeBlob:
            def __init__(self, name: str) -> None:
                self.name = name

            def upload_from_filename(self, *_args, **_kwargs):
                return None

            def upload_from_string(self, *_args, **_kwargs):
                return None

            def generate_signed_url(self, *_args, **_kwargs):
                raise AttributeError("no private key")

        class FakeBucket:
            def blob(self, name: str) -> FakeBlob:
                return FakeBlob(name)

        class FakeClient:
            def bucket(self, _name: str) -> FakeBucket:
                return FakeBucket()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic = _topic()
            script = build_script(topic)
            with mock.patch("src.yt_shorts_gen._gcs_client", return_value=FakeClient()):
                gcs_uri, signed_url = _upload_artifacts(
                    bucket_name="bucket",
                    run_id="run-1",
                    rendered=_rendered(root),
                    topic=topic,
                    script=script,
                )

        self.assertEqual(gcs_uri, "gs://bucket/yt_shorts/runs/run-1/short.mp4")
        self.assertEqual(signed_url, "")

    def test_mail_body_omits_mp4_button_when_signed_url_empty(self):
        topic = _topic()
        script = build_script(topic)

        text_body, html_body = _mail_bodies(
            topic,
            script,
            signed_url="",
            gcs_uri="gs://bucket/short.mp4",
            youtube_watch_url="https://www.youtube.com/watch?v=abc123_DEF-4",
        )

        self.assertIn("動画URL: (dry-run / no upload)", text_body)
        self.assertNotIn("MP4を開く", html_body)
        self.assertIn("YouTubeで確認", html_body)

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

    def test_live_ignore_daily_cap_excludes_previous_topic_and_renders_next(self):
        previous_topic_key = "yt_shorts|2026-06-12|泉口友汰|連続試合安打|7試合"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch(
                    "src.yt_shorts_gen._load_history",
                    return_value={
                        "status": "sent",
                        "topic_key": previous_topic_key,
                        "title": "泉口友汰 連続試合安打7試合をデータで見る",
                    },
                ),
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
                mock.patch(
                    "src.yt_shorts_gen._upload_artifacts",
                    return_value=("gs://bucket/run/short.mp4", ""),
                ),
                mock.patch("src.yt_shorts_gen._write_history"),
            ):
                result = run(
                    live=True,
                    notable_data=_notable_data_two_topics(),
                    output_dir=Path(tmp),
                    allow_silent_tts=True,
                    bucket_name="bucket",
                    send_mail=False,
                    ignore_daily_cap=True,
                )

            self.assertEqual(result.status, "ok")
            self.assertIn("岡本和真", result.title)
            self.assertEqual(result.reason, "")

    def test_cooldown_exhausted_falls_back_to_least_recently_used(self):
        # Both candidates were used recently, so the cooldown empties the pool.
        # The fallback must pick the least-recently-used player (岡本, offset 3)
        # rather than re-picking the higher-priority recent one (泉口, offset 1).
        used = {
            "2026-06-11": {
                "status": "sent",
                "player": "泉口友汰",
                "topic_key": "yt_shorts|2026-06-11|泉口友汰|連続試合安打|6試合",
            },
            "2026-06-09": {
                "status": "sent",
                "player": "岡本和真",
                "topic_key": "yt_shorts|2026-06-09|岡本和真|連続試合安打|4試合",
            },
        }

        def fake_history(_bucket, day):
            return used.get(day)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch("src.yt_shorts_gen._load_history", side_effect=fake_history),
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
                mock.patch(
                    "src.yt_shorts_gen._upload_artifacts",
                    return_value=("gs://bucket/run/short.mp4", ""),
                ),
                mock.patch("src.yt_shorts_gen._write_history"),
            ):
                result = run(
                    live=True,
                    notable_data=_notable_data_two_topics(),
                    output_dir=root,
                    allow_silent_tts=True,
                    bucket_name="bucket",
                    send_mail=False,
                    now=datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc),
                )

            self.assertEqual(result.status, "ok")
            self.assertIn("岡本和真", result.title)

    def test_target_player_selects_requested_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
            ):
                result = run(
                    live=False,
                    notable_data=_notable_data_three_topics(),
                    output_dir=Path(tmp),
                    allow_silent_tts=True,
                    send_mail=False,
                    target_players=["松本 剛"],
                )

            self.assertEqual(result.status, "ok")
            self.assertIn("松本剛", result.title)
            self.assertEqual(result.reason, "")

    def test_target_player_loads_wider_notable_data_from_repo(self):
        items = [
            {
                "player": f"候補{idx}",
                "slug": f"candidate-{idx}",
                "label": "OPS",
                "value": f".{700 + idx}",
                "note": "通常候補",
                "category": "form",
            }
            for idx in range(20)
        ]
        items.append(
            {
                "player": "浦田俊輔",
                "slug": "urata-shunsuke",
                "label": "二塁打",
                "value": "3本",
                "note": "直近データで候補化",
                "category": "form",
            }
        )

        def fake_load(limit: int = 16) -> dict[str, object]:
            self.assertGreaterEqual(limit, 80)
            return {"as_of": "2026-06-15", "items": items[:limit]}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch("src.yt_shorts_gen._load_notable_data_from_repo", side_effect=fake_load),
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
            ):
                result = run(
                    live=False,
                    output_dir=Path(tmp),
                    allow_silent_tts=True,
                    send_mail=False,
                    target_players=["浦田俊輔"],
                )

            self.assertEqual(result.status, "ok")
            self.assertIn("浦田俊輔", result.title)
            self.assertEqual(result.reason, "")

    def test_exclude_players_skips_named_players(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
            ):
                result = run(
                    live=False,
                    notable_data=_notable_data_three_topics(),
                    output_dir=Path(tmp),
                    allow_silent_tts=True,
                    send_mail=False,
                    exclude_players=["泉口友汰", "ダルベック"],
                )

            self.assertEqual(result.status, "ok")
            self.assertIn("松本剛", result.title)
            self.assertEqual(result.reason, "")

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

    def test_load_notable_data_from_json_inline_requires_object(self):
        payload = json.dumps(_notable_data(), ensure_ascii=False)

        data = _load_notable_data_from_json_inline(payload)

        self.assertEqual(data["as_of"], "2026-06-12")
        with self.assertRaisesRegex(ValueError, "must be an object"):
            _load_notable_data_from_json_inline("[]")

    def test_main_accepts_topic_json_inline(self):
        payload = json.dumps(
            {
                "as_of": "2026-06-15",
                "items": [
                    {
                        "player": "浦田俊輔",
                        "slug": "urata-shunsuke",
                        "label": "対DeNA打率",
                        "value": ".464",
                        "note": "対DeNAは13安打/28打数・3打点。シーズン打率.265から+.199の対戦別split。",
                        "category": "form",
                    }
                ],
            },
            ensure_ascii=False,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                mock.patch("src.yt_shorts_gen.render_short", return_value=_rendered(root)),
            ):
                rc = main(
                    [
                        "--topic-json-inline",
                        payload,
                        "--output-dir",
                        str(root),
                        "--allow-silent-tts",
                        "--no-mail",
                    ]
                )

        self.assertEqual(rc, 0)

    def test_main_rejects_topic_json_and_inline_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "topic.json"
            fixture.write_text(json.dumps(_notable_data(), ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(SystemExit) as cm:
                main(
                    [
                        "--topic-json",
                        str(fixture),
                        "--topic-json-inline",
                        json.dumps(_notable_data(), ensure_ascii=False),
                        "--no-mail",
                    ]
                )

        self.assertNotEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
