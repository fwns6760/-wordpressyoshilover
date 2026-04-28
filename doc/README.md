# 102 ticket index and priority board

## meta

- owner: Claude Code
- type: execution queue / Codex A-B dispatch board
- status: READY
- created: 2026-04-26
- updated: 2026-04-28
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

Current publish-policy reference:

- `doc/active/154-publish-policy-2026-04-26-PM.md` = current publish-policy
- `doc/done/2026-04/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md` = superseded archive

## numbering policy

- Continue the existing numeric ticket sequence: `102`, `103`, `104`, ...
- Do not create a new `YOSHI-001` style sequence.
- Keep old names such as `PUB-004-D`, `SPEECH-001`, and `PUB-005-A2` as aliases.
- Do not rename existing ticket docs.
- New execution tickets should use `<number>-<topic>.md`.
- Reserve the next number in `doc/README.md` before handing work to Claude / Codex / Codex-M.
- `1 number = 1 scope`; do not mix separate purposes under one number.
- Multiple commits are allowed under one number when they belong to the same scope, such as spec / impl / doc sync.
- Commit message default: `<number>: <summary>`.
- If a historical number conflict is found later, record the cleanup in the next doc-only board sync instead of silently reusing the number.

## status definitions

- `READY`: can be fired or executed now within its constraints
- `IN_FLIGHT`: currently running in Claude/Codex
- `REVIEW_NEEDED`: implementation returned and needs verification
- `READY_FOR_AUTH_EXECUTOR`: implementation and runbook are ready; an authenticated live executor must perform the remaining mutation step
- `BLOCKED_USER`: explicit user judgment or user-side operation required
- `BLOCKED_EXTERNAL`: external system/precondition required
- `CLOSED`: done and accepted
- `PARKED`: intentionally deferred

## ticket folder policy(2026-04-26 PM 第 5 次 final、PUB-* runbook も status 別へ、root = 102 のみ)

```
doc/
├── README.md  ← board 本体(root 唯一)
├── active/    READY / IN_FLIGHT / REVIEW_NEEDED(154 publish-policy 含む)
├── waiting/   READY_FOR_AUTH_EXECUTOR / BLOCKED_USER / BLOCKED_EXTERNAL / PARKED(PUB-005 含む)
└── done/YYYY-MM/  CLOSED(PUB-004-guarded 含む)
```

- doc/ root = **102 board のみ**(.md 1 file)
- READY / IN_FLIGHT / REVIEW_NEEDED → `doc/active/`(154 publish-policy 等 current runbook も active なら ここ)
- READY_FOR_AUTH_EXECUTOR / BLOCKED_USER / BLOCKED_EXTERNAL / PARKED → `doc/waiting/`
- CLOSED → `doc/done/YYYY-MM/`
- **優先順位はフォルダではなく、本 102 board の `priority` / `next_action` で判別**
- status 変更時 doc_path も同 commit で更新
- `git add -A` 禁止、明示 path stage

## lane definitions

- `A`: Codex A lane, ops / mail / cron / publish runner / WP REST / backup / history / queue / doc commit work
- `B`: Codex B lane, evaluator / validator / article quality / duplicate suppression / source / subtype / tests / audit work
- `Codex-M`: board hygiene / status reconciliation / numbering / prompt-prep lane when Claude is unavailable or needs narrow doc work
- `either`: either Codex lane can take it after write-scope check
- `Claude`: Claude orchestration or read-only operation
- `User`: user-side operation or final judgment
- `Front-Claude`: front/plugin lane outside backend ownership

## authenticated executor boundary

- Codex owns repo implementation, tests, Docker / Cloud Build config changes, deploy runbooks, and read-only verification.
- Live GCP mutation is executed by an authenticated executor: Claude shell, user shell, or a future dedicated deploy executor.
- Live mutation includes Cloud Build submit, Cloud Run Job create/update, Scheduler create/update, IAM changes, Secret Manager changes, and live env changes.
- When user go is already present and only the authenticated shell is missing, use `READY_FOR_AUTH_EXECUTOR` instead of treating Codex auth failure as ticket failure.

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
- **write_scope**: `doc/README.md`
- **doc_path**: `doc/README.md`
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
- **doc_path**: `doc/done/2026-04/103-publish-notice-cron-health-check.md`
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
- **status**: **IN_FLIGHT**(2026-04-26 累計 **66 件 publish**、daily cap 残 34、pool 枯渇で本日実質完了)
- **owner**: Claude Code(orchestration)
- **lane**: Claude
- **ready_for**: 翌 JST 0:00 reset 後 RSS fetcher 新着 + 残 cleanup_failed retry
- **next_action**: 1) 翌日 daily cap reset 後再 ramp 2) 124-A live cleanup apply 3) 残 cleanup_failed の cleanup chain 改善
- **blocked_by**: none(pool 枯渇のみ、技術的 blocker なし)
- **user_action_required**: **NO**(autonomous lock、142 freshness 降格 + 145 mapping fix 適用済)
- **cap**: max_burst default **20** / hard cap **30** / daily **100**(JST 0:00 reset 既設、137 sent-only count)
- **write_scope**: PUB-004-B `--live --max-burst 20 --daily-cap-allow` autonomous fire
- **doc_path**: `doc/active/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`
- **gates_applied**: 130(hard_stop)/ 135(freshness audit、142 で降格)/ 136(lineup_dup)/ 137(cap sent only)/ 141(cleanup chain)/ 142(freshness REPAIRABLE)/ 145(freshness no-op mapping)
- **burst_chain_2026-04-26**:
  - **burst 1**(10:23 AM 旧 spec): 20 sent(63531-63383 列、全 stale 事故 → 135 gate 化)
  - **burst 3**(11:36 PM 137 後): 1 sent(63321 farm)
  - **burst 6**(12:01 AM 142+145 後): 17 sent(63282-63205 列)
  - **burst 7**(12:10 AM): 4 sent(63199/63193/63153/63151)
  - **burst 8**(12:15 AM history clear 後): 18 sent(63358-63284 列)
  - **burst 9**(12:20 AM): 6 sent(63149/63145/63133/63125/63107/63105)
  - **burst 10**(12:25 AM): 0 sent(残 11 件 cleanup_failed = pool 枯渇)
  - **累計: 66 sent**(burst1 stale 20 含む)
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
- **doc_path**: `doc/done/2026-04/108-existing-published-site-component-cleanup-audit.md`
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
- **doc_path**: `doc/done/2026-04/109-missing-primary-source-blocker-reduction.md`
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
- **doc_path**: `doc/done/2026-04/110-subtype-unresolved-blocker-reduction.md`
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
- **doc_path**: `doc/done/2026-04/111-long-body-compression-or-exclusion.md`
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
- **doc_path**: `doc/done/2026-04/112-title-prefix-and-lineup-misclassification-fixtures.md`
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
- **doc_path**: `doc/waiting/PUB-005-x-post-gate.md`
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
- **doc_path**: `doc/done/2026-04/117-adsense-ad-unlock-policy-and-css-toggle.md`
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
- **doc_path**: `doc/done/2026-04/118-pub004-red-reason-decision-pack.md`
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
- **doc_path**: `doc/done/2026-04/119-x-post-eligibility-evaluator.md`
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
- **doc_path**: `doc/waiting/120-x-post-autopost-queue-and-ledger.md`
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
- **doc_path**: `doc/waiting/121-x-post-live-helper-one-shot-smoke.md`
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
- **doc_path**: `doc/waiting/122-x-post-controlled-autopost-rollout.md`
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
- **doc_path**: `doc/done/2026-04/125-adsense-manual-ad-unit-embed.md`
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
- **doc_path**: `doc/done/2026-04/126-sns-topic-fire-intake-dry-run.md`
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
- **doc_path**: `doc/done/2026-04/127-sns-topic-source-recheck-and-draft-builder.md`
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
- **next_action**: wait for **180 SNS lane separation 完了** + 123 readiness re-run + 105 ramp stabilization, then publish source-rechecked drafts through PUB-004 gate
- **blocked_by**: **180 SNS lane separation 完了** + 123 readiness re-run + 105 ramp stabilization
- **user_action_required**: none per article once 127/128 automation is activated; no raw SNS direct publish
- **write_scope**: `src/sns_topic_publish_bridge.py`, `src/tools/run_sns_topic_publish_bridge.py`, `tests/test_sns_topic_publish_bridge.py`
- **doc_path**: `doc/waiting/128-sns-topic-auto-publish-through-pub004.md`
- **acceptance**: 127 source-rechecked drafts only, PUB-004 evaluator mandatory, Red refused, dry-run would_publish visible, live respects PUB-004 caps/history/backup
- **repo_state**: doc exists
- **commit_state**: pending SNS topic sync
- **next_prompt_path**: create after 123 readiness re-run + 105 ramp stabilization
- **last_commit**: -
- **parent**: 127 / PUB-004

