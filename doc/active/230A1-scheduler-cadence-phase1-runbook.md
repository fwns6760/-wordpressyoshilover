# 230-A1 scheduler cadence governor phase 1 runbook

## meta

- number: 230-A1
- type: runbook
- status: REVIEW_NEEDED
- priority: P0.5
- parent: 230-A
- related: 230
- created: 2026-04-28
- mode: read-only audit + runbook generation only
- live_apply_owner: authenticated executor only

## background

GCP budget 1500 円到達に対し、230-A audit では Gemini 品質そのものよりも `*/5` 常時実行と quiet-hours / no-op 実行の積み上がりが先に削減候補だと確認した。本票は scheduler cadence governor phase 1 の apply 手順を固定する runbook であり、Codex は read-only audit とコマンド生成だけを行い、live apply はしない。

## scope

- apply 対象 4 jobs:
  - `publish-notice-trigger`
  - `codex-shadow-trigger`
  - `draft-body-editor-trigger`
  - `fact-check-morning-report`
- 維持対象 2 jobs:
  - `guarded-publish-trigger`
  - `giants-realtime-trigger`
- 変更対象は Scheduler の `schedule` と `timeZone` 指定のみ
- `uri` / `httpMethod` / auth / message body / retry / IAM / Secret / env / Cloud Run image / code は不変

## before snapshot

Read-only 採取日時: 2026-04-28 JST  
採取元: `gcloud scheduler jobs list` と `gcloud scheduler jobs describe`

| job | current schedule | state | timeZone | uri | method | note |
|---|---|---|---|---|---|---|
| `publish-notice-trigger` | `*/5 * * * *` | `ENABLED` | `Asia/Tokyo` | `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/publish-notice:run` | `POST` | apply 対象 |
| `codex-shadow-trigger` | `*/5 * * * *` | `ENABLED` | `Asia/Tokyo` | `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/codex-shadow:run` | `POST` | apply 対象 |
| `draft-body-editor-trigger` | `2,12,22,32,42,52 * * * *` | `ENABLED` | `Asia/Tokyo` | `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/draft-body-editor:run` | `POST` | apply 対象 |
| `fact-check-morning-report` | `0 * * * *` | `ENABLED` | `Asia/Tokyo` | `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/fact_check_notify?since=yesterday` | `GET` | apply 対象 |
| `guarded-publish-trigger` | `*/5 * * * *` | `ENABLED` | `Asia/Tokyo` | `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/guarded-publish:run` | `POST` | 維持、phase 1 では変更しない |
| `giants-realtime-trigger` | `*/5 * * * *` | `ENABLED` | `Asia/Tokyo` | `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run` | `POST` | 維持、phase 1 では変更しない |

## phase 1 cron table

| job | before | after | timeZone | rationale |
|---|---|---|---|---|
| `publish-notice-trigger` | `*/5 * * * *` | `*/15 * * * *` | `Asia/Tokyo` | 公開 4 件/h max 前提では 15 分 cadence で十分。no-op 通知実行を 2/3 削減する。 |
| `codex-shadow-trigger` | `*/5 * * * *` | `*/15 * * * *` | `Asia/Tokyo` | shadow lane で即時性不要。WP write 禁止 policy を維持したまま cadence だけ落とす。 |
| `draft-body-editor-trigger` | `2,12,22,32,42,52 * * * *` | `2,12,22,32,42,52 10-23 * * *` | `Asia/Tokyo` | active window を JST 10:00-23:59 に限定。quiet-hours 10h 分の no-op 実行を止める。 |
| `fact-check-morning-report` | `0 * * * *` | `0 8,12,16 * * *` 推奨 | `Asia/Tokyo` | hourly を 3/day に縮退。`since=yesterday` 固定 endpoint のため鮮度低下 risk は低め。 |
| `guarded-publish-trigger` | `*/5 * * * *` | `*/5 * * * *` 維持 | `Asia/Tokyo` | publish 本線。phase 1 では絶対に触らない。 |
| `giants-realtime-trigger` | `*/5 * * * *` | `*/5 * * * *` 維持 | `Asia/Tokyo` | realtime 本線。phase 1 では絶対に触らない。 |

`fact-check-morning-report` の 3/day 候補:

- 推奨 A: `0 8,12,16 * * *`
- 候補 B: `0 9,13,17 * * *`
- 候補 C: `0 7,12,18 * * *`

## apply runbook

前提:

- 実行者は authenticated executor の shell を使う
- Codex sandbox からは実行しない
- `--schedule` と `--time-zone` 以外は触らない
- `--uri` / `--http-method` / auth 系 flag / message body 系 flag を追加しない
- update 前後で JSON snapshot を採取し、`diff` で schedule 以外の drift が無いことを確認する

### 1. publish-notice-trigger

```bash
gcloud scheduler jobs describe publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format=json > /tmp/publish-notice-trigger.before.json

gcloud scheduler jobs update http publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="*/15 * * * *" \
  --time-zone=Asia/Tokyo

gcloud scheduler jobs describe publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format=json > /tmp/publish-notice-trigger.after.json

diff -u /tmp/publish-notice-trigger.before.json /tmp/publish-notice-trigger.after.json
```

### 2. codex-shadow-trigger

```bash
gcloud scheduler jobs describe codex-shadow-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format=json > /tmp/codex-shadow-trigger.before.json

gcloud scheduler jobs update http codex-shadow-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="*/15 * * * *" \
  --time-zone=Asia/Tokyo

gcloud scheduler jobs describe codex-shadow-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format=json > /tmp/codex-shadow-trigger.after.json

diff -u /tmp/codex-shadow-trigger.before.json /tmp/codex-shadow-trigger.after.json
```

