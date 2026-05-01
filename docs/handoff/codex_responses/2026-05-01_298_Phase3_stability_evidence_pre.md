# 298-Phase3 stability evidence pre-collection

作成: 2026-05-01 JST  
mode: Lane B round 4 / read-only / doc-only / single-file diff  
scope: `docs/handoff/codex_responses/2026-05-01_298_Phase3_stability_evidence_pre.md` 新規のみ

---

## 0. window lock

- capture time lock: `2026-05-01T05:18:12Z` = `2026-05-01 14:18:12 JST`
- query window lock: `2026-05-01T05:00:00Z` to `2026-05-01T05:18:12Z`
- user 指示の `05:00-13:00 UTC (= 14:00-22:00 JST)` baseline band を採用したが、**今回の pre-collection は band 全体ではなく、その先頭 18m12s の partial slice**
- よって本 doc は **17:00 JST `production_health_observe` 用の baseline** であり、17:00 時点では同 query を fresh recompute する前提
- 実行制約は user 指示通り `gcloud logging read` / `gcloud run jobs describe` / `gcloud run services describe` / `gcloud scheduler jobs describe` のみ

---

## 1. KPI snapshot

| # | KPI | expected | query | actual | 判定 |
|---|---|---|---|---|---|
| 1 | publish-notice `sent / suppressed / errors` | rollback 後 `sent=10 burst=0`, `errors=0` | `Q1` | `sent=3`, `suppressed=0`, `errors=0`, `sent=10 burst=0/4 run` | OK |
| 2 | `【要確認(古い候補)】` emit count | `0` 想定 | `Q2` | `0` | OK |
| 3 | `【要review｜post_gen_validate】` emit count | path 維持 | `Q2` | `1` | OK |
| 4 | yellow real review emit count | path 維持 | `Q2` | `2` (`【要確認】` 2件) | OK |
| 5 | `【要確認・X見送り】` emit count | `0` でも可、path 維持 | `Q2` | `0` | OK |
| 6 | silent skip detection | `0` 想定 | `Q4` | `0` | OK |
| 7 | Gemini call delta baseline | publish-notice rollback 起因の異常増なし | `Q5`, `Q6` | gemini-related match `34`, `google.genai=0`, actual `gemini_call_made:true=1` at `2026-05-01T05:10:37Z` | INFO |
| 8 | Team Shiny From verify | `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` | `Q7` | `y.sebata@shiny-lab.org` | OK |
| 9 | publish-notice job env invariants | `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` absent / `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS` absent / `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` | `Q7` | 期待通り | OK |
| 10 | fetcher service image invariant | `yoshilover-fetcher:4be818d` / rev `00175-c8c` | `Q8` | `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d`, rev `yoshilover-fetcher-00175-c8c` | OK |
| 11 | publish-notice image invariant | `publish-notice:1016670` 維持 | `Q7` + session log cross-check | live は digest `sha256:644a0ff30494bd41c078ea4a08179ba8b41ad507a66af47677c6c430176059e2`; `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md` `13:06 JST` 記録の `publish-notice:1016670` と一致 | OK |
| 12 | forbidden post_id range `63003-63311` emit count | `0` 想定 | `Q2` | `0` | OK |

補足:

- KPI 7 は **絶対 0 が期待値ではない**。298 は `publish-notice` 側 change のため、ここでは fetcher 側に publish-notice 起因の spillover 異常が見えないかを baseline 化した。
- この partial slice では、fetcher に gemini 関連 log はあるが、**actual miss/call は 1 件**で、それ以外は cache lookup log。

---

## 2. baseline evidence rows

### 2.1 publish-notice summary rows (`Q1`)

| timestamp(UTC) | summary |
|---|---|
| `2026-05-01T05:00:43.020515Z` | `sent=1 suppressed=0 errors=0` |
| `2026-05-01T05:05:36.357958Z` | `sent=1 suppressed=0 errors=0` |
| `2026-05-01T05:10:33.558622Z` | `sent=0 suppressed=0 errors=0` |
| `2026-05-01T05:15:38.169375Z` | `sent=1 suppressed=0 errors=0` |

