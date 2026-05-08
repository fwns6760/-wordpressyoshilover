# 303 - フロント rich body / nomotoke-style enrichment 復元用 ticket

| 項目 | 値 |
|---|---|
| **ticket #** | 303 |
| **status** | DONE_REVERSIBLE |
| **owner** | Claude Code |
| **created** | 2026-05-08 |
| **scope** | 2026-05-07 〜 2026-05-08 にかけて入れた本文装飾 / RSS pipeline enrichment の roll-back ガイド |
| **risk** | low (全て純コード変更、env / Secret / Scheduler 変更ゼロ) |

## 背景

今日 1 セッションで以下を実施:

1. 手動投入アプリ (manual-intake-service) の本文を 8〜10 倍の情報密度に拡張
2. RSS 自動 pipeline (yoshilover-fetcher) にも同等の enrichment を適用 (Phase 3)
3. 短文記事の fallback path も装飾されるよう修正 (FALLBACK-SHELL-001)
4. 監査で見つけた 5 件の bug 修正 (audit fixes A/B/D/E)

何か問題が出たら即 revert できるよう、commit 一覧と revert コマンドをここに記録する。

---

## 本日の commit 一覧 (新しい順)

### 自分が入れた commit (rollback target)

| ハッシュ | サマリ |
|---|---|
| `0bf8900` | NOMOTOKE-INTAKE-FALLBACK-SHELL-001 — 短文記事 fallback も装飾入る |
| `2654e5a` | NOMOTOKE-INTAKE-AUTO-ROUTE-001 — auto article_type → nomotoke 自動振り分け |
| `adb5b15` | NOMOTOKE-INTAKE-AUDIT-FIXES-001 — 監査 A+B+D+E 修正 |
| `c52437c` | NOMOTOKE-INTAKE-TOP-CTA-001 — 冒頭 CTA 追加 (4 か所構成) |
| `e5208be` | NOMOTOKE-INTAKE-NOMOTOKE-MATCH-001 — X 投稿埋め込み + シェアボタン + emoji 軽減 |
| `50bd58a` | NOMOTOKE-INTAKE-EMOJI-DECORATE-001 — emoji 装飾 |
| `3d24953` | NOMOTOKE-INTAKE-DEDUP-001 — 重複ブロック削減 (22→16) |
| `28f36e9` | NOMOTOKE-INTAKE-N1234-001 — AI badge + JSON-LD + 当日他試合 + シリーズ |
| `8bce3d6` | NOMOTOKE-INTAKE-READER-UX-001 — ToC + 読了時間 + 選手名リンク + chip |
| `06dd58c` | NOMOTOKE-INTAKE-FRESH-INFO-001 — 選手成績 + 著者他記事 + 公示 + コメ数 + roster 119 名 |
| `cf9104c` | NOMOTOKE-CTA-RESTORE-001 — オレンジ CTA × 3 か所 |
| `c4d47b3` | NOMOTOKE-INTAKE-NEXT-GAME-001 / STANDINGS-001 / ROSTER-PHASE-2 — G4 + C4 + RSS rollout |
| `a90adf4` | NOMOTOKE-INTAKE-JSONLD-META-001 / NPB-OFFICIAL-001 — JSON-LD 著者・掲載日 + NPB公式 link |
| `e669c60` | NOMOTOKE-INTAKE-LINEUP-001 — Yahoo Sportsnavi スタメン |
| `cd90149` | NOMOTOKE-INTAKE-WP-CROSSLINK-001 — 関連記事 / 直近 / 対戦成績 |
| `43e56cd` | NOMOTOKE-INTAKE-ROSTER-ASIDE-001 — 関連選手・首脳陣 名札 |
| `0a2080d` | NOMOTOKE-INTAKE-BODY-EXCERPT-001 — 本文抜粋 (240字) |
| `fb79d02` | NOMOTOKE-INTAKE-MANUAL-FACTS-001 — operator 任意 fields + 監督 allowlist 拡張 + YouTube 正規化 |
| `17db97e` | NOMOTOKE-INTAKE-POSTGAME-001 / HERO-001 — Yahoo postgame + hero figure |
| `b55aff9` | NOMOTOKE-INTAKE-TEMPLATE-001 — article_type → nomotoke renderer 配線 |
| `927ac2c` | NOMOTOKE-RSS-PIPELINE-ENRICHMENT-001 — RSS pipeline 全面適用 |

### 並走で入った別 commit (touch しない)

別セッション owner の作業:

- `44f4ed9` fetcher: RUN_DRAFT_ONLY=0
- `55ae3c7` NOMOTOKE-FETCHER-BYPASS-002
- `86a21a6` NOMOTOKE-BURST-THRESHOLD-ENV-001
- `b2b3678` NOMOTOKE-MORNING-RELIABILITY-001
- `b432801` NOMOTOKE-AUTO-PUBLISH-001
- `bd35498` NOMOTOKE-DEDUP-BODY-MARKER-001
- `216d1d7` NOMOTOKE-P0-AUDIT-FIX-001
- `54d3eec` NOMOTOKE-FRONTIER-AUDIT-FIX-001
- `84e48cd` NOMOTOKE-TITLE-POLISH-DEDUP-ORDER-FIX
- `5687649` NOMOTOKE-EYECATCH-AUTO-004
- `939b0c3` NOMOTOKE-EYECATCH-AUTO-003
- `450249e` NOMOTOKE-EYECATCH-AUTO-002
- `eb38006` NOMOTOKE-EYECATCH-AUTO-001
- `5a253a2` NOMOTOKE-TITLE-SEO-POLISH-001
- `2076920` NOMOTOKE-PUBLISH-NOTICE-MANUAL-FLIP-FIX
- `74b0cec` NOMOTOKE-MAIL-MINIMAL-BODY-001
- `6349995` NOMOTOKE-MAIL-SUBJECT-DETAIL-001