### 180 sns-topic-intake-to-publish-lane-separation

- **alias**: -
- **priority**: **P0.5**
- **status**: **READY**(doc-only 整理、即着手可)
- **owner**: Claude Code(設計 / 起票)/ Codex B(必要時実装、本 ticket は doc-only)
- **lane**: B
- **ready_for**: doc-only 着手
- **next_action**: SNS 入口 lane(126/127/128)と X 出口 lane(PUB-005 / 147-175)の境界を明文化、判定 5 種 / reject 条件 / SNS 由来記事の X 自動投稿境界を固定
- **blocked_by**: none
- **user_action_required**: none(doc-only、code 変更なし)
- **write_scope**: `doc/active/180-sns-topic-intake-to-publish-lane-separation.md` + `doc/README.md`(本セクション)+ `doc/active/assignments.md` + `doc/waiting/128-...md`(blocked_by 追記)+ `doc/waiting/PUB-005-x-post-gate.md`(SNS 由来記事の X 自動投稿境界 追記)
- **doc_path**: `doc/active/180-sns-topic-intake-to-publish-lane-separation.md`
- **acceptance**: 180 doc 作成 / README 180 row / assignments 180 row / 128 blocked_by に 180 / PUB-005 に SNS 由来記事の X 自動投稿境界記述 / code/WP/X/mail/env 一切触らず
- **repo_state**: doc 配置済
- **commit_state**: doc-only commit 予定
- **next_prompt_path**: -
- **parent**: 126 / 127 / 128 / PUB-004 / PUB-005

### 183 publish-gate-aggressive-relax

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: none
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/guarded_publish_runner.py`, `src/guarded_publish_evaluator.py`, `tests/test_guarded_publish_runner.py`, `tests/test_guarded_publish_evaluator.py`
- **doc_path**: `doc/done/2026-04/183-publish-gate-aggressive-relax.md`
- **acceptance**: ✓ post-cleanup verify 3 種 warning_only 化 / env strict 復元可 / hard_stop 2 件 repairable 降格 / full pytest pass
- **repo_state**: pushed
- **commit_state**: `f5b91a3`
- **next_prompt_path**: -
- **last_commit**: `f5b91a3` 183 publish-gate aggressive relax

### 184 ledger-integration-cloud-run

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: none
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/guarded_publish_evaluator.py`, `src/guarded_publish_runner.py`, `src/runner_ledger_integration.py`, `src/tools/run_draft_body_editor_lane.py`, `src/tools/run_guarded_publish.py`, `src/tools/run_publish_notice_email_dry_run.py`, related tests
- **doc_path**: `doc/done/2026-04/184-ledger-integration-cloud-run.md`
- **acceptance**: ✓ 4 runner に Firestore/GCS ledger wire-up / env opt-in / failure tolerant / full pytest pass
- **repo_state**: pushed
- **commit_state**: `59b2438`
- **next_prompt_path**: -
- **last_commit**: `59b2438` 184 ledger integration
- **parent**: 168 / 179 / 177 / 160 / 161

### 185 guarded-publish-entrypoint-exclude-published-today-relax

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**
- **owner**: Codex A
- **lane**: A
- **ready_for**: none
- **next_action**: none
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `bin/guarded_publish_entrypoint.sh`
- **doc_path**: `-(board row only)`
- **acceptance**: ✓ entrypoint の `--exclude-published-today` を一時除去し、same-day publish 済み記事との `game_key` 衝突で draft が silent 除外される経路を止血
- **repo_state**: pushed
- **commit_state**: `1842fb8`
- **next_prompt_path**: -
- **last_commit**: `1842fb8` 185 entrypoint exclude-published-today 一時除去

