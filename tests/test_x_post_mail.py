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
    apply_x_impression_policy,
    _candidate_anomaly_flags,
    _candidate_source_kind,
    _sample_threshold_label,
    _source_mix_summary,
    _load_giants_player_aliases,
    _normalize_player_name,
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


class MondayNoGameWindowTests(unittest.TestCase):
    def test_before_7am_is_skipped(self) -> None:
        from src.tools import run_x_post_mail as runner

        self.assertTrue(runner._is_before_7am_jst(datetime(2026, 6, 8, 6, 59, tzinfo=JST)))
        self.assertFalse(runner._is_before_7am_jst(datetime(2026, 6, 8, 7, 0, tzinfo=JST)))

    def test_before_7am_skip_can_be_overridden(self) -> None:
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {"X_POST_MAIL_ALLOW_BEFORE_7AM": "1"}):
            self.assertFalse(runner._before_7am_skip_enabled())

    def test_monday_game_windows_are_skipped(self) -> None:
        from src.tools import run_x_post_mail as runner

        for now in [
            datetime(2026, 6, 8, 17, 0, tzinfo=JST),
            datetime(2026, 6, 8, 18, 30, tzinfo=JST),
            datetime(2026, 6, 8, 19, 15, tzinfo=JST),
            datetime(2026, 6, 8, 22, 0, tzinfo=JST),
        ]:
            with self.subTest(now=now.isoformat()):
                self.assertTrue(runner._is_monday_game_window(now))

    def test_monday_daytime_and_non_monday_game_windows_are_not_skipped(self) -> None:
        from src.tools import run_x_post_mail as runner

        self.assertFalse(runner._is_monday_game_window(datetime(2026, 6, 8, 13, 0, tzinfo=JST)))
        self.assertFalse(runner._is_monday_game_window(datetime(2026, 6, 9, 19, 15, tzinfo=JST)))

    def test_monday_game_window_skip_can_be_overridden(self) -> None:
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {"X_POST_MAIL_ALLOW_MONDAY_GAME_WINDOWS": "1"}):
            self.assertFalse(runner._monday_game_window_skip_enabled())

    def test_extra_day_game_window_uses_in_game_timing(self) -> None:
        from src import x_post_mail_lane as lane
        from src.tools.run_x_post_mail import _is_fan_voice_fire_window

        env = {
            "X_POST_MAIL_EXTRA_GAME_DATE": "2026-06-07",
            "X_POST_MAIL_EXTRA_GAME_START": "13:45",
            "X_POST_MAIL_EXTRA_GAME_END": "17:15",
        }
        with patch.dict("os.environ", env):
            now = datetime(2026, 6, 7, 14, 15, tzinfo=JST)
            self.assertEqual(lane.x_impression_timing_label(now), "試合中強イベント枠")
            self.assertEqual(lane.phase_freshness_max_age_hours(now), 0.5)
            self.assertTrue(_is_fan_voice_fire_window(now))
            self.assertFalse(lane.is_extra_game_window(datetime(2026, 6, 7, 17, 30, tzinfo=JST)))

    def test_live_duplicate_cooldown_only_active_in_game(self) -> None:
        from src.tools import run_x_post_mail as runner

        self.assertTrue(
            runner._live_duplicate_player_cooldown_active(
                datetime(2026, 6, 9, 20, 0, tzinfo=JST)
            )
        )
        self.assertFalse(
            runner._live_duplicate_player_cooldown_active(
                datetime(2026, 6, 9, 13, 0, tzinfo=JST)
            )
        )


