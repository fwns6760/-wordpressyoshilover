# 301-OBSERVE GCP-side autonomous verify Job + alert policy design

Date: 2026-05-02 JST  
Mode: doc-only / design-only / no live mutation  
Target: `observe-verify` Cloud Run Job + Cloud Logging metrics + Cloud Monitoring alerts

## 0. Conclusion

`301-OBSERVE` should move the current session-bound observe loop into GCP-side primitives that survive Claude session end:

1. raw log signals become Cloud Logging metrics
2. a new read-only Cloud Run Job `observe-verify` computes cross-log derived state every `30m`
3. `observe_verify_summary` becomes the single machine-readable heartbeat for alerting
4. alert policies notify email/PagerDuty immediately and publish to a Pub/Sub rollback hook source

The design is intentionally split:

- raw event presence/counts: logs-based counter metrics
- rolling aggregates / env drift / derived state: `observe-verify` emits one structured summary log, then summary-based metrics alert on that output

This is the narrowest path that solves the current gap:

- Claude `/loop` is best-effort and session-bound
- `mail breach`, `silent skip`, `Team Shiny From drift`, and `default-OFF flag unexpectedly firing` all require monitoring even when no human session is open

## 1. Design goals

### 1.1 Must solve

- 24h-grade monitoring must continue after Claude session exit
- current operations-critical signals must be observable from GCP alone
- P0/P1 anomalies must notify without waiting for a human to reopen a session
- rollback trigger source must be generated from infra-side alerts, not from chat memory

### 1.2 Non-goals

- no source-code implementation in this turn
- no env flip, no Scheduler change, no Cloud Run mutation in this turn
- no replacement of existing publish / review / hold / skip logic
- no expansion into SEO / X / source-ingestion redesign

## 2. Signal inventory

The table below is the required `301-OBSERVE` signal set derived from today’s operations.

| # | signal | why it matters | primary source | monitoring mode |
|---|---|---|---|---|
| 1 | publish-notice rolling 1h `sent` | storm detection / P1 | `publish-notice` `[summary]` log | derived summary metric |
| 2 | publish-notice cumulative 24h `sent` | daily budget breach | `publish-notice` `[summary]` log | derived summary metric |
| 3 | silent skip (`PREFLIGHT_SKIP_MISSING_*`, `REVIEW_POST_DETAIL_ERROR`, `REVIEW_POST_MISSING`) | user-invisible candidate disappearance = P0 | `publish-notice` / scanner logs | raw counter |
| 4 | severity `>=ERROR` consecutive burst | runtime regression / broken deploy | Cloud Run service/job logs | raw counter + derived consecutive check |
| 5 | Team Shiny `MAIL_BRIDGE_FROM` drift | sender identity regression = P0 | Cloud Run Job spec / optional audit log | derived summary metric |
| 6 | `guarded_publish_idempotent_history_skip` while 300 default should be OFF | unexpected feature activation | `guarded-publish` stderr JSON | raw counter |
| 7 | `permanent_dedup_ttl_prune` | change #5 exercised / count anomaly | `publish-notice` scanner log | raw counter + extracted prune count |
| 8 | `ingest_visibility_fix_v1_emit` | 288 trigger exercised | `draft-body-editor` / repair lane log | raw counter |
| 9 | `cache_hit_split_metric` | change #1 metric path alive | fetcher / dedupe ledger-backed path | raw counter with labels |
| 10 | cap=10 reserve trigger | change #6 exercised / reserve congestion visible | `publish-notice` scanner | derived signal, gap today |
| 11 | 293 preflight skip event | 293 path exercised | fetcher / scanner logs | raw counter |
| 12 | `【要review｜preflight_skip】` mail path | 293 user-visible route alive | `publish-notice` send logs | raw counter |
| 13 | `drafts_created` | 293 progression / activity baseline | `rss_fetcher_run_summary` | derived summary metric |
| 14 | `x_ai_generation_count` | 293 progression / Gemini gate context | `rss_fetcher_run_summary` | derived summary metric |

### 2.1 Observability gaps to close explicitly

Two required signals are not first-class explicit runtime events today:

