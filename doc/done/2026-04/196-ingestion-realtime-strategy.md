# 196 記事 ingestion 5 分毎リアルタイム化

- priority: P0.5
- status: CLOSED
- owner: Codex / Claude follow-up
- lane: A
- parent: 042 / 155

## Close note(2026-04-28)

- `giants-realtime-trigger` 5分化は live 作成・natural tick HTTP 200 確認済み。
- scheduler overlap / cadence再整理は別 ticket で扱う。

## Background

- user 明示: 「リアルタイム掲示板を作る」「コスト気にしない、リアルタイムに」「11:00 待つのおそい」
- 現行 `giants-*` ingestion trigger は平日昼 1 時間毎、週末前半 30 分毎、試合前後だけ 10 分毎で、週末早朝・深夜・平日 9-16 時に空白が残っている
- `yoshilover-fetcher-job` は PAUSED の旧 monolith で、resume は `/run` 二重発火リスクがあるため不可触

## Scope

- Cloud Scheduler に `giants-realtime-trigger` を新規追加する
- 既存 `giants-*` scheduler の schedule / state / URI / SA は変更しない
- `src/`, `tests/`, `requirements*.txt`, `bin/`, `Dockerfile`, `cloudbuild*` は不可触
- Cloud Run service / job の image / env / IAM は不可触
- Secret Manager, WP, X, GCS 直接操作はしない

## Step 1 Existing Trigger Findings

### Sample jobs

| job | schedule | attempt deadline | target URI | auth mode | caller SA |
|---|---|---|---|---|---|
| `giants-weekday-daytime` | `0 9-16 * * 1-5` | `180s` | `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run` | OIDC | `seo-web-runtime@baseballsite.iam.gserviceaccount.com` |
| `giants-weekend-pre` | `0,30 11-13 * * 0,6` | `300s` | `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run` | OIDC | `seo-web-runtime@baseballsite.iam.gserviceaccount.com` |
| `giants-weekend-lineup-day-b` | `10,20,40,50 13 * * 0,6` | `180s` | `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run` | OIDC | `seo-web-runtime@baseballsite.iam.gserviceaccount.com` |

### All `giants-*` jobs

- `gcloud scheduler jobs list --filter='name~giants-'` で確認した 14 本すべてが同一 URI を使用していた
- 全 `giants-*` job の caller SA は `seo-web-runtime@baseballsite.iam.gserviceaccount.com` で統一されていた
- target は Cloud Run Job API ではなく Cloud Run service `yoshilover-fetcher` の `/run` endpoint
- したがって本 ticket の新規 trigger は、PAUSED の `yoshilover-fetcher-job` ではなく、既存 `giants-*` と同じ `yoshilover-fetcher` service endpoint を叩くのが正

## Design Options

### Option A: 新 trigger 1 本追加(並走 + 既存維持)

- 新規 scheduler `giants-realtime-trigger` を作成
- schedule は `*/5 * * * *`
- target URI / auth mode / caller SA は既存 `giants-*` と同一にする
- 重複は既存の `rss_history.json` / draft dedup に委ねる
- 既存 `giants-*` は当面残し、1-2 週間の観察期間を設ける

Pros:

- 即効性が高い
- 既存 trigger を触らないので rollback が容易
- PAUSED の旧 monolith を revive せずに空白帯を埋められる

Cons:

- 既存 trigger と一時的に冗長になる
- 同一 source の重複 fetch が増える

### Option B: 既存 trigger 全 schedule 拡張

- `giants-weekday-daytime` を `*/5 9-16 * * 1-5` へ拡張
- `giants-weekend-*` を `*/5` 化し、早朝・深夜用 trigger も追加する
- ラインナップ系 / postgame 系との境界も再調整する

Pros:

- 最終形としては trigger 体系が整理される
- 冗長 scheduler を増やさずに済む

Cons:

- 既存 job を多数更新するためロールバックが複雑
- 誤更新時の影響範囲が広い
- 本 ticket の hard constraint「既存 giants-* 一切変更しない」に反する

## Recommendation

- 推奨は Option A
- user の「11:00 待つのおそい」に対する即効性が最も高く、既存 cadence を壊さずに 5 分周期を導入できる
- 1-2 週間観察して duplicate load や空振り頻度が許容範囲なら、別 ticket で既存 `giants-*` の削減または schedule 簡素化を検討する

## Implementation

- `giants-realtime-trigger` を `*/5 * * * *` / `Asia/Tokyo` / `attemptDeadline=180s` で新規作成
- target は `https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run`
- auth mode は既存と同じ OIDC、caller SA は `seo-web-runtime@baseballsite.iam.gserviceaccount.com`
- message body は `{}`、header は `Content-Type: application/json`
- sandbox では `gcloud` mutate が `~/.config/gcloud` read-only と copied config credential invalid の組み合わせで不安定だったため、ADC token を使った Cloud Scheduler REST API create で反映した

## Runbook

Read-only inspect:

```bash
gcloud scheduler jobs list \
  --project=baseballsite \
  --location=asia-northeast1 \
  --filter='name~giants-' \
  --format='csv(name,httpTarget.oidcToken.serviceAccountEmail,httpTarget.uri,attemptDeadline)'
```

Equivalent create command for user shell:

```bash
gcloud scheduler jobs create http giants-realtime-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule='*/5 * * * *' \
  --time-zone='Asia/Tokyo' \
  --uri='https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run' \
  --http-method=POST \
  --headers='Content-Type=application/json' \
  --message-body='{}' \
  --oidc-service-account-email='seo-web-runtime@baseballsite.iam.gserviceaccount.com' \
  --oidc-token-audience='https://yoshilover-fetcher-487178857517.asia-northeast1.run.app/run' \
  --attempt-deadline=180s
```

Rollback:

```bash
gcloud scheduler jobs delete giants-realtime-trigger \
  --project=baseballsite \
  --location=asia-northeast1
```

## Verify

- create response: HTTP 200
- created job: `projects/baseballsite/locations/asia-northeast1/jobs/giants-realtime-trigger`
- state: `ENABLED`
- schedule: `*/5 * * * *`
- next natural tick at create time: `2026-04-27 09:55:00 JST`
- first natural tick observed:
  - job `lastAttemptTime`: `2026-04-27T00:55:23.545102Z` (`2026-04-27 09:55:23 JST`)
  - next scheduled fire after verify: `2026-04-27T01:00:04.306542Z` (`2026-04-27 10:00:04 JST`)
  - Cloud Scheduler execution log:
    - `AttemptStarted` scheduled time `2026-04-27T00:55:00.223718Z`
    - `AttemptFinished` at `2026-04-27T00:55:32.402066554Z`
    - HTTP response: `200`
- existing `giants-*` schedules remained unchanged during this ticket

## Guardrails Held

- existing `giants-*` scheduler changes: NO
- `yoshilover-fetcher-job` resume: NO
- Cloud Run image/env/IAM change: NO
- WP write: NO
- git push: NO
