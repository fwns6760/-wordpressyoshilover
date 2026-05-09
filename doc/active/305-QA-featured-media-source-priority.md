# 305-QA featured media source priority

## meta

- number: 305-QA
- type: featured media / eyecatch priority fix
- status: REVIEW_NEEDED
- priority: P0.5
- owner: Codex B
- implementation_owner: Codex B
- lane: B
- created: 2026-05-09
- related: 304-QA, 277-QA
- doc_path: `doc/active/305-QA-featured-media-source-priority.md`
- note: source eyecatch を最優先し、unrelated existing media reuse を止める narrow fix

## 1. 今回の目的

アイキャッチが「記事や X に関連するもの」にならないケースを narrow に修正する。

featured media の優先順を次のように固定する。

- 第1優先: 元記事または元 X post から取れた source eyecatch を使う
- 第1優先の補足: その source eyecatch が既に WP media に存在するなら、再 upload せず既存 media を再利用する
- 第2優先: source eyecatch が取れないときだけ阿部監督 fallback を使う
- 禁止: source と無関係な既存 media や diversified player pool に流してごまかさない

## 2. 今回触る範囲

- `src/rss_fetcher.py`
- `src/wp_client.py`
- `src/player_eyecatch_resolver.py`
- `tests/test_featured_media_fallback.py`
- `tests/test_featured_media_helpers.py`
- `tests/test_player_eyecatch_resolver.py`
- 必要なら featured media regression test 1 file
- 本 ticket 自身 `doc/active/305-QA-featured-media-source-priority.md`

## 3. 今回触らない範囲

- 本文生成ロジック
- `src/tools/manual_intake.py` / `src/nomotoke_rss_router.py`
- publish / mail / scheduler / env / Cloud Run 設定
- SEO / publish 条件 / X 運用
- frontend / plugin / CSS
- live WP 記事の手修正

## 4. 影響範囲

- `featured_media` 候補選定
- source image dedup / reuse 判定
- player / manager / lineup / pregame の eyecatch fallback
- 既存 media の再利用条件

## 5. 実行予定テスト

1. red 先行の再現テスト
   - source image が既に WP media にある時、その media id を再利用する
   - source image がある時、diversified pool や unrelated fallback に流れない
   - source image がない時だけ阿部監督 fallback に落ちる
2. 修正後の targeted tests
   - `python3 -m unittest tests.test_featured_media_fallback`
   - `python3 -m unittest tests.test_featured_media_helpers`
   - `python3 -m unittest tests.test_player_eyecatch_resolver`
3. safety check
   - 可能なら `python3 -m unittest discover -s tests`

## 6. STOP条件

- fix が publish / mail / scheduler / env / Cloud Run 変更を要求する場合
- source image と existing media の対応を安全に特定できない場合
- 本文生成や publish 条件変更まで scope が広がる場合
- full suite で今回修正起因の failure が残る場合

## 7. 禁止事項

- `git add -A` を使わない
- unrelated file を巻き込まない
- publish / mail / scheduler / env / Cloud Run 設定を変えない
- 本文 quality fix をこの ticket に混ぜない

## 8. 想定されるデグレ

- source image reuse 判定が弱く、同一 source image の既存 media を拾えず `featured_media_missing` が増える
- fallback 条件を狭めすぎて、従来 publish できていた記事が draft 維持になる
- 阿部監督 fallback が広すぎて、選手記事でも違和感が残る

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-09 JST | ticket 作成 | source eyecatch priority fix の write scope を固定 |
| 2026-05-09 JST | impl + test 完了 | source eyecatch reuse / generic skip / 阿部 fallback 固定、full suite 3315 tests green |

## 10. Regression Memo欄

- source eyecatch が generic SNS image や duplicate 扱いで skip され、固定 fallback に落ちる
- player / manager 記事で source image が取れない時、related ではない既存 media や generic fallback が見える
- user 方針: source eyecatch 最優先、無ければ阿部監督 fallback、unrelated existing media は使わない

## 11. 作業後追記

### 実際に変更したファイル

- `src/rss_fetcher.py`
- `src/wp_client.py`
- `src/player_eyecatch_resolver.py`
- `tests/test_featured_media_fallback.py`
- `tests/test_featured_media_helpers.py`
- `tests/test_notice_body_template.py`
- `tests/test_player_eyecatch_resolver.py`
- `doc/README.md`
- `doc/active/assignments.md`
- `doc/active/305-QA-featured-media-source-priority.md`

### diff概要

- source eyecatch URL が generic SNS / OGP 画像なら featured candidate から除外
- source eyecatch URL が既に WP media にある時は media id を再利用し、再 upload しない
- auto eyecatch fallback では既存 player media cache / diversified pool を使わず、source 不在時だけ team fallback を使う
- notice / story helper の generic URL fallback を止め、team fallback 優先に寄せる
- 上記の regression test を追加し、期待値を source-first / team-fallback-second に更新

### 実行したテスト

1. red 確認
   - `python3 -m unittest tests.test_featured_media_fallback`
   - `python3 -m unittest tests.test_featured_media_helpers`
   - `python3 -m unittest tests.test_notice_body_template tests.test_player_eyecatch_resolver`
2. targeted green
   - `python3 -m unittest tests.test_featured_media_fallback tests.test_featured_media_helpers tests.test_notice_body_template tests.test_player_eyecatch_resolver tests.test_wp_client`
3. full suite
   - `python3 -m unittest discover -s tests`
   - sandbox では `tests/test_manual_intake_service.py` の port bind 制約で失敗
   - escalated rerun で full suite を再確認

### テスト結果

- red 確認: 期待どおり失敗を確認してから修正に入った
- targeted green: `Ran 92 tests ... OK`
- full suite green: `Ran 3315 tests in 61.026s ... OK`

### 残った懸念

- 阿部監督 fallback `media_id=36062` 自体の見た目が全カテゴリで最適とは限らない
- source image を持たない記事では fallback 利用率が上がるため、live で違和感がないかは deploy 後観測が必要

### 新しく見つかったデグレ

- なし

### 追加した回帰テスト

- source image の既存 WP media reuse
- generic primary を skip して article-specific source を reuse
- generic 候補しかない時は upload せず `0` を返す
- auto fallback で player cache hit があっても team fallback を優先する
- notice / story helper が generic URL fallback を使わないこと

### 次回触ってはいけない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- 本文生成ロジック
- X 運用 / SEO / frontend
