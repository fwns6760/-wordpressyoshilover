"""Tests for src/manual_intake_service.py — MANUAL-INTAKE-GCP-001.

Covers:
- token absent / mismatch -> 403
- token present + dry-run -> 200, manual_intake invoked
- draft mode hands off to wp_client_factory
- invalid article_type / source_published_at -> 400
- form GET / -> HTML containing dropdown options
- /health -> 200
- memo never reaches body / token never echoed
- X URL canonicalization preserved
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import manual_intake_service as svc
from src.tools import manual_intake as mi


def _isolated_rate_limit_lockfile() -> Path:
    """Per-test ephemeral lockfile so service tests don't share rate-limit
    state with the on-repo default file.
    """
    tmp = tempfile.NamedTemporaryFile(
        prefix="manual_intake_lock_", suffix=".json", delete=False
    )
    tmp.close()
    return Path(tmp.name)


class _FakeRWPair:
    def __init__(self, body: bytes = b""):
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()


class _FakeRequest:
    """Stand-in for the socket-like first arg of BaseHTTPRequestHandler.

    We bypass the socket layer by directly invoking handler.do_GET / do_POST
    after seeding rfile, wfile, headers, path, command.
    """


def _invoke_handler(
    *,
    method: str,
    path: str,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
    handler_cls=None,
) -> tuple[int, dict[str, str], bytes]:
    headers = headers or {}
    if handler_cls is None:
        handler_cls = svc.build_handler()

    class _BoundHandler(handler_cls):
        def __init__(self):
            # Skip BaseHTTPRequestHandler.__init__ (it expects a socket).
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

        def log_message(self, fmt, *args):  # silence
            pass

        def log_request(self, code="-", size="-"):  # silence
            pass

        def address_string(self):
            return "127.0.0.1"

    h = _BoundHandler()
    if method == "GET":
        h.do_GET()
    elif method == "POST":
        h.do_POST()
    else:
        raise ValueError(f"unsupported method {method}")

    raw = h.wfile.getvalue()
    head, _, body_bytes = raw.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status_line = lines[0].decode("iso-8859-1")
    status_code = int(status_line.split(" ", 2)[1])
    resp_headers: dict[str, str] = {}
    for line in lines[1:]:
        if b":" in line:
            k, _, v = line.partition(b":")
            resp_headers[k.decode("iso-8859-1").strip()] = v.decode(
                "iso-8859-1"
            ).strip()
    return status_code, resp_headers, body_bytes


def _json_body(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8"))


class HealthAndFormTests(unittest.TestCase):
    def test_health_returns_200(self):
        status, _h, body = _invoke_handler(method="GET", path="/health")
        self.assertEqual(status, 200)
        self.assertEqual(_json_body(body), {"ok": True})

    def test_form_html_includes_article_type_choices(self):
        status, headers, body = _invoke_handler(method="GET", path="/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        text = body.decode("utf-8")
        for value in mi.ARTICLE_TYPE_CHOICES:
            self.assertIn(f'value="{value}"', text)
        # 12 distinct options (auto + 11 overrides).
        for label in (
            "試合結果", "試合速報", "予告先発", "公示", "監督談話",
            "選手コメント", "動画", "成績", "番組情報", "コラム", "ニュース",
        ):
            self.assertIn(label, text)
        # form posts to /manual-intake
        self.assertIn("/manual-intake", text)
        # The new UX (NOMOTOKE-INTAKE-COOKIE-001) drops the visible mode
        # radio. Default mode is sent by the form's JS as 'draft' on
        # submit, with an opt-in 'dry-run' checkbox tucked inside the
        # 詳細設定 disclosure.
        self.assertIn('id="dry-run-toggle"', text)
        # The detail disclosure is collapsed by default — operators see
        # only URL + 記事タイプ + 「記事化」 button on first load.
        self.assertIn("詳細設定", text)
        self.assertIn('data-tab="sources"', text)
        self.assertIn('id="source-form"', text)
        for source_name in (
            "読売新聞オンライン プロ野球",
            "朝日新聞スポーツRSS",
            "毎日新聞スポーツRSS",
            "週刊ベースボールONLINE RSS",
            "FRIDAY ジャイアンツ tag",
        ):
            self.assertIn(source_name, text)

    def test_manifest_returns_json(self):
        status, headers, body = _invoke_handler(
            method="GET", path="/manifest.webmanifest"
        )
        self.assertEqual(status, 200)
        self.assertIn(
            "application/manifest+json", headers.get("Content-Type", "")
        )
        manifest = _json_body(body)
        self.assertEqual(manifest["start_url"], "/")

    def test_unknown_get_returns_404(self):
        status, _h, _b = _invoke_handler(method="GET", path="/something")
        self.assertEqual(status, 404)


class AuthTests(unittest.TestCase):
    def setUp(self):
        os.environ[svc.TOKEN_ENV] = "secret-token-xyz"
        self._lockfile = _isolated_rate_limit_lockfile()
        self._lock_patch = patch.object(mi, "DEFAULT_LOCKFILE", self._lockfile)
        self._lock_patch.start()

    def tearDown(self):
        self._lock_patch.stop()
        try:
            self._lockfile.unlink()
        except FileNotFoundError:
            pass
        os.environ.pop(svc.TOKEN_ENV, None)

    def test_missing_token_returns_403(self):
        body = b"url=https://x.com/foo/status/1&mode=dry-run&title=test"
        status, _h, raw = _invoke_handler(
            method="POST",
            path="/manual-intake",
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
            },
        )
        self.assertEqual(status, 403)
        self.assertEqual(_json_body(raw)["reason"], "forbidden")

    def test_wrong_token_returns_403(self):
        body = b"url=https://x.com/foo/status/1&mode=dry-run&token=wrong&title=test"
        status, _h, raw = _invoke_handler(
            method="POST",
            path="/manual-intake",
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
            },
        )
        self.assertEqual(status, 403)

    def test_correct_token_via_header_runs_intake(self):
        body = (
            b"url=https://hochi.news/articles/x.html&mode=dry-run"
            b"&title=%E5%B7%A8%E4%BA%BA+%E8%A9%A6%E5%90%88%E9%80%9F%E5%A0%B1+0-5+%E3%83%A4%E3%82%AF%E3%83%AB%E3%83%88"
            b"&summary=%E3%83%A4%E3%82%AF%E3%83%AB%E3%83%88%E6%88%A6%E6%95%97%E6%88%A6"
        )
        status, _h, raw = _invoke_handler(
            method="POST",
            path="/manual-intake",
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
                svc.TOKEN_HEADER: "secret-token-xyz",
            },
        )
        self.assertEqual(status, 200)
        payload = _json_body(raw)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["article_type"], mi.ARTICLE_TYPE_AUTO)

    def test_source_candidates_requires_token_when_configured(self):
        status, _h, raw = _invoke_handler(
            method="GET",
            path="/source-candidates?source=%E8%AA%AD%E5%A3%B2",
        )
        self.assertEqual(status, 403)
        self.assertEqual(_json_body(raw)["reason"], "forbidden")

    def test_source_candidates_endpoint_returns_items(self):
        fake_payload = {
            "ok": True,
            "source": "読売新聞オンライン プロ野球",
            "source_count": 1,
            "fetched_source_count": 1,
            "count": 1,
            "items": [
                {
                    "source_name": "読売新聞オンライン プロ野球",
                    "source_type": "tag_scrape",
                    "title": "巨人・テスト記事",
                    "url": "https://www.yomiuri.co.jp/sports/npb/test/",
                    "summary": "巨人のテスト記事",
                    "published_at": "2026-05-18T12:00:00+09:00",
                    "article_type": "コラム",
                }
            ],
        }
        with patch.object(svc, "_source_candidates_payload", return_value=fake_payload):
            status, _h, raw = _invoke_handler(
                method="GET",
                path="/source-candidates?source=%E8%AA%AD%E5%A3%B2%E6%96%B0%E8%81%9E%E3%82%AA%E3%83%B3%E3%83%A9%E3%82%A4%E3%83%B3%20%E3%83%97%E3%83%AD%E9%87%8E%E7%90%83",
                headers={svc.TOKEN_HEADER: "secret-token-xyz"},
            )
        self.assertEqual(status, 200)
        payload = _json_body(raw)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["items"][0]["source_name"], "読売新聞オンライン プロ野球")

    def test_token_unconfigured_env_runs_in_open_mode(self):
        # NOMOTOKE-INTAKE-OPEN-001: when MANUAL_INTAKE_TOKEN is unset on
        # the service, the auth gate is skipped and the request flows
        # into the manual_intake handler unchanged. The previous 503
        # `service_token_unconfigured` behaviour is intentionally
        # dropped — the production deploy now runs without a token
        # because the operator wanted "誰でもアクセスでいい". WP write
        # remains draft-only, output is noindex, and guarded-publish
        # plus manual review are the canonical safety gates.
        os.environ.pop(svc.TOKEN_ENV, None)
        body = b"url=https://x.com/foo/status/1"
        status, _h, raw = _invoke_handler(
            method="POST",
            path="/manual-intake",
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
            },
        )
        # Either 200 (validation_ok) or 4xx (validation failure inside
        # mi.handle) is acceptable here; the assertion is just that we
        # never hit 503 service_token_unconfigured anymore.
        self.assertNotEqual(status, 503)
        payload = _json_body(raw)
        self.assertNotEqual(payload.get("reason"), "service_token_unconfigured")
        self.assertNotEqual(payload.get("reason"), "forbidden")


class IntakeBehaviourTests(unittest.TestCase):
    def setUp(self):
        os.environ[svc.TOKEN_ENV] = "tok"
        self._lockfile = _isolated_rate_limit_lockfile()
        self._lock_patch = patch.object(mi, "DEFAULT_LOCKFILE", self._lockfile)
        self._lock_patch.start()

    def tearDown(self):
        self._lock_patch.stop()
        try:
            self._lockfile.unlink()
        except FileNotFoundError:
            pass
        os.environ.pop(svc.TOKEN_ENV, None)

    def _post(self, payload: dict, *, handler_cls=None) -> tuple[int, dict]:
        body_str = "&".join(
            f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in payload.items()
        )
        body = body_str.encode("utf-8")
        status, _h, raw = _invoke_handler(
            method="POST",
            path="/manual-intake",
            body=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(len(body)),
                svc.TOKEN_HEADER: "tok",
            },
            handler_cls=handler_cls,
        )
        return status, _json_body(raw)

    def test_draft_mode_invokes_wp_client_factory_with_meta(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 9001

        wp = MagicMock()
        wp.create_post = fake_create
        handler_cls = svc.build_handler(wp_client_factory=lambda: wp)

        status, resp = self._post(
            {
                "url": "https://hochi.news/articles/abc.html",
                "mode": "draft",
                "title": "巨人 試合速報 0-5 ヤクルト",
                "summary": "ヤクルト戦敗戦",
                "article_type": "試合結果",
                "source_published_at": "2026-05-07T18:30:00+09:00",
                "memo": "操作メモ_DO_NOT_LEAK_42",
            },
            handler_cls=handler_cls,
        )
        self.assertEqual(status, 200)
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["post_id"], 9001)
        # WP receives category_id list (not the name) per article_type override.
        self.assertEqual(resp["category"], "試合速報")
        self.assertEqual(resp["category_ids"], [663])
        self.assertEqual(captured.get("categories"), [663])
        self.assertEqual(
            captured.get("source_published_at_iso"),
            "2026-05-07T18:30:00+09:00",
        )
        # memo never enters body / title / meta.
        self.assertNotIn(
            "操作メモ_DO_NOT_LEAK_42", captured.get("content", "")
        )
        self.assertNotIn(
            "操作メモ_DO_NOT_LEAK_42", captured.get("title", "")
        )

    def test_dry_run_does_not_call_wp_factory(self):
        wp_factory = MagicMock()
        handler_cls = svc.build_handler(wp_client_factory=wp_factory)

        status, resp = self._post(
            {
                "url": "https://hochi.news/articles/dr.html",
                "mode": "dry-run",
                "title": "巨人 試合速報 0-5 ヤクルト",
                "summary": "ヤクルト戦敗戦",
                "article_type": "auto",
            },
            handler_cls=handler_cls,
        )
        self.assertEqual(status, 200)
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["mode"], "dry-run")
        wp_factory.assert_not_called()

    def test_invalid_article_type_returns_400(self):
        status, resp = self._post(
            {
                "url": "https://x.com/foo/status/1",
                "mode": "dry-run",
                "title": "巨人 試合終了 0-5 ヤクルト",
                "article_type": "nonexistent",
            }
        )
        self.assertEqual(status, 400)
        self.assertEqual(resp["skip_reason"], "invalid_article_type")

    def test_invalid_source_published_at_returns_400(self):
        status, resp = self._post(
            {
                "url": "https://x.com/foo/status/1",
                "mode": "dry-run",
                "title": "巨人 試合終了 0-5 ヤクルト",
                "source_published_at": "yesterday",
            }
        )
        self.assertEqual(status, 400)
        self.assertEqual(resp["skip_reason"], "invalid_source_published_at")

    def test_missing_url_returns_400(self):
        status, resp = self._post({"mode": "dry-run"})
        self.assertEqual(status, 400)
        self.assertEqual(resp["reason"], "missing_url")

    def test_invalid_mode_returns_400(self):
        # publish is now an accepted mode (operator-vetted manual intake).
        # 'bogus' stands in as the explicit-rejection sentinel.
        status, resp = self._post(
            {
                "url": "https://x.com/foo/status/1",
                "mode": "bogus",
                "title": "巨人 試合終了 0-5 ヤクルト",
            }
        )
        self.assertEqual(status, 400)
        self.assertEqual(resp["reason"], "invalid_mode")

    def test_publish_mode_creates_wp_post_with_status_publish(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 9999

        wp = MagicMock()
        wp.create_post = fake_create
        handler_cls = svc.build_handler(wp_client_factory=lambda: wp)

        status, resp = self._post(
            {
                "url": "https://hochi.news/articles/xyz.html",
                "mode": "publish",
                "title": "巨人 サヨナラ勝ち 5-4 ヤクルト",
                "summary": "9回サヨナラ本塁打",
                "article_type": "試合結果",
            },
            handler_cls=handler_cls,
        )
        self.assertEqual(status, 200)
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["post_id"], 9999)
        self.assertEqual(resp["mode"], "publish")
        self.assertEqual(resp.get("wp_status"), "publish")
        self.assertEqual(captured.get("status"), "publish")
        self.assertEqual(captured.get("caller"), "manual_intake")

    def test_x_url_normalized_through_service(self):
        captured: dict = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return 9002

        wp = MagicMock()
        wp.create_post = fake_create
        handler_cls = svc.build_handler(wp_client_factory=lambda: wp)

        status, resp = self._post(
            {
                "url": "https://x.com/TokyoGiants/status/12345",
                "mode": "draft",
                "title": "巨人 試合終了 0-5 ヤクルト",
                "article_type": "auto",
            },
            handler_cls=handler_cls,
        )
        self.assertEqual(status, 200)
        self.assertEqual(resp["source_kind"], "x")
        self.assertEqual(
            captured.get("source_url"),
            "https://twitter.com/TokyoGiants/status/12345",
        )
        # No source-fact inflation: body still embed-only.
        self.assertIn("twitter-tweet", captured.get("content", ""))

    def test_json_body_accepted(self):
        body = json.dumps(
            {
                "url": "https://hochi.news/articles/json.html",
                "mode": "dry-run",
                "title": "巨人 試合速報 0-5 ヤクルト",
                "summary": "ヤクルト戦敗戦",
                "article_type": "ニュース",
                "token": "tok",
            }
        ).encode("utf-8")
        status, _h, raw = _invoke_handler(
            method="POST",
            path="/manual-intake",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        self.assertEqual(status, 200)
        resp = _json_body(raw)
        self.assertTrue(resp["ok"])
        self.assertEqual(resp["article_type"], "ニュース")
        # ニュース -> コラム -> 670
        self.assertEqual(resp["category_ids"], [670])

    def test_token_not_echoed_in_response(self):
        # Even valid responses must not surface the token field.
        status, resp = self._post(
            {
                "url": "https://hochi.news/articles/echo.html",
                "mode": "dry-run",
                "title": "巨人 試合速報 0-5 ヤクルト",
                "summary": "ヤクルト戦敗戦",
            }
        )
        self.assertEqual(status, 200)
        self.assertNotIn("token", resp)


class SourceCandidateHelperTests(unittest.TestCase):
    def test_manual_source_sources_include_general_newspapers_and_magazines(self):
        names = {source.get("name") for source in svc._load_manual_source_sources()}
        for expected in (
            "読売新聞オンライン プロ野球",
            "朝日新聞スポーツRSS",
            "毎日新聞スポーツRSS",
            "週刊ベースボールONLINE RSS",
            "FRIDAY ジャイアンツ tag",
            "Smart FLASH 巨人 tag",
            "週刊女性PRIME 巨人 tag",
            "文春オンライン 読売ジャイアンツ",
            "NEWSポストセブン 巨人 search",
            "デイリー新潮 巨人 search",
            "現代ビジネス 巨人 search",
            "アサ芸プラス 巨人 search",
        ):
            self.assertIn(expected, names)

    def test_source_candidates_payload_filters_non_giants_entries(self):
        source = {
            "name": "朝日新聞スポーツRSS",
            "url": "https://www.asahi.com/rss/asahi/sports.rdf",
            "type": "news",
            "role": ["article_source"],
        }
        fake_entries = [
            {
                "title": "巨人・テスト記事",
                "link": "https://www.asahi.com/articles/test1.html",
                "summary": "読売ジャイアンツのテスト",
                "published_parsed": time.gmtime(0),
            },
            {
                "title": "サッカー日本代表の記事",
                "link": "https://www.asahi.com/articles/test2.html",
                "summary": "代表戦の結果",
                "published_parsed": time.gmtime(0),
            },
        ]
        with patch.object(svc, "_fetch_manual_source_entries", return_value=fake_entries):
            payload = svc._source_candidates_payload(
                source_name="朝日新聞スポーツRSS",
                sources=[source],
                limit=5,
            )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["title"], "巨人・テスト記事")
        self.assertEqual(payload["items"][0]["source_name"], "朝日新聞スポーツRSS")


class LiveServerSmokeTest(unittest.TestCase):
    """Spin up a real HTTPServer on an ephemeral port to confirm the
    request loop wiring (rfile/wfile/headers) works end-to-end."""

    def setUp(self):
        os.environ[svc.TOKEN_ENV] = "smoke-tok"
        self._lockfile = _isolated_rate_limit_lockfile()
        self._lock_patch = patch.object(mi, "DEFAULT_LOCKFILE", self._lockfile)
        self._lock_patch.start()
        self.server = HTTPServer(("127.0.0.1", 0), svc.build_handler())
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self._lock_patch.stop()
        try:
            self._lockfile.unlink()
        except FileNotFoundError:
            pass
        os.environ.pop(svc.TOKEN_ENV, None)

    def test_live_health(self):
        with closing(urllib.request.urlopen(f"{self.base}/health", timeout=3)) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data.get("ok"))

    def test_live_post_dry_run_returns_200(self):
        body = json.dumps(
            {
                "url": "https://hochi.news/articles/live.html",
                "mode": "dry-run",
                "title": "巨人 試合速報 0-5 ヤクルト",
                "summary": "ヤクルト戦敗戦",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/manual-intake",
            data=body,
            headers={
                "Content-Type": "application/json",
                svc.TOKEN_HEADER: "smoke-tok",
            },
        )
        with closing(urllib.request.urlopen(req, timeout=3)) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["mode"], "dry-run")

    def test_live_post_without_token_403(self):
        body = b'{"url":"https://hochi.news/articles/live.html","mode":"dry-run","title":"x"}'
        req = urllib.request.Request(
            f"{self.base}/manual-intake",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(cm.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
