"""Tests for 382 stale content date skip (pro baseball 鮮度).

User spec (2026-05-18 lock):
- relative keyword (昨日 / 昨夜 / 前日 / 前夜 / 先日 / 凱旋 / 翌朝) → skip
- absolute date (M月N日 / M/N / N日) で today より前 → skip
- 対象 category = 試合速報 / 選手情報 / 首脳陣
- program / event 告知 (future date) は keep
- same day (今日) は keep

受け入れ条件 (4 件):
1. 5/18 19:00 に「5/17朝」 系 post 来ない
2. 当日 (5/18) 試合 / 練習 / コメント は来る
3. program / event 告知 (「7/17 イベント」) は来る (future)
4. milestone は当日達成なら来る、 過去 reference は来ない
"""

from __future__ import annotations

import datetime as _dt
import unittest

from src import rss_fetcher


JST = _dt.timezone(_dt.timedelta(hours=9))


def _today(year: int = 2026, month: int = 5, day: int = 18, hour: int = 19) -> _dt.datetime:
    """Fixed `now` for deterministic testing。 default = 5/18 19:00 JST。"""
    return _dt.datetime(year, month, day, hour, 0, tzinfo=JST)


class StaleContentDateAbsoluteTests(unittest.TestCase):
    """`_is_stale_absolute_date` direct tests。"""

    def test_yesterday_M月N日_returns_true(self):
        """受け入れ 1: 5/18 に 「5月17日」 表記 → True (skip)."""
        self.assertTrue(rss_fetcher._is_stale_absolute_date(
            "5月17日朝の試合結果",
            now=_today(),
        ))

    def test_yesterday_M_slash_N_returns_true(self):
        """5/18 に 「5/17」 slash 表記 → True (skip)."""
        self.assertTrue(rss_fetcher._is_stale_absolute_date(
            "5/17のサヨナラ弾を振り返る",
            now=_today(),
        ))

    def test_yesterday_standalone_N日_returns_true(self):
        """5/18 に 「17日」 単独 (同月内) → True (skip)."""
        self.assertTrue(rss_fetcher._is_stale_absolute_date(
            "17日の試合は接戦だった",
            now=_today(),
        ))

    def test_today_same_day_returns_false(self):
        """受け入れ 2: 5/18 に 「5月18日」 → False (same day, keep)."""
        self.assertFalse(rss_fetcher._is_stale_absolute_date(
            "5月18日 18時から試合開始",
            now=_today(),
        ))

    def test_future_date_returns_false(self):
        """受け入れ 3: 5/18 に 「7月17日 イベント」 → False (future, keep)."""
        self.assertFalse(rss_fetcher._is_stale_absolute_date(
            "7月17日 ファン感謝デー開催",
            now=_today(),
        ))

    def test_future_month_slash_returns_false(self):
        """5/18 に 「7/17」 → False (future)."""
        self.assertFalse(rss_fetcher._is_stale_absolute_date(
            "7/17 イベント告知",
            now=_today(),
        ))

    def test_no_date_returns_false(self):
        """日付 keyword 無し → False (keep)."""
        self.assertFalse(rss_fetcher._is_stale_absolute_date(
            "戸郷翔征が好投で勝利",
            now=_today(),
        ))

    def test_historical_year_reference_not_skipped(self):
        """382 fix: 「2019年5月17日」 等の歴史 reference は skip しない。

        spec §副作用想定 #3 で「year 一致 check 必要」 と書かれた既知 gap を
        fix。 year が current year (2026) でなければ skip 対象外。
        """
        self.assertFalse(rss_fetcher._is_stale_absolute_date(
            "2019年5月17日に達成した記録",
            now=_today(),
        ))

    def test_current_year_explicit_pastdate_still_skipped(self):
        """current year explicit + past date → skip 維持 (false-skip 防止が
        歴史 reference のみであることを verify)."""
        self.assertTrue(rss_fetcher._is_stale_absolute_date(
            "2026年5月17日 戸郷好投",
            now=_today(),
        ))


