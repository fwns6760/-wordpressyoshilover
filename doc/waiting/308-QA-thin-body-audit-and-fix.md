# 308-QA thin body audit and fix for 65801 pattern

## meta

- number: 308-QA
- type: article body quality / thin-body audit / regression-safe fix
- status: BLOCKED_USER
- priority: P1
- owner: user GO 待ち
- implementation_owner: Codex after GO
- lane: B
- created: 2026-05-09
- doc_path: `doc/waiting/308-QA-thin-body-audit-and-fix.md`
- note: user 制約により初手はこの Markdown 新規作成のみ。code edit、commit、push、deploy、env / scheduler 変更は GO 後まで保留

## 1. 今回の目的

`post_id=65801` のような「公開はされたが本文が極端に薄い」記事を監査し、同系統の発生条件を特定して改善する。

今回の主眼は次の 2 点。

- `65801` がなぜ `事実カード + 短い一文` だけで公開されたかを deterministic に切り分ける
- 同系統の thin-body 記事が他にもあるかを監査し、再発を抑える narrow fix を入れる

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/rss_fetcher.py`
- 必要なら `src/body_validator.py` または thin-body 判定 helper 1 file
- thin-body 監査 / 回帰テスト
- 本 ticket 自身 `doc/waiting/308-QA-thin-body-audit-and-fix.md`

実装観点は次の 3 本に限定する。

- `65801` 系の thin-body 条件を fixture 化する
- scoreboard-only / fact-card-only postgame の publishable 判定を見直す
- 事実が薄い時は「無理に公開」ではなく deterministic な最小要約か hold に寄せる

## 3. 今回触らない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- X 投稿生成、SEO、schema、アイキャッチ選定
- WordPress 本番記事の手修正、WP admin 操作
- `doc/README.md` / `doc/active/assignments.md` の同期

## 4. 影響範囲

- postgame / scoreboard-only 記事の本文生成
- thin-body / body contract / fallback 判定
- `事実カード` と narrative block の並び
- 公開前の本文品質ガード

直接影響は本文品質だが、判定を誤ると

- 本来出せる試合結果記事まで hold する
- 逆に薄いまま publish する
- postgame の本文長だけを基準にして他 subtype へ誤適用する

可能性がある。

## 5. 実行予定テスト

GO 後の予定テストは次の通り。

1. regression tests
   - `65801` 相当 fixture で `事実カードだけ + 短文` の本文が再現されることを赤確認
   - 同条件で改善後に thin-body が解消される、または publishable から外れることを緑確認
   - `scoreboard-only postgame` 以外の通常 postgame では本文が痩せないこと
2. related unit tests
   - `tests/test_build_news_block.py`
   - `tests/test_rss_fetcher_article_quality_v1.py`
   - 必要なら thin-body / body validator 系 test
3. full suite
   - `python3 -m unittest discover -s tests`
4. output spot-check
   - 直近の postgame article fixture で本文テキスト長と事実 block の有無を確認

## 6. STOP条件

- 改善のために publish / mail / scheduler / env / Cloud Run 変更が必要になった場合
- thin-body 改善が postgame 以外の大規模 routing 改修へ広がる場合
- `65801` 相当を stable fixture として固定できない場合
- 通常 postgame 記事まで広く hold される兆候が出た場合
- 追加テストの赤確認ができない場合
- 全件テスト green を満たせない場合

## 7. 禁止事項

- user の GO 前に code edit しない
- commit / push / deploy / env 変更 / scheduler 変更をしない
- `git add -A` を使わない
- live 記事の本文を手修正して済ませない
- LLM 自由作文で thin-body を埋めない
- source に無い事実、数字、コメントを補わない
- 「thin-body 改善」の名目で publish 条件や mail 条件をついで修正しない

## 8. 想定されるデグレ

- thin-body guard が強すぎて、通常の試合結果記事まで公開されなくなる
- `事実カード` 自体まで消えて、最低限の score 情報も失う
- 短文を避けるために不自然な filler 文が増える
- postgame 以外の manager / player 記事にも誤適用される
- fixture では直っても、本番の Yahoo scoreboard 系だけ別経路で漏れる

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-09 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |

## 10. Regression Memo欄

### current observation

- `post_id=65801` は本文テキスト長が約 `211` 文字で、直近公開 50 件の中で最短
- 本文実体は `日付 + 出典 + 事実カード + CTA + 「悔しい敗戦です。」` 程度で、narrative block がほぼ無い
- 直近 50 件では `250` 文字未満は `65801` のみ
- `500` 文字未満は `65801 / 65761 / 65667 / 65671` の 4 件で、`65801` が最も極端

### guard hypothesis

- common guard A: `fact-card-only postgame` を thin-body として検出する
- common guard B: `scoreboard-only` の時は deterministic な最小要約 block を追加するか、publishable から外す
- common guard C: thin-body 判定は postgame / scoreboard 系に限定し、他 subtype へ広げない

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

### 実際に変更したファイル

- `src/thin_body_validator.py`
- `tests/test_thin_body_validator.py`
- `tests/test_wp_client.py`
- `doc/waiting/308-QA-thin-body-audit-and-fix.md`

### diff概要

- `65801` 系の scoreboard-only postgame body を `postgame_scorecard_only` として thin-body STOP gate に追加
- 判定は `nomotoke card footer + 試合スコア heading + generic closing + detail section 不在 + text short` の narrow 条件に限定
- renderer 出力を直接使った regression test を追加
- `WPClient.create_post()` chokepoint で該当 body が実際に stop される integration test を追加

### 実行したテスト

1. red 確認
   - `python3 -m unittest tests.test_thin_body_validator.TestScoreboardOnlyPostgameDetection`
   - `python3 -m unittest tests.test_wp_client.TestThinBodyStopGate.test_scoreboard_only_postgame_card_raises_thin_body_stop`
2. 追加テスト緑化
   - 同コマンドを再実行
3. 関連テスト
   - `python3 -m unittest tests.test_thin_body_validator tests.test_wp_client tests.test_nomotoke_card_renderer`
   - `python3 -m unittest tests.test_build_news_block tests.test_rss_fetcher_article_quality_v1`
4. 全件
   - `python3 -m unittest discover -s tests`
   - sandbox 失敗後、権限付きで再実行

### テスト結果

- red 確認: 追加した thin-body / wp_client test は修正前に fail
- 追加テスト緑化: `4 tests` green
- 関連テスト:
  - `243 tests` green
  - `65 tests` green
- 全件:
  - sandbox は `test_manual_intake_service` の loopback bind 制約で fail
  - 権限付き再実行で `Ran 3326 tests ... OK`

### 残った懸念

- 今回は `nomotoke` の scoreboard-only postgame HTML を thin-body STOP gate で止める fix であり、本文を厚く生成する fix ではない
- `65801` と同系統でも renderer 経路が別なら漏れる可能性がある
- 実 live で出ている thin-body 記事の route を完全に 1 本化したわけではない

### 新しく見つかったデグレ

- なし

### 追加した回帰テスト

- rendered scoreboard-only postgame card が thin 判定されること
- opposing pitcher だけ足しても thin 判定のままであること
- detail section を持つ postgame card は thin 判定されないこと
- `WPClient.create_post()` が scoreboard-only postgame card を `thin_body_stop: postgame_scorecard_only` で拒否すること

### 次回触ってはいけない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- X 投稿生成、SEO、schema、アイキャッチ選定
