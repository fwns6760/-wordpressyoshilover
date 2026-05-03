# 2026-05-03 Lane W2 death/grave deploy recovery

作成: 2026-05-03 22:38 JST

## mode

- live ops request received
- scope: Lane W2 deploy + env apply + narrow recovery for the 7 Lane R death/grave stuck IDs
- code / tests / config edits: `0`
- non-scope jobs / scheduler / cursor / queue wipe / other post IDs: untouched
- git push: not run

## Step 1 release composition

Verified on repo state before the build export:

- `git log --oneline ec250dc..3ae845a -- src/guarded_publish_evaluator.py`
  - `8bde7cf bug-004-291: broaden death_or_grave classifier exempt for injury/return/coach (default OFF)`

Important runtime note:

- while the build was being prepared, `HEAD` advanced from `3ae845a` to `0f5e95a` because another lane committed a **doc-only** record
- guarded-publish build inputs had **no diff** across `3ae845a..0f5e95a`
- the clean export used for the build stayed:
  - `/tmp/guarded-publish-build-3ae845a.aOFwyY`

Conclusion:

- the runtime image used the expected guarded-publish source that already contained `8bde7cf`
- the later `0f5e95a` tag is safe because the concurrent commit did not change guarded-publish build inputs

## Step 2 image build

Build:

- build id: `87f86a7f-77e2-4e06-b132-80596a01d39f`
- status: `SUCCESS`
- duration: `3M20S`
- image tag applied: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:0f5e95a`
- image digest: `sha256:8618171111fc4ca9b7ad78c72b0a6385874eef35c2f11c0f900f5e7379f6564b`
- fully qualified digest:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish@sha256:8618171111fc4ca9b7ad78c72b0a6385874eef35c2f11c0f900f5e7379f6564b`

Build hygiene:

- dirty checkout was not sent directly
- the build used the clean `git archive` export only

## Step 3 image update + env apply

Updated Cloud Run Job:

- job: `guarded-publish`
- generation after apply: `25`
- image:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:0f5e95a`
- env confirmed on the job:
  - `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`
  - `ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT=1`
  - `ENABLE_DEATH_GRAVE_INJURY_RETURN_EXEMPT=1`
- post-apply natural executions observed:
  - `guarded-publish-j4qqf` at `2026-05-03T13:15:04.765422Z` → `EXECUTION_SUCCEEDED`
  - `guarded-publish-glksx` at `2026-05-03T13:30:05.329619Z` → `EXECUTION_SUCCEEDED`

## Step 4 backup + narrow recovery

Fresh backup root:

- local:
  - `/tmp/lane_W2_backup_20260503T221315`
- remote:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503T221315_lane_W2_death_grave_recovery/guarded_publish_history.before.jsonl`
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503T221315_lane_W2_death_grave_recovery/dedupe_pre.jsonl`
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503T221315_lane_W2_death_grave_recovery/meta.json`

Fresh 24h rows in scope:

- `63175` → `2026-05-03T20:49:06.026824+09:00`
- `63385` → `2026-05-03T19:05:39.742769+09:00`
- `63517` → `2026-05-03T19:05:39.742769+09:00`
- `63661` → `2026-05-03T19:05:39.742769+09:00`
- `64321` → `2026-05-03T12:10:39.035340+09:00`
- `64324` → `2026-05-03T12:25:39.330058+09:00`
- `64332` → `2026-05-03T13:05:39.198788+09:00`
- all 7 rows were still `refused / hard_stop_death_or_grave_incident`

Preflight after env apply:

- local evaluator with `ENABLE_DEATH_GRAVE_INJURY_RETURN_EXEMPT=1` surfaced:
  - `63385` as `yellow / publishable`
  - `63661` as `yellow / publishable`
  - `63175` as `review`
  - `63517` as `review`
  - `64321 / 64324 / 64332` absent from the current evaluator pool

Because the user goal was tonight's publish URL maximization, Lane W2 spent live mutation budget only on the 2 IDs that showed a publish-forward signal after the new flag went live.

### `63385`

Delete:

- deleted latest 24h refused row only
- local backup:
  - `/tmp/lane_W2_backup_20260503T221315/63385/deleted_rows.jsonl`
