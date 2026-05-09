# 304-QA player / manager common quality guard

## meta

- number: 304-QA
- type: quality guard / regression ticket
- status: BLOCKED_USER
- priority: P0.5
- owner: user GO 待ち
- implementation_owner: Codex B after GO
- lane: B
- created: 2026-05-09
- related: 256-QA, 277-QA, 295-QA
- doc_path: `doc/waiting/304-QA-player-manager-common-quality-guard.md`
- note: user 制約により初手はこの Markdown 新規作成のみ。`doc/README.md` / `doc/active/assignments.md` の同期、コード編集、commit、push、deploy は GO 後まで保留

## 1. 今回の目的

player / manager 系の記事で出ている deterministic な壊れ方に対して、個別の narrow fix ではなく共通 guard を 1 便で入れるための作業記録を先に固定する。

今回の品質 hold 対象は次の 4 点。

- post `65706`: `笑みはない。だが、確かな闘志は宿っていた。` のような主観文が既存 lead として残る
- post `65706`: 主語に関係ない `ティマ` が related-player として混ざる
- post `65704`: `田中将大` 記事なのに `田中瑛斗` 行が混ざる
- post `65704`: 投手記事なのに `打率.000 / 0本 / 0打点` の野手向け当日成績表が出る

この ticket の狙いは「この 3 件だけを場当たりで直す」ではなく、player / manager 系で同種の崩れをかなり出しにくくする共通品質ガードを入れること。

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/rss_fetcher.py`
- `tests/test_build_news_block.py`
- `tests/test_related_posts.py`
- `tests/test_rss_fetcher_lead_paraphrase_guard.py`
- 必要なら追加の narrow regression test 1 file
- 本 ticket 自身 `doc/waiting/304-QA-player-manager-common-quality-guard.md`

GO 後の実装観点は次の 3 本。

- player / manager lead から主観文を落とす共通 guard
- related player / related posts / subject match を単一主語 strict にする guard
- 当日成績表を野手記事だけ、または source に明示数字がある時だけ出す guard

## 3. 今回触らない範囲

- `src/rss_fetcher.py` 以外の production code への横展開
- `src/tools/manual_intake.py` / `src/nomotoke_rss_router.py` / frontend / plugin / CSS
- Cloud Run / Scheduler / Secret Manager / env / deploy script / Docker / build config
- WordPress 本番記事の手修正、WP admin 操作、X 投稿、メール運用
- `doc/README.md` / `doc/active/assignments.md` / 他 ticket の status 移動
- code path と無関係な `logs/`, `build/`, `data/`, `docs/ops/` の整理

## 4. 影響範囲

- `選手情報` の body 生成
- `首脳陣` の body 生成
- player subject 抽出に依存する related posts 選定
- player daily stat table の表示条件
- title / summary から subject を拾う fallback の挙動
- 既存の quality guard と body template の組み合わせ

直接の影響対象は player / manager 系だが、`src/rss_fetcher.py` 共通 helper を触る場合は `試合速報` や `ドラフト・育成` に波及する可能性があるため、対象 subtype を絞って確認する。

## 5. 実行予定テスト

GO 後の予定テストは次の通り。

1. targeted unit tests
   - `python3 -m unittest tests.test_build_news_block`
   - `python3 -m unittest tests.test_related_posts`
   - `python3 -m unittest tests.test_rss_fetcher_lead_paraphrase_guard`
2. narrow regression tests
   - `65706`: player / manager body に `笑みはない` `闘志` `見どころ` `追っていきたい` 系の主観文が残らないこと
   - `65706`: `ティマ` のような非主語 player が related 側に混ざらないこと
   - `65704`: `田中将大` 記事で `田中瑛斗` を surname 一致だけで拾わないこと
   - `65704`: 投手記事で `打率 / 本塁打 / 打点` の table を出さないこと
3. safety check
   - 既存の hitter player 記事では daily stat table が消えないこと
   - 既存の manager / player quote 記事で本文が極端に痩せないこと

必要に応じて `python3 -m unittest discover -s tests` まで拡張するが、初手は上の targeted scope で止める。

## 6. STOP条件

- fix に `src/rss_fetcher.py` を超える大規模 routing 改修が必要だと判明した場合
- full-name strict 化のために category / subtype 判定全体を触る必要が出た場合
- player / manager 用 guard が postgame / lineup / farm の既存挙動を広く壊す兆候が出た場合
- concrete fixture で `65704` / `65706` 相当を再現できず、期待値を固定できない場合
- env flag 追加、deploy、Scheduler 変更、live article 修正が必要になった場合
- user の許可範囲を超えて `doc/README.md` / `assignments.md` 同期まで同時に求められた場合

## 7. 禁止事項

- user の GO 前にコード編集しない
- commit / push / deploy / env 変更 / scheduler 変更をしない
- `git add -A` を使わない
- unrelated file を巻き込まない
- Cloud Run / Secret / `.env` / auth / token を表示しない
- live WP 記事や X 投稿を直接触らない
- 「この 3 件だけ直ればよい」という前提で broad guarantee を装わない

## 8. 想定されるデグレ

- subject strict 化が強すぎて、本来拾うべき related post まで消える
- surname 禁止が強すぎて、外国人選手やカタカナ表記で主語抽出に失敗する
- 投手記事の stats 抑制が広すぎて、野手記事の有効な daily stat table まで落ちる
- 主観文 guard が強すぎて、本文が不自然に短くなる
- manager / player quote の closing が機械的になり、既存 test の語尾期待値が崩れる
- related posts の選定が空になり、既存の関連記事 block coverage が下がる

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-09 JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施 |

## 10. Regression Memo欄

### initial known bad cases

- `65706`
  - bad text: `笑みはない。だが、確かな闘志は宿っていた。`
  - suspected cause: player / manager lead に主観文 guard がなく、既存 deterministic lead が残留
- `65706`
  - bad text: `ティマ`
  - suspected cause: related-player / related-post subject match が単一主語 strict になっていない
- `65704`
  - bad text: `田中将大` 記事に `田中瑛斗` 行が混入
  - suspected cause: surname 一致 (`田中`) だけで related subject を拾っている
- `65704`
  - bad text: `打率.000 / 0本 / 0打点`
  - suspected cause: 投手記事でも野手向け当日成績抽出が走る

### guard hypothesis

- common guard A: player / manager lead から主観 phrase を route 共通で落とす
- common guard B: related subject は full-name match 優先、surname-only match は禁止または厳格制限
- common guard C: 当日成績表は野手記事限定、または source に明示数字がある時だけ許可

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

- `src/rss_fetcher.py`
- `tests/test_build_news_block.py`
- `tests/test_related_posts.py`
- `tests/test_rss_fetcher_lead_paraphrase_guard.py`
- `doc/waiting/304-QA-player-manager-common-quality-guard.md`

### diff概要

- player / manager lead の先頭文に対して、title 非重複でも主観 phrase を検知したら lead paraphrase guard を発火させるよう調整
- player 記事の subject 抽出で surname-only を summary から full-name に拡張し、related posts と本文 fact line の主語一致を strict 化
- player 本文の fact line / summary snippet / fallback sentence から、非主語 player の行を落とす guard を追加
- 投手記事では野手向け当日成績表 (`打率 / 本塁打 / 打点`) を出さない guard を追加
- player fallback 文面を主観・感想・考察寄りの closing から、事実不足なら不足のまま止める factual 文面に変更
- 上記 4 点の regression test を追加

### 実行したテスト

赤確認:

- `python3 -m unittest tests.test_build_news_block.BuildNewsBlockTests.test_pitcher_player_story_avoids_other_player_lines_and_hitter_stats_table`
- `python3 -m unittest tests.test_related_posts.RelatedPostsTests.test_related_posts_use_full_name_when_title_only_has_ambiguous_surname`
- `python3 -m unittest tests.test_rss_fetcher_lead_paraphrase_guard.BodyLeadParaphraseGuardTests.test_flag_on_rewrites_player_subjective_lead_even_without_title_overlap`

緑確認:

- `python3 -m unittest tests.test_build_news_block.BuildNewsBlockTests.test_pitcher_player_story_avoids_other_player_lines_and_hitter_stats_table`
- `python3 -m unittest tests.test_related_posts.RelatedPostsTests.test_related_posts_use_full_name_when_title_only_has_ambiguous_surname`
- `python3 -m unittest tests.test_rss_fetcher_lead_paraphrase_guard.BodyLeadParaphraseGuardTests.test_flag_on_rewrites_player_subjective_lead_even_without_title_overlap`
- `python3 -m unittest tests.test_build_news_block`
- `python3 -m unittest tests.test_related_posts`
- `python3 -m unittest tests.test_rss_fetcher_lead_paraphrase_guard`
- `python3 -m unittest discover -s tests`

### テスト結果

- 追加した再現テスト 3 件は、追加直後に赤を確認した
- 修正後、追加した再現テスト 3 件はすべて緑化した
- 関連既存テスト `tests.test_build_news_block` `tests.test_related_posts` `tests.test_rss_fetcher_lead_paraphrase_guard` はすべて green
- `python3 -m unittest discover -s tests` は sandbox 内では `tests/test_manual_intake_service.py` の bind 制約で `PermissionError` が出たため、昇格実行で再確認した
- 昇格実行した `python3 -m unittest discover -s tests` は `Ran 3312 tests ... OK`

### 残った懸念

- surname-only strict 化は `田中` 系の混入には効くが、summary に full-name がない source では関連抽出が痩せる可能性がある
- subject strict 化を player 系 helper に寄せたため、将来 manager / OB 系へ同じ guard を横展開する時は別便で fixture を増やしてから触るべき
- 主観語 guard は deterministic phrase ベースなので、未知の新 phrasing までは今回の便では保証しない

### 新しく見つかったデグレ

- 今回の scope では新規デグレは未検出
- full suite 実行で 304-QA 修正起因の失敗は未検出

### 追加した回帰テスト

- 投手の player story で、非主語 player 行と野手向け当日成績表を同時に出さない回帰テスト
- title が surname-only でも summary の full-name を使って related posts を strict に絞る回帰テスト
- title overlap がなくても、`笑みはない。だが、確かな闘志は宿っていた。` のような主観 lead を落とす回帰テスト

### 次回触ってはいけない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- `src/rss_fetcher.py` 以外の production routing 全体
- `src/tools/manual_intake.py` / `src/nomotoke_rss_router.py`
- frontend / plugin / SEO / publish 条件
- `doc/README.md` / `doc/active/assignments.md` / 他 ticket の status 移動
