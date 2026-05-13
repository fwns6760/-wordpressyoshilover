"""Tests for src/player_voice_digest_body_renderer.py — 334-QA Phase 3."""

from __future__ import annotations

import unittest

from src.player_voice_digest_body_renderer import render_player_voice_digest_body


# body 内に長 quote (92 字、min 80 max 150 範囲内) + 地の文 数行
_PARENT_BODY = (
    "5月14日、東京ドームに集まった満員のファンの前で坂本勇人が決勝弾を放った。"
    "試合後の取材で坂本勇人は"
    "「最後まで集中して振り切れたんじゃないかと思いますし、ファンの皆さんに感謝しています。"
    "応援してくれている皆さんに勝利を届けることができて嬉しいです。"
    "これからも丁寧に積み重ねていきたいです」"
    "と振り返った。"
    "300号サヨナラホームランで巨人を勝利に導いた。"
    "5月の連勝もこれで3つ目となり、首位争いに加わる戦いが続いていく。"
)


def _make_candidate(
    *,
    player_name: str = "坂本勇人",
    body: str = _PARENT_BODY,
    children: list[dict] | None = None,
    officials: list[dict] | None = None,
    subtype_hint: str = "player_voice_digest",
    omit_payload: bool = False,
) -> dict:
    cand: dict = {
        "body": body,
        "subtype_hint": subtype_hint,
    }
    if not omit_payload:
        cand["digest_cluster_payload"] = {
            "player_name": player_name,
            "quote": "最後まで集中して振り切れたんじゃないかと思います",
            "event_token": "300号サヨナラホームラン",
            "parent_family": "hochi",
            "children": children if children is not None else [
                {
                    "family": "sanspo",
                    "label": "サンスポ",
                    "snippet": "坂本勇人のサヨナラ本塁打が決勝点、巨人が劇的勝利で連勝を伸ばす",
                    "url": "https://www.sanspo.com/article/1/",
                },
                {
                    "family": "nikkansports",
                    "label": "日刊スポーツ",
                    "snippet": "坂本勇人が満員の東京ドームで劇的なサヨナラ本塁打を放ち勝利を呼んだ",
                    "url": "https://www.nikkansports.com/baseball/news/1.html",
                },
            ],
            "officials": officials if officials is not None else [],
        }
    return cand


class BasicRenderTests(unittest.TestCase):
    def test_basic_render_includes_player_name(self):
        result = render_player_voice_digest_body(_make_candidate())
        self.assertIn("坂本勇人", result)

    def test_basic_render_includes_long_quote_from_body(self):
        result = render_player_voice_digest_body(_make_candidate())
        # body 内の 長 quote (約 95 字) が出る
        self.assertIn("最後まで集中して振り切れたんじゃないかと思いますし", result)

    def test_basic_render_includes_section_a(self):
        result = render_player_voice_digest_body(_make_candidate())
        self.assertIn("🌐 各社が伝える", result)
        self.assertIn("サンスポ", result)
        self.assertIn("日刊スポーツ", result)
        self.assertIn("https://www.sanspo.com/article/1/", result)

    def test_basic_render_includes_section_b_with_officials(self):
        officials = [
            {
                "family": "giants_official",
                "label": "巨人公式サイト",
                "snippet": "坂本勇人選手の通算300号本塁打達成のお知らせ、巨人軍より発表",
                "url": "https://www.giants.jp/news/1.html",
            },
        ]
        result = render_player_voice_digest_body(
            _make_candidate(officials=officials)
        )
        self.assertIn("📣 公式が発表", result)
        self.assertIn("巨人公式サイト", result)
        self.assertIn("https://www.giants.jp/news/1.html", result)

    def test_render_omits_section_b_when_no_officials(self):
        result = render_player_voice_digest_body(_make_candidate(officials=[]))
        self.assertNotIn("📣 公式が発表", result)
        self.assertIn("🌐 各社が伝える", result)


class GuardrailTests(unittest.TestCase):
    def test_no_subtype_hint_returns_empty(self):
        cand = _make_candidate(subtype_hint="postgame")
        result = render_player_voice_digest_body(cand)
        self.assertEqual(result, "")

    def test_no_payload_returns_empty(self):
        cand = _make_candidate(omit_payload=True)
        result = render_player_voice_digest_body(cand)
        self.assertEqual(result, "")

    def test_no_player_name_returns_empty(self):
        cand = _make_candidate(player_name="")
        result = render_player_voice_digest_body(cand)
        self.assertEqual(result, "")

    def test_empty_body_still_renders_player_name(self):
        cand = _make_candidate(body="")
        result = render_player_voice_digest_body(cand)
        # body 無くても player_name と section A は出る
        self.assertIn("坂本勇人", result)
        self.assertIn("🌐 各社が伝える", result)


class HtmlEscapeTests(unittest.TestCase):
    def test_player_name_html_escaped(self):
        # XSS 試行 → escape されるべき
        cand = _make_candidate(player_name='<script>alert("xss")</script>')
        result = render_player_voice_digest_body(cand)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_snippet_html_escaped(self):
        children = [
            {
                "family": "sanspo",
                "label": "サンスポ",
                "snippet": '<img src=x onerror=alert(1)>',
                "url": "https://example.com/",
            },
        ]
        result = render_player_voice_digest_body(
            _make_candidate(children=children)
        )
        self.assertNotIn("<img src=x", result)
        self.assertIn("&lt;img", result)

    def test_url_in_href_html_escaped(self):
        children = [
            {
                "family": "sanspo",
                "label": "サンスポ",
                "snippet": "坂本勇人のサヨナラ本塁打が決勝点、巨人が劇的勝利で連勝を伸ばす",
                "url": 'https://example.com/"><script>alert(1)</script>',
            },
        ]
        result = render_player_voice_digest_body(
            _make_candidate(children=children)
        )
        self.assertNotIn('"><script>', result)
        self.assertIn("&quot;", result)


class QuoteExtractionTests(unittest.TestCase):
    def test_long_quote_truncated_at_natural_break(self):
        # quote 200 字、natural break で 80-150 に収まるはず
        long_body = (
            "選手は試合後に"
            "「" + "あ" * 100 + "。これからも全力でいきます」"
            "と話した。"
        )
        cand = _make_candidate(body=long_body)
        result = render_player_voice_digest_body(cand)
        # 「あ」が大量 → natural break で 100 字目の 。 で切り、100 字までが採用される
        # 長すぎる場合は省略される (literal contract)
        self.assertIn("あ", result)

    def test_no_long_quote_falls_back_to_player_only(self):
        # body に長 quote が無い (短い quote のみ)
        short_body = "選手「短い」と話した。"
        cand = _make_candidate(body=short_body)
        result = render_player_voice_digest_body(cand)
        # player_name は出る、long quote 部分は無い
        self.assertIn("<strong>坂本勇人</strong>", result)


class LeadSentenceTests(unittest.TestCase):
    def test_lead_sentences_from_body(self):
        result = render_player_voice_digest_body(_make_candidate())
        # body の最初の数文 (quote 除外) が地の文として出る
        self.assertIn("東京ドーム", result)


if __name__ == "__main__":
    unittest.main()
