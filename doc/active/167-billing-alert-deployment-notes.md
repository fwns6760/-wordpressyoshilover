# 167 billing alert deployment notes

## scope

Ticket 167 adds Cloud Billing budget alerts for the `baseballsite` project billing path.

- create or reuse Pub/Sub topic `yoshilover-billing-alerts`
- create three monthly budgets:
  - `yoshilover-budget-warn`
  - `yoshilover-budget-investigate`
  - `yoshilover-budget-emergency`
- attach threshold rules `50% / 90% / 100%`
- rely on default billing IAM email recipients for `fwns6760@gmail.com`

Out of scope:

- changes to `src/`, `tests/`, `requirements*.txt`, `.env`, schedulers, Cloud Run jobs, WordPress, or X
- budget amount changes beyond the ticket specification
- any live publish / WP write / git push

## current rollout status

- live rollout: blocked
- reason: linked billing account currency is `JPY`, so exact `$` budgets from ticket 167 are rejected by Cloud Billing Budget API
- cleanup: a probe budget and temporary Pub/Sub topic created during validation were both deleted; no live billing budget resources remain from this ticket attempt
- next user decision:
  - switch the project to a USD billing account, then rerun `scripts/setup_billing_alerts.sh`
  - or explicitly approve JPY-equivalent budget thresholds in a follow-up ticket

## billing path

- project: `baseballsite`
- billing account ID: `0137****CA07`
- billing account currency: `JPY`
- email recipient path: default billing IAM recipient (`roles/billing.admin` on the linked billing account)
- Pub/Sub topic: `projects/baseballsite/topics/yoshilover-billing-alerts`

## setup command

```bash
cd /home/fwns6/code/wordpressyoshilover
bash scripts/setup_billing_alerts.sh
```

The script hard-stops before creating resources unless the linked billing account currency matches `EXPECTED_CURRENCY` (default: `USD`).

Optional overrides if the linked project changes later:

```bash
PROJECT_ID=baseballsite \
ALERT_EMAIL=fwns6760@gmail.com \
BILLING_ACCOUNT_ID=<masked-or-explicit> \
bash scripts/setup_billing_alerts.sh
```

`BILLING_ACCOUNT_ID` is normally auto-detected from `gcloud billing projects describe baseballsite`.

## verification

Verify the three budgets exist without printing budget amounts:

```bash
BILLING_ID=$(gcloud billing projects describe baseballsite --format='value(billingAccountName)' | sed 's|billingAccounts/||')
gcloud billing budgets list \
  --billing-account="$BILLING_ID" \
  --format='table(displayName,thresholdRules.thresholdPercent,notificationsRule.pubsubTopic,notificationsRule.disableDefaultIamRecipients)'
```

Confirm the active gcloud account is the intended email recipient and has a billing role:

```bash
gcloud auth list --format='value(account)'
gcloud billing accounts get-iam-policy "$BILLING_ID" \
  --flatten='bindings[]' \
  --filter='bindings.members:user:fwns6760@gmail.com AND (bindings.role=roles/billing.admin OR bindings.role=roles/billing.user)' \
  --format='table(bindings.role)'
```

Confirm the Pub/Sub topic exists:

```bash
gcloud pubsub topics describe yoshilover-billing-alerts --project=baseballsite
```

## operational notes

- `scripts/setup_billing_alerts.sh` is safe to re-run. Existing budgets with the target display names are detected and left untouched.
- The script enables `billingbudgets.googleapis.com` in `baseballsite` if it is not already enabled.
- The script hard-stops if the linked billing account currency is not `USD`.
- The script refuses to proceed if the active gcloud account is not `fwns6760@gmail.com` or if that account lacks a billing admin/user role on the linked billing account.
- The script does not print billing amounts or the full billing account ID to stdout.
- Budget alert emails use the default billing IAM recipient path. No Monitoring email notification channel is created by this ticket.
