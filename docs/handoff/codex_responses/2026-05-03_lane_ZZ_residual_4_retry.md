# 2026-05-03 Lane ZZ residual 4 retry

Scope: `64335 / 64331 / 64352 / 64390` only. Manual lane actions were limited to per-ID narrow history-row delete, single-ID guarded publish retry, and evidence capture. No `src/**`, `tests/**`, `config/**`, queue wipe, cursor wipe, or broad history wipe was performed.

## Final outcome

| post_id | final outcome | final hold / reason | WP status | publish |
| --- | --- | --- | --- | --- |
| 64335 | hold | `backlog_only` (`expired_lineup_or_pregame` lineage; widgets.js duplicate did **not** survive retry) | `draft` | no |
| 64331 | hold | `review_date_fact_mismatch_review` | `draft` | no |
| 64352 | hold | `review_date_fact_mismatch_review` | `draft` | no |
| 64390 | hold | `review_date_fact_mismatch_review` | `draft` | no |

Result: `publish` 0 / `real duplicate stop` 0 / `death-grave skip` 0 / `other legitimate hold` 4.

## Per-ID notes

### 64335

- Probe WP status: `draft` (`modified=2026-05-03T13:20:16+09:00`)
- Probe evaluator: `yellow`
- Key evaluator flags: `site_component_mixed_into_body`, `title_body_mismatch_partial`, `expired_lineup_or_pregame`
- Initial refused row deleted:
  - local backup: `/tmp/lane_ZZ_backup_20260503T230902/64335.deleted_rows.jsonl`
  - GCS backup: `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_ZZ_residual_4_retry/64335/live/64335.deleted_rows.jsonl`
  - deleted row was `review_duplicate_candidate_same_source_url` with `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
- Single-ID live retry report: `run_report.ts=2026-05-03T23:11:30.759324+09:00`, `status=skipped`, `hold_reason=backlog_only`
- Final conclusion: widgets.js false-positive was cleared, but the post is still not publishable because it is a stale lineup / backlog-only item.

### 64331

- Probe WP status: `draft` (`modified=2026-05-03T13:00:20+09:00`)
- Probe evaluator: `review`
- Key evaluator flags: `date_fact_mismatch_review`, `weak_source_display`, `roster_movement_yellow`, `site_component_mixed_into_body`
- Initial refused row deleted:
  - local backup: `/tmp/lane_ZZ_backup_20260503T230902/64331.deleted_rows.jsonl`
  - GCS backup: `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_ZZ_residual_4_retry/64331/live/64331.deleted_rows.jsonl`
- Single-ID live retry report: `run_report.ts=2026-05-03T23:14:09.406455+09:00`, `status=refused`, `hold_reason=review_date_fact_mismatch_review`
- Final conclusion: not a real duplicate; legitimate review hold remains.

### 64352

- Probe WP status: `draft` (`modified=2026-05-03T14:10:55+09:00`)
- Probe evaluator: `review`
- Key evaluator flags: `date_fact_mismatch_review`, `site_component_mixed_into_body`, `title_body_mismatch_partial`
- Initial refused row deleted twice because the first delete was overwritten by a concurrent main guarded-publish execution:
  - first local backup: `/tmp/lane_ZZ_backup_20260503T230902/64352.deleted_rows.jsonl`
  - second local backup used for verified delete: `/tmp/lane_ZZ_backup_20260503T230902/64352.retry2.deleted_rows.jsonl`
  - GCS backups:
    - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_ZZ_residual_4_retry/64352/live/64352.deleted_rows.jsonl`
    - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_ZZ_residual_4_retry/64352/live/64352.retry2.deleted_rows.jsonl`
- First live retry returned an empty `executed/refused` set because the stale refused row was already back in `guarded_publish_history.jsonl` and `attempted_post_ids` dedup short-circuited the run.
- Verified second delete: remote `guarded_publish_history.jsonl` confirmed `64352` absent before rerun.
- Second single-ID live retry report: `run_report.ts=2026-05-03T23:20:21.908633+09:00`, `status=refused`, `hold_reason=review_date_fact_mismatch_review`
- Final conclusion: not a real duplicate; legitimate review hold remains.

### 64390

- Probe WP status: `draft` (`modified=2026-05-03T18:45:39+09:00`)
- Probe evaluator: `review`
- Key evaluator flags: `date_fact_mismatch_review`, `weak_source_display`, `site_component_mixed_into_body`
- Initial refused row deleted:
  - local backup: `/tmp/lane_ZZ_backup_20260503T230902/64390.deleted_rows.jsonl`
  - GCS backup: `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_ZZ_residual_4_retry/64390/live/64390.deleted_rows.jsonl`
- Remote verify: `64390` absent from `guarded_publish_history.jsonl` before live rerun
- Single-ID live retry report: `run_report.ts=2026-05-03T23:22:59.183263+09:00`, `status=refused`, `hold_reason=review_date_fact_mismatch_review`
- Final conclusion: not a real duplicate; legitimate review hold remains.

## Public URLs

None. No row reached `status=sent`.

## Mail delta

- Actual publish-notice sends caused by Lane ZZ: `0`
- New queue/suppressed artifacts observed during this window:
  - `64335`: `status=suppressed`, `reason=BACKLOG_SUMMARY_ONLY`, `recorded_at=2026-05-03T23:15:38.446489+09:00`
- No new `publish` mail timestamp exists because no post was published.

## Background concurrency note

During Lane ZZ, the scheduler-backed main job `guarded-publish` also ran and touched the same IDs:

- `guarded-publish-c2w4n` completed around `2026-05-03 23:15 JST` and logged `64335`
- `guarded-publish-f2wnr` ran `2026-05-03T23:20:08Z` to `2026-05-03T23:20:50Z` and logged both `64335` and `64352`

This explains:

- extra `64335` `backlog_only` rows after the manual retry
- the first `64352` live retry no-op, because the refused row had already been restored into history before `attempted_post_ids` was recalculated

No evidence of a non-widgets real duplicate passing through to publish was found.

## Rollback per ID

Rollback means restoring the original pre-retry history row, not unpublishing content, because no content was published.

### 64335 rollback

1. Narrow-delete the latest `64335` `backlog_only` row from `guarded_publish_history.jsonl`.
2. Re-append `/tmp/lane_ZZ_backup_20260503T230902/64335.deleted_rows.jsonl` to `guarded_publish_history.jsonl`.

### 64331 rollback

1. Narrow-delete the latest `64331` `review_date_fact_mismatch_review` row.
2. Re-append `/tmp/lane_ZZ_backup_20260503T230902/64331.deleted_rows.jsonl`.

### 64352 rollback

1. Narrow-delete the latest `64352` `review_date_fact_mismatch_review` row.
2. Re-append `/tmp/lane_ZZ_backup_20260503T230902/64352.retry2.deleted_rows.jsonl`.

### 64390 rollback

1. Narrow-delete the latest `64390` `review_date_fact_mismatch_review` row.
2. Re-append `/tmp/lane_ZZ_backup_20260503T230902/64390.deleted_rows.jsonl`.