### 186 scan-limit-pagination-and-history-dedup-narrow

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**
- **owner**: Codex A
- **lane**: A
- **ready_for**: none
- **next_action**: none
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/guarded_publish_evaluator.py`, `src/guarded_publish_runner.py`, `tests/test_guarded_publish_evaluator.py`, `tests/test_guarded_publish_runner.py`
- **doc_path**: `doc/done/2026-04/186-scan-limit-pagination-and-history-dedup-narrow.md`
- **acceptance**: ✓ `max_pool` honor pagination / refused history dedup を 24h window に narrow / tests +7 / pytest 1431→1438
- **repo_state**: pushed
- **commit_state**: `26c6ae2`
- **next_prompt_path**: -
- **last_commit**: `26c6ae2` 186 scan_limit cap 緩和 + history dedup refused 24h narrow
- **parent**: 105 / 145 / guarded-publish history

### 187 publish-notice-scheduler-uri-v1-fix-verification

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(step 1 config verify は `0cc7cc3` で記録済み、step 2-4 は 188 Fix A 適用 + manual trigger success で実質解決)
- **owner**: Codex(A) / Claude
- **lane**: A
- **ready_for**: none
- **next_action**: none(ticket scope close。`2026-04-27 09:15 JST` の自然 tick 観測は別 follow-up)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/active/187-publish-notice-scheduler-uri-v1-fix.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/done/2026-04/187-publish-notice-scheduler-uri-v1-fix.md`
- **acceptance**: ✓ v1 URI / ENABLED / `15 * * * *` verify 記録済み、後続 trigger/execution 確認は 188 IAM fix 適用後 `publish-notice-9rsjt` success で担保
- **repo_state**: pushed
- **commit_state**: `0cc7cc3`
- **next_prompt_path**: -
- **last_commit**: `74ccef6` 188 IAM fix + manual trigger success で 187 実質 close
- **parent**: 161 / 103

### 188 publish-notice-scheduler-iam-fix

- **alias**: -
- **priority**: **P0.5**
- **status**: **CLOSED**(Fix A runbook `74ccef6` 着地、`seo-scheduler-invoker` に invoker 付与済み、manual trigger `publish-notice-9rsjt` で 20 mail 送信成功)
- **owner**: Codex A / User / Claude
- **lane**: A
- **ready_for**: none
- **next_action**: none(ticket scope close。自然 tick 09:15 JST の観測は別 follow-up)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/active/188-publish-notice-scheduler-iam-fix.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/done/2026-04/188-publish-notice-scheduler-iam-fix.md`
- **acceptance**: ✓ YAML/IAM 差分比較 / Fix A-B-C runbook / caller SA 真因説明 / Fix A 実行後 `publish-notice-9rsjt` success
- **repo_state**: pushed
- **commit_state**: `74ccef6`
- **next_prompt_path**: -
- **last_commit**: `74ccef6` 188 publish-notice scheduler IAM 修正 runbook
- **parent**: 161 / 187 / 160

### 189 publish-notice-contextual-manual-x-candidates

- **alias**: -
- **priority**: **P0.5**
- **status**: **CLOSED**
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: none
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/publish_notice_email_sender.py`, `tests/test_publish_notice_email_sender.py`, `doc/done/2026-04/189-publish-notice-contextual-manual-x-candidates.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/done/2026-04/189-publish-notice-contextual-manual-x-candidates.md`
- **acceptance**: ✓ subtype別出力 / notice fan hookなし / 怪我・復帰ワード fan hookなし / inside_voice 条件付き / 280字以内 / URL付き最大3 / `tests/test_publish_notice_email_sender.py` pass
- **repo_state**: pushed
- **commit_state**: `b7a9e1f`
- **next_prompt_path**: -
- **last_commit**: `b7a9e1f` 189 contextual manual X candidates for publish notices
- **parent**: 190 / 191 / 095-D / 131 / PUB-005

### 190 publish-notice-manual-x-candidates-impl

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(2026-04-27 user 認容「ポストも乗るんだよね。公開記事に。」を keep ratify として採用)
- **owner**: Claude / User follow-up
- **lane**: B
- **ready_for**: none
- **next_action**: none; `1ac710b` / `b7a9e1f` landed behavior を keep し、`195` frontend share corner との整合込みで正式 scope を freeze
- **blocked_by**: none
- **user_action_required**: none(keep ratify 済み)
- **write_scope**: `src/publish_notice_email_sender.py`, `tests/test_publish_notice_email_sender.py`, `doc/done/2026-04/190-publish-notice-manual-x-candidates-impl.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/done/2026-04/190-publish-notice-manual-x-candidates-impl.md`
- **acceptance**: `1ac710b` 実装 keep ratify、`9vd48` / `9rsjt` / `pwh4r` 配信実績記録、`195` frontend share corner との整合確認が記録されている
- **repo_state**: local doc update
- **commit_state**: pending ticket 198 close commit
- **next_prompt_path**: -
- **last_commit**: `1ac710b` 188 add manual X candidates to publish notices
- **parent**: 191 / 095-D / 131 / PUB-005

### 191 publish-notice-manual-x-candidates-spec

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(`b6b2b2b` の spec 起点を `1ac710b` / `b7a9e1f` / `195` landed behavior で keep ratify し、正式 scope を freeze)
- **owner**: Claude / User follow-up
- **lane**: B
- **ready_for**: none
- **next_action**: none; subtype × pattern mapping(`lineup / postgame / farm / notice / program / default`)と base 文 only / hashtag user 任意追記の扱いを正式 spec として lock
- **blocked_by**: none
- **user_action_required**: none(spec freeze 済み)
- **write_scope**: `doc/done/2026-04/191-publish-notice-manual-x-candidates-spec.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/done/2026-04/191-publish-notice-manual-x-candidates-spec.md`
- **acceptance**: `188` impl + `189` contextual selector + `195` frontend 整合を前提に、subtype mapping と hashtag 任意運用が lock されている
- **repo_state**: local doc update
- **commit_state**: pending ticket 198 close commit
- **next_prompt_path**: -
- **last_commit**: `b6b2b2b` 188 ticket publish notice manual X candidates
- **parent**: 095-D / 131 / PUB-005

### 194 publish-notice-scheduler-5min

- **alias**: -
- **priority**: P0.5
- **status**: **REVIEW_NEEDED**(`publish-notice-trigger` schedule を `15 * * * *` -> `*/5 * * * *` に変更済み。`2026-04-27 09:40 JST` natural tick execution `publish-notice-6x7f5` も確認済みで、Claude close 待ち)
- **owner**: Codex / Claude follow-up
- **lane**: A
- **ready_for**: Claude close
- **next_action**: ticket doc の verify / rollback 記録を元に close 判定。cadence を戻す場合は doc 記載の rollback を実行
- **blocked_by**: none
- **user_action_required**: none(user request reflected)
- **write_scope**: `doc/active/194-publish-notice-scheduler-5min.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/194-publish-notice-scheduler-5min.md`
- **acceptance**: `publish-notice-trigger` schedule が `*/5 * * * *`、他 scheduler / Cloud Run Job env/image/IAM 不変、自然 tick で新 execution を確認、rollback command 記録済み
- **repo_state**: local doc update
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 161 / 187 / 188 / 189 / 105

