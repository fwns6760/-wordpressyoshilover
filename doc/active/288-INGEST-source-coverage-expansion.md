# 288-INGEST-source-coverage-expansion

| field | value |
|---|---|
| ticket_id | 288-INGEST-source-coverage-expansion |
| priority | P2(289 安定後、source 拡張) |
| status | DESIGN_DRAFTED + HOLD |
| owner | Claude(設計)→ user 判断後 Codex impl |
| lane | INGEST |
| ready_for | 289 安定 24h + 290-QA 救済 + 291 統一 ledger 完遂後 user 明示 GO |
| blocked_by | 289-OBSERVE 24h 安定 / 290-QA 救済設計 / 291 統一 ledger / **subtype 誤分類問題(別 ticket 想定)** |
| doc_path | doc/active/288-INGEST-source-coverage-expansion.md |
| created | 2026-04-30 |

## 1. 結論(本 ticket 自体の前提)

source 追加(NNN / スポニチ web / サンスポ web)は **289 + 290 + 291 が落ち着くまで HOLD**。

### HOLD 理由
- 候補の終端契約(291)が確立する前に source を増やすと、**「拾うが silent で消える」候補が増える**(29-OBSERVE で発見した silent skip pattern が拡大)
- subtype 誤分類問題(浦田俊輔の live_update 誤判定など)を先に潰す必要
- weak title rescue(290-QA)が無いと、新 source の記事も同じ pattern で skip される

## 2. user 5 問の audit 結果

### Q1. NNN / スポニチ web / サンスポ web fetch 対象外か
**YES、確定**(`config/rss_sources.json` audit 済)

| source | 状態 |
|---|---|
| **NNN (news.ntv.co.jp / nnn.co.jp)** | **未登録** |
| **スポニチ web (sponichi.co.jp)** | **未登録**(@SponichiYakyu X feed のみ登録) |
| **サンスポ web (sanspo.com)** | **未登録**(@Sanspo_Giants X feed のみ登録) |

### Q2. 報知 RSS error 時の fallback
**fallback 機構なし**

- `https://hochi.news/rss/giants.xml` 現在 `<title>エラー : スポーツ報知</title>` 継続
- fetcher は取得失敗で当該 source skip、retry / 代替 source 切替なし
- 期間限定エラーなら無視できるが、**現在 進行中**で本日 publish 取りこぼしの一因

### Q3. 堀田賢慎 / 浦田俊輔 / 山田龍聖 / 泉口友汰 が拾えなかった原因

| ニュース | 拾えていたか | 真因 | 対策 |
|---|---|---|---|
| 泉口友汰 屋外フリー打撃(報知 12:13) | **YES**(@hochi_giants X 経由) | `weak_subject_title:related_info_escape` で post_gen_validate skip | 290-QA 救済 |
| 浦田俊輔 149km直撃(報知) | **YES**(同上) | `live_update_disabled` で skip = **subtype 誤分類**(notice/recovery が live_update に誤判定) | 別 ticket(295-QA-subtype-evaluator-misclassify-fix 仮称) |
| 山田龍聖 二軍楽天先発(報知 12:52) | **間接的に**(二軍スタメン記事として `history_duplicate` skip、山田龍聖個人話題は明示記事化されず) | farm_lineup history dedup logic / 個別話題抽出弱い | 後続 ticket |
| 堀田賢慎 1軍合流(報知 13:50)/ 東京ドーム(NNN 14:19) | **NO**(fetcher log で 0 hit) | **報知 RSS error + NNN 未登録 = source coverage 確定 gap** | **288 本 ticket 対象** |

→ **真の source coverage gap は堀田賢慎の 2 件のみ**。他 3 件は既存 source で拾えており、別問題(subtype / title / dedup)。

### Q4. source 追加 + Gemini call / silent skip 防止のデグレ試験案
本 ticket 対象、section 5 で詳細

### Q5. 288 impl 前の前提条件
本 ticket 対象、section 6 で詳細

