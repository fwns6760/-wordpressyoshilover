import unittest

from src import body_validator, rss_fetcher
from src.comment_lane_validator import normalize_fail_tags, validate_comment_lane_draft
from src.fact_conflict_guard import (
    GAME_RESULT_CONTEXT_SUBTYPES,
    TITLE_BODY_MISMATCH_SUBTYPES,
    detect_game_result_conflict,
    detect_no_game_but_result,
    detect_title_body_entity_mismatch,
)


SOURCE_HTML = '<div class="yoshilover-article-source">記事元を読む</div>'


class FactConflictGuardHelperTests(unittest.TestCase):
    def _comment_base_draft(self) -> dict[str, object]:
        return {
            "title": "阿部監督、試合後の浅野に「積極性が良かった」",
            "speaker_name": "阿部監督",
            "scene_type": "試合後",
            "target_entity": "浅野",
            "quote_core": "積極性が良かった",
            "source_ref": "スポーツ報知",
            "quote_source": "スポーツ報知",
            "fact_header": "スポーツ報知によると、阿部監督が試合後に浅野の起用意図を説明した。",
            "lede": "阿部監督は試合後に浅野の起用意図として「積極性が良かった」と語った。",
            "quote_block": "スポーツ報知が伝えたコメントは「積極性が良かった」。",
            "context": "試合後の振り返りで浅野の初回打席に触れた。",
            "related": "次戦で同じ起用を続けるかが焦点になる。",
            "game_id": "",
            "scoreline": "",
            "team_result": "",
        }

    def test_detect_no_game_but_result_matches_067_contract(self):
        draft = self._comment_base_draft()
        draft["fact_header"] = "スポーツ報知によると、巨人は3-2で勝利し、阿部監督が試合後に振り返った。"

        self.assertTrue(detect_no_game_but_result(draft, draft))

    def test_detect_game_result_conflict_matches_067_contract(self):
        draft = self._comment_base_draft()
        draft["game_id"] = "G20260423"
        draft["scoreline"] = "3-2"
        draft["team_result"] = "win"
        draft["fact_header"] = "スポーツ報知によると、阿部監督が試合後に2-3の敗戦を振り返った。"
        draft["lede"] = "阿部監督は敗戦でも次戦につながるとした。"

        self.assertTrue(detect_game_result_conflict(draft, draft))

    def test_detect_title_body_entity_mismatch_matches_067_contract(self):
        draft = self._comment_base_draft()
        draft["title"] = "阿部監督、試合後に「積極性が良かった」"
        draft["fact_header"] = "スポーツ報知によると、岡本が試合後にコメントした。"
        draft["lede"] = "岡本は試合後に「積極性が良かった」と話した。"
        draft["context"] = "岡本の打席内容を振り返った。"

        self.assertTrue(detect_title_body_entity_mismatch(str(draft["title"]), draft))

    def test_subtype_policy_constants_cover_068_scope(self):
        self.assertEqual(
            GAME_RESULT_CONTEXT_SUBTYPES,
            frozenset({"farm", "farm_result", "lineup", "postgame", "pregame", "probable_starter"}),
        )
        self.assertEqual(
            TITLE_BODY_MISMATCH_SUBTYPES,
            frozenset(
                {
                    "fact_notice",
                    "farm",
                    "farm_result",
                    "lineup",
                    "notice",
                    "postgame",
                    "pregame",
                    "probable_starter",
                    "program",
                }
            ),
        )


