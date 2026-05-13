import json
import logging
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src import rss_fetcher


class RssFetcherObservabilityTests(unittest.TestCase):
    def _run_main_once(
        self,
        *,
        entry_link: str,
        roles: list[str] | None = None,
        source_type: str = "news",
        title: str = "巨人4-0で阪神に勝利",
        summary: str = "試合後のコメントあり",
        source_id_mock: Mock | None = None,
        trust_url_mock: Mock | None = None,
        trust_handle_mock: Mock | None = None,
    ) -> tuple[Mock, Mock, Mock]:
        roles = roles or ["article_source"]
        source_id_mock = source_id_mock or Mock(return_value="observed-source-id")
        trust_url_mock = trust_url_mock or Mock(return_value="secondary")
        trust_handle_mock = trust_handle_mock or Mock(return_value="primary")
        entry = {"title": title, "summary": summary, "link": entry_link}
        args = Namespace(dry_run=True, draft_only=False, limit=10, article_ai_mode=None)

        with tempfile.TemporaryDirectory() as tmpdir, ExitStack() as stack:
            tmpdir_path = Path(tmpdir)
            sources_file = tmpdir_path / "rss_sources.json"
            keywords_file = tmpdir_path / "keywords.json"
            sources_file.write_text(
                json.dumps(
                    [
                        {
                            "name": "テストソース",
                            "url": "https://feed.example.com/rss.xml",
                            "type": source_type,
                            "role": roles,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            keywords_file.write_text(
                json.dumps({"選手情報": ["巨人"]}, ensure_ascii=False),
                encoding="utf-8",
            )

            stack.enter_context(patch.object(rss_fetcher, "RSS_SOURCES_FILE", sources_file))
            stack.enter_context(patch.object(rss_fetcher, "KEYWORDS_FILE", keywords_file))
            stack.enter_context(patch.object(rss_fetcher, "check_giants_game_today", return_value=(False, "", "")))
            stack.enter_context(patch.object(rss_fetcher, "load_history", return_value={}))
            stack.enter_context(patch.object(rss_fetcher.feedparser, "parse", return_value=SimpleNamespace(entries=[entry])))
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_entry_published_datetime",
                    return_value=datetime(2026, 4, 21, 12, 0, 0),
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_entry_day_key", return_value="2026-04-21"))
            stack.enter_context(
                patch.object(rss_fetcher, "_aggregate_lineup_candidates", side_effect=lambda items: items)
            )
            stack.enter_context(patch.object(rss_fetcher, "_should_skip_stale_postgame_entry", return_value=False))
            stack.enter_context(patch.object(rss_fetcher, "_should_skip_stale_player_status_entry", return_value=False))
            stack.enter_context(patch.object(rss_fetcher, "_is_promotional_video_entry", return_value=False))
            stack.enter_context(patch.object(rss_fetcher, "_detect_article_subtype", return_value="player"))
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_source_fact_block_metrics",
                    return_value=("x" * 200, 200),
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_is_thin_source_fact_block", return_value=False))
            stack.enter_context(
                patch.object(
                    rss_fetcher,
                    "_rewrite_display_title_with_template",
                    return_value=("観測テストタイトル", "observability_test"),
                )
            )
            stack.enter_context(patch.object(rss_fetcher, "_log_title_template_selected"))
            stack.enter_context(patch.object(rss_fetcher, "_source_id_key", source_id_mock))
            stack.enter_context(patch.object(rss_fetcher, "_source_trust_classify_url", trust_url_mock))
            stack.enter_context(patch.object(rss_fetcher, "_source_trust_classify_handle", trust_handle_mock))

            rss_fetcher._main(args, logging.getLogger("rss_fetcher"))

        return source_id_mock, trust_url_mock, trust_handle_mock

    def test_source_id_observation_calls_source_id_key(self):
        source_id_mock = Mock(return_value="normalized-source-id")

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            self._run_main_once(
                entry_link="https://hochi.news/articles/2026/04/21/12345.html?utm_source=social",
                source_id_mock=source_id_mock,
            )

        source_id_mock.assert_called_once_with(
            "https://hochi.news/articles/2026/04/21/12345.html?utm_source=social"
        )
        self.assertIn("source_id=normalized-source-id", "\n".join(cm.output))

    def test_source_trust_observation_uses_handle_classifier_for_x_status(self):
        trust_url_mock = Mock(return_value="secondary")
        trust_handle_mock = Mock(return_value="primary")

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            self._run_main_once(
                entry_link="https://x.com/TokyoGiants/status/19001?ref_src=twsrc",
                trust_url_mock=trust_url_mock,
                trust_handle_mock=trust_handle_mock,
            )

        trust_handle_mock.assert_called_once_with("@TokyoGiants")
        trust_url_mock.assert_not_called()
        self.assertIn("source_trust=primary", "\n".join(cm.output))

    def test_tag_category_guard_observation_logs_warnings(self):
        roles = [f"role{i}" for i in range(21)]

        with self.assertLogs("rss_fetcher", level="INFO") as cm:
            self._run_main_once(
                entry_link="https://hochi.news/articles/2026/04/21/67890.html",
                roles=roles,
            )

        self.assertIn(
            'tag_category_warnings=["too many tags: 21 > 20"]',
            "\n".join(cm.output),
        )

    def test_game_live_window_blocks_default_article_sources(self):
        live_now = datetime(2026, 5, 12, 18, 0, tzinfo=timezone(timedelta(hours=9)))
        default_roles = rss_fetcher._source_roles_from_config(None)

        self.assertTrue(rss_fetcher._is_game_live_source_policy_window(live_now))
        self.assertFalse(
            rss_fetcher._source_allowed_by_game_live_policy(default_roles, now=live_now)
        )

    def test_game_live_window_allows_hochi_and_dazn_roles(self):
        live_now = datetime(2026, 5, 12, 18, 0, tzinfo=timezone(timedelta(hours=9)))

        self.assertTrue(
            rss_fetcher._source_allowed_by_game_live_policy(
                {"article_source", "game_live_primary"},
                now=live_now,
            )
        )
        self.assertTrue(
            rss_fetcher._source_allowed_by_game_live_policy(
                {"media_quote_only", "game_live_video_signal", "review_only"},
                now=live_now,
            )
        )

    def test_game_live_window_ends_at_2130_jst(self):
        after_window = datetime(2026, 5, 12, 21, 30, tzinfo=timezone(timedelta(hours=9)))

        self.assertFalse(rss_fetcher._is_game_live_source_policy_window(after_window))
        self.assertTrue(
            rss_fetcher._source_allowed_by_game_live_policy(
                {"article_source"},
                now=after_window,
            )
        )

    def test_main_skips_non_live_sources_during_game_live_policy(self):
        args = Namespace(dry_run=True, draft_only=False, limit=10, article_ai_mode=None)

        with tempfile.TemporaryDirectory() as tmpdir, ExitStack() as stack:
            tmpdir_path = Path(tmpdir)
            sources_file = tmpdir_path / "rss_sources.json"
            keywords_file = tmpdir_path / "keywords.json"
            sources_file.write_text(
                json.dumps(
                    [
                        {
                            "name": "日刊スポーツX",
                            "url": "https://feed.example.com/nikkan.xml",
                            "type": "news",
                            "role": ["article_source"],
                        },
                        {
                            "name": "スポーツ報知巨人班X",
                            "url": "https://feed.example.com/hochi.xml",
                            "type": "news",
                            "role": ["article_source", "game_live_primary"],
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            keywords_file.write_text(
                json.dumps({"選手情報": ["巨人"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            parse_mock = Mock(return_value=SimpleNamespace(entries=[]))

            stack.enter_context(patch.object(rss_fetcher, "RSS_SOURCES_FILE", sources_file))
            stack.enter_context(patch.object(rss_fetcher, "KEYWORDS_FILE", keywords_file))
            stack.enter_context(patch.object(rss_fetcher, "check_giants_game_today", return_value=(True, "中日", "東京ドーム")))
            stack.enter_context(patch.object(rss_fetcher, "load_history", return_value={}))
            stack.enter_context(patch.object(rss_fetcher.feedparser, "parse", parse_mock))
            stack.enter_context(patch.object(rss_fetcher, "_is_game_live_source_policy_window", return_value=True))

            with self.assertLogs("rss_fetcher", level="INFO") as cm:
                rss_fetcher._main(args, logging.getLogger("rss_fetcher"))

        parse_mock.assert_called_once_with("https://feed.example.com/hochi.xml")
        logs = "\n".join(cm.output)
        self.assertIn('"event": "game_live_source_policy_skip"', logs)
        self.assertIn('"source_name": "日刊スポーツX"', logs)
        self.assertIn('"game_live_source_policy_active": true', logs)
        self.assertIn('"game_live_source_policy_skipped_sources": 1', logs)


if __name__ == "__main__":
    unittest.main()
