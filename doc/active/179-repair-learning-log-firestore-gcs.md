# 179 repair-learning-log-firestore-gcs(option A: yoshilover-history GCS + Firestore ledger)

## meta

- number: 179
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / ledger / persistence / learning infra
- status: **READY**(168 + 158 land 後、即 fire 可、160/177 と disjoint)
- priority: P0(GCP 修復学習仕組みの本実装、038 ledger system の GCP bridge)
- lane: B
- created: 2026-04-26
- parent: 168 / 158 / 038(baseballwordpress quality ledger)/ 040 / 048 / ChatGPT D1

## 背景

GCP 移行で 038 ledger system(local file `docs/handoff/ledger/<date>.jsonl`)が壊れる。
Cloud Run Job は ephemeral container、local file 書き込み不可。

168 で repair_provider_ledger schema v0 + JsonlLedgerWriter + FirestoreLedgerWriter **stub** は land 済。
本 ticket で Firestore writer **本実装** + GCS artifact upload を追加し、修復学習 loop の log を GCP 永続化する。

## ゴール

修復ごとに以下を保存:
1. **GCS** `gs://yoshilover-history/repair_artifacts/<date>/<post_id>_<provider>_<run_id>.json` に before/after 本文 + diff
2. **Firestore** `repair_ledger` collection に 168 schema v0 entry(provider/strict_pass/hash 等)
3. ledger entry の `artifact_uri` field に GCS path 記録(168 schema v0 既定)

これで 048 formatter / 040 playbook / 036 prompt 改善 loop が GCP-side data から動く。

## 仕様

### 新規 / 拡張

#### A. `src/repair_provider_ledger.py` 拡張

- `FirestoreLedgerWriter`(168 で stub class)を **本実装**:
  - `__init__(project_id, collection_name="repair_ledger")`
  - `write(entry: RepairLedgerEntry) -> None`: Firestore に document add
    - subprocess `gcloud firestore documents create ...` で実装(google-cloud-firestore Python SDK 使えるなら使う、新 dep 追加 OK)
    - もしくは `google-cloud-firestore` SDK 直叩き
  - `with_lock(idempotency_key)` context manager(Firestore transaction で lock)
  - `LedgerWriteError` 既存 raise を維持
- 既存 `JsonlLedgerWriter` の挙動は不変(local fallback 用)

#### B. `src/cloud_run_persistence.py` 拡張(158 で land 済 module)

- `class ArtifactUploader(bucket_name="yoshilover-history", prefix="repair_artifacts")`
  - `upload(post_id, provider, run_id, before_body, after_body, extra_meta=None) -> str`:
    - JSON construct: `{"post_id": ..., "provider": ..., "before_body": ..., "after_body": ..., "diff_summary": ...}`
    - 一時 file → `gcloud storage cp` で GCS upload
    - return: `gs://yoshilover-history/repair_artifacts/<date>/<post_id>_<provider>_<run_id>.json`
  - `compute_diff_summary(before, after) -> dict`: line count diff / char delta / added_keywords / removed_keywords

#### C. dependency

- `google-cloud-firestore`(必要なら追加 OK、ただし image 軽量化のため subprocess gcloud 経由なら避ける)
- requirements.txt 追加可、ただし最小限

### 統合は別 ticket(本 ticket scope 外)

- 042 / publish-notice / Codex shadow Cloud Run Job entry script から呼び出す統合は **180 別 ticket**(本 ticket は library 実装まで)
- 本 ticket land 後、180 で各 entrypoint script から ledger.write() + uploader.upload() 呼ぶ
- 並走 task `b3ngiu1an`(160)/ `b200f9azk`(177)が touching する entry script に **絶対触らない**(disjoint scope 維持)

## 不可触

- WSL crontab(全行)
- 既存 cron 時刻
- 既存 src の挙動変更:
  - 168 ledger schema v0 不変
  - 168 JsonlLedgerWriter / dataclass 不変
  - 170 / 171 / 172 controller logic 不変
  - 165 retry/backoff 不変
