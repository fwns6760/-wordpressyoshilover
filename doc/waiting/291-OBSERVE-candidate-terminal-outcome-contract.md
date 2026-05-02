# 291-OBSERVE-candidate-terminal-outcome-contract

| field | value |
|---|---|
| ticket_id | 291-OBSERVE-candidate-terminal-outcome-contract |
| priority | P0 equivalent(silent skip 再発防止の契約) |
| status | DESIGN_DRAFTED(read-only decomposition complete、impl hold) |
| owner | Claude(audit/draft) → Codex(将来 impl) |
| lane | OBSERVE |
| ready_for | 289 / 293 の live visibility 確認 + user 明示 GO。292 は standalone fire せず本 ticket 配下で durable ledger 方針を維持 |
| blocked_by | 289-OBSERVE live 可視化確認、293-COST live 可視化確認、user GO |
| doc_path | doc/waiting/291-OBSERVE-candidate-terminal-outcome-contract.md |
| created | 2026-04-30 |
| updated | 2026-05-03 |

## 目的

prepared candidate が **必ず以下 5 つの terminal outcome のいずれか** に落ち、silent に消えない契約を作る:

1. `publish`(WP に公開済 + publish mail 配信)
2. `review_notified`(review draft + 要 review mail 配信)
3. `hold_notified`(draft で残し + hold mail 配信)
4. `skip_accounted`(skip 理由が durable ledger/log に残り、理由 class に応じて mail or digest か ledger/log で追跡可能)
5. `error_accounted`(処理 error + error mail / digest / durable ledger)

`skip_accounted` の扱いは一律 mail にしない。

- `post_gen_validate` / `preflight_skip` は user-visible な mail or digest を持つ。
- `body_contract_fail` は通常 mail 不要、durable ledger/log で十分。
- `Cloud Logging だけ` で silent skip 解消済みとは扱わない。

## 背景

### 既知の silent skip 経路(本 ticket で潰す対象)
- post_gen_validate skip(289 は repo 実装済み、live visible confirm 待ち)
- body_contract_validate fail(292 相当。通常 mail 必須ではなく durable ledger/log で扱う)
- guarded-publish 経由前の rss_fetcher 内 skip 経路全般
- error 系(except handler で握りつぶし → log だけ → user silent)

### 真因
- candidate の終端状態が分散して定義されている
- 各 skip path で「log emit して終わり」が許されている
- mail 経路に乗らない skip = user silent

### 会議室 Codex 監査による発見(2026-04-30)
- post_gen_validate skip 22 件/trigger が user silent(289 で対処)
- body_contract_validate fail は candidate 消失源になり得るが、通常 mail ではなく ledger/log 契約で扱う(292 相当)
- preflight skip(282-COST)も flag ON 時 silent になり得る(293 で対処)

→ **個別の skip path を都度 fix するのではなく、契約として「terminal outcome は 5 つだけ」を確立**して再発防止する。

## 対象範囲

### 範囲内
- candidate lifecycle の terminal state 定義
- 各 terminal state に必ず **追跡可能な user-visible / ledger-visible 経路**が紐付く契約
- terminal state が記録される統一 ledger(または同等の永続 store)
- 全 skip path から terminal state への変換 helper
- 終端到達観測 KPI(prepared 数 = 5 terminal state 合計、 unaccounted = 0)

### 範囲外(個別 ticket で対応)
- post_gen_validate skip notification(289)
- body_contract_fail ledger/log wire の narrow 実装(292 相当。方針は本 ticket に吸収、実装便は別 fire)
- preflight_skip notification(293)
- source 追加(288 hold)
- weak title rescue(290 後続)

## 2026-05-03 read-only 原因分解(BUG-004+291 active subtask)

### evidence snapshot

