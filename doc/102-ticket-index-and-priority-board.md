# 102 ticket index and priority board

## meta

- owner: Claude Code
- type: execution queue / Codex A-B dispatch board
- status: READY
- created: 2026-04-26
- updated: 2026-04-26
- source_of_truth: current execution order, status, owner, lane, and blocked state

## role

This file is the execution queue source of truth.

- `CLAUDE.md` = operating rules
- `AGENTS.md` = implementation-agent rules
- this file = current execution queue and A/B dispatch board
- individual ticket docs = detailed specs
- `docs/handoff/codex_requests/` = prompts generated from this board
- `docs/handoff/codex_responses/` and `docs/handoff/run_logs/` = execution evidence

If this file conflicts with an individual ticket doc:

- execution order / status / owner / lane / blocked state: follow this file
- detailed implementation contract: follow the individual ticket doc

## numbering policy

- Continue the existing numeric ticket sequence: `102`, `103`, `104`, ...
- Do not create a new `YOSHI-001` style sequence.
- Keep old names such as `PUB-004-D`, `SPEECH-001`, and `PUB-005-A2` as aliases.
- Do not rename existing ticket docs.
- New execution tickets should use `<number>-<topic>.md`.

## status definitions

- `READY`: can be fired or executed now within its constraints
- `IN-FLIGHT`: currently running in Claude/Codex
- `REVIEW_NEEDED`: implementation returned and needs verification
- `BLOCKED_USER`: explicit user judgment or user-side operation required
- `BLOCKED_EXTERNAL`: external system/precondition required
- `CLOSED`: done and accepted
- `PARKED`: intentionally deferred

## lane definitions

- `A`: Codex A lane, ops / mail / cron / publish runner / WP REST / backup / history / queue / doc commit work
- `B`: Codex B lane, evaluator / validator / article quality / duplicate suppression / source / subtype / tests / audit work
- `either`: either Codex lane can take it after write-scope check
- `Claude`: Claude orchestration or read-only operation
- `User`: user-side operation or final judgment
- `Front-Claude`: front/plugin lane outside backend ownership

## active execution board

### 102 ticket-index-and-priority-board

- **alias**: -
- **priority**: P0
- **status**: READY
- **owner**: Claude Code
- **lane**: Claude
- **ready_for**: none
- **next_action**: keep this board current after each close/fire; stage only this doc when syncing
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/102-ticket-index-and-priority-board.md`
- **acceptance**: 102-122 rows are present, old 104-wait contradiction removed, X unlock sequence explicit, A/B next actions clear
- **repo_state**: committed
- **commit_state**: current X ticket sync commit
- **next_prompt_path**: -
- **last_commit**: `42d279b` board source-of-truth cross-ref

### 103 publish-notice-cron-health-check

- **alias**: -
- **priority**: P0.5
- **status**: CLOSED
- **owner**: Codex A
- **lane**: A
- **ready_for**: none
- **next_action**: use the health-check tool during mail/cron uncertainty; no follow-up unless thresholds need tuning
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/publish_notice_cron_health.py`, `src/tools/run_publish_notice_cron_health_check.py`, `tests/test_publish_notice_cron_health.py`
- **acceptance**: cron/publish/log/SMTP/history are distinguished, dry-run only, secret values are never displayed
- **repo_state**: pushed
- **commit_state**: `d6548ba`
- **next_prompt_path**: -
- **last_commit**: `d6548ba` 103 publish-notice cron health check (dry-run)

### 104 lineup-hochi-only-duplicate-suppression

