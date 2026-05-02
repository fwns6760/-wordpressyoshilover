# 291-OBSERVE-candidate-terminal-outcome-contract

| field | value |
|---|---|
| ticket_id | 291-OBSERVE-candidate-terminal-outcome-contract |
| priority | P0 equivalent(silent skip 再発防止の契約) |
| status | DESIGN_DRAFTED(実装 hold、289 完遂後 user 判断) |
| owner | Claude(audit/draft) → Codex(将来 impl) |
| lane | OBSERVE |
| ready_for | 289 完遂 + 292 完遂後、user 明示 GO で impl 起票 |
| blocked_by | 289-OBSERVE 完遂、292-OBSERVE 完遂 |
| doc_path | doc/active/291-OBSERVE-candidate-terminal-outcome-contract.md |
| created | 2026-04-30 |

## 目的

prepared candidate が **必ず以下 5 つの terminal outcome のいずれか** に落ちる契約を作る:

1. `publish`(WP に公開済 + publish mail 配信)
2. `review_notified`(review draft + 要 review mail 配信)
3. `hold_notified`(draft で残し + hold mail 配信)
4. `skip_notified`(post_gen_validate / body_contract_fail 等の skip + 要 review mail 配信、289/292 で確立)
5. `error_notified`(処理 error + error mail or digest 配信)

**Cloud Logging だけでは可視化済み扱いにしない**。user に **mail or digest で実際に届く**ことを受け入れ条件にする。

## 背景

### 既知の silent skip 経路(本 ticket で潰す対象)
- post_gen_validate skip(289 で通知化中)
- body_contract_validate fail(292 で通知化対象)
- guarded-publish 経由前の rss_fetcher 内 skip 経路全般
- error 系(except handler で握りつぶし → log だけ → user silent)

### 真因
- candidate の終端状態が分散して定義されている
- 各 skip path で「log emit して終わり」が許されている
- mail 経路に乗らない skip = user silent

### 会議室 Codex 監査による発見(2026-04-30)
- post_gen_validate skip 22 件/trigger が user silent(289 で対処中)
- body_contract_validate fail も同様の silent skip の可能性高い(292)
- preflight skip(282-COST)も flag ON 時 silent になり得る(293)

→ **個別の skip path を都度 fix するのではなく、契約として「terminal outcome は 5 つだけ」を確立**して再発防止する。

## 対象範囲

### 範囲内
- candidate lifecycle の terminal state 定義
- 各 terminal state に必ず **user-visible 通知**(mail or digest)が紐付く契約
- terminal state が記録される統一 ledger(または同等の永続 store)
- 全 skip path から terminal state への変換 helper
- 終端到達観測 KPI(prepared 数 = 5 terminal state 合計、 unaccounted = 0)

### 範囲外(個別 ticket で対応)
- post_gen_validate skip notification(289)
- body_contract_fail notification(292)
- preflight_skip notification(293)
- source 追加(288 hold)
- weak title rescue(290 後続)

## user-visible な受け入れ条件

1. **完全性**: prepared candidate 全部が 5 terminal state のいずれかに分類される(unaccounted=0、 daily KPI 集計可能)
2. **通知**: 各 terminal state に **mail emit が紐付く**(または explicit digest mail として 1 日 1 通 集計可能)
3. **dedup**: 同 source_url_hash + 同 terminal state は 24h 1 度(通知爆発防止)
4. **subject 識別**: 件名 prefix で terminal state 判別可能(`【公開済｜...】`/`【要review｜...】`/`【hold｜...】`/`【要review｜post_gen_validate】` 等)
5. **rollback**: env flag で全契約を OFF できる(問題発生時即座に通知導線元に戻せる)
6. **観察**: GCP Logging で `event=candidate_terminal_outcome` が emit、24h で集計可能
7. **silent ゼロ**: 任意の rss_fetcher trigger で log/mail に終端記録のない candidate=0 assert

## 必須デグレ試験(設計時の契約、impl 時に test 化)

### A. 完全性
- [ ] prepared = sum(terminal_state) assert(任意の trigger で)
- [ ] 任意の skip path が terminal state を skip しない fixture(unaccounted candidate 0)

### B. 既存通知導線維持
- [ ] publish 通知従来通り届く
- [ ] review/hold 通知従来通り届く
- [ ] 267-QA dedup 維持
- [ ] post_gen_validate 通知(289)維持
- [ ] body_contract_fail 通知(292)維持(292 完遂後)
- [ ] preflight_skip 通知(293)維持(293 完遂後)

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

## HOLD 解除条件

以下 **全部** 満たした時点で user 判断 + 子 ticket impl 起票:

1. 289-OBSERVE deploy + flag ON 完遂、本日 audit の post_gen_validate skip 22 件が実際に user mail で見えた
2. 292-OBSERVE deploy 完遂、body_contract_fail も同様に通知化
3. 293-COST 完遂(282-COST flag ON 前提が整う)
4. user 明示 GO

## owner

- Claude: 設計 + 子 ticket 起票
- Codex: 統一 ledger / helper / 各 skip path の terminal state 接続 impl
- user: 受け入れ条件 + GO/HOLD 判断

## 次に実装してよいタイミング

- 上記 HOLD 解除条件 4 つ全部達成後
- 289 / 292 / 293 を経た上で「個別通知 → 統一契約」へ昇華するフェーズ
- 単独先行は **禁止**(個別 skip 通知が確立する前に契約だけ作っても効果薄)

## 不変方針(継承)

- 本 ticket は **設計 / 契約定義のみ**、本 task では impl しない
- 既存 publish/review/hold/post_gen_validate 通知導線壊さない
- Cloud Logging 単独で可視化扱いしない、mail/digest 必須

## Folder cleanup note(2026-05-02)

- Active folder????? waiting ????
- ????????deploy?env????????
- ?????? ticket ? status / blocked_by / user GO ??????