### 195 article-footer-manual-x-share-corner

- **alias**: B1
- **priority**: P0.5
- **status**: **REVIEW_NEEDED**(repo 実装は `26fc0ca` で着地済み。ただし live frontend 未反映のため CLOSE 不可)
- **owner**: Codex / Claude follow-up
- **lane**: Front-Claude
- **ready_for**: 197 live deploy handoff + post-deploy review
- **next_action**: repo 側の render / copy / toggle 実装は維持しつつ、`197` の default-off canary deploy と WP 側反映確認を待つ
- **blocked_by**: `197` live deploy handoff
- **user_action_required**: none for repo code review; live reflect は `197`
- **write_scope**: `src/yoshilover-063-frontend.php`, `doc/active/195-article-footer-manual-x-share-corner.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/195-article-footer-manual-x-share-corner.md`
- **acceptance**: single post publish 記事のみ / heading「この記事を X でシェア」/ 3 候補 fixed / copy + intent / permalink + `#巨人 #ジャイアンツ` 含む / option+env toggle / `php -l` pass
- **repo_state**: pushed
- **commit_state**: `26fc0ca`
- **next_prompt_path**: -
- **last_commit**: `26fc0ca` 195 article footer 手動 X 投稿シェアコーナー(B1)
- **parent**: 190 / 191 / 176

### 196 ingestion-realtime-5min-trigger

- **alias**: -
- **priority**: P0.5
- **status**: **REVIEW_NEEDED**(`giants-realtime-trigger` を `*/5 * * * *` で新規作成済み。既存 `giants-*` と同じ `yoshilover-fetcher /run` + `seo-web-runtime@baseballsite.iam.gserviceaccount.com` を使用し、`2026-04-27 09:55 JST` の初回 natural tick で HTTP 200 を確認)
- **owner**: Codex / Claude follow-up
- **lane**: A
- **ready_for**: Claude close
- **next_action**: `doc/active/196-ingestion-realtime-strategy.md` の verify をもとに close 判定。1-2 週間観察後、別 ticket で既存 `giants-*` の削減または cadence 再整理を判断
- **blocked_by**: none
- **user_action_required**: none(user request reflected)
- **write_scope**: `doc/active/196-ingestion-realtime-strategy.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/196-ingestion-realtime-strategy.md`
- **acceptance**: `giants-realtime-trigger` が `*/5 * * * *` / `Asia/Tokyo` / `attemptDeadline=180s` で存在し、既存 `giants-*` と同じ URI/SA を使用、既存 schedule 不変、`yoshilover-fetcher-job` は PAUSED のまま、初回 natural tick HTTP 200 を確認
- **repo_state**: local doc update + live scheduler create
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 042 / 155 / 194

### 197 195-live-deploy-manual-x-share-corner

- **alias**: -
- **priority**: P0.5
- **status**: **READY_FOR_AUTH_EXECUTOR**(195 の repo 実装と runbook は揃っており、残りは authenticated executor による live deploy のみ。repo 既存 artifact は stale のため fresh zip が前提)
- **owner**: Codex / Claude follow-up
- **lane**: Front-Claude
- **ready_for**: authenticated executor shell / WP admin access
- **next_action**: 1) fresh zip / artifact 再生成 2) default-off canary を先置き 3) WP 側反映確認 4) enable 5) rollback 手順の実行可否を同じ authenticated executor で保持
- **blocked_by**: authenticated executor 側の Xserver / WP access
- **user_action_required**: no new policy judgment; live mutation を実行できる authenticated executor が必要
- **write_scope**: `doc/waiting/197-195-live-deploy.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/waiting/197-195-live-deploy.md`
- **acceptance**: deploy route 明記 / fresh zip 前提 / default-off canary / WP 側反映確認 / enable / rollback 手順 / live write 未実行を記録
- **repo_state**: local doc update
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 195 / 176

### 199 publish-notice-rebuild-a9c2814

- **alias**: -
- **priority**: P0.5
- **status**: **REVIEW_NEEDED**(read-only verify で live image が `23853cd`、latest execution が success、Gmail 着信も確認。いっぽう sample mail 本文では `manual_x_post_candidates` block をまだ確認できていない)
- **owner**: Codex / Claude follow-up
- **lane**: A
- **ready_for**: live body / runtime drift review
- **next_action**: 1) `23853cd` live image と repo expectation の差分を read-only で照合 2) sample mail で `manual_x_post_candidates` 不在の理由を切り分け 3) 必要なら narrow follow-up or redeploy ticket を起票
- **blocked_by**: none for read-only review
- **user_action_required**: none for current verification; mutationが必要なら別便で executor handoff
- **write_scope**: `doc/active/199-publish-notice-rebuild-a9c2814.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/199-publish-notice-rebuild-a9c2814.md`
- **acceptance**: live image tag / latest execution / Gmail 着信の read-only 事実を記録し、未確認点(`manual_x_post_candidates`)を review item として残す
- **repo_state**: local doc update
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 188 / 189 / 194