- **alias**: PUB-002-E
- **priority**: P0.5
- **status**: CLOSED
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: verify effect during 105 dry-run/ramp; no implementation wait remains
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/lineup_source_priority.py`, related tools/tests, evaluator hook
- **acceptance**: Hochi source wins, one lineup per `game_id`, non-Hochi lineup deferred/refused, prefix misuse detected
- **repo_state**: pushed
- **commit_state**: `78f965d`
- **next_prompt_path**: -
- **last_commit**: `78f965d` PUB-002-E lineup-source-priority-and-duplicate-suppression

### 105 all-eligible-draft-backlog-publish-ramp

- **alias**: PUB-004-D
- **priority**: P0
- **status**: BLOCKED_TICKET(130 land 後 autonomous re-dry-run + auto ramp、user 確認なし)
- **owner**: Claude Code(orchestration)
- **lane**: Claude
- **ready_for**: 130 land 後 autonomous re-dry-run → publish_clean + repaired_publishable 件数 > 0 → **autonomous live ramp**(burst 20 / hard cap 30 / daily 100、hard_stop 個別 hold、repairable 前 cleanup → verify)
- **next_action**: 130 (3 分類 + publish 前 cleanup chain) land → 105 autonomous re-dry-run → 出力 4 件数(publish_clean / repaired_publishable / hard_stop / hold_due_cleanup_failure)確認 → 20 件 burst autonomous live publish
- **blocked_by**: 130 implementation
- **user_action_required**: **NO**(新方針: hard_stop 以外 autonomous publish、user 確認なし)
- **cap**: max_burst default **20** / hard cap **30** / daily **100**(JST 0:00 reset 既設)
- **write_scope**: re-dry-run + PUB-004-B `--live --max-burst 20 --daily-cap-allow` autonomous fire
- **acceptance**: 4 件数(publish_clean / repaired_publishable / hard_stop / hold_due_cleanup_failure)出力 + top refusal reasons + lineup effect が visible
- **dry_run_result**(2026-04-26 旧 spec、filter 過 strict): total 97 / Green 0 / Yellow 0 / Red 97 / cleanup 0 / lineup_representative 0 / lineup_deferred 2(`/tmp/pub004d/full_eval.json`、130 実装後 obsolete)
- **repo_state**: 130 land 後に再 dry-run 必須
- **commit_state**: doc alias `4741eee`
- **next_prompt_path**: -
- **last_commit**: `4741eee` docs for 105/PUB-004-D

### 106 speech-seed-intake-dry-run

- **alias**: SPEECH-001
- **priority**: P1
- **status**: CLOSED
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: later bridge into comment_notice/fixed lane as a separate numbered ticket
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/speech_seed_intake.py`, `src/tools/run_speech_seed_intake_dry_run.py`, `tests/test_speech_seed_intake.py`
- **acceptance**: comment_candidate / deferred_pickup / duplicate_like / reject route hints and tests pass
- **repo_state**: pushed
- **commit_state**: `4f4b70d`
- **next_prompt_path**: -
- **last_commit**: `4f4b70d` SPEECH-001 news-duplicate-resistant speech seed intake dry-run

### 107 x-post-template-candidate-dry-run

- **alias**: PUB-005-A2
- **priority**: P2
- **status**: CLOSED
- **owner**: Codex A
- **lane**: A
- **ready_for**: none
- **next_action**: keep live X posting blocked until PUB-005-B / user explicit trigger
- **blocked_by**: none for dry-run; live post remains blocked under 114
- **user_action_required**: none for this closed dry-run ticket
- **write_scope**: `src/x_post_template_candidates.py`, `src/tools/run_x_post_template_candidates_dry_run.py`, `tests/test_x_post_template_candidates.py`
- **acceptance**: four template types, 280-character limit, URL inclusion, history dedup, tests pass
- **repo_state**: pushed
- **commit_state**: `34a1bfa`
- **next_prompt_path**: -
- **last_commit**: `34a1bfa` PUB-005-A2 x-post template candidate generator dry-run

### 108 existing-published-site-component-cleanup-audit

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: 124-A (live cleanup apply) で audit 結果を適用、本日 publish 8 件 site_component cleanup 候補
- **blocked_by**: none
- **user_action_required**: none(124-A は autonomous fire 候補 = 130 land 後)
- **write_scope**: src/published_site_component_audit.py + tools + tests(read-only audit)
- **acceptance**: ✓ WP write zero / cleanup_proposals JSON / 6 tests pass / suite 1127
- **repo_state**: pushed
- **commit_state**: **`84b91ce`**
- **next_prompt_path**: -
- **last_commit**: `84b91ce` 108 audit

### 109 missing-primary-source-blocker-reduction

- **alias**: PUB-002-B
- **priority**: P1
- **status**: **CLOSED**
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: 109 audit 結果を 130 Hard/Soft 判定 + PUB-004-A の `missing_primary_source` Soft 化に活用
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: src/missing_primary_source_recovery.py + tools + tests(read-only audit)
- **acceptance**: ✓ 6 cause_tag 分類 / rescue_candidates / WP write zero
- **repo_state**: pushed
- **commit_state**: **`94c6186`**
- **next_prompt_path**: -
- **last_commit**: `94c6186` 109 audit (102/124 bundle)

### 110 subtype-unresolved-blocker-reduction

- **alias**: PUB-002-C
- **priority**: P1
- **status**: **CLOSED**
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: extractor heuristic 拡張は反映済(infer_subtype 6 新 branch + off_field 追加)、後続 follow-up は別 narrow ticket で起票時
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: src/pre_publish_fact_check/extractor.py 改修 + tests/test_subtype_unresolved_recovery.py
- **acceptance**: ✓ 6 新 branch / first-match order / 既存 tests pass
- **repo_state**: pushed
- **commit_state**: **`99e9f1c`**
- **next_prompt_path**: -
- **last_commit**: `99e9f1c` 110 extractor heuristic 拡張

### 111 long-body-compression-or-exclusion

