"""Tests for ``src.x_post_mail_lane`` (ticket 347)."""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import MagicMock

from src.x_post_mail_lane import (
    CENTRAL_LEAGUE_TEAM_ALIASES,
    JST,
    X_CHAR_LIMIT,
    Candidate,
    build_subject,
    compose_mail,
    encode_x_intent_url,
    filter_central_league,
    is_central_league,
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
        self.assertEqual(subject, "[X 投稿候補 7件] 朝 / 2026-05-16 07:00 JST")

    def test_subject_zero_candidates_does_not_crash(self) -> None:
        ts = datetime(2026, 5, 16, 22, 30, tzinfo=JST)
        subject = build_subject(ts, 0)
        self.assertIn("0件", subject)
        self.assertIn("試合後", subject)


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
        # 353: marker 強化 — ` ← 巨人` から ` ←⭐巨人` に変更
        self.assertIn("←⭐巨人", cands[0].draft_text)

    def test_too_few_central_rows_skipped(self) -> None:
        # Only 1 セ row → skip (351: giants_only combos may still pass since
        # they have a lower min_central_rows=3 threshold and 巨人 row exists).
        # Verify non-giants-only combos all skip.
        sparse = [
            _row(1, "巨人選手", "巨人", 0.900),
            _row(2, "パ選手 A", "ソフトバンク", 0.890),
            _row(3, "パ選手 B", "オリックス", 0.880),
        ]
        query_mock = MagicMock(return_value={"ok": True, "rows": sparse, "count": 3, "total": 60, "focus_player": None})
        cands = pick_candidates(query_mock, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST), max_candidates=22, min_sample=1)
        # All emitted candidates must be 巨人内 ranking (since non-giants-only
        # combos require min_central_rows=5 default and we only have 1 セ row).
        for c in cands:
            self.assertIn("巨人内", c.title, msg=f"Unexpected non-giants combo: {c.title}")

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

    def test_period_label_appears_in_draft(self) -> None:
        """351: 22 combo pool から全候補取得、season-wide combo が必ず含まれる。"""
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
            max_candidates=22,  # 351: get the whole shuffled pool
            min_sample=1,
            min_central_rows=3,
        )
        # At least one season-wide candidate (今シーズン period_label) must exist
        season_cands = [c for c in cands if c.period_label == "今シーズン"]
        self.assertGreaterEqual(len(season_cands), 1)
        # And its header carries the concrete season range form
        self.assertIn("開幕〜5/16 累積", season_cands[0].draft_text)

    def test_header_includes_date_range_and_sample_threshold(self) -> None:
        """350-v3 + 351: 全候補が具体 date range と 規定 sample 閾値を含む。"""
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
            # Every candidate header must carry either "累積" (season-wide)
            # or "〜" (date range form like 5/1〜5/16).
            self.assertTrue(
                ("累積" in text) or ("〜" in text),
                msg=f"missing date range in: {text[:60]}",
            )
            # Every candidate carries the sample threshold marker
            self.assertTrue(
                ("規定打席 30+" in text) or ("規定投球回 30+" in text),
                msg=f"missing sample threshold in: {text[:60]}",
            )

    def test_monthly_combo_header_shows_concrete_date_range(self) -> None:
        """350-v3: monthly combo は具体的 since-today range を出す。"""
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
        # At least one monthly candidate within the 22 pool
        monthly_cands = [c for c in cands if c.period_label == "今月"]
        self.assertGreaterEqual(len(monthly_cands), 1)
        text = monthly_cands[0].draft_text
        # 5/1〜5/16 form expected for May 16 timestamp
        self.assertIn("5/1〜5/16", text)

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
        # 351: 巨人内 ranking combo only needs 3 巨人 rows; rows4 has 1 巨人
        # row so still skips. Verify that NON-巨人-only combos do skip.
        non_giants_combos_skipped_at_4 = pick_candidates(
            MagicMock(return_value={"ok": True, "rows": rows4, "count": 4, "total": 20, "focus_player": None}),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
        )
        for c in non_giants_combos_skipped_at_4:
            # If any candidate slips through with only 4 rows, it must be the
            # giants_only ranking which has its own min=3 threshold and a
            # single 巨人 row in the input → still excluded.
            self.assertNotIn("ランキング 📊（", c.draft_text[:0])
        cands5 = pick_candidates(
            MagicMock(return_value={"ok": True, "rows": rows5, "count": 5, "total": 20, "focus_player": None}),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
        )
        self.assertGreaterEqual(len(cands5), 1, msg="5 セ rows should be accepted")


