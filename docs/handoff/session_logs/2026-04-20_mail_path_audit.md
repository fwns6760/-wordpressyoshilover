# mail path read-only 調査便 (2026-04-20 22:25 JST)

read-only 観測。gcloud / Cloud Logging / Cloud Scheduler で fact_check / audit_notify 経路を確認。

## 実行コマンド

- `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND jsonPayload.event=~"fact_check_email_"' --freshness=24h`
- `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND jsonPayload.event=~"audit_notify"' --freshness=72h`
- `gcloud scheduler jobs list --location=asia-northeast1`
- `gcloud scheduler jobs describe audit-notify-6x`

## fact_check 経路

- 直近 24h、毎時 `fact_check_email_skipped` が安定発火
- 最新: `2026-04-20T13:00:50Z`(= JST 22:00:50)
- reason は全件 `no_change_no_red`、red=0 / yellow=0 / green=9(正常 skip)
- `fact_check_email_failed` / `fact_check_email_demo` はゼロ件
- scheduler `fact-check-morning-report`(`0 * * * *`)= ENABLED、last attempt 2026-04-20T13:00:50Z
- 判定: **正常**

## audit_notify 経路

- `audit_notify_completed` の最終発火: `2026-04-20T06:00:12Z`(= JST 15:00:12)
- scheduler `audit-notify-6x`(`0 10-23 * * *`)= **PAUSED**
- pause 時刻: `userUpdateTime=2026-04-20T07:46:17Z`(= JST 16:46:17)
- 15:00 JST の完了から 1h46m 後に PAUSED 化
- 誰がなぜ pause したかは log からは不明(audit log 未確認)
- 判定: **停止中**(stopped, not broken)

## Scheduler 全体スナップショット(2026-04-20 22:25 JST)

- ENABLED: `fact-check-morning-report` / `giants-*`(postgame/lineup/weekend/weekday 系)/ `prosports-*` / `seo-fetch-daily` / `fetch-gsc-daily` / `ga4-traffic-analyzer-daily`
- PAUSED: `audit-notify-6x` / `yoshilover-fetcher-job` / `family-fetch-gsc-daily`

## 判定

- **mail path は現時点で正常**(fact_check 経路)
- **audit_notify 経路は意図不明の PAUSED 状態**
- 既知正常状態(T-017 RESOLVED、hourly warm)は現在も維持されている
- latest.log が止まっていた件は実害なし(正本は Cloud Logging、local symlink は Codex transcript の遺物)

## 次の1手

`audit-notify-6x` PAUSED の経緯確認を Claude 側で先に行う(read-only audit log 確認)。
原因が判明するまでは mail path 全体の monitoring mode 移行を保留。
