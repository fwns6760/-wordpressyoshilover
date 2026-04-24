import unittest

from src.title_body_nucleus_validator import validate_title_body_nucleus


class TitleBodyNucleusValidatorTests(unittest.TestCase):
    def test_happy_paths(self):
        cases = [
            {
                "name": "postgame player stat aligned",
                "title": "坂本勇人 3安打 3打点",
                "body": "坂本勇人は3安打3打点の活躍で、巨人の3-2勝利を導いた。",
                "subtype": "postgame",
                "expected_subject": "坂本勇人",
                "expected_event": "3安打",
            },
            {
                "name": "lineup role aligned",
                "title": "岡本和真 4番起用",
                "body": "岡本和真は4番で先発出場するオーダーに入った。",
                "subtype": "lineup",
                "expected_subject": "岡本和真",
                "expected_event": "4番起用",
            },
            {
                "name": "manager strategy aligned",
                "title": "阿部監督 継投 采配",
                "body": "阿部監督は継投策について試合後に説明した。",
                "subtype": "manager",
                "expected_subject": "阿部監督",
                "expected_event": "継投",
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = validate_title_body_nucleus(case["title"], case["body"], case["subtype"])
                self.assertTrue(result.aligned)
                self.assertIsNone(result.reason_code)
                self.assertEqual(result.title_subject, case["expected_subject"])
                self.assertEqual(result.body_subject, case["expected_subject"])
                self.assertEqual(result.title_event, case["expected_event"])

    def test_subject_absent_paths(self):
        cases = [
            {
                "name": "player missing from lineup opening",
                "title": "岡本和真 4番起用",
                "body": "坂本勇人は3番で先発出場する。",
                "subtype": "lineup",
            },
            {
                "name": "public number missing from pregame opening",
                "title": "公示番号128 登録",
                "body": "戸郷翔征は東京ドームで調整した。",
                "subtype": "pregame",
            },
            {
                "name": "team missing from postgame opening",
                "title": "巨人 試合結果",
                "body": "阿部監督は打線の状態について語った。",
                "subtype": "postgame",
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = validate_title_body_nucleus(case["title"], case["body"], case["subtype"])
                self.assertFalse(result.aligned)
                self.assertEqual(result.reason_code, "SUBJECT_ABSENT")

    def test_event_diverge_paths(self):
        cases = [
            {
                "name": "roster up versus appearance",
                "title": "井上温大 昇格",
                "body": "井上温大は八回に登板した。",
                "subtype": "pregame",
                "expected": ("昇格", "登板"),
            },
            {
                "name": "starting pitcher versus training",
                "title": "戸郷翔征 先発",
                "body": "戸郷翔征は2軍練習で調整した。",
                "subtype": "pregame",
                "expected": ("先発", "2軍練習"),
            },
            {
                "name": "farm article mixed with first-team context",
                "title": "秋広優人 15号",
                "body": "秋広優人は一軍練習に合流した。",
                "subtype": "farm",
                "expected": ("15号", "一軍練習"),
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = validate_title_body_nucleus(case["title"], case["body"], case["subtype"])
                self.assertFalse(result.aligned)
                self.assertEqual(result.reason_code, "EVENT_DIVERGE")
                self.assertEqual((result.title_event, result.body_event), case["expected"])

    def test_multiple_nuclei_paths(self):
        cases = [
            {
                "name": "two player nuclei in postgame opening",
                "title": "坂本勇人 3安打",
                "body": "坂本勇人は3安打を放った。岡本和真は15号を放った。",
                "subtype": "postgame",
            },
            {
                "name": "three parallel nuclei despite single title subject",
                "title": "巨人 試合結果",
                "body": "坂本勇人は3安打を放った。岡本和真は15号を放った。井上温大は先発した。",
                "subtype": "postgame",
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                result = validate_title_body_nucleus(case["title"], case["body"], case["subtype"])
                self.assertFalse(result.aligned)
                self.assertEqual(result.reason_code, "MULTIPLE_NUCLEI")
                self.assertIn("opening subjects=", result.detail or "")

    def test_known_subjects_take_priority_for_rare_name(self):
        result = validate_title_body_nucleus(
            "𠮷川尚輝 2安打",
            "𠮷川尚輝は2安打で出塁した。",
            "postgame",
            known_subjects=["𠮷川尚輝"],
        )

        self.assertTrue(result.aligned)
        self.assertEqual(result.title_subject, "𠮷川尚輝")
        self.assertEqual(result.body_subject, "𠮷川尚輝")
        self.assertEqual(result.title_event, "2安打")


if __name__ == "__main__":
    unittest.main()
