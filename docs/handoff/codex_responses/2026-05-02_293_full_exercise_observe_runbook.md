# 293-COST FULL_EXERCISE 観測 runbook(5/2 朝、Claude 自律 read-only)

## 目的

293-COST OBSERVED_OK_SHORT(5/1 21:00 JST deploy + 24 min 短時間 verify)から FULL_EXERCISE_OK 確定へ。AI 上限 reset 後の fetcher run で preflight gate 実 exercise + publish-notice 通知発生 + Gemini delta 測定。read-only、production 不触。

## 前提

- 5/1 21:00 JST: 293 deploy 完了(image d541ebb、env ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1 両 services)
- 5/1 21:00-21:30 JST: 24 min 短時間 verify pass、ただし AI 上限 (x_ai_generation 10/10) 到達中で preflight gate 未 exercise
- 5/2 00:00 JST 想定: AI 上限 reset(daily counter)
- 5/2 朝 fetcher schedulers:
  - giants-realtime-trigger */5(継続)
  - giants-postgame-catchup-am 0 7
  - giants-weekday-pre 0,30 17(weekday の場合)
  - giants-weekday-daytime 0 9-16
  - giants-weekday-lineup-a 50 16

## 観測 task(優先順)

### Task 1: AI 上限 reset 確認(5/2 00:30 JST 以降)

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-05-02T00:00:00+09:00" AND textPayload:"x_ai_generation_count"' \
  --limit=5 --order=desc --format='value(timestamp,textPayload)'
```

期待:`x_ai_generation_count: 0` または非 10 値、上限 reset 確認。

### Task 2: preflight skip event 発生確認(5/2 朝 fetcher run 後)

fetcher 側:
```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-05-02T00:00:00+09:00" AND (textPayload:"preflight_skip" OR textPayload:"PREFLIGHT_SKIP")' \
  --limit=10 --order=desc --format='value(timestamp,textPayload)'
```

期待:preflight_skip event ≥ 1 件(AI 必要候補で gate trigger)。

ledger:
```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-05-02T00:00:00+09:00" AND textPayload:"PREFLIGHT_SKIP"' \
  --limit=5 --order=desc --format='value(timestamp,textPayload)'
```

### Task 3: publish-notice 通知発生確認

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-05-02T00:00:00+09:00" AND textPayload:"要review｜preflight_skip"' \
  --limit=5 --order=desc --format='value(timestamp,textPayload)'
```

期待:`【要review｜preflight_skip】<title>` subject mail ≥ 1 件 user 受信。

### Task 4: Gemini delta 測定

deploy 前 24h(4/30 21:00 - 5/1 21:00) vs deploy 後 24h(5/1 21:00 - 5/2 21:00)の Gemini call rate 比較:

```bash
# deploy 前 24h
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-04-30T21:00:00+09:00" AND timestamp<="2026-05-01T21:00:00+09:00" AND textPayload:"x_ai_generation_count"' \
  --format='value(textPayload)' | grep -oE 'x_ai_generation_count":\s*[0-9]+' | awk -F: '{sum+=$2} END {print "pre:", sum}'

# deploy 後 24h(段階的計測、5/2 21:00 まで)
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-05-01T21:00:00+09:00" AND textPayload:"x_ai_generation_count"' \
  --format='value(textPayload)' | grep -oE 'x_ai_generation_count":\s*[0-9]+' | awk -F: '{sum+=$2} END {print "post:", sum}'
```

期待:**delta -10〜-30%**(preflight gate により Gemini call 削減)。+5% 超過時 abnormal、§20.5 異常 trigger #4 該当。

### Task 5: silent skip 0 維持確認

```bash
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite logging read \
  'resource.type="cloud_run_revision" AND timestamp>="2026-05-02T00:00:00+09:00" AND (textPayload:"PREFLIGHT_SKIP_MISSING_" OR textPayload:"REVIEW_POST_DETAIL_ERROR" OR textPayload:"REVIEW_POST_MISSING")' \
  --limit=10 --order=desc --format='value(timestamp,textPayload)'
```

期待:**0 件**(POLICY §8 / §19.1 silent skip 違反候補 path 不在維持)。

### Task 6: mail volume / Team Shiny / 既存通知 確認

```bash
# mail volume(rolling 1h、24h)
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-05-02T00:00:00+09:00" AND textPayload:"[summary]"' \
  --limit=20 --order=desc --format='value(timestamp,textPayload)'

# Team Shiny From(env review)
CLOUDSDK_CONFIG=/tmp/gcloud-config gcloud --project=baseballsite run jobs describe publish-notice --region=asia-northeast1 --format='value(spec.template.spec.template.spec.containers[0].env)' | grep -oE "MAIL_BRIDGE_FROM[^;]*"
```

期待:
- mail volume: rolling 1h ≤ 30、24h ≤ 100(MAIL_BUDGET 内)
- Team Shiny `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` 維持
- 既存通知(real review / 289 / error) alive

## 判定 criteria

**FULL_EXERCISE_OK 確定条件(全 6 必須):**
1. AI 上限 reset 確認 ✓
2. preflight skip event ≥ 1 件 fetcher 側
3. publish-notice 通知 ≥ 1 件 user 可視
4. Gemini delta -10〜-30%(+5% 超過 abnormal)
5. silent skip 0 維持
6. mail volume / Team Shiny From / 既存通知 全維持

**HOLD 条件(任意 1 fail):**
- preflight gate 想定動作と乖離(skip 発生せず or 過剰発生)
- publish-notice 通知不在(silent skip risk)
- Gemini delta +5% 超過(逆効果)
- silent skip > 0
- 既存通知 路線破損

**ROLLBACK_REQUIRED 条件(§20.5 異常 8 trigger):**
- mail burst(rolling 1h sent>30)
- MAIL_BUDGET 超過
- silent skip > 0
- Gemini call >+5%
- Team Shiny From 変動
- publish/review/hold/skip 導線破損
- error 連続

## 異常時 rollback(§20.6、3-dim)

### Tier 1 runtime
- env rollback: `gcloud run services/jobs update <name> --remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION --region=asia-northeast1`(30 sec、両 services)
- image rollback: `gcloud run services update-traffic yoshilover-fetcher --to-revisions=yoshilover-fetcher-00176-vnk=100 --region=asia-northeast1`(2-3 min)+ `gcloud run jobs update publish-notice --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:1016670 --region=asia-northeast1`(2-3 min)

### Tier 2 source
- `git revert 10022c0 7c2b0cc afdf140 6932b25` + push origin master

### Post-rollback verify
- §20.2 + §20.3 同等で旧状態(290 Pack A / 298-v4)復帰確認

## 成功時 next action

FULL_EXERCISE_OK 確定 → 282-COST GO 検討に進める(env apply only `ENABLE_GEMINI_PREFLIGHT=1` to fetcher、image rebuild 不要、USER_DECISION_REQUIRED で user 5-field 提示)。

## 並行作業

- 298-Phase3 v4 Phase 6 verify(NEXT_SESSION_RUNBOOK §15 整合、5/2 09:00 JST):
  - 第二波防止 confirmation(5/1朝 99 cohort + 13:35 50 cohort sent=0 維持)
  - permanent_dedup ledger 106+ 件安定
  - 24h 安定確認(5/2 19:35 JST、deploy 後 24h)
- §14 P0/P1 mail monitor 24h 継続

両 verify 同時並行で 5/2 朝に full report。
