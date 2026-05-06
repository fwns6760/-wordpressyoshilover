# Lane 7: Cloud Run cost guard 設計 (doc-only)

作成日: 2026-05-06
作成者: Claude Code 直接 (session-level lock 解除中)
スコープ: doc-only (deploy / env flip / config 変更なし)

## 1. 現状 snapshot (2026-05-06 取得)

### 1-1. Cloud Run services / jobs

| service/job | type | CPU | memory | timeoutSeconds | maxRetries / parallelism | maxScale |
|---|---|---|---|---|---|---|
| `yoshilover-fetcher` | service | 1 | 1Gi | 300 | (request-driven) | **1** (fan-out 防止) |
| `publish-notice` | job | 1 | 512Mi | **300** (今朝 900→300 緊急対応) | maxRetries=**0** (今朝 1→0) | parallelism=1 |
| `guarded-publish` | job | 1 | **2Gi** | 600 | maxRetries=1 | parallelism=1 |
| `draft-body-editor` | job | 1 | 512Mi | 600 | maxRetries=1 | parallelism=1 |
| `codex-shadow` | job | 1 | 512Mi | 600 | maxRetries=0 | parallelism=1 |

### 1-2. fetcher service 補足
- startup-cpu-boost=true (cold start 高速化、cost 影響軽微)
- env vars 97 個 (各種 flag 累積)
- maxScale=1 で同時実行ゼロ

### 1-3. Scheduler */5 cycle
- `giants-realtime-trigger` (fetcher /run): `*/5 * * * *` ENABLED
- `publish-notice-trigger`: `*/5 * * * *` ENABLED
- `guarded-publish-trigger`: `*/5 * * * *` ENABLED
- `draft-body-editor-trigger`: `2,12,22,32,42,52 * * * *` (10min 間隔、5min offset)
- `codex-shadow-trigger`: PAUSED ✓ (cost 節約済)
- `yoshilover-fetcher-job` (旧 monolith): PAUSED ✓

### 1-4. 過去 24h コスト相関データ
- fetcher 504 (300s timeout 到達 GCP scheduler request): **24 件**
- publish-notice timeout 到達 (900s 制限時代): **100 件** (今朝の incident、緊急処置で停止)

## 2. cost 暴発リスクポイント

### 2-1. publish-notice timeout chain (今朝の incident、回避済)
- root: scan() 内 direct + review/diagnostic phase serial → 96 MiB `guarded_publish_history.jsonl` scan で 900s 到達 → 全 mail 巻き込み停止
- 緊急対応: `PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=0` / timeout=300 / maxRetries=0 / RUNNING cancel
- 恒久対応: P0 `ENABLE_PUBLISH_NOTICE_TWO_PHASE` (commit `bf29bcc`、本日 deploy 予定)

### 2-2. fetcher 504 chronic noise (24/24h 件)
- root: Gemini strict retry 3 attempts × 90s = 270s/candidate、service timeout 300s ぎりぎり
- cost 影響: 504 時の Gemini call は cancel 済 (実 token 消費は途中まで)、scheduler retry policy で重複 fire ある
- 対応案 (今は HOLD):
  - timeout 300s → 360s (1 candidate strict 全 fail でも margin)
  - リスク: */5 cycle と重なる、maxScale=1 で重複は防げる
  - 別案: GEMINI_STRICT_MAX_ATTEMPTS=3 → 2 (270s → 180s)、ただし draft 品質低下 risk

### 2-3. guarded-publish 2Gi memory (継続要)
- 96 MiB `guarded_publish_history.jsonl` の load + scan + cleanup_log 書き込みで heap 使用
- 1Gi に削減すると OOM risk (Lane 6 history rotation 後に再検討可)
- 当面 2Gi 継続で OK

### 2-4. draft-body-editor 10min 間隔 / codex-shadow PAUSED
- draft-body-editor: 既存通り 10min cycle で OK、cost 比較的軽い
- codex-shadow: PAUSED 維持 (resume すると Gemini cost 増、明日 P2 整理便で扱う)

## 3. max runtime / retry / overlap guard 案

### 3-1. max runtime guard (job-level)
| job | 現 timeout | 推奨 (P0 後) | 備考 |
|---|---|---|---|
| publish-notice | 300s | **300s 維持** | two-phase で direct phase は短く完走、review phase が timeout しても direct は安全 |
| guarded-publish | 600s | **600s 維持** | freshness check + WP REST + ledger 書き込みで 600s 必要 |
| draft-body-editor | 600s | **600s 維持** | Gemini 1-2 call + WP REST PUT |
| codex-shadow | 600s | (PAUSED) | resume 時に再評価 |

### 3-2. retry guard (job-level)
| job | 現 maxRetries | 推奨 | 備考 |
|---|---|---|---|
| publish-notice | 0 (今朝変更) | **0 維持** | 失敗 cycle は次 trigger で recover、retry で重複 mail risk あった |
| guarded-publish | 1 | **1 維持** | 一時的 WP REST hiccup の自動 recover 用 |
| draft-body-editor | 1 | **1 維持** | 同上 |

### 3-3. overlap guard (Scheduler-level)
- Scheduler */5 trigger で前 cycle がまだ走っている時、Cloud Run job は parallelism=1 で重複起動を防ぐ ✓
- ただし scheduler 側は trigger を発火し続けるので、queue が溜まる risk あり
- 対応: scheduler の `attemptDeadline` を timeout より少し長く設定 (現状未確認、別途調査)

### 3-4. service-level (fetcher)
- maxScale=1 維持 (fan-out 防止、cost 節約) ✓
- startup-cpu-boost=true 維持 (cold start 軽減、cost 影響軽微)
- timeout 300s で 504 24/24h 出るが、fetcher 自身 lock + Scheduler retry で recover 中

## 4. 推奨アクション

### 4-1. 即適用なし (今日 deploy 範囲外)
- 全 job/service の現設定を **当面維持**
- P0 two-phase deploy で publish-notice timeout chain は解消見込み

### 4-2. 後日検討 (別 ticket)
- fetcher timeout 300s → 360s 緩和 (Lane 7 別便で再評価)
- `guarded_publish_history.jsonl` rotation (Lane 6 設計、本日 doc-only)
- Gemini cost 削減 (cache_miss_breaker tuning は theme1 commit 164f5d5 で完了済)

### 4-3. 監視強化 (cost guard alarm 案)
- Cloud Monitoring で各 job の monthly execution-second / billable-time alarm
- timeout 到達率 > 5% で alert
- まとめ: 今朝の publish-notice 100/24h timeout は alert 対象、現在は disabled (cron-fail-publish-notice policy 22:44 で手動 disable)

## 5. rollback / 不可触

- 本 doc は doc-only、code/config 変更なし
- 全 Cloud Run job/service 設定 当面 不変
- 推奨アクションは別 ticket で扱う、本セッションでは適用しない

## 6. 関連 commit / 文書
- P0 publish-notice two-phase: `bf29bcc` (本日 build/deploy 予定)
- 緊急対応 alert disable: `cron-fail-publish-notice` policy enabled=False (今朝 22:44 適用済)
- guarded-publish history rotation 設計: `2026-05-06_lane6_guarded_publish_history_rotation.md` (同日別 doc)

## 7. next_judgment
- doc-only commit + push のみ
- 適用は別 ticket、本セッション内では実行しない
