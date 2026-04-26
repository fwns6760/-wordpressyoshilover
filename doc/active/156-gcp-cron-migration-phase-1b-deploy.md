# 156 gcp-cron-migration phase 1b: 042 Cloud Run Job deploy + 手動 smoke

## meta

- number: 156
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / infra / cron migration
- status: **READY**(155-1a `88391d0` push 済、即 fire 可)
- priority: P0.5
- lane: A
- created: 2026-04-26
- parent: 155 / 155-1a

## 背景

155-1a で Dockerfile + Cloud Build yaml は repo にあるが、まだ image push してないし Cloud Run Job も作ってない。Phase 1b では:

1. `gcloud builds submit` で image を Artifact Registry に push
2. Cloud Run Job 作成(env / secret は仮値、Phase 1d で Secret Manager 化)
3. `gcloud run jobs execute` で 1 回手動 trigger
4. Cloud Logging に正常 output 確認

## ゴール

`draft-body-editor:<commit-hash>` image が Artifact Registry に存在し、Cloud Run Job が作成済みで、手動 trigger 1 回 success 確認できる状態にする。

## 前提

- GCP project: `baseballsite`(155-1a deployment notes 参照)
- region: `asia-northeast1`
- Artifact Registry repo: `yoshilover`(無ければ作成)
- service account: 既存 giants-* で使ってる SA を流用 or 専用 SA 作成
- env: 仮で `WP_API_URL` / `WP_API_USER` / `WP_API_PASSWORD` / `GEMINI_API_KEY` を Cloud Run Job env として設定(Phase 1d で Secret Manager 化)

## 仕様

### Phase 1b 手順

1. **Artifact Registry repo 確認 / 作成**:
   ```bash
   gcloud artifacts repositories describe yoshilover --location=asia-northeast1 --project=baseballsite
   # 無ければ:
   gcloud artifacts repositories create yoshilover --repository-format=docker --location=asia-northeast1 --project=baseballsite
   ```

2. **Cloud Build で image push**:
   ```bash
   cd /home/fwns6/code/wordpressyoshilover
   gcloud builds submit \
     --project=baseballsite \
     --region=asia-northeast1 \
     --config=cloudbuild_draft_body_editor.yaml \
     --substitutions=_PROJECT_ID=baseballsite,_REGION=asia-northeast1,_IMAGE_NAME=draft-body-editor,_TAG=$(git rev-parse --short HEAD) \
     .
   ```

3. **Cloud Run Job 作成**(env は WSL の `.env` から読み出し、Codex が prompt で受け取った値を使う):
   ```bash
   IMAGE="asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/draft-body-editor:$(git -C /home/fwns6/code/wordpressyoshilover rev-parse --short HEAD)"
   gcloud run jobs create draft-body-editor \
     --image="$IMAGE" \
     --region=asia-northeast1 \
     --project=baseballsite \
     --task-timeout=600s \
     --max-retries=1 \
     --set-env-vars="WP_API_URL=...,WP_API_USER=...,WP_API_PASSWORD=...,GEMINI_API_KEY=..." \
     --args="--max-posts,3"
   ```

4. **手動 trigger smoke**:
   ```bash
   gcloud run jobs execute draft-body-editor --region=asia-northeast1 --project=baseballsite --wait
   ```

5. **Cloud Logging で output 確認**:
   ```bash
   gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=draft-body-editor' --limit=20 --project=baseballsite --format=json
   ```

### 成果物

- Cloud Run Job `draft-body-editor` が `baseballsite` project に作成済み
- 1 回手動 execute success(exit 0)
- Cloud Logging に WSL cron 同等の JSON 出力が残る
- `doc/active/156-deployment-notes.md`(実 deploy command / 環境変数の masked snapshot / smoke 結果)
- 既存 src / tests / .env / WSL crontab / 155-1a 系 file 一切変更なし

## 不可触

