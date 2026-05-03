import logging
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src import rss_fetcher
from src import weak_title_rescue


SOURCE_NAME = "報知 巨人"
SOURCE_URL = "https://example.com/story"
NOW = datetime(2026, 5, 3, 21, 0, tzinfo=rss_fetcher.JST)


class SubtypeAwareRescueTests(unittest.TestCase):
    def _rescue(
        self,
        *,
        rewritten_title: str,
        source_title: str,
        summary: str,
        article_subtype: str,
        category: str,
        metadata: dict[str, object] | None = None,
    ) -> tuple[str, str | None]:
        with patch.dict(
            "os.environ",
            {
                rss_fetcher.WEAK_TITLE_RESCUE_ENV_FLAG: "1",
                rss_fetcher.NARROW_UNLOCK_SUBTYPE_AWARE_ENV_FLAG: "1",
            },
            clear=False,
        ):
            return rss_fetcher._maybe_apply_weak_title_rescue(
                rewritten_title=rewritten_title,
                source_title=source_title,
                source_body=summary,
                summary=summary,
                category=category,
                article_subtype=article_subtype,
                logger=logging.getLogger("test_narrow_unlock_subtype_aware"),
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                metadata=metadata,
            )

    def _allow(
        self,
        *,
        title: str,
        article_subtype: str,
        source_title: str,
        summary: str,
        metadata: dict[str, object] | None = None,
        source_url: str = SOURCE_URL,
        duplicate_guard_context: dict[str, object] | None = None,
        body_contract_validate: dict[str, object] | None = None,
        numeric_guard_ok: bool = True,
        placeholder_residual: bool = False,
        stale_postgame: bool = False,
    ) -> bool:
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_SUBTYPE_AWARE_ENV_FLAG: "1"}, clear=False):
            return rss_fetcher._allow_narrow_unlock_candidate(
                title=title,
                article_subtype=article_subtype,
                source_name=SOURCE_NAME,
                source_url=source_url,
                source_title=source_title,
                source_body=summary,
                summary=summary,
                metadata=metadata,
                weak_reason="blacklist_phrase:結果のポイント",
                duplicate_guard_context=duplicate_guard_context,
                body_contract_validate=body_contract_validate,
                numeric_guard_ok=numeric_guard_ok,
                placeholder_residual=placeholder_residual,
                stale_postgame=stale_postgame,
                current_time=NOW,
            )

    def test_postgame_unlocks_with_recent_score_and_opponent(self):
        allowed = self._allow(
            title="試合結果 巨人 阪神 3-2 結果のポイント",
            article_subtype="postgame",
            source_title="【巨人】阪神に3-2で勝利",
            summary="巨人が阪神に3-2で勝利した。",
            metadata={"published_at": NOW, "score": "3-2", "opponent": "阪神"},
        )

        self.assertTrue(allowed)

    def test_coach_comment_rescue_unlocks_with_quote(self):
        title, reason = self._rescue(
            rewritten_title="コーチコメント整理",
            source_title="【巨人】川相コーチ「守備から入る」試合前コメント",
            summary="川相コーチが「守備から入る」と話した。",
            article_subtype="coach_comment",
            category="首脳陣",
            metadata={"article_subtype": "coach_comment", "speaker": "川相", "role": "コーチ"},
        )

        self.assertEqual(title, "川相コーチ「守備から入る」")
        self.assertIsNotNone(reason)
        self.assertTrue(str(reason).startswith("weak_generated_title:"))
        self.assertTrue(
            self._allow(
                title=title,
                article_subtype="coach_comment",
                source_title="【巨人】川相コーチ「守備から入る」試合前コメント",
                summary="川相コーチが「守備から入る」と話した。",
                metadata={"article_subtype": "coach_comment", "speaker": "川相", "role": "コーチ"},
            )
        )

    def test_player_comment_rescue_unlocks_with_quote(self):
        title, reason = self._rescue(
            rewritten_title="選手コメント整理",
            source_title="【巨人】浅野翔吾「手応えはあった」試合後コメント",
            summary="浅野翔吾が「手応えはあった」と振り返った。",
            article_subtype="player_comment",
            category="選手情報",
            metadata={"article_subtype": "player_comment", "player_name": "浅野翔吾", "role": "選手"},
        )

        self.assertEqual(title, "浅野翔吾「手応えはあった」")
        self.assertIsNotNone(reason)
        self.assertTrue(str(reason).startswith("weak_generated_title:"))
        self.assertTrue(
            self._allow(
                title=title,
                article_subtype="player_comment",
                source_title="【巨人】浅野翔吾「手応えはあった」試合後コメント",
                summary="浅野翔吾が「手応えはあった」と振り返った。",
                metadata={"article_subtype": "player_comment", "player_name": "浅野翔吾", "role": "選手"},
            )
        )

    def test_farm_result_rescue_unlocks_with_score(self):
        title, reason = self._rescue(
            rewritten_title="二軍 発言ポイント",
            source_title="【巨人2軍】ロッテに3-2で勝利",
            summary="巨人2軍がロッテに3-2で勝利した。",
            article_subtype="farm_result",
            category="ドラフト・育成",
            metadata={"article_subtype": "farm_result", "farm": True, "opponent": "ロッテ", "score": "3-2"},
        )

        self.assertEqual(title, "二軍 ロッテ 3-2")
        self.assertIsNotNone(reason)
        self.assertTrue(str(reason).startswith("weak_generated_title:"))
        self.assertTrue(
            self._allow(
                title=title,
                article_subtype="farm_result",
                source_title="【巨人2軍】ロッテに3-2で勝利",
                summary="巨人2軍がロッテに3-2で勝利した。",
                metadata={"article_subtype": "farm_result", "farm": True, "opponent": "ロッテ", "score": "3-2"},
            )
        )

    def test_farm_lineup_rescue_unlocks_with_date(self):
        title, reason = self._rescue(
            rewritten_title="二軍 関連情報",
            source_title="【巨人2軍】5月3日 ロッテ戦スタメン発表",
            summary="5月3日のロッテ戦で二軍スタメンが発表された。",
            article_subtype="farm_lineup",
            category="ドラフト・育成",
            metadata={"article_subtype": "farm_lineup", "farm": True},
        )

        self.assertEqual(title, "二軍スタメン 5月3日")
        self.assertEqual(reason, "weak_subject_title:related_info_escape")
        self.assertTrue(
            self._allow(
                title=title,
                article_subtype="farm_lineup",
                source_title="【巨人2軍】5月3日 ロッテ戦スタメン発表",
                summary="5月3日のロッテ戦で二軍スタメンが発表された。",
                metadata={"article_subtype": "farm_lineup", "farm": True},
            )
        )

    def test_probable_starter_unlocks_before_start(self):
        allowed = self._allow(
            title="巨人 阪神 18:00 予告先発 注目ポイント",
            article_subtype="probable_starter",
            source_title="【巨人】阪神戦は18:00開始、予告先発は戸郷翔征",
            summary="巨人の予告先発は戸郷翔征で、阪神戦は18:00開始。",
            metadata={
                "article_subtype": "probable_starter",
                "published_at": datetime(2026, 5, 3, 16, 0, tzinfo=rss_fetcher.JST),
                "game_time": "18:00",
            },
        )

        self.assertTrue(allowed)

    def test_roster_notice_rescue_unlocks_with_event(self):
        title, reason = self._rescue(
            rewritten_title="選手、昇格・復帰 関連情報",
            source_title="【巨人】田中将大が一軍昇格",
            summary="田中将大が一軍昇格となった。",
            article_subtype="player",
            category="選手情報",
            metadata={
                "article_subtype": "player",
                "special_story_kind": "player_notice",
                "player_name": "田中将大",
                "notice_type": "一軍昇格",
            },
        )

        self.assertEqual(title, "田中将大 一軍昇格")
        self.assertEqual(reason, "weak_subject_title:related_info_escape")
        self.assertTrue(
            self._allow(
                title=title,
                article_subtype="player",
                source_title="【巨人】田中将大が一軍昇格",
                summary="田中将大が一軍昇格となった。",
                metadata={
                    "article_subtype": "player",
                    "special_story_kind": "player_notice",
                    "player_name": "田中将大",
                    "notice_type": "一軍昇格",
                },
            )
        )

    def test_farm_player_result_rescue_unlocks_with_young_player_event(self):
        title, reason = self._rescue(
            rewritten_title="若手関連情報",
            source_title="【巨人2軍】浅野翔吾が3安打1本塁打",
            summary="巨人2軍の浅野翔吾が3安打1本塁打を記録した。",
            article_subtype="farm_player_result",
            category="ドラフト・育成",
            metadata={"article_subtype": "farm_player_result", "player_name": "浅野翔吾", "farm": True},
        )

        self.assertEqual(title, "浅野翔吾 3安打1本塁打")
        self.assertEqual(reason, "weak_subject_title:related_info_escape")
        self.assertTrue(
            self._allow(
                title=title,
                article_subtype="farm_player_result",
                source_title="【巨人2軍】浅野翔吾が3安打1本塁打",
                summary="巨人2軍の浅野翔吾が3安打1本塁打を記録した。",
                metadata={"article_subtype": "farm_player_result", "player_name": "浅野翔吾", "farm": True},
            )
        )

    def test_flag_off_keeps_subtype_aware_rescue_inert(self):
        with patch.dict("os.environ", {rss_fetcher.WEAK_TITLE_RESCUE_ENV_FLAG: "1"}, clear=False):
            title, reason = rss_fetcher._maybe_apply_weak_title_rescue(
                rewritten_title="コーチコメント整理",
                source_title="【巨人】川相コーチ「守備から入る」試合前コメント",
                source_body="川相コーチが「守備から入る」と話した。",
                summary="川相コーチが「守備から入る」と話した。",
                category="首脳陣",
                article_subtype="coach_comment",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                metadata={"article_subtype": "coach_comment", "speaker": "川相", "role": "コーチ"},
            )

        self.assertEqual(title, "コーチコメント整理")
        self.assertIsNone(reason)


