# 300-COST source-side guarded-publish 再評価 cost analysis

## scope

- read-only / doc-only
- `src/` / `tests/` edit 0
- impl 0
- source trace + cost estimate + deferred design only

## TL;DR

- `hold_reason=backlog_only` の fresh `ts` 再 append は `src/guarded_publish_runner.py` の `run_guarded_publish()` 内で発生している。
- 直接の trigger は `backlog_only` publishable entry が `backlog_narrow` 不適格だったケースで、`status=skipped` / `error=backlog_only` / `hold_reason=backlog_only` row を毎回作る。
- しかも `_history_attempted_post_ids()` は `sent` と recent `refused` しか dedup しないため、`skipped/backlog_only` は次回 `*/5` run でも再評価され続ける。
- ただし 300-COST 単独では Cloud Scheduler cadence は不変なので **Cloud Run execution count/day は 288 のまま**。減るのは history growth と publish-notice scanner の入力件数。
- 追加の重要所見: `bin/guarded_publish_entrypoint.sh` は `guarded_publish_history.jsonl` を run ごとに **object 全体 upload** している。よって source-side append 抑制だけでは **288 uploads/day** 自体は減らない。

## 1. source trace: backlog_only 再評価と fresh ts append

### 1-1. 判定点

| file:line | function | condition | behavior |
|---|---|---|---|
| `src/guarded_publish_runner.py:1201-1230` | `_iter_publishable_entries()` | evaluator report の `green/yellow` entry を publishable 候補化。`backlog_only` flag をそのまま保持 | downstream で backlog branch に入る元データを作る |
| `src/guarded_publish_runner.py:1269-1314` | `_backlog_narrow_publish_context()` / `_backlog_narrow_publish_eligible()` | subtype / age / allowlist / unresolved fallback 条件で「古いが narrow publish 許可」か判定 | `None` なら backlog_only hold 側へ落ちる |
| `src/guarded_publish_runner.py:1317-1321` | `_is_backlog_entry()` | `entry.backlog_only == True` または freshness age が cutoff 超え | backlog 扱い確定 |
| `src/guarded_publish_runner.py:2095-2143` | `run_guarded_publish()` | `publishable_entries` の各 entry で `backlog_only == True` かつ `_backlog_narrow_publish_context(...) is None` | `refused += {"reason":"backlog_only"}`、`live=True` なら `live_history_rows` に `status=skipped` / `error=backlog_only` / `hold_reason=backlog_only` row を積む |
| `src/guarded_publish_runner.py:2423-2426` | `run_guarded_publish()` | `live=True` 時に `live_history_rows` がある | 上で積んだ skipped row を `history_path` へ `_append_jsonl()` |

### 1-2. 毎 trigger 再評価が続く理由

| file:line | function | effect |
|---|---|---|
| `src/guarded_publish_runner.py:1108-1128` | `_history_attempted_post_ids()` | attempted 扱いにするのは `status=="sent"` と recent `status=="refused"` のみ。`status=="skipped"` は dedup 対象外 |
| `src/guarded_publish_runner.py:1934-1937` | `run_guarded_publish()` | 毎 run 冒頭で `history_rows` を読み、`attempted_post_ids` を計算 |
| `src/guarded_publish_runner.py:2050-2053` | `run_guarded_publish()` | publishable entry は `attempted_post_ids` に入っていない限り次回も再び候補化 |

結論:

- `backlog_only` row は `skipped` なので attempted に入らない。
- そのため **同じ old backlog post が `*/5` trigger ごとに再評価され、同条件なら fresh `ts` row が再 append** される。

### 1-3. related path: backlog_deferred_for_fresh

`hold_reason=backlog_only` そのものではないが、同系統の old backlog 再 append が別 branch にもある。

| file:line | function | condition | behavior |
|---|---|---|---|
| `src/guarded_publish_runner.py:2145-2156` | `run_guarded_publish()` | fresh entry が 1 件でもある時、backlog entry は `deferred_backlog_entries` に退避 | backlog pool を後回し |
| `src/guarded_publish_runner.py:2162-2194` | `run_guarded_publish()` | deferred backlog を live run で処理 | `status=skipped` / `hold_reason=backlog_deferred_for_fresh` row を毎回 append |

これは 300-COST の直接対象外だが、「古い backlog に fresh `ts` が繰り返し付く」系統として同じ cost surface に乗る。

## 2. `*/5` trigger ごとの cost surface

### 2-1. Cloud Run execution count/day

source:

- `doc/done/2026-04/160-deployment-notes.md:117-135`
- `docs/handoff/session_logs/2026-04-30_next_action_queue.md:40`

fact:

- `guarded-publish-trigger` cadence は `*/5 * * * *`
- 1 時間 12 trigger
- 24 時間で **288 executions/day**

300-COST source-side option だけで変わるもの:

- history growth
- publish-notice scan input
- runner 内 JSON append / local I/O

300-COST source-side option だけで **変わらない**もの:

- Scheduler cadence
- Cloud Run Job invocation count/day
- container startup count/day

したがって execution count/day ベースの cost は:

- **current**: 288/day
- **after Option C only**: 288/day
- 削減率: **0%**

### 2-2. `guarded_publish_history.jsonl` append growth

observed evidence:

- `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md:53-54`
  - ledger size: `28.81 MiB`
  - tail 200 records: `103` unique `post_id`
  - same post_id が `09:30:45 JST` と `09:35:47 JST` に 2 回出現
- `docs/handoff/codex_responses/2026-05-01_codex_a_storm_verify.md:74`
  - `status=skipped`, `judgment=yellow`, `hold_reason=backlog_only` の再 append を確認

row size estimate:

- `_history_row()` shape で `backlog_only` skipped row を JSON serialize すると約 **359 bytes/row** (`ensure_ascii=False`, newline 込み)
- user 既知の rough estimate `~100 rows/trigger` を使うと:
  - `100 rows/trigger * 288 trigger/day = 28,800 rows/day`
  - `28,800 * 359 bytes ≒ 10.3 MB/day` raw append growth

安全側の表現:

- **rough range**: 約 `7-10 MB/day`
- 理由: 実 row により `freshness_source`, duplicate fields, error text 長が少し揺れる

### 2-3. 重要所見: GCS write は append だけではない

source:

- `bin/guarded_publish_entrypoint.sh:45-67`
- `src/cloud_run_persistence.py:137-175` (`GCSStateManager.upload()` / `with_state()`)

fact:

1. run 開始時に `guarded_publish_history.jsonl` を download
2. local file に row append
3. run 終了時に `gcloud storage cp "${HISTORY_PATH}" "${GCS_PREFIX}/guarded_publish_history.jsonl"` で **file 全体**を再 upload

つまり 300-COST source-side だけで減るのは:

- local history append row 数
- file growth slope
- publish-notice 側 incremental scan の new-row count

一方で残るもの:

- **GCS object upload count/day = 288**
- whole-file upload pattern

live size `28.81 MiB` をそのまま使うと、whole-file upload volume は理論上:

- `28.81 MiB * 288 ≒ 8297 MiB/day`
- 約 **8.1 GiB/day**

このため 300-COST の効果は本当にあるが、**GCS upload op/transfer を根本的に削る ticket ではない**。真に GCS write を大きく下げるには entrypoint 側の「unchanged file は upload skip」も別途必要。

### 2-4. downstream parse/load cost

source:

- `src/publish_notice_scanner.py:523-565`
- `src/publish_notice_scanner.py:790-852`
- `src/publish_notice_scanner.py:966-982`

fact:

- publish-notice は guarded history を reverse scan し、cursor/newest `ts` より新しい row だけ扱う
- したがって source-side で unchanged backlog_only row の append を止めると、publish-notice はその row を **次 run で見なくなる**
- これは mail storm 抑止には有効

## 3. candidate disappearance risk

### 3-1. current behavior の risk

### A. `backlog_only` 自体は attempted dedup に入らないので、再評価が publish chance を保持している

source:

- `src/guarded_publish_runner.py:1108-1128`
- `src/guarded_publish_runner.py:2050-2053`

meaning:

- `skipped/backlog_only` は次回も再評価される
- 将来 source/title/body/meta が変わって `backlog_only` でなくなれば publish path に戻れる

したがって **current source semantics は「古い候補のしつこい再通知」は起こすが、「将来の publish chance」は残している**。

### B. backlog starvation は既にある

source:

- `src/guarded_publish_runner.py:2145-2156`
- `src/guarded_publish_runner.py:2162-2194`

meaning:

- fresh entry がある限り backlog は `backlog_deferred_for_fresh` で後回し
- fresh stream が切れないと old backlog は事実上ずっと publish されない

これは 300-COST で新しく作る risk ではなく、現行 runner に既にある「publish chance の遅延/飢餓」。

### 3-2. Option C-narrow の risk

proposal under review:

- `status / judgment / hold_reason` が前回 row と同じ
- かつ `hold_reason=backlog_only`
- なら fresh `ts` row を append しない
- flag default OFF

expected safe side:

- runner 自体の再評価は継続できる
- `attempted_post_ids` も `skipped` を見ないので、**source-side publish chance 自体は失わない**
- old-candidate repeated mail/review pool だけを細らせられる

residual risk:

1. post 本文や source URL が変わっても、`status/judgment/hold_reason` が同じなら downstream delta consumer は変化を見ない
2. `publish_notice_scanner` は cursor 後の新 row ベースなので、unchanged backlog_only の「定期 reminder」は消える
3. 将来別 consumer が `guarded_publish_history.jsonl` の fresh `ts` を backlog pulse として使っていた場合、その consumer の前提は崩れる

