# 205 GCP runtime drift audit

- priority: P0.5
- status: WAITING
- owner: Codex A / Claude
- lane: A
- parent: 155 / 199 / 200 / 202

## Goal

2026-04-29 queue triage:

- still useful as a read-only runtime drift audit
- moved out of `active/` because the immediate work is template / numeric hallucination hardening
- bring back only when Cloud Run image, Scheduler, or log drift is suspected

- detect cases where repo state moved but GCP runtime stayed behind
- keep the ticket strictly read-only

## Audit Targets

- Cloud Run Job image tags vs repo HEAD / intended feature commit
- Cloud Scheduler enabled / disabled state and cadence
- WSL cron remnants after GCP migration
- latest execution result for guarded-publish / draft-body-editor / publish-notice
- whether publish-notice mail actually contains the expected X candidate block
- guarded-publish / draft-body-editor / publish-notice GCS history artifacts

## Evidence Sources

- read-only `gcloud`
- read-only Gmail search / sample read when needed
- local cron / automation config inspection
- existing GCS history references and repo docs

## Non-Goals

- no Cloud Build submit
- no Cloud Run Job update
- no Scheduler update
- no IAM / Secret / env mutation
- no WP write
- no X post

## Expected Output

- current live image tag per target lane
- latest execution snapshot
- drift summary: matched / stale / inconclusive
- next action separated into:
  - no-op
  - doc clarify
  - follow-up fix ticket
  - authenticated executor handoff

## Acceptance

- drift surfaces are enumerated in one place
- mutation remains explicitly forbidden
- any repair, redeploy, or WP change is deferred to a separate ticket
