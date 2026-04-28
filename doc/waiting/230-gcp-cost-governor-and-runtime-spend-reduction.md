# 230 GCP cost governor + runtime spend reduction

## meta

- number: 230
- type: audit + plan
- status: REVIEW_NEEDED
- priority: P0.5
- parent: 155 GCP migration master
- related: 229 LLM cost governor
- lane: A / Claude
- created: 2026-04-27
- scope: read-only audit + next-step design only

## background

GCP 移行後のコスト源は、Gemini 品質ではなく基盤側の高頻度実行、no-op 実行、肥大化した Cloud Logging、累積し続ける Artifact Registry image に寄っている。`guarded-publish` / `publish-notice` / `codex-shadow` / `draft-body-editor` はすでに Cloud Run Jobs 化されており、Scheduler cadence と log 粒度の調整だけでもランニングコストを落とせる余地がある。

本票では Gemini 品質、publish gate、WP write 方針、GCP live 設定を一切変えずに、read-only 観測だけで「どこを先に削るべきか」を整理する。実装は別便に分離する。

## evidence basis

- `gcloud run jobs list/describe/executions list`
- `gcloud scheduler jobs list/describe`
- `gcloud logging read`
- `gcloud artifacts docker images list`
- `gcloud artifacts repositories describe`
- local repo read-only inspection:
  - `cloudbuild_guarded_publish.yaml`
  - `cloudbuild_publish_notice.yaml`
  - `cloudbuild_draft_body_editor.yaml`
  - `cloudbuild_codex_shadow.yaml`
  - `.dockerignore`
  - `Dockerfile.publish_notice`
  - `Dockerfile.draft_body_editor`

## audit caveats

- `CLOUDSDK_CONFIG=/tmp/gcloud` workaround が必要だった。`~/.config/gcloud` は read-only で、直接の `gcloud` 実行は一部失敗した。
- `gcloud builds triggers list` はこの shell では timeout し、remote trigger の ignore-path 設定までは確認できなかった。
- `gcloud scheduler jobs describe ... --format='value(httpTarget.body)'` も timeout し、`/run` を叩く複数 Scheduler の body 差分は未確認。
- したがって、`giants-*` 系 `/run` Scheduler の意味差分と Cloud Build remote trigger の path filter は、実装便の前に user/Claude shell で再確認が必要。

## Cloud Run Jobs / Scheduler 棚卸し

観測できた Cloud Run Jobs は 8 本、Cloud Scheduler Jobs は 27 本だった。コスト源として目立つのは「5 分 cadence の Cloud Run Job 3 本 + 5 分 cadence の Cloud Run Service trigger 1 本 + 10 分 cadence の repair lane 1 本」で、日次 SEO job 群は相対的に小さい。

| lane | kind | cadence | daily executions | runtime evidence | resources / timeout / retry | current cost note |
|---|---|---:|---:|---|---|---|
| guarded-publish | Cloud Run Job + Scheduler | `*/5` | 288 | recent execution `guarded-publish-rf7q4`: 36.29s | 1 CPU / 512Mi / 600s / retry 1 | 約 174 分/日。publish 本線なので cadence 変更は慎重に扱うべき。 |
| publish-notice | Cloud Run Job + Scheduler | `*/5` | 288 | recent execution `publish-notice-rhsz4`: 32.29s | 1 CPU / 512Mi / 300s / retry 1 | 約 155 分/日。直近 5 execution は `sent=0` で no-op。 |
| codex-shadow | Cloud Run Job + Scheduler | `*/5` | 288 | recent execution `codex-shadow-sjzvs`: 46.33s | 1 CPU / 512Mi / 600s / retry 0 / parallelism 1 | 約 222 分/日。shadow lane で WP write 禁止のため cadence 削減しやすい。 |
| draft-body-editor | Cloud Run Job + Scheduler | `2,12,22,32,42,52 * * * *` | 144 | recent execution `draft-body-editor-42lwj`: 40.28s | 1 CPU / 512Mi / 600s / retry 1 | 約 97 分/日。直近 summary は `edited=0 put_ok=0`。 |
| giants-realtime-trigger | Scheduler -> `yoshilover-fetcher /run` | `*/5` | 288 | recent request latency: 20.7s〜31.9s | service HTTP / deadline 180s | 約 125 分/日の service runtime 相当。realtime 主軸なので phase 1 の削減対象にはしない。 |
| giants-weekday-daytime | Scheduler -> `yoshilover-fetcher /run` | `0 9-16 * * 1-5` | 8/weekday | target URI は `yoshilover-fetcher /run` | service HTTP / deadline 180s | cadence 自体は小さいが `realtime` と窓が重なる。body 差分未確認。 |
| fact-check-morning-report | Scheduler -> `yoshilover-fetcher /fact_check_notify?since=yesterday` | `0 * * * *` | 24 | recent request latency: 1.0s〜9.3s | service HTTP / deadline 300s | 「morning-report」という名前に対して cadence が高い。 |
| fetch-gsc-daily | Cloud Run Job + Scheduler | `0 6 * * *` | 1 | recent execution `fetch-gsc-vqwrd`: 26.94s | 1 CPU / 512Mi / 1800s / retry 1 | コスト寄与は小さい。 |
| prosports-fetch-gsc-daily | Cloud Run Job + Scheduler | `0 6 * * *` | 1 | latest observed execution was `2026-03-19` | 1 CPU / 512Mi / 1800s / retry 1 | 現在の実行実態が不明。ticket 230 の主対象からは外す。 |
| family-fetch-gsc-daily | Cloud Run Job + Scheduler | `0 6 * * *` but PAUSED | 0 | latest observed execution was `2026-03-17` | 1 CPU / 512Mi / 1800s / retry 1 | runtime cost は現状ゼロ。Artifact cleanup 側の対象。 |
| ga4-traffic-analyzer-daily | Scheduler | `0 6 * * *` | 1 | corresponding job detail not collected in this shell | deadline 180s | 本票では優先度低。 |

