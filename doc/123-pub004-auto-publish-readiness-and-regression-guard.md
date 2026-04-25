# 123 pub004-auto-publish-readiness-and-regression-guard

## meta

- number: 123
- owner: Claude Code / Codex A if implementation is needed
- lane: A / Claude orchestration
- priority: P0.5
- status: READY
- parent: 105 / PUB-004-D
- created: 2026-04-26

## purpose

Full auto WordPress publish is not currently active. This ticket determines whether that is an intended safety stop or a regression, without doing any live publish.

Current observed state:
- PUB-004-A evaluator and PUB-004-B guarded runner exist.
- Guarded publish tests pass.
- WSL crontab has publish-notice mail only; no `PUB-004-WSL-CRON-AUTO-PUBLISH` line exists.
- Latest 105 dry-run artifact reports total 97 / Green 0 / Yellow 0 / Red 97 / cleanup 0 / publishable 0.
- Guarded publish history/yellow/cleanup logs are empty.

Therefore, this is not treated as a publish-code regression by default. It is treated as an activation/readiness block until proven otherwise.

## scope

Read-only readiness gate before any 105 live ramp or PUB-004-C cron activation:

1. Reconfirm current guarded publish test suite.
2. Re-read current draft evaluation artifact or regenerate evaluator output in dry-run only.
3. Produce a readiness summary:
   - publishable count
   - Red reason top 5
   - cleanup-rescuable candidates
   - absolute Red candidates
   - whether cron activation is allowed
4. If publishable count is 0, do not run live publish and do not add cron.
5. If publishable count is greater than 0, run guarded publish dry-run only with max burst 3 and report would_publish list.
6. Live publish remains blocked until the readiness summary is shown and an explicit 105 live decision is made.

## non-goals

- live WP publish
- crontab activation
- PUB-004-A filter retune
- Red to Yellow policy change
- `RUN_DRAFT_ONLY` flip
- Cloud Run env change
- X / SNS post
- mail real-send
- secret / `.env` display
- front/plugin changes

## regression guard

Before any live ramp:
- `python3 -m pytest tests/test_guarded_publish_evaluator.py tests/test_guarded_publish_runner.py tests/test_published_site_component_audit.py`
- confirm no `PUB-004-WSL-CRON-AUTO-PUBLISH` crontab line is added by this ticket
- confirm `logs/guarded_publish_history.jsonl` is not appended by dry-run
- confirm WP write calls are not made during evaluator/readiness checks
- confirm `RUN_DRAFT_ONLY` and Cloud Run env are untouched

## acceptance

1. Current state is classified as one of:
   - `safe_stop_all_red`
   - `ready_for_one_burst_dry_run`
   - `possible_regression_needs_retune`
   - `cron_missing_but_not_ready`
2. No live publish occurs.
3. No cron activation occurs.
4. Readiness summary names the next safe action.
5. If a regression is suspected, the fix is ticketed separately; this ticket does not retune filters.

## recommended current classification

`safe_stop_all_red` + `cron_missing_but_not_ready`

Reason:
- publishable count is 0
- cron line is absent
- tests pass
- no guarded publish attempts are logged

## next action after this ticket

- If still all Red: run 108 / 109 / 110 / 111 / 112 quality unblock tickets, then re-run 105 dry-run.
- If publishable > 0: proceed to 105 dry-run with PUB-004-B, then request explicit live burst decision.
- PUB-004-C cron activation only after at least one safe live burst succeeds and mail notification/dedup is verified.

## related files

- `doc/102-ticket-index-and-priority-board.md`
- `doc/118-pub004-red-reason-decision-pack.md`
- `doc/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`
- `doc/PUB-004-guarded-auto-publish-runner.md`
- `src/tools/run_guarded_publish_evaluator.py`
- `src/tools/run_guarded_publish.py`
- `tests/test_guarded_publish_evaluator.py`
- `tests/test_guarded_publish_runner.py`
- `tests/test_published_site_component_audit.py`