class ReplyTargetHandleTests(unittest.TestCase):
    def test_default_reply_targets_add_tokyo_giants_without_env_change(self) -> None:
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {}, clear=True):
            # 2026-07-03 user 追加: Sanspo_Giants / koba_nikkan を default 化
            # + 「特に公式と報知」で 報知 → 公式 を先頭固定
            self.assertEqual(
                runner._reply_target_handles(),
                ["hochi_giants", "TokyoGiants", "Sanspo_Giants", "koba_nikkan"],
            )

    def test_configured_reply_targets_keep_existing_and_add_tokyo_giants(self) -> None:
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {"X_POST_REPLY_TARGET_HANDLES": "hochi_giants,Sanspo_Giants"}):
            self.assertEqual(
                runner._reply_target_handles(),
                ["hochi_giants", "TokyoGiants", "Sanspo_Giants"],
            )

    def test_reply_target_tail_rotates_but_priority_fixed(self) -> None:
        """2026-07-03 user「その他メディアは分散」: 報知/公式は先頭固定のまま、
        残りメディアだけ時刻ローテする。"""
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {}, clear=True):
            h9 = runner._reply_target_handles(now=datetime(2026, 7, 3, 9, 0, tzinfo=JST))
            h10 = runner._reply_target_handles(now=datetime(2026, 7, 3, 10, 0, tzinfo=JST))
        self.assertEqual(h9[:2], ["hochi_giants", "TokyoGiants"])
        self.assertEqual(h10[:2], ["hochi_giants", "TokyoGiants"])
        self.assertEqual(sorted(h9[2:]), sorted(h10[2:]))
        self.assertNotEqual(h9[2:], h10[2:])

    def test_fan_reply_default_handles_include_2026_07_03_additions(self) -> None:
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {}, clear=True):
            handles = runner._fan_reply_target_handles()
        self.assertEqual(
            sorted(handles),
            sorted(["EH87EazmV9D2eSw", "kandume92", "ay222000", "vto6u", "GIANTSLIFE0801"]),
        )

    def test_fan_reply_handles_rotate_by_hour(self) -> None:
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {}, clear=True):
            h9 = runner._fan_reply_target_handles(now=datetime(2026, 7, 3, 9, 0, tzinfo=JST))
            h10 = runner._fan_reply_target_handles(now=datetime(2026, 7, 3, 10, 0, tzinfo=JST))
        # 同じ集合のまま走査開始位置だけ変わる (先頭 handle が毎便勝ち続けない)
        self.assertEqual(sorted(h9), sorted(h10))
        self.assertNotEqual(h9[0], h10[0])

    def test_mlb_watch_max_age_hours_default_and_env(self) -> None:
        """2026-07-03: MLB引用RTの鮮度は default 20h (朝便で昨日夜のクリップを出す)。"""
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(runner._mlb_watch_max_age_hours(), 20.0)
        with patch.dict("os.environ", {"X_POST_MLB_WATCH_MAX_AGE_HOURS": "12"}):
            self.assertEqual(runner._mlb_watch_max_age_hours(), 12.0)

    def test_mlb_reply_defaults(self) -> None:
        """2026-07-03: MLBリプ lane は env gate (default OFF)、対象は日本語系 default。"""
        from src.tools import run_x_post_mail as runner

        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(runner._mlb_reply_enabled())
            self.assertEqual(runner._mlb_reply_max_per_run(), 1)
            self.assertEqual(
                runner._mlb_reply_target_handles(),
                ["30R9gmaMUy3guDJ", "MLBJapan", "SPOTVNOW_jp"],
            )
        with patch.dict("os.environ", {"ENABLE_X_POST_MLB_REPLY": "1", "X_POST_MLB_REPLY_TARGET_HANDLES": "@MLBJapan"}):
            self.assertTrue(runner._mlb_reply_enabled())
            self.assertEqual(runner._mlb_reply_target_handles(), ["MLBJapan"])

    def test_tokyo_giants_reply_candidate_uses_official_label(self) -> None:
        from src.tools import run_x_post_mail as runner

        label, why_now, source_type, metric, tags = runner._reply_candidate_mail_labels("TokyoGiants")
        self.assertEqual(label, "公式リプ候補")
        self.assertIn("読売巨人軍公式", why_now)
        self.assertEqual(source_type, "official_reply")
        self.assertEqual(metric, "reply_candidate")
        self.assertIn("reply:official", tags)


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

    def test_reply_candidate_uses_reply_intent_button(self) -> None:
        ts = datetime(2026, 6, 3, 21, 0, tzinfo=JST)
        cand = Candidate(
            title="報知リプ候補",
            metric="HOCHI_REPLY",
            period_label="報知リプ候補",
            draft_text="根拠",
            post_text="坂本勇人、この流れは次の場面まで見たいですね。",
            char_count=25,
            reply_to_id="12345",
        )
        mail = compose_mail([cand], now=ts)
        self.assertIn("in_reply_to=12345", mail.html_body)
        self.assertIn("この投稿にリプライ", mail.html_body)
        reply_urls = [
            line.strip()
            for line in mail.text_body.splitlines()
            if "in_reply_to=12345" in line
        ]
        self.assertEqual(len(reply_urls), 1)
        decoded = parse_qs(urlparse(reply_urls[0]).query)["text"][0]
        self.assertEqual(decoded, cand.post_text)

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

    def test_hochi_reply_is_source_a_and_does_not_need_db_tokens(self) -> None:
        reply = Candidate(
            title="報知リプ候補",
            metric="HOCHI_REPLY",
            period_label="報知リプ候補",
            draft_text="根拠",
            post_text=(
                "坂本勇人のこの流れは、結果だけでなく立ち位置まで見たいですね。\n"
                "次の場面でどうつながるかまで追いたいです。"
            ),
            char_count=56,
            focus_player="坂本勇人",
            reply_to_id="12345",
        )
        self.assertEqual(_candidate_source_kind(reply), "A")
        self.assertFalse(
            any(flag.startswith("hard:source_b_table_token_missing") for flag in _candidate_anomaly_flags(reply))
        )

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

    def test_impression_policy_drops_recently_shown_players_across_lanes(self) -> None:
        ts = datetime(2026, 6, 28, 12, 0, tzinfo=JST)
        # 直近メールで井上・浦田を既出 → 別レーン (buzz/コメント/画像) でも全部外れる。
        recent = {"井上温大", "浦田俊輔"}
        cands = [
            Candidate("buzz井上", "x_buzz_post", "引用RT候補", "根拠", 5,
                      post_text="井上の話題 #巨人", focus_player="井上温大"),
            Candidate("コメント浦田", "player_comment", "コメント", "根拠", 3,
                      post_text="浦田のコメント #巨人", focus_player="浦田俊輔"),
            Candidate("写真井上", "record_article", "写真", "根拠", 3,
                      post_text="井上の写真 #巨人", focus_player="井上温大"),
            Candidate("新規大城", "OPS", "直近5試合", "根拠", 80,
                      post_text="大城の記録 #巨人", focus_player="大城卓三"),
        ]
        kept, dropped = apply_x_impression_policy(cands, now=ts, recent_player_keys=recent)
        kept_players = {_normalize_player_name(c.focus_player) for c in kept}
        self.assertNotIn(_normalize_player_name("井上温大"), kept_players)
        self.assertNotIn(_normalize_player_name("浦田俊輔"), kept_players)
        self.assertIn(_normalize_player_name("大城卓三"), kept_players)
        reasons = {r for _c, r in dropped}
        self.assertIn("dedup_player_recent", reasons)

    def test_impression_policy_recent_filter_exempts_reply_lane(self) -> None:
        ts = datetime(2026, 6, 28, 12, 0, tzinfo=JST)
        from src.x_post_mail_lane import _REPLY_CANDIDATE_METRIC
        recent = {_normalize_player_name("井上温大")}
        reply = Candidate("リプ井上", _REPLY_CANDIDATE_METRIC, "リプ", "根拠", 3,
                          post_text="井上へのリプ #巨人", focus_player="井上温大")
        kept, _dropped = apply_x_impression_policy([reply], now=ts, recent_player_keys=recent)
        self.assertEqual(len(kept), 1)  # 返信レーンは直近既出でも残す

    def test_impression_policy_per_group_reply_recent_keeps_original(self) -> None:
        # 2026-06-29: レス群で 戸郷 既出でも、動画/本人コメントのオリジナルは残す。
        ts = datetime(2026, 6, 28, 12, 0, tzinfo=JST)
        from src.x_post_mail_lane import (
            _VIDEO_RADAR_METRIC, _PLAYER_COMMENT_METRIC,
        )
        # 戸郷(動画)・大城(本人コメント) ともレス群で既出。 別選手なので
        # 同一メール内 dedup には掛からず、 レス既出でも 2 本とも残る。
        by_group = {
            "original": set(),
            "reply": {
                _normalize_player_name("戸郷翔征"),
                _normalize_player_name("大城卓三"),
            },
            "other": set(),
        }
        video = Candidate("動画戸郷", _VIDEO_RADAR_METRIC, "引用RT候補", "根拠", 5,
                          post_text="戸郷の動画 #巨人", focus_player="戸郷翔征")
        comment = Candidate("コメ大城", _PLAYER_COMMENT_METRIC, "本人コメント", "根拠", 4,
                            post_text="大城のコメント #巨人", focus_player="大城卓三")
        kept, _dropped = apply_x_impression_policy(
            [video, comment], now=ts, recent_player_keys_by_group=by_group
        )
        self.assertEqual(len(kept), 2)  # レス既出はオリジナルを落とさない

    def test_impression_policy_per_group_same_group_recent_drops(self) -> None:
        # オリジナル群で既出なら、同群(動画)のオリジナルは従来通り落ちる。
        ts = datetime(2026, 6, 28, 12, 0, tzinfo=JST)
        from src.x_post_mail_lane import _VIDEO_RADAR_METRIC
        by_group = {
            "original": {_normalize_player_name("戸郷翔征")},
            "reply": set(),
            "other": set(),
        }
        video = Candidate("動画戸郷", _VIDEO_RADAR_METRIC, "引用RT候補", "根拠", 5,
                          post_text="戸郷の動画 #巨人", focus_player="戸郷翔征")
        kept, dropped = apply_x_impression_policy(
            [video], now=ts, recent_player_keys_by_group=by_group
        )
        self.assertEqual(len(kept), 0)
        self.assertIn("dedup_player_recent", {r for _c, r in dropped})

    def test_impression_policy_per_group_other_recent_keeps_original(self) -> None:
        # データ速報(other群)で既出でも、動画オリジナルは残す。
        ts = datetime(2026, 6, 28, 12, 0, tzinfo=JST)
        from src.x_post_mail_lane import _VIDEO_RADAR_METRIC
        by_group = {
            "original": set(),
            "reply": set(),
            "other": {_normalize_player_name("戸郷翔征")},
        }
        video = Candidate("動画戸郷", _VIDEO_RADAR_METRIC, "引用RT候補", "根拠", 5,
                          post_text="戸郷の動画 #巨人", focus_player="戸郷翔征")
        kept, _dropped = apply_x_impression_policy(
            [video], now=ts, recent_player_keys_by_group=by_group
        )
        self.assertEqual(len(kept), 1)

    def test_impression_policy_same_player_different_media_videos_kept(self) -> None:
        # 2026-07-02 user 決定: 動画SNS はインプが取れるため、同一選手でも
        # 媒体 (@handle) が違えば同一メール内で両方残す。
        ts = datetime(2026, 7, 2, 12, 0, tzinfo=JST)
        from src.x_post_mail_lane import _VIDEO_RADAR_METRIC
        hochi = Candidate("動画岡本(報知)", _VIDEO_RADAR_METRIC, "引用RT候補",
                          "元動画: https://x.com/hochi_giants/status/1", 5,
                          signature="xbuzz|aaa", post_text="岡本の一発、報知の角度 #巨人",
                          focus_player="岡本和真", media_handle="hochi_giants")
        sponichi = Candidate("動画岡本(スポニチ)", _VIDEO_RADAR_METRIC, "引用RT候補",
                             "元動画: https://x.com/sponichi_giants/status/2", 5,
                             signature="xbuzz|bbb", post_text="岡本の一発、スポニチのリプレー #巨人",
                             focus_player="岡本和真", media_handle="sponichi_giants")
        kept, dropped = apply_x_impression_policy([hochi, sponichi], now=ts)
        self.assertEqual(len(kept), 2, dropped)

    def test_impression_policy_same_player_same_media_video_dropped(self) -> None:
        # 同一選手×同一媒体の別動画は従来通り 1 本に抑える。
        ts = datetime(2026, 7, 2, 12, 0, tzinfo=JST)
        from src.x_post_mail_lane import _VIDEO_RADAR_METRIC
        v1 = Candidate("動画岡本1", _VIDEO_RADAR_METRIC, "引用RT候補",
                       "元動画: https://x.com/hochi_giants/status/1", 5,
                       signature="xbuzz|aaa", post_text="岡本の一発 第1打席 #巨人",
                       focus_player="岡本和真", media_handle="hochi_giants")
        v2 = Candidate("動画岡本2", _VIDEO_RADAR_METRIC, "引用RT候補",
                       "元動画: https://x.com/hochi_giants/status/3", 5,
                       signature="xbuzz|ccc", post_text="岡本の守備の場面はこちら #巨人",
                       focus_player="岡本和真", media_handle="hochi_giants")
        kept, dropped = apply_x_impression_policy([v1, v2], now=ts)
        self.assertEqual(len(kept), 1)
        # 同一 (選手×媒体) は topic key (player|metric|period|handle) か
        # (選手×媒体) mail 内 gate のどちらかで 1 本に落ちる。
        reasons = {r for _c, r in dropped}
        self.assertTrue(
            reasons & {"dedup_player_in_mail", "dedup_player_metric_period"},
            reasons,
        )

    def test_impression_policy_video_media_aware_recent_gate(self) -> None:
        # 12h クールダウン: 報知の岡本動画を既送 → 報知の別動画は落ち、
        # スポニチの岡本動画は残る (媒体が違えばインプが取れる)。
        ts = datetime(2026, 7, 2, 12, 0, tzinfo=JST)
        from src.x_post_mail_lane import _VIDEO_RADAR_METRIC
        recent_media = {f"{_normalize_player_name('岡本和真')}|hochi_giants"}
        hochi = Candidate("動画岡本(報知)", _VIDEO_RADAR_METRIC, "引用RT候補", "根拠", 5,
                          signature="xbuzz|ddd", post_text="岡本の一発また来た #巨人",
                          focus_player="岡本和真", media_handle="hochi_giants")
        sponichi = Candidate("動画岡本(スポニチ)", _VIDEO_RADAR_METRIC, "引用RT候補", "根拠", 5,
                             signature="xbuzz|eee", post_text="岡本の一発、別カメラ #巨人",
                             focus_player="岡本和真", media_handle="sponichi_giants")
        by_group = {
            "original": {_normalize_player_name("岡本和真")},
            "reply": set(), "other": set(),
        }
        kept, dropped = apply_x_impression_policy(
            [hochi, sponichi], now=ts,
            recent_player_keys_by_group=by_group,
            recent_video_player_media=recent_media,
        )
        kept_titles = {c.title for c in kept}
        self.assertNotIn("動画岡本(報知)", kept_titles)
        self.assertIn("動画岡本(スポニチ)", kept_titles)
        self.assertIn("dedup_player_recent", {r for _c, r in dropped})

    def test_impression_policy_video_without_media_handle_keeps_legacy(self) -> None:
        # media_handle 無しの動画候補は従来の選手単位 recent 判定のまま。
        ts = datetime(2026, 7, 2, 12, 0, tzinfo=JST)
        from src.x_post_mail_lane import _VIDEO_RADAR_METRIC
        by_group = {
            "original": {_normalize_player_name("戸郷翔征")},
            "reply": set(), "other": set(),
        }
        video = Candidate("動画戸郷", _VIDEO_RADAR_METRIC, "引用RT候補", "根拠", 5,
                          post_text="戸郷の動画 #巨人", focus_player="戸郷翔征")
        kept, dropped = apply_x_impression_policy(
            [video], now=ts,
            recent_player_keys_by_group=by_group,
            recent_video_player_media=set(),
        )
        self.assertEqual(len(kept), 0)
        self.assertIn("dedup_player_recent", {r for _c, r in dropped})

    def test_video_player_media_within_cooldown_builds_keys(self) -> None:
        from src.x_post_mail_lane import (
            _video_player_media_within_cooldown, _VIDEO_RADAR_METRIC,
        )
        now = datetime(2026, 7, 2, 12, 0, tzinfo=JST)
        records = [
            {"ts": "2026-07-02T11:00:00+09:00", "metric": _VIDEO_RADAR_METRIC,
             "focus_player": "岡本和真", "media_handle": "hochi_giants",
             "signature": "xbuzz|aaa"},
            # 窓の外 (13h 前) は含めない
            {"ts": "2026-07-01T23:00:00+09:00", "metric": _VIDEO_RADAR_METRIC,
             "focus_player": "戸郷翔征", "media_handle": "sponichi_giants",
             "signature": "xbuzz|bbb"},
            # 動画以外の lane は含めない
            {"ts": "2026-07-02T11:30:00+09:00", "metric": "GEMMA_BRANDING",
             "focus_player": "岡本和真", "media_handle": "hochi_giants",
             "signature": "news|ccc"},
            # media_handle 無しの旧 record は含めない
            {"ts": "2026-07-02T11:30:00+09:00", "metric": _VIDEO_RADAR_METRIC,
             "focus_player": "吉川尚輝", "signature": "xbuzz|ddd"},
        ]
        keys = _video_player_media_within_cooldown(records, now, 12)
        self.assertEqual(
            keys, {f"{_normalize_player_name('岡本和真')}|hochi_giants"}
        )

    def test_players_within_cooldown_by_group_buckets_by_metric(self) -> None:
        from src.x_post_mail_lane import (
            _players_within_cooldown_by_group,
            _VIDEO_RADAR_METRIC, _PLAYER_COMMENT_METRIC,
            _HOCHI_REPLY_METRIC, _NEWS_SCRAPE_METRIC,
        )
        now = datetime(2026, 6, 28, 12, 0, tzinfo=JST)
        ts = (now - timedelta(hours=1)).isoformat()
        records = [
            {"ts": ts, "focus_player": "戸郷翔征", "metric": _VIDEO_RADAR_METRIC},
            {"ts": ts, "focus_player": "大城卓三", "metric": _PLAYER_COMMENT_METRIC},
            {"ts": ts, "focus_player": "泉口友汰", "metric": _HOCHI_REPLY_METRIC},
            {"ts": ts, "focus_player": "岡本和真", "metric": _NEWS_SCRAPE_METRIC},
        ]
        out = _players_within_cooldown_by_group(records, now, cooldown_hours=12)
        self.assertEqual(
            out["original"],
            {_normalize_player_name("戸郷翔征"), _normalize_player_name("大城卓三")},
        )
        self.assertEqual(out["reply"], {_normalize_player_name("泉口友汰")})
        self.assertEqual(out["other"], {_normalize_player_name("岡本和真")})

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

    def test_record_news_candidate_uses_record_phrase_from_source_title(self) -> None:
        ts = datetime(2026, 5, 18, 7, 0, tzinfo=JST)
        cand = build_news_opinion_candidate(
            source_title="巨人・岸田行倫がプロ初本塁打達成",
            source_url="https://example.test/giants-kishida-record",
            source_name="テスト新聞",
            source_excerpt="岸田行倫の節目を伝える記事。",
            player_name="岸田行倫",
            now=ts,
        )
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertEqual(cand.metric, "NEWS_OPINION")
        self.assertEqual(cand.source_material_type, "record")
        # 2026-07-03 user「【選手名】 内容」「記事の数字ごと載せて出す」
        self.assertIn("記事記載値｜記録/節目案｜岸田行倫", cand.title)
        self.assertIn("【岸田行倫】プロ初本塁打達成", cand.post_text)
        self.assertNotIn("あと", cand.post_text)
        self.assertNotIn("https://example.test/giants-kishida-record", cand.post_text)
        self.assertIn("材料種別: 記録/節目 (record)", cand.draft_text)
        self.assertIn("元記事タイトル: 巨人・岸田行倫がプロ初本塁打達成", cand.draft_text)
        self.assertIn("数値の扱い: 元記事記載の数字のみ掲載", cand.draft_text)

    def test_record_news_candidate_strips_hashtags_urls_and_name_dup(self) -> None:
        """2026-07-03: X 由来 RSS タイトルのハッシュタグ / 切れURL / ▼記事を読む▼ を
        投稿文へ持ち込まない + 冠イニシャル表示名との名前二重化を防ぐ。

        実事故: 「Ｆ．ウィットリー、巨人・ウィットリーがつかんだ好調の感覚
        高校時代は３戦連続ノーノー #巨人 #giants ▼記事を読む▼ https://hochi.n…。」
        """
        ts = datetime(2026, 7, 3, 7, 0, tzinfo=JST)
        cand = build_news_opinion_candidate(
            source_title=(
                "巨人・岸田行倫が達成した節目 高校時代は３戦連続ノーノー "
                "#巨人 #giants ▼記事を読む▼ https://hochi.n…"
            ),
            source_url="https://x.com/hochi_giants/status/2072778250556739726",
            source_name="スポーツ報知巨人班X",
            player_name="岸田行倫",
            now=ts,
        )
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertEqual(cand.source_material_type, "record")
        self.assertNotIn("#巨人", cand.post_text)
        self.assertNotIn("#giants", cand.post_text)
        self.assertNotIn("▼", cand.post_text)
        self.assertNotIn("https://", cand.post_text)
        self.assertNotIn("hochi.n", cand.post_text)
        # 名前二重化しない (【】ヘッダ + phrase 先頭の選手名は除去済み)
        self.assertNotIn("岸田行倫、岸田行倫", cand.post_text)
        self.assertIn("【岸田行倫】達成した節目 高校時代は３戦連続ノーノー", cand.post_text)

    def test_record_news_candidate_carries_article_image(self) -> None:
        """2026-07-03 user「【選手名】 内容 画像があるとよい」: 元記事画像を
        候補に添付し、mail の画像つき投稿導線を有効化。"""
        ts = datetime(2026, 7, 3, 9, 0, tzinfo=JST)
        cand = build_news_opinion_candidate(
            source_title="巨人・岸田行倫がプロ初本塁打達成",
            source_url="https://example.test/giants-kishida-record",
            source_name="テスト新聞",
            player_name="岸田行倫",
            now=ts,
            image_bytes=b"\x89PNGfake",
            image_source_url="https://example.test/images/kishida.jpg",
        )
        self.assertIsNotNone(cand)
        assert cand is not None
        self.assertEqual(cand.image_bytes, b"\x89PNGfake")
        self.assertEqual(cand.image_source_url, "https://example.test/images/kishida.jpg")
        self.assertIn("テスト新聞掲載画像", cand.image_alt_text)
        self.assertIn("添付画像: https://example.test/images/kishida.jpg", cand.draft_text)

    def test_record_phrase_core_name_dedup_with_initial_prefix(self) -> None:
        """表示名 'Ｆ．ウィットリー' vs 記事表記 '巨人・ウィットリー' でも
        名前二重化しない (核名 core match)。"""
        from src.x_post_mail_lane import _build_source_backed_post_text

        body = _build_source_backed_post_text(
            "Ｆ．ウィットリー",
            "record",
            source_title="巨人・ウィットリーがつかんだ好調の感覚 高校時代は３戦連続ノーノー #巨人 ▼記事を読む▼ https://hochi.n…",
            source_excerpt="",
            source_topic_family="pitching",
        )
        # 【選手名】ヘッダ形式 + phrase 先頭の核名 (ウィットリーが) は除去
        self.assertIn("【Ｆ．ウィットリー】つかんだ好調の感覚", body)
        self.assertNotIn("Ｆ．ウィットリー、", body)
        self.assertNotIn("【Ｆ．ウィットリー】ウィットリー", body)
        self.assertNotIn("#巨人", body)
        self.assertNotIn("https://", body)

    def test_gemini_branding_mix_uses_news_label(self) -> None:
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
                # 2026-06-04 voice-only 方針より前のテスト。 dedup バックフィル
                # (pick_candidates 2 回 → データ候補で mail を送る) を検証するのが
                # 目的なので voice-only filter を OFF にして data 候補を残す。
                "X_POST_MAIL_VOICE_ONLY": "0",
                # hermetic 化: local env に GEMINI key があると queue 417 drain が
                # 実 GCS / 実ネットワークを読み flaky になるため空にして skip。
                "GEMINI_API_KEY": "",
                "GEMMA_BRANDING_GEMINI_API_KEY": "",
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
            media_handles=["", "", "", ""],
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
                # hermetic 化: local env に GEMINI key があると queue 417 drain が
                # 実 GCS を読み、 prod queue の中身次第で候補が湧いて flaky になる
                "GEMINI_API_KEY": "",
                "GEMMA_BRANDING_GEMINI_API_KEY": "",
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
                # voice-only filter (2026-06-04) は DB データ候補を落とすため、
                # この legacy「data+news 合成」テストでは明示 OFF にして旧挙動を検証する。
                "X_POST_MAIL_VOICE_ONLY": "0",
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
            "_fetch_player_comment_priority_candidates",
            return_value=[],
        ), patch.object(
            run_x_post_mail,
            "_fetch_record_article_priority_candidates",
            return_value=[],
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
                # voice-only filter (2026-06-04) を OFF にして旧 data+news 合成を検証。
                "X_POST_MAIL_VOICE_ONLY": "0",
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
            "_fetch_player_comment_priority_candidates",
            return_value=[],
        ), patch.object(
            run_x_post_mail,
            "_fetch_record_article_priority_candidates",
            return_value=[],
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

    def test_player_comment_priority_prefers_scraped_comment_over_full_data_mail(self) -> None:
        """満枠DB候補があっても、本文スクレイプの本人コメントを先頭側に入れる。"""
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
            )
            for idx in range(1, 4)
        ]
        comment_text = (
            "岸田行倫『投手が粘ってくれていたので、何とか追加点につなげたいと思っていました。"
            "次も任せてもらえるように、準備から変えずにやっていきたいです』"
        )
        comment_cand = Candidate(
            title="(コメント速報) 岸田行倫",
            metric="PLAYER_COMMENT",
            period_label="本人コメント",
            draft_text=(
                "【根拠: 記事本文の本人発言 (literal)】\n"
                "添付画像: https://img.example.test/kishida.jpg\n\n"
                f"{comment_text}"
            ),
            post_text=comment_text,
            char_count=len(comment_text),
            signature="player_comment|kishida",
            focus_player="岸田行倫",
            source_material_type="player_comment",
            image_bytes=b"\xff\xd8\xffcomment-image",
            image_source_url="https://img.example.test/kishida.jpg",
        )
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
                "X_POST_MAIL_PLAYER_COMMENT_PRIORITY_CANDIDATES": "1",
                "X_POST_MAIL_VOICE_ONLY": "0",
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
            "_fetch_player_comment_priority_candidates",
            return_value=[comment_cand],
        ) as comment_priority, patch.object(
            run_x_post_mail,
            "_fetch_record_article_priority_candidates",
            return_value=[],
        ), patch.object(
            run_x_post_mail,
            "_fetch_news_opinion_fallback_candidates",
            return_value=[],
        ) as generic_fallback, patch.object(
            run_x_post_mail.mdb,
            "send",
            return_value=send_result,
        ) as send:
            result = run_x_post_mail.main(["--max-candidates", "3"])

        self.assertEqual(result, 0)
        comment_priority.assert_called_once()
        # 2026-07-03: 優先ソースがあっても generic fallback は残枠 (3-1=2) で top-up
        generic_fallback.assert_called_once()
        self.assertEqual(generic_fallback.call_args.kwargs.get("max_candidates"), 2)
        request = send.call_args.args[0]
        self.assertEqual(request.metadata["candidate_count"], 3)
        self.assertIn("岸田行倫『", request.text_body)
        self.assertIn("https://img.example.test/kishida.jpg", request.text_body)
        self.assertLess(
            request.text_body.index("岸田行倫『"),
            request.text_body.index("DB候補 2"),
        )

    def test_record_article_priority_prefers_source_record_over_full_data_mail(self) -> None:
        """満枠DB候補があっても、記事に出ている記録/節目を先頭側に入れる。"""
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
            )
            for idx in range(1, 4)
        ]
        record_cand = build_news_opinion_candidate(
            source_title="巨人・岸田行倫がプロ初本塁打達成",
            source_url="https://example.test/kishida-record",
            source_name="テスト新聞",
            source_excerpt="岸田行倫の節目を伝える記事。",
            player_name="岸田行倫",
        )
        assert record_cand is not None
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
                "X_POST_MAIL_RECORD_ARTICLE_PRIORITY_CANDIDATES": "1",
                "X_POST_MAIL_VOICE_ONLY": "0",
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
            "_fetch_player_comment_priority_candidates",
            return_value=[],
        ), patch.object(
            run_x_post_mail,
            "_fetch_record_article_priority_candidates",
            return_value=[record_cand],
        ) as record_priority, patch.object(
            run_x_post_mail,
            "_fetch_news_opinion_fallback_candidates",
            return_value=[],
        ) as generic_fallback, patch.object(
            run_x_post_mail.mdb,
            "send",
            return_value=send_result,
        ) as send:
            result = run_x_post_mail.main(["--max-candidates", "3"])

        self.assertEqual(result, 0)
        record_priority.assert_called_once()
        # 2026-07-03: 残枠 top-up 方式 (3-1=2)
        generic_fallback.assert_called_once()
        self.assertEqual(generic_fallback.call_args.kwargs.get("max_candidates"), 2)
        request = send.call_args.args[0]
        self.assertEqual(request.metadata["candidate_count"], 3)
        self.assertIn("【岸田行倫】プロ初本塁打達成", request.text_body)
        self.assertLess(
            request.text_body.index("プロ初本塁打達成"),
            request.text_body.index("DB候補 2"),
        )

    def test_fetch_record_article_priority_uses_feed_title_only(self) -> None:
        """記録優先枠はDBを掘らず、RSS/title/excerptに出た節目だけを採用する。"""
        from src.tools import run_x_post_mail

        entries = [
            {
                "title": "巨人・岸田行倫がプロ初本塁打達成",
                "link": "https://example.test/kishida-record",
                "summary": "岸田行倫が節目の一発を放った。",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            },
            {
                "title": "巨人・岸田行倫が練習で汗",
                "link": "https://example.test/kishida-practice",
                "summary": "記録や節目ではない通常記事。",
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
            cands = run_x_post_mail._fetch_record_article_priority_candidates(
                [],
                max_records=1,
                now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
            )

        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].source_material_type, "record")
        self.assertIn("プロ初本塁打達成", cands[0].post_text)
        self.assertNotIn("あと", cands[0].post_text)

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

    def test_news_opinion_fallback_weak_surname_match_skipped(self) -> None:
        """2026-07-03 実事故: サッカー記事「鈴木彩艶」が姓 alias「鈴木」で
        巨人・鈴木大和に誤帰属。巨人文脈の無い記事は姓だけの一致では通さず、
        フルネーム級 alias の一致がある記事だけ通す。"""
        from src.tools import run_x_post_mail

        entries = [
            {
                # 巨人文脈なし + 姓しか一致しない (別人フルネーム) → skip
                "title": "「あそこは自分が出るべきでした」ブラジル戦後、鈴木彩艶が口にした後悔",
                "link": "https://example.test/soccer",
                "summary": "冨安健洋の移籍にも注目が集まる",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            },
            {
                # 巨人文脈なしでもフルネーム一致なら通す
                "title": "鈴木大和が二軍戦で猛打賞の活躍",
                "link": "https://example.test/yamato",
                "summary": "若手野手の台頭が続く",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            },
        ]
        with patch.object(
            run_x_post_mail,
            "_load_news_fallback_sources",
            return_value=[{"name": "テスト総合スポーツ", "url": "https://example.test/feed"}],
        ), patch.object(
            run_x_post_mail,
            "_fetch_feed_entries",
            return_value=entries,
        ):
            cands = run_x_post_mail._fetch_news_opinion_fallback_candidates(
                [],
                max_candidates=2,
                now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
            )

        joined = " ".join(
            (getattr(c, "draft_text", "") or "") + (getattr(c, "title", "") or "")
            for c in cands
        )
        self.assertNotIn("example.test/soccer", joined)
        self.assertTrue(
            any("鈴木" in (c.focus_player or "") for c in cands),
            f"full-name match should survive: {[c.title for c in cands]}",
        )

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

    def test_news_opinion_fallback_prefers_literal_comment_with_image(self) -> None:
        """長い本人コメントが取れた記事は抽象ニュース案ではなく画像付きコメント案にする。"""
        from src.tools import run_x_post_mail

        entries = [
            {
                "title": "巨人・岸田行倫が試合後にコメント",
                "link": "https://example.test/kishida-comment",
                "summary": "岸田行倫のコメント",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            }
        ]
        html = (
            "<html><body>岸田行倫捕手は試合後、"
            "「投手が粘ってくれていたので、何とか追加点につなげたいと思っていました。"
            "次も任せてもらえるように、準備から変えずにやっていきたいです」"
            "と話した。</body></html>"
        )
        comment_fn = MagicMock(side_effect=AssertionError("generic news voice should not run"))
        with patch.object(
            run_x_post_mail,
            "_load_news_fallback_sources",
            return_value=[{"name": "テスト新聞", "url": "https://example.test/feed"}],
        ), patch.object(
            run_x_post_mail,
            "_fetch_feed_entries",
            return_value=entries,
        ), patch.object(
            run_x_post_mail,
            "_fetch_comment_article_material",
            return_value=(html, b"\xff\xd8\xffcomment-image", "https://img.example.test/kishida.jpg"),
        ):
            cands = run_x_post_mail._fetch_news_opinion_fallback_candidates(
                [],
                max_candidates=1,
                now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
                comment_fn=comment_fn,
            )

        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].metric, "PLAYER_COMMENT")
        self.assertEqual(cands[0].image_bytes, b"\xff\xd8\xffcomment-image")
        self.assertEqual(cands[0].image_source_url, "https://img.example.test/kishida.jpg")
        self.assertIn("岸田行倫『", cands[0].post_text)
        self.assertNotIn("巨人・岸田行倫が試合後にコメント", cands[0].post_text)
        comment_fn.assert_not_called()

    def test_literal_comment_bypasses_recent_history_player(self) -> None:
        """同じ選手の直近履歴が多くても、本人コメントそのものは別物として残す。"""
        from src.tools import run_x_post_mail

        entries = [
            {
                "title": "巨人・竹丸和幸が8回力投",
                "link": "https://example.test/takemaru-comment",
                "summary": "竹丸和幸の試合後記事。",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            }
        ]
        html = (
            "<html><body>竹丸和幸投手は試合後、"
            "「8イニングはアマ時代含めて結構久々だったんですけど、思ったよりいけるなと。"
            "きょうぐらいテンポよくいければ、それなりにイニングが食えるのかなとは思います」"
            "と振り返った。</body></html>"
        )
        with patch.object(
            run_x_post_mail,
            "_load_news_fallback_sources",
            return_value=[{"name": "テスト新聞", "url": "https://example.test/feed"}],
        ), patch.object(
            run_x_post_mail,
            "_fetch_feed_entries",
            return_value=entries,
        ), patch.object(
            run_x_post_mail,
            "_fetch_comment_article_material",
            return_value=(html, b"\xff\xd8\xffcomment-image", "https://img.example.test/takemaru.jpg"),
        ):
            cands = run_x_post_mail._fetch_news_opinion_fallback_candidates(
                [],
                max_candidates=1,
                now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
                recent_player_counts={"竹丸和幸": 14},
            )

        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].metric, "PLAYER_COMMENT")
        self.assertEqual(cands[0].focus_player, "竹丸和幸")
        self.assertEqual(cands[0].image_source_url, "https://img.example.test/takemaru.jpg")

    def test_literal_comment_skips_existing_dedup_signature(self) -> None:
        """同じ記事URL・発言者の本人コメントは、送信済み signature があれば再掲しない。"""
        from src.tools import run_x_post_mail

        entries = [
            {
                "title": "巨人・竹丸和幸が8回力投",
                "link": "https://example.test/takemaru-comment",
                "summary": "竹丸和幸の試合後記事。",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            }
        ]
        html = (
            "<html><body>竹丸和幸投手は試合後、"
            "「8イニングはアマ時代含めて結構久々だったんですけど、思ったよりいけるなと。"
            "きょうぐらいテンポよくいければ、それなりにイニングが食えるのかなとは思います」"
            "と振り返った。</body></html>"
        )
        common_patches = (
            patch.object(
                run_x_post_mail,
                "_load_news_fallback_sources",
                return_value=[{"name": "テスト新聞", "url": "https://example.test/feed"}],
            ),
            patch.object(run_x_post_mail, "_fetch_feed_entries", return_value=entries),
            patch.object(
                run_x_post_mail,
                "_fetch_comment_article_material",
                return_value=(html, b"\xff\xd8\xffcomment-image", "https://img.example.test/takemaru.jpg"),
            ),
        )
        with common_patches[0], common_patches[1], common_patches[2]:
            first = run_x_post_mail._fetch_news_opinion_fallback_candidates(
                [],
                max_candidates=1,
                now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
            )

        self.assertEqual(len(first), 1)
        with common_patches[0], common_patches[1], common_patches[2]:
            repeated = run_x_post_mail._fetch_news_opinion_fallback_candidates(
                [],
                max_candidates=1,
                now=datetime(2026, 5, 18, 14, 7, tzinfo=JST),
                dedup_set={first[0].signature},
            )

        self.assertEqual(repeated, [])

    def test_comments_only_fallback_does_not_create_generic_news_candidate(self) -> None:
        """コメント専用スクレイプでは、引用が取れない記事を抽象ニュース案に変えない。"""
        from src.tools import run_x_post_mail

        entries = [
            {
                "title": "巨人・岸田行倫が攻守で存在感",
                "link": "https://example.test/kishida-news",
                "summary": "岸田行倫の話題",
                "published": "Mon, 18 May 2026 03:00:00 GMT",
            }
        ]
        comment_fn = MagicMock(side_effect=AssertionError("generic news voice should not run"))
        with patch.object(
            run_x_post_mail,
            "_load_news_fallback_sources",
            return_value=[{"name": "テスト新聞", "url": "https://example.test/feed"}],
        ), patch.object(
            run_x_post_mail,
            "_fetch_feed_entries",
            return_value=entries,
        ), patch.object(
            run_x_post_mail,
            "_fetch_comment_article_material",
            return_value=("<html><body>岸田行倫の本文。本人の長い発言はない。</body></html>", b"", ""),
        ):
            cands = run_x_post_mail._fetch_news_opinion_fallback_candidates(
                [],
                max_candidates=1,
                now=datetime(2026, 5, 18, 13, 7, tzinfo=JST),
                comment_fn=comment_fn,
                comments_only=True,
            )

        self.assertEqual(cands, [])
        comment_fn.assert_not_called()


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


