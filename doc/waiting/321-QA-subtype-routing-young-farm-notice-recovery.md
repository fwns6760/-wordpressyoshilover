# 321-QA-subtype-routing-young-farm-notice-recovery

| field | value |
|---|---|
| ticket_id | 321-QA-subtype-routing-young-farm-notice-recovery |
| priority | P1 |
| status | BLOCKED_USER_COMMIT_GO |
| owner | Codex B after user GO |
| lane | B |
| created | 2026-05-11 |
| doc_path | doc/waiting/321-QA-subtype-routing-young-farm-notice-recovery.md |

## 1. 今回の目的

`general` に落ちて自動公開対象外になる記事を、本文・タイトルの根拠に応じて正しい subtype に分類する。

対象は、特に以下の取りこぼしを減らすこと。

- 二軍 / ファーム / 育成系
- 若手選手の活躍 / 個人成績 / 昇格候補
- 出場選手登録 / 抹消 / 一軍昇格
- 負傷 / 復帰 / リハビリ / 実戦復帰

`ENABLE_PUBLISH_FOR_GENERAL=0` は維持する。`general` の自動公開を丸ごと解放しない。

## 2. 背景

2026-05-11 08時台 JST の観察で、fetcher は3件の下書きを作成したが、自動公開は0件だった。

確認できた事実:

- `drafts_created=3`
- `error_count=0`
- `would_publish=0`
- 3件とも `article_subtype=general`
- publish skip reason は `publish_disabled_for_subtype`
- 本番 env は `ENABLE_PUBLISH_FOR_GENERAL=0`

つまり、mail / scheduler / publish-notice が止まったのではなく、記事分類が `general` になったため既存 gate により下書き止めになった。

本 ticket は `general` gate を緩めず、記事分類の精度を上げる narrow fix とする。

## 3. 今回触ってよい範囲

実装 GO 後に触ってよい範囲:

- `src/rss_fetcher.py`
- `tests/test_rss_fetcher_rule_based_subtypes.py`
- subtype 分類に既に関係する既存テストファイル
- 本 ticket Markdown の作業ログ追記

## 4. 今回触ってはいけない範囲

- Cloud Run env
- `RUN_DRAFT_ONLY`
- `AUTO_TWEET_ENABLED`
- `PUBLISH_REQUIRE_IMAGE`
- `ENABLE_PUBLISH_FOR_GENERAL`
- その他本番挙動に関わる env / flag
- publish 条件そのもの
- mail
- scheduler
- Cloud Run service / job 設定
- Secret Manager
- GitHub Actions
- SEO / noindex / canonical / 301
- X投稿
- 指示外の source 追加
- frontend plugin / WordPress plugin
- build artifact

## 5. 影響範囲

直接影響:

- 記事候補の `article_subtype` 判定
- `general` に落ちていた一部記事が `farm` / `player` / `notice` / `recovery` に分類される可能性

間接影響:

- 既存 env で公開ONになっている subtype に分類された場合、自動公開候補に入る可能性がある
- publish-notice は公開済み記事が出た場合のみ通常通知対象になる

影響しない範囲:

- `general` の publish gate
- mail 送信ロジック
- scheduler 起動条件
- Cloud Run env
- X 投稿
- SEO
- source 収集対象

## 6. 実行予定テスト

バグ修正時ルールに従い、先に再現テストを追加して赤確認する。

追加予定 fixture:

- 二軍 / ファーム / 育成 / 2軍キーワードを含む記事が `farm` に分類される
- 若手選手の活躍 / 個人成績 / 昇格候補が `player` に分類される
- 出場選手登録 / 抹消 / 一軍昇格が `notice` に分類される
- 負傷 / 復帰 / リハビリ / 実戦復帰が `recovery` に分類される
- 根拠が薄い雑多な記事は `general` のまま維持される
- `general` gate は緩めない

実行予定:

- 追加テスト赤確認
- `python3 -m pytest <targeted test>`
- `python3 -m py_compile <touched python files>`
- `python3 -m compileall <touched python files>`
- `python3 -m ast <touched python files>`
- `python3 -m pytest`
- `git diff --check -- <changed files>`

## 7. STOP 条件

- `general` の公開ONが必要になる
- env / Cloud Run / scheduler / publish条件変更が必要になる
- 分類根拠が曖昧で誤公開リスクが高い
- 二軍・若手・登録/抹消・復帰以外に scope が広がる
- source 追加が必要になる
- 既存テスト全件が落ちる
- unrelated failure と混線する
- publish / mail / scheduler に波及する

## 8. 禁止事項

- `ENABLE_PUBLISH_FOR_GENERAL=1` にしない
- publish gate 全体を緩めない
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

- 本来 `general` のまま下書き止めすべき記事が、`player` 等に誤分類されて自動公開候補に入る
- 若手 / 育成という単語だけで、巨人と関係の薄い記事を拾う
- 負傷 / 復帰系を `recovery` に寄せすぎ、事実が薄い記事が公開候補になる
- 登録 / 抹消を `notice` に寄せすぎ、出典が弱い情報を公開候補にする
- 二軍試合記事と一軍記事を混線する
- 既存 `295-QA-subtype-evaluator-misclassify-fix` と scope が重なる

## 10. 実装方針メモ

基本方針:

