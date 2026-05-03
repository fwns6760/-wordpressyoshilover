# 2026-05-03 Lane BB residual 5 publish forward

作成: 2026-05-04 00:37 JST

## mode

- live ops request received
- scope fixed to `64356 -> 64361 -> 64374 -> 64378 -> 64382`
- repo code / tests / config edits: `0`
- live mutation scope:
  - per-ID `guarded_publish_history.jsonl` narrow delete of the latest `24h refused` row only
  - per-ID deleted-row backup to local `/tmp/lane_BB_backup_20260503T234443/`
  - per-ID deleted-row backup upload to `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_BB_residual_5_publish_forward/<post_id>/live/`
- temporary execution helper:
  - created `guarded-publish-manual-single` to test single-ID runner execution without touching the main job template
  - deleted the helper job after use

## final outcome

| post_id | final outcome | final hold / reason | public URL | publish-notice |
| --- | --- | --- | --- | --- |
| `64356` | hold | `review_duplicate_candidate_same_source_url` reclassified to real duplicate of `64396` | - | no `sent` evidence |
| `64361` | publish | `status=sent` at `2026-05-04T00:10:45.437331+09:00` | `https://yoshilover.com/64361` | `sent` at `2026-05-04T00:16:03.093985+09:00` |
| `64374` | hold | `review_duplicate_candidate_same_source_url` reclassified to real duplicate of `64361` | - | no `sent` evidence |
| `64378` | hold | `review_duplicate_candidate_same_source_url` reclassified to real duplicate of `64396` | - | no `sent` evidence |
| `64382` | publish | `status=sent` at `2026-05-04T00:30:43.711948+09:00` | `https://yoshilover.com/64382` | `sent` at `2026-05-04T00:36:05.059709+09:00` |

Result summary:

- `publish`: `2`
- `real duplicate hold`: `3`
- `widgets.js hold survived`: `0`
- `death/grave stop`: `0`
- `placeholder/body_contract/numeric/date_fact hold`: `0`

## per-ID notes

### `64356`

- deleted row:
  - `ts=2026-05-03T14:40:41.009845+09:00`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
- local backup:
  - `/tmp/lane_BB_backup_20260503T234443/64356.deleted_rows.jsonl`
- remote backup:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_BB_residual_5_publish_forward/64356/live/64356.deleted_rows.jsonl`
- single-ID helper execution:
  - `guarded-publish-manual-single-94dc8`
- terminal row after retry:
  - `ts=2026-05-04T00:03:49.562287+09:00`
  - `status=refused`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_of_post_id=64396`
  - `duplicate_target_source_url=https://yoshilover.com/64343`
- reading:
  - widgets.js false-positive cleared
  - real duplicate remains, so this ID stops here

### `64361`

- deleted row:
  - `ts=2026-05-03T15:15:39.588862+09:00`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
- local backup:
  - `/tmp/lane_BB_backup_20260503T234443/64361.deleted_rows.jsonl`
- remote backup:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_BB_residual_5_publish_forward/64361/live/64361.deleted_rows.jsonl`
- publish was actually performed by the main `guarded-publish` `00:10 JST` execution:
  - main execution: `guarded-publish-g9dht`
  - terminal row:
    - `ts=2026-05-04T00:10:45.437331+09:00`
    - `status=sent`
    - `backup_path=/tmp/pub004d/cleanup_backup/64361_20260503T151045.json`
- publish-notice evidence:
  - `2026-05-04T00:16:03.093985+09:00`
  - `[result] kind=per_post post_id=64361 status=sent`
- secondary helper execution:
  - `guarded-publish-manual-single-rrrg6`
  - failed after the main publish had already happened; no extra publish evidence was observed

### `64374`

- deleted row:
  - `ts=2026-05-03T16:50:36.023288+09:00`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
- local backup:
  - `/tmp/lane_BB_backup_20260503T234443/64374.deleted_rows.jsonl`
- remote backup:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_BB_residual_5_publish_forward/64374/live/64374.deleted_rows.jsonl`
- main execution that retried it:
  - `guarded-publish-wvfbf`
- terminal row after retry:
  - `ts=2026-05-04T00:20:40.760205+09:00`
  - `status=refused`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_of_post_id=64361`
  - `duplicate_target_source_url=https://yoshilover.com/64319`
- reading:
  - widgets.js false-positive cleared
  - real duplicate remains, so this ID stops here

### `64378`

- deleted row:
  - `ts=2026-05-03T16:55:37.005558+09:00`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
- local backup:
  - `/tmp/lane_BB_backup_20260503T234443/64378.deleted_rows.jsonl`
- remote backup:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_BB_residual_5_publish_forward/64378/live/64378.deleted_rows.jsonl`
- main execution that retried it:
  - `guarded-publish-9m4kp`
- terminal row after retry:
  - `ts=2026-05-04T00:25:42.149969+09:00`
  - `status=refused`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_of_post_id=64396`
  - `duplicate_target_source_url=https://yoshilover.com/64343`
- reading:
  - widgets.js false-positive cleared
  - real duplicate remains, so this ID stops here

### `64382`

- deleted row:
  - `ts=2026-05-03T17:15:45.866096+09:00`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
- local backup:
  - `/tmp/lane_BB_backup_20260503T234443/64382.deleted_rows.jsonl`
- remote backup:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_BB_residual_5_publish_forward/64382/live/64382.deleted_rows.jsonl`
- publish was performed by the main `guarded-publish` `00:30 JST` execution:
  - main execution: `guarded-publish-ggs67`
  - log evidence:
    - `2026-05-04T00:30:48 JST` equivalent log line contained `post_id=64382`
    - `publish_link=https://yoshilover.com/?p=64382`
  - terminal row:
    - `ts=2026-05-04T00:30:43.711948+09:00`
    - `status=sent`
    - `backup_path=/tmp/pub004d/cleanup_backup/64382_20260503T153043.json`
- publish-notice evidence:
  - `2026-05-04T00:36:05.059709+09:00`
  - `[result] kind=per_post post_id=64382 status=sent`

## public URLs

- `https://yoshilover.com/64361`
- `https://yoshilover.com/64382`

## mail delta actual

- publish-notice `sent`: `2`
  - `64361` at `2026-05-04T00:16:03.093985+09:00`
  - `64382` at `2026-05-04T00:36:05.059709+09:00`
- targeted hold IDs with new publish-notice `sent`: `0`
- net publish-mail delta caused by Lane BB: `+2`

## rollback per ID

### `64356`

1. narrow-delete the latest `64356` real-duplicate row from `guarded_publish_history.jsonl`
2. re-append `/tmp/lane_BB_backup_20260503T234443/64356.deleted_rows.jsonl`

### `64361`

1. set WordPress post `64361` back to `draft`
2. narrow-delete the latest `64361` `status=sent` row from `guarded_publish_history.jsonl`
3. re-append `/tmp/lane_BB_backup_20260503T234443/64361.deleted_rows.jsonl`

### `64374`

1. narrow-delete the latest `64374` real-duplicate row from `guarded_publish_history.jsonl`
2. re-append `/tmp/lane_BB_backup_20260503T234443/64374.deleted_rows.jsonl`

### `64378`

1. narrow-delete the latest `64378` real-duplicate row from `guarded_publish_history.jsonl`
2. re-append `/tmp/lane_BB_backup_20260503T234443/64378.deleted_rows.jsonl`

### `64382`

1. set WordPress post `64382` back to `draft`
2. narrow-delete the latest `64382` `status=sent` row from `guarded_publish_history.jsonl`
3. re-append `/tmp/lane_BB_backup_20260503T234443/64382.deleted_rows.jsonl`
