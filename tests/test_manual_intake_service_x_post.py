"""Tests for the 346 X-post endpoints added to manual_intake_service.

Covers:
- GET /x-post-draft: happy path, empty question (400), unresolved question
- POST /x-post-direct: happy path (X API mocked), empty text (400), too long
  text (400), token mismatch (403), X API failure (502), env missing (503)
- Regression: existing /manual-intake POST unaffected.
"""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from src import manual_intake_service as svc


def _invoke(method: str, path: str, body: bytes = b"", headers: dict | None = None) -> tuple[int, dict, bytes]:
    headers = headers or {}
    handler_cls = svc.build_handler()

    class _BoundHandler(handler_cls):
        def __init__(self):
            self.rfile = io.BytesIO(body)
            self.wfile = io.BytesIO()
            self.command = method
            self.path = path
            self.request_version = "HTTP/1.1"
            self.requestline = f"{method} {path} HTTP/1.1"
            self.client_address = ("127.0.0.1", 12345)
            from http.client import HTTPMessage

            msg = HTTPMessage()
            for k, v in headers.items():
                msg[k] = v
            self.headers = msg

        def log_message(self, *_a, **_kw):
            pass

        def log_request(self, *_a, **_kw):
            pass

        def address_string(self):
            return "127.0.0.1"

    h = _BoundHandler()
    if method == "GET":
        h.do_GET()
    else:
        h.do_POST()
    raw = h.wfile.getvalue()
    head, _, body_bytes = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status_line = lines[0].decode("iso-8859-1")
    status = int(status_line.split(" ", 2)[1])
    resp_headers: dict[str, str] = {}
    for line in lines[1:]:
        if b":" in line:
            k, _, v = line.partition(b":")
            resp_headers[k.decode("iso-8859-1").strip()] = v.decode("iso-8859-1").strip()
    return status, resp_headers, body_bytes


def _json(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))


