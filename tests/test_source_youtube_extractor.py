"""Tests for src/source_youtube_extractor.py — NOMOTOKE-VIDEO-SOURCE-001.

Acceptance gate
================

- Pure-function: zero network, zero disk I/O, zero rss_fetcher coupling.
- Atom parsing handles single-entry / multi-entry / empty-feed / malformed.
- Skip taxonomy: ``invalid_xml`` / ``no_entries`` / ``no_video_id``.
- ``extract_video_card_facts`` projects each entry into the data_preview
  shape that ``render_video_card`` consumes (video_url / team_name /
  player_name / play_summary required, plus optional date_label /
  description / thumbnail_url / source_url / source_name).
- Player-name regex respects the Phase 2C+ rule: kanji or katakana
  surnames only, no hiragana phrases.
- The module source is greppable for forbidden imports — no requests,
  no rss_fetcher, no nomotoke_card_renderer / nomotoke_rss_router
  cross-dependency at parse time.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.source_youtube_extractor import (  # noqa: E402
    SKIP_REASON_INVALID_XML,
    SKIP_REASON_NO_ENTRIES,
    SKIP_REASON_NO_VIDEO_ID,
    YOUTUBE_WATCH_URL_TEMPLATE,
    YouTubeFeedEntry,
    YouTubeFeedParseResult,
    extract_video_card_facts,
    parse_youtube_atom,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "youtube_rss"


def _load(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Atom parser
# ---------------------------------------------------------------------------


class AtomParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.r: YouTubeFeedParseResult = parse_youtube_atom(
            _load("giants_official_sample.xml")
        )

    def test_feed_metadata_extracted(self):
        self.assertFalse(self.r.is_skipped())
        self.assertEqual(self.r.feed_title, "巨人公式チャンネル")
        self.assertEqual(
            self.r.feed_channel_id, "UCFAKEGIANTS00000000001"
        )
        self.assertEqual(self.r.feed_channel_name, "巨人公式チャンネル")

    def test_three_entries_parsed(self):
        self.assertEqual(len(self.r.entries), 3)

    def test_entry_video_id_and_url(self):
        e0 = self.r.entries[0]
        self.assertEqual(e0.video_id, "abc12345DEF")
        self.assertEqual(
            e0.video_url, "https://www.youtube.com/watch?v=abc12345DEF"
        )

    def test_entry_title_and_channel(self):
        e0 = self.r.entries[0]
        self.assertIn("岡本和真", e0.title)
        self.assertIn("ハイライト", e0.title)
        self.assertEqual(e0.channel_name, "巨人公式チャンネル")
        self.assertEqual(e0.channel_id, "UCFAKEGIANTS00000000001")

    def test_entry_published_and_thumbnail(self):
        e0 = self.r.entries[0]
        self.assertTrue(e0.published_at.startswith("2026-05-06T19:00:00"))
        self.assertEqual(
            e0.thumbnail_url,
            "https://i.ytimg.com/vi/abc12345DEF/hqdefault.jpg",
        )

    def test_entry_description_extracted(self):
        e0 = self.r.entries[0]
        self.assertIn("岡本和真", e0.description)


# ---------------------------------------------------------------------------
# Skip cases
# ---------------------------------------------------------------------------


class SkipCaseTests(unittest.TestCase):
    def test_empty_input_invalid_xml(self):
        r = parse_youtube_atom("")
        self.assertEqual(r.skip_reason, SKIP_REASON_INVALID_XML)

    def test_non_string_input_invalid_xml(self):
        r = parse_youtube_atom(None)  # type: ignore[arg-type]
        self.assertEqual(r.skip_reason, SKIP_REASON_INVALID_XML)

    def test_non_atom_xml_invalid(self):
        r = parse_youtube_atom("<rss><channel></channel></rss>")
        self.assertEqual(r.skip_reason, SKIP_REASON_INVALID_XML)

    def test_feed_with_no_entries_skips(self):
        xml = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<title>Empty</title>"
            "</feed>"
        )
        r = parse_youtube_atom(xml)
        self.assertEqual(r.skip_reason, SKIP_REASON_NO_ENTRIES)
        self.assertEqual(r.feed_title, "Empty")

    def test_entries_without_video_id_dropped(self):
        # Two entries: first has yt:videoId, second does not. Result
        # should contain only the first entry; no skip at result level
        # because at least one entry survived.
        xml = (
            '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
            'xmlns="http://www.w3.org/2005/Atom">'
            "<title>F</title>"
            "<entry><yt:videoId>HASID0001</yt:videoId>"
            "<title>巨人 岡本 ホームラン</title></entry>"
            "<entry><title>巨人 戸郷 完投</title></entry>"
            "</feed>"
        )
        r = parse_youtube_atom(xml)
        self.assertEqual(r.skip_reason, "")
        self.assertEqual(len(r.entries), 1)
        self.assertEqual(r.entries[0].video_id, "HASID0001")

    def test_all_entries_missing_video_id_skips(self):
        xml = (
            '<feed xmlns="http://www.w3.org/2005/Atom">'
            "<title>NoVideoId</title>"
            "<entry><title>巨人 戸郷</title></entry>"
            "</feed>"
        )
        r = parse_youtube_atom(xml)
        self.assertEqual(r.skip_reason, SKIP_REASON_NO_VIDEO_ID)


# ---------------------------------------------------------------------------
# extract_video_card_facts
# ---------------------------------------------------------------------------


class ExtractVideoFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.r: YouTubeFeedParseResult = parse_youtube_atom(
            _load("giants_official_sample.xml")
        )

    def test_required_fields_present_for_homerun_video(self):
        facts = extract_video_card_facts(self.r.entries[0])
        self.assertEqual(
            facts["video_url"],
            "https://www.youtube.com/watch?v=abc12345DEF",
        )
        self.assertEqual(facts["team_name"], "巨人")
        self.assertEqual(facts["player_name"], "岡本和真")
        # play_summary picked from outcome-keyword scan
        self.assertIn(facts["play_summary"], {"ホームラン", "本塁打", "ハイライト"})

    def test_required_fields_present_for_pitcher_video(self):
        facts = extract_video_card_facts(self.r.entries[1])
        self.assertEqual(facts["player_name"], "戸郷翔征")
        self.assertIn(
            facts["play_summary"],
            {"完投", "ハイライト", "好投"},
        )

    def test_no_player_name_returns_partial_facts(self):
        # Entry 3 (お知らせ) — no kanji player name in title.
        facts = extract_video_card_facts(self.r.entries[2])
        # video_url + team_name + description still populated.
        self.assertTrue(facts["video_url"])
        self.assertEqual(facts["team_name"], "巨人")
        # player_name SHOULD be empty since title has no katakana/kanji name token
        # (the renderer will then skip with missing_video_fields).
        self.assertEqual(facts["player_name"], "")

    def test_team_name_skips_giants_alias_when_picking_player(self):
        # Constructed entry: title 「巨人 ジャイアンツ 岡本」 — must pick 岡本,
        # not 巨人 / ジャイアンツ.
        e = YouTubeFeedEntry(
            video_id="vid",
            video_url="https://www.youtube.com/watch?v=vid",
            title="巨人 ジャイアンツ 岡本和真 本塁打",
        )
        facts = extract_video_card_facts(e)
        self.assertEqual(facts["player_name"], "岡本和真")

    def test_date_label_uses_japanese_format(self):
        facts = extract_video_card_facts(self.r.entries[0])
        self.assertEqual(facts["date_label"], "2026年5月6日")

    def test_description_truncated_to_280_chars(self):
        long_desc = "あ" * 500
        e = YouTubeFeedEntry(
            video_id="x",
            video_url="https://www.youtube.com/watch?v=x",
            title="巨人 岡本和真 ハイライト",
            description=long_desc,
        )
        facts = extract_video_card_facts(e)
        self.assertLessEqual(len(facts["description"]), 280)

    def test_source_url_equals_video_url(self):
        facts = extract_video_card_facts(self.r.entries[0])
        self.assertEqual(facts["source_url"], facts["video_url"])

    def test_thumbnail_carried_through(self):
        facts = extract_video_card_facts(self.r.entries[0])
        self.assertIn("hqdefault.jpg", facts["thumbnail_url"])

    def test_description_strips_embedded_urls(self):
        # YouTube descriptions routinely carry promo URLs
        # (e.g. ``https://bit.ly/3s2Un79`` GIANTS TV). Live drafting
        # surfaced these as visible raw URLs in the rendered card body
        # — a regression of the LINK-LABEL-FIX 「visible raw URL 0」
        # gate. The extractor strips http(s) URLs from the description
        # text before forwarding to the renderer; surrounding prose
        # is kept.
        e = YouTubeFeedEntry(
            video_id="vid",
            video_url="https://www.youtube.com/watch?v=vid",
            title="巨人 岡本和真 ホームラン",
            description=(
                "5月6日のヤクルト戦、岡本和真選手の本塁打 ◆「GIANTS TV」"
                "https://bit.ly/3s2Un79 公式サイト https://www.giants.jp/"
            ),
        )
        facts = extract_video_card_facts(e)
        self.assertNotIn("https://", facts["description"])
        self.assertNotIn("http://", facts["description"])
        # Surrounding prose preserved.
        self.assertIn("ヤクルト戦", facts["description"])
        self.assertIn("岡本和真", facts["description"])
        self.assertIn("GIANTS TV", facts["description"])


# ---------------------------------------------------------------------------
# End-to-end: facts → render_video_card → HTML body
# ---------------------------------------------------------------------------


class FactsToVideoRendererTests(unittest.TestCase):
    """Confirm the projected facts feed cleanly into the existing
    ``render_video_card`` so video_v1 can produce a card from a YouTube
    atom entry without any further plumbing.
    """

    def setUp(self) -> None:
        import os

        os.environ["ENABLE_NOMOTOKE_CARD_TEMPLATES"] = "1"
        from src.nomotoke_card_renderer import render_video_card

        self._render = render_video_card
        self.r = parse_youtube_atom(
            _load("giants_official_sample.xml")
        )

    def test_homerun_entry_renders_video_card(self):
        facts = extract_video_card_facts(self.r.entries[0])
        out = self._render(facts)
        self.assertTrue(out["validation_ok"])
        body = out["content_html"]
        self.assertIn("岡本和真", body)
        # The rendered card includes the video link / fallback anchor.
        self.assertIn(
            "https://www.youtube.com/watch?v=abc12345DEF", body
        )

    def test_no_player_name_entry_skips_with_missing_video_fields(self):
        facts = extract_video_card_facts(self.r.entries[2])
        out = self._render(facts)
        self.assertFalse(out["validation_ok"])
        self.assertEqual(out["skip_reason"], "missing_video_fields")


# ---------------------------------------------------------------------------
# No-side-effects: pure module
# ---------------------------------------------------------------------------


class Phase0NoSideEffectsTests(unittest.TestCase):
    def test_module_source_no_network_imports(self):
        src = (ROOT / "src" / "source_youtube_extractor.py").read_text(
            encoding="utf-8"
        )
        # Only check actual code lines (imports / function calls), not
        # mentions inside docstrings. Docstrings may legitimately reference
        # forbidden modules to explain why we're decoupled from them.
        code_lines: List[str] = []
        in_docstring = False
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                # toggle docstring state on opening / closing triple
                # (count of triples on this line; inside a docstring the
                # following content lines are skipped).
                triples = stripped.count('"""') + stripped.count("'''")
                if triples % 2 == 1:
                    in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            code_lines.append(line)
        code = "\n".join(code_lines)
        for needle in (
            "import requests",
            "from requests",
            "import urllib.request",
            "from urllib.request",
            "import urllib3",
            "import http.client",
            "import aiohttp",
            "import httpx",
            "from src.rss_fetcher",
            "import rss_fetcher",
            "wp_client.WPClient",
            "google.cloud",
            "import gemini",
            "from gemini",
            "vertexai",
        ):
            self.assertNotIn(
                needle,
                code,
                f"VIDEO-SOURCE-001 must not depend on {needle!r}",
            )

    def test_module_source_no_disk_or_robots_calls(self):
        src = (ROOT / "src" / "source_youtube_extractor.py").read_text(
            encoding="utf-8"
        )
        for needle in ("open(", "Path(", "robots.txt"):
            self.assertNotIn(
                needle,
                src,
                f"VIDEO-SOURCE-001 must not touch disk / robots: {needle!r}",
            )


if __name__ == "__main__":
    unittest.main()
