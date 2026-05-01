# YOSHILOVER CURRENT_STATE

Last updated: 2026-05-01 JST
Owner: Claude updates this file as the operations source of truth.

This file is the first operational document to read at session start. If this file conflicts with session logs, old handoffs, old POLICY text, or old OPS_BOARD entries, this file and the current docs/ops set win.

## Today Decisions

- The user is not the work owner for every ticket.
- The user is only the decision owner for high-risk changes.
- Claude is the field lead.
- Codex is the field developer / worker.
- Raw Codex answers must not be sent directly to the user.
- Do not ask the user small fragmented questions.
- Report decisions in a Decision Batch.
- When a Codex lane becomes idle, Claude must detect it and autonomously feed the next low-risk subtask from the existing ticket order.
- The user discovering an idle Codex lane is an operations failure.
- Read-only, doc-only, evidence collection, test plans, rollback plans, Acceptance Packs, and ticket cleanup are Claude autonomous GO.
- Deploy, flag/env changes, Scheduler changes, SEO changes, source additions, Gemini call increases, major mail routing changes, cleanup mutation, and non-rollbackable changes require user GO.
- ACTIVE is limited to at most 2 tickets.
- The user decides time boundaries such as "today is done" or "continue."
- Claude should proceed by risk, regression, and cost gates, not by the clock.
- "Too cautious so everything stops" is REJECT.
- "There is time, so do everything" is REJECT.

## Current Incident State

### 298-Phase3

- Status: `HOLD_NEEDS_PACK`
- Phase label: `ROLLED_BACK_AFTER_REGRESSION`
- DONE is forbidden for this ticket until a new Acceptance Pack passes and the follow-up observation succeeds.
- The image was deployed, but the feature flag was rolled back.
- `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` is OFF or absent.
- Persistent ledger behavior is disabled.
- The current mail storm is contained.
- The tomorrow-morning second-wave risk remains OPEN.
- Phase3 re-ON is forbidden until the following are known:
  - old candidate pool cardinality estimate
  - expected first-send mail count
  - max mails/hour
  - max mails/day
  - stop condition
  - rollback command and rollback owner
- If any of the above is UNKNOWN, GO is forbidden.

### Mail Storm Rules

- Do not stop all mail.
- Do not pause the Scheduler as a normal fallback.
- Do not reapply `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`.
- Do not wait for pool exhaustion as a strategy.
- If mail volume impact is UNKNOWN, GO is forbidden.
- MAIL_BUDGET violation is P1.
- Repeated old-candidate mail is P1 recurrence.
- Normal review mail, 289 notifications, and error notifications must remain active.

## Current Ticket Board Summary

| ticket | current state | allowed now | user GO required for |
|---|---|---|---|
| 293-COST | ACTIVE, doc/test/rollback planning | design, Pack, tests, rollback plan | deploy, flag/env, Gemini increase |
| 300-COST | ACTIVE, read-only analysis | source-side guarded-publish cost analysis | implementation/deploy |
| 299-QA | OBSERVE | flaky/transient evidence and baseline recording | none unless it becomes deploy/flag work |
| 298-Phase3 | HOLD_NEEDS_PACK | Pack reconstruction only | any re-ON, deploy, flag/env |
| 282-COST | FUTURE_USER_GO | Pack after 293 | flag ON |
| 290-QA | FUTURE_USER_GO | deploy decision Pack | deploy |
| 288-INGEST | FUTURE_USER_GO | source-add decision Pack | source addition |

## Decision Batch Format

Use this format when reporting to the user:

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

## Next Session Read Order

1. `docs/ops/CURRENT_STATE.md`
2. `docs/ops/POLICY.md`
3. `docs/ops/OPS_BOARD.yaml`
4. `docs/ops/NEXT_SESSION_RUNBOOK.md`
5. `docs/ops/INCIDENT_LIBRARY.md`
6. `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`

Session logs, handoff logs, and codex responses are history only. They are not current policy.

## Immediate Operating Posture

- Keep 298-Phase3 OFF.
- Continue 293-COST and 300-COST only inside allowed low-risk boundaries.
- Keep 299-QA as observe, not P0 by default.
- Do not ask the user to choose READY-incomplete work.
- Do not create new tickets unless the issue cannot fit into an existing active/hold ticket.
- Do not expose raw Codex output to the user; Claude compresses it into a Decision Batch.