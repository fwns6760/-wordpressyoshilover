# P1-mail-storm-permanent-fix design draft

Design-only / Acceptance Pack draft for the guarded-publish old-candidate mail storm.

- Scope of this note: comparison only, no runtime mutation, no `src/` or `tests/` edits in this pass
- Facts used: guarded-publish backlog rows are re-appended every `*/5` run; publish-notice review scan uses `recent_window=24h` and `max_per_run=10`; dedup expiry allows the same backlog pool to re-emit indefinitely

## 1. Three-option comparison

| option | touched_files (under `src/`) | env_knobs (proposed) | implementation_complexity | test_surface | blast_radius | rollback_method |
|---|---|---|---|---|---|---|
| **A. age filter in scanner** | `src/publish_notice_scanner.py` | `PUBLISH_NOTICE_BACKLOG_ONLY_MAX_AGE_DAYS=3` (`0` = disable) | ~35-45 LOC, **3/10** | Adjust `tests/test_publish_notice_scanner.py` backlog-only review cases; add temp WP post-detail fixtures for `date` above/below threshold; regression sweep `tests/test_post_gen_validate_notification.py` and `tests/test_publish_notice_email_sender.py` | `review/hold`: **low-med** (`hold_reason=backlog_only` only). `post_gen_validate`: **low** indirect effect via shared cap. Does not touch real `cleanup_required` / `review` logic directly. | Disable by `PUBLISH_NOTICE_BACKLOG_ONLY_MAX_AGE_DAYS=0`. Image revert SHA: **unknown** until an implementation image exists. |
| **B. persistent sent ledger for old_candidate** | `src/publish_notice_scanner.py`<br>`src/cloud_run_persistence.py` | `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=0`<br>`PUBLISH_NOTICE_OLD_CANDIDATE_MIN_AGE_DAYS=3`<br>`PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_PATH=/tmp/publish_notice_old_candidate_once.json` | ~110-160 LOC, **7/10** | Adjust `tests/test_publish_notice_scanner.py`; add permanent-ledger temp fixtures; add `tests/test_cloud_run_persistence.py` coverage for new state sync/upload; regression sweep `tests/test_post_gen_validate_notification.py` and `tests/test_publish_notice_email_sender.py` | `review/hold`: **med** if scoped strictly to `hold_reason=backlog_only` and age-thresholded old candidates. `post_gen_validate`: **low-med** because shared cap may be freed when old-candidate rows are suppressed. Real `review` / `cleanup_required` path can stay unchanged. | Disable by `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=0` or raise `PUBLISH_NOTICE_OLD_CANDIDATE_MIN_AGE_DAYS` very high. Image revert SHA: **unknown** until an implementation image exists. |
| **C. idempotent guarded history append** | `src/guarded_publish_runner.py` | `ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY=0` | ~55-90 LOC, **5/10** | Adjust `tests/test_guarded_publish_runner.py` and `tests/test_guarded_publish_backlog_narrow.py`; add unchanged-vs-changed history-row fixtures; scanner regression needed because fewer guarded rows change downstream cap behavior | `review/hold`: **high** because unchanged `review` / `cleanup_required` rows would stop producing fresh guarded history records, which can suppress legitimate re-notify behavior as well as old-candidate spam. `post_gen_validate`: **med** indirect effect via shared cap. | Disable by `ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY=0`. Image revert SHA: **unknown** until an implementation image exists. |

## 2. Recommended option

**Recommended option: B**

Option B is the best permanent target because it suppresses the old-candidate storm at the notification boundary without changing the global meaning of `guarded_publish_history.jsonl`. Option A is narrow and easy to roll back, but it is still a sink-side age cutoff and does not preserve a first visible notification for old candidates; Option C fixes the source more aggressively but has the highest blast radius because unchanged real review/hold states would also stop re-emitting.

## 3. Recommended-option test design (`Option B`)

### New fixture files

- **None required**. The existing scanner/persistence tests already prefer `tempfile` JSON/JSONL fixtures over checked-in fixture files; keep that style unless Claude explicitly wants shared fixture files later.

### New test cases

- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_old_candidate_over_threshold_emits_once_and_records_permanent_ledger`
  - first scan with `hold_reason=backlog_only`, draft post status, and WP `date` older than threshold
  - emits exactly once
  - writes `post_id` to the permanent old-candidate ledger
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_old_candidate_over_threshold_is_suppressed_after_permanent_ledger_hit`
  - same guarded row + same `post_id` + permanent ledger already populated
  - emits zero
  - leaves real 24h dedup history logic untouched
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_backlog_only_under_threshold_still_uses_existing_24h_recent_dedup`
  - `hold_reason=backlog_only`, but WP `date` is newer than threshold
  - behavior stays on current 24h dedup path
  - permanent ledger is not written
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_cleanup_review_bypasses_old_candidate_once_ledger`
  - `judgment=review` or `hold_reason=cleanup_required`
  - permanent old-candidate ledger must not suppress this path
- `tests/test_cloud_run_persistence.py::test_entrypoint_restores_and_uploads_old_candidate_once_ledger`
  - publish-notice entrypoint downloads/uploads the new state file under the publish-notice prefix
  - guarded history remains read-only as today
- `tests/test_post_gen_validate_notification.py::test_scan_integration_old_candidate_once_keeps_post_gen_validate_fields_unchanged`
  - mixed run with guarded backlog-old suppression + valid `post_gen_validate`
  - `record_type`, `skip_layer`, subject prefix, and 289 path formatting remain unchanged

### Critical assertions to keep green

