"""CARE LAND 発達障害・福祉ニュース版レーンのテスト。

ネットワーク・WordPress・Gemini を叩かず、判定/メール/承認ボタン/重複/週次を検証する。
特に「AIが自動投稿・自動公開しない」設計をアサートする。
"""

from __future__ import annotations

from datetime import datetime
import os
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src import careland_news_judgment as judge
from src.careland_news_article import build_article_draft, decide_index
from src.tools import careland_news_sns_candidates as cnc

JST = ZoneInfo("Asia/Tokyo")


class JudgmentFallbackTest(unittest.TestCase):
    def test_official_change_defaults_to_x_article(self):
        v = judge.fallback_verdict(
            title="障害福祉サービス等報酬改定について（通知）", summary="",
            source_name="厚生労働省", url="https://www.mhlw.go.jp/x.html",
            lane="official_change", lane_label="制度・行政・公式発表",
            default_decision="x_article",
        )
        self.assertEqual(v.decision, "x_article")
        self.assertEqual(v.source, "fallback")

    def test_medical_trigger_forces_hold(self):
        v = judge.fallback_verdict(
            title="この薬で発達障害が治る？診断の最新事情", summary="治療効果を解説",
            source_name="某メディア", url="https://example.test/a",
            lane="welfare_media", lane_label="福祉専門メディア",
            default_decision="x_only",
        )
        self.assertEqual(v.decision, "hold")
        self.assertTrue(v.risk_flags)

    def test_risk_trigger_forces_hold(self):
        v = judge.fallback_verdict(
            title="炎上覚悟で物申す差別問題", summary="",
            source_name="某ブログ", url="https://example.test/b",
            lane="welfare_media", lane_label="福祉専門メディア",
            default_decision="x_only",
        )
        self.assertEqual(v.decision, "hold")

    def test_judge_news_without_api_key_uses_fallback(self):
        v = judge.judge_news(
            title="放課後等デイサービスの基準改正", summary="",
            source_name="厚労省", url="https://www.mhlw.go.jp/y.html",
            lane="official_change", lane_label="制度・行政・公式発表",
            default_decision="x_article", api_key="",
        )
        self.assertEqual(v.source, "fallback")
        self.assertEqual(v.decision, "x_article")


class ArticleBuilderTest(unittest.TestCase):
    def _verdict(self, decision="x_article", flags=()):
        return judge.NewsVerdict(
            decision=decision, reason="r", audience="当事者", what_changes="未確定",
            where_to_check="公式", official_url="https://www.mhlw.go.jp/z.html",
            risk_flags=flags, x_post_text="落ち着いた文案", article_title="改正のお知らせ",
        )

    def test_article_has_required_sections_and_no_transcription(self):
        draft = build_article_draft(
            verdict=self._verdict(), title="障害者雇用の法定雇用率引き上げ", summary="",
            source_name="厚生労働省", url="https://www.mhlw.go.jp/z.html",
            lane="official_change", lane_label="制度・行政・公式発表",
            breaking_id=55, category_map={"障害者雇用": 56, "制度": 58},
            default_index=False, slug_hint="careland-news-x",
        )
        # yoshilover（のもとけ）と同じ構造のブロックがそろっていること。
        for section in ["nomotoke-news-banner", "CARE LAND NEWS", "nomotoke-lead",
                        "nomotoke-trust-badge", "引用記事", "出典記事",
                        "nomotoke-card-footer", "コメントする", "ご注意"]:
            self.assertIn(section, draft.content)
        # careland では「ファンの声」は出さない。生RSS HTML も漏らさない。
        self.assertNotIn("ファンの声", draft.content)
        self.assertNotIn("news.google.com", draft.content)
        self.assertNotIn("&lt;a", draft.content)
        self.assertIn("断定するものではありません", draft.content)
        self.assertIn(55, draft.category_ids)
        self.assertIn(56, draft.category_ids)  # 障害者雇用

    def test_index_decision(self):
        self.assertTrue(decide_index(self._verdict("x_article"), default_index=False))
        self.assertFalse(decide_index(self._verdict("hold"), default_index=True))
        self.assertFalse(decide_index(self._verdict("x_article", flags=("注意",)), default_index=True))
        self.assertFalse(decide_index(self._verdict("x_only"), default_index=False))


