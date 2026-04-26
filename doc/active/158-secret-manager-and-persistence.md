# 158 secret-manager-and-persistence(155 Phase 1d、Cloud Run Job env Secret 化 + cursor 永続化)

## meta

- number: 158
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / infra / secret + persistence
- status: **READY**(157 と disjoint 並列可、161 完了済み、172 完了済み)
- priority: P0(WSL cron 042 / 095 disable 解除の前提条件、161 で /data placeholder 残ってる解消)
- lane: A
- created: 2026-04-26
- parent: 155 / 156 / 161 / 172

## 背景

### 161 で残った課題

- Cloud Run Job `publish-notice` の `/data` path が永続化されてない
- 各 execution で fresh cursor bootstrap → 実 publish notice 送れない
- WSL 095 を disable できない

### 042 Cloud Run Job(156)で残った課題

- env vars が plain(`WP_URL=*** WP_APP_PASSWORD=*** GEMINI_API_KEY=***`)
- Cloud Run Console に表示されるリスク、Secret Manager 化必須

## ゴール

1. **env vars を Secret Manager 化**:
   - `WP_URL` / `WP_USER` / `WP_APP_PASSWORD` / `WP_API_BASE`
   - `GEMINI_API_KEY`
   - `MAIL_BRIDGE_SMTP_USERNAME` / `MAIL_BRIDGE_FROM` / `MAIL_BRIDGE_GMAIL_APP_PASSWORD` / `MAIL_BRIDGE_TO` / `PUBLISH_NOTICE_EMAIL_TO`
   - `PUBLISH_NOTICE_EMAIL_ENABLED`(boolean、env でも OK)
   - 既存 Cloud Run Jobs(`draft-body-editor` / `publish-notice`)を Secret Manager 参照に update
2. **publish-notice の cursor / history 永続化**(GCS pattern):
   - GCS bucket 作成: `gs://baseballsite-yoshilover-state/`
   - object: `publish_notice/cursor.txt` / `publish_notice/history.json`
   - Cloud Run Job 起動時に download → 実行 → 終了時に upload
   - Python helper `src/cloud_run_persistence.py` で実装
3. WSL 042 / 095 cron は **並走維持**(本 ticket では disable しない、Phase 1e / 3e で別判断)

## 仕様

### 新 module

- `src/cloud_run_persistence.py`
  - `class GCSStateManager(bucket_name, prefix, project_id)`
    - `download(remote_name, local_path) -> bool`: GCS object → local file、object 不在で False return(初回 bootstrap 許容)
    - `upload(local_path, remote_name) -> None`: local file → GCS object(atomic 上書き)
    - `with_state(remote_name, local_path)`: context manager(download → yield → upload)
  - `class GCSAccessError(RuntimeError)`
  - subprocess `gsutil cp` 経由(gcloud auth と同じ ADC 利用)
- `bin/publish_notice_entrypoint.sh`(新規):
  - 起動時 `GCSStateManager.download` で cursor / history → `/tmp/`
  - `python3 -m src.tools.run_publish_notice_email_dry_run --scan --send --cursor-path /tmp/publish_notice_cursor.txt --history-path /tmp/publish_notice_history.json --queue-path /tmp/publish_notice_queue.jsonl` 実行
  - 終了時 `upload` で `/tmp/` → GCS

### Secret Manager 設定

```bash
# Secret 作成(11 secret)
for secret in wp-url wp-user wp-app-password wp-api-base gemini-api-key \
              mail-bridge-smtp-username mail-bridge-from mail-bridge-gmail-app-password \
              mail-bridge-to publish-notice-email-to publish-notice-email-enabled; do
  gcloud secrets create $secret --replication-policy=automatic --project=baseballsite
  # WSL .env から値取得 + 投入(masked、log に値出さない)
done

# Cloud Run Job env を Secret 参照に update
gcloud run jobs update draft-body-editor \
  --update-secrets="WP_URL=wp-url:latest,WP_USER=wp-user:latest,WP_APP_PASSWORD=wp-app-password:latest,GEMINI_API_KEY=gemini-api-key:latest" \
  --region=asia-northeast1 --project=baseballsite

gcloud run jobs update publish-notice \
  --update-secrets="WP_URL=wp-url:latest,...(全 11 secret)" \
  --region=asia-northeast1 --project=baseballsite
```

### GCS bucket 設定

