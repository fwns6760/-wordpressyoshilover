# 264-QA-cleanup-existing-duplicates

| field | value |
|---|---|
| ticket_id | 264-QA-cleanup-existing-duplicates |
| priority | **P2**(read-only audit のみ即可、cleanup mutation は user 明示 GO 必須) |
| status | DESIGN_DRAFTED + HOLD(cleanup mutation HOLD) |
| owner | Claude(audit/draft) → Codex(将来 mutation 便、user GO 後) |
| lane | QA |
| ready_for | read-only audit(本 ticket 内)着手は user GO 不要、cleanup mutation は別便 + user 明示 GO |
| blocked_by | (なし、独立) |
| doc_path | doc/active/264-QA-cleanup-existing-duplicates.md |
| created | 2026-04-30(memory draft `feedback_264_QA_cleanup_existing_duplicates.md` から repo 昇格) |

## 1. 結論

**既存 publish 重複の整理 ticket**。
263-QA / 269-QA / 235 は **「今後の重複防止」**(これから出さない)。
本 ticket(264-QA)は **「過去に出た重複の整理」**(既存重複の cleanup 判断材料を作る)。

**本 ticket scope = read-only audit + cleanup 条件設計のみ**。
cleanup mutation(WP delete / draft 戻し / 統合)は **user 明示 GO 必須**、本 ticket では実行しない。

## 2. 背景

### 既存「これから防止」3 経路(LIVE)
- **263-QA**(`7667658`):guarded-publish duplicate guard、first publish wins、draft+publish cross-check、source URL hash priority、duplicate_of_post_id log
- **269-QA**(`d58941b`):263-QA narrow relax、subtype/age/speaker 別緩和、完全重複は hold 継続
- **235**(`a162552`):pre-Gemini duplicate guard、duplicate_key 6 軸、Gemini call 前 skip

→ これらが本日着地の前から既に live で動いている = **これから新規重複は出にくい設計**。

### 過去の重複は手付かず
- 263-QA 着地前に publish された重複記事は存在し得る
- 「同 source_url で複数 post_id が publish されている」cases
- WP 上で並んで見えると user 体感で「重複しているサイト」と映る可能性
- ただし削除には:
  - SEO 影響(404 増)
  - SNS / 検索からの link 切れ
  - 統合判断(どちらを残すか)
- = mutation は **慎重判断必須**

## 3. 目的

1. **read-only audit**:既存 publish 重複ペアを post_id 単位で集計
2. **cleanup 条件設計**:どういう条件なら cleanup 対象にするか / しないかを doc 化
3. **user 判断材料を作る**:audit 結果 + 条件設計 → user が cleanup 範囲を決める素材
4. **mutation は別便**:本 ticket では実行しない

## 4. 対象範囲(本 ticket scope)

### 範囲内(read-only audit のみ)
- WP REST GET で publish 記事一覧取得(per_page=100、複数 page)
- source_url / source_url_hash 別 grouping、複数 post_id 持つ source 抽出
- guarded_publish_history.jsonl scan で `duplicate_of_post_id` 記録 cross check
- 集計レポート出力(GCS or 一時 file、write 範囲は集計 doc のみ)
- cleanup 条件設計 doc 化(本 ticket 内の section 6)
- HOLD 解除条件の明文化

### 範囲外(本 ticket では実行しない)
- WP delete / draft 戻し / 統合 / status 変更
- guarded-publish / publish-notice 変更
- canonical / 301 / SEO 設定変更
- Gemini call(audit に LLM 不要、regex / hash 比較のみ)

## 5. read-only audit 手順(本 ticket 内で実行可、user GO 不要)

### A. 同 source_url 重複 post_id ペアの集計

#### 集計方法
1. **WP REST GET** で `status=publish` の post 一覧取得(per_page=100、orderby=date&order=desc、複数 page)
2. 各 post の `meta.source_url`(or `_yoshilover_source_url` カスタムフィールド名は要確認)を取得
3. `source_url` で grouping、count > 1 のペア抽出
4. 各ペアについて:
   - 古い post_id(first publish)
   - 新しい post_id(later publish)
   - publish 日時差
   - title 編集距離
   - subtype
