# 230-A GCP runtime cost governor 具体提案

## meta

- number: 230-A
- type: plan
- status: REVIEW_NEEDED
- priority: P0.5
- parent: 230
- lane: A / Claude
- created: 2026-04-28
- scope: read-only deeper audit + concrete next-step proposal only

## background

GCP budget 1500 円到達は notification only で、現時点では自動停止も品質低下も起きていない。ただし 230 audit の通り、Gemini 品質そのものよりも「5 分 cadence の常時実行」「quiet-hours / no-op 実行」「guarded-publish の heavy logging」「Artifact Registry の version 累積」が先に削れるコスト源になっている。

本票は live 変更なしの read-only audit として、次便でどこを先に触るべきかを 1 枚に落とす。実測時刻は `2026-04-27T21:12:00Z` 基準で、24h 回数は現行 cron からの理論値、平均時間と空振り率は recent sample からの推定値である。

## evidence basis

- `gcloud run jobs executions list`
- `gcloud scheduler jobs list/describe`
- `gcloud logging read`
- `gcloud artifacts docker images list`
- `gcloud artifacts docker tags list`
- `gcloud artifacts repositories describe`

## 24h 実績 table

注:

- `24h runs` は現行 cadence からの理論値。
- `avg duration` は recent sample 平均。
- `sampled empty rate` は summary log が取れた lane だけ recent sample で推定。
- `giants-realtime-trigger` は Cloud Run Job ではなく Scheduler -> Cloud Run Service `/run`。application-level no-op はこの便では分離していない。

| job | current cadence | 24h runs | avg duration sample | 24h cumulative runtime | sampled empty rate | audit note |
|---|---|---:|---:|---:|---|---|
| guarded-publish | `*/5` | 288 | 31.86s (`n=20`) | 152.9 min/day | exact 24h unknown | 最新 sample は publish 0 / skipped-only で、`hold_reason=backlog_only` 系の multi-line JSON log が支配的。速報 publish 本線のため phase 1 では維持寄り。 |
| publish-notice | `*/5` | 288 | 30.48s (`n=20`) | 146.3 min/day | about 100% (`6/6` recent summaries = `emitted=0 sent=0`) | cadence に対して連続 no-op。phase 1 で最も落としやすい。 |
| giants-realtime-trigger | `*/5` | 288 | 23.6s (`n=4` scheduler attempts) | 113.4 min/day | not isolated in this ticket | `4/4` recent scheduler attempts were HTTP 200. realtime ingestion 主軸なので cadence は維持寄り。 |
| codex-shadow-trigger | `*/5` | 288 | 19.72s (`n=20`) | 94.7 min/day | about 100% (`12/12` recent summaries = `candidates=0 put_ok=0 stop_reason=quiet_hours`) | shadow lane で WP write なし。phase 1 の有力削減候補。 |
| draft-body-editor | `2,12,22,32,42,52 * * * *` | 144 | 17.09s (`n=10`) | 41.0 min/day | about 100% (`10/10` recent summaries = `candidates=0 put_ok=0 stop_reason=quiet_hours`) | recent sample は quiet-hours 側に偏る。cadence そのものより active window 制限の方が安全。 |

### additional non-5min candidate

| job | current cadence | observation | implication |
|---|---|---|---|
| fact-check-morning-report | `0 * * * *` | target URI is `/fact_check_notify?since=yesterday` | endpoint 名と query から見て 24 回/日は過剰。5 分 lane ではないが phase 1 に近い低 risk 削減候補。 |

## 5 分 cron 落とし候補

### 結論

- **phase 1 で落とす**: `publish-notice`, `codex-shadow-trigger`
- **phase 1 で window だけ絞る**: `draft-body-editor`
- **phase 1 では維持**: `guarded-publish`, `giants-realtime-trigger`
- **別枠で同時に見直してよい**: `fact-check-morning-report`

