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
- **priority**: P0.5
- **status**: BLOCKED_USER(dry-run 完了、live ramp は user go/no-go 待ち)
- **owner**: Claude Code(orchestration)
- **lane**: Claude
- **ready_for**: live ramp = user judgment 待ち / dry-run = 完了済
- **next_action**: run/refresh 123 readiness guard → present Red reason top 5 + readiness classification → user 1 ワード判断(go / no-go / retune filter)
- **blocked_by**: all-red dry-run result + user ramp decision + no PUB-004 auto-publish cron line
- **user_action_required**: **YES**(live publish ramp の go / no-go / filter retune の最終判断)
- **write_scope**: none for dry-run(完了済); live ramp は PUB-004-B gates 経由のみ、user go 後
- **acceptance**: total draft count + Green/Yellow/Red/cleanup counts + top refusal reasons + lineup effect が user に提示済
- **dry_run_result**(2026-04-26 morning autonomous 実行): **total 97 / Green 0 / Yellow 0 / Red 97 / cleanup 0 / lineup_representative 0 / lineup_deferred 2**(`/tmp/pub004d/full_eval.json`)
- **repo_state**: doc committed as alias `PUB-004-D`; dry-run artifact `/tmp/pub004d/full_eval.json` 存在
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
- **status**: READY
- **owner**: Codex B
- **lane**: B
- **ready_for**: B
- **next_action**: fire read-only audit for published articles with `site_component_heavy` / related cleanup candidates
- **blocked_by**: none
- **user_action_required**: none; any WP write/apply belongs to a later ticket
- **write_scope**: proposed read-only module/tool/tests only; no WP write path
- **acceptance**: published articles are audited, cleanup candidates are emitted as JSON/human summary, fixtures pass, WP write zero
- **repo_state**: pushed
- **commit_state**: `79ab94b`
- **next_prompt_path**: create at fire time
- **last_commit**: `79ab94b` docs for 108-112

### 109 missing-primary-source-blocker-reduction

- **alias**: PUB-002-B
- **priority**: P1
- **status**: READY
- **owner**: Codex B
- **lane**: B
- **ready_for**: B
- **next_action**: classify missing-primary-source blockers and propose narrow reductions
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: source recovery/audit module/tool/tests; no WP write
- **acceptance**: blocker categories and recovery candidates are visible, tests pass, existing source trust contract unchanged
- **repo_state**: alias doc exists
- **commit_state**: alias doc committed
- **next_prompt_path**: create at fire time
- **last_commit**: alias doc synced in `e49ae2d`

### 110 subtype-unresolved-blocker-reduction

- **alias**: PUB-002-C
- **priority**: P1
- **status**: READY
- **owner**: Codex B
- **lane**: B
- **ready_for**: B
- **next_action**: classify unresolved subtype blockers and add bounded tests/branch proposals
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: subtype extraction/audit code and tests only
- **acceptance**: unresolved patterns counted, new branch candidates explicit, existing extractor tests pass
- **repo_state**: alias doc exists
- **commit_state**: alias doc committed
- **next_prompt_path**: create at fire time
- **last_commit**: alias doc synced in `e49ae2d`

### 111 long-body-compression-or-exclusion

- **alias**: PUB-002-D
- **priority**: P2
- **status**: READY
- **owner**: Codex B
- **lane**: B
- **ready_for**: B
- **next_action**: audit long-body distribution and propose compression/exclusion policy
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: read-only audit module/tool/tests; no WP write
- **acceptance**: prose length distribution, subtype causes, and safe policy options are produced
- **repo_state**: alias doc exists
- **commit_state**: alias doc committed
- **next_prompt_path**: create at fire time
- **last_commit**: alias doc synced in `e49ae2d`

### 112 title-prefix-and-lineup-misclassification-fixtures

- **alias**: -
- **priority**: P0.5
- **status**: READY
- **owner**: Codex B
- **lane**: B
- **ready_for**: B
- **next_action**: add regression fixtures for non-lineup articles incorrectly carrying `巨人スタメン` prefix
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: new tests only; no source changes unless a failing fixture exposes a minimal fix request
- **acceptance**: fixture set proves 104 behavior and guards prefix misuse without touching production code
- **repo_state**: pushed
- **commit_state**: `79ab94b`
- **next_prompt_path**: create at fire time
- **last_commit**: `79ab94b` docs for 108-112