- `src/rss_fetcher.py` には `post_gen_validate` と `preflight_skip` の history writer があり、`src/publish_notice_scanner.py` には対応 scan が実装済み。`tests/test_post_gen_validate_notification.py`、`tests/test_preflight_skip_notification.py`、`tests/test_publish_notice_scanner_class_reserve.py` は 2026-05-03 に local pass。
- `logs/post_gen_validate_history.jsonl` と `logs/preflight_skip_history.jsonl` はローカル copy に存在せず、289/293 の live ledger 可視化はこの環境では未観測。
- `logs/guarded_publish_history.jsonl` と `logs/publish_notice_queue.jsonl` のローカル更新時刻は 2026-04-30 13:27 JST 止まりで、現状の `publish=0` は guarded-publish より前段で候補が尽きている可能性が高い。
- `logs/sports_fetcher.log` の直近 42 本の `rss_fetcher_flow_summary` では `prepared_total=2`、`created_total=0`、`skip_reason=stale_postgame` が 42/42。
- `prepared_total=2` の 2 本はどちらも `lineup` で、`2026-04-30 17:54:42` と `2026-04-30 18:16:38` に `prepared_subtype_counts={\"lineup\": 1}` を残したまま `created=0`。
- 同じ期間の `postgame` 候補 `【巨人】阪神に3-2で勝利　岡田悠希が決勝打` は `strict_review_fallback:strict_contract_fail:close_marker` / `strict_insufficient_for_render` / `strict_validation_fail:schema_violation:key_events` を各 36 回、`strict_empty_response` 13 回、`strict_parse_fail:non_json_wrapper` 12 回。
- `gemini_call_skipped` は 17 件すべて `existing_publish_same_source_url` / `subtype=postgame`。
- `weak_title_rescued` は 12 件だが、確認できた strategy は `blacklist_phrase_message` 1 系統のみ。
- `title_player_name_review` は 24 件すべて `source_title=candidate_title=投手コメント整理` / `article_subtype=player`。
- `body_validator_reroll` は 100 件すべて `pregame` で、fail axis は `first_block_mismatch` + `block_order_mismatch` 固定。
- `body_validator_fail` / `body_validator_reroll` には `post_gen_validate` / `preflight_skip` 相当の history writer や scanner path が見当たらず、292 相当の durable ledger は repo 未実装。
- `subtype_reclassified_from_live_update` など 295 直結の local 実行証拠は現時点で未観測。
- `gemini_cache_backend_error` はこの sandbox の `gcloud` read-only 制約に起因する local ノイズであり、本 ticket の live publish-path unlock 根拠には使わない。

### ticket / guard / reason 単位の分解

| axis | current evidence | 主因判定 | unlock judgment |
|---|---|---|---|
| 277 title quality | `title_player_name_review=24`、すべて `投手コメント整理` | 二次原因。generic title のままでは戻せない | 人名未解決記事は unlock 対象外 |
| 289 `post_gen_validate` 可視化 | repo 実装と local tests はあるが、live ledger はこの環境で未観測 | 可視化不足は重要だが、直近 `created=0` の一次原因ではない | 289 契約は維持。unlock で隠さない |
| 290 weak title rescue | `weak_title_rescued=12`、strategy は `blacklist_phrase_message` のみ観測 | 部分効果のみ。publish=0 の主因ではない | deterministic title rescue だけ narrow 候補 |
| 293 preflight skip / duplicate | `gemini_call_skipped existing_publish_same_source_url=17` | duplicate 側の主因。flag を見える化しても duplicate 自体は残る | duplicate bypass 禁止。通知で隠さない |
| freshness / backlog | `stale_postgame=42/42`、`prepared_total=2` でも `created=0` | **現状の主因** | stale/backlog は維持。解除しない |
| 4-tier strict postgame | `close_marker=36` / `insufficient_for_render=36` / `schema_violation:key_events=36` / `strict_empty_response=13` / `strict_parse_fail=12` | **現状の主因** | strict postgame は閉じたまま。別 ticket で source facts を揃える |
| 292 body_contract durable ledger | `body_validator_fail` / `body_validator_reroll` は log のみ、durable history/scanner 不在 | `publish=0` の一次主因ではないが、silent skip 契約上は必須穴 | 通常 mail は増やさず ledger/state row で必ず残す |
| 295 subtype misclassify | `subtype_reclassified_from_live_update` 等の local 実行証拠なし | 現時点では未立証 | unlock 根拠に使わない |
| numeric guard | current window で dedicated numeric fail の優勢証拠なし | 主因では未観測 | numeric guard は維持。解除しない |
| placeholder | current window で placeholder 優勢証拠なし | 主因では未観測 | placeholder guard は維持。解除しない |
| source facts 不足 | postgame strict 失敗の実体は `schema_violation:key_events` | postgame 側の一次要因 | facts 不足記事を通さない |

### 現時点の結論

- `publish=0` は「guard 全体が厳しすぎる」より、`stale/duplicate` と `strict postgame fallback` による upstream starvation が主因。
- したがって rollback や gate 全体緩和ではなく、**postgame 以外の deterministic rescue だけを狭く戻す**方針が妥当。
- `strict_review_fallback:*` の `postgame`、`existing_publish_same_source_url`、`stale_postgame`、`title_player_name_unresolved` は unlock 対象にしない。

