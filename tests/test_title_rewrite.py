import json
import unittest
from pathlib import Path

from src import rss_fetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class DisplayTitleRewriteTests(unittest.TestCase):
    def test_title_rewrite_golden_fixture(self):
        with open(FIXTURE_DIR / "title_rewrite_golden.json", encoding="utf-8") as f:
            cases = json.load(f)
        with open(rss_fetcher.KEYWORDS_FILE, encoding="utf-8") as f:
            keywords = json.load(f)

        for case in cases:
            with self.subTest(case=case["name"]):
                title = case["title"]
                summary = case.get("summary", "")
                category = case.get("category")
                if "expected_category" in case:
                    category = rss_fetcher.classify_category(f"{title} {summary}", keywords)
                    self.assertEqual(category, case["expected_category"])
                rewritten = rss_fetcher.rewrite_display_title(
                    title,
                    summary,
                    category,
                    case.get("has_game", True),
                )
                self.assertEqual(rewritten, case["expected_title"])

    def test_lineup_candidates_are_aggregated_across_sources(self):
        candidates = [
            {
                "entry_index": 0,
                "source_rank": 0,
                "source_name": "スポーツ報知",
                "source_type": "news",
                "post_url": "https://example.com/hochi",
                "category": "試合速報",
                "title": "【巨人】今日のスタメン発表　1番丸、4番岡田",
                "summary": "巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。",
                "entry_has_game": True,
                "published_day": "2026-04-14",
                "history_urls": ["https://example.com/hochi"],
                "history_title_norms": ["titlea"],
            },
            {
                "entry_index": 1,
                "source_rank": 1,
                "source_name": "日刊スポーツ",
                "source_type": "news",
                "post_url": "https://example.com/nikkan",
                "category": "試合速報",
                "title": "【巨人】スタメン発表　岡田が4番、甲斐が先発マスク",
                "summary": "巨人が阪神戦のスタメンを発表した。甲斐拓也が先発マスクに入った。",
                "entry_has_game": True,
                "published_day": "2026-04-14",
                "history_urls": ["https://example.com/nikkan"],
                "history_title_norms": ["titleb"],
            },
        ]

        aggregated = rss_fetcher._aggregate_lineup_candidates(candidates)

        self.assertEqual(len(aggregated), 1)
        self.assertEqual(aggregated[0]["merged_source_count"], 2)
        self.assertIn("スポーツ報知", aggregated[0]["source_name"])
        self.assertIn("日刊スポーツ", aggregated[0]["source_name"])
        self.assertIn("甲斐拓也が先発マスクに入った", aggregated[0]["summary"])

    def test_classify_category_routes_farm_lineup_to_development(self):
        keywords = {
            "試合速報": ["スタメン", "打順"],
            "ドラフト・育成": ["二軍", "ファーム"],
        }

        category = rss_fetcher.classify_category("【二軍】巨人対DeNA 4番ショートでスタメン", keywords)

        self.assertEqual(category, "ドラフト・育成")

    def test_classify_category_routes_fullwidth_2gun_article_to_development(self):
        keywords = {
            "選手情報": ["昇格", "復帰"],
            "ドラフト・育成": ["育成", "2軍", "２軍", "ファーム"],
        }

        category = rss_fetcher.classify_category(
            "巨人育成ドミニカンが２軍戦猛打＆Ｖ２号 同郷ルシアーノの支配下昇格が刺激…６年目",
            keywords,
        )

        self.assertEqual(category, "ドラフト・育成")

    def test_extract_player_status_topic_does_not_treat_farm_story_as_ichigun_shokaku(self):
        title = "巨人育成ドミニカンが２軍戦猛打＆Ｖ２号 同郷ルシアーノの支配下昇格が刺激…６年目"
        summary = "巨人育成ドミニカンのティマが２軍戦で猛打＆Ｖ２号。育成選手としてプレーしている。"

        topic = rss_fetcher._extract_player_status_topic(title, summary)

        self.assertEqual(topic, "二軍戦")

    def test_manager_title_prefers_angle_over_source_headline(self):
        title = "【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督、若手積極起用で競争期待"
        summary = "阿部監督が「レギュラーは決まってません。結果残せば使います」と話した。若手積極起用で競争を促す考えを示した。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "首脳陣", False)

        self.assertEqual(rewritten, "阿部監督「レギュラーは決まってません。結果残せば使います」 若手起用で序列はどう…")

    def test_player_title_becomes_reader_angle(self):
        title = "【巨人】大胆フォーム変更の戸郷翔征「人の助言を取り入れることも重要」久保コーチとの取り組み"
        summary = "ファームでフォーム改造中の巨人戸郷翔征投手が調整した。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "選手情報", False)

        self.assertEqual(rewritten, "戸郷翔征、フォーム変更のポイントはどこか")

    def test_player_title_keeps_full_name_without_role_suffix(self):
        title = "【巨人】田中将大が２軍戦で先発へ"
        summary = "田中将大が2軍戦で先発する予定。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "選手情報", False)

        self.assertEqual(rewritten, "田中将大の現状整理 いま何を見たいか")

    def test_player_quote_title_prefers_game_angle_over_generic_change_label(self):
        title = "【巨人】田中将大「打線を線にしない」甲子園の“申し子”が移籍後初の阪神戦で好投誓う"
        summary = "田中将大が移籍後初の阪神戦に向け「打線を線にしない」と話した。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "選手情報", False)

        self.assertEqual(rewritten, "田中将大「打線を線にしない」 実戦で何を見せるか")

    def test_extract_subject_label_finds_name_from_rotation_context(self):
        title = "巨人が１４日からの阪神３連戦で先発ローテを再編 初戦は則本昂大 第２戦は田中将大"
        summary = "巨人が14日からの阪神3連戦で先発ローテを再編。初戦は則本昂大、第2戦は田中将大が務める見込み。"

        subject = rss_fetcher._extract_subject_label(title, summary, "選手情報")

        self.assertEqual(subject, "田中将大")

    def test_extract_subject_label_handles_middle_dot_after_team_name(self):
        title = "巨人・田中将大「打線を線にしない」甲子園の“申し子”が移籍後初の阪神戦で好投誓う"
        summary = "田中将大が移籍後初の阪神戦に向け「打線を線にしない」と話した。"

        subject = rss_fetcher._extract_subject_label(title, summary, "選手情報")
        role_label = rss_fetcher._extract_player_role_label(title, summary)

        self.assertEqual(subject, "田中将大")
        self.assertEqual(role_label, "田中将大投手")

    def test_extract_subject_label_handles_name_after_initial_start_context(self):
        title = "【巨人】伝統の一戦初先発の田中将大「投げる試合すべて勝つ気持ちで」２試合連続ＱＳで日米通算２０２勝マーク"

        subject = rss_fetcher._extract_subject_label(title, "", "試合速報")

        self.assertEqual(subject, "田中将大")

    def test_game_pregame_title_keeps_name_after_initial_start_context(self):
        title = "【巨人】伝統の一戦初先発の田中将大「投げる試合すべて勝つ気持ちで」２試合連続ＱＳで日米通算２０２勝マーク"

        rewritten = rss_fetcher.rewrite_display_title(title, "", "試合速報", True)

        self.assertEqual(rewritten, "田中将大先発でどこを見たいか")

    def test_extract_subject_label_prefers_first_pitcher_after_context_phrase(self):
        title = "今日の先発は戸郷、阿部監督が選んだのは菅野"

        subject = rss_fetcher._extract_subject_label(title, "", "選手情報")

        self.assertEqual(subject, "戸郷")

    def test_extract_subject_label_handles_multiple_players_joined_by_middle_dot(self):
        title = "坂本・丸が状態上向き、打線再編へ"

        subject = rss_fetcher._extract_subject_label(title, "", "選手情報")

        self.assertEqual(subject, "坂本・丸")

    def test_player_title_handles_middle_dot_foreign_name_join_story(self):
        title = "トラビス・バーンズが一軍合流へ"
        summary = "トラビス・バーンズが合流へ。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "選手情報", False)

        self.assertEqual(rewritten, "トラビス・バーンズ、一軍合流でどこを見たいか")

    def test_player_title_handles_long_foreign_name_without_falling_back_to_generic_subject(self):
        title = "カール・エドワーズ・ジュニアが来日初登板へ"
        summary = "カール・エドワーズ・ジュニアが初登板へ。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "選手情報", False)

        self.assertEqual(rewritten, "カール・エドワーズ・ジュニアの現状整理 いま何を見たいか")

    def test_extract_subject_label_keeps_staff_role_compound(self):
        title = "桑田投手コーチが見た戸郷の修正点"
        summary = "桑田投手コーチが戸郷の修正点を語った。"

        subject = rss_fetcher._extract_subject_label(title, summary, "首脳陣")

        self.assertEqual(subject, "桑田投手コーチ")

    def test_lineup_title_drops_source_like_duplication(self):
        title = "【巨人】今日のスタメン発表　1番丸、4番岡田"
        summary = "巨人が阪神戦のスタメンを発表した。1番に丸佳浩、4番に岡田悠希が入った。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "試合速報", True)

        self.assertEqual(rewritten, "巨人スタメン 1番丸、4番岡田でどこを動かしたか")

    def test_farm_lineup_title_gets_separate_angle(self):
        title = "【二軍】巨人対DeNA 4番ショートでスタメン"
        summary = "巨人の二軍スタメンが発表され、若手の配置に注目が集まった。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "ドラフト・育成", True)

        self.assertEqual(rewritten, "巨人二軍スタメン 若手をどう並べたか")

    def test_postgame_title_prefers_reader_angle_over_generic_flow_label(self):
        title = "【巨人】今季２度目の０封負けで連敗　井上温大は６回２失点も打線が沈黙"
        summary = "巨人はヤクルト投手陣を攻略できず、今季2度目の0封負けを喫した。先発井上温大投手は6回6安打2失点と粘投したが、打線の援護なく今季2敗目を喫した。"

        rewritten = rss_fetcher.rewrite_display_title(title, summary, "試合速報", True)

        self.assertEqual(rewritten, "巨人ヤクルト戦 打線沈黙で何が止まったか")

    def test_parse_yahoo_team_batting_stats_extracts_core_stats(self):
        html = """
        <table>
          <tr><th>位置</th><th>背番号</th><th>選手名</th><th>打率</th><th>試合</th><th>打席</th><th>打数</th><th>安打</th><th>二塁打</th><th>三塁打</th><th>本塁打</th><th>塁打</th><th>打点</th><th>得点</th><th>三振</th><th>四球</th><th>死球</th><th>犠打</th><th>犠飛</th><th>盗塁</th></tr>
          <tr><td>外</td><td>8</td><td><a href="/npb/player/1/top">丸 佳浩</a></td><td>.281</td><td>14</td><td>60</td><td>55</td><td>15</td><td>2</td><td>0</td><td>3</td><td>26</td><td>12</td><td>8</td><td>11</td><td>4</td><td>0</td><td>0</td><td>1</td><td>2</td></tr>
        </table>
        """

        stats = rss_fetcher._parse_yahoo_team_batting_stats(html)

        self.assertEqual(stats["丸佳浩"]["avg"], ".281")
        self.assertEqual(stats["丸佳浩"]["hr"], "3")
        self.assertEqual(stats["丸佳浩"]["rbi"], "12")
        self.assertEqual(stats["丸佳浩"]["sb"], "2")

    def test_parse_yahoo_starting_lineup_extracts_giants_rows(self):
        html = """
        <div id="async-starting">
          <section>
            <h3>阪神</h3>
            <table>
              <tr><th>打順</th><th>位置</th><th>選手名</th><th>打</th><th>打率</th><th>調子</th></tr>
              <tr><td>1</td><td>中</td><td>近本 光司</td><td>左</td><td>.310</td><td>好調</td></tr>
            </table>
            <h3>巨人</h3>
            <table>
              <tr><th>打順</th><th>位置</th><th>選手名</th><th>打</th><th>打率</th><th>調子</th></tr>
              <tr><td>1</td><td>中</td><td>丸 佳浩</td><td>左</td><td>.281</td><td>普通</td></tr>
              <tr><td>4</td><td>左</td><td>岡田 悠希</td><td>右</td><td>.298</td><td>好調</td></tr>
            </table>
          </section>
        </div>
        <div id="async-bench"></div>
        """

        rows = rss_fetcher._parse_yahoo_starting_lineup(html, team_label="巨人", opponent_label="阪神")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "丸 佳浩")
        self.assertEqual(rows[1]["avg"], ".298")

    def test_extract_opponent_name_prefers_non_giants_team(self):
        html = """
        <div class="bb-gameScoreTable__teamName">巨人</div>
        <div class="bb-gameScoreTable__teamName">ソフトバンク</div>
        """

        opponent = rss_fetcher._extract_opponent_name_from_game_html(html, team_label="巨人")

        self.assertEqual(opponent, "ソフトバンク")

    def test_merge_lineup_rows_with_team_stats_fills_hr_rbi_sb(self):
        lineup_rows = [
            {"order": "1", "position": "中", "name": "丸 佳浩", "avg": ".281"},
            {"order": "4", "position": "左", "name": "岡田 悠希", "avg": ".298"},
        ]
        team_stats = {
            "丸佳浩": {"name": "丸 佳浩", "avg": ".281", "hr": "3", "rbi": "12", "sb": "2"},
            "岡田悠希": {"name": "岡田 悠希", "avg": ".298", "hr": "5", "rbi": "18", "sb": "1"},
        }

        rows = rss_fetcher._merge_lineup_rows_with_stats(lineup_rows, team_stats)

        self.assertEqual(rows[0]["hr"], "3")
        self.assertEqual(rows[1]["rbi"], "18")
        self.assertEqual(rows[1]["sb"], "1")


if __name__ == "__main__":
    unittest.main()
