# 161 deployment notes

## meta

- ticket: 161
- phase: 3
- date: 2026-04-26 JST
- operator: Codex
- repo: `/home/fwns6/code/wordpressyoshilover`
- git_head: `cbe05b0`
- project: `baseballsite`
- region: `asia-northeast1`
- artifact_registry_repo: `yoshilover`
- cloud_run_job: `publish-notice`
- smoke_execution: `publish-notice-96qxr`

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
  --config=cloudbuild_publish_notice.yaml \
  --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=publish-notice,_TAG=$(git rev-parse --short HEAD) \
  .
```

Result:

- build ID: `88c6d8f3-55f3-48b2-98be-22c94fd9cb46`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:cbe05b0`
- digest: `sha256:0ea0afb8e7c521ed20657e2c2048401cd9124844a50a7e8a565bb5f142dee596`
- status: `SUCCESS`

### 3. Cloud Run Job create

`.env` values were loaded from `/home/fwns6/code/wordpressyoshilover/.env` into `/tmp/publish_notice_env.yaml` and passed via `--env-vars-file` so secret values were never printed to stdout/stderr. `MAIL_BRIDGE_SMTP_USERNAME` and `MAIL_BRIDGE_FROM` were not present as dedicated `.env` keys, so both were derived from the single configured mail recipient address, matching the ticket spec.

```bash
python3 - <<'PY'
from dotenv import dotenv_values
from pathlib import Path
import json

vals = dotenv_values('/home/fwns6/code/wordpressyoshilover/.env')

def first(*keys):
    for key in keys:
        value = str(vals.get(key, '')).strip()
        if value:
            return value
    return ''

wp_url = str(vals.get('WP_URL', '')).strip()
wp_user = str(vals.get('WP_USER', '')).strip()
wp_app_password = str(vals.get('WP_APP_PASSWORD', '')).strip()
recipients = first('PUBLISH_NOTICE_EMAIL_TO', 'MAIL_BRIDGE_TO')
primary_recipient = recipients.split(',')[0].strip() if recipients else ''
smtp_username = first('MAIL_BRIDGE_SMTP_USERNAME', 'FACT_CHECK_EMAIL_FROM', 'MAIL_BRIDGE_FROM') or primary_recipient
sender = first('MAIL_BRIDGE_FROM', 'FACT_CHECK_EMAIL_FROM', 'MAIL_BRIDGE_SMTP_USERNAME') or primary_recipient
app_password = first('MAIL_BRIDGE_GMAIL_APP_PASSWORD', 'GMAIL_APP_PASSWORD')

env_map = {
    'PUBLISH_NOTICE_EMAIL_ENABLED': '1',
    'PUBLISH_NOTICE_EMAIL_TO': recipients,
    'MAIL_BRIDGE_TO': recipients,
    'MAIL_BRIDGE_SMTP_USERNAME': smtp_username,
    'MAIL_BRIDGE_FROM': sender,
    'MAIL_BRIDGE_GMAIL_APP_PASSWORD': app_password,
    'WP_URL': wp_url,
    'WP_USER': wp_user,
    'WP_APP_PASSWORD': wp_app_password,
    'WP_API_BASE': wp_url.rstrip('/') + '/wp-json/wp/v2',
}

out = Path('/tmp/publish_notice_env.yaml')
with out.open('w', encoding='utf-8') as handle:
    for key, value in env_map.items():
        handle.write(f"{key}: {json.dumps(value, ensure_ascii=False)}\n")
print(out)
PY

IMAGE="asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:$(git -C /home/fwns6/code/wordpressyoshilover rev-parse --short HEAD)"
gcloud run jobs create publish-notice \
  --image="$IMAGE" \
  --region=asia-northeast1 \
  --project=baseballsite \
  --task-timeout=300s \
  --max-retries=1 \
  --env-vars-file=/tmp/publish_notice_env.yaml
```

Result:

