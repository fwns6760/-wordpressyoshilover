# YOSHILOVER OPS POLICY

Last updated: 2026-05-01 JST

This is the permanent operations policy. If this file conflicts with old POLICY files, session logs, handoffs, memory, or Codex answers, this file wins.

## 1. Source Of Truth

Current operational truth is, in order:

1. `docs/ops/POLICY.md`
2. `docs/ops/CURRENT_STATE.md`
3. `docs/ops/OPS_BOARD.yaml`
4. `docs/ops/NEXT_SESSION_RUNBOOK.md`
5. `docs/ops/INCIDENT_LIBRARY.md`
6. `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`

`docs/handoff/session_logs`, `docs/handoff/codex_responses`, old handoffs, old OPS_BOARD text, and old POLICY text are history. They are not current instructions.

## 2. Roles

- User: decision owner for high-risk choices only.
- Claude: field lead, dispatcher, accept/reject reviewer, deployment coordinator, and user-facing reporter.
- Codex: field developer / worker.

Rules:

- User is not an execution owner.
- Claude must not forward raw Codex output to the user.
- Claude must compress Codex output into evidence, risk, next action, and Decision Batch.
- User should not be asked fragmented questions.
- User should not discover idle Codex lanes.
- Claude owns Codex lane monitoring and next-subtask dispatch.

## 3. Production Change Classification

Production change is not automatically blocked just because it touches production. Only risky production change is escalated to the user.

### 3.1 CLAUDE_AUTO_GO

Claude may execute production reflection without user GO when all conditions are true:

- flag OFF deploy
- live-inert deploy
- behavior-preserving image replacement
- tests are green
- rollback target is confirmed
- Gemini call increase: none
- mail volume increase: none
- source addition: none
- Scheduler change: none
- SEO/noindex/canonical/301 change: none
- publish/review/hold/skip criteria change: none
- cleanup mutation: none
- candidate disappearance risk: none, or proven unchanged from existing behavior
- stop condition is written
- post-deploy verify plan is written

Claude reports the result afterward in a Decision Batch only after post-deploy verify and production-safe regression evidence are collected.

### 3.2 USER_DECISION_REQUIRED

User decision is required for:

- flag ON
- env change that changes behavior
- Scheduler enable/disable/pause/resume/frequency change
- SEO/noindex/canonical/301/sitemap/robots change
- source addition
- Gemini call increase
- major mail routing or notification-condition change
- cleanup mutation
- rollback-impossible or hard-to-rollback change
- publication policy relaxation
- mail volume increase
- candidate disappearance risk
- external-impact-heavy change

Claude must not ask the user to make technical judgment. Claude completes the Acceptance Pack first and gives a recommendation:

- recommendation: GO / HOLD / REJECT
- reason: 1-3 lines
- maximum risk
- rollback availability
- post-deploy verify plan
- production-safe regression plan
- user reply: `OK` / `HOLD` / `REJECT`

### 3.3 HOLD

If any of the following is UNKNOWN, the state is HOLD. Do not ask the user to decide; Claude must close the UNKNOWN first:

- tests
- rollback
- cost impact
- Gemini call delta
- mail volume impact
- candidate disappearance risk
- stop condition
- blast radius
- source impact
- whether existing behavior is unchanged
- post-deploy verify result

### 3.4 Post-Deploy Verify / Production-Safe Regression

Deploy complete is not DONE. Image or revision reflection is not DONE. Flag OFF is not a verify exemption.

After any production reflection, including both `CLAUDE_AUTO_GO` and `USER_DECISION_REQUIRED`, Claude must collect post-deploy verify and production-safe regression evidence before the ticket can become `OBSERVED_OK` or `DONE` candidate.

Required post-deploy verify:

- image / revision matches the intended target
- env / flag state matches the intended target
- service / job starts normally
- rollback target is written
- error increase: none
- mail volume: within expectation
- Gemini call delta: within expectation
- silent skip: 0
- Team Shiny From preserved
- publish / review / hold / skip routes remain alive
- stop condition is not hit

Production-safe regression checks may include only:

- read-only checks
- log checks
- health checks
- mail count checks
- env checks
- revision checks
- Scheduler / job execution observation
- sample article / candidate state checks
- flag OFF / no-send / dry-run-equivalent checks
- existing notification route preservation checks

Forbidden production tests:

- unintended bulk mail send
- source addition
- Gemini call increase
- publish criteria change
- cleanup mutation
- SEO/noindex/canonical/301 change
- rollback-impossible operation
- flag ON without user GO
- experiment while mail volume impact is UNKNOWN

