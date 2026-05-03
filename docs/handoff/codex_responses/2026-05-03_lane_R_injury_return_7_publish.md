# 2026-05-03 Lane R injury/return 7 publish

作成: 2026-05-03 21:03 JST

## mode

- live ops request received
- target set fixed by user:
  - `63175`
  - `63385`
  - `63517`
  - `63661`
  - `64321`
  - `64324`
  - `64332`
- result: **stopped after rollback**
- code / tests / config changes: `0`

## summary

- Step 1 backup verification passed.
- Step 2 was narrowed from `7-row delete at once` to `1-row delete -> 1 execution -> verify` because the current `guarded-publish` job image does not expose a per-post input override. Deleting all 7 rows at once would have violated the user's sequential requirement.
- `63175` was re-evaluated once and remained `refused / hard_stop_death_or_grave_incident`.
- `63385` was partially attempted, but the live state entered a transient malformed-JSONL window and both the manual execution and the next natural scheduler execution failed with:
  - `Unterminated string starting at: line 1 column 172 (char 171)`
- rollback was applied from the last known-good full history file.
- the next natural execution after rollback (`guarded-publish-gd5bd`, 21:00 JST slot) completed successfully, so the live runner recovered.
- no post reached `publish`.
- no publish-notice mail was sent.

## Step 1 existing backup verification

Verified file:

- `/tmp/lane_O_backup_20260503T200906/dedupe_pre.jsonl`

Verification result:

- line count: `7`
- all rows:
  - target `post_id` only
  - `status=refused`
  - `hold_reason=hard_stop_death_or_grave_incident`
- exact IDs matched:
  - `63175`
  - `63385`
  - `63517`
  - `63661`
  - `64321`
  - `64324`
  - `64332`

## Step 2 fresh live backup and diff prep

Fresh backup root:

- local: `/tmp/lane_R_backup_20260503T203605`
- remote:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_R_injury_return_7_publish/guarded_publish_history.before.jsonl`
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_R_injury_return_7_publish/guarded_publish_history.deleted_rows.jsonl`

Fresh live snapshot facts:

