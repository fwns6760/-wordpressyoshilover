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
- `IN_FLIGHT`: currently running in Claude/Codex
- `REVIEW_NEEDED`: implementation returned and needs verification
- `BLOCKED_USER`: explicit user judgment or user-side operation required
- `BLOCKED_EXTERNAL`: external system/precondition required
- `CLOSED`: done and accepted
- `PARKED`: intentionally deferred

## ticket folder policy(2026-04-26 PM 第 2 次 simplification)

```
doc/
├── active/
│   ├── now/    P0 = 今 fire 中 / orchestration 必須(102 board / 105 ramp)
│   ├── next/   P1 = 次着手(123 readiness / 124 cleanup apply 等)
│   └── later/  P1.5+ = 後で(125 AdSense / 128 SNS / reference contracts)
└── archived/YYYY-MM/  CLOSED + BLOCKED_USER + PARKED 全部統合
```

- **doc/ root は空(.md ファイルなし)**。102 board 自身も `doc/active/now/` に配置
- IN_FLIGHT / 高優先 → `doc/active/now/`
- READY 次着手 → `doc/active/next/`
- READY 後回し or reference → `doc/active/later/`
- CLOSED / BLOCKED_USER / PARKED → `doc/archived/YYYY-MM/`(status 詳細は 102 board row)
- status 変更時 doc_path も同 commit で更新
- `git add -A` 禁止、明示 path stage

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
- **doc_path**: `doc/102-ticket-index-and-priority-board.md`
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
- **doc_path**: `doc/archived/2026-04/103-publish-notice-cron-health-check.md`
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
- **doc_path**: `-(board row only)`
- **acceptance**: Hochi source wins, one lineup per `game_id`, non-Hochi lineup deferred/refused, prefix misuse detected
- **repo_state**: pushed
- **commit_state**: `78f965d`
- **next_prompt_path**: -
- **last_commit**: `78f965d` PUB-002-E lineup-source-priority-and-duplicate-suppression

### 105 all-eligible-draft-backlog-publish-ramp

- **alias**: PUB-004-D
- **priority**: P0
- **status**: **IN_FLIGHT**(2026-04-26 PM 累計 38 件 publish、daily cap 残 62、autonomous 継続)
- **owner**: Claude Code(orchestration)
- **lane**: Claude
- **ready_for**: 24h 内追加 invocation 可、翌 JST 0:00 reset 後 backlog 残 drain
- **next_action**: 1) burst 観察 + 24h 内追加 publish 2) 翌日 daily cap reset 後再 ramp 3) 124-A live cleanup apply
- **blocked_by**: none
- **user_action_required**: **NO**(autonomous lock、142 freshness 降格 + 145 mapping fix 適用済)
- **cap**: max_burst default **20** / hard cap **30** / daily **100**(JST 0:00 reset 既設、137 sent-only count)
- **write_scope**: PUB-004-B `--live --max-burst 20 --daily-cap-allow` autonomous fire
- **doc_path**: `doc/active/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`
- **gates_applied**: 130(hard_stop)/ 135(freshness audit、142 で降格)/ 136(lineup_dup)/ 137(cap sent only)/ 141(cleanup chain)/ 142(freshness REPAIRABLE)/ 145(freshness no-op mapping)
- **burst_chain_2026-04-26**:
  - **burst 1**(10:23 AM 旧 spec): 20 sent(63531/63523/63515/63510/63509/63505/63497/63495/63493/63487/63483/63480/63479/63466/63464/63463/63429/63398/63393/63383)= 全 stale だった事故、135 で gate 化
  - **burst 3**(11:36 PM 137 後): 1 sent(63321 farm)
  - **burst 6**(12:01 AM 142+145 後): 17 sent(63282/63276/63272/63265/63263/63249/63247/63243/63238/63236/63234/63230/63226/63222/63211/63209/63205)
  - 累計: **38 sent**
