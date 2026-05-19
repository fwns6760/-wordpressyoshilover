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


if __name__ == "__main__":
    unittest.main()
