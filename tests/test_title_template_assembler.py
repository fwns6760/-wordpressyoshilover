"""Tests for src/title_template_assembler.py — 330-QA のもとけ pattern."""

from __future__ import annotations

import os
import unittest

from src.title_template_assembler import (
    assemble_nomotoke_title,
    nomotoke_title_template_enabled,
)


class EnablementTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("ENABLE_NOMOTOKE_TITLE_TEMPLATE", None)

    def tearDown(self):
        os.environ.pop("ENABLE_NOMOTOKE_TITLE_TEMPLATE", None)

    def test_default_enabled(self):
        self.assertTrue(nomotoke_title_template_enabled())

    def test_disabled_returns_none(self):
        os.environ["ENABLE_NOMOTOKE_TITLE_TEMPLATE"] = "0"
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="dummy",
            source_body="戸郷翔征「自分らしく投げるだけ」",
            player_name="戸郷翔征",
            role="投手",
        )
        self.assertIsNone(result)


class PatternAPlayerCommentTests(unittest.TestCase):
    def test_basic_quote_assembly(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="戸郷翔征 試合後コメント",
            source_body="戸郷翔征選手「自分らしく投げるだけ」と前向きに語った。",
            player_name="戸郷翔征",
            role="投手",
        )
        self.assertEqual(result, "戸郷翔征「自分らしく投げるだけ」")

    def test_long_quote_trimmed(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body="戸郷「" + "あ" * 50 + "」",
            player_name="戸郷",
            role="投手",
        )
        self.assertIsNotNone(result)
        self.assertIn("戸郷「", result)
        self.assertIn("…」", result)

    def test_no_quote_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="戸郷翔征 試合後コメント",
            source_body="戸郷翔征が無失点で投球を続けた。",
            player_name="戸郷翔征",
            role="投手",
        )
        self.assertIsNone(result)

    def test_no_name_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body="「自分らしく」",
            player_name="",
            role="",
        )
        self.assertIsNone(result)


class PatternAManagerTests(unittest.TestCase):
    def test_manager_subtype_appends_manager_suffix(self):
        result = assemble_nomotoke_title(
            article_subtype="manager",
            existing_title="阿部 試合後",
            source_body="阿部監督「勝負をかけた」と語った。",
            player_name="阿部",
            role="監督",
        )
        self.assertEqual(result, "阿部監督「勝負をかけた」")

    def test_manager_name_already_with_suffix(self):
        result = assemble_nomotoke_title(
            article_subtype="manager",
            existing_title="d",
            source_body="阿部監督「勝負をかけた」",
            player_name="阿部監督",
            role="監督",
        )
        # already ends with 監督 → no duplication
        self.assertEqual(result, "阿部監督「勝負をかけた」")


class PatternACoachTests(unittest.TestCase):
    def test_coach_suffix(self):
        result = assemble_nomotoke_title(
            article_subtype="coach_comment",
            existing_title="d",
            source_body="杉内投手チーフコーチ「なんとか勝たせてあげたい」",
            player_name="杉内",
            role="コーチ",
        )
        self.assertIn("杉内", result)
        self.assertIn("「なんとか勝たせてあげたい」", result)


class PatternBPostgameTests(unittest.TestCase):
    def test_sayonara_modifier(self):
        result = assemble_nomotoke_title(
            article_subtype="postgame",
            existing_title="d",
            source_body="佐々木俊輔が劇的サヨナラ2ランで勝利を呼び込んだ。",
            player_name="佐々木俊輔",
            role="選手",
        )
        self.assertIsNotNone(result)
        self.assertIn("サヨナラ", result)
        self.assertIn("巨人・佐々木俊輔", result)

    def test_no_modifier_no_result_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="postgame",
            existing_title="d",
            source_body="特になし",
            player_name="佐々木俊輔",
            role="選手",
        )
        self.assertIsNone(result)


class PatternEBroadcastTests(unittest.TestCase):
    def test_broadcast_with_date_and_opponent(self):
        result = assemble_nomotoke_title(
            article_subtype="broadcast",
            existing_title="d",
            metadata={
                "event_date_label": "5月13日(水)",
                "opponent": "広島",
            },
        )
        self.assertEqual(
            result, "5月13日(水)「巨人vs.広島」【テレビ・ネット中継】"
        )

    def test_broadcast_missing_facts_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="broadcast",
            existing_title="d",
            metadata={"opponent": "広島"},
        )
        self.assertIsNone(result)


class UnsupportedSubtypeTests(unittest.TestCase):
    def test_unknown_subtype_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="general",
            existing_title="d",
            source_body="戸郷「a」",
            player_name="戸郷",
        )
        self.assertIsNone(result)


