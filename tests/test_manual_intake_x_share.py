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
    def test_parses_hook_summary_reply(self):
        raw = "HOOK: 見立ての一言。\nSUMMARY: 要約1文目。\\n要約2文目。\nREPLY: 続きの文です。"
        hook, summary, reply = xshare._parse_labeled_output(raw)
        self.assertEqual(hook, "見立ての一言。")
        self.assertEqual(summary, "要約1文目。\n要約2文目。")
        self.assertEqual(reply, "続きの文です。")

    def test_missing_labels_returns_empty(self):
        self.assertEqual(xshare._parse_labeled_output("ただの文"), ("", "", ""))


class HookEchoTests(unittest.TestCase):
    _TITLE = "【巨人】勝ち頭の井上温大「成功体験が増えてきている」　捕手のサインに首振らない理由も説明"

    def test_title_copy_is_echo(self):
        self.assertTrue(xshare._hook_echoes_title("勝ち頭の井上温大「成功体験が増えてきている」", self._TITLE))

    def test_original_hook_passes(self):
        self.assertFalse(xshare._hook_echoes_title("首を振らない勇気じゃなくて、合理性。", self._TITLE))

    def test_empty_hook_is_echo(self):
        self.assertTrue(xshare._hook_echoes_title("", self._TITLE))


class AssembleMainTests(unittest.TestCase):
    def test_full_three_blocks(self):
        text = xshare._assemble_main("タイトル（スポーツ報知）", "フック。", "要約文。")
        self.assertEqual(text, "フック。\n\nタイトル（スポーツ報知）\n\n要約文。")

    def test_degrades_when_over_limit(self):
        # env で旧 280 上限に戻した時の退避動作 (Premium default は 900)
        import os
        from unittest import mock
        long_summary = "あ" * 135  # weighted 270 で3ブロック合計は 280 を必ず超過
        with mock.patch.dict(os.environ, {"X_SHARE_MAIN_WEIGHTED_LIMIT": "280"}):
            text = xshare._assemble_main("タイトル（報知）", "フックの一言。", long_summary)
        self.assertNotIn(long_summary, text)
        self.assertIn("タイトル（報知）", text)
        self.assertLessEqual(xshare.x_weighted_len(text), 280)

    def test_premium_default_keeps_long_body(self):
        """2026-07-07 user「オリポスながめ。プレミアプランだし」: 長文本文は削らない。"""
        long_summary = "あ" * 135  # weighted 270、Premium default 900 なら丸ごと残る
        text = xshare._assemble_main("タイトル（報知）", "フックの一言。", long_summary)
        self.assertIn(long_summary, text)
        self.assertLessEqual(xshare.x_weighted_len(text), 900)


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

    def test_fallback_title_line_includes_media_name(self):
        material = dict(self._MATERIAL, media_name="スポーツ報知")
        drafts = xshare.build_share_drafts(material, gemini_api_key="")
        self.assertTrue(
            drafts["main_text"].startswith("井上温大が7回無失点で今季3勝目（スポーツ報知）")
        )

    def test_llm_path_assembles_hook_title_summary(self):
        material = dict(self._MATERIAL, media_name="スポーツ報知")
        with patch.object(
            xshare, "_build_drafts_llm",
            return_value=("低めの制球が答え。", "丁寧に低めを突く投球で7回無失点。", "次戦はカード頭で先発予定。"),
        ):
            drafts = xshare.build_share_drafts(material, gemini_api_key="k")
        self.assertTrue(drafts["used_llm"])
        self.assertEqual(
            drafts["main_text"],
            "低めの制球が答え。\n\n井上温大が7回無失点で今季3勝目（スポーツ報知）\n\n"
            "丁寧に低めを突く投球で7回無失点。",
        )
        self.assertIn("次戦はカード頭で先発予定。", drafts["reply_text"])

    def test_main_text_has_no_reply_pointer(self):
        """2026-07-19 user「リプの考えは捨てる」: おりポス単発運用のため、
        リプ欄への誘導行は本文に入れない。fallback 経路も対象。"""
        drafts = xshare.build_share_drafts(self._MATERIAL, gemini_api_key="")
        self.assertNotIn("リプ欄", drafts["main_text"])
        self.assertLessEqual(
            xshare.x_weighted_len(drafts["main_text"]),
            xshare._main_weighted_limit(),
        )

    def test_detect_media_name_domain_first(self):
        self.assertEqual(
            xshare._detect_media_name('<a href="https://hochi.news/articles/1">出典</a>', ""),
            "スポーツ報知",
        )
        self.assertEqual(
            xshare._detect_media_name("", "出典: スポニチ「巨人が勝利」"), "スポニチ"
        )
        self.assertEqual(xshare._detect_media_name("", "出典なし本文"), "")

    def test_detect_media_name_prose_mention_not_picked(self):
        # 本文の別文脈に媒体名があっても出典ブロック外なら拾わない (102501 東スポ誤判定)
        body = "東スポの記事が話題になった。 出典: news.yahoo.co.jp「タイトル」"
        html = '<a href="https://news.yahoo.co.jp/articles/x">出典</a>'
        self.assertEqual(xshare._detect_media_name(html, body), "Yahoo!ニュース")

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


