import unittest

from src import x_post_generator


class XPostGeneratorTests(unittest.TestCase):
    def test_player_post_uses_quote_angle_question_and_three_tags(self):
        text = x_post_generator.build_post(
            title="【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み",
            url="https://yoshilover.com/61897",
            category="選手情報",
            summary=(
                "ファームでフォーム改造中の巨人戸郷翔征投手（26）が13日、ジャイアンツ球場での先発投手練習に参加し、心境を明かした。"
                "前日12日の2軍DeNA戦に先発して7回4安打1失点と好投した。"
            ),
        )

        self.assertIn("戸郷翔征「人の助言を取り入れることも重要」", text)
        self.assertIn("今回は結果より、フォーム変更の中身が気になる記事です。", text)
        self.assertIn("この変化、どう見ますか？", text)
        self.assertIn("https://yoshilover.com/61897", text)
        self.assertIn("#巨人 #ジャイアンツ #戸郷翔征", text)
        self.assertNotIn("#プロ野球", text)

    def test_player_post_without_quote_falls_back_to_player_led_copy(self):
        text = x_post_generator.build_post(
            title="【巨人】浅野翔吾が1軍昇格へ",
            url="https://yoshilover.com/62000",
            category="選手情報",
            summary="巨人の浅野翔吾外野手が1軍昇格に向けて準備を進めている。",
        )

        self.assertIn("浅野翔吾の今回の動き、気になります。", text)
        self.assertIn("今回の動き、今後の起用にも関わってきそうです。", text)
        self.assertIn("この流れ、どう見ますか？", text)
        self.assertIn("#巨人 #ジャイアンツ #浅野翔吾", text)

    def test_manager_post_uses_quote_angle_question_and_three_tags(self):
        text = x_post_generator.build_post(
            title="【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待",
            url="https://yoshilover.com/61903",
            category="首脳陣",
            summary="阿部監督が「レギュラーは決まってません。結果残せば使います」と話した。若手積極起用で競争を促す考えを示した。",
        )

        self.assertIn("阿部慎之助「レギュラーは決まってません。結果残せば使います」", text)
        self.assertIn("このコメント、次の序列にも関わってきそうです。", text)
        self.assertIn("この競争、どう見ますか？", text)
        self.assertIn("https://yoshilover.com/61903", text)
        self.assertIn("#巨人 #ジャイアンツ #阿部慎之助", text)
        self.assertNotIn("#プロ野球", text)

    def test_manager_post_lineup_variant_changes_question(self):
        text = x_post_generator.build_post(
            title="【巨人】阿部監督がスタメン起用の狙いを説明",
            url="https://yoshilover.com/62010",
            category="首脳陣",
            summary="阿部監督がスタメンと打順の組み方について説明した。次の起用にも注目が集まる。",
        )

        self.assertIn("この発言、次のスタメンをどう動かすか気になります。", text)
        self.assertIn("次のスタメン、どう変わると思いますか？", text)

    def test_manager_post_strategy_variant_changes_question(self):
        text = x_post_generator.build_post(
            title="【巨人】阿部監督が継投の意図を説明",
            url="https://yoshilover.com/62011",
            category="首脳陣",
            summary="阿部監督が継投と代打の判断について説明した。次の采配にも視線が集まる。",
        )

        self.assertIn("この発言、次のベンチワークをどう読むか気になります。", text)
        self.assertIn("この采配、どう見ますか？", text)


if __name__ == "__main__":
    unittest.main()