- remote backup:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503T221315_lane_W2_death_grave_recovery/63385.deleted_rows.jsonl`

Manual execution:

- execution: `guarded-publish-22xhf`
- completion: `2026-05-03T13:18:36.324070Z`
- status: `Completed=True`

Observed notify follow-up:

- `publish_notice/queue.jsonl` recorded:
  - `post_id=63385`
  - `status=suppressed`
  - `reason=PUBLISH_ONLY_FILTER`
  - `recorded_at=2026-05-03T22:21:57.400610+09:00`
  - `publish_time_iso=2026-04-24T16:50:55+09:00`

Interpretation:

- in this repo, `PUBLISH_ONLY_FILTER` is a **mail suppression**, not a publish blocker
- therefore `63385` is treated as having reached published state and then being suppressed at notify time

### `63661`

Delete:

- deleted latest 24h refused row only
- local backup:
  - `/tmp/lane_W2_backup_20260503T221315/63661/deleted_rows.jsonl`
- remote backup:
  - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503T221315_lane_W2_death_grave_recovery/63661.deleted_rows.jsonl`

Manual execution:

- execution: `guarded-publish-25hg6`
- status: completed successfully

Observed notify follow-up:

- `publish_notice/queue.jsonl` recorded:
  - `post_id=63661`
  - `status=suppressed`
  - `reason=PUBLISH_ONLY_FILTER`
  - `recorded_at=2026-05-03T22:36:35.371863+09:00`
  - `publish_time_iso=2026-04-26T17:00:29+09:00`

Interpretation:

- same as `63385`: published-state reached notify, then mail-suppressed by `PUBLISH_ONLY_FILTER`

### untouched in W2 final scope

These remained unmutated in W2 after the post-deploy preflight:

- `63175`
  - current post-deploy signal: `review`
- `63517`
  - current post-deploy signal: `review`
- `64321`
  - absent from current evaluator pool
- `64324`
  - absent from current evaluator pool
- `64332`
  - absent from current evaluator pool

Rationale:

- W2 goal was URL recovery tonight, not widening review-only risk
- after the new flag went live, only `63385` and `63661` showed a publish-forward signal

## Step 5 public URL + notify timestamps

Recovered-to-publish set:

| post_id | public URL | notify outcome | notify timestamp |
|---|---|---|---|
| `63385` | `https://yoshilover.com/63385` | `suppressed / PUBLISH_ONLY_FILTER` | `2026-05-03T22:21:57.400610+09:00` |
| `63661` | `https://yoshilover.com/63661` | `suppressed / PUBLISH_ONLY_FILTER` | `2026-05-03T22:36:35.371863+09:00` |

Remaining IDs:

| post_id | W2 outcome | public URL | notify |
|---|---|---|---|
| `63175` | draft maintained | - | - |
| `63517` | draft maintained | - | - |
| `64321` | draft maintained | - | - |
| `64324` | draft maintained | - | - |
| `64332` | draft maintained | - | - |

Note:

- the timestamps above are publish-notice queue timestamps, not actual sent-mail timestamps
- actual mail send count was `0` because both recovered posts were suppressed by the publish-only filter

## Step 6 mail delta actual

- `sent`: `0`
- `suppressed / PUBLISH_ONLY_FILTER`: `2`
- new recoveries with public URL evidence: `2`

## rollback

### runtime image / env

Revert the guarded-publish job to the pre-W2 live state:

```bash
gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:ec250dc

gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_DEATH_GRAVE_INJURY_RETURN_EXEMPT
```

### history

Restore the pre-W2 history snapshot:

- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503T221315_lane_W2_death_grave_recovery/guarded_publish_history.before.jsonl`

Or surgically restore only the deleted rows:

- `.../63385.deleted_rows.jsonl`
- `.../63661.deleted_rows.jsonl`
- `.../dedupe_pre.jsonl`

### post state

If the 2 recovered posts must be reverted to draft:

- change `63385` back to `draft`
- change `63661` back to `draft`

## next user action

- tomorrow's phone posting candidate set can use:
  - `https://yoshilover.com/63385`
  - `https://yoshilover.com/63661`
- if the remaining 5 IDs should still be forced through, do it as a separate follow-up lane with explicit permission to spend risk budget on `review` / evaluator-absent items
