"""Tests for 記事X共有 (おりポス+リプ) — manual_intake_x_share + service endpoints.

2026-07-06 user GO「Xまで共有でおりポスとリプまでつくって」:
- x_weighted_len: CJK=2 / ASCII=1 / URL=23 の weighted 計算
- classify_share_type: comment / data / news の型判定
- build_share_drafts: LLM なし fallback (URL はリプ側のみ)
- post_thread: おりポス (media 付き) → in_reply_to リプの連続投稿 (X API mock)
- endpoints: /x-share-recent, /x-share-draft, /x-share-thread
"""

from __future__ import annotations

import io
import json
import types
import unittest
from unittest.mock import MagicMock, patch

from src import manual_intake_x_share as xshare


class XWeightedLenTests(unittest.TestCase):
    def test_ascii_counts_one(self):
        self.assertEqual(xshare.x_weighted_len("abc 123"), 7)

    def test_cjk_counts_two(self):
        self.assertEqual(xshare.x_weighted_len("巨人"), 4)

    def test_url_counts_23(self):
        self.assertEqual(
            xshare.x_weighted_len("見て https://yoshilover.com/archives/1234"),
            2 + 2 + 1 + 23,
        )


class ClassifyShareTypeTests(unittest.TestCase):
    def test_comment_article(self):
        t = xshare.classify_share_type(
            "井上温大がサインへの考えを語る",
            "井上温大は『キャッチャーの意図をくみ取って投げるのが大事』とコメントした。",
        )
        self.assertEqual(t, "comment")

    def test_data_article(self):
        t = xshare.classify_share_type(
            "井上温大が20回1/3連続無失点", "節目の記録をチームトップで更新した。"
        )
        self.assertEqual(t, "data")

    def test_news_article(self):
        t = xshare.classify_share_type("巨人が先発ローテを再編", "次カードから順番を入れ替える。")
        self.assertEqual(t, "news")


class ParseLabeledOutputTests(unittest.TestCase):
    def test_parses_main_and_reply(self):
        raw = "MAIN: 1行目\\n2行目\nREPLY: 続きの文です。"
        main, reply = xshare._parse_labeled_output(raw)
        self.assertEqual(main, "1行目\n2行目")
        self.assertEqual(reply, "続きの文です。")

    def test_missing_labels_returns_empty(self):
        self.assertEqual(xshare._parse_labeled_output("ただの文"), ("", ""))


class BuildShareDraftsTests(unittest.TestCase):
    _MATERIAL = {
        "post_id": 1,
        "title": "井上温大が7回無失点で今季3勝目",
        "link": "https://yoshilover.com/archives/9999",
        "body_text": "井上温大が7回を無失点に抑えた。丁寧な低めへの制球が光った。次戦はカード頭で先発予定。",
        "image_url": "https://yoshilover.com/wp-content/uploads/eyecatch.jpg",
    }

    def test_fallback_without_llm_key(self):
        drafts = xshare.build_share_drafts(self._MATERIAL, gemini_api_key="")
        self.assertTrue(drafts["ok"])
        self.assertFalse(drafts["used_llm"])
        # おりポスに URL を入れない / リプ末尾に記事URL
        self.assertNotIn("http", drafts["main_text"])
        self.assertIn("https://yoshilover.com/archives/9999", drafts["reply_text"])
        self.assertIn("井上温大", drafts["main_text"])
        self.assertEqual(drafts["image_url"], self._MATERIAL["image_url"])

    def test_forbidden_pattern_helper(self):
        self.assertEqual(xshare._forbidden_in_post("スポーツ報知によると"), "media_name")
        self.assertEqual(xshare._forbidden_in_post("#巨人 勝利"), "hashtag")
        self.assertEqual(xshare._forbidden_in_post("見て https://x.com/a"), "url")
        self.assertEqual(xshare._forbidden_in_post("坂本勇人が決めた"), "")


