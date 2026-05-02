# 292-OBSERVE-body-contract-fail-notification

| field | value |
|---|---|
| ticket_id | 292-OBSERVE-body-contract-fail-notification |
| priority | P0 equivalent(silent skip 第 2 経路) |
| status | DESIGN_DRAFTED(parent=BUG-004+291、standalone fire 禁止) |
| owner | Claude(audit/draft) → Codex(将来 impl) |
| lane | OBSERVE |
| ready_for | 291 親契約の user GO 後に narrow impl 起票。単独 ACTIVE 化しない |
| blocked_by | 291 親契約 hold、289/293 live visibility 確認、user GO |
| doc_path | doc/waiting/292-OBSERVE-body-contract-fail-notification.md |
| created | 2026-04-30 |
| updated | 2026-05-03 |

## 目的

`body_contract_validate` fail を **log だけで終わらせず**、`BUG-004+291` 配下の durable ledger/log/state row 契約へ接続する。
silent skip 第 2 経路を潰すが、**通常 mail を増やすことは目的にしない**。

## 親 ticket との関係

- 本 ticket は **独立 ACTIVE ではない**
- `BUG-004+291` の解除条件に含まれる必須サブタスク
- 方針の正本は `doc/waiting/291-OBSERVE-candidate-terminal-outcome-contract.md`
- ここでは `body_contract_fail` 専用の durable ledger 要件だけを保持する

## 背景

### 会議室 Codex 監査(2026-04-30)
- 289 で post_gen_validate skip を通知化対象にしたが、`body_contract_validate` fail は別 path
- body_contract_fail も `post_gen_validate_history.jsonl` には乗らない可能性高い
- このままだと **silent skip の温床**(289 で 1 経路潰しても、別経路で同じ穴ができる)

### 現状の body_contract_validate(audit 結果、`src/body_validator.py` 系)
- `_validate_farm_result_anchor` / `_validate_farm_lineup_anchor` 等の fail_axes 累積
- `farm_result_player_unverified` / `farm_result_numeric_fabrication` / `farm_lineup_lineup_missing` 等の hard fail 系列
- これらが trip すると body 不正判定 → 記事化 skip
- 一部は guarded-publish の `hard_stop_*` に乗るが、**rss_fetcher 内 body 段階で trip するケース** は ledger 不在の可能性

### 真因
- body_contract validate は src/body_validator.py 単独で動作、ledger 出力 helper 無い
- guarded-publish 到達前 skip = `guarded_publish_history.jsonl` に書かれない
- post_gen_validate(289 ledger)とも別 path = 289 ledger にも書かれない可能性
- → user silent

## 対象範囲

### 範囲内
- body_contract_validate fail event の永続 ledger 出力
- record_type=`body_contract_fail` / skip_layer=`body_contract` の durable row 契約
- fail_axes / stop_reason / block-order 情報が後から引ける schema
- local jsonl + GCS mirror or state row など、Cloud Logging 単独ではない永続経路
- `publish=0` 原因分解で count できる集計前提

### 範囲外
- body_contract 判定 logic 緩和(救済は別 ticket、本 ticket は通知のみ)
- post_gen_validate 通知(289 既出)
- preflight_skip 通知(293)
- per-post 通常 mail 新設
- publish-notice class reserve 追加

## durable ledger の最小契約

- required fields:
  - `ts`
  - `record_type=body_contract_fail`
  - `skip_layer=body_contract`
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
- dedupe key: `source_url_hash + article_subtype + sorted(fail_axes)` の 24h 窓
- terminal state: `skip_accounted`

## user-visible な受け入れ条件

1. body_contract fail → durable ledger record(env flag ON 時)
2. ledger or state row だけで件数と fail reason を後追い確認できる
3. `publish=0` 原因分解で body_contract 系件数を独立集計できる
4. per-post 通常 mail は増やさない
5. env flag default OFF、rollback path が明確
6. silent body_contract_fail = 0(全 fail event が ledger/log/state row のどれかに到達 assert)

## 必須デグレ試験

### A. silent skip 解消
- [ ] fixture: farm_result_player_unverified fail → ledger record
- [ ] fixture: farm_result_numeric_fabrication fail → 同上
- [ ] fixture: farm_lineup_lineup_missing fail → 同上
- [ ] fixture: 任意の body_contract fail event → silent 0 assert

### B. 既存通知導線維持
- [ ] 289 post_gen_validate 通知不変
- [ ] 293 preflight_skip 通知不変
- [ ] publish/review/hold 通知従来通り(267-QA dedup 不変)
- [ ] publish-notice class reserve を増やさない
- [ ] guarded_publish_history scan 不変

### C. 通知爆発防止
- [ ] 同 source_url_hash + 同 fail_axes 24h 1 度
- [ ] per-post 通常 mail を新設しない
- [ ] count 集計は既存 digest / summary へ吸収可能

### D. 安全系維持
- [ ] body_contract 判定 logic 不変(本 ticket で skip 条件緩めない)
- [ ] hard_stop 維持
- [ ] duplicate guard 維持
- [ ] スコア矛盾 / 一軍二軍混線 publish しない

### E. 環境不変
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] SEO/X/Scheduler/Team Shiny 不変
- [ ] 新 subtype 追加なし

### F. コスト
- [ ] Gemini call 0 増(metadata 層のみ)
- [ ] 229-COST cache 不変

## HOLD 解除条件

1. 291 親契約の方針固定
2. 289 / 293 の live visibility が確認済み
3. user 明示 GO

## owner

- Claude: 親 ticket 整理 + subtask 明文化
- Codex: ledger 接続 impl
- user: 受け入れ + GO/HOLD 判断

## 次に実装してよいタイミング

- 291 親契約の HOLD 解除条件が揃った後
- 289 / 293 の可視化を壊さない narrow impl としてのみ fire
- 単独 ACTIVE 化や mail-first 実装はしない

## 不変方針(継承)

- 本 ticket は **設計のみ**、本 task では impl しない
- body_contract 判定 logic は緩めない(救済は別 ticket)
- 289 / 293 既存通知導線壊さない
- per-post 通常 mail を増やさない
- env flag default OFF、rollback path 明確

## Folder cleanup note(2026-05-03)

- 本 ticket は `waiting/` 維持。
- `292` は BUG-004+291 の必須サブタスクであり、独立 ACTIVE へ戻さない。
- 今回の更新は durable ledger 方針への修正のみ。deploy / env / Scheduler / SEO / WP 状態変更は 0。
