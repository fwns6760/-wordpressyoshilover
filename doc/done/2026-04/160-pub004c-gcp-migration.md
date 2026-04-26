# 160 pub004c-gcp-migration(155 Phase 2、PUB-004-C WSL cron → Cloud Run Job)

## meta

- number: 160
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / infra / migration
- status: **READY**(155-1a/1b/1c done、158 GCS persistence done、即 fire 可)
- priority: **P0**(WSL 042/095 disable 後の publish lane 完全 GCP 化)
- lane: A
- created: 2026-04-26
- parent: 155 / 156 / 158 / ChatGPT phasing(Phase 2 = 160)

## 背景

WSL 042 + 095 は今 disable 済(GCP Cloud Run Jobs で代替)。
**PUB-004-C(`*/5 * * * *` で publish 評価 + 実行)が WSL のみで動いてる**(disable すると publish 停止)。

完全 GCP 化のために本 ticket で:
- `run_guarded_publish_evaluator`(PUB-004-A)+ `run_guarded_publish`(PUB-004-B、--live --daily-cap-allow)を 1 つの Cloud Run Job として container 化
- Cloud Scheduler `*/5 * * * *` で trigger
- 158 GCS persistence pattern を `cron_eval.json` / publish history に適用

## ゴール

`guarded-publish` Cloud Run Job を作成し、Cloud Scheduler から 5 min ごと auto trigger、WSL PUB-004-C と完全置換可能な状態にする(WSL disable は別 commit、本 ticket で smoke pass まで)。

## 仕様

### 成果物

- `Dockerfile.guarded_publish`(repo root)
- `cloudbuild_guarded_publish.yaml`
- `bin/guarded_publish_entrypoint.sh`(GCS download cron_eval.json + history → run evaluator → run publisher → upload back)
- `doc/active/160-deployment-notes.md`(deploy command / Cloud Scheduler / smoke 結果)
- 既存 src(`src/tools/run_guarded_publish_evaluator.py` / `run_guarded_publish.py`)/ tests / .env / WSL crontab: 一切変更なし

### Dockerfile 要点(155-1a / 161 と同パターン)

- base: `python:3.12-slim`
- workdir: `/app`
- install: `google-cloud-cli`(gcloud / gsutil 含む)
- copy: `src/`, `vendor/`, `requirements*.txt`, `bin/guarded_publish_entrypoint.sh`
- ENV: `PYTHONPATH=/app`、その他 env は Cloud Run Jobs 側 Secret Manager で注入(158 で land 済 secret 流用)
- ENTRYPOINT: `["/app/bin/guarded_publish_entrypoint.sh"]`

### bin/guarded_publish_entrypoint.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

GCS_PREFIX="gs://baseballsite-yoshilover-state/guarded_publish"
LOCAL_TMP="/tmp/pub004d"
mkdir -p "$LOCAL_TMP"

# 1. download history (cron_eval.json は毎回 fresh 生成、download 不要)
gcloud storage cp "${GCS_PREFIX}/guarded_publish_history.jsonl" \
  "$LOCAL_TMP/guarded_publish_history.jsonl" 2>/dev/null || \
  echo "[]" > "$LOCAL_TMP/guarded_publish_history.jsonl"

# 2. run evaluator → cron_eval.json
python3 -m src.tools.run_guarded_publish_evaluator \
  --window-hours 999999 --max-pool 500 --format json \
  --output "$LOCAL_TMP/cron_eval.json" --exclude-published-today

# 3. run publisher (live, daily cap)
python3 -m src.tools.run_guarded_publish \
  --input-from "$LOCAL_TMP/cron_eval.json" \
  --max-burst 20 --live --daily-cap-allow \
  --history-path "$LOCAL_TMP/guarded_publish_history.jsonl"

# 4. upload history back
gcloud storage cp "$LOCAL_TMP/guarded_publish_history.jsonl" \
  "${GCS_PREFIX}/guarded_publish_history.jsonl"
