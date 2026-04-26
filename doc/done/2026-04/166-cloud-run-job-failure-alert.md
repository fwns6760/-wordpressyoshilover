# 166 cloud-run-job-failure-alert(GCP migration 残リスク #2)

## meta

- number: 166
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / observability / alerting
- status: **BLOCKED**(155-1b deploy 完了後 fire 可)
- priority: P1(GCP migration の品質事故自動検知 = MVP §5)
- lane: A
- created: 2026-04-26
- parent: 155 / 165 残リスク #2

## 背景

GCP 移行後、Cloud Run Job が non-zero exit / timeout / OOM で fail した際、現状は **silent fail**(誰も気づかない)。Cloud Logging に残るが見ない。

→ **失敗を即時 mail / Slack に通知**する経路を作り、品質事故自動検知(MVP §5)を満たす。

## ゴール

各 Cloud Run Job(042 / PUB-004-C / 095 / gemini_audit / quality-monitor / quality-gmail)が fail した際、**fwns6760@gmail.com に mail 通知**する。

## 仕様

### 経路

```
Cloud Run Job (fail/timeout)
    ↓ (Cloud Logging)
Log-based Metric: severity=ERROR or exit_code != 0
    ↓
Cloud Monitoring Alert Policy (threshold: 1 fail / 5min window)
    ↓
Notification Channel: Email (fwns6760@gmail.com)
```

### Alert Policy 設定(各 Job 1 つ、計 6 つ)

- Display Name: `cron-fail-<job_name>`(例 `cron-fail-draft-body-editor`)
- Condition: log-based metric の count > 0 in last 5 min
- Notification: Email channel
- Auto-close: 30 min(同事象連続 mail 防止)
- Documentation: job 名 / 想定 cron schedule / 復旧 link

### 成果物

- `terraform/cloud_run_alerts.tf`(または `gcloud_alert_policies.yaml`、user の preferred IaC で)
- `doc/active/166-deployment-notes.md`(alert 設定手順 / 確認手順)
- 既存 src / tests / .env / crontab 一切変更なし

### 動作確認

1. 1 つの Job(例 042)を `gcloud run jobs execute --command=exit 1` で意図的 fail
2. 5min 以内に Email 着信
3. Mail 本文に job 名 / 失敗時刻 / Cloud Logging link 含む
4. Auto-close 30min で再 fire 可能

## 不可触

- 既存 src / tests / requirements*.txt / .env / secrets / crontab
- baseballwordpress repo
- 既存 GCP services / schedulers
- WordPress / X / Cloud Run env(本 ticket は Alert Policy のみ)

## acceptance

1. 6 lane 分の Alert Policy が GCP に作成済み
2. fail 注入 → mail 着信(end-to-end smoke)
3. mail 本文に必須 4 項目(job 名 / 失敗時刻 / log link / 復旧手順 link)
4. 30min auto-close 確認
5. IaC ファイル(terraform / gcloud yaml)が repo に commit
6. live publish / WP write / push: 全て NO

## stop 条件

- 既存 GCP project に notification channel が無い → 別 ticket で channel 作成 → 本 ticket fire 再開
- mail spam 振り分け確認必要 → 1 件目 user 確認 op

## 残リスク

- mail delivery delay(Gmail 側)— Pub/Sub → Slack 連携で補完可能(167 で扱うか、本 ticket で並列 channel 化)

## 完了後の次便

167(GCP billing alert)起票 + fire 判断。