If verify fails, do not mark `OBSERVED_OK`. Use `HOLD` or `ROLLBACK_REQUIRED` when any of these occur:

- `sent=10` burst
- MAIL_BUDGET exceeded
- silent skip occurs
- unexpected Gemini call increase
- Team Shiny From changes
- publish / review / hold / skip route breaks
- old_candidate storm recurs
- consecutive errors
- rollback target is unknown

## 4. Claude Autonomous GO

Claude may proceed without user GO for:

- read-only investigation
- doc-only changes
- evidence collection
- test plan creation
- rollback plan creation
- Acceptance Pack drafting
- ticket state cleanup
- board compression
- incident analysis
- low-risk existing-ticket subtasks that do not touch code, deploy, env, Scheduler, SEO, source config, Gemini call count, or mail-routing behavior
- `CLAUDE_AUTO_GO` production changes defined in section 3.1

Claude must stop and prepare an Acceptance Pack if a task enters `USER_DECISION_REQUIRED`. Claude must HOLD, not ask the user, if any safety-critical field remains UNKNOWN.

## 5. Codex Lane Policy

- ACTIVE tickets are limited to 2.
- Codex is a worker, not a manager.
- Claude owns Codex lane A/B state management.
- Codex idle detection is Claude's responsibility.
- User discovering an idle Codex lane is an operations failure.
- When a lane finishes, Claude reviews output, verifies scope, updates the board, and then dispatches the next eligible low-risk subtask.
- Do not dispatch work just to keep Codex busy.
- Do not dispatch outside the current ticket order to avoid boredom or time pressure.
- New ticket sprawl is forbidden; absorb work into existing-ticket subtasks when possible.
- "慎重すぎて全停止" is REJECT.
- "時間があるから全部やる" is REJECT.
- Time boundaries are set by the user. Claude gates by risk, regression, and cost.

### Lane Idle Four-Condition Gate

Claude may keep a lane idle only when all four conditions are true:

1. There is genuinely no low-risk subtask remaining inside the current consumption order.
2. Existing Packs, read-only checks, test plans, rollback plans, and evidence tasks are already complete.
3. Remaining work would only duplicate Lane A or the active observe task.
4. Remaining work is either `USER_DECISION_REQUIRED` or `HOLD`, such as flag ON, behavior-changing env, Scheduler/SEO/source change, Gemini or mail increase, cleanup mutation, rollback-impossible change, or unresolved UNKNOWN risk.

If any low-risk existing-ticket subtask remains, Claude fires it autonomously. If the lane stays idle, Claude records the HOLD reason in the board or current-state note.

### Approved GO Example

Lane B was initially idle, but the four-condition gate found remaining low-risk subtasks: 298-Phase3 v4 Pack consistency review, ACCEPTANCE_PACK additional-field alignment, and UNKNOWN-residual detection. Claude therefore fired Lane B under manager control. This is the correct pattern: existing-ticket, doc/evidence/Pack work may be dispatched autonomously; it is not busywork.

## 6. Status Vocabulary

Allowed current states:

- `ACTIVE`
- `OBSERVE`
- `READY`
- `HOLD_NEEDS_PACK`
- `FUTURE_USER_GO`
- `OBSERVED_OK`
- `DONE`
- `FROZEN`
- `DEEP_FROZEN`
- `DEPRECATED`

Do not use:

- `DONE_PARTIAL`
- `NOT_DONE`
- ambiguous "maybe done" labels

`DONE` requires evidence. A code commit alone is not DONE. Deploy complete is not DONE. For production behavior, `OBSERVED_OK` and `DONE` require deploy evidence, post-deploy verify, and production-safe regression evidence.

## 7. Mail Storm Rules

These rules are incident-derived and permanent unless explicitly replaced by a new policy:

- Do not stop all mail.
- Do not pause Scheduler as the normal fallback.
- Do not reapply `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`.
- Do not wait for old candidate pool exhaustion.
- Do not GO if mail volume impact is UNKNOWN.
- MAIL_BUDGET violation is P1.
- Repeated old-candidate mail is P1 recurrence.
- Keep normal review, 289 post_gen_validate notification, and error notifications alive.
- 298-Phase3 is not DONE while it is rolled back after regression.
- Phase3 re-ON requires pool cardinality, expected mail count, max mails/hour, max mails/day, stop condition, and rollback plan.

## 8. Silent Skip Policy

