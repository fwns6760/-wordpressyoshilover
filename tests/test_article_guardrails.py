import logging
import unittest

from src import rss_fetcher


class ArticleGuardrailTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test_article_guardrails")

    def test_article_with_unverified_number_falls_back(self):
        article = "【ニュースの整理】\n巨人は防御率1.23の投手が支えました。"
        guarded = rss_fetcher._apply_article_guardrails(
            "巨人が勝利",
            "先発が好投した。",
            "試合速報",
            article,
            True,
            self.logger,
        )
        self.assertIn("【ニュースの整理】", guarded)
        self.assertIn("みなさんの意見はコメントで教えてください！", guarded)
        self.assertNotIn("1.23", guarded)

    def test_non_game_article_cannot_introduce_score(self):
        article = "■選手情報の整理\nこの話題は3-2の勝利でさらに注目されました。"
        guarded = rss_fetcher._apply_article_guardrails(
            "阿部監督がコメント",
            "阿部監督が起用方針について語った。",
            "首脳陣",
            article,
            False,
            self.logger,
        )
        self.assertNotIn("3-2", guarded)
        self.assertIn("【ニュースの整理】", guarded)
        self.assertIn("整理すると、今回のニュースは3点です。", guarded)
        self.assertIn("結果次第で序列や役割を動かす前提が見えてきた", guarded)

    def test_fake_citation_triggers_fallback(self):
        article = "【ニュースの整理】\n今季は上昇傾向です（npb.jp）。"
        guarded = rss_fetcher._apply_article_guardrails(
            "巨人の近況",
            "チーム状態が上向いている。",
            "コラム",
            article,
            True,
            self.logger,
        )
        self.assertNotIn("npb.jp", guarded)
        self.assertIn("ニュースの整理", guarded)
        self.assertIn("ここでは元記事の事実を土台に論点を整理しました", guarded)

    def test_pregame_article_cannot_claim_final_result(self):
        article = "【ニュースの整理】\n14日の阪神戦で、巨人の則本昂大投手が移籍後初勝利を飾りました。"
        guarded = rss_fetcher._apply_article_guardrails(
            "【巨人】則本昂大、甲子園で12年ぶり先発",
            "巨人の則本昂大投手が14日の阪神戦で移籍後初勝利を狙う。",
            "試合速報",
            article,
            True,
            self.logger,
        )
        self.assertNotIn("勝利を飾りました", guarded)
        self.assertIn("この登板や試合前の空気が実際の結果にどうつながるか", guarded)
        self.assertIn("結果が出る前の記事だからこそ", guarded)
        self.assertGreater(len(guarded), 250)

    def test_safe_article_passes(self):
        article = "【ニュースの整理】\n巨人が勝利しました。\n【試合のポイント】\n先発が好投しました。"
        guarded = rss_fetcher._apply_article_guardrails(
            "巨人が勝利",
            "先発が好投した。",
            "試合速報",
            article,
            True,
            self.logger,
        )
        self.assertEqual(article, guarded)

    def test_offday_player_article_can_keep_source_based_farm_result(self):
        article = "【ニュースの整理】\n前日12日の2軍DeNA戦では7回4安打1失点と好投した。"
        guarded = rss_fetcher._apply_article_guardrails(
            "【巨人】大胆フォーム変更の戸郷翔征",
            "ファームで調整中の戸郷翔征投手が前日12日の2軍DeNA戦で7回4安打1失点と好投した。",
            "選手情報",
            article,
            False,
            self.logger,
        )
        self.assertEqual(article, guarded)

    def test_game_article_keeps_source_based_dates_scores_and_stats(self):
        article = (
            "【ニュースの整理】\n"
            "4月16日の阪神戦で巨人は3-1で勝利した。\n"
            "【試合のポイント】\n"
            "田中将大投手は9回2失点で4勝8敗、防御率2.50となった。吉川尚輝は打率.285で2回に先制打を放った。阿部監督は20分間ベンチで動きを確認した。"
        )
        guarded = rss_fetcher._apply_article_guardrails(
            "【巨人】4/16阪神戦は3-1で勝利",
            "2026年4月16日の阪神戦で巨人は3-1で勝利した。田中将大投手は9回2失点で4勝8敗、防御率2.50。吉川尚輝は打率.285で2回に先制打を放った。阿部監督は２０分間ベンチで動きを確認した。",
            "試合速報",
            article,
            True,
            self.logger,
        )
        self.assertEqual(article, guarded)

    def test_game_article_with_source_missing_number_falls_back(self):
        article = (
            "【ニュースの整理】\n"
            "4月17日の阪神戦で巨人は5-0で勝利した。\n"
            "【試合のポイント】\n"
            "田中将大投手は9回2失点で4勝8敗、防御率2.50となった。"
        )
        guarded = rss_fetcher._apply_article_guardrails(
            "【巨人】4/16阪神戦は3-1で勝利",
            "2026年4月16日の阪神戦で巨人は3-1で勝利した。田中将大投手は9回2失点で4勝8敗、防御率2.50。",
            "試合速報",
            article,
            True,
            self.logger,
        )
        self.assertIn("【ニュースの整理】", guarded)
        self.assertIn("みなさんの意見はコメントで教えてください！", guarded)
        self.assertNotIn("5-0", guarded)
        self.assertNotIn("4月17日", guarded)


if __name__ == "__main__":
    unittest.main()
