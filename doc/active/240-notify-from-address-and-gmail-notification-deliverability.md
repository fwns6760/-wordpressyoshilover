# 240 notify-from-address and Gmail notification deliverability

- number: 240
- type: audit + minimal impl + runbook
- status: REVIEW_NEEDED
- priority: P0.5
- parent: -
- related: 219, 222, 223, 225, 231
- owner: Codex A
- lane: A
- created: 2026-04-28

## Background

publish-notice 系の Gmail 通知は現状 `From: fwns6760@gmail.com` / `To: fwns6760@gmail.com` の self-send になっている可能性が高く、Gmail のスマホ/PC 通知が飛ばない主因として妥当。

別アドレスから `fwns6760@gmail.com` 宛に送ると通知されるため、今回の主眼は「見た目の From を雑に変える」ことではなく、**Gmail SMTP の認証 account / send-as 制約を満たした別 sender に切り替える手順を確立すること**。

This ticket intentionally does not update `doc/README.md` or `doc/active/assignments.md`, per the ticket guardrail and to avoid dirty-tree collision.

## Step 1 Audit Result

### current sender / reply-to resolution

Observed in `src/mail_delivery_bridge.py`:

- SMTP login user: `MAIL_BRIDGE_SMTP_USERNAME` -> fallback `FACT_CHECK_EMAIL_FROM`
- sender precedence after ticket 240 minimal impl:
  - explicit `MailRequest.sender`
  - `NOTIFY_FROM`
  - `MAIL_BRIDGE_FROM`
  - `FACT_CHECK_EMAIL_FROM`
  - SMTP username
- reply-to precedence after ticket 240 minimal impl:
  - explicit `MailRequest.reply_to`
  - `NOTIFY_REPLY_TO`
  - `MAIL_BRIDGE_REPLY_TO`
  - otherwise omitted

Observed in `src/publish_notice_email_sender.py`:

- caller `_BridgeMailRequest` has `sender` / `reply_to` fields, but publish-notice send path does not populate them
- therefore publish-notice runtime defaults come from `mail_delivery_bridge` env resolution, not from per-call overrides

### Cloud Run Job env / secret refs (read-only)

Read-only command used:

```bash
gcloud run jobs describe publish-notice \
  --project baseballsite \
  --region asia-northeast1 \
  --format='value(spec.template.spec.template.spec.containers[0].env)'
```

Observed mail-related env refs:

| env key | current source |
|---|---|
| `PUBLISH_NOTICE_EMAIL_ENABLED` | secret `publish-notice-email-enabled` |
| `PUBLISH_NOTICE_EMAIL_TO` | secret `publish-notice-email-to` |
| `MAIL_BRIDGE_TO` | secret `mail-bridge-to` |
| `MAIL_BRIDGE_SMTP_USERNAME` | secret `mail-bridge-smtp-username` |
| `MAIL_BRIDGE_FROM` | secret `mail-bridge-from` |
| `MAIL_BRIDGE_GMAIL_APP_PASSWORD` | secret `mail-bridge-gmail-app-password` |

Important:

- actual password env key in code is `MAIL_BRIDGE_GMAIL_APP_PASSWORD`
- there is no runtime support for a separate `MAIL_BRIDGE_SMTP_PASSWORD` key in current code
- `Reply-To` env support did not exist before ticket 240; it now exists via `NOTIFY_REPLY_TO` / `MAIL_BRIDGE_REPLY_TO`

## Step 2 Candidate Comparison

| candidate | summary | advantages | risks / limits |
|---|---|---|---|
| A. dedicated notify Gmail | separate Gmail account such as `yoshilover-notify@...` authenticates and sends to `fwns6760@gmail.com` | fastest path, distinct sender identity, no SPF/DKIM custom-domain dependency, strongest chance to break self-send suppression | new Gmail account, 2FA, App Password, new Secret Manager entry |
| B. `noreply@yoshilover.com` / `monitor@yoshilover.com` | branded domain sender | best long-term branding, cleaner ops mailbox model | requires confirmed Workspace / SMTP relay / SPF / DKIM / DMARC; unsafe to adopt without DNS/auth verification |
| C. Gmail send-as alias | keep existing Gmail account and add alias / send-as | low code impact, can reuse current Gmail account | Gmail UI setup required, `+alias` may still behave like same-account mail, push notification outcome is uncertain until live smoke confirms |

## Codex Recommendation

**Recommend A: dedicated notify Gmail.**

Reason:

- smallest operational ambiguity
- does not depend on custom-domain mail auth
- avoids the most likely Gmail self-send trap directly
- lets `Reply-To` remain `fwns6760@gmail.com` if desired

Use B only as a later branded mail project with DNS / Workspace ownership. Use C only if the user specifically wants minimal account sprawl and accepts mandatory live smoke validation.

## Minimal Implementation Added In This Ticket

Files changed:

- `src/mail_delivery_bridge.py`
- `tests/test_mail_delivery_bridge.py`
- `tests/test_publish_notice_email_sender.py`
- `doc/active/240-notify-from-address-and-gmail-notification-deliverability.md`

Diff summary:

- added `NOTIFY_FROM` as a semantic alias above `MAIL_BRIDGE_FROM`
- added env-driven `Reply-To` fallback via `NOTIFY_REPLY_TO` / `MAIL_BRIDGE_REPLY_TO`
- preserved existing behavior when new envs are unset
- kept publish-notice subject prefix / mail classification / manual X candidate logic unchanged
- added queue-log regression check so secret-like bridge payloads are not serialized into send-result logs

## Required Environment Variables

