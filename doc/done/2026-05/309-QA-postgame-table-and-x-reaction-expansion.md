# 309-QA postgame table and X reaction expansion

## meta

- number: 309-QA
- type: postgame body / table + X reaction expansion / regression-safe rendering
- status: CLOSED, LIVE_VERIFIED
- priority: P1
- owner: Claude (実装+deploy 済)
- implementation_owner: completed in commit `2b48482` (2026-05-10 00:29 JST)
- lane: B
- created: 2026-05-10
- closed: 2026-05-13 (user "まとめて GO" 承認、doc 同期遅延の解消)
- doc_path: `doc/done/2026-05/309-QA-postgame-table-and-x-reaction-expansion.md`
- prod_status: live since 2026-05-10、prod revision `00417-wuw` (hotfix B = `b8a7f01`) の ancestor として稼働中

## 1. 今回の目的

`postgame` 記事を「速報 prose を長くする」のではなく、`表形式 + X反応` で厚くする。

今回の主眼は次の 2 点。

- 試合結果の確定情報を表形式で読みやすくする
- `💬 ファンの声` / `📣 公式・報道X` を増やして掲示板っぽさを出す

対象の事実表は次を想定する。

- 勝利投手
- 敗戦投手
- セーブ
- 巨人スタメン
- 相手スタメン

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/nomotoke_card_renderer.py`
- 必要なら `src/rss_fetcher.py`
- X reaction / postgame renderer 関連 test
- 本 ticket 自身 `doc/waiting/309-QA-postgame-table-and-x-reaction-expansion.md`

実装観点は次の 3 本に限定する。

- postgame の表形式 block を増やす
- postgame の X reaction block を `1〜5件` に増やす
- 一致が弱い時は無理に X を入れない

## 3. 今回触らない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- X 自動投稿、SEO、schema、アイキャッチ選定
- WordPress 本番記事の手修正、WP admin 操作
- `doc/README.md` / `doc/active/assignments.md` の同期

## 4. 影響範囲

- postgame 記事本文の構造
- nomotoke postgame renderer
- postgame の X reaction 選定数と表示順
- thin-body 改善後の postgame 見え方

直接影響は postgame の body presentation だが、判定を誤ると

- 他試合の X を混ぜる
- 反応欄が多すぎて本文が散らかる
- 表が大きすぎて本文の核が見えにくくなる

可能性がある。

## 5. 実行予定テスト

GO 後の予定テストは次の通り。

1. regression tests
   - postgame に `勝利投手 / 敗戦投手 / セーブ` 表が出る
   - postgame に `巨人スタメン / 相手スタメン` 表が出る
   - X reaction が `1〜5件` で増える
   - 一致が弱い時は X reaction を無理に出さない
2. related unit tests
   - `tests/test_nomotoke_card_renderer.py`
   - 必要なら `tests/test_rss_fetcher*`
3. full suite
   - `python3 -m unittest discover -s tests`
4. output spot-check
   - win / loss / draw の representative fixture で本文構造確認

## 6. STOP条件

- 改善のために publish / mail / scheduler / env / Cloud Run 変更が必要になった場合
- X reaction 増量のために topic / player / game match の strict 条件を壊す必要がある場合
- postgame 以外の広い template 改修へ広がる場合
- 追加テストの赤確認ができない場合
- 全件テスト green を満たせない場合

## 7. 禁止事項

- user の GO 前に code edit しない
- commit / push / deploy / env 変更 / scheduler 変更をしない
- `git add -A` を使わない
- source に無い score / 投手名 / スタメンを補わない
- 一致が弱い X を数合わせで混ぜない
- 「掲示板っぽさ」の名目で publish 条件や mail 条件をついで修正しない

## 8. 想定されるデグレ

- 巨人戦と違う試合の X が混ざる
- 同じ巨人でも別テーマの X が混ざる
- postgame が長くなりすぎて、表より X が主役になる
- thin-body fix と干渉して別の stop が増える

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-10 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |
| 2026-05-10 JST | 実装・テスト完了 | postgame support block と X embed safe path を `manual_intake` 系へ限定追加、full suite green 確認 |

## 10. Regression Memo欄

### current observation

- `65801` 系の thin-body は `事実カード + CTA + 一言` だけで終わる時に起きやすい
- `nomotoke_card_renderer` の postgame は `試合スコア / 打席結果 / 投球結果 / 相手スタメン` が主
- `勝利投手 / 敗戦投手 / セーブ / 両軍スタメン表` はまだ弱い
- X reaction は quality 上の事故を避けるため、現在は強く絞られている

### guard hypothesis

- common guard A: postgame の厚みは prose ではなく table で増やす
- common guard B: X reaction は `試合 / 相手 / 時間帯 / テーマ` が一致するものだけに絞る
- common guard C: 一致が弱い時は 0 件でよい

## 11. 作業後追記

### 1. 実際に変更したファイル

- `src/tools/manual_intake.py`
- `tests/test_manual_intake.py`
- `doc/waiting/309-QA-postgame-table-and-x-reaction-expansion.md`

### 2. diff概要

- `postgame` 向けに `勝利投手 / 敗戦投手 / セーブ` の result pitchers table を追加
- `巨人スタメン / 相手スタメン` を `打順 / 位置 / 選手名` の table block で出すよう追加
- X embed block を `nomotoke_card_postgame_v1` では最大 `5件` まで拡張
- X embed 生成が失敗しても記事生成を止めず、空 block で継続する safe wrapper を追加
- 一致が弱い postgame では無理に generic X を差し込まないように調整

### 3. 実行したテスト

- red確認
  - `python3 -m unittest tests.test_manual_intake.PostgameExpansionTests`
- 関連テスト
  - `python3 -m unittest tests.test_manual_intake`
  - `python3 -m unittest tests.test_nomotoke_card_renderer tests.test_source_yahoo_boxscore_extractor`
- 全件
  - `python3 -m unittest discover -s tests`

### 4. テスト結果

- `tests.test_manual_intake.PostgameExpansionTests`
  - 修正前 red 確認後、修正後 `Ran 5 tests ... OK`
- `tests.test_manual_intake`
  - `Ran 64 tests ... OK`
- `tests.test_nomotoke_card_renderer tests.test_source_yahoo_boxscore_extractor`
  - `Ran 194 tests ... OK`
- `python3 -m unittest discover -s tests`
  - sandbox では `test_manual_intake_service` の localhost bind 制約で失敗
  - 権限付き再実行で `Ran 3331 tests ... OK`

### 5. 残った懸念

- 今回の反映経路は `manual_intake` / enrichment path が中心で、全 postgame renderer 共通化まではしていない
- lineup table は source の Yahoo HTML または preview HTML に依存するため、両方で row が取れない時は出ない
- X 増量は keyword ベースの strict match で増やしており、将来さらに増やす場合は試合 identity の強化が必要

### 6. 新しく見つかったデグレ

- なし

### 7. 追加した回帰テスト

- postgame に `勝利投手 / 敗戦投手 / セーブ` table が出る
- postgame に lineup table が出る
- `nomotoke_card_postgame_v1` では X embed が最大 `5件` まで増える
- X embed 生成が失敗しても `apply_rss_pipeline_enrichment()` が元本文を返して止まらない

### 8. 次回触ってはいけない範囲

- `publish / mail / scheduler / env / Cloud Run 設定`
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- `310-QA` / `311-QA` の template 拡張範囲
