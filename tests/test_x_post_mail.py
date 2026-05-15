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
        self.assertIn("← 巨人", cands[0].draft_text)

    def test_too_few_central_rows_skipped(self) -> None:
        # Only 1 セ row → skip (min_central_rows=3 default)
        sparse = [
            _row(1, "巨人選手", "巨人", 0.900),
            _row(2, "パ選手 A", "ソフトバンク", 0.890),
            _row(3, "パ選手 B", "オリックス", 0.880),
        ]
        query_mock = MagicMock(return_value={"ok": True, "rows": sparse, "count": 3, "total": 60, "focus_player": None})
        cands = pick_candidates(query_mock, now=datetime(2026, 5, 16, 7, 0, tzinfo=JST), max_candidates=10, min_sample=1)
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

    def test_period_label_appears_in_draft(self) -> None:
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
            max_candidates=1,
            min_sample=1,
            min_central_rows=3,
        )
        self.assertEqual(len(cands), 1)
        # 350-v3: header now contains explicit date range, no longer "今シーズン"
        # The combo is season-wide → header should say "開幕〜5/16 累積"
        self.assertIn("開幕〜5/16 累積", cands[0].draft_text)
        # period_label on the Candidate dataclass still carries the original combo label
        self.assertEqual(cands[0].period_label, "今シーズン")

    def test_header_includes_date_range_and_sample_threshold(self) -> None:
        """350-v3: header に具体的 date range と 規定打席 N+ が含まれる。"""
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
            max_candidates=1,
            min_sample=30,
            min_central_rows=3,
        )
        self.assertEqual(len(cands), 1)
        text = cands[0].draft_text
        # First combo = season-wide → "開幕〜5/16 累積"
        self.assertIn("開幕〜5/16 累積", text)
        # OPS is batting → 規定打席
        self.assertIn("規定打席 30+", text)

    def test_monthly_combo_header_shows_concrete_date_range(self) -> None:
        """350-v3: monthly combo は具体的 since-today range を出す。"""
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": _MIXED_12_TEAM_ROWS,
            "count": 12,
            "total": 60,
            "focus_player": None,
        })
        # First 5 combos are season-wide; combo #6 is monthly OPS.
        cands = pick_candidates(
            query_mock,
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=10,
            min_sample=1,
            min_central_rows=3,
        )
        # At least one monthly candidate
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
            max_candidates=10,
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
        cands4 = pick_candidates(
            MagicMock(return_value={"ok": True, "rows": rows4, "count": 4, "total": 20, "focus_player": None}),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=10,
            min_sample=1,
        )
        cands5 = pick_candidates(
            MagicMock(return_value={"ok": True, "rows": rows5, "count": 5, "total": 20, "focus_player": None}),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=10,
            min_sample=1,
        )
        self.assertEqual(cands4, [], msg="4 セ rows should be skipped under default min_central_rows=5")
        self.assertGreaterEqual(len(cands5), 1, msg="5 セ rows should be accepted")


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


if __name__ == "__main__":
    unittest.main()
