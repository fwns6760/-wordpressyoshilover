# 2026-05-04 Lane MM publish-notice phantom publish marker fix

作成: 2026-05-04 JST

## scope

- lane: `MM`
- target: `64437` / `64447` 型の phantom publish marker
- repo scope:
  - `src/publish_notice_scanner.py`
  - `src/publish_notice_email_sender.py`
  - `src/tools/run_publish_notice_email_dry_run.py`
  - `tests/test_publish_notice_scanner.py`
  - `tests/test_publish_notice_email_sender.py`
- non-goals kept:
  - `src/wp_client.py` publish path untouched
  - `src/guarded_publish_runner.py` untouched
  - mail bridge / Scheduler / Secret / live env mutation not executed

## Step 1 audit

### history write path inventory

`src/publish_notice_scanner.py`

- direct publish scan:
  - `scan(...)` queues `status="queued"` rows for `status=publish` posts
  - old behavior: the same scan also wrote `publish_notice_history.json` before sender execution
  - effect: later sender suppression could still leave a `published` marker behind
- guarded review scan:
  - `scan_guarded_publish_history(...)` wrote `history_after[post_id]` at scan time for emitted review-hold notices
  - this happened before mail send result was known
- post-gen-validate scan:
  - `scan_post_gen_validate_history(...)` wrote `history_after[dedupe_key]` at scan time
- preflight-skip scan:
  - `scan_preflight_skip_history(...)` wrote `history_after[dedupe_key]` at scan time

`src/publish_notice_email_sender.py`

- read-only against `publish_notice_history.json` before this lane
  - replay-window dedupe reads local + remote sibling `history.json`
  - queue append writes `queue.jsonl`
- there was **no** history write on mail send success before this lane

### suppress-path finding

- `DUPLICATE_WITHIN_REPLAY_WINDOW` itself did not write history in sender
- the marker already existed because scanner had stamped history earlier
- `PUBLISH_ONLY_FILTER` and `BACKLOG_SUMMARY_ONLY` therefore also inherited the same problem when the request had already been stamped by scanner

### 64437 chronology

sources:

- Cloud Logging read-only
- live GCS objects:
  - `gs://baseballsite-yoshilover-state/publish_notice/history.json`
  - `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`
- prior incident evidence already recorded in:
  - `docs/handoff/codex_responses/2026-05-04_lane_KK_64424_64461_incident_ledger.md`

timeline:

| ts JST | source | evidence | note |
|---|---|---|---|
| `2026-05-04 00:55:49.098001` | Cloud Logging / `yoshilover-fetcher` | `[WP] 記事draft post_id=64437` | repo-visible create was `draft` |
| `2026-05-04 00:55:50.292063` | Cloud Logging / `yoshilover-fetcher` | `[下書き止め] post_id=64437 reason=draft_only` | fetcher kept draft-only |
| `2026-05-04 00:55:50.587135` | Cloud Logging / `yoshilover-fetcher` | `[下書き維持] post_id=64437 reason=draft_only image=あり` | same conclusion |
| `2026-05-04 10:05:40` | prior Lane KK evidence | `publish_notice/history.json` had `64437` marker | current bucket snapshot no longer preserves this generation |
| `2026-05-04 10:06:36.373219` | live `publish_notice/queue.jsonl` | `status=suppressed`, `reason=DUPLICATE_WITHIN_REPLAY_WINDOW`, subject `【公開済】...`, `publish_time_iso=2026-05-04T09:55:49+09:00` | replay-window suppress consumed the earlier marker |
| current snapshot | live `publish_notice/history.json` | key `64437` is now absent | queue row survived, history marker did not |

inference:

- the `64437` queue row could not come from sender alone; it depended on an earlier history marker
- the current code before this lane allowed scanner-side pre-stamp without a later successful mail send
- the current bucket state no longer contains the old `64437` key, so the exact `10:05:40` generation is unrecoverable from GCS now
- because `publish_notice/history.json` is a 24h rolling dedupe object and the bucket is not versioned, a **7-day exact reconstruction is impossible** after overwrite; only current snapshot + queue + prior incident ledger remain

`64447` matched the same shape:

- `queue.jsonl` still has `suppressed / DUPLICATE_WITHIN_REPLAY_WINDOW`
- current `history.json` no longer has key `64447`

## Step 2 live counts

### exact limits

- direct WordPress REST re-check from this sandbox failed because outbound DNS to `yoshilover.com` is unavailable here
- exact user-requested `history says published` vs current live WP `draft/private/trash` comparison is therefore **not fully provable from this sandbox**
- additionally, `publish_notice/history.json` is only the current rolling dedupe object, not a 7-day archive

### current live snapshot counts

from current GCS state:

- `publish_notice/history.json`
  - total keys: `128`
  - numeric post ids: `81`
- `publish_notice/queue.jsonl`
  - total rows: `1444`
  - `status=suppressed` with subject prefix `【公開済】`: `72`
  - breakdown:
    - `BACKLOG_SUMMARY_ONLY`: `67`
    - `DUPLICATE_WITHIN_REPLAY_WINDOW`: `5`