class PatternFPostgameDetailTests(unittest.TestCase):
    def test_first_team_with_score_and_result(self):
        # B が modifier 取れない時 F に fall back
        result = assemble_nomotoke_title(
            article_subtype="postgame",
            existing_title="d",
            source_body="5月13日の試合は 5-3 で勝利。展開が動いた。",
            source_title="2026年5月13日 セ・リーグ7回戦 巨人vs.広島",
            metadata={
                "event_date_label": "5月13日(水)",
                "opponent": "広島",
                "league_level": "first",
            },
            player_name="",
        )
        self.assertIsNotNone(result)
        self.assertIn("【試合結果】", result)
        self.assertIn("5-3", result)
        self.assertIn("巨人vs.広島", result)
        self.assertIn("勝利", result)

    def test_postgame_b_path_preferred_if_modifier_available(self):
        # サヨナラ modifier ある時は B 優先
        result = assemble_nomotoke_title(
            article_subtype="postgame",
            existing_title="d",
            source_body="佐々木俊輔の劇的サヨナラ2ラン。",
            player_name="佐々木俊輔",
            role="選手",
        )
        self.assertIsNotNone(result)
        self.assertIn("サヨナラ", result)
        # B pattern には「【試合結果】」は付かない
        self.assertNotIn("【試合結果】", result)


class PatternGFarmTests(unittest.TestCase):
    def test_farm_with_score_and_result(self):
        result = assemble_nomotoke_title(
            article_subtype="farm",
            existing_title="d",
            source_body="2軍は 4-5 で敗戦。",
            source_title="ファーム 巨人vs.西武",
            metadata={
                "event_date_label": "5月13日(水)",
                "opponent": "西武",
            },
        )
        self.assertIsNotNone(result)
        self.assertIn("ファーム公式戦", result)
        self.assertIn("巨人vs.西武", result)
        self.assertIn("巨人2軍", result)
        self.assertIn("4-5", result)
        self.assertIn("敗戦", result)


class PatternOLineupTests(unittest.TestCase):
    def test_lineup_with_date_and_opponent(self):
        result = assemble_nomotoke_title(
            article_subtype="lineup",
            existing_title="d",
            metadata={
                "event_date_label": "5月13日(水)",
                "opponent": "広島",
                "game_number": "7",
            },
        )
        self.assertEqual(
            result,
            "5月13日(水) セ・リーグ7回戦「巨人vs.広島」 巨人、スタメン発表！！！",
        )

    def test_lineup_missing_opponent_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="lineup",
            existing_title="d",
            metadata={"event_date_label": "5月13日(水)"},
        )
        self.assertIsNone(result)


class PatternNProbableStarterTests(unittest.TestCase):
    def test_pregame_with_opponent_enriched(self):
        result = assemble_nomotoke_title(
            article_subtype="pregame",
            existing_title="d",
            source_title="本日の予告先発が発表される",
            metadata={
                "event_date_label": "5月14日(木)",
                "opponent": "中日",
            },
        )
        self.assertIsNotNone(result)
        self.assertIn("予告先発", result)
        self.assertIn("巨人vs.中日", result)
        self.assertIn("！！！", result)

    def test_probable_starter_minimum_no_opponent(self):
        result = assemble_nomotoke_title(
            article_subtype="probable_starter",
            existing_title="d",
            source_title="本日の予告先発が発表される",
            metadata={"event_date_label": "5月14日(木)"},
        )
        self.assertEqual(
            result, "5月14日(木)の予告先発が発表される！！！"
        )

    def test_pregame_no_keyword_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="pregame",
            existing_title="d",
            source_title="試合前の様子",
            metadata={"event_date_label": "5月14日(木)"},
        )
        self.assertIsNone(result)


class PatternMNoticeTests(unittest.TestCase):
    def test_notice_with_action_and_count(self):
        result = assemble_nomotoke_title(
            article_subtype="notice",
            existing_title="d",
            source_title="プロ野球公示 巨人が2名の選手を登録抹消",
            source_body="本日5月13日のプロ野球公示にて、巨人が2人の選手を登録抹消した。",
            metadata={"event_date_label": "5月13日(火)"},
        )
        self.assertIsNotNone(result)
        self.assertIn("【公示】", result)
        self.assertIn("5月13日(火)", result)
        self.assertIn("巨人が2人の選手を登録抹消", result)

    def test_official_notice_no_count(self):
        result = assemble_nomotoke_title(
            article_subtype="official_notice",
            existing_title="d",
            source_title="プロ野球公示 巨人が選手を登録",
            source_body="本日5月13日のプロ野球公示にて、巨人が選手を登録した。",
            metadata={"event_date_label": "5月13日(火)"},
        )
        self.assertIsNotNone(result)
        self.assertIn("巨人が選手を登録", result)

    def test_notice_without_action_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="notice",
            existing_title="d",
            source_title="プロ野球公示",
            source_body="本日のプロ野球公示。",
            metadata={"event_date_label": "5月13日(火)"},
        )
        self.assertIsNone(result)


