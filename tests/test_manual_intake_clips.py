"""Tests for the 🎬 動画引用RT即応アプリ (/clips、2026-07-19).

Covers:
- GET /clips: ページ配信 (intent 直起動リンク / API 不使用)
- GET /clip-candidates: token gate (403) / happy path (ビルダー patch)
- _build_clip_candidates: gather_fn 注入で video_radar 素材 → 候補 dict 変換
"""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from src import manual_intake_service as svc


def _invoke(method: str, path: str, body: bytes = b"", headers: dict | None = None) -> tuple[int, bytes]:
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
    status = int(head.split(b"\r\n")[0].decode("iso-8859-1").split(" ", 2)[1])
    return status, body_bytes


class ClipsPageTests(unittest.TestCase):
    def test_clips_page_served_with_intent_link(self):
        status, body = _invoke("GET", "/clips")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        # 投稿は x.com/intent/post 1タップ (API 直投稿は使わない、2026-07-19)
        self.assertIn("x.com/intent/post", text)
        self.assertIn("引用RT", text)
        self.assertNotIn("/x-post-direct", text)

    def test_top_page_nav_links_clips(self):
        status, body = _invoke("GET", "/?token=")
        self.assertEqual(status, 200)
        self.assertIn('href="/clips"', body.decode("utf-8"))


class ClipCandidatesEndpointTests(unittest.TestCase):
    def test_token_mismatch_is_403(self):
        with patch.dict("os.environ", {svc.TOKEN_ENV: "secret-token"}):
            status, body = _invoke("GET", "/clip-candidates?token=wrong")
        self.assertEqual(status, 403)
        self.assertFalse(json.loads(body)["ok"])

    def test_happy_path_returns_builder_payload(self):
        payload = {"ok": True, "away": True, "handles": ["DAZNJPNBaseball"], "clips": []}
        with patch.dict("os.environ", {svc.TOKEN_ENV: "secret-token"}), patch.object(
            svc, "_build_clip_candidates", return_value=payload
        ):
            status, body = _invoke("GET", "/clip-candidates?token=secret-token")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), payload)


class BuildClipCandidatesTests(unittest.TestCase):
    def test_gather_posts_become_clip_cards(self):
        posts = [
            {
                "text": "10球目を捉えた 泉口友汰 値千金の5号ソロ ⚾️巨人×中日",
                "url": "https://x.com/DAZNJPNBaseball/status/1",
                "handle": "DAZNJPNBaseball",
                "player": "泉口友汰",
                "score": 3,
                "type_tag": "好プレー・反応",
                "has_video": True,
                "has_image": False,
            }
        ]
        # ビジター判定は NPB 日程 fetch (network) を踏まないよう cache を prefill
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from src import x_post_mail_lane as lane

        now = datetime(2026, 7, 19, 19, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        with patch.dict(lane._today_away_cache, {"2026-07-19": True}, clear=False):
            out = svc._build_clip_candidates(now, gather_fn=lambda **kw: posts)
        self.assertTrue(out["ok"])
        self.assertIs(out["away"], True)
        # ビジター戦 → 日テレ除外 / DAZN は残る (game_buzz_handles 共用)
        self.assertNotIn("ntv_baseball", out["handles"])
        self.assertIn("DAZNJPNBaseball", out["handles"])
        self.assertEqual(len(out["clips"]), 1)
        clip = out["clips"][0]
        self.assertEqual(clip["url"], "https://x.com/DAZNJPNBaseball/status/1")
        self.assertEqual(clip["player"], "泉口友汰")
        # 選手名ありは定型コメントが付く (LLM なし)
        self.assertTrue(clip["comment"])

    def test_playerless_clip_kept_without_comment(self):
        posts = [
            {
                "text": "劇的サヨナラの瞬間をもう一度",
                "url": "https://x.com/ntv_baseball/status/2",
                "handle": "ntv_baseball",
                "player": "",
                "score": 1,
                "type_tag": "巨人の話題",
                "has_video": True,
                "has_image": False,
            }
        ]
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from src import x_post_mail_lane as lane

        now = datetime(2026, 7, 19, 19, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        with patch.dict(lane._today_away_cache, {"2026-07-19": False}, clear=False):
            out = svc._build_clip_candidates(now, gather_fn=lambda **kw: posts)
        self.assertEqual(len(out["clips"]), 1)
        self.assertEqual(out["clips"][0]["comment"], "")
        self.assertIn("ntv_baseball", out["handles"])


if __name__ == "__main__":
    unittest.main()
