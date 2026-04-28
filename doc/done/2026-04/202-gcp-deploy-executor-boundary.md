# 202 GCP deploy executor boundary

- priority: P0.5
- status: CLOSED
- owner: Claude / Codex A
- lane: A
- parent: 155 / 177 / 197 / 199

## Close note(2026-04-28)

- authenticated executor boundary is now reflected in the root board / assignments operating model.
- current active lanes are Codex A / Codex B only; Codex-M is not an active dispatch target.

## Background

- recent live-mutation tickets showed a repeated mismatch:
  - Codex can finish repo work, runbooks, and read-only verification
  - the sandbox may still fail on authenticated GCP mutation steps
- if that boundary is treated as generic failure, tickets stall even when the implementation side is already done

## Policy

- Codex owns:
  - repo implementation
  - tests
  - Docker / Cloud Build config changes in git
  - deploy runbooks
  - read-only GCP verification
- authenticated executor owns:
  - Cloud Build submit
  - Cloud Run Job create / update
  - Cloud Scheduler create / update / pause / resume
  - IAM changes
  - Secret Manager changes
  - live env mutation
- authenticated executor may be:
  - Claude shell
  - user shell
  - future dedicated deploy executor

## Status Mapping

- use `BLOCKED_USER` when user judgment, approval, or user-owned access handoff is still missing
- use `READY_FOR_AUTH_EXECUTOR` when:
  - implementation is done
  - runbook is ready
  - validation steps are known
  - only authenticated live execution remains
- Codex auth failure at the mutation boundary is not, by itself, a failed implementation ticket

## Guardrails

- secret values are still never displayed
- env mutation is still a hard stop for Codex repo execution
- this policy does not reopen PC / WSL cron mainline or bypass GCP migration locks

## Ticket Impact

- `197` should read as `READY_FOR_AUTH_EXECUTOR`, not `BLOCKED_USER`, because the remaining work is authenticated live deploy
- `199` should move out of `BLOCKED_USER` once read-only facts show that the live image and executions are already moving

## Acceptance

- `READY_FOR_AUTH_EXECUTOR` is defined in shared docs
- repo responsibility vs live mutation responsibility is explicit
- future tickets stop waiting on Codex to perform live mutation from a structurally unsuitable shell
