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
- **acceptance**: 102-116 rows are present, old 104-wait contradiction removed, A/B next actions clear
- **repo_state**: modified
- **commit_state**: uncommitted update after `d6548ba`
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
- **next_action**: present Red reason top 5 to user → user 1 ワード判断(go / no-go / retune filter)
- **blocked_by**: user ramp decision after dry-run result
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
- **repo_state**: doc exists untracked
- **commit_state**: uncommitted doc
- **next_prompt_path**: create at fire time
- **last_commit**: -

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
- **repo_state**: doc exists untracked
- **commit_state**: uncommitted doc
- **next_prompt_path**: create at fire time
- **last_commit**: -

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
- **priority**: P2
- **status**: BLOCKED_USER
- **owner**: Codex A or B after user go
- **lane**: either
- **ready_for**: none
- **next_action**: wait for explicit user go; live X post remains prohibited
- **blocked_by**: X live post / user explicit go
- **user_action_required**: explicit X live helper go and credential boundary approval
- **write_scope**: not assigned until unblocked
- **acceptance**: no X API live post without user trigger and final approval
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
- **repo_state**: doc 起票 untracked
- **commit_state**: uncommitted doc
- **next_prompt_path**: -(Claude 自身で実装、user 明示後)
- **last_commit**: -
- **policy A**: UI 優先、anchor/vignette 殺し、記事内広告最大 3 枠
- **policy B**: 自動広告フル解除
- **policy C**: 広告 OFF 維持(現状)
- **source_of_truth**: `docs/handoff/ad_policy_memo_post_launch.md`(A/B/C 方針正本)
- **parent**: 087(器 = AdSense slot 枠 既設)

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
| A | 0 direct implementation tickets | use 105 Claude orchestration, then replenish A if needed |
| B | 5 | 108 / 109 / 110 / 111 / 112 |
| either | 0 unblocked live tickets | 114 blocked by user |

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

- **A slot next**: 105 dry-run / dry-run result presentation. If 105 is parked after user review, replenish A with a new ops/doc/test ticket.
- **B slot next**: 108 or 112.
- **Live 105 ramp**: only after 105 dry-run result is shown and user explicitly says go.
- **Do not advance 113 / 114 / 115 / 116** without user action or external precondition.

## dependency locks

- 104 before 105: satisfied (`78f965d`).
- 103 before/near 105: satisfied (`d6548ba`).
- X live post: blocked until explicit user trigger.
- HALLUC-LANE-002 real LLM/API: blocked until explicit user go.
- `RUN_DRAFT_ONLY=False`: prohibited here.
- Cloud Run env changes: prohibited here.

## Claude notification

```text
102 board の整合修正方針をCodex側で反映しました。

修正内容:
- 104はCLOSEDで固定し、旧前提文言を削除
- 105はREADY、blocked_byなし。ただしlive rampはdry-run後のuser判断待ち
- 103/106/107はCLOSED
- 093は115、095-Eは116へalias整理
- PUB-002-B/C/Dは109/110/111へalias整理
- HALLUC-LANE-002は113、X live helperは114へalias整理
- 108〜116を102 boardへ追加
- B slot在庫として108/109/110/111/112をREADY化
- 113/114/115/116はBLOCKED_USER扱い

次の実行:
- A slot next: 105 dry-run / dry-run結果提示
- B slot next: 108または112
- 105 live rampはuserの明示go後のみ

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
- 105 has `blocked_by: none`; live ramp is still user-gated after dry-run.
- 108-116 are present.
- A slot next and B slot next are explicit.

## related files

- `doc/103-publish-notice-cron-health-check.md`
- `doc/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`
- `doc/PUB-002-B-missing-primary-source-publish-blocker-reduction.md`
- `doc/PUB-002-C-subtype-unresolved-publish-blocker-reduction.md`
- `doc/PUB-002-D-long-body-draft-compression-or-exclusion-policy.md`
- `doc/PUB-005-x-post-gate.md`
- `doc/HALLUC-LANE-002-llm-based-fact-check-augmentation.md`