- **alias**: PUB-002-D
- **priority**: P2
- **status**: **CLOSED**
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: audit 結果は 130 Hard/Soft 判定の `long_body` Soft Cleanup 化に活用
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: src/long_body_compression_audit.py + tools + tests(read-only audit)
- **acceptance**: ✓ prose 長分布 / subtype 別 policy / WP write zero
- **repo_state**: pushed
- **commit_state**: **`deea3bd`**
- **next_prompt_path**: -
- **last_commit**: `deea3bd` 111 audit

### 112 title-prefix-and-lineup-misclassification-fixtures

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: 104 lineup_prefix_misuse の regression test として常時 suite 内、追加修正不要
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: tests/test_title_prefix_lineup_misuse_fixtures.py(new tests only、src 改変ゼロ)
- **acceptance**: ✓ 9 fixtures / src diff zero / suite 1144
- **repo_state**: pushed
- **commit_state**: **`28b0dec`**
- **next_prompt_path**: -
- **last_commit**: `28b0dec` 112 fixture regression

### 113 halluc-lane-002-llm-fact-check-augmentation

- **alias**: HALLUC-LANE-002
- **priority**: P1
- **status**: **PARKED**(adapter 実装済 / 凍結 = Gemini live call は user-go 境界)
- **owner**: Codex A 完了(adapter 実装は mock-test only)
- **lane**: A
- **ready_for**: none(凍結)
- **next_action**: 凍結維持。Gemini live call(`--live` 経由)実行は user 明示 go 後のみ unfreeze
- **blocked_by**: Gemini API 課金境界(user 1 ワード `HALLUC-LANE-002 live go` 待ち)
- **user_action_required**: explicit `HALLUC-LANE-002 live go` only when ready to incur Gemini API cost
- **write_scope**: src/pre_publish_fact_check/llm_adapter_gemini.py + detector.py 改修 + tests + requirements.txt(google-generativeai 追加)
- **acceptance**: ✓ adapter 実装(mock-test)、live call 未実行
- **repo_state**: doc + impl pushed (DOC-SYNC-11 経由想定)
- **commit_state**: impl 一括 commit(進行中 `bl8c0ddpm`)
- **next_prompt_path**: -
- **last_commit**: `269e1f4` 113 HALLUC-LANE-002 Gemini Flash adapter (mock-tested)

### 114 x-post-gate-live-helper

- **alias**: PUB-005-B
- **priority**: P1
- **status**: PARKED(umbrella; child tickets 119-122 govern execution)
- **owner**: Claude Code / Codex A or B per child ticket
- **lane**: either
- **ready_for**: none
- **next_action**: execute child tickets in order: 119 -> 120 -> 121 -> 122
- **blocked_by**: 119/120 prerequisites and one-time live unlock at 121
- **user_action_required**: only for 121 X live unlock / credential boundary
- **write_scope**: umbrella only; child tickets define concrete write scopes
- **acceptance**: Green-only controlled autopost path is split into safe child tickets; no direct 114 fire
- **repo_state**: parent doc-first exists
- **commit_state**: committed doc
- **next_prompt_path**: none until unblocked
- **last_commit**: `b69c322` / `34a1bfa` related dry-run work

### 115 codex-desktop-automation-tick-recovery

- **alias**: 093
- **priority**: P1
- **status**: BLOCKED_USER
- **owner**: Claude/User
- **lane**: User
- **ready_for**: none
- **next_action**: user-side Codex Desktop / workspace / restart operation when needed
- **blocked_by**: user-side desktop/app operation
- **user_action_required**: restart/reattach when this lane is revisited
- **write_scope**: none
- **acceptance**: heartbeat/log/tick evidence appears after user operation
- **repo_state**: alias doc exists
- **commit_state**: committed doc
- **next_prompt_path**: -
- **last_commit**: docs synced in `f6575a8`/later doc commits

### 116 wsl-cron-reboot-resilience-check

- **alias**: 095-E
- **priority**: P2
- **status**: BLOCKED_USER
- **owner**: Claude/User
- **lane**: User
- **ready_for**: none
- **next_action**: verify WSL cron resilience after an actual PC reboot
- **blocked_by**: user-side reboot / external runtime observation
- **user_action_required**: perform/confirm reboot window when desired
- **write_scope**: none unless a later fix ticket is opened
- **acceptance**: after reboot, cron service and publish-notice schedule are confirmed without secret display
- **repo_state**: alias doc exists
- **commit_state**: committed doc
- **next_prompt_path**: -
- **last_commit**: docs synced in recent publish-notice docs

### 117 adsense-ad-unlock-policy-and-css-toggle

