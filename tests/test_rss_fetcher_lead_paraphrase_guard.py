import json
import os
import unittest
from unittest.mock import patch

from src import article_quality_guards, rss_fetcher


class BodyLeadParaphraseGuardTests(unittest.TestCase):
    SOURCE_URL = "https://example.com/source"
    SOURCE_NAME = "スポーツ報知"

    def _apply_guard(
        self,
        *,
        body_text: str,
        article_title: str,
        source_title: str,
        summary: str,
        category: str = "コラム",
        article_subtype: str = "social_news",
        flag_overrides: dict[str, str] | None = None,
        capture_logs: bool = False,
    ):
        env = dict(flag_overrides or {})
        with patch.dict(os.environ, env, clear=False):
            if capture_logs:
                with self.assertLogs("rss_fetcher", level="INFO") as cm:
                    guarded = rss_fetcher._maybe_apply_body_lead_paraphrase_guard(
                        body_text=body_text,
                        article_title=article_title,
                        source_title=source_title,
                        summary=summary,
                        category=category,
                        article_subtype=article_subtype,
                        source_name=self.SOURCE_NAME,
                        source_url=self.SOURCE_URL,
                        logger=rss_fetcher.logging.getLogger("rss_fetcher"),
                    )
                logs = [json.loads(record.getMessage()) for record in cm.records if record.getMessage().startswith("{")]
                return guarded, logs

            return rss_fetcher._maybe_apply_body_lead_paraphrase_guard(
                body_text=body_text,
                article_title=article_title,
                source_title=source_title,
                summary=summary,
                category=category,
                article_subtype=article_subtype,
                source_name=self.SOURCE_NAME,
                source_url=self.SOURCE_URL,
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            )

    def test_flag_off_keeps_existing_dup_reduction_behavior(self):
        article_title = "阿部監督が起用意図を説明した記事です"
        summary = "阿部監督が起用意図を説明した。若手起用への言及があった。"
        body = "\n".join(
            [
                "【ニュースの整理】",
                "阿部監督が起用意図を説明した記事です。",
                "若手起用への言及があった。",
                "【次の注目】",
                "次戦の起用に注目です。",
            ]
        )

        with patch.dict(os.environ, {"ENABLE_BODY_DUP_REDUCTION": "1"}, clear=False):
            baseline = rss_fetcher._maybe_reduce_body_intro_dup(
                body_text=body,
                article_title=article_title,
                article_subtype="social_news",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            )
            guarded = self._apply_guard(
                body_text=body,
                article_title=article_title,
                source_title=article_title,
                summary=summary,
                flag_overrides={"ENABLE_BODY_DUP_REDUCTION": "1"},
            )
            reduced = rss_fetcher._maybe_reduce_body_intro_dup(
                body_text=guarded,
                article_title=article_title,
                article_subtype="social_news",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            )

        self.assertEqual(guarded, body)
        self.assertEqual(reduced, baseline)
        self.assertNotIn("阿部監督が起用意図を説明した記事です。", reduced)

    def test_flag_on_excludes_title_ngrams_from_lead_first_sentence(self):
        article_title = "大城卓三、先制3号3ラン こどもの日の東京ドームで歓声"
        summary = "大城卓三が先制3号3ランを放った。五回二死一、二塁で右翼席へ運んだ。試合の流れを引き寄せた。"
        body = "\n".join(
            [
                "【ニュースの整理】",
                "大城卓三、先制3号3ラン こどもの日の東京ドームで歓声。",
                "試合の流れを引き寄せた。",
                "【次の注目】",
                "次の打席も注目です。",
            ]
        )

        guarded = self._apply_guard(
            body_text=body,
            article_title=article_title,
            source_title=article_title,
            summary=summary,
            flag_overrides={"ENABLE_BODY_LEAD_PARAPHRASE_GUARD": "1"},
        )

        lead_line = rss_fetcher._first_body_content_line(guarded)
        self.assertNotEqual(lead_line, "大城卓三、先制3号3ラン こどもの日の東京ドームで歓声。")
        self.assertLess(rss_fetcher._body_dup_reduction_ngram_overlap(article_title, lead_line), 0.55)

    def test_flag_on_keeps_quote_based_lead_when_only_quote_available(self):
        article_title = "阿部監督「若手を使う」構想を示す"
        summary = "阿部監督「若手を使う」構想を示す"
        body = "\n".join(
            [
                "【発言の要旨】",
                "阿部監督が「若手を使う」と話した。",
                "【次の注目】",
                "次の起用に注目です。",
            ]
        )

        guarded = self._apply_guard(
            body_text=body,
            article_title=article_title,
            source_title=article_title,
            summary=summary,
            category="首脳陣",
            article_subtype="manager",
            flag_overrides={"ENABLE_BODY_LEAD_PARAPHRASE_GUARD": "1"},
        )

        self.assertEqual(guarded, body)

    def test_flag_on_does_not_break_body_dup_reduction_post_process(self):
        article_title = "大城卓三、先制3号3ラン こどもの日の東京ドームで歓声"
        summary = "大城卓三が先制3号3ランを放った。五回二死一、二塁で右翼席へ運んだ。試合の流れを引き寄せた。"
        body = "\n".join(
            [
                "【ニュースの整理】",
                "大城卓三、先制3号3ラン こどもの日の東京ドームで歓声。",
                "試合の流れを引き寄せた。",
                "【次の注目】",
                "次の打席も注目です。",
            ]
        )

        with patch.dict(
            os.environ,
            {
                "ENABLE_BODY_LEAD_PARAPHRASE_GUARD": "1",
                "ENABLE_BODY_DUP_REDUCTION": "1",
            },
            clear=False,
        ):
            guarded = self._apply_guard(
                body_text=body,
                article_title=article_title,
                source_title=article_title,
                summary=summary,
                flag_overrides={
                    "ENABLE_BODY_LEAD_PARAPHRASE_GUARD": "1",
                    "ENABLE_BODY_DUP_REDUCTION": "1",
                },
            )
            reduced = rss_fetcher._maybe_reduce_body_intro_dup(
                body_text=guarded,
                article_title=article_title,
                article_subtype="social_news",
                logger=rss_fetcher.logging.getLogger("rss_fetcher"),
            )

        self.assertEqual(reduced, guarded)
        self.assertIsNone(rss_fetcher.find_duplicate_sentence(reduced))

    def test_flag_on_emits_structured_log(self):
        article_title = "大城卓三、先制3号3ラン こどもの日の東京ドームで歓声"
        summary = "大城卓三が先制3号3ランを放った。五回二死一、二塁で右翼席へ運んだ。試合の流れを引き寄せた。"
        body = "\n".join(
            [
                "【ニュースの整理】",
                "大城卓三、先制3号3ラン こどもの日の東京ドームで歓声。",
                "試合の流れを引き寄せた。",
                "【次の注目】",
                "次の打席も注目です。",
            ]
        )

        guarded, logs = self._apply_guard(
            body_text=body,
            article_title=article_title,
            source_title=article_title,
            summary=summary,
            flag_overrides={"ENABLE_BODY_LEAD_PARAPHRASE_GUARD": "1"},
            capture_logs=True,
        )

        payload = [entry for entry in logs if entry.get("event") == "body_lead_paraphrase_avoided"][0]
        self.assertEqual(payload["source_url"], self.SOURCE_URL)
        self.assertEqual(payload["subtype"], "social_news")
        self.assertTrue(payload["title_ngrams_excluded"])
        lead_sentence = rss_fetcher._body_dup_reduction_sentence_units(
            rss_fetcher._first_body_content_line(guarded)
        )[0]
        self.assertEqual(payload["body_lead_length"], len(lead_sentence))

    def test_flag_on_does_not_relax_validator_threshold(self):
        self.assertEqual(article_quality_guards.find_duplicate_sentence.__defaults__, (0.9,))

        issue = article_quality_guards.find_duplicate_sentence(
            "\n".join(
                [
                    "【試合結果】",
                    "巨人が阪神に3-2で勝利した。",
                    "【ハイライト】",
                    "巨人が阪神に3-2で勝利した。",
                ]
            )
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue["reason"], "near_duplicate_sentence")


if __name__ == "__main__":
    unittest.main()