| job | current | proposed | direct runtime reduction | expected effect | risk / hold line |
|---|---|---|---:|---|---|
| publish-notice | `*/5` | `*/15` | 192 runs/day and about 97.5 min/day saved | mail/noise lane の 66.7% runtime 削減 | 通知遅延が最大 10 分増える。速報掲示板運用でも mail は publish 本体ではないので許容余地あり。 |
| codex-shadow-trigger | `*/5` | `*/15` first, optionally `*/30` after 24h verify | `*/15` で about 63.1 min/day saved; `*/30` なら about 78.9 min/day | shadow lane を 1/3 cadence にしても WP write 禁止 policy と整合 | shadow feedback の鮮度だけ低下。publish 本線への直接影響はない。 |
| draft-body-editor | 10 分おき 24h | cadence 維持のまま `10:00-23:59 JST` だけ動かす | 60 runs/day and about 17.1 min/day saved | off-hours no-op を安全に除去 | 10:00 JST 前の repair が次 window まで待つ。速報 publish より優先度は低い。 |
| guarded-publish | `*/5` | phase 1 は維持。phase 2 なら off-hours だけ `*/10` or `*/15` を検討 | full `*/15` なら about 102.0 min/day saved | 直接 runtime は大きいが freshness risk も大きい | 105 auto publish の「5-15 分以内」期待を崩し得るため、この便では推奨しない。 |
| giants-realtime-trigger | `*/5` | 維持。`giants-weekday-daytime` と body 差分が取れた後に統合検討 | n/a | realtime ingestion freshness を維持 | `/run` service mainline なので、cost だけで落とすのは不可。 |

### non-5min 追加提案

| job | current | proposed | expected effect | risk |
|---|---|---|---|---|
| fact-check-morning-report | `0 * * * *` | `0 6,12,18 * * *` から開始。さらに許容なら `0 6 * * *` | 実行回数 24/day -> 3/day で 87.5% 削減 | 1 時間単位の report freshness が落ちる。ただし query は `since=yesterday` 固定。 |

## Cloud Logging 肥大 audit 結果

### 1 execution あたりの log 行数(sample)

| execution sample | entries/execution | log shape | verdict |
|---|---:|---|---|
| `guarded-publish-l4852` | 319 | multi-line stdout JSON + stderr GCS copy lines + system/audit | heavy |
| `publish-notice-8tjzg` | 4 | `[scan]` + `[summary]` + system/audit | light |
| `draft-body-editor-6zchr` | 3 | single structured `jsonPayload` summary + system/audit | light |
| `codex-shadow-fzm7p` | 3 | single structured `jsonPayload` summary + system/audit | light |

### 観測メモ

- broad sample (`resource.type=cloud_run_job` from `2026-04-27T15:00:00Z`) でも、目立ったのは `guarded-publish` の GCS copy 行だった。
- sampled Cloud Run Job logs では、Gemini prompt 全文や WP 記事 body 全文の dump は観測していない。
- ただし `guarded-publish` は per-post detail を pretty-print で流しており、`post_id`, `status`, `publish_link`, `hold_reason` を数百行単位で吐いている。
- `publish-notice` は payload 自体は小さいが、`emitted=0 sent=0` の 5 分実行が連続すると log noise になる。
- `draft-body-editor` / `codex-shadow` は 1 回あたりは軽いが、quiet-hours no-op を短 cadence で繰り返している。

## log 削減提案

### proposal 1: guarded-publish を summary-first にする

- Cloud Logging には 1 execution 1 summary line を基本とする。
- per-post detail は `published > 0`, `cleanup > 0`, `error > 0` のときだけ emit し、通常 skip-only 実行では count のみ残す。
- multi-line pretty JSON をやめ、single-line structured JSON に寄せる。
- `Copying file:///tmp/... to gs://...` のような成功時 transfer log は INFO 常時出力から外す。必要なら debug 相当へ退避。
- 目標: skip-only execution で `319 entries -> under 10 entries`。line count 基準で 95% 以上削減。

### proposal 2: publish-notice の no-op 実行を 1 行化する

- `emitted=0 sent=0 errors=0` のときは `[scan]` と `[summary]` を統合して 1 行にする。
- cursor detail は state file 側に寄せ、常時の verbose pair を減らす。

### proposal 3: draft-body-editor / codex-shadow の quiet-hours summary を圧縮する

- `candidates=0 put_ok=0 reject=0` なら compact one-line summary に縮める。
- `per_post_outcomes` は `edited > 0` または `reject > 0` のときだけ出す。
- same no-op summary が続く場合は `N` 回に 1 回だけ詳細出力する sampling も候補。

