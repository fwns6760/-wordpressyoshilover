# 2026-05-02 observe handoff: ScheduleWakeup → GCP-side monitoring 移行

作成: 2026-05-02 11:14 JST  
理由: Claude Code session の `ScheduleWakeup` は session-bound (Claude は常駐監視プロセスではない) のため、24h 級の自律 observe には不向き。GCP Cloud Monitoring + Logging-based metrics + Scheduler-driven verify Job 側で監視を設計し直す。

## 1. 現在状態 (5/2 11:14 JST、MANUAL_CYCLE_OK 直後)

### deploy / production 反映済

| ticket | image / revision | env / flag | 完了時刻 |
|---|---|---|---|
| 298-Phase3 v4 | publish-notice:d541ebb | ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1 | 5/1 19:35 JST |
| 290-QA Pack A | yoshilover-fetcher:c14e269 (00176-vnk → 00177-qtr に traffic 移行) | ENABLE_WEAK_TITLE_RESCUE 未設定 (live-inert 維持) | 5/1 20:40 JST |
| 293-COST | yoshilover-fetcher:d541ebb / 00177-qtr + publish-notice:d541ebb | ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1 両 services | 5/1 21:00 JST |
| 300-COST | guarded-publish:9e9302f gen 19 | ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY 未設定 (default OFF live-inert) | 5/2 10:43 JST |

### 観測サマリ (11:12:30 JST 手動 cycle)

- 5/1 19:35 JST 以降 cumulative mail: sent=71/100、suppressed=0、errors=0
- silent skip last 60 min: 0
- severity≥ERROR last 60 min: 0
- 293 drafts_created (last 60 min): 全 0 (試合 14:00 JST 開始前)
- 293 preflight_skip event fetcher: 0 件 (gate 未 exercise)
- 293 publish-notice mail 「要review｜preflight_skip」: 0 件
- 300 post-deploy fires: 6 連続 Container exit(0) clean
- 300 guarded_publish_idempotent_history_skip log: 0 件 (default OFF 維持)
- Team Shiny `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` 維持

### Pending state-trigger (未到達)

- **293 FULL_EXERCISE_OK**: postgame draft 発生 + AI exercise 後に判定
- **298 24h 安定 DONE**: 5/2 19:35 JST 以降の rolling 24h で判定
- **282 USER_DECISION_REQUIRED**: 上記両達成後に GO Pack 提示

### 全 rollback target

- 300 → image=`guarded-publish:6df049c` / source=`git revert 9e9302f` / env=n/a
- 293 → fetcher=`00176-vnk` + publish-notice=`:1016670` / env=`--remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION`
- 298 → publish-notice=`:1016670` / env=`--remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE`

## 2. ScheduleWakeup 不適切な理由

- Claude session 終了 (user close / timeout / context overflow) で wake 消失
- Claude session 継続中も wake 発火タイミング保証なし (best-effort)
- daemon ではないため、user が新 session を開いた時にしか確認できない
- "ALIVE 継続" を Claude 単独で証明できない

→ **24h 級の安定監視は GCP infrastructure 側で実装すべき**

## 3. GCP-side monitoring 設計案

### 3-1. Cloud Monitoring alert policy (即実装可)

| alert name | trigger condition | severity | notification |
|---|---|---|---|
| publish-notice mail storm | rolling 1h `[summary] sent` 合計 > 30 | P1 | email to fwns6760@gmail.com |
| MAIL_BUDGET 24h breach | rolling 24h `[summary] sent` 合計 > 100 | P1 | email |
| silent skip 検出 | textPayload regex `PREFLIGHT_SKIP_MISSING_\|REVIEW_POST_DETAIL_ERROR\|REVIEW_POST_MISSING` count > 0 / 5 min | P0 | email + (将来) PagerDuty |
| severity≥ERROR 連続 | severity≥ERROR count > 3 / 10 min | P1 | email |
| guarded_publish_idempotent_history_skip 出現 | textPayload `guarded_publish_idempotent_history_skip` count > 0 (env apply なし時) | P0 | email |
| Team Shiny From 変動 | Cloud Asset Inventory diff watch on publish-notice job env | P0 | email |