| signal | current gap | design answer |
|---|---|---|
| Team Shiny `MAIL_BRIDGE_FROM` drift | runtime logs don’t guarantee a dedicated change event | `observe-verify` queries live Cloud Run Job spec and emits `team_shiny_from_ok` + `team_shiny_from_actual` |
| cap=10 reserve trigger | current code has no dedicated `class_reserve_applied` event | `observe-verify` infers activation from class-reserve env + scan outcomes on first implementation; preferred follow-up is an explicit runtime event later |

`301-OBSERVE` should document these as intentional derived checks, not hide them as if raw logs already existed.

## 3. GCP component architecture

### 3.1 Components

1. **Cloud Logging-based metrics**
   - raw event counters
   - numeric extraction from `observe_verify_summary`
2. **Cloud Monitoring alert policies**
   - threshold/absence alerts on those metrics
3. **Cloud Run Job `observe-verify`**
   - read-only `gcloud logging read` + `gcloud run jobs describe`
   - emits one structured summary event every run
4. **Cloud Scheduler heartbeat**
   - `*/30 * * * *`
   - invokes `observe-verify`
5. **Notification channels**
   - email
   - PagerDuty
   - Pub/Sub rollback-hook source

### 3.2 Runtime flow

1. `publish-notice`, `yoshilover-fetcher`, `guarded-publish`, and `draft-body-editor` continue emitting their normal logs.
2. logs-based counter metrics increment as raw events arrive.
3. every 30 minutes `observe-verify` reads the last 60 minutes / 24 hours of relevant logs and current `publish-notice` job env.
4. `observe-verify` emits a single structured log row:

```json
{
  "event": "observe_verify_summary",
  "status": "ok|warning|critical",
  "mail_sent_1h": 12,
  "mail_sent_24h": 71,
  "silent_skip_count_1h": 0,
  "error_count_10m": 0,
  "guarded_publish_idempotent_history_skip_count_1h": 0,
  "permanent_dedup_ttl_prune_count_24h": 1,
  "permanent_dedup_ttl_prune_rows_24h": 4,
  "ingest_visibility_fix_v1_emit_count_24h": 2,
  "cache_hit_split_metric_count_24h": 18,
  "class_reserve_trigger_count_24h": 3,
  "preflight_skip_event_count_24h": 1,
  "preflight_skip_mail_count_24h": 1,
  "drafts_created_1h": 1,
  "x_ai_generation_count_1h": 1,
  "team_shiny_from_expected": "y.sebata@shiny-lab.org",
  "team_shiny_from_actual": "y.sebata@shiny-lab.org",
  "team_shiny_from_ok": true,
  "anomalies": [],
  "rollback_source_ready": true
}
```

5. summary metrics and alert policies evaluate that row.
6. alerts notify humans and optionally publish to Pub/Sub for rollback orchestration.

## 4. Metric design

### 4.1 Design rule

Use the following split consistently:

- **raw counter metric**
  - count exact event presence from existing logs
- **derived summary metric**
  - `observe-verify` computes a rolling or stateful value, then logs it once as `observe_verify_summary`
- **distribution metric**
  - numeric value extractor from summary log for threshold alerting
  - this functions as the practical gauge-like snapshot layer for values such as `mail_sent_1h` and `mail_sent_24h`

This avoids pretending that Cloud Logging counter metrics can natively compute all rolling aggregates or env drift by themselves.

### 4.2 Raw logs-based metrics

These are created directly from current runtime logs.