### 200 publish-notice-scanner-subtype-fallback

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(`e78f088`、REST subtype 欠落時の fallback 推論を scanner に追加し、manual X candidate の default 偏りを緩和)
- **owner**: Codex B
- **lane**: B
- **ready_for**: none
- **next_action**: none(scanner fix は着地、既存 flaky は 201 へ分離)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/publish_notice_scanner.py`, `tests/test_publish_notice_scanner.py`
- **doc_path**: `doc/done/2026-04/200-publish-notice-scanner-subtype-fallback.md`
- **acceptance**: REST `article_subtype` / `subtype` 欠落時でも lineup / postgame / farm / notice / program / default の 5+1 分類へ倒せる、scanner 専用 tests 追加、`src/publish_notice_email_sender.py` 不可触
- **repo_state**: committed(local)
- **commit_state**: `e78f088`
- **next_prompt_path**: -
- **last_commit**: `e78f088` 200 publish-notice scanner subtype fallback 推論(REST 欠落時 lineup/postgame/farm/notice/program/default 5+1 分類、X candidates default 偏り解消)
- **parent**: 188 / 189 / 190 / 191 / 199

### 201 readiness-guard-test-time-dependent-flaky

- **alias**: -
- **priority**: P1
- **status**: **READY**(full pytest residual 1 fail を別 ticket 化。scanner 変更とは write scope / failure cause ともに disjoint)
- **owner**: Codex B
- **lane**: B
- **ready_for**: next Codex narrow fix
- **next_action**: `tests/test_guarded_publish_readiness_guard.py::test_human_format_renders_summary` の real-now 依存を fixed `now` 注入または狭い assertion 調整で除去し、full pytest residual fail を解消
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `tests/test_guarded_publish_readiness_guard.py`、必要最小限で `src/tools/run_guarded_publish_readiness_check.py` または `src/guarded_publish_readiness_guard.py`
- **doc_path**: `doc/active/201-readiness-guard-test-time-dependent-flaky.md`
- **acceptance**: `summary: sent=1 refused=1 skipped=0` 前提の human-format test が実行日時に依存せず stable pass、200 scanner fix と scope 分離維持、`src/publish_notice_email_sender.py` 不可触
- **repo_state**: local doc update
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 200 / 123

### 202 gcp-deploy-executor-boundary

- **alias**: -
- **priority**: P0.5
- **status**: **REVIEW_NEEDED**(Codex repo workと authenticated executor の live mutation 境界を doc 化)
- **owner**: Codex-M / Claude
- **lane**: Codex-M
- **ready_for**: next live-mutation ticket adoption
- **next_action**: `READY_FOR_AUTH_EXECUTOR` を live GCP / live WP deploy handoff に適用し、Codex auth fail を generic failure 扱いしない
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/active/202-gcp-deploy-executor-boundary.md`, `doc/active/OPERATING_LOCK.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/202-gcp-deploy-executor-boundary.md`
- **acceptance**: Codexのrepo責務 / authenticated executor責務 / `READY_FOR_AUTH_EXECUTOR` 定義 / secret/env hard stop 維持が明文化されている
- **repo_state**: local doc update
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 155 / 177 / 197 / 199

### 203 ticket-number-reservation-rule

- **alias**: -
- **priority**: P0.5
- **status**: **REVIEW_NEEDED**(ticket 採番の事前予約と `1 number = 1 scope` を明文化)
- **owner**: Codex-M / Claude
- **lane**: Codex-M
- **ready_for**: next ticket fire
- **next_action**: 新規 ticket を fire する前に README へ番号予約し、別用途の番号混在を止める
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/active/203-ticket-number-reservation-rule.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/203-ticket-number-reservation-rule.md`
- **acceptance**: 番号予約 / `1 number = 1 scope` / commit message 基本形 / 衝突発見時の整理ルールが明文化されている
- **repo_state**: local doc update
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 188 / 189 / 192 / 200 / 201

### 204 195-live-state-clarify

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(195 は REVIEW_NEEDED 維持、197 は READY_FOR_AUTH_EXECUTOR へ正規化し、README / assignments の見え方を修正)
- **owner**: Codex-M
- **lane**: Codex-M
- **ready_for**: none
- **next_action**: none
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/README.md`, `doc/active/assignments.md`, `doc/waiting/197-195-live-deploy.md`
- **doc_path**: `-(board row only)`
- **acceptance**: 195 が live 未反映のまま CLOSED 扱いされず、197 の live 手順が fresh zip / canary / verify / enable / rollback まで board に反映されている
- **repo_state**: local doc update
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 195 / 197 / 202

### 205 gcp-runtime-drift-audit

- **alias**: -
- **priority**: P0.5
- **status**: **READY**(GCP 移行後の repo/runtime drift を read-only 監査するための ticket)
- **owner**: Codex A / Claude
- **lane**: A
- **ready_for**: next read-only audit pass
- **next_action**: Cloud Run Job image tag / Scheduler state / WSL cron 残骸 / latest execution / publish-notice mail / GCS history の drift を read-only 監査する
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/active/205-gcp-runtime-drift-audit.md`, read-only `gcloud` / Gmail / local cron evidence, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/205-gcp-runtime-drift-audit.md`
- **acceptance**: audit 対象が列挙され、mutation禁止が明記され、修正・deploy・WP write が別 ticket であることが固定されている
- **repo_state**: local doc update
- **commit_state**: pending ticket commit
- **next_prompt_path**: -
- **last_commit**: -
- **parent**: 155 / 199 / 200 / 202

### 207 publish-notice-send-result-persistence-and-alert

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(`a4c3974`、publish-notice の `queue.jsonl` / send-result summary を GCS に残し、`emit > 0` なのに `sent = 0` の全抑止ケースで alert log を出す repo 実装を追加)
- **owner**: Codex A
- **lane**: A
- **ready_for**: none
- **next_action**: 208 / 199 の read-only verify で live image 反映有無と mail 本文差分を継続確認
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/cloud_run_persistence.py`, `src/publish_notice_email_sender.py`, `src/tools/run_publish_notice_email_dry_run.py`, `tests/test_cloud_run_persistence.py`, `tests/test_publish_notice_email_sender.py`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `-(board row only)`
- **acceptance**: publish-notice の durable artifact に per-post status / reason / subject が残り、`emit > 0` かつ `sent = 0` のとき Cloud Logging で追跡しやすい alert 行が出る。SMTP / Scheduler / WP / X 挙動は変えない
- **repo_state**: committed(local)
- **commit_state**: `a4c3974`
- **next_prompt_path**: -
- **last_commit**: `a4c3974` 207 publish-notice send result GCS 永続化 + emit>0 sent=0 alert log(queue.jsonl persist、reason 内訳付き summary、alert 検出可能化)
- **parent**: 199 / 206

### 208 gcp-lane-result-log-persistence-audit

- **alias**: -
- **priority**: P1.5
- **status**: **REVIEW_NEEDED**(GCP mainline 各 lane の durable evidence を横断し、HIGH / MED / LOW severity と follow-up 候補を整理)
- **owner**: Codex-M / Claude
- **lane**: Codex-M
- **ready_for**: follow-up prioritization
- **next_action**: 207 live verify、draft-body-editor ledger persistence、codex-shadow repair artifact persistence、163 quality monitor GCP migration を board 優先度に反映
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/active/208-gcp-lane-result-log-persistence-audit.md`
- **doc_path**: `doc/active/208-gcp-lane-result-log-persistence-audit.md`
- **acceptance**: lane matrix に current persistence / missing evidence / severity / follow-up 候補が残り、read-only だけで次の persistence 改善 ticket を切れる
- **repo_state**: committed(local)
- **commit_state**: `3fb80d1`
- **next_prompt_path**: -
- **last_commit**: `3fb80d1` 208 GCP lane result log persistence audit(read-only、レーン別 evidence 表 + severity + follow-up 推奨、修正なし)
- **parent**: 155 / 163 / 199 / 206

