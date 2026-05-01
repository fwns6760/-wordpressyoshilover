# 300-COST source-side guarded-publish 再評価 cost reduction Pack draft

Date: 2026-05-01 JST  
Lane: Codex A(round 2, doc-only)  
Scope: Pack draft only, no `src/` / `tests/` / env / gcloud / WP / scheduler mutation

## 1. 設計 summary(Lane B 解析要約)

- 既存 read-only 解析の正本は [2026-05-01_300_COST_source_analysis.md](/home/fwns6/code/wordpressyoshilover/docs/handoff/codex_responses/2026-05-01_300_COST_source_analysis.md)。
- root cause は `src/guarded_publish_runner.py:2095-2143` と `src/guarded_publish_runner.py:2423-2426`。
  - `backlog_only` 候補が backlog narrow 不適格だと、live run ごとに `status=skipped` / `error=backlog_only` / `hold_reason=backlog_only` row を fresh `ts` で append する。
- 再評価 loop を維持している補助条件は `src/guarded_publish_runner.py:1108-1128` の `_history_attempted_post_ids()`。
  - dedup 対象は `sent` と recent `refused` のみ。
  - `skipped/backlog_only` は attempted に入らないので、`*/5` ごとに同じ post が再評価される。
- その結果、raw append growth は rough に `~100 rows/trigger * 288 trigger/day = ~28,800 rows/day`。
  - 1 row 約 359 bytes 換算で `7-10 MB/day` 規模の history growth になりうる。
- Option C-narrow が効く範囲はこの repeated append の抑制。
  - unchanged `backlog_only` の再 append を止めれば、append 対象は新規 backlog / state change / sent / refused / real review 系に絞られ、数百 rows/day 規模まで圧縮見込み。
- ただし source-side だけでは次は減らない。
  - Cloud Run execution count/day = `288` のまま。
  - GCS object upload count/day = `288` のまま。
  - `bin/guarded_publish_entrypoint.sh` の whole-file upload skip は別 ticket。
- INCIDENT_LIBRARY の結論とも整合する。
  - 298 は sink-side cutoff で第二波 mail storm を止血したが、source-side semantics は未変更。
  - 300-COST は root-cause eradication を deferred 管理している future ticket。

## 2. impl 案(設計のみ、未着手)

### 2-1. Option C-narrow

- default OFF の env flag を導入する。
  - `ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY=1` で活性化。
- live skipped backlog branch で、直前 latest row と今回 row を比較する。
- 比較 tuple は最小で以下。
  - `status`
  - `judgment`
  - `hold_reason`
- 条件を全部満たすときだけ history append を skip する。
  - `hold_reason=backlog_only`
  - latest row が存在
  - `status / judgment / hold_reason` が前回 record と同一
- 上記以外は現状通り append する。

### 2-2. blast radius 局所化

- skip 対象は **`hold_reason=backlog_only` かつ unchanged** に限定する。
- `real review` / `cleanup_required` / `backlog_deferred_for_fresh` / `refused` / `sent` は今回の narrow 化対象にしない。
- 特に `real review unchanged` は引き続き再 append を維持する。
  - 理由: review reminder semantics を壊さず、mail storm root-cause だけを狙うため。

### 2-3. 期待効果

- `backlog_only` unchanged の fresh `ts` append が消える。
- `guarded_publish_history.jsonl` の row growth は `28,800/day` から数百/day 規模へ低下見込み。
- publish-notice scanner の new-row input も同率で減る。
- 一方で、Cloud Scheduler cadence / Cloud Run executions / GCS object upload count は不変。

## 3. test plan(impl 後に実施、本 ticket は設計のみ)

1. `backlog_only unchanged`
   - 条件: 同一 post_id、`status / judgment / hold_reason` 不変、flag ON。
   - 期待: `ts` 再 append skip。
2. `real review unchanged`
   - 条件: review 系 hold が不変、flag ON。
   - 期待: 従来通り append 維持。300-COST の影響なし。
3. `backlog_only changed`
   - 条件: 同一 post_id でも `status` または `judgment` または `hold_reason` が変化。
   - 期待: `ts` append。
4. `flag OFF baseline`
   - 条件: `ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY` unset/0。
   - 期待: 挙動 100% 不変。same backlog_only candidate は run ごとに append。
5. `scanner consumer compatibility`
   - 条件: source-side no-new-row でも 298 ledger / guarded cursor / queue/history format が維持されること。
   - 期待: `publish_notice_scanner` は `cursor_at_head` 側へ進むだけで、289/298 系 consumer と整合。

