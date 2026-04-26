# 161 publish-notice-gcp-migration(155 Phase 3、095 WSL cron → Cloud Run Job)

## meta

- number: 161
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / infra / migration
- status: **READY**(155-1a/1b done、172 と disjoint 並列可)
- priority: P0.5(publish per-post mail を PC 依存解消)
- lane: A
- created: 2026-04-26
- parent: 155 / 095 series / ChatGPT phasing(Phase 3 = 161)

## 背景

現状:
- WSL crontab の 095(`15 * * * *`)で `run_publish_notice_email_dry_run --scan --send` 実行
- per-post mail + 10 件 summary + alert(131 mail layering)
- WSL 依存(PC sleep / Codex Desktop 不要、ただし PC 起動依存)

GCP 移行(155 master Phase 3):
- 同 Python script を Cloud Run Jobs で動かす
- Cloud Scheduler `15 * * * *` で trigger
- WSL 095 cron は並走維持(GCP 安定 1 日後に Phase 3e で disable)
- 既存 logic / mail layering / dedup(cursor / history)変更なし

## ゴール

`src/tools/run_publish_notice_email_dry_run.py` を Cloud Run Jobs で実行可能な container 化、Artifact Registry に push、Cloud Run Job 作成、Cloud Scheduler trigger 設定、手動 smoke 1 回 success まで。

## 仕様

### 成果物

- `Dockerfile.publish_notice`(repo root、155-1a `Dockerfile.draft_body_editor` と同パターン)
- `cloudbuild_publish_notice.yaml`(Cloud Build 用)
- `doc/active/161-deployment-notes.md`(deploy command / smoke 結果)
- 既存 src(`src/tools/run_publish_notice_email_dry_run.py`)/ tests / .env / WSL crontab: 一切変更なし

### Dockerfile 要点(155-1a と同)

- base: `python:3.12-slim`
- workdir: `/app`
- copy: `src/`, `vendor/`(必要なら)、`requirements*.txt`(無ければ vendor 直 import)
- pip install: 必要ぶんのみ
- ENV: `PYTHONPATH=/app`
- ENTRYPOINT: `["python3", "-m", "src.tools.run_publish_notice_email_dry_run"]`
- CMD default: `["--scan", "--send", "--cursor-path", "/data/publish_notice_cursor.txt", "--history-path", "/data/publish_notice_history.json", "--queue-path", "/data/publish_notice_queue.jsonl"]`(GCP 用 path、cursor / history は Cloud Run Job では永続化に GCS or Firestore 想定、本 ticket では `/data` placeholder で OK、158 で本実装)
- USER: 非 root user

### Cloud Build / Cloud Run Job / Scheduler

