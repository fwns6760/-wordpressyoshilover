# 158 deployment notes

## meta

- ticket: 158
- phase: 1d
- date: 2026-04-26 JST
- operator: Codex
- repo: `/home/fwns6/code/wordpressyoshilover`
- git_head: `e5deca9`
- project: `baseballsite`
- region: `asia-northeast1`
- artifact_registry_repo: `yoshilover`
- bucket: `gs://baseballsite-yoshilover-state`
- runtime_service_account: `487178857517-compute@developer.gserviceaccount.com`
- draft_body_editor_job: `draft-body-editor`
- publish_notice_job: `publish-notice`
- publish_notice_image_digest: `sha256:44d84374cb203267700c616023864532cf9d446a6157f5b5672362ec5972fcc0`
- publish_notice_build_id: `51973b45-ee32-467b-8dc5-45ab4afb77ce`
- publish_notice_execution_1: `publish-notice-njfrj`
- publish_notice_execution_2: `publish-notice-l6qkx`

## secret manager

11 secrets were created or updated from the local `.env` source without printing values to stdout/stderr.

- `WP_URL` -> `wp-url`
- `WP_USER` -> `wp-user`
- `WP_APP_PASSWORD` -> `wp-app-password`
- `WP_API_BASE` -> `wp-api-base`
- `GEMINI_API_KEY` -> `gemini-api-key`
- `MAIL_BRIDGE_SMTP_USERNAME` -> `mail-bridge-smtp-username`
- `MAIL_BRIDGE_FROM` -> `mail-bridge-from`
- `MAIL_BRIDGE_GMAIL_APP_PASSWORD` -> `mail-bridge-gmail-app-password`
- `MAIL_BRIDGE_TO` -> `mail-bridge-to`
- `PUBLISH_NOTICE_EMAIL_TO` -> `publish-notice-email-to`
- `PUBLISH_NOTICE_EMAIL_ENABLED` -> `publish-notice-email-enabled`

Notes:

- `WP_API_BASE` was derived from `WP_URL` when not present as a dedicated `.env` key.
- `MAIL_BRIDGE_SMTP_USERNAME` / `MAIL_BRIDGE_FROM` followed the same fallback chain used in ticket 161.
- Values are intentionally omitted from this document.

## bucket and iam

```bash
gcloud storage buckets create gs://baseballsite-yoshilover-state \
  --location=asia-northeast1 \
  --project=baseballsite \
  --uniform-bucket-level-access
```

Result:

- bucket created: `gs://baseballsite-yoshilover-state`
- IAM grant applied: `roles/storage.objectAdmin` to `487178857517-compute@developer.gserviceaccount.com`

## cloud run job updates

### draft-body-editor

The existing plain env vars had to be removed first because Cloud Run rejects direct type changes from plain env to Secret refs.

```bash
gcloud run jobs update draft-body-editor \
  --region=asia-northeast1 \
  --project=baseballsite \
  --remove-env-vars='WP_URL,WP_USER,WP_APP_PASSWORD,GEMINI_API_KEY'

gcloud run jobs update draft-body-editor \
  --region=asia-northeast1 \
  --project=baseballsite \
  --update-secrets='WP_URL=wp-url:latest,WP_USER=wp-user:latest,WP_APP_PASSWORD=wp-app-password:latest,GEMINI_API_KEY=gemini-api-key:latest'
```

Verified Secret refs:

- `WP_URL` -> `wp-url`
- `WP_USER` -> `wp-user`
- `WP_APP_PASSWORD` -> `wp-app-password`
- `GEMINI_API_KEY` -> `gemini-api-key`

### publish-notice

The existing plain env vars were removed first, then the job was updated with Secret refs and the new image digest.

