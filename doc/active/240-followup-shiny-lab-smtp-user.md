# 240-followup shiny-lab.org Workspace SMTP user switch

- number: 240-followup
- type: minimal impl + runbook
- status: REVIEW_NEEDED
- priority: P0.5
- parent: 240
- related: 219, 222, 223, 231
- owner: Codex A
- lane: A
- created: 2026-04-28

## Background

`shiny-lab.org` is now confirmed as a Google Workspace domain on the user side.
The target state for notification mail is:

- SMTP login user: `y.sebata@shiny-lab.org`
- `From`: `y.sebata@shiny-lab.org`
- `To`: `fwns6760@gmail.com`
- `Reply-To`: `fwns6760@gmail.com`

The goal of this follow-up is to verify whether the current bridge already supports that switch via env only, and to document the minimum production apply runbook without performing any live mutation here.

This follow-up intentionally does not edit `doc/README.md`, `doc/active/assignments.md`, or the existing `240` audit doc.

## Step 1 Audit Result

### external App Password caveat (`Q1.a-e`)

| check | result | evidence / note |
|---|---|---|
| `Q1.a` 2-Step Verification requirement | YES | Google Account Help says App Passwords require 2-Step Verification. User must enable 2SV on `y.sebata@shiny-lab.org` before apply. |
| `Q1.b` organization-account caveat | USER / ADMIN CONFIRM REQUIRED | Google Account Help says the App Password option may be unavailable on work/school/org accounts. Codex cannot prove tenant-side availability from repo state; user or Workspace admin must confirm. |
| `Q1.c` Workspace legacy-app policy caveat | USER / ADMIN CONFIRM REQUIRED | Google Workspace Help says legacy apps can use App Passwords, but enforced security-key-only 2SV disables App Passwords. Tenant policy confirmation is required. |
| `Q1.d` Gmail host compatibility assumption | YES, repo side | Current bridge default host is `smtp.gmail.com`; no repo-side blocker exists for Workspace Gmail SMTP on that host. Live auth success still depends on the tenant/app-password side. |
| `Q1.e` SSL port compatibility assumption | YES, repo side | Current bridge default port is `465` and the live send path uses `smtplib.SMTP_SSL(...)`; no STARTTLS rewrite is required in repo code. |

Reference sources used for `Q1`:

- Google Account Help: https://support.google.com/accounts/answer/185833?hl=en
- Google Workspace Help: https://knowledge.workspace.google.com/admin/security/how-2-step-verification-works-with-legacy-apps?hl=en&rd=1

### bridge / sender audit (`Q2-Q10`)

| # | check | result |
|---|---|---|
| `Q2` | `smtp.gmail.com:465 / SMTP_SSL` path exists | YES. Defaults are `DEFAULT_SMTP_HOST = "smtp.gmail.com"` and `DEFAULT_SMTP_PORT = 465`; live send uses `smtplib.SMTP_SSL(...)` at [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:15), [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:16), [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:265). |
| `Q3` | `MAIL_BRIDGE_SMTP_USERNAME` and `MAIL_BRIDGE_FROM` can both be set to `y.sebata@shiny-lab.org` | YES. SMTP login resolves from `MAIL_BRIDGE_SMTP_USERNAME`; `From` resolves independently from `MAIL_BRIDGE_FROM` / `NOTIFY_FROM` at [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:192), [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:199). |
| `Q4` | new secret name `yoshilover-shiny-lab-gmail-app-password` can be used without overwriting the existing secret | YES, with one apply caveat. Code supports `MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME` and loads it through Secret Manager at [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:104), [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:109), [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:122). However `MAIL_BRIDGE_GMAIL_APP_PASSWORD` direct env has higher precedence, so the live job must remove that direct secret/env binding if the new secret-name path is adopted. |
| `Q5` | `MAIL_BRIDGE_REPLY_TO=fwns6760@gmail.com` can be set by env | YES. `Reply-To` resolves from `MAIL_BRIDGE_REPLY_TO` / `NOTIFY_REPLY_TO` and is added only when present at [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:206), [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:218). |
| `Q6` | minimum code patch needed for `Reply-To` | NO. Current code already supports `MAIL_BRIDGE_REPLY_TO`; no `src/` change is required for this follow-up. |
| `Q7` | Cloud Run `publish-notice` env / secret update runbook produced | YES. See the runbook below. |
| `Q8` | one-mail smoke procedure produced | YES. See the smoke section below. |
| `Q9` | rollback procedure produced | YES. See the rollback section below. |
| `Q10` | `YOSHILOVER` subject suffix survives sender switch | YES. Subject branding is built in `publish_notice_email_sender` and does not depend on bridge sender envs at [src/publish_notice_email_sender.py](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:1326), [src/publish_notice_email_sender.py](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:1718). Coverage was added in [tests/test_publish_notice_email_sender.py](/home/fwns6/code/wordpressyoshilover/tests/test_publish_notice_email_sender.py:1318). |