- Artifact Registry: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:<commit-hash>`
- Cloud Run Job 名: `publish-notice`
- region: `asia-northeast1`
- task-timeout: 300s
- max-retries: 1
- env(plain、Phase 1d で Secret Manager 化):
  - `MAIL_BRIDGE_SMTP_USERNAME=fwns6760@gmail.com`
  - `MAIL_BRIDGE_FROM=fwns6760@gmail.com`
  - `PUBLISH_NOTICE_EMAIL_ENABLED=1`
  - `MAIL_BRIDGE_SMTP_PASSWORD=<masked>`(WSL `.env` から取得)
  - `WP_URL` / `WP_USER` / `WP_APP_PASSWORD`(同上、必要に応じて)
- Cloud Scheduler:
  - 名: `publish-notice-trigger`
  - schedule: `15 * * * *`(毎時 :15、WSL 095 と同時刻、並走中は両方発火 → 既存 dedup で吸収)
  - region: `asia-northeast1`

### 動作確認

1. Artifact Registry に image push
2. Cloud Run Job `publish-notice` 作成 + manual `gcloud run jobs execute --wait`
3. exit 0 確認、Cloud Logging に出力確認
4. 同時刻に WSL 095 も走る → 両方が同 history.json を見るが既存 dedup で重複 mail 出ない verify
5. Cloud Scheduler 設定(本 ticket では設定のみ、手動 trigger smoke が pass してから enable)

## 不可触

- WSL crontab 095 行(並走維持、disable は Phase 3e で別 ticket)
- `Dockerfile.draft_body_editor` / `cloudbuild_draft_body_editor.yaml`(155-1a で fix 済、別 image)
- 既存 src(`src/tools/run_publish_notice_email_dry_run.py`)/ tests / requirements*.txt: 一切変更なし
- 既存 GCP services(giants-* / draft-body-editor Cloud Run Job)
- automation.toml / .env / secrets / WordPress / X / Cloud Run env(既存)
- baseballwordpress repo
- **並走 task `b8t03kqjl`(172 secret-auth-writeback)が touching する file 触らない**: `src/cloud_run_secret_auth.py` / `tests/test_cloud_run_secret_auth.py` / `bin/codex_shadow_entrypoint.sh` / `tests/test_codex_shadow_entrypoint.py`

## acceptance

1. `Dockerfile.publish_notice` + `cloudbuild_publish_notice.yaml` repo 配置
2. `doc/active/161-deployment-notes.md` 作成(deploy command / env masked snapshot / smoke 結果)
3. Artifact Registry に image push 確認(`gcloud artifacts docker images list ...`)
4. Cloud Run Job `publish-notice` 作成 + 手動 `execute --wait` exit 0
5. Cloud Logging に publish-notice 出力(JSON、行数 / 失敗 / 成功)
6. WSL 095 並走中、dedup 動作 verify(同 history.json で重複 mail 出ない)
7. Cloud Scheduler `publish-notice-trigger` 作成(`15 * * * *`、enable 状態)
8. live mail 発生する可能性あり(cursor 進んでない publish があれば)、smoke は **1 回限り**、繰り返し execute しない
9. WSL crontab 095 行: **未変更 verify**
10. src / tests / requirements*: 未変更 verify
11. push なし、Claude が後で push

## Hard constraints

- **secret 値の chat 表示 / log 表示 / commit 完全禁止**(masked のみ doc に残す)
- 並走 task `b8t03kqjl`(172)が touching する file 触らない
- `git add -A` 禁止、stage は **`Dockerfile.publish_notice` + `cloudbuild_publish_notice.yaml` + `doc/active/161-deployment-notes.md`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- WSL crontab 編集 / 既存 cron 時刻変更: 禁止
- code 触らない(src / tests / requirements*)、Dockerfile + yaml + doc のみ
- pytest 影響なし(code 触らない)
- live mail 発生する可能性 → smoke は 1 回限り
- 165 / 168 / 169 / 170 / 171 で land 済の挙動を一切壊さない

## Verify

```bash
# Artifact Registry 確認
gcloud artifacts docker images list asia-northeast1-docker.pkg.dev/baseballsite/yoshilover --include-tags 2>&1 | grep publish-notice
# Cloud Run Job 確認
gcloud run jobs describe publish-notice --region=asia-northeast1 --project=baseballsite --format="value(name,latestSucceededExecution)" 2>&1
# Cloud Scheduler 確認
gcloud scheduler jobs describe publish-notice-trigger --location=asia-northeast1 --project=baseballsite 2>&1 | head -10
# Cloud Logging 確認
gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=publish-notice' --limit=5 --project=baseballsite 2>&1 | head -20
# repo 状態 verify(code に触れていないこと)
cd /home/fwns6/code/wordpressyoshilover
git status --short
git diff src/ tests/ requirements.txt 2>&1 | head -3  # 空であるべき
# WSL crontab 不変 verify
crontab -l | grep -E "publish_notice|095-WSL-CRON-FALLBACK" | head -3
```

## Commit

```bash
git add Dockerfile.publish_notice cloudbuild_publish_notice.yaml doc/active/161-deployment-notes.md
git status --short
git commit -m "161 (Phase 3): publish-notice Cloud Run Job migration (Dockerfile + Cloud Build + Cloud Scheduler trigger 15 * * * *、WSL 095 並走維持)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

```
- changed files: <list>
- Artifact Registry image: publish-notice:<hash>
- Cloud Run Job created: publish-notice
- gcloud run jobs execute exit code: 0/N
- Cloud Logging output excerpt: <JSON 抜粋>
- Cloud Scheduler created: publish-notice-trigger (15 * * * *)
- env vars set: <masked list>
- WSL cron 095 行: 未変更 verify
- src / tests / requirements*: 未変更 verify
- WP write 発生: yes/no(mail 通数)
- live mail 通数: <count>(smoke 1 回限り)
- push: NO
- commit hash: <hash>
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- Cloud Build fail → 即停止 + 報告
- Cloud Run Job execute exit non-zero → log 添えて停止 + 報告
- SMTP 認証 fail / mail 送信 fail → 即停止 + 報告
- WSL crontab dedup 効かず重複 mail 検出 → 即停止 + 報告
- 既存 src を改変する必要発覚 → 即停止 + 報告(本 ticket scope 外)
- write scope 外を触る必要 → 即停止 + 報告

## 完了後の次便

- Phase 3e: WSL crontab 095 行 disable(GCP 安定 1 日確認後、user 判断)
- Phase 4: gemini_audit GCP migration(162)
- Phase 5: quality-monitor / quality-gmail GCP migration(163)