- **alias**: 087-A
- **priority**: P1.5
- **status**: **CLOSED**(主作業 = full CSS kill removal `0555733` 着地済、policy A/B/C 選択は future tuning として ticket と独立、user op 待たない)
- **owner**: Claude-managed front-scope 完了
- **lane**: front-scope
- **ready_for**: none
- **next_action**: future tuning(A/B/C 選択)は別 narrow ticket で起票。本 ticket は core deliverable 完了で close。
- **blocked_by**: none
- **user_action_required**: **none**(2026-04-26 user 明示: 「あとでチューニングするから、君の中で作業が終ればクローズ」)
- **write_scope**: `src/custom.css` の AdSense 全殺し section(完了済)
- **acceptance**: ✓ CSS kill 全削除完了(`0555733` + `5855591` reader-focus / print AdSense 削除)/ AdSense pattern grep 0 hit / mobile/desktop 表示維持 / backend 差分ゼロ
- **repo_state**: pushed
- **commit_state**: **`0555733`** + `5855591`(reader-focus / print AdSense 追加削除)
- **next_prompt_path**: -
- **last_commit**: `5855591` AdSense reader-focus / print rules cleanup
- **future_tuning**: A/B/C policy 選択 + 各 pattern 適用 = 将来別 ticket(125 + 087 と関連)
- **source_of_truth**: `docs/handoff/ad_policy_memo_post_launch.md`(A/B/C 方針正本、future tuning 用 reference)
- **parent**: 087(器 = AdSense slot 枠 既設)

### 118 pub004-red-reason-decision-pack

- **alias**: -
- **priority**: P0.5
- **status**: REVIEW_NEEDED
- **owner**: Claude Code
- **lane**: A / Claude orchestration
- **ready_for**: Claude
- **next_action**: present or refresh decision pack from `/tmp/pub004d/full_eval.json`; do not retune filters here
- **blocked_by**: none for read-only summary; live ramp remains blocked by 105 / 123
- **user_action_required**: none for summary generation; live ramp decision remains user boundary
- **write_scope**: report/doc only; no src changes required
- **acceptance**: Red top reasons, representative post_ids, absolute Red, cleanup-rescuable candidates, and next action are visible
- **repo_state**: doc exists
- **commit_state**: pending 118/123 sync
- **next_prompt_path**: -
- **last_commit**: -
- **artifact**: `/tmp/pub004d/decision_pack.json`
- **parent**: 105 / PUB-004-D

### 119 x-post-eligibility-evaluator

