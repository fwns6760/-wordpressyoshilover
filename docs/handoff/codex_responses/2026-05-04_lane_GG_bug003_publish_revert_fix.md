# 2026-05-04 Lane GG BUG-003 publish revert deep audit + safe fix

作成: 2026-05-04 JST

## scope

- lane: `GG`
- bug family: `BUG-003`
- primary target: `post_id=64416`
- repo scope:
  - `src/wp_client.py`
  - `src/rss_fetcher.py`
  - `src/guarded_publish_runner.py`
  - `src/manual_post.py`
  - `src/weekly_summary.py`
  - `src/sports_fetcher.py`
  - `src/data_post_generator.py`
  - related tests only
- non-goals kept:
  - `src/publish_notice_email_sender.py` untouched
  - `publish-notice` runtime behavior untouched
  - Cloud Run / Scheduler / Secret / env live mutation not executed in this lane

## Step 1: 64416 timeline

### sources used

- Cloud Logging read:
  - `resource.labels.service_name="yoshilover-fetcher"`
  - `resource.labels.job_name="guarded-publish"`
  - `resource.labels.job_name="publish-notice"`
- GCS state download:
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
  - `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`
  - `gs://baseballsite-yoshilover-state/publish_notice/history.json`
- local sandbox check:
  - `curl https://yoshilover.com/?p=64416` failed with DNS resolution error, so current WP/public state is not directly verifiable here

### exact timeline

| ts JST | source | evidence | note |
|---|---|---|---|
| `2026-05-04 05:10:40.760` | `yoshilover-fetcher-00186-9cl` | `[WP] 記事draft post_id=64416` | repo-visible creation is `draft`, not `publish` |
| `2026-05-04 05:10:41.956` | `yoshilover-fetcher-00186-9cl` | `[下書き止め] post_id=64416 reason=draft_only` | fetcher explicitly kept draft-only |
| `2026-05-04 05:10:42.216` | `yoshilover-fetcher-00186-9cl` | `[下書き維持] post_id=64416 reason=draft_only image=あり` | same conclusion |
| `2026-05-04 05:15:37.532624` | `guarded_publish_history.jsonl` | `status=refused`, `hold_reason=review_date_fact_mismatch_review` | latest guarded durable row for 64416 |
| `2026-05-04 05:20:35.546762` | `publish_notice/history.json` | key `64416` updated | notify dedupe ledger only |
| `2026-05-04 05:21:07.429207` | `publish_notice/queue.jsonl` | `status=suppressed`, `reason=BACKLOG_SUMMARY_ONLY`, subject `【公開済】...` | notify surface only |
| `2026-05-04 06:45:15.279` | `publish-notice-jqtx7` | `[replay-live] post_id=64416 status=sent` | intended manual replay send |
| `2026-05-04 06:45:29.030` | `publish-notice-v88kh` | `[replay-live] post_id=64416 status=sent` | overlapping scheduler duplicate send |

### clarification on `publish_at`

- `publish_notice_scanner.py` sets `publish_time_iso` from `post.date`, not from a confirmed publish write.
- code reference:
  - `src/publish_notice_scanner.py` `_request_from_post(...)`
  - `publish_time_iso=_isoformat_jst(post.get("date"))`
- therefore `2026-05-04 05:10:40+09:00` in `queue.jsonl` is a **scanner-side proxy**, not proof that repo code wrote `status=publish`.

### 64416 actor finding

- repo-visible actor chain is:
  1. `yoshilover-fetcher` created `draft`
  2. `guarded-publish` refused review
  3. `publish-notice` surfaced then suppressed
  4. manual replay + overlapping scheduler sent mail twice
- repo-visible **publish writer** for `64416` was **not observed**
- if Claude/user-side field probe is correct that `64416` became public and later current `401` / non-publish, the final mutator is outside the repo-visible chain seen here

## Step 2: 24h same-pattern scan

Window used:

- start: `2026-05-03 07:29:00 JST`
- end: `2026-05-04 07:29:00 JST`

### strict guarded history scan

- criterion: `guarded_publish_history.status="sent"` followed by a later non-`sent` row for the same `post_id` inside the 24h window
- result: `0`

