"""Tests for ``src.format_as_x_post`` (ticket 346)."""

from __future__ import annotations

import unittest

from src.format_as_x_post import (
    DEFAULT_HASHTAGS,
    X_CHAR_LIMIT,
    format_as_x_post,
)


def _make_rank_result(
    rows: list[dict],
    *,
    ok: bool = True,
    focus_player: dict | None = None,
    reason: str | None = None,
) -> dict:
    payload: dict = {
        "ok": ok,
        "rows": rows,
        "count": len(rows),
        "total": len(rows),
        "focus_player": focus_player,
    }
    if reason is not None:
        payload["reason"] = reason
    return payload


def _row(rank: int, name: str, team: str, value: float, sample: int = 100) -> dict:
    return {
        "rank": rank,
        "total": 50,
        "player_canonical": name,
        "team_code": team,
        "metric_value": value,
        "sample_size": sample,
    }


class FormatAsXPostRankingTests(unittest.TestCase):
    def test_ops_ranking_template_includes_metric_label_and_rows(self) -> None:
        parsed = {"metric": "OPS", "top_n": 5, "position": None, "league": None}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "佐藤輝明", "阪神", 0.945),
                    _row(2, "牧秀悟", "DeNA", 0.932),
                    _row(3, "岡本和真", "巨人", 0.921),
                    _row(4, "村上宗隆", "ヤクルト", 0.918),
                    _row(5, "鈴木誠也", "広島", 0.910),
                ]
            ),
        )
        self.assertTrue(result["ok"], msg=result)
        text = result["draft_text"]
        # 418 case B: header = 「📊 OPS TOP5 ⚾」 形式
        self.assertIn("📊", text)
        self.assertIn("OPS", text)
        self.assertIn("TOP5", text)
        # All 5 rows present.
        for name in ["佐藤輝明", "牧秀悟", "岡本和真", "村上宗隆", "鈴木誠也"]:
            self.assertIn(name, text)
        # Giants player marked.
        self.assertIn("🟧巨人🟧", text)
        # Hashtag block present.
        self.assertIn(DEFAULT_HASHTAGS, text)
        # Batting-rate convention: leading-zero stripped.
        self.assertIn(".945", text)
        self.assertNotIn("0.945", text)

    def test_top_n_cap_at_10_for_280_char_budget(self) -> None:
        parsed = {"metric": "OPS", "top_n": 30}
        big_rows = [_row(i, f"選手{i:02d}", "阪神", 0.900 - i * 0.001) for i in range(1, 31)]
        result = format_as_x_post(parsed, _make_rank_result(big_rows))
        self.assertTrue(result["ok"])
        # Implementation clamps to top 10.
        self.assertIn("選手01", result["draft_text"])
        self.assertIn("選手10", result["draft_text"])
        self.assertNotIn("選手11", result["draft_text"])
        self.assertLessEqual(result["char_count"], X_CHAR_LIMIT)

    def test_giants_team_alias_variants_all_get_highlighted(self) -> None:
        # 全ての alias variant が ← 巨人 マークを得る (insight_defense_proxy
        # の alias と同期しているのが本契約)。
        for team_alias in ["巨人", "読売", "読売ジャイアンツ", "ジャイアンツ", "Giants", "GIANTS", "G", "g"]:
            parsed = {"metric": "OPS", "top_n": 3}
            result = format_as_x_post(
                parsed,
                _make_rank_result(
                    [
                        _row(1, "選手A", "阪神", 0.900),
                        _row(2, "巨人選手", team_alias, 0.890),
                        _row(3, "選手B", "ヤクルト", 0.880),
                    ]
                ),
            )
            self.assertTrue(result["ok"], msg=f"alias={team_alias}: {result}")
            self.assertIn("🟧巨人🟧", result["draft_text"], msg=f"alias={team_alias} should highlight")

    def test_non_giants_rows_do_not_get_highlighted(self) -> None:
        parsed = {"metric": "OPS", "top_n": 3}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "佐藤輝明", "阪神", 0.945),
                    _row(2, "牧秀悟", "DeNA", 0.932),
                    _row(3, "村上宗隆", "ヤクルト", 0.918),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        self.assertNotIn("🟧巨人🟧", result["draft_text"])

    def test_empty_rows_yields_friendly_message(self) -> None:
        parsed = {"metric": "OPS", "top_n": 5}
        result = format_as_x_post(parsed, _make_rank_result([]))
        self.assertTrue(result["ok"])
        self.assertIn("該当データなし", result["draft_text"])

    def test_era_pitching_uses_two_decimal_places(self) -> None:
        parsed = {"metric": "ERA", "top_n": 3}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "戸郷翔征", "巨人", 1.85),
                    _row(2, "村上頌樹", "阪神", 1.92),
                    _row(3, "森下暢仁", "広島", 2.11),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        text = result["draft_text"]
        # ERA は 2 桁小数で「.」前の 0 を残す (1.85 は 1.85 のまま)。
        self.assertIn("1.85", text)
        self.assertIn("防御率", text)

    def test_per_nine_metrics_use_japanese_labels(self) -> None:
        parsed = {"metric": "K_per_9", "top_n": 3}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "戸郷翔征", "巨人", 8.75),
                    _row(2, "村上頌樹", "阪神", 8.20),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        text = result["draft_text"]
        # 418 case B: 「奪三振率 TOP3 ⚾」 形式
        self.assertIn("奪三振率", text)
        self.assertIn("TOP3", text)
        self.assertNotIn("K/9", text)