| metric name | type | filter skeleton | labels / extracted fields | purpose |
|---|---|---|---|---|
| `observe_silent_skip_count` | counter | `resource.type=("cloud_run_job" OR "cloud_run_revision") AND (textPayload:"PREFLIGHT_SKIP_MISSING_" OR textPayload:"REVIEW_POST_DETAIL_ERROR" OR textPayload:"REVIEW_POST_MISSING" OR jsonPayload.reason=~"PREFLIGHT_SKIP_MISSING_.*|REVIEW_POST_DETAIL_ERROR|REVIEW_POST_MISSING")` | optional `reason` from `jsonPayload.reason` or regex on `textPayload` | P0 silent skip detection |
| `observe_error_count` | counter | `resource.type=("cloud_run_job" OR "cloud_run_revision") AND severity>=ERROR` | `resource_type`, `service_or_job` | consecutive ERROR baseline |
| `observe_guarded_publish_idempotent_history_skip_count` | counter | `resource.type="cloud_run_job" AND resource.labels.job_name="guarded-publish" AND (jsonPayload.event="guarded_publish_idempotent_history_skip" OR textPayload:"guarded_publish_idempotent_history_skip")` | `reason`, `judgment`, `hold_reason` | 300 default-OFF anomaly |
| `observe_permanent_dedup_ttl_prune_count` | counter | `resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND (jsonPayload.event="permanent_dedup_ttl_prune" OR textPayload:"permanent_dedup_ttl_prune")` | none | change #5 exercised |
| `observe_permanent_dedup_ttl_prune_rows` | distribution | same as above | `valueExtractor`: prune `count` from `jsonPayload.count` or regex `count=(\\d+)` fallback | prune volume anomaly |
| `observe_ingest_visibility_fix_v1_emit_count` | counter | `resource.type=("cloud_run_job" OR "cloud_run_revision") AND (jsonPayload.event="ingest_visibility_fix_v1_emit" OR textPayload:"ingest_visibility_fix_v1_emit")` | `reason`, `source_path`, `source_post_id` | 288 trigger evidence |
| `observe_cache_hit_split_metric_count` | counter | `resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND (jsonPayload.event="cache_hit_split_metric" OR textPayload:"cache_hit_split_metric")` | `hit_kind`, `cache_hit_reason`, `layer` | change #1 trigger evidence |
| `observe_preflight_skip_event_count` | counter | `resource.type=("cloud_run_revision" OR "cloud_run_job") AND (textPayload:"preflight_skip" OR textPayload:"PREFLIGHT_SKIP" OR jsonPayload.record_type="preflight_skip")` | `record_type`, `skip_layer` | 293 path exercised |
| `observe_preflight_skip_mail_count` | counter | `resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND textPayload:"要review｜preflight_skip"` | none | 293 visible mail alive |
| `observe_publish_notice_summary_count` | counter | `resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND textPayload:"[summary]"` | none | denominator / heartbeat for mail summary path |

### 4.3 Derived summary metrics from `observe_verify_summary`

These are emitted by the new verify job and then turned into logs-based distribution or boolean-like metrics.

| metric name | type | summary filter skeleton | value / label extraction | purpose |
|---|---|---|---|---|
| `observe_mail_sent_1h` | distribution | `resource.type="cloud_run_job" AND resource.labels.job_name="observe-verify" AND (jsonPayload.event="observe_verify_summary" OR textPayload:"observe_verify_summary")` | `valueExtractor`: `mail_sent_1h` | rolling 1h storm threshold |
| `observe_mail_sent_24h` | distribution | same | `valueExtractor`: `mail_sent_24h` | 24h mail budget |
| `observe_silent_skip_count_1h` | distribution | same | `valueExtractor`: `silent_skip_count_1h` | summary-based P0 threshold |
| `observe_error_count_10m` | distribution | same | `valueExtractor`: `error_count_10m` | burst alerting |
| `observe_team_shiny_from_ok` | counter | same + `jsonPayload.team_shiny_from_ok=false` | none | env drift alert source |
| `observe_class_reserve_trigger_count_24h` | distribution | same | `valueExtractor`: `class_reserve_trigger_count_24h` | change #6 exercise evidence |
| `observe_drafts_created_1h` | distribution | same | `valueExtractor`: `drafts_created_1h` | 293 progression |
| `observe_x_ai_generation_count_1h` | distribution | same | `valueExtractor`: `x_ai_generation_count_1h` | 293 progression |
| `observe_verify_status_critical` | counter | same + `jsonPayload.status="critical"` | none | roll-up incident signal |
| `observe_verify_heartbeat` | counter | same | label `status` | absence alert / job alive |

### 4.4 Metric count for implementation sizing

Recommended bundle size:

- raw metrics: `10`
- summary metrics: `10`
- practical minimum to implement first: `12`

Suggested phase split:

1. Phase A required-first: `12`
2. Phase B optional enrichment: remaining `8`

This keeps the initial live change smaller while still covering today’s real incidents.

## 5. Filter syntax reference

### 5.1 Reusable filter pattern for JSON-or-text logs