---

## 本番デプロイ状態 (2026-05-08 時点)

| service | revision | image |
|---|---|---|
| **manual-intake-service** | `manual-intake-service-00039-gtb` | `manual-intake-service:44f4ed9` |
| **yoshilover-fetcher** | `yoshilover-fetcher-00250-472` | `yoshilover-fetcher:44f4ed9` |
| **publish-notice / guarded-publish** | (touched してない、既存運用) | — |

両 service とも `--to-latest` (常に最新 revision に traffic 100%)。

---

## 完全 rollback (2026-05-07 朝の状態に戻す)

### 1. 手前の安全 revision を選ぶ

```bash
# 一覧
gcloud run revisions list --service=manual-intake-service \
  --project=baseballsite --region=asia-northeast1 \
  --filter="metadata.creationTimestamp<2026-05-07T00:00:00Z" \
  --format='table(name.basename(),metadata.creationTimestamp,spec.containers[0].image.basename())' --limit=5

gcloud run revisions list --service=yoshilover-fetcher \
  --project=baseballsite --region=asia-northeast1 \
  --filter="metadata.creationTimestamp<2026-05-07T00:00:00Z" \
  --format='table(name.basename(),metadata.creationTimestamp,spec.containers[0].image.basename())' --limit=5
```

### 2. traffic を旧 revision に向ける

```bash
# 例 (実際の revision name に置き換える)
gcloud run services update-traffic manual-intake-service \
  --project=baseballsite --region=asia-northeast1 \
  --to-revisions=manual-intake-service-00010-XXX=100

gcloud run services update-traffic yoshilover-fetcher \
  --project=baseballsite --region=asia-northeast1 \
  --to-revisions=yoshilover-fetcher-00200-XXX=100
```

これで本番は瞬時に旧コードに戻る。git 上の commit はそのまま残る (履歴破壊しない)。

---

## 部分 rollback (特定の問題機能だけ無効化)

例: 「fallback shell が壊れた、装飾は他の path だけ残したい」

```bash
git revert 0bf8900   # FALLBACK-SHELL-001 のみ取り消し

# rebuild + redeploy
IMAGE_TAG=$(git rev-parse --short HEAD)
gcloud builds submit --project=baseballsite \
  --config=cloudbuild_manual_intake_service.yaml \
  --substitutions=_TAG=$IMAGE_TAG \
  --gcs-source-staging-dir=gs://baseballsite_cloudbuild/source

gcloud run services update manual-intake-service \
  --project=baseballsite --region=asia-northeast1 \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/manual-intake-service:$IMAGE_TAG
```

`git revert` は元コミットを打ち消す逆コミットを作るので **履歴は壊れない**。複数取り消したい場合は `git revert <hash1> <hash2> ...` で順次。

---

## 個別問題ごとの最小 revert 表

| 起こり得る症状 | revert 対象 |
|---|---|
| 本文が長すぎ / モバイル重い | `0bf8900` `06dd58c` `8bce3d6` (装飾追加分を順次) |
| 短文記事が壊れた (再帰的に) | `0bf8900` (FALLBACK-SHELL-001) |
| auto routing が変な分類した | `2654e5a` (AUTO-ROUTE-001) |
| シェアボタンが反応しない / 見えない | `e5208be` (NOMOTOKE-MATCH-001) — script タグ周り |
| emoji が多すぎる / うるさい | `50bd58a` (EMOJI-DECORATE-001) |
| 名札が画面汚い | `43e56cd` (ROSTER-ASIDE-001) |
| Yahoo box score 取得が遅い / fail | `17db97e` (POSTGAME-001) |
| RSS 自動投稿に装飾入って見栄え悪化 | `927ac2c` (RSS-PIPELINE-ENRICHMENT-001) |
| すべてやめたい (出来たての朝に戻す) | 上記 21 commit を全て revert か、本番 revision を 5/7 朝のものに traffic 戻し |

---

## 復元時のチェックリスト

1. revert / traffic 戻し後、3 分以内に dry-run smoke test
   ```bash
   curl -sS -X POST "https://manual-intake-service-487178857517.asia-northeast1.run.app/manual-intake" \
     -H "Content-Type: application/json" \
     -d '{"url":"https://hochi.news/articles/test.html","mode":"dry-run","article_type":"auto"}'
   ```
2. `ok: true` が返ること
3. WP REST で直近 draft 取得し、body 構造を確認
4. 翌朝 5:30 の `giants-morning-catchup` が成功するか logs で確認

---

## 連絡先 / 履歴

- 全 commit は `git log --grep='NOMOTOKE-INTAKE\|NOMOTOKE-CTA-RESTORE\|RSS-PIPELINE-ENRICHMENT'` で再確認可能
- 各 commit message に「Constraints upheld」が書いてあり、env / Secret 変更ゼロ・¥0 を担保
- live test post_id 65033 は私が削除済 (garbage 残らず)
- 検証用 post_id 65041 は draft 残り (必要なら user 削除)

---

## 補足

- 今日の commit はすべて `git push origin master` 反映済
- `--to-latest` 設定なので、新 deploy するだけで自動的に traffic が乗る
- 旧 revision は 6 ヶ月間自動で保持される (Google Cloud デフォルト) → roll-back 余裕あり
