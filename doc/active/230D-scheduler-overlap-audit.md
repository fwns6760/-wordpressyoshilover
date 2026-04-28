# 230-D scheduler overlap audit

## meta

- number: 230-D
- type: audit + plan
- status: REVIEW_NEEDED
- priority: P0.5
- parent: 230-A
- related: 230 / 230-A1
- lane: A / Claude
- created: 2026-04-28
- mode: read-only `gcloud scheduler jobs list/describe` + doc 1 file only
- live_apply_owner: authenticated executor only

## background

230-A1 では `publish-notice` / `codex-shadow` / `draft-body-editor` / `fact-check` の cadence 調整 runbook が先行したが、`yoshilover-fetcher` service を直接叩く `giants-*` Scheduler 群は untouched のまま残っている。本票はその重複 / overlap / 統合可能性を、**Scheduler 側に見えている URI / method / query / body / state だけ**で棚卸しする read-only audit であり、src / tests / GCP live mutation は行わない。

今回の観測で、prompt baseline の「`giants-*` 7+」より実数は多く、**`giants-*` 15 本**、fetcher service hit Scheduler は **18 本 total / 16 本 enabled** だった。さらに prompt で `giants-weekday-post` として想定されていた `0 9-16 * * 1-5` は、現行では **`giants-weekday-daytime`** に存在し、`giants-weekday-post` 自体は **平日 18:00-23:30** の evening window になっている。

採取時点の要約:

- total Scheduler jobs: **28**
- fetcher service hit jobs: **18**
- enabled fetcher service hit jobs: **16**
- enabled `giants-*` jobs hitting `POST /run`: **15**
- paused legacy `/run` job: **`yoshilover-fetcher-job`**
- independent non-`/run` fetcher endpoints:
  - `fact-check-morning-report` -> `GET /fact_check_notify?since=yesterday`
  - `audit-notify-6x` -> `GET /audit_notify?window_minutes=60` (currently PAUSED)

## 全 scheduler 棚卸し

採取コマンド:

```bash
gcloud scheduler jobs list \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format='value(name,schedule,state,timeZone,httpTarget.uri,httpTarget.httpMethod,lastAttemptTime)'
```

