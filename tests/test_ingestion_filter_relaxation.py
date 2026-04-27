import json
import logging
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src import rss_fetcher


class IngestionFilterRelaxationTests(unittest.TestCase):
    def _fixed_datetime(self, now_value: datetime):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz:
                    return now_value.astimezone(tz)
                return now_value.replace(tzinfo=None)

        return FixedDateTime

    def test_is_giants_related_accepts_curated_alias_without_team_keyword(self):
        self.assertTrue(rss_fetcher.is_giants_related("オコエが先発出場へ向けて調整した。"))

    def test_is_giants_related_accepts_hashtag_signal_from_social_text(self):
        self.assertTrue(rss_fetcher.is_giants_related("#yomiurigiants 若手起用の方針を整理した投稿"))

    def test_is_giants_related_rejects_other_team_transfer_story_for_curated_alias(self):
        self.assertFalse(rss_fetcher.is_giants_related("阪神がオコエ瑠偉の獲得を検討、FA補強の候補に挙げた。"))

    def test_is_polluted_social_entry_keeps_skipping_untrusted_hashtag_post(self):
        self.assertTrue(
            rss_fetcher._is_polluted_social_entry(
                "岡本和真が打撃練習を再開 #GIANTS",
                "",
                source_name="一般SNS",
                post_url="https://x.com/genericfan/status/1",
            )
        )

    def test_is_polluted_social_entry_allows_trusted_media_handle(self):
        self.assertFalse(
            rss_fetcher._is_polluted_social_entry(
                "岡本和真が打撃練習を再開 #GIANTS",
                "",
                source_name="スポーツ報知X",
                post_url="https://x.com/SportsHochi/status/1",
            )
        )

    def test_evaluate_authoritative_social_entry_rescues_trusted_player_update(self):
        worthy, rescue_meta = rss_fetcher._evaluate_authoritative_social_entry(
            "岡本和真が打撃練習を再開し、状態を確認",
            "",
            "選手情報",
            "player",
            source_name="スポーツ報知X",
            source_handle="@SportsHochi",
        )
        self.assertTrue(worthy)
        self.assertEqual(rescue_meta, {"rescue_reason": "trusted_social_source", "matched_word": "打撃練習"})

    def test_evaluate_authoritative_social_entry_keeps_rejecting_generic_trusted_post(self):
        worthy, rescue_meta = rss_fetcher._evaluate_authoritative_social_entry(
            "本日も応援よろしくお願いします",
            "球場の雰囲気をお楽しみください",
            "球団情報",
            "general",
            source_name="巨人公式X",
            source_handle="@TokyoGiants",
        )
        self.assertFalse(worthy)
        self.assertIsNone(rescue_meta)

    def test_is_giants_related_accepts_exclusive_social_handle_without_team_keyword(self):
        self.assertTrue(
            rss_fetcher.is_giants_related(
                "先発発表です",
                source_name="巨人公式X",
                post_url="https://x.com/TokyoGiants/status/12345",
            )
        )

    def test_stale_postgame_36_hour_window_boundaries(self):
        fixed_now = datetime(2026, 4, 27, 20, 0, tzinfo=rss_fetcher.JST)
        recent_previous_day = datetime(2026, 4, 26, 12, 30, tzinfo=rss_fetcher.JST).astimezone(timezone.utc)
        older_story = datetime(2026, 4, 26, 2, 30, tzinfo=rss_fetcher.JST).astimezone(timezone.utc)

        with patch.object(rss_fetcher, "datetime", self._fixed_datetime(fixed_now)):
            with self.subTest("within_36h"):
                self.assertFalse(
                    rss_fetcher._should_skip_stale_postgame_entry(
                        "試合速報",
                        "巨人4-0勝利",
                        "岡本和真が決勝打で巨人が勝利した。",
                        recent_previous_day,
                        max_age_hours=36,
                    )
                )
            with self.subTest("over_36h"):
                self.assertTrue(
                    rss_fetcher._should_skip_stale_postgame_entry(
                        "試合速報",
                        "巨人4-0勝利",
                        "岡本和真が決勝打で巨人が勝利した。",
                        older_story,
                        max_age_hours=36,
                    )
                )

    def test_main_passes_36_hour_window_for_postgame_skip_check(self):
        args = Namespace(dry_run=True, draft_only=False, limit=10, article_ai_mode=None)
        entry = {
            "title": "巨人4-0勝利",
            "summary": "岡本和真が決勝打で巨人が勝利した。",
            "link": "https://hochi.news/articles/20260427-OHT1T51111.html",
        }
        skip_mock = Mock(return_value=True)

        with tempfile.TemporaryDirectory() as tmpdir, ExitStack() as stack:
            tmpdir_path = Path(tmpdir)
            sources_file = tmpdir_path / "rss_sources.json"
            keywords_file = tmpdir_path / "keywords.json"
            sources_file.write_text(
                json.dumps(
                    [
                        {
                            "name": "テストニュース",
                            "url": "https://feed.example.com/rss.xml",
                            "type": "news",
                            "role": ["article_source"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            keywords_file.write_text(json.dumps({"試合速報": ["勝利"]}, ensure_ascii=False), encoding="utf-8")

            stack.enter_context(patch.object(rss_fetcher, "RSS_SOURCES_FILE", sources_file))
            stack.enter_context(patch.object(rss_fetcher, "KEYWORDS_FILE", keywords_file))
            stack.enter_context(patch.object(rss_fetcher, "check_giants_game_today", return_value=(True, "阪神", "東京ドーム")))
            stack.enter_context(patch.object(rss_fetcher, "load_history", return_value={}))
            stack.enter_context(patch.object(rss_fetcher.feedparser, "parse", return_value=SimpleNamespace(entries=[entry])))
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_entry_published_datetime",
                    return_value=datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc),
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_entry_day_key", return_value="2026-04-27"))
            stack.enter_context(patch.object(rss_fetcher, "_aggregate_lineup_candidates", side_effect=lambda items: items))
            stack.enter_context(patch.object(rss_fetcher, "_should_skip_stale_postgame_entry", skip_mock))
            stack.enter_context(patch.object(rss_fetcher, "_should_skip_stale_player_status_entry", return_value=False))
            stack.enter_context(patch.object(rss_fetcher, "_source_id_key", return_value="test-source-id"))
            stack.enter_context(patch.object(rss_fetcher, "_source_trust_classify_url", return_value="secondary"))
            stack.enter_context(patch.object(rss_fetcher, "_source_trust_classify_handle", return_value="secondary"))
            stack.enter_context(patch.object(rss_fetcher, "_is_history_duplicate", return_value=False))

            rss_fetcher._main(args, logging.getLogger("rss_fetcher"))

        self.assertEqual(skip_mock.call_count, 1)
        self.assertEqual(skip_mock.call_args.kwargs["max_age_hours"], 36)


if __name__ == "__main__":
    unittest.main()
