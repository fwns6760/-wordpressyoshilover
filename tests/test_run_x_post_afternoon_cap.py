"""_quota_tail_llm_cap (2026-07-11 無料枠尻尾の午後絞り) の unit test。"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.tools import run_x_post_mail as rxm

_JST = timezone(timedelta(hours=9))


def _at(hour: int) -> datetime:
    return datetime(2026, 7, 11, hour, 30, tzinfo=_JST)


class QuotaTailLlmCapTests(unittest.TestCase):
    def test_outside_band_unchanged(self):
        for hour in (0, 7, 11, 16, 18, 23):
            self.assertEqual(
                rxm._quota_tail_llm_cap(
                    20, _at(hour), env_name="X_POST_MAIL_AFTERNOON_LLM_CAP", default_cap=8
                ),
                20,
                f"hour={hour} should be untouched",
            )

    def test_inside_band_capped(self):
        for hour in (12, 13, 14, 15):
            self.assertEqual(
                rxm._quota_tail_llm_cap(
                    20, _at(hour), env_name="X_POST_MAIL_AFTERNOON_LLM_CAP", default_cap=8
                ),
                8,
                f"hour={hour} should be capped",
            )

    def test_inside_band_smaller_budget_kept(self):
        # 既に cap 以下の予算は増やさない
        self.assertEqual(
            rxm._quota_tail_llm_cap(
                4, _at(13), env_name="X_POST_MLB_AFTERNOON_MAX", default_cap=8
            ),
            4,
        )

    def test_unlimited_or_disabled_budget_untouched(self):
        self.assertEqual(
            rxm._quota_tail_llm_cap(
                0, _at(13), env_name="X_POST_MAIL_AFTERNOON_LLM_CAP", default_cap=8
            ),
            0,
        )

    def test_env_zero_disables_squeeze(self):
        with patch.dict("os.environ", {"X_POST_MAIL_AFTERNOON_LLM_CAP": "0"}):
            self.assertEqual(
                rxm._quota_tail_llm_cap(
                    20, _at(13), env_name="X_POST_MAIL_AFTERNOON_LLM_CAP", default_cap=8
                ),
                20,
            )

    def test_env_override_cap(self):
        with patch.dict("os.environ", {"X_POST_MAIL_AFTERNOON_LLM_CAP": "5"}):
            self.assertEqual(
                rxm._quota_tail_llm_cap(
                    20, _at(14), env_name="X_POST_MAIL_AFTERNOON_LLM_CAP", default_cap=8
                ),
                5,
            )


if __name__ == "__main__":
    unittest.main()
