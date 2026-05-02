# 295-QA-subtype-evaluator-misclassify-fix

| field | value |
|---|---|
| ticket_id | 295-QA-subtype-evaluator-misclassify-fix |
| priority | P1(silent 候補消失の主因の 1 つ、2-3 件/trigger) |
| status | DESIGN_DRAFTED + HOLD(289 安定 + 290 整理後 user 判断) |
| owner | Claude(設計)→ user 判断後 Codex impl |
| lane | QA |
| ready_for | 289 24h 安定 + 290-QA 整理 + user 明示 GO で impl 起票 |
| blocked_by | 289-OBSERVE 24h 安定 / 290-QA 整理 |
| doc_path | doc/active/295-QA-subtype-evaluator-misclassify-fix.md |
| created | 2026-04-30 |

## 1. 目的

通常ニュースを `live_update_disabled` 等の **subtype 誤判定で消さない**。
特に **浦田俊輔の右手甲に149km直球直撃**のような **通常 notice / recovery / postgame 系記事**が `live_update` と誤判定されて skip される pattern を潰す。

ENABLE_LIVE_UPDATE_ARTICLES=0 維持(試合中実況の本格 ON は別判断)、本 ticket は **誤判定して捕まる側を救う** narrow fix。

## 2. 背景

### 2026-04-30 audit で発見した 誤判定 pattern

fetcher flow_summary `skip_reasons.live_update_disabled_sample_titles`:

| 元 title | 本来の subtype | 誤判定結果 |
|---|---|---|
| 【巨人】阿部監督、大勢のコンディション不良を明かす「明日様子を見るかも」 | manager / notice | `live_update_disabled` で skip |
| 【巨人】浦田俊輔の右手甲に149キロ直球が直撃 球場は落胆の声もプロテクターで大事には至らず | recovery / notice / player_notice | `live_update_disabled` で skip |

これらは **試合中実況**ではない:
- 大勢のコンディション不良 = 監督コメント / 起用 notice
- 浦田俊輔 直球直撃 = 怪我 / recovery 関連 notice

なのに `live_update` subtype と判定されて、env flag `ENABLE_LIVE_UPDATE_ARTICLES=0` により skip。
**= 通常ニュースが silent で消える**。

### 真因

`viral_topic_detector.py` の `classify_expected_subtype` or `rss_fetcher.py` 内 subtype 判定で:
- 「投手」「打者」「直撃」「コンディション不良」等の試合関連 keyword → live_update 判定
- 試合進行(スコア進行 / 速報 marker)が無いのに live_update に振り分け
- 結果:postgame / recovery / notice / manager などの通常記事が live_update に誤分類される

### 影響

- **本日 audit で 2-3 件/trigger** が live_update_disabled で silent skip(`skip_reasons` count)
- うち 浦田俊輔 / 大勢コンディション不良 等は **publish 価値の高い**通常ニュース
- silent skip:289 ledger には乗らない(post_gen_validate 段階より前で skip、別経路)
- = **289 で見える化されない盲点**

### 連携 ticket
- 289-OBSERVE: post_gen_validate skip 通知化(別 path、本 ticket の skip は post_gen_validate 到達前)
- 291-OBSERVE: 候補終端契約(本 ticket の skip も 5 terminal state に入る必要)
- 290-QA: weak title 救済(本 ticket とは別軸、disjoint)

## 3. 対象範囲

### A. live_update 判定 logic narrow 化
- 試合中実況 marker(score 進行 / 「○回表」「速報」「ヒット」等) **明示**で live_update 判定
- それ以外は live_update に振り分けない
- 「直撃」「コンディション不良」「コーチ」等の単発 keyword では live_update 不確定 → 別 subtype へ

### B. 誤判定救済 path
- 既存 live_update_disabled skip を:
  - **試合中実況 marker 明示なし** → live_update ではないと再分類(notice / recovery / manager 等へ)
  - **試合中実況 marker 明示あり** → 従来通り live_update_disabled skip
- 再分類後の subtype で post_gen_validate / publish path に流す

### C. log 強化
- 旧誤判定 path に乗っていた件数を log で集計可能に
- `event=subtype_reclassified_from_live_update` 等の telemetry

### 範囲外
- live_update ON 化(env flag 不変、ENABLE_LIVE_UPDATE_ARTICLES=0 維持)
- 試合中実況 publish 解禁(本 ticket は救済のみ、本格 ON は別判断)
- post_gen_validate / weak_title 救済(289 / 290 で別便)
- source 追加(288 で別便)

## 4. user-visible な受け入れ条件

1. 浦田俊輔 / 大勢コンディション不良 type の通常ニュースが live_update 誤判定で消えない
2. 真の試合中実況(○回表速報 等)は引き続き skip(env flag 維持)
3. 再分類された候補は post_gen_validate or publish path に流れる(289 ledger or guarded-publish history で可視化される)
4. silent な skip 0(全 skip event が log + ledger で見える)
5. env flag rollback path 明確(誤判定救済を OFF に戻せる)

## 5. 必須デグレ試験