- **alias**: PUB-005-A
- **priority**: P0.5
- **status**: **CLOSED**(impl 着地済 `0253b2a`、Green-only X candidates 評価器、X API zero)
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: 120 / 121 / 122 fire 時に再開(WP 公開済 Green 候補増えてから順次)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/x_post_eligibility_evaluator.py`, `src/tools/run_x_post_eligibility_evaluator.py`, `tests/test_x_post_eligibility_evaluator.py`
- **acceptance**: ✓ published-only / Green-only eligible list, Yellow/Red/X-side Red refused with reasons, JSON + human summary, WP write zero, X API zero
- **repo_state**: pushed
- **commit_state**: **`0253b2a`**
- **next_prompt_path**: -
- **last_commit**: `0253b2a` 119 x-post-eligibility-evaluator (read-only, X API zero)
- **known_issues**: 1227 suite に test_x_post_eligibility_evaluator の 2 fail(127 land 後の baseline)、follow-up narrow ticket で別途修正
- **parent**: 114 / PUB-005

### 120 x-post-autopost-queue-and-ledger

- **alias**: PUB-005-A3
- **priority**: P1
- **status**: PARKED
- **owner**: Codex A or either after 119 close
- **lane**: A/either
- **ready_for**: none
- **next_action**: wait for 119 close, then queue eligible + 107 template candidates with candidate_hash dedup
- **blocked_by**: 119 close
- **user_action_required**: none
- **write_scope**: `src/x_post_autopost_queue.py`, `src/tools/run_x_post_autopost_queue.py`, `tests/test_x_post_autopost_queue.py`
- **acceptance**: queue/ledger fields present, duplicate queue/post prevented, dry-run summary, X API zero
- **repo_state**: doc exists
- **commit_state**: current X ticket sync commit
- **next_prompt_path**: create after 119 close
- **last_commit**: current X ticket sync commit
- **parent**: 114 / PUB-005

### 121 x-post-live-helper-one-shot-smoke

- **alias**: PUB-005-B1
- **priority**: P1
- **status**: BLOCKED_USER
- **owner**: Codex A after user unlock
- **lane**: A
- **ready_for**: none
- **next_action**: wait for 120 close + one-time X live unlock / credential boundary
- **blocked_by**: X live unlock / credential boundary / 120 close
- **user_action_required**: explicit one-time X live unlock before implementation or live smoke
- **write_scope**: `src/x_post_live_helper.py`, `src/tools/run_x_post_live_helper.py`, `tests/test_x_post_live_helper.py`
- **acceptance**: dry-run default, `--live` required, one candidate only, ledger updated on success, duplicate refused, secret values never printed
- **repo_state**: doc exists
- **commit_state**: current X ticket sync commit
- **next_prompt_path**: none until unblocked
- **last_commit**: current X ticket sync commit
- **parent**: 114 / PUB-005

### 122 x-post-controlled-autopost-rollout

- **alias**: PUB-005-C
- **priority**: P1.5
- **status**: PARKED
- **owner**: Codex A after 121 smoke success
- **lane**: A
- **ready_for**: none
- **next_action**: wait for 121 smoke success, then start daily cap 1 controlled rollout
- **blocked_by**: 121 smoke success
- **user_action_required**: none after 121 one-time unlock unless cron/live policy changes
- **write_scope**: `src/x_post_controlled_rollout.py`, `src/tools/run_x_post_controlled_rollout.py`, `tests/test_x_post_controlled_rollout.py`
- **acceptance**: daily cap enforced, duplicate prevented, refusal/failure reasons recorded, Green-only gate cannot be bypassed
- **repo_state**: doc exists
- **commit_state**: current X ticket sync commit
- **next_prompt_path**: create after 121 smoke success
- **last_commit**: current X ticket sync commit
- **parent**: 114 / PUB-005

### 123 pub004-auto-publish-readiness-and-regression-guard

- **alias**: -
- **priority**: P0.5
- **status**: READY
- **owner**: Claude Code / Codex A if implementation is needed
- **lane**: A / Claude orchestration
- **ready_for**: A / Claude
- **next_action**: classify current no-auto-publish state without live publish; protect against filter/cron regressions
- **blocked_by**: none for read-only readiness; live publish remains blocked by 105 user decision
- **user_action_required**: none for readiness check; yes for any live publish or cron activation
- **write_scope**: `doc/123-pub004-auto-publish-readiness-and-regression-guard.md` / optional read-only report only
- **acceptance**: current state classified, guarded publish tests pass, no cron activation, no WP write, no filter retune
- **repo_state**: doc exists
- **commit_state**: pending 118/123 sync
- **next_prompt_path**: create at fire time if Codex is used
- **last_commit**: -
- **parent**: 105 / PUB-004-D

### 124 published-cleanup-apply-runner

- **alias**: -
- **priority**: P1
- **status**: READY (doc-first spec) / live 適用は BLOCKED_USER
- **owner**: Claude Code (spec) / Codex A (後続実装、user 判断後)
- **lane**: A
- **ready_for**: A (124-A 実装便、user 1 ワード判断後)
- **next_action**: spec doc commit + push、user `124-A go` 後 Codex A で 124-A 実装 fire
- **blocked_by**: live 適用 = user 判断(本日 publish 8 件 post-hoc cleanup 開始)
- **user_action_required**: 124-A 実装 fire の go / hold (1 ワード)
- **write_scope**: doc/124 (本 ticket = doc-first); 124-A 実装は src/published_cleanup_apply.py + src/tools/run_published_cleanup_apply.py + tests/test_published_cleanup_apply.py
- **acceptance**: 108 audit input → WP REST update_post_fields apply / 3-gate refuse / backup / history 記録 / PUB-004-B 同形 contract
- **repo_state**: pushed
- **commit_state**: `94c6186`
- **next_prompt_path**: 124-A fire 時に Claude が用意
- **last_commit**: `94c6186` doc sync
- **parent**: 108 (audit) / PUB-004-B (cleanup contract pre-publish 版)

### 125 adsense-manual-ad-unit-embed

- **alias**: 087-B
- **priority**: P0.5(autonomous front-scope work、user op 不要部分先行)
- **status**: **READY**(Claude-managed front-scope 自律進行、user op 待ちにしない)
- **owner**: **Claude-managed front-scope**(Front-Claude 不在のため Claude 自身が CSS/slot/template を直接編集)
- **lane**: Claude / front-scope
- **ready_for**: Claude 自律実装(slot scaffolding + CSS + template wrapper、ad unit ID 不要部分)
- **next_action**: Claude が autonomous で `.yoshi-ad--*` slot wrapper を WP theme template に追加、CSS で slot 寸法/余白を整備、ad unit ID 挿入箇所だけ後で差し替え可能な placeholder で wire up
- **blocked_by**: none for slot/CSS/template scaffolding。**ad unit ID 実値挿入のみ user op 必要**(AdSense dashboard で発行された unit ID 提供のとき Claude が差し替え)
- **user_action_required**: **none for scaffolding**。ad unit ID 実値が必要になった段階で Claude が「この slot の ID をください」と最小限要求するだけ
- **write_scope**: `src/custom.css` の AdSense slot 整備 + WP theme template の `.yoshi-ad--*` wrapper(backend Python / publish runner / WP REST / .env / secret 触らない)
- **acceptance**: slot wrapper が 087 設計通りの位置に配置 / CSS で破綻なし / placeholder で ad unit ID 差し替え可能 / backend 差分ゼロ / double script なし
- **repo_state**: doc committed `72a3ccd`
- **commit_state**: doc committed
- **next_prompt_path**: -(Claude 自身で実装)
- **last_commit**: `72a3ccd` 102 board sync
- **parent**: 087 / 117

### 126 sns-topic-fire-intake-dry-run

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(impl `5bfe892` + B review OK 10/10、suite 1227 pass、SNS 露出 zero、LLM SDK zero、WP write zero)
- **owner**: Codex B 完了
- **lane**: B
- **ready_for**: none
- **next_action**: 127 (`2669faa`) で SNS topic source recheck → draft builder 経路に接続済
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: src/sns_topic_fire_intake.py + src/tools/run_sns_topic_fire_intake.py + tests/test_sns_topic_fire_intake.py
- **acceptance**: ✓ 8 MVP categories / unsafe reject / post text/account/URL 露出ゼロ / fact_recheck_required=true / B review pass 10/10
- **repo_state**: pushed
- **commit_state**: **`5bfe892`**
- **next_prompt_path**: -
- **last_commit**: `5bfe892` 126 SNS topic fire intake
- **follow_up**: private-person reject heuristic 拡張(narrow ticket 候補、現状 family-centric なため非家族 private-person fixture 追加)
- **parent**: 064 / 082 / 106

### 127 sns-topic-source-recheck-and-draft-builder

- **alias**: -
- **priority**: P1
- **status**: **CLOSED**(impl 着地済 `2669faa`、5 route 分類 + 10 new tests、resolver mock-injectable、leak guard、WP write zero、LLM SDK zero、live HTTP zero)
- **owner**: Codex B 完了
- **lane**: B
- **ready_for**: none
- **next_action**: 128(SNS topic auto-publish through PUB-004 gate)で draft → publish 経路に接続(130 land 後)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/sns_topic_source_recheck.py`, `src/tools/run_sns_topic_source_recheck.py`, `tests/test_sns_topic_source_recheck.py`
- **acceptance**: ✓ 5 route 分類(draft_ready / candidate_only / hold_sensitive / duplicate_news / reject)/ resolver mock / SNS 漏洩 zero / `source_recheck_passed=true` / `publish_gate_required=true`
- **repo_state**: pushed
- **commit_state**: **`2669faa`**
- **next_prompt_path**: -
- **last_commit**: `2669faa` 127 sns-topic-source-recheck-and-draft-builder
- **parent**: 126 / PUB-002-A