Several repo paths emit JSON as `textPayload`, while some environments may parse them into `jsonPayload`. Filters should therefore follow the dual-path pattern already used in repo tooling:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="yoshilover-fetcher"
timestamp>="2026-05-02T00:00:00Z"
(
  jsonPayload.event="rss_fetcher_run_summary"
  OR textPayload:"rss_fetcher_run_summary"
)
```

### 5.2 Sample `gcloud logging metrics create` skeletons

Counter:

```bash
gcloud logging metrics create observe_silent_skip_count \
  --project=baseballsite \
  --description="Silent skip detection for PREFLIGHT/REVIEW payload-drop paths" \
  --log-filter='resource.type=("cloud_run_job" OR "cloud_run_revision")
AND (textPayload:"PREFLIGHT_SKIP_MISSING_" OR textPayload:"REVIEW_POST_DETAIL_ERROR" OR textPayload:"REVIEW_POST_MISSING"
     OR jsonPayload.reason=~"PREFLIGHT_SKIP_MISSING_.*|REVIEW_POST_DETAIL_ERROR|REVIEW_POST_MISSING")'
```

Distribution from summary:

```bash
gcloud logging metrics create observe_mail_sent_1h \
  --project=baseballsite \
  --description="observe-verify rolling 1h sent mail count" \
  --log-filter='resource.type="cloud_run_job"
AND resource.labels.job_name="observe-verify"
AND (jsonPayload.event="observe_verify_summary" OR textPayload:"observe_verify_summary")' \
  --value-extractor='EXTRACT(jsonPayload.mail_sent_1h)'
