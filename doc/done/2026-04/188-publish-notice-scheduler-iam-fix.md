# 188 publish-notice scheduler IAM fix runbook

## meta

- number: 188
- owner: Codex
- type: ops / scheduler IAM repair runbook
- status: CLOSED
- priority: P0.5
- lane: A
- created: 2026-04-27
- landed_in: `74ccef6`
- parent: 161 / 187 / 160

## scope

- read-only compare only
- no live IAM / Scheduler / Cloud Run Job write from Codex
- deliver a user-shell runbook that fixes `PERMISSION_DENIED`

## observed facts

### 1. Scheduler YAML diff

Compared:

```bash
gcloud scheduler jobs describe publish-notice-trigger --project=baseballsite --location=asia-northeast1 --format=yaml
gcloud scheduler jobs describe guarded-publish-trigger --project=baseballsite --location=asia-northeast1 --format=yaml
```

Key diff:

- both jobs use the same Cloud Run Jobs v1 regional URI shape:
  - `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/<job>:run`
- both jobs use `oauthToken`, not `oidcToken`
- `publish-notice-trigger` caller SA:
  - `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com`
- `guarded-publish-trigger` caller SA:
  - `487178857517-compute@developer.gserviceaccount.com`
- `attemptDeadline` and `retryConfig` are effectively the same
- `publish-notice-trigger` has `Content-Type: application/json` and body `{}`; `guarded-publish-trigger` does not
- only `publish-notice-trigger` shows `status.code: 7`

Conclusion:

- the 187 v2 -> v1 URI fix removed the path mismatch risk
- the remaining meaningful runtime difference is the OAuth caller service account

### 2. Cloud Run Job IAM policy diff

Compared:

```bash
gcloud run jobs get-iam-policy guarded-publish --project=baseballsite --region=asia-northeast1
gcloud run jobs get-iam-policy publish-notice --project=baseballsite --region=asia-northeast1
```

Result:

- both returned only `etag: ACAB`
- no job-level bindings were present on either job

Conclusion:

- there is no job-level allowlist difference today
- any successful call must therefore come from project-level privilege or a future job-level binding

### 3. Project-level IAM compare of the two caller SAs

Checked:

```bash
gcloud projects get-iam-policy baseballsite \
  --flatten='bindings[].members' \
  --filter='bindings.members:serviceAccount:seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com' \
  --format='table(bindings.role,bindings.members)'

gcloud projects get-iam-policy baseballsite \
  --flatten='bindings[].members' \
  --filter='bindings.members:serviceAccount:487178857517-compute@developer.gserviceaccount.com' \
  --format='table(bindings.role,bindings.members)'
```

Result:

- `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com`
  - no project-level bindings returned
- `487178857517-compute@developer.gserviceaccount.com`
  - `roles/editor`
  - `roles/secretmanager.secretAccessor`

Role definition check:

```bash
gcloud iam roles describe roles/run.invoker --format='yaml(name,title,includedPermissions)'
```

Returned:

- `roles/run.invoker`
  - `run.jobs.run`
  - `run.routes.invoke`

Conclusion:

- the guarded path works because its caller SA already has project-level privilege that includes `run.jobs.run`
- the publish-notice scheduler SA does not show any project-level privilege and has no job-level binding either

### 4. Failure logs and execution evidence

Checked:

```bash
gcloud logging read 'resource.type=cloud_scheduler_job AND resource.labels.job_id=publish-notice-trigger AND timestamp>="2026-04-26T23:10:00Z"' --project=baseballsite --limit=10
gcloud logging read 'resource.type=cloud_scheduler_job AND resource.labels.job_id=guarded-publish-trigger AND timestamp>="2026-04-26T23:10:00Z"' --project=baseballsite --limit=5
gcloud run jobs executions list --job=publish-notice --project=baseballsite --region=asia-northeast1 --limit=5
gcloud run jobs executions list --job=guarded-publish --project=baseballsite --region=asia-northeast1 --limit=5
```

Result:

- `publish-notice-trigger`
  - `2026-04-26T23:15:12Z` -> HTTP `403`, `PERMISSION_DENIED`
  - `2026-04-26T23:18:02Z` -> HTTP `403`, `PERMISSION_DENIED`
- `guarded-publish-trigger`
  - repeated HTTP `200`