### 128 sns-topic-auto-publish-through-pub004

- **alias**: -
- **priority**: P1
- **status**: PARKED
- **owner**: Codex A / Claude orchestration after 127 close
- **lane**: A
- **ready_for**: none
- **next_action**: wait for 127 close + PUB-004 readiness, then publish source-rechecked drafts through PUB-004 gate
- **blocked_by**: 127 close + PUB-004 readiness
- **user_action_required**: none per article once 127/128 automation is activated; no raw SNS direct publish
- **write_scope**: `src/sns_topic_publish_bridge.py`, `src/tools/run_sns_topic_publish_bridge.py`, `tests/test_sns_topic_publish_bridge.py`
- **acceptance**: 127 source-rechecked drafts only, PUB-004 evaluator mandatory, Red refused, dry-run would_publish visible, live respects PUB-004 caps/history/backup
- **repo_state**: doc exists
- **commit_state**: pending SNS topic sync
- **next_prompt_path**: create after 127 close and 123/PUB-004 readiness
- **last_commit**: -
- **parent**: 127 / PUB-004

### 130 pub004-hard-stop-vs-repairable-before-publish

- **alias**: -
- **priority**: **P0**
- **status**: **READY**(A slot next、即 fire)
- **owner**: Claude Code(設計)/ Codex A(実装)
- **lane**: A
- **ready_for**: A 即 fire
- **next_action**: A slot で 130 implementation fire(3 分類 hard_stop / repairable_before_publish / publish_clean + 公開前 cleanup → verify → publish + cap 20 burst / hard 30 / daily 100)
- **blocked_by**: none
- **user_action_required**: none(autonomous range)
- **spec_doc**: `doc/130-pub004-hard-stop-vs-repairable-before-publish.md`(新 spec、旧 file `130-pub004-hard-stop-vs-soft-cleanup-split.md` は本 file が supersede)
- **policy_revised**: 2026-04-26(Soft Cleanup の publish 後ログ → **公開前 cleanup → verify → publish** に変更)
- **write_scope**: `src/guarded_publish_evaluator.py` + `src/guarded_publish_runner.py` + `src/tools/run_guarded_publish.py` + `tests/test_guarded_publish_evaluator.py` + `tests/test_guarded_publish_runner.py`
- **acceptance**: 3 分類 / publishable=NOT hard_stop / cleanup_required=repairable / publish 前 cleanup → verify → publish / cleanup 失敗で hold(全体 abort なし)/ cap 20/30/100 / CLI help "max 3" 文言消滅 / 既存 tests pass
- **repo_state**: 新 spec doc untracked、旧 spec doc `130-pub004-hard-stop-vs-soft-cleanup-split.md` 削除予定
- **commit_state**: pending
- **next_prompt_path**: `/tmp/codex_130_impl_prompt.txt`(Claude が refire 時 rewrite)
- **last_commit**: -
- **parent**: 105 / PUB-004-A / PUB-004-B / PUB-002-A