- job create: success
- task timeout: `300s`
- max retries: `1`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:cbe05b0`

### 4. Manual smoke execute

```bash
gcloud run jobs execute publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --wait
```

Result:

- execution: `publish-notice-96qxr`
- exit: `0`
- status: success

### 5. Cloud Scheduler create

```bash
gcloud scheduler jobs create http publish-notice-trigger \
  --location=asia-northeast1 \
  --project=baseballsite \
  --schedule='15 * * * *' \
  --time-zone='Asia/Tokyo' \
  --uri='https://run.googleapis.com/v2/projects/baseballsite/locations/asia-northeast1/jobs/publish-notice:run' \
  --http-method=POST \
  --headers='Content-Type=application/json' \
  --message-body='{}' \
  --oauth-service-account-email='seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com' \
  --oauth-token-scope='https://www.googleapis.com/auth/cloud-platform' \
  --attempt-deadline=180s
```

Result:

- scheduler create/update: success
- schedule: `15 * * * *`
- state: `ENABLED`
- target URI: `https://run.googleapis.com/v2/projects/baseballsite/locations/asia-northeast1/jobs/publish-notice:run`

## masked env snapshot

- `PUBLISH_NOTICE_EMAIL_ENABLED=***`
- `PUBLISH_NOTICE_EMAIL_TO=***`
- `MAIL_BRIDGE_TO=***`
- `MAIL_BRIDGE_SMTP_USERNAME=***`
- `MAIL_BRIDGE_FROM=***`
- `MAIL_BRIDGE_GMAIL_APP_PASSWORD=***`
- `WP_URL=***`
- `WP_USER=***`
- `WP_APP_PASSWORD=***`
- `WP_API_BASE=***`

## smoke output summary

Cloud Logging (`run.googleapis.com/stdout`) showed one stdout entry for `publish-notice-96qxr`:

```text
[scan] emitted=0 skipped=0 cursor_before=None cursor_after=2026-04-26T17:18:52.628221+09:00
```

Interpretation:

- the job ran in live mode once, as specified
- this smoke created the initial cursor and emitted `0` per-post notices
- live mail count for this smoke was `0`
- container system log ended with `Container called exit(0).`

## verify

### Artifact Registry

`gcloud artifacts docker images list asia-northeast1-docker.pkg.dev/baseballsite/yoshilover --include-tags | grep publish-notice`

- `publish-notice` tag `cbe05b0` present

### Cloud Run Job

`gcloud run jobs describe publish-notice --region=asia-northeast1 --project=baseballsite --format='value(metadata.name,status.latestCreatedExecution.name,status.latestCreatedExecution.completionStatus,spec.template.spec.template.spec.timeoutSeconds,spec.template.spec.template.spec.maxRetries)'`

- job exists
- latest execution: `publish-notice-96qxr`
- completion status: `EXECUTION_SUCCEEDED`
- timeout: `300`
- max retries: `1`

### Cloud Scheduler

`gcloud scheduler jobs describe publish-notice-trigger --location=asia-northeast1 --project=baseballsite | head -10`

- job exists
- OAuth service account: `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com`
- body: `{}`
- state: `ENABLED`

### Cloud Logging

`gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=publish-notice AND labels."run.googleapis.com/execution_name"="publish-notice-96qxr"' --limit=20 --project=baseballsite --format='value(timestamp,logName,textPayload,jsonPayload.message)'`

- stdout entry present: `[scan] emitted=0 skipped=0 cursor_before=None ...`
- system log present: `Container called exit(0).`

### repo safety

- `src/`, `tests/`, `requirements*.txt`: no changes introduced by ticket 161
- tracked files added by this ticket: `Dockerfile.publish_notice`, `cloudbuild_publish_notice.yaml`, `doc/active/161-deployment-notes.md`

### WSL cron 095 line

Attempted verify command:

```bash
crontab -l | grep -E 'publish_notice|095-WSL-CRON-FALLBACK' | head -3
```

Result in this execution environment:

```text
crontabs/fwns6/: fopen: Permission denied
```

Notes:

- no crontab mutation command was run in this ticket
- direct read verification of the WSL crontab was blocked by local permission constraints in this shell

## notes

- The ticket spec baseline said `HEAD=0981ee2`, but the actual workspace `git rev-parse --short HEAD` at execution time was `cbe05b0`; the image tag and deployment records follow the actual local HEAD.
- Because this phase intentionally uses `/data` as a placeholder without shared persistence, the smoke execution only bootstrapped a fresh cursor and did not send mail. Until ticket 158 adds persistent storage, each Cloud Run Job execution will behave as a first-run bootstrap and will not replace the WSL 095 lane for real publish notices.
