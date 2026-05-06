"""RSS-251: sns_polluted narrow rescue tests.

`_is_polluted_social_entry` の strict trusted check で漏れた trusted-likely
Giants social の false positive を、AND 3条件 (handle/name soft match +
is_giants_related + important keyword) で救うことを pin する。

publish gate / validator は触らない。polluted gate (sns_polluted skip) のみ narrow rescue。
"""

import unittest

from src import rss_fetcher


def _is_polluted(
    *,
    title: str,
    summary: str,
    source_name: str = "",
    post_url: str = "",
) -> bool:
    return rss_fetcher._is_polluted_social_entry(
        title,
        summary,
        source_name=source_name,
        post_url=post_url,
    )


def _evaluate_rescue(
    *,
    title: str,
    summary: str,
    source_name: str = "",
    post_url: str = "",
) -> dict | None:
    return rss_fetcher._evaluate_sns_polluted_giants_rescue(
        title=title,
        summary=summary,
        source_name=source_name,
        post_url=post_url,
    )


class GiantsLikelyHandleNameTests(unittest.TestCase):
    """soft match helpers の挙動を pin する."""

    def test_handle_suffix_giants(self):
        self.assertTrue(rss_fetcher._is_giants_likely_trusted_social_handle("foo_giants"))

    def test_handle_prefix_hochi(self):
        self.assertTrue(rss_fetcher._is_giants_likely_trusted_social_handle("hochi_baseball"))

    def test_handle_prefix_sanspo(self):
        self.assertTrue(rss_fetcher._is_giants_likely_trusted_social_handle("sanspo_news"))

    def test_handle_prefix_yomiuri(self):
        self.assertTrue(rss_fetcher._is_giants_likely_trusted_social_handle("yomiuri_news"))

    def test_handle_unrelated(self):
        self.assertFalse(rss_fetcher._is_giants_likely_trusted_social_handle("random_user"))

    def test_handle_empty(self):
        self.assertFalse(rss_fetcher._is_giants_likely_trusted_social_handle(""))

    def test_handle_at_prefix(self):
        # @prefix を tolerate
        self.assertTrue(rss_fetcher._is_giants_likely_trusted_social_handle("@hochi_news"))

    def test_name_giants_keyword(self):
        self.assertTrue(rss_fetcher._is_giants_likely_trusted_social_name("巨人ファンXアカウント"))

    def test_name_giants_english(self):
        self.assertTrue(rss_fetcher._is_giants_likely_trusted_social_name("GIANTS Beat"))

    def test_name_no_giants_keyword(self):
        self.assertFalse(rss_fetcher._is_giants_likely_trusted_social_name("一般ニュースX"))


class SnsPollutedGiantsRescuePositiveTests(unittest.TestCase):
    """positive: trusted-likely Giants source の polluted false positive を救う."""

    def test_url_in_title_with_giants_lineup(self):
        # URL含む but trusted-likely + giants_kw + lineup keyword → rescue
        rescue = _evaluate_rescue(
            title="【巨人】本日のスタメン https://example.com/lineup",
            summary="本日のスターティングメンバーです",
            source_name="スポーツ報知巨人班X (新)",
            post_url="https://x.com/hochi_giants_jp/status/2052500000000000001",
        )
        self.assertIsNotNone(rescue)
        self.assertEqual(rescue["rescue_reason"], "sns_polluted_giants_narrow_rescue")
        self.assertIn("スタメン", rescue["keyword_hits"])

    def test_hashtag_with_giants_pregame(self):
        rescue = _evaluate_rescue(
            title="#巨人 #予告先発 本日の予告先発",
            summary="本日の予告先発：巨人・竹丸和幸",
            source_name="サンスポ巨人ニュースX",
            post_url="https://x.com/sanspo_extra/status/2052500000000000002",
        )
        self.assertIsNotNone(rescue)
        self.assertIn("予告先発", rescue["keyword_hits"])

    def test_at_mention_with_giants_homerun(self):
        rescue = _evaluate_rescue(
            title="@TokyoGiants 巨人 岡本和真 決勝ホームラン",
            summary="9回表に巨人の岡本和真選手が決勝3ランホームラン",
            source_name="ジャイアンツリポート",
            post_url="https://x.com/giants_report/status/2052500000000000003",
        )
        self.assertIsNotNone(rescue)
        self.assertTrue(any(kw in rescue["keyword_hits"] for kw in ("ホームラン", "決勝")))

    def test_outlet_marker_with_giants_recovery(self):
        # outlet marker (URL等) があっても trusted-likely name + giants + 復帰 で rescue
        rescue = _evaluate_rescue(
            title="【巨人ファーム情報】丸佳浩が一軍合流 https://hochi.news/articles/123",
            summary="二軍で調整していた丸佳浩選手が一軍合流",
            source_name="スポーツ報知巨人ニュース",
            post_url="https://x.com/hochi_extra/status/2052500000000000004",
        )
        self.assertIsNotNone(rescue)

    def test_polluted_text_passes_when_full_rescue_ok(self):
        # _is_polluted_social_entry レベルで rescue が効いて False を返すこと
        polluted = _is_polluted(
            title="【巨人】本日のスタメン #巨人 https://example.com/info",
            summary="本日のスターティングメンバー",
            source_name="ジャイアンツファンX",
            post_url="https://x.com/giants_fan_extra/status/2052500000000000005",
        )
        self.assertFalse(polluted)

    def test_postgame_decisive_with_polluted_markers_rescued(self):
        rescue = _evaluate_rescue(
            title="【巨人】3-2 ヤクルト 戸郷翔征が好投 #巨人 https://example.com/score",
            summary="戸郷翔征が7回1失点で好投。マルチ安打 岡本和真の決勝打。",
            source_name="読売ジャイアンツファンX",
            post_url="https://x.com/yomiuri_fan_extra/status/2052500000000000006",
        )
        self.assertIsNotNone(rescue)
        self.assertTrue(any(kw in rescue["keyword_hits"] for kw in ("好投", "決勝", "マルチ安打")))