class StaleContentDateRelativeTests(unittest.TestCase):
    """既存 relative keyword (回帰確認)."""

    def test_relative_yesterday_skip(self):
        self.assertTrue(rss_fetcher._should_skip_prior_event_postgame(
            "試合速報", "昨日の試合を振り返る", "", True, now=_today(),
        ))

    def test_relative_凱旋_skip(self):
        self.assertTrue(rss_fetcher._should_skip_prior_event_postgame(
            "選手情報", "巨人・吉川が地元凱旋", "", True, now=_today(),
        ))


class StaleContentDateCategoryGateTests(unittest.TestCase):
    """受け入れ 3: program / event 告知系は category gate で除外される確認."""

    def test_program_category_excluded(self):
        """category=program で過去日付があっても skip しない。"""
        # 試合速報 / 選手情報 / 首脳陣 以外は通る
        self.assertFalse(rss_fetcher._should_skip_prior_event_postgame(
            "program", "5月17日 イベント告知", "", True, now=_today(),
        ))

    def test_event_category_excluded(self):
        self.assertFalse(rss_fetcher._should_skip_prior_event_postgame(
            "general", "7月17日 ファン感謝デー", "", True, now=_today(),
        ))

    def test_target_category_pastday_skipped(self):
        """category=試合速報 + past date → skip"""
        self.assertTrue(rss_fetcher._should_skip_prior_event_postgame(
            "試合速報", "5月17日朝の試合", "", True, now=_today(),
        ))

    def test_target_category_sameday_kept(self):
        """category=試合速報 + same day → keep"""
        self.assertFalse(rss_fetcher._should_skip_prior_event_postgame(
            "試合速報", "5月18日の試合は接戦", "", True, now=_today(),
        ))


class StaleContentDateAcceptanceScenariosTests(unittest.TestCase):
    """spec acceptance condition 4 件を end-to-end scenario で確認."""

    def test_acceptance_1_yesterday_morning_post_skipped(self):
        """受け入れ 1: 5/18 19:00 で「5月17日朝」 系 post 来ない"""
        self.assertTrue(rss_fetcher._should_skip_prior_event_postgame(
            "試合速報",
            "5月17日朝のサヨナラ勝ちを振り返る",
            "前日の戸郷好投を分析",
            True,
            now=_today(),
        ))

    def test_acceptance_2_today_game_kept(self):
        """受け入れ 2: 当日 (5/18) の試合 / 練習 / コメント記事は来る"""
        # absolute date 無し / relative keyword 無し → keep
        self.assertFalse(rss_fetcher._should_skip_prior_event_postgame(
            "試合速報",
            "戸郷翔征が今日も先発予定",
            "山崎伊織は中継ぎ調整",
            True,
            now=_today(),
        ))

    def test_acceptance_3_future_event_kept(self):
        """受け入れ 3: program / event 告知 (future date) は来る"""
        # category=program 経路、 future date OK
        self.assertFalse(rss_fetcher._should_skip_prior_event_postgame(
            "program",
            "7月17日 イベント告知",
            "",
            True,
            now=_today(),
        ))

    def test_acceptance_4a_milestone_today_kept(self):
        """受け入れ 4 (前半): 当日達成 milestone は来る"""
        # same day date → keep
        self.assertFalse(rss_fetcher._should_skip_prior_event_postgame(
            "試合速報",
            "戸郷翔征 通算 150 勝達成",
            "5月18日 達成",
            True,
            now=_today(),
        ))

    def test_acceptance_4b_milestone_past_reference_skipped(self):
        """受け入れ 4 (後半): 過去 milestone reference は来ない (現実装の挙動)"""
        # 「5月17日達成」 → past day → skip
        self.assertTrue(rss_fetcher._should_skip_prior_event_postgame(
            "試合速報",
            "戸郷翔征 通算 150 勝達成",
            "5月17日に達成した",
            True,
            now=_today(),
        ))


if __name__ == "__main__":
    unittest.main()
