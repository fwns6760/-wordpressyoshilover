# 2026-05-03 BUG-004+291 widgets.js Lane C guarded-publish deploy

作成: 2026-05-03 17:15 JST

## scope

- live ops only
- target: `guarded-publish` Cloud Run Job
- code / tests / config change: 0
- Scheduler / cursor / queue / WP REST write / other jobs: untouched

## step 1: release composition verify

Command:

```bash
git rev-parse HEAD
git log --oneline 25d48cc..HEAD -- src/guarded_publish_runner.py src/guarded_publish_evaluator.py
git diff --name-only HEAD -- src/guarded_publish_runner.py src/guarded_publish_evaluator.py cloudbuild_guarded_publish.yaml Dockerfile.guarded_publish bin/guarded_publish_entrypoint.sh requirements.txt requirements-dev.txt vendor
```

Result:

- `HEAD = 565ef9ac1f74b775ce1707e0fb1d4eeb8fd5063d`
- guarded-publish delta since live image `:25d48cc`:
  - `62c9b6a bug-004-291: widgets.js duplicate false-positive narrow exempt (default OFF)`
- guarded-publish build inputs had no tracked dirty diff against `HEAD`
- worktree overall was dirty, so the build used a **clean `git archive HEAD` export** under `/tmp/guarded-publish-build-565ef9a.lfwGQ2`

## step 2: image build

Commands:

```bash
mktemp -d /tmp/guarded-publish-build-565ef9a.XXXXXX
git archive --format=tar HEAD | tar -xf - -C /tmp/guarded-publish-build-565ef9a.lfwGQ2
CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets \
gcloud builds submit /tmp/guarded-publish-build-565ef9a.lfwGQ2 \
  --project=baseballsite \
  --config=/tmp/guarded-publish-build-565ef9a.lfwGQ2/cloudbuild_guarded_publish.yaml \
  --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=guarded-publish,_TAG=565ef9a

CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets \
gcloud artifacts docker images describe \
  asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:565ef9a \
  --format='yaml(image_summary.digest,image_summary.fully_qualified_digest)'
```

Result:

| item | value |
|---|---|
| build id | `bd5b4a20-f9bf-4350-b3a8-aa0307d628a6` |
| build status | `SUCCESS` |
| duration | `4M15S` |
| image | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:565ef9a` |
| digest | `sha256:8ba5a8d5992dd562422a03f925af2713c28f6c4bc03a1485774abaa2babdedce` |
| fully qualified digest | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish@sha256:8ba5a8d5992dd562422a03f925af2713c28f6c4bc03a1485774abaa2babdedce` |

Note:

- `CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets` was used because the default `~/.config/gcloud` path is read-only in this sandbox.
- The build source was the clean `HEAD` export, not the dirty repo checkout.

## step 3: image update

Command:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets \
gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:565ef9a
```

Result:

- update succeeded
- post-apply job generation later advanced to `23`

## step 4: env apply(additive)

Commands:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets \
gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --update-env-vars=ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT=1

CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets \
gcloud run jobs describe guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --format=json
```

Env before:

- `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`
- `ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT` absent

Env after:

- `ENABLE_DUPLICATE_TARGET_INTEGRITY_STRICT=1`
- `ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT=1`

Job describe after apply:

- generation: `23`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:565ef9a`
- lastUpdatedTime: `2026-05-03T07:56:36.545463Z`

## step 5: verify(natural Scheduler only)

### natural executions observed

No manual `gcloud run jobs execute` was used.

Observed post-apply executions:

| execution | created(UTC) | result |
|---|---|---|
| `guarded-publish-sk9zn` | `2026-05-03 08:00:04` | success |
| `guarded-publish-crh82` | `2026-05-03 08:05:04` | success |
| `guarded-publish-vn9gs` | `2026-05-03 08:10:05` | success |

### 6 stuck draft targets

Target set:

- `64328`
- `64333`
- `64335`
- `64341`
- `64311`
- `64322`

Query used:

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets \
gcloud storage cat gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl \
  | rg '"post_id":\s*(64328|64333|64335|64341|64311|64322)' \
  | tail -n 100
```

Latest observed rows at 17:12 JST:

- all 6 remained at `status=refused`
- all 6 remained `hold_reason=review_duplicate_candidate_same_source_url`
- widgets.js target still visible on:
  - `64328`
  - `64333`
  - `64335`
  - `64341`

No target moved to `sent` or to a different hold reason during the first three post-apply executions.

### widgets.js exempt signal

Important limitation:

- `62c9b6a` adds the exempt behavior but does **not** emit a dedicated `widget_script_same_source_exempt` log event.
- Cloud Logging query for that exact event after apply returned no rows.
- Because the code has no dedicated emit point, absence of that exact event is **not** conclusive proof that the flag failed.

### integrity / failure / burst checks

Observed:

- `guarded_publish_history.jsonl` kept updating:
  - `2026-05-03T08:01:38Z` after the 17:00 JST run
- latest appended history rows during observed executions were `backlog_only` rows
- no recent tail matches for:
  - `cleanup_failed`
  - `publish_failed`
  - `hourly_cap`
  - `review_duplicate_candidate_same_source_url`
  - `duplicate_integrity`

publish-notice summaries after apply:

| timestamp(UTC) | summary |
|---|---|
| `2026-05-03T08:11:07.295805Z` | `[summary] sent=0 suppressed=0 errors=0 reasons={}` |
| `2026-05-03T08:06:01.447634Z` | `[summary] sent=0 suppressed=1 errors=0 reasons={"PUBLISH_ONLY_FILTER": 1}` |
| `2026-05-03T08:01:02.688822Z` | `[summary] sent=0 suppressed=1 errors=0 reasons={"PUBLISH_ONLY_FILTER": 1}` |

Interpretation:

- no mail burst
- no publish burst
- no cleanup/publish/hourly failure signatures in the observed window
- positive widgets.js-target release effect was **not yet observable** inside the first ~15 minutes because the 6 target posts were not re-evaluated into a different terminal state

## rollback

### env rollback

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets \
gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_DUPLICATE_WIDGET_SCRIPT_EXEMPT
```

### image rollback

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config-guarded-publish-widgets \
gcloud run jobs update guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:25d48cc
```

### source rollback

```bash
git revert 62c9b6aec115c5b5816abb54f6f84c9401e1b46f
```

## current judgment

- live apply: **done**
- additive env apply: **done**
- first 3 natural executions: **healthy**
- strict duplicate integrity env: **preserved**
- exact `widget_script_same_source_exempt` event verification: **not available in current code instrumentation**
- target 6 stuck drafts publish conversion: **not yet observed in the first ~15 minutes**

## remaining risk

- The expected positive signal is tied to target candidates that were not re-selected in the first three post-apply executions, so the fix is live but not yet functionally proven against the named 6 posts.
- Because no dedicated exempt event exists, runtime proof depends on downstream candidate outcome movement rather than a single log row.

## next judgment for Claude

1. Decide whether to continue passive observation for another 30-60 minutes to wait for the 6 target posts to re-enter the evaluated pool.
2. If quick positive proof is required in a future repo lane, add explicit observability for the widgets.js exempt branch before relying on event-based verification.