## 4. Acceptance Pack 18 項目 final draft

## Acceptance Pack: 300-COST-source-side-reevaluation-reduction

- **Decision**: `HOLD`
- **Requested user decision**: `298-Phase3` 安定確認後に、300-COST narrow impl + test + guarded-publish deploy を進めてよいか
- **Scope**: `guarded_publish_runner` の source-side idempotent history append narrow 化、flag default OFF、target は `hold_reason=backlog_only` unchanged 時のみ
- **Not in scope**: `publish-notice` sink-side 298 logic、`rss_fetcher`、WP mutation、Scheduler cadence 変更、Secret/env 追加以外の live routing change、`bin/guarded_publish_entrypoint.sh` whole-file upload skip、X、dashboard redesign
- **Why now**: `298` は sink-side で mail storm を止めたが、source-side root cause は未解消。24h 安定確認後に narrow に戻す前提整理として、先に Pack を固定しておく価値がある
- **Preconditions**:
  - `298-Phase3` deploy 後 24h 安定が通過していること
  - INCIDENT_LIBRARY の「sink-side flag ON 維持」方針を崩さないこと
  - `production_health_observe` で silent skip / mail routing / review path に異常が無いこと
  - 本 Pack を Claude が review し、future user GO timing で提示できること
- **Cost impact**: Gemini call `0` 増、token `0` 増、Cloud Build `1` 回。history raw append / scanner input は `28,800 rows/day -> 数百 rows/day` 見込みで `-90%` 規模。Cloud Run executions/day=`288` と GCS object upload count/day=`288` は不変
- **User-visible impact**: 通常 mail / WP / dashboard の意図的変更はなし。source-side cost と history growth を削るだけで、通常の publish/review UX は維持する
- **Rollback**: まず `--remove-env-vars=ENABLE_GUARDED_PUBLISH_IDEMPOTENT_HISTORY` で flag を外す。必要なら guarded-publish image を pre-300 digest へ戻す。history schema 変更は入れないので data migration 不要
- **Evidence**:
  - source evidence: `src/guarded_publish_runner.py:2095-2143` + `2423-2426` が repeated skipped append 点、`_history_attempted_post_ids()` が skipped 非 dedup
  - cost evidence: current rough growth `~28,800 rows/day`、Option C-narrow で数百/day 規模見込み
  - boundary evidence: Cloud Run execution count/day と GCS object upload count/day は 300-COST 単独では減らない
  - safety evidence: `hold_reason=backlog_only` unchanged 限定にして `real review unchanged` は従来通り再 append
- **Stop condition**: 真の review semantics 変化、silent skip 増、mail 通知 path 影響、unexpected candidate disappearance、unchanged 判定の誤爆で review/cleanup reminder が痩せる兆候
- **Expiry**: `298-Phase3` stable + 24h 確認後の次 review timing まで。有効期限超過時は source analysis と live state を再確認して Pack refresh
- **Recommended decision**: `HOLD`
- **Recommended reason**: 300-COST は root-cause に効くが、いまは 298 sink-side 安定維持が優先。source-side semantics を触るのは 298 安定確認後に限定し、今日は Pack draft のみで止めるのが順序として正しい
- **Gemini call increase**: `NO`
- **Token increase**: `NO`
- **Candidate disappearance risk**: `NO`
- **Cache impact**: `NO`
- **Mail volume impact**: `NO`

User reply format: 「GO」/「HOLD」/「REJECT」のみ

## 5. 注意事項

- 300-COST source-side だけでは `*/5` trigger 自体は変わらない。
  - Cloud Run execution count/day=`288` は減らない。
- GCS upload count/day の削減は別 ticket。
  - `bin/guarded_publish_entrypoint.sh` の unchanged whole-file upload skip が必要。
- この ticket の説明では「何が減るか / 何が減らないか」を必ず分けて提示する。
  - 減るもの: history row growth、scanner input、old backlog repeated append。
  - 減らないもの: Scheduler cadence、Cloud Run execution count、GCS object upload count。

## 6. Claude next action

1. `300-COST` を `FUTURE_USER_GO` のまま維持し、本 doc を Pack reference として紐付ける。
2. `298-Phase3` 安定 24h 通過後に、本 draft を user-facing 1 行 judgment へ圧縮できる状態にする。
3. impl fire 時は `hold_reason=backlog_only` unchanged 限定を厳守し、persistence whole-file upload skip は別 ticket に分離する。
