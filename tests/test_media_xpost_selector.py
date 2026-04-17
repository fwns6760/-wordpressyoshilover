import unittest

from src.media_xpost_selector import evaluate_media_quote_selection, select_media_quotes


class MediaXpostSelectorTests(unittest.TestCase):
    def test_social_news_returns_source_url(self):
        quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/hochi_giants/status/123",
                "source_name": "スポーツ報知巨人班X",
                "created_at": "2026-04-16T10:00:00+09:00",
            }
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["url"], "https://twitter.com/hochi_giants/status/123")
        self.assertEqual(quotes[0]["handle"], "@hochi_giants")
        self.assertEqual(quotes[0]["quote_type"], "source_tweet")

    def test_news_returns_empty_list(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "source_url": "https://twitter.com/hochi_giants/status/123",
                "source_name": "スポーツ報知巨人班X",
            }
        )

        self.assertEqual(quotes, [])

    def test_max_count_zero_returns_empty_list(self):
        quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/TokyoGiants/status/123",
            },
            max_count=0,
        )

        self.assertEqual(quotes, [])

    def test_falls_back_to_post_url_when_source_url_missing(self):
        quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "post_url": "https://x.com/TokyoGiants/status/456",
                "source_name": "巨人公式X",
            }
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["url"], "https://x.com/TokyoGiants/status/456")
        self.assertEqual(quotes[0]["handle"], "@TokyoGiants")

    def test_notice_story_matches_npb_quote_by_player_name_and_time(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "player_notice",
                "player_name": "皆川岳飛",
                "player_aliases": ["皆川岳飛", "皆川"],
                "notice_type": "一軍登録",
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            media_quote_pool=[
                {
                    "source_name": "NPB公式X",
                    "source_url": "https://twitter.com/npb/status/1",
                    "title": "【公示】4/16 巨人・皆川岳飛を出場選手登録",
                    "summary": "",
                    "created_at": "2026-04-16T09:30:00+09:00",
                }
            ],
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["url"], "https://twitter.com/npb/status/1")
        self.assertEqual(quotes[0]["section_label"], "📌 公示ポスト")
        self.assertIn(quotes[0]["match_reason"], {"composite", "player_name_match"})
        self.assertGreater(quotes[0]["match_score"], 100)

    def test_notice_story_returns_second_quote_from_official_when_available(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "player_notice",
                "player_name": "皆川岳飛",
                "player_aliases": ["皆川岳飛", "皆川"],
                "notice_type": "一軍登録",
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            max_count=2,
            media_quote_pool=[
                {
                    "source_name": "NPB公式X",
                    "source_url": "https://twitter.com/npb/status/1",
                    "title": "【公示】4/16 巨人・皆川岳飛を出場選手登録",
                    "summary": "",
                    "created_at": "2026-04-16T09:30:00+09:00",
                },
                {
                    "source_name": "巨人公式X",
                    "source_url": "https://twitter.com/TokyoGiants/status/2",
                    "title": "皆川岳飛が一軍に合流し、甲子園で練習に参加",
                    "summary": "",
                    "created_at": "2026-04-16T08:55:00+09:00",
                },
            ],
        )

        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[0]["handle"], "@npb")
        self.assertEqual(quotes[1]["handle"], "@TokyoGiants")

    def test_notice_story_rejects_npb_quote_when_player_name_does_not_match(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "player_notice",
                "player_name": "皆川岳飛",
                "player_aliases": ["皆川岳飛", "皆川"],
                "notice_type": "一軍登録",
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            media_quote_pool=[
                {
                    "source_name": "NPB公式X",
                    "source_url": "https://twitter.com/npb/status/1",
                    "title": "【公示】4/16 巨人・浅野翔吾を出場選手登録",
                    "summary": "",
                    "created_at": "2026-04-16T09:30:00+09:00",
                }
            ],
        )

        self.assertEqual(quotes, [])

    def test_notice_story_rejects_npb_quote_when_outside_time_window(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "player_notice",
                "player_name": "皆川岳飛",
                "player_aliases": ["皆川岳飛", "皆川"],
                "notice_type": "一軍登録",
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            media_quote_pool=[
                {
                    "source_name": "NPB公式X",
                    "source_url": "https://twitter.com/npb/status/1",
                    "title": "【公示】4/13 巨人・皆川岳飛を出場選手登録",
                    "summary": "",
                    "created_at": "2026-04-13T09:30:00+09:00",
                }
            ],
        )

        self.assertEqual(quotes, [])

    def test_notice_story_falls_back_to_official_quote_when_npb_missing(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "player_notice",
                "player_name": "皆川岳飛",
                "player_aliases": ["皆川岳飛", "皆川"],
                "notice_type": "一軍登録",
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            media_quote_pool=[
                {
                    "source_name": "巨人公式X",
                    "source_url": "https://twitter.com/TokyoGiants/status/99",
                    "title": "皆川岳飛が1軍に合流し、登録へ向けて調整",
                    "summary": "",
                    "created_at": "2026-04-16T09:30:00+09:00",
                }
            ],
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["url"], "https://twitter.com/TokyoGiants/status/99")
        self.assertEqual(quotes[0]["section_label"], "📌 公示ポスト")
        self.assertEqual(quotes[0]["source_class"], "official")

    def test_notice_story_respects_max_count_one(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "player_notice",
                "player_name": "皆川岳飛",
                "player_aliases": ["皆川岳飛", "皆川"],
                "notice_type": "一軍登録",
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            max_count=1,
            media_quote_pool=[
                {
                    "source_name": "NPB公式X",
                    "source_url": "https://twitter.com/npb/status/1",
                    "title": "【公示】4/16 巨人・皆川岳飛を出場選手登録",
                    "summary": "",
                    "created_at": "2026-04-16T09:30:00+09:00",
                },
                {
                    "source_name": "巨人公式X",
                    "source_url": "https://twitter.com/TokyoGiants/status/2",
                    "title": "皆川岳飛が一軍に合流し、甲子園で練習に参加",
                    "summary": "",
                    "created_at": "2026-04-16T08:55:00+09:00",
                },
            ],
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["handle"], "@npb")

    def test_manager_story_matches_media_quote_by_manager_name_and_time(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "manager_quote",
                "manager_name": "阿部監督",
                "manager_aliases": ["阿部監督", "阿部"],
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            media_quote_pool=[
                {
                    "source_name": "スポーツ報知巨人班X",
                    "source_url": "https://twitter.com/hochi_giants/status/55",
                    "title": "阿部監督が松本剛を高評価「自己犠牲ができる」",
                    "summary": "",
                    "created_at": "2026-04-16T09:15:00+09:00",
                }
            ],
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["url"], "https://twitter.com/hochi_giants/status/55")
        self.assertEqual(quotes[0]["section_label"], "📢 報道ポスト")
        self.assertEqual(quotes[0]["source_class"], "media")

    def test_manager_story_stays_single_when_only_media_exists(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "manager_quote",
                "manager_name": "阿部監督",
                "manager_aliases": ["阿部監督", "阿部"],
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            max_count=2,
            media_quote_pool=[
                {
                    "source_name": "スポーツ報知巨人班X",
                    "source_url": "https://twitter.com/hochi_giants/status/55",
                    "title": "阿部監督が松本剛を高評価「自己犠牲ができる」",
                    "summary": "",
                    "created_at": "2026-04-16T09:15:00+09:00",
                },
                {
                    "source_name": "報知野球X",
                    "source_url": "https://twitter.com/hochi_baseball/status/56",
                    "title": "阿部監督が継投を説明",
                    "summary": "",
                    "created_at": "2026-04-16T09:10:00+09:00",
                },
            ],
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["handle"], "@hochi_giants")

    def test_manager_story_rejects_media_quote_when_name_does_not_match(self):
        quotes = select_media_quotes(
            {
                "source_type": "news",
                "story_kind": "manager_quote",
                "manager_name": "阿部監督",
                "manager_aliases": ["阿部監督", "阿部"],
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            media_quote_pool=[
                {
                    "source_name": "スポーツ報知巨人班X",
                    "source_url": "https://twitter.com/hochi_giants/status/55",
                    "title": "高津監督が継投を説明",
                    "summary": "",
                    "created_at": "2026-04-16T09:15:00+09:00",
                }
            ],
        )

        self.assertEqual(quotes, [])

    def test_social_news_can_append_second_media_quote_for_same_topic(self):
        quotes = select_media_quotes(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/TokyoGiants/status/100",
                "source_name": "巨人公式X",
                "created_at": "2026-04-16T10:00:00+09:00",
                "category": "選手情報",
                "topic_aliases": ["皆川岳飛", "皆川"],
            },
            max_count=2,
            media_quote_pool=[
                {
                    "source_name": "スポーツ報知巨人班X",
                    "source_url": "https://twitter.com/hochi_giants/status/101",
                    "title": "皆川岳飛が一軍に合流して練習",
                    "summary": "",
                    "created_at": "2026-04-16T09:45:00+09:00",
                }
            ],
        )

        self.assertEqual(len(quotes), 2)
        self.assertEqual(quotes[0]["handle"], "@TokyoGiants")
        self.assertEqual(quotes[1]["handle"], "@hochi_giants")

    def test_evaluate_marks_social_news_as_target(self):
        result = evaluate_media_quote_selection(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/TokyoGiants/status/100",
                "source_name": "巨人公式X",
                "created_at": "2026-04-16T10:00:00+09:00",
                "category": "選手情報",
            }
        )

        self.assertEqual(result["selector_type"], "own_source")
        self.assertTrue(result["is_target"])
        self.assertEqual(len(result["quotes"]), 1)
        self.assertIsNone(result["skip_meta"])

    def test_evaluate_returns_pool_empty_for_notice_without_candidates(self):
        result = evaluate_media_quote_selection(
            {
                "source_type": "news",
                "story_kind": "player_notice",
                "player_name": "皆川岳飛",
                "player_aliases": ["皆川岳飛", "皆川"],
                "notice_type": "一軍登録",
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            media_quote_pool=[],
        )

        self.assertEqual(result["selector_type"], "npb_notice")
        self.assertTrue(result["is_target"])
        self.assertEqual(result["quotes"], [])
        self.assertEqual(result["skip_meta"]["skip_reason"], "pool_empty")
        self.assertEqual(result["skip_meta"]["pool_size_checked"], 0)
        self.assertIsNone(result["skip_meta"]["best_candidate_score"])

    def test_evaluate_returns_time_window_exceeded_for_old_notice_candidate(self):
        result = evaluate_media_quote_selection(
            {
                "source_type": "news",
                "story_kind": "player_notice",
                "player_name": "皆川岳飛",
                "player_aliases": ["皆川岳飛", "皆川"],
                "notice_type": "一軍登録",
                "created_at": "2026-04-16T10:00:00+09:00",
            },
            media_quote_pool=[
                {
                    "source_name": "NPB公式X",
                    "source_url": "https://twitter.com/npb/status/1",
                    "title": "【公示】4/13 巨人・皆川岳飛を出場選手登録",
                    "summary": "",
                    "created_at": "2026-04-13T09:30:00+09:00",
                }
            ],
        )

        self.assertEqual(result["quotes"], [])
        self.assertEqual(result["skip_meta"]["skip_reason"], "time_window_exceeded")
        self.assertEqual(result["skip_meta"]["best_candidate_handle"], "@npb")
        self.assertGreater(result["skip_meta"]["best_candidate_age_hours"], 48)

    def test_evaluate_returns_same_account_excluded_for_social_second_quote(self):
        result = evaluate_media_quote_selection(
            {
                "source_type": "social_news",
                "source_url": "https://twitter.com/hochi_giants/status/100",
                "source_name": "スポーツ報知巨人班X",
                "created_at": "2026-04-16T10:00:00+09:00",
                "category": "選手情報",
                "topic_aliases": ["皆川岳飛", "皆川"],
            },
            max_count=2,
            media_quote_pool=[
                {
                    "source_name": "スポーツ報知巨人班X",
                    "source_url": "https://twitter.com/hochi_giants/status/101",
                    "title": "皆川岳飛が一軍に合流して練習",
                    "summary": "",
                    "created_at": "2026-04-16T09:45:00+09:00",
                }
            ],
        )

        self.assertEqual(len(result["quotes"]), 1)
        self.assertEqual(result["skip_meta"]["skip_reason"], "same_account_excluded")
        self.assertEqual(result["skip_meta"]["pool_size_checked"], 1)
        self.assertEqual(result["skip_meta"]["best_candidate_handle"], "@hochi_giants")


if __name__ == "__main__":
    unittest.main()