class FormatAsXPostFocusPlayerTests(unittest.TestCase):
    def test_focus_player_renders_single_player_template(self) -> None:
        parsed = {"metric": "OPS", "focus_player": "岡本和真"}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [_row(3, "岡本和真", "巨人", 0.921, sample=200)],
                focus_player={
                    "player_canonical": "岡本和真",
                    "team_code": "巨人",
                    "metric_value": 0.921,
                    "sample_size": 200,
                    "rank": 3,
                    "total": 50,
                },
            ),
        )
        self.assertTrue(result["ok"])
        text = result["draft_text"]
        self.assertIn("岡本和真", text)
        self.assertIn("巨人", text)
        self.assertIn(".921", text)
        self.assertIn("3/50", text)
        self.assertIn("200", text)


class FormatAsXPostErrorTests(unittest.TestCase):
    def test_rank_result_not_ok_propagates_reason(self) -> None:
        parsed = {"metric": "OPS"}
        result = format_as_x_post(
            parsed, _make_rank_result([], ok=False, reason="db_not_available")
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "db_not_available")
        self.assertEqual(result["draft_text"], "")

    def test_missing_metric_rejected(self) -> None:
        result = format_as_x_post({}, _make_rank_result([]))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "metric_missing")

    def test_parsed_not_dict_returns_typed_error(self) -> None:
        result = format_as_x_post("not a dict", _make_rank_result([]))  # type: ignore[arg-type]
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "parsed_not_dict")

    def test_rank_result_not_dict_returns_typed_error(self) -> None:
        result = format_as_x_post({"metric": "OPS"}, None)  # type: ignore[arg-type]
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "rank_result_not_dict")


class FormatAsXPostNullValueTests(unittest.TestCase):
    def test_none_metric_value_renders_dash_not_crash(self) -> None:
        parsed = {"metric": "OPS", "top_n": 2}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "佐藤輝明", "阪神", 0.945),
                    {
                        "rank": 2,
                        "total": 50,
                        "player_canonical": "X",
                        "team_code": "ヤクルト",
                        "metric_value": None,
                        "sample_size": 0,
                    },
                ]
            ),
        )
        self.assertTrue(result["ok"])
        self.assertIn("-", result["draft_text"])

    def test_hashtag_override_to_empty_drops_block(self) -> None:
        parsed = {"metric": "OPS", "top_n": 2}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "佐藤輝明", "阪神", 0.945),
                    _row(2, "岡本和真", "巨人", 0.921),
                ]
            ),
            hashtags="",
        )
        self.assertTrue(result["ok"])
        self.assertNotIn("#巨人", result["draft_text"])


class FormatAsXPostLineBreakTests(unittest.TestCase):
    def test_ranking_has_blank_line_between_header_and_body(self) -> None:
        parsed = {"metric": "OPS", "top_n": 2}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "佐藤輝明", "阪神", 0.945),
                    _row(2, "岡本和真", "巨人", 0.921),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        # header → blank → body → blank → hashtags
        lines = result["draft_text"].split("\n")
        self.assertGreaterEqual(len(lines), 5)
        self.assertEqual(lines[1], "")