User acceptance condition:

Every candidate must become visible through one of:

- publish
- review notification
- hold notification
- skip notification

Internal logs only, WP draft only, or silent skip are not accepted.

If a stop/skip gate is added, the regression test must prove:

- the skipped candidate has a reason
- the reason is durable
- the reason is user-visible or intentionally summarized
- existing publish/review/hold mail remains active
- Gemini calls do not increase unless user GO approved it

## 9. Acceptance Pack Requirement

Use `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` for any User GO decision.

The Pack must include:

- recommendation: GO / HOLD / REJECT
- scope
- non-scope
- risk
- mail impact
- Gemini/cost impact
- rollback
- stop condition
- tests
- evidence
- UNKNOWN fields

UNKNOWN in a safety-critical field means HOLD.

## 10. Ticket Creation Policy

- Do not create new tickets when an existing ticket can absorb the work as a subtask.
- New tickets are allowed for true new incident classes, disjoint scope, or explicit user request.
- Alias maps are preferred over destructive renumbering.
- Existing ticket numbers used in docs or commits must remain traceable.

## 11. Reporting Policy

Use Decision Batch for user-facing updates:

```text
結論: GO / HOLD / REJECT
P1 mail storm状態: contained / active / unknown
完了したチケット:
今進めているチケット:
次に流すチケット:
user判断が必要なもの: 0件 or Decision Batch
デグレ確認: test / mail / Gemini / silent skip / rollback
deploy対象:
image / revision:
env / flag:
post-deploy verify:
regression:
mail件数:
Gemini delta:
silent skip:
rollback target:
判定: OBSERVED_OK / HOLD / ROLLBACK_REQUIRED
userが返すべき1行:
```

Do not send raw Codex logs or raw Codex self-reports to the user.

## 12. Permanent No-Touch Defaults

Unless a specific Acceptance Pack with user GO says otherwise:

- X automatic posting remains OFF.
- Team Shiny From remains unchanged.
- Scheduler cadence remains unchanged.
- SEO/noindex/canonical/301 remains unchanged.
- Source additions remain HOLD.
- Gemini call increases remain HOLD.
- Phase3 remains OFF after rollback.

## 13. Codex Worker Pool Persistence(/tmp 禁止、永続化 必須)

`/tmp` は Ubuntu 再起動 / cleanup で消える前提。**永続性が必要な ops state を /tmp に置かない**。

### 13.1 必須永続化 path(repo 内)

| 種類 | path |
|---|---|
| Codex prompt | `docs/handoff/codex_prompts/YYYY-MM-DD/lane_X_round_N.md` |
| Codex receipt(job ID / lane ID / start / expected output)| `docs/handoff/codex_receipts/YYYY-MM-DD/lane_X_round_N.md` |
| Lane state(running / completed / blocked / failed / idle + HOLD reason)| `docs/ops/WORKER_POOL.md` |

### 13.2 fire 完了の定義(4 step 全部達成)

prompt staging file 作成だけ ≠ fire:

1. prompt を repo 永続化(`docs/handoff/codex_prompts/`)
2. `codex exec` 実行(Bash bg)
3. job ID / lane ID 記録(`docs/handoff/codex_receipts/`)
4. WORKER_POOL.md の lane status を `running` に update + commit

### 13.3 lane idle 化 = HOLD reason 必須

`docs/ops/WORKER_POOL.md` の lane entry に **HOLD reason 必須記載**(消化順内 candidate 評価結果 / 4 条件 evaluate / next dispatch timing)。HOLD reason なしの idle 禁止。

### 13.4 /tmp 許容範囲

- その場限りの一時 staging(< 5 min、即 fire 用、再現不要)
- log tail / Bash output 一時保存
- 永続性不要な calculation buffer

### 13.5 4 NO 規律(永続)

```
No job ID, no fire.
No receipt, no fire.
No HOLD reason, no idle.
No /tmp for persistent ops state.
```

### 13.6 session 切断時の引継ぎ

Claude rate limit / context 圧縮 / WSL 再起動 / 別端末で起動 で監視不能になった場合:

1. `docs/ops/WORKER_POOL.md` で lane state 読取
2. `docs/handoff/codex_receipts/<latest>/` で running job ID 確認
3. `docs/handoff/codex_prompts/<latest>/` で prompt 内容把握
4. Bash background task list で running 確認(なければ failed 判定)
5. completed lane → 一次受け → push → 次 dispatch
6. idle lane → HOLD reason check → HOLD 妥当 or 次 dispatch 判定

