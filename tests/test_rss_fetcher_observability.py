import json
import logging
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack
from datetime import datetime
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
        title: str = "巨人・阿部監督「コメント」",
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


if __name__ == "__main__":
    unittest.main()
