"""3アカウント定期分析ツールの単体テスト (RSSHub fetch は fixture で mock)。"""
from __future__ import annotations

import unittest

from src.tools import run_rival_account_analysis as ra


_FEED = (
    "<rss><channel>"
    "<item><title>坂本勇人 サヨナラ満塁ホームラン</title>"
    "<description>劇的な一打だわ。次は2番でいいと思う &lt;img src=&quot;https://pbs.twimg.com/amplify_video_thumb/1/a.jpg&quot;&gt;</description>"
    "<pubDate>Mon, 01 Jun 2026 09:00:00 GMT</pubDate></item>"
    "<item><title>RT 誰か: 拡散希望</title><description>RT something</description>"
    "<pubDate>Mon, 01 Jun 2026 08:50:00 GMT</pubDate></item>"
    "</channel></rss>"
)


class AnalyzeAccountTests(unittest.TestCase):
    def test_counts_format_and_rapid(self):
        a = ra.analyze_account("dummy", fetch=lambda h: _FEED)
        self.assertEqual(a["n"], 2)
        self.assertEqual(a["rt"], 1)          # RT 1 件
        self.assertEqual(a["vid"], 1)         # 動画サムネ 1
        self.assertEqual(a["own"], 1)         # 本人投稿 1
        self.assertEqual(a["rapid"], 1)       # 10分差 = 連投
        self.assertIn("だわ", a["enders"])    # 語尾検出
        self.assertEqual(a["rt_pct"], 50)     # 2件中1RT

    def test_fetch_failure_returns_empty(self):
        def boom(h):
            raise RuntimeError("down")
        self.assertEqual(ra.analyze_account("x", fetch=boom), {})


class RenderReportTests(unittest.TestCase):
    def test_report_has_table_and_signal(self):
        a = ra.analyze_account("dummy", fetch=lambda h: _FEED)
        report = ra.render_report([("缶詰", "h", "辛口", a)], date_label="2026-06")
        self.assertIn("定期分析 (2026-06)", report)
        self.assertIn("| アカウント |", report)
        self.assertIn("見るべき signal", report)
        self.assertIn("缶詰", report)


class RecipientsTests(unittest.TestCase):
    def test_override_wins(self):
        self.assertEqual(ra._resolve_recipients(["a@b.com"]), ["a@b.com"])

    def test_env_fallback(self):
        import os
        old = os.environ.get("MAIL_BRIDGE_TO")
        os.environ["MAIL_BRIDGE_TO"] = "x@y.com, z@w.com"
        try:
            self.assertEqual(ra._resolve_recipients(None), ["x@y.com", "z@w.com"])
        finally:
            if old is None:
                del os.environ["MAIL_BRIDGE_TO"]
            else:
                os.environ["MAIL_BRIDGE_TO"] = old


if __name__ == "__main__":
    unittest.main()
