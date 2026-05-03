# 2026-05-03 Lane Z mass publish

作成: 2026-05-03 22:00 JST

## mode

- request type: live ops
- user live unlock: received (`もう流して`)
- code / tests / config changes: `0`
- live mutation scope:
  - `guarded_publish_history.jsonl` narrow delete for `64328` only
  - backup upload to `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_Z_mass_publish/`
- result: **STOP after first candidate**

## Step 1 stuck draft scan

Authoritative source:

- `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
- local mirror used for scan:
  - `/tmp/lane_z_guarded_publish_history.jsonl`
  - refreshed before mutation:
    - `/tmp/lane_z_guarded_publish_history_after_manual.jsonl`

Snapshot facts from latest-entry-per-post scan:

- latest `refused` / `skipped` within last `72h`: `425`
- latest `refused` / `skipped` older than `72h`: `8`

Recent latest-state hold counts:

| hold_reason | count |
|---|---:|
| `hard_stop_lineup_duplicate_excessive` | `141` |
| `backlog_only` | `137` |
| `hard_stop_farm_result_placeholder_body` | `51` |
| `hard_stop_death_or_grave_incident` | `31` |
| `review_duplicate_candidate_same_source_url` | `23` |
| `review_date_fact_mismatch_review` | `22` |
| `hard_stop_lineup_no_hochi_source` | `11` |
| `hard_stop_ranking_list_only` | `3` |
| `review_score_order_mismatch_review` | `3` |
| `review_farm_result_required_facts_weak_review` | `2` |
| `hard_stop_win_loss_score_conflict` | `1` |

## Step 2 filter result

### stop / exclude buckets

- real duplicate stop:
  - `64292`
    - latest refused row already points to real site URL
    - `duplicate_target_source_url=https://yoshilover.com/64274`
- death/grave retry list after Lane W:
  - `63175`
  - `63385`
  - `63517`
  - `63661`
  - `64321`
  - `64324`
  - `64332`
- stale / backlog-only bucket:
  - excluded from this lane based on prior exact-date recheck
  - no live mutation attempted for `backlog_only` latest rows

### selected D candidates

These were the only rows with enough title/source evidence to justify live movement without touching the death/grave retry class or blind unreconstructable rows.

| post_id | latest pre-run hold | evidence used | decision before live retry |
|---|---|---|---|
| `64328` | `review_duplicate_candidate_same_source_url` | reconstructed title `【巨人】主力続々カムバック 泉口友汰＆山崎伊織が実戦復帰 ４番はリチャード……`; source `https://twitter.com/hochi_giants/status/2050780711846617128`; latest duplicate target `widgets.js` | attempt first |
| `64335` | `review_duplicate_candidate_same_source_url` | reconstructed title `巨人スタメン 甲子園 スタメン 【巨人】 【阪神】 4吉川 7高`; source `https://twitter.com/hochi_giants/status/2050791476620296421`; latest duplicate target `widgets.js` | pending behind `64328` |
| `64331` | `review_date_fact_mismatch_review` | subject evidence `RT 【公式】ジャイアンツタウンスタジアム: 【二軍】巨人🆚 広島 ...`; official Giants Town inferred | pending behind `64328` |
| `64352` | `review_date_fact_mismatch_review` | subject evidence `阿部監督「野球って不思議。いろいろなことを考えさせられた」 ベンチ関連発言`; `nikkansports` hint in prior audit | pending behind `64328` |
| `64390` | `review_date_fact_mismatch_review` | publish-notice demotion subject `RT 【公式】ジャイアンツタウンスタジアム: 新イベント「ヒーローズランウェ…` | pending behind `64328` |

## Step 3 backup + upload

Local backup root:

- `/tmp/lane_Z_backup_20260503T214700`

Objects uploaded:

- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_Z_mass_publish/guarded_publish_history.before.jsonl`
- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_Z_mass_publish/dedupe_pre.jsonl`
- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_Z_mass_publish/meta.json`
- `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_Z_mass_publish/64328.deleted_rows.jsonl`

Backup facts:

- full-history snapshot row count: `175598`
- `dedupe_pre.jsonl` rows: `5`
- candidate order frozen in `meta.json`:
  - `64328`
  - `64335`
  - `64331`
  - `64352`
  - `64390`

## Step 4 sequential publish outcome

### `64328`

Fresh pre-delete snapshot:

- local:
  - `/tmp/lane_Z_backup_20260503T214700/64328/guarded_publish_history.live_before.jsonl`
- exact deleted row:
  - `post_id=64328`
  - `ts=2026-05-03T12:36:22.947307+09:00`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_target_source_url=https://platform.twitter.com/widgets.js`
  - `duplicate_of_post_id=64297`

Live mutation applied:

- deleted rows: `1`
- live history uploaded back to:
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`

Post-`21:55 JST` guarded-publish result:

- latest row after rerun:
  - `post_id=64328`
  - `ts=2026-05-03T21:55:42.510157+09:00`
  - `status=refused`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_of_post_id=64272`
  - `duplicate_target_source_url=https://yoshilover.com/64189`
  - `is_backlog=true`

Interpretation:

- `64328` did **not** clear into `sent`
- after removing the old `widgets.js` row, the runner reinserted a new refused row anchored to a **real duplicate target**
- this satisfies the lane stop rule for a real duplicate reclassification

### stop decision

Lane Z stopped immediately after `64328` because the first live retry surfaced a real duplicate anchor.

No further live retries were attempted for:

- `64335`
- `64331`
- `64352`
- `64390`

### publish result

- newly published count: `0`
- published `post_id` list: none
- public URL list: none

## Step 5 publish-notice verify

- no `status=sent` rows were produced in this lane
- no publish-notice mail send was expected
- mail sent timestamps: none
- mail delta actual: `0`

## Step 6 rollback procedure

### `64328`

Current live state:

- a new refused row already exists at `2026-05-03T21:55:42.510157+09:00`
- no WordPress publish happened

If strict history restoration is required:

1. restore the deleted prior row from:
   - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_Z_mass_publish/64328.deleted_rows.jsonl`
2. or restore the full pre-lane snapshot from:
   - `gs://baseballsite-yoshilover-state/ops_manual_backups/20260503_lane_Z_mass_publish/guarded_publish_history.before.jsonl`

WP rollback:

- not needed
- `64328` never reached `publish`

### untouched candidates

No rollback needed because no live mutation was applied to:

- `64335`
- `64331`
- `64352`
- `64390`

### death/grave retry list

Lane W completion is still required before any reattempt:

- `63175`
- `63385`
- `63517`
- `63661`
- `64321`
- `64324`
- `64332`

## final state

- D candidate total: `5`
- actually retried: `1`
- publish count: `0`
- stop trigger: `64328` reclassified to real duplicate after narrow delete

Remaining risk:

- at least one apparently safe `widgets.js` row can still collapse into a real duplicate once the stale refused row is removed
- continuing into `64335` / `64331` / `64352` / `64390` without a fresh user decision would violate the lane stop contract
- death/grave class remains blocked behind Lane W classifier broadening
