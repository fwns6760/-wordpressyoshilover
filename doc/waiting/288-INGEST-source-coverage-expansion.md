# 288-INGEST-source-coverage-expansion

| field | value |
|---|---|
| ticket_id | 288-INGEST-source-coverage-expansion |
| priority | P1.5(BUG-004+291後の source/topic READY_NEXT 候補) |
| status | DESIGN_DRAFTED + READY_NEXT_CANDIDATE(Phase 0 read-only) + SOURCE_ADD_HOLD |
| owner | Claude(設計)→ user 判断後 Codex impl |
| lane | INGEST |
| ready_for | Phase 0 read-only / dry-run: BUG-004+291 後の READY_NEXT 候補。source 追加: BUG-004+291 終端契約 + mail/Gemini 影響 + user 明示 GO |
| blocked_by | source 追加のみ: 候補終端契約 / mail volume impact / Gemini delta / duplicate risk / rollback plan |
| doc_path | doc/waiting/288-INGEST-source-coverage-expansion.md |
| created | 2026-04-30 |

## 1. 結論(本 ticket 自体の前提)

288 は、ニュース source 追加だけでなく **source/topic coverage expansion** を扱う親 ticket とする。

Phase 0 の read-only / dry-run 棚卸しは READY_NEXT 候補。
ただし、source 追加・fetcher 本線接続・mail/Gemini 増加につながる変更は **USER_DECISION_REQUIRED** で HOLD。

### source 追加 HOLD 理由
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

## 2b. 2026-05-03 source/topic coverage update

### 背景

2026-05-03 の再確認で、現行 `config/rss_sources.json` は X(RSSHub) と一部news RSSに偏っており、巨人専門としては以下の取りこぼし候補が残っている。

この追記は **source追加の即実装GOではない**。
BUG-004+291で候補終端・publish回収を先に進めつつ、288-INGESTの次フェーズで扱う source/topic expansion の棚卸しである。

### 現行main取得元に未接続の重要候補

| candidate | current state | evidence / note | 288での扱い |
|---|---|---|---|
| 東スポ巨人担当 `@tospo_giants` | `config/rss_sources.json` 未登録 | `src/x_api_client.py` の旧X API collect queryには `from:tospo_giants` があるが、X API停止後のRSSHub本線には未接続 | Phase 0 read-only / dry-run候補 |
| 東スポWEB 巨人ラベル | 未登録 | `https://www.tokyo-sports.co.jp/list/label/巨人` が存在。RSS endpointは未確定 | scraper/RSS existence確認候補。即本線接続しない |
| 巨人公式YouTube | 未登録 | `210e` でYouTube feed/GIANTS TV feedが0件と監査済み。候補channel idは外部確認が必要 | official YouTube RSS dry-run候補 |
| GIANTS TV / 公式動画 | 未登録 | `social_video_notice` builder/validator/dry-runは存在するが live fetch / source registry / publish route は未配線 | YouTube/official video lane候補。APIなし/RSS優先 |
| Yahooリアルタイム検索 バズkeyword | 実装の種あり、本線未接続 | `src/viral_topic_detector.py` と `src/tools/run_viral_topic_dry_run.py` は存在。publish/draft本線には流れていない | 246を288へ吸収検討。dry-run観察から |
| Yahooニュース野球ランキング | 実装の種あり、本線未接続 | viral topic detector内にranking scrape helperあり | topic trigger専用。事実sourceにはしない |

### 246との関係

- `246-viral-topic-detection` は、SNSバズ / Yahooリアルタイム検索 / Yahooニュースランキングを **topic trigger** として扱う設計。
- ただし新規subtypeやviral専用テンプレは作らず、既存subtypeへroutingする方針。
- 2026-05-03時点では、246を独立ACTIVEにせず、288-INGESTの source/topic expansion の一部として吸収検討する。

### source/topic拡張の固定方針

- SNS / Yahooリアルタイム / YouTube は **事実sourceではなく、topic triggerまたは公式source候補** として扱う。
- 本文に使う事実は、公式 / スポーツ媒体 / 既存RSS / source_trustで確認できるものに限定する。
- X APIは使わない。
- YouTube Data APIは使わない。最初はYouTube RSS / RSSHub / read-only dry-runのみ。
- source追加は `USER_DECISION_REQUIRED`。ただし、read-only audit / dry-run / Acceptance Pack補強は `CLAUDE_AUTO_GO` 範囲。

### 2c. Phase 0 extension (2026-05-03 PM, repo-only deeper read-only)

- repo-only deeper read-only 棚卸しを `doc/waiting/288_phase0_source_audit.md` §9 に追記した。
- この extension で確定した repo facts:
  - `automation/` directory は workspace に存在せず、source 別 mainline wiring を repo-side TOML で持っている痕跡は無し
  - current scheduler 可視契約は `giants-realtime-trigger -> yoshilover-fetcher POST /run` のままで、6 candidate は全て **mainline active wiring = NO**
  - repo-safe dry-run があるのは **4/6**:
    - `巨人公式 YouTube`, `GIANTS TV` -> `src/tools/run_social_video_notice_dry_run.py` / social_video fixture
    - `Yahoo realtime`, `Yahoo ranking` -> `src/tools/run_viral_topic_dry_run.py` / `tests/test_viral_topic_detector.py`
    - `東スポ X` は networked dry-run only、`東スポWEB` は runner 自体が無い
  - trust family readiness:
    - **present**: `GIANTS TV(web URL)` = `tv.giants.jp -> giants_official`、`Yahoo ranking` = `news.yahoo.co.jp -> yahoo_news_aggregator`
    - **absent / partial**: `東スポ X`, `東スポWEB`, `巨人公式 YouTube`, `Yahoo realtime`
- planning band(read-only estimate, current delta ではない):
  - low planning burden: Yahoo trigger lanes(`Gemini/mail current delta = 0`)
  - medium: 巨人公式 YouTube(`social_video_notice` / `program` に寄せれば deterministic path を使える)
  - medium-high to high: 東スポ X / 東スポWEB / GIANTS TV full ingest
- 結論:
  - Phase 1 USER_DECISION_REQUIRED Pack は **official YouTube first / Yahoo trigger-only second / 東スポ・GIANTS TV は planning burden 高** という整理で精度向上
  - source add HOLD 自体は据え置き。5 preconditions + user GO 前に本線接続しない

### 次の最小手

1. BUG-004+291を優先し、既に拾えている候補のpublish回収を進める。
2. 並走できる場合のみ、288 Phase 0として source/topic coverage read-only audit を実施する。
3. 対象は、東スポ巨人担当、東スポWEB巨人ラベル、巨人公式YouTube、GIANTS TV、Yahooリアルタイム検索、Yahooニュースランキング。
4. 各候補について `今configにあるか / 実装の種があるか / 本線接続済みか / cost・Gemini・duplicate・silent skip risk / 次の最小手` を1表にする。
5. 本線接続やsource追加は、BUG-004+291の終端契約とmail/Gemini影響が見えてから別判断。
6. repo-only deeper read-only matrix は `doc/waiting/288_phase0_source_audit.md` §9 を参照。

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
