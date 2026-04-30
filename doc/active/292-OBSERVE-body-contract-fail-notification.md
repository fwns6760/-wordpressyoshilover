# 292-OBSERVE-body-contract-fail-notification

| field | value |
|---|---|
| ticket_id | 292-OBSERVE-body-contract-fail-notification |
| priority | P0 equivalent(silent skip 第 2 経路) |
| status | DESIGN_DRAFTED(実装 hold、289 完遂後 user 判断) |
| owner | Claude(audit/draft) → Codex(将来 impl) |
| lane | OBSERVE |
| ready_for | 289 完遂後 user 明示 GO で impl 起票 |
| blocked_by | 289-OBSERVE 完遂(同 ledger/scan pattern を流用) |
| doc_path | doc/active/292-OBSERVE-body-contract-fail-notification.md |
| created | 2026-04-30 |

## 目的

`body_contract_validate` fail を **log だけで終わらせず**、289 と同じ通知 ledger 経路へ接続する。
silent skip 第 2 経路を潰し、候補が user に見える化する。

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
- 289 と同じ pattern: 専用 ledger or 既存 `post_gen_validate_history.jsonl` 共有
- publish-notice scan 拡張(record_type=body_contract_fail or 共通化)
- subject prefix 「【要review｜body_contract】<source_title>」
- skip_reason mapping: farm_result_player_unverified / farm_result_numeric_fabrication / farm_lineup_lineup_missing / その他 fail_axes

### 範囲外
- body_contract 判定 logic 緩和(救済は別 ticket、本 ticket は通知のみ)
- post_gen_validate 通知(289 既出)
- preflight_skip 通知(293)

## user-visible な受け入れ条件

1. body_contract fail → ledger record(env flag ON 時)
2. publish-notice scan で拾われ **mail emit**
3. subject 「【要review｜body_contract】...」または 289 と同 prefix で識別可能
4. 本文に skip_reason mapping、source_title / generated_title / source_url 表示
5. dedup: source_url_hash + skip_reason 24h 1 度
6. max_per_run cap、cap 超過時持ち越し
7. env flag default OFF(289 と同 pattern、`ENABLE_BODY_CONTRACT_FAIL_NOTIFICATION` or 共通 flag)
8. rollback: env flag remove で即時無効化
9. silent body_contract_fail = 0(全 fail event が ledger or mail に到達 assert)

## 必須デグレ試験

### A. silent skip 解消
- [ ] fixture: farm_result_player_unverified fail → ledger record + mail emit
- [ ] fixture: farm_result_numeric_fabrication fail → 同上
- [ ] fixture: farm_lineup_lineup_missing fail → 同上
- [ ] fixture: 任意の body_contract fail event → silent 0 assert

### B. 既存通知導線維持
- [ ] 289 post_gen_validate 通知不変
- [ ] publish/review/hold 通知従来通り(267-QA dedup 不変)
- [ ] guarded_publish_history scan 不変
- [ ] cursor 前進不変

### C. 通知爆発防止
- [ ] 同 source_url_hash + 同 skip_reason 24h 1 度
- [ ] max_per_run cap 共通(289 と統合)
- [ ] cap 超過 silent drop 0

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

1. 289-OBSERVE deploy + flag ON 完遂、ledger pattern 確立
2. 289 が 24h 安定動作(通知爆発なし、Team Shiny From 維持、既存導線不変)
3. user 明示 GO

## owner

- Claude: 設計 + ticket 起票
- Codex: ledger 接続 + scan 拡張 impl
- user: 受け入れ + GO/HOLD 判断

## 次に実装してよいタイミング

- 289 完遂 + 24h 安定確認後
- 291(契約)が確立する前でも、289 と同 pattern で先行実装可
- ただし 289 の安定性が担保されないうちに 292 を被せると、silent skip 経路が複雑化するため **289 安定後** が安全

## 不変方針(継承)

- 本 ticket は **設計のみ**、本 task では impl しない
- body_contract 判定 logic は緩めない(救済は別 ticket)
- 289 既存通知導線壊さない
- env flag default OFF、rollback path 明確