class PatternRReactionTests(unittest.TestCase):
    """335-QA Phase 2: 反応 pattern (AがBのfactをverb「q1」「q2」) を source から
    literal extraction する pattern R。LLM / AI 一切なし、regex で source 内 literal
    substring を直接拾う。"""

    def test_reaction_pattern_from_source_body(self):
        # 67146 reproduce: yoshilover H2 generator が出した literal を抽出
        body = (
            "岡本和真が坂本勇人の劇的通算３００号を祝福"
            "「さすが」「エンターテイナー」 試合前特打のＢＧＭは竹内まりや"
        )
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="岡本和真「エンターテイナー」",  # 旧 bad title
            source_body=body,
            player_name="岡本和真",
            role="選手",
        )
        self.assertEqual(
            result,
            "岡本和真が坂本勇人の劇的通算３００号を祝福「さすが」「エンターテイナー」",
        )

    def test_reaction_pattern_from_source_title(self):
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_title=(
                "戸郷翔征が阿部監督の采配を称賛「感謝」「最高でした」"
            ),
            player_name="戸郷翔征",
            role="投手",
        )
        self.assertIsNotNone(result)
        self.assertIn("戸郷翔征が阿部監督の采配を称賛", result)
        self.assertIn("「感謝」「最高でした」", result)

    def test_no_reaction_pattern_falls_through_to_a(self):
        # 反応 pattern が無いケースは Pattern A (player_comment) に fall-through
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="戸郷翔征 試合後コメント",
            source_body="戸郷翔征選手「自分らしく投げるだけ」と前向きに語った。",
            player_name="戸郷翔征",
            role="投手",
        )
        # Pattern A 通常出力
        self.assertEqual(result, "戸郷翔征「自分らしく投げるだけ」")

    def test_reaction_pattern_alt_verbs(self):
        # 称賛 / 絶賛 / 喝采 等 verb 列挙
        for verb in ("称賛", "絶賛", "感心", "喝采"):
            body = f"岡本が坂本の300号を{verb}「さすが」「すごい」"
            result = assemble_nomotoke_title(
                article_subtype="player_comment",
                existing_title="d",
                source_body=body,
                player_name="岡本",
                role="選手",
            )
            self.assertIsNotNone(result, msg=f"verb={verb}")
            self.assertIn(verb, result)
            self.assertIn("「さすが」「すごい」", result)

    def test_reaction_requires_two_quotes(self):
        # 短 quote 1 つだけだと Pattern R は match せず Pattern A fall-through
        body = "岡本和真が坂本勇人の300号を祝福「さすが」と語った"
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body=body,
            player_name="岡本和真",
            role="選手",
        )
        # Pattern A になり「さすが」だけが quote として残る (旧挙動)
        self.assertEqual(result, "岡本和真「さすが」")


class FirstQuoteNaturalBreakTests(unittest.TestCase):
    """335-QA Phase 1: `_first_quote` の `…` truncation 廃止 + max_len 28→40。"""

    def test_quote_under_40_chars_no_ellipsis(self):
        # 35 字 quote、max_len 40 内なのでそのまま literal で返る
        quote = "あ" * 35
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body=f"戸郷「{quote}」",
            player_name="戸郷",
            role="投手",
        )
        self.assertIsNotNone(result)
        self.assertIn(quote, result)
        # `…` は出ない
        self.assertNotIn("…", result)

    def test_quote_natural_break_used_for_long_input(self):
        # 50 字 quote、句点で natural break して 40 字以内に literal 切り出し
        body = "戸郷「最後まで集中して投げ切ったと思います。これからも頑張りたい。」"
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body=body,
            player_name="戸郷",
            role="投手",
        )
        self.assertIsNotNone(result)
        # natural break で 1 文目が選ばれる literal
        self.assertIn("最後まで集中して投げ切ったと思います", result)
        # `…` は出ない (natural break が成立した)
        self.assertNotIn("…", result)

    def test_quote_extremely_long_no_break_fallback_ellipsis(self):
        # 50 字 連続「あ」(句点無し)→ natural break 不可、legacy `…` fallback
        quote = "あ" * 50
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body=f"戸郷「{quote}」",
            player_name="戸郷",
            role="投手",
        )
        self.assertIsNotNone(result)
        # legacy fallback で `…` が出る
        self.assertIn("…", result)

    def test_quote_trailing_punctuation_stripped(self):
        # quote 末尾の 。 を strip ([[feedback_title_clickable_descriptive]] 整合)
        body = "戸郷「自分らしく投げるだけ。」"
        result = assemble_nomotoke_title(
            article_subtype="player_comment",
            existing_title="d",
            source_body=body,
            player_name="戸郷",
            role="投手",
        )
        self.assertIsNotNone(result)
        # quote 内末尾の 。 は strip され "「自分らしく投げるだけ」" になる
        self.assertIn("「自分らしく投げるだけ」", result)


