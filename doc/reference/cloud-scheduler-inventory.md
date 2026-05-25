# Cloud Scheduler inventory (yoshilover / baseballsite, asia-northeast1)

**purpose**: 全 GCP Cloud Scheduler jobs を 1 file で見渡せる SoT。 削除 / 統合 / 再開 判断のための inventory。 将来 agent (Claude / Codex) が「これ何の schedule か」 を grep で把握できる正本。

**最終 audit**: 2026-05-25 JST (Claude session)
**source command**: `gcloud scheduler jobs list --location=asia-northeast1 --project=baseballsite --format=json`
**TOTAL**: 54 jobs (PAUSED 15 / ENABLED 39)

---

## 1. PAUSED 残骸 (削除候補)

「never run = 一度も attempt なし」 OR 「1 ヶ月以上前に止まったまま」。 user 判断で 削除 / 保持を decide。

| name | schedule | target | last_attempt | 推定用途 | 削除可? |
|---|---|---|---|---|---|
| `audit-notify-6x` | `0 10-23 * * *` | yoshilover-fetcher (service) | never | 監査通知 (旧用途 不明) | 要 user 確認 |
| `codex-shadow-trigger` | `*/5 * * * *` | jobs:codex-shadow | never | Codex shadow lane (2026-05-12 user 切替で **廃止**) | **削除可** |
| `family-fetch-gsc-daily` | `0 6 * * *` | jobs:family-fetch-gsc | never | family blog GSC fetch (用途不明、 baseballsite repo に family-* code なし) | 要 user 確認 |
| `giants-weekday-lineup-a` | `50 16 * * 1-5` | yoshilover-fetcher | never | 平日 lineup 旧運用 (lineup-auto-pregame に置換済) | **削除可** |
| `giants-weekday-lineup-b` | `10,20,40,50 17 * * 1-5` | yoshilover-fetcher | never | 同上 | **削除可** |
| `giants-weekday-post` | `0,30 18-23 * * 1-5` | yoshilover-fetcher | never | 平日 postgame 旧運用 (giants-realtime-* + postgame-auto-daily に置換済) | **削除可** |
| `giants-weekday-pre` | `0,30 17 * * 1-5` | yoshilover-fetcher | never | 平日 pregame 旧運用 (lineup-auto-pregame に置換済) | **削除可** |
| `giants-weekend-eve` | `0,30 18-22 * * 0,6` | yoshilover-fetcher | never | 週末 evening 旧運用 (giants-realtime-* に置換) | **削除可** |
| `giants-weekend-lineup-day-a` | `50 12 * * 0,6` | yoshilover-fetcher | never | 週末 lineup 旧運用 (lineup-auto-pregame に置換) | **削除可** |
| `giants-weekend-lineup-day-b` | `10,20,40,50 13 * * 0,6` | yoshilover-fetcher | never | 同上 | **削除可** |
| `giants-weekend-lineup-late-a` | `50 15 * * 0,6` | yoshilover-fetcher | never | 同上 | **削除可** |
| `giants-weekend-lineup-late-b` | `10,20,40,50 16,17 * * 0,6` | yoshilover-fetcher | never | 同上 | **削除可** |
| `giants-weekend-post` | `0,30 16,17 * * 0,6` | yoshilover-fetcher | never | 週末 postgame 旧運用 (giants-realtime-* + postgame-auto-daily に置換) | **削除可** |
| `giants-weekend-post-late` | `30 23 * * 0,6` | yoshilover-fetcher | never | 同上 | **削除可** |
| `giants-weekend-pre` | `0,30 11-13 * * 0,6` | yoshilover-fetcher | never | 週末 pregame 旧運用 (lineup-auto-pregame に置換) | **削除可** |
| `publish-notice-peak-followup` | `25,55 20-21 * * *` | jobs:publish-notice | never | publish-notice 補助 (publish-notice-trigger-evening と機能重複) | 要 user 確認 |
| `yoshilover-fetcher-job` | `0 6-22 * * *` | yoshilover-fetcher (service) | 2026-04-19 | **旧 monolith** (memory `project_fetcher_scheduler_architecture.md` 参照、 PAUSED が正、 resume すると /run 二重発火 risk) | **削除可** (但し memory に「PAUSED が正」 と明記、 削除 vs 保持 user 判断) |

