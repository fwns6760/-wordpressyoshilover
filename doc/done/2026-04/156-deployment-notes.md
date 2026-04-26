# 156 deployment notes

## meta

- ticket: 156
- phase: 1b
- date: 2026-04-26 JST
- operator: Codex
- repo: `/home/fwns6/code/wordpressyoshilover`
- git_head: `3aa2cd1`
- project: `baseballsite`
- region: `asia-northeast1`
- artifact_registry_repo: `yoshilover`
- cloud_run_job: `draft-body-editor`
- smoke_execution: `draft-body-editor-92hbj`

## commands

### 1. Artifact Registry repo confirm

```bash
gcloud artifacts repositories describe yoshilover \
  --location=asia-northeast1 \
  --project=baseballsite
```

Result:

- repo already existed
- registry URI: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover`

### 2. Cloud Build image push

```bash
cd /home/fwns6/code/wordpressyoshilover
gcloud builds submit \
  --project=baseballsite \
  --region=asia-northeast1 \
  --config=cloudbuild_draft_body_editor.yaml \
  --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=draft-body-editor,_TAG=$(git rev-parse --short HEAD) \
  .
```

Result:

- build ID: `855c6545-9a0f-4734-b59e-48b04ed8efd3`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/draft-body-editor:3aa2cd1`
- digest: `sha256:efd41bb517d54e142d9a9f585e191b2805729bc53030b583c6e0f8807c32da13`
- status: `SUCCESS`

### 3. Cloud Run Job create

`.env` values were loaded from `/home/fwns6/code/wordpressyoshilover/.env` via `python-dotenv` inside the shell command and passed directly to `gcloud run jobs create --set-env-vars` without printing the values.

```bash
IMAGE="asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/draft-body-editor:$(git -C /home/fwns6/code/wordpressyoshilover rev-parse --short HEAD)"
ENV_VARS="$(python3 - <<'PY'
from dotenv import dotenv_values
vals = dotenv_values('/home/fwns6/code/wordpressyoshilover/.env')
required = ['WP_URL', 'WP_USER', 'WP_APP_PASSWORD', 'GEMINI_API_KEY']
missing = [k for k in required if not str(vals.get(k, '')).strip()]
if missing:
    raise SystemExit('missing:' + ','.join(missing))
print('^@^' + '@'.join(f"{k}={vals[k]}" for k in required))
PY
)"
gcloud run jobs create draft-body-editor \
  --image="$IMAGE" \
  --region=asia-northeast1 \
  --project=baseballsite \
  --task-timeout=600s \
  --max-retries=1 \
  --set-env-vars "$ENV_VARS" \
  --args="--max-posts,3"
```

Result:

- job create: success
- task timeout: `600s`
- max retries: `1`
- args: `--max-posts 3`

### 4. Manual smoke execute

```bash
gcloud run jobs execute draft-body-editor \
  --region=asia-northeast1 \
  --project=baseballsite \
  --wait
```

Result:

- execution: `draft-body-editor-92hbj`
- exit: `0`
- status: success

## masked env snapshot

- `WP_URL=***`
- `WP_USER=***`
- `WP_APP_PASSWORD=***`
- `GEMINI_API_KEY=***`

## smoke output summary

Cloud Logging (`run.googleapis.com/stdout`) showed one JSON summary entry for `draft-body-editor-92hbj`:

```json
{
  "aggregate_counts": {
    "edited": 0,
    "eligible_after_list_filters": 9,
    "guard_fail": 2,
    "list_level_skips": 336,
    "list_seen": 345,
    "pages_fetched": 5,
    "processed": 3,
    "processed_skip": 1,
    "selected_for_processing": 3
  },
  "candidates": 9,
  "candidates_before_filter": 345,
  "fetch_mode": "draft_list_paginated",
  "put_ok": 0,
  "reject": 2,
  "skip": 337,
  "stop_reason": "completed"
}
```

Interpretation:

- job ran in live mode once, as specified
- this smoke produced `put_ok: 0`, so no WordPress content update was written in this execution
- container system log ended with `Container called exit(0).`

## verify

### Artifact Registry

`gcloud artifacts docker images list asia-northeast1-docker.pkg.dev/baseballsite/yoshilover --include-tags | head -5`

- `draft-body-editor` tag `3aa2cd1` present

### Cloud Run Job

`gcloud run jobs describe draft-body-editor --region=asia-northeast1 --project=baseballsite`

- job exists
- `Ready=True`
- latest created execution: `draft-body-editor-92hbj`

### Cloud Logging

`gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=draft-body-editor' --project=baseballsite`

- system event present for `/Jobs.RunJob`
- stdout summary JSON present
- system log recorded `Container called exit(0).`

### WSL cron 042 line

`crontab -l | rg '2,12,22,32,42,52|draft_body_editor|run_draft_body_editor_lane'`

- unchanged:

```cron
2,12,22,32,42,52 * * * * cd /home/fwns6/code/wordpressyoshilover && /usr/bin/python3 -m src.tools.run_draft_body_editor_lane --max-posts 3 >> /home/fwns6/code/wordpressyoshilover/logs/draft_body_editor_cron.log 2>&1
```

### repo safety

- `src/`, `tests/`, `requirements*.txt`: no changes introduced by ticket 156
- only new tracked file for this ticket: `doc/active/156-deployment-notes.md`

## notes

- Ticket spec example used `WP_API_*` placeholder names, but the deployed runner currently reads `WP_URL / WP_USER / WP_APP_PASSWORD / GEMINI_API_KEY`; the job was created with the runtime keys the code actually consumes.
- Phase 1d remains responsible for Secret Manager migration.
