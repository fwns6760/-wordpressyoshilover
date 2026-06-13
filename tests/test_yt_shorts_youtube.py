import json
from pathlib import Path
import tempfile
import unittest

from src.yt_shorts_youtube import (
    YouTubeOAuthConfig,
    refresh_access_token,
    set_video_privacy,
    upload_private_video,
)


class FakeResponse:
    def __init__(self, payload=None, *, headers=None, status_code=200, text=""):
        self._payload = payload or {}
        self.headers = headers or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        if "oauth2.googleapis.com" in url:
            return FakeResponse({"access_token": "access-token"})
        return FakeResponse(headers={"Location": "https://upload.example/session"})

    def put(self, url, **kwargs):
        self.calls.append(("put", url, kwargs))
        if "upload.example" in url:
            return FakeResponse({"id": "abc123_DEF-4", "status": {"privacyStatus": "private"}})
        return FakeResponse({"id": "abc123_DEF-4", "status": {"privacyStatus": "public"}})

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return FakeResponse(
            {
                "items": [
                    {
                        "id": "abc123_DEF-4",
                        "status": {
                            "privacyStatus": "private",
                            "selfDeclaredMadeForKids": False,
                            "containsSyntheticMedia": True,
                            "uploadStatus": "processed",
                        },
                    }
                ]
            }
        )


def _config() -> YouTubeOAuthConfig:
    return YouTubeOAuthConfig(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
    )


class YtShortsYoutubeTests(unittest.TestCase):
    def test_refresh_access_token_posts_refresh_grant(self):
        session = FakeSession()

        token = refresh_access_token(_config(), session=session)

        self.assertEqual(token, "access-token")
        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "post")
        self.assertIn("oauth2.googleapis.com", url)
        self.assertEqual(kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(kwargs["data"]["refresh_token"], "refresh-token")

    def test_upload_private_video_uses_resumable_upload(self):
        session = FakeSession()
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "short.mp4"
            video.write_bytes(b"video")

            result = upload_private_video(
                video,
                title="title",
                description="description",
                tags=("巨人", "shorts"),
                config=_config(),
                session=session,
            )

        self.assertEqual(result.video_id, "abc123_DEF-4")
        self.assertEqual(result.privacy_status, "private")
        post_call = session.calls[1]
        self.assertEqual(post_call[0], "post")
        self.assertEqual(post_call[2]["params"]["uploadType"], "resumable")
        body = json.loads(post_call[2]["data"].decode("utf-8"))
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["containsSyntheticMedia"], True)
        self.assertEqual(body["snippet"]["categoryId"], "17")
        self.assertEqual(session.calls[2][0], "put")
        self.assertEqual(session.calls[2][1], "https://upload.example/session")

    def test_set_video_privacy_preserves_settable_status_only(self):
        session = FakeSession()

        result = set_video_privacy(
            "abc123_DEF-4",
            "public",
            config=_config(),
            session=session,
        )

        self.assertEqual(result.privacy_status, "public")
        update_call = session.calls[-1]
        self.assertEqual(update_call[0], "put")
        body = json.loads(update_call[2]["data"].decode("utf-8"))
        self.assertEqual(body["id"], "abc123_DEF-4")
        self.assertEqual(body["status"]["privacyStatus"], "public")
        self.assertEqual(body["status"]["selfDeclaredMadeForKids"], False)
        self.assertEqual(body["status"]["containsSyntheticMedia"], True)
        self.assertNotIn("uploadStatus", body["status"])


if __name__ == "__main__":
    unittest.main()
