import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from src import rss_fetcher


JST = timezone(timedelta(hours=9))

POSTGAME_TITLE = "巨人勝利 阿部監督がコメント"
POSTGAME_SUMMARY = "巨人は本拠地で勝利した"


class PostgameMorningWindowTests(unittest.TestCase):
    def _call(
        self,
        *,
        category: str = "試合速報",
        title: str = POSTGAME_TITLE,
        summary: str = POSTGAME_SUMMARY,
        source_published_at: datetime | None,
        now_jst: datetime | None,
        cutoff_hour: int | None = None,
        force_postgame: bool = True,
    ) -> bool:
        if force_postgame:
            ctx = patch.object(
                rss_fetcher, "_detect_article_subtype", return_value="postgame"
            )
        else:
            ctx = patch.object(
                rss_fetcher, "_detect_article_subtype",
                wraps=rss_fetcher._detect_article_subtype,
            )
        with ctx:
            return rss_fetcher._should_skip_postgame_after_morning_window(
                category,
                title,
                summary,
                source_published_at,
                now_jst=now_jst,
                cutoff_hour=cutoff_hour,
            )

    def test_morning_publish_within_window_keeps_article(self):
        pub = datetime(2026, 5, 14, 6, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 11, 0, tzinfo=JST)
        self.assertFalse(self._call(source_published_at=pub, now_jst=now))

    def test_afternoon_publish_after_morning_skip_actual_incident(self):
        # 67366 / 67369 reproduction: RSS arrived 5/14 AM, publish attempt 5/14 17:31 JST.
        pub = datetime(2026, 5, 14, 6, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 17, 31, tzinfo=JST)
        self.assertTrue(self._call(source_published_at=pub, now_jst=now))

    def test_day_game_postgame_late_afternoon_keeps_article(self):
        # デーゲーム postgame: source 配信が 16:00 JST 以降なら朝刊扱いしない。
        pub = datetime(2026, 5, 14, 16, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 17, 30, tzinfo=JST)
        self.assertFalse(self._call(source_published_at=pub, now_jst=now))

    def test_different_day_source_delegates_to_existing_stale_path(self):
        pub = datetime(2026, 5, 13, 23, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 17, 31, tzinfo=JST)
        self.assertFalse(self._call(source_published_at=pub, now_jst=now))

    def test_cutoff_env_override_pushes_window_back(self):
        pub = datetime(2026, 5, 14, 6, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 13, 30, tzinfo=JST)
        self.assertTrue(self._call(source_published_at=pub, now_jst=now))
        self.assertFalse(self._call(source_published_at=pub, now_jst=now, cutoff_hour=14))

    def test_non_postgame_category_keeps_article(self):
        pub = datetime(2026, 5, 14, 6, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 17, 31, tzinfo=JST)
        self.assertFalse(
            self._call(
                category="選手情報",
                source_published_at=pub,
                now_jst=now,
                force_postgame=False,
            )
        )

    def test_non_postgame_subtype_keeps_article(self):
        pub = datetime(2026, 5, 14, 6, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 17, 31, tzinfo=JST)
        with patch.object(
            rss_fetcher, "_detect_article_subtype", return_value="pregame"
        ):
            self.assertFalse(
                rss_fetcher._should_skip_postgame_after_morning_window(
                    "試合速報",
                    POSTGAME_TITLE,
                    POSTGAME_SUMMARY,
                    pub,
                    now_jst=now,
                )
            )

    def test_missing_source_published_keeps_article(self):
        now = datetime(2026, 5, 14, 17, 31, tzinfo=JST)
        self.assertFalse(self._call(source_published_at=None, now_jst=now))

    def test_invalid_cutoff_hour_disables_gate(self):
        pub = datetime(2026, 5, 14, 6, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 17, 31, tzinfo=JST)
        self.assertFalse(self._call(source_published_at=pub, now_jst=now, cutoff_hour=0))
        self.assertFalse(self._call(source_published_at=pub, now_jst=now, cutoff_hour=24))

    def test_env_var_consumed_when_cutoff_not_passed(self):
        pub = datetime(2026, 5, 14, 6, 0, tzinfo=JST)
        now = datetime(2026, 5, 14, 13, 30, tzinfo=JST)
        with patch.dict(os.environ, {"STALE_POSTGAME_MORNING_CUTOFF_HOUR": "14"}, clear=False):
            self.assertFalse(self._call(source_published_at=pub, now_jst=now))
        with patch.dict(os.environ, {"STALE_POSTGAME_MORNING_CUTOFF_HOUR": "13"}, clear=False):
            self.assertTrue(self._call(source_published_at=pub, now_jst=now))

    def test_utc_source_normalized_to_jst(self):
        # source_published_at が UTC 表記でも JST 換算で同日扱い。
        pub_utc = datetime(2026, 5, 13, 21, 0, tzinfo=timezone.utc)  # = 5/14 06:00 JST
        now = datetime(2026, 5, 14, 17, 31, tzinfo=JST)
        self.assertTrue(self._call(source_published_at=pub_utc, now_jst=now))


if __name__ == "__main__":
    unittest.main()
