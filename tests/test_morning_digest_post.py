"""morning_digest_post — 毎朝の巨人データ定点ポスト (2026-07-10)。"""

import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src import morning_digest_post as mdp

JST = timezone(timedelta(hours=9))
_NOW = datetime(2026, 7, 10, 8, 0, tzinfo=JST)

_BUZZ = {"岡本和真": 12, "泉口友汰": 8, "戸郷翔征": 5, "キャベッジ": 3}
_TRENDS = ["オールスター", "岡本和真"]


class BuildTests(unittest.TestCase):
    def _build(self, **kw):
        kw.setdefault("now", _NOW)
        kw.setdefault("buzz_counts", dict(_BUZZ))
        kw.setdefault("trend_keywords", list(_TRENDS))
        kw.setdefault("dedup_set", set())
        return mdp.build_morning_digest_candidate(**kw)

    def test_builds_ranking_post(self):
        c = self._build()
        self.assertIsNotNone(c)
        self.assertEqual(c.metric, "MORNING_DIGEST")
        self.assertIn("1位 岡本和真", c.post_text)
        self.assertIn("4位 キャベッジ", c.post_text)
        self.assertIn("オールスター", c.post_text)
        self.assertIn("7/10(金)", c.post_text)
        self.assertIn("8時の巨人データ定点観測", c.post_text)
        self.assertTrue(c.post_text.startswith("おはようございます。"))
        # 言及件数の生数字は post 本文には出さない (card/draft のみ)
        self.assertNotIn("言及12件", c.post_text)
        self.assertEqual(c.focus_player, "岡本和真")

    def test_card_ranking_lines_parse(self):
        """draft の ranking 行が 437 カード生成の parser に乗ること。"""
        from src.x_post_mail_lane import _extract_ranking_rows_from_draft

        c = self._build()
        rows = _extract_ranking_rows_from_draft(c.draft_text)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["name"], "岡本和真")
        self.assertTrue(rows[0]["is_giants"])
        self.assertEqual(rows[0]["value"], "言及12件")

    def test_fewer_than_three_names_skips(self):
        self.assertIsNone(self._build(buzz_counts={"岡本和真": 5, "泉口友汰": 2}))

    def test_dedup_once_per_hour(self):
        sig = "morndigest|" + hashlib.sha1(b"20260710-08").hexdigest()[:16]
        self.assertIsNone(self._build(dedup_set={sig}))

    def test_next_hour_fires_again(self):
        sig = "morndigest|" + hashlib.sha1(b"20260710-07").hexdigest()[:16]
        self.assertIsNotNone(self._build(dedup_set={sig}))

    def test_no_llm_key_uses_deterministic_close(self):
        c = self._build(gemini_api_key="")
        self.assertIn("岡本和真", c.post_text.splitlines()[-1])

    def test_llm_comment_used_when_available(self):
        with patch.object(mdp, "_build_digest_comment", return_value="読み解きの一言。"):
            c = self._build(gemini_api_key="k")
        self.assertTrue(c.post_text.endswith("読み解きの一言。"))


if __name__ == "__main__":
    unittest.main()
