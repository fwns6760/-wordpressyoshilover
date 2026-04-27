# 184 ledger integration(Cloud Run Job → Firestore + GCS 学習データ蓄積)

## meta

- number: 184
- owner: Claude Code(設計 / 起票)/ Codex B(実装)
- type: dev / integration / learning data
- status: **CLOSED**
- priority: P0.5(全公開モードで蓄積した data を学習に回す pipeline 完成)
- lane: B
- created: 2026-04-26
- landed_in: `59b2438`
- parent: 168(schema v0)/ 179(FirestoreLedgerWriter + ArtifactUploader)/ 177(codex-shadow Cloud Run Job)/ 160(guarded-publish Cloud Run Job)/ 161(publish-notice Cloud Run Job)

## 背景

179 で `FirestoreLedgerWriter` 本実装 + `ArtifactUploader`(GCS upload)land 済。
ただし **各 Cloud Run Job entrypoint script から呼出未統合** = 学習 data が蓄積されない。

本 ticket で各 entrypoint(bin/*.sh) と runner(src/tools/run_*.py) を ledger.write + uploader.upload に wire up。

## ゴール

各 Cloud Run Job 実行ごとに:
1. **Firestore `repair_ledger` collection** に 168 schema v0 entry 書込み(provider / strict_pass / hash / metrics / error 全部)
2. **GCS `gs://yoshilover-history/repair_artifacts/<date>/<post_id>_<provider>_<run_id>.json`** に before/after 本文 + diff upload
3. publish 成功 / 失敗 / cleanup_failed 等 全 case で ledger entry 残す

## 仕様

### 影響対象

| Cloud Run Job | runner | ledger 書込み追加 |
|---|---|---|
| `draft-body-editor` | `src/tools/run_draft_body_editor_lane.py` | provider="gemini" 各 repair + before/after upload |
| `codex-shadow` | 同上(`--provider codex` で起動) | provider="codex" 各 repair + before/after upload + shadow_only / success(178 env=true 後)|
| `guarded-publish` | `src/tools/run_guarded_publish.py` | publish 成功 / cleanup_failed / hard_stop 全 case ledger 記録 |
| `publish-notice` | `src/tools/run_publish_notice_email_dry_run.py` | mail 送信成否 ledger(別 collection `notice_ledger` でも可) |

### 統合方法

各 runner で:
```python
from src.repair_provider_ledger import FirestoreLedgerWriter, RepairLedgerEntry
from src.cloud_run_persistence import ArtifactUploader

ledger = FirestoreLedgerWriter(project_id="baseballsite", collection="repair_ledger")
uploader = ArtifactUploader(bucket_name="yoshilover-history", prefix="repair_artifacts")

# repair / publish 後に:
artifact_uri = uploader.upload(post_id, provider, run_id, before_body, after_body)
entry = RepairLedgerEntry(...)  # 168 schema v0
entry.artifact_uri = artifact_uri
ledger.write(entry)
```

env で opt-in 制(default off、Cloud Run Job 側で env 設定で有効化):
- `LEDGER_FIRESTORE_ENABLED=true`(default false、local test 時 noop)
- `LEDGER_GCS_ARTIFACT_ENABLED=true`(同上)

### 失敗時 fallback

- Firestore write fail → 既存 JsonlLedgerWriter にも書く(local fallback、container ephemeral だが log 経由で観測可)
- GCS upload fail → log warning、publish 自体は継続(ledger 記録は best-effort)
- ledger 書込み failure で publish 自体止めない

### tests

- mock subprocess(gcloud)で Firestore write / GCS upload 動作 verify
- env opt-in で disabled 時 noop verify
- write fail時 publish 継続 verify
- artifact_uri が ledger entry に正しく記録 verify

## 不可触

- 168 ledger schema v0 不変(field 追加禁止)
- 179 で land 済の `FirestoreLedgerWriter` / `ArtifactUploader` interface 不変(使うだけ)
- 既存 runner の core logic(repair / publish 判定 / WP REST 操作)不変、ledger 書込み追加のみ
- Cloud Run Job env 直接編集禁止(本 ticket は code のみ、env 設定は別 commit)
- WSL crontab(全行)
- 165 / 170 / 171 / 172 / 178 等で land 済の挙動を一切壊さない
- automation.toml / .env / secrets / Cloud Run / Scheduler / Storage
- baseballwordpress repo
- WordPress / X
- requirements*.txt 触らない(google-cloud-firestore は subprocess gcloud 経由なので不要)
- 並走 task touching file 触らない:
  - 182 v2 / 183(`src/guarded_publish_runner.py` / `src/guarded_publish_evaluator.py` / 関連 tests)

## acceptance

1. ✓ 4 runner(draft_body_editor_lane / guarded_publish / codex shadow / publish_notice_email_dry_run)に ledger 統合
2. ✓ env `LEDGER_FIRESTORE_ENABLED` / `LEDGER_GCS_ARTIFACT_ENABLED` 切替
3. ✓ Firestore write fail / GCS upload fail で publish 継続 verify
4. ✓ artifact_uri が ledger entry に記録 verify
5. ✓ pytest baseline + 新 tests pass、pre-existing fail 0 維持
6. ✓ live publish / Cloud Run deploy / push: 全て NO(env 切替は別 commit で deploy)

## Hard constraints

- 並走 task touching file 触らない(182 v2 / 183 の src/guarded_publish_*)
- `git add -A` 禁止、stage は影響 file のみ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 維持、pre-existing fail 0 維持
- 新 dependency 禁止(subprocess gcloud + 既存 deps)
- env default は **false**(safety、env 設定で有効化)
- ledger write fail で publish 止めない(best-effort、log warning)
- 168 schema v0 不変
- 既存 runner core logic 不変

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_run_draft_body_editor_lane.py tests/test_run_guarded_publish.py tests/test_run_publish_notice_email_dry_run.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
```

## Commit

```bash
git add <影響 src + tests を明示>
git status --short
git commit -m "184: ledger integration (4 runner で Firestore + GCS upload 呼出統合、env opt-in、学習 data 蓄積開始)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

doc § 完了報告 形式厳守、env 切替 + ledger entry sample(masked)+ artifact GCS path sample 含む。

## stop 条件

- 並走 task scope と衝突 → 即停止 + 報告
- pytest baseline を割る → 即停止 + 報告
- runner core logic 大幅変更が必要 → 即停止 + 報告
- 168 schema 変更が必要 → 即停止 + 報告

## 完了後の次便

- 184b deploy: Cloud Run Job env で `LEDGER_FIRESTORE_ENABLED=true` / `LEDGER_GCS_ARTIFACT_ENABLED=true` 有効化(別 commit、Codex に gcloud で update)
- 184b 後の数日 observation で Firestore に data 蓄積 verify
- 蓄積 data を 048 formatter で aggregate(別 ticket、将来)