class PatternXPlayerVoiceDigestTests(unittest.TestCase):
    """334-QA player_voice_digest: 3-token literal assembly (player / quote / event).

    AI / LLM 一切禁止、source からの literal のみで title 組み立て。
    3-token のいずれかが揃わない場合は None を返し、caller は draft + review に
    落とす (LLM で補完して title 可能化することは禁止)。
    """

    def test_basic_3_token_assembly(self):
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body=(
                "坂本勇人「最後まで集中して振り切れたんじゃないかと思います」と振り返った。"
            ),
            player_name="坂本勇人",
            metadata={"event_token": "300号サヨナラホームラン"},
        )
        self.assertEqual(
            result,
            "坂本勇人「最後まで集中して振り切れたんじゃないかと思います」"
            "300号サヨナラホームラン",
        )

    def test_quote_exactly_20_chars_minimum_boundary(self):
        quote = "あ" * 20
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body=f"岡本「{quote}」",
            player_name="岡本和真",
            metadata={"event_token": "逆転3ラン"},
        )
        self.assertEqual(result, f"岡本和真「{quote}」逆転3ラン")

    def test_quote_exactly_40_chars_maximum_boundary(self):
        quote = "あ" * 40
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body=f"岡本「{quote}」",
            player_name="岡本和真",
            metadata={"event_token": "完封勝利"},
        )
        self.assertEqual(result, f"岡本和真「{quote}」完封勝利")

    def test_quote_too_short_19_chars_returns_none(self):
        quote = "あ" * 19
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body=f"岡本「{quote}」",
            player_name="岡本和真",
            metadata={"event_token": "逆転3ラン"},
        )
        self.assertIsNone(result)

    def test_quote_too_long_41_chars_returns_none(self):
        quote = "あ" * 41
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body=f"岡本「{quote}」",
            player_name="岡本和真",
            metadata={"event_token": "逆転3ラン"},
        )
        self.assertIsNone(result)

    def test_no_player_name_returns_none(self):
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body="坂本「" + "あ" * 25 + "」",
            player_name="",
            metadata={"event_token": "300号サヨナラホームラン"},
        )
        self.assertIsNone(result)

    def test_no_event_token_returns_none(self):
        # metadata.event_token 不在 → 3-token 揃わない → None
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body="坂本勇人「" + "あ" * 25 + "」",
            player_name="坂本勇人",
            metadata={},
        )
        self.assertIsNone(result)

    def test_no_quote_in_source_returns_none(self):
        # source に literal quote 「」 が無い → LLM で補完しない → None
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body="坂本勇人がサヨナラ本塁打を放った。",
            player_name="坂本勇人",
            metadata={"event_token": "300号サヨナラホームラン"},
        )
        self.assertIsNone(result)

    def test_event_pitcher_innings_token(self):
        # event_token に投手成績 fact (7回1失点) を入れた case。
        # 旧版 test は quote が 18 字で min_len=20 を満たさず実装が正しく reject
        # していたので、quote を 28 字 (実発言寄り) に直して 3-token 完成 case とする。
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body="菅野「球が走っていた感触は確かに自分でも手応えのある試合でした」",
            player_name="菅野智之",
            metadata={"event_token": "7回1失点"},
        )
        self.assertEqual(
            result,
            "菅野智之「球が走っていた感触は確かに自分でも手応えのある試合でした」"
            "7回1失点",
        )

    def test_trailing_punctuation_stripped(self):
        # quote 末尾の 。 を のもとけ headline style に合わせて strip
        result = assemble_nomotoke_title(
            article_subtype="player_voice_digest",
            existing_title="d",
            source_body=(
                "坂本勇人「最後まで集中して振り切れたんじゃないかと思います。」"
            ),
            player_name="坂本勇人",
            metadata={"event_token": "300号サヨナラホームラン"},
        )
        self.assertEqual(
            result,
            "坂本勇人「最後まで集中して振り切れたんじゃないかと思います」"
            "300号サヨナラホームラン",
        )


if __name__ == "__main__":
    unittest.main()