- source object: `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
- snapshot row count at 20:39 JST: `173687`
- total historical rows for the 7 target IDs: `35`
- current 24h dedupe rows for the target set: `7`

24h rows in scope:

| post_id | ts (JST) | status | hold_reason |
|---|---|---|---|
| 64321 | 2026-05-03T12:10:39.035340+09:00 | refused | hard_stop_death_or_grave_incident |
| 64324 | 2026-05-03T12:25:39.330058+09:00 | refused | hard_stop_death_or_grave_incident |
| 64332 | 2026-05-03T13:05:39.198788+09:00 | refused | hard_stop_death_or_grave_incident |
| 63661 | 2026-05-03T19:05:39.742769+09:00 | refused | hard_stop_death_or_grave_incident |
| 63517 | 2026-05-03T19:05:39.742769+09:00 | refused | hard_stop_death_or_grave_incident |
| 63385 | 2026-05-03T19:05:39.742769+09:00 | refused | hard_stop_death_or_grave_incident |
| 63175 | 2026-05-03T19:05:39.742769+09:00 | refused | hard_stop_death_or_grave_incident |

## Step 3 actual live actions

### 3-A. `63175`

Pre-delete verify:

- fresh live history download:
  - `/tmp/lane_R_backup_20260503T203605/63175/guarded_publish_history.live_before.jsonl`
- row count before delete: `173961`
- exactly one current 24h refused row matched:
  - `63175`
  - `2026-05-03T19:05:39.742769+09:00`
  - `hard_stop_death_or_grave_incident`

Delete apply:

- deleted rows: `1`
- after row count: `173960`
- remote verify after upload:
  - `63175` current 24h refused rows: `0`
  - other 6 target IDs still present

Manual re-eval:

- execution: `guarded-publish-nzc4l`
- run_by: `fwns6760@gmail.com`
- completed successfully
- evaluator summary in logs:
  - `would_publish=0`
- target outcome from execution logs:
  - `post_id=63175`
  - `status=refused`
  - `hold_reason=hard_stop_death_or_grave_incident`

Interpretation:

- `63175` was reclassified back into the same hard stop.
- no publish happened.
- this matches the user-defined `skip + record + continue` branch.

### 3-B. `63385`

Pre-delete verify:

- fresh live history download:
  - `/tmp/lane_R_backup_20260503T203605/63385/guarded_publish_history.live_before.jsonl`
- row count before delete: `174233`
- exactly one current 24h refused row matched:
  - `63385`
  - `2026-05-03T19:05:39.742769+09:00`
  - `hard_stop_death_or_grave_incident`

Delete apply:

- deleted rows: `1`
- after row count: `174232`

Failure window:

- verify download taken immediately after the upload produced a truncated local file and could not be parsed.
- manual execution:
  - `guarded-publish-qcfp8`
  - failed
- next natural scheduler execution:
  - `guarded-publish-zx2nh`
  - failed
- both failures logged the same parser error:
  - `Unterminated string starting at: line 1 column 172 (char 171)`

Stop decision:

- this crossed the live safety boundary.
- no additional target IDs were attempted after this point.

Rollback:

- restored the full last known-good history file from:
  - `/tmp/lane_R_backup_20260503T203605/63385/guarded_publish_history.live_before.jsonl`
- post-rollback recovery signal:
  - next natural execution `guarded-publish-gd5bd` completed successfully in the 21:00 JST slot

Interpretation:

- `63385` did not reach a valid re-evaluation outcome.
- the delete attempt was rolled back.
- no publish happened.

### 3-C. untouched after stop

These IDs were **not re-run** after the `63385` failure window:

- `63517`
- `63661`
- `64321`
- `64324`
- `64332`

## Step 4 current per-id outcome

Latest live history rows after rollback and 21:00 JST natural recovery:

| post_id | latest ts (JST) | outcome | hold_reason | public URL | mail sent timestamp |
|---|---|---|---|---|---|
| 63175 | 2026-05-03T20:49:06.026824+09:00 | draft kept | hard_stop_death_or_grave_incident | - | - |
| 63385 | 2026-05-03T19:05:39.742769+09:00 | rollback to original draft state | hard_stop_death_or_grave_incident | - | - |
| 63517 | 2026-05-03T19:05:39.742769+09:00 | draft kept | hard_stop_death_or_grave_incident | - | - |
| 63661 | 2026-05-03T19:05:39.742769+09:00 | draft kept | hard_stop_death_or_grave_incident | - | - |
| 64321 | 2026-05-03T12:10:39.035340+09:00 | draft kept | hard_stop_death_or_grave_incident | - | - |
| 64324 | 2026-05-03T12:25:39.330058+09:00 | draft kept | hard_stop_death_or_grave_incident | - | - |
| 64332 | 2026-05-03T13:05:39.198788+09:00 | draft kept | hard_stop_death_or_grave_incident | - | - |

Mail observation:

- publish-notice logging showed only `REVIEW_EXCLUDED` skips for these IDs.
- no `status=sent` evidence was found for any of the 7 IDs.

mail delta actual:

- `0`

## Step 5 rollback procedure per id

### `63175`

- current live state already contains a new refused row from `guarded-publish-nzc4l`
- no WP rollback is needed because no publish happened
- if a future live retry is desired:
  - remove only the current 24h refused row for `63175`
  - re-run in an isolated safe window

### `63385`

- rollback already applied
- restored source:
  - `/tmp/lane_R_backup_20260503T203605/63385/guarded_publish_history.live_before.jsonl`
- no WP rollback is needed because no publish happened

### `63517`, `63661`, `64321`, `64324`, `64332`

- rollback not needed
- no live mutation was applied to these IDs in Lane R

## deleted entry count

- expected by original plan: `7`
- actual safe live deletions attempted:
  - `63175`: `1`, then re-evaluated, current state reinserted by job as refused
  - `63385`: `1`, then rolled back by full-history restore
- net live end-state:
  - no target row remains deleted without a compensating reinsert or rollback

## remaining risk

- the underlying classifier still returns `hard_stop_death_or_grave_incident` for this injury/return class; `63175` proved that a simple dedupe unlock does not rescue every target.
- the current job image has no per-post input override, so the user's ideal `full 7-row delete + per-id rerun` procedure cannot be executed safely from this environment.
- the 20:55 JST slot showed a transient malformed-JSONL window during `63385` handling. Although rollback and the 21:00 JST natural recovery restored service, that failure mode should be treated as unresolved until a safer per-id execution path exists.

## next user action

1. treat Lane R as **stopped, partially executed, rolled back**.
2. do not continue the remaining 5 IDs with the current live procedure.
3. before any next rescue attempt, add one of these protections:
   - a true per-post guarded-publish execution path in the job image, or
   - a controlled scheduler pause / lock window owned by the authenticated executor.
