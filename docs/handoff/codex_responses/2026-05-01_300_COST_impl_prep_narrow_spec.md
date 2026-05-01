# 300-COST impl-prep narrow spec

supersedes implementation-narrow scope of `2026-05-01_300_COST_ready_pack.md`

Date: 2026-05-01 JST  
Mode: Lane B round 16 / doc-only / production unchanged  
Status: implementation-prep only / future fire contract / current recommendation remains `HOLD`

Source alignment:

- `docs/handoff/codex_responses/2026-05-01_300_COST_ready_pack.md`
- `docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis_v2.md`
- `docs/handoff/codex_responses/2026-05-01_300_COST_pack_supplement.md`
- `docs/handoff/codex_responses/2026-05-01_293_COST_deploy_pack_v3.md`
- `docs/handoff/codex_responses/2026-05-01_298_v4_production_regression_test_plan.md`

This page narrows `300-COST` from future deploy judgment into an implementation-ready contract only. It does not authorize code change, deploy, env mutation, or production behavior change by itself.

## Decision Header

```yaml
ticket: 300-COST
recommendation: HOLD
decision_owner: user
execution_owner: Codex (impl) + Claude (push, deploy verify)
risk_class: medium-low (source-side dedupe, guarded-publish runner narrow fix)
classification: USER_DECISION_REQUIRED
user_go_reason: SOURCE_DEDUPE_BEHAVIOR_CHANGE
expires_at: 2026-05-02 09:00 JST Phase 6 checkpoint
```

Date note:

- `2026-05-02 09:00 JST` is the planned `298-v4` Phase 6 observation checkpoint.
- The exact earliest `298-v4` `24h` stability close recorded in the current ready pack remains `2026-05-02 14:15 JST`.
- `300-COST` stays `HOLD` until the full gate is green: `298-v4` Phase 6 verify, exact `24h` stable close, and `293-COST` deploy completion.

## 1. write_scope

Primary touch set for the future implementation round:

- `src/guarded_publish_runner.py`
- `tests/test_guarded_publish_runner_dedupe_idempotent.py`

Optional secondary touch, only if helper extraction is strictly needed:

- `src/cron_eval.py`

Write-scope rules:

- Keep the change inside the current source-side guarded-publish evaluation path.
- `src/cron_eval.py` does not exist today. Create it only if the idempotent `cron_eval.json` helper cannot remain private to `guarded_publish_runner.py`.
- Do not widen scope to `src/tools/run_guarded_publish_evaluator.py`, `bin/guarded_publish_entrypoint.sh`, or other evaluator entrypoints in the first impl round unless a separate doc update re-opens scope.

Do not read or touch:

- `src/publish_notice_*`
- `src/mail_*`
- `src/wordpress_*`
- `src/gemini_*`
- `config/rss_sources.json`

## 2. change_scope

Allowed behavior change is narrow and source-side only:

- Prevent duplicate reevaluation work for the same `post_id` when the latest visible guarded history state is unchanged.
- Treat unchanged as the same `post_id` plus the same latest `status`, `judgment`, and `hold_reason`.
- When unchanged `backlog_only` is detected, skip the repeated reevaluation append and emit an explicit runner log event.
- Preserve the already-existing visible ledger row instead of creating a fresh duplicate row.
- Keep `cron_eval.json` trigger timestamp append idempotent inside the same generation flow. A second identical write attempt for the same `post_id` must be a no-op and must not overwrite the first timestamp.

Must remain unchanged:

- `backlog_only` routing semantics
- `refused` routing semantics, including the current `24h` refused dedupe behavior
- `proposed` path semantics
- actual publish path semantics
- mail class, recipient, subject, cap, sender, and downstream scanner policy

## 3. test_cases

The future impl round should land at least the following targeted cases:

1. Existing ledger row for the same `post_id` with unchanged latest visible state results in source-side reevaluation skip, no new history row append, and an explicit log event.
2. New `post_id` with no prior ledger state follows normal evaluation and appends exactly one history row.
3. Same `post_id` with changed latest visible state still evaluates normally and appends a fresh row.
4. `cron_eval.json` idempotent trigger timestamp append is a no-op on the second identical write and leaves the file payload unchanged.
5. `backlog_only` narrow path remains unchanged for candidates that should still be visible as `backlog_only`.
6. `refused` path remains unchanged, including the existing `24h` refused-history dedupe contract.
7. `proposed` path remains unchanged for eligible candidates.
8. mail-volume-facing behavior remains unchanged: no new mail class, no new emit path, no `MAIL_BUDGET` delta expectation.

