"""RSS-255: post_gen_validate failure history dedup tests.

post_gen_validate fail 時に source_url / x_status_id / entry_title_norm を
fail history に記録、次 cycle で early skip される動作を pin する。
TTL 24h 経過後は再評価される。重複判定の閾値変更ではない。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src import rss_fetcher


def _utc_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _record(
    history: dict,
    *,
    post_url: str = "",
    x_status_id: str = "",
    entry_title_norm: str = "",
    fail_axes: tuple[str, ...] = (),
) -> None:
    rss_fetcher._record_post_gen_validate_failure(
        history,
        post_url=post_url,
        x_status_id=x_status_id,
        entry_title_norm=entry_title_norm,
        fail_axes=fail_axes,
    )


def _is_recent(
    history: dict,
    *,
    post_url: str = "",
    x_status_id: str = "",
    entry_title_norm: str = "",
    ttl_hours: float | None = None,
) -> tuple[bool, str]:
    kwargs = dict(
        post_url=post_url,
        x_status_id=x_status_id,
        entry_title_norm=entry_title_norm,
    )
    if ttl_hours is not None:
        kwargs["ttl_hours"] = ttl_hours
    return rss_fetcher._is_post_gen_validate_failure_recent(history, **kwargs)


class FailureKeyGenerationTests(unittest.TestCase):
    """fail history 用 key 列挙の挙動を pin."""

    def test_keys_include_status_url_title(self):
        keys = rss_fetcher._post_gen_validate_failure_keys(
            post_url="https://x.com/hochi_giants/status/2050000000000000001",
            x_status_id="2050000000000000001",
            entry_title_norm="testtitle12345",
        )
        self.assertEqual(len(keys), 3)
        self.assertTrue(any(k.endswith(":status:2050000000000000001") for k in keys))
        self.assertTrue(any(k.endswith(":url:https://x.com/hochi_giants/status/2050000000000000001") for k in keys))
        self.assertTrue(any("title:testtitle12345" in k for k in keys))

    def test_keys_skip_short_entry_title_norm(self):
        keys = rss_fetcher._post_gen_validate_failure_keys(
            post_url="https://x.com/foo/status/1",
            x_status_id="1",
            entry_title_norm="abc",
        )
        # 5 char 以下の entry_title_norm は title key を生成しない (false positive 防止)
        self.assertFalse(any("title:" in k for k in keys))

    def test_keys_empty_when_all_inputs_empty(self):
        keys = rss_fetcher._post_gen_validate_failure_keys(
            post_url="",
            x_status_id="",
            entry_title_norm="",
        )
        self.assertEqual(keys, [])


class RecordAndDetectRecentFailureTests(unittest.TestCase):
    """fail history record & detect の TTL 内 / TTL 外 挙動を pin."""

    def test_record_then_detect_status_id_match(self):
        history: dict = {}
        _record(
            history,
            post_url="https://twitter.com/sanspo_giants/status/2051584183752069623",
            x_status_id="2051584183752069623",
            entry_title_norm="finalpitchresult",
            fail_axes=("placeholder_body:empty_section",),
        )
        is_recent, kind = _is_recent(
            history,
            post_url="",
            x_status_id="2051584183752069623",
            entry_title_norm="",
        )
        self.assertTrue(is_recent)
        self.assertEqual(kind, "status")

    def test_record_then_detect_source_url_match(self):
        history: dict = {}
        _record(
            history,
            post_url="https://twitter.com/sanspo_giants/status/2051584183752069623",
            x_status_id="",
            entry_title_norm="finalpitchresult",
            fail_axes=("close_marker",),
        )
        is_recent, kind = _is_recent(
            history,
            post_url="https://twitter.com/sanspo_giants/status/2051584183752069623",
            x_status_id="",
            entry_title_norm="",
        )
        self.assertTrue(is_recent)
        self.assertEqual(kind, "url")

    def test_record_then_detect_entry_title_norm_match(self):
        history: dict = {}
        _record(
            history,
            post_url="https://example.com/article-001",
            x_status_id="",
            entry_title_norm="koujituniyoshilovermukoujituuniyoshilovern",
            fail_axes=("h3_count:too_many_h3",),
        )
        is_recent, kind = _is_recent(
            history,
            post_url="",
            x_status_id="",
            entry_title_norm="koujituniyoshilovermukoujituuniyoshilovern",
        )
        self.assertTrue(is_recent)
        self.assertEqual(kind, "title")

    def test_no_match_when_history_empty(self):
        history: dict = {}
        is_recent, kind = _is_recent(
            history,
            post_url="https://x.com/foo/status/1",
            x_status_id="1",
            entry_title_norm="someothertitle",
        )
        self.assertFalse(is_recent)
        self.assertEqual(kind, "")

    def test_ttl_expired_returns_false(self):
        # 25h 前の record は TTL 24h 切れ → recent 扱いではなくなる
        history: dict = {}
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        keys = rss_fetcher._post_gen_validate_failure_keys(
            post_url="",
            x_status_id="2051584183752069623",
            entry_title_norm="",
        )
        for k in keys:
            history[k] = {
                "timestamp": _utc_str(old),
                "fail_axes": ["placeholder_body:empty_section"],
            }
        is_recent, kind = _is_recent(
            history,
            post_url="",
            x_status_id="2051584183752069623",
            entry_title_norm="",
            ttl_hours=24.0,
        )
        self.assertFalse(is_recent)
        self.assertEqual(kind, "")

    def test_ttl_within_returns_true(self):
        history: dict = {}
        # 1h 前の record は TTL 24h 内 → recent
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        keys = rss_fetcher._post_gen_validate_failure_keys(
            post_url="",
            x_status_id="2051584183752069623",
            entry_title_norm="",
        )
        for k in keys:
            history[k] = {
                "timestamp": _utc_str(recent_time),
                "fail_axes": ["close_marker"],
            }
        is_recent, kind = _is_recent(
            history,
            post_url="",
            x_status_id="2051584183752069623",
            entry_title_norm="",
            ttl_hours=24.0,
        )
        self.assertTrue(is_recent)
        self.assertEqual(kind, "status")

    def test_invalid_timestamp_no_match(self):
        history: dict = {
            "pgv_fail:status:1": {"timestamp": "not-a-date", "fail_axes": []},
        }
        is_recent, kind = _is_recent(
            history,
            post_url="",
            x_status_id="1",
            entry_title_norm="",
        )
        self.assertFalse(is_recent)

    def test_non_dict_meta_no_match(self):
        history: dict = {"pgv_fail:status:1": "scalar-not-dict"}
        is_recent, kind = _is_recent(
            history,
            post_url="",
            x_status_id="1",
            entry_title_norm="",
        )
        self.assertFalse(is_recent)


class RecordPayloadShapeTests(unittest.TestCase):
    """fail history に書き込まれる payload の形を pin."""

    def test_record_payload_includes_timestamp_axes_status_url(self):
        history: dict = {}
        _record(
            history,
            post_url="https://x.com/hochi_giants/status/2055000000000000010",
            x_status_id="2055000000000000010",
            entry_title_norm="abcdefghijabc",
            fail_axes=("placeholder_body:empty_section", "h3_count:too_many_h3"),
        )
        for key in rss_fetcher._post_gen_validate_failure_keys(
            post_url="https://x.com/hochi_giants/status/2055000000000000010",
            x_status_id="2055000000000000010",
            entry_title_norm="abcdefghijabc",
        ):
            payload = history.get(key)
            self.assertIsInstance(payload, dict)
            self.assertIn("timestamp", payload)
            self.assertEqual(payload["fail_axes"], ["placeholder_body:empty_section", "h3_count:too_many_h3"])
            self.assertEqual(payload["x_status_id"], "2055000000000000010")
            self.assertEqual(payload["source_url"], "https://x.com/hochi_giants/status/2055000000000000010")

    def test_record_no_op_when_all_keys_missing(self):
        history: dict = {}
        _record(history, post_url="", x_status_id="", entry_title_norm="")
        self.assertEqual(history, {})


class HistoryDuplicateUnchangedRegressionTests(unittest.TestCase):
    """RSS-255 は history_duplicate / duplicate_sentence の閾値や挙動を変えない."""

    def test_is_history_duplicate_signature_unchanged(self):
        # _is_history_duplicate は post_url + entry_title_norm で判定する既存 signature を維持
        history: dict = {"https://example.com/foo": "2026-05-06T00:00:00"}
        self.assertTrue(rss_fetcher._is_history_duplicate("https://example.com/foo", "", history))
        self.assertFalse(rss_fetcher._is_history_duplicate("https://example.com/bar", "", history))

    def test_is_history_duplicate_does_not_match_pgv_fail_keys(self):
        # fail history の pgv_fail: prefix は history_duplicate とは独立
        history: dict = {}
        _record(
            history,
            post_url="https://x.com/foo/status/123",
            x_status_id="123",
            entry_title_norm="duplicatetestnorm",
            fail_axes=("close_marker",),
        )
        # _is_history_duplicate は pgv_fail: prefix に反応しない
        self.assertFalse(
            rss_fetcher._is_history_duplicate(
                "https://x.com/foo/status/124",  # 別 url
                "duplicatetestnorm",  # 同 title_norm
                history,
            )
        )

    def test_pgv_fail_dedup_independent_of_history_duplicate(self):
        # 別の post_url だが、status_id が同じ場合は recent failure
        history: dict = {}
        _record(
            history,
            post_url="https://x.com/foo/status/999",
            x_status_id="999",
            entry_title_norm="",
            fail_axes=("close_marker",),
        )
        # 同 status_id の別 url を新規として渡しても pgv_fail で early skip
        is_recent, kind = _is_recent(
            history,
            post_url="https://twitter.com/foo/status/999",
            x_status_id="999",
            entry_title_norm="",
        )
        self.assertTrue(is_recent)
        self.assertEqual(kind, "status")


class TtlConstantsExposedTests(unittest.TestCase):
    """TTL / key prefix は module 定数として export されていること."""

    def test_ttl_default_is_24_hours(self):
        self.assertEqual(rss_fetcher.POST_GEN_VALIDATE_FAILURE_TTL_HOURS, 24.0)

    def test_key_prefix_is_pgv_fail(self):
        self.assertEqual(rss_fetcher.POST_GEN_VALIDATE_FAILURE_KEY_PREFIX, "pgv_fail:")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
