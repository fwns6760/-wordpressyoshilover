# 177 deployment notes

## meta

- ticket: 177
- phase: 155 final
- date: 2026-04-26 JST
- operator: Codex
- repo: `/home/fwns6/code/wordpressyoshilover`
- git_head_at_note_update: `e39990b`
- image_tag_at_build_submit: `38eaa70`
- project: `baseballsite`
- region: `asia-northeast1`
- artifact_registry_repo: `yoshilover`
- cloud_run_job: `codex-shadow`
- cloud_scheduler_job: `codex-shadow-trigger`
- runtime_service_account: `487178857517-compute@developer.gserviceaccount.com`
- cloud_build_id: `3e0f940b-2a37-4895-9552-1d4e80f8affe`
- image_digest: `sha256:34d103b0476e642f9e427de665ec18781796acbcec9d363fee7a4b7d0833dcf1`
- smoke_execution: `codex-shadow-8zdmj`

## status

Stopped on manual smoke failure before Cloud Scheduler creation.

## auth secret

Local auth file existed before deploy and was handled without printing contents.

- local path: `~/.codex/auth.json`
- local sha256: `bcfbdfc2ce6dfefb330c33293b01a7f6556e301fc2ccbe36924ed0e47adfef62`
- local size: `4205` bytes

Secret Manager actions:

- secret created: `codex-auth-json`
- created at: `2026-04-26T09:53:31.523998Z`
- version added from local file: `1`
- IAM granted on the secret to `487178857517-compute@developer.gserviceaccount.com`
  - `roles/secretmanager.secretAccessor`
  - `roles/secretmanager.secretVersionAdder`

Post-smoke version state:

- listed versions: `1 enabled`
- writeback-created extra version: none observed

## artifact registry

Cloud Build command:

```bash
gcloud builds submit \
  --project=baseballsite \
  --region=asia-northeast1 \
  --config=cloudbuild_codex_shadow.yaml \
  --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=codex-shadow,_TAG=38eaa70 \
  .
```

Build result:

- build ID: `3e0f940b-2a37-4895-9552-1d4e80f8affe`
- status: `SUCCESS`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/codex-shadow:38eaa70`
- digest: `sha256:34d103b0476e642f9e427de665ec18781796acbcec9d363fee7a4b7d0833dcf1`

## cloud run job

Job create succeeded:

```bash
gcloud run jobs create codex-shadow \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/codex-shadow@sha256:34d103b0476e642f9e427de665ec18781796acbcec9d363fee7a4b7d0833dcf1 \
  --region=asia-northeast1 \
  --project=baseballsite \
  --task-timeout=600s \
  --max-retries=0 \
  --parallelism=1 \
  --tasks=1 \
  --service-account=487178857517-compute@developer.gserviceaccount.com \
  --set-env-vars=CODEX_AUTH_SECRET_NAME=codex-auth-json,CODEX_SHADOW_PROVIDER=codex,CODEX_SHADOW_MAX_POSTS=3 \
  --set-secrets=WP_URL=wp-url:latest,WP_USER=wp-user:latest,WP_APP_PASSWORD=wp-app-password:latest,GEMINI_API_KEY=gemini-api-key:latest
```

Verified job config:

- `parallelism: 1`
- `taskCount: 1`
- `maxRetries: 0`
- `timeoutSeconds: 600`
- service account: `487178857517-compute@developer.gserviceaccount.com`
- plain envs:
  - `CODEX_AUTH_SECRET_NAME=codex-auth-json`
  - `CODEX_SHADOW_PROVIDER=codex`
  - `CODEX_SHADOW_MAX_POSTS=3`
- secret refs:
  - `WP_URL -> wp-url`
  - `WP_USER -> wp-user`
  - `WP_APP_PASSWORD -> wp-app-password`
  - `GEMINI_API_KEY -> gemini-api-key`

## manual smoke

Command:

```bash
gcloud run jobs execute codex-shadow \
  --region=asia-northeast1 \
  --project=baseballsite \
  --wait
```

Result:

- execution: `codex-shadow-8zdmj`
- status: `EXECUTION_FAILED`
- failed count: `1`
- stop condition triggered: `Cloud Run Job execute exit non-zero`

Execution detail:

- `Task codex-shadow-8zdmj-task0 failed with exit code: 1 and message: The container exited with an error.`

Cloud Logging failure excerpt:

```text
ImportError: cannot import name 'NotRequired' from 'typing' (/usr/lib/python3.9/typing.py)
```

Root cause observed from the traceback:

- container runtime installed `python3` from Debian bullseye (`/usr/lib/python3.9/...`)
- `src/article_parts_renderer.py` imports `typing.NotRequired`
- the current image therefore fails before the shadow lane can emit any `shadow_only` ledger/output record

## scheduler

Not created.

Reason:

- ticket stop condition fired on manual smoke failure before `codex-shadow-trigger` creation

## verify snapshot

- Secret Manager: `codex-auth-json` exists, `1 enabled`
- Artifact Registry: `codex-shadow:38eaa70` present with digest `sha256:34d103b0476e642f9e427de665ec18781796acbcec9d363fee7a4b7d0833dcf1`
- Cloud Run Job: `codex-shadow` exists with `parallelism=1`, `maxRetries=0`
- Manual smoke: failed at import time
- Shadow lane invariant verify: not reached
- WP write verify: not reached
- Scheduler verify: not reached

## next required fix

Make the container run a Python version that supports `typing.NotRequired` and rerun the manual smoke before creating the scheduler.