### 3-2. Log-based metrics + Scheduler-driven verify Job (中期)

新規 ticket 候補: **301-OBSERVE: GCP-side autonomous verify Job + alert policy bundle**

scope 案:
- Cloud Run Job `observe-verify` 新規作成
- Scheduler `*/30` で fire (heartbeat 30 min)
- Job 内で以下 read-only 確認:
  - 293/298/300 state-trigger (preflight_skip event / 24h mail rolling / guarded-publish idempotent flag)
  - anomaly (silent skip / ERROR / Team Shiny / mail storm)
  - postgame draft 発生 + AI exercise 検出 → 293 FULL_EXERCISE_OK 自動判定
- 結果を Cloud Logging に `observe_verify_summary` event として出力
- alert policy で異常検出 → email 通知

### 3-3. 短期 fallback (今日 5/2 中の運用)

- Claude Code session で `/loop` ScheduleWakeup を best-effort 設定 (現状 11:34 JST pending)
- 自律 wake 発火しない場合は user 次 session open 時に手動 cycle 実行
- 異常通知は GCP-side alert (もし設定済) または user 手動確認

## 4. 次 session 開始時の resume 手順

1. **現在状態確認**:
   ```bash
   # 5/2 19:35 JST 以降 rolling 24h mail
   gcloud --project=baseballsite logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-05-01T10:35:00Z" AND textPayload:"[summary]"' --limit=500 --order=asc --format='value(textPayload)' | grep -oE 'sent=\d+ suppressed=\d+ errors=\d+' | python3 -c "import sys,re; t=[(0,0,0)]; [t.append(tuple(map(int, re.findall(r'\d+', L)))) for L in sys.stdin]; s=tuple(map(sum,zip(*t))); print(f'cumulative: sent={s[0]} suppressed={s[1]} errors={s[2]}')"
   
   # 293 postgame draft 発生確認
   gcloud --project=baseballsite logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-05-02T05:00:00Z" AND textPayload:"rss_fetcher_run_summary"' --limit=10 --order=desc --format='value(timestamp,textPayload)' | grep -oE 'drafts_created":\s*\d+\|x_ai_generation_count":\s*\d+'
   
   # 300 post-deploy fires
   gcloud --project=baseballsite logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="guarded-publish" AND timestamp>="2026-05-02T01:43:00Z" AND textPayload:"Container called exit"' --limit=20 --order=desc --format='value(timestamp,textPayload)' | wc -l
   ```

2. **state-trigger 判定**:
   - 293 FULL_EXERCISE_OK = drafts_created > 0 で且つ preflight_skip event ≥ 1 件 + Gemini delta -10〜-30%
   - 298 24h DONE = rolling 24h cumulative ≤ 100 + silent skip 0 + ERROR 0 + Team Shiny 維持
   - 両達成 → 282 GO Pack 5-field 提示

3. **anomaly 検出時 §14 自律 rollback** (上記 § 1 rollback target 参照)

4. **次 ticket 候補**:
   - 301-OBSERVE: GCP-side monitoring 実装 (Cloud Run Job + Scheduler + alert policy)
   - 改修 #4 prompt-id cost review gate (doc-only / Pack template)
   - 改修 #5 old_candidate ledger TTL impl (narrow prune script)
   - 288-INGEST Phase 2 visibility fix narrow design

## 5. 結論

- **observe 状態**: MANUAL_CYCLE_OK / AUTO_OBSERVE_UNPROVEN
- **Claude /loop**: best-effort、daemon 不可
- **24h 級監視**: GCP-side Cloud Monitoring + Scheduler-driven Job が必要
- **301-OBSERVE ticket 起票推奨** (次 session で着手)
- **本 doc が次 session resume の正本**