class MailComposeTest(unittest.TestCase):
    def _candidate(self, decision="x_article", post_id=123):
        v = judge.NewsVerdict(decision=decision, audience="当事者", x_post_text="文案")
        return cnc.CarelandCandidate(
            source_id="s", source_name="厚労省", post_lane="official_change",
            lane_label="制度・行政・公式発表", default_decision="x_article",
            title="報酬改定の通知", url="https://www.mhlw.go.jp/a.html", summary="",
            score=88, priority="P0", dedupe_key="abc123", verdict=v,
            post_id=post_id, want_index=True,
        )

    def test_buttons_point_to_wordpress_login_required_approval(self):
        stats = cnc.fnc.FinanceBuildStats(loaded_sources=1)
        _, text, html, _imgs = cnc.compose_mail(
            [self._candidate()], now=datetime(2026, 6, 24, 12, 0, tzinfo=JST),
            stats=stats, wp_admin_base="https://careland.org",
        )
        for label in ["𝕏 投稿画面を開く", "記事公開（index）", "noindex公開", "非公開化",
                      "週次まとめに入れる", "WordPressで編集"]:
            self.assertIn(label, html)
        # 公開系は WordPress(ログイン必須)の確認画面 admin-post.php を開く
        self.assertIn("/wp-admin/admin-post.php?action=careland_news_confirm", html)
        self.assertIn("mode=publish_index", html)
        self.assertIn("mode=publish_noindex", html)
        self.assertIn("mode=unpublish", html)
        # Cloud Run の公開エンドポイントは使わない
        self.assertNotIn("/careland/action", html)
        # 自動投稿・自動公開しないことの明示
        self.assertIn("AIは公開・投稿しません", text)
        self.assertIn("自動公開・自動投稿はしません", html)
        # Xポストはクライアント側 (twitter intent)
        self.assertIn("twitter.com/intent/tweet", html)
        # yoshilover 体裁のメール（緑テーブル + 帯）。CARE LAND ブランドは出さない。
        self.assertNotIn("CARE LAND", html)
        self.assertIn("発達障害・福祉ニュース", html)
        self.assertIn("@nananana43219", html)

    def test_no_publish_buttons_without_wp_admin_base(self):
        stats = cnc.fnc.FinanceBuildStats(loaded_sources=1)
        _, _, html, _imgs = cnc.compose_mail(
            [self._candidate()], now=datetime(2026, 6, 24, 12, 0, tzinfo=JST),
            stats=stats, wp_admin_base=None,
        )
        # WP URL 無し → 公開系ボタンは出さない（X投稿画面のみ）
        self.assertNotIn("記事公開（index）", html)
        self.assertIn("𝕏 投稿画面を開く", html)


class BuildCandidatesRoutingTest(unittest.TestCase):
    def test_decisions_routed_by_lane_without_network_or_ai(self):
        # collect_raw_items をモックして、固定の生 item を返す
        sample = [
            (cnc.fnc.FinanceSource(id="mhlw", name="厚労省", market="JP", kind="rss",
                                   url="https://www.mhlw.go.jp/", priority="P0",
                                   post_lane="official_change", score_base=88),
             {"source_id": "mhlw", "source_name": "厚労省", "market": "JP",
              "post_lane": "official_change",
              "title": "障害福祉サービス等報酬改定の通知", "url": "https://www.mhlw.go.jp/a.html",
              "summary": "", "published": ""}),
            (cnc.fnc.FinanceSource(id="media", name="福祉新聞", market="JP", kind="rss",
                                   url="https://www.fukushishimbun.co.jp/", priority="P2",
                                   post_lane="welfare_media", score_base=62,
                                   include_keywords=("障害",)),
             {"source_id": "media", "source_name": "福祉新聞", "market": "JP",
              "post_lane": "welfare_media",
              "title": "障害者就労支援の現場ルポ", "url": "https://www.fukushishimbun.co.jp/b",
              "summary": "", "published": ""}),
        ]
        with tempfile.TemporaryDirectory() as d:
            ledger = os.path.join(d, "ledger.jsonl")
            with patch.object(cnc.fnc, "collect_raw_items", return_value=sample):
                result = cnc.build_candidates(
                    now=datetime(2026, 6, 24, 12, 0, tzinfo=JST),
                    ledger_path=ledger, run_judgment=True, api_key="",  # fallback
                    minimum_score=0,
                )
        by_lane = {c.post_lane: c.decision for c in result.candidates}
        self.assertEqual(by_lane.get("official_change"), "x_article")
        self.assertEqual(by_lane.get("welfare_media"), "x_only")


if __name__ == "__main__":
    unittest.main()
