# 208 GCP lane result log persistence audit

- number: 208
- status: CLOSED
- priority: P1.5
- lane: Claude/Codex A
- created: 2026-04-27
- type: read-only audit

## close note(2026-04-28)

- read-only audit is complete and follow-up persistence work is tracked separately.
- Codex-M is not an active dispatch lane in current operations.

## background

206 audit で publish-notice は `cursor.txt` / `history.json` の GCS 永続化はある一方、`send result` / `suppress reason` / `SMTP error` の durable evidence が弱く、`scan emit > 0` なのに `sent = 0` の原因切り分けが難しいことが判明した。

本票は同じ穴が他 GCP lane にもあるかを横断で見る read-only audit。修正はしない。README / assignments / 他 active doc は触らない。

## shared audit axes

1. Cloud Scheduler / Cloud Run の起動ログはあるか
2. 処理件数が残るか
3. 成功件数 / 失敗件数が残るか
4. 失敗理由が残るか
5. `post_id` / `run_id` / `execution_id` が紐づくか
6. GCS / Firestore / BigQuery / Cloud Logging のどこに残るか
7. コンテナ内 `/tmp` や repo local log だけで消えるログがないか
8. 次の read-only audit で原因切り分けできるか

## evidence basis

- GCS state bucket observed:
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_yellow_log.jsonl`
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_cleanup_log.jsonl`
  - `gs://baseballsite-yoshilover-state/guarded_publish/cleanup_backup/...json`
  - `gs://baseballsite-yoshilover-state/publish_notice/cursor.txt`
  - `gs://baseballsite-yoshilover-state/publish_notice/history.json`
  - `gs://baseballsite-yoshilover-state/draft_body_editor/` は observed object なし
- history bucket observed:
  - `gs://yoshilover-history/rss_history.json`
  - `gs://yoshilover-history/repair_artifacts/` は observed object なし
- GCP read-only observations:
  - Cloud Run Jobs: `draft-body-editor`, `guarded-publish`, `publish-notice`, `codex-shadow`
  - Cloud Scheduler: `draft-body-editor-trigger`, `guarded-publish-trigger`, `publish-notice-trigger`, `codex-shadow-trigger` は ENABLED
  - `audit-notify-6x` は PAUSED
  - `fact-check-morning-report` は ENABLED
  - `yoshilover-fetcher` service env has `GCS_BUCKET=yoshilover-history`
- live env observations:
  - `draft-body-editor`, `guarded-publish`, `publish-notice`, `codex-shadow` live job env には `LEDGER_FIRESTORE_ENABLED` / `LEDGER_GCS_ARTIFACT_ENABLED` が見当たらない
  - `codex-shadow` live job env では `CODEX_WP_WRITE_ALLOWED=true`
  - `publish-notice` live image is `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:210ce41`
- Cloud Logging observations:
  - `publish-notice` job logs include execution name and `[scan] emitted=... skipped=... cursor_before=... cursor_after=...`
  - `guarded-publish` job logs include execution name and GCS upload actions
  - `draft-body-editor` and `codex-shadow` stdout include JSON summary with `aggregate_counts`, `skip_reason_counts`, `per_post_outcomes`, and `post_id`
  - `yoshilover-fetcher` service logs include `rss_fetcher_run_summary` and `rss_fetcher_flow_summary`
  - `fact_check_notifier` service logs include `fact_check_notify_started` and `fact_check_email_skipped`

## lane matrix

