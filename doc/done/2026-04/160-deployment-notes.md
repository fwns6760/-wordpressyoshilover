# 160 deployment notes

## meta

- ticket: 160
- phase: 2
- date: 2026-04-26 JST
- operator: Codex
- repo: `/home/fwns6/code/wordpressyoshilover`
- git_head_at_build: `cd550f6`
- workspace_head_after_observation: `38eaa70`
- project: `baseballsite`
- region: `asia-northeast1`
- artifact_registry_repo: `yoshilover`
- cloud_run_job: `guarded-publish`
- cloud_scheduler_job: `guarded-publish-trigger`
- runtime_service_account: `487178857517-compute@developer.gserviceaccount.com`
- build_id: `295a965c-d40e-450e-85ac-c83c3bb5caae`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:cd550f6`
- image_digest: `sha256:8987524ff46a06cac72bb5bb84030d55fbff6b134fabb2ecf58aebf7e99b1a15`
- manual_smoke_execution: `guarded-publish-x2724`
- first_auto_execution: `guarded-publish-npjqx`

## build

Cloud Build used the dedicated config below and pushed the image successfully.

```bash
export CLOUDSDK_CONFIG=/tmp/gcloud-config
cd /home/fwns6/code/wordpressyoshilover
gcloud builds submit \
  --project=baseballsite \
  --region=asia-northeast1 \
  --config=cloudbuild_guarded_publish.yaml \
  --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=guarded-publish,_TAG=$(git rev-parse --short HEAD) \
  .
```

Result:

- build status: `SUCCESS`
- pushed image tag: `guarded-publish:cd550f6`
- pushed image digest: `sha256:8987524ff46a06cac72bb5bb84030d55fbff6b134fabb2ecf58aebf7e99b1a15`

Notes:

- `cloudbuild_guarded_publish.yaml` stages a temporary build context under `/workspace/.cloudbuild-guarded-publish` because the repo-root `.dockerignore` does not include `bin/guarded_publish_entrypoint.sh`.

## cloud run job

```bash
export CLOUDSDK_CONFIG=/tmp/gcloud-config
IMAGE='asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish@sha256:8987524ff46a06cac72bb5bb84030d55fbff6b134fabb2ecf58aebf7e99b1a15'
gcloud run jobs create guarded-publish \
  --image="$IMAGE" \
  --region=asia-northeast1 \
  --project=baseballsite \
  --task-timeout=600s \
  --max-retries=1 \
  --service-account='487178857517-compute@developer.gserviceaccount.com' \
  --set-secrets='WP_URL=wp-url:latest,WP_USER=wp-user:latest,WP_APP_PASSWORD=wp-app-password:latest,WP_API_BASE=wp-api-base:latest,GEMINI_API_KEY=gemini-api-key:latest'
```

Verified job state:

- job create: success
- timeout: `600s`
- max retries: `1`
- service account: `487178857517-compute@developer.gserviceaccount.com`
- secret refs:
  - `WP_URL -> wp-url`
  - `WP_USER -> wp-user`
  - `WP_APP_PASSWORD -> wp-app-password`
  - `WP_API_BASE -> wp-api-base`
  - `GEMINI_API_KEY -> gemini-api-key`

## manual smoke

```bash
export CLOUDSDK_CONFIG=/tmp/gcloud-config
gcloud run jobs execute guarded-publish \
  --region=asia-northeast1 \
  --project=baseballsite \
  --wait
