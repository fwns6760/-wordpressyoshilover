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

    def test_no_card_ranking_lines_in_draft(self):
        """2026-07-10 user「図が意味わからない」: draft に 437 カード用の
        ranking 行 format を入れない = カードが生成されないこと。"""
        from src.x_post_mail_lane import _extract_ranking_rows_from_draft

        c = self._build()
        self.assertEqual(_extract_ranking_rows_from_draft(c.draft_text), [])

    def test_categorized_trend_sections(self):
        c = self._build(trend_keywords={
            "giants": ["岡本和真"], "npb": ["阪神 先発"], "mlb": ["大谷翔平"],
        })
        self.assertIn("【検索トレンド/巨人】岡本和真", c.post_text)
        self.assertIn("【検索トレンド/プロ野球】阪神 先発", c.post_text)
        self.assertIn("【検索トレンド/メジャー】大谷翔平", c.post_text)

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


class RankingCardKillSwitchTests(unittest.TestCase):
    """2026-07-10 user「図いらないかも」: ranking 図解カードの env OFF。"""

    def test_env_off_skips_ranking_card(self):
        import os
        from unittest.mock import patch as _patch

        from src import x_post_mail_lane as lane

        cand = lane.Candidate(
            title="t", metric="AVG", period_label="p",
            draft_text="1位 岡本和真（巨人）.345 🟧巨人🟧",
            char_count=1,
        )
        with _patch.dict(os.environ, {"X_POST_RANKING_CARD_ENABLED": "0"}):
            self.assertIsNone(lane._generate_candidate_image_png(cand))

    def test_direct_player_photo_bytes_still_pass(self):
        import os
        from unittest.mock import patch as _patch

        from src import x_post_mail_lane as lane

        cand = lane.Candidate(
            title="t", metric="x_buzz_post", period_label="p",
            draft_text="", char_count=1, image_bytes=b"png-bytes",
        )
        with _patch.dict(os.environ, {"X_POST_RANKING_CARD_ENABLED": "0"}):
            self.assertEqual(
                lane._generate_candidate_image_png(cand), b"png-bytes"
            )
