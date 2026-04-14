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

    def test_lineup_post_uses_verified_stat_rows_when_present(self):
        text = x_post_generator.build_post(
            title="【巨人】今日のスタメン発表 1番丸、4番岡田",
            url="https://yoshilover.com/62012",
            category="試合速報",
            summary=(
                "【今日のスタメンデータ】 "
                "1番 丸佳浩 打率.281 3本 12打点 2盗塁 "
                "4番 岡田悠希 打率.298 5本 18打点 1盗塁"
            ),
        )

        self.assertIn("1番丸佳浩 .281 3本 12打点 2盗塁", text)
        self.assertIn("4番岡田悠希 .298 5本 18打点 1盗塁", text)
        self.assertIn("この並び、どう見ますか？", text)
        self.assertIn("#巨人 #ジャイアンツ", text)

    def test_lineup_post_falls_back_when_stats_missing(self):
        text = x_post_generator.build_post(
            title="【巨人】今日のスタメン発表 1番丸、4番岡田",
            url="https://yoshilover.com/62013",
            category="試合速報",
            summary="巨人が阪神戦のスタメンを発表した。",
        )

        self.assertIn("今日の並び、どこが気になりますか？", text)

    def test_lineup_post_can_read_stats_from_article_html(self):
        text = x_post_generator.build_post(
            title="【巨人】今日のスタメン発表 1番丸、4番岡田",
            url="https://yoshilover.com/62014",
            category="試合速報",
            summary="巨人が阪神戦のスタメンを発表した。",
            content_html=(
                "<table>"
                "<tr><th>打順</th><th>位置</th><th>選手名</th><th>打率</th><th>本塁打</th><th>打点</th><th>盗塁</th></tr>"
                "<tr><td>1</td><td>中</td><td>丸 佳浩</td><td>.281</td><td>3</td><td>12</td><td>2</td></tr>"
                "<tr><td>4</td><td>左</td><td>岡田 悠希</td><td>.298</td><td>5</td><td>18</td><td>1</td></tr>"
                "</table>"
            ),
        )

        self.assertIn("1番丸 佳浩 .281 3本 12打点 2盗塁", text)
        self.assertIn("4番岡田 悠希 .298 5本 18打点 1盗塁", text)

    def test_postgame_post_uses_result_flow_and_question(self):
        text = x_post_generator.build_post(
            title="【巨人】今季２度目の０封負けで連敗　井上温大は６回２失点も打線が沈黙",
            url="https://yoshilover.com/61924",
            category="試合速報",
            summary=(
                "巨人はヤクルト投手陣を攻略できず、今季2度目の0封負けを喫した。"
                "先発井上温大投手は6回6安打2失点と粘投したが、打線の援護なく今季2敗目を喫した。"
            ),
        )

        self.assertIn("巨人、打線が沈黙して連敗。", text)
        self.assertIn("井上温大は試合を壊さず、勝敗を分けたのは攻撃でした。", text)
        self.assertIn("この試合の分岐点、どこでしたか？", text)
        self.assertIn("#巨人 #ジャイアンツ #井上温大", text)

    def test_postgame_post_win_variant_uses_endgame_angle(self):
        text = x_post_generator.build_post(
            title="【巨人】阪神に3-2で勝利　岡田が決勝打",
            url="https://yoshilover.com/62015",
            category="試合速報",
            summary="巨人が阪神に3-2で勝利した。終盤に岡田悠希の決勝打が飛び出した。",
        )

        self.assertIn("巨人、競り勝って白星。", text)
        self.assertIn("岡田悠希の一打で流れが動き、終盤の勝負どころがはっきり出た試合でした。", text)
        self.assertIn("この試合の分岐点、どこでしたか？", text)
        self.assertIn("#巨人 #ジャイアンツ #岡田悠希", text)

    def test_live_update_post_uses_non_bot_like_flow_copy(self):
        text = x_post_generator.build_post(
            title="【巨人途中経過】6回表 巨人2-2阪神と同点",
            url="https://yoshilover.com/62020",
            category="試合速報",
            summary="巨人が6回表に2-2の同点に持ち込んだ。ここから次の1点が重い。",
        )

        self.assertIn("巨人、6回表に2-2の同点。", text)
        self.assertIn("次の1点をどちらが取るかです。", text)
        self.assertIn("この流れ、どう見ますか？", text)
        self.assertIn("#巨人 #ジャイアンツ", text)

    def test_farm_post_uses_player_and_promotion_angle(self):
        text = x_post_generator.build_post(
            title="【巨人2軍】浅野翔吾が昇格へ向けてマルチ安打",
            url="https://yoshilover.com/62021",
            category="ドラフト・育成",
            summary="巨人2軍の浅野翔吾外野手がマルチ安打を記録。昇格候補として注目が集まる。",
        )

        self.assertIn("浅野翔吾の2軍での動き、気になります。", text)
        self.assertIn("この動き、一軍の入れ替えにも関わってきそうです。", text)
        self.assertIn("次に上がるなら誰を見たいですか？", text)
        self.assertIn("#巨人 #ジャイアンツ #浅野翔吾", text)

    def test_data_obp_post_uses_top_five_tags_and_source_name(self):
        text = x_post_generator.build_post(
            title="巨人打線は打率だけで見ていいのか 出塁率で見ると泉口友汰が先頭に立つ",
            url="https://yoshilover.com/61939",
            category="コラム",
            summary="巨人の出塁率記事。",
            content_html=(
                "<table>"
                "<tr><th>順</th><th>選手</th><th>試合</th><th>打席</th><th>打率</th><th>出塁率</th><th>OPS</th></tr>"
                "<tr><td>1</td><td>泉口 友汰</td><td>14</td><td>57</td><td>.294</td><td>.368</td><td>.897</td></tr>"
                "<tr><td>2</td><td>ダルベック</td><td>13</td><td>52</td><td>.205</td><td>.327</td><td>.759</td></tr>"
                "<tr><td>3</td><td>キャベッジ</td><td>14</td><td>55</td><td>.309</td><td>.309</td><td>.836</td></tr>"
                "<tr><td>4</td><td>佐々木 俊輔</td><td>11</td><td>27</td><td>.296</td><td>.296</td><td>.777</td></tr>"
                "<tr><td>5</td><td>浦田 俊輔</td><td>11</td><td>38</td><td>.229</td><td>.289</td><td>.603</td></tr>"
                "<tr><td>10</td><td>坂本 勇人</td><td>10</td><td>29</td><td>.077</td><td>.172</td><td>.364</td></tr>"
                "</table>"
            ),
        )

        self.assertIn("阿部監督は打線をどう組むのか。", text)
        self.assertIn("出塁率上位5人", text)
        self.assertIn("泉口 友汰 .368", text)
        self.assertIn("浦田 俊輔 .289", text)
        self.assertIn("坂本勇人 10位 .172", text)
        self.assertIn("NPB調べ", text)
        self.assertIn("#巨人 #ジャイアンツ #泉口友汰 #ダルベック #キャベッジ #佐々木俊輔 #浦田俊輔", text)


if __name__ == "__main__":
    unittest.main()