| key | purpose | recommended use |
|---|---|---|
| `MAIL_BRIDGE_SMTP_USERNAME` | Gmail SMTP login account | set to the dedicated notify Gmail address under plan A |
| `MAIL_BRIDGE_GMAIL_APP_PASSWORD` | Gmail App Password secret-backed credential | point to the dedicated notify Gmail App Password secret |
| `NOTIFY_FROM` | preferred visible sender override | set to the same dedicated notify Gmail address under plan A |
| `MAIL_BRIDGE_FROM` | legacy visible sender fallback | can remain as-is if `NOTIFY_FROM` is set |
| `NOTIFY_REPLY_TO` | optional semantic reply-to override | optional; typically `fwns6760@gmail.com` |
| `MAIL_BRIDGE_REPLY_TO` | optional legacy reply-to env | optional; same role as above if `NOTIFY_REPLY_TO` is not used |
| `PUBLISH_NOTICE_EMAIL_TO` | actual destination mailbox | keep `fwns6760@gmail.com` |

## Required External Setup

### plan A: dedicated notify Gmail

- create a new Gmail account
- enable 2FA
- issue a Gmail App Password
- register the App Password in Secret Manager
- point `publish-notice` job SMTP username/password to the new account
- set `NOTIFY_FROM` to the same sender address
- optional: set `MAIL_BRIDGE_REPLY_TO` or `NOTIFY_REPLY_TO` to `fwns6760@gmail.com`

### plan B: branded custom domain sender

- confirm Google Workspace or another authenticated SMTP relay can legally send as `yoshilover.com`
- confirm SPF / DKIM / DMARC alignment
- only then change sender address

### plan C: Gmail send-as alias

- configure Gmail Web UI send-as / alias first
- do a live smoke send before declaring success
- avoid assuming `+alias` alone will fix push notifications

## Production Apply Runbook (Plan A)

### 1. user creates the notify Gmail account

- create a new Gmail account for notifications
- enable 2FA
- create an App Password

### 2. user registers the App Password in Secret Manager

Example shape only; do not expose the secret value in shell history or chat:

```bash
gcloud secrets create yoshilover-notify-smtp-password --data-file=/path/to/app-password.txt
```

If the secret already exists, add a new version instead of recreating it.

### 3. user registers a job-local SMTP username secret

Using a dedicated secret keeps the `publish-notice` job isolated from other mail bridge consumers:

```bash
printf '%s' 'notify-account@gmail.com' > /tmp/publish-notice-mail-bridge-smtp-username.txt
gcloud secrets create publish-notice-mail-bridge-smtp-username \
  --data-file=/tmp/publish-notice-mail-bridge-smtp-username.txt
rm -f /tmp/publish-notice-mail-bridge-smtp-username.txt
```

### 4. authenticated executor updates the job env / secret refs

```bash
gcloud run jobs update publish-notice \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars=NOTIFY_FROM=notify-account@gmail.com,MAIL_BRIDGE_REPLY_TO=fwns6760@gmail.com \
  --update-secrets=MAIL_BRIDGE_SMTP_USERNAME=publish-notice-mail-bridge-smtp-username:latest,MAIL_BRIDGE_GMAIL_APP_PASSWORD=yoshilover-notify-smtp-password:latest
```

Notes:

- `NOTIFY_FROM` is preferred because it avoids editing the legacy `MAIL_BRIDGE_FROM` secret just to change the visible sender
- `MAIL_BRIDGE_REPLY_TO` is optional but useful if replies should still route to `fwns6760@gmail.com`
- `PUBLISH_NOTICE_EMAIL_TO` and `MAIL_BRIDGE_TO` should remain `fwns6760@gmail.com`

### 5. smoke

```bash
gcloud run jobs execute publish-notice \
  --project baseballsite \
  --region asia-northeast1
```

Then verify on the receiving Gmail side:

- inbox receives the notification
- mobile push fires
- desktop/web notification fires if enabled
- mail is not grouped into muted/self-send behavior
- mail is not silently classified into Promotions/Spam

## Rollback Runbook

Return `publish-notice` to the current shared Gmail sender path:

```bash
gcloud run jobs update publish-notice \
  --project baseballsite \
  --region asia-northeast1 \
  --remove-env-vars=NOTIFY_FROM,MAIL_BRIDGE_REPLY_TO,NOTIFY_REPLY_TO \
  --update-secrets=MAIL_BRIDGE_SMTP_USERNAME=mail-bridge-smtp-username:latest,MAIL_BRIDGE_GMAIL_APP_PASSWORD=mail-bridge-gmail-app-password:latest
```

This rollback intentionally leaves the legacy `MAIL_BRIDGE_FROM` secret ref in place because the job already has it today.

## Gmail Notification Verification Checklist

- Android or iOS push appears for the test mail
- Gmail web/desktop notification appears if enabled
- sender is shown as the dedicated notify mailbox, not `fwns6760@gmail.com`
- `Reply-To` points to `fwns6760@gmail.com` when configured
- message is not categorized as Spam or Promotions
- Gmail importance marker / label rules still apply

## Non-goals

- no production deploy from this ticket
- no Cloud Run env mutation from this ticket
- no Secret Manager writes from this ticket
- no Workspace / DNS change
- no Gmail filter deletion
- no WP publish logic change
- no publish gate / Gemini / X live / scheduler change
- no secret value display

## Next

- `240-impl-1`: user/authenticated-executor applies plan A in GCP
- `240-impl-2`: if the user rejects new-account ops, run plan C alias smoke as a separate bounded ticket
