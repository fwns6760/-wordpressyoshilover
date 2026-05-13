# 310-QA player manager X reaction expansion

## meta

- number: 310-QA
- type: player / manager body / X reaction expansion / regression-safe rendering
- status: CLOSED, LIVE_VERIFIED
- priority: P1
- owner: Claude (実装+deploy 済)
- implementation_owner: completed in commit `f87af66` (2026-05-10 00:47 JST)
- lane: B
- created: 2026-05-10
- closed: 2026-05-13 (user "まとめて GO" 承認、doc 同期遅延の解消)
- doc_path: `doc/done/2026-05/310-QA-player-manager-x-reaction-expansion.md`
- prod_status: live since 2026-05-10、prod revision `00417-wuw` (hotfix B = `b8a7f01`) の ancestor として稼働中

## 1. 今回の目的

`選手情報 / 首脳陣` 記事で X reaction を今より増やし、掲示板っぽさを強める。

ただし目的は量ではなく、

- 選手違いを混ぜない
- 話題違いを混ぜない
- 主観や煽りだけを本文の核にしない

という条件の中で、安全に `2〜3件` 程度へ拡張すること。

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/rss_fetcher.py`
- 必要なら reaction selector helper 1 file
- player / manager X reaction 関連 test
- 本 ticket 自身 `doc/waiting/310-QA-player-manager-x-reaction-expansion.md`

実装観点は次の 3 本に限定する。

- player 記事の X reaction を `2〜3件` に拡張する
- manager 記事の X reaction を `2〜3件` に拡張する
- full-name / topic strict match を維持したまま件数だけ増やす

## 3. 今回触らない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- postgame table / scorecard 構造
- X 自動投稿、SEO、schema、アイキャッチ選定
- WordPress 本番記事の手修正、WP admin 操作

## 4. 影響範囲

- `選手情報` 記事の reaction block
- `首脳陣` 記事の reaction block
- player / manager の topic match 精度

## 5. 実行予定テスト

1. regression tests
   - 同一選手 / 同一テーマの X reaction が `2〜3件` 出る
   - 姓一致だけの別選手 X を混ぜない
   - manager 記事に player テーマの X を混ぜない
2. related unit tests
   - `tests/test_build_news_block.py`
   - `tests/test_related_posts.py`
   - 必要なら reaction selector test
3. full suite
   - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 件数を増やすために strict match を崩す必要がある場合
- 選手違い / 話題違いの混入が増える兆候が出る場合
- 追加テストの赤確認ができない場合
- 全件テスト green を満たせない場合

## 7. 禁止事項

- source に無い事実を reaction で補強しない
- 主語違いの X を数合わせで混ぜない
- 「掲示板っぽさ」の名目で player / manager guard を弱めない

## 8. 想定されるデグレ

- `田中将大` 記事に `田中瑛斗` 反応が混ざる
- 選手記事に監督談話の反応が混ざる
- reaction block が本文より強くなり、元ソースの核が弱く見える

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-10 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |

## 10. Regression Memo欄

### current observation

- player / manager 系は strict guard を入れてようやく別選手混入が減っている
- 反応欄を増やすと再び subject drift が起きやすい
- ただし速報事故よりも、今は受け入れしやすさが優先

### guard hypothesis

- common guard A: 件数は増やすが full-name / topic strict match は維持する
- common guard B: 一致が弱い時は 0 件でよい
- common guard C: reaction は本文の核ではなく補助として扱う

## 11. 作業後追記欄

### 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_yahoo_realtime.py`
- `tests/test_build_news_block.py`
- `doc/waiting/310-QA-player-manager-x-reaction-expansion.md`

### diff概要

- player 記事の X reaction query を team/context 付きに拡張し、strict match のまま `2〜3件` 取りやすくした
- manager 記事の X reaction query に source 内 manager context term を追加し、件数を増やしつつ player topic 混入を避けた
- `選手情報 / 首脳陣` だけ reaction 上限を `3件` に固定し、件数増加が本文を圧迫しないようにした
- X reaction は従来通り non-blocking とし、`0件` や取得失敗でも記事生成を止めないままにした

### 実行したテスト

1. 追加再現テスト赤確認
   - `python3 -m unittest tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_build_fan_reaction_queries_adds_team_context_queries_for_player_quote tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_fetch_fan_reactions_player_quote_uses_team_context_query_to_fill_three tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_build_fan_reaction_queries_adds_manager_context_queries tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_fetch_fan_reactions_manager_uses_context_query_to_fill_three`
   - `python3 -m unittest tests.test_build_news_block.BuildNewsBlockTests.test_manager_article_caps_fan_reaction_embeds_at_three`
2. 追加再現テスト緑確認
   - `python3 -m unittest tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_build_fan_reaction_queries_adds_team_context_queries_for_player_quote tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_fetch_fan_reactions_player_quote_uses_team_context_query_to_fill_three tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_build_fan_reaction_queries_adds_manager_context_queries tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_fetch_fan_reactions_manager_uses_context_query_to_fill_three tests.test_build_news_block.BuildNewsBlockTests.test_manager_article_caps_fan_reaction_embeds_at_three`
3. 関連テスト
   - `python3 -m unittest tests.test_yahoo_realtime tests.test_build_news_block tests.test_related_posts`
   - `python3 -m unittest tests.test_manager_body_template tests.test_rss_fetcher tests.test_rss_fetcher_lead_paraphrase_guard`
4. 全件
   - `python3 -m unittest discover -s tests`

### テスト結果

- 追加再現テストは修正前 `FFFF + F` を確認
- 修正後の追加再現テストは `5 tests ... OK`
- 関連テストは `109 tests ... OK` と `12 tests ... OK`
- 全件は sandbox の localhost bind 制約を避けて権限付き再実行し、`Ran 3336 tests in 68.334s ... OK`

### 残った懸念

- 今回の query 拡張で件数は増えたが、常に `3件` を保証する実装ではない。一致が弱い時は `0〜2件` のまま止まる
- `選手情報 / 首脳陣` 以外の template へは未展開で、postgame 以外の短報系 reaction 増量は別 ticket のまま

### 新しく見つかったデグレ

- なし

### 追加した回帰テスト

- player quote 記事で `巨人 + context term` query を追加して `3件` まで埋められること
- manager 記事で manager context term query を追加して `3件` まで埋められること
- manager 記事の compact X embed は `3件` を上限にすること

### 次回触ってはいけない範囲

- `publish / mail / scheduler / env / Cloud Run` 設定
- strict match を崩す broad query 化
- player / manager 以外の template へのついで展開
