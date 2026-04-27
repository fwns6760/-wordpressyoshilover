# 187 publish-notice scheduler URI v1 fix verification

## meta

- number: 187
- owner: Codex
- type: ops / scheduler verification
- status: CLOSED
- priority: P0.5
- lane: A
- created: 2026-04-27
- closed_via: `74ccef6`
- parent: 161 / 103

## 背景

- 2026-04-27 朝、`publish-notice-trigger` が `PERMISSION_DENIED` を返し、13 時間超 Cloud Run Job `publish-notice` を起動できず、mail が送られていなかった。
- Claude が境界越えで緊急復旧を実施し、Scheduler URI を Cloud Run Jobs v2 endpoint から v1 endpoint へ切り替えた。
- その後、Cloud Run Job `publish-notice` を手動 execute し、execution `publish-notice-9vd48` で 8 件 + summary mail 送信が完了した。

## 修正内容

- `publish-notice-trigger` の target URI を以下へ統一した。

```text
https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/publish-notice:run
```

- これは既存で稼働している `guarded-publish-trigger` と同系の v1 regional URI である。

## verify result

### Step 1: Scheduler 設定確認

Command:

```bash
gcloud scheduler jobs describe publish-notice-trigger --project=baseballsite --location=asia-northeast1 --format=yaml
```

Result:

- success
- `httpTarget.uri`: `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/publish-notice:run`
- `state`: `ENABLED`
- `schedule`: `15 * * * *`
- `timeZone`: `Asia/Tokyo`
- `lastAttemptTime`: `2026-04-26T23:17:55.887466Z`
- `scheduleTime`: `2026-04-27T00:15:04.786579Z`
- `status.code`: `7` was still present in describe output, which is consistent with the pre-fix failure history and is not, by itself, a proof of post-fix success.

### Step 2: Scheduler 手動 trigger

Command:

```bash
gcloud scheduler jobs run publish-notice-trigger --project=baseballsite --location=asia-northeast1
```

Result:

- not verified in Codex sandbox
- first failure: `Unable to create private file [/home/fwns6/.config/gcloud/credentials.db]` because the sandbox mount for `~/.config/gcloud` is read-only
- retry with writable config:

```bash
env CLOUDSDK_CONFIG=/tmp/gcloud-config-187 gcloud scheduler jobs run publish-notice-trigger --project=baseballsite --location=asia-northeast1
```

- second failure: `Failed to resolve 'cloudscheduler.googleapis.com'` from the sandbox

### Step 3: Scheduler trigger result log

Command to run outside the sandbox:

```bash
gcloud logging read 'resource.type=cloud_scheduler_job AND resource.labels.job_id=publish-notice-trigger AND timestamp>="2026-04-26T23:15:00Z"' --project=baseballsite --limit=10 --format='value(timestamp,severity,jsonPayload.status)'
```

Result:

- skipped in Codex sandbox because Step 2 could not reach the Cloud Scheduler API
- success criterion: latest entry is not `ERROR` and `jsonPayload.status` is not `PERMISSION_DENIED`

### Step 4: Cloud Run Job execution 起動確認

Command to run outside the sandbox:

```bash
gcloud run jobs executions list --job=publish-notice --project=baseballsite --region=asia-northeast1 --limit=3
```

Result:

- skipped in Codex sandbox because Step 2 could not reach the Cloud Scheduler API
- success criterion: a new execution appears after the Step 2 trigger time and is newer than `publish-notice-9vd48`

## current status

- `REVIEW_NEEDED`
- config verification completed at Step 1
- Step 2-4 require execution from the user shell via `!` or another non-sandbox environment
- next natural tick shown by `describe`: `2026-04-27 09:15 JST` (`2026-04-27T00:15:04.786579Z`)
- once external Step 2-4 succeed, move this doc to `doc/done/2026-04/`

## guardrails held

- `src/`, `tests/`, `requirements*.txt`: untouched
- IAM / other scheduler jobs / Cloud Run job definitions / Secret Manager: untouched by Codex
- WP write: NO
- git push: NO
