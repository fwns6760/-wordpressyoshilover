"""Mock-based tests for ``src.x_post_branding_gen`` (ticket 392)。

google-genai / requests / Tavily / Gemini に実 access せず、 mock で全て閉じる。
fastmcp は 392 では使わない (391 用、 install されてなくても 392 test は通る)。
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ----- fake google.genai (もし install 済なら respect) ----------------------
def _ensure_fake_module(name: str) -> types.ModuleType:
    if name in sys.modules and sys.modules[name] is not None:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


_google = _ensure_fake_module("google")
_google_genai = _ensure_fake_module("google.genai")
setattr(_google, "genai", _google_genai)
if not hasattr(_google_genai, "Client"):
    class _FakeGenaiClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self.models = MagicMock(name="genai.Client.models")

    _google_genai.Client = _FakeGenaiClient  # type: ignore[attr-defined]


# Now safe to import.
import src.x_post_branding_gen as xbg  # noqa: E402


class TavilySearchTests(unittest.TestCase):
    def test_empty_query_returns_empty(self) -> None:
        self.assertEqual(xbg._tavily_search("", "key"), [])

    def test_empty_key_returns_empty(self) -> None:
        self.assertEqual(xbg._tavily_search("巨人 戸郷", ""), [])

    def test_200_response_returns_results(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"title": "戸郷投手 復帰", "content": "戸郷翔征が..."},
                {"title": "別記事", "content": "..."},
            ]
        }
        with patch("requests.post", return_value=mock_resp) as mock_post:
            results = xbg._tavily_search(
                "巨人 戸郷", "tvly-fake", same_day_only=False
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "戸郷投手 復帰")
        mock_post.assert_called_once()
        # api.tavily.com endpoint 確認
        args, kwargs = mock_post.call_args
        self.assertIn("api.tavily.com", args[0])

    def test_same_day_filter_keeps_today_drops_others(self) -> None:
        from datetime import datetime, timezone, timedelta
        from email.utils import format_datetime
        jst = timezone(timedelta(hours=9))
        today_jst = datetime.now(jst).replace(hour=12, minute=0, second=0, microsecond=0)
        yesterday_jst = today_jst - timedelta(days=1)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "今日の戸郷",
                    "content": "...",
                    "published_date": format_datetime(today_jst.astimezone(timezone.utc)),
                },
                {
                    "title": "昨日の戸郷",
                    "content": "...",
                    "published_date": format_datetime(yesterday_jst.astimezone(timezone.utc)),
                },
                {"title": "日付不明", "content": "..."},
            ]
        }
        with patch("requests.post", return_value=mock_resp):
            results = xbg._tavily_search("巨人 戸郷", "tvly-fake", same_day_only=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "今日の戸郷")

    def test_non_200_returns_empty(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        with patch("requests.post", return_value=mock_resp):
            self.assertEqual(xbg._tavily_search("巨人 戸郷", "tvly-fake"), [])

    def test_network_error_returns_empty(self) -> None:
        with patch("requests.post", side_effect=ConnectionError("net down")):
            self.assertEqual(xbg._tavily_search("巨人 戸郷", "tvly-fake"), [])

    def test_invalid_json_returns_empty(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"not_results_key": "..."}
        with patch("requests.post", return_value=mock_resp):
            self.assertEqual(xbg._tavily_search("巨人 戸郷", "tvly-fake"), [])


class SafetyCheckTests(unittest.TestCase):
    def test_empty_text_rejected(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check(""))
        self.assertFalse(xbg._gemma_branding_safety_check("   \n  "))

    def test_url_rejected(self) -> None:
        self.assertFalse(
            xbg._gemma_branding_safety_check(
                "戸郷投手の話題。 https://example.test/article"
            )
        )
        self.assertFalse(
            xbg._gemma_branding_safety_check("詳細は http://example.test/")
        )

    def test_hashtag_rejected(self) -> None:
        self.assertFalse(
            xbg._gemma_branding_safety_check("戸郷投手の話題 #巨人 #ジャイアンツ")
        )

    def test_yoshilover_phrase_rejected(self) -> None:
        self.assertFalse(
            xbg._gemma_branding_safety_check("戸郷投手をヨシラバーで整理しました")
        )
        self.assertFalse(
            xbg._gemma_branding_safety_check("詳しくはヨシラバーに整理しました")
        )

    def test_x_voice_phrase_rejected(self) -> None:
        self.assertFalse(
            xbg._gemma_branding_safety_check("Xでは戸郷投手が話題")
        )
        self.assertFalse(
            xbg._gemma_branding_safety_check("X上では多くの声が上がっている")
        )
        self.assertFalse(
            xbg._gemma_branding_safety_check("みんなの声を集めた")
        )

    def test_over_char_limit_rejected(self) -> None:
        long_text = "あ" * (xbg.X_CHAR_LIMIT + 10)
        self.assertFalse(xbg._gemma_branding_safety_check(long_text))

    def test_clean_text_accepted(self) -> None:
        self.assertTrue(
            xbg._gemma_branding_safety_check(
                "エースが苦しむ姿を見るのは辛い。けれど、 そこから這い上がるプロセスこそが、 ファンを熱狂させる物語になる。"
            )
        )


class BuildCandidateTests(unittest.TestCase):
    def test_missing_keys_skip(self) -> None:
        self.assertIsNone(
            xbg.build_gemma_branding_candidate(
                "戸郷翔征",
                gemini_api_key="",
                tavily_api_key="tvly",
            )
        )
        self.assertIsNone(
            xbg.build_gemma_branding_candidate(
                "戸郷翔征",
                gemini_api_key="gem",
                tavily_api_key="",
            )
        )
        self.assertIsNone(
            xbg.build_gemma_branding_candidate(
                "",
                gemini_api_key="gem",
                tavily_api_key="tvly",
            )
        )

    def test_non_giants_player_skip(self) -> None:
        # 非巨人 roster の player (例: 大谷翔平) は skip
        with patch.object(xbg, "_is_verified_full_giants_player_name", return_value=False):
            result = xbg.build_gemma_branding_candidate(
                "大谷翔平",
                gemini_api_key="gem",
                tavily_api_key="tvly",
            )
        self.assertIsNone(result)

    def test_no_tavily_results_skip(self) -> None:
        # Tavily が空返したら factual ground 無し = skip (hallucination 抑制)
        with patch.object(xbg, "_is_verified_full_giants_player_name", return_value=True), \
             patch.object(xbg, "_tavily_search", return_value=[]):
            result = xbg.build_gemma_branding_candidate(
                "戸郷翔征",
                gemini_api_key="gem",
                tavily_api_key="tvly",
            )
        self.assertIsNone(result)

    def test_gemini_error_skip(self) -> None:
        with patch.object(xbg, "_is_verified_full_giants_player_name", return_value=True), \
             patch.object(
                xbg,
                "_tavily_search",
                return_value=[{"title": "戸郷投手", "content": "復帰"}],
             ):
            # genai.Client が例外
            fake_client = MagicMock()
            fake_client.models.generate_content.side_effect = RuntimeError("rate limit")
            with patch.object(xbg, "genai", create=True) as _genai:
                # google.genai を fake
                pass
            # 実装は ``from google import genai`` を関数内で行うため、
            # google.genai.Client を patch する
            with patch("google.genai.Client", return_value=fake_client):
                result = xbg.build_gemma_branding_candidate(
                    "戸郷翔征",
                    gemini_api_key="gem",
                    tavily_api_key="tvly",
                )
        self.assertIsNone(result)

    def test_unsafe_output_skip(self) -> None:
        # Gemma が URL 含む出力を返したら drop
        fake_response = MagicMock()
        fake_response.text = "戸郷投手の話 https://example.test/leak"
        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = fake_response
        with patch.object(xbg, "_is_verified_full_giants_player_name", return_value=True), \
             patch.object(
                xbg,
                "_tavily_search",
                return_value=[{"title": "戸郷投手", "content": "復帰"}],
             ), \
             patch("google.genai.Client", return_value=fake_client):
            result = xbg.build_gemma_branding_candidate(
                "戸郷翔征",
                gemini_api_key="gem",
                tavily_api_key="tvly",
            )
        self.assertIsNone(result)

    def test_clean_output_returns_candidate(self) -> None:
        fake_response = MagicMock()
        fake_response.text = (
            "エースが苦しむ姿を見るのは辛い。 けれど、 そこから這い上がる"
            "プロセスこそが、 ファンを熱狂させる物語になる。"
        )
        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = fake_response
        with patch.object(xbg, "_is_verified_full_giants_player_name", return_value=True), \
             patch.object(
                xbg,
                "_tavily_search",
                return_value=[
                    {"title": "戸郷投手 復帰", "content": "戸郷翔征が..."},
                    {"title": "別記事", "content": "..."},
                ],
             ), \
             patch("google.genai.Client", return_value=fake_client):
            result = xbg.build_gemma_branding_candidate(
                "戸郷翔征",
                gemini_api_key="gem",
                tavily_api_key="tvly",
                db_fact_line="戸郷翔征は今季登板回数 9、 防御率 2.55",
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.metric, "GEMMA_BRANDING")
        self.assertEqual(result.focus_player, "戸郷翔征")
        self.assertIn("戸郷翔征", result.title)
        self.assertIn("エースが苦しむ姿", result.post_text)
        self.assertIn("【Tavily 検索結果 snippet】", result.draft_text)
        self.assertIn("DB fact 注入: あり", result.draft_text)
        self.assertIn("【DB fact line】", result.draft_text)
        # post_text は URL 含まない
        self.assertNotIn("https://", result.post_text)
        # 280 字以内
        self.assertLessEqual(len(result.post_text), xbg.X_CHAR_LIMIT)


class BuildDbFactLineTests(unittest.TestCase):
    """Ticket 394: build_db_fact_line() の SQLite read-only path test。"""

    def _seed_db(self, db_path: str) -> None:
        import sqlite3
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        today = datetime.now(jst).strftime("%Y-%m-%d")
        yesterday = (datetime.now(jst) - timedelta(days=1)).strftime("%Y-%m-%d")
        two_days_ago = (datetime.now(jst) - timedelta(days=2)).strftime("%Y-%m-%d")
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.executescript(
            """
            CREATE TABLE games (
                game_id TEXT PRIMARY KEY,
                game_date TEXT NOT NULL,
                opponent TEXT NOT NULL,
                home_away TEXT,
                giants_score INTEGER,
                opp_score INTEGER,
                result TEXT,
                league_label TEXT,
                one_line_summary TEXT,
                winning_pitcher TEXT,
                losing_pitcher TEXT,
                save_pitcher TEXT,
                source_url TEXT,
                source_kind TEXT,
                ingested_at TEXT NOT NULL
            );
            CREATE TABLE batting_logs (
                game_id TEXT NOT NULL,
                team_role TEXT NOT NULL,
                slot_order INTEGER,
                position TEXT,
                player_display TEXT NOT NULL,
                player_canonical TEXT,
                is_sub INTEGER NOT NULL DEFAULT 0,
                AB INTEGER, R INTEGER, H INTEGER, RBI INTEGER, SB INTEGER,
                atbats_json TEXT, team_name TEXT,
                PRIMARY KEY (game_id, team_role, slot_order, player_display)
            );
            CREATE TABLE pitching_logs (
                game_id TEXT NOT NULL,
                team_role TEXT NOT NULL,
                appearance_order INTEGER NOT NULL,
                player_display TEXT NOT NULL,
                player_canonical TEXT,
                result_mark TEXT, pitches INTEGER, BF INTEGER, IP REAL,
                H_allowed INTEGER, HR_allowed INTEGER, BB INTEGER, HBP INTEGER,
                K INTEGER, WP INTEGER, BK INTEGER, R INTEGER, ER INTEGER,
                team_name TEXT,
                PRIMARY KEY (game_id, team_role, appearance_order)
            );
            """
        )
        cur.execute(
            "INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("g-today", today, "DeNA", "home", 3, 1, "win", None, None,
             None, None, None, None, None, "2026-05-19T13:00:00Z"),
        )
        cur.execute(
            "INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("g-y1", yesterday, "DeNA", "home", 5, 2, "win", None, None,
             None, None, None, None, None, "2026-05-18T13:00:00Z"),
        )
        cur.execute(
            "INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("g-y2", two_days_ago, "ヤクルト", "away", 1, 4, "loss", None, None,
             None, None, None, None, None, "2026-05-17T13:00:00Z"),
        )
        # 戸郷翔征 投手 今日
        cur.execute(
            "INSERT INTO pitching_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("g-today", "giants", 1, "戸郷翔征", "戸郷翔征", "○", 87, 24, 6.0,
             4, 0, 1, 0, 8, 0, 0, 1, 1, "巨人"),
        )
        # 平山功太 打撃 今日
        cur.execute(
            "INSERT INTO batting_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("g-today", "giants", 1, "中堅", "平山 功太", "平山 功太", 0,
             4, 1, 2, 1, 0, None, "巨人"),
        )
        con.commit()
        con.close()

    def test_db_fact_line_with_game_and_pitcher(self) -> None:
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_db(db)
            fact = xbg.build_db_fact_line("戸郷翔征", db)
            self.assertIn("巨人 vs DeNA", fact)
            self.assertIn("3-1", fact)
            self.assertIn("勝利", fact)
            self.assertIn("戸郷翔征 投球", fact)
            self.assertIn("6.0回", fact)
            self.assertIn("8K", fact)
            self.assertIn("(○)", fact)
            self.assertIn("直近", fact)
            self.assertIn("○", fact)
            self.assertIn("●", fact)

    def test_db_fact_line_with_batter(self) -> None:
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_db(db)
            fact = xbg.build_db_fact_line("平山 功太", db)
            self.assertIn("平山 功太 打撃", fact)
            self.assertIn("4打数2安打", fact)
            self.assertIn("1打点", fact)

    def test_db_fact_line_empty_when_no_game(self) -> None:
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_db(db)
            fact = xbg.build_db_fact_line(
                "戸郷翔征", db, target_date="2030-01-01"
            )
            # No today game, no player log → 連勝 line のみ or 空
            self.assertNotIn("巨人 vs", fact)

    def test_db_fact_line_missing_db_path_returns_empty(self) -> None:
        self.assertEqual(xbg.build_db_fact_line("戸郷翔征", ""), "")

    def test_db_fact_line_missing_player_returns_empty(self) -> None:
        self.assertEqual(xbg.build_db_fact_line("", "/tmp/x.db"), "")


class TavilyWhitelistTests411(unittest.TestCase):
    """411 (2026-05-20): user 仕様 = 公式 / NPB / 球団 / 主要スポーツ紙優先."""

    def test_whitelist_covers_official_and_papers(self) -> None:
        domains = set(xbg._TAVILY_INCLUDE_DOMAINS)
        # 公式 / 球団
        self.assertIn("giants.jp", domains)
        self.assertIn("npb.or.jp", domains)
        # 主要スポーツ紙
        self.assertIn("hochi.news", domains)
        self.assertIn("sponichi.co.jp", domains)
        self.assertIn("nikkansports.com", domains)
        self.assertIn("sanspo.com", domains)
        self.assertIn("daily.co.jp", domains)
        self.assertIn("chunichi.co.jp", domains)
        # ポータル (既存)
        self.assertIn("sports.yahoo.co.jp", domains)
        self.assertGreaterEqual(len(domains), 9)

    def test_tavily_search_request_explicitly_disables_answer(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        with patch("requests.post", return_value=mock_resp) as mock_post:
            xbg._tavily_search("巨人 戸郷", "tvly-fake")
        args, kwargs = mock_post.call_args
        body = kwargs.get("json") or {}
        # spec lock: answer 使わない、 URL 本文 / 媒体名 / 日付のみ
        self.assertIn("include_answer", body)
        self.assertFalse(body["include_answer"])


class FormatTavilyContextTests411(unittest.TestCase):
    """411: published_date + 媒体名 を Gemma context に注入."""

    def test_includes_published_date_and_source_label(self) -> None:
        results = [
            {
                "title": "戸郷快投",
                "content": "戸郷翔征が7回1失点で勝利投手...",
                "url": "https://hochi.news/articles/12345.html",
                "published_date": "Tue, 19 May 2026 13:30:00 GMT",
            },
        ]
        ctx = xbg._format_tavily_context(results)
        self.assertIn("[2026-05-19]", ctx)
        self.assertIn("[スポーツ報知]", ctx)
        self.assertIn("戸郷快投", ctx)

    def test_unknown_date_falls_back_to_label(self) -> None:
        results = [
            {
                "title": "記事タイトル",
                "content": "本文",
                "url": "https://sponichi.co.jp/x.html",
                "published_date": "garbage-not-a-date",
            },
        ]
        ctx = xbg._format_tavily_context(results)
        self.assertIn("[日付不明]", ctx)
        self.assertIn("[スポニチ]", ctx)

    def test_unknown_source_label_falls_back_to_host(self) -> None:
        results = [
            {
                "title": "記事",
                "content": "本文",
                "url": "https://example.invalid/x.html",
                "published_date": "Tue, 19 May 2026 13:30:00 GMT",
            },
        ]
        ctx = xbg._format_tavily_context(results)
        self.assertIn("[example.invalid]", ctx)


class IsGiantsGameDayTests411(unittest.TestCase):
    """411: insight.db games table 経由の試合日判定."""

    def _seed_db(self, db_path: str, date_str: str = "") -> None:
        import sqlite3
        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS games ("
                "game_id TEXT, game_date TEXT, opponent TEXT, "
                "giants_score INTEGER, opp_score INTEGER, result TEXT, "
                "ingested_at TEXT)"
            )
            if date_str:
                cur.execute(
                    "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("g1", date_str, "ヤクルト", 5, 4, "win", "2026-05-20T22:00:00Z"),
                )
            con.commit()
        finally:
            con.close()

    def test_returns_true_when_games_row_exists(self) -> None:
        import os
        import tempfile
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        now = datetime(2026, 5, 20, 19, 0, tzinfo=jst)
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_db(db, date_str="2026-05-20")
            self.assertTrue(xbg.is_giants_game_day(now, db))

    def test_returns_false_when_no_games_row(self) -> None:
        import os
        import tempfile
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        now = datetime(2026, 5, 20, 19, 0, tzinfo=jst)
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "insight.db")
            self._seed_db(db)  # empty
            self.assertFalse(xbg.is_giants_game_day(now, db))

    def test_returns_false_when_db_path_empty(self) -> None:
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        now = datetime(2026, 5, 20, 19, 0, tzinfo=jst)
        self.assertFalse(xbg.is_giants_game_day(now, ""))

    def test_returns_false_when_db_open_fails(self) -> None:
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        now = datetime(2026, 5, 20, 19, 0, tzinfo=jst)
        self.assertFalse(xbg.is_giants_game_day(now, "/nonexistent/path/x.db"))


class SelectBrandingPersonaTests411(unittest.TestCase):
    """411: persona 自動選択 (試合日 18-21時 = 缶詰、 他 = フーガ)."""

    def _now_at(self, hour: int):
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        return datetime(2026, 5, 20, hour, 0, tzinfo=jst)

    def test_kandume_on_game_day_evening_18(self) -> None:
        self.assertEqual(xbg.select_branding_persona(self._now_at(18), True), "kandume")

    def test_kandume_on_game_day_evening_20(self) -> None:
        self.assertEqual(xbg.select_branding_persona(self._now_at(20), True), "kandume")

    def test_kandume_on_game_day_evening_21(self) -> None:
        self.assertEqual(xbg.select_branding_persona(self._now_at(21), True), "kandume")

    def test_fuuga_on_game_day_morning_11(self) -> None:
        self.assertEqual(xbg.select_branding_persona(self._now_at(11), True), "fuuga")

    def test_fuuga_on_game_day_afternoon_17(self) -> None:
        # 17時は試合直前だが 18-21 範囲外なので フーガ
        self.assertEqual(xbg.select_branding_persona(self._now_at(17), True), "fuuga")

    def test_fuuga_on_game_day_late_night_22(self) -> None:
        # 22時は試合後余韻、 缶詰 範囲外
        self.assertEqual(xbg.select_branding_persona(self._now_at(22), True), "fuuga")

    def test_fuuga_on_non_game_day_evening(self) -> None:
        # 非試合日は 18-21 時でもフーガ
        self.assertEqual(xbg.select_branding_persona(self._now_at(19), False), "fuuga")


class HallucinationPreventionAxisCTests414(unittest.TestCase):
    """414 axis C: hallucination 防止 (regex + 数値 whitelist + temperature + date filter)."""

    # axis C1: \d+位 forbidden
    def test_safety_check_rejects_rank_28(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("岸田は出塁率28位の数字を残してる"))

    def test_safety_check_rejects_rank_3(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("打率3位の選手だ"))

    def test_safety_check_accepts_no_rank(self) -> None:
        # 順位表現なしの 220+ 字の post
        text = (
            "戸郷さん 完投ナイスピッチ "
            "ボールに伸びがあった 直球で押し込めるのは大きい 連勝の流れに乗れそう "
            "あと打線が早めに点取れるようになると更に楽になる 試合運びの完成度上がってる "
            "明日からのカードも楽しみで仕方ない 噛み締めましょう "
            "次の中継ぎ陣も整ってきた感じあるし やってる野球が強い"
        )
        self.assertTrue(xbg._gemma_branding_safety_check(text))

    # axis C3: rate forbidden
    def test_safety_check_rejects_batting_average(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("岸田は打率.345を残してる"))

    def test_safety_check_rejects_era_specific(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("戸郷の防御率1.85は素晴らしい"))

    # axis C2: 数値 whitelist
    def test_extract_unverified_numbers_returns_unverified(self) -> None:
        text = "今日の戸郷は7回1失点 8奪三振 28イニング無失点"
        verified = "戸郷 7回 1失点 8奪三振"
        unverified = xbg._extract_unverified_numbers(text, verified)
        self.assertIn("28", unverified)

    def test_extract_unverified_numbers_empty_when_all_verified(self) -> None:
        text = "戸郷は 7回 1失点 8奪三振"
        verified = "戸郷 7回 1失点 8奪三振 連勝中"
        self.assertEqual(xbg._extract_unverified_numbers(text, verified), [])

    def test_extract_unverified_numbers_handles_empty_text(self) -> None:
        self.assertEqual(xbg._extract_unverified_numbers("", "anything"), [])

    # axis C5: temperature default
    def test_build_gemma_branding_candidate_default_temperature(self) -> None:
        import inspect
        sig = inspect.signature(xbg.build_gemma_branding_candidate)
        self.assertEqual(sig.parameters["temperature"].default, 0.4)

    # axis C6: published_date 7 日超 drop
    def test_recent_published_within_days_drops_old_entry(self) -> None:
        from datetime import datetime, timezone, timedelta
        from email.utils import format_datetime
        jst = timezone(timedelta(hours=9))
        today_jst = datetime.now(jst).replace(hour=12)
        very_old = today_jst - timedelta(days=30)
        recent = today_jst - timedelta(days=3)
        results = [
            {"title": "古い", "published_date": format_datetime(very_old.astimezone(timezone.utc))},
            {"title": "最近", "published_date": format_datetime(recent.astimezone(timezone.utc))},
        ]
        kept = xbg._recent_published_within_days(results, days=7)
        titles = [r["title"] for r in kept]
        self.assertNotIn("古い", titles)
        self.assertIn("最近", titles)

    def test_recent_published_within_days_keeps_unknown_date(self) -> None:
        results = [{"title": "日付不明", "content": "本文"}]
        kept = xbg._recent_published_within_days(results, days=7)
        # 日付不明は false-negative 寄りで残す
        self.assertEqual(len(kept), 1)

    def test_recent_published_within_days_zero_means_same_day_only(self) -> None:
        from datetime import datetime, timezone, timedelta
        from email.utils import format_datetime
        jst = timezone(timedelta(hours=9))
        today_jst = datetime.now(jst).replace(hour=12)
        yesterday = today_jst - timedelta(days=1)
        results = [
            {"title": "昨日", "published_date": format_datetime(yesterday.astimezone(timezone.utc))},
            {"title": "今日", "published_date": format_datetime(today_jst.astimezone(timezone.utc))},
        ]
        kept = xbg._recent_published_within_days(results, days=0)
        titles = [r["title"] for r in kept]
        self.assertNotIn("昨日", titles)
        self.assertIn("今日", titles)


class PostTypeAxisATests414(unittest.TestCase):
    """414 axis A: 5 型分離 + 自動選択."""

    def _now_at(self, hour: int):
        from datetime import datetime, timezone, timedelta
        jst = timezone(timedelta(hours=9))
        return datetime(2026, 5, 20, hour, 0, tzinfo=jst)

    def test_post_types_constant_has_5_types(self) -> None:
        self.assertEqual(set(xbg._POST_TYPES), {"flash", "emotion", "data", "next", "positive"})

    def test_post_type_guidance_covers_all_5(self) -> None:
        for t in xbg._POST_TYPES:
            self.assertIn(t, xbg._POST_TYPE_GUIDANCE)
            self.assertGreater(len(xbg._POST_TYPE_GUIDANCE[t]), 30)

    # 試合日
    def test_game_day_18_returns_next(self) -> None:
        self.assertEqual(xbg.select_post_type(self._now_at(18), True), "next")

    def test_game_day_20_returns_next(self) -> None:
        self.assertEqual(xbg.select_post_type(self._now_at(20), True), "next")

    def test_game_day_22_returns_emotion(self) -> None:
        self.assertEqual(xbg.select_post_type(self._now_at(22), True), "emotion")

    def test_game_day_morning_returns_data(self) -> None:
        self.assertEqual(xbg.select_post_type(self._now_at(8), True), "data")

    def test_game_day_afternoon_with_db_fact_returns_data(self) -> None:
        result = xbg.select_post_type(self._now_at(14), True, has_db_fact=True)
        self.assertEqual(result, "data")

    def test_game_day_afternoon_without_db_fact_returns_emotion(self) -> None:
        result = xbg.select_post_type(self._now_at(14), True, has_db_fact=False)
        self.assertEqual(result, "emotion")

    def test_game_day_17_returns_next(self) -> None:
        # 17時 = 試合直前 = next
        self.assertEqual(xbg.select_post_type(self._now_at(17), True), "next")

    # 非試合日
    def test_non_game_day_morning_returns_data(self) -> None:
        self.assertEqual(xbg.select_post_type(self._now_at(8), False), "data")

    def test_non_game_day_afternoon_returns_positive(self) -> None:
        self.assertEqual(xbg.select_post_type(self._now_at(14), False), "positive")

    def test_non_game_day_evening_returns_emotion(self) -> None:
        self.assertEqual(xbg.select_post_type(self._now_at(20), False), "emotion")


class InflammationPreventionAxisDTests414(unittest.TestCase):
    """414 axis D: 炎上・ズレ防止 6 check."""

    # D1: 強批判語
    def test_safety_check_rejects_player_criticism(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("戸郷は使えない投手だ"))
        self.assertFalse(xbg._gemma_branding_safety_check("岸田は戦犯"))
        self.assertFalse(xbg._gemma_branding_safety_check("もう引退しろという声"))

    # D3: 断定語
    def test_safety_check_rejects_absolute_claim(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("絶対優勝する流れ"))
        self.assertFalse(xbg._gemma_branding_safety_check("100%勝てる試合"))
        self.assertFalse(xbg._gemma_branding_safety_check("間違いなく好投する"))

    # D4: 監督批判の雑な隣接
    def test_safety_check_rejects_manager_harsh_criticism(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("阿部監督の采配は無能だ"))
        self.assertFalse(xbg._gemma_branding_safety_check("監督を解任すべき"))

    # D6: 他球団 / 相手ファン煽り
    def test_safety_check_rejects_opponent_taunting(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("阪神なんて雑魚だ"))
        self.assertFalse(xbg._gemma_branding_safety_check("中日は三流"))

    # D5: 偽名 / generic placeholder
    def test_safety_check_rejects_placeholder_name(self) -> None:
        self.assertFalse(xbg._gemma_branding_safety_check("打者Aの活躍がすごい"))
        self.assertFalse(xbg._gemma_branding_safety_check("投手Xに期待"))

    # 正常系 (D 全 check 通過)
    def test_safety_check_accepts_positive_fan_voice(self) -> None:
        text = (
            "今日の戸郷さん ナイスピッチ "
            "球が走ってた 直球で押し込めるのが大きい "
            "連勝の流れに乗れそう 噛み締めましょう "
            "あと打線も早めに点取れると更に楽 試合運びの完成度が上がってる "
            "明日のカードも楽しみで仕方ない とんでもないチームになりそう "
            "やってる野球が強い ガチで凄い"
        )
        self.assertTrue(xbg._gemma_branding_safety_check(text))

    # helper: _matched_inflammatory_pattern
    def test_matched_inflammatory_pattern_returns_pattern_string(self) -> None:
        pattern_str = xbg._matched_inflammatory_pattern("阪神なんて雑魚だ")
        self.assertIsNotNone(pattern_str)
        assert pattern_str is not None
        self.assertIn("雑魚", pattern_str)

    def test_matched_inflammatory_pattern_returns_none_when_clean(self) -> None:
        self.assertIsNone(xbg._matched_inflammatory_pattern("良い試合だった"))


class BuildSystemPromptPersonaTests411(unittest.TestCase):
    """411 → #95: persona 切替 helper は維持、 ただし新 unified
    ヨシラバー voice prompt を 1 本 返す。 persona = fuuga / kandume /
    unknown どれでも同じ prompt content (例文 / hard rule / 3 軸圧縮).
    """

    def test_default_persona_returns_yoshilover_voice(self) -> None:
        prompt = xbg._build_system_prompt(19, "2026-05-20")
        # ヨシラバー voice の few-shot 例「完勝！」 (試合後)
        self.assertIn("完勝！", prompt)
        # 3 軸圧縮の voice 核 phrasing
        self.assertIn("3 軸", prompt)

    def test_kandume_persona_returns_same_unified_prompt(self) -> None:
        # #95: kandume persona でも unified prompt を返す (alias)。
        prompt = xbg._build_system_prompt(19, "2026-05-20", persona="kandume")
        # 統合された unified prompt の試合中 example も含まれる
        self.assertIn("4回終わって 2-2", prompt)
        # 完勝！ も含まれる (試合後 example)
        self.assertIn("完勝！", prompt)

    def test_unknown_persona_falls_back_to_yoshilover_voice(self) -> None:
        prompt = xbg._build_system_prompt(19, "2026-05-20", persona="unknown_voice")
        self.assertIn("完勝！", prompt)


class XImpressionPhase5OfficialHandleTests(unittest.TestCase):
    """X インプ向上 Phase 5 (2026-05-27): source URL → 公式 X handle 解決 + 付与。"""

    def test_resolve_hochi_news_to_hochi_giants(self) -> None:
        self.assertEqual(
            xbg._resolve_official_x_handle("https://hochi.news/articles/20260527.html"),
            "@hochi_giants",
        )

    def test_resolve_twitter_hochi_giants(self) -> None:
        self.assertEqual(
            xbg._resolve_official_x_handle("https://twitter.com/hochi_giants/status/123"),
            "@hochi_giants",
        )

    def test_resolve_sanspo(self) -> None:
        self.assertEqual(
            xbg._resolve_official_x_handle("https://www.sanspo.com/article/x"),
            "@Sanspo_Giants",
        )

    def test_resolve_tokyo_giants_official_x(self) -> None:
        self.assertEqual(
            xbg._resolve_official_x_handle("https://twitter.com/TokyoGiants/status/x"),
            "@TokyoGiants",
        )

    def test_resolve_unknown_returns_none(self) -> None:
        self.assertIsNone(xbg._resolve_official_x_handle("https://example.com/article"))
        self.assertIsNone(xbg._resolve_official_x_handle(""))

    def test_append_handle_adds_attribution_line(self) -> None:
        out = xbg._append_x_handle_to_post_text(
            "巨人が勝った",
            "https://hochi.news/articles/x",
        )
        self.assertEqual(out, "巨人が勝った\n\n(出典 @hochi_giants)")

    def test_append_handle_unchanged_when_no_match(self) -> None:
        out = xbg._append_x_handle_to_post_text(
            "巨人が勝った",
            "https://example.com/article",
        )
        self.assertEqual(out, "巨人が勝った")

    def test_append_handle_skipped_when_exceeds_280(self) -> None:
        # 270 字の本文に @ 付与で 280 超過 → 元 text のまま
        long_body = "あ" * 270
        out = xbg._append_x_handle_to_post_text(
            long_body,
            "https://hochi.news/articles/x",
        )
        self.assertEqual(out, long_body)


if __name__ == "__main__":
    unittest.main()
