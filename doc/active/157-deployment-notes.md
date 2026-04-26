# 157 deployment notes

## meta

- ticket: 157
- phase: 1c
- date: 2026-04-26 JST
- operator: Codex
- repo: `/home/fwns6/code/wordpressyoshilover`
- git_head: `cbe05b0`
- project: `baseballsite`
- region: `asia-northeast1`
- cloud_run_job: `draft-body-editor`
- cloud_scheduler_job: `draft-body-editor-trigger`

## commands

### 1. Prepare writable gcloud config mirror

The sandbox could not write under `~/.config/gcloud`, so a writable mirror was created under `/tmp` and used for all `gcloud` mutations. No credential values were printed.

```bash
rm -rf /tmp/gcloud-config
mkdir -p /tmp/gcloud-config
(cd ~/.config/gcloud && tar cf - .) | (cd /tmp/gcloud-config && tar xf -)
```

Result:

- mirror path: `/tmp/gcloud-config`
- active account and project remained unchanged

### 2. Existing scheduler service account confirm

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud scheduler jobs describe giants-weekday-daytime \
  --location=asia-northeast1 \
  --project=baseballsite \
  --format='yaml(httpTarget.oidcToken.serviceAccountEmail,httpTarget.uri,httpTarget.httpMethod,schedule,timeZone,state)'
```

Result:

- existing scheduler auth mode: `OIDC`
- initial service account candidate: `<masked-existing-scheduler-sa>`
- reference job state: `ENABLED`

### 3. Create Cloud Scheduler trigger

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud scheduler jobs create http draft-body-editor-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule='2,12,22,32,42,52 * * * *' \
  --time-zone='Asia/Tokyo' \
  --uri='https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/draft-body-editor:run' \
  --http-method=POST \
  --oauth-service-account-email='<masked-existing-scheduler-sa>' \
  --oauth-token-scope='https://www.googleapis.com/auth/cloud-platform'
```

Result:

- job create: success
- state: `ENABLED`
- next scheduled tick at create time: `2026-04-26 17:22 JST`
- target URI: `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/draft-body-editor:run`
- first auto tick with the initial scheduler service account returned `403`, so the auth identity was corrected before the next tick

### 4. Update scheduler auth to an existing project runtime service account

The first `17:22 JST` automatic attempt returned `403` and did not create a new Cloud Run Job execution. `gcloud projects get-iam-policy` confirmed that the initial scheduler service account had no `run` role, while an existing project runtime service account already had project-level `roles/editor`. The scheduler job was updated to use that existing runtime service account.

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud scheduler jobs update http draft-body-editor-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule='2,12,22,32,42,52 * * * *' \
  --time-zone='Asia/Tokyo' \
  --uri='https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/draft-body-editor:run' \
  --http-method=POST \
  --oauth-service-account-email='<masked-runtime-sa-with-run-permission>' \
  --oauth-token-scope='https://www.googleapis.com/auth/cloud-platform'
```

Result:

- scheduler update: success
- next scheduled tick after the auth fix: `2026-04-26 17:32 JST`
- updated service account: `<masked-runtime-sa-with-run-permission>`

### 5. Scheduler describe verify

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud scheduler jobs describe draft-body-editor-trigger \
  --location=asia-northeast1 \
  --project=baseballsite \
  --format='yaml(name,schedule,timeZone,state,httpTarget.uri,httpTarget.httpMethod,httpTarget.oauthToken.serviceAccountEmail,retryConfig,attemptDeadline,scheduleTime,userUpdateTime)'
```

Result:

- name: `projects/baseballsite/locations/asia-northeast1/jobs/draft-body-editor-trigger`
- schedule: `2,12,22,32,42,52 * * * *`
- time zone: `Asia/Tokyo`
- http method: `POST`
- auth mode: `OAuth`
- oauth service account: `<masked-runtime-sa-with-run-permission>`
- last attempt after auth fix: `2026-04-26 17:32:01 JST`
- retry config:
  - `minBackoffDuration=5s`
  - `maxBackoffDuration=3600s`
  - `maxDoublings=5`
  - `maxRetryDuration=0s`
- attempt deadline: `180s`

### 6. Next tick observation

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud run jobs executions list \
  --job=draft-body-editor \
  --region=asia-northeast1 \
  --project=baseballsite \
  --limit=3

CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud logging read \
  'resource.type=cloud_scheduler_job AND resource.labels.job_id=draft-body-editor-trigger' \
  --limit=3 \
  --project=baseballsite
```

Result:

- first automatic tick at `17:22 JST`: `403` from Cloud Scheduler, no new Cloud Run Job execution
- second automatic tick after auth fix (`17:32 JST`): success
  - Cloud Scheduler `AttemptFinished`: `HTTP 200`
  - Cloud Run Job execution: `draft-body-editor-p92zq`
  - execution start: `2026-04-26 17:32:03 JST`
  - execution complete: `2026-04-26 17:32:46 JST`
  - completion message: `Execution completed successfully in 43.6s.`
  - stdout summary: `put_ok=0`, `processed=3`, `guard_fail=2`, `selected_for_processing=3`, `stop_reason=completed`
  - live publish observed: no (`put_ok=0`)

## verify

### Cloud Scheduler

- `draft-body-editor-trigger` created in `asia-northeast1`
- `state=ENABLED`
- `schedule=2,12,22,32,42,52 * * * *`
- `timeZone=Asia/Tokyo`
- target Cloud Run Job run URI confirmed
- first auto tick (`17:22 JST`) returned `403` with the initial scheduler identity
- second auto tick (`17:32 JST`) returned `200` after the auth fix

### Cloud Run Job

- existing target job `draft-body-editor` was present before scheduler creation
- `17:22 JST` automatic attempt did not start the job because Cloud Scheduler received `403`
- `17:32 JST` automatic attempt started execution `draft-body-editor-p92zq`
- execution finished successfully and produced stdout summary with `put_ok=0`

### WSL cron 042 line

- this ticket did not execute any command that edits crontab
- direct `crontab -l` re-read was blocked in the sandbox with `crontabs/fwns6/: fopen: Permission denied`
- last confirmed 042 line remains recorded in [156-deployment-notes.md](/home/fwns6/code/wordpressyoshilover/doc/active/156-deployment-notes.md:124)

### repo safety

- `src/`, `tests/`, `Dockerfile*`, `cloudbuild*.yaml`: unchanged by this ticket
- only tracked file intended for commit: `doc/active/157-deployment-notes.md`

## notes

- `gcloud` mutation commands require a writable config directory in this sandbox; `/tmp/gcloud-config` was used only as a transient mirror and is not part of the repo.
- WSL 042 remains enabled by design during the observation period; this ticket does not disable or edit it.
