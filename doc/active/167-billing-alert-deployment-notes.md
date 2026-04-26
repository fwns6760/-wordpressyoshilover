# 167 billing alert deployment notes

## scope

Ticket 167 adds Cloud Billing budget alerts for the `baseballsite` project billing path.

- create three monthly budgets:
  - `yoshilover-budget-warn`
  - `yoshilover-budget-investigate`
  - `yoshilover-budget-emergency`
- use JPY-equivalent monthly limits:
  - `yoshilover-budget-warn` = `¥1,500`
  - `yoshilover-budget-investigate` = `¥4,500`
  - `yoshilover-budget-emergency` = `¥7,500`
- attach threshold rules `50% / 90% / 100%`
- reuse Monitoring email notification channel `7008520332246366374`
- scope each budget to `projects/baseballsite`

Out of scope:

- changes to `src/`, `tests/`, `requirements*.txt`, `.env`, schedulers, Cloud Run jobs, WordPress, or X
- budget amount changes beyond the ticket specification
- any live publish / WP write / git push

## rollout result

- v1 rollback status: the prior USD probe was removed before this v2 rollout; no live USD budget remains
- v2 rollout status: completed on `2026-04-26`; the three JPY budgets above were created and re-verified successfully
- notification path: Cloud Billing Budget -> Monitoring email channel `7008520332246366374`

## billing path

- project: `baseballsite`
- billing account ID: `0137****CA07`
- billing account currency: `JPY`
- notification channel: `projects/baseballsite/notificationChannels/7008520332246366374`
- notification channel display name: `yoshilover cloud run job failure alerts`

## setup command

```bash
cd /home/fwns6/code/wordpressyoshilover
bash scripts/setup_billing_alerts.sh
```

The script hard-stops before creating resources unless the linked billing account currency matches `EXPECTED_CURRENCY` (default: `JPY`).

Optional overrides if the linked project changes later:

```bash
PROJECT_ID=baseballsite \
NOTIFICATION_CHANNEL_ID=7008520332246366374 \
BILLING_ACCOUNT_ID=<masked-or-explicit> \
bash scripts/setup_billing_alerts.sh
```

`BILLING_ACCOUNT_ID` is normally auto-detected from `gcloud billing projects describe baseballsite`.

## verification

Verify the three budgets exist and that each remains JPY-scoped:

```bash
BILLING_ID=$(gcloud billing projects describe baseballsite --format='value(billingAccountName)' | sed 's|billingAccounts/||')
gcloud billing budgets list \
  --billing-account="$BILLING_ID" \
  --format='table(displayName,amount.specifiedAmount.units,amount.specifiedAmount.currencyCode,thresholdRules.thresholdPercent)'
```

Confirm the budgets point at the expected Monitoring email channel:

```bash
gcloud billing budgets list \
  --billing-account="$BILLING_ID" \
  --format='table(displayName,notificationsRule.monitoringNotificationChannels,budgetFilter.projects)'
```

`budgetFilter.projects` is rendered by GCP as a canonical `projects/<project-number>` resource even when the budget is created from `projects/baseballsite`.

Confirm the email channel is present and enabled:

```bash
gcloud alpha monitoring channels describe \
  projects/baseballsite/notificationChannels/7008520332246366374 \
  --format='yaml(name,displayName,type,enabled,labels.email_address)'
```

## operational notes

- `scripts/setup_billing_alerts.sh` is safe to re-run only when the existing budget names already match the JPY ticket spec. Any same-name mismatch is treated as a collision and the script exits non-zero.
- The script hard-stops if the linked billing account currency is not `JPY`.
- The script verifies that notification channel `7008520332246366374` exists, is an enabled email channel, and is attached to each budget.
- The script compares the saved project scope against the canonical `projects/<project-number>` form returned by Cloud Billing.
- The script does not print billing amounts or the full billing account ID to stdout.
- No new Monitoring notification channel is created by this ticket; the existing channel from ticket 166 is reused.
