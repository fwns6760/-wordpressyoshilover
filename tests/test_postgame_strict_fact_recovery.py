import json
import logging
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src import rss_fetcher
from src.postgame_strict_fact_recovery import ENABLE_POSTGAME_STRICT_FACT_RECOVERY_ENV
from src.postgame_strict_template import POSTGAME_STRICT_FEATURE_FLAG_ENV


JST = ZoneInfo("Asia/Tokyo")


def _payload(
    *,
    result: str,
    opponent: str | None = None,
    game_date: str | None = None,
    giants_score: int | None = None,
    opponent_score: int | None = None,
    manager_comment: str = "試合後のコメントを整理した。",
) -> dict:
    return {
        "game_date": game_date,
        "opponent": opponent,
        "giants_score": giants_score,
        "opponent_score": opponent_score,
        "result": result,
        "starter_name": None,
        "starter_innings": None,
        "starter_hits": None,
        "starter_runs": None,
        "key_events": [],
        "manager_comment": manager_comment,
        "next_game_info": {},
        "confidence": "high",
        "evidence_text": [],
    }


FIXTURES = {
    "202605020001031": {
        "title": "【巨人】9回2発の反撃も届かず 阪神戦を振り返る",
        "summary": "阿部監督が試合後に内容を振り返った。",
        "source_url": "https://www.nikkansports.com/baseball/news/202605020001031.html",
        "published_at": datetime(2026, 5, 2, 22, 10, tzinfo=JST),
        "payload": _payload(result="loss", opponent="阪神", opponent_score=7),
        "fetched_text": "\n".join(
            [
                "＜阪神7－5巨人＞◇2日◇甲子園",
                "5回に吉川尚輝の適時二塁打で追い上げた。",
                "9回に岡本和真の8号ソロで反撃した。",
            ]
        ),
        "expect_fetch": True,
        "body_checks": ("2026年5月2日の阪神戦", "巨人が5-7で敗戦", "適時打"),
        "expect_success": True,
    },
    "202605020001323": {
        "title": "巨人は阪神に敗れ 阿部監督が試合後に振り返る",
        "summary": "阿部監督が試合後に反撃の場面を振り返った。",
        "source_url": "https://www.nikkansports.com/baseball/news/202605020001323.html",
        "published_at": datetime(2026, 5, 2, 23, 0, tzinfo=JST),
        "payload": _payload(result="loss", opponent="阪神"),
        "fetched_text": "\n".join(
            [
                "＜阪神7－5巨人＞◇2日◇甲子園",
                "阿部監督は9回の反撃について振り返った。",
                "吉川尚輝の適時打と岡本和真の8号ソロが出た。",
            ]
        ),
        "expect_fetch": True,
        "body_checks": ("2026年5月2日の阪神戦", "巨人が5-7で敗戦", "適時打"),
        "expect_success": True,
    },
    "202605010002047": {
        "title": "【巨人】阪神戦を制し 阿部監督が試合後に振り返る",
        "summary": "阿部監督が試合後に投手陣の粘りを評価した。",
        "source_url": "https://www.nikkansports.com/baseball/news/202605010002047.html",
        "published_at": datetime(2026, 5, 1, 22, 40, tzinfo=JST),
        "payload": _payload(result="win", opponent="阪神"),
        "fetched_text": "\n".join(
            [
                "＜阪神3－5巨人＞◇1日◇甲子園",
                "3回に甲斐拓也の先制2点適時打が飛び出した。",
                "6回に岡本和真の7号3ランで突き放した。",
            ]
        ),
        "expect_fetch": True,
        "body_checks": ("2026年5月1日の阪神戦", "巨人が5-3で勝利", "適時打"),
        "expect_success": True,
    },
    "202605010001921": {
        "title": "【巨人】田中将大が日米203勝目 阪神戦を振り返る",
        "summary": "田中将大が試合後にチームの攻撃を振り返った。",
        "source_url": "https://www.nikkansports.com/baseball/news/202605010001921.html",
        "published_at": datetime(2026, 5, 1, 21, 55, tzinfo=JST),
        "payload": _payload(result="win"),
        "fetched_text": "\n".join(
            [
                "＜阪神3－5巨人＞◇1日◇甲子園",
                "3回に甲斐拓也の先制2点適時打が生まれた。",
                "岡本和真が7号3ランを放った。",
            ]
        ),
        "expect_fetch": True,
        "body_checks": ("2026年5月1日の阪神戦", "巨人が5-3で勝利", "適時打"),
        "expect_success": True,
    },
    "694560": {
        "title": "巨人戦 終盤の一打で動いた試合",
        "summary": "岡本和真の一発を伝える試合後記事として扱われた。",
        "source_url": "https://baseballking.jp/ns/694560/",
        "published_at": datetime(2026, 5, 2, 18, 0, tzinfo=JST),
        "payload": _payload(result="win", game_date="2026-05-02", giants_score=3, opponent_score=2),
        "fetched_text": "ブルージェイズで岡本和真が8号ソロを放った。3-2で勝利した。",
        "expect_fetch": False,
        "expected_reason": "required_facts_missing:opponent",
        "expect_success": False,
    },
    "202605020000169": {
        "title": "巨人阪神戦 田中将大の試合後発言整理",
        "summary": "田中将大が試合後に反省点を口にした。",
        "source_url": "https://www.nikkansports.com/baseball/news/202605020000169.html",
        "published_at": datetime(2026, 5, 2, 20, 35, tzinfo=JST),
        "payload": _payload(result="loss", opponent="阪神"),
        "fetched_text": "\n".join(
            [
                "＜巨人－阪神＞◇2日◇甲子園",
                "田中将大が試合後に反省点を口にした。",
                "SNSで反響が広がった。",
            ]
        ),
        "expect_fetch": True,
        "expected_reason": "required_facts_missing:giants_score",
        "expect_success": False,
    },
    "202605010002174": {
        "title": "【巨人】田中将大ホッとした203勝目 阪神戦を振り返る",
        "summary": "田中将大が試合後に救援陣への感謝を口にした。",
        "source_url": "https://www.nikkansports.com/baseball/news/202605010002174.html",
        "published_at": datetime(2026, 5, 1, 22, 5, tzinfo=JST),
        "payload": _payload(result="win", opponent="阪神"),
        "fetched_text": "\n".join(
            [
                "＜阪神3－5巨人＞◇1日◇甲子園",
                "田中将大が日米203勝目を挙げた。",
                "救援陣がリードを守った。",
            ]
        ),
        "expect_fetch": True,
        "expected_reason": "postgame_decisive_event_missing",
        "expect_success": False,
    },
    "694482": {
        "title": "巨人戦 田中瑛斗の試合後発言整理",
        "summary": "田中瑛斗が試合後に救援の場面を振り返った。",
        "source_url": "https://baseballking.jp/ns/694482/",
        "published_at": datetime(2026, 5, 1, 22, 15, tzinfo=JST),
        "payload": _payload(result="win", giants_score=5, opponent_score=3),
        "fetched_text": "5-3で勝利した試合後、田中瑛斗が取材に応じた。",
        "expect_fetch": False,
        "expected_reason": "required_facts_missing:opponent",
        "expect_success": False,
    },
}