5. 集計結果を:
   - GCS:`gs://baseballsite-yoshilover-state/duplicate_audit/duplicate_pairs.jsonl`(可)
   - or 一時 doc:`docs/handoff/audit_logs/2026-04-30_duplicate_audit.md`(local 集計)

#### 集計対象ハッシュ
- **source_url 完全一致**(優先、263-QA と同 key)
- **source_url_hash 一致**(`utils.source_url_hash` 流用)
- **content_hash 一致**(229-COST 既存 cache key 流用、強い重複指標)

### B. ledger cross-check

`gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl` を scan、
`duplicate_of_post_id != null` の record 一覧化(263-QA が hold した重複候補)。

### C. 集計レポート

audit 出力 format:
```json
{
  "source_url": "https://...",
  "post_ids": [64081, 64104],
  "first_publish_at": "2026-04-30T11:50:41Z",
  "later_publish_at": "2026-04-30T17:10:35Z",
  "title_edit_distance": 12,
  "subtype": "farm_result",
  "title_first": "巨人二軍スタメン 当日カード試合前情報",
  "title_later": "投手陣が乱れ楽天に連敗 中山礼都が猛打賞...",
  "duplicate_severity": "low",  // high(完全重複)/ medium(タイトル類似)/ low(別記事だが同 source)
  "recommended_action": "human_review"  // delete_later / merge / keep_both / human_review
}
```

## 6. cleanup 条件設計(本 ticket scope の本旨)

### A. cleanup 対象にする条件(将来 mutation 便で実行する場合の基準)

以下 **全部** 満たす場合のみ cleanup 候補:
1. 同 source_url 完全一致(or content_hash 完全一致)
2. publish 日時差が **24h 以内**(古い重複は SEO 影響大)
3. title 編集距離 < 20%(タイトルもほぼ同じ = 価値ない重複)
4. 後から publish された方を draft 戻し(古い方を残す)
5. 検索 / SNS の link が後から publish された方に向いていない
6. user 明示 GO

### B. cleanup しない条件(明示 hold)

以下 **どれか** 該当する場合 cleanup 候補から除外:
1. 同 source_url でも **異なる subtype**(例:同 X tweet を pregame と postgame で別記事化)
2. publish 日時差 > 7 日(SEO 影響回避、404 増やさない)
3. title 編集距離 > 50%(別の角度から書いた記事 = 価値あり)
4. 検索 / SNS の link が後発記事に向いている(canonical / redirect 必要、SEO 触らない方針なので不可)
5. publish-notice mail で user が「公開で良い」と承認済(履歴確認)
6. user 明示 hold

### C. user 必ず GO すべき変更
- WP post delete(完全削除)
- WP post status=draft 戻し
- WP post status=private 化
- canonical 設定変更
- 301 redirect 設定
- SEO meta 触る変更

## 7. rollback / 復元方針

### cleanup mutation 実行時の安全策(将来 mutation 便で必須)
1. **削除前に snapshot 取得**:WP post 全 fields を GCS に backup(`gs://baseballsite-yoshilover-state/duplicate_cleanup/backups/<post_id>.json`)
2. **status 変更のみ**(delete ではなく draft / private 化、復元可能)
3. **bulk 実行禁止**(1 post_id ずつ、user 確認 mode)
4. **24h 以内 rollback**:WP REST PUT で status=publish に戻せる経路を保つ

### rollback 手順(将来)
- backup JSON から WP REST PUT で post 復元
- canonical / SEO は触らないので元の状態維持

## 8. 必須デグレ試験(本 ticket は audit のみ、mutation 便で必須)

### A. read-only audit 試験(本 ticket 内)
- [ ] WP REST GET で publish 一覧取得 fixture(write 0 assert)
- [ ] guarded_publish_history.jsonl scan fixture(read-only)
- [ ] 集計 output が GCS or local doc に書き出される(WP write 0)