```bash
gcloud storage buckets create gs://baseballsite-yoshilover-state \
  --location=asia-northeast1 --project=baseballsite \
  --uniform-bucket-level-access
# Cloud Run Job SA に objectAdmin grant
gcloud storage buckets add-iam-policy-binding gs://baseballsite-yoshilover-state \
  --member=serviceAccount:<service-account>@baseballsite.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

### 成果物

- `src/cloud_run_persistence.py`(新規)
- `tests/test_cloud_run_persistence.py`(新規、subprocess mock)
- `bin/publish_notice_entrypoint.sh`(新規、download → run → upload wrapper)
- `Dockerfile.publish_notice` 更新(ENTRYPOINT を新 entry script に切替、必要なら gsutil install)
- `doc/active/158-deployment-notes.md`(Secret Manager + GCS bucket / Cloud Run Job update / smoke 結果)

## 不可触

- WSL crontab 042 / 095 行(disable 禁止、Phase 1e / 3e 別判断)
- 既存 src(`src/tools/run_*.py` 等)の logic 変更禁止(env 名や CLI args は変えない、wrapping のみ)
- 既存 Cloud Run Job 自体の削除 / 再作成: 禁止(update のみ)
- Cloud Run Job `draft-body-editor` の Dockerfile 更新は最小限(env Secret 化のみ、code path 変えない)
- `.env` ファイル 削除 / 編集 禁止(WSL 用に維持、本 ticket は GCP 側のみ)
- baseballwordpress repo
- WordPress / X
- automation.toml
- **並走 task `brjgbrk6e`(157)が touching する file 触らない**: `doc/active/157-deployment-notes.md`(157 が書く予定)
- requirements*.txt(stdlib + 既存 deps + `google-cloud-storage` 追加 OK のみ、他 dep 禁止)
  - もしくは subprocess gsutil で済ませて新 dep 0(推奨)

## acceptance

1. Secret Manager に 11 secret 作成済み verify
2. Cloud Run Jobs `draft-body-editor` / `publish-notice` env を Secret Manager 参照に update verify
3. GCS bucket `baseballsite-yoshilover-state` 作成 + IAM grant verify
4. `src/cloud_run_persistence.py` module + tests
5. `bin/publish_notice_entrypoint.sh` 新規、download → run → upload pattern
6. `Dockerfile.publish_notice` 更新(ENTRYPOINT 切替、gsutil installed verify)
7. Cloud Build 再実行 → Artifact Registry に新 image push
8. Cloud Run Job `publish-notice` を新 image に update
9. 手動 execute → cursor / history が GCS から download → run → upload で persistent verify
10. 2 回目 execute で前回 cursor 引き継ぎ verify(emit 数増えない、または期待通り)
11. WSL 095 lane: **未変更 verify**(disable しない、Phase 3e で別判断)
12. live mail 発生する可能性あり、smoke は 2 回まで(persist verify)
13. push なし、Claude が後で push

## Hard constraints

- secret 値の chat / log / commit / mail への記載 完全禁止(masked のみ doc に残す)
- 並走 task `brjgbrk6e`(157)が touching する file 触らない
- `git add -A` 禁止、stage は **`src/cloud_run_persistence.py` + `tests/test_cloud_run_persistence.py` + `bin/publish_notice_entrypoint.sh` + `Dockerfile.publish_notice` + `doc/active/158-deployment-notes.md`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- WSL crontab 編集 / disable 禁止(Phase 1e / 3e 別)
- `.env` 触らない
- pytest baseline 1395(172 land 後)維持
- 新 dependency は最小限(subprocess + gsutil で済ませて 0 dep が理想)
- Codex CLI 並列利用禁止(172 で land 済 invariant 維持)
- 165 / 168 / 169 / 170 / 171 / 172 で land 済の挙動を一切壊さない

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_cloud_run_persistence.py -v 2>&1 | tail -20
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
# Secret 確認
gcloud secrets list --project=baseballsite --format="table(name)" 2>&1 | head -15
# Cloud Run Job env 確認
gcloud run jobs describe draft-body-editor --region=asia-northeast1 --project=baseballsite --format="value(template.containers[0].env[].valueSource.secretKeyRef.secret)" 2>&1 | head
gcloud run jobs describe publish-notice --region=asia-northeast1 --project=baseballsite --format="value(template.containers[0].env[].valueSource.secretKeyRef.secret)" 2>&1 | head
# GCS bucket 確認
gcloud storage ls gs://baseballsite-yoshilover-state/ 2>&1 | head -5
# WSL crontab 不変
crontab -l | grep -E "draft_body|publish_notice" | head -5
```

## Commit

```bash
git add src/cloud_run_persistence.py tests/test_cloud_run_persistence.py bin/publish_notice_entrypoint.sh Dockerfile.publish_notice doc/active/158-deployment-notes.md
git status --short
git commit -m "158 (Phase 1d): Secret Manager env + GCS persistence (cursor/history download/upload、Cloud Run Jobs update、WSL 042/095 並走維持)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

```
- changed files: <list>
- pytest collect: 1395 → <after>
- pytest pass: 1395 → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash>
- Secret Manager 11 secret 作成: yes/no(secret 名 list、値は絶対 mask)
- Cloud Run Job env Secret 化: draft-body-editor / publish-notice 各 verify
- GCS bucket created: gs://baseballsite-yoshilover-state/
- IAM grant: storage.objectAdmin to <service-account>(masked)
- bin/publish_notice_entrypoint.sh: 新規、download/upload pattern verify
- Dockerfile.publish_notice 更新: ENTRYPOINT 切替 verify、gsutil installed
- 手動 execute(2 回): 1 回目 bootstrap、2 回目 cursor 引き継ぎ verify
- WSL 042 / 095 lane: 未変更 verify
- live mail 発生: yes/no(通数)
- push: NO
- secret 値漏洩 check: なし(grep + log inspection)
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- gcloud secrets / storage / Cloud Run / IAM 権限不足 → 即停止 + 報告(user IAM grant 必要)
- gsutil が container に入らない → ベース image 変更要、別 ticket で判断
- pytest 1395 を割る → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告
- secret 値が log / stdout / commit に漏れる箇所発覚 → 即停止 + 報告
- WSL crontab を改変する必要に見える → 即停止 + 報告(Phase 1e / 3e、user 判断)

## 完了後の次便

- 159 WSL cron 042 disable(Phase 1e、GCP 042 安定 1 日確認後、user judgment)
- Phase 3e 同時に WSL cron 095 disable(GCP publish-notice cursor 永続化 verify 後、user judgment)
- 162 gemini_audit GCP migration(Phase 4)
- 163 quality-monitor / quality-gmail GCP migration(Phase 5)
