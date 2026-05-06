"""RSS-250: trusted_social_too_weak narrow rescue tests.

`_evaluate_trusted_social_giants_rescue` が信頼source + Giants-related +
重要キーワード の AND 3条件を満たした時のみ rescue meta を返すこと、
かつ x_status_id / source_url が dedupe 用に meta に含まれることを pin する。

negative 群:
- 写真のみ / 動画公開のみ / プレゼント / RT 一般 / 紙面告知 / 球団文脈なし /
  trusted_source 外
"""

import unittest
from unittest.mock import patch

from src import rss_fetcher


def _evaluate(
    *,
    title: str,
    summary: str,
    category: str,
    article_subtype: str,
    source_url: str,
    source_name: str,
    source_handle: str = "",
) -> dict | None:
    return rss_fetcher._evaluate_trusted_social_giants_rescue(
        title=title,
        summary=summary,
        category=category,
        article_subtype=article_subtype,
        source_url=source_url,
        source_name=source_name,
        source_handle=source_handle,
    )


def _is_worthy(
    *,
    title: str,
    summary: str,
    category: str,
    article_subtype: str,
    source_url: str,
    source_name: str,
    source_handle: str = "",
) -> tuple[bool, dict | None]:
    return rss_fetcher._evaluate_authoritative_social_entry(
        title,
        summary,
        category,
        article_subtype,
        source_name=source_name,
        source_handle=source_handle,
        source_url=source_url,
    )