| name | schedule | state | timeZone | target | method | lastAttemptTime |
|---|---|---|---|---|---|---|
| `draft-body-editor-trigger` | `2,12,22,32,42,52 * * * *` | `ENABLED` | `Asia/Tokyo` | `run job draft-body-editor:run` | `POST` | `2026-04-28T01:32:00.940753Z` |
| `family-fetch-gsc-daily` | `0 6 * * *` | `PAUSED` | `Asia/Tokyo` | `run job family-fetch-gsc:run` | `POST` | - |
| `giants-weekday-post` | `0,30 18-23 * * 1-5` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-27T14:30:27.368227Z` |
| `giants-realtime-trigger` | `*/5 * * * *` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-28T01:35:18.102496Z` |
| `prosports-crawl-internal-links-daily` | `30 6 * * *` | `ENABLED` | `Asia/Tokyo` | `run job prosports-crawl-internal-links:run` | `POST` | `2026-04-27T21:30:03.191179Z` |
| `audit-notify-6x` | `0 10-23 * * *` | `PAUSED` | `Asia/Tokyo` | `fetcher /audit_notify?window_minutes=60` | `GET` | - |
| `prosports-fetch-gsc-daily` | `0 6 * * *` | `ENABLED` | `Asia/Tokyo` | `run job prosports-fetch-gsc:run` | `POST` | `2026-04-27T21:00:03.997913Z` |
| `codex-shadow-trigger` | `*/5 * * * *` | `ENABLED` | `Asia/Tokyo` | `run job codex-shadow:run` | `POST` | `2026-04-28T01:35:03.342747Z` |
| `giants-weekend-lineup-day-b` | `10,20,40,50 13 * * 0,6` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-26T04:50:34.275193Z` |
| `giants-weekend-lineup-day-a` | `50 12 * * 0,6` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-26T03:50:44.209199Z` |
| `ga4-traffic-analyzer-daily` | `0 6 * * *` | `ENABLED` | `Asia/Tokyo` | `run job ga4-traffic-analyzer-daily:run` | `POST` | `2026-04-27T21:00:00.915575Z` |
| `fact-check-morning-report` | `0 * * * *` | `ENABLED` | `Asia/Tokyo` | `fetcher /fact_check_notify?since=yesterday` | `GET` | `2026-04-28T01:00:10.543748Z` |
| `giants-postgame-catchup-am` | `0 7 * * *` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-27T22:00:17.600953Z` |
| `giants-weekend-eve` | `0,30 18-22 * * 0,6` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-26T13:31:05.466455Z` |
| `giants-weekend-pre` | `0,30 11-13 * * 0,6` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-26T04:31:33.436512Z` |
| `giants-weekday-pre` | `0,30 17 * * 1-5` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-27T08:30:35.658034Z` |
| `giants-weekday-daytime` | `0 9-16 * * 1-5` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-28T01:00:31.066061Z` |
| `yoshilover-fetcher-job` | `0 6-22 * * *` | `PAUSED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-19T09:13:51.807969Z` |
| `fetch-gsc-daily` | `0 6 * * *` | `ENABLED` | `Asia/Tokyo` | `run job fetch-gsc:run` | `POST` | `2026-04-27T21:00:00.578787Z` |
| `giants-weekend-lineup-late-a` | `50 15 * * 0,6` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-26T06:52:10.920067Z` |
| `giants-weekend-lineup-late-b` | `10,20,40,50 16,17 * * 0,6` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-26T08:50:47.527783Z` |
| `publish-notice-trigger` | `*/5 * * * *` | `ENABLED` | `Asia/Tokyo` | `run job publish-notice:run` | `POST` | `2026-04-28T01:35:05.703313Z` |
| `giants-weekend-post-late` | `30 23 * * 0,6` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-26T14:31:08.431576Z` |
| `giants-weekday-lineup-a` | `50 16 * * 1-5` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-27T07:50:27.297823Z` |
| `giants-weekday-lineup-b` | `10,20,40,50 17 * * 1-5` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-27T08:50:32.271959Z` |
| `guarded-publish-trigger` | `*/5 * * * *` | `ENABLED` | `Asia/Tokyo` | `run job guarded-publish:run` | `POST` | `2026-04-28T01:35:04.955291Z` |
| `giants-weekend-post` | `0,30 16,17 * * 0,6` | `ENABLED` | `Asia/Tokyo` | `fetcher /run` | `POST` | `2026-04-26T08:31:05.189128Z` |
| `seo-fetch-daily` | `15 5 * * *` | `ENABLED` | `Asia/Tokyo` | `run job seo-fetch-job:run` | `POST` | `2026-04-27T20:15:03.592201Z` |

## giants-* fetcher hit 分析

採取コマンド:

```bash
gcloud scheduler jobs describe <job> \
  --project=baseballsite \
  --location=asia-northeast1 \
  --format='value(name,schedule,httpTarget.uri,httpTarget.httpMethod,httpTarget.body,lastAttemptTime,state)'
```

Scheduler 側で見えた事実:

- `giants-*` **15/15** が同じ host の **`POST /run`** を叩いている
- query string 差分は **なし**
- body 差分は **`giants-realtime-trigger` の `{}` のみ**。他 14 本は body 未設定
- custom mode header は観測できず、`giants-realtime-trigger` だけ body 由来の `Content-Type: application/json` が付く
- よって **Scheduler 側で明示されている sub-scope は job 名と schedule 以外に存在しない**

理論発火数は cron からの平均値。`giants-realtime-trigger */5` は 24h 常時 288 回で、他 `giants-*` の全時刻を包含する。

