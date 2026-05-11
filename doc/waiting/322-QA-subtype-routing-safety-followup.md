# 322-QA-subtype-routing-safety-followup

| field | value |
|---|---|
| ticket_id | 322-QA-subtype-routing-safety-followup |
| priority | P1 |
| status | BLOCKED_USER_COMMIT_GO |
| owner | Codex B after user GO |
| lane | B |
| created | 2026-05-11 |
| doc_path | doc/waiting/322-QA-subtype-routing-safety-followup.md |
| related | 321-QA-subtype-routing-young-farm-notice-recovery / 295-QA-subtype-evaluator-misclassify-fix / CATEGORY-RESTRUCTURE-2026-05-08 / 277-QA-title-player-name-backfill |

## 1. 今回の目的

`321-QA-subtype-routing-young-farm-notice-recovery` で残った分類リスクを、さらに狭く減らす。

対象は以下の3点。

- 人名候補の誤認を減らす
- `article_subtype` だけでなく、必要な場合に category reroute するか判断する
- 三軍記事を direct 分類に含めるか、既存 flag 管理のままにするかを明確化する

本 ticket は `general` gate を緩めない。publish 条件を直接変更しない。

## 2. 背景

321 では `general` に落ちた記事を、根拠がある場合だけ `farm` / `player` / `notice` / `recovery` に寄せた。

321 の残リスク:

- 人名候補判定は0誤認ではない
- category 自体は変更していない
- 三軍は既存 flag 管理を維持し、direct 分類対象外にした

これらを一度に本線へ混ぜると影響範囲が広がるため、321 とは別 ticket にする。

## 3. 今回触ってよい範囲

実装 GO 後に触ってよい範囲:

- `src/rss_fetcher.py`
- player name / roster / title helper が既に存在する場合、その read-only 調査
- subtype / category routing に関係する既存テスト
- 新規 regression test
- 本 ticket Markdown の作業ログ追記

## 4. 今回触ってはいけない範囲

- publish 条件
- mail
- scheduler
- Cloud Run env
- Cloud Run service / job 設定
- Secret Manager
- GitHub Actions
- SEO / noindex / canonical / 301
- X投稿
- source 追加
- frontend plugin / build artifact
- `ENABLE_PUBLISH_FOR_GENERAL`
- `RUN_DRAFT_ONLY`
- `AUTO_TWEET_ENABLED`
- `PUBLISH_REQUIRE_IMAGE`

## 5. 影響範囲

直接影響:

- `general` から `player` / `farm` / `notice` / `recovery` へ寄せる条件
- category reroute を採用する場合、記事カテゴリ保存先
- 三軍記事の subtype 判定方針

間接影響:

- category reroute を入れる場合、一覧表示 / 関連記事 / 通知分類 / X判定に影響する可能性
- 三軍 direct 分類を入れる場合、既存 flag 管理テストを更新する必要がある可能性

影響しない範囲:

- publish gate 自体
- mail 送信処理
- scheduler 起動条件
- Cloud Run env
- source 収集対象

## 6. 実行予定テスト

実装 GO 後、先に再現テストを追加して赤確認する。

想定 fixture:

- 実在選手名辞書 / whitelist にある選手だけ `player` に寄せる
- stopword / 媒体名 / チーム名風テキストは `player` に寄せない
- category reroute する場合、`notice` / `recovery` は `選手情報`、`farm` は `ドラフト・育成` に寄ること
- category reroute しない場合、その理由をテストで固定する
- 三軍 direct 分類を入れる場合、三軍結果記事が `farm` に寄ること
- 三軍 direct 分類を入れない場合、既存 flag 管理が維持されること
- `general` gate は緩めない

実行予定:

- 追加テスト赤確認
- `python3 -m pytest <targeted test>`
- `python3 -m py_compile <touched python files>`
- `python3 -m compileall <touched python files>`
- AST確認
- `python3 -m pytest`
- `git diff --check -- <changed files>`

## 7. STOP 条件

- player whitelist の正本が repo 内に見つからない
- category reroute が publish / mail / X / frontend 表示に広く波及する
- 三軍 direct 分類が既存 flag 管理と衝突する
- `ENABLE_PUBLISH_FOR_GENERAL` を変えないと成立しない
- env / Cloud Run / scheduler 変更が必要になる
- source 追加が必要になる
- 誤公開リスクが分類改善メリットを上回る
- 既存テスト全件が落ちる
- unrelated failure と混線する

## 8. 禁止事項

- `ENABLE_PUBLISH_FOR_GENERAL=1` にしない
- publish gate を直接緩めない
- Cloud Run env を独断で変えない
- scheduler を独断で変えない
- 本番設定を変えない
- 指示外の source を追加しない
- X 投稿をしない
- SEO を触らない
- frontend plugin を触らない
- ついで修正をしない
- テスト未実行で commit / push / deploy しない

## 9. 想定されるデグレ

- whitelist が狭すぎて、本来 `player` に寄せたい記事が `general` のまま残る
- whitelist が広すぎて、媒体名や一般名詞を選手名扱いする
- category reroute により、WP一覧や関連記事の見え方が変わる
- 三軍 direct 分類で、既存 flag 管理を意図せず迂回する
- `notice` / `recovery` を `選手情報` へ寄せた結果、既存のカテゴリ別表示とズレる