### 209 source-coverage-and-topic-sensor-audit

- **alias**: -
- **priority**: P0.5
- **status**: **REVIEW_NEEDED**(source coverage / SNS topic sensor の現行入口、primary gap、重複抑止、dry-run lane を整理)
- **owner**: Codex-M / Claude
- **lane**: Codex-M
- **ready_for**: next source-expansion planning
- **next_action**: 210 で primary source expansion / SNS sensor boundary / source_trust drift のどれを先に詰めるかを board 判断する
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/active/209-source-coverage-and-topic-sensor-audit.md`
- **doc_path**: `doc/active/209-source-coverage-and-topic-sensor-audit.md`
- **acceptance**: 現行 source inventory、primary / secondary gap、SNS is signal not fact の境界、既存 duplicate suppression が doc-only で再構成されている
- **repo_state**: committed(local)
- **commit_state**: `7b1bb7d`
- **next_prompt_path**: -
- **last_commit**: `7b1bb7d` 209 source coverage and topic sensor audit
- **parent**: 005 / 014 / 064 / 128 / 180

### 210 primary-source-expansion-plan

- **alias**: -
- **priority**: P0.5
- **status**: **REVIEW_NEEDED**(7 source 候補 + 重複対策 5 項目 + sub-ticket outline を doc-only で整理、実装は別 ticket)
- **owner**: Claude(spec) / Codex(将来実装)
- **lane**: Claude / Codex
- **ready_for**: user 確認後 sub-ticket 起票
- **next_action**: user 確認後 210a source_trust family 拡張から実装を開始するか判断
- **blocked_by**: none
- **user_action_required**: 実装 priority 判断
- **write_scope**: `doc/active/210-primary-source-expansion-plan.md`(本便 spec のみ、実装は別 ticket)
- **doc_path**: `doc/active/210-primary-source-expansion-plan.md`
- **acceptance**: 7 source 候補 + 重複対策 5 項目 + sub-ticket outline が documented
- **repo_state**: pushed
- **commit_state**: `4acda2b`
- **next_prompt_path**: -
- **last_commit**: `4acda2b` 210 primary source expansion plan
- **parent**: 209

### 211 restore-202-203-205-docs-after-207-commit-accident

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(`ad729b4`、207 commit 時に巻き戻された 199 / 202 / 203 / 205 の active doc と board 反映を `210ce41` 基準で復元)
- **owner**: Codex-M
- **lane**: Codex-M
- **ready_for**: none
- **next_action**: none(復元後の board reconcile は 213 で実施)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/README.md`, `doc/active/199-publish-notice-rebuild-a9c2814.md`, `doc/active/202-gcp-deploy-executor-boundary.md`, `doc/active/203-ticket-number-reservation-rule.md`, `doc/active/205-gcp-runtime-drift-audit.md`, `doc/active/assignments.md`, `doc/active/OPERATING_LOCK.md`, `doc/waiting/197-195-live-deploy.md`
- **doc_path**: `-(board row only)`
- **acceptance**: 199 / 202 / 203 / 205 の active doc と README / assignments の整合が復元され、src / tests / live mutation は含まれない
- **repo_state**: committed(local)
- **commit_state**: `ad729b4`
- **next_prompt_path**: -
- **last_commit**: `ad729b4` 211 restore 202/203/205 docs after 207 commit accident
- **parent**: 199 / 202 / 203 / 205 / 207

### 217 wp-publish-all-mode-hotfix

- **alias**: -
- **priority**: P0(緊急 hotfix)
- **status**: REVIEW_NEEDED
- **owner**: Codex(impl)/ Claude(dispatch)
- **lane**: Codex
- **ready_for**: GCP authenticated executor
- **next_action**: GCP 反映(guarded-publish + publish-notice rebuild + Job update b03890c tag)、反映後 63795 再判定
- **blocked_by**: GCP authenticated executor 待ち
- **user_action_required**: deploy 実行(authenticated executor)
- **write_scope**: src/guarded_publish_evaluator.py + src/guarded_publish_runner.py + src/publish_notice_email_sender.py + tests + src/rss_fetcher.py(b36c30c は実質 218、番号衝突)
- **doc_path**: doc/active/217-wp-publish-all-mode-hotfix.md
- **acceptance**: 63795 publishable Yellow / death 系 hard_stop 維持 / pytest 1498 pass
- **repo_state**: pushed
- **commit_state**: `b03890c`(本体 `579401a` + 補完 `b03890c`、番号衝突 `b36c30c` は実質 218)
- **next_prompt_path**: -
- **last_commit**: `b03890c` 217 add death_or_grave_incident to hard-stop set
- **parent**: 183 / 200

### 224 article-body-entity-role-consistency-awkward-rewrite-guard