class XPostDraftEndpointTests(unittest.TestCase):
    def test_empty_question_returns_400(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            status, _h, body = _invoke("GET", "/x-post-draft?q=")
        self.assertEqual(status, 400, msg=body)
        self.assertEqual(_json(body).get("reason"), "empty_question")

    def test_happy_path_returns_draft_text(self) -> None:
        fake_rank = {
            "ok": True,
            "rows": [
                {
                    "rank": 1,
                    "total": 50,
                    "player_canonical": "佐藤輝明",
                    "team_code": "阪神",
                    "metric_value": 0.945,
                    "sample_size": 100,
                },
                {
                    "rank": 2,
                    "total": 50,
                    "player_canonical": "岡本和真",
                    "team_code": "巨人",
                    "metric_value": 0.921,
                    "sample_size": 110,
                },
            ],
            "count": 2,
            "total": 50,
            "focus_player": None,
        }
        with patch("src.manual_intake_service.miq.ensure_local_db"), patch(
            "src.manual_intake_service.miq.query_rank", return_value=fake_rank
        ):
            status, _h, body = _invoke("GET", "/x-post-draft?q=OPS%2010%E4%BD%8D")
        self.assertEqual(status, 200, msg=body)
        payload = _json(body)
        self.assertTrue(payload.get("ok"), msg=payload)
        self.assertIn("draft_text", payload)
        self.assertIn("OPS", payload["draft_text"])
        # 418 case B: Giants marker は `🟧巨人🟧` (旧 `← 巨人` から更新)
        self.assertIn("🟧巨人🟧", payload["draft_text"])
        self.assertGreater(payload.get("char_count", 0), 0)

    def test_metric_not_detected_returns_200_with_diagnostic(self) -> None:
        with patch("src.manual_intake_service.miq.ensure_local_db"):
            status, _h, body = _invoke(
                "GET",
                "/x-post-draft?q=" + "%E3%81%82%E3%81%82%E3%81%82",  # 「あああ」
            )
        # Endpoint returns 200 with ok=False + parsed so the UI can guide.
        self.assertEqual(status, 200, msg=body)
        payload = _json(body)
        self.assertFalse(payload.get("ok"))
        self.assertIn(payload.get("reason"), {"metric_not_detected", "unresolved_fields"})


class XPostDirectEndpointTests(unittest.TestCase):
    def test_empty_text_returns_400(self) -> None:
        body = json.dumps({"text": ""}).encode("utf-8")
        status, _h, raw = _invoke(
            "POST",
            "/x-post-direct",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        self.assertEqual(status, 400, msg=raw)
        self.assertEqual(_json(raw).get("reason"), "empty_text")

    def test_too_long_text_returns_400(self) -> None:
        # 2026-07-07 Premium 長文化: ゲートは 900 字
        body = json.dumps({"text": "a" * 901}).encode("utf-8")
        status, _h, raw = _invoke(
            "POST",
            "/x-post-direct",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        self.assertEqual(status, 400, msg=raw)
        self.assertEqual(_json(raw).get("reason"), "text_too_long")

    def test_happy_path_calls_create_tweet(self) -> None:
        fake_client = MagicMock()
        fake_client.create_tweet.return_value = MagicMock(data={"id": "1234567890"})
        body = json.dumps({"text": "テスト投稿"}).encode("utf-8")
        with patch("src.x_api_client.get_client", return_value=fake_client):
            status, _h, raw = _invoke(
                "POST",
                "/x-post-direct",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
        self.assertEqual(status, 200, msg=raw)
        payload = _json(raw)
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("tweet_id"), "1234567890")
        fake_client.create_tweet.assert_called_once_with(text="テスト投稿")

    def test_token_mismatch_returns_403(self) -> None:
        body = json.dumps({"text": "テスト"}).encode("utf-8")
        with patch.dict("os.environ", {"MANUAL_INTAKE_TOKEN": "expected"}, clear=False):
            status, _h, raw = _invoke(
                "POST",
                "/x-post-direct",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "X-Manual-Intake-Token": "wrong",
                },
            )
        self.assertEqual(status, 403, msg=raw)
        self.assertEqual(_json(raw).get("reason"), "forbidden")

    def test_x_api_failure_returns_502(self) -> None:
        fake_client = MagicMock()
        fake_client.create_tweet.side_effect = RuntimeError("rate limit")
        body = json.dumps({"text": "テスト投稿"}).encode("utf-8")
        with patch("src.x_api_client.get_client", return_value=fake_client):
            status, _h, raw = _invoke(
                "POST",
                "/x-post-direct",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
        self.assertEqual(status, 502, msg=raw)
        self.assertIn("x_api_error", _json(raw).get("reason", ""))

    def test_env_missing_returns_503(self) -> None:
        # x_api_client.get_client() raises KeyError when X_API_KEY etc. are
        # absent. We simulate by patching get_client to raise KeyError.
        def _raise_keyerror():
            raise KeyError("X_API_KEY")

        body = json.dumps({"text": "テスト投稿"}).encode("utf-8")
        with patch("src.x_api_client.get_client", side_effect=_raise_keyerror):
            status, _h, raw = _invoke(
                "POST",
                "/x-post-direct",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
        self.assertEqual(status, 503, msg=raw)
        self.assertIn("env_missing", _json(raw).get("reason", ""))


class ExistingManualIntakeRegressionTests(unittest.TestCase):
    """346 must not change /manual-intake auth / response semantics."""

    def test_post_manual_intake_still_routes_to_existing_handler(self) -> None:
        # An empty body POST to /manual-intake without token should still
        # behave like before (400 missing_url or similar). We only verify
        # the response is NOT 404 (i.e. the route is still wired).
        status, _h, _raw = _invoke(
            "POST",
            "/manual-intake",
            body=b"",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertNotEqual(status, 404)

    def test_unknown_post_path_still_404(self) -> None:
        status, _h, raw = _invoke(
            "POST",
            "/some-random-unknown-path",
            body=b"",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 404)
        self.assertEqual(_json(raw).get("reason"), "not_found")


if __name__ == "__main__":
    unittest.main()
