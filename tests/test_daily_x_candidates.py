"""Tests for daily_x_candidates (449 §5 RSS話題ゲート, read-only)."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from src.tools import daily_x_candidates as dxc


class FreshnessGateTests(unittest.TestCase):
    """ゲート②: 最終出場が最新試合日から FRESH_DAYS 以内のみ fresh。"""

    def test_recent_is_fresh(self) -> None:
        self.assertTrue(dxc._is_fresh("2026-05-31", "2026-05-31"))
        self.assertTrue(dxc._is_fresh("2026-05-28", "2026-05-31"))  # 3日差 = 境界内

    def test_stale_excluded(self) -> None:
        # 平山型: 最終出場 5/22、最新試合 5/31 → 9日差で除外
        self.assertFalse(dxc._is_fresh("2026-05-22", "2026-05-31"))

    def test_missing_dates(self) -> None:
        self.assertFalse(dxc._is_fresh(None, "2026-05-31"))
        self.assertFalse(dxc._is_fresh("2026-05-31", None))


class RosterMoveRegexTests(unittest.TestCase):
    """昇格/抹消タイトルから数字を拾う(出典=記事)。"""

    def test_extracts_numbers(self) -> None:
        title = "巨人が森田駿哉を一軍登録 ファーム8登板、防御率1.65と好調の左腕が再昇格"
        nums = []
        for pat in dxc.NUM_PATTERNS:
            nums.extend(pat.findall(title))
        self.assertTrue(any("防御率1.65" in n for n in nums))
        self.assertTrue(any("8登板" in n for n in nums))

    def test_move_keyword_detect(self) -> None:
        self.assertTrue(any(kw in "今季初昇格・登録抹消" for kw in dxc.ROSTER_MOVE_KEYWORDS))


class IchigunPipelineTests(unittest.TestCase):
    """巨人ロスター ∩ 鮮度ゲート ∩ 日付ベース数字 の統合(in-memory DB)。"""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        conn = sqlite3.connect(self.tmp.name)
        conn.executescript(
            """
            CREATE TABLE advanced_metric_snapshots(
                snapshot_date TEXT, scope TEXT, player_canonical TEXT, team_code TEXT,
                metric_name TEXT, metric_value REAL, sample_size INT,
                league_rank INT, league_total INT);
            CREATE TABLE article_candidates(
                player_canonical TEXT, signal_type TEXT, current_value TEXT, created_at TEXT);
            CREATE TABLE games(game_id TEXT, game_date TEXT);
            CREATE TABLE batting_logs(game_id TEXT, player_canonical TEXT);
            CREATE TABLE pitching_logs(game_id TEXT, player_canonical TEXT);
            """
        )
        # 巨人2選手: 岸田(fresh, 5/31) と 平山(stale, 5/22)。他球団 佐藤輝明 も混ぜる。
        conn.executemany(
            "INSERT INTO advanced_metric_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("2026-05-31", "last_7d", "岸田 行倫", "g", "AVG", 0.444, 12, 5, 127),
                ("2026-05-31", "last_7d", "平山 功太", "g", "AVG", 0.350, 10, 8, 127),
                ("2026-05-31", "last_7d", "佐藤輝明", "t", "AVG", 0.400, 12, 3, 127),
            ],
        )
        conn.executemany(
            "INSERT INTO article_candidates VALUES (?,?,?,?)",
            [
                ("岸田 行倫", "batter_hit_streak", "5試合連続安打", "2026-05-31T22:00:00"),
                ("平山 功太", "batter_hit_streak", "8試合連続安打", "2026-05-31T22:00:00"),
                ("佐藤輝明", "batter_hit_streak", "5試合連続安打", "2026-05-31T22:00:00"),
            ],
        )
        conn.executemany("INSERT INTO games VALUES (?,?)", [
            ("g1", "2026-05-31"), ("g2", "2026-05-22"),
        ])
        conn.executemany("INSERT INTO batting_logs VALUES (?,?)", [
            ("g1", "岸田 行倫"), ("g2", "平山 功太"), ("g1", "佐藤輝明"),
        ])
        conn.commit()
        conn.close()
        self._prev = os.environ.get("INSIGHT_DB_PATH")
        os.environ["INSIGHT_DB_PATH"] = self.tmp.name

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("INSIGHT_DB_PATH", None)
        else:
            os.environ["INSIGHT_DB_PATH"] = self._prev
        os.unlink(self.tmp.name)

    def test_giants_only_and_fresh_only(self) -> None:
        conn = sqlite3.connect(self.tmp.name)
        cands = dxc.collect_ichigun_candidates(conn.cursor())
        conn.close()
        players = {c.player for c in cands}
        self.assertIn("岸田 行倫", players)        # 巨人 + fresh
        self.assertNotIn("平山 功太", players)      # 巨人だが stale → ゲート②で除外
        self.assertNotIn("佐藤輝明", players)        # fresh だが他球団 → ゲート①で除外

    def test_kishida_uses_date_based_number(self) -> None:
        conn = sqlite3.connect(self.tmp.name)
        cands = {c.player: c for c in dxc.collect_ichigun_candidates(conn.cursor())}
        conn.close()
        self.assertIn("直近7日", cands["岸田 行倫"].number)
        self.assertIn(".444", cands["岸田 行倫"].number)


class NewsAnchoredTests(IchigunPipelineTests):
    """ニュース起点: 記事タイトルの巨人選手にデータを紐付ける(ゲート①の DB を継承)。"""

    def test_news_links_giants_player_data(self) -> None:
        conn = sqlite3.connect(self.tmp.name)
        posts = [
            {"title": {"rendered": "巨人・岸田行倫が決勝打 好調キープ"}, "link": "https://x/1"},
            {"title": {"rendered": "【巨人データ】岸田行倫 打率セ2位"}, "link": "https://x/2"},  # 自前→除外
            {"title": {"rendered": "阪神・佐藤輝明が満塁弾"}, "link": "https://x/3"},  # 他球団→紐付かない
        ]
        cands = dxc.collect_news_anchored(conn.cursor(), posts)
        conn.close()
        joined = " ".join(c.player + c.number for c in cands)
        self.assertIn("岸田 行倫", joined)         # 記事の巨人選手にデータ紐付け
        self.assertIn(".444", joined)               # last_7d データ
        self.assertNotIn("佐藤輝明", joined)         # 他球団は紐付かない
        # 【巨人データ】post は除外(冗長回避)
        self.assertTrue(all("x/2" not in c.source for c in cands))
        # 全候補に締めの願望(reaction)が入る
        self.assertTrue(cands and all(c.reaction for c in cands))


class PostCompositionTests(unittest.TestCase):
    def test_post_text_facts_and_reaction_only(self) -> None:
        c = dxc.Candidate("直近変化型", "岸田 行倫", "岸田行倫 直近10試合 打率.412(39打席)・セ2位",
                          "insight.db", context="今季通算は打率.270(180打席)",
                          reaction="ここから乗っていってほしい。")
        post = c.post_text()
        self.assertIn(".412", post)            # 検証数字
        self.assertIn("今季通算", post)         # 検証文脈
        self.assertIn("乗っていって", post)     # 願望

    def test_reaction_is_wish_no_claim(self) -> None:
        # 願望のみ(型でトーンは変わるが事実主張しない)
        self.assertTrue(dxc._reaction("防御率1.65で1軍昇格"))
        self.assertTrue(dxc._reaction("打率.412・セ2位"))
        self.assertTrue(dxc._reaction("7試合連続安打"))

    def test_has_hook_gate(self) -> None:
        strong = dxc.Candidate("直近変化型", "岸田", "岸田 直近 打率.412", "db")
        thin = dxc.Candidate("直近変化型", "井上", "井上 今試合6番", "signal")
        thin_quote = dxc.Candidate("直近変化型", "井上", "井上 今試合6番", "signal",
                                   quote="悪いイメージは気にしない")
        self.assertTrue(dxc._has_hook(strong))    # 数字hookあり
        self.assertFalse(dxc._has_hook(thin))     # 打順だけ→除外
        self.assertTrue(dxc._has_hook(thin_quote))  # 発言があれば可

    def test_combined_mail_one_email_all_cards(self) -> None:
        cands = [
            dxc.Candidate("ニュース連動", "岸田 行倫(記事: …)", "岸田行倫 直近7日 打率.444",
                          "https://x/1", reaction="今日も期待したい。", article_url="https://y/9"),
            dxc.Candidate("直近変化型", "キャベッジ", "キャベッジ 7試合連続安打", "db",
                          reaction="続けてほしい。"),
        ]
        subj, text, html = dxc.build_combined_mail(cands, date_label="2026-06-01")
        self.assertIn("2件", subj)                         # 1通に2件
        self.assertIn(".444", html)
        self.assertIn("キャベッジ", html)                   # 両方含む
        self.assertEqual(html.count("𝕏 にポストする"), 2)   # 候補ごとにボタン
        self.assertIn("今日も期待したい。", html)
        self.assertIn("記事を読む", html)                   # 記事URLあるカードに

    def test_quote_shown_with_caution(self) -> None:
        c = dxc.Candidate("ニュース連動", "浦田俊輔", "浦田俊輔 直近7日 .273", "https://x/1",
                          quote="何とか打って恩返しをできたらと…やりました！",
                          reaction="期待したい。")
        _, _, html = dxc.build_combined_mail([c], date_label="2026-06-01")
        self.assertIn("やりました", html)
        self.assertIn("発言の主は記事で確認", html)         # 発言主の注意書き


class LlmPolishGuardTests(unittest.TestCase):
    def test_post_text_prefers_polished(self) -> None:
        c = dxc.Candidate("直近変化型", "岸田", "岸田 直近 打率.412", "db",
                          reaction="頼む。", polished="岸田行倫、直近.412\n来てるわ")
        self.assertEqual(c.post_text(), "岸田行倫、直近.412\n来てるわ")

    def test_post_text_falls_back_to_facts(self) -> None:
        c = dxc.Candidate("直近変化型", "岸田", "岸田 直近 打率.412", "db", reaction="頼む。")
        self.assertIn(".412", c.post_text())   # polished 無し → fact 版
        self.assertIn("頼む", c.post_text())

    def test_allowed_rate_tokens(self) -> None:
        c = dxc.Candidate("直近変化型", "岸田", "岸田 直近10試合 打率.412(39打席)", "db",
                          context="今季通算は打率.270")
        allowed = dxc._allowed_rate_tokens(c)
        self.assertIn(".412", allowed)   # 先頭0なし野球表記も捕捉
        self.assertIn(".270", allowed)
        # 事実に無い rate(.999)は許可集合に入らない=出力に出たら却下される
        self.assertNotIn(".999", allowed)

    def test_rate_regex_catches_baseball_style(self) -> None:
        self.assertIn(".412", dxc._RATE_RE.findall("直近.412は見事"))   # 先頭0なし
        self.assertIn("1.65", dxc._RATE_RE.findall("防御率1.65で昇格"))


class PositionAndPositiveGateTests(unittest.TestCase):
    def test_quote_fits_position(self) -> None:
        pitch_q = "どんどん攻めて自分の投球ができた"
        # 投手発言を野手(is_pitcher=False)に付けない
        self.assertFalse(dxc._quote_fits_position(pitch_q, False))
        self.assertTrue(dxc._quote_fits_position(pitch_q, True))   # 投手ならOK
        self.assertTrue(dxc._quote_fits_position("最後まで集中して振り切れた", False))  # 打撃発言は野手OK
        self.assertTrue(dxc._quote_fits_position("", False))       # 引用なしはOK

    def test_positive_hook_batter(self) -> None:
        self.assertFalse(dxc._is_positive_hook("ティマ 直近7日 打率.000(7打席)", is_pitcher=False))  # 不調除外
        self.assertTrue(dxc._is_positive_hook("岸田 直近 打率.412(39打席)", is_pitcher=False))
        self.assertTrue(dxc._is_positive_hook("◯◯ 打率.210・セ2位", is_pitcher=False))  # 順位あればOK
        self.assertTrue(dxc._is_positive_hook("◯◯ 7試合連続安打", is_pitcher=False))  # 記録はOK

    def test_positive_hook_pitcher(self) -> None:
        self.assertTrue(dxc._is_positive_hook("戸郷 防御率1.29(投球回基準7)", is_pitcher=True))
        self.assertFalse(dxc._is_positive_hook("◯◯ 防御率5.40(投球回基準10)", is_pitcher=True))  # 悪い側除外


class ExtractQuoteTests(unittest.TestCase):
    def test_keeps_speech_drops_noise(self) -> None:
        html = ('<p>見出し</p>'
                '<p>「野村克也門下生対決」</p>'           # ノイズ(対決名)
                '<p>本人は「何とか打って恩返しをできたらと…やりました！」と振り返った。</p>'  # 発言
                '<p>「北海道日本ハムファイターズvs.読売ジャイアンツ」</p>')  # ノイズ(カード)
        q = dxc._extract_quote(html)
        self.assertIn("やりました", q)
        self.assertNotIn("門下生", q)
        self.assertNotIn("ファイターズ", q)

    def test_empty_when_no_quote(self) -> None:
        self.assertEqual(dxc._extract_quote("<p>引用なしの本文</p>"), "")
        self.assertEqual(dxc._extract_quote(""), "")

    def test_proximity_picks_quote_near_player(self) -> None:
        html = ("<p>岸田行倫は「最後まで集中して振り切れました」と笑顔。</p>"
                + "<p>" + "余白" * 200 + "</p>"
                + "<p>別の選手は「もっと頑張りたいです」と話した。</p>")
        self.assertIn("振り切れました", dxc._extract_quote(html, "岸田 行倫"))

    def test_no_quote_when_player_far(self) -> None:
        html = ("<p>無関係の前置き。</p>" + "<p>" + "余白" * 200 + "</p>"
                + "<p>誰かが「やってやりました」と話した。</p>")
        # 選手名が本文に出てこない → 引用は付けない(誤帰属防止)
        self.assertEqual(dxc._extract_quote(html, "存在しない 選手"), "")

    def test_flatten_order(self) -> None:
        res = {"news": [dxc.Candidate("ニュース連動", "A", "n", "m", "")],
               "hidden_hot": [dxc.Candidate("直近変化型", "B", "n", "m", "")]}
        flat = dxc.flatten_candidates(res)
        self.assertEqual([c.player for c in flat], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