```

Fallback when the row is plain `textPayload` JSON should be documented in the implementation pack with a regex extractor if needed.

## 6. Alert policy design

### 6.1 Required policies

| alert policy | source metric | condition | severity | notification | auto action source |
|---|---|---|---|---|---|
| `observe-mail-storm-1h` | `observe_mail_sent_1h` | `> 30` | P1 | email + Pub/Sub | rollback hook source `observe-alerts` |
| `observe-mail-budget-24h` | `observe_mail_sent_24h` | `> 100` | warning | email | none |
| `observe-silent-skip` | `observe_silent_skip_count_1h` or raw counter over `5m` | `> 0` | P0 | PagerDuty + email + Pub/Sub | rollback hook source |
| `observe-error-burst` | `observe_error_count_10m` or raw ERROR counter | `>= 3` in `10m` | P1 | email + Pub/Sub | rollback hook source |
| `observe-team-shiny-from-drift` | `observe_team_shiny_from_ok` | any `false` / count `> 0` | P0 | PagerDuty + email + Pub/Sub | rollback hook source |
| `observe-verify-heartbeat-missing` | `observe_verify_heartbeat` | metric absence `> 60m` | P1 | email | none |

### 6.2 Optional follow-up policies

Useful, but not required in the first implementation slice:

- `observe-guarded-publish-idempotent-history-skip`
  - P0 when count `>0` while 300 default should be OFF
- `observe-preflight-skip-mail-missing`
  - when fetcher preflight event exists but visible mail count remains `0`
- `observe-class-reserve-trigger-anomaly`
  - if trigger count spikes beyond expected band after change #6 enablement

### 6.3 Alert policy notes

- `mail_sent_24h > 100` is warning, not automatic rollback by itself
  - today’s evidence already showed `101/100` can be budget-breach without `30/h` storm
- `silent skip > 0` stays P0 because it violates the current terminal-visibility contract
- Team Shiny drift is P0 because sender identity regression is operationally user-facing and easy to miss manually

## 7. `observe-verify` Cloud Run Job skeleton

### 7.1 Responsibility

`observe-verify` is read-only and should do only these actions:

1. query recent logs
2. query `publish-notice` job env/spec
3. compute rolling aggregates and boolean drift checks
4. emit one `observe_verify_summary` structured log row
5. exit non-zero only if the verify job itself is broken, not merely because it found anomalies

### 7.2 Input windows

Recommended windows:

- heartbeat cadence: `30m`
- mail storm: last `60m`
- daily budget: last `24h`
- error burst: last `10m`
- silent skip: last `60m`
- progression counters: last `60m`
- feature-exercise counters: last `24h`

### 7.3 Read-only command families

Expected implementation style:

```bash
gcloud logging read '<FILTER>' --limit=500 --order=desc --format=json
gcloud run jobs describe publish-notice --region=asia-northeast1 --format=json
```

No mutations:

- no `gcloud run jobs update`
- no `gcloud scheduler jobs update`
- no `gcloud builds submit`
- no Secret Manager mutation

### 7.4 Summary event contract

The summary event should always contain:

- `event`
- `status`
- `window_end`
- every monitored numeric field, even if zero
- `team_shiny_from_expected`
- `team_shiny_from_actual`
- `team_shiny_from_ok`
- `anomalies[]`
- `rollback_source_ready`

This avoids the current ambiguity of having to reconstruct state from many ad hoc human commands.

### 7.5 Hooking anomalies to alerts

The verify job should not call rollback directly.

Instead:

1. emit `observe_verify_summary`
2. alert policy fires
3. notification channels notify humans
4. Pub/Sub receives the alert as the machine trigger source
5. a later authenticated rollback executor may subscribe and decide whether to apply rollback

This keeps `301-OBSERVE` consistent with the authenticated-executor boundary.

## 8. Deploy plan

### 8.1 Order

Recommended deploy sequence for the future implementation ticket:

1. create notification channels first
2. deploy `observe-verify` image/job in read-only mode
3. create raw logs-based metrics
4. create summary metrics
5. create alert policies in muted or email-only mode
6. create Scheduler `*/30`
7. verify summary heartbeat for at least `2` runs
8. unmute PagerDuty / Pub/Sub actions

### 8.2 Why this order

- channels first: policy creation otherwise blocks or gets wired to the wrong recipient
- job before summary metrics: summary metrics would be empty until the first heartbeat exists
- metrics before alerting: avoids false incidents from missing metric descriptors
- Scheduler last: prevents a half-wired system from paging immediately on first run

### 8.3 Service-by-service scope

| component | action | rollback target |
|---|---|---|
| `observe-verify` Cloud Run Job | new create | delete/disable job, revert image |
| `observe-verify` Scheduler | new create | pause/delete scheduler |
| raw logging metrics | new create | delete metrics |
| summary logging metrics | new create | delete metrics |
| alert policies | new create | disable/delete policies |
| notification channels | new create or wire existing | disable channel / detach from policies |

No existing production service image must be changed for this ticket:

- `yoshilover-fetcher`: no change
- `publish-notice`: no change
- `guarded-publish`: no change
- `draft-body-editor`: no change

### 8.4 Notification channel preconditions

Before live apply, Claude/user must confirm:

1. email notification channel exists and is verified
2. PagerDuty integration key exists
3. Pub/Sub topic for rollback trigger exists
4. on-call destination for P0 is agreed

Without these, the repo work can still land, but the ticket should stop at `READY_FOR_AUTH_EXECUTOR`.

### 8.5 Cloud Build need

`YES`, one new Cloud Build YAML is warranted.

Reason:

- new Cloud Run Job requires repeatable build/deploy
- monitoring resource creation is likely a scripted executor step
- the job is infra-facing enough that ad hoc shell history is not sufficient

Recommended artifact count:

- new `cloudbuild.observe-verify.yaml`: `1`

### 8.6 Rollback plan

Rollback order if the monitoring deployment itself misbehaves:

1. pause Scheduler
2. disable alert policies
3. delete or roll back `observe-verify` job image
4. keep raw logs and existing production workloads untouched

Because this ticket introduces only new monitoring resources, rollback is additive and low-risk.

## 9. Migration plan

### 9.1 Transition model

Current model:

- Claude `/loop`
- ScheduleWakeup best-effort
- manual `gcloud logging read`

Target model:

- GCP metrics + alert policies
- `observe-verify` summary heartbeat
- Claude only reviews incidents and makes higher-level decisions

### 9.2 Recommended overlap window

Run both paths for:

- minimum `72h`
- and at least `1` postgame cycle
- and at least `1` pregame or quiet-window cycle

This overlap is long enough to prove:

- heartbeat continuity
- no missing alert on quiet periods
- no false-positive flood during a real cycle

### 9.3 Overlap procedure

1. keep Claude `/loop` read-only checks alive
2. enable `observe-verify` email alerts first
3. compare every anomaly detected by Claude with GCP alert output
4. compare every GCP alert with Claude’s human read
5. once congruence is good, keep only GCP as the 24h watcher

### 9.4 Decommission criteria for Claude `/loop`

Claude `/loop` polling can be retired when all are true:

1. `observe_verify_summary` heartbeat arrived for `>= 72h`
2. no heartbeat gap exceeded `60m`
3. at least one synthetic or real alert fired and reached the correct channel
4. Team Shiny drift check was proven by at least one manual env-read compare
5. mail 1h / 24h counters matched manual calculation within tolerance
6. no silent skip event was missed by GCP-side monitoring
7. Pub/Sub rollback source path is validated, even if rollback remains human-approved

Until then, Claude remains a shadow observer, not the primary always-on monitor.

## 10. `CLAUDE_AUTO_GO` 14-condition fit check

This section evaluates whether the future implementation/deploy can qualify for safe autonomous apply.

Interpretation:

- **Pack A** = repo implementation + monitoring resources create
- there is no Pack B equivalent here because this ticket adds new infra resources rather than flipping a behavior flag inside an existing service

| # | condition | pre-judgment | note |
|---|---|---|---|
| 1 | flag OFF deploy | YES | no existing feature flags need to flip |
| 2 | live-inert deploy | PARTIAL | resources are additive, but alerts can still page if thresholds are wrong |
| 3 | behavior-preserving image replacement | YES | existing app behavior unchanged; only new monitoring job added |
| 4 | tests are green | PENDING | impl ticket must add unit tests for log parsing / summary building |
| 5 | rollback target confirmed | YES | additive resource rollback is straightforward but exact names must be fixed in impl pack |
| 6 | Gemini call increase none | YES | verify job reads logs only |
| 7 | mail volume increase none | YES | monitoring does not send publish mail; only incident notifications |
| 8 | source addition none | YES | no RSS/source touch |
| 9 | Scheduler change none | NO | new Scheduler is required |
| 10 | SEO/noindex/canonical/301 change none | YES | none |
| 11 | publish/review/hold/skip criteria unchanged | YES | observe-only |
| 12 | cleanup mutation none | YES | no WP mutation |
| 13 | candidate disappearance risk none/proven unchanged | YES | observe-only |
| 14 | stop condition written | YES | this design defines them |

`+1` post-deploy discipline:

- post-deploy verify plan written -> `YES`
  - heartbeat, alert dry-run, and absence-check plan are explicit in this doc

### 10.1 Judgment

`301-OBSERVE` is **not** a clean `CLAUDE_AUTO_GO` ticket today because condition `9` fails:

- a new Scheduler is an intentional live infra mutation

So the correct future status is:

- repo implementation can be `CLAUDE_AUTO_GO`-like up to commit/test/runbook
- live apply should still be `READY_FOR_AUTH_EXECUTOR`

## 11. Implementation sizing

### 11.1 Estimated scope

| item | estimate |
|---|---|
| new Cloud Run Job | `1` (`observe-verify`) |
| new Cloud Build YAML | `1` |
| logs-based metrics | `~10` raw + `~2-4` summary-first minimum, or `~20` full design |
| alert policies | `6` required |
| notification channel work | `1` user-owned setup line + executor wiring |
| new Scheduler | `1` |

### 11.2 Recommended implementation breakdown

Estimated Codex execution runs: `4`

1. **Run 1**
   - scaffold `observe-verify` job code
   - implement log readers / summary builder
   - add focused tests
2. **Run 2**
   - add Cloud Build YAML
   - add deploy/runbook doc for monitoring resources
3. **Run 3**
   - prepare metrics/policies creation scripts or executor-ready command pack
   - finalize exact filter strings and resource names
4. **Run 4**
   - post-deploy verify pack
   - dry synthetic alert test plan

If the team wants to keep the first live step smaller, split Run 3 into:

- `3A`: raw metrics + summary metrics
- `3B`: alert policies + Scheduler

That would make the estimate `5` runs instead of `4`.

## 12. Recommended next step

1. accept this design doc
2. fire a narrow implementation ticket for `observe-verify`
3. keep all live GCP mutations in authenticated-executor scope
4. treat Team Shiny drift and class-reserve trigger as explicit derived checks in the first version

## 13. Open questions for implementation turn

These are not blockers for accepting this design, but the implementation pack must lock them:

1. whether the summary metrics are kept at the minimum `12`-metric slice or the full `20`-metric design
2. whether cap=10 reserve trigger remains derived-only or gets an explicit runtime event in a follow-up
3. whether Pub/Sub rollback hook is wired immediately or left as a future consumer with email/PagerDuty first
4. exact notification channel ids in project `baseballsite`