class SnsPollutedGiantsRescueNegativeTests(unittest.TestCase):
    """negative: 3条件 AND を満たさない / non-Giants は rescue しない."""

    def test_non_trusted_handle_no_rescue(self):
        # handle が trusted-likely でない、name も Giants kw 含まない
        rescue = _evaluate_rescue(
            title="巨人 本日のスタメン https://example.com",
            summary="スタメン情報",
            source_name="ランダムニュースX",
            post_url="https://x.com/random_user_xyz/status/2052600000000000001",
        )
        self.assertIsNone(rescue)

    def test_no_giants_relevance_no_rescue(self):
        # handle は trusted-likely だが本文に巨人キーワードなし、不在
        rescue = _evaluate_rescue(
            title="練習しました #野球 https://example.com",
            summary="今日も練習を頑張りました",
            source_name="スポーツ報知一般X",
            post_url="https://x.com/sportshochi_general/status/2052600000000000002",
        )
        self.assertIsNone(rescue)

    def test_no_important_keyword_no_rescue(self):
        # trusted-likely + giants_kw あるが important keyword なし
        rescue = _evaluate_rescue(
            title="巨人ファンの皆さん #巨人 https://example.com/news",
            summary="今日も応援しましょう",
            source_name="巨人ファンクラブX",
            post_url="https://x.com/giants_fanclub_extra/status/2052600000000000003",
        )
        self.assertIsNone(rescue)

    def test_polluted_remains_skip_when_no_rescue_match(self):
        # _is_polluted_social_entry レベルで True (skip) を維持
        polluted = _is_polluted(
            title="不審な内容 https://malicious.example.com #spam",
            summary="本文も spam",
            source_name="ランダムBOTX",
            post_url="https://x.com/random_bot/status/2052600000000000004",
        )
        self.assertTrue(polluted)

    def test_other_team_giants_kw_in_text_but_handle_unrelated(self):
        # 他球団記事で「巨人戦」だけ言及している non-trusted source
        rescue = _evaluate_rescue(
            title="ソフトバンク・柳田が巨人戦で4番起用 https://example.com",
            summary="柳田悠岐がスタメン復帰",
            source_name="ソフトバンクニュースX",
            post_url="https://x.com/softbank_news/status/2052600000000000005",
        )
        # name に "巨人" 含まないので handle/name どちらも Giants-likely でない
        self.assertIsNone(rescue)


class SnsPollutedRescueDedupeMetaTests(unittest.TestCase):
    """rescue meta は dedupe key (post_url / x_status_id) を持つこと."""

    def test_rescue_meta_includes_x_status_id(self):
        rescue = _evaluate_rescue(
            title="【巨人】岡本和真が決勝ホームラン #巨人 https://example.com/score",
            summary="9回表に岡本和真選手が決勝3ランホームラン",
            source_name="スポーツ報知巨人特報X",
            post_url="https://x.com/hochi_special/status/2052700000000000001",
        )
        self.assertIsNotNone(rescue)
        self.assertEqual(rescue["x_status_id"], "2052700000000000001")
        self.assertEqual(rescue["post_url"], "https://x.com/hochi_special/status/2052700000000000001")

    def test_rescue_meta_includes_source_handle(self):
        rescue = _evaluate_rescue(
            title="【巨人】予告先発 https://example.com",
            summary="本日の予告先発が発表",
            source_name="サンスポ巨人特報X",
            post_url="https://twitter.com/sanspo_special/status/2052700000000000002",
        )
        self.assertIsNotNone(rescue)
        # _extract_handle_from_tweet_url は @prefix 付き handle を返す
        self.assertEqual(rescue["source_handle"].lstrip("@"), "sanspo_special")


class StrictTrustedSourceShortCircuitTests(unittest.TestCase):
    """既存 strict TRUSTED_SOCIAL_SOURCE_HANDLES path は維持される (regression check)."""

    def test_strict_trusted_handle_skips_pollution_check_entirely(self):
        # hochi_giants は TRUSTED_SOCIAL_SOURCE_HANDLES に含まれる → polluted check 全 skip
        polluted = _is_polluted(
            title="【巨人】試合速報 https://example.com #spam @anyone",
            summary="本文",
            source_name="スポーツ報知巨人班X",
            post_url="https://x.com/hochi_giants/status/2052800000000000001",
        )
        self.assertFalse(polluted)

    def test_strict_trusted_name_skips_pollution_check_entirely(self):
        # 巨人公式X は TRUSTED_SOCIAL_SOURCE_NAMES に含まれる
        polluted = _is_polluted(
            title="本日の試合 https://example.com",
            summary="GIANTS TVでLIVE配信",
            source_name="巨人公式X",
            post_url="https://x.com/anyhandle/status/2052800000000000002",
        )
        self.assertFalse(polluted)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