class TrustedSocialGiantsRescuePositiveTests(unittest.TestCase):
    """positive: trusted_source + Giants-related + important keyword AND 3条件."""

    def test_hochi_x_lineup_today(self):
        meta = _evaluate(
            title="【一軍】巨人 vs ヤクルト 東京ドーム 14時試合開始 本日のスタメン",
            summary="本日のスタメンが発表されました。1番中堅・丸佳浩 2番二塁・吉川尚輝 3番一塁・岡本和真",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052100000000000001",
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(meta)
        self.assertEqual(meta["rescue_reason"], "trusted_source_giants_important_keyword")
        self.assertIn("スタメン", meta["keyword_hits"])
        self.assertEqual(meta["x_status_id"], "2052100000000000001")
        self.assertEqual(meta["template_key"], "trusted_social_short")

    def test_giants_official_x_pregame_starter(self):
        meta = _evaluate(
            title="【一軍】巨人 vs ヤクルト 5/6 14時試合開始 予告先発",
            summary="予告先発：巨人・竹丸和幸 / ヤクルト・山野太一",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://x.com/TokyoGiants/status/2052100000000000002",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertIsNotNone(meta)
        self.assertIn("予告先発", meta["keyword_hits"])

    def test_sanspo_x_coach_comment(self):
        meta = _evaluate(
            title="【巨人】二岡コーチが試合前コメント",
            summary="二岡智宏二軍打撃コーチが試合前に若手育成について談話。",
            category="首脳陣",
            article_subtype="social_news",
            source_url="https://twitter.com/sanspo_giants/status/2052100000000000003",
            source_name="サンスポ巨人X",
        )
        self.assertIsNotNone(meta)
        self.assertTrue(any(kw in meta["keyword_hits"] for kw in ("コーチ", "コメント", "談話")))

    def test_hochi_x_roster_register_demote(self):
        meta = _evaluate(
            title="【巨人】登録抹消・登録 公示が出ました",
            summary="本日の公示で増田陸選手が抹消、若林晃弘選手が登録となりました。",
            category="選手情報",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052100000000000004",
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(meta)

    def test_hochi_x_first_team_join(self):
        meta = _evaluate(
            title="【巨人】丸佳浩が一軍合流",
            summary="二軍で調整を続けていた丸佳浩選手が一軍合流しました。",
            category="選手情報",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052100000000000005",
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(meta)

    def test_hochi_x_recovery_injury_clear(self):
        meta = _evaluate(
            title="【巨人】中山礼都が故障明けで実戦復帰",
            summary="春先に右肘を負傷し離脱していた中山礼都選手が実戦復帰しました。",
            category="選手情報",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052100000000000006",
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(meta)

    def test_giants_official_x_farm_result(self):
        meta = _evaluate(
            title="【二軍】巨人 5-0 ハヤテ 試合結果",
            summary="二軍は本日ハヤテベンチャーズ静岡に5-0で勝利。打線が好調でした。",
            category="ドラフト・育成",
            article_subtype="social_news",
            source_url="https://x.com/TokyoGiants/status/2052100000000000007",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertIsNotNone(meta)

    def test_hochi_x_third_team_or_ikusei(self):
        meta = _evaluate(
            title="【巨人】三軍/育成情報",
            summary="育成選手の支配下昇格候補について三軍コーチがコメント。",
            category="ドラフト・育成",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052100000000000008",
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(meta)

    def test_giants_official_x_homerun_decisive(self):
        meta = _evaluate(
            title="【巨人】岡本和真が決勝ホームラン",
            summary="9回表に岡本和真選手が決勝の3ランホームラン。試合を決めました。",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://x.com/TokyoGiants/status/2052100000000000009",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertIsNotNone(meta)

    def test_sanspo_x_postgame_manager_comment(self):
        meta = _evaluate(
            title="【巨人】阿部監督が試合後コメント",
            summary="阿部監督が試合後の囲み取材で『勝ち越しの場面』について談話。",
            category="首脳陣",
            article_subtype="social_news",
            source_url="https://x.com/sanspo_giants/status/2052100000000000010",
            source_name="サンスポ巨人X",
        )
        self.assertIsNotNone(meta)

    def test_hochi_x_farm_lineup(self):
        meta = _evaluate(
            title="【二軍】巨人 vs ハヤテ 13時試合開始 本日のスタメン",
            summary="二軍 本日のスタメン：1️⃣ 丸 2️⃣ 萩尾 3️⃣ 皆川",
            category="ドラフト・育成",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052100000000000011",
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNotNone(meta)

    def test_hochi_x_broadcast_or_ticket_with_giants_context(self):
        # 巨人試合文脈ありの放送予定/チケット情報
        meta = _evaluate(
            title="【巨人】今日の試合 放送予定",
            summary="本日の試合は GIANTS TV で LIVE 配信。試合前情報も放送予定です。",
            category="球団情報",
            article_subtype="social_news",
            source_url="https://x.com/TokyoGiants/status/2052100000000000012",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertIsNotNone(meta)


class TrustedSocialGiantsRescueNegativeTests(unittest.TestCase):
    """negative: 3条件 AND を満たさない / negative-only ポストは rescue しない."""

    def test_photo_only_post(self):
        # 📸 単独 / 重要キーワード一切なし
        meta = _evaluate(
            title="【巨人】📸",
            summary="📸",
            category="球団情報",
            article_subtype="social_news",
            source_url="https://x.com/TokyoGiants/status/2052200000000000001",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertIsNone(meta)

    def test_video_promo_only_post(self):
        meta = _evaluate(
            title="【動画】巨人 YouTube公開中",
            summary="新動画を YouTube 公開しました。ぜひご覧ください。",
            category="球団情報",
            article_subtype="social_news",
            source_url="https://x.com/TokyoGiants/status/2052200000000000002",
            source_name="読売ジャイアンツ公式X",
        )
        # 動画 promo / negative-only context — rescue しない
        self.assertIsNone(meta)

    def test_giveaway_campaign(self):
        meta = _evaluate(
            title="サイン入りステッカー プレゼント キャンペーン",
            summary="抽選で3名様にサイン入りステッカーをプレゼント！キャンペーン応募はこちら。",
            category="球団情報",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052200000000000003",
            source_name="スポーツ報知巨人班X",
        )
        self.assertIsNone(meta)

    def test_non_giants_rt_post(self):
        # RT 他球団系 — Giants-related が False
        meta = _evaluate(
            title="RT 他球団情報",
            summary="ソフトバンクの選手が...",
            category="コラム",
            article_subtype="social_news",
            source_url="https://x.com/sponichiyakyu/status/2052200000000000004",
            source_name="スポニチ野球記者X",
        )
        self.assertIsNone(meta)

    def test_paper_layout_only_post(self):
        meta = _evaluate(
            title="本日の紙面レイアウト",
            summary="本日の紙面レイアウトはこちらです。",
            category="球団情報",
            article_subtype="social_news",
            source_url="https://x.com/sportshochi/status/2052200000000000005",
            source_name="スポーツ報知X",
        )
        self.assertIsNone(meta)

    def test_no_player_or_team_context(self):
        # trusted source だが巨人特化ではない (sportshochi)、本文に巨人 keyword なし
        # → is_giants_related が False になり rescue しない
        meta = _evaluate(
            title="練習しました",
            summary="今日も練習を頑張りました。",
            category="コラム",
            article_subtype="social_news",
            source_url="https://x.com/sportshochi/status/2052200000000000006",
            source_name="スポーツ報知X",
        )
        self.assertIsNone(meta)

    def test_non_trusted_source_post(self):
        # trusted ではない一般 X
        meta = _evaluate(
            title="【巨人】岡本和真がホームラン",
            summary="決勝3ランホームラン。",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://x.com/random_user_xyz/status/2052200000000000007",
            source_name="ランダムファンX",
        )
        self.assertIsNone(meta)


class TrustedSocialRescueDedupeMetaTests(unittest.TestCase):
    """rescue meta は dedupe key (source_url / x_status_id) を持つこと."""

    def test_rescue_meta_includes_x_status_id(self):
        meta = _evaluate(
            title="【巨人】岡本和真が決勝ホームラン",
            summary="9回表に岡本和真選手が決勝の3ランホームラン。",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://x.com/TokyoGiants/status/2052300000000000001",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertIsNotNone(meta)
        self.assertEqual(meta["x_status_id"], "2052300000000000001")
        self.assertEqual(meta["source_url"], "https://x.com/TokyoGiants/status/2052300000000000001")

    def test_invalid_x_url_no_rescue(self):
        # tweet URL 形式でない場合は rescue しない (要件: 元 X URL を残す)
        meta = _evaluate(
            title="【巨人】岡本和真が決勝ホームラン",
            summary="9回表に岡本和真選手が決勝の3ランホームラン。",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://example.com/no-status",
            source_name="読売ジャイアンツ公式X",
        )
        self.assertIsNone(meta)

    def test_x_status_id_extract_from_twitter_domain(self):
        meta = _evaluate(
            title="【巨人】岡本和真がマルチ安打",
            summary="2安打1本塁打 マルチ安打を記録。",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://twitter.com/sanspo_giants/status/2052300000000000099",
            source_name="サンスポ巨人X",
        )
        self.assertIsNotNone(meta)
        self.assertEqual(meta["x_status_id"], "2052300000000000099")


class AuthoritativeSocialEntryIntegrationTests(unittest.TestCase):
    """`_evaluate_authoritative_social_entry` integration:
    既存 path で skip されていた giants-related X が新 rescue 経路で worthy に転換するか."""

    def test_homerun_post_was_too_weak_now_worthy(self):
        # 既存 path では category=試合速報 + article_subtype=social_news の
        # ホームラン/スタメン 含むポストが social_too_weak で落ちていたが、
        # RSS-250 の giants_rescue で important keyword 多数 match → worthy
        worthy, meta = _is_worthy(
            title="【一軍】巨人 vs ヤクルト 14時試合開始 ホームランを放った 選手 5番キャッチャーでスタメン出場",
            summary="9回表 岡本和真選手が決勝3ランホームラン スタメン",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://x.com/TokyoGiants/status/2052400000000000001",
            source_name="読売ジャイアンツ公式X",
            source_handle="TokyoGiants",
        )
        self.assertTrue(worthy)
        self.assertIsNotNone(meta)
        # rescue_reason は既存 path / 新 path どちらか (TRUSTED_SOCIAL_REPORTABLE_MARKERS
        # に試合速報の marker があれば既存 trusted_social_source が先に hit する)
        self.assertIn(
            meta["rescue_reason"],
            (
                "trusted_social_source",
                "trusted_source_giants_important_keyword",
                "social_too_weak_narrow_rescue",
            ),
        )

    def test_pregame_starter_post_worthy_via_new_rescue(self):
        worthy, meta = _is_worthy(
            title="【一軍】巨人 vs ヤクルト 14時試合開始 予告先発",
            summary="本日の予告先発：巨人・竹丸和幸",
            category="試合速報",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052400000000000002",
            source_name="スポーツ報知巨人班X",
            source_handle="hochi_giants",
        )
        # 既存 path (試合速報 + 先発 keyword) で worthy=True が確定する
        # → meta は None でも OK (既存 path の挙動を破壊しない)
        self.assertTrue(worthy)

    def test_giveaway_post_remains_unworthy(self):
        worthy, meta = _is_worthy(
            title="サイン入りステッカー プレゼント キャンペーン",
            summary="抽選で3名様にサイン入りステッカーをプレゼント！",
            category="球団情報",
            article_subtype="social_news",
            source_url="https://x.com/hochi_giants/status/2052400000000000003",
            source_name="スポーツ報知巨人班X",
            source_handle="hochi_giants",
        )
        self.assertFalse(worthy)
        self.assertIsNone(meta)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