class SubtypeAwareExclusionTests(unittest.TestCase):
    def _allow(self, **kwargs) -> bool:
        base = {
            "title": "田中将大 一軍昇格",
            "article_subtype": "player",
            "source_title": "【巨人】田中将大が一軍昇格",
            "summary": "田中将大が一軍昇格となった。",
            "metadata": {
                "article_subtype": "player",
                "special_story_kind": "player_notice",
                "player_name": "田中将大",
                "notice_type": "一軍昇格",
            },
        }
        base.update(kwargs)
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_SUBTYPE_AWARE_ENV_FLAG: "1"}, clear=False):
            return rss_fetcher._allow_narrow_unlock_candidate(
                title=base["title"],
                article_subtype=base["article_subtype"],
                source_name=SOURCE_NAME,
                source_url=base.get("source_url", SOURCE_URL),
                source_title=base["source_title"],
                source_body=base["summary"],
                summary=base["summary"],
                metadata=base["metadata"],
                weak_reason="related_info_escape",
                duplicate_guard_context=base.get("duplicate_guard_context"),
                body_contract_validate=base.get("body_contract_validate"),
                numeric_guard_ok=base.get("numeric_guard_ok", True),
                placeholder_residual=base.get("placeholder_residual", False),
                title_player_name_unresolved=base.get("title_player_name_unresolved", False),
                stale_postgame=base.get("stale_postgame", False),
                current_time=NOW,
            )

    def test_live_update_fragment_is_excluded(self):
        self.assertFalse(
            self._allow(
                title="九回表 田中将大 一軍昇格",
                source_title="【巨人】九回表に同点打の直後、田中将大が一軍昇格",
                summary="九回表の速報断片。",
            )
        )

    def test_placeholder_text_is_excluded(self):
        self.assertFalse(
            self._allow(
                title="田中将大 一軍昇格",
                source_title="【巨人】田中将大 結果確認中",
                summary="結果確認中のため詳細未定。",
            )
        )

    def test_unknown_subtype_is_excluded(self):
        self.assertFalse(
            self._allow(
                article_subtype="default_review",
                metadata={"article_subtype": "default_review"},
            )
        )

    def test_body_contract_fail_is_excluded(self):
        self.assertFalse(self._allow(body_contract_validate={"ok": False, "fail_axes": ["first_block_mismatch"]}))

    def test_numeric_guard_fail_is_excluded(self):
        self.assertFalse(self._allow(numeric_guard_ok=False))

    def test_non_giants_target_is_excluded(self):
        self.assertFalse(
            self._allow(
                source_title="【阪神】田中将大が一軍昇格",
                summary="阪神での昇格情報。",
                metadata={
                    "article_subtype": "player",
                    "special_story_kind": "player_notice",
                    "player_name": "田中将大",
                    "notice_type": "一軍昇格",
                    "non_giants": True,
                },
            )
        )

    def test_missing_source_url_is_excluded(self):
        self.assertFalse(self._allow(source_url=""))

    def test_duplicate_integrity_is_excluded(self):
        self.assertFalse(self._allow(duplicate_guard_context={"existing_publish_same_source_url": True}))

    def test_stale_postgame_is_excluded(self):
        self.assertFalse(
            self._allow(
                article_subtype="probable_starter",
                title="巨人 阪神 18:00 予告先発 注目ポイント",
                source_title="【巨人】阪神戦は18:00開始、予告先発は戸郷翔征",
                summary="巨人の予告先発は戸郷翔征で、阪神戦は18:00開始。",
                metadata={
                    "article_subtype": "probable_starter",
                    "published_at": datetime(2026, 5, 3, 19, 0, tzinfo=rss_fetcher.JST),
                    "game_time": "18:00",
                },
                stale_postgame=True,
            )
        )

    def test_hard_stop_signal_is_excluded(self):
        self.assertFalse(
            self._allow(
                source_title="【巨人】田中将大が救急搬送",
                summary="救急搬送についての速報。",
                metadata={
                    "article_subtype": "player",
                    "special_story_kind": "player_notice",
                    "player_name": "田中将大",
                    "notice_type": "一軍昇格",
                    "hard_stop": True,
                },
            )
        )

    def test_strict_postgame_fallback_is_excluded(self):
        with patch.dict("os.environ", {rss_fetcher.NARROW_UNLOCK_SUBTYPE_AWARE_ENV_FLAG: "1"}, clear=False):
            allowed = rss_fetcher._allow_narrow_unlock_candidate(
                title="試合結果 巨人 阪神 3-2 結果のポイント",
                article_subtype="postgame",
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_title="【巨人】阪神に3-2で勝利",
                source_body="巨人が阪神に3-2で勝利した。",
                summary="巨人が阪神に3-2で勝利した。",
                metadata={"article_subtype": "postgame", "published_at": NOW, "score": "3-2", "opponent": "阪神"},
                weak_reason="strict_review_fallback:strict_empty_response",
                current_time=NOW,
            )

        self.assertFalse(allowed)


class SubtypeAwareWeakTitleRescueHelperTests(unittest.TestCase):
    def test_subtype_aware_rescue_helper_emits_expected_strategy(self):
        result = weak_title_rescue.rescue_subtype_aware(
            gen_title="選手コメント整理",
            source_title="【巨人】浅野翔吾「手応えはあった」試合後コメント",
            body="浅野翔吾が「手応えはあった」と振り返った。",
            summary="浅野翔吾が「手応えはあった」と振り返った。",
            metadata={"article_subtype": "player_comment", "player_name": "浅野翔吾", "role": "選手"},
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.title, "浅野翔吾「手応えはあった」")
        self.assertEqual(result.strategy, "subtype_aware_player_comment")


if __name__ == "__main__":
    unittest.main()