## 3. 対象範囲(impl 時)

### A. 報知 RSS error retry / fallback
- 取得失敗時の retry(指数 backoff 2-3 回)
- fallback として @SportsHochi X feed や baseballking RSS を一時補完
- error 状態が一定期間続く場合の telemetry log

### B. NNN(日テレ NEWS NNN)RSS 追加
- 探索:`https://news.ntv.co.jp/category/sports/feed` 等の正式 RSS endpoint 確認
- 巨人関連 keyword filter(現行 fetcher の T1 trust 仕組み流用)
- T1 trust level 設定(news.ntv.co.jp domain を `source_trust.py` に登録)

### C. スポニチ web RSS / サンスポ web RSS 追加
- 同上、正式 endpoint 探索 + T1 trust 設定

### D. 全 source の T1 / T2 整理
- 既存 `source_trust.py` の SourceFamily 拡張(NNN family 等)

## 4. 不可触

- 既存 source の T1 / T2 trust level 変更
- `_evaluate_post_gen_validate` 判定 logic
- 289 ledger / 通知導線
- guarded-publish / publish-notice / Team Shiny From / SEO / X / live_update / Scheduler
- Gemini call 増加(本 ticket は source 追加のみ、生成 logic 不変)

## 5. 必須デグレ試験(impl 時)

### A. silent skip 増えない(289 / 291 を壊さない)
- [ ] 新 source 由来の post_gen_validate skip も既存 ledger に必ず記録される
- [ ] silent な「source 拾われたが ledger に残らない」case = 0 assert
- [ ] subtype evaluator が新 source domain を未知と判定して default/other に流れすぎない(fixture)

### B. Gemini call 増加 抑制
- [ ] 新 source 由来の content も 229-COST cache_hit ratio 維持(同 source_url 再 fetch 0)
- [ ] preflight gate(282-COST、flag ON 時)が新 source も適切に skip 判定可能
- [ ] 1 trigger あたり Gemini call 数 baseline 比較、+20% 超えたら fail
- [ ] 24h running window で source_url_hash 別 Gemini call 数集計

### C. 既存 publish/mail 導線維持
- [ ] publish 通知従来通り
- [ ] review/hold 通知従来通り
- [ ] 267-QA dedup 維持
- [ ] post_gen_validate 通知(289)維持
- [ ] Team Shiny From `y.sebata@shiny-lab.org` 維持
- [ ] cap=10/run dedup 維持

### D. source coverage 効果測定
- [ ] 新 source 追加後 24h で「新 source 由来の publish」N 件、「skip」M 件を集計
- [ ] N+M = 真の source coverage 拡張効果
- [ ] N が 0 で M が大量 = silent 候補大量生成の警告

### E. 安全系(回帰禁止)
- [ ] hard_stop 維持(死亡/重傷/救急/意識不明)
- [ ] duplicate guard 維持(263-QA 同 source_url cross check、新 domain も対象)
- [ ] スコア矛盾 publish しない
- [ ] 一軍/二軍混線 publish しない
- [ ] 巨人関連性 weak filter で他球団単独記事を弾く

### F. 環境不変
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] SEO/noindex/canonical/301 不変
- [ ] X 自動投稿 path 不変
- [ ] Scheduler 頻度変更なし

### G. 報知 RSS error fallback
- [ ] error 検出時 fallback path 動作 fixture
- [ ] retry 上限超過時の log emit
- [ ] error 永続時の telemetry alert(別便で実装可)

## 6. 288 HOLD 解除条件(時間軸ではなく条件管理、user 確定 2026-04-30)

以下 **5 条件全部** 達成 + user 明示 GO で impl 起票:

