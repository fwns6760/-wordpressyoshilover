"""Tests for src/title_seo_polisher.py."""

from __future__ import annotations

import os
import unittest

from src import title_seo_polisher as polisher


class PolishTitleTests(unittest.TestCase):
    def setUp(self):
        # Default-on but make explicit for the tests.
        self._prev = os.environ.get(polisher._TITLE_SEO_ENV)
        os.environ[polisher._TITLE_SEO_ENV] = "1"

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(polisher._TITLE_SEO_ENV, None)
        else:
            os.environ[polisher._TITLE_SEO_ENV] = self._prev

    def test_strip_about_comment_filler(self):
        self.assertEqual(
            polisher.polish_title("巨人・大勢、真っ直ぐで押し切れたについてコメント"),
            "巨人・大勢、真っ直ぐで押し切れた",
        )

    def test_strip_about_filler_alone(self):
        self.assertEqual(
            polisher.polish_title("阿部監督、配球の組み立てについて"),
            "阿部監督、配球の組み立て",
        )

    def test_strip_relating_comment_filler(self):
        self.assertEqual(
            polisher.polish_title("吉川尚輝、復帰タイミングに関するコメント"),
            "吉川尚輝、復帰タイミング",
        )

    def test_html_entity_decode(self):
        # Sponichi feed leaks &#8217; in titles.
        self.assertEqual(
            polisher.polish_title("RT スポニチ野球記者&#8217;26: 防御率トップ"),
            "防御率トップ",
        )

    def test_rt_prefix_stripped(self):
        self.assertEqual(
            polisher.polish_title("RT TokyoGiants: スタメン発表"),
            "スタメン発表",
        )

    def test_leading_particle_dropped(self):
        # 助詞始まり (が) is style-forbidden.
        self.assertEqual(
            polisher.polish_title("が逆転の場面で起きたこと"),
            "逆転の場面で起きたこと",
        )

    def test_trailing_dust_trimmed(self):
        self.assertEqual(
            polisher.polish_title("巨人、ヤクルト戦で勝利。"),
            "巨人、ヤクルト戦で勝利",
        )

    def test_length_cap_applies_ellipsis(self):
        long = "巨人・吉川尚輝、5月の打率と守備指標と OPS と xBA と各種パラメータの推移を整理した記事"
        polished = polisher.polish_title(long, max_length=30)
        self.assertEqual(len(polished), 30)
        self.assertTrue(polished.endswith("…"))

    def test_protected_date_prefix_only_decoded(self):
        # 試合結果 series — leave the prefix structure untouched.
        title = "2026年5月7日 セ・リーグ 7回戦「読売ジャイアンツvs.ヤクルト」"
        self.assertEqual(polisher.polish_title(title), title)

    def test_protected_bracket_prefix(self):
        for t in (
            "【公示】2026年5月7日のプロ野球公示 巨人が抹消",
            "【一軍】巨人 0-5 ヤクルト 先発の竹丸和幸 投手は6回2/3を投げ5失点。",
            "【二軍】巨人 1-6 ハヤテ ちゅ～るスタジアム清水",
            "【YouTube】ＧＷ３勝６敗と大誤算「負け越したけど…」",
            "巨人スタメン: 1番（中）ヘルナンデス",
        ):
            with self.subTest(t=t):
                self.assertEqual(polisher.polish_title(t), t)

    def test_brand_exclamation_kept(self):
        # 動画ハイライト brand ending should not be stripped.
        self.assertEqual(
            polisher.polish_title("巨人・田中将大、歴代2位タイの日米通算203勝！！！【動画】"),
            "巨人・田中将大、歴代2位タイの日米通算203勝！！！【動画】",
        )

    def test_env_disable_is_noop(self):
        os.environ[polisher._TITLE_SEO_ENV] = "0"
        self.assertEqual(
            polisher.polish_title("巨人・大勢、真っ直ぐで押し切れたについてコメント"),
            "巨人・大勢、真っ直ぐで押し切れたについてコメント",
        )

    def test_force_overrides_env_disable(self):
        os.environ[polisher._TITLE_SEO_ENV] = "0"
        self.assertEqual(
            polisher.polish_title(
                "巨人・大勢、真っ直ぐで押し切れたについてコメント",
                force=True,
            ),
            "巨人・大勢、真っ直ぐで押し切れた",
        )

    def test_empty_input_returned_as_is(self):
        self.assertEqual(polisher.polish_title(""), "")
        self.assertEqual(polisher.polish_title("   "), "   ")

    def test_non_string_input_returned_as_is(self):
        self.assertIsNone(polisher.polish_title(None))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