```

Result:

- execution: `guarded-publish-x2724`
- exit: `0`
- live publish: `0 sent`
- history rows written at `2026-04-26T18:51:29.547524+09:00`: `74 refused`
  - `68` hard-stop rows
  - `6` cleanup-failed rows (`hold_reason=cleanup_failed_post_condition`)
- uploaded cleanup backups:
  - `63155_20260426T095129.json`
  - `63203_20260426T095129.json`
  - `63232_20260426T095129.json`
  - `63274_20260426T095129.json`
  - `63331_20260426T095129.json`
  - `63634_20260426T095129.json`

Observed runtime behavior:

- `guarded_publish_history.jsonl`, `guarded_publish_yellow_log.jsonl`, and `guarded_publish_cleanup_log.jsonl` were uploaded back to GCS.
- `cleanup_backup/` objects were uploaded to GCS for the 6 cleanup-failed candidates.
- no WordPress post reached `status=sent` in the manual smoke.

Implementation note:

- the spec sample initialized missing `guarded_publish_history.jsonl` with `[]`, but the runner consumes JSONL object rows. The shipped entrypoint initializes missing state files as empty files instead so the runner can parse them.

## cloud scheduler

```bash
export CLOUDSDK_CONFIG=/tmp/gcloud-config
gcloud scheduler jobs create http guarded-publish-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule='*/5 * * * *' \
  --time-zone='Asia/Tokyo' \
  --uri='https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/guarded-publish:run' \
  --http-method=POST \
  --oauth-service-account-email='487178857517-compute@developer.gserviceaccount.com' \
  --oauth-token-scope='https://www.googleapis.com/auth/cloud-platform' \
  --attempt-deadline=180s
```

Result:

- scheduler create: success
- state: `ENABLED`
- schedule: `*/5 * * * *`
- time zone: `Asia/Tokyo`
- target URI: `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/guarded-publish:run`
- next schedule after observation: `2026-04-26T10:00:04.532298Z`

## first auto tick observation

Observed the first scheduled tick at `18:55 JST`.

- Cloud Scheduler `AttemptFinished`: `Original HTTP response code number = 200`
- Cloud Run execution started by scheduler: `guarded-publish-npjqx`
- execution completion: success (`Container called exit(0).`)
- stdout summary:
  - `proposed_count=0`
  - `refused_count=0`
  - `would_publish=0`
  - `would_skip=0`
  - `executed=[]`

Interpretation:

- the scheduler invocation successfully ran the Cloud Run Job
- the job reused the persisted history from the manual smoke and found no additional candidates to execute on the next `:55` tick

## gcs persistence verify

Objects present under `gs://baseballsite-yoshilover-state/guarded_publish/` after the smoke + auto tick:

- `guarded_publish_history.jsonl`
- `guarded_publish_yellow_log.jsonl`
- `guarded_publish_cleanup_log.jsonl`
- `cleanup_backup/`

Backup objects verified:

- `cleanup_backup/63155_20260426T095129.json`
- `cleanup_backup/63203_20260426T095129.json`
- `cleanup_backup/63232_20260426T095129.json`
- `cleanup_backup/63274_20260426T095129.json`
- `cleanup_backup/63331_20260426T095129.json`
- `cleanup_backup/63634_20260426T095129.json`

## verify

- Artifact Registry:
  - `guarded-publish` tag `cd550f6` present
  - digest `sha256:8987524ff46a06cac72bb5bb84030d55fbff6b134fabb2ecf58aebf7e99b1a15`
- Cloud Run Job:
  - `guarded-publish` exists
  - image pinned to the digest above
  - latest successful scheduler execution: `guarded-publish-npjqx`
- Cloud Scheduler:
  - `guarded-publish-trigger` exists
  - `state=ENABLED`
  - `schedule=*/5 * * * *`
  - first observed attempt returned HTTP `200`
- repo safety:
  - `src/`, `tests/`, `requirements*.txt`: unchanged by ticket 160

## wsl cron

Attempted read-only verify:

```bash
crontab -l | grep "PUB-004-C\|guarded_publish" | head
```

Result in this shell:

```text
crontabs/fwns6/: fopen: Permission denied
```

Notes:

- no crontab mutation command was run in ticket 160
- WSL PUB-004-C remains untouched by this ticket

## notes

- The workspace fast-forwarded from the fire-time baseline `cd550f6` to `38eaa70` during execution via an external doc-only update (`176 close` / assignments sync). There was no overlap with the four tracked files for ticket 160.
- Pre-existing unrelated tracked changes were already present in `doc/done/2026-04/167-billing-alert-deployment-notes.md` and `src/custom.css`; they were not modified in this ticket.
- `guarded_publish_yellow_log.jsonl` and `guarded_publish_cleanup_log.jsonl` remained empty after the manual smoke because no cleanup-qualified candidate reached `status=sent`.
