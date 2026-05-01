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

## Incident: P1 Mail Storm 2026-05-01 Second-Wave Risk

### Summary

- `2026-05-01` の P1 mail storm は `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168` 単独事故ではなく、old-candidate sink-side first emit が `99+` backlog pool に再露出したことで `MAIL_BUDGET` を破った。

### Timeline

- `09:00 JST`: first wave started after the `168h` review-window hotfix.
- `09:55 JST`: first wave stopped naturally; the storm did not require Scheduler stop or global mail stop.
- `13:00 JST`: `298-Phase3` deploy continuation started.
- `13:24 JST`: flag-ON observe looked green, but only the first protected batches had been sampled.
- `13:35 JST`: second storm was detected after re-ON; `cap=10` held per run but not per hour.
- `13:55 JST`: rollback removed `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` and restored pre-ON behavior.
- `14:15 JST`: post-rollback observe showed `errors=0`, `silent skip=0`, old-candidate emit `0`, and normal paths alive.
- `17:00 JST`: production health observe remains required before any new GO framing.

### Root Causes

- `guarded-publish */5` trigger reevaluated `backlog_only` rows every run, so old candidates kept becoming eligible for publish-notice scanning.
- `24h dedup` expiry reopened old-candidate first emits the next day instead of permanently draining the historical pool.
- `cap=10` limited only per-run sends and did not make the overall system budget-safe.
- pool cardinality itself was too large; a `99+ unique post_id` first emit is already a P1 budget breach even if every single run looks capped.

### Judgment Errors

- treating the `env=168` hotfix as the main fix path was counterproductive; it changed the review window but did not remove the sink-side replay behavior.
- turning `Phase3` flag ON without seeding or neutralizing the existing pool reopened the unregistered backlog.
- Codex preflight stop chaining compressed safe observe time and delayed the cleaner `target=HEAD` deploy path.

### Preserved Boundaries

- `Team Shiny From` remained unchanged.
- `289 post_gen_validate` notification remained alive.
- Scheduler cadence remained unchanged.
- X lane remained unchanged.
- `live_update` remained unchanged.
- Gemini call volume remained unchanged.

### Prevention Anchors

- treat scan-window expansion as a replay-risk change, not as a harmless mail-tuning change.
- never call `cap` alone safe; per-run limits do not replace hour/day budget modeling.
- require first-emit cardinality estimate before GO whenever historical pools can reopen.
- prioritize source-side fixes when sink-side caps still leave a budget-breaking first wave.
- use `target=HEAD` dynamic deploy preflight so doc-only commits do not create false deploy stops.

### Related Commit / Ticket

- tickets: `298-Phase3`, `299-QA`, `300-COST`, `289-OBSERVE`
- commits: `d44594a` (`298` once-only suppression), `7d0c9a5` (`298` deploy result), `a3871f2` (`298` incident evidence), `cdd0c3f` (`298` second-wave pack), `cf86e88` (`298` unknown-close evidence)

### 2026-05-02 09:00 JST Second-Wave Risk OPEN

- cardinality estimate remains `99+` unique old-candidate `post_id`; this is enough to break `MAIL_BUDGET 30/h` on first emit.
- `298-Phase3 v4 Case A` Pack is the planned user-facing mitigation proposal for the next morning.
- keep monitoring anchored to `MAIL_BUDGET 30/h・100/d`, `silent skip 0`, and `Team Shiny` invariants.