```

(具体 history path / yellow_log / cleanup_log の handling は既存 runner CLI args に応じて実装、download/upload する file は all relevant logs)

### Cloud Run Job 設定

- 名: `guarded-publish`
- region: `asia-northeast1`
- task-timeout: 600s(burst 20 件 publish + cleanup + WP REST 想定)
- max-retries: 1
- env Secret 参照: 158 で作成済 secret(WP_URL / WP_USER / WP_APP_PASSWORD / WP_API_BASE / GEMINI_API_KEY)
- service account: 既存 `487178857517-compute@developer.gserviceaccount.com`

### Cloud Scheduler 設定

- 名: `guarded-publish-trigger`
- schedule: `*/5 * * * *`(JST、WSL PUB-004-C と同時刻、両方稼働中は dedup で吸収)
- target: Cloud Run Job `guarded-publish`

### 動作確認

1. Artifact Registry に image push
2. Cloud Run Job 作成 + 手動 `gcloud run jobs execute --wait` exit 0
3. Cloud Logging に publish 結果 JSON
4. Cloud Scheduler enable → 5min 後の :XX5 で auto trigger 観測
5. 1-2 tick observation で挙動評価
6. 問題なければ別 commit で WSL PUB-004-C disable

## 不可触

- WSL crontab PUB-004-C 行(本 ticket は GCP 化のみ、disable は別 commit)
- 既存 src(`run_guarded_publish_*.py`)/ tests / requirements*.txt: 一切変更なし
- 既存 GCP services(giants-* / draft-body-editor / publish-notice)
- automation.toml / .env / secrets / 既存 Secret Manager(158 で land 済を流用)
- baseballwordpress repo
- WordPress / X
- Cloud Run env(既存 services)
- 並走 task `bvci2zkhq`(167 v2 billing alert)が touching する file 触らない(`scripts/setup_billing_alerts.sh` / `doc/active/167-billing-alert-deployment-notes.md`)

## acceptance

1. `Dockerfile.guarded_publish` + `cloudbuild_guarded_publish.yaml` repo 配置
2. `bin/guarded_publish_entrypoint.sh` 新規(GCS download/upload pattern)
3. `doc/active/160-deployment-notes.md` 作成
4. Artifact Registry に image push
5. Cloud Run Job `guarded-publish` 作成 + 手動 `execute --wait` exit 0
6. Cloud Logging に publish 結果出力
7. GCS bucket `gs://baseballsite-yoshilover-state/guarded_publish/` に history persist verify
8. Cloud Scheduler `guarded-publish-trigger` 作成 + ENABLED
9. 次 :X5 tick で auto trigger 観測
10. WSL crontab PUB-004-C 行: **未変更 verify**
11. src / tests / requirements*: 未変更 verify
12. live publish 発生する可能性あり(WSL PUB-004-C と GCP guarded-publish 両方走る、history dedup で重複防止)
13. push なし、Claude が後で push

## Hard constraints

- secret 値の chat / log / commit 完全禁止(masked のみ)
- 並走 task `bvci2zkhq`(167 v2)が touching する file 触らない
- WSL crontab PUB-004-C 行 編集 / disable 禁止(本 ticket scope 外、別 commit)
- code 触らない(src / tests / requirements*)、Dockerfile + yaml + entrypoint script + doc のみ
- `git add -A` 禁止、stage は **`Dockerfile.guarded_publish` + `cloudbuild_guarded_publish.yaml` + `bin/guarded_publish_entrypoint.sh` + `doc/active/160-deployment-notes.md`** だけ
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest 影響なし(code 触らない)
- live publish 発生する可能性 → smoke は **1-2 回限り**、繰り返し execute しない
- 165 / 168 / 169 / 170 / 171 / 172 / 156 / 157 / 158 / 161 / 166 で land 済の挙動を一切壊さない
- gcloud auth / IAM / Cloud Run / Scheduler / Secret Manager / Storage 全て 158 / 156 / 157 で land 済 SA 流用

## 環境設定

```bash
mkdir -p /tmp/gcloud-config
if [ -d ~/.config/gcloud ] && [ ! -d /tmp/gcloud-config/configurations ]; then
  cp -r ~/.config/gcloud/* /tmp/gcloud-config/ 2>/dev/null || true
fi
export CLOUDSDK_CONFIG=/tmp/gcloud-config
```

## Verify

```bash
export CLOUDSDK_CONFIG=/tmp/gcloud-config
gcloud artifacts docker images list asia-northeast1-docker.pkg.dev/baseballsite/yoshilover --include-tags 2>&1 | grep guarded-publish
gcloud run jobs describe guarded-publish --region=asia-northeast1 --project=baseballsite --format="value(name,latestSucceededExecution)" 2>&1
gcloud scheduler jobs describe guarded-publish-trigger --location=asia-northeast1 --project=baseballsite --format="value(name,schedule,timeZone,state)" 2>&1
gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=guarded-publish' --limit=5 --project=baseballsite 2>&1 | head -20
gcloud storage ls gs://baseballsite-yoshilover-state/guarded_publish/ 2>&1 | head
crontab -l | grep "PUB-004-C\|guarded_publish" | head
```

## Commit

```bash
git add Dockerfile.guarded_publish cloudbuild_guarded_publish.yaml bin/guarded_publish_entrypoint.sh doc/active/160-deployment-notes.md
git status --short
git commit -m "160 (Phase 2): PUB-004-C Cloud Run Job migration (Dockerfile + Cloud Build + Cloud Scheduler */5 * * * *、GCS history persist、WSL PUB-004-C 並走維持)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

doc § 完了報告 形式厳守、**secret 値は絶対含めない**(masked のみ)。

## stop 条件

- gcloud / Cloud Run / Scheduler / Storage 権限不足 → 即停止 + 報告
- Cloud Build fail → 即停止 + 報告
- Cloud Run Job execute exit non-zero → log 添えて停止 + 報告
- WSL PUB-004-C を改変する必要発覚 → 即停止 + 報告(本 ticket scope 外)
- write scope 外を触る必要 → 即停止 + 報告
- 既存 src / runner CLI args 変更が必要 → 即停止 + 報告(別 ticket)

## 完了後の次便

- WSL PUB-004-C cron disable(別 commit、user 判断、ただし「GCPのみ」承認済なので Claude 自律で実行)
- Phase 4: 162 gemini_audit GCP migration(残 WSL cron 全廃へ)
- title-truncation audit(post 63668 等の主語欠落 bug 別 ticket)
