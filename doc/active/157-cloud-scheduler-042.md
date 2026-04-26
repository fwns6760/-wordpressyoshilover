# 157 cloud-scheduler-042(155 Phase 1c、042 Cloud Run Job に Scheduler trigger 追加)

## meta

- number: 157
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / infra / cron
- status: **READY**(155-1b done `c5adfa3`、172 done、161 と disjoint 並列可)
- priority: P0.5
- lane: A
- created: 2026-04-26
- parent: 155 / 156

## 背景

156 で Cloud Run Job `draft-body-editor` 作成 + 手動 smoke pass 済。
本 ticket で **Cloud Scheduler から自動 trigger** 追加し、WSL cron 042(`2,12,22,32,42,52 * * * *`)と並走させる。
WSL 042 は disable せず維持(Phase 1e で別判断)。

## ゴール

Cloud Scheduler `draft-body-editor-trigger` 作成、`2,12,22,32,42,52 * * * *` で Cloud Run Job `draft-body-editor` を auto trigger する。WSL 042 と同時刻に並走、Cloud Logging で両方の挙動を観察可能にする。

## 仕様

### Cloud Scheduler 設定

```bash
gcloud scheduler jobs create http draft-body-editor-trigger \
  --project=baseballsite \
  --location=asia-northeast1 \
  --schedule="2,12,22,32,42,52 * * * *" \
  --time-zone="Asia/Tokyo" \
  --uri="https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/draft-body-editor:run" \
  --http-method=POST \
  --oauth-service-account-email="<service-account>@baseballsite.iam.gserviceaccount.com" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

(具体 service account は既存 giants-* で使ってる SA を流用、なければ Cloud Run Invoker role 付きで新規作成)

### 並走運用

- **WSL crontab 042 行 unchanged**(`2,12,22,32,42,52 * * * *` 継続)
- Cloud Scheduler `draft-body-editor-trigger` も同時刻に Cloud Run Job 起動
- → 同 draft を **両方が処理する可能性あり**:
  - WP REST GET 競合: 軽量、問題なし
  - Gemini API 二重 call: cost 倍(¥120 → ¥240/月相当、free tier 内継続)
  - WP PUT 競合: 既存 042 の internal lock / dedup(`recently_edited_by_lane` filter)で吸収
- **observation 期間 1-2 日**で competing 挙動評価、Phase 1e で WSL 042 disable

### 成果物

- `doc/active/157-deployment-notes.md`(deploy command / scheduler 確認手順 / smoke 結果)
- 既存 src / tests / .env / WSL crontab / Dockerfile / cloudbuild yaml: 一切変更なし

## 不可触

- WSL crontab 042 行(本 ticket は disable しない、Phase 1e で別判断)
- 既存 src / tests / requirements*.txt / .env / secrets
- 既存 GCP services(giants-* / draft-body-editor Cloud Run Job 自体)
- Cloud Run Job `draft-body-editor` の env / arg(本 ticket は trigger 追加のみ)
- baseballwordpress repo
- WordPress / X / Cloud Run env(既存)
- automation.toml
- **並走 task `bocimjz37`(161 publish-notice GCP)が touching する file 触らない**: `Dockerfile.publish_notice` / `cloudbuild_publish_notice.yaml` / `doc/active/161-deployment-notes.md`

## acceptance

1. Cloud Scheduler `draft-body-editor-trigger` 作成済(`gcloud scheduler jobs describe ...` で state=ENABLED 確認)
2. schedule = `2,12,22,32,42,52 * * * *`(JST 確認)
3. target = Cloud Run Job `draft-body-editor`(invoke URI 確認)
4. 次の :02 / :12 / :22 等の tick で Cloud Run Job execute 発生(Cloud Logging で execution 確認)
5. WSL cron 042 行: **未変更 verify**
6. doc/active/157-deployment-notes.md commit
7. live publish 発生: yes(scheduler enable 後 1 tick で Gemini call + WP PUT)
8. push なし、Claude が後で push

## Hard constraints

- secret 値 / service account credentials の chat / log / commit 完全禁止(masked のみ doc に残す)
- 並走 task `bocimjz37`(161)が touching する file 触らない
- `git add -A` 禁止、stage は **`doc/active/157-deployment-notes.md`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- WSL crontab 042 行 編集 / disable 禁止(本 ticket scope 外、Phase 1e)
- code 触らない(src / tests / Dockerfile / cloudbuild yaml)
- pytest 影響なし
- live publish 発生する可能性 → smoke は scheduler enable まで(1 tick 自動発火後は通常運用に入る)

## Verify

```bash
# Cloud Scheduler 確認
gcloud scheduler jobs describe draft-body-editor-trigger --location=asia-northeast1 --project=baseballsite --format="value(name,schedule,timeZone,state,lastAttemptTime)" 2>&1
# 次 tick 後 Cloud Run Job execution 確認(数 min 待機)
gcloud run jobs executions list --job=draft-body-editor --region=asia-northeast1 --project=baseballsite --limit=3 2>&1 | head -10
# Cloud Logging
gcloud logging read 'resource.type=cloud_scheduler_job AND resource.labels.job_id=draft-body-editor-trigger' --limit=3 --project=baseballsite 2>&1 | head -20
# repo 状態
cd /home/fwns6/code/wordpressyoshilover
git status --short
git diff src/ tests/ requirements.txt 2>&1 | head -3  # 空であるべき
# WSL crontab 不変 verify
crontab -l | grep "draft_body_editor" | head -3
```

## Commit

```bash
git add doc/active/157-deployment-notes.md
git status --short
git commit -m "157 (Phase 1c): Cloud Scheduler trigger for draft-body-editor (2,12,22,32,42,52 * * * * JST、WSL 042 並走維持)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

```
- changed files: doc/active/157-deployment-notes.md(他なし)
- Cloud Scheduler created: draft-body-editor-trigger
- schedule: 2,12,22,32,42,52 * * * * (JST)
- state: ENABLED / DISABLED
- target Cloud Run Job: draft-body-editor invoke URI
- service account used: <masked>
- 次 tick 自動 execute 観測: yes/no(timestamp)
- WSL cron 042 行: 未変更 verify
- src / tests / Dockerfile / yaml: 未変更 verify
- live publish 発生: yes/no(Gemini call + WP PUT 数)
- push: NO
- commit hash: <hash>
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- Cloud Scheduler 作成権限なし → 即停止 + 報告(IAM grant 必要)
- service account が無い → 既存 giants-* SA 確認、なければ新規作成判断 escalate
- target Cloud Run Job 不在 → 156 deploy 状態確認、停止 + 報告
- WSL 042 行 disable が必要に見える → 即停止 + 報告(Phase 1e、別 ticket)

## 完了後の次便

- 158 Secret Manager env(WP/Gemini key)for 042(API key 経路、auth.json は 172 で別系統)
- 159 WSL cron 042 disable(GCP 042 安定 1 日確認後、user 判断)
