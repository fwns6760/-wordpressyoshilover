# YOSHILOVER ACCEPTANCE_PACK_TEMPLATE

Last updated: 2026-05-03 JST

This is the canonical Pack shape for:

- `USER_DECISION_REQUIRED`
- `CLAUDE_AUTO_GO` work that still needs normalized evidence
- read-only / doc-only / acceptance-draft work that must keep the same field split

Do not use a Pack to offload unresolved technical judgment to the user. If rollback, verify, cost, mail, Gemini, or blast-radius facts are unknown, the Pack stays `HOLD`.

## Canonical 13-item format

Every Pack must keep these 13 sections in this order:

1. `DECISION`
2. `EXECUTION`
3. `EVIDENCE`
4. `USER_GO_REQUIRED`
5. `USER_GO_REASON`
6. `NEXT_REVIEW_AT`
7. `EXPIRY`
8. `ROLLBACK_TARGETS`
9. `POST_DEPLOY_VERIFY`
10. `STOP_CONDITION`
11. `REGRESSION`
12. `MAIL_GEMINI_DELTA`
13. `OPEN_QUESTIONS`

## Field rules

- `DECISION`
  - write `recommendation`, `classification`, `decision_owner`, and a one-line `reason`
  - `classification` is `CLAUDE_AUTO_GO`, `USER_DECISION_REQUIRED`, or `HOLD`
- `EXECUTION`
  - split `scope` and `non_scope`
  - state whether live mutation exists; do not bury deploy/env/source/mail changes in prose
- `EVIDENCE`
  - keep 5 buckets even when empty: `commit`, `image`, `env`, `execution`, `log`
  - write `none` when not applicable; do not omit the bucket
- `USER_GO_REQUIRED`
  - always write `is` and `category`
  - doc-only / read-only / no-mutation drafts still write `is=false`, `category=none`
- `USER_GO_REASON`
  - if `USER_GO_REQUIRED.is=true`, choose exactly one category from the 9 canonical categories below
  - if `false`, write `none`
- `NEXT_REVIEW_AT`
  - state-based only
  - do not promise a wall-clock time unless a separate runbook already fixed that time
- `EXPIRY`
  - write the condition that invalidates the Pack
  - if fresh evidence or a new live mutation occurs, old Packs expire
- `ROLLBACK_TARGETS`
  - always split into 3 dimensions: `env`, `image`, `github`
  - use exact commands or explicit `none`
  - placeholders and "later decide" are treated as `HOLD`
- `POST_DEPLOY_VERIFY`
  - keep the section even for doc-only / read-only work
  - if no production reflection exists, set `required=false` and write the reason
- `STOP_CONDITION`
  - flat list of observable triggers only
  - if the stop condition cannot be observed, the Pack is incomplete
- `REGRESSION`
  - separate required safe checks from forbidden expansion
  - production-safe checks must stay read-only unless the ticket explicitly permits more
- `MAIL_GEMINI_DELTA`
  - state `unchanged`, `decrease`, or bounded `increase`
  - `unknown` is not allowed; `unknown => HOLD`
- `OPEN_QUESTIONS`
  - flat list only
  - empty list is valid

## USER_GO_REASON canonical categories(9)

Use exactly one of these when `USER_GO_REQUIRED.is=true`:

1. `deploy`
2. `flag_env`
3. `scheduler`
4. `seo`
5. `source_add`
6. `gemini_increase`
7. `mail_increase`
8. `wp_body`
9. `publish_state`

When `USER_GO_REQUIRED.is=false`, write `category: none`.

## Canonical skeleton

```yaml
DECISION:
  ticket:
  recommendation: GO | HOLD | REJECT | OBSERVED_OK
  classification: CLAUDE_AUTO_GO | USER_DECISION_REQUIRED | HOLD
  decision_owner: Claude | user
  reason:

EXECUTION:
  owner:
  scope:
  non_scope:
  live_mutation: none | deploy | env | scheduler | seo | source | mail | wp | mixed

EVIDENCE:
  commit:
    - hash:
      summary:
  image:
    current:
    target:
  env:
    add_or_change:
    remove_or_revert:
  execution:
    command_or_job:
    observed_result:
  log:
    commands:
    observed_signals:

USER_GO_REQUIRED:
  is: true | false
  category: none | deploy | flag_env | scheduler | seo | source_add | gemini_increase | mail_increase | wp_body | publish_state

USER_GO_REASON:
  summary:
  max_risk:
  rollback_ready: yes | no

NEXT_REVIEW_AT:
  trigger:

EXPIRY:
  invalidates_when:

ROLLBACK_TARGETS:
  env:
    apply:
    rollback:
    owner:
  image:
    current_live_before_apply:
    target_after_apply:
    rollback:
    owner:
  github:
    release_composition_commits:
    revert:
    owner:

POST_DEPLOY_VERIFY:
  required: true | false
  commands:
    - ...
  success_signals:
    - ...
  observed_status: NOT_RUN | PASS | FAIL | PARTIAL

STOP_CONDITION:
  - ...

REGRESSION:
  required_checks:
    - ...
  forbidden_expansion:
    - ...

MAIL_GEMINI_DELTA:
  mail_delta:
  gemini_delta:
  invariant:

OPEN_QUESTIONS:
  - ...
```

## Required invariants

- `CLAUDE_AUTO_GO` work still needs evidence, rollback anchors, and post-deploy verify if production reflection exists.
- `USER_DECISION_REQUIRED` work must keep the 13-section shape and compress the user ask to `OK / HOLD / REJECT`.
- `HOLD` means the blocker is internal; do not ask the user to resolve unknown technical fields.
- `release composition verify` and 3-dimension rollback anchors must exist before production reflection.
- Exclusion guards such as `hard_stop`, `duplicate`, `numeric`, `placeholder`, `source missing`, and `body_contract` cannot be relaxed silently inside a Pack.
- Ticket-specific visible intermediate states such as `queued_visible` may appear in a ticket doc, but the Pack must still show how they drain to a final outcome.

## Pack outcome rules

- `CLAUDE_AUTO_GO`
  - `USER_GO_REQUIRED.is=false`
  - all 13 sections still required
- `USER_DECISION_REQUIRED`
  - 13 sections required
  - append a one-line user reply request
- `HOLD`
  - blocker must appear in both `DECISION.reason` and `OPEN_QUESTIONS`
  - next review trigger must be explicit

## Addendum: 298-Phase3 re-ON packs

For `298-Phase3` re-ON work, also include:

- old candidate pool cardinality estimate
- expected first-send mail count
- max mails/hour
- max mails/day
- stop condition
- rollback command
- confirmation that `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` is currently OFF/absent before GO
- confirmation that persistent ledger bootstrap behavior is understood
- confirmation that normal review, 289, and error mail remain active

## Addendum: audit-derived mandatory checks for production reflection

Before any production reflection, the Pack must show:

1. release composition verify result
2. dirty worktree snapshot result
3. silent skip grep result
4. 3-dimension rollback anchor completeness
5. mail path LLM-free invariant result

## Forbidden Pack patterns

- "safe enough" without evidence
- "mail volume unknown but GO"
- "Gemini impact unknown but GO"
- "rollback later"
- "post-deploy verify later" without commands or owner
- multiple unrelated decisions in one Pack
- raw Codex output pasted without normalization

## Optional user reply block

If and only if `USER_GO_REQUIRED.is=true`, append:

```text
結論:
理由:
最大リスク:
rollback:
userが返すべき1行: OK / HOLD / REJECT
```