### 3. draft-body-editor-trigger

```bash
gcloud scheduler jobs describe draft-body-editor-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format=json > /tmp/draft-body-editor-trigger.before.json

gcloud scheduler jobs update http draft-body-editor-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="2,12,22,32,42,52 10-23 * * *" \
  --time-zone=Asia/Tokyo

gcloud scheduler jobs describe draft-body-editor-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format=json > /tmp/draft-body-editor-trigger.after.json

diff -u /tmp/draft-body-editor-trigger.before.json /tmp/draft-body-editor-trigger.after.json
```

### 4. fact-check-morning-report

推奨 A をそのまま適用する場合:

```bash
gcloud scheduler jobs describe fact-check-morning-report \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format=json > /tmp/fact-check-morning-report.before.json

gcloud scheduler jobs update http fact-check-morning-report \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="0 8,12,16 * * *" \
  --time-zone=Asia/Tokyo

gcloud scheduler jobs describe fact-check-morning-report \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format=json > /tmp/fact-check-morning-report.after.json

diff -u /tmp/fact-check-morning-report.before.json /tmp/fact-check-morning-report.after.json
```

候補 B / C を使う場合は `--schedule` だけ差し替える:

```bash
# 候補 B
--schedule="0 9,13,17 * * *"

# 候補 C
--schedule="0 7,12,18 * * *"
```

## rollback runbook

phase 1 apply 後に問題が出た場合は、before snapshot の実測値に戻す。

```bash
gcloud scheduler jobs update http publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="*/5 * * * *" \
  --time-zone=Asia/Tokyo

gcloud scheduler jobs update http codex-shadow-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="*/5 * * * *" \
  --time-zone=Asia/Tokyo

gcloud scheduler jobs update http draft-body-editor-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="2,12,22,32,42,52 * * * *" \
  --time-zone=Asia/Tokyo

gcloud scheduler jobs update http fact-check-morning-report \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="0 * * * *" \
  --time-zone=Asia/Tokyo
```

## verification

apply 直後:

```bash
gcloud scheduler jobs list \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format='table(name,schedule,state,lastAttemptTime)'

gcloud scheduler jobs describe publish-notice-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format='value(name,schedule,state,timeZone,httpTarget.uri,httpTarget.httpMethod)'

gcloud scheduler jobs describe codex-shadow-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format='value(name,schedule,state,timeZone,httpTarget.uri,httpTarget.httpMethod)'

gcloud scheduler jobs describe draft-body-editor-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format='value(name,schedule,state,timeZone,httpTarget.uri,httpTarget.httpMethod)'

gcloud scheduler jobs describe fact-check-morning-report \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format='value(name,schedule,state,timeZone,httpTarget.uri,httpTarget.httpMethod)'
```

apply 後 30 分以内:

```bash
gcloud run jobs executions list \
  --job=publish-notice \
  --project=baseballsite \
  --region=asia-northeast1 \
  --limit=3 \
  --format='value(name,status.startTime,status.conditions[0].status)'

gcloud run jobs executions list \
  --job=codex-shadow \
  --project=baseballsite \
  --region=asia-northeast1 \
  --limit=3 \
  --format='value(name,status.startTime,status.conditions[0].status)'

gcloud run jobs executions list \
  --job=draft-body-editor \
  --project=baseballsite \
  --region=asia-northeast1 \
  --limit=3 \
  --format='value(name,status.startTime,status.conditions[0].status)'

gcloud run jobs executions list \
  --job=guarded-publish \
  --project=baseballsite \
  --region=asia-northeast1 \
  --limit=5 \
  --format='value(name,status.startTime,status.conditions[0].status)'
```

`giants-realtime-trigger` は Cloud Run Job ではなく Cloud Run Service `/run` を叩くため、execution list ではなく scheduler 側の直近実行と service 側ログで確認する:

```bash
gcloud scheduler jobs describe giants-realtime-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format='value(name,schedule,state,timeZone,lastAttemptTime)'

gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher"' \
  --project=baseballsite \
  --limit=20 \
  --freshness=30m \
  --format='value(timestamp,severity,textPayload)'
```

補足:

- `guarded-publish-trigger` と `giants-realtime-trigger` は cadence 維持であり、apply 対象外
- ただし phase 1 apply 後 30 分以内は publish 本線 / realtime 本線の failure 有無を別途監視する

## anomaly detection and rollback triggers

- `guarded-publish` execution failure を 1 回でも確認したら即 rollback
- `giants-realtime-trigger` の `lastAttemptTime` 停滞、または `yoshilover-fetcher` `/run` 側で non-2xx / failure log を確認したら即 rollback とし、phase 1 変更との相関を切り分ける
- `publish-notice` failure が 2 連続したら rollback
- `codex-shadow` failure が 2 連続したら rollback
- `draft-body-editor` failure が 2 連続したら rollback
- `fact-check-morning-report` が想定時刻に発火しない、または `uri` / `httpMethod` drift が見えたら rollback
- `diff -u /tmp/*.before.json /tmp/*.after.json` で schedule / timeZone 以外の差分が出たら rollback して再 describe

## non-goals

- Cloud Run Job / Service update
- image rebuild / Cloud Build submit
- src / tests / config / Dockerfile / cloudbuild の変更
- WP write / X 投稿 / mail 内容変更
- Secret / env / IAM / retry policy / auth 設定変更
- `guarded-publish-trigger` / `giants-realtime-trigger` の cadence 変更

## next

phase 2 は `guarded-publish` logging compaction を別便で扱う。scheduler cadence governor phase 1 と同時に image rebuild や code 変更を混ぜない。