1. **289 で post_gen_validate skip が通知される**(silent skip 解消、24h 安定)
2. **290 で weak title 救済の方針が決まる**(weak_subject_title:related_info_escape 等の救済 path、新 source も同 pattern で skip されるため必須)
3. **295 で live_update 誤判定の扱いが整理される**(subtype evaluator 誤分類問題、新 source 追加で増える前に潰す)
4. **source 追加後の候補が publish / review通知 / hold通知 / skip通知 のどれかに必ず落ちる**(候補終端契約、291 統一 outcome ledger と整合)
5. **Gemini call 増加を抑える preflight / dedupe 方針がある**(282-COST preflight gate flag ON or 同等の cost gate、新 source content も 229-COST cache layer 通る前提)

**期間軸での着手予測は撤回**(条件管理に統一)。条件達成順序は問わないが、5 つすべて揃う前は HOLD。

## 7. impl 段階(将来、上記前提達成後)

### Phase 1:報知 RSS error retry / fallback(本 ticket A)
- 既存 hochi.news/rss/giants.xml の error 安定化が最優先
- impl 軽量、リスク低

### Phase 2:NNN RSS 追加(本 ticket B)
- 正式 endpoint 探索
- 巨人関連 filter 強化
- T1 trust 登録

### Phase 3:スポニチ / サンスポ web RSS 追加(本 ticket C)
- Phase 2 知見を踏まえて拡張
- 段階的 24h 観察

### Phase 4:T1/T2 整理(本 ticket D)
- 全 source の trust level audit + 整理

各 Phase 間に **24h 観察** + デグレ試験 5 軸 verify 必須。

## 8. deploy 要否

- impl Phase 1: fetcher image rebuild 必要(`yoshilover-fetcher` 単独)
- impl Phase 2-4: 同上、各 phase で別 deploy 便
- env flag で source 個別 ON/OFF 可能にする推奨(rollback 簡素化、`ENABLE_SOURCE_NNN=0` default、Phase 検証時のみ ON)

## 9. rollback 条件

- impl commit revert で即時 rollback
- env flag(導入時)で source 個別無効化
- image rebuild 後問題発生時は前 image に traffic 戻し

## 10. 優先順位

- 全体:289 / 290 / 291 / 295 より下(全部の解除条件を後追い)
- 着手判断: section 6 の 5 条件全部達成 + user 明示 GO(時間軸ではなく条件管理)

## 11. owner

- Claude:設計 + 子 ticket 起票
- Codex:RSS endpoint impl + source_trust 拡張 + retry/fallback impl
- user:source 追加判断 + 24h 観察判断

## 12. 関連 ticket

- 289-OBSERVE-post-gen-validate-mail-notification(silent skip 通知化)
- 290-QA-weak-title-rescue-backfill(weak title 救済、未起票)
- 291-OBSERVE-candidate-terminal-outcome-contract(統一 outcome ledger)
- 295-QA-subtype-evaluator-misclassify-fix(仮称、live_update 誤判定問題、未起票)
- 294-PROCESS-release-composition-gate(deploy 前 commit 一覧 verify)

## 13. 不変方針(継承)

- 新 subtype 追加なし
- live_update / ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- SEO/X/Scheduler/Team Shiny From 不変
- Gemini call 増加なし(source 追加でも 229-COST cache 効く前提)
- 既存 publish/mail 導線壊さない

---

## 真因分布まとめ(本日 audit ベース)

| 候補消失原因 | 件数 | 解決 ticket |
|---|---|---|
| post_gen_validate silent skip | 21/trigger | 289(完遂)+ 290(救済)|
| subtype 誤分類(live_update 等) | 2-3 件/trigger | 別 ticket(295 仮)|
| history_duplicate(個別話題抽出弱) | 16+/trigger | 後続(個別話題分離)|
| **source 自体未登録(NNN)** | **2 件 (本日サンプル)** | **本 ticket 288** |
| **既存 source error(報知 RSS)** | **不明件数(全部 silent)** | **本 ticket 288 Phase 1** |

= source coverage gap は重要だが、**全体の取りこぼしの少数派**。289/290/291/subtype 誤分類修正の方が体感改善大きい。