- `general` gate は維持する
- `resolve_publish_gate_subtype()` の publish gate だけを直接いじらない
- 先に upstream の article subtype 判定を正す
- LLM で分類しない。既存の rule-based subtype 判定を狭く補強する
- `source_type` / category / title / summary の根拠が揃う場合だけ分類を動かす

優先分類:

| pattern | target subtype |
|---|---|
| 二軍 / 2軍 / ２軍 / ファーム / 育成 / 三軍 | `farm` |
| 若手選手の活躍 / 個人成績 / 昇格候補 | `player` |
| 出場選手登録 / 登録抹消 / 一軍昇格 / 公示 | `notice` |
| 負傷 / 故障 / 復帰 / リハビリ / 実戦復帰 | `recovery` |
| 根拠不足 / 雑多な話題 | `general` 維持 |

## 11. Regression Memo 欄

実装時に必ず確認すること:

- `ENABLE_PUBLISH_FOR_GENERAL=0` を維持
- `live_update` の扱いを変えない
- `postgame` / `lineup` / `manager` の既存分類を壊さない
- social_news の structured template 優先を壊さない
- source 追加なし
- publish/mail/scheduler/env 変更なし

## 12. 作業ログ欄

- 2026-05-11: user request により ticket 作成。コード編集・commit・push・deploy・env変更・scheduler変更は未実施。
- 2026-05-11: 8時台 JST の観察で、`general` 分類 + `ENABLE_PUBLISH_FOR_GENERAL=0` により下書き止めになったことを確認済み。本 ticket は gate 緩和ではなく分類精度改善を目的とする。

## 13. 作業後追記欄

- 実際に変更したファイル:
  - `src/rss_fetcher.py`
  - `tests/test_general_subtype_routing.py`
  - `doc/waiting/321-QA-subtype-routing-young-farm-notice-recovery.md`
- diff 概要:
  - `general` 判定後だけに効く `_detect_general_article_subtype()` を追加。
  - 出場選手登録/抹消系は `notice`、負傷/復帰系は `recovery` に分類。
  - 二軍/2軍/ファーム/イースタン + 結果根拠は `farm` に分類。
  - 巨人関連 + 人名候補 + 個人成績/記録根拠は `player` に分類。
  - 三軍の既存 flag 管理は維持するため、三軍だけでは新 direct 分類対象にしない。
- 実行したテスト:
  - `python3 -m pytest tests/test_general_subtype_routing.py` 赤確認: 4 failed
  - `python3 -m pytest tests/test_general_subtype_routing.py` 修正後 green
  - `python3 -m pytest tests/test_classifier_fallback.py tests/test_publish_gating.py tests/test_rss_fetcher_type_routing_flags.py tests/test_rss_template_routing_v2.py`
  - `python3 -m pytest tests/test_general_subtype_routing.py tests/test_rss_fetcher_candidate_quality_flags.py tests/test_classifier_fallback.py tests/test_publish_gating.py tests/test_rss_fetcher_type_routing_flags.py tests/test_rss_template_routing_v2.py`
  - `python3 -m py_compile src/rss_fetcher.py tests/test_general_subtype_routing.py`
  - `python3 -m compileall src/rss_fetcher.py tests/test_general_subtype_routing.py`
  - `python3 -m ast src/rss_fetcher.py`
  - `python3 -m ast tests/test_general_subtype_routing.py`
  - `python3 -c "import ast, pathlib; [ast.parse(pathlib.Path(path).read_text()) for path in ('src/rss_fetcher.py','tests/test_general_subtype_routing.py')]; print('ast ok')"`
  - `python3 -m pytest` sandbox 内: 3580 passed / 3 failed
  - `python3 -m pytest` sandbox 外: 3583 passed
  - `git diff --check -- src/rss_fetcher.py tests/test_general_subtype_routing.py doc/waiting/321-QA-subtype-routing-young-farm-notice-recovery.md`
- テスト結果:
  - 追加テストは赤確認後、修正により green。
  - 関連テスト 81 passed。
  - 全件 pytest は sandbox 内で `tests/test_manual_intake_service.py::LiveServerSmokeTest` 3件が `PermissionError: [Errno 1] Operation not permitted` により失敗。
  - 同じ全件 pytest を sandbox 外で再実行し、3583 passed。
  - `git diff --check` は問題なし。
- 残った懸念:
  - `general` から `player` へ寄せる条件は人名候補 + 巨人関連 + 成績/記録語に限定したが、未知の媒体表現で人名候補を誤認する可能性は0ではない。
  - 二軍/ファームは direct 分類するが、三軍は既存 flag 管理を維持したため、三軍記事の公開候補化は今回の対象外。
  - category 自体を `選手情報` / `ドラフト・育成` に移す変更はしていない。
- 新しく見つかったデグレ:
  - 実装修正後の関連テスト・全件テストでは新規デグレは確認されていない。
  - 初回実装では三軍 flag 管理テスト2件が失敗したため、二軍/ファーム direct 分類に絞り直した。
- 追加した回帰テスト:
  - `tests/test_general_subtype_routing.py`
  - `test_farm_result_from_column_routes_to_farm_subtype`
  - `test_player_notice_from_column_routes_to_notice_subtype`
  - `test_player_recovery_from_column_routes_to_recovery_subtype`
  - `test_player_record_from_team_info_routes_to_player_subtype`
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