## 10. 実装方針メモ

Phase A: read-only 調査

- repo 内に選手名辞書 / roster helper / title player backfill helper があるか確認
- `classify_category()` と `_detect_article_subtype()` の責務境界を確認
- 三軍関連の既存 flag / tests を確認

Phase B: 最小実装候補

- `player` への direct 分類条件を whitelist / known player helper 優先にする
- category reroute は、まず `notice` / `recovery` / `farm` の明確なものだけ検討する
- 三軍 direct 分類は、既存 flag 管理を壊さない形が取れる場合のみ実装する

Phase C: 観察

- `created_subtype_counts`
- `created_category_counts`
- `publish_skip_reason_counts`
- 誤分類記事の有無

## 11. Regression Memo 欄

実装時に必ず確認すること:

- 321 の追加テストは green 維持
- 295 の live_update 誤分類 scope と混ぜない
- 277 の title player name backfill と重複実装しない
- CATEGORY-RESTRUCTURE の広いカテゴリ再設計とは混ぜない
- `general` gate は緩めない
- publish / mail / scheduler / env は変更しない

## 12. 作業ログ欄

- 2026-05-11: 321 の deploy前レビューで残リスクとして出た、人名候補誤認 / category未変更 / 三軍direct対象外について、user request により follow-up ticket 作成。コード編集・commit・push・deploy・env変更・scheduler変更は未実施。
- 2026-05-11: user GO 後、既存 helper を read-only 調査。`src/rss_fetcher.py` に `_load_giants_roster()` / `_matching_giants_roster_names()` が存在し、`config/giants_roster.json` を正本として使えることを確認。
- 2026-05-11: `スポーツ報知` / `GIANTS TV` のような媒体名風テキスト + 記録語が `player` に誤分類される再現テストを追加し、赤確認済み。
- 2026-05-11: `general` から `player` に寄せる条件を、広い `title_has_person_name_candidate()` から既存 roster helper `_matching_giants_roster_names()` 必須へ狭めた。category reroute と三軍 direct 分類は今回未実装。

## 13. 作業後追記欄

- 実際に変更したファイル:
  - `src/rss_fetcher.py`
  - `tests/test_general_subtype_routing.py`
  - `doc/waiting/322-QA-subtype-routing-safety-followup.md`
- diff 概要:
  - `general` から `player` に寄せる条件を、既存 roster helper `_matching_giants_roster_names(text)` の hit 必須に変更。
  - `スポーツ報知` / `GIANTS TV` のような媒体名風テキストが、記録語だけで `player` へ寄らない回帰テストを追加。
  - `farm` / `notice` / `recovery` の 321 分類は変更なし。
  - category reroute は未実装。
  - 三軍 direct 分類は未実装。
- 実行したテスト:
  - `python3 -m pytest tests/test_general_subtype_routing.py` 赤確認: 2 failed / 4 passed
  - `python3 -m pytest tests/test_general_subtype_routing.py` 修正後 green
  - `python3 -m pytest tests/test_general_subtype_routing.py tests/test_giants_roster_filter.py tests/test_title_player_name_backfill.py tests/test_player_eyecatch_resolver.py tests/test_rss_fetcher_type_routing_flags.py tests/test_classifier_fallback.py tests/test_publish_gating.py`
  - `python3 -m py_compile src/rss_fetcher.py tests/test_general_subtype_routing.py`
  - `python3 -m compileall src/rss_fetcher.py tests/test_general_subtype_routing.py`
  - `python3 -c "import ast, pathlib; [ast.parse(pathlib.Path(path).read_text()) for path in ('src/rss_fetcher.py','tests/test_general_subtype_routing.py')]; print('ast ok')"`
  - `python3 -m pytest` sandbox 内: 3582 passed / 3 failed
  - `python3 -m pytest` sandbox 外: 3585 passed
- テスト結果:
  - 追加テストは赤確認後、修正により green。
  - 関連テスト 85 passed。
  - 全件 pytest は sandbox 内で `tests/test_manual_intake_service.py::LiveServerSmokeTest` 3件が `PermissionError: [Errno 1] Operation not permitted` により失敗。
  - 同じ全件 pytest を sandbox 外で再実行し、3585 passed。
- 残った懸念:
  - roster に未登録の新加入・育成・OB寄り選手は、`player` direct 分類から外れる可能性がある。
  - category reroute は未実装のため、WPカテゴリ保存先は変わらない。
  - 三軍 direct 分類は未実装のため、既存 flag 管理が継続する。
- 新しく見つかったデグレ:
  - 実装修正後の関連テスト・全件テストでは新規デグレは確認されていない。
- 追加した回帰テスト:
  - `tests/test_general_subtype_routing.py::test_media_name_with_record_words_stays_general`
  - `tests/test_general_subtype_routing.py::test_channel_name_with_record_words_stays_general`
- 次回触ってはいけない範囲:
  - publish 条件そのもの
  - mail
  - scheduler
  - env / Cloud Run 設定
  - Secret Manager
  - GitHub Actions
  - SEO / noindex / canonical / 301
  - X投稿
  - source 追加
  - frontend plugin / build artifact