- **alias**: -
- **priority**: P0.5
- **status**: READY(impl 進行中 `bif6lgn6p`)
- **owner**: Codex B
- **lane**: dev / quality
- **ready_for**: implementation
- **next_action**: detector + safe_rewrite + awkward_role_phrasing flag を Yellow 扱いで evaluator 統合、`bif6lgn6p` 着地後 verify
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/article_entity_role_consistency.py`(新規)+ `src/guarded_publish_evaluator.py` + tests
- **doc_path**: `doc/active/224-article-body-entity-role-consistency-awkward-rewrite-guard.md`
- **acceptance**: 不自然 `人名+肩書き+となって/となり` 検出 + safe rewrite + Yellow flag、既存 hard_stop 不変
- **repo_state**: doc 起票済、impl 進行中
- **commit_state**: `bif6lgn6p` in flight
- **parent**: 217 / 200

### 225 / MKT-008 x-post-candidate-text-quality-hardening

- **alias**: `MKT-008`
- **priority**: P0.5
- **status**: REOPENED(225 本体 `873fcf0` 着地、225-A safety fix 進行中 `bss84x1u1`)
- **owner**: Codex B
- **lane**: marketing / mail body
- **ready_for**: 225-A 完了後 publish-notice rebuild(authenticated executor)
- **next_action**: 225-A safety fix(x_post_ready=false で本文表示抑止)→ rebuild + Job update
- **blocked_by**: none
- **user_action_required**: 225-A 完了後の publish-notice rebuild 判断
- **write_scope**: `src/publish_notice_email_sender.py` + tests
- **doc_path**: `doc/marketing/active/MKT-008-x-post-candidate-text-quality-hardening.md`
- **acceptance**: 225 本体(整形 + sensitive 抑止)+ 225-A(x_post_ready=false 本文非表示)、内部生成 logic 不変
- **repo_state**: 225 本体 push 済、225-A impl 進行中
- **commit_state**: `873fcf0`(本体)、225-A は `bss84x1u1` 着地予定
- **parent**: MKT-001 (219) / 218 / 222 / 225 本体

### 219 publish-notice-marketing-mail-classification

- **alias**: `MKT-001`
- **priority**: P0.5
- **status**: IN_FLIGHT
- **owner**: Codex B / Claude
- **lane**: mail本文・マーケ運用
- **ready_for**: parallel implementation(`bh1vb526h`)
- **next_action**: `MKT-001` の正本を `doc/marketing/README.md` に分離しつつ、publish-notice mail の件名先頭を `【投稿候補】/【公開済】/【要確認】/【警告】/【まとめ】/【緊急】` に分類し、本文先頭metadata / mail class selector と合わせて Gmail filterで仕分けできる形にする
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/publish_notice_email_sender.py`, `tests/test_publish_notice_email_sender.py`
- **doc_path**: `doc/marketing/active/MKT-001-publish-notice-marketing-mail-classification.md`
- **acceptance**: `【投稿候補】/【公開済】/【要確認】/【警告】/【まとめ】/【緊急】` が件名先頭に出る、件名末尾に `| YOSHILOVER` を残す、本文先頭 metadata、Gmail filter 前提の安定 prefix、既存 manual_x_post_candidates 非破壊、tests pass
- **repo_state**: parallel implementation in progress
- **commit_state**: `bh1vb526h`(src/tests parallel lane, no doc commit in that lane yet)
- **next_prompt_path**: `doc/marketing/active/MKT-001-publish-notice-marketing-mail-classification.md`
- **last_commit**: -
- **parent**: 189 / 190 / 191 / 207

### 241 mail-header-reply-to-self-recipient-investigation

- **alias**: 240 follow-up
- **priority**: P0.5
- **status**: **CLOSED**(2026-04-28、image rebuild `25f176b` + smoke v5 + PC/mobile 通知 yes/yes 両方発火確認)
- **owner**: Codex B(impl)/ Claude(dispatch + accept + push + auth executor smoke)
- **lane**: B
- **ready_for**: none
- **next_action**: none(close gate 全 pass、live 反映済)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/mail_delivery_bridge.py`, `tests/test_mail_delivery_bridge.py`, `doc/done/2026-04/241-mail-header-reply-to-self-recipient-investigation.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/done/2026-04/241-mail-header-reply-to-self-recipient-investigation.md`
- **acceptance**: ✓ Reply-To resolved address が recipient と一致する場合 header omit、異なる Reply-To は維持、mail bridge 既存 flow 不変、live env/secret/Scheduler 不変、smoke v5 で実 mail 配信 + PC/mobile 通知両方発火を user 確認
- **repo_state**: pushed
- **commit_state**: `894db98`
- **next_prompt_path**: -
- **last_commit**: `894db98` 241: omit self-recipient reply-to mail header
- **parent**: 240 / 219 / 222

### 242 auto-publish-gate-regression-off-topic-published-and-eligible-held

- **alias**: -
- **priority**: P0.5
- **status**: REVIEW_NEEDED
- **owner**: Codex B / Claude
- **lane**: B
- **ready_for**: Claude review / 242-B and 242-C follow-up split
- **next_action**: 242-A landed as narrow fix; Claude should review the regression coverage, then fire 242-B(entity-role mismatch) and arrange 242-C live verify / handoff
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`
- **acceptance**: incident trace / root cause / 242-A narrow fix summary / 242-B and 242-C boundaries are all documented without touching env, secret, or live publish policy
- **repo_state**: local impl + tests pass
- **commit_state**: pending 242-A commit
- **next_prompt_path**: `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`
- **last_commit**: -
- **parent**: 105 / 154 / 217 / 226

### 242-A narrow-farm-lineup-medical-roster-false-positive-fix

- **alias**: -
- **priority**: P0.5
- **status**: REVIEW_NEEDED
- **owner**: Codex B
- **lane**: B
- **ready_for**: Claude review / authenticated executor dry-run-canary verify
- **next_action**: review `_medical_roster_flag()` narrow subtype branch, then run the pending dry-run/canary diff against recent guarded-publish history
- **blocked_by**: authenticated executor verify not yet run
- **user_action_required**: none
- **write_scope**: `src/guarded_publish_evaluator.py`, `tests/test_guarded_publish_evaluator.py`, `tests/test_guarded_publish_runner.py`, `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`
- **acceptance**: 63841/63845 型 farm or lineup source-missing roster-signal cases no longer escalate to `death_or_grave_incident`, true grave/death/long-recovery cases stay hard-stop, generic non-farm/lineup missing-source escalate path stays unchanged, and the 63844 visibility fixture remains yellow-visible for 242-B
- **repo_state**: local impl + targeted pytest pass
- **commit_state**: pending 242-A commit
- **next_prompt_path**: `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`
- **last_commit**: -
- **parent**: 242