- **commit_state**: orchestration ticket、code commit は 130/135/136/137/141/142/145 で個別反映
- **next_prompt_path**: -
- **last_commit**: `5b01662` 145 freshness flags no-op cleanup mapping

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
- **doc_path**: `-(board row only)`
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
- **doc_path**: `-(board row only)`
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
- **user_action_required**: none(124-A は autonomous fire 候補)
- **write_scope**: src/published_site_component_audit.py + tools + tests(read-only audit)
- **doc_path**: `doc/archived/2026-04/108-existing-published-site-component-cleanup-audit.md`
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
- **doc_path**: `doc/archived/2026-04/109-missing-primary-source-blocker-reduction.md`
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
- **doc_path**: `doc/archived/2026-04/110-subtype-unresolved-blocker-reduction.md`
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
- **doc_path**: `doc/archived/2026-04/111-long-body-compression-or-exclusion.md`
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
- **doc_path**: `doc/archived/2026-04/112-title-prefix-and-lineup-misclassification-fixtures.md`
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
- **doc_path**: `-(board row only)`
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
- **doc_path**: `doc/blocked/PUB-005-x-post-gate.md`
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
- **doc_path**: `-(board row only)`
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
- **doc_path**: `-(board row only)`
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
- **doc_path**: `doc/archived/2026-04/117-adsense-ad-unlock-policy-and-css-toggle.md`
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
- **doc_path**: `doc/archived/2026-04/118-pub004-red-reason-decision-pack.md`
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
- **doc_path**: `doc/archived/2026-04/119-x-post-eligibility-evaluator.md`
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
- **doc_path**: `doc/blocked/120-x-post-autopost-queue-and-ledger.md`
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
- **doc_path**: `doc/blocked/121-x-post-live-helper-one-shot-smoke.md`
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
- **doc_path**: `doc/blocked/122-x-post-controlled-autopost-rollout.md`
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
- **doc_path**: `doc/active/123-pub004-auto-publish-readiness-and-regression-guard.md`
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
- **doc_path**: `doc/active/124-published-cleanup-apply-runner.md`
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
- **doc_path**: `doc/active/125-adsense-manual-ad-unit-embed.md`
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
- **doc_path**: `doc/archived/2026-04/126-sns-topic-fire-intake-dry-run.md`
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
- **next_action**: 128(SNS topic auto-publish through PUB-004 gate)で draft → publish 経路に接続。130 close 済みのため、123 readiness guard + 105 ramp stability を見て起票
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/sns_topic_source_recheck.py`, `src/tools/run_sns_topic_source_recheck.py`, `tests/test_sns_topic_source_recheck.py`
- **doc_path**: `doc/archived/2026-04/127-sns-topic-source-recheck-and-draft-builder.md`
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
- **next_action**: wait for 123 readiness re-run + 105 ramp stabilization, then publish source-rechecked drafts through PUB-004 gate
- **blocked_by**: 123 readiness re-run + 105 ramp stabilization
- **user_action_required**: none per article once 127/128 automation is activated; no raw SNS direct publish
- **write_scope**: `src/sns_topic_publish_bridge.py`, `src/tools/run_sns_topic_publish_bridge.py`, `tests/test_sns_topic_publish_bridge.py`
- **doc_path**: `doc/active/128-sns-topic-auto-publish-through-pub004.md`
- **acceptance**: 127 source-rechecked drafts only, PUB-004 evaluator mandatory, Red refused, dry-run would_publish visible, live respects PUB-004 caps/history/backup
- **repo_state**: doc exists
- **commit_state**: pending SNS topic sync
- **next_prompt_path**: create after 123 readiness re-run + 105 ramp stabilization
- **last_commit**: -
- **parent**: 127 / PUB-004

### 130 pub004-hard-stop-vs-repairable-before-publish

- **alias**: -
- **priority**: **P0**
- **status**: **CLOSED**(impl 着地 `867d90f`、5 点追認全 pass、105 第 1 burst 20 件 sent で実証)
- **owner**: Codex A 完了
- **lane**: A
- **ready_for**: none
- **next_action**: 105 残 40 件 publishable で次 burst、131 mail layering で完成
- **blocked_by**: none
- **user_action_required**: none
- **spec_doc**: `doc/130-pub004-hard-stop-vs-repairable-before-publish.md`
- **write_scope**: ✓ src/guarded_publish_evaluator.py + src/guarded_publish_runner.py + src/tools/run_guarded_publish.py + 2 tests
- **doc_path**: `doc/archived/2026-04/130-pub004-hard-stop-vs-repairable-before-publish.md`
- **acceptance**: ✓ 3 分類(hard_stop / repairable / clean)/ publishable=NOT hard_stop / 公開前 cleanup → verify(prose>=100 / source URL残存 / title subject残存)→ publish / cleanup 失敗 hold(全体 abort なし)/ cap 20/30/100 / CLI help "max 3" 文言消滅 / 既存 tests pass
- **5_point_audit**: ✓ git log + git status clean + grep + pytest collect 1238 + pytest pass 1238/0 fail
- **live_validation**: 105 burst_1 で 20 件 sent / 40 hard_stop hold / 40 cap skip / postcheck 2 round
- **repo_state**: pushed
- **commit_state**: **`867d90f`**
- **next_prompt_path**: -
- **last_commit**: `867d90f` 130 PUB-004 hard_stop / repairable_before_publish / publish_clean
- **parent**: 105 / PUB-004-A / PUB-004-B / PUB-002-A

### 131 publish-notice-burst-summary-and-alerts

- **alias**: -
- **priority**: **P0.5**
- **status**: **IN_FLIGHT**(A lane 実装進行中 `b5fmteg53`)
- **owner**: Claude Code(設計)/ Codex A(実装中)
- **lane**: A
- **ready_for**: none
- **next_action**: per-post 通常通知を suppress しない前提で、10 本ごと summary + Hard Stop / publish 失敗 / postcheck 失敗 / X 発火 alert を layering 実装して review へ進める
- **blocked_by**: none
- **user_action_required**: none
- **spec_doc**: `doc/131-publish-notice-burst-summary-and-alerts.md`(新 spec、旧 file `131-publish-notice-batch-suppress.md` は本 file が supersede)
- **policy_lock**: publish-notice mail を **suppress しない**。layer 5(同 post_id 30 分内重複)のみ抑止
- **write_scope**: src/publish_notice_email_sender.py 改修 + src/tools/run_publish_notice_email_dry_run.py 改修 + tests
- **doc_path**: `doc/archived/2026-04/131-publish-notice-burst-summary-and-alerts.md`
- **acceptance**: per-post 通常通知 維持 / 10 本ごと batch summary / Hard Stop / publish 失敗 / postcheck 失敗 / X 発火 alert / duplicate のみ suppress / mock SMTP test
- **repo_state**: 新 spec doc pushed `73bbdf0`、implementation in flight
- **commit_state**: A `b5fmteg53` 進行中
- **next_prompt_path**: `/tmp/codex_131_impl_prompt.txt`
- **last_commit**: -
- **parent**: 095-D / 088 / 130

### 132 test_x_post_eligibility_evaluator-2-fail-baseline-restore

- **alias**: -
- **priority**: P0(narrow)
- **status**: **CLOSED**(`147507c`、test 側を src constant に整合、approach A 採用)
- **owner**: Codex B 完了
- **lane**: B
- **ready_for**: none
- **next_action**: contract drift 確認済(speculative_title が wp_gate_yellow_* 維持 = OK、verified)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: tests/test_x_post_eligibility_evaluator.py のみ
- **doc_path**: `-(board row only)`
- **acceptance**: ✓ 2 fail → 8/8 pass、src 触らず、side effect なし
- **repo_state**: pushed
- **commit_state**: **`147507c`**
- **next_prompt_path**: -
- **last_commit**: `147507c` 132 test_x_post_eligibility 2 fail fix (baseline restore)
- **incident_origin**: 119 commit `0253b2a` accept 時、私(Claude)が pytest 通過確認を怠り 2 fail を baseline に持ち込んだ。この incident をきっかけに「accept 5 点追認」+「全 prompt に baseline contract」を永続 lock(memory: feedback_no_degradation_role_assignment.md)
- **parent**: 119

### 133 sns-topic-source-recheck-draft-id-schema-fix

- **alias**: -
- **priority**: P1(narrow)
- **status**: **CLOSED**(`06a1315`、`mock_draft_id` deterministic + top-level `draft_ids` 配列追加)
- **owner**: Codex B 完了
- **lane**: B
- **ready_for**: none
- **next_action**: 128 SNS topic auto-publish 実装時に draft_id を実 WP draft 連携で利用
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: src/sns_topic_source_recheck.py + tests/test_sns_topic_source_recheck.py
- **doc_path**: `-(board row only)`
- **acceptance**: ✓ DraftProposal に mock_draft_id / 全 proposal に top-level draft_ids list / 5 new tests pass / 既存 10 tests pass / suite 1238 維持
- **repo_state**: pushed
- **commit_state**: **`06a1315`**
- **next_prompt_path**: -
- **last_commit**: `06a1315` 133 127 draft_ids JSON output schema fix
- **mock_draft_id_format**: `mock_draft_<sha256_first_16hex>`(deterministic from topic_key)
- **parent**: 127

### 134 doc-ticket-archive-and-folder-policy

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(`35fb67c`、113 file reorg = M:1 + R:107 + A:5、doc/ root 9 files only、folder policy 永続 lock memory 化)
- **owner**: Codex C 完了
- **lane**: C
- **ready_for**: none
- **next_action**: 全 Codex 便で folder mv contract 遵守(永続 rule)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: 113 doc files reorg + doc/102 doc_path fields
- **doc_path**: `doc/archived/2026-04/134-doc-ticket-archive-and-folder-policy.md`(本 commit 後 Claude が mv)
- **acceptance**: ✓ active/review/blocked/archived/2026-04 folder 作成、doc/ root = 102 + PUB-* 9 件のみ、102 board doc_path field 全反映
- **repo_state**: pushed
- **commit_state**: **`35fb67c`**
- **next_prompt_path**: -
- **last_commit**: `35fb67c` 134 doc folder reorg

### 135 pub004-breaking-news-freshness-gate

- **alias**: -
- **priority**: **P0**(critical safety、105 ramp halt blocker)
- **status**: **READY**(A 即 fire、user 指定 134 はリナンバーで 135、user 指定 134 は doc reorg で `35fb67c` 使用済)
- **owner**: Claude Code(設計)/ Codex A(実装)
- **lane**: A
- **ready_for**: A 即 fire
- **next_action**: A slot で 135 implementation fire(evaluator に subtype 別 freshness threshold + 3 新 hard_stop flag + content_date / freshness_age_hours 出力)
- **blocked_by**: none
- **user_action_required**: none
- **incident**: 2026-04-26 10:23 PM 105 第 1 burst で **4/24 created の draft が 4/26 新着扱いで publish された**疑い → 速報掲示板 brand 損傷 risk → 第 2 burst halt + freshness gate 必須化
- **policy**:
  - lineup/pregame/probable_starter: 6h 超 hold(`expired_lineup_or_pregame`)
  - postgame/game_result: 24h 超 hold(`expired_game_context`)
  - roster/injury/registration/recovery: 24h 超 hold(既 `injury_death` も維持)
  - comment/speech/program/off_field/farm_feature: 48h 超 hold(`stale_for_breaking_board`)
  - default: 24h 超 hold(`stale_for_breaking_board`)
- **content_date 算出**: source date 優先 → 本文内日付表現 → created_at(modified は **使わない**)
- **spec_doc**: `doc/active/135-pub004-breaking-news-freshness-gate.md`
- **write_scope**: `src/guarded_publish_evaluator.py` + `tests/test_guarded_publish_evaluator.py` + 必要なら `src/pre_publish_fact_check/extractor.py`
- **doc_path**: `doc/active/135-pub004-breaking-news-freshness-gate.md`
- **acceptance**: 3 新 hard_stop flag / freshness 出力 4 field / summary 3 count / 既存 evaluator/runner tests pass / 新 tests 追加 / suite 1248 baseline 維持(0 failed)
- **repo_state**: spec doc 配置済
- **commit_state**: pending impl
- **next_prompt_path**: `/tmp/codex_135_freshness_gate_prompt.txt`
- **last_commit**: -
- **parent**: 130 / 105

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

Current inventory(2026-04-26 PM sync、3 lane fire 中):

| lane | 状態 | task / ticket |
|---|---|---|
| A | IN_FLIGHT | 131 publish-notice burst summary(`b5fmteg53`)|
| B | IN_FLIGHT | 130 read-only review(`bmczd8g41`)|
| C | refire 待ち | DOC-SYNC-15(117 close + 130/132/133/105 row 包括 board update)|
| Claude 直 | 残務 | 125 AdSense slot 実装、105 残 40 件 publishable 次 burst、123 readiness guard re-run、124-A cleanup live apply |

**Closed today**(2026-04-26、commit hash 順):
- 119 X-post eligibility evaluator(`0253b2a`)
- 113 HALLUC-LANE-002 Gemini Flash adapter(`269e1f4`、live は PARKED = user-go 境界)
- 126 SNS topic intake(`5bfe892` + B review OK 10/10)
- 127 SNS source recheck(`2669faa` + B review 11/12 OK + 1 NG → 133 で fix)
- 130 PUB-004 3 分類 + 公開前 cleanup chain(`867d90f` + 5 点追認 全 pass + 105 burst で実証)
- 132 test_x_post_eligibility baseline restore(`147507c`)
- 133 127 draft_id schema fix(`06a1315`)
- 117 AdSense unlock policy(`0555733` 主作業 + user OK で close、A/B/C tuning は将来別 ticket)
- 108 / 109 / 110 / 111 / 112(commit hashes 各 row 参照、本日以前 close)
- 105 第 1 burst(20 件 sent、post_ids は 105 row 参照)

**push 順**: `0253b2a → 5bfe892 → 269e1f4 → 72a3ccd → 338f3a0 → 2669faa → 73bbdf0 → 147507c → 867d90f → 06a1315`(10 commit、6am 以降)+ 本 board commit DOC-SYNC-15 予定

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

- **A slot next**: 131 publish-notice burst summary は **IN_FLIGHT**(`b5fmteg53`)。着地後は 123(readiness/regression guard の read-only confirm)。
- **B slot next**: 130 read-only review は **IN_FLIGHT**(`bmczd8g41`)。新規 narrow B ticket 補充までは待機、128 prep は 123 readiness re-run + 105 ramp stability 後に扱う。
- **Claude 直**: 125 AdSense slot 実装(`.yoshi-ad--*` wrapper を `src/yoshilover-063-frontend.php` + `src/custom.css` に追加、ad unit ID 差し替えのみ user op)、105 残 40 件 publishable 次 burst、123 readiness guard re-run、124-A cleanup live apply。
- **Live 105 ramp**: 第 1 burst 20 件 sent 済み。次は visual/mail check で異常なしを見て、残 40 件 publishable から第 2 burst 20 件を fire。
- **PUB-004-C auto-publish cron**: 105 第 2 burst まで安全に通った後に追加検討。
- **SNS topic auto-publish path**: 126(`5bfe892`)→ 127(`2669faa`)→ 133(`06a1315`) まで close。128 は 123 readiness re-run + 105 ramp stability 後。raw SNS から直接 publish しない。
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
102 board の PM comprehensive sync をCodex側で反映しました。

修正内容:
- 117 を CLOSED で固定(`0555733` 主作業完了、A/B/C tuning は将来別 ticket)
- 130 を CLOSED へ更新(`867d90f`、5 点追認 pass、105 burst_1 20 件 sent で実証)
- 132 / 133 row を追加し、それぞれ CLOSED で記録(`147507c` / `06a1315`)
- 105 を IN_FLIGHT へ更新(burst_1 20 件 sent、daily cap 残 80、post_ids 列挙)
- lane inventory を PM 状態へ更新(A=131 in flight / B=130 review / C=DOC-SYNC-15 refire / Claude 直 4 件)
- closed today list と 6am→PM 10 commit log を追記
- 131 / 128 / next actions / verification 内の古い「130 land 後」「user判断待ち」前提を除去

次の実行:
- A slot next: 131 in flight → 123 read-only confirm
- B slot next: 130 review in flight、128 prep は 123 + 105 安定後
- Claude direct: 125 / 105 next burst / 123 re-run / 124-A live cleanup
- 121 は one-time X live unlock 後のみ
- 122 は 121 smoke 成功後のみ

注意:
doc/102 のみ変更。
コード変更なし。
publish実行なし。
mail実送信なし。
env/secret操作なし。
git pushなし。
git add -A禁止。
```