blast radius を user 指定どおり狭めるなら:

- **`hold_reason=backlog_only` 限定**
- **unchanged real review / cleanup_required は従来どおり再 append 維持**

この narrow 化なら、「real review を再通知したい」経路は残しつつ、storm root-cause だけ狙える。

## 4. deferred impl sketch (this ticket does not implement)

### 4-1. insertion point

最小の差し込み点は `run_guarded_publish()` の live skipped backlog branch:

- `src/guarded_publish_runner.py:2118-2133`
- `src/guarded_publish_runner.py:2423-2426`

impl image:

1. run 冒頭の `history_rows` から post_id ごとの latest row を index 化
2. `backlog_only` skipped row を作る前に latest row を比較
3. flag ON かつ latest row が unchanged なら `live_history_rows.append(row)` を skip
4. それ以外は現状通り append

### 4-2. narrow comparison contract

最低限 compare する tuple:

- `status`
- `judgment`
- `hold_reason`

必要なら safety 追加候補:

- `is_backlog`
- `freshness_source`

`real review unchanged` は比較対象にしても append skip しない。

### 4-3. flag proposal

env proposal:

- `ENABLE_GUARDED_PUBLISH_IDEMPOTENT_BACKLOG_HISTORY=0` default

behavior:

- `0` or unset: 現行挙動
- `1`: `hold_reason=backlog_only` unchanged 時だけ append skip

## 5. cost reduction estimate

user rough formula:

- current: `~100 entries/trigger * 12 trigger/h * 24h = ~28,800 records/day`

source-side Option C-narrow estimate:

- unchanged `backlog_only` が大半なら、append 対象は
  - 新しい `backlog_only`
  - `hold_reason` change
  - `judgment` change
  - `status` change
  - real review / cleanup / sent / refused
  のみになる

therefore:

- `28,800 records/day` → **数百/day 規模**は妥当
- raw append growth: 約 `7-10 MB/day` → **`0.1-0.3 MB/day` 前後**まで低下見込み

ただし重要な caveat:

- **Cloud Run executions/day は 288 のまま**
- **GCS whole-file upload count/day も 288 のまま**
- したがって 300-COST 単独の削減対象は
  - history growth
  - scanner input
  - downstream mail/review storm risk
 であり、GCS transfer op まで大きく削り切るには entrypoint 別 ticket が必要

## 6. test plan(after impl; design only)

target files:

- `tests/test_guarded_publish_runner.py`
- 必要なら `tests/test_publish_notice_scanner.py`

recommended cases:

1. `flag OFF`: same `backlog_only` candidate を 2 run 流すと history row が 2 本増える
2. `flag ON`: same `backlog_only` candidate を 2 run 流すと 2 回目は history row 増加 0
3. `flag ON`: same post_id でも `hold_reason` が `backlog_only -> backlog_deferred_for_fresh` に変わったら append する
4. `flag ON`: same post_id でも `judgment/status` 変化時は append する
5. `flag ON`: `review` / `cleanup_required` unchanged は **append 維持**する
6. scanner regression: source-side no-new-row 時、`publish_notice_scanner` の guarded cursor が head に張り付き `cursor_at_head` になるが 289 post-gen-validate path は不変
7. summary regression: `history_after`, `queue.jsonl`, `publish_notice_history.json` の既存 format 不変

success criteria:

- 300-COST flag ON でも `backlog_only` 以外の review/cleanup mail path は不変
- same post_id の old-candidate storm pool が publish-notice に再注入されない
- `attempted_post_ids` semantics 不変

## 7. rollback plan

repo / runtime rollback:

1. env `ENABLE_GUARDED_PUBLISH_IDEMPOTENT_BACKLOG_HISTORY=0` or remove
2. guarded-publish image を pre-300 digest へ戻す
3. scheduler / WP / GCS object schema は触らないので data migration 不要

why rollback is simple:

- history schema 追加なし
- `guarded_publish_history.jsonl` の既存 row format 不変
- flag OFF で即 baseline 挙動に戻せる

## key findings for Claude

1. root-cause source は `run_guarded_publish()` の `2095-2143` + `2423-2426`、補助条件は `_history_attempted_post_ids()` が skipped を dedup しないこと
2. Option C-narrow は「mail storm root-cause」には効くが、**Cloud Run execution count/day=288 は減らない**
3. current code でも old backlog starvation(`backlog_deferred_for_fresh`)は既にあるため、300-COST は「publish chance を新たに消す」より「existing reminder semantics を弱める」変更
4. GCS write を本当に削るには source-side idempotent append に加え、`bin/guarded_publish_entrypoint.sh` の unchanged-upload skip が別途必要
5. したがって Claude 次 action は、300-COST Pack では「何が減る/減らないか」を user に明示したうえで、298 安定後 narrow deploy か別途 persistence optimization ticket を分けて起票すること
