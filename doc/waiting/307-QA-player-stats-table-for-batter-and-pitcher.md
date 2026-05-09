# 307-QA player stats table for batter and pitcher

## meta

- number: 307-QA
- type: article body / player stats table / regression-safe rendering
- status: BLOCKED_USER
- priority: P1
- owner: user GO 待ち
- implementation_owner: Codex after GO
- lane: B
- created: 2026-05-09
- doc_path: `doc/waiting/307-QA-player-stats-table-for-batter-and-pitcher.md`
- note: user 制約により初手はこの Markdown 新規作成のみ。code edit、commit、push、deploy、env / scheduler 変更は GO 後まで保留

## 1. 今回の目的

選手記事で拾えている season stats を、本文内でより読みやすい table 形式に整理する。

対象は次の 2 系統。

- 打者: `打率 / 本塁打 / 打点 / 盗塁`
- 投手: `勝 / 敗 / 防御率 / 奪三振`

方針は deterministic な source-backed table block を追加することであり、LLM prose や推測で補わない。

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/tools/manual_intake.py`
- `src/rss_fetcher.py`
- 必要なら `src/nomotoke_card_renderer.py`
- 関連 unit / regression test
- 本 ticket 自身 `doc/waiting/307-QA-player-stats-table-for-batter-and-pitcher.md`

実装観点は次の 3 本に限定する。

- 打者の season stats を table 化する
- 投手の season stats を table 化する
- stats row が無い / 欠損がある時は無理に本文へ出さない

## 3. 今回触らない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- 本文の fact extraction / routing / subject match / duplicate guard の core logic
- title 生成、X 投稿生成、SEO、schema 方針
- WordPress 本番記事の手修正、WP admin 操作
- `doc/README.md` / `doc/active/assignments.md` の同期

## 4. 影響範囲

- 選手記事本文の stats block 表示
- batter / pitcher の season stats row 参照ロジック
- `manual_intake` と `rss_fetcher` の player stats block
- 必要なら `player_stats` renderer の列構成

直接影響は本文の stats rendering だが、適用条件を誤ると投手記事に野手 table が出る、または row 欠損時に不正確な `-` 埋めが広がる可能性がある。

## 5. 実行予定テスト

GO 後の予定テストは次の通り。

1. regression tests
   - 打者記事で `打率 / 本塁打 / 打点 / 盗塁` の table が出る
   - 投手記事で `勝 / 敗 / 防御率 / 奪三振` の table が出る
   - 投手記事に野手向け table を出さない
   - stats row が無い時に無理に table を出さない
2. related unit tests
   - `tests/test_manual_intake*`
   - `tests/test_rss_fetcher*`
   - 必要なら `tests/test_nomotoke_card_renderer.py`
3. full suite
   - `python3 -m unittest discover -s tests`
4. output spot-check
   - 代表的な batter / pitcher fixture で列名と値が source-backed であること

## 6. STOP条件

- table 化のために publish / mail / scheduler / env / Cloud Run 変更が必要になった場合
- stats 判定が core routing 改修へ広がる場合
- batter / pitcher 判定を安全に分岐できない場合
- 欠損値 handling のせいで既存 body contract が広く崩れる場合
- 追加テストの赤確認ができない場合
- 全件テスト green を満たせない場合

## 7. 禁止事項

- user の GO 前に code edit しない
- commit / push / deploy / env 変更 / scheduler 変更をしない
- `git add -A` を使わない
- source に無い stats を補完しない
- LLM 自由作文で成績説明を増やさない
- 投手記事へ野手 table、野手記事へ投手 table を混ぜない
- 「table 改善」の名目で publish 条件や body quality guard をついで修正しない

## 8. 想定されるデグレ

- 投手記事に打者 table が混ざる
- 打者記事に投手 table が混ざる
- `盗塁` や `奪三振` の列だけ空で見栄えが崩れる
- source row 欠損時に `0` や `-` を誤って確定値のように見せる
- 既存の compact stats line と table が重複し、本文が冗長になる
- 既存 fixture / snapshot の本文構造が崩れる

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-09 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |

## 10. Regression Memo欄

### current observation

- 現在の player stats block は compact line 寄りで、打者は `打率 / 本塁打 / 打点` が主
- `盗塁` は lineup 系 table では扱いがあるが、player stats block では table 化されていない
- 投手は compact line で `登板 / 勝 / 敗 / 防御率` が主で、`奪三振` は現行 summary に出ていない
- `player_stats` renderer 自体は table renderer を持っているため、table 化の足場は存在する

### guard hypothesis

- common guard A: stats は source-backed row のみ table 化する
- common guard B: batter / pitcher を strict に分け、他方の table を出さない
- common guard C: row / value 欠損時は無理に table を出さず compact fallback または非表示にする

## 11. 作業後追記欄

GO 後の実装完了時に、同じファイルへ次を追記する。

- 実際に変更したファイル
- diff概要
- 実行したテスト
- テスト結果
- 残った懸念
- 新しく見つかったデグレ
- 追加した回帰テスト
- 次回触ってはいけない範囲

---

## 実際に変更したファイル

- `src/tools/manual_intake.py`
- `tests/test_manual_intake.py`
- `doc/waiting/307-QA-player-stats-table-for-batter-and-pitcher.md`

## diff概要

- `manual_intake` の `関連選手` stats block で、season stats row がある場合は compact line ではなく table を優先表示するよう変更
- 打者 table を `打率 / 本塁打 / 打点 / 盗塁` に固定
- 投手 table を `勝 / 敗 / 防御率 / 奪三振` に固定
- row が無い場合は table を出さず、既存の roster line だけを維持
- compact summary fallback も `盗塁` / `奪三振` を拾えるよう補強

## 実行したテスト

1. red 確認
   - `python3 -m unittest tests.test_manual_intake.PlayerStatsTableBlockTests.test_build_player_stats_block_renders_batter_table_with_sb tests.test_manual_intake.PlayerStatsTableBlockTests.test_build_player_stats_block_renders_pitcher_table_with_strikeouts tests.test_manual_intake.PlayerStatsTableBlockTests.test_build_player_stats_block_pitcher_table_does_not_show_batter_headers`
2. 追加テスト緑化
   - 同コマンド再実行
   - `python3 -m unittest tests.test_manual_intake.PlayerStatsTableBlockTests`
3. 関連テスト
   - `python3 -m unittest tests.test_manual_intake`
   - `python3 -m unittest tests.test_source_npb_team_stats_extractor tests.test_nomotoke_card_renderer`
4. 全件
   - `python3 -m unittest discover -s tests`
   - sandbox では `test_manual_intake_service` の loopback bind 制約で失敗
   - 権限付き再実行で完走

## テスト結果

- red 確認: batter / pitcher table 化不足を 2 failure で再現
- `tests.test_manual_intake.PlayerStatsTableBlockTests`: `Ran 4 tests ... OK`
- `tests.test_manual_intake`: `Ran 59 tests ... OK`
- `tests.test_source_npb_team_stats_extractor tests.test_nomotoke_card_renderer`: `Ran 186 tests ... OK`
- full suite: `Ran 3322 tests in 71.089s ... OK`

## 残った懸念

- 今回の table 化は `manual_intake` / nomotoke renderer enrichment 側のみで、`rss_fetcher.build_news_block()` の player follow-up table には手を入れていない
- source row に列欠損がある場合は `-` を表示するため、見栄え最適化は別便の余地がある

## 新しく見つかったデグレ

- なし

## 追加した回帰テスト

- batter row が `打率 / 本塁打 / 打点 / 盗塁` table で出る
- pitcher row が `勝 / 敗 / 防御率 / 奪三振` table で出る
- pitcher table に batter header を混ぜない
- stats row 無しでは table を出さない

## 次回触ってはいけない範囲

- `publish / mail / scheduler / env / Cloud Run 設定`
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- routing / subject match / duplicate guard の core logic
