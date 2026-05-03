# 2026-05-04 Lane EE backlog publish bypass fix + deploy record

作成: 2026-05-04 JST

## scope

- target runtime: `publish-notice` Cloud Run Job
- code scope:
  - `src/publish_notice_email_sender.py`
  - `tests/test_publish_notice_email_sender.py`
- deploy scope:
  - publish-notice image rebuild
  - publish-notice env apply
  - exact replay for `64416` then `64366`
- non-goals kept:
  - `src/publish_notice_scanner.py` semantics unchanged
  - Scheduler config unchanged
  - fetcher / guarded-publish runtime untouched
  - queue/history wipe not used

## Step 1-2 code change

- added env flag:
  - `ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS`
- added helper:
  - `_should_bypass_backlog_summary_only(request)`
- helper returns `True` only when all three match:
  - `notice_kind == "publish"`
  - `notice_origin == "direct_publish_scan"`
  - `record_type != "24h_budget_summary_only"`
- sender order change:
  - backlog suppress branch now checks the helper immediately before returning `BACKLOG_SUMMARY_ONLY`
- default remains OFF:
  - when the new flag is unset or `0`, sender behavior is unchanged

### tests added/extended

- direct publish + backlog + publish subject + new flag ON => `sent`
- direct publish + backlog + review-family article + both bypass flags ON => `sent`
- `24h_budget_summary_only` + new flag ON => still `BACKLOG_SUMMARY_ONLY`
- non-direct backlog + new flag ON => still `BACKLOG_SUMMARY_ONLY`
- new flag OFF => existing behavior preserved

## Step 3 pytest

Command:

```bash
python3 -m pytest tests/test_publish_notice_*.py -q
```

Result:

- `209 passed`
- `0 fail`
- `50 subtests passed`
- warnings: `3` pre-existing dependency warnings only

## Step 4 commit

| item | value |
|---|---|
| code commit | `eb0a31e` |
| message | `bug-004-291: BACKLOG_SUMMARY_ONLY publish bypass for direct_publish_scan (default OFF)` |

## Step 5 build

Dirty worktree was excluded by building from `git archive eb0a31e`.

| item | value |
|---|---|
| build id | `89984d01-a953-41c5-bc05-feca06f2369a` |
| build status | `SUCCESS` |
| image | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:eb0a31e` |
| digest | `sha256:f4db77393f3e0da43593d4b97ce3f230588d2c77d6a49e14218c951045c481c1` |
| build start | `2026-05-03T21:36:47.188934381Z` |
| build finish | `2026-05-03T21:40:25.595880Z` |

## Step 6 image update + env apply

### pre-state

Observed before apply from `gcloud run jobs describe publish-notice`:

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:62c9b6a`
- env present:
  - `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
  - `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`
  - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`
- env absent:
  - `ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS`

### applied

```bash
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:eb0a31e

gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS=1
```

### post-state

Observed after apply:

| item | value |
|---|---|
| job generation | `61` |
| lastUpdatedTime | `2026-05-03T21:46:38.350250Z` |
| image | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:eb0a31e` |
| latestCreatedExecution | `publish-notice-q8p2z` |
| latestCreatedExecution status | `EXECUTION_SUCCEEDED` |

Env confirmed after apply:

- `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
- `ENABLE_PUBLISH_ONLY_FILTER_DIRECT_PUBLISH_BYPASS=1`
- `ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS=1`
- `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`
- other pre-existing publish-notice envs unchanged

## Step 7 replay outcome

### pre-replay unsent verify

Remote `publish_notice/queue.jsonl` was downloaded read-only before replay.

- `64416`
  - found only one terminal row
  - status = `suppressed`
  - reason = `BACKLOG_SUMMARY_ONLY`
  - no `sent` row found before replay
- `64366`
  - found `queued` + `suppressed`
  - suppress reason = `PUBLISH_ONLY_FILTER`
  - no `sent` row found before replay

### replay method

- Cloud Run Job temporary command override
- replay order:
  1. `64416`
  2. `64366`
- each execution:
  - downloaded latest remote `queue.jsonl` inside the job for dedupe reference
  - ran sender once in dry-run mode
  - required `status=dry_run reason=None`
  - then ran live send once
  - job command/args were reverted immediately after each execution

### 64416

Intended replay execution:

- execution: `publish-notice-jqtx7`
- dry-run:
  - `2026-05-04 06:45:13.023 JST`
  - `status=dry_run`
- live send:
  - `2026-05-04 06:45:15.279 JST`
  - `status=sent`

Unexpected duplicate:

- execution: `publish-notice-v88kh`
- live send:
  - `2026-05-04 06:45:29.030 JST`
  - `status=sent`
- cause:
  - scheduler execution overlapped the temporary replay-command window before full revert completed
- impact:
  - `64416` mail was sent twice
- action taken:
  - lane stopped after finishing revert
  - no further 64416 replay attempts

### 64366

- execution: `publish-notice-q8p2z`
- dry-run:
  - `2026-05-04 06:46:22.146 JST`
  - `status=dry_run`
- live send:
  - `2026-05-04 06:46:23.703 JST`
  - `status=sent`
- duplicate observed: `no`

## Step 8 per-id verify + record

Public URL convention was fixed by user instruction as `https://yoshilover.com/<post_id>`.
Direct WP REST verification still failed in this sandbox with `curl: (6) Could not resolve host: yoshilover.com`.

| post_id | public URL | pre-fix result | replay sent timestamp JST | execution | note |
|---|---|---|---|---|---|
| `64416` | `https://yoshilover.com/64416` | `2026-05-04 05:21:07.430 JST` suppressed `BACKLOG_SUMMARY_ONLY` | `2026-05-04 06:45:15.279 JST` and duplicate `06:45:29.030 JST` | `publish-notice-jqtx7`, `publish-notice-v88kh` | duplicate send during scheduler overlap |
| `64366` | `https://yoshilover.com/64366` | `2026-05-03 15:55:58.608 JST` suppressed `PUBLISH_ONLY_FILTER` | `2026-05-04 06:46:23.703 JST` | `publish-notice-q8p2z` | single replay send |

## mail delta actual

- intended replay target: `+2 sent`
- actual result:
  - `64416`: `+2 sent`
  - `64366`: `+1 sent`
- actual mail delta total: `+3 sent`

## stop-condition note

User stop condition `existing sent post_id duplicate send` was hit by `64416`.

- duplicate happened between:
  - intended replay execution `publish-notice-jqtx7`
  - overlapping scheduler execution `publish-notice-v88kh`
- rollback on the replay mechanism was completed by reverting:
  - temporary `command`
  - temporary `args`
  - temporary replay env vars `REPLAY_PY_B64` / `REPLAY_PAYLOAD_B64`
- publish-notice fix image + backlog bypass env remained live

## rollback

### runtime rollback

Remove the new backlog bypass env:

```bash
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_PUBLISH_ONLY_FILTER_BACKLOG_BYPASS
```

Revert image to pre-fix tag:

```bash
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:62c9b6a
```

Emergency replay-command cleanup if needed again:

```bash
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --command='' \
  --args='' \
  --remove-env-vars=REPLAY_PY_B64,REPLAY_PAYLOAD_B64
```

### source rollback

```bash
git revert eb0a31e
```

## result summary

- code fix: landed
- tests: passed
- image rebuild: success
- env apply: success
- exact replay:
  - `64366` single send success
  - `64416` replay succeeded but duplicated once due scheduler overlap
- current publish-notice live state:
  - fix image `eb0a31e`
  - backlog bypass env ON
  - replay command reverted to default
