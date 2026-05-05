import inspect
import json
import os
import unittest
from unittest.mock import patch

from src import rss_fetcher
from src import title_validator


FLAG = rss_fetcher.ENABLE_MANAGER_QUOTE_SHORT_TITLE_REPAIR_ENV_FLAG


class ManagerQuoteShortTitleRepairTests(unittest.TestCase):
    def test_flag_off_keeps_bench_comment_fallback(self):
        with patch.dict(os.environ, {FLAG: "0"}, clear=False):
            rewritten_title, template_key = rss_fetcher._rewrite_display_title_with_template(
                "【巨人】阿部監督が起用方針を説明",
                "阿部監督が今後の起用方針について説明した。",
                "首脳陣",
                False,
            )
            repaired_title = rss_fetcher._maybe_apply_manager_quote_short_title_repair(
                rewritten_title=rewritten_title,
                source_title="【巨人】阿部監督が起用方針を説明",
                source_body="阿部監督が今後の起用方針について説明した。",
                summary="阿部監督が今後の起用方針について説明した。",
                category="首脳陣",
                article_subtype="manager",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                source_url="https://example.com/manager-comment",
                metadata={"manager_name": "阿部監督"},
            )

        self.assertEqual(template_key, "manager_generic")
        self.assertEqual(rewritten_title, "阿部コメント整理 ベンチ関連の発言ポイント")
        self.assertEqual(repaired_title, rewritten_title)

    def test_flag_on_repairs_to_player_quote_when_name_and_action_present(self):
        with patch.dict(os.environ, {FLAG: "1"}, clear=False):
            repaired_title = rss_fetcher._maybe_apply_manager_quote_short_title_repair(
                rewritten_title="首脳陣コメント整理 ベンチ関連の発言ポイント",
                source_title="【巨人】戸郷翔征が試合を振り返る",
                source_body="戸郷翔征は「不用意な1球を減らしていけばまた勝てる」と振り返った。",
                summary="戸郷翔征は「不用意な1球を減らしていけばまた勝てる」と振り返った。",
                category="首脳陣",
                article_subtype="manager",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                source_url="https://example.com/player-quote",
                metadata={"player_name": "戸郷翔征"},
            )

        self.assertEqual(repaired_title, "戸郷翔征「不用意な1球を減らしていけばまた勝てる」")

    def test_flag_on_repairs_to_short_form_when_quote_missing(self):
        with patch.dict(os.environ, {FLAG: "1"}, clear=False):
            repaired_title = rss_fetcher._maybe_apply_manager_quote_short_title_repair(
                rewritten_title="阿部コメント整理 ベンチ関連の発言ポイント",
                source_title="【巨人】阿部監督が起用方針を説明",
                source_body="阿部監督が今後の起用方針について説明した。",
                summary="阿部監督が今後の起用方針について説明した。",
                category="首脳陣",
                article_subtype="manager",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                source_url="https://example.com/no-quote",
                metadata={"manager_name": "阿部監督"},
            )

        self.assertEqual(repaired_title, "阿部監督のコメント")

    def test_flag_on_keeps_review_when_no_name_or_action(self):
        logger = rss_fetcher.logging.getLogger("rss_fetcher")

        with patch.dict(os.environ, {FLAG: "1"}, clear=False):
            repaired_title = rss_fetcher._maybe_apply_manager_quote_short_title_repair(
                rewritten_title="首脳陣コメント整理 ベンチ関連の発言ポイント",
                source_title="【巨人】ベンチの動きを整理",
                source_body="今後の見通しを整理した。",
                summary="今後の見通しを整理した。",
                category="首脳陣",
                article_subtype="manager",
                logger=logger,
                source_url="https://example.com/review",
            )
            fallback = rss_fetcher._maybe_route_weak_generated_title_review(
                article_subtype="manager",
                rewritten_title=repaired_title,
                original_title="【巨人】ベンチの動きを整理",
                source_name="報知 巨人",
                logger=logger,
                source_url="https://example.com/review",
                source_title="【巨人】ベンチの動きを整理",
                source_body="今後の見通しを整理した。",
                summary="今後の見通しを整理した。",
                metadata={},
            )

        self.assertEqual(repaired_title, "首脳陣コメント整理 ベンチ関連の発言ポイント")
        self.assertIsInstance(fallback, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(fallback.reason, "blacklist_phrase:ベンチ関連の発言ポイント")

    def test_flag_on_emits_structured_log(self):
        with patch.dict(os.environ, {FLAG: "1"}, clear=False):
            with self.assertLogs("rss_fetcher", level="INFO") as captured:
                repaired_title = rss_fetcher._maybe_apply_manager_quote_short_title_repair(
                    rewritten_title="首脳陣コメント整理 ベンチ関連の発言ポイント",
                    source_title="【巨人】戸郷翔征が試合を振り返る",
                    source_body="戸郷翔征は「不用意な1球を減らしていけばまた勝てる」と振り返った。",
                    summary="戸郷翔征は「不用意な1球を減らしていけばまた勝てる」と振り返った。",
                    category="首脳陣",
                    article_subtype="manager",
                    logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                    source_url="https://example.com/player-quote",
                    metadata={"player_name": "戸郷翔征"},
                )

        payload = json.loads(captured.records[-1].getMessage())
        self.assertEqual(repaired_title, "戸郷翔征「不用意な1球を減らしていけばまた勝てる」")
        self.assertEqual(payload["event"], "manager_quote_short_title_repaired")
        self.assertEqual(payload["source_url"], "https://example.com/player-quote")
        self.assertEqual(payload["original_fallback_title"], "首脳陣コメント整理 ベンチ関連の発言ポイント")
        self.assertEqual(payload["repaired_title"], repaired_title)
        self.assertEqual(payload["name_extracted"], "戸郷翔征")
        self.assertEqual(payload["quote_extracted"], "不用意な1球を減らしていけばまた勝てる")

    def test_flag_on_does_not_relax_validator_threshold(self):
        source = inspect.getsource(title_validator.is_weak_generated_title)

        self.assertIn("len(normalized) < 12", source)
        self.assertEqual(title_validator.is_weak_generated_title("巨人岡本和真が一軍復帰"), (True, "title_too_short"))
        self.assertEqual(title_validator.is_weak_generated_title("巨人岡本和真が一軍復帰へ"), (False, ""))


if __name__ == "__main__":
    unittest.main()
