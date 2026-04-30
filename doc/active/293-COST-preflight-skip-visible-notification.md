# 293-COST-preflight-skip-visible-notification

| field | value |
|---|---|
| ticket_id | 293-COST-preflight-skip-visible-notification |
| priority | P1(282-COST flag ON 前提条件、cost 削減と silent skip 防止のバランス) |
| status | DESIGN_DRAFTED(実装 hold、user 判断後 impl 起票) |
| owner | Claude(audit/draft) → Codex(将来 impl) |
| lane | COST |
| ready_for | 289 完遂 + user 明示 GO で impl 起票 |
| blocked_by | 289-OBSERVE 完遂(同 ledger pattern 流用) |
| doc_path | doc/active/293-COST-preflight-skip-visible-notification.md |
| created | 2026-04-30 |

## 目的

282-COST の `gemini_call_skipped`(skip_layer=preflight)を **mail or digest で見える化**する。
**282-COST flag ON は本 ticket 完遂後に判断**(可視化なしで ON にすると「安くなったが候補が消えた」状態に見えるリスク)。

## 背景

### 282-COST 現状(本日 deploy 済、flag OFF 維持)
- `src/gemini_preflight_gate.py` で 8 skip_reason:
  - existing_publish_same_source_url
  - placeholder_body
  - not_giants_related
  - live_update_target_disabled
  - farm_lineup_backlog_blocked
  - farm_result_age_exceeded
  - unofficial_source_only
  - expected_hard_stop_death_or_grave
- flag OFF なので preflight skip 0 件、現状は cost 削減効果なし
- flag ON にすると Gemini call 削減見込み(対象 subtype 次第で 10-30%)

### リスク
- flag ON にすると Gemini 呼ぶ前に skip → 通知 path に乗らない
- 結果:候補が user silent で消える(289/292 と同種の silent skip)
- user 体感:「Gemini cost は減ったが、候補がいきなり減った」と錯覚
- 289/292 で post_gen_validate / body_contract が通知化されても、**preflight 段階の skip は別経路**で通知化が必要

### 真因
- preflight skip は `_log_article_skipped_preflight`(or 同等)で logger emit のみ
- 289 ledger とは **別 record_type**(record_type=preflight_skip)で出力する必要
- publish-notice 側の scan も 282-COST の 8 skip_reason mapping を持つ必要

## 対象範囲

### 範囲内
- preflight skip event を 289 同等の通知 ledger に出力
  - 同 ledger 共有(`post_gen_validate_history.jsonl` に record_type=preflight_skip)or 専用 ledger(`preflight_skip_history.jsonl`)
- publish-notice scan 拡張(record_type=preflight_skip 分岐)
- subject prefix 「【要review｜preflight_skip】<source_title>」
- 8 skip_reason mapping を本文に展開
- digest 案: 1 日 1 通の集計 mail で 8 skip_reason 別 count(個別 mail 爆発を抑制したい場合の代替)
- env flag `ENABLE_PREFLIGHT_SKIP_NOTIFICATION` default OFF

### 範囲外
- preflight 判定 logic 緩和
- 282-COST flag ON 自体(本 ticket 完遂後 user 判断)
- post_gen_validate / body_contract 通知(289/292)

## user-visible な受け入れ条件

1. flag ON 時:preflight skip → ledger record(同 ledger 共有 or 専用)
2. publish-notice scan + mail emit(個別 or digest)
3. subject 識別可能(「【要review｜preflight_skip】...」 or 「【digest｜preflight_skip 24h】...」)
4. 本文 skip_reason mapping 8 種(282-COST の全 reason)
5. dedup: source_url_hash + skip_reason 24h 1 度
6. max_per_run cap or digest mode で爆発防止
7. env flag default OFF、`ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1` で有効
8. **本 ticket impl + flag ON 確認後**にのみ 282-COST 側 `ENABLE_GEMINI_PREFLIGHT=1` 有効化を認める運用契約
9. silent preflight skip = 0(env flag ON 時)

## 必須デグレ試験

### A. preflight skip 可視化
- [ ] 8 skip_reason 全部の fixture(各 reason で ledger record + mail emit 確認)
- [ ] silent preflight skip = 0 assert
- [ ] flag OFF 時は ledger 書込 0、既存挙動不変

### B. 既存通知導線維持
- [ ] 289 post_gen_validate 通知不変
- [ ] 292 body_contract 通知不変(292 完遂後)
- [ ] publish/review/hold 通知不変(267-QA 不変)
- [ ] guarded_publish_history scan 不変

### C. 通知爆発防止
- [ ] dedup(source_url_hash + skip_reason 24h)
- [ ] max_per_run cap 共通
- [ ] digest mode の場合:1 日 1 通、内訳 8 reason × count

### D. cost 削減との両立
- [ ] flag ON で Gemini call 減(282-COST 効果)+ skip mail/digest 増 = 両方確認
- [ ] cache_hit ratio 維持(229-COST 75% 不変)
- [ ] 同 source_url 再生成 0(229 不変)

### E. 安全系維持
- [ ] hard_stop 維持
- [ ] duplicate guard 維持
- [ ] スコア矛盾 publish しない
- [ ] 一軍/二軍混線 publish しない

### F. 環境不変
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] SEO/X/Scheduler/Team Shiny 不変
- [ ] 新 subtype 追加なし

### G. flag ON 順序契約
- [ ] **293 impl + ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1 動作確認** 後に
- [ ] 282-COST `ENABLE_GEMINI_PREFLIGHT=1` を有効化する運用順守
- [ ] 順序逆 = silent skip 発生 risk

## HOLD 解除条件

1. 289-OBSERVE deploy + flag ON 完遂、ledger pattern 確立 + 24h 安定
2. 282-COST 本番 deploy 済(flag OFF)= 既達
3. user 明示 GO

## owner

- Claude: 設計 + ticket 起票
- Codex: ledger 出力(preflight gate 側)+ publish-notice scan 拡張 impl
- user: 受け入れ + GO/HOLD + 282-COST flag ON 順序判断

## 次に実装してよいタイミング

- 289 完遂 + 24h 安定後
- 282-COST flag OFF 状態で本 ticket impl 完了 → ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1 で動作確認(skip 数 0 でも通知経路が稼働確認)
- そのうえで初めて 282-COST flag ON 判断

## 282-COST flag ON 順序契約(本 ticket の最重要 deliverable)

```
[現状] 282-COST flag OFF / 293 未実装
   ↓
[step 1] 289 完遂 + 24h 安定
   ↓
[step 2] 293 impl + push + deploy + ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1
   ↓
[step 3] 24h 観察:既存通知導線不変 + flag ON で preflight skip 0 件確認(282-COST flag OFF なので skip 自体無)
   ↓
[step 4] 282-COST flag ON: ENABLE_GEMINI_PREFLIGHT=1
   ↓
[step 5] 24h 観察:preflight skip 件数増 + Gemini call 数減 + 全 skip が mail/digest で見える
   ↓
[step 6] cost 削減効果 KPI 集計 + user 受け入れ判断
```

順序を逆にしないこと(282-COST flag ON 先行は **silent skip 再発 risk**)。

## 不変方針(継承)

- 本 ticket は **設計のみ**、本 task では impl しない
- preflight 判定 logic は緩めない
- 282-COST flag ON は本 ticket impl 完遂後の **user 別判断**
- env flag default OFF、rollback path 明確
- 289/292 既存通知導線壊さない