current replay-window suppressed rows with public subject:

- post-gen-validate key `post_gen_validate:18598c4e74edaaba:...`
- post-gen-validate key `post_gen_validate:0e0b6d18acbb92f6:close_marker`
- `64437`
- `64447`
- `63940`

### proxy mismatch cohort

Because bulk WP status is blocked, I compared:

- current numeric keys in `publish_notice/history.json`
- latest per-post queue outcome in `publish_notice/queue.jsonl`
- latest guarded row in `guarded_publish_history.jsonl`

proxy criterion:

- latest guarded status is non-`sent`, or
- latest queue row is `suppressed` with subject prefix `【公開済】`

proxy result:

- mismatch-like count: `55`
- queue status breakdown:
  - `suppressed`: `51`
  - `sent`: `4`
- queue reason breakdown:
  - `BACKLOG_SUMMARY_ONLY`: `26`
  - `PUBLISH_ONLY_FILTER`: `23`
  - `DUPLICATE_WITHIN_REPLAY_WINDOW`: `2`
  - `(none)`: `4`

This is **not** the same as authoritative current WP draft/private/trash count, but it does show that scanner/history markers and visible queue outcomes are frequently out of sync with guarded durable state.

## Step 3 design

Implemented recommendation: `case A + case B`

- `case A`
  - strict flag ON stops scanner-side pre-stamp into `publish_notice_history.json`
  - history is only written after sender result is `sent`
  - suppress reasons such as `DUPLICATE_WITHIN_REPLAY_WINDOW` and `PUBLISH_ONLY_FILTER` therefore no longer create markers
- `case B`
  - for numeric post ids, history write now requires a best-effort WP status re-check returning `publish`
  - if re-check fails or status is not `publish`, numeric marker is not written

flag:

- `ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP`
- default: OFF

## Step 4 implementation

### code changes

`src/publish_notice_scanner.py`

- added strict-stamp env helper
- under strict flag ON:
  - direct publish scan no longer writes numeric publish markers at scan time
  - guarded review / post-gen-validate / preflight history keys are no longer pre-written at scan time
  - queue `status="queued"` rows remain unchanged

`src/publish_notice_email_sender.py`

- added strict-stamp env helper
- added `_verify_wp_status_publish(post_id) -> bool`
- added post-send history recording helper
- under strict flag ON:
  - only `result.status == "sent"` can write to `publish_notice_history.json`
  - numeric keys require successful `status=publish` verification
  - non-numeric dedupe keys (for example `post_gen_validate:*`) remain recordable after successful send

`src/tools/run_publish_notice_email_dry_run.py`

- per-post send path now passes the original request + `history_path` into `append_send_result(...)`
- this is what lets sender-side post-send history recording happen without changing summary / alert paths

## Step 5 tests

Command run:

```bash
python3 -m pytest tests/test_publish_notice_*.py -q
```

Result:

- `222 passed`
- `0 fail`
- `50 subtests passed`
- warnings: `3` pre-existing dependency warnings only

Added coverage:

- strict ON direct scan defers history write
- strict ON sent mail writes history after send
- strict ON replay-window suppress does not write history
- strict ON `PUBLISH_ONLY_FILTER` suppress does not write history
- strict ON numeric key with `status != publish` does not write history
- strict ON non-numeric post-gen-validate key still writes after send
- strict OFF keeps existing sender-side no-history side effect

## Step 6 commit status

- repo changes are ready
- push not executed
- commit not created yet in this doc snapshot
- requested commit message:
  - `lane-MM: publish-notice phantom publish marker narrow fix (suppress-skip stamp + WP verify, default OFF)`

## Step 7 live apply plan

current live `publish-notice` job state (read-only):

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4231805`
- current env already present:
  - `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS=1`
  - `ENABLE_REPLAY_WINDOW_DEDUP=1`
- new flag currently absent:
  - `ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP`

authenticated executor plan:

1. build new publish-notice image from the repo commit
2. update Cloud Run Job image
3. apply env:
   - `ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP=1`
4. keep existing envs unchanged

suggested commands:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live \
gcloud builds submit . \
  --project=baseballsite \
  --region=asia-northeast1 \
  --config=cloudbuild_publish_notice.yaml \
  --substitutions=_TAG=<new_commit>,_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=publish-notice
```

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:<new_commit>
```

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP=1
```

post-apply verify:

- new `publish_notice/history.json` numeric keys should only appear after `sent` rows
- replay-window suppress rows like `64437` / `64447` should not create fresh numeric history markers
- if a publish-notice send succeeds while WP status is non-`publish`, no numeric history key should be added

## rollback

Disable the new flag only:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP
```

If needed, revert the image to the previous live tag:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4231805
```

## residual risk

- exact 7-day authoritative WP-status mismatch count still requires an environment that can bulk query live WP REST
- current GCS bucket without history object versioning means overwritten `history.json` generations are not recoverable after the fact
- old-candidate once ledger behavior was intentionally left untouched in this lane
