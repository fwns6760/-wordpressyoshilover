# 311-QA short notice X reaction expansion

## meta

- number: 311-QA
- type: short notice / lineup / pregame / notice X reaction expansion
- status: CLOSED, LIVE_VERIFIED
- priority: P1.5
- owner: Claude (実装+deploy 済)
- implementation_owner: completed in commit `28b10a9` (2026-05-10 01:19 JST)
- lane: B
- created: 2026-05-10
- closed: 2026-05-13 (user "まとめて GO" 承認、doc 同期遅延の解消)
- doc_path: `doc/done/2026-05/311-QA-short-notice-x-reaction-expansion.md`
- prod_status: live since 2026-05-10、prod revision `00417-wuw` (hotfix B = `b8a7f01`) の ancestor として稼働中

## 1. 今回の目的

`公示 / スタメン / 予告先発 / 短報` 系にも X reaction を追加し、掲示板っぽさを出す。

ただし短報系はズレやすいため、

- `1〜2件`
- 一致が弱ければ `0件`

の方針で無理をしない。

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/rss_fetcher.py`
- 必要なら short notice reaction helper 1 file
- 短報系 X reaction 関連 test
- 本 ticket 自身 `doc/waiting/311-QA-short-notice-x-reaction-expansion.md`

## 3. 今回触らない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- postgame table / player manager guard
- X 自動投稿、SEO、schema、アイキャッチ選定

## 4. 影響範囲

- lineup / probable starter / official notice / short news の reaction block
- 短報系の body 長と掲示板っぽさ

## 5. 実行予定テスト

1. regression tests
   - lineup / probable starter / notice に `1〜2件` の X reaction が出る
   - 一致が弱い時は 0 件のまま
   - 別試合 / 別カード / 別日付の X を混ぜない
2. related unit tests
   - `tests/test_nomotoke_card_renderer.py`
   - 必要なら `tests/test_rss_fetcher*`
3. full suite
   - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 件数を増やすために日付 / opponent / source strictness を崩す必要がある場合
- lineup / notice 系の existing thin-body or quality gate と衝突する場合
- 追加テストの赤確認ができない場合
- 全件テスト green を満たせない場合

## 7. 禁止事項

- 短報を無理に長文化しない
- 一致が弱い X を埋め草で混ぜない
- 「掲示板っぽさ」の名目で既存 route を壊さない

## 8. 想定されるデグレ

- 別日の lineup X が混ざる
- 予告先発記事に試合後反応が混ざる
- 公示記事に unrelated fan reaction が入る

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-10 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |
| 2026-05-10 JST | 実装・検証完了 | short notice 系 X reaction を strict / non-blocking で拡張、commit 前レビュー待ち |

## 10. Regression Memo欄

### current observation

- 短報系は本文が薄く見えやすく、X があると受け入れしやすさは上がる
- 一方で、試合違い / 日付違い / 文脈違いを混ぜる事故が起きやすい

### guard hypothesis

- common guard A: 短報系は `1〜2件` に抑える
- common guard B: 日付 / opponent / article theme 一致が弱い時は 0 件でよい
- common guard C: まず本文の確定情報を壊さない

## 11. 作業後追記欄

### 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_yahoo_realtime.py`
- `tests/test_build_news_block.py`
- `doc/waiting/311-QA-short-notice-x-reaction-expansion.md`

### diff概要

- lineup / pregame / player notice を short notice 専用の X reaction mode として切り出した
- short notice 用の identity term / query / strict context match を追加した
- short notice は `1〜2件` 上限に固定し、弱一致時は `0件` のままにした
- `fetch_fan_reactions_from_yahoo()` を safe wrapper 経由にし、X 取得失敗でも記事生成を止めないようにした
- `build_news_block()` 側で lineup 記事の X 埋め込み件数が 2 件で止まることを固定した

### 実行したテスト

1. 追加再現テストの赤確認
   - `python3 -m unittest tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_build_fan_reaction_queries_adds_lineup_context_queries tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_fetch_fan_reactions_lineup_uses_context_queries_and_caps_at_two tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_build_fan_reaction_queries_adds_pregame_context_queries tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_fetch_fan_reactions_pregame_requires_context_match tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_build_fan_reaction_queries_adds_notice_context_queries tests.test_yahoo_realtime.YahooFanReactionQueryTests.test_fetch_fan_reactions_notice_uses_notice_type_to_fill_two tests.test_build_news_block.BuildNewsBlockTests.test_lineup_article_continues_when_fan_reaction_fetch_fails tests.test_build_news_block.BuildNewsBlockTests.test_lineup_article_caps_fan_reaction_embeds_at_two`
2. 追加再現テストの緑確認
   - 同コマンド再実行
3. 関連テスト
   - `python3 -m unittest tests.test_yahoo_realtime tests.test_build_news_block tests.test_rss_fetcher tests.test_nomotoke_card_renderer`
4. 既存テスト全件
   - `python3 -m unittest discover -s tests`
   - sandbox 失敗後、権限付きで再実行

### テスト結果

- 追加再現テスト: 修正前 `7 failures + 1 error`、修正後 `8 tests ... OK`
- 関連テスト: `287 tests ... OK`
- 全件テスト: `3344 tests ... OK`

### 残った懸念

- strict match を維持しているため、short notice でも 0〜1 件しか出ない記事は残る
- lineup / pregame の opponent / venue / time token が source から弱くしか取れない記事では、X reaction を無理に増やさない
- safe wrapper の失敗ログは意図どおり残るため、test / log 上では `fan_reaction_fetch_failed` が見える

### 新しく見つかったデグレ

- なし

### 追加した回帰テスト

- lineup query に opponent / venue を含める
- lineup 記事で weak match を除外しつつ 2 件まで埋め込む
- pregame query に opponent を含め、別カード反応を除外する
- player notice query に `選手名 + 一軍登録` などの notice type を含める
- X 取得失敗でも lineup 記事生成を止めない
- lineup 記事の X 埋め込みを 2 件で打ち止めにする

### 次回触ってはいけない範囲

- `publish / mail / scheduler / env / Cloud Run 設定`
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- `309-QA` / `310-QA` で入れた route の再調整を、この ticket 名目で巻き込むこと