class PostThreadTests(unittest.TestCase):
    def _client(self, ids=("111", "222")):
        client = MagicMock()
        client.create_tweet.side_effect = [
            types.SimpleNamespace(data={"id": ids[0]}),
            types.SimpleNamespace(data={"id": ids[1]}),
        ]
        return client

    def test_posts_main_with_media_then_reply(self):
        client = self._client()
        with patch("src.x_api_client.get_client", return_value=client), patch.object(
            xshare, "_upload_media_from_url", return_value=42
        ):
            result = xshare.post_thread(
                "おりポス本文", "リプ本文 https://yoshilover.com/a",
                image_url="https://yoshilover.com/eyecatch.jpg",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["main_tweet_id"], "111")
        self.assertEqual(result["reply_tweet_id"], "222")
        self.assertTrue(result["image_attached"])
        first = client.create_tweet.call_args_list[0]
        self.assertEqual(first.kwargs["media_ids"], [42])
        second = client.create_tweet.call_args_list[1]
        self.assertEqual(second.kwargs["in_reply_to_tweet_id"], "111")

    def test_image_failure_posts_text_only(self):
        client = self._client()
        with patch("src.x_api_client.get_client", return_value=client), patch.object(
            xshare, "_upload_media_from_url", side_effect=RuntimeError("upload down")
        ):
            result = xshare.post_thread(
                "本文", "リプ", image_url="https://yoshilover.com/e.jpg"
            )
        self.assertTrue(result["ok"])
        self.assertFalse(result["image_attached"])
        self.assertIn("upload down", result["image_error"])
        first = client.create_tweet.call_args_list[0]
        self.assertNotIn("media_ids", first.kwargs)


def _invoke(method: str, path: str, body: bytes = b"", headers: dict | None = None):
    from src import manual_intake_service as svc

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
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:  # noqa: BLE001
        payload = {}
    return status, payload


class FormJsEscapeTests(unittest.TestCase):
    """2026-07-06 実バグ: _HTML_FORM 内の JS `'\\n'` が Python 実改行になり
    script ブロック全体が SyntaxError で死ぬ (おりポス+リプ案ボタン無応答の原因)。
    rendered HTML に実改行入り文字列リテラルが無いことを固定する。"""

    def test_js_string_literals_keep_backslash_n(self):
        import re
        from src.manual_intake_service import _render_form

        html = _render_form()
        self.assertIn("md.split('\\n')", html)
        self.assertIn("paraBuf.join('\\n')", html)
        # script ブロック内に「'(改行)」で切れる文字列リテラルが無いこと
        for block in re.findall(r"<script>(.*?)</script>", html, re.DOTALL):
            for lineno, line in enumerate(block.splitlines(), 1):
                stripped = line.rstrip()
                self.assertFalse(
                    stripped.endswith(".split('") or stripped.endswith(".join('")
                    or stripped.endswith("+= '"),
                    f"unterminated JS string literal at script line {lineno}: {stripped!r}",
                )


class XShareEndpointTests(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict("os.environ", {"MANUAL_INTAKE_TOKEN": ""})
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_recent_returns_posts(self):
        with patch.object(
            xshare, "list_recent_published",
            return_value=[{"id": 9, "title": "t", "link": "https://x/9", "date": "", "featured_media": 0}],
        ):
            status, payload = _invoke("GET", "/x-share-recent")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["posts"][0]["id"], 9)

    def test_draft_requires_numeric_post_id(self):
        status, payload = _invoke("GET", "/x-share-draft?post_id=abc")
        self.assertEqual(status, 400)
        self.assertEqual(payload["reason"], "post_id_required")

    def test_draft_happy_path(self):
        material = {
            "post_id": 9, "title": "t", "link": "https://x/9",
            "body_text": "本文。", "image_url": "https://x/e.jpg",
        }
        with patch.object(xshare, "fetch_article_material", return_value=material):
            status, payload = _invoke("GET", "/x-share-draft?post_id=9")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("main_text", payload)
        self.assertIn("https://x/9", payload["reply_text"])

    def test_thread_empty_text_rejected(self):
        body = json.dumps({"main_text": "", "reply_text": "r"}).encode("utf-8")
        status, payload = _invoke(
            "POST", "/x-share-thread", body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["reason"], "empty_text")

    def test_thread_weighted_too_long_rejected(self):
        body = json.dumps({
            "main_text": "あ" * 200,  # weighted 400 > 280
            "reply_text": "r",
        }).encode("utf-8")
        status, payload = _invoke(
            "POST", "/x-share-thread", body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["reason"], "text_too_long")

    def test_thread_happy_path(self):
        with patch.object(
            xshare, "post_thread",
            return_value={"ok": True, "main_tweet_id": "1", "reply_tweet_id": "2",
                          "image_attached": True, "image_error": ""},
        ) as pt:
            body = json.dumps({
                "main_text": "おりポス", "reply_text": "リプ https://x/9",
                "image_url": "https://x/e.jpg", "share_type": "comment",
            }).encode("utf-8")
            status, payload = _invoke(
                "POST", "/x-share-thread", body=body,
                headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["main_tweet_id"], "1")
        pt.assert_called_once()
        self.assertEqual(pt.call_args.kwargs["image_url"], "https://x/e.jpg")


if __name__ == "__main__":
    unittest.main()