### 直近の no-op / low-yield 観測

- `publish-notice` 直近 5 execution はすべて `sent=0 suppressed=0 errors=0`。
- `draft-body-editor` 直近 summary は `edited=0`, `put_ok=0`, `outside_edit_window=242`, `unresolved_and_stale=22`。
- `codex-shadow` 直近 summary も `put_ok=0`, `reject=2`, `skip=272` で、5 分ごとにほぼ同じ no-op 集計を返している。
- `guarded-publish` は publish 本線だが、sample execution では per-post `skipped` JSON と GCS copy log が支配的で、常時 heavy logging になっている。

## 頻度落とし候補

### phase 1 ですぐ下げてよい候補

- `publish-notice`: `*/5` -> `*/15`
  - 直近 5 execution が連続 no-op。
  - 通知遅延は最大 15 分になるが、WP write や Gemini 品質には影響しない。
  - 推定削減: 約 103 分/日の Job runtime。
- `codex-shadow`: `*/5` -> `*/15`
  - shadow lane であり、`parallelism=1` / `WP write 禁止` の安全側ポリシーと整合。
  - 直近 summary が no-op に近い。
  - 推定削減: 約 148 分/日の Job runtime。
- `draft-body-editor`: 24h 10 分おきではなく `10:00-23:59 JST` の active window のみに限定
  - job 自身が `edit_window_jst=10:00-23:59 JST` を出している。
  - 現在 cadence のままでも window 外は無駄実行が多い。
  - 推定削減: 144 回/日 -> 84 回/日、約 40 分/日の Job runtime。
- `fact-check-morning-report`: `0 * * * *` -> `0 6,12,18 * * *` あるいは `0 6 * * *`
  - endpoint が `since=yesterday` 固定で、1 時間ごとの差分専用ではない。
  - 名前も `morning-report` なので 24 回/日は過剰。
  - 推定削減: 24 回/日 -> 3 回/日で 87.5% 減。

### verify 後に触る候補

- `guarded-publish`: いきなり `*/15` に落とすより、まず off-hours だけ `*/10` or `*/15` に寄せるほうが安全
  - 105 auto publish 本線は「5-15 分以内」の鮮度期待がある。
  - 先に `publish-notice` / `codex-shadow` / `draft-body-editor` を削り、publish 本線は phase 2 に回すべき。
- `giants-weekday-daytime`: `giants-realtime-trigger` と同じ `/run` を叩くため、mode 差分がなければ統合候補
  - ただし scheduler body がこの shell では取れなかった。
  - `giants-weekday-post` / lineup 系など他 `/run` job も存在し、game-window ごとの意味差分があり得るため、disable は verify 後に限定。
- `giants-realtime-trigger`: realtime 主軸なので cost だけで削らない
  - publish freshness を守る前提なら last-step の最適化対象。

## Cloud Logging 肥大化 risk

### 観測結果