集計:

- total sent: `3`
- total suppressed: `0`
- total errors: `0`
- `sent=10` runs: `0`

### 2.2 publish-notice result rows (`Q2`)

| timestamp(UTC) | post_id | subject class | subject |
|---|---|---|---|
| `2026-05-01T05:00:43.020484Z` | `64189` | `【要確認】` | `【要確認】中山礼都、若林楽人が１軍合流 中山は２軍戦の直近３試合で打率６割３分６厘 | YOSHILOVER` |
| `2026-05-01T05:05:36.357813Z` | `64185` | `【要確認】` | `【要確認】坂本「もっと打てるように」 関連発言 | YOSHILOVER` |
| `2026-05-01T05:15:38.169364Z` | `post_gen_validate:f246bcbb7501573a:postgame_strict:strict_validation_fail:required_facts_missing:game_date,required_facts_missing:giants_score,required_facts_missing:opponent_score` | `【要review｜post_gen_validate】` | `【要review｜post_gen_validate】【記事全文】阪神・村上頌樹が1日の巨人戦に先発 今季初の中5日「バッターに集中して」開幕戦黒星の雪辱だ - スポニチ Sponichi Annex 野球 | YOSHILOVER` |

class count:

- `【要確認(古い候補)】`: `0`
- `【要review｜post_gen_validate】`: `1`
- `【要確認】`: `2`
- `【要確認・X見送り】`: `0`
- other sent class: `0`

### 2.3 publish-notice scan rows (`Q3`)

| timestamp(UTC) | emitted | skipped | cursor_before | cursor_after |
|---|---:|---:|---|---|
| `2026-05-01T05:00:41.475850Z` | `1` | `3913` | `2026-05-01T13:55:33.995556+09:00` | `2026-05-01T14:00:33+09:00` |
| `2026-05-01T05:05:34.688019Z` | `1` | `3938` | `2026-05-01T14:00:33+09:00` | `2026-05-01T14:03:14+09:00` |
| `2026-05-01T05:10:33.517316Z` | `0` | `3951` | `2026-05-01T14:03:14+09:00` | `2026-05-01T14:10:31.875638+09:00` |
| `2026-05-01T05:15:36.451507Z` | `1` | `3966` | `2026-05-01T14:10:31.875638+09:00` | `2026-05-01T14:15:33.751625+09:00` |

scan baseline:

- total emitted: `3`
- total skipped: `15768`
- `scan emitted` と `summary sent` はこの slice では `3 = 3` で一致

### 2.4 fetcher gemini baseline (`Q5`, `Q6`)

- gemini-related match count: `34`
- `google.genai` textual matches: `0`
- actual `gemini_call_made:true`: `1`
  - `2026-05-01T05:10:37.226919Z`
  - `source_url_hash=f246bcbb7501573a`
  - `prompt_template_id=postgame_strict_slotfill_v1`
- corresponding success line:
  - `2026-05-01T05:10:37.226433Z`
  - `Gemini postgame strict slot-fill 生成成功 905文字`

読み方:

- `34` は cache lookup を含む **gemini-related log volume**
- 実際の miss/call はこの slice では `1`
- 298 scope は `publish-notice` であり、ここでは **fetcher 側に publish-notice rollback 起因の異常スパイクは見えていない**

### 2.5 silent detection (`Q4`)

- `textPayload contains "silent"` matches: `0`

### 2.6 forbidden range check (`Q2`)

- numeric `post_id` in `63003-63311`: `0`

---

## 3. env / image invariants

### 3.1 publish-notice job (`Q7`)