## Step 2 SMTP host / port env evaluation

Current code already supports:

- `MAIL_BRIDGE_SMTP_HOST` with default fallback `smtp.gmail.com`
- `MAIL_BRIDGE_SMTP_PORT` with default fallback `465`

That means the desired Workspace switch is already repo-compatible without any new `src/` patch.
Explicitly setting the host and port remains acceptable for clarity and future-proofing, but it is not required for correctness because the current defaults already match the desired Gmail Workspace endpoint.

## Decision

This follow-up lands as **case 3a**:

- requested env knobs already exist
- no repo code change is required in `src/`
- only audit/runbook documentation and narrow regression tests were added

## Secret / env design note

The app-password path has two modes:

1. direct env value: `MAIL_BRIDGE_GMAIL_APP_PASSWORD`
2. secret-name indirection: `MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME` -> runtime Secret Manager API fetch

Current precedence favors mode 1.
Therefore, switching to the new secret name `yoshilover-shiny-lab-gmail-app-password` requires the live executor to remove the existing `MAIL_BRIDGE_GMAIL_APP_PASSWORD` secret/env binding from `publish-notice`; otherwise the direct env value continues to win and the new secret-name env is ignored.

The secret-name mode also assumes the Cloud Run job service account can access the new secret through Secret Manager. This follow-up does not perform that IAM verification or any live grant.

## Required new secret

- `yoshilover-shiny-lab-gmail-app-password`

Do not overwrite the existing mail bridge app-password secret.

## Production Apply Runbook (user / authenticated executor boundary)

### 0. snapshot for rollback

```bash
gcloud run jobs describe publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --format=yaml > /tmp/publish-notice.before.yaml
```

### 1. Workspace-side App Password creation

User-side only:

- sign in as `y.sebata@shiny-lab.org`
- enable 2-Step Verification if it is not already enabled
- confirm the tenant actually exposes App Passwords for that managed account
- create an App Password for Mail / custom name `yoshilover-publish-notice`

If the App Password UI is absent, stop here and resolve the Workspace admin policy first.

### 2. create the new Secret Manager secret

```bash
gcloud secrets create yoshilover-shiny-lab-gmail-app-password \
  --replication-policy=automatic \
  --project=baseballsite

read -s APP_PASSWORD
printf '%s' "$APP_PASSWORD" | gcloud secrets versions add yoshilover-shiny-lab-gmail-app-password \
  --data-file=- \
  --project=baseballsite
unset APP_PASSWORD
```

### 3. update `publish-notice`

This version switches the job from secret-backed env vars for sender credentials to explicit env vars for username/from, and removes the direct `MAIL_BRIDGE_GMAIL_APP_PASSWORD` binding so that the new `MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME` path can take effect.

```bash
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-secrets=MAIL_BRIDGE_TO,MAIL_BRIDGE_SMTP_USERNAME,MAIL_BRIDGE_FROM,MAIL_BRIDGE_GMAIL_APP_PASSWORD \
  --update-env-vars=MAIL_BRIDGE_TO=fwns6760@gmail.com,MAIL_BRIDGE_SMTP_USERNAME=y.sebata@shiny-lab.org,MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org,MAIL_BRIDGE_REPLY_TO=fwns6760@gmail.com,MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME=yoshilover-shiny-lab-gmail-app-password,MAIL_BRIDGE_SMTP_HOST=smtp.gmail.com,MAIL_BRIDGE_SMTP_PORT=465
```

