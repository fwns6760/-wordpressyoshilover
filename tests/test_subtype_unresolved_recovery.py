import unittest

from src.pre_publish_fact_check.extractor import infer_subtype


class SubtypeUnresolvedRecoveryTests(unittest.TestCase):
    def test_coach_comment_title_is_recovered_as_comment(self):
        title = "阿部監督「きっかけにしてほしい」 ベンチの狙いはどこか"
        self.assertEqual(infer_subtype(title), "comment")

    def test_coach_comment_c_title_is_recovered_as_comment(self):
        title = "巨人Ｃ「状態は上がってきた」 若手起用の意図を明かす"
        self.assertEqual(infer_subtype(title), "comment")

    def test_pitcher_focus_title_is_recovered_as_postgame(self):
        title = "山崎伊織が8Ｋで無失点 投球内容を振り返る"
        self.assertEqual(infer_subtype(title), "postgame")

    def test_batter_focus_title_is_recovered_as_postgame(self):
        title = "吉川尚輝が猛打賞 初安打の若手も続いた"
        self.assertEqual(infer_subtype(title), "postgame")

    def test_farm_postgame_title_stays_farm_before_postgame(self):
        title = "2軍が3-1で勝利 若手右腕が好投"
        self.assertEqual(infer_subtype(title), "farm")

    def test_roster_move_title_is_recovered_as_notice(self):
        title = "浅野翔吾が一軍合流 帯同メンバー入りへ"
        self.assertEqual(infer_subtype(title), "notice")

    def test_roster_move_exclusion_falls_through_to_injury(self):
        title = "主力が昇格目前で故障離脱"
        self.assertEqual(infer_subtype(title), "injury")

    def test_promotional_event_title_maps_to_off_field(self):
        title = "ＣＬＵＢ ＧＩＡＮＴＳデー 会員限定Ｔシャツ販売開始"
        self.assertEqual(infer_subtype(title), "off_field")

    def test_program_branch_keeps_priority_over_promotional_event(self):
        title = "ＣＬＵＢ ＧＩＡＮＴＳ会員限定グッズ紹介をGIANTS TVで放送"
        self.assertEqual(infer_subtype(title), "program")


if __name__ == "__main__":
    unittest.main()