class FactConflictGuardFixedLaneTests(unittest.TestCase):
    def test_body_validator_escalates_hard_fail_tags_without_repair(self):
        cases = {
            "NO_GAME_BUT_RESULT": {
                "subtype": "pregame",
                "body": "\n".join(
                    [
                        "【変更情報の要旨】",
                        "巨人が阪神に3-2で勝利した直後の変更を整理する。",
                        "【具体的な変更内容】",
                        "翌日の予告先発見込みをまとめる。",
                        "【この変更が意味すること】",
                        "入り方の違いを見ていきたい。",
                    ]
                ),
                "source_context": {
                    "title": "【4/21予告先発】 巨人 vs 阪神",
                    "source_title": "巨人 vs 阪神 予告先発",
                },
            },
            "GAME_RESULT_CONFLICT": {
                "subtype": "postgame",
                "body": "\n".join(
                    [
                        "【試合結果】",
                        "4月21日、巨人が阪神に2-3で敗戦した。",
                        "【ハイライト】",
                        "岡本和真の決勝打で終盤に勝ち越した。",
                        "【選手成績】",
                        "先発は7回2失点だった。",
                        "【試合展開】",
                        "終盤の継投が流れを分けた。",
                    ]
                ),
                "source_context": {
                    "title": "試合結果 巨人 3-2 阪神",
                    "source_title": "巨人 3-2 阪神 試合結果",
                    "scoreline": "3-2",
                    "team_result": "win",
                    "opponent": "阪神",
                },
            },
            "TITLE_BODY_ENTITY_MISMATCH": {
                "subtype": "fact_notice",
                "body": "\n".join(
                    [
                        "【訂正の対象】",
                        "対象記事の誤記を整理します。",
                        "【訂正内容】",
                        "登録選手名の表記に誤りがありました。",
                        "【訂正元】",
                        "球団発表を確認しました。",
                        "【お詫び / ファン視点】",
                        "確認できた範囲だけを短く整理します。",
                    ]
                ),
                "source_context": {
                    "title": "【公示】4月21日 浅野翔吾を登録",
                    "entity_tokens": ["浅野翔吾"],
                },
            },
        }

        for expected_tag, case in cases.items():
            with self.subTest(expected_tag=expected_tag):
                result = body_validator.validate_body_candidate(
                    case["body"],
                    case["subtype"],
                    rendered_html=SOURCE_HTML,
                    source_context=case["source_context"],
                )
                self.assertFalse(result["ok"])
                self.assertEqual(result["action"], "fail")
                self.assertIn(expected_tag, result["fail_axes"])
                self.assertEqual(result["stop_reason"], expected_tag)

    def test_title_body_mismatch_applies_across_fixed_subtypes(self):
        cases = {
            "fact_notice": {
                "body": "\n".join(
                    [
                        "【訂正の対象】",
                        "対象記事を整理します。",
                        "【訂正内容】",
                        "登録選手名の表記を訂正します。",
                        "【訂正元】",
                        "球団発表を確認しました。",
                        "【お詫び / ファン視点】",
                        "確認できた範囲だけを短く整理します。",
                    ]
                ),
                "source_context": {"title": "【公示】4月21日 浅野翔吾を登録", "entity_tokens": ["浅野翔吾"]},
            },
            "pregame": {
                "body": "\n".join(
                    [
                        "【変更情報の要旨】",
                        "雨天中止で先発がスライドします。",
                        "【具体的な変更内容】",
                        "開始時刻と先発見込みを整理します。",
                        "【この変更が意味すること】",
                        "試合前に見たい点は継投です。",
                    ]
                ),
                "source_context": {"title": "【4/21予告先発】 巨人 vs 阪神", "opponent": "阪神"},
            },
            "farm": {
                "body": "\n".join(
                    [
                        "【二軍結果・活躍の要旨】",
                        "巨人二軍が勝ちました。",
                        "【ファームのハイライト】",
                        "若手の長打が出ました。",
                        "【二軍個別選手成績】",
                        "ティマが2安打3打点でした。",
                        "【一軍への示唆】",
                        "昇格争いを見たいところです。",
                    ]
                ),
                "source_context": {"title": "巨人二軍 4-1 結果のポイント", "scoreline": "4-1"},
            },
            "postgame": {
                "body": "\n".join(
                    [
                        "【試合結果】",
                        "4月21日、巨人が勝利した。",
                        "【ハイライト】",
                        "岡本和真の決勝打が出た。",
                        "【選手成績】",
                        "先発は7回2失点だった。",
                        "【試合展開】",
                        "終盤の継投が流れを分けた。",
                    ]
                ),
                "source_context": {"title": "試合結果 巨人 3-2 阪神", "scoreline": "3-2", "opponent": "阪神"},
            },
        }

        for subtype, case in cases.items():
            with self.subTest(subtype=subtype):
                result = body_validator.validate_body_candidate(
                    case["body"],
                    subtype,
                    rendered_html=SOURCE_HTML,
                    source_context=case["source_context"],
                )
                self.assertIn("TITLE_BODY_ENTITY_MISMATCH", result["fail_axes"])
                self.assertEqual(result["action"], "fail")

    def test_game_result_tags_do_not_fire_for_non_result_notice_context(self):
        body = "\n".join(
            [
                "【訂正の対象】",
                "浅野翔吾の登録記事を整理します。",
                "【訂正内容】",
                "前日の勝利後に公開した記事の日時表記を訂正します。",
                "【訂正元】",
                "球団発表を確認しました。",
                "【お詫び / ファン視点】",
                "確認できた範囲だけを短く整理します。",
            ]
        )

        result = body_validator.validate_body_candidate(
            body,
            "fact_notice",
            rendered_html=SOURCE_HTML,
            source_context={
                "title": "【公示】4月21日 浅野翔吾を登録",
                "entity_tokens": ["浅野翔吾"],
            },
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("NO_GAME_BUT_RESULT", result["fail_axes"])
        self.assertNotIn("GAME_RESULT_CONFLICT", result["fail_axes"])

    def test_game_result_tags_apply_for_result_notice_context(self):
        body = "\n".join(
            [
                "【訂正の対象】",
                "試合結果記事の誤記を整理します。",
                "【訂正内容】",
                "巨人が阪神に2-3で敗戦したと記載していました。",
                "【訂正元】",
                "公式記録を確認しました。",
                "【お詫び / ファン視点】",
                "誤解を招いた点をお詫びします。",
            ]
        )

        result = body_validator.validate_body_candidate(
            body,
            "fact_notice",
            rendered_html=SOURCE_HTML,
            source_context={
                "title": "【試合結果訂正】 巨人 3-2 阪神",
                "source_title": "巨人 3-2 阪神 試合結果",
                "scoreline": "3-2",
                "team_result": "win",
                "opponent": "阪神",
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["action"], "fail")
        self.assertIn("GAME_RESULT_CONFLICT", result["fail_axes"])
        self.assertNotIn("NO_GAME_BUT_RESULT", result["fail_axes"])

    def test_lineup_policy_uses_post_gen_validator_adapter(self):
        text = "\n".join(
            [
                "【試合概要】",
                "巨人がスタメンを発表した。",
                "【スタメン一覧】",
                "1番丸、4番岡本和。",
                "【先発投手】",
                "先発は戸郷翔征。",
                "【注目ポイント】",
                "並びの意味をどう読むかが一番のポイントです。試合が始まって最初にどこを見るかまで、コメントで教えてください！",
            ]
        )

        result = rss_fetcher._evaluate_post_gen_validate(
            text,
            article_subtype="lineup",
            title="巨人スタメン 阪神戦 1番丸 4番岡本",
            source_refs={"opponent": "阪神", "source_title": "阪神戦スタメン発表"},
        )

        self.assertFalse(result["ok"])
        self.assertIn("TITLE_BODY_ENTITY_MISMATCH", result["fail_axes"])


class FactConflictGuardCommentLaneCompatibilityTests(unittest.TestCase):
    def _base_comment_draft(self) -> dict[str, object]:
        return {
            "title": "阿部監督、試合後の浅野に「積極性が良かった」",
            "speaker_name": "阿部監督",
            "scene_type": "試合後",
            "target_entity": "浅野",
            "quote_core": "積極性が良かった",
            "source_ref": "スポーツ報知",
            "quote_source": "スポーツ報知",
            "quote_source_type": "major_web",
            "trust_tier": "fact",
            "game_id": None,
            "opponent": None,
            "scoreline": None,
            "team_result": None,
            "downstream_link": "次戦でも同じ姿勢を求めた",
            "fact_header": "スポーツ報知によると、阿部監督が試合後に浅野の起用意図を説明した。",
            "lede": "阿部監督は試合後に浅野の起用意図として「積極性が良かった」と語り、次戦でも同じ姿勢を求めた。",
            "quote_block": "スポーツ報知が伝えたコメントは「積極性が良かった」。",
            "context": "試合後の振り返りで浅野の初回打席に触れた。",
            "related": "次戦で同じ起用を続けるかが次の焦点になる。",
        }

    def test_comment_lane_game_result_conflict_still_hard_fails(self):
        draft = self._base_comment_draft()
        draft["scoreline"] = "3-2"
        draft["team_result"] = "win"
        draft["game_id"] = "G20260423"
        draft["fact_header"] = "スポーツ報知によると、阿部監督が試合後に2-3の敗戦を振り返った。"
        draft["lede"] = "阿部監督は試合後に「積極性が良かった」と話し、敗戦でも次戦につながるとした。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("GAME_RESULT_CONFLICT", result.hard_fail_tags)
        self.assertEqual(result.stop_lane, "agent")

    def test_comment_lane_title_body_mismatch_still_hard_fails(self):
        draft = self._base_comment_draft()
        draft["title"] = "阿部監督、試合後に「積極性が良かった」"
        draft["fact_header"] = "スポーツ報知によると、岡本が試合後にコメントした。"
        draft["lede"] = "岡本は試合後に「積極性が良かった」と話し、次戦でも同じ姿勢を求めた。"
        draft["context"] = "岡本の打席内容を振り返った。"

        result = validate_comment_lane_draft(draft)

        self.assertIn("TITLE_BODY_ENTITY_MISMATCH", result.hard_fail_tags)
        self.assertEqual(result.stop_lane, "agent")

    def test_hard_fail_tags_keep_existing_ledger_normalization(self):
        self.assertEqual(
            normalize_fail_tags(("NO_GAME_BUT_RESULT", "GAME_RESULT_CONFLICT", "TITLE_BODY_ENTITY_MISMATCH")),
            ("fact_missing", "title_body_mismatch"),
        )


if __name__ == "__main__":
    unittest.main()
