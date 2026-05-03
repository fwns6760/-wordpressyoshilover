# 2026-05-04 Lane FF replay-window dedup fix

作成: 2026-05-04 JST

## scope

- target runtime: `publish-notice` Cloud Run Job
- code scope:
  - `src/publish_notice_email_sender.py`
  - `tests/test_publish_notice_email_sender.py`
- live scope:
  - publish-notice image rebuild
  - publish-notice job image update
  - publish-notice env apply: `ENABLE_REPLAY_WINDOW_DEDUP=1`
- non-goals kept:
  - `src/publish_notice_scanner.py` contract unchanged
  - Scheduler config unchanged
  - mail bridge / Team Shiny unchanged
  - `RUN_DRAFT_ONLY` unchanged
  - queue/history wipe not used

## Step 1 read-only code path

`src/publish_notice_email_sender.py`

- suppression order in `send(...)` before this fix:
  1. `EMPTY_TITLE` / `MISSING_URL`
  2. `_should_suppress_publish_only_mail(...)`
  3. `BURST_SUMMARY_ONLY`
  4. `_resolve_is_backlog(...)` + `BACKLOG_SUMMARY_ONLY`
  5. `_deliver_mail(...)`
- existing recent sent dedupe was already present in `_deliver_mail(...)`
  - helper: `_is_recent_per_post_duplicate(...)`
  - source: `duplicate_history_path` JSONL queue
  - timestamp path: `sent_at` fallback `recorded_at`
  - reason: `DUPLICATE_WITHIN_30MIN`
- existing 24h scanner dedupe is separate
  - `src/publish_notice_scanner.py`
  - file: `publish_notice_history.json`
  - write timing: scan phase, before sender call

## Step 2 code change

Added narrow replay-window dedupe in `src/publish_notice_email_sender.py`.

- new env flag:
  - `ENABLE_REPLAY_WINDOW_DEDUP`
- new env knob:
  - `PUBLISH_NOTICE_REPLAY_WINDOW_MINUTES`
  - default: `10`
- new suppression reason:
  - `DUPLICATE_WITHIN_REPLAY_WINDOW`
- new helpers:
  - `_replay_window_dedup_enabled()`
  - `_resolve_replay_window_minutes()`
  - `_is_within_recent_replay_window(...)`
  - `_has_recent_publish_notice_history_overlap(...)`
  - `_should_suppress_recent_replay_duplicate(...)`
- behavior:
  - flag OFF: existing sender behavior unchanged
  - flag ON:
    - same `post_id` with recent `sent` row inside replay window is suppressed before bridge send
    - non-direct/manual replay path is also suppressed when sibling `publish_notice_history.json` shows the same `post_id` was just scanned in the replay window
    - Cloud Run runtime additionally tries a best-effort remote refresh of queue/history from GCS-backed state before deciding, so overlapping executions are not limited to the local `/tmp` snapshot only
- existing `DUPLICATE_WITHIN_30MIN` path remains intact and unchanged

## Step 3 tests

Extended `tests/test_publish_notice_email_sender.py`.

- recent same-`post_id` sent row + flag ON => `DUPLICATE_WITHIN_REPLAY_WINDOW`
- same-`post_id` outside replay window + flag ON => `sent`
- different `post_id` + flag ON => unaffected
- flag OFF + recent sent row => existing `DUPLICATE_WITHIN_30MIN` preserved
- flag OFF + recent `publish_notice_history.json` overlap => no new suppression
- `64416`-like fixture:
  - manual replay request for `post_id=64416`
  - sibling `history.json` contains recent same post id within 10 minutes
  - result => suppressed with `DUPLICATE_WITHIN_REPLAY_WINDOW`

## Step 4 pytest

Command:

```bash
python3 -m pytest tests/test_publish_notice_*.py -q
```

Result:

- `215 passed`
- `0 fail`
- `50 subtests passed`
- warnings: `3` pre-existing dependency warnings only

## Step 5 code commit

| item | value |
|---|---|
| code commit | `4231805` |
| message | `bug-004-291: replay-window dedup to prevent manual+scheduler overlap duplicate mail (default OFF)` |

## Step 6 build + Cloud Run job update + env apply

### pre-state