| name | schedule | uri path | body | run scope (name-based recap) | overlap with | 想定発火 / 日 | current judgement |
|---|---|---|---|---|---|---:|---|
| `giants-realtime-trigger` | `*/5 * * * *` | `/run` | `{}` | realtime ingest mainline | all other `giants-*` | 288.00 | **維持必須** |
| `giants-weekday-daytime` | `0 9-16 * * 1-5` | `/run` | unset | weekday daytime ingest window | realtime exact overlap | 5.71 | pause candidate |
| `giants-weekday-pre` | `0,30 17 * * 1-5` | `/run` | unset | weekday pregame ingest window | realtime exact overlap | 1.43 | pause candidate |
| `giants-weekday-lineup-a` | `50 16 * * 1-5` | `/run` | unset | weekday lineup early slot | realtime exact overlap | 0.71 | pause candidate |
| `giants-weekday-lineup-b` | `10,20,40,50 17 * * 1-5` | `/run` | unset | weekday lineup follow-up slots | realtime exact overlap | 2.86 | pause candidate |
| `giants-weekday-post` | `0,30 18-23 * * 1-5` | `/run` | unset | weekday evening/postgame ingest window | realtime exact overlap | 8.57 | pause candidate |
| `giants-postgame-catchup-am` | `0 7 * * *` | `/run` | unset | morning catchup ingest | realtime exact overlap | 1.00 | conditional keep or pause |
| `giants-weekend-pre` | `0,30 11-13 * * 0,6` | `/run` | unset | weekend pregame ingest window | realtime exact overlap | 1.71 | pause candidate |
| `giants-weekend-lineup-day-a` | `50 12 * * 0,6` | `/run` | unset | weekend lineup day early slot | realtime exact overlap | 0.29 | pause candidate |
| `giants-weekend-lineup-day-b` | `10,20,40,50 13 * * 0,6` | `/run` | unset | weekend lineup day follow-up slots | realtime exact overlap | 1.14 | pause candidate |
| `giants-weekend-lineup-late-a` | `50 15 * * 0,6` | `/run` | unset | weekend lineup late early slot | realtime exact overlap | 0.29 | pause candidate |
| `giants-weekend-lineup-late-b` | `10,20,40,50 16,17 * * 0,6` | `/run` | unset | weekend lineup late follow-up slots | realtime exact overlap | 2.29 | pause candidate |
| `giants-weekend-post` | `0,30 16,17 * * 0,6` | `/run` | unset | weekend afternoon/evening post window | realtime exact overlap | 1.14 | pause candidate |
| `giants-weekend-eve` | `0,30 18-22 * * 0,6` | `/run` | unset | weekend evening ingest window | realtime exact overlap | 2.86 | pause candidate |
| `giants-weekend-post-late` | `30 23 * * 0,6` | `/run` | unset | weekend late postgame catchup | realtime exact overlap | 0.29 | pause candidate |
| `audit-notify-6x` | `0 10-23 * * *` | `/audit_notify?window_minutes=60` | n/a (`GET`) | audit lane | endpoint independent from `/run` | 14.00 if enabled | keep paused; rename/cadence fix before resume |

補足:

- `audit-notify-6x` は名前に反して **6/day ではなく 14/day** 相当の cron になっている
- `audit-notify-6x` は現在 `PAUSED` なので、現時点の active overlap/cost には寄与していない
- `yoshilover-fetcher-job` は `giants-*` ではないが、同じ `POST /run` を叩く paused legacy job であり、現時点では **resume 非推奨**

## 重複判定

### 現在の scheduler-visible 結論

この ticket の観測範囲では、**`giants-*` 非 realtime 14 本はすべて `giants-realtime-trigger` と scheduler-visible contract が同一**である。

- same host: `yoshilover-fetcher-...run.app`
- same path: `/run`
- same method: `POST`
- same query: なし
- same custom-header contract: 観測なし
- body difference: `giants-realtime-trigger` の `{}` vs 他 14 本の unset のみ

したがって、**Scheduler 側だけを根拠にすると「realtime-trigger が常時動いている間、他 `giants-*` は冗長」**という判定が最も強い。少なくとも Scheduler 設定上は、`lineup` / `catchup` / `weekday` / `weekend` を識別する引数は付いていない。

### same-payload branch

この branch が今回の主結論。

- `giants-realtime-trigger` を残し、他 `giants-*` はまず **pause** で止める
- delete ではなく pause を推奨する理由は rollback を `resume` だけで戻せるため
- first-wave apply は weekday group と weekend group を分けてもよいが、scheduler-visible evidence は一括 pause を支持している

### different-payload branch

今回の観測では支持されなかったが、別便で src read-only audit を行うなら分岐条件は以下になる。

- fetcher service が caller identity や request metadata を使って内部的に別 mode へ分岐している
- `catchup` や `lineup` の意味差分が Scheduler 設定ではなく service 実装にのみ埋まっている

この場合でも、現在の Scheduler 定義は冗長度が高すぎるため、最小構成は次のどちらかに縮約されるはず。

- realtime + `giants-postgame-catchup-am` だけ残す
- realtime + `giants-postgame-catchup-am` + lineup overlay 各 1 本だけ残す

少なくとも `weekday/weekend` で A/B/late/post/eve を多重に残す根拠は、Scheduler 設定からは見えない。

## 統合候補

apply ticket では **pause first, delete later** を前提にする。rollback は原則 `gcloud scheduler jobs resume ...`、cadence 修正系は `gcloud scheduler jobs update http ... --schedule=...` で戻す。

