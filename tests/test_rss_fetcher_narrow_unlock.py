import logging
import unittest
from unittest.mock import MagicMock, patch

from src import rss_fetcher


SOURCE_NAME = "報知 巨人"
SOURCE_URL = "https://example.com/story"


class NarrowUnlockRouteTests(unittest.TestCase):
    def _logger(self) -> logging.Logger:
        logger = logging.getLogger("test_rss_fetcher_narrow_unlock")
        logger.info = MagicMock()
        logger.warning = MagicMock()
        return logger

    def test_flag_off_keeps_notice_title_on_review_path(self):
        with patch.dict("os.environ", {}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="notice",
                rewritten_title="泉口友汰、登録抹消 関連情報",
                original_title="【巨人】泉口友汰が登録抹消",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
            )

        self.assertIsInstance(fallback, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(fallback.reason, "related_info_escape")

    def test_player_notice_related_info_unlocks_with_flag_on(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="notice",
                rewritten_title="泉口友汰、登録抹消 関連情報",
                original_title="【巨人】泉口友汰が登録抹消",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
            )

        self.assertIsNone(fallback)

    def test_player_quote_related_info_unlocks_with_flag_on(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="player",
                rewritten_title="坂本勇人「まだまだやれる」 関連情報",
                original_title="【巨人】坂本勇人「まだまだやれる」復帰戦へ意欲",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
            )

        self.assertIsNone(fallback)

    def test_manager_quote_related_info_unlocks_with_flag_on(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="manager",
                rewritten_title="阿部監督「継投は想定通り」 関連情報",
                original_title="【巨人】阿部監督「継投は想定通り」阪神戦後に説明",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
            )

        self.assertIsNone(fallback)

    def test_lineup_particle_title_unlocks_with_flag_on(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="lineup",
                rewritten_title="巨人スタメン が「2番・二塁」で今季初先発、先発は戸郷翔征",
                original_title="【巨人】吉川尚輝が「2番・二塁」で今季初先発、先発は戸郷翔征",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
            )

        self.assertIsNone(fallback)

    def test_farm_result_blacklist_title_unlocks_with_flag_on(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_generated_title_review(
                article_subtype="farm",
                rewritten_title="二軍 浅野翔吾が3安打1本塁打 発言ポイント",
                original_title="【巨人2軍】浅野翔吾が3安打1本塁打",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
            )

        self.assertIsNone(fallback)

    def test_existing_publish_same_source_url_blocks_unlock(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="notice",
                rewritten_title="泉口友汰、登録抹消 関連情報",
                original_title="【巨人】泉口友汰が登録抹消",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
                duplicate_guard_context={"existing_publish_same_source_url": True},
            )

        self.assertIsInstance(fallback, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(fallback.reason, "related_info_escape")

    def test_title_player_name_unresolved_blocks_unlock(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="notice",
                rewritten_title="泉口友汰、登録抹消 関連情報",
                original_title="【巨人】泉口友汰が登録抹消",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
                title_player_name_unresolved=True,
            )

        self.assertIsInstance(fallback, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(fallback.reason, "related_info_escape")

    def test_body_contract_fail_blocks_unlock(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="notice",
                rewritten_title="泉口友汰、登録抹消 関連情報",
                original_title="【巨人】泉口友汰が登録抹消",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
                body_contract_validate={"ok": False, "fail_axes": ["first_block_mismatch"]},
            )

        self.assertIsInstance(fallback, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(fallback.reason, "related_info_escape")

    def test_numeric_guard_fail_blocks_unlock(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="notice",
                rewritten_title="泉口友汰、登録抹消 関連情報",
                original_title="【巨人】泉口友汰が登録抹消",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
                numeric_guard_ok=False,
            )

        self.assertIsInstance(fallback, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(fallback.reason, "related_info_escape")

    def test_placeholder_residual_blocks_unlock(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_subject_title_review(
                article_subtype="notice",
                rewritten_title="泉口友汰、登録抹消 関連情報",
                original_title="【巨人】泉口友汰が登録抹消",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
                placeholder_residual=True,
            )

        self.assertIsInstance(fallback, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(fallback.reason, "related_info_escape")

    def test_subtype_misclassify_blocks_unlock(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            fallback = rss_fetcher._maybe_route_weak_generated_title_review(
                article_subtype="manager",
                rewritten_title="巨人スタメン 阪神戦 吉川尚輝が2番二塁、先発は戸郷翔征 発言ポイント",
                original_title="【巨人】阿部監督がスタメン意図を説明",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                logger=self._logger(),
            )

        self.assertIsInstance(fallback, rss_fetcher._WeakTitleReviewFallback)
        self.assertEqual(fallback.reason, "blacklist_phrase:発言ポイント")


class NarrowUnlockHelperExclusionTests(unittest.TestCase):
    def test_postgame_strict_fallback_is_never_allowlisted(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            allowed = rss_fetcher._allow_narrow_unlock_candidate(
                title="巨人3-2勝利 試合結果のポイント",
                article_subtype="postgame",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                weak_reason="strict_review_fallback:strict_empty_response",
            )

        self.assertFalse(allowed)

    def test_stale_postgame_signal_is_never_allowlisted(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_NON_POSTGAME_ENV_FLAG: "1"}, clear=False):
            allowed = rss_fetcher._allow_narrow_unlock_candidate(
                title="泉口友汰、登録抹消 関連情報",
                article_subtype="notice",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                weak_reason="related_info_escape",
                stale_postgame=True,
            )

        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
