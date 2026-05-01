# 298-Phase3 v4 Pack UNKNOWN close

作成: 2026-05-01 JST  
mode: Lane B round 6 / doc-only / read-only evidence close / single-file diff  
scope: `docs/handoff/codex_responses/2026-05-01_298_phase3_v4_unknown_close.md` 新規のみ

---

## 0. 結論

- `298-Phase3 v4 Pack` で残っていた UNKNOWN 2 件は、この doc で **evidence fixed** とする。
- close 対象:
  1. `rollback command` 未固定
  2. `normal review / 289 / error mail remain active` evidence 未固定
- 判定:
  - `rollback command`: **3-tier command を明示固定**
  - `remain active evidence`: **直近 6h live log + current job describe で固定**
- したがって alignment は **9 / 9**。
- ただし **re-ON 自体は user GO 必須** のまま維持する(`docs/ops/POLICY.md` §7、`docs/ops/OPS_BOARD.yaml` `hold_needs_pack.298-Phase3`)。

---

## 1. rollback command 3-tier 固定

### Tier 1: env rollback (最 narrow)

```bash
gcloud run jobs update publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE
```

- rollback time: `~30 sec`
- rollback owner: `Claude` (`§14` 自律 hotfix or user 明示 `GO`)
- role: old-candidate once path だけを止める最小 rollback
- provenance:
  - `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md`
  - `2026-05-01 13:55 JST` の実 rollback と同一 command

### Tier 2: image rollback

```bash
gcloud run jobs update publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:4be818d
```

- rollback time: `~2-3 min`
- rollback owner: `Claude` (image revert は scope 拡大なので user 確認推奨)
- role: live image を 298 deploy 前 baseline へ戻す
- provenance:
  - `docs/handoff/session_logs/2026-04-30_next_action_queue.md`
  - `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md`
  - `docs/handoff/codex_responses/2026-05-01_codex_b_storm_permanent_fix.md`

### Tier 3: ledger archive (必要時のみ)

```bash
gsutil mv \
  gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json \
  gs://baseballsite-yoshilover-state/publish_notice/archive/<timestamp>.json
```

- rollback time: `~10-30 sec`
- rollback owner: `Claude` or authenticated executor
- role: ledger 異常検出時、または Phase3 v4 Case A seed reset 時だけ実行
- note:
  - 常用 rollback ではない
  - Tier 1 / Tier 2 だけで止まるなら不要

結論:

- `rollback command` は **plan** ではなく **exact command 3-tier** まで fixed。
- `ACCEPTANCE_PACK_TEMPLATE.md` が要求する `rollback command` field はこれで充足。

---

## 2. current live invariants

capture window:

- `now_utc`: `2026-05-01T06:08:01Z`
- `since_utc`: `2026-05-01T00:08:01Z`
- JST 換算: `2026-05-01 09:08:01 JST` から `2026-05-01 15:08:01 JST`

`gcloud run jobs describe publish-notice` current facts:

- generation: `42`
- image digest:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice@sha256:644a0ff30494bd41c078ea4a08179ba8b41ad507a66af47677c6c430176059e2`
  - session log 対応 tag: `publish-notice:1016670`
- `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org`
- `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1`
- `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` absent
- latest succeeded execution at capture:
  - `publish-notice-jmf9d`
  - created `2026-05-01T06:05:06.822743Z`
  - completed `2026-05-01T06:05:58.772031Z`

`gcloud scheduler jobs describe publish-notice-trigger` current facts:

- schedule: `*/5 * * * *`
- state: `ENABLED`
- timezone: `Asia/Tokyo`
- URI:
  - `https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/baseballsite/jobs/publish-notice:run`

state alignment:

- `docs/ops/CURRENT_STATE.md`:
  - `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` is OFF/absent
  - persistent ledger behavior is disabled
- `docs/ops/POLICY.md` §7:
  - keep normal review
  - keep `289` post_gen_validate notification
  - keep error notifications alive

---

## 3. 直近 6h log evidence

source:

- Cloud Logging
- `resource.type="cloud_run_job"`
- `resource.labels.job_name="publish-notice"`
- window: `2026-05-01T00:08:01Z` to `2026-05-01T06:08:01Z`

### 3.1 result / summary aggregates

summary rows:

- `summary_runs=72`
- `summary_sent_total=161`
- `summary_errors_nonzero=0`
- `severity>=ERROR rows=0`
- `[ALERT] publish-notice emitted=... but sent=0` rows = `0`

skip rows:

- sampled `[skip]` rows fetched(limit `5000`): `5000`
- server-side `reasonless [skip]` rows: `0`

判定:

- `72 / 72` trigger で `errors=0`
- `emit > 0 but sent = 0` alert `0`
- `silent skip` として扱う `reasonless [skip]` `0`

### 3.2 path emit count

exact subject-start count in the 6h window:

| path | meaning | count |
|---|---|---:|
| `【要review｜post_gen_validate】` | `289` 通知 | `8` |
| `【要確認】` | yellow real review | `6` |
| `【要確認・X見送り】` | 別 path | `2` |
| `【巨人】` | 通常 publish notice exact-prefix | `0` |

supplemental counts:

| path | count |
|---|---:|
| `【要review】` | `4` |
| `【要確認(古い候補)】` | `141` |
| all `[result]` rows | `161` |

note on `【巨人】 = 0`:

- exact-prefix 集計では、この 6h 窓に `subject='【巨人】...'` は **0 件**。
- subject 内に `【巨人】` を含む result 行は `4` 件あり、**4 / 4 が `【要review｜post_gen_validate】【巨人】...`** だった。
- ただし `2026-05-01 14:15 JST` の earlier note で `【巨人】1` と見えていたものは、実 log 上は
  - `【要review｜post_gen_validate】【巨人】...`
  という `289` path の 1 行だった。
- つまり earlier note の `【巨人】1` は **human summary shorthand** であり、exact subject-prefix accounting では `289` count に属する。

### 3.3 remain-active 判定

required field の観点では、必要なのは

- normal review
- `289` post_gen_validate
- error notification

である。

evidence:

- `289` path:
  - `【要review｜post_gen_validate】 = 8`
- review path:
  - `【要確認】 = 6`
  - `【要review】 = 4`
  - 合計 visible review class = `10`
- X hold path:
  - `【要確認・X見送り】 = 2`
- error path:
  - 観測窓では `errors=0` のため positive emit 自体は不要
  - ただし current live job は
    - image unchanged (`publish-notice:1016670`)
    - scheduler enabled
    - `MAIL_BRIDGE_FROM` unchanged
    - error-path を落とす env flag removal なし
  - よって **error notification path was not disabled** と判断する

inference note:

- `error mail remain active` は、この 6h 窓で意図的に error を起こしていないため、**positive fire ではなく routing invariance からの inference**。
- ただし inference に使った live facts はすべて current `gcloud` read-only evidence で固定済み。

---

## 4. UNKNOWN close verdict

### UNKNOWN 1: rollback command

- before:
  - env remove 実行例だけ fixed
  - image revert / ledger archive が command 未固定
- now:
  - Tier 1 / Tier 2 / Tier 3 の **exact command** fixed

判定: **CLOSED**

### UNKNOWN 2: normal review / 289 / error mail remain active

- before:
  - 14:15 JST slice summary はあったが、live invariant と exact-count が 1 枚に固定されていなかった
- now:
  - `289` = `8`
  - review visible class = `10`
  - `X見送り` = `2`
  - `72 / 72` summaries `errors=0`
  - `severity>=ERROR = 0`
  - `reasonless [skip] = 0`
  - `MAIL_BRIDGE_FROM` unchanged
  - `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` unchanged
  - error path disable evidence `0`

判定: **CLOSED**

---

## 5. alignment final

`2026-05-01_298_phase3_v4_alignment_review.md` で残っていた UNKNOWN は本 doc で消化完了。

final status:

- alignment: **9 / 9**
- `all UNKNOWN fields resolved`: **YES**
- `re_on_forbidden_until` last missing evidence: **cleared**
- re-ON precondition:
  - **all UNKNOWN fields resolved** = `YES`

ただし policy gate:

- `298-Phase3` は依然 `HOLD_NEEDS_PACK`
- re-ON / deploy / flag apply は **user GO 必須**
- この doc は **GO を出す文書ではなく、UNKNOWN close evidence** である

明日朝 user 提示前の precondition:

- **complete**

Claude 次 action 1 行:

```text
v4 Pack 9/9 整合、明日朝 06:00 JST user GO 提示 ready
```

---

## 6. evidence commands

used read-only commands:

```bash
CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud run jobs describe publish-notice \
  --region=asia-northeast1 \
  --project=baseballsite \
  --format=json

CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud scheduler jobs describe publish-notice-trigger \
  --location=asia-northeast1 \
  --project=baseballsite \
  --format=json

CLOUDSDK_CONFIG=/tmp/gcloudconfig gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="publish-notice" AND timestamp>="2026-05-01T00:08:01Z" AND timestamp<="2026-05-01T06:08:01Z"'
```

no live mutation:

- no env change
- no job update
- no scheduler change
- no WP action
- no impl