| lane | current persistence | missing evidence | severity | recommended follow-up ticket |
|---|---|---|---|---|
| publish-notice | Cloud Scheduler + Cloud Run Job are active. Cloud Logging keeps `execution_name` and scan summary. GCS currently keeps only `cursor.txt` and `history.json` under `publish_notice/`. Repo HEAD already has `src/cloud_run_persistence.py` queue persistence support, but live image is still `publish-notice:210ce41`, so the observed live lane is pre-207. | Live lane still does not durably keep per-run send result, suppress reason breakdown, SMTP error payload, or `queue.jsonl` in GCS. `emit > 0 / sent = 0` remains hard to reconstruct from durable state alone. | HIGH | `207 publish-notice send-result GCS persistence rollout + verify` |
| guarded-publish | Strongest current lane. GCS keeps `guarded_publish_history.jsonl`, `guarded_publish_yellow_log.jsonl`, `guarded_publish_cleanup_log.jsonl`, plus `cleanup_backup/*.json`. Cloud Logging keeps execution names and upload trail. Repo runner can also mirror appended history into `BestEffortLedgerSink`. | Live env does not currently enable `LEDGER_FIRESTORE_ENABLED` / `LEDGER_GCS_ARTIFACT_ENABLED`, so `repair_ledger` / `repair_artifacts` are not observed. No separate per-execution summary object in GCS keyed by execution name. | LOW | なし。将来改善なら `guarded-publish ledger env enable audit` |
| draft-body-editor | Cloud Run Job + Scheduler are active. Cloud Logging stdout keeps JSON summary with `aggregate_counts`, `skip_reason_counts`, `per_post_outcomes`, `post_id`, and `execution_name`. | The lane still writes touched-state and session history to local `logs/draft_body_editor/*.jsonl`, and repair ledger starts as local JSONL. Live env has no GCS/Firestore sink enabled, and no `draft_body_editor/` bucket path is observed. Exact 24h touched history and before/after repair evidence can disappear with the container. | MED | `draft-body-editor session/ledger persistence on GCP` |
| codex-shadow / Codex-GCP repair | Cloud Run Job + Scheduler are active. Cloud Logging stdout keeps JSON summary with `aggregate_counts`, `skip_reason_counts`, `per_post_outcomes`, `post_id`, and `execution_name`. Repo has `BestEffortLedgerSink`, `FirestoreLedgerWriter`, and `ArtifactUploader`. | Live env does not enable `LEDGER_FIRESTORE_ENABLED` / `LEDGER_GCS_ARTIFACT_ENABLED`; `gs://yoshilover-history/repair_artifacts/` is empty. Because this lane has `CODEX_WP_WRITE_ALLOWED=true`, durable before/after body artifacts and ledger rows for real repairs are missing from live evidence. | HIGH | `codex-shadow ledger env enable + repair_artifacts verify` |
| yoshilover-fetcher / RSS ingestion | `yoshilover-fetcher` service env has `GCS_BUCKET=yoshilover-history`, and `rss_history.json` exists in GCS. Cloud Logging keeps `rss_fetcher_run_summary` and `rss_fetcher_flow_summary` with counts, skip reasons, and revision. | Durable state is mostly `rss_history.json`; detailed per-run result evidence lives in Cloud Logging, not in a separate GCS/Firestore run ledger. Created / skipped / failed details are observable, but not normalized into one durable run object keyed by execution id. | LOW | なし。将来改善なら `fetcher run-result ledger` |
| quality monitor / fact-check / audit mail | `fact_check_notifier` logs `fact_check_notify_started`, `fact_check_email_skipped/failed/sent` to Cloud Logging on `yoshilover-fetcher`. `audit_notify.py` logs `audit_notify_completed` with `counts`, `mail_sent`, and SMTP fields. | `quality-monitor` itself is not yet on GCP mainline; board still has `163 quality-monitor / quality-gmail GCP migration` queued, and current implementation writes local `logs/quality_monitor/*.jsonl`. `audit-notify-6x` is PAUSED, so there is no steady live evidence stream. No single durable store combines scan counts, mail result, and reasons across this lane family. | MED | `163 quality-monitor / quality-gmail GCP migration + result persistence` |
| X gate / queue dry-run | Repo has `src/x_post_queue_ledger.py` with JSONL queue/ledger schema and dry-run smoke tooling. The lane is still pre-live and not observed as a Cloud Run Job/Scheduler in this audit. | Persistence is local JSONL only (`logs/x_post_queue.jsonl`, `logs/x_post_ledger.jsonl`). `x_post_queue_ledger.FirestoreLedgerWriter` is still an in-memory stub, not a live durable backend. No GCS/Firestore evidence exists yet, but the lane is not production-live. | LOW | `X queue durable ledger before 149/174/175 live unlock` |
| SNS topic intake / source recheck | Current tooling is fixture/mock dry-run CLI. `run_sns_topic_fire_intake` and `run_sns_topic_source_recheck` emit stdout or optional file output; `sns_topic_publish_bridge` can reuse guarded-publish paths when bridging mock drafts. | No live Cloud Run Job / Scheduler / GCS / Firestore persistence was observed for SNS decisions. Route decisions, source recheck pass/fail, and bridge outcomes are mainly stdout or optional local file output. | LOW | `180 SNS topic lane separation + persistence plan before GCP activation` |

## recommended follow-up tickets

1. `207 publish-notice send-result GCS persistence rollout + verify`
2. `draft-body-editor session/ledger persistence on GCP`
3. `codex-shadow ledger env enable + repair_artifacts verify`
4. `163 quality-monitor / quality-gmail GCP migration + result persistence`
5. `X queue durable ledger before 149/174/175 live unlock`
6. `180 SNS topic lane separation + persistence plan before GCP activation`

## not goal

- 本票では修正しない
- GCP live mutation しない
- WP write / mail send / X post をしない
- README / assignments / 他 active doc を触らない
