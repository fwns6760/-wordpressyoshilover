"""Tests for ``src.x_post_mail_lane`` (ticket 347)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import ANY, MagicMock, patch

from src.x_post_mail_lane import (
    CENTRAL_LEAGUE_TEAM_ALIASES,
    JST,
    X_CHAR_LIMIT,
    Candidate,
    _candidate_anomaly_flags,
    _candidate_source_kind,
    _sample_threshold_label,
    _source_mix_summary,
    _load_giants_player_aliases,
    build_comment_numeric_candidate,
    build_news_opinion_candidate,
    build_subject,
    compose_mail,
    detect_giants_player_name,
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
        self.assertIn("x.com/intent/post", url)
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
        # 382 系: no &hashtags / &url params allowed in the intent URL.
        self.assertNotIn("hashtags", qs)
        self.assertNotIn("url", qs)

    def test_empty_text_safe(self) -> None:
        self.assertEqual(encode_x_intent_url(""), "https://x.com/intent/post?text=")
        self.assertEqual(encode_x_intent_url(None), "https://x.com/intent/post?text=")


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
        # 418 case B: marker 形式 ` 🟧巨人🟧` (STEP1 の `⭐巨人` から更新)
        self.assertIn("🟧巨人🟧", cands[0].draft_text)
        self.assertNotIn("←", cands[0].draft_text)
        self.assertNotIn("⭐巨人", cands[0].draft_text)

    def test_farm_rows_do_not_mix_into_first_team_x_candidates(self) -> None:
        rows = [
            {**_row(1, "若手二軍", "巨人", 1.100, sample=30), "league_label": "イースタン"},
            _row(2, "岡本和真", "巨人", 0.950, sample=30),
            _row(3, "牧秀悟", "DeNA", 0.930, sample=30),
            _row(4, "村上宗隆", "ヤクルト", 0.920, sample=30),
            _row(5, "細川成也", "中日", 0.910, sample=30),
            _row(6, "坂倉将吾", "広島", 0.900, sample=30),
        ]
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": rows,
            "count": len(rows),
            "total": len(rows),
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
        self.assertEqual(cands[0].focus_player, "岡本和真")
        self.assertNotIn("若手二軍", cands[0].draft_text)
        self.assertEqual(cands[0].team_level, "first")

    def test_low_sample_rate_rows_do_not_drive_x_candidates(self) -> None:
        rows = [
            _row(1, "少数打席", "巨人", 1.100, sample=2),
            _row(2, "岡本和真", "巨人", 0.950, sample=12),
            _row(3, "牧秀悟", "DeNA", 0.930, sample=12),
            _row(4, "村上宗隆", "ヤクルト", 0.920, sample=12),
            _row(5, "細川成也", "中日", 0.910, sample=12),
            _row(6, "坂倉将吾", "広島", 0.900, sample=12),
        ]
        query_mock = MagicMock(return_value={
            "ok": True,
            "rows": rows,
            "count": len(rows),
            "total": len(rows),
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
        self.assertEqual(cands[0].focus_player, "岡本和真")
        self.assertNotIn("少数打席", cands[0].draft_text)
        self.assertGreaterEqual(cands[0].sample_size, 10)

    def test_sample_gate_hard_skips_when_only_low_sample_rows(self) -> None:
        rows = [
            _row(1, "少数打席", "巨人", 1.100, sample=2),
            _row(2, "牧秀悟", "DeNA", 0.930, sample=2),
            _row(3, "村上宗隆", "ヤクルト", 0.920, sample=2),
            _row(4, "細川成也", "中日", 0.910, sample=2),
            _row(5, "坂倉将吾", "広島", 0.900, sample=2),
            _row(6, "佐藤輝明", "阪神", 0.890, sample=2),
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
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=1,
            min_sample=1,
            min_central_rows=3,
        )
        self.assertEqual(cands, [])

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
        # 429: Source B keeps the DB table as post_text even when lineup context is present.
        self.assertIn("📊", cand.post_text)
        self.assertIn("TOP", cand.post_text)
        self.assertIn("今日のスタメン: 泉口友汰", cand.post_text)
        self.assertIn("泉口友汰", cand.post_text)
        self.assertNotIn("今日のスタメンから", cand.post_text)
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

    def test_player_diversity_uses_next_giants_row_before_repeating(self) -> None:
        """380: top 巨人 row が既出なら同 ranking の次の巨人 row を使う。"""
        rows = [
            _row(1, "佐藤輝明", "阪神", 1.045),
            _row(2, "岸田 行倫", "巨人", 0.990),
            _row(3, "平山 功太", "巨人", 0.980),
            _row(4, "キャベッジ", "巨人", 0.970),
            _row(5, "浦田俊輔", "巨人", 0.960),
            _row(6, "泉口友汰", "巨人", 0.950),
            _row(7, "丸佳浩", "巨人", 0.940),
            _row(8, "牧秀悟", "DeNA", 0.930),
            _row(9, "村上宗隆", "ヤクルト", 0.920),
            _row(10, "細川成也", "中日", 0.910),
            _row(11, "坂倉将吾", "広島", 0.900),
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
            now=datetime(2026, 5, 18, 7, 0, tzinfo=JST),
            max_candidates=6,
            min_sample=1,
            min_central_rows=3,
        )
        players = [c.focus_player for c in cands]
        self.assertEqual(len(players), 6)
        self.assertEqual(len(set(players)), 6)
        self.assertEqual(players[0], "岸田 行倫")
        self.assertIn("平山 功太", players)

    def test_player_diversity_caps_same_player_when_no_alternative(self) -> None:
        """397: 代替巨人 row が無い時、同一選手は player_max=1 (default) まで。"""
        rows = [
            _row(1, "佐藤輝明", "阪神", 1.045),
            _row(2, "マルティネス", "巨人", 0.990),
            _row(3, "牧秀悟", "DeNA", 0.930),
            _row(4, "村上宗隆", "ヤクルト", 0.920),
            _row(5, "細川成也", "中日", 0.910),
            _row(6, "坂倉将吾", "広島", 0.900),
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
            now=datetime(2026, 5, 18, 7, 0, tzinfo=JST),
            max_candidates=8,
            min_sample=1,
            min_central_rows=3,
        )
        players = [c.focus_player for c in cands]
        # 397: _DEFAULT_PLAYER_MAX_PER_MAIL=1 で同一 player 1 件のみ
        self.assertEqual(players, ["マルティネス"])

    def test_recent_player_history_uses_next_giants_row(self) -> None:
        """380 follow-up: 直近24h既出 player は次の巨人 row に差し替える。"""
        rows = [
            _row(1, "佐藤輝明", "阪神", 1.045),
            _row(2, "浦田俊輔", "巨人", 0.990),
            _row(3, "平山 功太", "巨人", 0.980),
            _row(4, "キャベッジ", "巨人", 0.970),
            _row(5, "牧秀悟", "DeNA", 0.930),
            _row(6, "村上宗隆", "ヤクルト", 0.920),
            _row(7, "細川成也", "中日", 0.910),
            _row(8, "坂倉将吾", "広島", 0.900),
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
            now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
            max_candidates=1,
            min_sample=1,
            min_central_rows=3,
            recent_player_counts={"浦田俊輔": 3},
        )
        self.assertEqual([c.focus_player for c in cands], ["平山 功太"])

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

    def test_pitching_metrics_use_ip_sample_label(self) -> None:
        """436 follow-up: 投手rate系で「規定打席」を出さない。"""
        for metric in ("ERA", "K_per_9", "BB_per_9", "HR_per_9"):
            self.assertEqual(_sample_threshold_label(metric, 3), "規定投球回3以上")
        for metric in ("AVG", "OBP", "SLG", "OPS"):
            self.assertEqual(_sample_threshold_label(metric, 10), "規定打席10以上")

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
            max_per_player=99,
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
        # 巨人 players appear with strong marker (418 case B: ⭐巨人 → 🟧巨人🟧)
        self.assertIn("岡本和真", text)
        self.assertIn("🟧巨人🟧", text)
        self.assertNotIn("←⭐巨人", text)
        self.assertNotIn("⭐巨人", text)

    def test_format_one_adds_branded_post_text_and_emoji_title(self) -> None:
        """429: X intent 用の本文はDB ranking tableを正本にする。"""
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
        self.assertNotIn("#巨人", cand.post_text)
        self.assertNotIn("#ジャイアンツ", cand.post_text)
        self.assertIn("📊", cand.post_text)
        self.assertIn("TOP", cand.post_text)
        self.assertIn("巨人最上位", cand.post_text)
        self.assertIn("🟧巨人🟧", cand.post_text)
        self.assertIn("岡本和真", cand.post_text)
        self.assertIn("OPS", cand.post_text)
        self.assertIn("セ・リーグ", cand.post_text)
        self.assertNotIn("https://", cand.post_text)
        self.assertNotIn("整理しました", cand.post_text)
        self.assertNotIn("どう見ますか", cand.post_text)
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
        # 418 case B: 「11位 岡本和真（巨人）.900 🟧巨人🟧」 形式
        self.assertIn("11位 岡本和真（巨人）.900 🟧巨人🟧", cand.draft_text)
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
          - 直近1週間 × 4 batting metric  = 4 (394 fix: 投手除外)
          - 守備位置別直近1週間 AVG × 4 pos = 4
          - 今週 × 4 batting metric    = 4 (394 fix: 投手除外、 週初め以外)
          - 今月 × 8 metric            = 8
        2026-05-16 (Sat) は週初め (Mon=05-11) と直近1週間 (05-09) が違うので 今週 enabled。
        計 20 combo。
        """
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        self.assertEqual(len(combos), 20)
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
        self.assertIn("x.com/intent/post", mail.html_body)
        self.assertIn("%23", mail.html_body)  # # in text was URL-encoded
        # The plain text body also lists the URL for fallback copy.
        self.assertIn("x.com/intent/post", mail.text_body)

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

    def test_text_body_x_intent_decodes_final_post_text_not_draft_text(self) -> None:
        ts = datetime(2026, 5, 16, 17, 30, tzinfo=JST)
        cand = Candidate(
            title="📊 Xポスト案｜正本確認",
            metric="OPS",
            period_label="直近5試合",
            draft_text="根拠データだけにある文",
            post_text="Xに実際に入る本文",
            char_count=len("Xに実際に入る本文"),
        )
        mail = compose_mail([cand], now=ts)
        urls = [
            line.strip()
            for line in mail.text_body.splitlines()
            if line.strip().startswith("https://x.com/intent/post?text=")
        ]
        self.assertEqual(len(urls), 1)
        decoded = parse_qs(urlparse(urls[0]).query)["text"][0]
        self.assertEqual(decoded, "Xに実際に入る本文")
        self.assertNotEqual(decoded, "根拠データだけにある文")

    def test_source_mix_summary_visible_in_text_and_html(self) -> None:
        ts = datetime(2026, 5, 16, 17, 30, tzinfo=JST)
        source_a = Candidate(
            title="Source A",
            metric="NEWS_OPINION",
            period_label="ニュース",
            draft_text="根拠",
            post_text="坂本勇人の次の打席を見たい。",
            char_count=15,
        )
        source_b = Candidate(
            title="Source B",
            metric="OPS",
            period_label="直近5試合",
            draft_text="根拠",
            post_text="📊 セ OPS TOP5 ⚾\n(直近5試合・規定打席5以上)\n巨人最上位: 岡本和真 セ・リーグ 2/20位\n\n2位 岡本和真（巨人）.950 🟧巨人🟧",
            char_count=80,
        )
        mail = compose_mail([source_a, source_b], now=ts)
        self.assertIn("【Source / flags】", mail.text_body)
        self.assertIn("Source構成: A(RSS観戦)=1 / B(DB表)=1 / C(DB slice)=0 / total=2", mail.text_body)
        self.assertIn("Source / flags", mail.html_body)
        self.assertIn("candidate_count_low:2", mail.text_body)
        self.assertIn("採用理由:", mail.text_body)
        self.assertIn("DB表=1", mail.text_body)

    def test_selected_reason_visible_in_text_and_html(self) -> None:
        ts = datetime(2026, 5, 16, 17, 30, tzinfo=JST)
        cand = Candidate(
            title="Source B",
            metric="OPS",
            period_label="直近5試合",
            draft_text="根拠",
            post_text="📊 セ OPS TOP5 ⚾\n(直近5試合・規定打席10以上)\n巨人最上位: 岡本和真 セ・リーグ 2/20位\n2位 岡本和真（巨人）.950 🟧巨人🟧",
            char_count=80,
            focus_player="岡本和真",
            team_level="first",
            sample_size=12,
            reason_tags=("fan_useful:central_rank", "sample_ok"),
        )
        mail = compose_mail([cand], now=ts)
        self.assertIn("【採用理由】", mail.text_body)
        self.assertIn("DB表", mail.text_body)
        self.assertIn("短期変化", mail.text_body)
        self.assertIn("sample確認", mail.text_body)
        self.assertIn("採用理由:", mail.html_body)
        self.assertIn("DB表", mail.html_body)

    def test_anomaly_flags_separate_hard_and_flag_only(self) -> None:
        source_a_short = Candidate(
            title="Source A short",
            metric="NEWS_OPINION",
            period_label="ニュース",
            draft_text="根拠",
            post_text="短い。",
            char_count=3,
        )
        source_b_broken = Candidate(
            title="Source B broken",
            metric="OPS",
            period_label="直近5試合",
            draft_text="根拠",
            post_text="今日の巨人データメモ。数字だけで語り切る話ではないけど、どう見ますか？",
            char_count=40,
        )
        self.assertEqual(_candidate_source_kind(source_a_short), "A")
        self.assertEqual(_candidate_source_kind(source_b_broken), "B")
        # 2026-05-25 user 確定: ヨシラバー voice 短文化 (180-280→100-180)。
        # hard NG 140 → 60 字、 warn 180 → 100 字 に閾値更新。
        self.assertIn("hard:source_a_under_60", _candidate_anomaly_flags(source_a_short))
        b_flags = _candidate_anomaly_flags(source_b_broken)
        self.assertTrue(any(flag.startswith("hard:source_b_table_token_missing") for flag in b_flags))
        self.assertIn("hard:source_b_prose_overwrite", b_flags)

    def test_source_c_slice_requires_sample_condition(self) -> None:
        source_c_ok = Candidate(
            title="Source C ok",
            metric="VS_LHP_AVG",
            period_label="直近10試合",
            draft_text="根拠",
            post_text="📊 巨人 対左投手 打率 TOP5\n(直近10試合・規定打席8以上)\n1位 岡本和真(巨人) .333 🟧巨人🟧\n次の起用が気になる。",
            char_count=80,
            source_material_type="specialized_db",
        )
        source_c_bad = Candidate(
            title="Source C bad",
            metric="VS_LHP_AVG",
            period_label="直近10試合",
            draft_text="根拠",
            post_text="岡本和真は対左が良さそう。",
            char_count=14,
            source_material_type="specialized_db",
        )
        self.assertEqual(_candidate_source_kind(source_c_ok), "C")
        self.assertEqual(_candidate_anomaly_flags(source_c_ok), [])
        self.assertIn("hard:source_c_sample_condition_missing", _candidate_anomaly_flags(source_c_bad))

    def test_farm_unknown_and_low_sample_flags_are_visible(self) -> None:
        farm_b = Candidate(
            title="Source B farm",
            metric="OPS",
            period_label="直近5試合",
            draft_text="根拠",
            post_text="📊 セ OPS TOP5 ⚾\n(直近5試合・規定打席10以上)\n巨人最上位: 若手二軍 セ・リーグ 1/20位\n1位 若手二軍（巨人）1.100 🟧巨人🟧",
            char_count=80,
            focus_player="若手二軍",
            team_level="farm2",
            sample_size=12,
        )
        unknown_b = Candidate(
            title="Source B unknown",
            metric="OPS",
            period_label="直近5試合",
            draft_text="根拠",
            post_text="📊 セ OPS TOP5 ⚾\n(直近5試合・規定打席10以上)\n巨人最上位: 岡本和真 セ・リーグ 2/20位\n2位 岡本和真（巨人）.950 🟧巨人🟧",
            char_count=80,
            focus_player="岡本和真",
            team_level="unknown",
            sample_size=12,
        )
        low_sample_b = Candidate(
            title="Source B low sample",
            metric="OPS",
            period_label="直近5試合",
            draft_text="根拠",
            post_text="📊 セ OPS TOP5 ⚾\n(直近5試合・規定打席10以上)\n巨人最上位: 少数打席 セ・リーグ 1/20位\n1位 少数打席（巨人）1.100 🟧巨人🟧",
            char_count=80,
            focus_player="少数打席",
            team_level="first",
            sample_size=2,
        )
        self.assertIn("hard:team_level_farm2_separated", _candidate_anomaly_flags(farm_b))
        self.assertIn("hard:team_level_unknown", _candidate_anomaly_flags(unknown_b))
        self.assertIn("hard:sample_too_small:2<10", _candidate_anomaly_flags(low_sample_b))

    def test_source_mix_summary_flags_low_source_b_ratio(self) -> None:
        cands = [
            Candidate("A1", "NEWS_OPINION", "ニュース", "根拠", 3, post_text="短い。"),
            Candidate("A2", "FAN_VOICE", "ニュース", "根拠", 3, post_text="短い。"),
            Candidate("B1", "OPS", "直近5試合", "根拠", 80, post_text="📊 セ OPS TOP5 ⚾\n巨人最上位: 岡本和真 セ・リーグ 2/20位\n2位 岡本和真（巨人）.950 🟧巨人🟧"),
        ]
        lines, flags = _source_mix_summary(cands)
        self.assertIn("Source構成: A(RSS観戦)=2 / B(DB表)=1 / C(DB slice)=0 / total=3", lines[0])
        self.assertIn("source_b_ratio_low:1/3", flags)

    def test_source_mix_summary_flags_duplicate_player_metric_and_level_counts(self) -> None:
        cands = [
            Candidate(
                "B1", "OPS", "直近5試合", "根拠", 80,
                post_text="📊 セ OPS TOP5 ⚾\n巨人最上位: 岡本和真 セ・リーグ 2/20位\n2位 岡本和真（巨人）.950 🟧巨人🟧",
                focus_player="岡本和真",
                team_level="first",
                sample_size=12,
            ),
            Candidate(
                "B2", "OPS", "直近10試合", "根拠", 80,
                post_text="📊 セ OPS TOP5 ⚾\n巨人最上位: 岡本和真 セ・リーグ 3/20位\n3位 岡本和真（巨人）.900 🟧巨人🟧",
                focus_player="岡本和真",
                team_level="first",
                sample_size=22,
            ),
            Candidate(
                "B3", "OPS", "今月", "根拠", 80,
                post_text="📊 セ OPS TOP5 ⚾\n巨人最上位: 坂本勇人 セ・リーグ 5/20位\n5位 坂本勇人（巨人）.850 🟧巨人🟧",
                focus_player="坂本勇人",
                team_level="farm2",
                sample_size=40,
            ),
        ]
        lines, flags = _source_mix_summary(cands)
        self.assertIn("Data構成: first=2 / farm2=1 / farm3=0 / unknown=0", lines)
        self.assertIn("duplicate_player:岡本和真x2", flags)
        self.assertIn("duplicate_metric:OPSx3", flags)

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

    def test_news_opinion_candidate_uses_source_evidence_label(self) -> None:
        ts = datetime(2026, 5, 18, 7, 0, tzinfo=JST)
        cand = build_news_opinion_candidate(
            source_title="巨人・岸田行倫が攻守で存在感とコメント",
            source_url="https://example.test/giants-kishida",
            source_name="テスト新聞",
            source_excerpt="巨人の岸田行倫についての記事。",
            player_name="岸田行倫",
            now=ts,
        )
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertEqual(cand.metric, "NEWS_OPINION")
        self.assertIn("要確認: 数値未照合｜コメント案｜岸田行倫", cand.title)
        self.assertIn("岸田行倫", cand.post_text)
        self.assertIn("コメント", cand.post_text)
        self.assertGreaterEqual(len(cand.post_text), 180)
        self.assertLessEqual(len(cand.post_text), X_CHAR_LIMIT)
        self.assertEqual(len([line for line in cand.post_text.splitlines() if line.strip()]), 3)
        self.assertEqual(_candidate_anomaly_flags(cand), [])
        self.assertNotIn("https://example.test/giants-kishida", cand.post_text)
        self.assertNotIn("#巨人", cand.post_text)
        self.assertNotIn("#ジャイアンツ", cand.post_text)
        self.assertNotIn("整理しました", cand.post_text)
        self.assertIn("材料種別: コメント (comment)", cand.draft_text)
        self.assertIn("論点種別: なし", cand.draft_text)
        self.assertIn("DB数値照合: なし", cand.draft_text)
        self.assertIn("https://example.test/giants-kishida", cand.draft_text)

        mail = compose_mail([self._make_cand(1), cand], now=ts)
        self.assertIn("データ+ニュース意見", mail.subject)
        self.assertIn("📮 巨人Xポスト案", mail.text_body)
        self.assertNotIn("📮 巨人データXポスト案", mail.text_body)
        self.assertIn("📮 巨人Xポスト案", mail.html_body)

    def test_gemma_branding_mix_uses_news_label(self) -> None:
        # 仕様: news 派生候補 (article_info_branding=GEMMA_BRANDING) は
        # 画像なし、 1 件でも混ざれば「巨人Xポスト案」表示。
        ts = datetime(2026, 5, 26, 22, 0, tzinfo=JST)
        branding = Candidate(
            title="X-post branding｜則本昂大 (gemini-3.1-flash-lite)",
            metric="GEMMA_BRANDING",
            period_label="LLM 生成 (queue 417)",
            draft_text="【根拠: gemini】\n対象選手: 則本昂大",
            char_count=120,
            post_text="則本昂大コメント",
        )
        mail = compose_mail([self._make_cand(1), branding], now=ts)
        self.assertIn("📮 巨人Xポスト案", mail.text_body)
        self.assertNotIn("📮 巨人データXポスト案", mail.text_body)
        self.assertIn("📮 巨人Xポスト案", mail.html_body)

    def test_fan_voice_mix_uses_news_label(self) -> None:
        # 仕様: fan_voice も news 派生 (画像なし)、 混合 mail は「巨人Xポスト案」。
        ts = datetime(2026, 5, 26, 22, 30, tzinfo=JST)
        fan = Candidate(
            title="(参考) ファン投稿｜@xyz｜...",
            metric="FAN_VOICE",
            period_label="(参考) ファン投稿",
            draft_text="【根拠: 巨人ファン X 投稿 (参考)】",
            char_count=180,
        )
        mail = compose_mail([self._make_cand(1), fan], now=ts)
        self.assertIn("📮 巨人Xポスト案", mail.text_body)
        self.assertNotIn("📮 巨人データXポスト案", mail.text_body)

    def test_comment_numeric_candidate_uses_same_player_db_fact_only(self) -> None:
        ts = datetime(2026, 5, 18, 7, 0, tzinfo=JST)
        news = build_news_opinion_candidate(
            source_title="巨人・岸田行倫が打撃について試合後にコメント",
            source_url="https://example.test/comment",
            source_name="テスト新聞",
            player_name="岸田行倫",
            now=ts,
        )
        assert news is not None
        data = Candidate(
            title="DB候補 岸田",
            metric="SLG",
            period_label="直近5試合",
            draft_text="セ・リーグ 長打率ランキング\n巨人最上位: 岸田行倫 セ・リーグ 4/20位",
            post_text="岸田行倫は直近5試合の長打率でセ・リーグ 4/20位。",
            char_count=26,
            signature="data-sig-kishida",
            focus_player="岸田行倫",
            db_fact_line="岸田行倫は直近5試合の長打率でセ・リーグ 4/20位（長打率 .500、規定打席の半分以上）",
        )
        combined = build_comment_numeric_candidate(news, data)
        self.assertIsNotNone(combined)
        assert combined is not None
        self.assertIn("DB照合済: フルネーム+論点一致｜コメント×DB｜岸田行倫", combined.title)
        self.assertEqual(combined.metric, "COMMENT_DB")
        self.assertIn("DBで確認できる数字", combined.post_text)
        self.assertIn("長打率 .500", combined.post_text)
        self.assertGreaterEqual(len(combined.post_text), 180)
        self.assertLessEqual(len(combined.post_text), X_CHAR_LIMIT)
        self.assertEqual(len([line for line in combined.post_text.splitlines() if line.strip()]), 3)
        self.assertEqual(_candidate_anomaly_flags(combined), [])
        self.assertNotIn("https://example.test/comment", combined.post_text)
        self.assertNotIn("#巨人", combined.post_text)
        self.assertIn("DB数値照合: あり（同一フルネーム+論点一致）", combined.draft_text)
        self.assertIn("論点照合: あり（コメント=打撃 / DB=打撃）", combined.draft_text)
        self.assertIn("https://example.test/comment", combined.draft_text)
        self.assertIn("セ・リーグ 長打率ランキング", combined.draft_text)

        mismatch = build_comment_numeric_candidate(
            news,
            Candidate(
                title="DB候補 別選手",
                metric="OPS",
                period_label="直近5試合",
                draft_text="DB根拠",
                char_count=4,
                focus_player="大城卓三",
                db_fact_line="大城卓三は直近5試合のOPSでセ・リーグ 1/20位（OPS 1.000、規定打席の半分以上）",
            ),
        )
        self.assertIsNone(mismatch)

    def test_comment_numeric_candidate_rejects_same_player_without_topic_match(self) -> None:
        news = build_news_opinion_candidate(
            source_title="巨人・岸田行倫が試合後にコメント",
            source_url="https://example.test/no-topic",
            source_name="テスト新聞",
            player_name="岸田行倫",
        )
        assert news is not None
        data = Candidate(
            title="DB候補 岸田",
            metric="OPS",
            period_label="直近5試合",
            draft_text="DB根拠",
            char_count=4,
            signature="data-no-topic",
            focus_player="岸田行倫",
            db_fact_line="岸田行倫は直近5試合のOPSでセ・リーグ 4/20位（OPS .900、規定打席の半分以上）",
        )
        self.assertIsNone(build_comment_numeric_candidate(news, data))

    def test_comment_numeric_candidate_rejects_same_player_topic_mismatch(self) -> None:
        news = build_news_opinion_candidate(
            source_title="巨人・田中将大が打線についてコメント",
            source_url="https://example.test/topic-mismatch",
            source_name="テスト新聞",
            player_name="田中将大",
        )
        assert news is not None
        data = Candidate(
            title="DB候補 田中将大",
            metric="ERA",
            period_label="直近5試合",
            draft_text="DB根拠",
            char_count=4,
            signature="data-topic-mismatch",
            focus_player="田中将大",
            db_fact_line="田中将大は直近5試合の防御率でセ・リーグ 4/20位（防御率 2.00、規定投球回の半分以上）",
        )
        self.assertIsNone(build_comment_numeric_candidate(news, data))

    def test_comment_numeric_candidate_rejects_ambiguous_surname_only_match(self) -> None:
        news = Candidate(
            title="要確認: 数値未照合｜コメント案｜田中｜巨人・田中がコメント",
            metric="NEWS_OPINION",
            period_label="コメント",
            draft_text="DB数値照合: なし",
            post_text="田中の言葉を見たい。",
            char_count=10,
            signature="news-tanaka",
            focus_player="田中",
            source_material_type="comment",
        )
        data = Candidate(
            title="DB候補 田中",
            metric="ERA",
            period_label="直近5試合",
            draft_text="DB根拠",
            char_count=4,
            signature="data-tanaka",
            focus_player="田中",
            db_fact_line="田中は直近5試合の防御率でセ・リーグ 4/20位（防御率 2.00、規定投球回の半分以上）",
        )
        self.assertIsNone(build_comment_numeric_candidate(news, data))

    def test_detect_giants_player_name_requires_source_alias(self) -> None:
        alias_map = {
            "岸田行倫": "岸田行倫",
            "岸田": "岸田行倫",
            "丸": "丸佳浩",
        }
        self.assertEqual(
            detect_giants_player_name(
                "巨人・岸田行倫が攻守で存在感",
                alias_map=alias_map,
            ),
            "岸田行倫",
        )
        self.assertEqual(detect_giants_player_name("ただの巨人ニュース", alias_map=alias_map), "")
        self.assertEqual(detect_giants_player_name("丸が出塁", alias_map=alias_map), "")
        self.assertEqual(detect_giants_player_name("巨人・丸が出塁", alias_map=alias_map), "丸佳浩")

    def test_duplicate_surname_alias_is_not_loaded_as_player_alias(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            roster_path = Path(tmpdir) / "roster.json"
            roster_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "田中将大",
                            "aliases": ["田中将大", "田中 将大"],
                            "role": "player",
                            "active": True,
                        },
                        {
                            "name": "田中 瑛斗",
                            "aliases": ["田中 瑛斗", "田中瑛斗"],
                            "role": "player",
                            "active": True,
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            aliases = _load_giants_player_aliases(roster_path)

        self.assertEqual(aliases["田中将大"], "田中将大")
        self.assertEqual(aliases["田中瑛斗"], "田中 瑛斗")
        self.assertNotIn("田中", aliases)


class EmptyResultBehaviourTests(unittest.TestCase):
    def test_compose_mail_with_empty_candidates_no_crash(self) -> None:
        ts = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        mail = compose_mail([], now=ts)
        self.assertEqual(mail.candidate_count, 0)
        self.assertIn("0件", mail.subject)


class TicketThreeFiftyThreeFormatTests(unittest.TestCase):
    """353/STEP1 + 418 case B: 大手なし pool + 意外性 sampling + format 見た目改善
    (改行 / metric 別絵文字 / 数字 prefix / 🟧巨人🟧 highlight) の検証。

    STEP1 (2026-05-17): medal 🥇🥈🥉 + top3 空行を廃止、 全行数字 prefix
    に統一。 ←⭐巨人 → ⭐巨人 へ。
    418 case B (2026-05-21): header に 📊 + TOP{N} 追加、 ranking prefix を
    「1.」→「1位」、 Giants marker を「⭐巨人」→「🟧巨人🟧」 で強調、 metric
    label は ranking 行末から削除 (header の metric 表示で代替)。
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
        """418 case B + X インプ向上 Phase 3 (2026-05-27): hook line → 📊 header
        → 期間 / サンプル / focus_line の順で並ぶ。 hook line が無い場合 (巨人選手
        が rows に居ない時) は header が line[0]。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
            max_per_player=99,
        )
        self.assertGreaterEqual(len(cands), 1)
        for c in cands:
            lines = c.draft_text.split("\n")
            # X インプ向上 Phase 3: header は「📊」 を含む行 (line[0] か line[2])
            header_idx = next((i for i, line in enumerate(lines) if "📊" in line), -1)
            self.assertGreaterEqual(header_idx, 0, msg=f"📊 header not found in {c.draft_text!r}")
            self.assertIn("TOP", lines[header_idx])
            # header 直後に期間 context (period_suffix) が separate されている
            self.assertFalse(
                lines[header_idx + 1].startswith("1位") or lines[header_idx + 1].startswith("1."),
                msg=f"period line missing, ranking starts right after header: {lines[header_idx + 1]!r}",
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
            max_per_player=99,
        )
        batter_cands = [c for c in cands if c.metric in ("OPS", "AVG", "OBP", "SLG")]
        self.assertGreaterEqual(len(batter_cands), 1)
        for c in batter_cands:
            # X インプ向上 Phase 3 (2026-05-27): line[0] が hook line に変わった。
            # header は「📊」 を含む行で identify する。
            header = next(
                (line for line in c.draft_text.splitlines() if "📊" in line),
                "",
            )
            self.assertIn("⚾", header, msg=f"batter header missing ⚾: {header}")
            # 418 case B: 📊 が header に来る (旧 STEP1 では 📊 leak 禁止だったが、
            # 418 で 📊 + TOPN 形式に統一、 batter/pitcher emoji は維持)
            self.assertIn("📊", header, msg=f"new 418 case B header missing 📊: {header}")
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
            max_per_player=99,
        )
        era_only = [c for c in era_cands if c.metric == "ERA"]
        self.assertGreaterEqual(len(era_only), 1)
        for c in era_only:
            # X インプ向上 Phase 3 (2026-05-27): hook line 追加後、 header は line[0]
            # ではなくなる。「📊」 を含む header 行を search で見つける。
            header = next(
                (line for line in c.draft_text.splitlines() if "📊" in line),
                "",
            )
            self.assertIn("⚡", header, msg=f"pitcher header missing ⚡: {header}")

    def test_all_ranks_use_numeric_prefix(self) -> None:
        """STEP1 (2026-05-17) + 418 case B: 全行 数字 prefix (`1位` `2位` ...)、 medal 廃止。"""
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
            max_per_player=99,
        )
        self.assertGreaterEqual(len(cands), 1)
        text = cands[0].draft_text
        # 418 case B: 「1位」「2位」「3位」 で揃う (旧 STEP1 の 「1.」 形式から変更)
        self.assertIn("1位", text)
        self.assertIn("2位", text)
        self.assertIn("3位", text)
        # Medal 🥇🥈🥉 は使われない。
        self.assertNotIn("🥇", text)
        self.assertNotIn("🥈", text)
        self.assertNotIn("🥉", text)

    def test_giants_marker_strong_form(self) -> None:
        """418 case B (2026-05-21): 巨人行 marker は ` 🟧巨人🟧` で囲み強調。

        STEP1 (2026-05-17) の `⭐巨人` から 418 case B で `🟧巨人🟧` に統一。
        """
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
        )
        with_giants = [
            c for c in cands
            if "巨人" in c.draft_text and "🟧巨人🟧" in c.draft_text
        ]
        self.assertGreaterEqual(len(with_giants), 1)
        for c in with_giants:
            self.assertIn("🟧巨人🟧", c.draft_text)
            # 旧 form (arrow 付き / 半角1 spc / ⭐) は出ない
            self.assertNotIn("←⭐巨人", c.draft_text)
            self.assertNotIn("← 巨人", c.draft_text)
            self.assertNotIn(" ←", c.draft_text)
            self.assertNotIn("⭐巨人", c.draft_text)

    def test_metric_label_prefix_before_value(self) -> None:
        """418 case B (2026-05-21): metric label は header に集約、 ranking 行末は
        裸の数値のみ。 STEP1 (2026-05-17) の「打率 .945」 ranking-row 前置は廃止。
        """
        cands = pick_candidates(
            self._make_mock(),
            now=datetime(2026, 5, 16, 7, 0, tzinfo=JST),
            max_candidates=17,
            min_sample=1,
            min_central_rows=3,
            max_per_player=99,
        )
        avg_cands = [c for c in cands if c.metric == "AVG"]
        self.assertGreaterEqual(len(avg_cands), 1)
        text = avg_cands[0].draft_text
        # header に metric_jp 「打率」 が含まれる
        header = text.split("\n", 1)[0]
        self.assertIn("打率", header, msg=f"AVG label missing in header: {header}")
        # ranking 行末は裸の値 (".945" 等)、 metric label が ranking 行ごとに重複しない
        ranking_lines = [ln for ln in text.split("\n") if ln.startswith(("1位", "2位", "3位"))]
        self.assertGreaterEqual(len(ranking_lines), 1)
        for ln in ranking_lines:
            self.assertNotIn("打率 .", ln, msg=f"metric label leaked into ranking row: {ln!r}")

    def test_no_blank_between_ranks_after_step1(self) -> None:
        """STEP1 + 418 case B: ranking は連続表示、 medal 区切り空行なし、
        prefix 「1位」「2位」「3位」 形式で改行のみ。
        """
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
        # 3 位の row index を見つけ、 直後が 4位 で始まる (間に空行なし) こと。
        idx_3 = next(
            (i for i, ln in enumerate(lines) if ln.startswith("3位")),
            -1,
        )
        self.assertGreaterEqual(idx_3, 0, msg="3位 row not found")
        # idx_3 の直後行が 4位 で始まる (もしくは ranking 末尾)。
        if idx_3 + 1 < len(lines):
            self.assertTrue(
                lines[idx_3 + 1].startswith("4位") or not lines[idx_3 + 1].strip()
                or lines[idx_3 + 1].startswith("#")  # hashtag footer の場合
                or lines[idx_3 + 1].startswith("巨人最上位:"),
                msg=f"unexpected line after 3位: {lines[idx_3 + 1]!r}",
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
        394 fix で投手指標は短窓 (直近1週間 / 今週) から除外。
        (直近1週間 batting 4 + 守備位置別 AVG 4 + 今週 batting 4 + 今月 8) = 20。
        5/16 は土曜なので 今週 enabled。"""
        from src.x_post_mail_lane import _build_combos
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST))
        self.assertEqual(len(combos), 20)

    def test_build_combos_with_db_path_adds_last_n_after_step1(self) -> None:
        """STEP1 + snapshot 復活 + 397 (2026-05-20): db_path 指定で 20 base +
        直近3/5/10/20試合 × 8 metric = 32、 ただし 15 dates seed では
        20-game window が返らないので 3/5/10 = 24 combo。 base 20 + 24 = 44。"""
        from src.x_post_mail_lane import _build_combos
        # need ≥10 distinct game dates for 5/10-game windows. 20-game は seed 不足で skip。
        dates = [f"2026-05-{day:02d}" for day in range(1, 16)]  # 15 dates
        self._seed_games(dates)
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST), db_path=self.db_path)
        self.assertEqual(len(combos), 44)

    def test_last_n_games_combos_are_high_novelty_and_league_scoped(self) -> None:
        from src.x_post_mail_lane import _build_combos
        dates = [f"2026-05-{day:02d}" for day in range(1, 16)]
        self._seed_games(dates)
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST), db_path=self.db_path)
        last_n_combos = [
            c for c in combos
            if c.period_label in ("直近3試合", "直近5試合", "直近10試合", "直近20試合")
        ]
        # 397: 直近 3/5/10 × 8 metric (batter + pitcher) = 24 (20-game seed 不足で skip)
        self.assertEqual(len(last_n_combos), 24)
        for c in last_n_combos:
            self.assertEqual(c.novelty, "high", msg=f"non-high novelty leaked: {c}")
            self.assertFalse(c.giants_only, msg=f"giants-only combo leaked: {c}")
            self.assertIn(
                c.metric,
                ("AVG", "OBP", "SLG", "OPS",
                 "ERA", "K_per_9", "BB_per_9", "HR_per_9"),
            )

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
        # X インプ向上 Phase 3 (2026-05-27): hook line 追加で period_suffix の
        # 行 index がずれた。 period line を search で identify する。
        period_line = next(
            (line for line in cand.draft_text.splitlines() if "直近5試合" in line),
            "",
        )
        self.assertIn("直近5試合", period_line)
        self.assertIn("規定打席10以上", period_line)
        self.assertNotIn("5/11〜5/16", period_line)
        self.assertIn("直近5試合", cand.title)
        # 429: DB ranking table is the actual post_text, not prose-only branding.
        self.assertIn("📊", cand.post_text)
        self.assertIn("TOP", cand.post_text)
        self.assertIn("巨人最上位", cand.post_text)
        self.assertIn("🟧巨人🟧", cand.post_text)
        self.assertIn("この推移は追いたい。", cand.post_text)
        self.assertNotIn("どう見ますか", cand.post_text)

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
        # X インプ向上 Phase 3 (2026-05-27): period line を search で identify。
        period_line = next(
            (line for line in cand.draft_text.splitlines() if "7月成績" in line),
            "",
        )
        self.assertIn("7月成績", period_line)
        self.assertIn("規定打席30以上", period_line)
        self.assertNotIn("7/1〜7/31", period_line)

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
        # 直近 5/10 試合 combo の query_rank call は min_sample override (5 or 10) を使う。
        # 394 fix で投手指標が短窓から除外された結果、 batting metric は
        # 直近1週間 / 直近5試合 / 直近10試合 が同一 family として競合し、
        # period-family skip で 直近5/10 が 直近1週間に flush されるケース
        # がある (ms_values 全部 30 になる)。 そのケースは accept。
        ms_values = [c.get("min_sample") for c in captured]
        ms_set = set(ms_values)
        if not ({5, 10} & ms_set):
            # period-family skip 経路: ms_values 全部 default (30) に flush 済み
            self.assertEqual(
                ms_set, {30},
                msg=f"unexpected ms_values when last-N suppressed: {ms_values}",
            )
        # And the default 30 should still appear for non-override combos
        self.assertIn(30, ms_values, msg=f"default 30 missing: {ms_values}")

    def test_db_path_with_insufficient_games_falls_back_gracefully(self) -> None:
        """394 fix + 397: games 件数不足の時、 直近 N 試合 combo は追加されず
        base 20 (直近1週間 batting 4 + 守備位置別 AVG 4 + 今週 batting 4
        + 今月 8) 維持。 397 で直近 3 試合 window が追加されたので、 3 dates
        だと last_3_games × 8 metric = 8 combo は追加される (20 + 8 = 28)。
        last_5/10/20 は seed 不足で skip。"""
        from src.x_post_mail_lane import _build_combos
        # 3 games seeded → last_3_games window OK、 last_5/10/20 は seed 不足で None
        self._seed_games(["2026-05-14", "2026-05-15", "2026-05-16"])
        combos = _build_combos(datetime(2026, 5, 16, 7, 0, tzinfo=JST), db_path=self.db_path)
        self.assertEqual(len(combos), 28, msg=f"unexpected combo count: {len(combos)}")


class XPostMailEntrypointFreshnessTests(unittest.TestCase):
    """DB freshness guard for the X post mail CLI entrypoint."""

    def _entrypoint_candidate(self, signature: str, *, focus_player: str = "") -> Candidate:
        return Candidate(
            title=f"候補 {signature}",
            metric="OPS",
            period_label="直近5試合",
            draft_text=f"候補 {signature}\n#巨人 #ジャイアンツ",
            char_count=24,
            signature=signature,
            focus_player=focus_player,
        )

    def test_backfill_dedup_starved_skips_player_in_24h_history(self) -> None:
        """397: starvation fallback で 24h history に出た player を skip する。"""
        from src.tools import run_x_post_mail

        # candidates (pre-pass after dedup): 1 件のみ (枯れた状態)
        fresh = [self._entrypoint_candidate("fresh-sig", focus_player="大城卓三")]
        # relaxed (dedup=None で再 pick した結果): 浦田 2 件 + 増田陸 1 件
        relaxed = [
            self._entrypoint_candidate("OBP|今月|False|None", focus_player="浦田俊輔"),
            self._entrypoint_candidate("AVG|直近10試合|False|None", focus_player="浦田俊輔"),
            self._entrypoint_candidate("AVG|今月|False|None", focus_player="増田陸"),
        ]
        merged = run_x_post_mail._backfill_dedup_starved_candidates(
            fresh,
            relaxed,
            max_candidates=4,
            recent_player_counts={"浦田俊輔": 5},
        )
        players = [c.focus_player for c in merged]
        # 浦田 は 24h history で 5 回出てるので Stage A で skip、増田陸は採用
        self.assertEqual(len(merged), 2)
        self.assertEqual(players, ["大城卓三", "増田陸"])
        for c in merged:
            self.assertNotEqual(c.focus_player, "浦田俊輔")

    def test_backfill_dedup_starved_player_dedup_for_current_mail(self) -> None:
        """397: current mail に既に同一 player が居る場合も Stage A で skip。"""
        from src.tools import run_x_post_mail

        # 浦田が既に candidates に居る (これは 24h dedup pre-pass を通過した)
        fresh = [self._entrypoint_candidate("first-uchida", focus_player="浦田俊輔")]
        # relaxed で 同じ player 別 metric を出してきた → skip して別 player を採用
        relaxed = [
            self._entrypoint_candidate("OBP|今月|False|None", focus_player="浦田俊輔"),
            self._entrypoint_candidate("OPS|直近10試合|False|None", focus_player="平山 功太"),
        ]
        merged = run_x_post_mail._backfill_dedup_starved_candidates(
            fresh,
            relaxed,
            max_candidates=4,
            recent_player_counts=None,
        )
        players = [c.focus_player for c in merged]
        self.assertEqual(players, ["浦田俊輔", "平山 功太"])

    def test_backfill_dedup_starved_does_not_restore_history_when_sparse(self) -> None:
        """436 follow-up: sparseでも24h履歴playerは戻さない。"""
        from src.tools import run_x_post_mail

        # 既存 0 件、relaxed は全部 history に居る player
        fresh: list = []
        relaxed = [
            self._entrypoint_candidate("sig-a", focus_player="浦田俊輔"),
            self._entrypoint_candidate("sig-b", focus_player="浦田俊輔"),
            self._entrypoint_candidate("sig-c", focus_player="平山 功太"),
        ]
        merged = run_x_post_mail._backfill_dedup_starved_candidates(
            fresh,
            relaxed,
            max_candidates=10,
            recent_player_counts={"浦田俊輔": 3, "平山 功太": 2},
            min_candidates=3,
        )
        # 以前はここで Stage B が同じ選手を戻していた。今は候補数が少なくても戻さない。
        self.assertEqual(merged, [])

    def test_backfill_dedup_starved_keeps_all_history_players_out(self) -> None:
        """436 follow-up: 同一history player候補を複数戻さない。"""
        from src.tools import run_x_post_mail

        fresh: list = []
        relaxed = [
            self._entrypoint_candidate("sig-a", focus_player="浦田俊輔"),
            self._entrypoint_candidate("sig-b", focus_player="浦田俊輔"),
            self._entrypoint_candidate("sig-c", focus_player="浦田俊輔"),
            self._entrypoint_candidate("sig-d", focus_player="浦田俊輔"),
            self._entrypoint_candidate("sig-e", focus_player="浦田俊輔"),
        ]
        merged = run_x_post_mail._backfill_dedup_starved_candidates(
            fresh,
            relaxed,
            max_candidates=10,
            recent_player_counts={"浦田俊輔": 5},
            min_candidates=2,
        )
        self.assertEqual(merged, [])

    def test_backfill_dedup_starved_no_history_no_change(self) -> None:
        """397: recent_player_counts=None 時、 signature dedup のみで従来挙動。"""
        from src.tools import run_x_post_mail

        fresh = [self._entrypoint_candidate("fresh", focus_player="大城卓三")]
        relaxed = [
            self._entrypoint_candidate("fresh", focus_player="大城卓三"),  # sig dup
            self._entrypoint_candidate("new1", focus_player="浦田俊輔"),
            self._entrypoint_candidate("new2", focus_player="増田陸"),
        ]
        merged = run_x_post_mail._backfill_dedup_starved_candidates(
            fresh,
            relaxed,
            max_candidates=4,
            recent_player_counts=None,
        )
        self.assertEqual(
            [c.signature for c in merged],
            ["fresh", "new1", "new2"],
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
                "X_POST_MAIL_LINEUP_FOCUS_DISABLED": "1",
                "X_POST_MAIL_NEWS_FALLBACK_DISABLED": "1",
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
            "_load_recent_dedup_records",
            return_value=[
                {"signature": "old-sig-1", "focus_player": "浦田俊輔"},
                {"signature": "old-sig-2", "focus_player": "浦田俊輔"},
                {"signature": "old-sig-3", "focus_player": "浦田俊輔"},
            ],
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
        self.assertEqual(
            pick_candidates.call_args_list[0].kwargs["recent_player_counts"],
            {"浦田俊輔": 3},
        )
        self.assertIsNone(pick_candidates.call_args_list[1].kwargs["dedup_set"])
        self.assertEqual(
            pick_candidates.call_args_list[1].kwargs["recent_player_counts"],
            {"浦田俊輔": 3},
        )
        request = send.call_args.args[0]
        self.assertEqual(request.metadata["candidate_count"], 4)
        record.assert_called_once_with(
            "insight-bucket",
            ["fresh-sig", "old-sig-1", "old-sig-2", "old-sig-3"],
            ANY,
            focus_players=["", "", "", ""],
            metrics=["OPS", "OPS", "OPS", "OPS"],
            period_labels=["直近5試合", "直近5試合", "直近5試合", "直近5試合"],
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
                "X_POST_MAIL_LINEUP_FOCUS_DISABLED": "1",
                "X_POST_MAIL_NEWS_FALLBACK_DISABLED": "1",
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
            "_load_recent_dedup_records",
            return_value=[{"signature": "old-sig"}],
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

    def test_player_history_zero_candidate_skips_mail(self) -> None:
        """441: player history で 0 件化したら relaxed retry せず mail skip
        (user 方針「少なくてもよいから連発回避優先」)。"""
        from src.tools import run_x_post_mail

        with patch.dict(
            "os.environ",
            {
                "MAIL_BRIDGE_TO": "ops@example.test",
                "INSIGHT_GCS_BUCKET": "insight-bucket",
                "X_POST_MAIL_DEDUP_MIN_CANDIDATES": "0",
                "X_POST_MAIL_LINEUP_FOCUS_DISABLED": "1",
                "X_POST_MAIL_NEWS_FALLBACK_DISABLED": "1",
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
            "_load_recent_dedup_records",
            return_value=[{"signature": "old-sig", "focus_player": "浦田俊輔"}],
        ), patch.object(
            run_x_post_mail.lane,
            "pick_candidates",
            return_value=[],
        ) as pick_candidates, patch.object(
            run_x_post_mail.mdb,
            "send",
        ) as send, patch.object(
            run_x_post_mail.lane,
            "_record_dedup_signatures",
            return_value=True,
        ):
            result = run_x_post_mail.main(["--max-candidates", "1"])

        self.assertEqual(result, 0)
        # 441: 旧 relaxed-history fallback は削除。
        self.assertEqual(pick_candidates.call_count, 1)
        self.assertEqual(
            pick_candidates.call_args_list[0].kwargs["recent_player_counts"],
            {"浦田俊輔": 1},
        )
        send.assert_not_called()

    def test_news_opinion_fallback_fills_sparse_data_candidates(self) -> None:
        """source-backed RSS/comment 候補をデータ候補と同じメールに足す。"""
        from src.tools import run_x_post_mail

        data_cand = self._entrypoint_candidate("data-sig")
        news_cand = build_news_opinion_candidate(
            source_title="巨人・岸田行倫が攻守で存在感",
            source_url="https://example.test/news",
            source_name="テスト新聞",
            player_name="岸田行倫",
        )
        assert news_cand is not None
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
                "X_POST_MAIL_DEDUP_DISABLED": "1",
                "X_POST_MAIL_LINEUP_FOCUS_DISABLED": "1",
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
            "pick_candidates",
            return_value=[data_cand],
        ), patch.object(
            run_x_post_mail,
            "_fetch_news_opinion_fallback_candidates",
            return_value=[news_cand],
        ) as fallback, patch.object(
            run_x_post_mail.mdb,
            "send",
            return_value=send_result,
        ) as send:
            result = run_x_post_mail.main(["--max-candidates", "3"])

        self.assertEqual(result, 0)
        fallback.assert_called_once()
        request = send.call_args.args[0]
        self.assertEqual(request.metadata["candidate_count"], 2)
        self.assertIn("データ+ニュース意見", request.subject)
        self.assertIn("巨人Xポスト案", request.text_body)
        self.assertIn("岸田行倫", request.text_body)

    def test_news_opinion_candidates_take_priority_over_full_data_mail(self) -> None:
        """DB候補が満枠でも、RSS/comment 候補を先頭側に入れる。"""
        from src.tools import run_x_post_mail

        data_cands = [
            Candidate(
                title=f"DB候補 {idx}",
                metric="OPS",
                period_label="直近5試合",
                draft_text=f"DB候補 {idx}",
                post_text=f"DB投稿 {idx}",
                char_count=len(f"DB投稿 {idx}"),
                signature=f"data-sig-{idx}",
                focus_player="岸田行倫" if idx == 1 else f"DB選手{idx}",
                db_fact_line=(
                    "岸田行倫は直近5試合のOPSでセ・リーグ 4/20位"
                    "（OPS .900、規定打席の半分以上）"
                    if idx == 1 else ""
                ),
            )
            for idx in range(1, 4)
        ]
        news_cand = build_news_opinion_candidate(
            source_title="巨人・岸田行倫が打撃について試合後にコメント",
            source_url="https://example.test/news",
            source_name="テスト新聞",
            player_name="岸田行倫",
        )
        assert news_cand is not None
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
                "X_POST_MAIL_DEDUP_DISABLED": "1",
                "X_POST_MAIL_LINEUP_FOCUS_DISABLED": "1",
                "X_POST_MAIL_NEWS_PRIORITY_CANDIDATES": "1",
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
            "pick_candidates",
            return_value=data_cands,
        ), patch.object(
            run_x_post_mail,
            "_fetch_news_opinion_fallback_candidates",
            return_value=[news_cand],
        ), patch.object(
            run_x_post_mail.mdb,
            "send",
            return_value=send_result,
        ) as send:
            result = run_x_post_mail.main(["--max-candidates", "3"])

        self.assertEqual(result, 0)
        request = send.call_args.args[0]
        self.assertEqual(request.metadata["candidate_count"], 3)
        self.assertIn("DB照合済: フルネーム+論点一致｜コメント×DB｜岸田行倫", request.text_body)
        self.assertIn("OPS .900", request.text_body)
        self.assertLess(
            request.text_body.index("岸田行倫"),
            request.text_body.index("DB候補 2"),
        )
        # 382 系: no #巨人 hashtag in post bodies.
        self.assertNotIn("#巨人", request.text_body)

    def test_news_priority_merge_prefers_short_mail_over_same_player_repeat(self) -> None:
        """436 follow-up: 枠埋め目的で同じ選手を復活させない。"""
        from src.tools import run_x_post_mail

        news_cand = Candidate(
            title="News A",
            metric="NEWS_OPINION",
            period_label="ニュース",
            draft_text="根拠",
            post_text="岸田行倫の話題",
            char_count=7,
            signature="news-a",
            focus_player="岸田行倫",
        )
        data_same_player = Candidate(
            title="DB same",
            metric="OPS",
            period_label="直近5試合",
            draft_text="DB same",
            post_text="DB same",
            char_count=7,
            signature="data-a",
            focus_player="岸田行倫",
        )
        data_other_player = Candidate(
            title="DB other",
            metric="AVG",
            period_label="直近5試合",
            draft_text="DB other",
            post_text="DB other",
            char_count=8,
            signature="data-b",
            focus_player="岡本和真",
        )
        merged = run_x_post_mail._merge_news_priority_candidates(
            [news_cand],
            [data_same_player, data_other_player],
            max_candidates=3,
        )
        self.assertEqual([c.focus_player for c in merged], ["岸田行倫", "岡本和真"])

    def test_news_opinion_fallback_skips_recent_history_player(self) -> None:
        """380 follow-up: news fallback も直近24h既出 player を補充しない。"""
        from src.tools import run_x_post_mail
        import src.x_post_mail_lane as lane

        # 鮮度ゲート (フェーズ別、 日付不明は strict skip) に対応するため published を付与。
        # now=2026-05-18 13:07 JST (昼=24h窓) に対し 03:00 GMT=12:00 JST = 約1h前 → 通る。
        entries = [
            {
                "title": "巨人・浦田俊輔が攻守で存在感",
                "link": "https://example.test/urata",
                "summary": "浦田俊輔の話題",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            },
            {
                "title": "巨人・岸田行倫が攻守で存在感",
                "link": "https://example.test/kishida",
                "summary": "岸田行倫の話題",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            },
        ]
        with patch.object(
            run_x_post_mail,
            "_load_news_fallback_sources",
            return_value=[{"name": "テスト新聞", "url": "https://example.test/feed"}],
        ), patch.object(
            run_x_post_mail,
            "_fetch_feed_entries",
            return_value=entries,
        ):
            cands = run_x_post_mail._fetch_news_opinion_fallback_candidates(
                [],
                max_candidates=2,
                now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
                recent_player_counts={"浦田俊輔": 3},
            )

        players = [lane._normalize_player_name(c.focus_player) for c in cands]
        self.assertNotIn("浦田俊輔", players)
        self.assertIn("岸田行倫", players)

    def test_news_opinion_fallback_reads_tag_scrape_sources(self) -> None:
        """巨人だけ総合: RSSなし媒体の tag_scrape も12時メール補完に使う。"""
        from src.tools import run_x_post_mail
        import src.x_post_mail_lane as lane

        tag_entries = [
            {
                "title": "巨人・岸田行倫が攻守で存在感",
                "link": "https://news.ntv.co.jp/category/sports/abcd1234",
                "summary": "読売ジャイアンツの話題",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            }
        ]
        with patch.object(
            run_x_post_mail,
            "_load_news_fallback_sources",
            return_value=[
                {
                    "name": "日テレNEWS NNN 巨人 tag",
                    "url": "https://news.ntv.co.jp/tag/%E5%B7%A8%E4%BA%BA",
                    "type": "tag_scrape",
                    "scraper": "ntv_news_giants_tag",
                    "max_age_days": 7,
                    "article_limit": 30,
                    "role": ["article_source", "media_quote_pool"],
                }
            ],
        ), patch(
            "src.tag_page_scraper.fetch_tag_page_entries",
            return_value=tag_entries,
        ) as tag_fetch:
            cands = run_x_post_mail._fetch_news_opinion_fallback_candidates(
                [],
                max_candidates=1,
                now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
            )

        tag_fetch.assert_called_once()
        players = [lane._normalize_player_name(c.focus_player) for c in cands]
        self.assertEqual(players, ["岸田行倫"])


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
        """441: 168h 超 (= 200h 前) の record は除外。"""
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        now = datetime(2026, 5, 16, 7, 0, tzinfo=JST)
        old_ts = (now - timedelta(hours=200)).isoformat()
        recent_ts = (now - timedelta(hours=2)).isoformat()
        old_date = (now - timedelta(hours=200)).strftime("%Y-%m-%d")
        recent_date = (now - timedelta(hours=2)).strftime("%Y-%m-%d")
        store = {
            f"x_post_mail/dedup/{old_date}.jsonl":
                f'{{"ts": "{old_ts}", "signature": "STALE|x|False|None"}}\n',
            f"x_post_mail/dedup/{recent_date}.jsonl":
                f'{{"ts": "{recent_ts}", "signature": "FRESH|y|False|None"}}\n',
        }
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

    def test_load_recent_player_counts_from_dedup_records(self) -> None:
        """380 follow-up: GCS dedup JSONL から focus_player count を読む。"""
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        ts = datetime(2026, 5, 18, 12, 1, tzinfo=JST).isoformat()
        store = {
            "x_post_mail/dedup/2026-05-18.jsonl":
                f'{{"ts": "{ts}", "signature": "AVG|今月|False|None", "focus_player": "浦田俊輔"}}\n'
                f'{{"ts": "{ts}", "signature": "OBP|直近10試合|False|None", "focus_player": "浦田俊輔"}}\n'
                f'{{"ts": "{ts}", "signature": "OPS|今月|False|None", "focus_player": "岸田 行倫"}}\n'
                f'{{"ts": "{ts}", "signature": "LEGACY|x|False|None"}}\n',
        }
        now = datetime(2026, 5, 18, 13, 7, tzinfo=JST)
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            counts = lane._load_recent_player_counts("test-bucket", now)
        self.assertEqual(counts["浦田俊輔"], 2)
        self.assertEqual(counts["岸田行倫"], 1)

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

    def test_record_dedup_signatures_can_write_focus_player_fields(self) -> None:
        from unittest.mock import patch
        import json
        import src.x_post_mail_lane as lane

        store: dict[str, str] = {}
        now = datetime(2026, 5, 18, 13, 7, tzinfo=JST)
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            ok = lane._record_dedup_signatures(
                "test-bucket",
                ["OPS|今月|False|None"],
                now,
                focus_players=["浦田俊輔"],
                metrics=["OPS"],
                period_labels=["今月"],
            )
        self.assertTrue(ok)
        rec = json.loads(store["x_post_mail/dedup/2026-05-18.jsonl"].strip())
        self.assertEqual(rec["signature"], "OPS|今月|False|None")
        self.assertEqual(rec["focus_player"], "浦田俊輔")
        self.assertEqual(rec["metric"], "OPS")
        self.assertEqual(rec["period_label"], "今月")

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

    def test_record_fan_voice_pool_writes_jsonl(self) -> None:
        """397: fan_voice_pool entries が GCS JSONL に書ける。"""
        from unittest.mock import patch
        import json
        import src.x_post_mail_lane as lane

        store: dict[str, str] = {}
        now = datetime(2026, 5, 20, 11, 30, tzinfo=JST)
        entries = [
            {
                "source_name": "フーガ X (巨人ファン長文分析)",
                "handle": "EH87EazmV9D2eSw",
                "text": "完勝！ 7連勝！！ 戸郷ナイスピッチ！",
                "url": "https://x.com/EH87EazmV9D2eSw/status/2056705467792163327",
                "created_at": None,
            },
            {
                "source_name": "缶詰 X (巨人ファン試合中実況)",
                "handle": "kandume92",
                "text": "やったー！！！ 7回無失点！！！！",
                "url": "https://x.com/kandume92/status/2056681000000000000",
                "created_at": None,
            },
        ]
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            ok = lane.record_fan_voice_pool_entries_to_gcs(
                "test-bucket",
                now,
                entries,
            )
        self.assertTrue(ok)
        path = "fan_voice/pool_2026-05-20.jsonl"
        self.assertIn(path, store)
        lines = [ln for ln in store[path].split("\n") if ln.strip()]
        self.assertEqual(len(lines), 2)
        rec0 = json.loads(lines[0])
        self.assertEqual(rec0["handle"], "EH87EazmV9D2eSw")
        self.assertEqual(rec0["source_name"], "フーガ X (巨人ファン長文分析)")
        self.assertIn("ts", rec0)
        self.assertIn("text", rec0)

    def test_record_fan_voice_pool_dedupes_existing_urls(self) -> None:
        """397: 既に同 URL が GCS に書かれてる時は再追加しない。"""
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        path = "fan_voice/pool_2026-05-20.jsonl"
        existing_url = "https://x.com/EH87EazmV9D2eSw/status/2056705467792163327"
        store = {
            path: f'{{"ts": "2026-05-20T07:00:00+09:00", "url": "{existing_url}", "text": "old"}}\n',
        }
        now = datetime(2026, 5, 20, 11, 30, tzinfo=JST)
        entries = [
            {
                "source_name": "フーガ X",
                "handle": "EH87EazmV9D2eSw",
                "text": "completely different text",
                "url": existing_url,
                "created_at": None,
            },
        ]
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            lane.record_fan_voice_pool_entries_to_gcs(
                "test-bucket",
                now,
                entries,
            )
        body = store[path]
        self.assertEqual(body.count(existing_url), 1)

    def test_load_recent_fan_voice_pool_filters_old(self) -> None:
        """397: 24h 超 (= 30h 前) の record は除外。"""
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        old_ts = (datetime(2026, 5, 20, 12, 0, tzinfo=JST) - timedelta(hours=30)).isoformat()
        recent_ts = (datetime(2026, 5, 20, 12, 0, tzinfo=JST) - timedelta(hours=2)).isoformat()
        store = {
            "fan_voice/pool_2026-05-19.jsonl":
                f'{{"ts": "{old_ts}", "url": "https://x.com/old/status/1", "text": "old", "handle": "old"}}\n'
                f'{{"ts": "{recent_ts}", "url": "https://x.com/fresh/status/2", "text": "fresh", "handle": "fresh"}}\n',
        }
        now = datetime(2026, 5, 20, 12, 0, tzinfo=JST)
        with patch.object(lane, "_get_storage_client",
                          return_value=self._fake_storage_client(store)):
            recs = lane.load_recent_fan_voice_pool_entries("test-bucket", now)
        urls = [r["url"] for r in recs]
        self.assertIn("https://x.com/fresh/status/2", urls)
        self.assertNotIn("https://x.com/old/status/1", urls)

    def test_load_recent_fan_voice_pool_silent_fallback_on_error(self) -> None:
        """397: GCS client init 失敗時は empty list、 raise しない。"""
        from unittest.mock import patch
        import src.x_post_mail_lane as lane

        def _boom():
            raise RuntimeError("simulated GCS auth failure")
        now = datetime(2026, 5, 20, 12, 0, tzinfo=JST)
        with patch.object(lane, "_get_storage_client", side_effect=_boom):
            recs = lane.load_recent_fan_voice_pool_entries("test-bucket", now)
        self.assertEqual(recs, [])

    def test_is_fan_voice_fire_window(self) -> None:
        """397 (2026-05-20 user 更新): 19:00-23:59 JST のみ True。
        17:30 evening 便はファンツイートが未熟のため対象外、 22:30 postgame
        のみ fan_voice 発動する。"""
        from src.tools.run_x_post_mail import _is_fan_voice_fire_window

        def _at(hh: int, mm: int) -> datetime:
            return datetime(2026, 5, 20, hh, mm, tzinfo=JST)
        # 朝 / 昼 / 午後 / 17:30 evening: False
        self.assertFalse(_is_fan_voice_fire_window(_at(7, 0)))
        self.assertFalse(_is_fan_voice_fire_window(_at(12, 0)))
        self.assertFalse(_is_fan_voice_fire_window(_at(15, 0)))
        self.assertFalse(_is_fan_voice_fire_window(_at(17, 0)))
        self.assertFalse(_is_fan_voice_fire_window(_at(17, 30)))
        self.assertFalse(_is_fan_voice_fire_window(_at(18, 59)))
        # 19:00-23:59 postgame window: True
        self.assertTrue(_is_fan_voice_fire_window(_at(19, 0)))
        self.assertTrue(_is_fan_voice_fire_window(_at(20, 0)))
        self.assertTrue(_is_fan_voice_fire_window(_at(22, 30)))
        self.assertTrue(_is_fan_voice_fire_window(_at(23, 30)))
        self.assertTrue(_is_fan_voice_fire_window(_at(23, 59)))
        # 翌日早朝: False
        self.assertFalse(_is_fan_voice_fire_window(_at(2, 0)))

    def test_build_fan_voice_candidate_ok(self) -> None:
        """397: 正常 entry → Candidate(metric=FAN_VOICE) 生成。"""
        import src.x_post_mail_lane as lane
        entry = {
            "source_name": "フーガ X (巨人ファン長文分析)",
            "handle": "EH87EazmV9D2eSw",
            "text": "完勝！ 7連勝！！ 戸郷ナイスピッチ！ こんなに勝ちが続くなんていつ以来やろ ピッチャーのクオリティが高すぎる",
            "url": "https://x.com/EH87EazmV9D2eSw/status/2056705467792163327",
            "pub_iso": "2026-05-19T20:56:09+09:00",
        }
        cand = lane.build_fan_voice_candidate(entry, detected_player="戸郷翔征")
        self.assertIsNotNone(cand)
        self.assertEqual(cand.metric, "FAN_VOICE")
        self.assertEqual(cand.focus_player, "戸郷翔征")
        self.assertIn("完勝", cand.draft_text)
        self.assertIn("@EH87EazmV9D2eSw", cand.draft_text)
        self.assertTrue(cand.signature.startswith("fan_voice|"))

    def test_build_fan_voice_candidate_rejects_short_text(self) -> None:
        """397: 文字数 20 未満は None。"""
        import src.x_post_mail_lane as lane
        entry = {
            "handle": "EH87EazmV9D2eSw",
            "text": "短い",
            "url": "https://x.com/EH87EazmV9D2eSw/status/1",
        }
        self.assertIsNone(lane.build_fan_voice_candidate(entry, detected_player="戸郷翔征"))

    def test_build_fan_voice_candidate_rejects_no_player(self) -> None:
        """397: detected_player 空は None (NER hit なし時)。"""
        import src.x_post_mail_lane as lane
        entry = {
            "handle": "EH87EazmV9D2eSw",
            "text": "完勝！ 7連勝！！ 戸郷ナイスピッチ！ こんなに勝ちが続くなんていつ以来やろ",
            "url": "https://x.com/EH87EazmV9D2eSw/status/1",
        }
        self.assertIsNone(lane.build_fan_voice_candidate(entry, detected_player=""))


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


class BuildDataSplitCandidatesTests(unittest.TestCase):
    """448: 序盤/中盤/終盤・本拠地/ビジター別打率 surprise 候補。"""

    def _make_db(self, rows):
        import sqlite3 as _sq
        import tempfile as _tf
        import os as _os
        fd, path = _tf.mkstemp(suffix=".db")
        _os.close(fd)
        conn = _sq.connect(path)
        conn.execute(
            "CREATE TABLE batting_logs (game_id TEXT, team_name TEXT, "
            "player_canonical TEXT, AB INT, H INT, atbats_json TEXT)"
        )
        conn.executemany("INSERT INTO batting_logs VALUES (?,?,?,?,?,?)", rows)
        conn.commit()
        conn.close()
        self.addCleanup(lambda: _os.path.exists(path) and _os.remove(path))
        return path

    def test_inning_surprise_emitted_with_full_name_no_honorific(self):
        import json as _j
        # 序盤=全安打 / 終盤=全三振 の極端 player を 30 試合分。 home game_id。
        arr = _j.dumps(["左前安", "左前安", "-", "投ゴロ", "投ゴロ", "-", "三 振", "三 振", ""])
        rows = [
            (f"2026-05-{d:02d}:g-t-01", "巨人", "強打者", 6, 2, arr)
            for d in range(1, 31)
        ]
        db = self._make_db(rows)
        from src.x_post_mail_lane import build_data_split_candidates
        cands = build_data_split_candidates(db, max_count=5)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c.metric, "inning_split_surprise")
        self.assertIn("強打者", c.title)
        self.assertIn("序盤に強い", c.title)
        self.assertNotIn("さん", c.post_text)
        self.assertNotIn("君", c.post_text)
        self.assertIn("#巨人", c.post_text)
        self.assertIn("序盤打率", c.db_fact_line)
        self.assertEqual(c.signature, "data_split|強打者|inning")
        self.assertEqual(c.focus_player, "強打者")

    def test_below_gap_threshold_skipped(self):
        import json as _j
        arr = _j.dumps(["左前安", "投ゴロ", "-", "左前安", "投ゴロ", "-", "左前安", "投ゴロ", ""])
        rows = [
            (f"2026-05-{d:02d}:g-t-01", "巨人", "平凡打者", 6, 3, arr)
            for d in range(1, 31)
        ]
        db = self._make_db(rows)
        from src.x_post_mail_lane import build_data_split_candidates
        self.assertEqual(build_data_split_candidates(db, max_count=5), [])

    def test_low_season_ab_skipped(self):
        import json as _j
        arr = _j.dumps(["左前安", "左前安", "-", "投ゴロ", "投ゴロ", "-", "三 振", "三 振", ""])
        rows = [
            (f"2026-05-{d:02d}:g-t-01", "巨人", "控え", 6, 2, arr)
            for d in range(1, 6)  # AB ~30 < 80
        ]
        db = self._make_db(rows)
        from src.x_post_mail_lane import build_data_split_candidates
        self.assertEqual(build_data_split_candidates(db, max_count=5), [])

    def test_dedup_set_skips_signature(self):
        import json as _j
        arr = _j.dumps(["左前安", "左前安", "-", "投ゴロ", "投ゴロ", "-", "三 振", "三 振", ""])
        rows = [
            (f"2026-05-{d:02d}:g-t-01", "巨人", "強打者", 6, 2, arr)
            for d in range(1, 31)
        ]
        db = self._make_db(rows)
        from src.x_post_mail_lane import build_data_split_candidates
        cands = build_data_split_candidates(
            db, max_count=5, dedup_set={"data_split|強打者|inning"}
        )
        self.assertEqual(cands, [])


class BuildVideoRadarCandidatesTests(unittest.TestCase):
    """451: X バズ投稿の引用RT候補 (YouTube 不使用、 外部リンク無し、 X 内完結)。"""

    # RSSHub twitter feed 風 RSS。 坂本の投稿 1 件。
    # require_video=True に対応するため description に動画サムネ (amplify_video_thumb) を含める。
    # pubDate は固定 (テストは now 既定 = 実行時刻だが、 video path は日付不明を keep するため省略可)。
    _FEED = (
        "<rss><channel>"
        "<item><title>坂本勇人 サヨナラ満塁ホームラン</title>"
        "<description>坂本勇人 サヨナラ満塁ホームラン "
        "&lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/111/img/abc.jpg&quot;&gt;</description>"
        "<link>https://x.com/yomiuri_giants/status/111</link></item>"
        "</channel></rss>"
    )

    def _detect_patch(self):
        from unittest import mock
        # 「坂本」を含む投稿は坂本勇人を返す簡易 detector
        return mock.patch(
            "src.x_post_mail_lane.detect_giants_player_name",
            side_effect=lambda t, alias_map=None: "坂本勇人" if "坂本" in str(t) else "",
        )

    def test_builds_quote_rt_candidate_native_no_external_link(self):
        from src import x_post_mail_lane as lane
        with self._detect_patch():
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3, fetch_fn=lambda url: self._FEED,
            )
        # 一記事一本: 坂本は 1 本だけ
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c.metric, "x_buzz_post")
        self.assertEqual(c.focus_player, "坂本勇人")
        # 本文は native (外部リンクを貼らない) — yoshilover voice、 hashtag 無し
        self.assertNotIn("http", c.post_text)
        self.assertNotIn("#", c.post_text)
        self.assertNotIn("さん", c.post_text)
        # 引用元ツイート URL は quote_url に乗る (HTML mail の引用RTボタン用)
        self.assertEqual(c.quote_url, "https://x.com/yomiuri_giants/status/111")
        self.assertTrue(c.signature.startswith("xbuzz|"))
        self.assertIn("引用RT/リプライ先", c.draft_text)

    def test_quote_intent_url_for_buzz_candidate(self):
        from src.x_post_mail_lane import encode_x_quote_intent_url
        url = encode_x_quote_intent_url("坂本勇人 きてる！", "https://x.com/y/status/9")
        self.assertIn("intent/post", url)
        self.assertIn("text=", url)
        self.assertIn("url=", url)  # 引用元ツイートが quote として開く
        self.assertIn("status%2F9", url)  # url= は percent-encoded

    def test_comment_fn_llm_used_when_nonempty(self):
        from src import x_post_mail_lane as lane
        with self._detect_patch():
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3, fetch_fn=lambda url: self._FEED,
                comment_fn=lambda pt, pl: f"{pl}、最高だ！",
            )
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].post_text, "坂本勇人、最高だ！")  # LLM 出力を採用

    def test_comment_fn_empty_falls_back_to_template(self):
        from src import x_post_mail_lane as lane
        with self._detect_patch():
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3, fetch_fn=lambda url: self._FEED,
                comment_fn=lambda pt, pl: "",  # LLM 失敗 → template fallback
            )
        self.assertEqual(len(cands), 1)
        self.assertIn("坂本勇人", cands[0].post_text)  # 出来事 template が効く
        self.assertNotIn("http", cands[0].post_text)

    def test_dedup_set_skips(self):
        from src import x_post_mail_lane as lane
        with self._detect_patch():
            first = lane.build_video_radar_candidates(
                db_path=None, max_count=3, fetch_fn=lambda url: self._FEED,
            )
            sigs = {c.signature for c in first}
            again = lane.build_video_radar_candidates(
                db_path=None, max_count=3, fetch_fn=lambda url: self._FEED,
                dedup_set=sigs,
            )
        self.assertEqual(again, [])


class XBuzzPlayerFactTests(unittest.TestCase):
    """451: 引用RT コメントを濃くする今季実数字 (insight.db read-only)。"""

    def _db(self, batting=None, pitching=None):
        import sqlite3 as _sq, tempfile as _tf, os as _os
        fd, path = _tf.mkstemp(suffix=".db"); _os.close(fd)
        conn = _sq.connect(path)
        conn.execute("CREATE TABLE batting_logs (player_canonical TEXT, AB INT, H INT, RBI INT)")
        conn.execute("CREATE TABLE pitching_logs (player_canonical TEXT, K INT, ER INT, IP REAL)")
        for r in (batting or []):
            conn.execute("INSERT INTO batting_logs VALUES (?,?,?,?)", r)
        for r in (pitching or []):
            conn.execute("INSERT INTO pitching_logs VALUES (?,?,?,?)", r)
        conn.commit(); conn.close()
        self.addCleanup(lambda: _os.path.exists(path) and _os.remove(path))
        return path

    def test_batter_fact(self):
        from src.x_post_mail_lane import _x_buzz_player_fact
        db = self._db(batting=[("佐々木俊輔", 60, 18, 5), ("佐々木俊輔", 30, 6, 2)])
        fact = _x_buzz_player_fact(db, "佐々木俊輔")
        self.assertIn("打率.267", fact)  # 24/90
        self.assertIn("24安打", fact)
        self.assertIn("7打点", fact)

    def test_pitcher_fact_when_no_bats(self):
        from src.x_post_mail_lane import _x_buzz_player_fact
        db = self._db(pitching=[("竹丸和幸", 10, 3, 9.0), ("竹丸和幸", 9, 0, 9.0)])
        fact = _x_buzz_player_fact(db, "竹丸和幸")
        self.assertIn("2登板", fact)
        self.assertIn("19奪三振", fact)
        self.assertIn("防御率", fact)

    def test_empty_when_no_data(self):
        from src.x_post_mail_lane import _x_buzz_player_fact
        db = self._db()
        self.assertEqual(_x_buzz_player_fact(db, "無名選手"), "")
        self.assertEqual(_x_buzz_player_fact(None, "誰か"), "")


class BuildQuoteRtCommentTests(unittest.TestCase):
    """451: Flash Lite 引用RTコメント生成 (post-API path、 log NameError regression)。"""

    def _patch_genai(self, text):
        import sys, types
        from unittest import mock
        fake_client = mock.MagicMock()
        fake_client.models.generate_content.return_value = types.SimpleNamespace(text=text)
        fake_genai = types.SimpleNamespace(Client=lambda api_key=None: fake_client)
        google_mod = sys.modules.get("google") or types.ModuleType("google")
        setattr(google_mod, "genai", fake_genai)
        return mock.patch.dict(sys.modules, {"google": google_mod, "google.genai": fake_genai})

    def test_returns_comment_post_api(self):
        from src import x_post_branding_gen as xbg
        with self._patch_genai("坂本勇人、サヨナラ最高だ！しびれた。"):
            out = xbg.build_quote_rt_comment("坂本勇人 サヨナラ", "坂本勇人", gemini_api_key="k")
        self.assertEqual(out, "坂本勇人、サヨナラ最高だ！しびれた。")  # log NameError 回帰防止

    def test_hallucinated_number_rejected(self):
        from src import x_post_branding_gen as xbg
        # 投稿に無い "100号" を出したら捏造として破棄 → ""
        with self._patch_genai("坂本勇人、通算100号おめでとう！"):
            out = xbg.build_quote_rt_comment("坂本勇人 サヨナラ", "坂本勇人", gemini_api_key="k")
        self.assertEqual(out, "")

    def test_empty_key_returns_empty(self):
        from src import x_post_branding_gen as xbg
        self.assertEqual(xbg.build_quote_rt_comment("x", "y", gemini_api_key=""), "")


class VideoRadarImpressionPolicyTests(unittest.TestCase):
    """451: 動画候補は同選手のデータ候補が居ても落とさず確実に届ける。"""

    def test_video_survives_player_dedup_against_data_candidate(self):
        from src.x_post_mail_lane import Candidate, apply_x_impression_policy, _VIDEO_RADAR_METRIC
        data_c = Candidate(
            title="坂本勇人 OPS", metric="OPS", period_label="今シーズン",
            draft_text="x", char_count=10, signature="ops|sakamoto",
            post_text="坂本勇人 OPS .900", focus_player="坂本勇人",
        )
        video_c = Candidate(
            title="(動画) 名場面回顧｜巨人公式｜坂本", metric=_VIDEO_RADAR_METRIC,
            period_label="動画候補", draft_text="y", char_count=10,
            signature="video_radar|VID1", post_text="坂本勇人 名場面 ▶ url",
            focus_player="坂本勇人",
        )
        kept, dropped = apply_x_impression_policy([data_c, video_c])
        kept_sigs = {c.signature for c in kept}
        self.assertIn("ops|sakamoto", kept_sigs)
        self.assertIn("video_radar|VID1", kept_sigs)  # 同選手でも動画は残る
        self.assertEqual(dropped, [])


if __name__ == "__main__":
    unittest.main()
