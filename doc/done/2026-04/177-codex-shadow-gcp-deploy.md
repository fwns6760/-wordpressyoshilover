# 177 codex-shadow-gcp-deploy(Codex repair lane を GCP Cloud Run Jobs で稼働開始)

## meta

- number: 177
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / infra / migration / Codex shadow lane
- status: **READY**(171 + 172 land 後、user `codex login` 完了後に fire)
- priority: P0(GCP migration の Codex shadow lane 稼働開始、最終 phase)
- lane: A
- created: 2026-04-26
- parent: 155 / 171 / 172 / ChatGPT phasing(Codex shadow Cloud Run 化)

## 背景

171 で `call_codex` 実装、172 で auth.json restore/writeback 実装、両方 land 済み。
**ただし Cloud Run Job として deploy はまだ無い**(コードだけ完成、稼働 0)。

本 ticket で完成:
1. Codex CLI を含む container image build
2. Cloud Run Job `codex-shadow` 作成
3. Secret Manager `codex-auth-json` に local auth.json push(初回 user `codex login` 必須)
4. Cloud Scheduler trigger 設定(repair lane と同 cadence、shadow lane なので頻度低めも可)
5. 手動 smoke 1 回 success 確認
6. shadow lane invariant 維持(WP write 禁止、parallelism=1)

## 前提

- user が WSL で `codex login` 1 回実行済み(`~/.codex/auth.json` 存在)
- これは OAuth ブラウザ認証で server 側自動化不可
- auth.json 内容は **絶対にログ / commit に出さない**(masked のみ)

## ゴール

`codex-shadow` Cloud Run Job が ChatGPT Pro auth.json で動き、Cloud Scheduler から 10-20 min ごと auto trigger され、Gemini 本線と並列に shadow execute(WP write なし、ledger に shadow_only 記録のみ)する状態。

## 仕様

### 成果物

- `Dockerfile.codex_shadow`(repo root)
- `cloudbuild_codex_shadow.yaml`
- `bin/codex_shadow_entrypoint.sh` は 172 で land 済(流用)
- `doc/active/177-deployment-notes.md`(deploy command / Cloud Scheduler / smoke 結果)

### Dockerfile 要点

- base: `node:22-bullseye-slim`(Codex CLI = Node.js binary)or `python:3.12-slim` + Node install
- install: `npm install -g @openai/codex`(Codex CLI)
- install: `google-cloud-cli`(gcloud / gsutil)
- install: `python3` + 既存 deps(repair runner も呼ぶ)
- copy: `src/`, `bin/codex_shadow_entrypoint.sh`(172 で land 済)
- ENV: `PYTHONPATH=/app`、`CODEX_HOME=/tmp/.codex`(172 invariant)
- ENTRYPOINT: `["/app/bin/codex_shadow_entrypoint.sh"]`

### Secret Manager

```bash
# 既存 secret に追加(無ければ create)
if gcloud secrets describe codex-auth-json --project=baseballsite >/dev/null 2>&1; then
  # 既存 → 新 version 追加
  gcloud secrets versions add codex-auth-json \
    --data-file="$HOME/.codex/auth.json" --project=baseballsite
else
  gcloud secrets create codex-auth-json --replication-policy=automatic --project=baseballsite
  gcloud secrets versions add codex-auth-json \
    --data-file="$HOME/.codex/auth.json" --project=baseballsite
fi
```

### Cloud Run Job 設定

- 名: `codex-shadow`
- region: `asia-northeast1`
- task-timeout: 600s(Codex CLI cold start + repair 想定)
- max-retries: 0(失敗は ledger 記録のみ、リトライしない)
- **parallelism: 1(必須、172 invariant)**
- env Secret 参照:
  - `codex-auth-json`(本 ticket)
  - 既存 secret(WP_URL / WP_USER / WP_APP_PASSWORD / WP_API_BASE / GEMINI_API_KEY、158 で land 済)
- service account: 既存 `487178857517-compute@developer.gserviceaccount.com`
- 追加 IAM: Secret Manager `secretmanager.secretAccessor` + `secretmanager.secretVersionAdder`(writeback 必要)

### Cloud Scheduler 設定

- 名: `codex-shadow-trigger`
- schedule: `5,15,25,35,45,55 * * * *`(10 min 間隔、Cloud Scheduler `draft-body-editor-trigger` の `2,12,...` と 3 min ずらし、衝突回避)
- target: Cloud Run Job `codex-shadow`
- shadow lane なので頻度は適宜調整(初期 10 min 安全)

### 動作確認

1. local `~/.codex/auth.json` 存在確認(`ls -la ~/.codex/auth.json` user 確認済)
2. Secret Manager に push
3. Artifact Registry に image push(`gcloud builds submit`)
4. Cloud Run Job 作成
5. 手動 `gcloud run jobs execute --wait` exit 0
6. Cloud Logging に shadow_only ledger 記録確認(WP write 0 verify)
7. Cloud Scheduler enable
8. 1 tick 自動 trigger 観測