## Artifact Registry cleanup policy 提案

### current snapshot

- repository size: **21,820 MB**
- observed version counts:

| image | versions | oldest observed | newest observed | note |
|---|---:|---|---|---|
| `fetcher` | 102 | 2026-04-12 23:37 UTC | 2026-04-17 21:06 UTC | 累積の主因。legacy / adhoc tag が多い。 |
| `publish-notice` | 13 | 2026-04-26 17:17 UTC | 2026-04-27 21:30 UTC | active runtime image。 |
| `guarded-publish` | 8 | 2026-04-26 18:49 UTC | 2026-04-27 21:29 UTC | active runtime image。 |
| `draft-body-editor` | 4 | 2026-04-26 15:31 UTC | 2026-04-28 06:11 UTC | 小さめ。 |
| `codex-shadow` | 2 | 2026-04-26 19:02 UTC | 2026-04-26 19:26 UTC | 小さめ。 |

### cleanup policy

1. 先に live digest inventory を取る。
2. keep:
   - 現在 Cloud Run Job / Service が参照中の digest
   - 各 image の latest 5 tagged versions
   - 明示 rollback 用 tag
3. delete:
   - latest 5 + live digest + rollback tag 以外の tagged versions
   - untagged versions older than 3 days
   - `guarded-publish` / `publish-notice` / `draft-body-editor` / `codex-shadow` は 14 days を超えた tagged versions を age side でも掃除
   - `fetcher` は年齢ではなく **latest 5 + live digest keep を first pass の主ルール**にする。現状 102 versions が 2026-04-12 から 2026-04-17 に密集しており、age rule だけでは削れない
4. apply 手順は report-first / dry-run から始める。

### expected storage effect

- conservative でも **10GB-15GB** reclaim は見込める。
- `fetcher` 102 versions が主因なので、実際にはそれ以上削れる可能性がある。
- 円換算は billing export なしでは厳密化しないが、storage growth を止める意味では phase 1 の runtime 削減と別系統で効く。

## 推奨実装順 + 想定削減効果

円換算は **directional estimate only**。Cloud Billing export 未導入のため、ここでは `1500 円 alert` を基準に「runtime / logging / storage の寄与が大きい」という前提で幅を持って示す。

| order | action | why first | expected reduction |
|---|---|---|---|
| 1 | scheduler cadence governor phase 1 (`publish-notice */15`, `codex-shadow */15`, `draft-body-editor` active-window only, `fact-check-morning-report` 3/day) | live quality を落とさず no-op 実行を先に切れる | audited high-frequency runtime の about **32.4%** (`177.7 min/day` over `548.3 min/day`) を削減。monthly total では directionally **150-300 円/月** クラスを期待。 |
| 2 | guarded-publish logging compaction | `guarded-publish` だけ 1 execution 319 entries と突出 | guarded-publish lane の line count を **95%+** 圧縮見込み。Cloud Logging 側で directionally **tens to low hundreds 円/月** の防波堤。 |
| 3 | Artifact Registry cleanup policy | 21.82GB の repository 成長を止める | one-time **10GB-15GB** reclaim。継続 storage も頭打ち化。directionally **low hundreds 円/月 ceiling** の抑制。 |

## 次便 1 本

### candidate

- `230-A1 scheduler cadence governor phase 1 apply`

### intended scope

- live mutation は authenticated executor 前提
- first apply 対象:
  - `publish-notice-trigger`
  - `codex-shadow-trigger`
  - `draft-body-editor-trigger`
  - `fact-check-morning-report`
- keep:
  - `guarded-publish-trigger`
  - `giants-realtime-trigger`

### acceptance for the next ticket

- before/after cadence table がある
- rollback cron strings を併記する
- `guarded-publish` と `giants-realtime-trigger` を phase 1 で触らない
- src / tests / WP / mail / X を不変で保つ

## non-goals

- 自動公開停止
- Gemini 品質低下
- 5 分 cron の即時全面停止
- live GCP mutation の実行
- src / tests / config / WP / mail / X / existing ticket doc の編集
