# 次回セッション開始 Runbook(永続正本)

本 doc は **Claude が次セッション起動直後に読む固定手順**。
session_logs に依存せず、`docs/ops/` 5 file だけで再開できる。

---

## 1. 必読 sequence(最初の 1 分)

以下を **順番通り** 読む(他 file は本 sequence 完了後の参照、POLICY §21 正本 3 + 補助 2 + INCIDENT_LIBRARY と整合):

```
1. docs/ops/CURRENT_STATE.md       (現在地、6 カテゴリ board)
2. docs/ops/OPS_BOARD.yaml         (ticket 状態の機械可読正本)
3. docs/ops/POLICY.md              (運用ルール、§14 / §17 / §18 / §22 / §23 等)
```

これだけで再開可能。以下は必要時のみ:
- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`(user GO 提示時、18 項目)
- `docs/ops/INCIDENT_LIBRARY.md`(P1 体感事故時、過去事例参照、§19 必須)
- `docs/handoff/session_logs/*.md`(過去 incident 詳細が必要な時、履歴扱い)
- `docs/handoff/codex_responses/*.md`(Codex 履歴が必要な時、履歴扱い)

---

## 2. 起動直後の必須 read-only verify(2-3 分)

```bash
# repo 同期
cd /home/fwns6/code/wordpressyoshilover
git fetch origin
git reset --hard origin/master
git log --oneline -5
git status --short | head -10

# CI 状態
gh run list --workflow=tests.yml --limit 3 --json status,conclusion,headSha

# live image / scheduler
gcloud run services describe yoshilover-fetcher --region=asia-northeast1 --project=baseballsite \
  --format='value(spec.template.spec.containers[0].image,status.latestReadyRevisionName)'
gcloud run jobs describe publish-notice --region=asia-northeast1 --project=baseballsite \
  --format='value(spec.template.spec.template.spec.containers[0].image)'
gcloud run jobs describe guarded-publish --region=asia-northeast1 --project=baseballsite \
  --format='value(spec.template.spec.template.spec.containers[0].image)'
gcloud scheduler jobs describe codex-shadow-trigger --location=asia-northeast1 \
  --project=baseballsite --format='value(state)'
```

期待値(`OPS_BOARD.yaml` permanent_evidence と一致):
- fetcher: `:4be818d` rev `00175-c8c`
- publish-notice: `:4be818d`
- guarded-publish: `:6df049c`
- codex-shadow scheduler: PAUSED

差分検出時 → **P0 即報告**(自律対処しない)。

---

## 3. 起動後の最初の報告 format(永続、user 向け)

以下 format で必ず出す:

```markdown
## YOSHILOVER 再開報告

### 現在地(CURRENT_STATE.md より)
- ACTIVE: <list>
- OBSERVE: <list>
- READY: <list>(Acceptance Pack 完成済のみ)
- HOLD_NEEDS_PACK: <list>
- FUTURE_USER_GO: <list>
- DONE: <list>

### live verify 結果(read-only)
- repo HEAD: <commit>
- CI 直近: <status>
- fetcher / publish-notice / guarded-publish image: <verify 結果>
- codex-shadow scheduler: PAUSED 確認

### P0 / Safety
- <なし or 検出内容>

### 今 user に必要な判断(0 or 1 件、Acceptance Pack 形式)
- <0 件 or Acceptance Pack 13 項目>

### 次の 1 手(Claude 自律 GO 範囲)
- <1 件、user 確認不要>
```

---

## 4. 禁止事項(永続、確認なしに違反しない)

### 自律 GO 範囲外(必ず Acceptance Pack 提示してから)
- deploy / image rebuild / service-job update / traffic 切替
- env / flag 値変更(`--update-env-vars` / `--remove-env-vars`)
- Scheduler 操作(enable / disable / pause / resume / 頻度)
- SEO / noindex / canonical / 301 / robots / sitemap
- Gemini call 増加(prompt 拡張 / TTL 短縮 / model 変更 / call site 追加)
- mail 通知条件 大改修(subject / dedup / cap / Team Shiny / SMTP)
- source 追加(`config/rss_sources.json` 拡張)
- live_update 変更(`ENABLE_LIVE_UPDATE_ARTICLES` 値)
- X 自動投稿 ON
- cleanup mutation(WP delete / draft 戻し / private 化)
- rollback 不能変更
- 公開基準の緩和(duplicate guard 解除 / hard_stop 解除)
- 新規 ticket 起票(P0 incident 以外)

### 通常時の即停止条件(自律 GO 中、P0/P1 incident でない場合)
- src / tests / config / Dockerfile / cloudbuild yaml / requirements.txt 編集が必要
- silent skip 検出(P0 即報告、自律対処しない、`POLICY.md` §6)
- ledger silent / mail silent / rss_fetcher 内 silent / WP 直接 silent
- env / image / Scheduler の差分検出(期待値と乖離)

### P0/P1 incident 時の例外(`POLICY.md` §14、user 明示 GO 不要)
**8 条件 全部 AND を満たす場合**、Acceptance Pack なしで Claude 自律即時 hotfix 実行可:
1. 継続中のユーザー体感破壊
2. scope narrow(1 service or 1 job の env / scheduler 操作のみ、code 変更 0)
3. Gemini call 増加なし
4. Team Shiny From 変更なし
5. 既存通知全停止ではない(289 / 通常 publish notice / その他通知 1 つ以上残る)
6. rollback 1 コマンドまたは明確
7. 実施後 verify 条件明確(sent=N / errors=0 等)
8. SEO / source 追加 / Scheduler 変更 / publish 基準緩和 に触れない

実行後の事後報告 5 項目(env action / 次 trigger 結果 / errors / rollback 要否 / 影響範囲)で完結。

---

## 5. Claude 自律 GO 範囲(USER_GO_REQUIRED=false で進める、永続)

以下のみ自律で進める(`POLICY.md` §3 10 categories):
- READ_ONLY / DOC_ONLY / EVIDENCE_ONLY / HANDOFF_UPDATE / TEST_DESIGN / ROLLBACK_CATALOG / BOARD_COMPRESSION / ACCEPTANCE_PACK_DRAFT
- **INCIDENT_ANALYSIS**(P0/P1 root cause 解析 / ledger 解析、read-only)
- **P0_P1_NARROW_HOTFIX**(§14 8 条件 全部 AND 満たす narrow hotfix 即時実行、Acceptance Pack 不要)

---

## 6. 更新責任(本 runbook 自身)

| 観点 | 更新責任者 |
|---|---|
| 本 runbook(`NEXT_SESSION_RUNBOOK.md`)| Claude(自律 GO、運用変更時のみ) |
| 期待値 update(image tag / scheduler state)| Claude(本番 deploy 後 commit + push)|
| 必読 sequence 変更 | Claude + ChatGPT 監査(運用 root 変更時) |

---

## 7. 関連 doc(階層、POLICY §21 / §24 と整合)

```
docs/ops/                       (永続正本、6 file = 正本 3 + 補助 2 + INCIDENT_LIBRARY 1)
├── POLICY.md                   (運用ルール 24 sections、user GO 9 / 自律 GO 10 / Pack 18 項目 / silent skip P0 / clean build / P0_P1 自律 hotfix 8 条件 / Outcome Ledger / Claude 一次受け / MAIL_BUDGET / user 通知絞り込み)【正本】
├── CURRENT_STATE.md            (現在地、6 カテゴリ board、session 単位更新)【正本】
├── OPS_BOARD.yaml              (ticket 状態機械可読正本、各 ticket 7 軸 OWNER + state + evidence)【正本】
├── ACCEPTANCE_PACK_TEMPLATE.md (user GO 提示 template、18 項目)【補助正本】
├── NEXT_SESSION_RUNBOOK.md     (本 doc、次回開始固定手順)【補助正本】
└── INCIDENT_LIBRARY.md         (P1 体感事故 post-mortem ライブラリ、§19 参照義務)【補助正本】

docs/handoff/                   (履歴、過去事実、新規 ops 状態の正本ではない)
├── session_logs/
│   ├── 2026-04-30_p0_publish_recovery_observation.md  (P0 復旧履歴)
│   ├── 2026-04-30_next_action_queue.md                (旧 queue、参考履歴)
│   ├── 2026-04-30_session_summary.md                  (旧 1 行サマリ、参考履歴)
│   ├── 2026-05-01_ops_reset.md                        (本 ops reset の起源履歴)
│   └── 2026-05-01_p1_mail_storm_hotfix.md             (P1 mail storm hotfix 1 行履歴 + §14 例外発動 evidence)
└── codex_responses/, codex_requests/, run_logs/       (Codex 履歴)
    ├── 2026-05-01_codex_a_storm_verify.md             (Codex A storm read-only verify + env-only hotfix 案)
    └── 2026-05-01_codex_b_storm_permanent_fix.md      (Codex B 恒久対策 設計 + deploy Pack final)

~/.claude/projects/.../memory/  (Claude 補助記憶、正本ではない、矛盾時は repo 優先)
```

mail / Gmail 通知は Ops Board ではない(POLICY §21、状態は OPS_BOARD.yaml に戻す)。

---

## 8. production_health_observe 手順(永続、17:00 JST 1 round read-only)

session 跨ぎでも次 Claude が再現可能なよう、query template を本 doc に永続化。
所要 ~5 min、user 接点なし、自律 GO 範囲(EVIDENCE_ONLY)。

### 実行手順(1 round で全 7 query 実行、結果を OPS_BOARD evidence に embed)

```bash
cd /home/fwns6/code/wordpressyoshilover

# 1. publish-notice 24h sent/errors 集計
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-04-30T08:00:00Z" AND textPayload:"summary"' \
  --project=baseballsite --limit=300 --format='value(textPayload)' \
  | grep -oE 'sent=[0-9]+|errors=[0-9]+' | sort | uniq -c

# 2. publish-notice 直近 trigger 5 件
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND textPayload:"summary"' \
  --project=baseballsite --limit=10 --format='value(timestamp,textPayload)' | head -10

# 3. 289 post_gen_validate emit 24h count
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-04-30T08:00:00Z" AND (textPayload:"post_gen_validate" OR textPayload:"要review｜post_gen_validate")' \
  --project=baseballsite --limit=1000 --format='value(timestamp)' | wc -l

# 4. Gemini call 24h delta(fetcher)
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-04-30T08:00:00Z" AND (textPayload:"google.genai" OR textPayload:"gemini")' \
  --project=baseballsite --limit=1000 --format='value(timestamp)' | wc -l

# 5. silent skip detection
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-04-30T08:00:00Z" AND textPayload:"silent"' \
  --project=baseballsite --limit=100 --format='value(timestamp,textPayload)' | head -10

# 6. env / image / scheduler 不変 verify
gcloud run jobs describe publish-notice --region=asia-northeast1 --project=baseballsite \
  --format='value(spec.template.spec.template.spec.containers[0].image,spec.template.spec.template.spec.containers[0].env)'
gcloud run services describe yoshilover-fetcher --region=asia-northeast1 --project=baseballsite \
  --format='value(spec.template.spec.containers[0].image,status.latestReadyRevisionName)'
gcloud scheduler jobs describe publish-mail-trigger --location=asia-northeast1 --project=baseballsite \
  --format='value(state,schedule)' 2>/dev/null || echo 'scheduler name unknown - search via list'

# 7. cache_hit ratio
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-04-30T08:00:00Z" AND (textPayload:"cache_hit" OR textPayload:"cache_miss")' \
  --project=baseballsite --limit=500 --format='value(textPayload)' \
  | grep -oE 'cache_hit|cache_miss' | sort | uniq -c

# 8. 299-QA flaky 再現性 check(local pytest 1 round)
python3 -m pytest tests/test_postgame_strict_template.py -q 2>&1 | tail -10
```

### 期待値(POLICY OPS_BOARD permanent_evidence と照合)

| 観測項目 | 期待値 |
|---|---|
| publish-notice errors | 0 |
| publish-notice sent | MAIL_BUDGET 内(30/h, 100/d、本日 storm 90 通含む 24h 値は許容)|
| 289 post_gen_validate emit | 100+ count(silent skip 0 維持の証跡)|
| Gemini call delta | 24h baseline ±20% 以内 |
| silent skip | 0 件 |
| publish-notice image | Phase3 deploy 後の new image(Codex 報告 hash)|
| publish-notice env | `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` / `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` / `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`(Phase3 flag ON 後)|
| fetcher image | `yoshilover-fetcher:4be818d` rev `00175-c8c` |
| scheduler state | ENABLED(publish-mail-trigger)|
| cache_hit ratio | 75% 以上(POLICY §7、99% 持続なら真因 audit 必要)|
| 299-QA pytest | 失敗増加 0(0 or 3 failures とも acceptable、failures 増加なら真因解析)|

### 異常検出時の対応(POLICY §6 / §14 / §19 連動)

- **silent skip > 0 検出** → P0 即報告(自律対処しない)、Acceptance Pack 経由
- **errors > 0 検出** → P1 体感事故扱い、§14 8 条件 hotfix 検討 / Acceptance Pack 経由
- **MAIL_BUDGET 違反**(直近 1h sent > 30 等)→ P1、INCIDENT_LIBRARY 参照
- **Gemini call 急増** → 真因 audit、user 報告 + Acceptance Pack
- **env / image / scheduler 期待値乖離** → P0 即報告
- **299-QA pytest failures 増加** → 真因解析、本物の P0 候補

### 結果の embed 先

- `docs/ops/OPS_BOARD.yaml` `observe.production_health_observe.evidence:` に集計値 update
- `docs/ops/CURRENT_STATE.md` 「OBSERVE 結果(17:00 JST)」section 更新
- 異常 0 確認なら **ops reset + 298 Phase3 close 確定**(DONE 化)

---

## 9. 「次セッション開始」の意味

「次セッション」=:
- WSL 再起動後 / 別端末で起動後 / Claude session が消えた後
- 24h 以上経過後の再開
- ChatGPT Pro 監査後の再開

いずれの場合も、本 runbook の sequence 1-3 をたどれば再開可能。
session_logs / Claude memory なしでも本 runbook + `docs/ops/` 5 file で完結。

---

## 9. 不変方針(永続、`POLICY.md` section 12 と整合)

- `ENABLE_LIVE_UPDATE_ARTICLES=0` 維持
- Team Shiny From `y.sebata@shiny-lab.org` 維持
- SEO/noindex/canonical/301 不変
- X 自動投稿 OFF
- duplicate guard 全解除なし(narrow 緩和のみ可)
- Scheduler 頻度変更なし(現フェーズ NEVER)
- 既存 fixed_lane prompt text 不変
- 新 subtype 追加なし
- prosports 修正なし

これらを変更する場合 = フェーズ変更 = user 明示 GO + Acceptance Pack。
