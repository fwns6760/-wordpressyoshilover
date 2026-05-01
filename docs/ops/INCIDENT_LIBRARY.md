# YOSHILOVER INCIDENT_LIBRARY

Last updated: 2026-05-01 JST

This file records reusable incident rules. It is not a session diary.

## Incident: P1 Mail Storm From Old Candidates

### Symptoms

- publish-notice sends old candidate mail repeatedly.
- sent count approaches or exceeds MAIL_BUDGET.
- old candidates recur after dedupe expiry.

### Current Standing

- Current storm is contained.
- 298-Phase3 is rolled back after regression.
- Phase3 is not DONE.
- Phase3 re-ON is forbidden without a new Acceptance Pack.

### Do

- Preserve normal review mail.
- Preserve 289 post_gen_validate notification mail.
- Preserve error mail.
- Estimate old candidate pool cardinality.
- Estimate first-send mail count.
- Define max mails/hour and max mails/day.
- Define stop condition.
- Keep rollback one-command where possible.

### Do Not

- Do not stop all mail.
- Do not pause Scheduler as a normal fallback.
- Do not reapply `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168`.
- Do not wait for pool exhaustion.
- Do not GO with UNKNOWN mail volume impact.
- Do not call Phase3 DONE while the flag is OFF after rollback.

### Required Tests

- old candidate pool count test
- first-send estimate test
- max/hour cap test
- max/day cap test
- normal review mail still sent
- 289 mail still sent
- error mail still sent
- rollback command verified

## Incident: Silent Skip

### Definition

A candidate is unacceptable if it disappears into logs, WP draft state, or internal ledgers without user-visible publish/review/hold/skip notification.

### Accepted Terminal States

- publish
- review notification
- hold notification
- skip notification

### Do

- Add durable reason.
- Add user-visible route.
- Test the route.
- Preserve existing publish/review/hold mail.
- Keep Gemini calls unchanged unless user GO approves an increase.

### Do Not

- Do not treat Cloud Logging alone as acceptance.
- Do not create a skip gate without a visible reason path.
- Do not enable 282 preflight before visible skip readiness.

## Incident: Post-Gen Validate Skip

### Standing Rule

289 is the correct lane for post_gen_validate skip visibility.

### Required Evidence

- skip ledger written
- publish-notice scanner reads it
- mail subject clearly says `post_gen_validate`
- duplicate suppression is bounded
- max_per_run behavior is known
- skipped payload counts are visible

### Known Gap To Watch

`body_contract_validate` failures must not remain log-only. If they are outside 289, add them as a subtask rather than creating a new unrelated ticket.

## Incident: Cost Gate Candidate Loss

### Standing Rule

Cost gates must not make candidates disappear.

### Order

1. candidate visibility
2. silent skip 0
3. cost estimate
4. preflight skip visible
5. flag ON decision

### Do Not

- Do not enable `ENABLE_GEMINI_PREFLIGHT` before 293/visibility readiness.
- Do not add sources before candidate visibility and mail impact are understood.

## Incident: Flaky / Transient Tests

### Standing Rule

Do not call a transient test failure P0 without repeatable evidence.

### Required Evidence

- failing command
- passing retry or repeated failure
- environment difference
- affected ticket
- whether production behavior is affected

### State

Use OBSERVE until repeatability is proven.

## Incident: Raw Codex Output Leakage

### Problem

Raw Codex answers can confuse the user and mix speculation with action.

### Rule

Claude must compress Codex output before user-facing reporting.

### User-Facing Output

Use Decision Batch. Include conclusion, evidence, risk, next action, and the one line the user should return if a decision is needed.