### A. live_update 判定の narrow 化
- [ ] fixture: 「巨人 4-2 ○回表」「速報」「ヒット」等の試合中 marker → live_update 判定維持(skip)
- [ ] fixture: 「コンディション不良」「コーチ」「直撃」等の単発 keyword → live_update 判定しない
- [ ] fixture: 浦田俊輔 直球直撃 type → recovery / player_notice に再分類、publish/review path
- [ ] fixture: 大勢コンディション不良 type → manager / notice に再分類

### B. 既存通知導線維持
- [ ] live_update 真の skip(試合中実況)は引き続き silent skip しない、適切な terminal state(289 ledger or hold mail)に乗る
- [ ] publish/review/hold 既存導線不変
- [ ] 267-QA dedup 維持

### C. 環境不変(本 ticket の最重要 contract)
- [ ] **ENABLE_LIVE_UPDATE_ARTICLES=0 維持**(本 ticket で env 触らない)
- [ ] 試合中実況 publish 解禁しない
- [ ] live_update ON 化なし
- [ ] SEO/X/Scheduler/Team Shiny From 全部不変

### D. 安全系
- [ ] hard_stop 維持(死亡/重傷/救急/意識不明、特に「直撃」keyword で誤検知ないか fixture 確認)
- [ ] duplicate guard 維持
- [ ] スコア矛盾 publish しない
- [ ] 一軍/二軍混線 publish しない

### E. silent skip 0
- [ ] 再分類されない candidate は引き続き skip だが、log + ledger で可視化される
- [ ] 旧 live_update_disabled silent skip pattern の再発なし

### F. コスト
- [ ] Gemini call 増加なし(本 ticket は subtype 判定 logic narrow 化のみ、生成 logic 不変)
- [ ] 229-COST cache_hit 維持
- [ ] 282-COST preflight gate(flag ON 時)と整合

### G. 新 subtype 追加禁止
- [ ] 既存 subtype(notice / recovery / player_notice / manager / postgame)流用のみ
- [ ] VALID_ARTICLE_SUBTYPES set 不変

## 6. HOLD 解除条件(impl 起票前)

1. **289-OBSERVE 24h 安定**: silent skip 通知導線が安定、本 ticket 救済対象が新たに 289 経由で出てこない pattern 確認
2. **290-QA 整理**: weak title 救済方針が決まり、本 ticket 救済 candidate が weak_title path で再 skip されないか整合確認
3. **user 明示 GO**

## 7. impl 案(参考、impl 時 Codex 検討)

### A. subtype 判定 narrow 化
- `viral_topic_detector.classify_expected_subtype` or `rss_fetcher` 内分類で:
  - 試合中実況 marker(score 進行 regex / 「○回表」「○回裏」「速報」 等)を明示 require
  - marker 無いものは live_update から外す
- 既存 marker logic を narrow 化(削るのではなく条件追加)

### B. 再分類 helper
- `_reclassify_from_live_update_if_no_progression_marker(title, body, metadata)`
  - input: 旧 live_update 判定 candidate
  - output: 再分類された subtype(recovery / player_notice / manager / notice / postgame など)
  - LLM 呼び出し 0(regex / keyword based)
- 既存 subtype 判定 helper を再利用

### C. log
- `event=subtype_reclassified_from_live_update`(rss_fetcher.py)
- field: `original_subtype="live_update"` / `new_subtype=...` / `reason=no_game_progression_marker`

## 8. deploy 要否

- impl 自体: fetcher image rebuild 必要(`yoshilover-fetcher`)
- env flag 不要(coded narrow fix、rollback は commit revert)
- 別便で deploy、user 明示 GO 後

## 9. rollback 条件

- impl commit revert で即時 rollback
- image rebuild 後問題発生時は前 image に戻す
- env flag は新規追加しない(rollback 簡素化)

## 10. 優先順位

- silent 候補消失 主因 3 つ中 2 番目(289 が 1 番、本 ticket が 2 番、source coverage 288 は 3 番)
- 全体: 289 / 290 完遂後の最優先 narrow fix 候補

## 11. owner

- Claude: 設計 + ticket 起票
- Codex: subtype 判定 narrow 化 + 再分類 helper impl
- user: env 不変 contract verify + 24h 観察判断

## 12. 関連 ticket

- 289-OBSERVE-post-gen-validate-mail-notification(silent skip 通知化、本 ticket とは別 path)
- 290-QA-weak-title-rescue-backfill(weak title 救済、本 ticket とは別軸)
- 291-OBSERVE-candidate-terminal-outcome-contract(候補終端契約、本 ticket 救済も 5 terminal state に入る)
- 288-INGEST-source-coverage-expansion(source 追加、本 ticket は既存 source の救済)

## 13. 不変方針(継承)

- ENABLE_LIVE_UPDATE_ARTICLES=0 維持(本 ticket で env 触らない)
- 試合中実況 publish 解禁しない
- 新 subtype 追加なし
- live_update ON なし
- SEO/X/Scheduler/Team Shiny From / Gemini call 全部不変
- 既存 publish/mail 導線壊さない

## Folder cleanup note(2026-05-02)

- Active folder????? waiting ????
- ????????deploy?env????????
- ?????? ticket ? status / blocked_by / user GO ??????
