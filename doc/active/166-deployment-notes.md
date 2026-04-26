# 166 deployment notes

## scope

- ticket: `166 cloud-run-job-failure-alert`
- project: `baseballsite`
- region: `asia-northeast1`
- current lanes in scope: `draft-body-editor`, `publish-notice`
- notification target: `fwns6760@gmail.com`

## files

- `scripts/setup_cloud_run_alerts.sh`

## intended resources

- notification channel: email channel for `fwns6760@gmail.com` (reuse if already present)
- log-based metrics:
  - `cloud_run_job_failure_draft_body_editor`
  - `cloud_run_job_failure_publish_notice`
- alert policies:
  - `cron-fail-draft-body-editor`
  - `cron-fail-publish-notice`

## schedules embedded in alert documentation

- `draft-body-editor`: `2,12,22,32,42,52 * * * *` (`Asia/Tokyo`)
- `publish-notice`: `15 * * * *` (`Asia/Tokyo`)

## applied result

- script run date: `2026-04-26`
- notification channel:
  - resource: `projects/baseballsite/notificationChannels/7008520332246366374`
  - display name: `yoshilover cloud run job failure alerts`
  - api verification status field: `NOT_RETURNED_BY_API`
  - operator action: mailbox owner must click the verification email once
- log-based metrics:
  - `cloud_run_job_failure_draft_body_editor`
  - `cloud_run_job_failure_publish_notice`
- alert policies:
  - `projects/baseballsite/alertPolicies/6237466878651589140` = `cron-fail-draft-body-editor`
  - `projects/baseballsite/alertPolicies/10803386374382604927` = `cron-fail-publish-notice`
- policy settings verified:
  - threshold filter target: `logging.googleapis.com/user/cloud_run_job_failure_*` + `resource.type="cloud_run_job"`
  - auto-close: `1800s` (`30 min`)
  - notification channel: `projects/baseballsite/notificationChannels/7008520332246366374`

## deployment command

```bash
export CLOUDSDK_CONFIG=/tmp/gcloud-config
mkdir -p /tmp/gcloud-config
if [ -d ~/.config/gcloud ] && [ ! -d /tmp/gcloud-config/configurations ]; then
  cp -r ~/.config/gcloud/* /tmp/gcloud-config/ 2>/dev/null || true
fi

bash scripts/setup_cloud_run_alerts.sh
```

## verification commands

```bash
export CLOUDSDK_CONFIG=/tmp/gcloud-config
gcloud alpha monitoring policies list --project=baseballsite --format="table(displayName,enabled)" 2>&1 | head -10
gcloud alpha monitoring channels list --project=baseballsite --format="table(displayName,type,verificationStatus)" 2>&1 | head -5
gcloud logging metrics list --project=baseballsite --filter='name:(cloud_run_job_failure_)' --format="table(name,description)" 2>&1 | head -10
```

## operator note

- email notification channels require one manual verification click from the mailbox owner.
- `gcloud alpha monitoring channels describe` did not return a `verificationStatus` field immediately after create/reuse, so this note records that state as `NOT_RETURNED_BY_API`.
- ticket 166 does not include intentional fail injection. end-to-end alert mail smoke remains a separate user decision / follow-up ticket.