class PostgameThreadTests(unittest.TestCase):
    """2026-07-07 user GO「今日の試合スレ (mail→アプリ→ボタン1回で3連投稿)」。"""

    def test_find_latest_postgame_picks_result_title(self):
        posts = [
            {"id": 1, "title": "岡本和真がコメント", "link": "https://x/1", "date": "", "featured_media": 0},
            {"id": 2, "title": "巨人、中日に5-2で快勝　戸郷が7回2失点", "link": "https://x/2", "date": "", "featured_media": 0},
        ]
        with patch.object(xshare, "list_recent_published", return_value=posts):
            got = xshare.find_latest_postgame()
        self.assertEqual(got["id"], 2)

    def test_find_latest_postgame_empty_when_no_result(self):
        posts = [{"id": 1, "title": "岡本和真がコメント", "link": "https://x/1", "date": "", "featured_media": 0}]
        with patch.object(xshare, "list_recent_published", return_value=posts):
            self.assertEqual(xshare.find_latest_postgame(), {})

    def test_build_thread_drafts_includes_data_text(self):
        material = {
            "post_id": 2, "title": "巨人、中日に5-2で快勝　戸郷翔征が7回2失点",
            "link": "https://x/2", "body_text": "本文。", "image_url": "", "status": "publish",
        }
        with patch.object(xshare, "build_share_drafts", return_value={"ok": True, "main_text": "m", "reply_text": "r"}), \
             patch.object(xshare, "_build_hero_data_text", return_value="今日の戸郷翔征、数字で見るとこう👇\n投球: 7回 2失点"):
            drafts = xshare.build_thread_drafts(material)
        self.assertIn("戸郷翔征", drafts["data_text"])
        self.assertEqual(drafts["main_text"], "m")

    def test_hero_data_text_empty_when_player_not_detected(self):
        with patch("src.x_post_mail_lane.detect_giants_player_name", return_value=""):
            out = xshare._build_hero_data_text({"title": "何か", "body_text": ""})
        self.assertEqual(out, "")

    def test_post_thread_with_data_text_chains_three(self):
        client = MagicMock()
        client.create_tweet.side_effect = [
            types.SimpleNamespace(data={"id": "10"}),
            types.SimpleNamespace(data={"id": "11"}),
            types.SimpleNamespace(data={"id": "12"}),
        ]
        with patch("src.x_api_client.get_client", return_value=client):
            result = xshare.post_thread("本文", "リプ", data_text="データ")
        self.assertTrue(result["ok"])
        self.assertEqual(result["main_tweet_id"], "10")
        self.assertEqual(result["data_tweet_id"], "11")
        self.assertEqual(result["reply_tweet_id"], "12")
        calls = client.create_tweet.call_args_list
        self.assertEqual(calls[1].kwargs["in_reply_to_tweet_id"], "10")
        self.assertEqual(calls[2].kwargs["in_reply_to_tweet_id"], "11")

    def test_post_thread_without_data_text_keeps_two(self):
        client = MagicMock()
        client.create_tweet.side_effect = [
            types.SimpleNamespace(data={"id": "10"}),
            types.SimpleNamespace(data={"id": "11"}),
        ]
        with patch("src.x_api_client.get_client", return_value=client):
            result = xshare.post_thread("本文", "リプ")
        self.assertEqual(client.create_tweet.call_count, 2)
        self.assertEqual(result["data_tweet_id"], "")
        self.assertEqual(
            client.create_tweet.call_args_list[1].kwargs["in_reply_to_tweet_id"], "10"
        )


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
        # 2026-07-19: おりポス (main) は Premium 長文上限 (default 1400 weighted)。
        # 上限を動的に参照して常に「上限超過」の本文を作る (上限変更でこのテストが
        # 実APIへ到達した事故の再発防止)。
        over = xshare._main_weighted_limit() // 2 + 10
        body = json.dumps({
            "main_text": "あ" * over,
            "reply_text": "r",
        }).encode("utf-8")
        status, payload = _invoke(
            "POST", "/x-share-thread", body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["reason"], "text_too_long")

    def test_thread_reply_over_280_rejected(self):
        # リプは従来どおり 280 weighted 上限。
        body = json.dumps({
            "main_text": "おりポス",
            "reply_text": "あ" * 200,  # weighted 400 > 280
        }).encode("utf-8")
        status, payload = _invoke(
            "POST", "/x-share-thread", body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["reason"], "text_too_long")

    def test_thread_main_premium_length_accepted(self):
        # 280 超〜900 weighted のおりポスは投稿を通す (旧 280 ゲートのデグレ防止)。
        with patch.object(
            xshare, "post_thread",
            return_value={"ok": True, "main_tweet_id": "1", "reply_tweet_id": "2",
                          "image_attached": False, "image_error": ""},
        ) as pt:
            body = json.dumps({
                "main_text": "あ" * 200,  # weighted 400 (280 < x <= 900)
                "reply_text": "リプ https://x/9",
            }).encode("utf-8")
            status, payload = _invoke(
                "POST", "/x-share-thread", body=body,
                headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        pt.assert_called_once()

    def test_thread_draft_endpoint_happy_path(self):
        latest = {"id": 2, "title": "巨人、中日に5-2で快勝", "link": "https://x/2", "date": "", "featured_media": 0}
        material = {
            "post_id": 2, "title": "巨人、中日に5-2で快勝", "link": "https://x/2",
            "body_text": "本文。", "image_url": "", "status": "publish",
        }
        with patch.object(xshare, "find_latest_postgame", return_value=latest), \
             patch.object(xshare, "fetch_article_material", return_value=material), \
             patch.object(xshare, "build_thread_drafts", return_value={"ok": True, "main_text": "m", "reply_text": "r", "data_text": "d"}):
            status, payload = _invoke("GET", "/x-thread-draft")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["is_thread"])
        self.assertEqual(payload["data_text"], "d")
        self.assertEqual(payload["post_id"], 2)

    def test_thread_draft_endpoint_404_when_no_postgame(self):
        with patch.object(xshare, "find_latest_postgame", return_value={}):
            status, payload = _invoke("GET", "/x-thread-draft")
        self.assertEqual(status, 404)
        self.assertEqual(payload["reason"], "no_postgame_article")

    def test_thread_data_text_over_280_rejected(self):
        body = json.dumps({
            "main_text": "おりポス",
            "reply_text": "リプ",
            "data_text": "あ" * 200,  # weighted 400 > 280
        }).encode("utf-8")
        status, payload = _invoke(
            "POST", "/x-share-thread", body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["reason"], "text_too_long")

    def test_thread_post_passes_data_text(self):
        with patch.object(
            xshare, "post_thread",
            return_value={"ok": True, "main_tweet_id": "1", "data_tweet_id": "2",
                          "reply_tweet_id": "3", "image_attached": False, "image_error": ""},
        ) as pt:
            body = json.dumps({
                "main_text": "おりポス", "reply_text": "リプ https://x/9",
                "data_text": "今日の数字",
            }).encode("utf-8")
            status, payload = _invoke(
                "POST", "/x-share-thread", body=body,
                headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["data_tweet_id"], "2")
        self.assertEqual(pt.call_args.kwargs["data_text"], "今日の数字")

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
