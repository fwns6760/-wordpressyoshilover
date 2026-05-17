import unittest

from src import rss_fetcher


class HumanContextTitleRepairTests(unittest.TestCase):
    def test_player_quote_short_prefers_pitching_line_over_light_quote(self):
        title, review = rss_fetcher._finalize_title(
            "井上温大「ミスドの券」 関連発言",
            source_title="【とっておきメモ】巨人井上温大　誕プレで「ミスドの券」ポン・デ・リングが勝利のご褒美？",
            summary=(
                "巨人が今季初の完封劇で4連勝。"
                "井上温大投手が自己最長8回を投げ、3安打無失点9奪三振と快投した。"
                "勝ったら食べたいご褒美として「ミスドの券」を挙げた。"
            ),
            analysis={"actor_name": "井上温大"},
        )

        self.assertIsNone(review)
        self.assertEqual(title, "井上温大、8回3安打無失点9奪三振")

    def test_manager_generic_prefers_target_player_context(self):
        title, review = rss_fetcher._finalize_title(
            "内海哲也投手コーチコメント整理 ベンチ関連の発言ポイント",
            source_title=(
                "東京ドーム 内海哲也投手コーチ 先発・ウィットリー投手について "
                "「コントロールにばらつきがあり自分のペースで投げられていない印象」"
            ),
            summary="力のある投手なので、どんどんゾーン内で勝負してほしい。",
            analysis={"actor_name": "内海哲也投手コーチ"},
        )

        self.assertIsNone(review)
        self.assertEqual(title, "内海哲也投手コーチ、ウィットリーの投球に言及")

    def test_short_quote_uses_specific_source_headline_when_no_stat_line(self):
        title, review = rss_fetcher._finalize_title(
            "杉内投手チーフコーチ「つないでよく頑張ってくれた」 関連発言",
            source_title="【巨人】無失点リレーのリリーフ陣に杉内投手チーフコーチ「つないでよく頑張ってくれた」",
            summary="リリーフ陣が無失点でつないだ。",
            analysis={"actor_name": "杉内投手チーフコーチ"},
        )

        self.assertIsNone(review)
        self.assertEqual(title, "無失点リレーのリリーフ陣に杉内投手チーフコーチ「つないでよく頑張ってくれた」")

    def test_short_quote_uses_milestone_source_headline(self):
        title, review = rss_fetcher._finalize_title(
            "菅野智之「阿部さん」",
            source_title="菅野智之が日米通算１５０勝 「阿部さん」「小林誠司」「ラッチマン」名前を挙げて歴代捕手に感謝",
            summary=(
                "菅野智之投手が日米通算150勝目を達成した。"
                "阿部さん、小林誠司、ラッチマンら歴代捕手への感謝を口にした。"
            ),
            analysis={"actor_name": "菅野智之"},
        )

        self.assertIsNone(review)
        self.assertEqual(
            title,
            "菅野智之が日米通算１５０勝 「阿部さん」「小林誠司」「ラッチマン」名前を挙げて歴代捕手に感謝",
        )

    def test_generic_related_info_uses_specific_source_headline(self):
        title, review = rss_fetcher._finalize_title(
            "泉口友汰の現状整理 関連情報",
            source_title="巨人・泉口友汰、ナイター翌日も早出打撃練習",
            summary="泉口友汰が東京ドームで早出打撃練習を行った。",
            analysis={"actor_name": "泉口友汰"},
        )

        self.assertIsNone(review)
        self.assertEqual(title, "巨人・泉口友汰、ナイター翌日も早出打撃練習")

    def test_generic_subject_quote_uses_specific_source_headline(self):
        title, review = rss_fetcher._finalize_title(
            "選手「ファンに感謝」 関連発言",
            source_title="竹丸和幸とダルベック、月間MVP賞に「ファンに感謝」",
            summary="竹丸和幸とダルベックが月間MVP賞を受賞し、ファンへの感謝を語った。",
            analysis={"actor_name": "選手"},
        )

        self.assertIsNone(review)
        self.assertEqual(title, "竹丸和幸とダルベック、月間MVP賞に「ファンに感謝」")

    def test_eventful_quote_title_is_left_alone(self):
        title, review = rss_fetcher._finalize_title(
            "浦田俊輔、東京ドーム2回適時打「打ったのは真っすぐです」",
            source_title="東京ドーム 2回適時打の浦田俊輔選手のコメント",
            summary="浦田俊輔が2回に適時打を放った。",
            analysis={"actor_name": "浦田俊輔"},
        )

        self.assertIsNone(review)
        self.assertEqual(title, "浦田俊輔、東京ドーム2回適時打「打ったのは真っすぐです」")

    def test_manager_quote_does_not_become_player_pitching_line(self):
        title, review = rss_fetcher._finalize_title(
            "阿部監督「チームにとって大きい」 関連発言",
            source_title="巨人・阿部監督「チームにとって大きい」７試合ぶり先発に白星",
            summary="阿部監督が8回3安打無失点の井上温大について話した。",
            analysis={"actor_name": "阿部監督"},
        )

        self.assertIsNone(review)
        self.assertEqual(title, "巨人・阿部監督「チームにとって大きい」７試合ぶり先発に白星")


if __name__ == "__main__":
    unittest.main()