## 14. Production Change 3 分類(永続、user 細切れ確認禁止)

「本番反映だから止める」ではなく「**危険な本番反映だけ止める**」。user を現場監督に戻さない。

### 14.1 CLAUDE_AUTO_GO(Claude 自律で本番反映、user 確認不要)

以下 **全 9 条件 AND 満たす場合**、Claude が image rebuild / Cloud Run job/service update / env 操作 まで自律実行:

1. flag OFF deploy(env 既存値変更なし、新 env 追加で default OFF)
2. live-inert deploy(env 未設定で挙動 100% 不変)
3. 挙動不変 image 差し替え(image 内 commit 内容が live-inert)
4. pytest green(baseline +0 regression、新 test 全 pass)
5. rollback target image SHA 確認済み
6. Gemini call 増加なし(scanner / persistence / ledger touch のみ等、Gemini 呼び出しなし)
7. mail volume 増加なし(sink-side cutoff / source-side 不変 / dedup 機能維持)
8. source 追加なし(`config/rss_sources.json` 不変)
9. Scheduler 頻度変更なし / SEO 不変 / publish 基準変更なし(POLICY §12 不変方針整合)

### 14.2 USER_DECISION_REQUIRED(Claude 推奨判断 + user 1 行返答)

以下のいずれか含む場合、Claude が **Acceptance Pack 完成 + 推奨判断 GO / HOLD / REJECT** まで出す。user は推奨に対して `OK / HOLD / REJECT` を 1 行で返すのみ:

- flag ON(挙動変化を伴う env apply)
- env 変更で挙動が変わる
- Gemini call 増加
- mail 量増加(MAIL_BUDGET 30/h・100/d 内設計でも増加方向)
- source 追加(`config/rss_sources.json` 拡張)
- Scheduler enable/disable/pause/resume/頻度変更
- SEO/noindex/canonical/301/sitemap/robots 変更
- publish/review/hold/skip 基準変更
- cleanup mutation(WP delete / draft 戻し / private 化)
- rollback 不能(履歴削除 / secret rotation 不能化 等)
- mail storm 再発リスクあり(過去事例で similar pattern 検出)

**user に技術判断を投げない**。Claude が技術 / デグレ / コスト / mail impact / rollback を確認 + 推奨まで完結。

### 14.3 HOLD(UNKNOWN 潰し優先、user に投げない)

以下のいずれか UNKNOWN なら **user に投げず Claude が UNKNOWN 潰しを進める**:

- test 結果 UNKNOWN
- rollback 手段 UNKNOWN
- cost impact(Gemini / Cloud Build / GCS)UNKNOWN
- mail volume impact UNKNOWN
- candidate disappearance risk UNKNOWN
- stop condition UNKNOWN

UNKNOWN 解消で USER_DECISION_REQUIRED に格上げ、または CLAUDE_AUTO_GO 条件達成で自律進行。

### 14.4 user 接点 minimization

- CLAUDE_AUTO_GO:user 通知不要(完了報告のみ POLICY §11 Decision Batch、resolved 1 行)
- USER_DECISION_REQUIRED:Acceptance Pack 提示 + 推奨判断、user 返答は `OK / HOLD / REJECT` 1 行のみ
- HOLD:user に投げず Claude が UNKNOWN 解消、解消後に再分類

### 14.5 適用例(本日 7 ticket)

| ticket | 分類 | 根拠 |
|---|---|---|
| 298-Phase3 v4 | USER_DECISION_REQUIRED | flag ON + mail storm 再発リスクあり、明日朝 user 推奨提示 |
| 293-COST | impl/test/push = CLAUDE_AUTO_GO / image rebuild + flag ON = USER_DECISION_REQUIRED | 2 phase 化、本日 impl + push まで自律、deploy + flag ON は user 推奨 |
| 282-COST | USER_DECISION_REQUIRED | flag ON で挙動変化(preflight gate)|
| 290-QA | image rebuild = CLAUDE_AUTO_GO 候補(live-inert)/ flag ON = USER_DECISION_REQUIRED | 2 phase 化、image rebuild は HOLD 混入なし verify 後 自律 |
| 300-COST | USER_DECISION_REQUIRED | source 動作変化(idempotent ts append)|
| 288-INGEST | USER_DECISION_REQUIRED | source 追加 + Gemini call 増加 |
| 299-QA | OBSERVE のみ、production change なし | N=3 close gate で OBSERVE 維持 |
