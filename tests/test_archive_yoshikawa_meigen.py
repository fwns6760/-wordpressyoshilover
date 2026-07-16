"""tests for archive_yoshikawa_meigen feeder (2026-07-16 写真ポスト紐付け + ロゴ除去)。"""

from __future__ import annotations

import unittest

from src.tools import archive_yoshikawa_meigen as feeder


def _rec(tid: str, *, permalink: str, image_url: str = "", created_at: str = "") -> dict:
    media = [{"url": image_url, "type": "photo"}] if image_url else []
    return {
        "tweet_id": tid,
        "text": f"quote-{tid}",
        "created_at": created_at or "2026-07-15T00:00:00+00:00",
        "has_media": bool(image_url),
        "media": media,
        "permalink": permalink,
    }


class StripGenericImagesTests(unittest.TestCase):
    def test_pattern_logo_stripped(self) -> None:
        recs = [_rec("a", permalink="https://ex.com/1",
                     image_url="https://news.jsports.co.jp/img/ogp-image.png")]
        changed = feeder.strip_generic_images(recs)
        self.assertEqual(changed, 1)
        self.assertFalse(recs[0]["has_media"])
        self.assertEqual(recs[0]["media"], [])

    def test_overused_image_across_3_articles_stripped(self) -> None:
        img = "https://media.example.jp/img/site-banner.png"
        recs = [
            _rec("a", permalink="https://ex.com/1", image_url=img),
            _rec("b", permalink="https://ex.com/2", image_url=img),
            _rec("c", permalink="https://ex.com/3", image_url=img),
        ]
        self.assertEqual(feeder.strip_generic_images(recs), 3)
        self.assertTrue(all(not r["has_media"] for r in recs))

    def test_same_article_multi_quotes_photo_kept(self) -> None:
        """同一記事の複数引用が記事写真を共有するのは正当 (使い回しと区別)。"""
        img = "https://number.ismcdn.jp/mwimgs/a/f/img_real_photo.jpg"
        recs = [
            _rec("a", permalink="https://number.jp/article1", image_url=img),
            _rec("b", permalink="https://number.jp/article1", image_url=img),
            _rec("c", permalink="https://number.jp/article1", image_url=img),
        ]
        self.assertEqual(feeder.strip_generic_images(recs), 0)
        self.assertTrue(all(r["has_media"] for r in recs))

    def test_matched_x_post_untouched(self) -> None:
        rec = _rec("a", permalink="https://x.com/TokyoGiants/status/1",
                   image_url="https://x.com/TokyoGiants/status/1")
        rec["matched_x_post"] = True
        self.assertEqual(feeder.strip_generic_images([rec]), 0)
        self.assertTrue(rec["has_media"])


def _fake_rss(handle: str, *, tid: str, text: str, pubdate: str, with_image: bool) -> str:
    img = '<img src="https://pbs.twimg.com/media/abc.jpg">' if with_image else ""
    return f"""<rss><channel>
<item>
<title>{text}</title>
<description>{text} {img}</description>
<link>https://x.com/{handle}/status/{tid}</link>
<pubDate>{pubdate}</pubDate>
</item>
</channel></rss>"""


class AttachMatchingPhotoPostsTests(unittest.TestCase):
    def _run(self, records: list[dict], xml: str) -> int:
        return feeder.attach_matching_photo_posts(
            records,
            fetch_fn=lambda url: xml,
            handles=["TokyoGiants"],
        )

    def test_matches_photo_post_near_article_date(self) -> None:
        recs = [_rec("a", permalink="https://news.example.jp/article",
                     created_at="2026-07-15T00:00:00+00:00")]
        xml = _fake_rss("TokyoGiants", tid="9001", text="#吉川尚輝 選手がヒーローインタビュー",
                        pubdate="Wed, 15 Jul 2026 10:00:00 GMT", with_image=True)
        self.assertEqual(self._run(recs, xml), 1)
        self.assertEqual(recs[0]["permalink"], "https://x.com/TokyoGiants/status/9001")
        self.assertTrue(recs[0]["has_media"])
        self.assertTrue(recs[0]["matched_x_post"])

    def test_no_match_when_too_far_in_time(self) -> None:
        recs = [_rec("a", permalink="https://news.example.jp/article",
                     created_at="2026-06-01T00:00:00+00:00")]
        xml = _fake_rss("TokyoGiants", tid="9002", text="吉川尚輝の猛打賞",
                        pubdate="Wed, 15 Jul 2026 10:00:00 GMT", with_image=True)
        self.assertEqual(self._run(recs, xml), 0)
        self.assertEqual(recs[0]["permalink"], "https://news.example.jp/article")

    def test_no_match_without_image(self) -> None:
        recs = [_rec("a", permalink="https://news.example.jp/article",
                     created_at="2026-07-15T00:00:00+00:00")]
        xml = _fake_rss("TokyoGiants", tid="9003", text="吉川尚輝がタイムリー",
                        pubdate="Wed, 15 Jul 2026 10:00:00 GMT", with_image=False)
        self.assertEqual(self._run(recs, xml), 0)

    def test_no_match_for_other_player(self) -> None:
        recs = [_rec("a", permalink="https://news.example.jp/article",
                     created_at="2026-07-15T00:00:00+00:00")]
        xml = _fake_rss("TokyoGiants", tid="9004", text="戸郷翔征が完投",
                        pubdate="Wed, 15 Jul 2026 10:00:00 GMT", with_image=True)
        self.assertEqual(self._run(recs, xml), 0)


if __name__ == "__main__":
    unittest.main()