- `publish-notice` executions
  - newest execution is manual `publish-notice-9vd48`
  - created `2026-04-26 23:11:58 UTC`
  - run by `fwns6760@gmail.com`
  - no scheduler-created execution exists after the failed `23:15Z` / `23:18Z` attempts
- `guarded-publish` executions
  - created by `487178857517-compute@developer.gserviceaccount.com`

## true cause

The remaining failure is not URI shape, retry config, or attempt deadline.

The true cause is:

- `publish-notice-trigger` authenticates with `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com`
- that service account has no observed project-level binding granting `run.jobs.run`
- `publish-notice` also has no job-level `roles/run.invoker` binding
- Cloud Scheduler therefore reaches the Cloud Run Jobs endpoint and receives HTTP `403 PERMISSION_DENIED`

## recommended repair path

Recommended: keep the dedicated scheduler SA and grant it least-privilege invoke permission on the `publish-notice` job.

### Fix A (recommended): add job-level `roles/run.invoker`

Run from the user shell:

```bash
gcloud run jobs add-iam-policy-binding publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --member='serviceAccount:seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com' \
  --role='roles/run.invoker'
```

Expected result:

- command exits `0`
- `gcloud run jobs get-iam-policy publish-notice ...` shows one binding:
  - role `roles/run.invoker`
  - member `serviceAccount:seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com`

### Verify after Fix A

```bash
gcloud run jobs get-iam-policy publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --format='table(bindings.role,bindings.members)'

gcloud scheduler jobs run publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1

gcloud logging read 'resource.type=cloud_scheduler_job AND resource.labels.job_id=publish-notice-trigger' \
  --project=baseballsite \
  --limit=5 \
  --format='table(timestamp,severity,httpRequest.status,jsonPayload.status,jsonPayload.debugInfo)'

gcloud run jobs executions list \
  --job=publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --limit=5
```

Success criteria:

- latest scheduler log is `INFO` with HTTP `200`
- latest execution list contains a new execution newer than `publish-notice-9vd48`
- `RUN BY` is `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com` or the bound caller used by the scheduler

### Rollback for Fix A

```bash
gcloud run jobs remove-iam-policy-binding publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --member='serviceAccount:seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com' \
  --role='roles/run.invoker'
```

## alternate repair paths

### Fix B: align the scheduler SA with `guarded-publish-trigger`

Use this if you want both schedulers to share the same proven caller identity instead of keeping a dedicated publish-notice SA.

```bash
gcloud scheduler jobs update http publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule='15 * * * *' \
  --time-zone='Asia/Tokyo' \
  --uri='https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/publish-notice:run' \
  --http-method=POST \
  --headers='Content-Type=application/json' \
  --message-body='{}' \
  --oauth-service-account-email='487178857517-compute@developer.gserviceaccount.com' \
  --oauth-token-scope='https://www.googleapis.com/auth/cloud-platform' \
  --attempt-deadline=180s
```

Expected result:

- scheduler update exits `0`
- `describe` shows the compute SA as the OAuth caller
- subsequent manual run returns HTTP `200`

Rollback for Fix B:

```bash
gcloud scheduler jobs update http publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule='15 * * * *' \
  --time-zone='Asia/Tokyo' \
  --uri='https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/publish-notice:run' \
  --http-method=POST \
  --headers='Content-Type=application/json' \
  --message-body='{}' \
  --oauth-service-account-email='seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com' \
  --oauth-token-scope='https://www.googleapis.com/auth/cloud-platform' \
  --attempt-deadline=180s
```

### Fix C: project-level fallback

Only use this if job-level binding is blocked by policy or CLI version. It is broader than Fix A.

```bash
gcloud projects add-iam-policy-binding baseballsite \
  --member='serviceAccount:seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com' \
  --role='roles/run.invoker'
```

Rollback:

```bash
gcloud projects remove-iam-policy-binding baseballsite \
  --member='serviceAccount:seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com' \
  --role='roles/run.invoker'
```

## no SA creation needed

- `seo-scheduler-invoker@baseballsite.iam.gserviceaccount.com` already exists
- this ticket does not require new service account creation

## next action

- user runs Fix A first
- if Fix A is blocked by policy or does not clear the 403, use Fix B
- after one fix path succeeds, move this ticket to `CLOSED` and archive the doc under `doc/done/2026-04/`