### 242-D farm-result-placeholder-body-publish-blocker

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(2026-04-28、`a224add` landed、最終 narrow boundary/live verify は 242-D2 `25f176b` で完了)
- **owner**: Codex B(impl)/ Claude(dispatch + accept + push + live verify via 242-D2)
- **lane**: B
- **ready_for**: none
- **next_action**: none(63845 type blocker landed、最終 classifier/review alignment と live verify は 242-D2 で完了)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/guarded_publish_evaluator.py`, `tests/test_guarded_publish_evaluator.py`, `doc/done/2026-04/242-D-farm-result-placeholder-body-publish-blocker.md`, `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/done/2026-04/242-D-farm-result-placeholder-body-publish-blocker.md`
- **acceptance**: ✓ 63845 type repeated placeholder body blocker landed / single filler-only tail skip / empty-heading hard-stop / 242-A medical_roster, freshness, lineup_dup, cleanup gates unchanged; final classifier boundary/live verify is captured in 242-D2
- **repo_state**: pushed
- **commit_state**: `a224add`
- **next_prompt_path**: -
- **last_commit**: `a224add` 242-D: farm_result placeholder body publish blocker (63845 type) + 6 fixtures
- **parent**: 242

### 242-D2 farm-result-classifier-review-alignment

- **alias**: -
- **priority**: P0.5
- **status**: **CLOSED**(2026-04-28、image rebuild `25f176b` で live 反映、sample 5 件 verify で 242-A/D/D2 narrow 設計通り動作確認、別軸 DEATH false positive は 242-E で対応)
- **owner**: Codex B(impl)/ Claude(dispatch + accept + push + live verify)
- **lane**: B
- **ready_for**: none
- **next_action**: none(narrow design 動作確認済み、別軸 DEATH false positive は 242-E で対応)
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/guarded_publish_evaluator.py`, `src/guarded_publish_runner.py`, `tests/test_guarded_publish_evaluator.py`, `tests/test_guarded_publish_runner.py`, `doc/done/2026-04/242-D2-farm-result-classifier-review-alignment.md`, `doc/done/2026-04/242-D-farm-result-placeholder-body-publish-blocker.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/done/2026-04/242-D2-farm-result-classifier-review-alignment.md`
- **acceptance**: ✓ farm_result classifier narrow に動作 / 63845-type placeholder body hard-stops / 63841-type farm_lineup excluded / 242-A medical_roster narrow 維持 / DEATH/INJURY 真陽性維持 / Gemini/LLM call 増加なし / live verify sample 5 件で確認
- **repo_state**: pushed
- **commit_state**: `25f176b`
- **next_prompt_path**: -
- **last_commit**: `25f176b` 242-D2: align farm_result placeholder gate with classifier and review flags
- **parent**: 242-D

### 242-E death-or-grave-family-context-precision

- **alias**: -
- **priority**: P0.5
- **status**: READY
- **owner**: Codex B(implementation)/ Claude(dispatch + accept + push + live verify)
- **lane**: B
- **ready_for**: Codex B narrow fix fire
- **next_action**: `DEATH_OR_GRAVE_INCIDENT_RE` 発火直前に family-context 共起チェックを追加し、family death(祖父/祖母/おじいちゃん/おばあちゃん/父/母/家族 etc.)を player-self death と区別する narrow skip
- **blocked_by**: none
- **user_action_required**: none(scope 確定済み、Codex B fire 可)
- **write_scope**: `src/guarded_publish_evaluator.py`, `tests/test_guarded_publish_evaluator.py`, `doc/active/242-E-death-or-grave-family-context-precision.md`, `doc/active/242-auto-publish-gate-regression-off-topic-published-and-eligible-held.md`, `doc/README.md`, `doc/active/assignments.md`
- **doc_path**: `doc/active/242-E-death-or-grave-family-context-precision.md`
- **acceptance**: 63475/63470 type(family death co-occurrence)が hard_stop しない / player-self death/grave injury 真陽性は hard_stop 維持 / 242-A/D/D2 既存挙動不変 / Gemini/LLM call 追加なし / pytest 124 baseline + 6 fixture 全 pass
- **repo_state**: doc 起票済(active untracked)
- **commit_state**: pending Codex B implementation
- **next_prompt_path**: `doc/active/242-E-death-or-grave-family-context-precision.md`
- **last_commit**: -
- **parent**: 242 / 242-A

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
- **doc_path**: `doc/done/2026-04/130-pub004-hard-stop-vs-repairable-before-publish.md`
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
- **doc_path**: `doc/done/2026-04/131-publish-notice-burst-summary-and-alerts.md`
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
- **doc_path**: `doc/done/2026-04/134-doc-ticket-archive-and-folder-policy.md`(本 commit 後 Claude が mv)
- **acceptance**: ✓ active/review/blocked/archived/2026-04 folder 作成、doc/ root = 102 + PUB-* 9 件のみ、102 board doc_path field 全反映
- **repo_state**: pushed
- **commit_state**: **`35fb67c`**
- **next_prompt_path**: -
- **last_commit**: `35fb67c` 134 doc folder reorg

### 135 pub004-breaking-news-freshness-gate

- **alias**: -
- **priority**: **P0**(critical safety、105 ramp halt blocker)
- **status**: **CLOSED**(`ef9e21d` push 済、pytest 1318 → 1321、3 hard_stop flag + 4 出力 field + 3 summary count 実装)
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
- **spec_doc**: `doc/done/2026-04/135-pub004-breaking-news-freshness-gate.md`
- **write_scope**: `src/guarded_publish_evaluator.py` + `tests/test_guarded_publish_evaluator.py` + 必要なら `src/pre_publish_fact_check/extractor.py`
- **doc_path**: `doc/done/2026-04/135-pub004-breaking-news-freshness-gate.md`
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

- `git diff -- doc/README.md`
- 219 row carries alias `MKT-001` and points to `doc/marketing/active/MKT-001-publish-notice-marketing-mail-classification.md`.
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

## marketing board

- Marketing ticket source of truth: `doc/marketing/README.md`
- Historical numeric ticket `219` is preserved as alias `MKT-001`
- Related implementations still obey the root execution board, but marketing decomposition lives under `doc/marketing/`

## related files

- `doc/103-publish-notice-cron-health-check.md`
- `doc/active/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`
- `doc/118-pub004-red-reason-decision-pack.md`
- `doc/123-pub004-auto-publish-readiness-and-regression-guard.md`
- `doc/done/2026-04/PUB-002-B-missing-primary-source-publish-blocker-reduction.md`
- `doc/done/2026-04/PUB-002-C-subtype-unresolved-publish-blocker-reduction.md`
- `doc/done/2026-04/PUB-002-D-long-body-draft-compression-or-exclusion-policy.md`
- `doc/waiting/PUB-005-x-post-gate.md`
- `doc/119-x-post-eligibility-evaluator.md`
- `doc/120-x-post-autopost-queue-and-ledger.md`
- `doc/121-x-post-live-helper-one-shot-smoke.md`
- `doc/122-x-post-controlled-autopost-rollout.md`
- `doc/125-adsense-manual-ad-unit-embed.md`
- `doc/126-sns-topic-fire-intake-dry-run.md`
- `doc/127-sns-topic-source-recheck-and-draft-builder.md`
- `doc/128-sns-topic-auto-publish-through-pub004.md`
- `doc/HALLUC-LANE-002-llm-based-fact-check-augmentation.md`