### 113 halluc-lane-002-llm-fact-check-augmentation

- **alias**: HALLUC-LANE-002
- **priority**: P1
- **status**: BLOCKED_USER
- **owner**: Codex B after user go
- **lane**: B
- **ready_for**: none
- **next_action**: wait for explicit user go because Gemini API/cost is involved
- **blocked_by**: Gemini API cost / user explicit go
- **user_action_required**: explicit `HALLUC-LANE-002 go`
- **write_scope**: not assigned until unblocked
- **acceptance**: no real LLM/API/cost before explicit user go
- **repo_state**: doc-first alias exists
- **commit_state**: committed doc
- **next_prompt_path**: none until unblocked
- **last_commit**: `c84ef21` doc sync

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
- **priority**: P1.5(105 公開 ramp より後、今すぐはやらない)
- **status**: BLOCKED_USER
- **owner**: **Claude-managed front-scope**(Front-Claude 不在、Claude 自身が front-scope を管理)
- **lane**: either / front-scope
- **ready_for**: none(user choice 待ち)
- **next_action**: user が A / B / C を明示 → `src/custom.css` AdSense 全殺し section の read-only 確認 → 選択 pattern に応じた CSS 解除
- **blocked_by**: **user choice A / B / C + AdSense account 状態確認**
- **user_action_required**: 「広告方針 A / B / C で」と明示
- **write_scope**: `src/custom.css` の AdSense 全殺し section のみ(backend Python / publish runner / WP REST 触らない)
- **acceptance**: user 明示後着手 / 解除対象 CSS 明確 / mobile/desktop 表示破綻なし / anchor/vignette が方針通り / backend 差分なし
- **repo_state**: pushed
- **commit_state**: `0c883ba`
- **next_prompt_path**: -(Claude 自身で実装、user 明示後)
- **last_commit**: `0c883ba`
- **policy A**: UI 優先、anchor/vignette 殺し、記事内広告最大 3 枠
- **policy B**: 自動広告フル解除
- **policy C**: 広告 OFF 維持(現状)
- **source_of_truth**: `docs/handoff/ad_policy_memo_post_launch.md`(A/B/C 方針正本)
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
- **status**: READY
- **owner**: Codex B
- **lane**: B
- **ready_for**: B
- **next_action**: fire read-only evaluator for published Green-only X candidates
- **blocked_by**: none
- **user_action_required**: none
- **write_scope**: `src/x_post_eligibility_evaluator.py`, `src/tools/run_x_post_eligibility_evaluator.py`, `tests/test_x_post_eligibility_evaluator.py`
- **acceptance**: published-only / Green-only eligible list, Yellow/Red/X-side Red refused with reasons, JSON + human summary, WP write zero, X API zero
- **repo_state**: doc exists
- **commit_state**: current X ticket sync commit
- **next_prompt_path**: create at fire time
- **last_commit**: current X ticket sync commit
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
- **repo_state**: doc 起票 untracked
- **commit_state**: pending sync (本 commit便で push)
- **next_prompt_path**: 124-A fire 時に Claude が用意
- **last_commit**: -
- **parent**: 108 (audit) / PUB-004-B (cleanup contract pre-publish 版)

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

Current inventory:

| lane | READY count | tickets |
|---|---:|---|
| A | 1 | 123 |
| B | 6 | 108 / 109 / 110 / 111 / 112 / 119 |
| either | 0 unblocked live tickets | 114 umbrella parked; 120 parked until 119 close |

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

## next actions

- **A slot next**: 123 readiness/regression guard for no-auto-publish state; then 105 decision presentation.
- **B slot next**: 119 first for X unlock path, otherwise 108 or 112.
- **Live 105 ramp**: only after 105 dry-run result is shown and user explicitly says go.
- **PUB-004-C auto-publish cron**: do not add until 123 says ready and at least one safe live burst succeeds.
- **Do not advance 113 / 115 / 116 / 121** without user action or external precondition.
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

次の実行:
- B slot next: 119
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
- 108-123 are present.
- 123 is READY for no-auto-publish readiness/regression guard.
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
- `doc/HALLUC-LANE-002-llm-based-fact-check-augmentation.md`