Notes:

- `MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME` is a plain env var containing the secret name; the password value is fetched inside the job by `src/mail_delivery_bridge.py`.
- `--update-secrets` is not required for the new app-password path because the code uses Secret Manager directly.
- if the execution fails with a Secret Manager access error, stop and grant the `publish-notice` runtime service account access to `yoshilover-shiny-lab-gmail-app-password` before retrying. This follow-up does not make IAM changes.
- if `MAIL_BRIDGE_TO` is already correct and the operator wants the smallest possible change surface, that key can remain secret-backed instead of being moved to plain env; the command above chooses explicit full-state clarity.
- keep `NOTIFY_FROM` and `NOTIFY_REPLY_TO` unset unless there is a deliberate reason to override `MAIL_BRIDGE_FROM` / `MAIL_BRIDGE_REPLY_TO`.

### 4. optional follow-up audit for other bridge consumers

Repo grep shows other sender modules consume `MAIL_BRIDGE_TO` and the shared bridge:

- `src/x_draft_email_sender.py`
- `src/ops_status_email_sender.py`
- `src/morning_analyst_email_sender.py`

This follow-up does not prove which Cloud Run Jobs, if any, back those modules in production. If separate jobs exist, audit them separately before applying the same switch there.

## Smoke Runbook

```bash
gcloud run jobs execute publish-notice \
  --project=baseballsite \
  --region=asia-northeast1

gcloud run jobs executions list \
  --job=publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --limit=1

gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=publish-notice AND severity>="ERROR"' \
  --project=baseballsite \
  --limit=10
```

Receiver-side checks:

- `From: y.sebata@shiny-lab.org`
- `To: fwns6760@gmail.com`
- `Reply-To: fwns6760@gmail.com`
- subject still includes `YOSHILOVER`
- mobile/desktop notification fires as a non-self-send mail
- not silently classified as spam/promotions

## Rollback Runbook

If the Workspace mail path fails, return the job to the previous shared bridge shape.

```bash
gcloud run jobs update publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=MAIL_BRIDGE_TO,MAIL_BRIDGE_SMTP_USERNAME,MAIL_BRIDGE_FROM,MAIL_BRIDGE_REPLY_TO,MAIL_BRIDGE_GMAIL_APP_PASSWORD_SECRET_NAME,MAIL_BRIDGE_SMTP_HOST,MAIL_BRIDGE_SMTP_PORT \
  --remove-secrets=MAIL_BRIDGE_TO,MAIL_BRIDGE_SMTP_USERNAME,MAIL_BRIDGE_FROM \
  --update-secrets=MAIL_BRIDGE_TO=mail-bridge-to:latest,MAIL_BRIDGE_SMTP_USERNAME=mail-bridge-smtp-username:latest,MAIL_BRIDGE_FROM=mail-bridge-from:latest,MAIL_BRIDGE_GMAIL_APP_PASSWORD=mail-bridge-gmail-app-password:latest
```

Keep `yoshilover-shiny-lab-gmail-app-password` in Secret Manager after rollback; there is no need to destroy it immediately.

## Tests added in this follow-up

- direct app-password env still wins over secret-name env
- secret-name env path works when direct app-password env is absent
- `publish-notice` subject branding still ends with `| YOSHILOVER` even when sender/login/reply-to envs are switched to `shiny-lab.org`

## Non-goals

This follow-up does not:

- apply any live Cloud Run mutation
- register secret values
- change Workspace settings
- touch DNS
- change WP / publish / mail classification / Gemini / X / audit logic
- edit the existing `240` audit doc

## Next

- `240-followup-apply`: user / authenticated executor runs the apply runbook above
- `240-followup-2`: if other Cloud Run jobs use the bridge in production, audit and switch them separately
