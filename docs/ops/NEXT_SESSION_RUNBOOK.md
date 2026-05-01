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

Do not deploy, change env, change Scheduler, change SEO, add sources, or increase Gemini calls during startup.

## 3. Restore Current Board

Current major state:

- 298-Phase3: `HOLD_NEEDS_PACK`, `ROLLED_BACK_AFTER_REGRESSION`, flag OFF/absent, persistent ledger disabled, storm contained, second-wave risk OPEN.
- 293-COST: active only for design/Pack/test/rollback planning.
- 300-COST: active only for read-only source-side cost analysis.
- 299-QA: observe flaky/transient, not P0 by default.
- 282-COST: future user GO for flag ON after 293.
- 290-QA: future user GO for deploy Pack.
- 288-INGEST: future user GO for source addition Pack.

## 4. Codex Lane Handling

- Claude owns lane monitoring.
- If a lane is idle and there is an eligible low-risk subtask in the existing ticket order, Claude dispatches it.
- Eligible low-risk subtasks are read-only, doc-only, evidence, test plan, rollback plan, Acceptance Pack, or ticket cleanup.
- Do not dispatch code/deploy/env/Scheduler/source/Gemini/mail-routing work without the required user GO.
- Do not ask the user whether to dispatch a READY-incomplete low-risk subtask.

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

## 9. Stop Conditions

Stop and prepare a Decision Batch if:

- deploy is needed
- flag/env change is needed
- Scheduler change is needed
- SEO/source addition is needed
- Gemini calls would increase
- mail routing condition would change materially
- cleanup mutation is proposed
- rollback path is unclear
- mail volume impact is UNKNOWN
- candidate visibility is not guaranteed

## 10. Successful Session Close

Before closing a session:

- update `CURRENT_STATE.md`
- update `OPS_BOARD.yaml`
- ensure ACTIVE count is at most 2
- record unresolved user decisions as Decision Batch items only
- do not mark 298-Phase3 DONE while it is rolled back after regression