## 292 吸収方針(body_contract_fail durable ledger)

`292 body_contract_fail durable ledger` は **独立 ACTIVE にしない**。`BUG-004+291` の解除条件に含まれる必須サブタスクとして、この ticket に吸収する。

### 必須状態

- `body_contract_fail` 件数が後から集計できる
- fail reason が `ledger / log / state row` のいずれかに durable に残る
- `publish=0` 原因分解で `body_contract_fail` の寄与を count で切り出せる
- 通常 mail 量は増やさない

### durable ledger の最小契約

- record_type: `body_contract_fail`
- skip_layer: `body_contract`
- required fields:
  - `ts`
  - `source_url`
  - `source_url_hash`
  - `source_title`
  - `generated_title`
  - `category`
  - `article_subtype`
  - `fail_axes`
  - `expected_first_block`
  - `actual_first_block`
  - `missing_required_blocks`
  - `has_source_block`
  - `stop_reason`
  - `terminal_state=skip_accounted`
- storage priority:
  - local durable jsonl
  - existing GCS mirror / state row があるなら同一 key family に append
  - Cloud Logging 単独は不可

### 通知方針

- per-post の通常 mail は **出さない**
- 必要なら既存 digest / ops summary の count 行に吸収する
- publish-notice の class reserve は増やさない
- dedupe key は `source_url_hash + article_subtype + sorted(fail_axes)` の 24h 窓

### 292 相当の acceptance

- `body_contract_fail` が log-only で消えない
- ledger だけで「何件 / どの fail axis か」が答えられる
- `publish=0` 原因分解で `body_contract_fail` を他理由と分離できる
- mail volume / Gemini call / source 数 / SEO 設定は増えない

## user-visible / ledger-visible な受け入れ条件

1. **完全性**: prepared candidate 全部が 5 terminal state のいずれかに分類される(unaccounted=0、 daily KPI 集計可能)
2. **通知 / ledger**:
   - `publish` / `review_notified` / `hold_notified` は mail or digest で届く
   - `post_gen_validate` / `preflight_skip` は user-visible mail or digest で追える
   - `body_contract_fail` は durable ledger/log/state row に残り、silent drop にならない
   - `body_contract_fail` は per-post 通常 mail にしない
3. **dedup**: 同 source_url_hash + 同 terminal state は 24h 1 度(通知爆発防止)
4. **subject 識別**: 件名 prefix で terminal state 判別可能(`【公開済｜...】` / `【要review｜...】` / `【hold｜...】` / `【要review｜post_gen_validate】` 等)
5. **rollback**: env flag で全契約を OFF できる(問題発生時即座に通知導線元に戻せる)
6. **観察**: GCP Logging で `event=candidate_terminal_outcome` が emit、24h で集計可能
7. **silent ゼロ**: 任意の rss_fetcher trigger で terminal state の無い prepared candidate=0 assert

## 必須デグレ試験(設計時の契約、impl 時に test 化)

### A. 完全性
- [ ] prepared = sum(terminal_state) assert(任意の trigger で)
- [ ] 任意の skip path が terminal state を skip しない fixture(unaccounted candidate 0)

### B. 既存通知導線維持
- [ ] publish 通知従来通り届く
- [ ] review/hold 通知従来通り届く
- [ ] 267-QA dedup 維持
- [ ] post_gen_validate 通知(289)維持
- [ ] body_contract_fail ledger/log 契約(292)維持
- [ ] preflight_skip 通知(293)維持(293 完遂後)
- [ ] body_contract_fail を新しい通常 mail class にしない

### C. 通知爆発防止
- [ ] 全 terminal state に共通 dedup(source_url_hash + terminal_state、24h)
- [ ] 1 run cap(289 max_per_run cap と統合)
- [ ] cap 超過時の持ち越し log emit、silent drop 0

### D. 安全系
- [ ] hard_stop 維持(死亡/重傷/救急/意識不明)
- [ ] duplicate guard 維持(263-QA)
- [ ] スコア矛盾 publish しない
- [ ] 一軍/二軍混線 publish しない

### E. 環境不変(全 ticket 共通)
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] SEO/noindex/canonical/301 不変
- [ ] X 自動投稿 path 不変
- [ ] Team Shiny From 不変
- [ ] Scheduler 頻度変更なし
- [ ] 新 subtype 追加なし

### F. コスト
- [ ] Gemini call 0 増(本契約は metadata layer のみ、LLM 呼び出し 0)
- [ ] 229-COST cache_hit ratio 維持

## narrow publish-path unlock contract(設計のみ)

