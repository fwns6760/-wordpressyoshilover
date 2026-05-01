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

## 3. User GO Required

User GO is required for:

- production deploy
- flag/env change
- Scheduler enable/disable/pause/resume/frequency change
- SEO/noindex/canonical/301/sitemap/robots change
- source addition
- Gemini call increase
- major mail routing or notification-condition change
- cleanup mutation
- rollback-impossible or hard-to-rollback change
- publication policy relaxation

If the risk is unknown, treat it as HOLD.

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

Claude must stop and create an Acceptance Pack if a task crosses into User GO territory.

## 5. Codex Lane Policy

- ACTIVE tickets are limited to 2.
- Codex idle detection is Claude's responsibility.
- When a lane finishes, Claude reviews output, verifies scope, updates the board, and then dispatches the next eligible low-risk subtask.
- Do not dispatch work just to keep Codex busy.
- Do not dispatch outside the current ticket order to avoid boredom or time pressure.
- "慎重すぎて全停止" is REJECT.
- "時間があるから全部やる" is REJECT.
- Time boundaries are set by the user. Claude gates by risk, regression, and cost.

## 6. Status Vocabulary

Allowed current states:

- `ACTIVE`
- `OBSERVE`
- `READY`
- `HOLD_NEEDS_PACK`
- `FUTURE_USER_GO`
- `DONE`
- `FROZEN`
- `DEEP_FROZEN`
- `DEPRECATED`

Do not use:

- `DONE_PARTIAL`
- `NOT_DONE`
- ambiguous "maybe done" labels

`DONE` requires evidence. A code commit alone is not DONE. For production behavior, DONE requires deploy evidence and observation evidence when applicable.

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