---

## 2. ENABLED active (運用中)

### 2.1 data-insight 系 (Cloud Run Job: insight-nightly、 計 7 fire/day)

| name | schedule | 用途 |
|---|---|---|
| `data-insight-morning-trigger` | `0 7 * * *` | 朝の data 記事生成 |
| `data-insight-1000-trigger` | `0 10 * * *` | 10 時 data 記事 |
| `data-insight-noon-trigger` | `0 12 * * *` | 昼 data 記事 |
| `data-insight-1500-trigger` | `0 15 * * *` | 15 時 data 記事 |
| `data-insight-pregame-trigger` | `0 17 * * *` | 試合前 data 記事 |
| `data-insight-2000-trigger` | `0 20 * * *` | 20 時 data 記事 |
| `data-insight-during-game-trigger` | `0 21 * * *` | 試合中 data 記事 |

### 2.2 publish-notice 系 (Cloud Run Job: publish-notice)

| name | schedule | 用途 |
|---|---|---|
| `publish-notice-trigger` | `5 6-15 * * *` | 日中 publish mail (毎時 :05) |
| `publish-notice-trigger-evening` | `5,35 16-22 * * *` | 夕-夜 publish mail (毎時 :05, :35) |
| `publish-notice-trigger-burst-tail` | `10 7,10,12,15,17,20,21 * * *` | burst tail 補助 (data-insight fire 後 10 分) |

memo: data-insight fire 後 5 分 (publish-notice-trigger) と 10 分 (burst-tail) 両方 trigger。 重複の可能性。

### 2.3 guarded-publish 系 (Cloud Run Job: guarded-publish)

| name | schedule | 用途 |
|---|---|---|
| `guarded-publish-trigger` | `*/30 * * * *` | 30 分毎 (= 24h × 2 = 48 fire/day) |

### 2.4 x-post-mail 系 (Cloud Run Job: x-post-mail-lane)

| name | schedule | 用途 |
|---|---|---|
| `x-post-mail-flush` | `0 6-22 * * *` | 毎時 :00 (= 17 fire/day) |
| `x-post-mail-flush-game-1` | `15,30,45 19-20 * * *` | 試合中 19-20 時 (3 fire × 2h) |
| `x-post-mail-flush-game-2` | `15,30,45 21 * * *` | 試合中 21 時 (3 fire) |

### 2.5 giants-realtime / fetcher 系 (Cloud Run Service: yoshilover-fetcher、 旧 fetcher 跡)

| name | schedule | 用途 / 備考 |
|---|---|---|
| `giants-morning-catchup` | `30 4 * * *` | 朝 4:30 まとめ |
| `giants-weekday-daytime` | `0 6-16 * * *` | 平日昼 (毎時) |
| `giants-realtime-trigger` | `0,30 17-21 * * *` | 試合時間 0,30 分 |
| `giants-realtime-peak-15min` | `15,45 18-21 * * *` | 試合時間 15,45 分 (上と組合せで 試合中 4 fire/h) |
| `giants-realtime-2230` | `30 22 * * *` | 試合後 catchup |
| `giants-realtime-2300` | `0 23 * * *` | 試合後 catchup |
| `giants-postgame-catchup-am` | `0 22 * * *` | 試合後 22 時 |
| `lineup-auto-pregame` | `0,15,30,45 17-18 * * *` | スタメン pregame |
| `postgame-auto-daily` | `30 22 * * *` | 試合後 22:30 (postgame-auto job) |

### 2.6 名言 mail 系