| 廃止 / 統合候補 | 現在の対象 | 推奨アクション | 残す scheduler | rollback |
|---|---|---|---|---|
| weekday overlay set | `giants-weekday-daytime`, `giants-weekday-pre`, `giants-weekday-lineup-a`, `giants-weekday-lineup-b`, `giants-weekday-post` | **pause 候補**。Scheduler-visible diff が無いので realtime に吸収 | `giants-realtime-trigger` | `gcloud scheduler jobs resume <job> --project=baseballsite --location=asia-northeast1` |
| weekend overlay set | `giants-weekend-pre`, `giants-weekend-lineup-day-a`, `giants-weekend-lineup-day-b`, `giants-weekend-lineup-late-a`, `giants-weekend-lineup-late-b`, `giants-weekend-post`, `giants-weekend-eve`, `giants-weekend-post-late` | **pause 候補**。Scheduler-visible diff が無いので realtime に吸収 | `giants-realtime-trigger` | `gcloud scheduler jobs resume <job> --project=baseballsite --location=asia-northeast1` |
| postgame catchup | `giants-postgame-catchup-am` | **conditional**。same-payload branch なら pause、different-payload branch が後で証明された場合のみ 1x/day catchup として残す | `giants-realtime-trigger` or `giants-realtime-trigger + giants-postgame-catchup-am` | `gcloud scheduler jobs resume giants-postgame-catchup-am --project=baseballsite --location=asia-northeast1` |
| paused legacy `/run` | `yoshilover-fetcher-job` | **keep paused**。realtime 既存下で resume する理由なし | `giants-realtime-trigger` | 現状維持。resume 非推奨 |
| audit lane | `audit-notify-6x` | **keep paused now**。resume するなら先に cadence を name 相当の 6/day か `1x/3h` へ修正 | `audit-notify-6x` paused or rescheduled audit job | `gcloud scheduler jobs update http audit-notify-6x --project=baseballsite --location=asia-northeast1 --schedule='0 10-23 * * *' --time-zone=Asia/Tokyo` |

### `audit-notify-6x` の cadence 候補

- true 6/day に戻す候補:
  - `0 8,10,12,14,16,18 * * *`
  - `0 9,11,13,15,17,19 * * *`
- `1x/3h` 候補:
  - `0 */3 * * *`
- `1x/day` 候補:
  - `0 9 * * *`

`audit-notify-6x` は現在 paused なので、ここは overlap よりも **name/schedule drift 修正**が主題になる。

## 維持必須

- `giants-realtime-trigger`
- `guarded-publish-trigger`
- `publish-notice-trigger` は 230-A1 別レーン対象であり、本票の overlap apply 対象にしない

## 想定削減効果

Scheduler hit count ベースの directional estimate:

- `giants-realtime-trigger` を残し、non-realtime `giants-*` 14 本を pause すると:
  - `giants-*` family total: **318.29 hits/day**
  - realtime only: **288.00 hits/day**
  - reduction: **30.29 hits/day**
  - reduction ratio: **9.52%**
- `yoshilover-fetcher-job` はすでに paused のため、現状でも **17.00 hits/day** 分の legacy `/run` が抑止されている
- `audit-notify-6x` はすでに paused のため active cost reduction は現時点 **0**
  - ただし将来 resume するなら、current 14/day を true 6/day に戻すだけで **8 hits/day** 削減
  - 1/day まで落とすなら **13 hits/day** 削減

この票では service 実行時間までは測っていないため、cost 効果は hit count 削減の方向感に留める。少なくとも Scheduler 定義上は、`giants-*` 非 realtime 群を残すことで fresh data gain を説明する材料は見えなかった。

## non-goals

- 自動公開停止
- publish 本線停止
- `giants-realtime-trigger` 廃止提案
- `guarded-publish-trigger` 廃止提案
- src / tests / config / Cloud Build / Docker / GCP live mutation
- WP / mail / X / Gemini 操作
- README / assignments / 既存 ticket doc の編集

## next

- `230-D-apply`
  - authenticated executor が Scheduler pause / reschedule を実行
  - first-wave は **delete ではなく pause**
  - before/after snapshot と rollback を同 ticket で固定
- 必要なら別便で src read-only audit
  - `/run` handler が caller identity 依存の special branch を持つかだけ確認
  - その結果がなければ、non-realtime `giants-*` 14 本は realtime に統合してよい