- generation: `42`
- lastUpdatedTime: `2026-05-01T02:59:23.356762Z`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice@sha256:644a0ff30494bd41c078ea4a08179ba8b41ad507a66af47677c6c430176059e2`
- targeted env checks:
  - `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org`
  - `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1`
  - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` absent
  - `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS` absent

### 3.2 fetcher service (`Q8`)

- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d`
- latest ready revision: `yoshilover-fetcher-00175-c8c`

### 3.3 scheduler context (`Q9`)

- `publish-notice-trigger`
- schedule: `*/5 * * * *`
- state: `ENABLED`
- lastAttemptTime: `2026-05-01T05:15:05.804128Z`
- next scheduleTime at capture: `2026-05-01T05:20:04.786579Z`

---

## 4. anomaly verdict

- anomaly detected in this baseline slice: `0`
- no `sent=10` burst after rollback in the captured window
- no `【要確認(古い候補)】` re-emit
- no forbidden `63003-63311` emit
- no silent text hit
- no publish-notice error

residual caution:

- この baseline は `2026-05-01T05:00:00Z` から `2026-05-01T05:18:12Z` までの **18m12s**
- したがって `24h stable` 判定や `17:00 JST` health gate には **fresh recompute が必須**
- 特に第二波 risk は別 doc の通り `2026-05-02 09:00 JST` 近辺で再評価が必要であり、本 baseline 自体はそれを打ち消さない

---

## 5. query appendix

`Q1` publish-notice summary

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-05-01T05:00:00Z" AND timestamp<="2026-05-01T05:18:12Z" AND logName="projects/baseballsite/logs/run.googleapis.com%2Fstdout" AND textPayload:"[summary]"' \
  --project=baseballsite --limit=50 --format='value(timestamp,textPayload)'
```

`Q2` publish-notice result rows

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-05-01T05:00:00Z" AND timestamp<="2026-05-01T05:18:12Z" AND logName="projects/baseballsite/logs/run.googleapis.com%2Fstdout" AND textPayload:"[result]"' \
  --project=baseballsite --limit=200 --format='value(timestamp,textPayload)'
```

`Q3` publish-notice scan rows

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-05-01T05:00:00Z" AND timestamp<="2026-05-01T05:18:12Z" AND logName="projects/baseballsite/logs/run.googleapis.com%2Fstdout" AND textPayload:"[scan]"' \
  --project=baseballsite --limit=100 --format='value(timestamp,textPayload)'
```

`Q4` silent detection

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud logging read \
  '(resource.type="cloud_run_job" OR resource.type="cloud_run_revision") AND timestamp>="2026-05-01T05:00:00Z" AND timestamp<="2026-05-01T05:18:12Z" AND textPayload:"silent"' \
  --project=baseballsite --limit=200 --format='value(timestamp,resource.type,textPayload)'
```

`Q5` fetcher gemini-related lines

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-05-01T05:00:00Z" AND timestamp<="2026-05-01T05:18:12Z" AND (textPayload:"google.genai" OR textPayload:"gemini" OR jsonPayload.message:"google.genai" OR jsonPayload.message:"gemini")' \
  --project=baseballsite --limit=200 --format='value(timestamp,logName,textPayload,jsonPayload.message)'
```

`Q6` fetcher actual gemini call marker

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND timestamp>="2026-05-01T05:00:00Z" AND timestamp<="2026-05-01T05:18:12Z" AND textPayload:"gemini_call_made\": true"' \
  --project=baseballsite --limit=200 --format='value(timestamp,textPayload)'
```

`Q7` publish-notice job describe

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud run jobs describe publish-notice \
  --project=baseballsite --region=asia-northeast1 --format=json
```

`Q8` fetcher service describe

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud run services describe yoshilover-fetcher \
  --project=baseballsite --region=asia-northeast1 --format='value(spec.template.spec.containers[0].image,status.latestReadyRevisionName)'
```

`Q9` scheduler describe

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud scheduler jobs describe publish-notice-trigger \
  --project=baseballsite --location=asia-northeast1 --format=json
```