### 131 publish-notice-burst-summary-and-alerts

- **alias**: -
- **priority**: **P0.5**
- **status**: READY(130 land 後 fire)
- **owner**: Claude Code(設計)/ Codex A(実装)
- **lane**: A
- **ready_for**: 130 land 後
- **next_action**: 130 land 後、131 implementation fire(per-post 通常通知 **suppress しない** + 10 本ごと summary + alert + emergency + duplicate のみ抑止)
- **blocked_by**: 130 land(PUB-004-B alert hook 連携)
- **user_action_required**: none
- **spec_doc**: `doc/131-publish-notice-burst-summary-and-alerts.md`(新 spec、旧 file `131-publish-notice-batch-suppress.md` は本 file が supersede)
- **policy_lock**: publish-notice mail を **suppress しない**。layer 5(同 post_id 30 分内重複)のみ抑止
- **write_scope**: src/publish_notice_email_sender.py 改修 + src/tools/run_publish_notice_email_dry_run.py 改修 + tests
- **acceptance**: per-post 通常通知 維持 / 10 本ごと batch summary / Hard Stop / publish 失敗 / postcheck 失敗 / X 発火 alert / duplicate のみ suppress / mock SMTP test
- **repo_state**: 新 spec doc untracked、旧 spec doc `131-publish-notice-batch-suppress.md` 削除予定
- **commit_state**: pending
- **next_prompt_path**: 131 fire 時 Claude が用意
- **last_commit**: -
- **parent**: 095-D / 088 / 130

## lane inventory rule

Goal:

- Codex A READY inventory: at least 2 tickets when possible
- Codex B READY inventory: at least 2 tickets
- either READY inventory: at least 1 ticket when possible

Operational rule:

- If a lane has fewer than 2 READY tickets, Claude should replenish inventory before opening unrelated new feature work.
- Codex B replenishment should come from quality, validator, duplicate, source, subtype, article audit, tests, or fixtures.
- Codex A replenishment should come from ops, mail, cron, publish runner, WP REST, backup/history/queue, or doc commit work.
- Each READY ticket should include `next_prompt_path`, `write_scope`, `acceptance`, and a test command or verification command before fire.

Current inventory(2026-04-26 16:00 JST sync):

| lane | READY count | tickets |
|---|---:|---|
| A | 3 | 123(readiness/regression guard) / **130**(P0、即 fire) / 131(130 land 後)|
| B | 0 | 119 / 126 / 127 close 後のため READY 在庫なし。次の narrow B ticket を Claude が補充 |
| Claude | 1 | 125 AdSense slot 自律実装(front-scope、user 待ちなし)|
| either | 0 unblocked live tickets | 114 umbrella parked; 120 parked until live ramp |

Closed today:
- 108 / 109 / 110 / 111 / 112(commit hashes 各 row 参照)
- 117 B(`0555733`)/ 119(`0253b2a`)
- 126(`5bfe892` + B review OK 10/10)/ 127(`2669faa`)
- 113(`269e1f4`、PARKED with Gemini live = user-go 境界)

## pull rule

### Codex A

1. Pull highest-priority `lane=A` and `status=READY`.
2. If none exists, use bounded ops/doc/test work only after write-scope check.
3. Do not touch `.env`, secrets, Cloud Run env, `RUN_DRAFT_ONLY`, X live post, or front/plugin.

### Codex B

1. Pull highest-priority `lane=B` and `status=READY`.
2. Prefer P0.5 quality/fixture tickets before P1/P2 cleanup work.
3. Do not collide with Codex A write scopes.
4. Do not touch `.env`, secrets, Cloud Run env, `RUN_DRAFT_ONLY`, X live post, or front/plugin.

## next actions(2026-04-26 PM 同期)