- **289 post_gen_validate emit count unchanged for valid skip records**
  - keep `tests/test_post_gen_validate_notification.py::test_scan_and_send_twenty_two_post_gen_validate_notifications`
  - keep `tests/test_post_gen_validate_notification.py::test_post_gen_validate_dedup_and_cap_carryover`
  - keep `tests/test_post_gen_validate_notification.py::test_scan_integration_keeps_publish_and_guarded_paths_and_adds_post_gen_validate`
- **Team Shiny From (`MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org`) unchanged**
  - keep `tests/test_publish_notice_email_sender.py::test_send_keeps_yoshilover_subject_when_sender_envs_change`
  - no sender-env logic should be touched in the implementation
- **real review-needed emit unchanged**
  - keep `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_queues_cleanup_review`
  - keep `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_excludes_red_hard_stop`
  - add the new cleanup-review-bypasses-ledger case above
- **emit cap=10 / dedup 24h not regressed**
  - keep `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_respects_max_per_run`
  - keep `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_skips_recent_notified_post`
  - keep `tests/test_post_gen_validate_notification.py::test_post_gen_validate_dedup_and_cap_carryover`
- **emit suppression for backlog_only old posts works for posts older than threshold**
  - cover with the two new over-threshold old-candidate tests above

### Existing tests already touching the relevant paths

- `publish_notice_scanner.py`
  - `tests/test_publish_notice_scanner.py`
  - direct guarded review coverage already exists for `backlog_only`, `cleanup_required`, hard-stop exclusion, cursor behavior, dedup, and max-per-run behavior
- `guarded_publish_runner.py`
  - `tests/test_guarded_publish_runner.py`
  - `tests/test_guarded_publish_backlog_narrow.py`
  - these do not need semantic changes for Option B, but they are the regression net proving `backlog_only` production rules stay unchanged upstream
- `post_gen_validate` notification path
  - `tests/test_post_gen_validate_notification.py`
  - this is the direct regression net for ticket 289 behavior
- mail sender / Team Shiny regression sentinels
  - `tests/test_publish_notice_email_sender.py`

## 4. Acceptance Pack draft

## Acceptance Pack: P1-mail-storm-permanent-fix / Option B

- **Decision**: HOLD
- **Requested user decision**: Option B を permanent-fix の実装ターゲットとして承認し、Claude が narrow impl ticket を起票してよいか判断する(この Pack 自体では deploy / env flip はしない)
- **Scope**: `src/publish_notice_scanner.py` に old-candidate threshold + emit-once permanent ledger を追加し、`src/cloud_run_persistence.py` でその ledger state を publish-notice prefix に read/write する
- **Not in scope**: `src/guarded_publish_runner.py` の publish 判定、`src/rss_fetcher.py`、`MAIL_BRIDGE_FROM`、289/282/293 の既存通知ロジック、WP mutation、scheduler/job change、secret change、image rebuild
- **Why now**: env 168 removalだけでは storm が止まらず、`2026-05-01 09:35 UTC` trigger でも `sent=10` が継続したため。再発条件を残したまま observe を続ける意味が薄い
- **Preconditions**: `289 24h stable close = unknown`(current state では `2026-05-01 17:00 JST` observe pending) / Team Shiny From 不変確認が必要 / implementation commit と green test evidence は未作成
- **Cost impact**: Gemini call 変化なし / Cloud Run CPU 影響は小 / publish-notice に小さい state file 1本の download+upload が追加 / repeated backlog-only old-candidate mail は first-hit 後 0 になる想定
- **User-visible impact**: 古い候補は threshold 到達後も最初の 1 回は見えるが、同じ stale pool が毎日 cap を食って再送される挙動は止まる。real review-needed mail と 289 post_gen_validate mail は維持する設計
- **Rollback**: `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=0` で即 disable。代替として `PUBLISH_NOTICE_OLD_CANDIDATE_MIN_AGE_DAYS` を極端に大きくして実質無効化できる。image revert SHA は **unknown**(implementation deploy 未実施)
- **Evidence**: 事前 evidence = 本 design draft のみ / 完了 evidence 予定 = scanner+persistence unit green、`tests/test_post_gen_validate_notification.py` green、`tests/test_publish_notice_email_sender.py::test_send_keeps_yoshilover_subject_when_sender_envs_change` green、mixed old-candidate/read-only scan proof
- **Stop condition**: real `review` / `cleanup_required` emit が減る、Team Shiny From が変わる、cap=10 or 24h dedup が崩れる、new ledger upload/download failure が出る、289 path の subject/record_type/skip_layer が変わる
- **Expiry**: 2026-05-02 JST
- **Recommended decision**: HOLD
- **Recommended reason**: Option B 自体は最有力だが、この Pack 時点では implementation/test evidence がなく、`production_health_observe` close も未確定だから

User reply format: 「GO」/「HOLD」/「REJECT」のみ

## 5. Completion report

- **changed_files**: [`docs/handoff/codex_responses/2026-05-01_codex_b_storm_permanent_fix.md`]
- **commit_hash**: `pending`
- **recommended_option**: `B`
  - `A` は low-risk だが sink-side cutoff に留まり、古い候補を 1 回も見せずに落とすだけで再発構造の一部を残す
  - `C` は source-side に近いが、unchanged な real review/hold まで history append を止めてしまい、正常な再通知 semantics を壊す危険が高い
  - `B` は old-candidate だけを emit-once 化でき、permanence と blast-radius の均衡が最もよい
- **open_questions_for_claude**:
  - `post_gen_validate` と guarded review が同じ cap=10 を共有しているため、old-candidate suppression で空いた枠を 289 に自然開放してよいか、それとも総量配分を固定したいか
  - threshold default を `3 days` で切るか、`7 days` にして first visible mail を長めに残すか
- **next_action_for_claude**: `Claude relays Acceptance Pack to user, awaits GO/HOLD/REJECT`