### B. mutation 便(将来)で必須
- [ ] WP post delete 0(status 変更のみ)
- [ ] canonical / 301 / SEO meta 触らない
- [ ] publish-notice mail に「重複 cleanup 通知」が出る(user に見える)
- [ ] backup JSON が GCS にある
- [ ] 1 post_id ずつ実行、bulk 禁止
- [ ] user 明示 GO 1 post 1 GO
- [ ] rollback fixture(backup から WP REST PUT で復元できる確認)

### C. 環境不変(本 ticket + 将来便共通)
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] SEO/noindex/canonical/301 不変
- [ ] X 自動投稿 path 不変
- [ ] Team Shiny From 不変
- [ ] Scheduler 頻度変更なし
- [ ] 新 subtype 追加なし
- [ ] Gemini call 0 増(audit に LLM 不要)

## 9. HOLD 解除条件

### read-only audit 着手(本 ticket section 5)
- **無条件で着手可**(user GO 不要、read-only)

### cleanup mutation(将来別便)
1. 本 ticket section 5 audit 完了 + 集計結果 review
2. user が cleanup 対象を **個別 post_id 単位で明示 GO**(bulk 不可)
3. 263-QA / 269-QA / 235 が live で安定動作確認(本日 LIVE 確認済)
4. backup 経路 + rollback fixture 整備
5. canonical / SEO に触らない代替策確立(または「触らない」選択維持)
6. user 明示 GO

## 10. 推奨実行順序

### Phase 1(本 ticket 内、read-only)
- WP REST GET で全 publish post 取得、source_url 別 grouping、重複ペア抽出
- guarded_publish_history.jsonl の `duplicate_of_post_id` cross-check
- 集計結果を `docs/handoff/audit_logs/2026-04-30_duplicate_audit.md`(local) or GCS に出力
- 集計結果を user に提示、cleanup 候補を一覧化

### Phase 2(別便、user 明示 GO 後)
- cleanup 対象の個別承認(1 post 1 GO)
- backup 取得 + status=draft 戻し(delete ではない)
- 24h 観察、問題なければ次 post

### Phase 3(将来、必要時)
- canonical / 301 redirect 設計(本 ticket scope 外、SEO 触らない方針継続なら不要)

## 11. 関連 ticket

- **263-QA**(LIVE):guarded-publish duplicate guard、これから防止
- **269-QA**(LIVE):263 narrow relax
- **235**(LIVE):pre-Gemini duplicate guard
- **289-OBSERVE**(LIVE):silent skip 通知化、本 ticket と無関係
- **291-OBSERVE**:候補終端契約、本 ticket と直接関係なし
- **294-PROCESS**:release composition gate、本 ticket cleanup 便にも適用

## 12. 不変方針(継承)

- ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- Team Shiny From / SEO / noindex / canonical / 301 不変
- 新 subtype 追加なし
- Scheduler 頻度変更なし
- duplicate guard 全解除なし(263/269 narrow 緩和は維持)
- WP delete は cleanup 便でも禁止(status 変更のみ)
- bulk 実行禁止(1 post 1 GO)
- Gemini call 0(audit / cleanup 共)

## 13. 受け入れ条件(本 ticket 完了)

- [ ] section 5 audit 結果が doc 化された
- [ ] section 6 cleanup 条件が明文化された
- [ ] section 9 HOLD 解除条件が明確
- [ ] WP / publish-mail / SEO 全部不変(本 ticket 内 mutation 0)
- [ ] cleanup mutation の安全策(backup + rollback)が doc 化された
- [ ] 関連 ticket(263/269/235)との役割境界が明確

## 14. 本 ticket は「廃止」ではない

- 過去の重複が user 体感で問題化したときに、安全側で cleanup できる経路を **準備しておく**
- audit 結果次第では「重複は実は少ない、cleanup 不要」と判断できる
- audit 結果がそのまま 263-QA / 269-QA narrow 設定の調整材料にもなる
- 設計 phase として価値あり、cleanup 便着手は別判断

## Folder cleanup note(2026-05-02)

- Active folder????? waiting ????
- ????????deploy?env????????
- ?????? ticket ? status / blocked_by / user GO ??????