class XImpressionPhase3HookLineTests(unittest.TestCase):
    """X インプ向上 Phase 3 (2026-05-27): 「結論先出し」 hook line。"""

    def test_hook_line_inserted_when_giants_in_ranking(self) -> None:
        parsed = {"metric": "OPS", "top_n": 3, "league": "セ"}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "岡本和真", "巨人", 0.950),
                    _row(2, "佐藤輝明", "阪神", 0.910),
                    _row(3, "坂本勇人", "巨人", 0.880),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        first = result["draft_text"].split("\n", 1)[0]
        self.assertTrue(first.startswith("★"), msg=f"hook missing: {first!r}")
        self.assertTrue(first.endswith("★"))
        self.assertIn("岡本和真", first)
        self.assertIn(".950", first)

    def test_hook_line_omitted_when_no_giants(self) -> None:
        parsed = {"metric": "OPS", "top_n": 3, "league": "セ"}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "佐藤輝明", "阪神", 0.945),
                    _row(2, "村上宗隆", "ヤクルト", 0.921),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        first = result["draft_text"].split("\n", 1)[0]
        self.assertFalse(first.startswith("★"))
        self.assertIn("📊", first)

    def test_hook_line_uses_focus_player_when_present(self) -> None:
        parsed = {"metric": "OPS", "league": "セ"}
        rank_result = {
            "ok": True,
            "rows": [],
            "count": 0,
            "total": 30,
            "focus_player": {
                "player_canonical": "坂本勇人",
                "team_code": "巨人",
                "metric_value": 0.875,
                "rank": 4,
                "total": 30,
                "sample_size": 50,
            },
        }
        result = format_as_x_post(parsed, rank_result)
        self.assertTrue(result["ok"])
        first = result["draft_text"].split("\n", 1)[0]
        self.assertTrue(first.startswith("★"))
        self.assertIn("坂本勇人", first)
        self.assertIn("4/30", first)


class XImpressionPhase4DynamicHashtagsTests(unittest.TestCase):
    """X インプ向上 Phase 4 (2026-05-27): 動的ハッシュタグ。"""

    def test_dynamic_tags_include_giants_player_name(self) -> None:
        parsed = {"metric": "OPS", "top_n": 3}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "岡本和真", "巨人", 0.950),
                    _row(2, "佐藤輝明", "阪神", 0.910),
                    _row(3, "坂本勇人", "巨人", 0.880),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        last = result["draft_text"].rsplit("\n", 1)[-1]
        self.assertIn("#巨人", last)
        self.assertIn("#ジャイアンツ", last)
        self.assertIn("#岡本和真", last)
        self.assertIn("#坂本勇人", last)

    def test_dynamic_tags_skip_non_giants_player_names(self) -> None:
        parsed = {"metric": "OPS", "top_n": 3}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "佐藤輝明", "阪神", 0.945),
                    _row(2, "村上宗隆", "ヤクルト", 0.921),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        last = result["draft_text"].rsplit("\n", 1)[-1]
        self.assertIn("#巨人", last)
        self.assertNotIn("#佐藤輝明", last)
        self.assertNotIn("#村上宗隆", last)

    def test_dynamic_tags_add_baseball_tag_for_pitcher_metric(self) -> None:
        parsed = {"metric": "ERA", "top_n": 2}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "戸郷翔征", "巨人", 2.50),
                    _row(2, "村上頌樹", "阪神", 2.80),
                ]
            ),
        )
        self.assertTrue(result["ok"])
        last = result["draft_text"].rsplit("\n", 1)[-1]
        self.assertIn("#戸郷翔征", last)
        self.assertIn("#プロ野球", last)

    def test_explicit_hashtags_override_still_works(self) -> None:
        """既存挙動: hashtags="..." 引数で override すれば動的化が抑制される。"""
        parsed = {"metric": "OPS", "top_n": 2}
        result = format_as_x_post(
            parsed,
            _make_rank_result(
                [
                    _row(1, "岡本和真", "巨人", 0.950),
                    _row(2, "佐藤輝明", "阪神", 0.910),
                ]
            ),
            hashtags="#カスタム",
        )
        self.assertTrue(result["ok"])
        last = result["draft_text"].rsplit("\n", 1)[-1]
        self.assertEqual(last, "#カスタム")


if __name__ == "__main__":
    unittest.main()