この ticket で戻してよいのは、**global gate を緩めずに high-confidence candidate だけ publish 判定へ戻す経路**だけ。

### publish path に戻してよい最小条件

- YOSHILOVER 対象
- `source_url` あり
- `subtype` / `template_key` が high confidence
- `numeric guard` pass
- `body_contract` pass
- placeholder なし
- silent skip なし
- title が最低限「何の記事か分かる」
- `review` / `hold` 理由なし

### 現時点で narrow unlock 候補にしてよい class

- `lineup` のような structure が固定で、`source_url` と template が明確な non-postgame candidate
- `manager` / `player quote` 系のうち、`source_title` に actor + event があり、`290` 型の deterministic title rescue だけで通せる candidate
- `related_info_escape` / `blacklist_phrase` のうち、source facts を増やさず title だけ具体化できる candidate

### 現時点で unlock 対象外

- `strict_review_fallback:*` を踏んでいる `postgame`
- `existing_publish_same_source_url`
- `stale_postgame`
- `title_player_name_unresolved`
- `body_contract_fail`
- `numeric guard fail`
- placeholder 残存
- `subtype misclassify` 疑いが解消していない candidate

### narrow unlock brief(Codex 実装便を切る時の scope)

- write_scope:
  - `src/weak_title_rescue.py`
  - `src/title_validator.py`
  - `src/rss_fetcher.py`
  - `tests/test_weak_title_rescue.py`
- acceptance pack:
  - high-confidence non-postgame candidate だけが既存 publish/review path へ戻る
  - `strict_review_fallback:*` の `postgame` は 1 件も unlock しない
  - `body_contract_fail` は ledger-only 契約のまま
  - `post_gen_validate` / `preflight_skip` 通知導線は不変
- do-not-touch:
  - `src/guarded_publish_runner.py`
  - `src/gemini_preflight_gate.py`
  - `src/body_validator.py`
  - `src/publish_notice*.py`
  - SEO / noindex / Scheduler / env / source inventory / Gemini budget

### 実装する場合の rollback target

- `src/weak_title_rescue.py`
- `src/title_validator.py`
- `src/rss_fetcher.py` の weak-title rescue integration

`guarded_publish_runner.py`、`gemini_preflight_gate.py`、SEO、Scheduler、mail cap、source 追加は rollback target に含めない。そこを触る unlock は本 ticket の範囲外。

### stop condition

- unlock candidate が `review` / `hold` 理由を残したまま publish path に入る
- `strict_review_fallback:*` の `postgame` が 1 件でも unlock 対象に混ざる
- stale / duplicate / placeholder / body_contract / numeric guard のどれかを bypass する必要が出る
- mail 量、Gemini call、source 数、SEO 設定の増加を前提にしないと成立しない
- non-YOSHILOVER source が unlock 候補へ流れ込む

## HOLD 解除条件

以下 **全部** 満たした時点で user 判断 + 子 ticket impl 起票:

1. 289-OBSERVE の live visibility が確認され、post_gen_validate skip が user-visible になった
2. 292 相当の方針がこの ticket 内で確定し、body_contract_fail が durable ledger/log で追跡可能になった
3. 293-COST の live visibility が確認され、282-COST flag ON 前提が整う
4. user 明示 GO

## owner

- Claude: 設計 + 子 ticket 起票
- Codex: 統一 ledger / helper / 各 skip path の terminal state 接続 impl
- user: 受け入れ条件 + GO/HOLD 判断

## 次に実装してよいタイミング

- 上記 HOLD 解除条件 4 つ全部達成後
- 289 / 292 / 293 を経た上で「個別通知 or ledger → 統一契約」へ昇華するフェーズ
- 単独先行は **禁止**(個別 skip 可視化が確立する前に契約だけ作っても、原因を隠してしまう)

## 不変方針(継承)

- 本 ticket は **設計 / 契約定義のみ**、本 task では impl しない
- 既存 publish/review/hold/post_gen_validate 通知導線壊さない
- `body_contract_fail` は通常 mail 必須にしない
- Cloud Logging 単独で可視化扱いしない。少なくとも durable ledger か user-visible path のどちらかを要求する

## Folder cleanup note(2026-05-03)

- 本 ticket は `waiting/` 維持。実装 fire はまだしない。
- 今回の更新は read-only 原因分解、292 durable ledger 方針の吸収、unlock brief の固定のみ。deploy / env / Scheduler / SEO / WP 状態変更は 0。
- 289 / 293 の live 可視化確認と user GO が揃うまで、narrow unlock も設計止まりにする。
