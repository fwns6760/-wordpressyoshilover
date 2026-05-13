# INSIGHT-004 — Cloud Run job 化 + Scheduler 設定 runbook

**朝に user が確認 + 実行する手順書**。Claude は本セッション中 **gcloud 系の本番書き込みコマンドを 1 度も実行しない**。

## 前提

- `master` ブランチに本ブランチを merge 済 (or `gcloud builds submit` 時に `--branch` 指定)
- gcloud auth は user 端末で済
- 既存 Scheduler (giants-realtime-trigger / publish-notice-trigger / guarded-publish-trigger 等) は **触らない**

## Step 1: image build

```bash
cd /home/fwns6/code/wordpressyoshilover

gcloud builds submit \
  --config cloudbuild_insight_nightly.yaml \
  --substitutions=_TAG=initial \
  --region=asia-northeast1 \
  --project=baseballsite
```

成功すれば `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:initial` が push される。

## Step 2: Cloud Run job 作成

```bash
gcloud run jobs create insight-nightly \
  --image asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:initial \
  --region asia-northeast1 \
  --project baseballsite \
  --task-timeout 5m \
  --max-retries 1 \
  --memory 512Mi \
  --cpu 1
```

注意:
- 既存 job 名 (`publish-notice` / `guarded-publish` / `repair-fallback` 等) と被らないこと
- 既存 secret は使わない (insight は WP / Gemini / X API を呼ばない)
- volume mount は最初は無しで OK。蓄積が必要になったら GCS bucket か Cloud SQL を別チケットで判断

## Step 3: 手動 1 回試走（本番デプロイ前の verify）

```bash
gcloud run jobs execute insight-nightly \
  --region asia-northeast1 \
  --project baseballsite \
  --wait
```

成功条件:
- exit code 0
- ログに `"status": "ok"` + `"slug"`, `"game_id"`, `"csv_rows_total"` が出る
- ログに「実 HTTP が `https://npb.jp/scores/...`」へ 1-2 回飛んでいる（schedule + box.html）
- robots.txt も 1 回 fetch されている

失敗時 (parser が NPB の実 HTML 構造とズレた等):
1. Cloud Run logs から fetched HTML 例を抜く
2. `src/analysis/insight_schedule.py` の正規表現を実 HTML に合わせて修正
3. test を増やす
4. image rebuild → 再 execute

## Step 4: Scheduler 作成

NPB の試合終了は 22 時前後。**JST 02:00** (= UTC 17:00) に nightly を回す。
これは既存 `giants-realtime-trigger` (17-21 JST) / `publish-notice-trigger` /
`guarded-publish-trigger` などと **時間が被らない**ので衝突なし。

```bash
gcloud scheduler jobs create http insight-nightly-trigger \
  --location=asia-northeast1 \
  --schedule="0 2 * * *" \
  --time-zone="Asia/Tokyo" \
  --uri="https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/insight-nightly:run" \
  --http-method=POST \
  --oauth-service-account-email=$(gcloud iam service-accounts list --filter='displayName:Compute Engine default service account' --format='value(email)') \
  --project=baseballsite
```

検証:

```bash
gcloud scheduler jobs run insight-nightly-trigger --location=asia-northeast1
gcloud run jobs executions list --job=insight-nightly --region=asia-northeast1 --limit=5
```

## Rollback 手順 (insight 系を全停止する場合)

```bash
gcloud scheduler jobs pause insight-nightly-trigger --location=asia-northeast1
gcloud run jobs delete insight-nightly --region=asia-northeast1 --quiet
gcloud artifacts docker images delete \
  asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:initial \
  --quiet
```

既存の publish 系 Scheduler / Cloud Run service には**一切影響しない**設計。

## Step 5 (Optional): 永続ストレージ

最初は ephemeral SQLite で動かし、毎晩 ETL → digest を logs に残す形を観測。
データ蓄積が必要になったら、別チケットで以下を判断:

- GCS bucket に insight.db を毎晩 upload / restore
- Cloud SQL (PostgreSQL) へ移行
- BigQuery (高機能だが有料)

本フェーズでは判断保留。

## 「安全に止める」ためのフラグ

万一 NPB scrape で問題が出た時、`gcloud run jobs update insight-nightly --args="--auto"` で `--live` を外す → cache 限定モードに即時退避。

## 既存運用との完全分離

| 既存 (触らない) | INSIGHT-004 (新規) |
|---|---|
| publish-notice / guarded-publish / repair-fallback 系 Cloud Run job | insight-nightly Cloud Run job |
| giants-realtime / publish-notice-trigger / guarded-publish-trigger 系 Scheduler | insight-nightly-trigger Scheduler |
| `publish-notice` / `guarded-publish` / `external-ping` / `codex-shadow` Artifact Registry image | `insight-nightly` Artifact Registry image |
| WP REST 経由の draft/publish flow | (insight は WP に書かない) |
| Gemini call / X API | (insight は使わない) |

## STOP 条件 (本 runbook 実行中)

- Step 3 で実 HTTP が NPB に飛んだのに `articles_candidates` が空 → 正常範囲内 (試合がない日 / 解析 failure)、まず logs を確認
- Step 4 で Scheduler が既存 job 名と衝突 → 即 abort、名前変更
- WP REST / Gemini / X API への trafic がログに出る → INSIGHT 系から発生しているか確認、もし発生なら即 rollback
- 既存 Scheduler の状態に変化が出る → 即 rollback、Claude に escalate
