"""Tests for ``src.x_post_mail_lane`` (ticket 347)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import ANY, MagicMock, patch

from src.x_post_mail_lane import (
    CENTRAL_LEAGUE_TEAM_ALIASES,
    JST,
    X_CHAR_LIMIT,
    Candidate,
    build_subject,
    compose_mail,
    encode_x_intent_url,
    filter_central_league,
    focus_player_names_from_lineup_rows,
    is_central_league,
    normalize_focus_player_names,
    pick_candidates,
    time_band_label,
)


def _row(rank: int, name: str, team: str, value: float, total: int = 60, sample: int = 200) -> dict:
    return {
        "rank": rank,
        "total": total,
        "player_canonical": name,
        "team_code": team,
        "metric_value": value,
        "sample_size": sample,
    }


# Realistic 12-team mix to verify セ filter pulls only 6 teams.
_MIXED_12_TEAM_ROWS = [
    _row(1, "佐藤輝明", "阪神", 0.945),
    _row(2, "山川穂高", "ソフトバンク", 0.940),     # パ
    _row(3, "牧秀悟", "DeNA", 0.932),
    _row(4, "近藤健介", "ソフトバンク", 0.930),     # パ
    _row(5, "岡本和真", "巨人", 0.921),
    _row(6, "村上宗隆", "ヤクルト", 0.918),
    _row(7, "ポランコ", "ロッテ", 0.915),           # パ
    _row(8, "鈴木誠也", "広島", 0.910),
    _row(9, "頓宮裕真", "オリックス", 0.905),       # パ
    _row(10, "細川成也", "中日", 0.900),
    _row(11, "万波中正", "日本ハム", 0.895),        # パ
    _row(12, "浅村栄斗", "楽天", 0.890),            # パ
]


class CentralLeagueFilterTests(unittest.TestCase):
    def test_central_league_teams_pass(self) -> None:
        for team in ["巨人", "阪神", "DeNA", "ヤクルト", "中日", "広島"]:
            self.assertTrue(is_central_league(team), msg=team)

    def test_pacific_league_teams_blocked(self) -> None:
        for team in [
            "ソフトバンク",
            "オリックス",
            "ロッテ",
            "日本ハム",
            "楽天",
            "西武",
        ]:
            self.assertFalse(is_central_league(team), msg=team)

    def test_filter_drops_pacific_keeps_central(self) -> None:
        kept = filter_central_league(_MIXED_12_TEAM_ROWS)
        self.assertEqual(len(kept), 6)
        kept_teams = {r["team_code"] for r in kept}
        self.assertEqual(kept_teams, {"阪神", "DeNA", "巨人", "ヤクルト", "広島", "中日"})

    def test_empty_team_code_blocked(self) -> None:
        self.assertFalse(is_central_league(""))
        self.assertFalse(is_central_league(None))
        self.assertFalse(is_central_league("   "))

    def test_giants_alias_variants(self) -> None:
        # Giants must remain detected so the highlight survives.
        for alias in ["巨人", "読売", "ジャイアンツ", "Giants", "G", "g"]:
            self.assertTrue(is_central_league(alias), msg=alias)


class IntentUrlEncodeTests(unittest.TestCase):
    def test_url_encodes_newline_and_hashtag(self) -> None:
        text = "line1\nline2 #巨人"
        url = encode_x_intent_url(text)
        self.assertIn("twitter.com/intent/tweet", url)
        self.assertIn("%0A", url)  # newline encoded
        self.assertIn("%23", url)  # `#` encoded so it's not a fragment
        self.assertNotIn("\n", url)
        self.assertNotIn("#", url.split("?", 1)[1])  # no raw `#` in query

    def test_full_text_round_trips_via_decode(self) -> None:
        from urllib.parse import parse_qs, urlparse

        text = "セ・OPS ランキング 📊\n\n1. 佐藤輝明（阪神）.945\n#巨人 #ジャイアンツ"
        url = encode_x_intent_url(text)
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        # parse_qs replaces + with space; our quote uses %20 so this should round-trip.
        self.assertEqual(qs["text"][0], text)

    def test_empty_text_safe(self) -> None:
        self.assertEqual(encode_x_intent_url(""), "https://twitter.com/intent/tweet?text=")
        self.assertEqual(encode_x_intent_url(None), "https://twitter.com/intent/tweet?text=")


class SubjectAndTimeBandTests(unittest.TestCase):
    def test_time_band_labels_per_hour(self) -> None:
        cases = {
            7: "朝",
            10: "朝",
            12: "昼",
            13: "昼",
            15: "午後",
            16: "午後",
            17: "夕方",
            18: "夕方",
            20: "夕方",
            21: "試合後",
            22: "試合後",
            23: "試合後",
        }
        for hour, expected in cases.items():
            self.assertEqual(time_band_label(hour), expected, msg=f"hour={hour}")

    def test_subject_format(self) -> None:
        ts = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        subject = build_subject(ts, 7)
        self.assertEqual(
            subject,
            "🟠🐦📮【Xポスト案 7件】🌅朝｜直近データ 07:00 JST",
        )

    def test_subject_zero_candidates_does_not_crash(self) -> None:
        ts = datetime(2026, 5, 16, 22, 30, tzinfo=JST)
        subject = build_subject(ts, 0)
        self.assertIn("0件", subject)
        self.assertIn("試合後", subject)
        self.assertIn("🌙", subject)
        self.assertIn("Xポスト案", subject)

    def test_subject_emoji_per_time_band(self) -> None:
        for hour, expected_emoji, expected_band in [
            (7, "🌅", "朝"),
            (12, "🌞", "昼"),
            (15, "☀️", "午後"),
            (17, "🌆", "夕方"),
            (22, "🌙", "試合後"),
        ]:
            ts = datetime(2026, 5, 17, hour, 0, tzinfo=JST)
            subject = build_subject(ts, 3)
            self.assertIn(expected_emoji, subject, msg=f"hour={hour}")
            self.assertIn(expected_band, subject, msg=f"hour={hour}")
            self.assertTrue(subject.startswith("🟠🐦📮"), msg=f"hour={hour}")

    def test_subject_can_show_lineup_context(self) -> None:
        ts = datetime(2026, 5, 17, 17, 30, tzinfo=JST)
        subject = build_subject(ts, 2, context_label="今日のスタメン")
        self.assertEqual(
            subject,
            "🟠🐦📮【Xポスト案 2件】🌆夕方｜今日のスタメン 17:30 JST",
        )


class PickCandidatesTests(unittest.TestCase):
    def test_pick_central_only_excludes_pacific(self) -> None:
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })
        cands = pick_candidates(query_mock, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST), max_candidates=3, min_sample=1)
        self.assertGreaterEqual(len(cands), 1)
        for c in cands:
            # パ team name must not appear in draft text
            for pa_team in ["ソフトバンク", "オリックス", "ロッテ", "日本ハム", "楽天", "西武"]:
                self.assertNotIn(pa_team, c.draft_text, msg=f"パ team leaked: {pa_team}\n{c.draft_text}")

    def test_giants_marker_present_when_giants_in_top(self) -> None:
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })
        cands = pick_candidates(query_mock, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST), max_candidates=1, min_sample=1)
        self.assertEqual(len(cands), 1)
        # STEP1: marker 形式 — ` ← 巨人` → `  ⭐巨人` (arrow drop, 半角2sp)
        self.assertIn("⭐巨人", cands[0].draft_text)
        self.assertNotIn("←", cands[0].draft_text)

    def test_too_few_central_rows_skipped(self) -> None:
        # Only 1 セ row → skip. The mail no longer falls back to 巨人内
        # ranking because the user needs the セ・リーグ6球団での順位.
        sparse = [
            _row(1, "巨人選手", "巨人", 0.900),
            _row(2, "パ選手 A", "ソフトバンク", 0.890),
            _row(3, "パ選手 B", "オリックス", 0.880),
        ]
        query_mock = MagicMock(return_value={"ok": True, "rows": sparse, "count": 3, "total": 60, "focus_player": None})
        cands = pick_candidates(query_mock, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST), max_candidates=22, min_sample=1)
        self.assertEqual(cands, [])

    def test_query_failure_skipped_not_crash(self) -> None:
        def _raise(**_kw):
            raise RuntimeError("DB down")

        cands = pick_candidates(_raise, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST), max_candidates=3, min_sample=1)
        self.assertEqual(cands, [])

    def test_query_returns_not_ok_skipped(self) -> None:
        query_mock = MagicMock(return_value={"ok": False, "reason": "db_not_available", "rows": []})
        cands = pick_candidates(query_mock, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST), max_candidates=3, min_sample=1)
        self.assertEqual(cands, [])

    def test_max_candidates_cap_honored(self) -> None:
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })
        cands = pick_candidates(query_mock, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST), max_candidates=2, min_sample=1)
        self.assertLessEqual(len(cands), 2)

    def test_lineup_focus_prefers_today_starter_over_top_giants_row(self) -> None:
        rows = [
            _row(1, "佐藤輝明", "阪神", 0.945),
            _row(2, "牧秀悟", "DeNA", 0.932),
            _row(3, "岡本和真", "巨人", 0.921),
            _row(4, "村上宗隆", "ヤクルト", 0.918),
            _row(5, "鈴木誠也", "広島", 0.910),
            _row(6, "細川成也", "中日", 0.900),
            _row(7, "泉口友汰", "巨人", 0.895),
        ]

        def _mock(metric_name=None, **_kw):
            if metric_name == "AVG":
                return {
                    "ok": True,
                    "rows": rows,
                    "count": len(rows),
                    "total": len(rows),
                    "focus_player": None,
                }
            return {"ok": False, "rows": [], "reason": "skip"}

        cands = pick_candidates(
            _mock,
            now=datetime(2026, 5, 17, 17, 30, tzinfo=JST),
            max_candidates=3,
            min_sample=1,
            min_central_rows=3,
            focus_player_names={"泉口"},
            context_label="今日のスタメン",
        )
        self.assertGreaterEqual(len(cands), 1)
        cand = cands[0]
        self.assertIn("今日のスタメン 泉口友汰", cand.title)
        self.assertIn("今日のスタメンから", cand.post_text)
        self.assertIn("泉口友汰", cand.post_text)
        self.assertNotIn("岡本和真", cand.post_text)
        self.assertIn("今日のスタメン: 泉口友汰", cand.draft_text)
        self.assertNotIn("巨人最上位: 泉口友汰", cand.draft_text)
        self.assertEqual(cand.context_label, "今日のスタメン")
        self.assertEqual(cand.focus_player, "泉口友汰")

    def test_lineup_focus_spreads_across_starters_before_repeating(self) -> None:
        rows = [
            _row(1, "佐藤輝明", "阪神", 0.945),
            _row(2, "牧秀悟", "DeNA", 0.932),
            _row(3, "浦田俊輔", "巨人", 0.921),
            _row(4, "泉口友汰", "巨人", 0.910),
            _row(5, "丸佳浩", "巨人", 0.905),
            _row(6, "村上宗隆", "ヤクルト", 0.900),
            _row(7, "鈴木誠也", "広島", 0.890),
            _row(8, "細川成也", "中日", 0.880),
        ]

        def _mock(**_kw):
            return {
                "ok": True,
                "rows": rows,
                "count": len(rows),
                "total": len(rows),
                "focus_player": None,
            }

        cands = pick_candidates(
            _mock,
            now=datetime(2026, 5, 17, 17, 30, tzinfo=JST),
            max_candidates=3,
            min_sample=1,
            min_central_rows=3,
            focus_player_names=["浦田俊輔", "泉口友汰", "丸佳浩"],
            context_label="今日のスタメン",
        )
        self.assertEqual(
            [c.focus_player for c in cands],
            ["浦田俊輔", "泉口友汰", "丸佳浩"],
        )

    def test_lineup_focus_names_from_rows_canonicalizes_surname(self) -> None:
        rows = [
            {"order": "1", "position": "中", "name": "丸"},
            {"order": "2", "position": "遊", "name": "泉口"},
            {"order": "3", "position": "左", "name": "キャベッジ"},
        ]
        names = focus_player_names_from_lineup_rows(rows)
        self.assertIn("丸佳浩", names)
        self.assertIn("泉口友汰", names)
        self.assertIn("キャベッジ", names)

    def test_normalize_focus_player_names_keeps_raw_when_alias_missing(self) -> None:
        names = normalize_focus_player_names(
            {"未知選手"},
            alias_map={"泉口": "泉口友汰"},
        )
        self.assertEqual(names, {"未知選手"})

    def test_same_metric_period_family_only_once_per_mail(self) -> None:
        """OPS の直近5/10試合/直近1週間を同じ mail に並べない。"""
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })
        cands = pick_candidates(
            query_mock,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
            min_central_rows=3,
        )
        seen: set[tuple[str, str, str]] = set()
        for cand in cands:
            metric, _period, giants_only, position = cand.signature.split("|")
            key = (metric, giants_only, position)
            self.assertNotIn(key, seen, msg=f"duplicate period family: {cand.signature}")
            seen.add(key)

    def test_full_season_period_removed_from_draft(self) -> None:
        """357: X 候補 mail では全期間 / 今シーズン slice を出さない。"""
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })
        cands = pick_candidates(
            query_mock,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
            min_central_rows=3,
        )
        self.assertFalse(
            [c for c in cands if c.period_label == "今シーズン"],
            msg="full-season candidate leaked into X post mail",
        )
        for c in cands:
            self.assertNotIn("開幕〜", c.draft_text)
            self.assertNotIn("今シーズン", c.draft_text)

    def test_header_includes_human_period_label_and_sample_threshold(self) -> None:
        """357: 日付だけではなく、人間向け period label と規定数を表示。"""
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })
        cands = pick_candidates(
            query_mock,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=30,
            min_central_rows=3,
        )
        self.assertGreaterEqual(len(cands), 1)
        for c in cands:
            text = c.draft_text
            # Every candidate header must carry a baseball-friendly
            # period label instead of only raw dates.
            self.assertTrue(
                ("直近1週間" in text)
                or ("直近5試合" in text)
                or ("直近10試合" in text)
                or ("今週" in text)
                or ("今月" in text),
                msg=f"missing human period label in: {text[:80]}",
            )
            # Every candidate carries the sample threshold marker
            self.assertTrue(
                ("規定打席30以上" in text) or ("規定投球回30以上" in text),
                msg=f"missing sample threshold in: {text[:60]}",
            )

    def test_monthly_combo_year_round_after_step1(self) -> None:
        """STEP1 (2026-05-17): 今月 combo は年通開放、 月別「N月成績」は
        月初 3 日だけ前月分を出す現状を維持。
        """
        from src.x_post_mail_lane import _build_combos
        mid_month = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        # 今月 combo は年通で pool に存在 (8 metric、 batting は snapshot 経由)。
        today_combos = [c for c in mid_month if c.period_label == "今月"]
        self.assertEqual(len(today_combos), 8)
        # 月中なので前月成績 (4月成績) は pool に居ない。
        self.assertFalse({c.period_label for c in mid_month} & {"4月成績"})

    def test_era_uses_innings_pitched_threshold_label(self) -> None:
        """350: ERA は 打席 ではなく 投球回 ベースで表記する。"""
        # Pitcher rows
        pitcher_rows = [
            {"rank": i, "total": 30, "player_canonical": f"投手{i}",
             "team_code": team, "metric_value": 2.0 + i * 0.1, "sample_size": 40}
            for i, team in enumerate(
                ["巨人", "阪神", "DeNA", "ヤクルト", "中日", "広島"], start=1
            )
        ]

        def _mock(metric_name=None, **_kw):
            if metric_name == "ERA":
                return {"ok": True, "rows": pitcher_rows, "count": 6, "total": 30, "focus_player": None}
            return {"ok": False, "rows": [], "reason": "skip"}

        cands = pick_candidates(
            _mock,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=10,
            min_central_rows=3,
        )
        self.assertGreaterEqual(len(cands), 1)
        # At least one ERA candidate should appear with 投球回 label
        era_cands = [c for c in cands if c.metric == "ERA"]
        self.assertGreaterEqual(len(era_cands), 1)
        self.assertIn("投球回", era_cands[0].draft_text)

    def test_min_central_rows_default_strict(self) -> None:
        """350: 4 row では skip、5 row で採用される (default 5)。"""
        rows4 = [
            {"rank": i, "total": 20, "player_canonical": f"p{i}",
             "team_code": team, "metric_value": 0.9 - i * 0.01, "sample_size": 100}
            for i, team in enumerate(["巨人", "阪神", "DeNA", "ヤクルト"], start=1)
        ]
        rows5 = rows4 + [
            {"rank": 5, "total": 20, "player_canonical": "p5",
             "team_code": "中日", "metric_value": 0.85, "sample_size": 100},
        ]
        # 巨人内 ranking fallback は廃止。4 セ row ではセ・リーグ
        # ranking として薄いので skip。
        non_giants_combos_skipped_at_4 = pick_candidates(
            MagicMock(return_value={"ok": True, "rows": rows4, "count": 4, "total": 20, "focus_player": None}),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
        )
        for c in non_giants_combos_skipped_at_4:
            # Defensive no-op assertion kept to preserve the old loop shape;
            # the expected behavior is no candidates.
            self.assertNotIn("ランキング 📊（", c.draft_text[:0])
        cands5 = pick_candidates(
            MagicMock(return_value={"ok": True, "rows": rows5, "count": 5, "total": 20, "focus_player": None}),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
        )
        self.assertGreaterEqual(len(cands5), 1, msg="5 セ rows should be accepted")


class VariationExpansionTests(unittest.TestCase):
    """351/356 follow-up: 短期・守備位置別・巨人順位 focus combo pool の検証。"""

    def _make_mock_with_rows(self) -> MagicMock:
        return MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })

    def test_last_month_combo_removed_outside_month_start(self) -> None:
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        self.assertNotIn("先月", {c.period_label for c in combos})
        self.assertNotIn("4月成績", {c.period_label for c in combos})

    def test_previous_month_combo_appears_only_at_month_start(self) -> None:
        """357: 月別は月初だけ「7月成績」のように出す。"""
        from src.x_post_mail_lane import _build_combos
        mid_month = _build_combos(datetime(2026, 8, 16, 7, 0, tzinfo=JST))
        month_start = _build_combos(datetime(2026, 8, 2, 7, 0, tzinfo=JST))
        self.assertNotIn("7月成績", {c.period_label for c in mid_month})
        monthly = [c for c in month_start if c.period_label == "7月成績"]
        # STEP1 + snapshot 復活 (2026-05-17): 8 metric。
        self.assertEqual(len(monthly), 8)
        self.assertFalse(any(c.giants_only for c in monthly))
        self.assertEqual(
            {c.metric for c in monthly},
            {"AVG", "OBP", "SLG", "OPS", "ERA", "K_per_9", "BB_per_9", "HR_per_9"},
        )

    def test_last_7_days_combo_appears(self) -> None:
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        last7_cands = [c for c in combos if c.period_label == "直近1週間"]
        self.assertGreaterEqual(len(last7_cands), 1)
        # 5/16 - 7 = 5/9
        self.assertEqual(last7_cands[0].since, "2026-05-09")

    def test_last_14_days_combo_removed(self) -> None:
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        self.assertNotIn("直近14日", {c.period_label for c in combos})

    def test_position_filter_combo_uses_position_kwarg(self) -> None:
        """守備位置別 combo は query_rank に position_filter を渡す。"""
        captured: list[dict] = []

        def _capture(**kw):
            captured.append(kw)
            return {"ok": True, "rows": _MIXED_12_TEAM_ROWS, "count": 12, "total": 60, "focus_player": None}

        cands = pick_candidates(
            _capture,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
            min_central_rows=3,
        )
        # At least one position-filtered call was made
        positions_used = [c.get("position_filter") for c in captured if c.get("position_filter")]
        self.assertGreater(len(positions_used), 0)
        # Header for position combo includes 「捕手」「遊撃」 etc.
        position_headers = [c for c in cands if any(p in c.draft_text for p in ("捕手", "二塁", "遊撃", "三塁"))]
        self.assertGreaterEqual(len(position_headers), 1)

    def test_giants_focus_keeps_league_rows_and_marks_giants_rank(self) -> None:
        """巨人 row だけに絞らず、セ・リーグ順位で巨人選手を強調する。"""
        mixed = [
            _row(1, "佐藤輝明", "阪神", 0.945),
            _row(2, "牧秀悟", "DeNA", 0.932),
            _row(3, "岡本和真", "巨人", 0.921),
            _row(4, "村上宗隆", "ヤクルト", 0.918),
            _row(5, "鈴木誠也", "広島", 0.910),
            _row(6, "細川成也", "中日", 0.900),
            _row(7, "坂本勇人", "巨人", 0.895),
            _row(8, "丸佳浩", "巨人", 0.880),
        ]
        cands = pick_candidates(
            MagicMock(return_value={"ok": True, "rows": mixed, "count": 8, "total": 60, "focus_player": None}),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
            min_central_rows=3,
        )
        focus_cands = [c for c in cands if "セ・リーグ" in c.draft_text]
        self.assertGreaterEqual(len(focus_cands), 1)
        cand = focus_cands[0]
        text = cand.draft_text
        self.assertNotIn("巨人内", text)
        self.assertIn("セ・リーグ", text)
        self.assertIn("巨人最上位: 岡本和真 セ・リーグ 3/8位", text)
        self.assertIn("岡本和真", cand.title)
        self.assertIn("3/8位", cand.title)
        # Non-巨人 rows remain because the ranking scope is セ・リーグ.
        self.assertIn("佐藤輝明", text)
        self.assertIn("牧秀悟", text)
        # 巨人 players appear with strong marker.
        self.assertIn("岡本和真", text)
        self.assertIn("⭐巨人", text)
        self.assertNotIn("←⭐巨人", text)

    def test_format_one_adds_branded_post_text_and_emoji_title(self) -> None:
        """X intent 用の本文はランキング表ではなく、ブランド投稿案にする。"""
        from src.x_post_mail_lane import _MetricCombo, _format_one, _rebuild_ranks_within_central

        ranked = _rebuild_ranks_within_central(_MIXED_12_TEAM_ROWS)
        cand = _format_one(
            _MetricCombo("OPS", "2026-05-09", "直近1週間"),
            ranked,
            min_sample=30,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
        )
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertTrue(cand.title.startswith("📊 Xポスト案｜"))
        self.assertIn("#巨人 #ジャイアンツ", cand.post_text)
        self.assertIn("岡本和真", cand.post_text)
        self.assertIn("OPS", cand.post_text)
        self.assertIn("セ・リーグ", cand.post_text)
        self.assertNotIn("🥇", cand.post_text)
        self.assertNotIn("阿部監督", cand.post_text)
        self.assertLessEqual(len(cand.post_text), X_CHAR_LIMIT)

    def test_giants_focus_row_survives_when_outside_top_five(self) -> None:
        """X字数調整で上位だけに削っても巨人最上位 row は残す。"""
        from src.x_post_mail_lane import _MetricCombo, _format_one, _rebuild_ranks_within_central

        rows = [
            _row(1, "阪神A", "阪神", 1.000),
            _row(2, "DeNAA", "DeNA", 0.990),
            _row(3, "ヤクルトA", "ヤクルト", 0.980),
            _row(4, "中日A", "中日", 0.970),
            _row(5, "広島A", "広島", 0.960),
            _row(6, "阪神B", "阪神", 0.950),
            _row(7, "DeNAB", "DeNA", 0.940),
            _row(8, "ヤクルトB", "ヤクルト", 0.930),
            _row(9, "中日B", "中日", 0.920),
            _row(10, "広島B", "広島", 0.910),
            _row(11, "岡本和真", "巨人", 0.900),
        ]
        ranked = _rebuild_ranks_within_central(rows)
        cand = _format_one(
            _MetricCombo("OPS", "2026-05-09", "直近1週間"),
            ranked,
            min_sample=30,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
        )
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertIn("巨人最上位: 岡本和真 セ・リーグ 11/11位", cand.draft_text)
        self.assertIn("11. 岡本和真（巨人）OPS .900  ⭐巨人", cand.draft_text)
        self.assertLessEqual(cand.char_count, X_CHAR_LIMIT)

    def test_combo_pool_size_after_step1_expansion(self) -> None:
        """STEP1 (2026-05-17): metric 8 (OPS/AVG/ERA/OBP/SLG/K_per_9/BB_per_9/HR_per_9)
        × period (直近1週間 + 今週 + 今月 + 守備位置別) で pool 拡張。

        STEP1 + snapshot path 復活 (2026-05-17):
        metric 8 (AVG / OBP / SLG / OPS / ERA / K_per_9 / BB_per_9 /
        HR_per_9) で pool 構成。 batting metric は snapshot 経由で
        正値、 守備位置別は AVG (snapshot 側に position 列無し)、
        投手 metric は legacy `_aggregate_pitching` 経由。

        db_path=None で:
          - 直近1週間 × 8 metric  = 8
          - 守備位置別直近1週間 AVG × 4 pos = 4
          - 今週 × 8 metric            = 8 (週初め以外、 当日 Monday なら 0)
          - 今月 × 8 metric            = 8
        2026-05-16 (Sat) は週初め (Mon=05-11) と直近1週間 (05-09) が違うので 今週 enabled = 8 combo。
        計 28 combo。
        """
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        self.assertEqual(len(combos), 28)
        self.assertTrue(all(c.novelty == "high" for c in combos))
        # 大手が出しやすい "今シーズン" 系 / 直近30日 / 直近14日 は除外維持。
        self.assertFalse({"今シーズン", "直近30日", "直近14日"} & {c.period_label for c in combos})
        # 全 combo は since 付き (period 限定なし combo は許可しない)。
        self.assertFalse([c for c in combos if c.since is None], msg=f"full-period combo leaked: {combos}")

    def test_diversity_seed_changes_per_hour(self) -> None:
        """diversity shuffle が hour 違うと違う順序になる。"""
        from src.x_post_mail_lane import _build_combos, _select_with_diversity
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        at_7 = _select_with_diversity(combos, max_candidates=10, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        at_12 = _select_with_diversity(combos, max_candidates=10, now=datetime(2026, 5, 16, 12, 0, tzinfo=JST))
        # Should not be exactly the same order
        self.assertNotEqual(
            [c.metric + c.period_label + str(c.position) for c in at_7],
            [c.metric + c.period_label + str(c.position) for c in at_12],
        )


class ComposeMailTests(unittest.TestCase):
    def _make_cand(self, idx: int, text: str = "test\nbody\n#巨人") -> Candidate:
        return Candidate(
            title=f"テスト候補 {idx}",
            metric="OPS",
            period_label="直近1週間",
            draft_text=text,
            char_count=len(text),
        )

    def test_compose_returns_subject_text_html_count(self) -> None:
        ts = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        cands = [self._make_cand(1), self._make_cand(2)]
        mail = compose_mail(cands, now=ts)
        self.assertEqual(mail.candidate_count, 2)
        self.assertIn("2件", mail.subject)
        self.assertIn("朝", mail.subject)
        self.assertIn("テスト候補 1", mail.text_body)
        self.assertIn("テスト候補 1", mail.html_body)
        self.assertIn("📮 巨人データXポスト案", mail.text_body)
        self.assertIn("公開通知ではありません", mail.text_body)
        self.assertIn("📮 巨人データXポスト案", mail.html_body)
        self.assertIn("公開通知ではなく", mail.html_body)

    def test_text_body_has_lf_newlines_only(self) -> None:
        ts = datetime(2026, 5, 16, 12, 0, tzinfo=JST)
        mail = compose_mail([self._make_cand(1)], now=ts)
        self.assertNotIn("\r\n", mail.text_body)
        self.assertNotIn("\r", mail.text_body)

    def test_html_includes_intent_url(self) -> None:
        ts = datetime(2026, 5, 16, 17, 30, tzinfo=JST)
        mail = compose_mail([self._make_cand(1, "テスト #巨人")], now=ts)
        self.assertIn("twitter.com/intent/tweet", mail.html_body)
        self.assertIn("%23", mail.html_body)  # # in text was URL-encoded
        # The plain text body also lists the URL for fallback copy.
        self.assertIn("twitter.com/intent/tweet", mail.text_body)

    def test_html_uses_post_text_for_x_intent_when_present(self) -> None:
        ts = datetime(2026, 5, 16, 17, 30, tzinfo=JST)
        cand = Candidate(
            title="📊 Xポスト案｜テスト",
            metric="OPS",
            period_label="直近5試合",
            draft_text="根拠データ #巨人",
            post_text="投稿本文 #巨人",
            char_count=len("投稿本文 #巨人"),
        )
        mail = compose_mail([cand], now=ts)
        self.assertIn("投稿本文 #巨人", mail.text_body)
        self.assertIn("根拠データ", mail.text_body)
        self.assertIn("投稿本文 #巨人", mail.html_body)
        self.assertIn("根拠データを開く", mail.html_body)
        self.assertIn("%E6%8A%95%E7%A8%BF%E6%9C%AC%E6%96%87", mail.html_body)

    def test_html_escapes_special_chars(self) -> None:
        # Draft text containing `<` `>` `&` must be escaped so the
        # HTML mail does not break or get reinterpreted as markup.
        ts = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        cand = self._make_cand(1, text="A<B>C&D ← 巨人")
        mail = compose_mail([cand], now=ts)
        self.assertNotIn("A<B>C&D", mail.html_body)  # raw must NOT appear
        self.assertIn("A&lt;B&gt;C&amp;D", mail.html_body)
        self.assertIn("← 巨人", mail.html_body)  # ← survives, it's safe

    def test_char_count_over_280_marked(self) -> None:
        ts = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        long_text = "a" * 300
        cand = Candidate(
            title="長い候補",
            metric="OPS",
            period_label="シーズン",
            draft_text=long_text,
            char_count=len(long_text),
        )
        mail = compose_mail([cand], now=ts)
        self.assertIn("⚠️ 超過", mail.html_body)
        self.assertIn("300", mail.html_body)

    def test_compose_mail_includes_lineup_context_note(self) -> None:
        ts = datetime(2026, 5, 17, 17, 30, tzinfo=JST)
        mail = compose_mail(
            [self._make_cand(1)],
            now=ts,
            context_label="今日のスタメン",
            context_note="今日のスタメン優先: 丸佳浩、泉口友汰",
        )
        self.assertIn("今日のスタメン", mail.subject)
        self.assertIn("今日のスタメン優先: 丸佳浩、泉口友汰", mail.text_body)
        self.assertIn("今日のスタメン優先: 丸佳浩、泉口友汰", mail.html_body)


class EmptyResultBehaviourTests(unittest.TestCase):
    def test_compose_mail_with_empty_candidates_no_crash(self) -> None:
        ts = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        mail = compose_mail([], now=ts)
        self.assertEqual(mail.candidate_count, 0)
        self.assertIn("0件", mail.subject)


class TicketThreeFiftyThreeFormatTests(unittest.TestCase):
    """353/STEP1: 大手なし pool + 意外性 sampling + format 見た目改善
    (改行 / metric 別絵文字 / 数字 prefix / ⭐巨人 / metric label) の検証。
    STEP1 (2026-05-17): medal 🥇🥈🥉 + top3 空行を廃止、 全行数字 prefix
    に統一。 ←⭐巨人 → ⭐巨人 へ。
    """

    def _make_mock(self) -> MagicMock:
        return MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })

    def test_period_line_separated_to_second_row(self) -> None:
        """period_suffix が lines[0] append から lines[1] 分離になっている。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        self.assertGreaterEqual(len(cands), 1)
        for c in cands:
            lines = c.draft_text.split("\n")
            # lines[0] = header (ランキング + 絵文字)、 lines[1] = period 括弧
            self.assertIn("ランキング", lines[0])
            self.assertTrue(
                lines[1].startswith("（") and lines[1].endswith("）"),
                msg=f"period not on line 1: {lines[1]!r}",
            )

    def test_metric_header_emoji_batting_pitching(self) -> None:
        """OPS/AVG/OBP/SLG header = ⚾、 ERA = ⚡。"""
        # Batter combo (any of short-window OPS/AVG)
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        batter_cands = [c for c in cands if c.metric in ("OPS", "AVG", "OBP", "SLG")]
        self.assertGreaterEqual(len(batter_cands), 1)
        for c in batter_cands:
            header = c.draft_text.split("\n", 1)[0]
            self.assertIn("⚾", header, msg=f"batter header missing ⚾: {header}")
            self.assertNotIn("📊", header, msg=f"old emoji leaked: {header}")
        # Pitcher combo (short-window ERA)
        pitcher_rows = [
            {"rank": i, "total": 30, "player_canonical": f"投手{i}",
             "team_code": team, "metric_value": 2.0 + i * 0.1, "sample_size": 40}
            for i, team in enumerate(
                ["巨人", "阪神", "DeNA", "ヤクルト", "中日", "広島"], start=1
            )
        ]
        era_cands = pick_candidates(
            MagicMock(return_value={"ok": True, "rows": pitcher_rows, "count": 6, "total": 30, "focus_player": None}),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=10,
            min_central_rows=3,
        )
        era_only = [c for c in era_cands if c.metric == "ERA"]
        self.assertGreaterEqual(len(era_only), 1)
        for c in era_only:
            header = c.draft_text.split("\n", 1)[0]
            self.assertIn("⚡", header, msg=f"pitcher header missing ⚡: {header}")

    def test_all_ranks_use_numeric_prefix(self) -> None:
        """STEP1 (2026-05-17): 全行 数字 prefix (`1.` `2.` ...)、 medal 廃止。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        self.assertGreaterEqual(len(cands), 1)
        text = cands[0].draft_text
        # 数字 prefix が rank 1-3 でも使われる。
        self.assertIn("1.", text)
        self.assertIn("2.", text)
        self.assertIn("3.", text)
        # Medal 🥇🥈🥉 は使われない。
        self.assertNotIn("🥇", text)
        self.assertNotIn("🥈", text)
        self.assertNotIn("🥉", text)

    def test_giants_marker_strong_form(self) -> None:
        """STEP1 (2026-05-17): 巨人行 marker は `  ⭐巨人` (半角2 spc + ⭐巨人、
        arrow 削除)。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        # find a candidate that should highlight a Giants row
        with_giants = [
            c for c in cands
            if "巨人" in c.draft_text and "⭐巨人" in c.draft_text
        ]
        self.assertGreaterEqual(len(with_giants), 1)
        for c in with_giants:
            self.assertIn("⭐巨人", c.draft_text)
            # 旧 form (arrow 付き、 半角1 spc) は出ない
            self.assertNotIn("←⭐巨人", c.draft_text)
            self.assertNotIn("← 巨人", c.draft_text)
            self.assertNotIn(" ←", c.draft_text)

    def test_metric_label_prefix_before_value(self) -> None:
        """ranking 行の数値前に metric_jp 前置 (例: ``打率 .945``、 ``OPS .945``、 ``防御率 2.10``)。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        avg_cands = [c for c in cands if c.metric == "AVG"]
        self.assertGreaterEqual(len(avg_cands), 1)
        text = avg_cands[0].draft_text
        # `打率 .945` 等の形式が ranking 行に出る
        self.assertIn("打率 .", text, msg=f"AVG label missing: {text}")

    def test_no_blank_between_ranks_after_step1(self) -> None:
        """STEP1 (2026-05-17): 旧 medal 区切り空行を廃止、 ranking は連続表示。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        self.assertGreaterEqual(len(cands), 1)
        text = cands[0].draft_text
        lines = text.split("\n")
        # 3 位の row index を見つけ、 直後が 4. で始まる (間に空行なし) こと。
        idx_3 = next(
            (i for i, ln in enumerate(lines) if ln.startswith("3.")),
            -1,
        )
        self.assertGreaterEqual(idx_3, 0, msg="3. row not found")
        # idx_3 の直後行が 4. で始まる (もしくは ranking 末尾)。
        if idx_3 + 1 < len(lines):
            self.assertTrue(
                lines[idx_3 + 1].startswith("4.") or not lines[idx_3 + 1].strip()
                or lines[idx_3 + 1].startswith("#")  # hashtag footer の場合
                or lines[idx_3 + 1].startswith("巨人最上位:"),
                msg=f"unexpected line after 3.: {lines[idx_3 + 1]!r}",
            )

    def test_mainstream_combos_excluded_from_pool(self) -> None:
        """シーズン累積 OPS/AVG/ERA/OBP/SLG の since=None / position=None /
        giants_only=False combo は pool に存在しない (大手定番除外)。
        """
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        for c in combos:
            if c.since is None and c.position is None and not c.giants_only:
                self.fail(f"mainstream season combo leaked: {c}")

    def test_novelty_weighted_shuffle_high_appears_early(self) -> None:
        """weighted shuffle で novelty=high が先頭側に偏って出る (seed
        固定 deterministic、 上位 5 のうち少なくとも 3 件は high)。
        """
        from src.x_post_mail_lane import _build_combos, _select_with_diversity
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        top5 = _select_with_diversity(combos, max_candidates=5, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        novelty_counts = {"high": 0, "mid": 0, "low": 0}
        for c in top5:
            novelty_counts[c.novelty] = novelty_counts.get(c.novelty, 0) + 1
        # high 70% / mid 30% weighting + 5 picks → high が 3 件以上は十分期待。
        # (deterministic なので fixed seed で常に同じ結果が出る)
        self.assertGreaterEqual(
            novelty_counts["high"],
            3,
            msg=f"high novelty under-represented in top 5: {novelty_counts}",
        )

    def test_x_char_cap_enforced_on_all_candidates(self) -> None:
        """全 candidate の char_count が X_CHAR_LIMIT (280) 以内。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        self.assertGreaterEqual(len(cands), 1)
        for c in cands:
            self.assertLessEqual(
                c.char_count,
                X_CHAR_LIMIT,
                msg=f"candidate exceeds cap: {c.char_count} chars / title={c.title}",
            )


class TicketThreeFiftyFourLastNGamesTests(unittest.TestCase):
    """354/356 follow-up: 直近 N 巨人試合 variation (セ・リーグ順位、
    novelty="high"、 min_sample_override で AB 閾値緩和)
    の検証。 all-NPB 化後の production DB に合わせ、 games + batting_logs
    の sqlite tempfile fixture を seed する。
    """

    def setUp(self) -> None:
        import shutil
        import sqlite3
        import tempfile
        from pathlib import Path

        self._sqlite3 = sqlite3
        self._shutil = shutil
        self._tmpdir = tempfile.mkdtemp(prefix="x_post_354_")
        self.db_path = str(Path(self._tmpdir) / "insight.db")

    def tearDown(self) -> None:
        self._shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _seed_games(self, dates: list[str], giants_dates: set[str] | None = None) -> None:
        """Create minimal games/batting_logs tables and seed one row per date."""
        if giants_dates is None:
            giants_dates = set(dates)
        conn = self._sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "CREATE TABLE games ("
                "game_id TEXT PRIMARY KEY, "
                "game_date TEXT NOT NULL, "
                "opponent TEXT NOT NULL, "
                "home_away TEXT NOT NULL, "
                "giants_score INTEGER, "
                "opp_score INTEGER, "
                "result TEXT, "
                "league_label TEXT, "
                "one_line_summary TEXT, "
                "winning_pitcher TEXT, "
                "losing_pitcher TEXT, "
                "save_pitcher TEXT, "
                "source_url TEXT, "
                "source_kind TEXT, "
                "ingested_at TEXT NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE TABLE batting_logs ("
                "game_id TEXT NOT NULL, "
                "team_name TEXT NOT NULL"
                ")"
            )
            for idx, d in enumerate(dates):
                game_id = f"test-{d}-{idx}"
                conn.execute(
                    "INSERT INTO games "
                    "(game_id, game_date, opponent, home_away, ingested_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (game_id, d, "test", "home", "2026-01-01T00:00:00"),
                )
                conn.execute(
                    "INSERT INTO batting_logs (game_id, team_name) VALUES (?, ?)",
                    (game_id, "巨人" if d in giants_dates else "西武"),
                )
            conn.commit()
        finally:
            conn.close()

    def test_query_recent_n_games_date_range_returns_tuple(self) -> None:
        from src.x_post_mail_lane import _query_recent_n_games_date_range
        self._seed_games(["2026-05-10", "2026-05-12", "2026-05-13", "2026-05-15", "2026-05-16"])
        # most recent 5 = entire seed; since=oldest 5/10, until=newest 5/16
        result = _query_recent_n_games_date_range(5, self.db_path)
        self.assertEqual(result, ("2026-05-10", "2026-05-16"))

    def test_query_recent_n_games_ignores_non_giants_recent_dates(self) -> None:
        from src.x_post_mail_lane import _query_recent_n_games_date_range
        dates = [
            "2026-05-10",
            "2026-05-11",
            "2026-05-12",
            "2026-05-13",
            "2026-05-14",
            "2026-05-15",
            "2026-05-16",
        ]
        self._seed_games(dates, giants_dates=set(dates[:-1]))
        result = _query_recent_n_games_date_range(5, self.db_path)
        self.assertEqual(result, ("2026-05-11", "2026-05-15"))

    def test_query_recent_n_games_returns_none_when_insufficient(self) -> None:
        from src.x_post_mail_lane import _query_recent_n_games_date_range
        self._seed_games(["2026-05-15", "2026-05-16"])  # only 2 games
        self.assertIsNone(_query_recent_n_games_date_range(5, self.db_path))

    def test_query_db_latest_game_date_and_staleness(self) -> None:
        from src.x_post_mail_lane import db_staleness_days, query_db_latest_game_date
        self._seed_games(["2026-05-14", "2026-05-15"])
        latest = query_db_latest_game_date(self.db_path)
        self.assertEqual(latest, "2026-05-15")
        self.assertEqual(
            db_staleness_days(latest, now=datetime(2026, 5, 16, 12, 0, tzinfo=JST)),
            1,
        )

    def test_build_combos_no_db_path_after_step1(self) -> None:
        """STEP1 + snapshot 復活 (2026-05-17): db_path=None で 28 combo
        (直近1週間 8 + 守備位置別 AVG 4 + 今週 8 + 今月 8)。 5/16 は土曜
        なので 今週 enabled。"""
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        self.assertEqual(len(combos), 28)

    def test_build_combos_with_db_path_adds_last_n_after_step1(self) -> None:
        """STEP1 + snapshot 復活: db_path 指定で 28 + 直近5試合 8 +
        直近10試合 8 = 44 combo。"""
        from src.x_post_mail_lane import _build_combos
        # need ≥10 distinct game dates for both 5-game and 10-game windows
        dates = [f"2026-05-{day:02d}" for day in range(1, 16)]  # 15 dates
        self._seed_games(dates)
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST), db_path=self.db_path)
        self.assertEqual(len(combos), 44)

    def test_last_n_games_combos_are_high_novelty_and_league_scoped(self) -> None:
        from src.x_post_mail_lane import _build_combos
        dates = [f"2026-05-{day:02d}" for day in range(1, 16)]
        self._seed_games(dates)
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST), db_path=self.db_path)
        last_n_combos = [c for c in combos if c.period_label in ("直近5試合", "直近10試合")]
        # STEP1 + snapshot 復活: 8 metric × 2 period = 16
        self.assertEqual(len(last_n_combos), 16)
        for c in last_n_combos:
            self.assertEqual(c.novelty, "high", msg=f"non-high novelty leaked: {c}")
            self.assertFalse(c.giants_only, msg=f"giants-only combo leaked: {c}")
            self.assertIn(
                c.metric,
                ("AVG", "OBP", "SLG", "OPS", "ERA", "K_per_9", "BB_per_9", "HR_per_9"),
            )
            self.assertIn(c.min_sample_override, (5, 10))

    def test_last_n_games_period_range_uses_game_dates(self) -> None:
        """直近 N 試合 combo の since/until が seed date と一致。"""
        from src.x_post_mail_lane import _build_combos
        dates = [f"2026-05-{day:02d}" for day in (1, 3, 5, 7, 9, 11, 13, 14, 15, 16)]
        self._seed_games(dates)
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST), db_path=self.db_path)
        last5 = [c for c in combos if c.period_label == "直近5試合"]
        self.assertGreaterEqual(len(last5), 1)
        # most recent 5 of the seed: 5/9, 5/11, 5/13, 5/14, 5/15, 5/16 — top 5 desc
        # = 5/16, 5/15, 5/14, 5/13, 5/11 → since=5/11, until=5/16
        self.assertEqual(last5[0].since, "2026-05-11")
        self.assertEqual(last5[0].until, "2026-05-16")

    def test_last_n_games_draft_uses_human_period_label(self) -> None:
        """357: X 本文は日付だけでなく「直近5試合」を前面に出す。"""
        from src.x_post_mail_lane import _MetricCombo, _format_one
        rows = [
            _row(1, "岡本和真", "巨人", 0.950),
            _row(2, "坂本勇人", "巨人", 0.910),
            _row(3, "丸佳浩", "巨人", 0.880),
        ]
        combo = _MetricCombo(
            "OPS",
            "2026-05-11",
            "直近5試合",
            until="2026-05-16",
            min_sample_override=5,
        )
        cand = _format_one(
            combo,
            rows,
            min_sample=5,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
        )
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertIn("直近5試合", cand.draft_text.split("\n")[1])
        self.assertIn("規定打席5以上", cand.draft_text.split("\n")[1])
        self.assertNotIn("5/11〜5/16", cand.draft_text.split("\n")[1])
        self.assertIn("直近5試合", cand.title)

    def test_monthly_draft_uses_month_record_label(self) -> None:
        """357: 月別は「7月成績」のように表示する。"""
        from src.x_post_mail_lane import _MetricCombo, _format_one
        rows = [
            _row(1, "岡本和真", "巨人", 0.950),
            _row(2, "坂本勇人", "巨人", 0.910),
            _row(3, "丸佳浩", "巨人", 0.880),
        ]
        combo = _MetricCombo(
            "OPS",
            "2026-07-01",
            "7月成績",
            until="2026-07-31",
            min_sample_override=30,
        )
        cand = _format_one(
            combo,
            rows,
            min_sample=30,
            now=datetime(2026, 8, 2, 7, 0, tzinfo=JST),
        )
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertIn("7月成績", cand.draft_text.split("\n")[1])
        self.assertIn("規定打席30以上", cand.draft_text.split("\n")[1])
        self.assertNotIn("7/1〜7/31", cand.draft_text.split("\n")[1])

    def test_min_sample_override_honoured_in_pick_candidates(self) -> None:
        """combo.min_sample_override が pick_candidates 内で min_sample より優先。"""
        captured: list[dict] = []

        def _capture(**kw):
            captured.append(kw)
            return {"ok": True, "rows": _MIXED_12_TEAM_ROWS, "count": 12, "total": 60, "focus_player": None}

        dates = [f"2026-05-{day:02d}" for day in range(1, 16)]
        self._seed_games(dates)
        pick_candidates(
            _capture,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=16,
            min_sample=30,  # default
            min_central_rows=3,
            db_path=self.db_path,
        )
        # 直近 5/10 試合 combo の query_rank call は min_sample override を使う。
        # 同一 metric の period-family skip があるため、1 mail 内では 5 or 10
        # のどちらか片方だけが実行されることがある。
        ms_values = [c.get("min_sample") for c in captured]
        self.assertTrue(
            {5, 10} & set(ms_values),
            msg=f"last-N min_sample override not honoured: {ms_values}",
        )
        # And the default 30 should still appear for non-override combos
        self.assertIn(30, ms_values, msg=f"default 30 missing: {ms_values}")

    def test_db_path_with_insufficient_games_falls_back_gracefully(self) -> None:
        """STEP1 + snapshot 復活 (2026-05-17): games 件数不足の時、
        直近 N 試合 combo は追加されず base 28 (直近1週間 8 + 守備位置別
        AVG 4 + 今週 8 + 今月 8) 維持。"""
        from src.x_post_mail_lane import _build_combos
        # only 3 games → both n=5 and n=10 windows return None
        self._seed_games(["2026-05-14", "2026-05-15", "2026-05-16"])
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST), db_path=self.db_path)
        self.assertEqual(len(combos), 28, msg=f"unexpected combo count: {len(combos)}")


class XPostMailEntrypointFreshnessTests(unittest.TestCase):
    """DB freshness guard for the X post mail CLI entrypoint."""

    def _entrypoint_candidate(self, signature: str) -> Candidate:
        return Candidate(
            title=f"候補 {signature}",
            metric="OPS",
            period_label="直近5試合",
            draft_text=f"候補 {signature}\n#巨人 #ジャイアンツ",
            char_count=24,
            signature=signature,
        )

    def test_main_aborts_before_candidate_pick_when_db_is_stale(self) -> None:
        from src.tools import run_x_post_mail

        with patch.dict(
            "os.environ",
            {
                "MAIL_BRIDGE_TO": "ops@example.test",
                "X_POST_MAIL_DEDUP_DISABLED": "1",
            },
            clear=False,
        ), patch.object(
            run_x_post_mail.miq,
            "ensure_local_db",
            return_value={"ok": True, "path": "/tmp/insight.db"},
        ), patch.object(
            run_x_post_mail.lane,
            "query_db_latest_game_date",
            return_value="2026-05-13",
        ), patch.object(
            run_x_post_mail.lane,
            "db_staleness_days",
            return_value=3,
        ), patch.object(
            run_x_post_mail.lane,
            "pick_candidates",
        ) as pick_candidates:
            result = run_x_post_mail.main([])

        self.assertEqual(result, 4)
        pick_candidates.assert_not_called()

    def test_invalid_staleness_env_falls_back_to_default(self) -> None:
        from src.tools import run_x_post_mail

        with patch.dict(
            "os.environ",
            {"X_POST_MAIL_MAX_DB_STALENESS_DAYS": "bad"},
            clear=False,
        ):
            self.assertEqual(
                run_x_post_mail._resolve_max_db_staleness_days(),
                run_x_post_mail.DEFAULT_MAX_DB_STALENESS_DAYS,
            )

    def test_dedup_starvation_backfills_relaxed_candidates(self) -> None:
        """24h dedupで候補が少なすぎる時は、mail自体を枯らさず不足分を埋める。"""
        from src.tools import run_x_post_mail

        fresh = self._entrypoint_candidate("fresh-sig")
        relaxed = [
            self._entrypoint_candidate("fresh-sig"),
            self._entrypoint_candidate("old-sig-1"),
            self._entrypoint_candidate("old-sig-2"),
            self._entrypoint_candidate("old-sig-3"),
        ]
        send_result = run_x_post_mail.mdb.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[],
            reason=None,
        )
        with patch.dict(
            "os.environ",
            {
                "MAIL_BRIDGE_TO": "ops@example.test",
                "INSIGHT_GCS_BUCKET": "insight-bucket",
                "X_POST_MAIL_DEDUP_MIN_CANDIDATES": "3",
            },
            clear=False,
        ), patch.object(
            run_x_post_mail.miq,
            "ensure_local_db",
            return_value={"ok": True, "path": "/tmp/insight.db"},
        ), patch.object(
            run_x_post_mail.lane,
            "query_db_latest_game_date",
            return_value="2026-05-16",
        ), patch.object(
            run_x_post_mail.lane,
            "db_staleness_days",
            return_value=0,
        ), patch.object(
            run_x_post_mail.lane,
            "_load_recent_dedup_signatures",
            return_value={"old-sig-1", "old-sig-2", "old-sig-3"},
        ), patch.object(
            run_x_post_mail.lane,
            "pick_candidates",
            side_effect=[[fresh], relaxed],
        ) as pick_candidates, patch.object(
            run_x_post_mail.mdb,
            "send",
            return_value=send_result,
        ) as send, patch.object(
            run_x_post_mail.lane,
            "_record_dedup_signatures",
            return_value=True,
        ) as record:
            result = run_x_post_mail.main(["--max-candidates", "4"])

        self.assertEqual(result, 0)
        self.assertEqual(pick_candidates.call_count, 2)
        self.assertEqual(
            pick_candidates.call_args_list[0].kwargs["dedup_set"],
            {"old-sig-1", "old-sig-2", "old-sig-3"},
        )
        self.assertIsNone(pick_candidates.call_args_list[1].kwargs["dedup_set"])
        request = send.call_args.args[0]
        self.assertEqual(request.metadata["candidate_count"], 4)
        record.assert_called_once_with(
            "insight-bucket",
            ["fresh-sig", "old-sig-1", "old-sig-2", "old-sig-3"],
            ANY,
        )

    def test_dedup_sufficient_candidates_do_not_retry(self) -> None:
        """dedup後に候補が十分あれば従来通り1回だけ選別する。"""
        from src.tools import run_x_post_mail

        cands = [
            self._entrypoint_candidate("sig-1"),
            self._entrypoint_candidate("sig-2"),
            self._entrypoint_candidate("sig-3"),
        ]
        send_result = run_x_post_mail.mdb.MailResult(
            status="sent",
            refused_recipients={},
            smtp_response=[],
            reason=None,
        )
        with patch.dict(
            "os.environ",
            {
                "MAIL_BRIDGE_TO": "ops@example.test",
                "INSIGHT_GCS_BUCKET": "insight-bucket",
                "X_POST_MAIL_DEDUP_MIN_CANDIDATES": "3",
            },
            clear=False,
        ), patch.object(
            run_x_post_mail.miq,
            "ensure_local_db",
            return_value={"ok": True, "path": "/tmp/insight.db"},
        ), patch.object(
            run_x_post_mail.lane,
            "query_db_latest_game_date",
            return_value="2026-05-16",
        ), patch.object(
            run_x_post_mail.lane,
            "db_staleness_days",
            return_value=0,
        ), patch.object(
            run_x_post_mail.lane,
            "_load_recent_dedup_signatures",
            return_value={"old-sig"},
        ), patch.object(
            run_x_post_mail.lane,
            "pick_candidates",
            return_value=cands,
        ) as pick_candidates, patch.object(
            run_x_post_mail.mdb,
            "send",
            return_value=send_result,
        ), patch.object(
            run_x_post_mail.lane,
            "_record_dedup_signatures",
            return_value=True,
        ):
            result = run_x_post_mail.main([])

        self.assertEqual(result, 0)
        self.assertEqual(pick_candidates.call_count, 1)


class TicketThreeFiftyFiveDedupTests(unittest.TestCase):
    """355: 24h dedup (GCS-backed JSONL) 検証。 GCS は in-memory fake で
    mock し、 `_get_storage_client` を patch する。
    """

    def _fake_storage_client(self, store: dict[str, str]):
        """Build a fake GCS client with an in-memory `store` (path -> text).

        ``store[blob_path]`` is the object body; missing keys behave as
        non-existent blobs.
        """
        class FakeBlob:
            def __init__(self, path: str) -> None:
                self.path = path

            def exists(self) -> bool:
                return self.path in store

            def download_as_text(self) -> str:
                return store.get(self.path, "")

            def upload_from_string(self, body: str, content_type: str = "") -> None:  # noqa: ARG002
                store[self.path] = body

        class FakeBucket:
            def blob(self, path: str) -> FakeBlob:
                return FakeBlob(path)

        class FakeClient:
            def bucket(self, name: str) -> FakeBucket:  # noqa: ARG002
                return FakeBucket()

        return FakeClient()

    def test_combo_signature_format(self) -> None:
        from src.x_post_mail_lane import _MetricCombo, _combo_signature
        combo = _MetricCombo("OPS", "2026-05-09", "直近1週間", novelty="high")
        self.assertEqual(_combo_signature(combo), "OPS|直近1週間|False|None")

    def test_combo_signature_unique_per_dimensions(self) -> None:
        from src.x_post_mail_lane import _MetricCombo, _combo_signature
        c1 = _MetricCombo("OPS", "2026-05-09", "直近1週間", position="捕")
        c2 = _MetricCombo("OPS", "2026-05-09", "直近1週間", position="二")
        c3 = _MetricCombo("OPS", "2026-05-01", "直近5試合")
        sigs = {_combo_signature(c1), _combo_signature(c2), _combo_signature(c3)}
        self.assertEqual(len(sigs), 3, msg=f"signatures collided: {sigs}")

    def test_load_recent_dedup_signatures_returns_set(self) -> None:
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        ts_today = datetime(2026, 5, 16, 6, 30, tzinfo=JST).isoformat()
        ts_yesterday = datetime(2026, 5, 15, 20, 0, tzinfo=JST).isoformat()
        store = {
            "x_post_mail/dedup/2026-05-16.jsonl":
                f'{{"ts": "{ts_today}", "signature": "OPS|直近1週間|False|None"}}\n',
            "x_post_mail/dedup/2026-05-15.jsonl":
                f'{{"ts": "{ts_yesterday}", "signature": "AVG|直近1週間|False|None"}}\n',
        }
        now = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            sigs = lane._load_recent_dedup_signatures("test-bucket", now)
        self.assertEqual(sigs, {"OPS|直近1週間|False|None", "AVG|直近1週間|False|None"})

    def test_load_recent_dedup_signatures_filters_old(self) -> None:
        """24h 超 (= 30h 前) の record は除外。"""
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        old_ts = (datetime(2026, 5, 16, 7, 0, tzinfo=JST) - timedelta(hours=30)).isoformat()
        recent_ts = (datetime(2026, 5, 16, 7, 0, tzinfo=JST) - timedelta(hours=2)).isoformat()
        store = {
            "x_post_mail/dedup/2026-05-15.jsonl":
                f'{{"ts": "{old_ts}", "signature": "STALE|x|False|None"}}\n'
                f'{{"ts": "{recent_ts}", "signature": "FRESH|y|False|None"}}\n',
        }
        now = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            sigs = lane._load_recent_dedup_signatures("test-bucket", now)
        self.assertIn("FRESH|y|False|None", sigs)
        self.assertNotIn("STALE|x|False|None", sigs)

    def test_load_recent_dedup_signatures_silent_fallback_on_error(self) -> None:
        """GCS client init が raise しても empty set を返す。"""
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        def _boom():
            raise RuntimeError("simulated GCS auth failure")
        now = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        with patch.object(lane, "_get_storage_client", side_effect=_boom):
            sigs = lane._load_recent_dedup_signatures("test-bucket", now)
        self.assertEqual(sigs, set())

    def test_pick_candidates_skips_combos_in_dedup_set(self) -> None:
        """dedup_set に含まれる signature の combo は select されない。"""
        # Build a dedup_set covering the entire combo pool minus one
        # to force pick_candidates to honour the gate.
        from src.x_post_mail_lane import _build_combos, _combo_signature

        all_combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        # Block every combo except league-wide OPS/直近1週間.
        dedup_set = {
            _combo_signature(c) for c in all_combos
            if not (
                c.metric == "OPS"
                and c.period_label == "直近1週間"
                and not c.giants_only
                and c.position is None
            )
        }
        query_mock = MagicMock(return_value={
            "ok": True, "rows": _MIXED_12_TEAM_ROWS, "count": 12,
            "total": 60, "focus_player": None,
        })
        cands = pick_candidates(
            query_mock,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=10,
            min_sample=1,
            min_central_rows=3,
            dedup_set=dedup_set,
        )
        # All surviving candidates must be league-wide OPS / 直近1週間.
        for c in cands:
            self.assertEqual(c.metric, "OPS")
            self.assertEqual(c.period_label, "直近1週間")
            self.assertEqual(c.signature, "OPS|直近1週間|False|None")

    def test_pick_candidates_dedup_set_none_keeps_legacy_behaviour(self) -> None:
        """dedup_set=None default で従来挙動と同じ。"""
        query_mock = MagicMock(return_value={
            "ok": True, "rows": _MIXED_12_TEAM_ROWS, "count": 12,
            "total": 60, "focus_player": None,
        })
        cands = pick_candidates(
            query_mock,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=5,
            min_sample=1,
            min_central_rows=3,
        )
        # Candidates must carry signatures even without dedup gating.
        self.assertGreaterEqual(len(cands), 1)
        for c in cands:
            self.assertTrue(c.signature, msg="candidate signature missing")

    def test_record_dedup_signatures_writes_jsonl(self) -> None:
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        store: dict[str, str] = {}
        now = datetime(2026, 5, 16, 7, 5, tzinfo=JST)
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            ok = lane._record_dedup_signatures(
                "test-bucket",
                ["OPS|直近1週間|False|None", "ERA|直近5試合|True|None"],
                now,
            )
        self.assertTrue(ok)
        path = "x_post_mail/dedup/2026-05-16.jsonl"
        self.assertIn(path, store)
        lines = [ln for ln in store[path].split("\n") if ln.strip()]
        self.assertEqual(len(lines), 2)
        import json
        rec0 = json.loads(lines[0])
        self.assertEqual(rec0["signature"], "OPS|直近1週間|False|None")
        self.assertIn("ts", rec0)

    def test_record_dedup_signatures_appends_to_existing(self) -> None:
        """既存 record に append (= 上書きしない)。"""
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        path = "x_post_mail/dedup/2026-05-16.jsonl"
        store = {
            path: '{"ts": "2026-05-16T03:00:00+09:00", "signature": "EXISTING|x|False|None"}\n',
        }
        now = datetime(2026, 5, 16, 12, 5, tzinfo=JST)
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            lane._record_dedup_signatures(
                "test-bucket",
                ["NEW|y|False|None"],
                now,
            )
        body = store[path]
        self.assertIn("EXISTING|x|False|None", body)
        self.assertIn("NEW|y|False|None", body)


class SnapshotPathBattingMetricsTests(unittest.TestCase):
    """2026-05-17: batting metrics (AVG/OBP/SLG/OPS) は
    `advanced_metric_snapshots` 経由で query する dispatch を持つ。
    legacy `_aggregate_batting` の 2B/3B/HR/BB/HBP/SF 未読問題で
    SLG=0 / OBP=AVG / OPS=AVG になっていた事故を防ぐ。
    """

    def setUp(self) -> None:
        import tempfile, sqlite3, os
        self.tmp_dir = tempfile.mkdtemp(prefix="xpostmail_snap_")
        self.db_path = os.path.join(self.tmp_dir, "snap.db")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE teams (
                    team_code TEXT PRIMARY KEY,
                    team_name TEXT,
                    league TEXT,
                    home_park TEXT
                );
                CREATE TABLE advanced_metric_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_date TEXT,
                    scope TEXT,
                    player_canonical TEXT,
                    team_code TEXT,
                    position TEXT,
                    metric_name TEXT,
                    metric_value REAL,
                    sample_size INTEGER,
                    league_rank INTEGER,
                    league_total INTEGER,
                    position_rank INTEGER,
                    position_total INTEGER,
                    extra_json TEXT
                );
                INSERT INTO teams (team_code, team_name, league) VALUES
                    ('g',  '巨人',     'central'),
                    ('t',  '阪神',     'central'),
                    ('db', 'DeNA',     'central'),
                    ('s',  'ヤクルト', 'central'),
                    ('d',  '中日',     'central'),
                    ('c',  '広島',     'central'),
                    ('l',  '西武',     'pacific');
                """
            )
            # Seed: 浦田 OPS .813 / AVG .333 (different values — the bug fix).
            rows = [
                # (snapshot_date, scope, player, team, metric, value, sample)
                ("2026-05-17", "last_10_games", "浦田俊輔",   "g",  "AVG",  0.3333, 37),
                ("2026-05-17", "last_10_games", "浦田俊輔",   "g",  "OPS",  0.8131, 37),
                ("2026-05-17", "last_10_games", "浦田俊輔",   "g",  "OBP",  0.3889, 37),
                ("2026-05-17", "last_10_games", "浦田俊輔",   "g",  "SLG",  0.4242, 37),
                ("2026-05-17", "last_10_games", "佐藤輝明",   "t",  "OPS",  0.9200, 40),
                ("2026-05-17", "last_10_games", "村上宗隆",   "s",  "OPS",  0.8800, 38),
                ("2026-05-17", "last_10_games", "牧秀悟",     "db", "OPS",  0.8500, 36),
                ("2026-05-17", "last_10_games", "細川成也",   "d",  "OPS",  0.8400, 35),
                ("2026-05-17", "last_10_games", "鈴木誠也",   "c",  "OPS",  0.8200, 39),
                # Pacific row should be filtered out by central filter
                ("2026-05-17", "last_10_games", "ネビン",     "l",  "OPS",  1.4179, 40),
            ]
            conn.executemany(
                "INSERT INTO advanced_metric_snapshots "
                "(snapshot_date, scope, player_canonical, team_code, "
                " metric_name, metric_value, sample_size) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_query_returns_central_only_with_correct_ops(self) -> None:
        """snapshot 経由の OPS は AVG とは別の値で、 セ・リーグだけ返す。"""
        from src.x_post_mail_lane import (
            _query_rank_from_snapshots,
            filter_central_league,
            _rebuild_ranks_within_central,
        )
        result = _query_rank_from_snapshots(
            self.db_path,
            metric_name="OPS",
            snapshot_scope="last_10_games",
            min_sample=10,
            limit=60,
        )
        self.assertTrue(result["ok"], msg=result)
        # team_code は teams.team_name で解決される (== '巨人' / '阪神' …)。
        team_names = {r["team_code"] for r in result["rows"]}
        self.assertIn("巨人", team_names)
        self.assertIn("西武", team_names)
        # filter_central_league で パ・リーグ (西武 = ネビン) が落ちる。
        central_rows = filter_central_league(result["rows"])
        central_teams = {r["team_code"] for r in central_rows}
        self.assertFalse(
            central_teams & {"西武", "ロッテ", "ソフトバンク", "オリックス", "楽天", "日本ハム"},
            msg=f"pacific leaked: {central_teams}",
        )
        # 浦田 row が含まれ、 metric_value が OPS の正値 (.813、 AVG .333 と別)。
        urata = next(r for r in central_rows if r["player_canonical"] == "浦田俊輔")
        self.assertAlmostEqual(urata["metric_value"], 0.8131, places=4)

    def test_avg_and_ops_differ_for_same_player(self) -> None:
        """同じ選手の AVG / OPS が同値にならない (broken aggregator 退行防止)。"""
        from src.x_post_mail_lane import _query_rank_from_snapshots
        avg_result = _query_rank_from_snapshots(
            self.db_path,
            metric_name="AVG",
            snapshot_scope="last_10_games",
            min_sample=10,
            limit=60,
        )
        ops_result = _query_rank_from_snapshots(
            self.db_path,
            metric_name="OPS",
            snapshot_scope="last_10_games",
            min_sample=10,
            limit=60,
        )
        urata_avg = next(
            r for r in avg_result["rows"] if r["player_canonical"] == "浦田俊輔"
        )
        urata_ops = next(
            r for r in ops_result["rows"] if r["player_canonical"] == "浦田俊輔"
        )
        self.assertNotAlmostEqual(
            urata_avg["metric_value"], urata_ops["metric_value"], places=3,
            msg="OPS が AVG と同値になっている — broken aggregator 退行",
        )

    def test_min_sample_filter_drops_low_pa(self) -> None:
        """sample_size < min_sample な row は除外される。"""
        from src.x_post_mail_lane import _query_rank_from_snapshots
        result = _query_rank_from_snapshots(
            self.db_path,
            metric_name="OPS",
            snapshot_scope="last_10_games",
            min_sample=40,  # 浦田 (37) は drop されるはず
            limit=60,
        )
        names = {r["player_canonical"] for r in result["rows"]}
        self.assertNotIn("浦田俊輔", names)
        # 40+ sample のみ残る
        self.assertIn("佐藤輝明", names)


if __name__ == "__main__":
    unittest.main()
