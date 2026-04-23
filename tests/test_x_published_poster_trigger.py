import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.x_published_poster import PublishedArticle, TEASER_MAX_LENGTH, build_post
from src.x_published_poster_trigger import (
    append_queue,
    fetch_published_since_wp,
    load_cursor,
    save_cursor,
    scan_and_queue,
)


NOW = datetime(2026, 4, 24, 0, 0, tzinfo=timezone.utc)


class _FakeHTTPResponse:
    def __init__(self, payload, headers=None):
        self._payload = json.dumps(payload).encode("utf-8")
        self.headers = headers or {}

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class XPublishedPosterTriggerTests(unittest.TestCase):
    def _article(self, **overrides) -> PublishedArticle:
        article = PublishedArticle(
            article_id=123,
            title="巨人、終盤の粘りで接戦を制した",
            excerpt="巨人が終盤の粘りで接戦を制した。救援陣が踏ん張り、終盤の得点機を逃さずに白星へつなげた。",
            body_first_paragraph=(
                "<p>巨人が終盤の粘りで接戦を制した。救援陣が踏ん張り、終盤の得点機を逃さずに白星へつなげた。</p>"
            ),
            canonical_url="https://yoshilover.com/giants-win-20260424/",
            published_at=(NOW - timedelta(hours=1)).isoformat(),
            post_status="publish",
        )
        return PublishedArticle(**{**article.__dict__, **overrides})

    def test_load_cursor_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            self.assertIsNone(load_cursor(cursor_path))

    def test_load_cursor_returns_iso_text_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            cursor_path.write_text("2026-04-23T00:00:00+00:00\n", encoding="utf-8")
            self.assertEqual(load_cursor(cursor_path), "2026-04-23T00:00:00+00:00")

    def test_save_cursor_uses_tmp_then_replace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            replace_calls = []

            def _replace(src, dst):
                replace_calls.append((Path(src), Path(dst)))
                os_replace(src, dst)

            os_replace = __import__("os").replace
            with patch("src.x_published_poster_trigger.os.replace", side_effect=_replace):
                save_cursor(cursor_path, "2026-04-24T00:00:00+00:00")

            self.assertEqual(len(replace_calls), 1)
            self.assertEqual(replace_calls[0][0], Path(f"{cursor_path}.tmp"))
            self.assertEqual(replace_calls[0][1], cursor_path)
            self.assertEqual(cursor_path.read_text(encoding="utf-8").strip(), "2026-04-24T00:00:00+00:00")
            self.assertFalse(Path(f"{cursor_path}.tmp").exists())

    def test_fetch_published_since_wp_parses_rendered_fields(self):
        payload = [
            {
                "id": 101,
                "title": {"rendered": "巨人が接戦を制す"},
                "excerpt": {"rendered": "<p>巨人が接戦を制した。終盤の継投が勝利につながった。</p>"},
                "content": {"rendered": "<p>本文1段落目。</p><p>本文2段落目。</p>"},
                "link": "https://yoshilover.com/post-101/",
                "date": "2026-04-23T10:00:00",
                "status": "publish",
            }
        ]
        response = _FakeHTTPResponse(payload, headers={"X-WP-TotalPages": "1"})
        with patch("src.x_published_poster_trigger.urllib.request.urlopen", return_value=response) as mock_urlopen:
            articles = fetch_published_since_wp("https://yoshilover.com", "2026-04-23T00:00:00+00:00")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].article_id, 101)
        self.assertEqual(articles[0].title, "巨人が接戦を制す")
        self.assertEqual(articles[0].excerpt, "<p>巨人が接戦を制した。終盤の継投が勝利につながった。</p>")
        self.assertEqual(articles[0].body_first_paragraph, "<p>本文1段落目。</p>")
        self.assertEqual(articles[0].canonical_url, "https://yoshilover.com/post-101/")
        request = mock_urlopen.call_args.args[0]
        self.assertIn("status=publish", request.full_url)
        self.assertIn("after=2026-04-23T00%3A00%3A00%2B00%3A00", request.full_url)

    def test_fetch_published_since_wp_returns_empty_list_for_empty_response(self):
        response = _FakeHTTPResponse([], headers={"X-WP-TotalPages": "1"})
        with patch("src.x_published_poster_trigger.urllib.request.urlopen", return_value=response):
            articles = fetch_published_since_wp("https://yoshilover.com", "2026-04-23T00:00:00+00:00")

        self.assertEqual(articles, [])

    def test_fetch_published_since_wp_filters_non_publish_status_entries(self):
        payload = [
            {
                "id": 201,
                "title": {"rendered": "公開記事"},
                "excerpt": {"rendered": "<p>公開済みです。</p>"},
                "content": {"rendered": "<p>公開本文。</p>"},
                "link": "https://yoshilover.com/post-201/",
                "date": "2026-04-23T10:00:00",
                "status": "publish",
            },
            {
                "id": 202,
                "title": {"rendered": "下書き記事"},
                "excerpt": {"rendered": "<p>下書きです。</p>"},
                "content": {"rendered": "<p>下書き本文。</p>"},
                "link": "https://yoshilover.com/post-202/",
                "date": "2026-04-23T10:05:00",
                "status": "draft",
            },
        ]
        response = _FakeHTTPResponse(payload, headers={"X-WP-TotalPages": "1"})
        with patch("src.x_published_poster_trigger.urllib.request.urlopen", return_value=response):
            articles = fetch_published_since_wp("https://yoshilover.com", "2026-04-23T00:00:00+00:00")

        self.assertEqual([article.article_id for article in articles], [201])

    def test_append_queue_writes_single_jsonl_entry_with_queued_at(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"
            payload = self._build_payload(article_id=301)

            append_queue(queue_path, payload)

            rows = queue_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            entry = json.loads(rows[0])
            self.assertEqual(entry["article_id"], 301)
            self.assertEqual(entry["teaser"], payload.teaser)
            self.assertEqual(entry["canonical_url"], payload.canonical_url)
            self.assertEqual(entry["published_at"], payload.published_at.isoformat())
            self.assertIn("queued_at", entry)

    def test_append_queue_appends_multiple_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_path = Path(tmpdir) / "queue.jsonl"

            append_queue(queue_path, self._build_payload(article_id=401))
            append_queue(queue_path, self._build_payload(article_id=402))

            rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["article_id"] for row in rows], [401, 402])

    def test_scan_and_queue_happy_path_detects_two_ok_and_one_skip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            articles = [
                self._article(article_id=501, canonical_url="https://yoshilover.com/post-501/", published_at="2026-04-23T01:00:00+00:00"),
                self._article(
                    article_id=502,
                    excerpt="巨人の試合後コメントをどう見るという見出しが続き、注目したいという表現も含まれているため不適切となる。",
                    body_first_paragraph="<p>巨人の試合後コメントをどう見るという見出しが続き、注目したいという表現も含まれているため不適切となる。</p>",
                    published_at="2026-04-23T02:00:00+00:00",
                ),
                self._article(article_id=503, canonical_url="https://yoshilover.com/post-503/", published_at="2026-04-23T03:00:00+00:00"),
            ]

            with patch("src.x_published_poster_trigger._utc_now", return_value=NOW):
                result = scan_and_queue(lambda _: articles, cursor_path, queue_path, history_path)

            self.assertEqual(result.detected, 3)
            self.assertEqual(result.ok, 2)
            self.assertEqual(result.skipped, [(502, "HARD_FAIL_TEASER_BANNED")])
            rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["article_id"] for row in rows], [501, 503])
            history = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(set(history.keys()), {"501", "503"})

    def test_scan_and_queue_advances_cursor_to_latest_published_at(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            articles = [
                self._article(article_id=601, published_at="2026-04-23T01:00:00+00:00"),
                self._article(article_id=602, published_at="2026-04-23T05:00:00+00:00"),
            ]

            with patch("src.x_published_poster_trigger._utc_now", return_value=NOW):
                result = scan_and_queue(lambda _: articles, cursor_path, queue_path, history_path)

            self.assertEqual(result.new_cursor, "2026-04-23T05:00:00+00:00")
            self.assertEqual(load_cursor(cursor_path), "2026-04-23T05:00:00+00:00")

    def test_scan_and_queue_respects_duplicate_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cursor_path = Path(tmpdir) / "cursor.txt"
            queue_path = Path(tmpdir) / "queue.jsonl"
            history_path = Path(tmpdir) / "history.json"
            history_path.write_text(
                json.dumps({"701": "2026-04-23T20:00:00+00:00"}, ensure_ascii=False),
                encoding="utf-8",
            )
            articles = [self._article(article_id=701, published_at="2026-04-23T21:00:00+00:00")]

            with patch("src.x_published_poster_trigger._utc_now", return_value=NOW):
                result = scan_and_queue(lambda _: articles, cursor_path, queue_path, history_path)

            self.assertEqual(result.ok, 0)
            self.assertEqual(result.skipped, [(701, "HARD_FAIL_DUPLICATE_24H")])
            self.assertFalse(queue_path.exists())

    def test_scan_and_queue_surfaces_hard_fail_reasons(self):
        cases = [
            (
                "preview_url",
                self._article(article_id=801, canonical_url="https://yoshilover.com/?preview=true"),
                "HARD_FAIL_CANONICAL_PREVIEW",
            ),
            (
                "banned_phrase",
                self._article(
                    article_id=802,
                    excerpt="巨人の試合後コメントをどう見るという見出しが続き、注目したいという表現も含まれているため不適切となる。",
                    body_first_paragraph="<p>巨人の試合後コメントをどう見るという見出しが続き、注目したいという表現も含まれているため不適切となる。</p>",
                ),
                "HARD_FAIL_TEASER_BANNED",
            ),
            (
                "teaser_length",
                self._article(
                    article_id=803,
                    excerpt="短い",
                    body_first_paragraph="<p>短い</p>",
                    title="あ" * (TEASER_MAX_LENGTH + 1),
                ),
                "HARD_FAIL_TEASER_GENERIC",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            for label, article, reason in cases:
                with self.subTest(label=label):
                    cursor_path = Path(tmpdir) / f"{label}.cursor.txt"
                    queue_path = Path(tmpdir) / f"{label}.queue.jsonl"
                    history_path = Path(tmpdir) / f"{label}.history.json"

                    with patch("src.x_published_poster_trigger._utc_now", return_value=NOW):
                        result = scan_and_queue(lambda _: [article], cursor_path, queue_path, history_path)

                    self.assertEqual(result.skipped, [(article.article_id, reason)])
                    self.assertEqual(result.ok, 0)

    def _build_payload(self, *, article_id: int):
        article = self._article(article_id=article_id)
        return build_post(article, now=NOW)


if __name__ == "__main__":
    unittest.main()
