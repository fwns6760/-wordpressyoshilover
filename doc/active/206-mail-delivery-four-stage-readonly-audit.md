# 206 mail delivery four-stage read-only audit

## meta

- number: 206
- status: BLOCKED_EXTERNAL
- priority: P0.5
- lane: A
- type: read-only audit
- scope: `doc/active/206-mail-delivery-four-stage-readonly-audit.md` only
- hard_constraints_respected:
  - `README / assignments / other active docs untouched`
  - `src / tests / requirements / cloudbuild / Dockerfile untouched`
  - `GCP live write / WP write / mail send / X post / secret display untouched`

## summary

2026-04-27 JST の 4-stage read-only audit を開始したが、sandbox では `~/.config/gcloud` が write 不可、回避のため既存 gcloud config を `/tmp/gcloud-codex-206-2` へ複製して再試行したところ、全 read-only command が `Your current active account [fwns6760@gmail.com] does not have any valid credentials` で停止した。

user 指定 stop 条件 `gcloud sandbox auth fail で全 read-only も止まる → runbook 出力 + 停止` に従い、Stage 1 の partial evidence までを固定し、Stage 2-4 は未実施で停止する。

## stage 1: RSS / ingestion

### raw data

- first attempt before config workaround:
  - command: `gcloud scheduler jobs describe giants-realtime-trigger --project=baseballsite --location=asia-northeast1 --format='value(state,schedule,lastAttemptTime,scheduleTime,status.code)'`
  - output: `ENABLED    */5 * * * *    2026-04-27T02:10:19.209688Z    2026-04-27T02:15:04.306542Z`
- sandbox filesystem failure on subsequent gcloud commands:
  - `Unable to create private file [/home/fwns6/.config/gcloud/credentials.db]: [Errno 30] Read-only file system`
- second attempt with `CLOUDSDK_CONFIG=/tmp/gcloud-codex-206-2`:
  - `gcloud scheduler jobs describe giants-realtime-trigger ...`
  - `gcloud scheduler jobs list ...`
  - `gcloud run jobs executions list --job=yoshilover-fetcher ...`
  - `gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=yoshilover-fetcher ...'`
  - `gcloud logging read 'resource.type=cloud_scheduler_job AND resource.labels.job_id=giants-realtime-trigger ...'`
- auth failure on every retried command:
  - `ERROR: (gcloud.*) Your current active account [fwns6760@gmail.com] does not have any valid credentials`

###判定

- `giants-realtime-trigger` 自体が disabled という証拠はない
- 直近 observed scheduler state:
  - state: `ENABLED`
  - schedule: `*/5 * * * *`
  - lastAttemptTime: `2026-04-27T02:10:19.209688Z` (`2026-04-27 11:10:19 JST`)
  - scheduleTime: `2026-04-27T02:15:04.306542Z` (`2026-04-27 11:15:04 JST`)
- ただし execution / HTTP 200 / draft creation log は auth failure により未観測

## stage 2: guarded-publish

### raw data

- not executed
- blocked by: `gcloud valid credentials` failure after sandbox config workaround

###判定

- `guarded-publish-trigger ENABLED / latest execution / proposed_count / sent_count / refused_count` は未判定

## stage 3: publish-notice

### raw data

- not executed
- blocked by: `gcloud valid credentials` failure after sandbox config workaround

###判定

- `publish-notice` image / execution / emit count / cursor / `manual_x_post_candidates` は未判定

## stage 4: WordPress reality via GCS/logs

### raw data

- not executed
- blocked by: `gcloud valid credentials` failure after sandbox config workaround

###判定

- `09:05 JST` 以降 publish 件数、`status=sent` 件数、draft pool 推測は未判定

## final conclusion

- result: `BLOCKED BEFORE A-E`
- reason:
  - sandbox で `~/.config/gcloud` write 不可
  - `/tmp` config workaround 後も active account credential invalid
  - user 指定 stop 条件により A-E 判定フェーズへ進めない
- note:
  - partial evidence としては `giants-realtime-trigger` が `ENABLED` で `*/5` という点のみ確認できた
  - `A / B / C / D / E` のいずれかを確定できる観測材料は取得不能

## recommended next ticket

- narrow fix direction:
  - authenticated executor 側で `gcloud auth login` または有効な service account credential を再セット
  - writable `CLOUDSDK_CONFIG` で read-only command 群を再実行
  - 同じ 4-stage command set をそのまま replay し、A-E を再判定
- minimal rerun order:
  1. Stage 1 の `yoshilover-fetcher` execution / log を回収
  2. Stage 2 の `guarded_publish_history.jsonl` と `proposed_count / sent_count / refused_count` を回収
  3. Stage 3 の `publish-notice` image / execution / cursor / emit count を回収
  4. Stage 4 の `status=sent` と draft evidence で `publish exists but notice misses` か `publish never happens` かを切り分ける
