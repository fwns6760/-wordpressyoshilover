import unittest

from src.title_style_validator import (
    TITLE_STYLE_CLICKBAIT,
    TITLE_STYLE_FORBIDDEN_PREFIX,
    TITLE_STYLE_GENERIC,
    TITLE_STYLE_OUT_OF_LENGTH,
    TITLE_STYLE_SPECULATIVE,
    TITLE_STYLE_CONTRACTS,
    build_title_style_prompt_lines,
    fixed_lane_to_editorial_subtype,
    normalize_title_style_subtype,
    validate_title_style,
)


class TitleStyleValidatorTests(unittest.TestCase):
    def test_prompt_lines_cover_all_editorial_subtypes(self):
        for subtype in TITLE_STYLE_CONTRACTS:
            with self.subTest(subtype=subtype):
                lines = build_title_style_prompt_lines(subtype)
                self.assertGreaterEqual(len(lines), 7)
                self.assertTrue(any(line.startswith("基本型:") for line in lines))
                self.assertTrue(any(line.startswith("Don't generate titles like:") for line in lines))

    def test_subtype_aliases_and_fixed_lane_mappings_are_normalized(self):
        self.assertEqual(normalize_title_style_subtype("fact_notice"), "notice")
        self.assertEqual(normalize_title_style_subtype("social_video_notice"), "social_video")
        self.assertEqual(normalize_title_style_subtype("x_source_notice"), "x_source")
        self.assertEqual(fixed_lane_to_editorial_subtype("program"), "program")
        self.assertEqual(fixed_lane_to_editorial_subtype("notice"), "notice")
        self.assertEqual(fixed_lane_to_editorial_subtype("probable_starter"), "pregame")
        self.assertEqual(fixed_lane_to_editorial_subtype("farm_result"), "farm")
        self.assertEqual(fixed_lane_to_editorial_subtype("postgame"), "postgame")

    def test_valid_titles_pass_for_all_subtypes(self):
        cases = {
            "postgame": "巨人・岡本和真、決勝3ランホームラン！！！",
            "lineup": "4月25日(金) セ・リーグ公式戦「巨人vs阪神」 巨人、スタメン発表！！！",
            "manager": "巨人・阿部監督、岡本和真の打順変更方針は…",
            "pregame": "4月25日(金)の予告先発が発表される！！！",
            "farm": "巨人二軍 浅野翔吾、2安打マルチヒット！！！",
            "comment": '巨人・坂本勇人、試合後に「守備から流れを作れたと感じた」',
            "social_video": "巨人・坂本勇人の守備練習映像【動画】",
            "x_source": "報知プロ野球担当、坂本勇人が一軍復帰を示唆",
            "notice": "巨人・戸郷翔征、現在の状態は…？",
            "program": 'GIANTS TV「阿部監督インタビュー」(4月25日 20:00放送)',
        }
        for subtype, title in cases.items():
            with self.subTest(subtype=subtype):
                result = validate_title_style(title, subtype)
                self.assertTrue(result.ok)
                self.assertIsNone(result.reason_code)

    def test_generic_titles_fail_for_all_subtypes(self):
        cases = {
            "postgame": "巨人・岡本和真の真相とは何か?",
            "lineup": "4月25日 巨人スタメンの比較をどう見るか総点検版",
            "manager": "巨人・阿部監督のコメントから見えるもの整理版",
            "pregame": "4月25日 巨人阪神戦の本音をどう見る",
            "farm": "巨人二軍 若手の本音をどう見るか完全整理版",
            "comment": "巨人・坂本勇人、試合後コメントをどう見るか徹底整理",
            "social_video": "巨人・坂本勇人の本音【動画】特集版",
            "x_source": "報知プロ野球担当の本音をどう見る整理",
            "notice": "巨人・坂本勇人の真相とは何か完全版",
            "program": "GIANTS TVの見どころ徹底解説完全版",
        }
        for subtype, title in cases.items():
            with self.subTest(subtype=subtype):
                result = validate_title_style(title, subtype)
                self.assertFalse(result.ok)
                self.assertEqual(result.reason_code, TITLE_STYLE_GENERIC)

    def test_speculative_titles_fail_for_all_subtypes_except_notice_state_case(self):
        cases = {
            "postgame": "巨人・岡本和真は何を見せるか",
            "lineup": "4月25日 巨人スタメン 若手をどう並べたかを考える",
            "manager": "巨人・阿部監督は何を見せるかを語らずに問う",
            "pregame": "4月25日 巨人阪神戦はどう挑む?",
            "farm": "巨人二軍 若手の打撃をどこを見たいか整理",
            "comment": "巨人・坂本勇人の試合後の打撃をどこを見たいか総整理",
            "social_video": "巨人・坂本勇人はどう見えるか【動画】",
            "x_source": "報知プロ野球担当、坂本勇人はどうなるか",
            "notice": "巨人・戸郷翔征、復帰後はどうなるか",
            "program": "GIANTS TV放送後の展開はどうなるか特集版",
        }
        for subtype, title in cases.items():
            with self.subTest(subtype=subtype):
                result = validate_title_style(title, subtype)
                self.assertFalse(result.ok)
                self.assertEqual(result.reason_code, TITLE_STYLE_SPECULATIVE)

        allowed = validate_title_style("巨人・戸郷翔征、現在の状態は…？", "notice")
        self.assertTrue(allowed.ok)

    def test_clickbait_titles_fail_across_multiple_subtypes(self):
        cases = {
            "postgame": "巨人・岡本和真、衝撃の決勝弾！！！",
            "notice": "巨人・戸郷翔征、驚愕の離脱情報",
            "social_video": "巨人・坂本勇人の圧倒的守備【動画】",
            "x_source": "報知プロ野球担当、ヤバい復帰情報",
            "program": "GIANTS TV 史上最高の放送回特集",
        }
        for subtype, title in cases.items():
            with self.subTest(subtype=subtype):
                result = validate_title_style(title, subtype)
                self.assertFalse(result.ok)
                self.assertEqual(result.reason_code, TITLE_STYLE_CLICKBAIT)

    def test_forbidden_prefix_titles_fail(self):
        cases = (
            ("postgame", "【速報】巨人・岡本和真、決勝弾！！！"),
            ("lineup", "【LIVE】4月25日 巨人、スタメン発表！！！"),
            ("pregame", "【巨人】4月25日(金)の予告先発が発表される！！！"),
            ("notice", "【速報】巨人・戸郷翔征、現在の状態は…？"),
            ("program", "【LIVE】GIANTS TV「阿部監督インタビュー」(4月25日 20:00放送)"),
        )
        for subtype, title in cases:
            with self.subTest(subtype=subtype):
                result = validate_title_style(title, subtype)
                self.assertFalse(result.ok)
                self.assertEqual(result.reason_code, TITLE_STYLE_FORBIDDEN_PREFIX)

    def test_length_bounds_fail_for_all_subtypes(self):
        cases = {
            "postgame": "巨人勝利",
            "lineup": "巨人スタメン発表",
            "manager": "阿部監督コメント",
            "pregame": "予告先発",
            "farm": "二軍結果",
            "comment": "巨人・坂本勇人、コメント",
            "social_video": "動画公開",
            "x_source": "報知、復帰",
            "notice": "登録情報",
            "program": "番組情報",
        }
        for subtype, title in cases.items():
            with self.subTest(subtype=subtype):
                result = validate_title_style(title, subtype)
                self.assertFalse(result.ok)
                self.assertEqual(result.reason_code, TITLE_STYLE_OUT_OF_LENGTH)

    def test_quote_style_and_period_fail_as_generic(self):
        period_result = validate_title_style("巨人・阿部監督、岡本和真の状態整理メモは。", "manager")
        self.assertFalse(period_result.ok)
        self.assertEqual(period_result.reason_code, TITLE_STYLE_GENERIC)

        quote_result = validate_title_style("巨人・坂本勇人、試合後に『守備から流れを作れたと感じた』", "comment")
        self.assertFalse(quote_result.ok)
        self.assertEqual(quote_result.reason_code, TITLE_STYLE_GENERIC)

    def test_alias_subtypes_validate_with_same_contract(self):
        notice_result = validate_title_style("巨人・戸郷翔征、現在の状態は…？", "fact_notice")
        social_result = validate_title_style("巨人・坂本勇人の守備練習映像【動画】", "social_video_notice")
        x_source_result = validate_title_style("報知プロ野球担当、坂本勇人が一軍復帰を示唆", "x_source_notice")

        self.assertTrue(notice_result.ok)
        self.assertTrue(social_result.ok)
        self.assertTrue(x_source_result.ok)


if __name__ == "__main__":
    unittest.main()
