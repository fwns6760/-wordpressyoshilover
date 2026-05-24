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

    def test_lineup_announcement_title_diverges_when_body_unrelated(self):
        """71314型: title が当日スタメン宣言なのに本文冒頭が別トピック."""
        cases = [
            {
                "name": "71314 mascot body under giants lineup title",
                "title": "巨人スタメン 試合前情報",
                "body": "マスコット通信簿の特集をお届けします。今週のジャビット君は...",
                "subtype": "pregame",
            },
            {
                "name": "honjitsu lineup but body covers unrelated event",
                "title": "本日のスタメン",
                "body": "東京ドームでは引退セレモニーが行われた。",
                "subtype": "pregame",
            },
            {
                "name": "starter pitcher announce but body is interview",
                "title": "予告先発 戸郷翔征",
                "body": "選手会の食事会の様子をレポートします。",
                "subtype": "pregame",
            },
            {
                "name": "mis-classified subtype still caught",
                "title": "巨人スタメン発表",
                "body": "ファン感謝デーのグッズ販売が始まった。",
                "subtype": "manager",
            },
        ]
        for case in cases:
            with self.subTest(case=case["name"]):
                result = validate_title_body_nucleus(
                    case["title"], case["body"], case["subtype"]
                )
                self.assertFalse(result.aligned, case["name"])
                self.assertEqual(result.reason_code, "EVENT_DIVERGE")
                self.assertIn("lineup", result.detail or "")

    def test_lineup_announcement_passes_with_supported_body(self):
        cases = [
            {
                "name": "lineup announcement with batting order list",
                "title": "巨人スタメン",
                "body": "巨人スタメンが発表された。1番中堅、2番二塁、3番右翼の打順が組まれている。",
                "subtype": "lineup",
            },
            {
                "name": "lineup announcement with order keyword",
                "title": "本日のスタメン",
                "body": "本日の先発オーダーが発表された。打順は次の通り。",
                "subtype": "lineup",
            },
        ]
        for case in cases:
            with self.subTest(case=case["name"]):
                result = validate_title_body_nucleus(
                    case["title"], case["body"], case["subtype"]
                )
                # Gate-specific assertion: the new lineup-announcement gate
                # must not raise EVENT_DIVERGE on supported announcement
                # bodies. Other axes are out of scope for this gate.
                if result.reason_code == "EVENT_DIVERGE":
                    self.assertNotIn(
                        "lineup but body opening lacks",
                        result.detail or "",
                        case["name"],
                    )

    def test_lineup_general_context_not_misfired(self):
        """スタメン定着 / 落ち / 争い / 予想 / 候補 / 振り返り は誤爆させない."""
        cases = [
            {
                "name": "starter spot retention discussion",
                "title": "坂本勇人 スタメン定着 へ",
                "body": "坂本勇人は今季ここまで打率.290と存在感を見せている。",
                "subtype": "feature",
            },
            {
                "name": "starter drop discussion",
                "title": "中山礼都 スタメン落ち の背景",
                "body": "中山礼都は調整不足を理由にベンチスタートとなった。",
                "subtype": "feature",
            },
            {
                "name": "lineup competition discussion",
                "title": "巨人 スタメン争い 激化",
                "body": "若手の台頭でレギュラー争いが激しくなっている。",
                "subtype": "feature",
            },
            {
                "name": "lineup prediction column",
                "title": "本日のスタメン予想",
                "body": "対戦相手は左腕。打線は右打者中心になりそうだ。",
                "subtype": "preview",
            },
            {
                "name": "starter candidate discussion",
                "title": "若手 スタメン候補 急浮上",
                "body": "二軍で結果を残す若手選手の名前が出てきた。",
                "subtype": "feature",
            },
            {
                "name": "retrospective lineup column",
                "title": "過去のスタメン振り返り 2010年代の名打線",
                "body": "2014年の打線は屈指の破壊力を誇った。",
                "subtype": "feature",
            },
        ]
        for case in cases:
            with self.subTest(case=case["name"]):
                result = validate_title_body_nucleus(
                    case["title"], case["body"], case["subtype"]
                )
                # The validator may still flag other axes (SUBJECT_ABSENT 等);
                # what matters is that the new lineup-announcement gate does
                # not misfire on general 定着/落ち/争い/予想/候補/振り返り forms.
                if result.reason_code == "EVENT_DIVERGE":
                    self.assertNotIn(
                        "lineup but body opening lacks",
                        result.detail or "",
                        f"{case['name']} should not raise lineup-announcement EVENT_DIVERGE",
                    )

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