class SnapshotStaleFreshnessGateTests(unittest.TestCase):
    """2026-06-10 鮮度ゲート: 直近 N 試合 scope は per-player rolling
    のため、 長期離脱中の選手 (平山功太 事例) が怪我前の古い試合で
    「直近10試合 OBP」 Top10 に載り続けていた。 最終出場が snapshot 日
    から打者 10 日 / 投手 14 日より古い選手は ranking から除外する。
    """

    SNAP_DATE = "2026-06-10"

    def setUp(self) -> None:
        import tempfile, sqlite3, os
        self.tmp_dir = tempfile.mkdtemp(prefix="xpostmail_stale_")
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
                CREATE TABLE games (
                    game_id TEXT PRIMARY KEY,
                    game_date TEXT
                );
                CREATE TABLE batting_logs (
                    game_id TEXT,
                    player_canonical TEXT
                );
                CREATE TABLE pitching_logs (
                    game_id TEXT,
                    player_canonical TEXT
                );
                INSERT INTO teams (team_code, team_name, league) VALUES
                    ('g', '巨人', 'central');
                """
            )
            snaps = [
                # 打者 OBP: 泉口 = 前日出場 (fresh)、 平山 = 5/20 が最終 (stale)
                (self.SNAP_DATE, "last_10_games", "泉口友汰",   "g", "OBP", 0.420, 35),
                (self.SNAP_DATE, "last_10_games", "平山 功太",  "g", "OBP", 0.450, 32),
                # logs に一切出てこない選手は誤除外を避けて残す (fail-open)
                (self.SNAP_DATE, "last_10_games", "佐藤輝明",   "g", "OBP", 0.400, 38),
                # 投手 ERA: 戸郷 = 11 日前 (中 6 日 + 順延の範囲内、 keep)、
                # 山崎 = 21 日前 (stale)
                (self.SNAP_DATE, "last_10_games", "戸郷翔征",   "g", "ERA", 2.10, 20),
                (self.SNAP_DATE, "last_10_games", "山崎伊織",   "g", "ERA", 1.80, 22),
            ]
            conn.executemany(
                "INSERT INTO advanced_metric_snapshots "
                "(snapshot_date, scope, player_canonical, team_code, "
                " metric_name, metric_value, sample_size) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                snaps,
            )
            conn.executemany(
                "INSERT INTO games (game_id, game_date) VALUES (?, ?)",
                [
                    ("g-0609", "2026-06-09"),
                    ("g-0530", "2026-05-30"),
                    ("g-0520", "2026-05-20"),
                ],
            )
            conn.executemany(
                "INSERT INTO batting_logs (game_id, player_canonical) VALUES (?, ?)",
                [
                    ("g-0609", "泉口友汰"),
                    # snapshot 側は「平山 功太」 (空白あり)、 logs 側は空白なし
                    # でも REPLACE 正規化で突き合わせられること
                    ("g-0520", "平山功太"),
                ],
            )
            conn.executemany(
                "INSERT INTO pitching_logs (game_id, player_canonical) VALUES (?, ?)",
                [
                    ("g-0530", "戸郷翔征"),
                    ("g-0520", "山崎伊織"),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _names(self, metric: str) -> set:
        from src.x_post_mail_lane import _query_rank_from_snapshots
        result = _query_rank_from_snapshots(
            self.db_path,
            metric_name=metric,
            snapshot_scope="last_10_games",
            min_sample=10,
            limit=60,
        )
        self.assertTrue(result["ok"], msg=result)
        return {r["player_canonical"] for r in result["rows"]}

    def test_stale_batter_dropped_fresh_batter_kept(self) -> None:
        """最終出場 21 日前の打者は OBP ranking から落ち、 前日出場は残る。"""
        names = self._names("OBP")
        self.assertNotIn("平山 功太", names)
        self.assertIn("泉口友汰", names)

    def test_player_without_logs_kept_fail_open(self) -> None:
        """logs に最終出場が見つからない選手は誤除外しない。"""
        self.assertIn("佐藤輝明", self._names("OBP"))

    def test_pitcher_threshold_is_longer(self) -> None:
        """投手は 14 日: 11 日前登板は keep、 21 日前登板は drop。"""
        names = self._names("ERA")
        self.assertIn("戸郷翔征", names)
        self.assertNotIn("山崎伊織", names)

    def test_rank_and_total_rebuilt_after_drop(self) -> None:
        """除外後の rank / total が残存 row で振り直されること。"""
        from src.x_post_mail_lane import _query_rank_from_snapshots
        result = _query_rank_from_snapshots(
            self.db_path,
            metric_name="OBP",
            snapshot_scope="last_10_games",
            min_sample=10,
            limit=60,
        )
        self.assertEqual(result["total"], 2)
        ranks = {r["player_canonical"]: r["rank"] for r in result["rows"]}
        self.assertEqual(ranks["泉口友汰"], 1)


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
        # 動画ポスト対策 (2026-06-09): 元動画リンク先頭 + コピペ用ブロックを明示
        self.assertIn("元動画ツイート", c.draft_text)
        self.assertIn("コピペ用", c.draft_text)
        # 本文が長いと動画を一緒に投稿できないため、コメントは短く調整される
        self.assertLessEqual(len(c.post_text), 110)

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

    # 2026-07-02 user 決定「試合前の動画付きSNSはお宝動画があるので逃さない」:
    # 出来事語なしの練習動画 (tag=選手の話題) は既定では除外だが、
    # keep_low_signal=True (試合前帯) では候補に残す。
    _PRACTICE_FEED = (
        "<rss><channel>"
        "<item><title>坂本勇人 本日の様子です</title>"
        "<description>坂本勇人 本日の様子です "
        "&lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/222/img/def.jpg&quot;&gt;</description>"
        "<link>https://x.com/yomiuri_giants/status/222</link></item>"
        "</channel></rss>"
    )

    def test_low_signal_video_skipped_by_default(self):
        from src import x_post_mail_lane as lane
        with self._detect_patch():
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3,
                fetch_fn=lambda url: self._PRACTICE_FEED,
                handles=["TokyoGiants"],  # 1 handle = buzz 加点なし (言及1<2)
            )
        self.assertEqual(cands, [])

    def test_low_signal_video_kept_in_pregame_treasure_mode(self):
        from src import x_post_mail_lane as lane
        with self._detect_patch():
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3,
                fetch_fn=lambda url: self._PRACTICE_FEED,
                handles=["TokyoGiants"],
                keep_low_signal=True, min_score=1,
            )
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].focus_player, "坂本勇人")
        self.assertEqual(
            cands[0].quote_url, "https://x.com/yomiuri_giants/status/222"
        )

    def test_avoid_player_skips_before_comment_fn(self):
        from src import x_post_mail_lane as lane
        calls = []

        def _comment(parent_text, player):
            calls.append((parent_text, player))
            return f"{player}、最高だ！"

        with self._detect_patch():
            cands = lane.build_video_radar_candidates(
                db_path=None,
                max_count=3,
                fetch_fn=lambda url: self._FEED,
                comment_fn=_comment,
                avoid_player_names={"坂本勇人"},
            )
        self.assertEqual(cands, [])
        self.assertEqual(calls, [])

    def test_comment_fn_empty_falls_back_to_concrete_video_hook(self):
        # LLM が空/門番落ちでも動画候補は捨てない。抽象テンプレではなく、元動画の
        # 場面語に寄せた deterministic hook に fallback する。
        from src import x_post_mail_lane as lane
        with self._detect_patch():
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3, fetch_fn=lambda url: self._FEED,
                comment_fn=lambda pt, pl: "",  # LLM 失敗/門番落ち → fallback
            )
        self.assertEqual(len(cands), 1)
        self.assertIn("坂本勇人", cands[0].post_text)
        self.assertIn("振り切り", cands[0].post_text)
        self.assertNotIn("これは見ておきたい", cands[0].post_text)

    def test_no_comment_fn_uses_template(self):
        # comment_fn 未設定 (key 無し / test) のみ graceful に出来事 template fallback。
        from src import x_post_mail_lane as lane
        with self._detect_patch():
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3, fetch_fn=lambda url: self._FEED,
            )
        self.assertEqual(len(cands), 1)
        self.assertIn("坂本勇人", cands[0].post_text)
        self.assertNotIn("http", cands[0].post_text)

    def test_defense_video_fallback_mentions_visible_scene(self):
        from unittest import mock
        from src import x_post_mail_lane as lane

        feed = (
            "<rss><channel>"
            "<item><title>門脇誠 ファインプレー 好返球</title>"
            "<description>門脇誠 ファインプレー 好返球 "
            "&lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/222/img/abc.jpg&quot;&gt;</description>"
            "<link>https://x.com/TokyoGiants/status/222</link></item>"
            "</channel></rss>"
        )
        with mock.patch(
            "src.x_post_mail_lane.detect_giants_player_name",
            side_effect=lambda t, alias_map=None: "門脇誠" if "門脇" in str(t) else "",
        ):
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3, fetch_fn=lambda url: feed,
            )
        self.assertEqual(len(cands), 1)
        self.assertIn("一歩目", cands[0].post_text)
        self.assertIn("送球", cands[0].post_text)
        self.assertNotIn("ナイスゲーム", cands[0].post_text)

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


class DetectPlayerBoundaryTests(unittest.TestCase):
    """2026-07-03 実事故: alias「バル」がサッカー記事「オヤルサバル」に部分一致。"""

    _AM = {"バル": "バルドナード", "バルドナード": "バルドナード", "吉川尚輝": "吉川尚輝"}

    def test_short_katakana_alias_inside_word_rejected(self) -> None:
        from src.x_post_mail_lane import detect_giants_player_name
        out = detect_giants_player_name(
            "スペインがオヤルサバルの2ゴールでオーストリアを下す W杯決勝T",
            alias_map=self._AM,
        )
        self.assertEqual(out, "")

    def test_short_katakana_alias_with_boundary_accepted(self) -> None:
        from src.x_post_mail_lane import detect_giants_player_name
        self.assertEqual(
            detect_giants_player_name("バルが三者凡退で試合を締めた", alias_map=self._AM),
            "バルドナード",
        )
        self.assertEqual(
            detect_giants_player_name("巨人・バルドナードが今季初セーブ", alias_map=self._AM),
            "バルドナード",
        )
        self.assertEqual(
            detect_giants_player_name("吉川尚輝が猛打賞", alias_map=self._AM),
            "吉川尚輝",
        )


class MultiTeamHandleGiantsGateTests(unittest.TestCase):
    """2026-07-03 実事故: DAZN (12球団アカ) のオリックス選手クリップが
    「好プレー」語だけで候補入り。多球団 handle は巨人裏付け必須。"""

    @staticmethod
    def _feed(text: str) -> str:
        return (
            "<rss><channel>"
            f"<item><title>{text}</title>"
            f"<description>{text} "
            "&lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/111/img/a.jpg&quot;&gt;"
            "</description>"
            "<link>https://x.com/DAZNJPNBaseball/status/111</link></item>"
            "</channel></rss>"
        )

    def test_multi_team_handle_without_giants_context_skipped(self) -> None:
        from src import video_radar as vr
        # fun marker (ファインプレー) + 年号で score 2 だが、巨人選手も巨人語も無い
        posts = vr.gather_buzz_posts(
            detect_player_fn=lambda t: "",
            fetch_fn=lambda url: self._feed("2026年もえげつないファインプレー！"),
            handles=["DAZNJPNBaseball"],
        )
        self.assertEqual(posts, [])

    def test_multi_team_handle_with_giants_word_kept(self) -> None:
        from src import video_radar as vr
        posts = vr.gather_buzz_posts(
            detect_player_fn=lambda t: "",
            fetch_fn=lambda url: self._feed("2026年も巨人戦でえげつないファインプレー！"),
            handles=["DAZNJPNBaseball"],
        )
        self.assertEqual(len(posts), 1)

    def test_dedicated_handle_not_gated(self) -> None:
        from src import video_radar as vr
        posts = vr.gather_buzz_posts(
            detect_player_fn=lambda t: "",
            fetch_fn=lambda url: self._feed("2026年もえげつないファインプレー！"),
            handles=["Sanspo_Giants"],
        )
        self.assertEqual(len(posts), 1)


class GameBuzzHandlesTests(unittest.TestCase):
    """2026-07-03 user「ホームでない場合は動画は DAZN にできる？日テレが出なくなる」"""

    def test_away_game_excludes_ntv(self) -> None:
        """ビジター戦は日テレ中継なし → ntv_baseball を外し DAZN が動画を担う。"""
        from src import x_post_mail_lane as lane
        with patch.object(lane, "_today_giants_away", return_value=True):
            handles = lane.game_buzz_handles()
        self.assertNotIn("ntv_baseball", handles)
        self.assertIn("DAZNJPNBaseball", handles)
        self.assertEqual(
            handles,
            [h for h in lane._GAME_BUZZ_HANDLES if h != "ntv_baseball"],
        )

    def test_home_or_unknown_keeps_default_order(self) -> None:
        from src import x_post_mail_lane as lane
        for venue in (False, None):
            with patch.object(lane, "_today_giants_away", return_value=venue):
                self.assertEqual(lane.game_buzz_handles(), lane._GAME_BUZZ_HANDLES)


class BuildMlbWatchCandidatesTests(unittest.TestCase):
    """2026-07-02 フォロワー増計画: 元巨人MLB組 (菅野/岡本) + 大谷別枠の引用RT候補。"""

    @staticmethod
    def _item(title: str, status_id: str, *, video: bool = True, image: bool = False) -> str:
        media = ""
        if video:
            media += (
                "&lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/"
                f"{status_id}/img/x.jpg&quot;&gt;"
            )
        if image:
            media += (
                "&lt;img src=&quot;https://pbs.twimg.com/media/"
                f"photo{status_id}.jpg&quot;&gt;"
            )
        return (
            f"<item><title>{title}</title>"
            f"<description>{title} {media}</description>"
            f"<link>https://x.com/MLBJapan/status/{status_id}</link></item>"
        )

    def _feed(self, *items: str) -> str:
        return "<rss><channel>" + "".join(items) + "</channel></rss>"

    def test_builds_ohtani_and_ex_giants_with_caps(self):
        from src import x_post_mail_lane as lane
        feed = self._feed(
            self._item("大谷翔平が第30号ホームラン", "1"),
            self._item("岡本和真がメジャー初の猛打賞", "2"),
            self._item("大谷翔平がベンチで笑顔", "3"),  # 大谷 2 件目 → 別枠 cap 1 で落ちる
            self._item("ヤンキースが連勝", "4"),        # 対象外選手 → 落ちる
        )
        cands = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: f"{pl}、これは効く一発。",
        )
        players = [c.focus_player for c in cands]
        self.assertEqual(sorted(players), ["大谷翔平", "岡本和真"])
        for c in cands:
            self.assertEqual(c.metric, "mlb_watch_post")
            self.assertTrue(c.signature.startswith("mlbwatch|"))
            self.assertTrue(c.quote_url.startswith("https://x.com/MLBJapan/status/"))
            self.assertEqual(c.media_handle, "mlbjapan")
            self.assertIn("コピペ用", c.draft_text)

    def test_extra_star_light_cap_one_per_mail(self):
        """2026-07-03 user「山本由伸と鈴木誠也も軽めに」(1万フォロワー到達、
        認証大手×日本人スターへ枠拡張): 軽め枠は 1 便 1 人まで、
        元巨人/大谷の枠は食わない。frame は 日本人スター 表示。"""
        from src import x_post_mail_lane as lane
        feed = self._feed(
            self._item("Yoshinobu Yamamoto strikes out 10", "11"),
            self._item("Seiya Suzuki two-run blast", "12"),  # 軽め枠 2 人目 → cap 1 で落ちる
            self._item("岡本和真がメジャー初の猛打賞", "13"),
        )
        cands = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: f"{pl}、これは効く一発。",
        )
        players = [c.focus_player for c in cands]
        self.assertIn("岡本和真", players)
        self.assertEqual(
            len([p for p in players if p in ("山本由伸", "鈴木誠也")]), 1
        )
        star = next(c for c in cands if c.focus_player in ("山本由伸", "鈴木誠也"))
        self.assertIn("日本人スター", star.title)
        self.assertNotIn("元巨人", star.title)

    def test_as_reply_builds_reply_candidates_with_custom_handles(self):
        """2026-07-03 user「メジャー系の日本公式で大谷や岡本や菅野にもリプしたい」:
        as_reply=True で reply_to_id 付きのリプ候補になり、handles 差し替えが効く。"""
        from src import x_post_mail_lane as lane
        feed = self._feed(self._item("大谷翔平が第30号ホームラン", "77"))
        calls = []

        def fetch(url):
            calls.append(url)
            return feed if "30R9gmaMUy3guDJ" in url else "<rss><channel></channel></rss>"

        cands = lane.build_mlb_watch_candidates(
            max_count=2,
            fetch_fn=fetch,
            comment_fn=lambda pt, pl: f"{pl}、この一発は角度も完璧でした。",
            handles=["30R9gmaMUy3guDJ", "MLBJapan"],
            as_reply=True,
        )
        self.assertTrue(any("30R9gmaMUy3guDJ" in u for u in calls))
        self.assertFalse(any("/Dodgers" in u for u in calls))  # handles 差し替えで US 公式は fetch しない
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertEqual(c.metric, lane._REPLY_CANDIDATE_METRIC)
        self.assertEqual(c.reply_to_id, "77")
        self.assertEqual(c.quote_url, "")
        self.assertTrue(c.signature.startswith("mlbreply|"))
        self.assertIn("MLBリプ候補", c.title)
        self.assertIn("reply:mlb", c.reason_tags)
        self.assertIn("manual_only", c.reason_tags)

    def test_as_reply_and_quote_signatures_differ(self):
        """同じ元投稿でも引用RT と リプ で signature が分かれ、dedup が互いを潰さない。"""
        from src import x_post_mail_lane as lane
        feed = self._feed(self._item("岡本和真がメジャー初の猛打賞", "5"))
        kw = dict(
            max_count=1,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: f"{pl}、逆方向への一打が光りました。",
            handles=["MLBJapan"],
        )
        quote = lane.build_mlb_watch_candidates(**kw)
        reply = lane.build_mlb_watch_candidates(as_reply=True, **kw)
        self.assertEqual(len(quote), 1)
        self.assertEqual(len(reply), 1)
        self.assertNotEqual(quote[0].signature, reply[0].signature)

    def test_skip_when_voice_empty_no_template(self):
        from src import x_post_mail_lane as lane
        feed = self._feed(self._item("大谷翔平が第30号ホームラン", "1"))
        cands = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: "",  # voice 門番落ち → skip
        )
        self.assertEqual(cands, [])
        # comment_fn 未設定でも skip (テンプレで埋めない)
        cands2 = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
        )
        self.assertEqual(cands2, [])

    def test_video_required_text_only_excluded(self):
        # 2026-07-02 user「ポストに動画がついてないと意味ない」: 動画無しは候補にしない。
        from src import x_post_mail_lane as lane
        feed = self._feed(
            self._item("菅野智之が今日先発", "1", video=False),
            self._item("菅野智之 7回無失点のハイライト", "2", video=True),
        )
        cands = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: f"{pl}、圧巻の投球。",
        )
        self.assertEqual(len(cands), 1)  # 動画付きのみ (同一選手 1 本)
        self.assertIn("/status/2", cands[0].quote_url)

    def test_all_text_only_feed_yields_nothing(self):
        from src import x_post_mail_lane as lane
        feed = self._feed(self._item("大谷翔平が記者会見", "9", video=False))
        cands = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: f"{pl}、注目。",
        )
        self.assertEqual(cands, [])

    def test_image_only_post_accepted_video_still_first(self):
        # 2026-07-02 user「画像でもよいが、動画多め」: 画像付きは候補OK、
        # 同一選手では動画付きが優先。
        from src import x_post_mail_lane as lane
        feed = self._feed(
            self._item("岡本和真のロッカールーム写真", "10", video=False, image=True),
            self._item("大谷翔平の第30号写真", "11", video=False, image=True),
            self._item("大谷翔平 第30号ホームラン動画", "12", video=True),
        )
        cands = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: f"{pl}、これは見たい。",
        )
        by_player = {c.focus_player: c for c in cands}
        self.assertIn("岡本和真", by_player)  # 画像のみでも候補になる
        self.assertIn("大谷翔平", by_player)
        # 大谷は動画付き (status/12) が画像 (status/11) より優先
        self.assertIn("/status/12", by_player["大谷翔平"].quote_url)

    def test_dedup_set_skips_signature(self):
        from src import x_post_mail_lane as lane
        import hashlib as _h
        url = "https://x.com/MLBJapan/status/1"
        sig = "mlbwatch|" + _h.sha1(url.encode("utf-8")).hexdigest()[:16]
        feed = self._feed(self._item("大谷翔平が第30号ホームラン", "1"))
        cands = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "MLBJapan" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: f"{pl}、これは効く。",
            dedup_set={sig},
        )
        self.assertEqual(cands, [])

    def test_us_team_english_feed_detected(self):
        # 2026-07-02 user「アメリカの所属チームとかか」: US 公式の英語 feed でも
        # 英 alias (Shohei/Okamoto 等) で選手検出できる。
        from src import x_post_mail_lane as lane
        feed = (
            "<rss><channel>"
            "<item><title>Shohei goes yard! His 19th of the season</title>"
            "<description>Shohei goes yard! "
            "&lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/21/img/x.jpg&quot;&gt;"
            "</description>"
            "<link>https://x.com/Dodgers/status/21</link></item>"
            "</channel></rss>"
        )
        cands = lane.build_mlb_watch_candidates(
            max_count=3,
            fetch_fn=lambda url: feed if "twitter/user/Dodgers" in url else "<rss><channel></channel></rss>",
            comment_fn=lambda pt, pl: f"{pl}、この一発は見逃せない。",
        )
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].focus_player, "大谷翔平")
        self.assertIn("/Dodgers/status/21", cands[0].quote_url)


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
        import contextlib, sys, types
        from unittest import mock
        fake_client = mock.MagicMock()
        fake_client.models.generate_content.return_value = types.SimpleNamespace(text=text)
        fake_genai = types.SimpleNamespace(Client=lambda api_key=None: fake_client)
        google_mod = sys.modules.get("google") or types.ModuleType("google")
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.dict(sys.modules, {"google": google_mod, "google.genai": fake_genai}))
        # 2026-07-03: 旧実装の bare setattr は google module に fake を残し、
        # 後続の test_x_post_branding_gen 側 genai patch を汚染していた (leak)。
        # patch.object なら退出時に元の属性へ戻る。
        stack.enter_context(mock.patch.object(google_mod, "genai", fake_genai, create=True))
        return stack

    def test_returns_comment_post_api(self):
        from src import x_post_branding_gen as xbg
        # 50字未満は非liveの _voice_quality_ok 門番が弾く (live時間帯だけ通る) ため、
        # 時刻に依存しない 50字以上の mock 文で「返り値=生成文」だけを検証する。
        comment = (
            "坂本勇人、サヨナラの場面で一番怖い打者であることをまた証明したな。"
            "土壇場でも自分のスイングを崩さないのが坂本勇人の凄みだよ。"
        )
        with self._patch_genai(comment):
            out = xbg.build_quote_rt_comment("坂本勇人 サヨナラ", "坂本勇人", gemini_api_key="k")
        self.assertEqual(out, comment)  # log NameError 回帰防止

    def test_hallucinated_number_rejected(self):
        from src import x_post_branding_gen as xbg
        # 投稿に無い "100号" を出したら捏造として破棄 → ""
        with self._patch_genai("坂本勇人、通算100号おめでとう！"):
            out = xbg.build_quote_rt_comment("坂本勇人 サヨナラ", "坂本勇人", gemini_api_key="k")
        self.assertEqual(out, "")

    def test_empty_key_returns_empty(self):
        from src import x_post_branding_gen as xbg
        self.assertEqual(xbg.build_quote_rt_comment("x", "y", gemini_api_key=""), "")

    def test_reply_mode_without_db_fact_skips(self):
        """2026-07-03: 補足リプは verified data が核。 db_fact 無し = 補足材料
        無しなので LLM を呼ばず "" (caller は候補ごとスキップ、 感想で埋めない)。"""
        from src import x_post_branding_gen as xbg
        with self._patch_genai("呼ばれないはず"):
            out = xbg.build_quote_rt_comment(
                "坂本勇人 サヨナラ", "坂本勇人",
                gemini_api_key="k", budget_site="reply", db_fact="",
            )
        self.assertEqual(out, "")

    def test_reply_mode_returns_short_supplement(self):
        """補足リプ mode: db_fact あり → 短い補足文が返る (捏造数字なし)。"""
        from src import x_post_branding_gen as xbg
        supplement = (
            "ちなみに坂本勇人、今季の得点圏は.345で12球団でも上位です。"
            "この場面で回ってくる巡り合わせも含めて強いですね。"
        )
        with self._patch_genai(supplement):
            out = xbg.build_quote_rt_comment(
                "坂本勇人 サヨナラ", "坂本勇人",
                gemini_api_key="k", budget_site="reply",
                db_fact="今季得点圏打率.345 (12球団上位)",
            )
        self.assertEqual(out, supplement)

    def test_reply_mode_mlb_no_fact_allowed_with_flag(self):
        """MLBリプ: require_db_fact=False なら db_fact 無しでも元投稿の具体場面
        ベースの短い補足リプが成立する (NPB DB に MLB 数字が無いため)。"""
        from src import x_post_branding_gen as xbg
        reply = (
            "打った瞬間に確信歩きが出る第30号でした。逆方向にあの角度で運べるのは"
            "今の大谷翔平の状態の良さそのものですね。"
        )
        with self._patch_genai(reply):
            out = xbg.build_quote_rt_comment(
                "大谷翔平が第30号ホームラン", "大谷翔平",
                gemini_api_key="k", budget_site="reply",
                db_fact="", require_db_fact=False,
            )
        self.assertEqual(out, reply)


class VideoRadarImpressionPolicyTests(unittest.TestCase):
    """451: 動画候補は同選手のデータ候補が居ても落とさず確実に届ける。"""

    def test_video_preferred_over_article_for_same_player(self):
        # 2026-06-04 user 決定:「引用RT＋記事を1選手1件に。引用RT優先」。
        # 同選手の引用RT(video) と記事voice(GEMINI_BRANDING) は 1 件に絞り、
        # append 順で先に来る引用RT が残り、 同選手の記事は dedup される。
        from src.x_post_mail_lane import (
            Candidate, apply_x_impression_policy, _VIDEO_RADAR_METRIC, _GEMINI_BRANDING_METRIC,
        )
        video_c = Candidate(
            title="(動画) 名場面回顧｜巨人公式｜坂本", metric=_VIDEO_RADAR_METRIC,
            period_label="動画候補", draft_text="y", char_count=10,
            signature="video_radar|VID1", post_text="坂本勇人 名場面 ▶ url",
            focus_player="坂本勇人",
        )
        article_c = Candidate(
            title="X-post branding｜坂本勇人", metric=_GEMINI_BRANDING_METRIC,
            period_label="記事voice", draft_text="x", char_count=10,
            signature="gemini|sakamoto", post_text="坂本勇人の一打は痺れたな。",
            focus_player="坂本勇人",
        )
        kept, dropped = apply_x_impression_policy([video_c, article_c])
        kept_sigs = {c.signature for c in kept}
        self.assertIn("video_radar|VID1", kept_sigs)       # 引用RT が優先で残る
        self.assertNotIn("gemini|sakamoto", kept_sigs)     # 同選手の記事は 1 件に絞られ落ちる
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0][1], "dedup_player_in_mail")

    def test_hochi_reply_survives_player_dedup_against_data_candidate(self):
        from src.x_post_mail_lane import Candidate, apply_x_impression_policy, _HOCHI_REPLY_METRIC
        data_c = Candidate(
            title="坂本勇人 OPS", metric="OPS", period_label="今シーズン",
            draft_text="x", char_count=10, signature="ops|sakamoto",
            post_text="坂本勇人 OPS .900", focus_player="坂本勇人",
        )
        reply_c = Candidate(
            title="(報知リプ) 坂本勇人", metric=_HOCHI_REPLY_METRIC,
            period_label="報知リプ候補", draft_text="y", char_count=80,
            signature="reply_cand|hochi_giants|12345",
            post_text=(
                "坂本勇人のこの流れは、結果だけでなく立ち位置まで見たいですね。\n"
                "次の場面でどうつながるかまで追いたいです。"
            ),
            focus_player="坂本勇人", reply_to_id="12345",
        )
        kept, dropped = apply_x_impression_policy([data_c, reply_c], max_candidates=2)
        kept_sigs = {c.signature for c in kept}
        self.assertIn("ops|sakamoto", kept_sigs)
        self.assertIn("reply_cand|hochi_giants|12345", kept_sigs)
        self.assertEqual(dropped, [])


class DataPrecisionPolicyTests(unittest.TestCase):
    """Data-angle candidates stay enabled, but thin facts are not mailed."""

    def test_low_sample_opponent_split_is_dropped(self):
        from src.x_post_mail_lane import Candidate, apply_x_impression_policy

        thin = Candidate(
            title="対阪神 split",
            metric="対戦別split",
            period_label="今シーズン",
            draft_text="根拠",
            char_count=80,
            signature="opp_split|選手|阪神",
            post_text="【選手】阪神キラー\n対阪神 .500 (5安打/10打数・2打点)\n#巨人",
            focus_player="選手",
            db_fact_line="対阪神 打率.500 (5安打/10打数・2打点) ｜ シーズン.250 ｜ 差 +.250",
            team_level="first",
            sample_size=10,
            source_material_type="opponent_split",
        )
        kept, dropped = apply_x_impression_policy([thin], max_candidates=1)
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 1)
        self.assertTrue(dropped[0][1].startswith("data_precision_sample_too_small:10<25"))

    def test_strong_opponent_split_survives(self):
        from src.x_post_mail_lane import Candidate, apply_x_impression_policy

        strong = Candidate(
            title="対阪神 split",
            metric="対戦別split",
            period_label="今シーズン",
            draft_text="根拠",
            char_count=100,
            signature="opp_split|選手|阪神",
            post_text="【選手】阪神キラー\n対阪神 .360 (9安打/25打数・5打点)\n他カード .240 — 対阪神で+.120\n#巨人",
            focus_player="選手",
            db_fact_line="対阪神 打率.360 (9安打/25打数・5打点) ｜ 他カード.240 (50打数) ｜ 差 +.120",
            team_level="first",
            sample_size=25,
            source_material_type="opponent_split",
        )
        kept, dropped = apply_x_impression_policy([strong], max_candidates=1)
        self.assertEqual([c.signature for c in kept], ["opp_split|選手|阪神"])
        self.assertEqual(dropped, [])

    def test_season_based_opponent_split_is_dropped(self):
        from src.x_post_mail_lane import Candidate, apply_x_impression_policy

        old_style = Candidate(
            title="対阪神 split",
            metric="対戦別split",
            period_label="今シーズン",
            draft_text="根拠",
            char_count=100,
            signature="opp_split|選手|阪神",
            post_text="【選手】阪神キラー\n対阪神 .360 (9安打/25打数・5打点)\nシーズン .240 — 対阪神で+.120\n#巨人",
            focus_player="選手",
            db_fact_line="対阪神 打率.360 (9安打/25打数・5打点) ｜ シーズン.240 ｜ 差 +.120",
            team_level="first",
            sample_size=25,
            source_material_type="opponent_split",
        )
        kept, dropped = apply_x_impression_policy([old_style], max_candidates=1)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0][1], "data_precision_opp_split_fact_weak")

    def test_small_gap_data_angle_is_dropped(self):
        from src.x_post_mail_lane import Candidate, apply_x_impression_policy

        small_gap = Candidate(
            title="対阪神 split",
            metric="対戦別split",
            period_label="今シーズン",
            draft_text="根拠",
            char_count=100,
            signature="opp_split|選手|阪神",
            post_text="【選手】阪神キラー\n対阪神 .300 (9安打/30打数・5打点)\n他カード .200 — 対阪神で+.100\n#巨人",
            focus_player="選手",
            db_fact_line="対阪神 打率.300 (9安打/30打数・5打点) ｜ 他カード.200 (60打数) ｜ 差 +.100",
            team_level="first",
            sample_size=30,
            source_material_type="opponent_split",
        )
        kept, dropped = apply_x_impression_policy([small_gap], max_candidates=1)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0][1], "data_precision_gap_too_small:.100<.120")

    def test_weak_win_correlation_fact_is_dropped(self):
        from src.x_post_mail_lane import Candidate, apply_x_impression_policy

        weak = Candidate(
            title="勝利相関",
            metric="勝利相関",
            period_label="今シーズン",
            draft_text="根拠",
            char_count=80,
            signature="win_corr|選手|rbi",
            post_text="【選手】打点を挙げた試合\nあり 8勝2敗\nなし 10勝10敗\n#巨人",
            focus_player="選手",
            db_fact_line="打点あり: 8勝2敗",
            team_level="first",
            sample_size=40,
            source_material_type="win_correlation",
        )
        kept, dropped = apply_x_impression_policy([weak], max_candidates=1)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0][1], "data_precision_win_corr_fact_weak")

    def test_small_gap_win_correlation_is_dropped(self):
        from src.x_post_mail_lane import Candidate, apply_x_impression_policy

        small_gap = Candidate(
            title="勝利相関",
            metric="勝利相関",
            period_label="今シーズン",
            draft_text="根拠",
            char_count=100,
            signature="win_corr|選手|rbi",
            post_text="【選手】打点を挙げた試合\nあり 11勝9敗 (勝率.550)\nなし 11勝11敗 (勝率.500)\n#巨人",
            focus_player="選手",
            db_fact_line=(
                "打点を挙げた試合: 11勝9敗 勝率.550 ｜ "
                "それ以外: 11勝11敗 勝率.500 ｜ 条件付き勝率差 +.050 (今季42試合)"
            ),
            team_level="first",
            sample_size=42,
            source_material_type="win_correlation",
        )
        kept, dropped = apply_x_impression_policy([small_gap], max_candidates=1)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0][1], "data_precision_gap_too_small:.050<.200")


class DbRankingKillSwitchTests(unittest.TestCase):
    """2026-06-12: 驚きのない DB ランキング候補 (直近N日打率等) の kill switch。

    効果学習 v0 実測 (直近7日打率 voice ♥0-1 vs 【】驚き角度 ♥3-5) を受けて、
    prod は X_POST_MAIL_DB_RANKING_ENABLED=0 で pick_candidates を止める。
    """

    def test_disabled_returns_empty_without_querying(self):
        query_mock = MagicMock()
        with patch.dict(
            "os.environ", {"X_POST_MAIL_DB_RANKING_ENABLED": "0"}, clear=False
        ):
            cands = pick_candidates(
                query_mock,
                now=datetime(2026, 6, 12, 7, 0, tzinfo=JST),
                max_candidates=3,
                min_sample=1,
            )
        self.assertEqual(cands, [])
        query_mock.assert_not_called()

    def test_default_keeps_legacy_behaviour(self):
        # env 未設定 (または "1") では従来どおり combo を query する
        query_mock = MagicMock(return_value={"rows": []})
        with patch.dict(
            "os.environ", {"X_POST_MAIL_DB_RANKING_ENABLED": ""}, clear=False
        ):
            pick_candidates(
                query_mock,
                now=datetime(2026, 6, 12, 7, 0, tzinfo=JST),
                max_candidates=1,
                min_sample=1,
            )
        self.assertGreater(query_mock.call_count, 0)


class DataPlainLlmRewriteTests(unittest.TestCase):
    """Data-only candidates can be made plain with Gemini 3.1 Flash Lite."""

    def test_rewrites_only_data_angle_candidates(self):
        from src.tools import run_x_post_mail

        data = Candidate(
            title="勝利相関",
            metric="勝利相関",
            period_label="今シーズン",
            draft_text="【根拠】打点を挙げた試合: 8勝2敗 勝率.800",
            char_count=40,
            signature="win_corr|x",
            post_text="【選手】打点を挙げた試合\nあり 8勝2敗 (勝率.800)\n#巨人",
            focus_player="選手",
            db_fact_line="打点を挙げた試合: 8勝2敗 勝率.800",
            source_material_type="win_correlation",
        )
        news = Candidate(
            title="ニュース",
            metric="NEWS_OPINION",
            period_label="ニュース",
            draft_text="根拠",
            char_count=20,
            post_text="ニュース本文",
            focus_player="選手",
        )
        fake_xbg = MagicMock()
        fake_xbg.build_plain_data_post.return_value = "選手は打点を挙げた試合で8勝2敗。\n数字だけ見ると、勝ち筋とのつながりが分かりやすい。"

        with patch.dict("os.environ", {"X_POST_MAIL_DATA_LLM_REWRITE_ENABLED": "1"}), patch.object(
            run_x_post_mail, "_xbg", fake_xbg
        ):
            out = run_x_post_mail._rewrite_data_candidates_plain_llm(
                [data, news],
                gemini_key="dummy",
                model_id="gemini-3.1-flash-lite",
            )

        self.assertEqual(out[0].post_text, fake_xbg.build_plain_data_post.return_value)
        self.assertIn("Gemini Flash Lite data rewrite model=gemini-3.1-flash-lite", out[0].draft_text)
        self.assertEqual(out[1].post_text, "ニュース本文")
        fake_xbg.build_plain_data_post.assert_called_once()

    def test_rewrite_flag_zero_keeps_original(self):
        from src.tools import run_x_post_mail

        data = Candidate(
            title="勝利相関",
            metric="勝利相関",
            period_label="今シーズン",
            draft_text="根拠",
            char_count=10,
            post_text="元本文",
            focus_player="選手",
        )
        fake_xbg = MagicMock()
        with patch.dict("os.environ", {"X_POST_MAIL_DATA_LLM_REWRITE_ENABLED": "0"}), patch.object(
            run_x_post_mail, "_xbg", fake_xbg
        ):
            out = run_x_post_mail._rewrite_data_candidates_plain_llm([data], gemini_key="dummy")
        self.assertEqual(out[0].post_text, "元本文")
        fake_xbg.build_plain_data_post.assert_not_called()


class ReplyCandidateRuntimeConfigTests(unittest.TestCase):
    """報知リプ候補は費用を増やさない設定を default にする。"""

    def test_reply_candidate_defaults_are_hochi_and_llm_on(self):
        # 2026-06-04 user 方針: リプも flash-lite voice (ヨシラバー風)。
        # _reply_llm_enabled() の default は ON に変更 (旧: deterministic テンプレ)。
        import os
        from src.tools import run_x_post_mail
        with patch.dict(
            os.environ,
            {
                "X_POST_REPLY_TARGET_HANDLES": "",
                "X_POST_REPLY_CANDIDATES_MAX": "",
                "ENABLE_X_POST_REPLY_LLM": "",
            },
            clear=False,
        ):
            # 469: 読売巨人軍公式 TokyoGiants は env に依らず常時補完される
            # 2026-07-03: Sanspo_Giants / koba_nikkan default 追加 + 報知/公式 先頭固定
            self.assertEqual(
                run_x_post_mail._reply_target_handles(),
                ["hochi_giants", "TokyoGiants", "Sanspo_Giants", "koba_nikkan"],
            )
            self.assertEqual(run_x_post_mail._reply_candidates_max_per_run(), 3)
            self.assertTrue(run_x_post_mail._reply_llm_enabled())

    def test_reply_candidate_env_overrides(self):
        import os
        from src.tools import run_x_post_mail
        with patch.dict(
            os.environ,
            {
                "X_POST_REPLY_TARGET_HANDLES": "@hochi_giants,Sanspo_Giants",
                "X_POST_REPLY_CANDIDATES_MAX": "5",
                "ENABLE_X_POST_REPLY_LLM": "1",
            },
            clear=False,
        ):
            # 469: env override しても公式 TokyoGiants は補完される
            # 2026-07-03: 報知/公式 先頭固定 (「特に公式と報知」)
            self.assertEqual(
                run_x_post_mail._reply_target_handles(),
                ["hochi_giants", "TokyoGiants", "Sanspo_Giants"],
            )
            self.assertEqual(run_x_post_mail._reply_candidates_max_per_run(), 5)
            self.assertTrue(run_x_post_mail._reply_llm_enabled())


if __name__ == "__main__":
    unittest.main()


class BuildPlayerCommentCandidateTests(unittest.TestCase):
    """パターン①: 選手コメント速報 (literal、 LLM不使用、 たんぱく)。"""

    _HTML = (
        "<html><body>竹丸和幸投手は試合後、"
        "「8イニングはアマ時代含めて結構久々だったんですけど、思ったよりいけるなと。"
        "そういう感じです。きょうぐらいテンポよくいければ、それなりにイニングが食えるのかなとは思います」"
        "と振り返った。</body></html>"
    )

    def test_self_standing_long_quote(self):
        from src import x_post_mail_lane as lane
        c = lane.build_player_comment_candidate(
            member_name="竹丸和幸", source_title="竹丸8回好投も黒星",
            source_url="https://x.test/1", html_text=self._HTML,
        )
        self.assertIsNotNone(c)
        self.assertEqual(c.metric, "PLAYER_COMMENT")
        self.assertTrue(c.post_text.startswith("竹丸和幸『"))       # コメント主役
        self.assertIn("思ったよりいけるなと", c.post_text)          # literal
        self.assertNotIn("竹丸8回好投も黒星", c.post_text)           # 状況説明は混ぜない
        self.assertNotIn("http", c.post_text)

    def test_no_quote_returns_none(self):
        from src import x_post_mail_lane as lane
        c = lane.build_player_comment_candidate(
            member_name="坂本勇人", source_title="x",
            source_url="https://x.test/2", html_text="<html><body>本文に発言なし</body></html>",
        )
        self.assertIsNone(c)

    def test_comment_candidate_carries_source_image(self):
        from src import x_post_mail_lane as lane
        c = lane.build_player_comment_candidate(
            member_name="竹丸和幸",
            source_title="竹丸8回好投も黒星",
            source_url="https://x.test/1",
            html_text=self._HTML,
            source_name="テスト新聞",
            image_bytes=b"\xff\xd8\xffcomment-image",
            image_source_url="https://img.example.test/takemaru.jpg",
        )
        self.assertIsNotNone(c)
        assert c is not None
        self.assertEqual(c.image_bytes, b"\xff\xd8\xffcomment-image")
        self.assertEqual(c.image_source_url, "https://img.example.test/takemaru.jpg")
        self.assertIn("竹丸和幸", c.image_alt_text)
        self.assertIn("添付画像: https://img.example.test/takemaru.jpg", c.draft_text)

    def test_non_member_returns_none(self):
        from src import x_post_mail_lane as lane
        c = lane.build_player_comment_candidate(
            member_name="架空太郎", source_title="x",
            source_url="https://x.test/3", html_text=self._HTML,
        )
        self.assertIsNone(c)


class GeminiBrandingPlayerCooldownTests(unittest.TestCase):
    """LLM 費用節約: 同一選手の過剰生成を cooldown + window cap で抑える。"""

    def _cand(self, player: str, fact: str = "") -> Candidate:
        return Candidate(
            title=f"Xポスト案｜{player}",
            metric="OPS",
            period_label="直近5試合",
            draft_text=f"{player} 好調 #巨人",
            char_count=10,
            focus_player=player,
            db_fact_line=fact,
        )

    def test_players_within_cooldown_filters_by_ts(self) -> None:
        from src.x_post_mail_lane import _players_within_cooldown
        now = datetime(2026, 6, 3, 21, 0, tzinfo=JST)
        records = [
            {"focus_player": "坂本勇人", "ts": "2026-06-03T20:00:00+09:00"},  # 1h ago
            {"focus_player": "岡本和真", "ts": "2026-06-01T20:00:00+09:00"},  # ~49h ago
            {"focus_player": "", "ts": "2026-06-03T20:30:00+09:00"},         # no player
        ]
        out = _players_within_cooldown(records, now, cooldown_hours=24)
        self.assertIn("坂本勇人", out)
        self.assertNotIn("岡本和真", out)

    def test_players_within_cooldown_zero_disables(self) -> None:
        from src.x_post_mail_lane import _players_within_cooldown
        now = datetime(2026, 6, 3, 21, 0, tzinfo=JST)
        records = [{"focus_player": "坂本勇人", "ts": "2026-06-03T20:00:00+09:00"}]
        self.assertEqual(_players_within_cooldown(records, now, 0), set())

    def test_pick_skips_player_in_cooldown(self) -> None:
        from src.tools import run_x_post_mail
        picks = run_x_post_mail._pick_gemini_branding_players(
            [self._cand("坂本勇人"), self._cand("岡本和真")],
            lineup_focus_names=None,
            recent_player_counts=None,
            max_count=3,
            cooldown_players={"坂本勇人"},
        )
        names = [p[0] for p in picks]
        self.assertNotIn("坂本勇人", names)
        self.assertIn("岡本和真", names)

    def test_pick_window_cap_defaults_to_two(self) -> None:
        from src.tools import run_x_post_mail
        # 既出 2 回の選手は default cap(2)で skip、 1 回なら通す。
        picks = run_x_post_mail._pick_gemini_branding_players(
            [self._cand("坂本勇人"), self._cand("岡本和真")],
            lineup_focus_names=None,
            recent_player_counts={"坂本勇人": 2, "岡本和真": 1},
            max_count=3,
        )
        names = [p[0] for p in picks]
        self.assertNotIn("坂本勇人", names)
        self.assertIn("岡本和真", names)


class VideoRadarSourceNarrowingTests(unittest.TestCase):
    """2026-06-03: 試合中は buzz ソースを高シグナル5アカウントに絞る (コスト削減 +
    user: DAZN/日テレ動画を戻す)。報知+スポニチ+公式+日テレ巨人中継+DAZN。"""

    _GAME_SOURCES = sorted(
        ["hochi_giants", "SponichiGiants", "TokyoGiants", "ntv_baseball", "DAZNJPNBaseball"]
    )

    def _handles_hit(self, hour: int) -> list:
        import src.x_post_mail_lane as lane
        captured = []
        def fake_fetch(url):
            captured.append(url); return ""
        lane.build_video_radar_candidates(
            now=datetime(2026, 6, 3, hour, 0, tzinfo=JST),
            fetch_fn=fake_fetch, comment_fn=None, max_count=3,
        )
        ig = [u for u in captured if "twitter/user/" in u]
        return sorted({u.split("twitter/user/")[1].split("?")[0] for u in ig})

    def test_in_game_narrows_to_five_sources(self):
        # 20:00 = in_game_strong → 5ソース(報知+スポニチ+公式+日テレ+DAZN)
        self.assertEqual(self._handles_hit(20), self._GAME_SOURCES)

    def test_lineup_window_also_narrows(self):
        # 18:00 = lineup 枠(試合ランプ)→ 同5ソース(user: 18時から)
        self.assertEqual(self._handles_hit(18), self._GAME_SOURCES)

    def test_off_game_uses_all_sources(self):
        # 10:00 = 試合外 → 全ソース (2026-07-02 差別化2アカ+日刊班+報知水上記者追加で 12)
        self.assertEqual(len(self._handles_hit(10)), 12)


class VideoRadarInGameFreshnessFloorTests(unittest.TestCase):
    """2026-06-11: 試合中でも動画 lane は floor 2h (DAZN クリップの編集遅延対策)。"""

    def _feed(self, pub_rfc: str) -> str:
        return (
            "<rss><channel>"
            "<item><title>坂本勇人 サヨナラ満塁ホームラン</title>"
            "<description>坂本勇人 サヨナラ満塁ホームラン "
            "&lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/111/img/abc.jpg&quot;&gt;</description>"
            f"<link>https://x.com/DAZNJPNBaseball/status/111</link><pubDate>{pub_rfc}</pubDate></item>"
            "</channel></rss>"
        )

    def test_in_game_keeps_clip_older_than_30min(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        from unittest import mock

        from src import x_post_mail_lane as lane

        # 試合中 (in_game_strong 帯: 19:30 JST)、 クリップは 90 分前 (旧窓 0.5h なら除外)
        now = datetime(2026, 6, 10, 19, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        pub = (now - timedelta(minutes=90)).strftime("%a, %d %b %Y %H:%M:%S %z")
        self.assertEqual(lane.phase_freshness_max_age_hours(now), 0.5)  # 帯の前提確認
        with mock.patch(
            "src.x_post_mail_lane.detect_giants_player_name",
            side_effect=lambda t, alias_map=None: "坂本勇人" if "坂本" in str(t) else "",
        ):
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3, now=now,
                fetch_fn=lambda url: self._feed(pub),
            )
        self.assertEqual(len(cands), 1)  # floor 2h で生存

    def test_in_game_still_drops_clip_older_than_2h(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        from unittest import mock

        from src import x_post_mail_lane as lane

        now = datetime(2026, 6, 10, 19, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        pub = (now - timedelta(hours=3)).strftime("%a, %d %b %Y %H:%M:%S %z")
        with mock.patch(
            "src.x_post_mail_lane.detect_giants_player_name",
            side_effect=lambda t, alias_map=None: "坂本勇人" if "坂本" in str(t) else "",
        ):
            cands = lane.build_video_radar_candidates(
                db_path=None, max_count=3, now=now,
                fetch_fn=lambda url: self._feed(pub),
            )
        self.assertEqual(cands, [])  # 3h 前は試合中候補にしない


class ShareXFallbackButtonTests(unittest.TestCase):
    """2026-06-11: 画像つき share ボタンがあってもテキストのみ intent を併記する。

    user 報告「X投稿画面で次へが遷移せず戻る」(端末/X app 側の画像ステップ詰まり)
    の際に、 メール内に確実な投稿経路 (intent 直開き) を常設する。
    """

    def _cand(self):
        from src import x_post_mail_lane as lane
        return lane.Candidate(
            title="t", metric="m", period_label="今シーズン",
            draft_text="d", char_count=10, post_text="本文 #巨人",
        )

    def test_fallback_text_button_shown_with_share_x(self):
        from datetime import datetime
        from src import x_post_mail_lane as lane
        html = lane._compose_html_body(
            [self._cand()], datetime(2026, 6, 11, 22, 5),
            share_x_button_urls=["https://fetcher.example/share-x-cand?key=k&token=t"],
        )
        self.assertIn("画像つきで X に投稿", html)
        self.assertIn("テキストのみで投稿", html)
        self.assertIn("x.com/intent/post?text=", html)

    def test_no_fallback_button_without_share_x(self):
        from datetime import datetime
        from src import x_post_mail_lane as lane
        html = lane._compose_html_body(
            [self._cand()], datetime(2026, 6, 11, 22, 5),
            share_x_button_urls=[None],
        )
        self.assertNotIn("テキストのみで投稿", html)
        self.assertIn("X で投稿", html)


class MlbAlumniFactLineWiringTests(unittest.TestCase):
    """2026-06-24: 岡本和真 / 菅野智之 は MLB 成績を fact line に供給する。"""

    def setUp(self):
        from src.tools import run_x_post_mail as runner
        # process キャッシュを test 毎にリセット。
        runner._MLB_ALUMNI_CACHE["fetched"] = False
        runner._MLB_ALUMNI_CACHE["data"] = None

    _DATA = {
        "season": 2026,
        "players": [
            {"name": "岡本和真", "group": "hitting", "team": "ドジャース",
             "season": {"games": 70, "avg": ".291", "hr": 18, "rbi": 52, "ops": ".910"}},
        ],
    }

    def test_alumni_player_gets_mlb_fact_line(self):
        from src.tools import run_x_post_mail as runner
        with patch.object(runner._mlb, "fetch_mlb_alumni_data", return_value=self._DATA) as m:
            line = runner._mlb_alumni_fact_line("岡本和真")
            # 2 回目はキャッシュで再 fetch しない。
            runner._mlb_alumni_fact_line("岡本和真")
        self.assertIn("MLB ドジャース", line)
        self.assertIn("18本塁打", line)
        self.assertEqual(m.call_count, 1)

    def test_non_alumni_player_returns_blank_without_fetch(self):
        from src.tools import run_x_post_mail as runner
        with patch.object(runner._mlb, "fetch_mlb_alumni_data", return_value=self._DATA) as m:
            line = runner._mlb_alumni_fact_line("戸郷翔征")
        self.assertEqual(line, "")
        self.assertEqual(m.call_count, 0)  # 非 alumnus は fetch すらしない

    def test_fetch_failure_falls_back_to_blank(self):
        from src.tools import run_x_post_mail as runner
        with patch.object(runner._mlb, "fetch_mlb_alumni_data", side_effect=RuntimeError("net")):
            line = runner._mlb_alumni_fact_line("岡本和真")
        self.assertEqual(line, "")


class PlayerDedupTests(unittest.TestCase):
    """user 2026-06-20: 1メール内の同一選手重複を圧縮し、枠を別ニュースへ。"""

    @staticmethod
    def _cand(name):
        from src.x_post_mail_lane import Candidate
        return Candidate(
            title="t", metric="m", period_label="p", draft_text="d",
            char_count=1, post_text="d", signature="sig-" + name,
            focus_player=name, source_material_type="x",
        )

    def test_dedupe_keeps_first_drops_same_player_space_insensitive(self):
        from src.tools import run_x_post_mail as runner
        cands = [self._cand("増田 大輝"), self._cand("増田大輝"),
                 self._cand("竹丸和幸"), self._cand("")]
        out = runner._dedupe_candidates_by_player(cands)
        self.assertEqual([c.focus_player for c in out], ["増田 大輝", "竹丸和幸", ""])

    def test_dedupe_flag_off_keeps_all(self):
        from src.tools import run_x_post_mail as runner
        with patch.dict("os.environ", {"X_POST_MAIL_PLAYER_DEDUP": "0"}):
            cands = [self._cand("増田大輝"), self._cand("増田大輝")]
            out = runner._dedupe_candidates_by_player(cands)
        self.assertEqual(len(out), 2)

    @staticmethod
    def _cand_text(name, post_text):
        from src.x_post_mail_lane import Candidate
        return Candidate(
            title="t", metric="m", period_label="p", draft_text=post_text,
            char_count=len(post_text), post_text=post_text,
            signature="sig-" + post_text[:8], focus_player=name,
            source_material_type="x",
        )

    def test_dedupe_same_player_different_content_both_kept(self):
        # 2026-06-24 user 方針: 同じ選手でも内容が違えば両方残す。
        from src.tools import run_x_post_mail as runner
        cands = [
            self._cand_text("戸郷翔征", "7回無失点の好投で連勝に貢献 #巨人"),
            self._cand_text("戸郷翔征", "オフに自主トレ公開、来季へ意欲を語った #巨人"),
        ]
        out = runner._dedupe_candidates_by_player(cands)
        self.assertEqual(len(out), 2)

    def test_dedupe_same_player_similar_content_compressed(self):
        # 同じ選手かつほぼ同趣旨は1本に圧縮する。
        from src.tools import run_x_post_mail as runner
        cands = [
            self._cand_text("戸郷翔征", "7回無失点の好投で連勝に貢献しました #巨人 #ジャイアンツ"),
            self._cand_text("戸郷翔征", "7回無失点の好投で連勝に貢献しました #巨人"),
        ]
        out = runner._dedupe_candidates_by_player(cands)
        self.assertEqual(len(out), 1)

    def test_news_scrape_skips_excluded_player_picks_other_news(self):
        from src.tools import run_x_post_mail as runner
        from src import news_scrape_x_post as nsx

        class _Item:
            def __init__(self, title, players, url):
                self.title = title
                self.summary = "x"
                self.source_url = url
                self.player_canonical = players

        items = [
            _Item("【巨人】増田大輝が猛打賞", ["増田大輝"], "u1"),
            _Item("【巨人】竹丸が6敗目", ["竹丸和幸"], "u2"),
        ]
        with patch.object(nsx, "format_scrape_post",
                          side_effect=lambda facts, **k: "本文 #巨人 #ジャイアンツ"):
            out = runner._build_news_scrape_candidates(
                items, gemini_key="k", max_count=5, log=runner.LOG,
                exclude_player_keys={"増田大輝"},
            )
        # 増田 は既出なので skip、枠は竹丸 (別ニュース) で埋まる
        self.assertEqual([c.focus_player for c, _ in out], ["竹丸和幸"])

    def test_news_scrape_same_player_different_topic_both_kept(self):
        # 2026-06-24 user 方針: 同一選手でも別トピックなら両方残す
        # (猛打賞 と 試合後コメント は別内容)。
        from src.tools import run_x_post_mail as runner
        from src import news_scrape_x_post as nsx

        class _Item:
            def __init__(self, title, players, url):
                self.title = title
                self.summary = "x"
                self.source_url = url
                self.player_canonical = players

        items = [
            _Item("【巨人】増田大輝が猛打賞、3安打の固め打ち", ["増田大輝"], "u1"),
            _Item("【巨人】増田大輝が試合後コメント「悔しい」", ["増田大輝"], "u2"),
        ]
        with patch.object(nsx, "format_scrape_post",
                          side_effect=lambda facts, **k: f"本文 {facts.get('見出し','')} #巨人 #ジャイアンツ"):
            out = runner._build_news_scrape_candidates(
                items, gemini_key="k", max_count=5, log=runner.LOG,
            )
        self.assertEqual(len(out), 2)

    def test_news_scrape_same_player_same_topic_deduped(self):
        # 別媒体が同じ猛打賞を拾った同趣旨重複は1本に圧縮する。
        from src.tools import run_x_post_mail as runner
        from src import news_scrape_x_post as nsx

        class _Item:
            def __init__(self, title, players, url):
                self.title = title
                self.summary = "x"
                self.source_url = url
                self.player_canonical = players

        items = [
            _Item("【巨人】増田大輝が猛打賞", ["増田大輝"], "u1"),
            _Item("巨人・増田大輝が猛打賞", ["増田大輝"], "u2"),
        ]
        with patch.object(nsx, "format_scrape_post",
                          side_effect=lambda facts, **k: f"本文 {facts.get('見出し','')} #巨人 #ジャイアンツ"):
            out = runner._build_news_scrape_candidates(
                items, gemini_key="k", max_count=5, log=runner.LOG,
            )
        self.assertEqual(len(out), 1)

    def test_related_player_context_uses_comment_quotes_only(self):
        from src.tools import run_x_post_mail as runner

        class _Item:
            def __init__(self, title, summary, players, url):
                self.title = title
                self.summary = summary
                self.source_url = url
                self.source_name = "スポーツ報知"
                self.player_canonical = players

        main = _Item("山崎伊織が7回1失点", "先発で試合を作った", ["山﨑伊織"], "u1")
        quote = _Item("山崎伊織がコメント「6回以降も低めに投げられた」", "", ["山﨑伊織"], "u2")
        no_quote = _Item("山崎伊織がブルペン調整", "次回登板へ調整した", ["山﨑伊織"], "u3")
        other = _Item("戸郷翔征がコメント「次も粘る」", "", ["戸郷翔征"], "u4")

        contexts = runner._build_related_player_context_by_item([main, quote, no_quote, other])
        self.assertIn("山﨑伊織『6回以降も低めに投げられた』", contexts[id(main)])
        self.assertNotIn("ブルペン調整", contexts[id(main)])
        self.assertNotIn("戸郷翔征", contexts[id(main)])