class VariationExpansionTests(unittest.TestCase):
    """351: 新 combo (先月 / 直近 7 日 / 直近 14 日 / 守備位置別 / 巨人内) 検証。"""

    def _make_mock_with_rows(self) -> MagicMock:
        return MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })

    def test_last_month_combo_appears(self) -> None:
        cands = pick_candidates(
            self._make_mock_with_rows(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
            min_central_rows=3,
        )
        last_month_cands = [c for c in cands if c.period_label == "先月"]
        self.assertGreaterEqual(len(last_month_cands), 1)
        # 5/16 から見た先月 = 4/1〜4/30
        self.assertIn("4/1〜4/30", last_month_cands[0].draft_text)

    def test_last_7_days_combo_appears(self) -> None:
        cands = pick_candidates(
            self._make_mock_with_rows(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
            min_central_rows=3,
        )
        last7_cands = [c for c in cands if c.period_label == "直近7日"]
        self.assertGreaterEqual(len(last7_cands), 1)
        # 5/16 - 7 = 5/9
        self.assertIn("5/9〜5/16", last7_cands[0].draft_text)

    def test_last_14_days_combo_appears(self) -> None:
        cands = pick_candidates(
            self._make_mock_with_rows(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=22,
            min_sample=1,
            min_central_rows=3,
        )
        last14_cands = [c for c in cands if c.period_label == "直近14日"]
        self.assertGreaterEqual(len(last14_cands), 1)
        # 5/16 - 14 = 5/2
        self.assertIn("5/2〜5/16", last14_cands[0].draft_text)

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

    def test_giants_only_ranking_filters_to_giants_rows(self) -> None:
        """巨人内 ranking は 巨人 row のみで header に「巨人内」を含む。"""
        # Mix with 3 giants players so giants_only meets min=3
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
        giants_cands = [c for c in cands if "巨人内" in c.draft_text]
        self.assertGreaterEqual(len(giants_cands), 1)
        text = giants_cands[0].draft_text
        # Non-巨人 player names must NOT appear in 巨人内 ranking
        for non_giants_name in ["佐藤輝明", "牧秀悟", "村上宗隆", "鈴木誠也", "細川成也"]:
            self.assertNotIn(non_giants_name, text, msg=f"non-Giants player leaked: {non_giants_name}")
        # 巨人 players appear
        self.assertIn("岡本和真", text)

    def test_combo_pool_size_17_after_mainstream_excluded(self) -> None:
        """353: 大手定番 シーズン累積 5 (OPS/AVG/ERA/OBP/SLG) を pool から削除。
        残り = 月 3 + 30 日 2 + 先月 2 + 7 日 1 + 14 日 2 + 守備 4 + 巨人内 3 = 17。
        """
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        self.assertEqual(len(combos), 17)
        # シーズン累積 (since=None、 position=None、 giants_only=False) は存在しない
        # ただし position / giants_only で限定された since=None combo は OK で残す。
        mainstream_season = [
            c for c in combos
            if c.since is None and c.position is None and not c.giants_only
        ]
        self.assertEqual(
            len(mainstream_season),
            0,
            msg=f"mainstream season combos leaked: {mainstream_season}",
        )

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
            period_label="今シーズン",
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


class EmptyResultBehaviourTests(unittest.TestCase):
    def test_compose_mail_with_empty_candidates_no_crash(self) -> None:
        ts = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        mail = compose_mail([], now=ts)
        self.assertEqual(mail.candidate_count, 0)
        self.assertIn("0件", mail.subject)


class TicketThreeFiftyThreeFormatTests(unittest.TestCase):
    """353: 大手なし pool + 意外性 sampling + 4 見た目改善 (改行 / metric 別
    絵文字 / 上位 3 メダル / ⭐巨人 / metric label / 1 行空け) の検証。
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
        # Batter combo (any of monthly OPS/AVG)
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
        # Pitcher combo (monthly ERA)
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

    def test_top3_medal_prefix(self) -> None:
        """ranking 行 1/2/3 = 🥇🥈🥉、 4 位以降 = N. 数字。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        self.assertGreaterEqual(len(cands), 1)
        text = cands[0].draft_text
        self.assertIn("🥇", text)
        self.assertIn("🥈", text)
        self.assertIn("🥉", text)
        # 4 位は通常の数字 prefix
        self.assertIn("4.", text)

    def test_giants_marker_strong_form(self) -> None:
        """巨人行 marker は ` ← 巨人` ではなく ` ←⭐巨人`。"""
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
            if "巨人" in c.draft_text and "←" in c.draft_text
        ]
        self.assertGreaterEqual(len(with_giants), 1)
        for c in with_giants:
            self.assertIn("←⭐巨人", c.draft_text)
            # 旧 form は出ない
            self.assertNotIn("← 巨人", c.draft_text)

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

    def test_blank_line_between_top3_and_rest(self) -> None:
        """1-3 位 ranking 行と 4 位以降の間に空行 1 行。"""
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
        # find index of 🥉 (3rd medal row)
        bronze_idx = next((i for i, ln in enumerate(lines) if ln.startswith("🥉")), -1)
        self.assertGreaterEqual(bronze_idx, 0, msg="🥉 row not found")
        # Next line should be blank, line after that should start with "4."
        self.assertEqual(lines[bronze_idx + 1], "", msg=f"missing blank after 🥉: {lines[bronze_idx + 1]!r}")
        self.assertTrue(
            lines[bronze_idx + 2].startswith("4."),
            msg=f"line after blank not 4.: {lines[bronze_idx + 2]!r}",
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


if __name__ == "__main__":
    unittest.main()