- **A slot next**: **130**(PUB-004 hard_stop / repairable_before_publish / publish_clean 3 分類 + 公開前 cleanup → verify → publish + cap 20/30/100)→ 131(suppress しない通知 layering)→ 123(readiness/regression guard の read-only confirm)。
- **B slot next**: 119 / 126 / 127 は **CLOSED**(`0253b2a` / `5bfe892` review OK / `2669faa`)。新規 narrow B ticket 補充までは待機、128 prep は 130 land 後の A lane で扱う。
- **Claude 直**: 125 AdSense slot 実装(`.yoshi-ad--*` wrapper を `src/yoshilover-063-frontend.php` + `src/custom.css` に追加、ad unit ID 差し替えのみ user op)。並行で 123 readiness guard を 130 land 後に挟む(read-only)。
- **Live 105 ramp**: 130 land → 105 autonomous re-dry-run → publish_clean + repaired_publishable 件数 > 0 → **autonomous live ramp 20 件 burst**(user 確認なし、新方針)。
- **PUB-004-C auto-publish cron**: 105 1 回目 burst が安全に通った後に追加検討。
- **SNS topic auto-publish path**: 126(`5bfe892`)→ 127(`2669faa`)→ 128(130 land 後)。raw SNS から直接 publish しない。
- **Do not advance 113 / 115 / 116 / 121** without user action or external precondition. 113 = Gemini live = user-go 境界(`HALLUC-LANE-002 live go`)で凍結。
- **Do not fire 114 directly**; use 119 -> 120 -> 121 -> 122.

## dependency locks

- 104 before 105: satisfied (`78f965d`).
- 103 before/near 105: satisfied (`d6548ba`).
- X live post: blocked until 121 one-time live unlock / credential boundary; after that, controlled autopost follows 122 daily cap.
- HALLUC-LANE-002 real LLM/API: blocked until explicit user go.
- `RUN_DRAFT_ONLY=False`: prohibited here.
- Cloud Run env changes: prohibited here.

## Claude notification

```text
102 board の整合修正方針をCodex側で反映しました。

修正内容:
- PUB-005の古い毎回確認 / 自律投稿禁止前提を置換
- 114はX live helper umbrellaとしてPARKED化し、直接fireしない
- 119〜122をX unlock sequenceとして追加
- 119はREADY、B slot first候補
- 120はPARKED、119 close後
- 121はBLOCKED_USER、X live unlock / credential boundary
- 122はPARKED、121 smoke成功後
- Grok / xAI API禁止、X検索 / X収集は別laneと明記
- controlled autopostはdaily cap初期1件、安定後3件
- 125をAdSense手動ad unit ticketとしてboardへ追加
- 126〜128をSNS話題検知→source recheck→PUB-004自動publish pathとして追加
- 126はREADY、SNS本文/アカウント/URLを出さないtopic-fire intake
- 127はPARKED、126 close後にsource recheck + WP draft自動生成
- 128はPARKED、127 close + PUB-004 readiness後に自動publish bridge

次の実行:
- B slot next: 126
- 126 close後: 127
- 127 close後: 128(PUB-004 readiness 必須)
- 119 close後: 120
- 121はone-time X live unlock後のみ
- 122は121 smoke成功後のみ
- 105 live rampは引き続きuser判断待ち

注意:
既存docリネームなし。
コード変更なし。
publish実行なし。
mail実送信なし。
env/secret操作なし。
git add -A禁止。
```

## verification checklist

- `git diff -- doc/102-ticket-index-and-priority-board.md`
- 104 is only represented as `CLOSED`; no old "104 wait" next-action remains.
- 105 live ramp remains user-gated after the all-red dry-run result.
- 108-128 are present.
- 123 is READY for no-auto-publish readiness/regression guard.
- 126 is READY.
- 127/128 are PARKED until dependencies close.
- 119 is READY.
- 121 is BLOCKED_USER.
- 114 is umbrella/PARKED and not a direct fire target.
- A slot next and B slot next are explicit.

## related files

- `doc/103-publish-notice-cron-health-check.md`
- `doc/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`
- `doc/118-pub004-red-reason-decision-pack.md`
- `doc/123-pub004-auto-publish-readiness-and-regression-guard.md`
- `doc/PUB-002-B-missing-primary-source-publish-blocker-reduction.md`
- `doc/PUB-002-C-subtype-unresolved-publish-blocker-reduction.md`
- `doc/PUB-002-D-long-body-draft-compression-or-exclusion-policy.md`
- `doc/PUB-005-x-post-gate.md`
- `doc/119-x-post-eligibility-evaluator.md`
- `doc/120-x-post-autopost-queue-and-ledger.md`
- `doc/121-x-post-live-helper-one-shot-smoke.md`
- `doc/122-x-post-controlled-autopost-rollout.md`
- `doc/125-adsense-manual-ad-unit-embed.md`
- `doc/126-sns-topic-fire-intake-dry-run.md`
- `doc/127-sns-topic-source-recheck-and-draft-builder.md`
- `doc/128-sns-topic-auto-publish-through-pub004.md`
- `doc/HALLUC-LANE-002-llm-based-fact-check-augmentation.md`