- `guarded-publish` sample execution `guarded-publish-rf7q4`
  - `gcloud logging read ... --limit=200 --format=json | wc -c` で **179,214 bytes / 200 entries**。query limit に達しているので実量はこれ以上。
  - per-post JSON 断片、`post_id`、`status`、`publish_link`、GCS copy 行が大量に出ている。
- `publish-notice` sample execution `publish-notice-rhsz4`
  - **11,392 bytes / 4 entries**。
  - `[scan]` と `[summary]` のみで、payload 自体は小さい。
- `draft-body-editor` sample execution `draft-body-editor-42lwj`
  - **9,760 bytes / 3 entries**。
  - `aggregate_counts`, `skip_reason_counts`, `per_post_outcomes`, `post_id` を持つ JSON summary が毎回出る。
- `codex-shadow` sample execution `codex-shadow-sjzvs`
  - **10,761 bytes / 3 entries**。
  - `draft-body-editor` と近い構造の JSON summary。

### risk 判定

- 本文全文、prompt 全文、secret は sample では観測しなかった。
- ただし `guarded-publish` は execution ごとの per-post detail を log に流しすぎており、Cloud Logging 料金と data minimization の両面で縮める価値が高い。
- `draft-body-editor` / `codex-shadow` は log 量そのものは moderate だが、同じ no-op summary を短 cadence で繰り返しているため、cadence 削減とセットで効く。
- `publish-notice` は payload は軽いが cadence が重く、`sent=0` の execution が続くと log noise 化する。

### logging governor design

- `guarded-publish`
  - execution あたり 1 つの structured summary を基本とする。
  - per-post detail は「publish 実行時」「cleanup 実行時」「error 時」だけ GCS artifact へ退避し、Cloud Logging には count と execution id だけ残す。
  - 期待効果: guarded-publish log volume を 80% 以上削減。
- `publish-notice`
  - `emitted=0 sent=0 errors=0` の時は `[scan]` と `[summary]` を 1 行に圧縮する。
  - cursor detail は state file に任せ、毎回の long timestamp pair を出しすぎない。
- `draft-body-editor` / `codex-shadow`
  - `aggregate_counts` は残し、`per_post_outcomes` は `edited > 0` または `reject > 0` の時だけ出す。
  - 同一 no-op summary が続く場合は nth-run ごとの sampling も候補。

## Artifact Registry image 累積

### 観測結果

- repository `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover`
  - size: **21,270.331MB**
  - cleanup policy: **observed なし**
- image version count sample
  - `fetcher`: **102**
  - `publish-notice`: **12**
  - `guarded-publish`: **7**
  - `draft-body-editor`: **3**
  - `codex-shadow`: **2**
- `fetcher` と `publish-notice` には untagged historical version が複数残っている。

### 判定

- 主因は legacy `fetcher` の積み上がり。102 version あるため、現行 live digest / rollback に必要な数を除けば削減余地が大きい。
- runtime に紐づく `publish-notice` / `guarded-publish` / `draft-body-editor` / `codex-shadow` は件数自体は少ないが、untagged version を残す理由は薄い。
- cleanup policy が未設定なので、storage は今後も線形に増える。

### cleanup policy design

- keep rule
  - 各 image で **currently deployed digest/tag**
  - 各 image で **latest 5 tagged versions**
  - 明示 rollback tag があるもの
- delete rule
  - untagged version は **3 日超**で削除
  - tagged version は **14 日または 30 日超**で削除
  - `fetcher` は legacy 系が多いため first pass の削減対象
- safety rule
  - delete 前に live Cloud Run Job / Service が参照中の digest/tag を inventory 化
  - initial apply は dry-run / report-first

### 想定効果

- conservative estimate でも **10GB〜15GB** の storage 圧縮が見込める。
- 以後の増分も cleanup policy で頭打ちにできる。

## doc-only 変更で rebuild しない運用 ratify

### local repo で確認できたこと

- in-repo の GitHub Actions workflow は observed なし。
- `cloudbuild_guarded_publish.yaml` と `cloudbuild_codex_shadow.yaml` は temp build context を自前生成しており、`src/`, `vendor/`, `requirements*`, `Dockerfile*`, `bin/*entrypoint*` のみをコピーしている。
- `cloudbuild_publish_notice.yaml` と `cloudbuild_draft_body_editor.yaml` は context `.` を使うが、`.dockerignore` が以下だけを whitelist している。
  - `.dockerignore`
  - `requirements.txt`
  - `requirements-dev.txt`
  - `src/**`
  - `vendor/**`
  - `Dockerfile.draft_body_editor`
