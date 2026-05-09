# 306-FRONT body emoji safe decoration

## meta

- number: 306-FRONT
- type: frontend / body presentation / regression-safe decoration
- status: BLOCKED_USER
- priority: P1
- owner: user GO 待ち
- implementation_owner: Codex after GO
- lane: B
- created: 2026-05-09
- doc_path: `doc/waiting/306-FRONT-body-emoji-safe-decoration.md`
- note: user 制約により初手はこの Markdown 新規作成のみ。`doc/README.md` / `doc/active/assignments.md` 同期、code edit、commit、push、deploy、env / scheduler 変更は GO 後まで保留

## 1. 今回の目的

のもとけ系の見た目との差別化として、本文に deterministic な絵文字装飾を追加したい。

ただし目的は「絵文字を増やすこと」そのものではなく、

- 記事が出なくならない
- publish / mail / scheduler に影響しない
- 事実抽出 / routing / 本文品質を壊さない

という条件の中で、見た目だけを安全に強化すること。

今回の方針は、絵文字を本文生成の core logic に混ぜず、最後の render 済み HTML に対する non-blocking な cosmetic layer として扱う。

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/tools/manual_intake.py`
- `src/rss_fetcher.py`
- 必要なら `src/nomotoke_card_renderer.py` または renderer helper 1 file
- 絵文字装飾の unit / regression test
- 本 ticket 自身 `doc/waiting/306-FRONT-body-emoji-safe-decoration.md`

実装観点は次の 3 本に限定する。

- 絵文字装飾を render 後の cosmetic layer として整理する
- 適用経路の差(`manual_intake` だけ / `postgame-auto` は別経路)を埋める
- 絵文字処理が失敗しても元本文をそのまま出す non-blocking 挙動を固定する

## 3. 今回触らない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
- 本文の事実抽出、routing、subject match、stats table 条件の core logic
- title 生成、X 投稿生成、SEO、schema 方針
- WordPress 本番記事の手修正、WP admin 操作
- `doc/README.md` / `doc/active/assignments.md` の同期

## 4. 影響範囲

- 記事本文の見出し / ラベル / keyword decoration
- `manual_intake` 経路の rendered HTML
- `rss_fetcher` の non-X passthrough body
- 必要なら `postgame-auto` / nomotoke card renderer の最終本文整形

直接影響は body presentation だが、装飾適用位置を誤ると本文比較テスト、golden fixture、thin-body 判定、quote integrity などに波及する可能性がある。

## 5. 実行予定テスト

GO 後の予定テストは次の通り。

1. regression tests
   - 絵文字装飾が失敗しても元本文を返す
   - 人名 / 数字 / URL / 引用文の中身を壊さない
   - 同じ keyword に過剰な絵文字重複を入れない
   - `manual_intake` 経路だけでなく今回対象にした renderer 経路でも反映される
2. related unit tests
   - `tests/test_manual_intake*`
   - `tests/test_rss_fetcher*`
   - 必要なら renderer / golden fixture test
3. full suite
   - `python3 -m unittest discover -s tests`
4. output spot-check
   - 直近の representative article type で本文に過剰装飾や崩れがないこと

## 6. STOP条件

- 絵文字追加のために publish / mail / scheduler / env / Cloud Run 変更が必要になった場合
- 絵文字処理が本文生成の core logic へ入り込み、抽出 / routing と分離できない場合
- `postgame-auto` や renderer 系に適用するために大規模 template 改修へ広がる場合
- 既存本文 fixture の崩れが広く、narrow fix では収まらない場合
- 装飾の追加で thin-body / quote / source-grounding 系テストが壊れ、境界を保てない場合
- 「のもとけとの差別化」と「事実ベース維持」が両立できない場合

## 7. 禁止事項

- user の GO 前に code edit しない
- commit / push / deploy / env 変更 / scheduler 変更をしない
- `git add -A` を使わない
- 絵文字のために publish 条件や mail 条件を変えない
- LLM 自由作文で絵文字入りの prose を増やさない
- 人名、数字、引用、出典 URL の中身を書き換えない
- 「見た目改善」の名目で core extraction / routing へついで修正をしない

## 8. 想定されるデグレ

- 絵文字が多すぎて本文が SNS っぽくなり、読みにくくなる
- 引用文や source title に絵文字が混ざり、事実ブロックが不自然になる
- 既存の golden fixture / snapshot が大量に崩れる
- renderer 経路ごとの差で、ある記事だけ絵文字が増えず一貫性が崩れる
- 装飾位置を誤って HTML 構造や CTA、X 埋め込み、schema block を壊す
- 装飾追加のせいで thin-body / duplicate sentence / body contract 判定に影響する

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-09 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |
| 2026-05-09 JST | implementation 完了 | renderer 見出し絵文字 + manual_intake safe fallback を narrow 追加、publish / mail / scheduler / env 変更なし |

## 10. Regression Memo欄

### current observation

- `50bd58a` で `manual_intake` に emoji decorate が入っている
- ただし `e5208be` で emoji 軽減が入り、現在は約 18 keyword へ縮小されている
- `rss_fetcher` では non-X passthrough 時だけ `manual_intake._build_body_for_news()` を使う
- `postgame-auto` は `nomotoke_card_postgame_v1` renderer 直行で、現在の emoji decorate の主対象外
- live sample では fixed heading emoji は見えるが、本文 prose 全体が増えた感触は弱い

### guard hypothesis

- common guard A: 絵文字は render 後 HTML の cosmetic layer に限定する
- common guard B: 絵文字処理が失敗しても本文を止めず、元 HTML を返す
- common guard C: 対象は高信頼 keyword / heading / label に絞り、人名・数字・引用には近づけない

## 11. 作業後追記欄

GO 後の実装完了時に、同じファイルへ次を追記する。

### 実際に変更したファイル

- `src/nomotoke_card_renderer.py`
- `src/tools/manual_intake.py`
- `tests/test_nomotoke_card_renderer.py`
- `tests/test_manual_intake.py`

### diff概要

- `nomotoke_card_renderer`: stable `h3` 見出しだけに絵文字を付ける cosmetic decorator を追加し、`_result_payload()` 末尾で best-effort 適用
- `manual_intake`: `_decorate_body_with_emoji_safe()` を追加し、manual-intake path / rss pipeline enrichment path の絵文字処理失敗時に元本文へフォールバック
- tests: renderer 見出し絵文字 2 件と、emoji decoration failure でも本文生成が止まらない回帰 1 件を追加

### 実行したテスト

1. red 確認
   - `python3 -m unittest tests.test_manual_intake.EmojiDecorationSafetyTests tests.test_nomotoke_card_renderer.HappyPathTests.test_postgame_card_adds_structural_emoji_headings tests.test_nomotoke_card_renderer.HappyPathTests.test_official_notice_card_adds_structural_emoji_headings`
2. 追加テスト緑確認
   - 同上
3. 関連テスト
   - `python3 -m unittest tests.test_manual_intake tests.test_nomotoke_card_renderer`
4. 全件
   - `python3 -m unittest discover -s tests`
   - sandbox では `test_manual_intake_service` の loopback bind 制約で失敗
   - 権限付き再実行で再確認
   - `python3 -m unittest discover -s tests`

### テスト結果

- 追加回帰テスト: green
- 関連テスト: `Ran 232 tests ... OK`
- 全件: `Ran 3318 tests in 76.266s ... OK`

### 残った懸念

- 今回は heading 中心の装飾で止めており、本文 prose の絵文字増量はまだ限定的
- `postgame-auto` を含む renderer 系では見出し絵文字は増えるが、quote / prose には意図的に触れていない
- manual-intake safe fallback は exception log を出すため、壊れた場合は記事は止まらないが log 上では検知される

### 新しく見つかったデグレ

- なし

### 追加した回帰テスト

- `tests/test_manual_intake.py`
  - `test_apply_rss_pipeline_enrichment_returns_body_when_emoji_step_fails`
- `tests/test_nomotoke_card_renderer.py`
  - `test_postgame_card_adds_structural_emoji_headings`
  - `test_official_notice_card_adds_structural_emoji_headings`

### 次回触ってはいけない範囲

- `publish / mail / scheduler / env / Cloud Run 設定`
- 本文の事実抽出、routing、subject match、stats table 条件の core logic
- `src/guarded_publish_runner.py`
- `src/guarded_publish_evaluator.py`
- `src/publish_notice_email_sender.py`
- `src/publish_notice_scanner.py`