### publish-notice public-subject mismatch scan

- criterion:
  - `publish_notice/queue.jsonl` row with subject prefix `【公開済】`
  - `publish_time_iso` inside the 24h window
  - later/equal guarded history row for same `post_id` with non-`sent`
- result count: `4`

| post_id | queue `publish_time_iso` JST | first later non-sent guarded row JST | guarded status | hold_reason | current WP state |
|---|---|---|---|---|---|
| `64335` | `2026-05-03 13:20:16` | `2026-05-03 23:11:30.759324` | `skipped` | `backlog_only` | `unverified` in this sandbox |
| `64373` | `2026-05-03 16:30:21` | `2026-05-03 16:30:40.319622` | `skipped` | `backlog_only` | `unverified` in this sandbox |
| `64390` | `2026-05-03 18:45:39` | `2026-05-03 23:22:59.183263` | `refused` | `review_date_fact_mismatch_review` | `unverified` in this sandbox |
| `64416` | `2026-05-04 05:10:40` | `2026-05-04 05:15:37.532624` | `refused` | `review_date_fact_mismatch_review` | user / Claude-side field report says current `401`; sandbox direct verify unavailable |

### important interpretation lock

- the 24h scan shows **public-subject mismatch**, not a repo-proven `publish -> draft/private/trash` write
- because `publish_time_iso` is derived from `post.date`, these `4` ids are an upper-bound mismatch cohort, not a confirmed demotion cohort

## Step 3: root-cause ranking refresh

### rank C: out-of-band actor / WP-side mutation

Verdict:

- strongest fit for `64416`

Evidence:

- fetcher log shows `draft` create + explicit `draft_only`
- guarded durable row is `refused`, not `sent`
- no repo-visible publish writer for `64416` was logged
- if the field fact is truly `publish -> current 401`, that transition is not owned by the visible repo chain above

Strength:

- `high` for explaining the current field/non-publish report
- still needs authenticated WP-side revision / plugin / cron trace to prove the exact actor

### rank B: silent publish visibility / bypass inside repo

Verdict:

- strongest repo-side containment fix, but secondary for the concrete `64416` actor

Evidence:

- `_reuse_existing_post()` can silently promote reused `draft/pending/future/auto-draft` posts to `publish`
- `rss_fetcher.finalize_post_publication()` had a direct `update_post_status(..., "publish")` path outside a central helper
- publish-notice `【公開済】` surfacing uses `post.date` and can look publish-final even when durable guarded state is non-`sent`

Strength:

- `high` for future containment
- `medium` as the direct explanation for `64416`, because this case shows draft-only + review in repo-visible logs

### rank A: cleanup path

Verdict:

- weakest fit

Evidence:

- `64416` guarded row has `cleanup_required=false`
- no cleanup backup failure or cleanup failure evidence was found for `64416`
- backlog-only rows exist in the broader mismatch cohort, but they do not explain `64416`

Strength:

- `low`

## Step 4: safe fix design

### implemented primary fix: B-hardening

- new default-OFF env flag:
  - `ENABLE_WP_PUBLISH_STATUS_GUARD`
- changes:
  - central helper `WPClient.publish_post(...)`
  - explicit opt-in `allow_status_upgrade=True` required for reused draft-like posts when guard flag is ON
  - structured guard events emitted only when flag is ON:
    - `wp_publish_status_guard_create_publish`
    - `wp_publish_status_guard_reuse_upgrade`
    - `wp_publish_status_guard_reuse_upgrade_blocked`
    - `wp_publish_status_guard_publish_write`
- fields logged:
  - `ts`
  - `post_id`
  - `caller`
  - `source_lane`
  - `status_before`
  - `status_after`
  - `allow_status_upgrade`
  - `used_update_fields`
  - `reason`

### A-hygiene

- not implemented in this lane to keep blast radius low
- recommended follow-up if needed:
  - add `status_write_attempted=false` or equivalent explicit history-only marker to non-live / skipped / review rows in `guarded_publish_history`

### C-WP-side