- 既存 GCP services / Cloud Run Jobs / Secret Manager / GCS 既存 bucket(yoshilover-history は read 可、新 prefix 追加のみ)
- automation.toml / .env / WordPress / X
- baseballwordpress repo
- 並走 task touching file 触らない:
  - `b3ngiu1an`(160): `Dockerfile.guarded_publish` / `bin/guarded_publish_entrypoint.sh` / `cloudbuild_guarded_publish.yaml` / `doc/active/160-deployment-notes.md`
  - `b200f9azk`(177): `Dockerfile.codex_shadow` / `cloudbuild_codex_shadow.yaml` / `doc/active/177-deployment-notes.md`
- `bin/*entrypoint.sh` 全部触らない(180 で統合)
- 180 の統合作業は本 ticket scope 外

## acceptance

1. `src/repair_provider_ledger.py` の `FirestoreLedgerWriter` 本実装(stub から実 connection に置換)
2. `src/cloud_run_persistence.py` に `ArtifactUploader` class 追加
3. `tests/test_repair_provider_ledger.py` で Firestore writer mock test:
   - write 成功 → document created
   - duplicate idempotency_key → `LedgerLockError`(transaction lock)
   - Firestore connection fail → `LedgerWriteError`
4. `tests/test_cloud_run_persistence.py` で ArtifactUploader mock test:
   - upload 成功 → GCS path return verify
   - subprocess fail → exception raise
   - diff_summary 計算 verify
5. pytest baseline 1404(167 v2 land 後)+ 新 tests
6. 既存挙動破壊なし(JsonlLedgerWriter / 既存 168 stub の interface 維持)
7. **本 ticket では Firestore に実 write しない**(test mock のみ、実 write は 180 で統合 + smoke)
8. live publish / WP write / Cloud Run deploy / push: 全て NO
9. 並走 task scope と衝突なし

## Hard constraints

- 並走 task touching file 触らない
- `git add -A` 禁止、stage は **`src/repair_provider_ledger.py` + `src/cloud_run_persistence.py` + `tests/test_repair_provider_ledger.py` + `tests/test_cloud_run_persistence.py`**(必要なら `requirements.txt` 1 行追加)だけ
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 1404 維持、pre-existing fail 0 維持
- 新 dependency 追加は最小限(`google-cloud-firestore` のみ許容、他禁止)
- 168 ledger schema 変更禁止(v0 fix)
- subprocess test では `subprocess.run` を mock、実 gcloud / Firestore 起動禁止
- 既存 GCS bucket `gs://yoshilover-history/` を read-only で参照(新 prefix `repair_artifacts/` 追加のみ、既存 `rss_history.json` には絶対触らない)

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_repair_provider_ledger.py tests/test_cloud_run_persistence.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
```

## Commit

```bash
git add src/repair_provider_ledger.py src/cloud_run_persistence.py tests/test_repair_provider_ledger.py tests/test_cloud_run_persistence.py
# requirements.txt 触ったら追加
git status --short
git commit -m "179: repair learning log infrastructure (FirestoreLedgerWriter 本実装 + ArtifactUploader 追加、yoshilover-history/repair_artifacts/ + repair_ledger collection)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

```
- changed files: <list>
- pytest collect: 1404 → <after>
- pytest pass: 1404 → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash>
- FirestoreLedgerWriter 本実装: yes(subprocess or SDK)
- ArtifactUploader 実装: yes
- new dependency 追加: yes/no(google-cloud-firestore)
- 168 schema v0 不変 verify: yes
- 並走 task scope 衝突: なし
- WP write / live API call / Cloud Run deploy / push: 全て NO
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- google-cloud-firestore install で大幅 dep 増(他 lib 引っ張る)→ 即停止 + 報告(subprocess gcloud 経由検討)
- pytest 1404 を割る → 即停止 + 報告
- write scope 外 / 並走 task scope と衝突 → 即停止 + 報告
- 168 schema 変更が必要 → 即停止 + 報告(v0 fix)

## 完了後の次便

- **180 ledger-integration**: 各 Cloud Run Job entrypoint(`bin/codex_shadow_entrypoint.sh` / `bin/guarded_publish_entrypoint.sh` / `bin/publish_notice_entrypoint.sh`)から ledger.write() + uploader.upload() 呼出統合
- **181 048-formatter-firestore-aware**: 048 formatter を Firestore query で動作化
- **182 038-bridge-sync**(任意): GCP Firestore ledger を local 038 ledger に定期 sync(既存 baseballwordpress 運用と統合する場合)