- WSL crontab 042 行(並走維持、disable は 1e で)
- `Dockerfile.draft_body_editor` / `cloudbuild_draft_body_editor.yaml`(155-1a で fix 済、本 ticket では touch しない)
- 既存 GCP services(giants-* / Cloud Run / Cloud Scheduler)
- `src/` / `tests/` / `requirements*.txt` / `.env` の中身改変
- Codex Desktop automation
- baseballwordpress repo
- WordPress / X / 既存 RUN_DRAFT_ONLY

## acceptance

1. Artifact Registry に image `draft-body-editor:<short-hash>` 存在
2. Cloud Run Job `draft-body-editor` 作成済み
3. `gcloud run jobs execute --wait` が exit 0
4. Cloud Logging に JSON 出力(`candidates` / `put_ok` / `aggregate_counts` など)あり
5. WSL cron 042 は **並走稼働中**(本 ticket は disable しない)
6. live publish / WP write は **発生する可能性あり**(live mode で run、Gemini Flash + WP REST 実呼び)→ Phase 1b は smoke 1 回のみ、繰り返し execute しない
7. doc/active/156-deployment-notes.md commit
8. push なし、Claude が後で push

## Hard constraints

- **並走 task `b0vi046ql`(165 resilience)が touching する file は触らない**: `src/tools/draft_body_editor.py` / `src/wp_client.py` / `tests/test_draft_body_editor.py` / `tests/test_wp_client.py`
- `git add -A` 禁止、stage は **`doc/active/156-deployment-notes.md`** だけ(本 ticket は doc + GCP infra 操作、code 変更なし)
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- Cloud Scheduler 設定 / Secret Manager 設定: 1c / 1d scope
- pytest 影響なし(code 触らない、tests も触らない)

## Verify

```bash
# Artifact Registry image 確認
gcloud artifacts docker images list asia-northeast1-docker.pkg.dev/baseballsite/yoshilover --include-tags 2>&1 | head -5
# Cloud Run Job 確認
gcloud run jobs describe draft-body-editor --region=asia-northeast1 --project=baseballsite --format="value(name,latestSucceededExecution)" 2>&1
# Cloud Logging 確認
gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=draft-body-editor' --limit=5 --project=baseballsite 2>&1 | head -20
# repo 状態 verify(code に触れていないこと)
cd /home/fwns6/code/wordpressyoshilover
git status --short  # 156-deployment-notes.md だけ ?? (or M after add)
git diff src/ tests/ requirements.txt 2>&1 | head -3  # 空であるべき
```

## Commit

```bash
git add doc/active/156-deployment-notes.md
git status --short
git commit -m "156 (Phase 1b): 042 Cloud Run Job deploy + 手動 smoke success (image push, job create, execute pass)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告(必須形式)

```
- changed files: doc/active/156-deployment-notes.md(他なし)
- Artifact Registry image tag: draft-body-editor:<hash>
- Cloud Run Job created: draft-body-editor
- gcloud run jobs execute exit code: 0/N
- Cloud Logging output excerpt: <JSON抜粋>
- env vars set: <masked list, no secret>
- WSL cron 042 行: 未変更 verify
- src / tests / requirements*: 未変更 verify
- live publish 発生: yes/no(Gemini call / WP PUT 数)
- push: NO
- commit hash: <hash>
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- gcloud auth が無い / project access fail → 即停止 + 報告(user op で auth 必要)
- Artifact Registry repo 作成権限なし → 即停止 + 報告
- Cloud Build fail(image build error)→ 即停止 + 報告(155-1a Dockerfile 見直し)
- Cloud Run Job execute exit non-zero → log 添えて停止 + 報告(env 不足 / source code bug を切り分け)
- Gemini / WP API key が空 / 不正 → 即停止 + 報告(.env 確認 user op)

## 完了後の次便

Phase 1c(157)= Cloud Scheduler trigger 追加(`2,12,22,32,42,52 * * * *`)起票 + fire 判断。
