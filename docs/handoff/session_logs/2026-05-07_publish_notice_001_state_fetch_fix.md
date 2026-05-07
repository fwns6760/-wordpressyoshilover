# 2026-05-07 PUBLISH-NOTICE-001 GCS state fetch failure fix

## 1 行サマリ

- 09:01 JST | INCIDENT_RECONFIRMED | publish-notice | exec=publish-notice (Cloud Run job) | gcloud crashed AttributeError 'str' object has no attribute 'url' on guarded_publish_history.jsonl copy → exit(1)
- 18:30 JST | REPO_IMPL_LANDED | PUBLISH-NOTICE-001 | commit 12e9c5245d2cc612fcd7b527337be5ae1f7dd912 | pushed origin/master
- 18:30 JST | TESTS_GREEN | full pytest 2916 pass / 822 subtests pass / 0 fail (baseline 2904 → +12 new tests)

## scope (1-ticket exception override)

- user 明示で Claude が src/tests 直接実装 (絶対 lock を本 ticket に限り解除、`feedback_claude_no_development_absolute.md`)
- 開発・テスト・commit・push 全て Claude 直接 (Codex 不使用)
- deploy / image rebuild / Scheduler 変更は user 判断 (今回 scope 外)

## 確認済み事実 (PUBLISH-BLOCK-001 read-only 調査由来)

- 2026-05-07T00:01:13Z (09:01 JST) publish-notice job exit(1):
  - `Copying gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl to file:///tmp/pub004d/guarded_publish_history.jsonl`
  - `ERROR: gcloud crashed (AttributeError): 'str' object has no attribute 'url'`
- 2026-05-05〜2026-05-06 に preflight_skip_history.jsonl で同等 GCS copy fail を 6 回観測
- 24h 連続 `[summary] sent=0 suppressed=0 errors=0 reasons={}` の silent stop を観測
- guarded-publish 側は別問題 (stale_source_age 25 件 / hard_stop_*)、本 ticket scope 外

## 修正方針 (option A: minimum-diff)

| 層 | 変更 |
|---|---|
| download() retry | transient gcloud failure (gcloud crashed / AttributeError / 5xx 等) を分類し 3 回まで 1s/2s/4s backoff で retry。permanent (auth/missing) は即 raise 維持 |
| with_state(mandatory=False) | GCSAccessError を swallow、failure_sink に reason 記録、upload_on_exit を skip (remote 上書き防止)、yield False |
| entrypoint | guarded_publish_history.jsonl と preflight_skip_history.jsonl のみ mandatory=False (cursor/history/queue/old_candidate_ledger は mandatory=True 維持)。失敗 reason を `PUBLISH_NOTICE_STATE_FETCH_REASONS` env で runner subprocess に forward |
| summarize_execution_results | optional `state_fetch_reasons` 引数を追加。`state_fetch_failed:<key>` prefix で `[summary] reasons={...}` に merge → silent reasons={} を構造的に消す |
| runner main | env を読んで `[state_fetch] failed_count=N reasons={...}` を summary 直前に明示出力、summarize に forward |

## 不可触 (確認済み)

- mail send 経路 / subject / body / recipient / TeamShinyFrom: 不変
- publish/review/hold/skip 判定: 不変
- scanner cursor 進行ロジック: 不変
- guarded_publish / rss_fetcher / wp_client: 不変
- Dockerfile.publish_notice の gcloud version pin: 未変更 (Phase 1 観察結果次第で別判断)
- Cloud Run env / Scheduler / WP REST: 触らず
- google-cloud-storage Python SDK 全面差し替え: 採用せず (narrow retry で transient を吸収)

## 受け入れ条件 (実装側)

- [x] download() が transient AttributeError を retry し、再現で成功すれば True 返却 (test_download_retries_transient_attribute_error_then_succeeds)
- [x] retry 尽きたら GCSAccessError raise (test_download_raises_after_transient_retries_exhausted)
- [x] permanent auth (401/403) は retry せず即 raise (test_download_does_not_retry_on_permanent_auth_failure)
- [x] with_state(mandatory=False) で failure_sink に reason 記録 + 例外吸収 (test_with_state_mandatory_false_swallows_failure_and_records_reason)
- [x] mandatory=False の場合 upload_on_exit は強制 skip (test_with_state_mandatory_false_skips_upload_even_when_local_file_present)
- [x] mandatory=True は従来通り例外 propagate (test_with_state_mandatory_true_propagates_gcs_access_error)
- [x] entrypoint が history fetch fail 時 PUBLISH_NOTICE_STATE_FETCH_REASONS env を runner に inject (test_entrypoint_continues_when_history_state_fetch_fails_transient)
- [x] summarize が state_fetch_reasons を `state_fetch_failed:` prefix で merge (test_summarize_merges_state_fetch_reasons_into_summary_reasons)
- [x] runner main が env を読んで [state_fetch] line + summarize forward (test_scan_summary_includes_state_fetch_reason_when_env_set)
- [x] 既存 163 targeted test green、full 2904 → 2916 pass (+12 new、減らない)

## 残作業 (USER_DECISION_REQUIRED)

判断してほしいこと:
本修正を Cloud Run job `publish-notice` に live 反映するための image rebuild + revision flip を進めてよいか

推奨: go (image rebuild → flip)
理由:
- repo 反映済み (commit 12e9c52、origin/master push 済み)
- silent stop 24h 継続中、mail 通知導線は閉鎖状態のまま
- 修正は backwards-compatible (state fetch 全成功時は従来挙動と完全同一、失敗時のみ summary に reason が乗る)
- rollback 経路 = 直前 image (現行 cloud_run_persistence 旧版) への traffic flip 1 操作

返答形式: 「go」「stop」「conditional (条件)」

## rollback 経路

- repo: `git revert 12e9c52` で完全戻し可能 (single commit、依存 commit なし)
- live: deploy 未実施 (本 commit 時点では repo 着地のみ)。image rebuild 後の rollback は previous revision (`yoshilover-publish-notice-XXXX-prev`) への traffic flip
- mail 通知導線への悪影響なし (修正は通知漏れを減らす方向のみ、追加送信は発生しない)

## 次の Phase 観察観点 (live 反映後)

1. publish-notice job の exit code 分布: exit(1) 比率が下がる
2. `[summary] reasons=` に `state_fetch_failed:transient_gcloud_attribute_error` 等の key が出現する run の有無
3. `[state_fetch] failed_count=` log line が出現する run の有無
4. `sent>0` / `suppressed>0` の有意な run が再開
5. 64786 のような既 publish post に対する mail 通知 trace 出現

これらが live 反映後 60-90 min で観察できれば close 候補。

## 関連 ticket / followup 候補

- PUBLISH-BLOCK-001 (read-only 調査): 本修正でも残る別 blocker = guarded-publish stale_source_age 全 refused 問題、64795 placeholder title bug、64313/64305 hard_stop_farm_result_placeholder_body は別 ticket
- (条件付) Dockerfile.publish_notice の gcloud version pin: live 反映後に再発する場合に別 narrow ticket で判断
