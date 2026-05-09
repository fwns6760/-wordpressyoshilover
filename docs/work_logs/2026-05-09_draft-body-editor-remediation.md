# 2026-05-09 draft-body-editor remediation

## 1. 今回の目的

- `draft-body-editor` の現行 failure 挙動が、repo 内の小さいコード修正と回帰テストで安全に是正できるかを、手順を切って実施する。
- 具体的には、`guard reject` や `no editable candidates` 系の扱いを見直す場合でも、記事公開・メール通知の本線に影響を出さない範囲に限定する。
- 今回の初手では、作業記録Markdownの作成のみを行い、コード編集は user の GO 待ちとする。

## 2. 今回触る範囲

- `src/tools/run_draft_body_editor_lane.py`
- `src/tools/draft_body_editor.py`
- `draft_body_editor` 関連テスト
- 本作業記録Markdown

## 3. 今回触らない範囲

- `src/rss_fetcher.py`
- publish 条件
- mail 通知
- `guarded-publish`
- `publish-notice`
- Cloud Run env
- scheduler
- source 追加
- X 投稿
- SEO / noindex / canonical / 301
- deploy / rerun / live mutation 全般

## 4. 影響範囲

- 直接影響候補は `draft-body-editor` lane の stop reason 判定、exit code、summary 出力、関連テストのみ。
- 期待する効果は、review が必要な候補しかないケースでの failure / alert ノイズを減らしつつ、真の異常は残すこと。
- WordPress の publish 本線、mail、本番 scheduler / env / deploy は今回の変更対象外。

## 5. 実行予定テスト

- `tests.test_run_draft_body_editor_lane`
- 必要なら `tests.test_draft_body_editor`
- 必要最小限の追加回帰テスト
- 変更後は対象ユニットテストを優先し、広域テストは scope 外に波及しない限り増やさない

## 6. STOP条件

- 修正が `draft-body-editor` を超えて publish / mail / scheduler / env / deploy に波及しそうな場合
- Cloud Run job の live 設定変更が前提になった場合
- 真の異常検知まで潰す設計になりそうな場合
- failure の意味を変えることで既存運用契約が崩れると判明した場合

## 7. 禁止事項

- user の GO 前にコード編集しない
- commit / push しない
- deploy しない
- env 変更しない
- scheduler 変更しない
- 手動 rerun しない
- 本線 publish / mail / guarded-publish / publish-notice に触らない

## 8. 想定されるデグレ

- 本来 alert すべき異常まで success 扱いにしてしまう
- `guard_fail` 件数や `stop_reason` の観測契約が崩れる
- `next_run_hint` や summary の意味が変わり、既存監視や人手運用がズレる
- fallback provider や dry-run / real-run の分岐で挙動差が生まれる

## 9. 作業ログ欄

- 2026-05-09 JST: user 指示に従い、本ファイルを新規作成。現時点の変更はこの Markdown のみ。
- 2026-05-09 JST: `master` 直 commit を避けるため、作業ブランチ `draft-body-editor-reject-streak-no-fail` を作成。
- 2026-05-09 JST: 先に再現テストを更新し、`python3 -m unittest tests.test_run_draft_body_editor_lane.TestLaneMain.test_guard_reject_three_streak_returns_success_with_review_hint` を実行。`43 != 0` で赤を確認。
- 2026-05-09 JST: `src/tools/run_draft_body_editor_lane.py` の `reject_streak` exit code を `0` に変更。`stop_reason` と `next_run_hint` は維持。
- 2026-05-09 JST: 対象テストを再実行し green を確認。
- 2026-05-09 JST: `python3 -m unittest tests.test_run_draft_body_editor_lane` を実行し、54 tests green を確認。
- 2026-05-09 JST: `python3 -m unittest discover -s tests` は sandbox 上の localhost bind 制約で 3 error。権限昇格で同コマンドを再実行し、3286 tests green を確認。

## 10. Regression Memo欄

- 修正方針:
  - `reject_streak` の review シグナルは維持し、Cloud Run Job failure と即時 retry だけ止める。
  - `stop_reason`, `per_post_outcomes`, `next_run_hint` は変えない。
- 回帰観点:
  - `wp_get_failed`, `input_error`, `api_fail`, `put_fail` は従来どおり non-zero のまま残す。
  - `no_candidate` は従来どおり exit `0`。
  - 3 連続 guard fail 時の summary payload が欠けないことを確認する。

## 実際に変更したファイル

- `src/tools/run_draft_body_editor_lane.py`
- `tests/test_run_draft_body_editor_lane.py`
- `docs/work_logs/2026-05-09_draft-body-editor-remediation.md`

## diff概要

- `reject_streak` を review-needed な summary 扱いのまま exit `0` に変更
- 既存の 3 連続 guard fail テストを、success + review hint を期待する形へ更新
- 作業記録に実施内容とテスト結果を追記

## 実行したテスト

- `python3 -m unittest tests.test_run_draft_body_editor_lane.TestLaneMain.test_guard_reject_three_streak_returns_success_with_review_hint`
- `python3 -m unittest tests.test_run_draft_body_editor_lane`
- `python3 -m unittest discover -s tests`
- 権限昇格後: `python3 -m unittest discover -s tests`

## テスト結果

- 再現テスト: 初回 red (`43 != 0`)
- 修正後の再現テスト: green
- `tests.test_run_draft_body_editor_lane`: 54 tests green
- 全件: 3286 tests green
- 補足: 非昇格の full suite は sandbox の localhost bind 制約で 3 error。repo 変更起因ではない。

## 残った懸念

- alert policy 自体は非変更のため、live 反映までは現行 image で同じ alert が継続する。
- `reject_streak` を failure metric に使っている外部運用がもしあれば、live 反映後にノイズ減少として見え方が変わる。

## 新しく見つかったデグレ

- なし

## 追加した回帰テスト

- `tests.test_run_draft_body_editor_lane.TestLaneMain.test_guard_reject_three_streak_returns_success_with_review_hint`

## 次回触ってはいけない範囲

- `src/rss_fetcher.py`
- publish 条件
- mail 通知
- `guarded-publish`
- `publish-notice`
- Cloud Run env
- scheduler
- source 追加
- X 投稿
- SEO / noindex / canonical / 301
- live deploy / rerun / 本番設定変更