## verification checklist

- `git diff -- doc/102-ticket-index-and-priority-board.md`
- 104 is only represented as `CLOSED`; no old "104 wait" next-action remains.
- 105 is `IN_FLIGHT` with burst_1 sent 20 and daily cap 80 remaining.
- 108-133 are present.
- 117 is `CLOSED` and future tuning is separated.
- 123 is READY for no-auto-publish readiness/regression guard.
- 126/127/130/132/133 are `CLOSED`; 128 remains `PARKED`.
- 131 is `IN_FLIGHT`.
- 121 is BLOCKED_USER.
- 114 is umbrella/PARKED and not a direct fire target.
- A slot next and B slot next are explicit.

## related files

- `doc/103-publish-notice-cron-health-check.md`
- `doc/active/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`
- `doc/118-pub004-red-reason-decision-pack.md`
- `doc/123-pub004-auto-publish-readiness-and-regression-guard.md`
- `doc/archived/2026-04/PUB-002-B-missing-primary-source-publish-blocker-reduction.md`
- `doc/archived/2026-04/PUB-002-C-subtype-unresolved-publish-blocker-reduction.md`
- `doc/archived/2026-04/PUB-002-D-long-body-draft-compression-or-exclusion-policy.md`
- `doc/blocked/PUB-005-x-post-gate.md`
- `doc/119-x-post-eligibility-evaluator.md`
- `doc/120-x-post-autopost-queue-and-ledger.md`
- `doc/121-x-post-live-helper-one-shot-smoke.md`
- `doc/122-x-post-controlled-autopost-rollout.md`
- `doc/125-adsense-manual-ad-unit-embed.md`
- `doc/126-sns-topic-fire-intake-dry-run.md`
- `doc/127-sns-topic-source-recheck-and-draft-builder.md`
- `doc/128-sns-topic-auto-publish-through-pub004.md`
- `doc/HALLUC-LANE-002-llm-based-fact-check-augmentation.md`