| name | schedule | 用途 |
|---|---|---|
| `sakamoto-meigen-mail-trigger` | `0 18 * * *` | 坂本名言 mail (18 時) |
| `kobayashi-meigen-mail-trigger-noon` | `0 12 * * *` | 小林名言 mail (12 時) |
| `kobayashi-meigen-mail-trigger-evening` | `0 17 * * *` | 小林名言 mail (17 時) |
| `kobayashi-meigen-mail-trigger-night` | `0 20 * * *` | 小林名言 mail (20 時) |

### 2.7 その他 (daily 系)

| name | schedule | 用途 |
|---|---|---|
| `digest-daily-morning` | `0 6 * * *` | 朝 digest mail |
| `fact-check-morning-report` | `5 * * * *` | 毎時 :05 fact-check |
| `broadcast-auto-daily` | `30 11 * * *` | 放送予定取得 |
| `draft-body-editor-trigger` | `0 */3 * * *` | 3 時間毎 draft 編集 |
| `external-ping-trigger` | `0 6 * * *` | external ping (alive check) |
| `fetch-gsc-daily` | `0 6 * * *` | GSC 検索データ取得 |
| `prosports-fetch-gsc-daily` | `0 6 * * *` | prosports GSC |
| `prosports-crawl-internal-links-daily` | `30 6 * * *` | prosports 内部リンク |
| `ga4-traffic-analyzer-daily` | `0 6 * * *` | GA4 アクセス解析 |
| `seo-fetch-daily` | `15 5 * * *` | SEO データ取得 |

---

## 3. 統合 / 整理 候補 (要 user 判断)

### 3.1 publish-notice の重複疑い
- `publish-notice-trigger` (5 6-15) + `-evening` (5,35 16-22) で 日中-夜 carry
- `-burst-tail` (10 7,10,12,15,17,20,21) は data-insight fire 後 10 分 補助
- → 3 系統で publish-notice job を毎日 ~25 fire 起動。 統合可能?

### 3.2 giants-realtime の peak split
- `giants-realtime-trigger` (0,30 17-21 = 8 fire) + `giants-realtime-peak-15min` (15,45 18-21 = 8 fire)
- 試合中 (17-21 時) 合計 ~16 fire/h、 1 試合 5 時間で ~80 fire
- 4 fire/h は overkill?

### 3.3 giants-realtime-2230 + 2300
- 試合後 22:30, 23:00 を別 trigger
- 統合可能? (postgame-auto-daily が 22:30 で別 job として稼働してる)

### 3.4 fetch-gsc / prosports-fetch-gsc / ga4-traffic-analyzer / seo-fetch / digest-daily-morning / external-ping / prosports-crawl-internal-links
- 同 6 時付近に 5-6 個 fire (集中)
- 順序依存ある場合、 fire 時刻が同じだと race condition risk

---

## 4. cost ざっくり

- Free tier: 3 jobs/月
- 課金: $0.10 / job / 月
- 現状 54 jobs - 3 free = **51 jobs × $0.10 = 月 $5.10 (~¥770)**
- 残骸 15 削除後: 39 - 3 = 36 jobs = 月 $3.60 (~¥540)
- **削減: 月 $1.50 (~¥230)**

---

## 5. 削除 / 整理 判断 record (user)

(user が判断したら下に追記)

- 2026-05-25 audit 実施 (Claude)。 削除 GO 待ち。

---

## 6. 操作 reference

### 削除前 backup
```bash
gcloud scheduler jobs describe <name> --location=asia-northeast1 --project=baseballsite > backup/<name>.yaml
```

### 削除
```bash
gcloud scheduler jobs delete <name> --location=asia-northeast1 --project=baseballsite --quiet
```

### code dependency 確認
```bash
grep -rn "<scheduler_name>" src/ doc/ config/ scripts/ cloudbuild_*.yaml 2>&1
```

### resume (paused → enabled、 削除前の最終手段)
```bash
gcloud scheduler jobs resume <name> --location=asia-northeast1 --project=baseballsite
```