```bash
gcloud run jobs update publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --remove-env-vars='PUBLISH_NOTICE_EMAIL_ENABLED,PUBLISH_NOTICE_EMAIL_TO,MAIL_BRIDGE_TO,MAIL_BRIDGE_SMTP_USERNAME,MAIL_BRIDGE_FROM,MAIL_BRIDGE_GMAIL_APP_PASSWORD,WP_URL,WP_USER,WP_APP_PASSWORD,WP_API_BASE'

gcloud run jobs update publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --update-secrets='PUBLISH_NOTICE_EMAIL_ENABLED=publish-notice-email-enabled:latest,PUBLISH_NOTICE_EMAIL_TO=publish-notice-email-to:latest,MAIL_BRIDGE_TO=mail-bridge-to:latest,MAIL_BRIDGE_SMTP_USERNAME=mail-bridge-smtp-username:latest,MAIL_BRIDGE_FROM=mail-bridge-from:latest,MAIL_BRIDGE_GMAIL_APP_PASSWORD=mail-bridge-gmail-app-password:latest,WP_URL=wp-url:latest,WP_USER=wp-user:latest,WP_APP_PASSWORD=wp-app-password:latest,WP_API_BASE=wp-api-base:latest'
```

Final image:

- `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice@sha256:44d84374cb203267700c616023864532cf9d446a6157f5b5672362ec5972fcc0`

Verified Secret refs:

- `PUBLISH_NOTICE_EMAIL_ENABLED` -> `publish-notice-email-enabled`
- `PUBLISH_NOTICE_EMAIL_TO` -> `publish-notice-email-to`
- `MAIL_BRIDGE_TO` -> `mail-bridge-to`
- `MAIL_BRIDGE_SMTP_USERNAME` -> `mail-bridge-smtp-username`
- `MAIL_BRIDGE_FROM` -> `mail-bridge-from`
- `MAIL_BRIDGE_GMAIL_APP_PASSWORD` -> `mail-bridge-gmail-app-password`
- `WP_URL` -> `wp-url`
- `WP_USER` -> `wp-user`
- `WP_APP_PASSWORD` -> `wp-app-password`
- `WP_API_BASE` -> `wp-api-base`

## publish-notice image build

Final successful build:

```bash
gcloud builds submit \
  --project=baseballsite \
  --region=asia-northeast1 \
  --config=cloudbuild_publish_notice.yaml \
  --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=publish-notice,_TAG=e5deca9 \
  .
```

Result:

- build ID: `51973b45-ee32-467b-8dc5-45ab4afb77ce`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:e5deca9`
- digest: `sha256:44d84374cb203267700c616023864532cf9d446a6157f5b5672362ec5972fcc0`
- status: `SUCCESS`

## persistence verify

Bucket objects after the successful runs:

- `gs://baseballsite-yoshilover-state/publish_notice/cursor.txt`
- `gs://baseballsite-yoshilover-state/publish_notice/history.json`

Cloud Logging excerpts:

- execution `publish-notice-njfrj`
  - `[scan] emitted=0 skipped=0 cursor_before=None cursor_after=2026-04-26T18:03:48.204091+09:00`
- execution `publish-notice-l6qkx`
  - `[scan] emitted=0 skipped=0 cursor_before=2026-04-26T18:03:48.204091+09:00 cursor_after=2026-04-26T18:04:31.593636+09:00`

Interpretation:

- first execution bootstrapped the persisted cursor in GCS
- second execution downloaded the prior cursor and advanced it
- live mail count for both manual executions: `0`

## repo verify

- targeted test: `tests/test_cloud_run_persistence.py` -> `9 passed`
- full pytest: `1404 passed`
- collect-only: `1404 tests collected`

## wsl cron

Attempted read-only verify command:

```bash
crontab -l | rg 'draft_body|publish_notice'
```

Result in this shell:

```text
crontabs/fwns6/: fopen: Permission denied
```

Notes:

- no crontab mutation command was run during ticket 158
- WSL 042 / 095 remain untouched by implementation and deployment steps in this ticket

## notes

- The workspace HEAD advanced from the fire-time baseline `ace5207` to `e5deca9` during execution via an upstream doc-only fast-forward. There was no overlap with the five tracked files for ticket 158.
- The original spec called for `gsutil`-based persistence. In Cloud Run runtime, the pip-installed `gsutil` path executed anonymously and failed with 401/anonymous caller errors. The final shipped implementation keeps the same `GCSStateManager` interface and subprocess pattern but uses `gcloud storage cp/mv`, which authenticated correctly with the Cloud Run service account and passed the two-run persistence verify.