## 不可触

- WSL crontab(全行)
- 既存 src(`src/codex_cli_shadow.py` / `src/cloud_run_secret_auth.py` 等、171/172 で land 済)/ tests / requirements*.txt 一切変更なし
- 既存 Cloud Run Jobs(`draft-body-editor` / `publish-notice` / `guarded-publish`)/ Secret Manager 既存 secret / GCS bucket 触らない
- 既存 Cloud Scheduler(`draft-body-editor-trigger` / `publish-notice-trigger` / `guarded-publish-trigger`)触らない
- automation.toml / .env / WordPress / X
- baseballwordpress repo
- **auth.json 内容を chat / log / commit / mail に絶対残さない**(file path / sha256 / size のみ)
- 並走 task `b3ngiu1an`(160)/ `b7nh41as4`(176)が touching する file 触らない

## acceptance

1. `Dockerfile.codex_shadow` + `cloudbuild_codex_shadow.yaml` repo 配置
2. `doc/active/177-deployment-notes.md` 作成
3. Secret Manager `codex-auth-json` 存在 + 1 version 以上(local auth.json から push)
4. Artifact Registry に image push
5. Cloud Run Job `codex-shadow` 作成 + parallelism=1 verify
6. 手動 `execute --wait` exit 0
7. Cloud Logging に shadow_only ledger 記録(provider="codex"、wp_write_allowed=False、status="shadow_only")
8. **WP write 数 = 0 verify**(shadow lane invariant)
9. Cloud Scheduler `codex-shadow-trigger` 作成 + ENABLED
10. auth.json sha256 比較で writeback 動作確認(refresh されたら Secret Manager 新 version)
11. push なし、Claude が後で push

## Hard constraints

- **auth.json 中身を log / stdout / exception message / commit / mail に絶対残さない**(masked のみ)
- 並走 task touching file 触らない
- secret 値 chat / log / commit 完全禁止
- WSL crontab 編集 / cron 時刻変更: 禁止
- `.env` 触らない
- 既存 src(171 / 172)logic 変更禁止
- `git add -A` 禁止、stage は **`Dockerfile.codex_shadow` + `cloudbuild_codex_shadow.yaml` + `doc/active/177-deployment-notes.md`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest 影響なし(code 触らない)
- Codex CLI 並列実行禁止(parallelism=1)
- Cloud Run Job 自動 retry 禁止(max-retries=0)
- live publish / WP write: 0 verify
- 165 / 168-173 / 156-167 で land 済の挙動を一切壊さない

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
# Secret 確認(value 表示禁止)
gcloud secrets describe codex-auth-json --project=baseballsite --format="value(name,createTime)" 2>&1
gcloud secrets versions list codex-auth-json --project=baseballsite --format="table(name,state)" 2>&1 | head -5
# Cloud Run Job 確認
gcloud run jobs describe codex-shadow --region=asia-northeast1 --project=baseballsite \
  --format="value(name,template.parallelism,template.taskCount,latestSucceededExecution)" 2>&1
# Cloud Scheduler 確認
gcloud scheduler jobs describe codex-shadow-trigger --location=asia-northeast1 --project=baseballsite --format="value(name,schedule,state)" 2>&1
# Cloud Logging 確認(shadow_only 記録 + WP write 0 verify)
gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=codex-shadow' --limit=10 --project=baseballsite 2>&1 | head -30
```

## Commit

```bash
git add Dockerfile.codex_shadow cloudbuild_codex_shadow.yaml doc/active/177-deployment-notes.md
git status --short
git commit -m "177: Codex shadow lane GCP deploy (Dockerfile + Cloud Build + Cloud Run Job parallelism=1 + Cloud Scheduler trigger、auth.json Secret Manager 経由)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

doc § 完了報告 形式厳守、**auth.json 内容 + 値は絶対含めない**(masked のみ)。

## stop 条件

- `~/.codex/auth.json` 不在 → 即停止 + 報告(user `codex login` 必要)
- Secret Manager push 失敗 → 即停止 + 報告
- Codex CLI が container 内で動かない(npm install 失敗等)→ 即停止 + 報告
- Cloud Run Job execute exit non-zero → log 添えて停止 + 報告
- shadow lane invariant 違反(WP write 検出)→ 即停止 + 即 disable Scheduler
- write scope 外 / 並走 task scope と衝突 → 即停止 + 報告

## 完了後の次便

- shadow lane 100 件以上の ledger 蓄積後、provider 比較 audit + 本線昇格判断(数週間後)
- Phase 4-5: gemini_audit / quality-monitor / quality-gmail GCP 化(残 WSL cron 全廃)
- title-subject-loss audit(178、別 ticket、share button 176 同等の quality issue)