Targeted future command set for the implementation round:

- `python3 -m unittest tests.test_guarded_publish_runner`
- `python3 -m unittest tests.test_guarded_publish_backlog_narrow`
- `python3 -m unittest tests.test_guarded_publish_runner_dedupe_idempotent`

## 4. runtime_rollback

This narrow spec intentionally overrides the earlier env-gated draft assumption. The future impl contract here is flag-less.

- env rollback: none for this narrow spec
- env rollback path: not applicable
- image rollback anchor: capture the exact pre-300 guarded-publish image digest/SHA immediately before deploy
- image rollback command: `gcloud run jobs update guarded-publish --project=baseballsite --region=asia-northeast1 --image=<pre_300_exact_sha>`
- expected image rollback time: `~2-3 min`

If a future implementation proposal reintroduces an env knob, that is a separate phase and requires a refreshed pack and user judgment.

## 5. source_rollback

Source rollback remains the third rollback dimension under `POLICY §16.4`:

- `git revert <impl_commit_sha>`
- Claude push path after revert: `git push origin master`
- record the actual impl commit SHA and its parent at fire time

Rollback anchor:

- last known good source family for the current dependency chain: `dab9b8e` and `10022c0`
- treat the exact pre-impl HEAD as the practical revert target for the implementation round

## 6. post_deploy_verify_plan

Future deploy verification must follow the same production-safe baseline used by the `298-v4` and `293-COST` packs.

Required checks:

1. image / revision match the intended deploy target
2. env / flag state matches expectation for a flag-less `300-COST` deploy
3. mail volume stays inside `MAIL_BUDGET 30/h, 100/d`
4. Gemini delta stays within `±5%` versus the `298-v4` stable baseline and should ideally remain flat
5. `silent skip = 0`
6. `MAIL_BRIDGE_FROM` and Team Shiny sender invariants remain unchanged
7. exact rollback target image SHA is written into the deploy log before observation starts

## 7. production_safe_regression_scope

Allowed:

- read-only observation
- log inspection
- health verification
- mail-count verification
- env observation
- revision observation
- Scheduler observation
- sample candidate observation
- dry-run reasoning
- existing notification-route observation

Forbidden:

- bulk mail experiments
- source addition
- Gemini increase
- publish criteria change
- cleanup mutation outside the narrow dedupe scope
- SEO scope
- rollback-impossible mutation
- flag ON without explicit user GO
- mail `UNKNOWN` experiments

## 8. stop_conditions

Any one of the following is an immediate stop condition for the future live round:

- rolling `1h sent > 30`
- `silent skip > 0`
- `errors > 0`
- `289 post_gen_validate` visible path decreases versus the `298-v4` stable baseline
- Team Shiny / `MAIL_BRIDGE_FROM` sender drift
- `publish / review / hold / skip` visibility contract breaks
- Gemini call volume exceeds `+5%`
- cache-hit ratio drifts by more than `±15pt`

## 9. dependencies

All items below must be green before `300-COST` moves from impl-ready to deploy-eligible:

- `298-v4` Phase 6 verify passes
- `298-v4` exact `24h` stability close passes; current ready-pack anchor is `2026-05-02 14:15 JST`
- `293-COST` image rebuild and flag ON are completed
- the exact pre-300 guarded-publish image digest/SHA is captured immediately before deploy

Interpretation:

- `2026-05-02 09:00 JST` is a checkpoint, not the exact earliest standalone GO timestamp
- `300-COST` remains sequenced after `298-v4` sink-side stability and after the `293-COST` image cycle is settled

## 10. estimated_impl_rounds

- `1-2` rounds
- expected split: `1` impl round for source dedupe + `1` round for targeted test/cleanup only if needed
- lane owner: `Codex B`

## 11. estimated_deploy_rounds

- `1` round
- scope: image rebuild, deploy, post-deploy verify, rollback anchor capture
- deploy execution remains user GO gated

## 12. user_facing_5_field_format

- 推奨: `HOLD` today / `GO` only after `298-v4` stable close and `293-COST` completion
- 理由: source-side dedupe should reduce repeated guarded-history growth and reevaluation cost without changing visible publish routing
- 最大リスク: an incorrect unchanged-state dedupe could break an existing visibility path and create `silent skip`
- rollback 可能か: `yes` via image rollback plus source revert, even without an env knob
- user reply: `OK` / `HOLD` / `REJECT`

## Net

- doc type: impl-prep narrow spec only
- production state: unchanged
- future impl blast radius: `guarded_publish_runner` source-side dedupe path only
- current decision: `HOLD`
