# OPERATING_LOCK — agent startup and hard-stop rules

Every Claude / Codex session must read this file before acting.

## source of truth

- Detailed board: `/home/fwns6/code/wordpressyoshilover/doc/README.md`
- Visible dashboard: `/home/fwns6/code/wordpressyoshilover/doc/active/assignments.md`
- Ticket folders: `doc/active/`, `doc/waiting/`, `doc/reference/`, `doc/done/YYYY-MM/`
- Execution order / status / owner / lane / blocked state / doc_path: follow `doc/README.md`
- Scope / acceptance / do-not-touch rules: follow the individual ticket doc

## role split

- Claude: field manager, accept, push, user-facing summary, risk-boundary judgment
- Codex A: ops / GCP / WP / mail / publish runner implementation
- Codex B: quality / evaluator / validator / SEO / SNS / X gate / mail-body implementation
- Codex-GCP: GCP runtime for repair, allowed WP article write, SNS topic processing, SEO/quality monitoring, mail digest generation, and X gate dry-run
- Authenticated executor: Claude shell / user shell / future deploy executor for live GCP mutation after repo work is ready
- User: live unlock, secret/env/scheduler/scope expansion, major policy decisions

## hard stops

- Do not display secrets, `.env` values, auth tokens, or `auth.json` contents.
- Do not use `git add -A`.
- Do not touch unrelated `logs/`, `build/`, front dirty files, or generated artifacts.
- Do not change Cloud Run / Scheduler / Secret Manager / live env unless the active ticket explicitly says so.
- Do not flip `RUN_DRAFT_ONLY`.
- Do not make X live posts before explicit live unlock.
- Do not bypass PUB-004 publish gates or PUB-005 X gates.
- Do not publish raw SNS signals directly; SNS topics must pass source recheck and publish gates.

## GCP live boundary

- Codex may implement repo changes, tests, Docker / Cloud Build config, deploy runbooks, and read-only GCP verification.
- Cloud Build submit, Cloud Run Job create/update, Scheduler create/update, IAM changes, Secret Manager changes, and live env changes must run through an authenticated executor.
- Codex auth failure on a live GCP mutation step is not treated as implementation failure when repo work and runbook are complete.
- Secret display and env mutation remain hard stops even for handoff-ready tickets.

## status rule

- Status changes require ticket doc move + README `doc_path` update + assignments update in the same commit, or an immediate doc-only follow-up commit.
- READY / IN_FLIGHT / REVIEW_NEEDED tickets live in `doc/active/`.
- READY_FOR_AUTH_EXECUTOR tickets live in `doc/waiting/` until an authenticated executor performs the live step.
- BLOCKED_USER / BLOCKED_EXTERNAL / PARKED tickets live in `doc/waiting/`.
- CLOSED tickets live in `doc/done/YYYY-MM/`.
- Do not leave CLOSED tickets in `doc/active/` or `doc/waiting/`.
- Use `BLOCKED_USER` when a decision, approval, or user-owned access handoff is still missing.
- Use `READY_FOR_AUTH_EXECUTOR` when implementation, runbook, and validation steps are ready and only an authenticated live executor remains.

## delegation rule

- Claude is the manager, not the default executor.
- When there are 2 or more READY tasks, Claude must delegate at least one concrete task to Codex-M / Codex A / Codex B unless a user-risk boundary blocks it.
- Codex-M handles board hygiene and status reconciliation.
- Codex A handles ops / GCP / WP / mail / publish implementation.
- Codex B handles quality / evaluator / SEO / SNS / X gate implementation.
- Claude keeps final judgment, user-facing summary, and dangerous-boundary decisions.

## startup report

After reading this file, an agent should report or internally lock:

- current mainline
- active READY / IN_FLIGHT work
- user / external blockers
- hard stops relevant to the task
- exact paths it may touch
