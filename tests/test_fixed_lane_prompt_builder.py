import unittest

from src import body_validator, source_attribution_validator, title_validator
from src.fixed_lane_prompt_builder import build_fixed_lane_prompt, get_contract, supported_fixed_lane_subtypes


class FixedLanePromptBuilderTests(unittest.TestCase):
    def _build_prompt(self, subtype: str, *, mode: str = "initial") -> str:
        kwargs = {
            "subtype": subtype,
            "mode": mode,
            "title_hint": get_contract(subtype).sample_title,
            "source_facts": ["source fact 1", "source fact 2"],
            "source_name": "一次情報",
            "source_url": "https://example.com/source",
        }
        if mode == "repair":
            kwargs["current_draft"] = "【試合結果】\n既存本文\n【ハイライト】\n既存本文"
            kwargs["fail_axes"] = ["required_block_missing", "source_attribution_missing"]
        return build_fixed_lane_prompt(**kwargs)

    def test_supported_subtypes_are_fixed(self):
        self.assertEqual(
            supported_fixed_lane_subtypes(),
            ("program", "notice", "probable_starter", "farm_result", "postgame"),
        )

    def test_each_subtype_initial_prompt_contains_five_contract_sections(self):
        for subtype in supported_fixed_lane_subtypes():
            with self.subTest(subtype=subtype):
                prompt = self._build_prompt(subtype)
                self.assertIn("required_fact_block:", prompt)
                self.assertIn("title_body_coherence:", prompt)
                self.assertIn("abstract_lead_ban:", prompt)
                self.assertIn("attribution_condition:", prompt)
                self.assertIn("fallback_copy:", prompt)

    def test_each_subtype_initial_prompt_includes_required_blocks(self):
        for subtype in supported_fixed_lane_subtypes():
            with self.subTest(subtype=subtype):
                prompt = self._build_prompt(subtype)
                for block in get_contract(subtype).required_blocks:
                    self.assertIn(block, prompt)

    def test_repair_prompt_contains_minimum_diff_rubric(self):
        prompt = self._build_prompt("postgame", mode="repair")
        self.assertIn("minimum_diff_rubric:", prompt)
        self.assertIn("該当 block / 該当 sentence / 該当 attribution だけを直す。", prompt)
        self.assertIn("全文再生成は禁止。差分が最小になるように補修する。", prompt)

    def test_initial_prompt_omits_minimum_diff_rubric(self):
        prompt = self._build_prompt("postgame", mode="initial")
        self.assertNotIn("minimum_diff_rubric:", prompt)
        self.assertNotIn("全文再生成は禁止。差分が最小になるように補修する。", prompt)

    def test_notice_and_probable_starter_titles_route_to_expected_validator_subtypes(self):
        self.assertEqual(title_validator.infer_subtype_from_title(get_contract("notice").sample_title), "fact_notice")
        self.assertEqual(title_validator.infer_subtype_from_title(get_contract("probable_starter").sample_title), "pregame")

    def test_farm_result_and_postgame_titles_route_to_expected_validator_subtypes(self):
        self.assertEqual(title_validator.infer_subtype_from_title(get_contract("farm_result").sample_title), "farm")
        self.assertEqual(title_validator.infer_subtype_from_title(get_contract("postgame").sample_title), "postgame")

    def test_probable_starter_and_postgame_prompts_reuse_validator_first_blocks(self):
        probable_prompt = self._build_prompt("probable_starter")
        postgame_prompt = self._build_prompt("postgame")
        self.assertIn(body_validator.expected_block_order("pregame")[0], probable_prompt)
        self.assertIn(body_validator.expected_block_order("postgame")[0], postgame_prompt)
        self.assertIn(title_validator.TITLE_PREFIX_BY_SUBTYPE["postgame"], postgame_prompt)

    def test_postgame_prompt_hardens_fact_kernel_and_abstract_lead_ban(self):
        prompt = self._build_prompt("postgame")
        self.assertIn(body_validator.POSTGAME_ABSTRACT_LEAD_PREFIXES[0], prompt)
        self.assertIn("勝敗を動かした出来事を最低1つ入れる", prompt)
        self.assertIn(body_validator.POSTGAME_HIGHLIGHT_HEADING, prompt)

    def test_special_subtypes_require_explicit_x_attribution(self):
        for subtype in ("program", "notice", "probable_starter"):
            with self.subTest(subtype=subtype):
                contract = get_contract(subtype)
                self.assertIn(contract.validator_subtype, source_attribution_validator.SPECIAL_REQUIRED_SUBTYPES)
                prompt = self._build_prompt(subtype)
                self.assertIn("明示 attribution を必ず残す", prompt)
                self.assertIn("T1 web の裏どり無しで断定しない", prompt)

    def test_postgame_and_farm_result_allow_web_backed_x_omission(self):
        for subtype in ("farm_result", "postgame"):
            with self.subTest(subtype=subtype):
                contract = get_contract(subtype)
                self.assertIn(contract.validator_subtype, source_attribution_validator.POSTGAME_OPTIONAL_WITH_WEB_SUBTYPES)
                prompt = self._build_prompt(subtype)
                self.assertIn("T1 web が別にある場合は本文 attribution を省略可", prompt)


if __name__ == "__main__":
    unittest.main()
