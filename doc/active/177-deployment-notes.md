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

## fix rerun (2026-04-26 JST)

### repo change

- `Dockerfile.codex_shadow`
  - base image changed from `node:22-bullseye-slim` to `python:3.12-slim`
  - Node 22 is now installed explicitly from NodeSource during image build
  - this keeps `python3` on the image-native 3.12 toolchain and avoids the Debian bullseye Python 3.9 import failure

### cloud build retry sequence

First retry used `node:22-bookworm-slim` and failed at build time because Debian bookworm marked the system Python environment as externally managed (PEP 668), so `python3 -m pip install ...` was rejected.

- failed retry build ID: `4993a7ff-8b53-405b-8a69-027ca6ac2be2`
- failed retry tag: `177-fix-20260426-191134`
- failed retry stop point: Docker build step 1 / pip install

Second retry switched to `python:3.12-slim` and succeeded.

- successful retry build ID: `4f03f2bf-ffb0-4814-bf57-f1df5f39e28d`
- successful retry tag: `177-fix-20260426-191134-py312`
- successful image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/codex-shadow:177-fix-20260426-191134-py312`
- successful digest: `sha256:6ba7d75668070282f642a46a1fe72150013ed04de6226186568afc62c4722fc8`
- build status: `SUCCESS`

### cloud run job update

Job image update command:

```bash
gcloud run jobs update codex-shadow \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/codex-shadow@sha256:6ba7d75668070282f642a46a1fe72150013ed04de6226186568afc62c4722fc8 \
  --region=asia-northeast1 \
  --project=baseballsite
```

Verified job state after update:

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/codex-shadow@sha256:6ba7d75668070282f642a46a1fe72150013ed04de6226186568afc62c4722fc8`
- parallelism: `1`
- taskCount: `1`
- maxRetries: `0`
- timeoutSeconds: `600`
- service account: `487178857517-compute@developer.gserviceaccount.com`

### manual smoke reruns

Default smoke:

- execution: `codex-shadow-w6lnx`
- command: existing job args (`--provider codex --max-posts 3`)
- result: `exit 0`
- completion: `Execution completed successfully in 45.66s.`
- stdout summary:
  - `processed: 3`
  - `edited: 0`
  - `put_ok: 0`
  - `stop_reason: completed`

Expanded smoke 1:

- execution: `codex-shadow-9fv4v`
- command override: `--provider codex --max-posts 10`
- result: `exit 0`
- completion: `Execution completed successfully in 43.41s.`
- stdout summary:
  - `processed: 10`
  - `edited: 0`
  - `put_ok: 0`
  - `stop_reason: completed`

Expanded smoke 2:

- execution: `codex-shadow-qk6m2`
- command override: `--provider codex --max-posts 25`
- result: `exit 0`
- completion: `Execution completed successfully in 41.69s.`
- stdout summary:
  - `processed: 18`
  - `edited: 0`
  - `put_ok: 0`
  - `stop_reason: completed`

Interpretation:

- the original import failure is resolved; all three executions completed successfully on the new image
- `put_ok: 0` across all reruns verified **WP write 0**
- current live draft pool did not yield an editable candidate during the reruns (`guard_fail` / `heading_mismatch` / `subtype_unresolved` only), so a live Cloud Logging observation of a new `shadow_only` row was not available from these three executions
- the codex shadow-only write-skip path was additionally verified by the existing unit test:
  - `python3 -m unittest tests.test_run_draft_body_editor_lane.TestLaneMain.test_provider_fallback_controller_codex_shadow_only_skips_wp_put`
  - result: `OK`

### cloud scheduler

Scheduler create command:

```bash
gcloud scheduler jobs create http codex-shadow-trigger \
  --location=asia-northeast1 \
  --project=baseballsite \
  --schedule='5,15,25,35,45,55 * * * *' \
  --time-zone='Asia/Tokyo' \
  --uri='https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/codex-shadow:run' \
  --http-method=POST \
  --oauth-service-account-email='487178857517-compute@developer.gserviceaccount.com' \
  --oauth-token-scope='https://www.googleapis.com/auth/cloud-platform' \
  --attempt-deadline=180s
```

Scheduler verify:

- name: `projects/baseballsite/locations/asia-northeast1/jobs/codex-shadow-trigger`
- schedule: `5,15,25,35,45,55 * * * *`
- time zone: `Asia/Tokyo`
- state: `ENABLED`
- next schedule after create: `2026-04-26T10:45:00Z`

### auth handling

- auth secret content remained masked throughout the rerun work
- no auth.json payload, token field, or secret value was printed to chat / log / commit text