class PostgameStrictFactRecoveryTests(unittest.TestCase):
    def strict_env(self, *, recovery_flag: str = "1") -> dict[str, str]:
        return {
            "LOW_COST_MODE": "1",
            "AI_ENABLED_CATEGORIES": "試合速報",
            "ARTICLE_AI_MODE": "gemini",
            "STRICT_FACT_MODE": "1",
            POSTGAME_STRICT_FEATURE_FLAG_ENV: "1",
            ENABLE_POSTGAME_STRICT_FACT_RECOVERY_ENV: recovery_flag,
            "ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME": "0",
            "ARTICLE_INJECT_TEAM_STATS": "0",
            "GEMINI_API_KEY": "dummy-key",
        }

    def _call_fixture(self, fixture_id: str, *, recovery_flag: str = "1"):
        fixture = FIXTURES[fixture_id]
        logger = logging.getLogger(f"test_postgame_strict_fact_recovery.{fixture_id}")
        with patch.dict("os.environ", self.strict_env(recovery_flag=recovery_flag), clear=False):
            with patch.object(rss_fetcher, "_detect_article_subtype", return_value="postgame"):
                with patch.object(
                    rss_fetcher,
                    "_gemini_text_with_cache",
                    return_value=(json.dumps(fixture["payload"], ensure_ascii=False), {}),
                ):
                    with patch(
                        "src.postgame_strict_fact_recovery._fetch_postgame_source_material",
                        return_value=fixture["fetched_text"],
                    ) as fetch_mock:
                        result = rss_fetcher._maybe_render_postgame_article_parts(
                            title=fixture["title"],
                            summary=fixture["summary"],
                            category="試合速報",
                            has_game=True,
                            source_name="日刊スポーツ",
                            source_url=fixture["source_url"],
                            source_type="news",
                            source_entry={},
                            published_at=fixture["published_at"],
                            win_loss_hint="※この試合の勝敗は source 由来のみで扱う",
                            logger=logger,
                        )
        return result, fetch_mock

    def test_flag_off_keeps_existing_review_path_for_rescue_candidate(self):
        result, fetch_mock = self._call_fixture("202605020001031", recovery_flag="0")

        self.assertFalse(isinstance(result, tuple))
        self.assertIn("required_facts_missing:giants_score", getattr(result, "reason", ""))
        fetch_mock.assert_not_called()

    def test_positive_fixture_rescues_with_flag_on(self):
        for fixture_id in ("202605020001031", "202605020001323", "202605010002047", "202605010001921"):
            with self.subTest(fixture_id=fixture_id):
                result, fetch_mock = self._call_fixture(fixture_id, recovery_flag="1")

                self.assertTrue(isinstance(result, tuple))
                body_text, _rendered_html = result
                for fragment in FIXTURES[fixture_id]["body_checks"]:
                    self.assertIn(fragment, body_text)
                if FIXTURES[fixture_id]["expect_fetch"]:
                    fetch_mock.assert_called_once()
                else:
                    fetch_mock.assert_not_called()

    def test_negative_fixture_stays_on_review_path_with_flag_on(self):
        for fixture_id in ("694560", "202605020000169", "202605010002174", "694482"):
            with self.subTest(fixture_id=fixture_id):
                result, fetch_mock = self._call_fixture(fixture_id, recovery_flag="1")

                self.assertFalse(isinstance(result, tuple))
                self.assertIn(FIXTURES[fixture_id]["expected_reason"], getattr(result, "reason", ""))
                if FIXTURES[fixture_id]["expect_fetch"]:
                    fetch_mock.assert_called_once()
                else:
                    fetch_mock.assert_not_called()
