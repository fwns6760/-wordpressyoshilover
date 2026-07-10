"""fan_pulse — ファンの反応まとめ 記事+ポスト (2026-07-10 user GO)。"""

import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src import fan_pulse as fp

JST = timezone(timedelta(hours=9))
_NOON = datetime(2026, 7, 10, 12, 5, tzinfo=JST)

_REACTIONS = [
    {"summary": f"ティマは二軍では打ってるのに一軍だと苦しいな その{i}",
     "link": f"https://x.com/fan{i}/status/{i}", "rt": 5, "like": 30}
    for i in range(1, 7)
]

_PARTS = {
    "intro": "ティマ選手の一軍起用を巡って、ファンの間で議論が広がっています。",
    "points": "・二軍の好成績と一軍の結果の差を指摘する声\n・リチャード選手の昇格を望む意見",
    "close": "我慢して使うか、入れ替えるか。皆さんはどう見ますか。",
    "post": "ティマの一軍起用を巡ってファンの議論が活発です。二軍では好成績、一軍では苦戦。リチャード昇格待望論も出ています。",
}


class BuildTests(unittest.TestCase):
    def _build(self, **kw):
        wp = MagicMock()
        wp.create_post.return_value = 999
        wp.get_post.return_value = {"link": "https://yoshilover.com/999"}
        kw.setdefault("now", _NOON)
        kw.setdefault("window", "noon")
        kw.setdefault("gemini_api_key", "k")
        kw.setdefault("dedup_set", set())
        kw.setdefault("wp_client_factory", lambda: wp)
        with patch.object(fp, "_noon_topic", return_value=("ティマ", "ティマを巡るファンの反応")), \
             patch.object(fp, "gather_reactions", return_value=list(_REACTIONS)), \
             patch.object(fp, "_summarize", return_value=dict(_PARTS)), \
             patch.object(fp, "_eyecatch_media_id", return_value=123):
            return fp.build_fan_pulse(**kw), wp

    def test_creates_article_and_candidate(self):
        cand, wp = self._build()
        self.assertIsNotNone(cand)
        # 記事: publish + アイキャッチ + oEmbed 埋め込み
        kwargs = wp.create_post.call_args.kwargs
        args = wp.create_post.call_args.args
        self.assertIn("【ファンの反応】", args[0])
        self.assertEqual(kwargs["status"], "publish")
        self.assertEqual(kwargs["featured_media"], 123)
        html = args[1]
        self.assertIn("twitter-tweet", html)
        self.assertIn("https://x.com/fan1/status/1", html)
        self.assertIn("論点まとめ", html)
        self.assertIn("公開ポストをもとに構成", html)
        # ポスト候補
        self.assertEqual(cand.metric, "FAN_PULSE")
        self.assertEqual(cand.post_text, _PARTS["post"])
        self.assertIn("https://yoshilover.com/999", cand.draft_text)

    def test_dedup_once_per_window_day(self):
        sig = "fanpulse|" + hashlib.sha1(b"20260710|noon").hexdigest()[:16]
        cand, _ = self._build(dedup_set={sig})
        self.assertIsNone(cand)

    def test_few_reactions_skips(self):
        with patch.object(fp, "_noon_topic", return_value=("ティマ", "t")), \
             patch.object(fp, "gather_reactions", return_value=_REACTIONS[:2]):
            self.assertIsNone(fp.build_fan_pulse(
                now=_NOON, window="noon", gemini_api_key="k", dedup_set=set()
            ))

    def test_no_topic_skips(self):
        with patch.object(fp, "_noon_topic", return_value=("", "")):
            self.assertIsNone(fp.build_fan_pulse(
                now=_NOON, window="noon", gemini_api_key="k", dedup_set=set()
            ))

    def test_wp_failure_returns_none(self):
        wp = MagicMock()
        wp.create_post.side_effect = RuntimeError("wp down")
        with patch.object(fp, "_noon_topic", return_value=("ティマ", "t")), \
             patch.object(fp, "gather_reactions", return_value=list(_REACTIONS)), \
             patch.object(fp, "_summarize", return_value=dict(_PARTS)), \
             patch.object(fp, "_eyecatch_media_id", return_value=None):
            self.assertIsNone(fp.build_fan_pulse(
                now=_NOON, window="noon", gemini_api_key="k",
                dedup_set=set(), wp_client_factory=lambda: wp,
            ))


if __name__ == "__main__":
    unittest.main()
