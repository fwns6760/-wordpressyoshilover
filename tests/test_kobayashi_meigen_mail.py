"""tests for 377-ARCHIVE Phase 2: kobayashi_meigen_mail_lane."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from src import kobayashi_meigen_mail_lane as lane

JST = ZoneInfo("Asia/Tokyo")


def _make_records() -> list[dict]:
    return [
        {
            "tweet_id": "100",
            "text": "古い tweet (2019)",
            "created_at": "2019-03-21T22:30:34+00:00",
            "public_metrics": {"like_count": 5, "retweet_count": 2,
                               "reply_count": 0, "quote_count": 0},
            "has_media": False,
            "media": [],
        },
        {
            "tweet_id": "200",
            "text": "中間 tweet (2021) #小林誠司",
            "created_at": "2021-01-16T08:00:00+00:00",
            "public_metrics": {"like_count": 189, "retweet_count": 15,
                               "reply_count": 1, "quote_count": 0},
            "has_media": True,
            "media": [{"media_key": "k1", "type": "photo", "url": None}],
        },
        {
            "tweet_id": "300",
            "text": "新しい tweet (2022)",
            "created_at": "2022-05-27T13:41:40+00:00",
            "public_metrics": {"like_count": 294, "retweet_count": 26,
                               "reply_count": 2, "quote_count": 0},
            "has_media": True,
            "media": [{"media_key": "k2", "type": "photo",
                       "url": "https://pbs.twimg.com/media/example.jpg"}],
        },
    ]


class PickCandidatesTests(unittest.TestCase):
    def test_oldest_first_unsent(self) -> None:
        records = _make_records()
        cands = lane.pick_candidates(records, sent_ids=set(), n=2)
        self.assertEqual([c.tweet_id for c in cands], ["100", "200"])
        # oldest comes first
        self.assertEqual(cands[0].created_at, "2019-03-21T22:30:34+00:00")

    def test_skips_already_sent(self) -> None:
        records = _make_records()
        cands = lane.pick_candidates(records, sent_ids={"100"}, n=2)
        self.assertEqual([c.tweet_id for c in cands], ["200", "300"])

    def test_returns_empty_when_all_sent(self) -> None:
        records = _make_records()
        sent = {"100", "200", "300"}
        cands = lane.pick_candidates(records, sent_ids=sent, n=3)
        self.assertEqual(cands, [])

    def test_n_cap_limits_count(self) -> None:
        records = _make_records()
        cands = lane.pick_candidates(records, sent_ids=set(), n=1)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].tweet_id, "100")


class SubjectAndComposeTests(unittest.TestCase):
    def test_subject_format(self) -> None:
        now = datetime(2026, 5, 18, 12, 0, tzinfo=JST)
        mail = lane.compose_mail(
            lane.pick_candidates(_make_records(), sent_ids=set(), n=2),
            now=now,
        )
        # filter prefix + suffix (yoshilover folder 振り分け用)
        self.assertIn("🟠🐦📮", mail.subject)
        self.assertTrue(mail.subject.endswith("| YOSHILOVER"))
        self.assertIn("小林誠司 名言", mail.subject)
        self.assertIn("2件", mail.subject)
        self.assertIn("12:00 JST", mail.subject)
        self.assertIn("🌞昼", mail.subject)

    def test_subject_band_evening(self) -> None:
        now = datetime(2026, 5, 18, 17, 0, tzinfo=JST)
        mail = lane.compose_mail([], now=now)
        self.assertIn("🌆夕方", mail.subject)

    def test_subject_band_night(self) -> None:
        now = datetime(2026, 5, 18, 20, 0, tzinfo=JST)
        mail = lane.compose_mail([], now=now)
        self.assertIn("🌙夜", mail.subject)

    def test_text_body_includes_dates_and_permalinks(self) -> None:
        records = _make_records()
        cands = lane.pick_candidates(records, sent_ids=set(), n=3)
        now = datetime(2026, 5, 18, 12, 0, tzinfo=JST)
        mail = lane.compose_mail(cands, now=now)
        # 全件 permalink が text に出る
        for c in cands:
            self.assertIn(c.permalink, mail.text_body)
        # 日付は JST 表示
        self.assertIn("2019年3月22日", mail.text_body)  # UTC → JST で +1 day
        self.assertIn("2022年5月27日", mail.text_body)

    def test_html_body_renders_image_when_url_present(self) -> None:
        records = _make_records()
        cands = lane.pick_candidates(records, sent_ids=set(), n=3)
        now = datetime(2026, 5, 18, 12, 0, tzinfo=JST)
        mail = lane.compose_mail(cands, now=now)
        # tweet 300 (媒体 URL あり) → <img> 出る
        self.assertIn("https://pbs.twimg.com/media/example.jpg", mail.html_body)
        self.assertIn("<img", mail.html_body)
        # tweet 200 (media あるが url None) → backfill 待ち文言
        self.assertIn("URL backfill", mail.html_body)

    def test_html_body_escapes_html_entities(self) -> None:
        records = [{
            "tweet_id": "999",
            "text": "<script>alert(1)</script> 名言",
            "created_at": "2022-01-01T00:00:00+00:00",
            "public_metrics": {"like_count": 1, "retweet_count": 0,
                               "reply_count": 0, "quote_count": 0},
            "has_media": False,
            "media": [],
        }]
        cands = lane.pick_candidates(records, sent_ids=set(), n=1)
        mail = lane.compose_mail(cands, now=datetime(2026, 5, 18, 12, 0, tzinfo=JST))
        self.assertNotIn("<script>", mail.html_body)
        self.assertIn("&lt;script&gt;", mail.html_body)


class _FakeBlob:
    def __init__(self, store: dict[str, str], key: str):
        self.store = store
        self.key = key

    def exists(self) -> bool:
        return self.key in self.store

    def download_as_text(self) -> str:
        return self.store[self.key]

    def upload_from_string(self, data: str, content_type: str = "") -> None:
        self.store[self.key] = data


class _FakeBucket:
    def __init__(self, store: dict[str, str]):
        self.store = store

    def blob(self, key: str) -> _FakeBlob:
        return _FakeBlob(self.store, key)


class CursorTests(unittest.TestCase):
    def test_load_sent_cursor_empty_when_missing(self) -> None:
        bucket = _FakeBucket({})
        self.assertEqual(lane.load_sent_cursor(bucket), set())

    def test_load_sent_cursor_returns_ids(self) -> None:
        store = {
            lane.CURSOR_KEY: (
                '{"ts": "2026-05-18T12:00:00+09:00", "tweet_id": "100"}\n'
                '{"ts": "2026-05-18T17:00:00+09:00", "tweet_id": "200"}\n'
            ),
        }
        bucket = _FakeBucket(store)
        ids = lane.load_sent_cursor(bucket)
        self.assertEqual(ids, {"100", "200"})

    def test_append_sent_cursor_appends_not_overwrites(self) -> None:
        store = {
            lane.CURSOR_KEY: '{"ts": "2026-05-18T12:00:00+09:00", "tweet_id": "100"}\n',
        }
        bucket = _FakeBucket(store)
        now = datetime(2026, 5, 18, 17, 0, tzinfo=JST)
        ok = lane.append_sent_cursor(
            bucket, sent_tweet_ids=["200", "300"], now=now,
        )
        self.assertTrue(ok)
        body = store[lane.CURSOR_KEY]
        self.assertIn('"tweet_id": "100"', body)
        self.assertIn('"tweet_id": "200"', body)
        self.assertIn('"tweet_id": "300"', body)


class XIntentButtonTests(unittest.TestCase):
    def test_intent_url_url_encodes_text(self) -> None:
        url = lane._build_x_intent_url("こんにちは #小林誠司")
        self.assertTrue(url.startswith("https://x.com/intent/post?text="))
        self.assertIn("%23", url)  # # is url-encoded
        self.assertNotIn(" ", url)

    def test_intent_url_truncates_long_text(self) -> None:
        long_text = "あ" * 400
        url = lane._build_x_intent_url(long_text)
        # decoded length must be ≤ 270
        from urllib.parse import unquote
        decoded = unquote(url.split("text=", 1)[1])
        self.assertLessEqual(len(decoded), 270)
        self.assertTrue(decoded.endswith("…"))

    def test_html_body_includes_x_intent_button(self) -> None:
        records = _make_records()
        cands = lane.pick_candidates(records, sent_ids=set(), n=1)
        now = datetime(2026, 5, 18, 12, 0, tzinfo=JST)
        mail = lane.compose_mail(cands, now=now)
        self.assertIn("x.com/intent/post", mail.html_body)
        self.assertIn("🐦 X に投稿", mail.html_body)

    def test_text_body_includes_intent_link(self) -> None:
        records = _make_records()
        cands = lane.pick_candidates(records, sent_ids=set(), n=1)
        now = datetime(2026, 5, 18, 12, 0, tzinfo=JST)
        mail = lane.compose_mail(cands, now=now)
        self.assertIn("x.com/intent/post", mail.text_body)


class LoadArchiveTests(unittest.TestCase):
    def test_load_archive_parses_jsonl(self) -> None:
        store = {
            lane.ARCHIVE_KEY: (
                '{"tweet_id": "100", "text": "a", "created_at": "2019-01-01T00:00:00+00:00", '
                '"public_metrics": {"like_count": 5}, "has_media": false}\n'
                '{"tweet_id": "200", "text": "b", "created_at": "2020-01-01T00:00:00+00:00", '
                '"public_metrics": {"like_count": 10}, "has_media": false}\n'
            ),
        }
        bucket = _FakeBucket(store)
        records = lane.load_archive(bucket)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["tweet_id"], "100")

    def test_load_archive_empty_when_missing(self) -> None:
        bucket = _FakeBucket({})
        self.assertEqual(lane.load_archive(bucket), [])

    def test_load_archive_skips_invalid_lines(self) -> None:
        store = {
            lane.ARCHIVE_KEY: (
                'not-json\n'
                '{"tweet_id": "100", "text": "ok"}\n'
                '\n'
            ),
        }
        bucket = _FakeBucket(store)
        records = lane.load_archive(bucket)
        self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
