"""Tests for rss_fetcher.py の player_voice_digest detection 接続 (334-QA Phase 2b).

本 file は rss_fetcher main flow を invoke しない。
追加された _player_voice_digest_detection_enabled() と
_aggregate_player_voice_digest_candidates() の 2 関数を直接呼んで
flag off / flag on / error handling の挙動を確認する。
"""

from __future__ import annotations

import logging
import os
import unittest

from src import rss_fetcher
from src.rss_fetcher import (
    PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG,
    _aggregate_player_voice_digest_candidates,
    _player_voice_digest_detection_enabled,
)


_HOST_URL = {
    "hochi": "https://hochi.news/articles/{}.html",
    "sanspo": "https://www.sanspo.com/article/{}/",
    "nikkansports": "https://www.nikkansports.com/baseball/news/{}.html",
}


def _cand(
    *,
    family: str = "hochi",
    game_id: str = "g1",
    player_name: str = "坂本勇人",
    title: str = "",
    body: str = "",
    article_id: str = "1",
) -> dict:
    return {
        "game_id": game_id,
        "player_name": player_name,
        "title": title,
        "body": body,
        "post_url": _HOST_URL[family].format(article_id),
        "published_at": "2026-05-14T20:00",
    }


_PARENT_BODY = (
    "坂本勇人は試合後の取材で"
    "「最後まで集中して振り切れたんじゃないかと思います」"
    "と振り返り、300号サヨナラホームランで勝利を引き寄せた。"
)


class FlagEnablementTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop(PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG, None)

    def tearDown(self):
        os.environ.pop(PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG, None)

    def test_default_disabled(self):
        self.assertFalse(_player_voice_digest_detection_enabled())

    def test_flag_on_enables(self):
        os.environ[PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG] = "1"
        self.assertTrue(_player_voice_digest_detection_enabled())

    def test_flag_zero_disables(self):
        os.environ[PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG] = "0"
        self.assertFalse(_player_voice_digest_detection_enabled())


class AggregatorBehaviorTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop(PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG, None)

    def tearDown(self):
        os.environ.pop(PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG, None)

    def test_flag_off_returns_candidates_unchanged_no_log(self):
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(family="sanspo", title="坂本勇人サヨナラ本塁打巨人勝利連勝"),
            _cand(family="nikkansports", title="坂本勇人サヨナラ本塁打巨人勝利連勝"),
        ]
        # flag off → 関数は logger を 1 件も呼ばないはず。assertLogs は最低 1 件を
        # 期待するので、no-call を確認するには handler を手動で attach して
        # 後で record list を確認する方式に切り替える。
        seen: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                seen.append(record)

        handler = _Capture(level=logging.DEBUG)
        rss_logger = logging.getLogger("rss_fetcher")
        rss_logger.addHandler(handler)
        try:
            result = _aggregate_player_voice_digest_candidates(candidates)
        finally:
            rss_logger.removeHandler(handler)
        self.assertIs(result, candidates)
        digest_records = [
            r for r in seen if "player_voice_digest" in r.getMessage()
        ]
        self.assertEqual(digest_records, [])

    def test_empty_candidates_returns_empty(self):
        os.environ[PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG] = "1"
        result = _aggregate_player_voice_digest_candidates([])
        self.assertEqual(result, [])

    def test_flag_on_no_clusters_logs_zero(self):
        os.environ[PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG] = "1"
        # only 2 families, not enough for clustering (min 3)
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(family="sanspo", title="坂本勇人サヨナラ本塁打巨人勝利連勝"),
        ]
        with self.assertLogs("rss_fetcher", level="INFO") as logs:
            result = _aggregate_player_voice_digest_candidates(candidates)
        self.assertIs(result, candidates)
        zero_logs = [
            m
            for m in logs.output
            if "player_voice_digest_detection" in m and "clusters=0" in m
        ]
        self.assertEqual(len(zero_logs), 1)

    def test_flag_on_detected_cluster_logs_info(self):
        os.environ[PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG] = "1"
        # 31 char title for snippet
        long_title = "坂本勇人のサヨナラ本塁打が決勝点、巨人が劇的勝利で連勝を伸ばす"
        candidates = [
            _cand(family="hochi", body=_PARENT_BODY),
            _cand(family="sanspo", title=long_title),
            _cand(family="nikkansports", title=long_title),
        ]
        with self.assertLogs("rss_fetcher", level="INFO") as logs:
            result = _aggregate_player_voice_digest_candidates(candidates)
        self.assertIs(result, candidates)
        cluster_logs = [
            m for m in logs.output if "player_voice_digest_cluster_detected" in m
        ]
        self.assertEqual(len(cluster_logs), 1)
        self.assertIn("game_id=g1", cluster_logs[0])
        self.assertIn("player=坂本勇人", cluster_logs[0])
        self.assertIn("parent_family=hochi", cluster_logs[0])

    def test_exception_in_clusterer_does_not_break_main_flow(self):
        os.environ[PLAYER_VOICE_DIGEST_DETECTION_ENV_FLAG] = "1"

        original = rss_fetcher._find_player_voice_digest_clusters

        def _raise(*args, **kwargs):
            raise RuntimeError("simulated clusterer failure")

        rss_fetcher._find_player_voice_digest_clusters = _raise
        try:
            candidates = [
                _cand(family="hochi", body=_PARENT_BODY),
                _cand(family="sanspo", title="坂本勇人"),
            ]
            with self.assertLogs("rss_fetcher", level="WARNING") as logs:
                result = _aggregate_player_voice_digest_candidates(candidates)
        finally:
            rss_fetcher._find_player_voice_digest_clusters = original

        self.assertIs(result, candidates)
        fail_logs = [
            m for m in logs.output if "player_voice_digest_detection_failed" in m
        ]
        self.assertEqual(len(fail_logs), 1)


if __name__ == "__main__":
    unittest.main()