Observed from `gcloud run jobs describe publish-notice` before apply:

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:eb0a31e`
- env confirmed present:
  - `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS=1`
- env absent:
  - `ENABLE_REPLAY_WINDOW_DEDUP`
  - `PUBLISH_NOTICE_REPLAY_WINDOW_MINUTES`

### build

Build source used clean archive export from committed tree:

```bash
builddir=/tmp/publish-notice-build-4231805.LQpUYY
git archive 4231805 | tar -xf - -C "$builddir"
```

Build command:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live.uYT7XB \
gcloud builds submit /tmp/publish-notice-build-4231805.LQpUYY \
  --project=baseballsite \
  --region=asia-northeast1 \
  --config=/tmp/publish-notice-build-4231805.LQpUYY/cloudbuild_publish_notice.yaml \
  --substitutions=_TAG=4231805,_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=publish-notice
```

Build result:

| item | value |
|---|---|
| build id | `c2760c0d-54d5-4ca0-bd13-62640e144b6e` |
| status | `SUCCESS` |
| image | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4231805` |
| digest | `sha256:d137d980de50e620d4ba3a375d8ba3b8043d48c3c5caacfddc168d483e00f77c` |
| duration | `5M9S` |

### job image update

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live.uYT7XB \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4231805
```

### env apply

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live.uYT7XB \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_REPLAY_WINDOW_DEDUP=1
```

### post-state

Observed after apply:

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4231805`
- last updated: `2026-05-03T22:13:23.212343Z`
- env confirmed present:
  - `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS=1`
  - `ENABLE_REPLAY_WINDOW_DEDUP=1`
- env intentionally still absent:
  - `PUBLISH_NOTICE_REPLAY_WINDOW_MINUTES`
  - code default `10` minutes is therefore active

## Step 7 live verify

### current live facts

- post-update execution using the new image has **not yet been observed**
- last completed execution seen during verify:
  - execution: `publish-notice-fvg5g`
  - image digest: `sha256:f4db77393f3e0da43593d4b97ce3f230588d2c77d6a49e14218c951045c481c1`
  - this is the pre-fix image, so it does not prove or disprove the new replay-window suppression

### logging / queue verify

- `gcloud logging read` for `DUPLICATE_WITHIN_REPLAY_WINDOW` in the last 2 hours returned `0` rows
- remote queue confirms the known pre-fix rows still exist:
  - `64366`
    - `queued` at `2026-05-03T15:55:33.777913+09:00`
    - `suppressed` `PUBLISH_ONLY_FILTER` at `2026-05-03T15:55:58.603492+09:00`
  - `64416`
    - `suppressed` `BACKLOG_SUMMARY_ONLY` at `2026-05-04T05:21:07.429207+09:00`
- replay evidence remains in logs only, pre-fix:
  - `64416` replay live sends at `2026-05-03T21:45:15.278956Z` and `2026-05-03T21:45:29.029601Z`
  - `64366` replay live send at `2026-05-03T21:46:23.702980Z`

### verify conclusion

- no contradictory live evidence after deploy
- no post-fix overlap execution has occurred yet, so live proof is pending the next real overlap event
- acceptance fallback used now:
  - repo fixture for `64416`-like overlap passes
  - runtime image/env are already updated

## 6 conditions summary

1. normal new publish mail remains enabled:
   - no scanner contract change
   - no publish-only/backlog bypass env removed
2. existing sent-history dedupe remains:
   - `DUPLICATE_WITHIN_30MIN` logic untouched
   - explicit regression test added
3. draft / review / hold / skip / diagnostic / 24h summary behavior remains:
   - non-publish paths unchanged
   - full `tests/test_publish_notice_*.py` suite passed
4. `64416`-like manual+scheduler overlap fixture added:
   - yes, explicit test covers it
5. `64416`-class duplicate prevention confirmed:
   - fixture-confirmed in repo
   - live overlap not yet re-occurred after deploy, so no fresh production log exists yet
6. existing Lane G / EE bypass behavior preserved:
   - envs remain in place
   - existing sender tests for publish-only / backlog bypass still pass inside the full suite

## rollback

Disable the new flag only:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live.uYT7XB \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_REPLAY_WINDOW_DEDUP
```

Revert image to the pre-fix tag if needed:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-live.uYT7XB \
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:eb0a31e
```