- したがって local build context には `doc/**` や `*.md` は入らない。

### 結論

- Docker context upload の観点では、doc-only commit で build 内容が膨らむ構成ではない。
- 残る無駄は **remote trigger が doc-only commit に反応して build を起こすこと** と **人手で不要 rebuild を回すこと**。
- よってこの ticket では次の運用を ratify する。

### ratified policy

1. `doc/**`, `docs/**`, `*.md` だけの変更では image rebuild しない。
2. rebuild 対象は `src/`, `vendor/`, `requirements*`, `Dockerfile*`, `bin/*entrypoint*`, `cloudbuild_*.yaml` の変更時に限定する。
3. remote trigger が存在する場合は ignored path / included path で doc-only build を明示的に除外する。
4. remote trigger 設定の実確認は `gcloud builds triggers list` が通る shell で別便 verify する。

## 日次 cost summary 設計

### 目的

- GCP cost を「月末に Billing 画面を見る」ではなく、日次の governor loop に落とす。
- runtime, logging, artifact, build の 4 つを同じ summary で追う。

### 設計案

- cadence
  - 1 日 1 回、`06:15 JST`
- data source
  - preferred: Cloud Billing export -> BigQuery
  - fallback: Cloud Run execution / request latency / Cloud Logging byte count / Artifact Registry size の推定集計
- summary fields
  - date
  - Cloud Run Jobs cost / execution_count / runtime_seconds
  - Cloud Run Service cost / request_count / latency band
  - Cloud Logging bytes by lane
  - Artifact Registry size GB and daily delta
  - Cloud Build count / minutes
  - top 3 spenders
  - delta vs trailing 7-day mean
- output
  - structured log 1 件
  - mail 1 通または既存 digest への append
- alerts
  - daily warning: **200 円/日**
  - monthly warning: **5,000 円/月**
  - Cloud Logging warning: **100MB/日**
  - Artifact Registry warning: **25GB**

### implementation note

- Billing export 未導入なら phase 1 は「推定サマリ」で開始し、後続で BigQuery export に格上げする。
- 実装は `230-E` or `230-impl-1` に分離し、本票では設計だけに留める。

## sub-ticket plan

- `230-A scheduler cadence governor phase 1`
  - `publish-notice 5m -> 15m`
  - `codex-shadow 5m -> 15m`
  - `draft-body-editor` を active window のみに制限
  - `fact-check-morning-report` を 1 日 1〜3 回へ縮退
  - `guarded-publish` は維持
- `230-B guarded-publish logging compaction + INFO discipline`
  - per-post stdout を summary + artifact pointer へ圧縮
- `230-C artifact registry cleanup policy`
  - keep-live / keep-latest-5 / delete-untagged-old / report-first
- `230-D no-rebuild ratify + remote trigger path filter verify`
  - remote trigger の ignore-path 実確認
  - doc-only build 禁止 runbook
- `230-E daily cost summary + alerting`
  - Billing export または fallback 推定集計

## 推奨実装順 + 想定削減効果

1. `230-A scheduler cadence governor phase 1`
   - もっとも低 risk で runtime 分をすぐ削れる。
   - `publish-notice` + `codex-shadow` + `draft-body-editor window gating` だけで **約 290 分/日** の runtime 削減見込み。
2. `230-B guarded-publish logging compaction`
   - sample だけで **179KB / execution** の heavy log を観測。
   - 288 回/日換算で lower bound でも **50MB/日超**の log を食っており、圧縮効果が大きい。
3. `230-C artifact registry cleanup policy`
   - one-time で **10GB〜15GB** 圧縮期待。
   - 以後の growth cap も付く。
4. `230-D no-rebuild enforcement`
   - 直接の節約額は運用依存だが、doc-only 便で build minutes を無駄にしない統制になる。
5. `230-E daily cost summary`
   - 直接削減ではなく、以後の drift を早期検知する governor 機能。

## non-goals

- 自動公開の停止
- Gemini 品質の低下
- publish gate の緩和
- GCP live 変更
- Cloud Run / Scheduler / Artifact Registry / Billing export の apply
- WP / mail / X の live mutation
- src / tests / config / existing ticket doc の編集

## 次便 1 本

- `230-A scheduler cadence governor phase 1`
  - 変更対象は Scheduler cadence と実行窓だけ
  - `guarded-publish` は維持
  - `giants-weekday-daytime` は body 差分 verify が取れるまで触らない
