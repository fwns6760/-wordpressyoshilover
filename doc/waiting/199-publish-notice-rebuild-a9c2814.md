# 199 publish-notice 単独 rebuild + deploy a9c2814

- priority: P0.5
- status: BLOCKED_USER
- owner: Codex / User / Claude follow-up
- lane: A
- parent: 188 / 189 / 194

## Background

- user 明示 GO: `publish-notice` のみを `a9c2814` で rebuild + deploy する。他 Job は触らない。
- baseline context:
  - current `publish-notice` image: `cbc335f` (`2026-04-26 22:48 UTC` build)
  - `1ac710b` / `b7a9e1f` で `src/publish_notice_email_sender.py` に `manual_x_post_candidates` / `_manual_x_context` が追加済み
  - 現 image にはこれらが未反映で、公開通知 mail に X 投稿候補 embed が入っていない想定
- hard constraints:
  - `guarded-publish` / `draft-body-editor` / `codex-shadow` / `publish-notice` 以外の Cloud Run Job は不可触
  - env / secret / scheduler / IAM / Secret Manager / WP / X / GCS state は不可触
  - `src/` / `tests/` / `requirements*.txt` / `Dockerfile.*` / `cloudbuild_*.yaml` は不可触
  - `git push` 禁止

## What Was Verified

- HEAD verify:
  - `git log -1 --format='%H'`
  - result: `a9c2814da76831132d116ed0ca1b8471eabb022f`

## Blocker

- Codex sandbox で live verify 用に `CLOUDSDK_CONFIG=/tmp/gcloud-cfg-199-a9c2814` を作成し、read-only confirm を試行した。
- stop point:

```text
ERROR: (gcloud.run.jobs.describe) Your current active account [fwns6760@gmail.com] does not have any valid credentials
Please run:

  $ gcloud auth login
```

- `gcloud run jobs describe publish-notice --project=baseballsite --region=asia-northeast1 ...` の read-only verify 時点で auth failure になったため、build / deploy / image update は未実行。
- partial live change を避けるため、この ticket は user shell runbook 化して停止した。

## No-Change Outcome

- Cloud Build submit: NOT RUN
- Cloud Run Job update: NOT RUN
- other Cloud Run Jobs touched: NO
- scheduler change: NO
- env / secret / IAM change: NO
- WP write: NO
- X post: NO

## User-Shell Runbook

前提: user shell 側で `gcloud` が有効認証済みであること。sandbox 回避のため一時 `CLOUDSDK_CONFIG` を `/tmp` に逃がす。

```bash
! cd /home/fwns6/code/wordpressyoshilover
! git log -1 --format='%H'
! mkdir -p /tmp/gcloud-cfg-199-a9c2814
! cp -a /home/fwns6/.config/gcloud/. /tmp/gcloud-cfg-199-a9c2814/
! CLOUDSDK_CONFIG=/tmp/gcloud-cfg-199-a9c2814 gcloud builds submit --project=baseballsite --region=asia-northeast1 --config=cloudbuild_publish_notice.yaml --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=publish-notice,_TAG=a9c2814 .
! CLOUDSDK_CONFIG=/tmp/gcloud-cfg-199-a9c2814 gcloud builds list --project=baseballsite --region=asia-northeast1 --filter='substitutions._TAG=a9c2814 AND substitutions._IMAGE_NAME=publish-notice' --format='value(status,id)' --limit=1
! CLOUDSDK_CONFIG=/tmp/gcloud-cfg-199-a9c2814 gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:a9c2814
! CLOUDSDK_CONFIG=/tmp/gcloud-cfg-199-a9c2814 gcloud run jobs describe publish-notice --project=baseballsite --region=asia-northeast1 --format='value(spec.template.spec.template.spec.containers[0].image,status.latestCreatedExecution.name)'
```

## Next Tick Verify

`publish-notice` の次 execution 後、latest execution name を取って `manual_x_post_candidates:` を確認する。

```bash
! CLOUDSDK_CONFIG=/tmp/gcloud-cfg-199-a9c2814 gcloud run jobs describe publish-notice --project=baseballsite --region=asia-northeast1 --format='value(status.latestCreatedExecution.name)'
! CLOUDSDK_CONFIG=/tmp/gcloud-cfg-199-a9c2814 gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=publish-notice AND labels."run.googleapis.com/execution_name"="<execution-name>" AND textPayload:"manual_x_post_candidates:"' --project=baseballsite --limit=20 --format='value(timestamp,textPayload)'
```

- accept 条件: 最新 execution の `textPayload` に `manual_x_post_candidates:` が含まれること

## Planned Rollback

deploy 成功後に旧 image へ戻す必要があれば、image だけ `cbc335f` に戻す。

```bash
! CLOUDSDK_CONFIG=/tmp/gcloud-cfg-199-a9c2814 gcloud run jobs update publish-notice --project=baseballsite --region=asia-northeast1 --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:cbc335f
```
