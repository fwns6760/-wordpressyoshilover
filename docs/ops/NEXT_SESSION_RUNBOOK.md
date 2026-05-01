# YOSHILOVER NEXT_SESSION_RUNBOOK

Last updated: 2026-05-01 JST

Use this when Claude/Codex resumes after restart.

## 1. First Read Order

1. `docs/ops/CURRENT_STATE.md`
2. `docs/ops/POLICY.md`
3. `docs/ops/OPS_BOARD.yaml`
4. `docs/ops/INCIDENT_LIBRARY.md`
5. `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`

Do not treat session logs, old handoffs, or raw Codex responses as current policy.

## 2. Startup Checks

Run read-only checks only:

- `git status --short`
- `git log --oneline -10`
- confirm dirty worktree paths before touching docs
- inspect `docs/ops/OPS_BOARD.yaml`
- confirm whether any Codex lane is currently running

Do not make unclassified production changes during startup. Apply `POLICY.md` section 3 before any production reflection: `CLAUDE_AUTO_GO` may proceed after evidence; `USER_DECISION_REQUIRED` needs a completed Pack; `HOLD` means Claude closes UNKNOWN first. Any production reflection then requires post-deploy verify before `OBSERVED_OK` or `DONE`.

## 3. Restore Current Board

Current major state:

- 298-Phase3: `HOLD_NEEDS_PACK`, `ROLLED_BACK_AFTER_REGRESSION`, flag OFF/absent, persistent ledger disabled, storm contained, second-wave risk OPEN.
- 293-COST: active for visible skip readiness; implementation/test/local verify/flag OFF or live-inert deploy may proceed only if `CLAUDE_AUTO_GO` conditions pass, followed by post-deploy verify.
- 300-COST: active for read-only source-side cost analysis; source-side behavior change must be classified before implementation/deploy.
- 299-QA: observe flaky/transient, not P0 by default.
- 282-COST: future user GO for flag ON after 293.
- 290-QA: live-inert deploy may be `CLAUDE_AUTO_GO` after classification and post-deploy verify plan; weak title rescue enablement is user decision.
- 288-INGEST: future user GO for source addition Pack.

## 4. Codex Lane Handling

- Claude owns lane monitoring.
- Codex is a worker, not a manager.
- If a lane is idle, Claude must apply the four-condition gate from `POLICY.md` section 5.
- If a low-risk existing-ticket subtask remains, Claude dispatches it autonomously.
- Eligible low-risk subtasks are read-only, doc-only, evidence, test plan, rollback plan, Acceptance Pack, or ticket cleanup.
- Do not dispatch code/deploy/env/Scheduler/source/Gemini/mail-routing work until it is classified under `POLICY.md` section 3. `CLAUDE_AUTO_GO` work may proceed; `USER_DECISION_REQUIRED` needs a Pack; `HOLD` stays internal until UNKNOWN is closed.
- Do not ask the user whether to dispatch a READY-incomplete low-risk subtask.
- Do not keep a lane idle unless the HOLD reason is explicit.
- Do not fire meaningless work just to make Codex look busy.
- Do not create new tickets when the work can be absorbed as a subtask of an existing ticket.

Approved example: Lane B was initially idle, but Claude found remaining low-risk work in 298-Phase3 v4 Pack consistency, ACCEPTANCE_PACK extra-field alignment, and UNKNOWN-residual detection. Dispatching that Lane B task was correct because it stayed inside existing-ticket Pack/evidence work and did not touch deploy, env, Scheduler, source, Gemini, code, or mail conditions.

## 5. Decision Batch Only

When reporting to the user, use:

```text
結論: GO / HOLD / REJECT
P1 mail storm状態: contained / active / unknown
完了したチケット:
今進めているチケット:
次に流すチケット:
user判断が必要なもの: 0件 or Decision Batch
デグレ確認: test / mail / Gemini / silent skip / rollback
userが返すべき1行:
```

Do not paste raw Codex output.

## 6. 298-Phase3 Guard

Before any Phase3 re-ON proposal, the Acceptance Pack must include:

- old candidate pool cardinality estimate
- expected mail count
- max mails/hour
- max mails/day
- stop condition
- rollback command
- UNKNOWN fields = 0

If any item is missing, the answer is HOLD.

## 7. Mail Storm Safety

Never use these as normal fixes:

- all-mail stop
- Scheduler pause
- `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`
- waiting for pool exhaustion

Keep normal review mail, 289 notification mail, and error mail active.

## 8. Low-Risk Work Queue

Proceed only inside current ticket scope:

1. 293-COST Pack/test/rollback planning.
2. 300-COST read-only cost analysis.
3. 299-QA baseline and recurrence observation.
4. 298-Phase3 Acceptance Pack reconstruction.
5. Board/doc cleanup if ambiguity blocks the above.

Do not create new tickets unless an issue cannot fit into the above.

## 9. Stop / Classify Conditions

Stop and classify the change under `POLICY.md` section 3 if any production effect is proposed.

Proceed autonomously only when it is `CLAUDE_AUTO_GO`:

- flag OFF deploy, live-inert deploy, or behavior-preserving image replacement
- tests green
- rollback target confirmed
- no Gemini/mail/source/Scheduler/SEO/publish criteria/candidate risk increase
- stop condition written
- post-deploy verify plan written

Prepare an Acceptance Pack when it is `USER_DECISION_REQUIRED`:

- flag ON
- behavior-changing env
- Gemini call increase
- mail volume increase
- source addition
- Scheduler/SEO change
- publish/review/hold/skip criteria change
- cleanup mutation
- rollback-impossible or external-impact-heavy change

Hold internally when any safety field is UNKNOWN. Do not ask the user to resolve UNKNOWN technical risk.

## 10. Post-Deploy Verify

Deploy complete is not DONE. After any production reflection, run only production-safe regression checks and record:

- image / revision
- env / flag
- service / job startup
- rollback target
- error trend
- mail count
- Gemini delta
- silent skip count
- Team Shiny From
- publish / review / hold / skip route health
- stop condition result

Allowed production-safe checks: read-only, logs, health, mail count, env/revision checks, Scheduler/job observation, sample article/candidate state, flag OFF/no-send/dry-run-equivalent checks, and existing notification route checks.

Forbidden production tests: bulk mail, source addition, Gemini increase, publish criteria change, cleanup mutation, SEO/noindex/canonical/301, rollback-impossible operation, user-GO-less flag ON, or experiments while mail impact is UNKNOWN.

If verify fails, classify as `HOLD` or `ROLLBACK_REQUIRED`; do not mark `OBSERVED_OK`.

## 11. Successful Session Close

Before closing a session:

- update `CURRENT_STATE.md`
- update `OPS_BOARD.yaml`
- ensure ACTIVE count is at most 2
- record unresolved user decisions as Decision Batch items only
- do not mark 298-Phase3 DONE while it is rolled back after regression