- audit only
- repo change cannot prove or prevent a WP-side plugin/manual/cron demotion

## Step 5: implementation

### files changed

- `src/wp_client.py`
- `src/rss_fetcher.py`
- `src/guarded_publish_runner.py`
- `src/manual_post.py`
- `src/weekly_summary.py`
- `src/sports_fetcher.py`
- `src/data_post_generator.py`
- `tests/test_wp_client.py`
- `tests/test_guarded_publish_runner.py`
- `tests/test_rss_fetcher_publish_status_guard.py`

### tests

Command:

```bash
python3 -m unittest \
  tests.test_wp_client \
  tests.test_rss_fetcher_publish_status_guard \
  tests.test_guarded_publish_runner
```

Result:

- `132` tests run
- `132` passed
- `0` failed

### commit

- code commit: `550d252`
- message: `bug-003: harden publish status writes`

## Step 6: affected runtime scope

### affected live runtimes

- `yoshilover-fetcher`
  - current image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:e0a58bb`
  - current revision: `yoshilover-fetcher-00186-9cl`
- `guarded-publish`
  - current image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:0f5e95a`
  - current generation: `25`
  - latest execution: `guarded-publish-8bp4l`

### unaffected runtime

- `publish-notice`
  - untouched in this lane

### rebuild / env apply scope

- both `yoshilover-fetcher` and `guarded-publish` need rebuild/redeploy because `src/wp_client.py` is shared and runtime-used in both lanes
- env apply scope for the new behavior is narrow:
  - `ENABLE_WP_PUBLISH_STATUS_GUARD=1`
  - target only:
    - `yoshilover-fetcher`
    - `guarded-publish`

## Step 7: live verify

Status:

- `plan only`

Reason:

- this Codex lane stayed inside repo implementation + read-only GCP verification
- Cloud Build / Cloud Run live mutation was not executed here
- sandbox cannot directly verify WP/public state because `yoshilover.com` DNS resolution fails

### authenticated executor runbook

1. rebuild and deploy `yoshilover-fetcher` from the code commit below
2. rebuild and deploy `guarded-publish` from the same code commit
3. set `ENABLE_WP_PUBLISH_STATUS_GUARD=1` on both runtimes
4. observe next natural publish attempts for structured guard events:
   - `wp_publish_status_guard_publish_write`
   - `wp_publish_status_guard_reuse_upgrade`
   - `wp_publish_status_guard_reuse_upgrade_blocked`
5. for any reused draft promotion that is still intended, confirm the caller is explicitly passing `allow_status_upgrade=True`
6. do **not** use `64416` republish as the first live verification target unless WP-side actor trace is also in hand; this case is not repo-proven as a legitimate publish candidate

## rollback

### config rollback

- remove env on both runtimes:

```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_WP_PUBLISH_STATUS_GUARD

gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_WP_PUBLISH_STATUS_GUARD
```

### image rollback anchors

- `yoshilover-fetcher`: rollback to current pre-change image family `:e0a58bb`
- `guarded-publish`: rollback to current pre-change image family `:0f5e95a`

### source rollback

- `git revert 550d252`

## 64416 specific outcome

- no republish was executed in this lane
- repo-visible evidence currently says:
  - created as `draft`
  - held as `draft_only`
  - later `review_date_fact_mismatch_review`
  - notify suppressed
  - replay mail sent twice
- therefore `64416` is **not** repo-proven as “published then reverted” from the evidence available in this sandbox
- if field truth still says current `401` after a real public exposure, the next required move is WP-side actor trace, not blind republish

## 5-step summary

1. `64416` timeline is reconstructed enough to rule out repo-visible fetcher/guarded-publish publish writes.
2. last-24h strict `sent -> non-sent` count is `0`; mismatch upper-bound count is `4` ids: `64335`, `64373`, `64390`, `64416`.
3. root-cause ranking refresh remains `C > B > A`, and `64416` strengthens `C`.
4. safe repo-side fix is implemented as default-OFF `ENABLE_WP_PUBLISH_STATUS_GUARD`.
5. live deploy / env apply / direct WP verify remain pending for an authenticated executor.
