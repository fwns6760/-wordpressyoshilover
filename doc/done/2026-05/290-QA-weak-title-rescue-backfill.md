# 290-QA-weak-title-rescue-backfill

| field | value |
|---|---|
| ticket_id | 290-QA-weak-title-rescue-backfill |
| priority | P1(289 で見えた A/B 群を publish/review に戻す) |
| status | REVIEW_NEEDED |
| owner | Claude(audit/draft) → Codex(別 lane、impl) |
| lane | QA |
| ready_for | Codex narrow 実装便 fire |
| blocked_by | (なし、独立) |
| doc_path | doc/active/290-QA-weak-title-rescue-backfill.md |
| created | 2026-04-30 |

## 実装メモ(2026-04-30)

- runtime rescue は `weak_generated_title_review` / `weak_subject_title_review` の直前で実行し、既存 skip 条件本体は変更しない
- `ENABLE_WEAK_TITLE_RESCUE` は default OFF。flag OFF 時は既存挙動を維持
- `no_strong_marker` の narrow 例外は **人名 + 具体イベント語** の AND 条件のみ
- `postgame_strict` 起因の #20 は subtype / strict path が 295-QA scope のため、本便では helper / predicate 側の境界整備まで

## 1. 目的

289 で silent skip 解消後、品質 audit で抽出した **A/B 群 7 候補**を **Gemini 不要・local regex / 既存 metadata だけで publish or review path に戻す**。

「！」を足してバリデータ通すだけの対応は **禁止**。**人名 + 具体イベント明確** な title は `no_strong_marker` 判定の narrow 例外で skip 回避、related_info_escape / blacklist_phrase は source_title から regex で再構成。

## 2. 背景:救済対象 7 候補(本日 audit ベース)

| # | source_title | gen_title | skip_reason | 救済方針 |
|---|---|---|---|---|
| #4 | 【巨人】泉口友汰が屋外フリー打撃再開 バックスクリーン右横へ特大弾も披露 脳しんとうから1軍復帰へ前進 | 泉口友汰、昇格・復帰 関連情報 | weak_subject_title:related_info_escape | **related_info_escape rescue**: src_title から人名+イベント抽出、「泉口友汰選手、屋外フリー打撃再開 1軍復帰へ前進」 |
| #5 | 巨人・山崎伊織と西舘勇陽が復帰へ前進 | 西舘勇陽、昇格・復帰 関連情報 | weak_subject_title:related_info_escape | **2 名併記 rescue**: 「山崎伊織・西舘勇陽が復帰へ前進」 |
| #7 | 【巨人評論】5回のピンチは阿部監督から竹丸へのメッセージ ハーラートップに並ぶ白星で新人王狙えると宮本和知氏 | 阿部コメント整理 ベンチ関連の発言ポイント | weak_generated_title:blacklist_phrase | **blacklist_phrase strip + src_title 使用**: 「阿部監督から竹丸へのメッセージ 宮本和知氏が新人王期待」 |
| #14 | 「左手おとりに使って右手出す練習やっていた」タッチかわし神生還 | 首脳陣「左手おとりに使って…」ベンチ関連発言 | weak_generated_title:no_strong_marker | **人名 backfill**(平山功太、metadata or context から)+ src_title 使用 |
| #16 | 【巨人】竹丸和幸、内海投手コーチの誕生日に4勝目「今日俺の誕生日」と何度も伝えられ… | 内海「今日俺の誕生日」 関連発言 | weak_generated_title:no_strong_marker | **主役 backfill**(竹丸和幸を主語に): 「竹丸和幸、内海投手コーチの誕生日に4勝目」 |
| #17 | 【巨人】平山功太が神走塁「スイム」を成功したワケ | 平山功太が神走塁「スイム」を成功したワケ | weak_generated_title:no_strong_marker | **人名+イベント明確で narrow 例外**(no_strong_marker でも publish 通す) |
| #20 | 巨人・平山功太が好走塁で魅せる！ 神業スライディングに片岡氏「タイミングは完全にアウトだと思ったんですが…」と感嘆 | 巨人戦 平山功太の試合後発言整理 | postgame_strict required_facts_missing | **subtype 再分類 + src_title 使用**: postgame ではなく player_quote に分類、src_title 使用 |

## 3. 実装方針(narrow、Gemini 不要)

### A. 新 helper 拡張: `src/weak_title_rescue.py` (新規)
または `src/title_player_name_backfiller.py` 拡張(277-QA helper を活用)

3 種 rescue logic:

**A-1. related_info_escape rescue**
- gen_title に「〇〇、昇格・復帰 関連情報」「〇〇、登録抹消 関連情報」 等 escape pattern 検出
- src_title に **人名 + イベント動詞**(復帰、再開、登録抹消、特大弾、昇格、合流 等) を regex で抽出
- 抽出可能 → 「〇〇選手が[イベント]、[文脈]」形式に再構成
- 抽出不可 → 既存 escape skip 維持
- 2 名併記対応:src_title に「○○と××が」 pattern → 「○○・××が[イベント]」

**A-2. blacklist_phrase strip rescue**
- gen_title 末尾の `ベンチ関連の発言ポイント` / `ベンチ関連発言` strip
- src_title に話者(監督/コーチ/選手名)+ 引用句 + 文脈あり → src_title から再構成
- 例: 「【巨人評論】5回のピンチは阿部監督から竹丸へのメッセージ 〇〇氏」
  → 「阿部監督から竹丸へのメッセージ 〇〇氏」(【巨人評論】prefix strip 程度)

**A-3. no_strong_marker narrow 例外**
- 既存 `is_weak_generated_title` 判定に **narrow 例外条件** 追加:
  - title に **固有人名(選手/コーチ/監督/評論家)が regex で 1 名以上明示**
  - title に **具体イベント語**(神走塁/4勝目/好走塁/神生還/特大弾/初本塁打/ホームラン/サヨナラ/タイムリー/復帰/抹消/昇格/コメント/談話/感嘆 等)が 1 つ以上含む
  - **両方満たす場合のみ** no_strong_marker 判定 skip(= publish 通す)
- 「！」だけで通すパターンは **禁止**(narrow 例外条件 = 人名 + イベント語の AND)

### B. integration 場所

- `src/rss_fetcher.py` の `_evaluate_post_gen_validate` 周辺(L7633-7755)
- skip 直前に rescue helper 呼出
- rescue 成功 → title 上書き + 既存 path に戻す
- rescue 失敗 → 既存 skip 維持(silent ではなく 289 ledger に流れる)

### C. env flag

- `ENABLE_WEAK_TITLE_RESCUE` default OFF
- deploy 便で `--update-env-vars ENABLE_WEAK_TITLE_RESCUE=1` で ON
- rollback: `--remove-env-vars=ENABLE_WEAK_TITLE_RESCUE` 即時無効化

### D. 触ってよい file (write scope)

- `src/weak_title_rescue.py`(新規 helper、推奨)
- `src/title_player_name_backfiller.py`(277-QA helper 既存、拡張可)
- `src/title_validator.py`(no_strong_marker narrow 例外、`is_weak_generated_title` 判定)
- `src/rss_fetcher.py`(integration 1 ブロック追加)
- `tests/test_weak_title_rescue.py`(新規)
- `doc/active/290-QA-weak-title-rescue-backfill.md`(本 file、status 更新)

### E. 不可触 file

- `.github/workflows/**`
- `src/guarded_publish_runner.py`(281-QA scope)
- `src/publish_notice*`(289 scope)
- `src/sns_topic_publish_bridge.py`(pre-existing dirty)
- `src/gemini_preflight_gate.py`(282-COST scope)
- `src/gemini_cache.py` / `src/llm_call_dedupe.py`(229-COST 不変)
- automation / scheduler / env / secret / `.codex/automations/**`
- prosports / SEO / X 自動投稿 / Team Shiny From / WP REST 直接呼出
- `_evaluate_post_gen_validate` 判定 logic 本体(rescue は呼出 wrapper のみ追加、skip 条件本体は不変)
- subtype evaluator(295-QA scope、290 では触らない)
- 既存 `BACKLOG_NARROW_*` 定数

## 4. 必須デグレ試験(`tests/test_weak_title_rescue.py`)

### 4-A. 救済対象 7 候補の rescue
- [ ] fixture #4: 「泉口友汰、昇格・復帰 関連情報」+ src_title「泉口友汰が屋外フリー打撃再開」 → rescue「泉口友汰選手、屋外フリー打撃再開」
- [ ] fixture #5: 「西舘勇陽、昇格・復帰 関連情報」+ src_title「山崎伊織と西舘勇陽が復帰へ前進」 → rescue「山崎伊織・西舘勇陽が復帰へ前進」
- [ ] fixture #7: 「阿部コメント整理 ベンチ関連の発言ポイント」+ src_title「阿部監督から竹丸へのメッセージ 宮本和知氏」 → rescue「阿部監督から竹丸へのメッセージ 宮本和知氏」
- [ ] fixture #14: 「首脳陣『…』ベンチ関連発言」+ context「平山功太」 → rescue「平山功太『左手おとりに…』神生還」(or 同等)
- [ ] fixture #16: 「内海『今日俺の誕生日』 関連発言」+ src_title「竹丸和幸、内海投手コーチの誕生日に4勝目」 → rescue「竹丸和幸、内海投手コーチの誕生日に4勝目」
- [ ] fixture #17: 「平山功太が神走塁『スイム』を成功したワケ」(no_strong_marker) → narrow 例外で publish 通す(rescue 不要、skip 回避のみ)
- [ ] fixture #20: 「平山功太が好走塁 片岡氏『…』感嘆」(no_strong_marker、人名+イベント明確) → narrow 例外で publish 通す or src_title rescue

### 4-B. 救済**しない**べき(C/D/E 群が誤って publish されない)
- [ ] fixture #1, #3 グッズ告知(「コジコジ」「NIKE」)→ 救済しない、既存 skip 維持
- [ ] fixture #19 ロッキーズ・菅野智之 → 救済しない、巨人/MLB 混線判定維持
- [ ] fixture #21 岡本和真 ブルージェイズ → 救済しない、close_marker 維持
- [ ] fixture #2 又木「初勝利」記念グッズ → 救済しない(subtype 誤分類は 295 対象、290 では触らない)
- [ ] fixture #6 ウィットリー pregame → 救済しない(subtype 誤分類 295 対象)
- [ ] fixture #8 プロ野球きょうの見どころ(主語抜け+混線) → 救済しない、既存 skip 維持
- [ ] fixture #18 gen_title 内容ズレ(平山 vs 竹丸) → 救済しない(別便)

### 4-C. 既存 publish/mail 導線維持
- [ ] 既存 publish 通知従来通り
- [ ] 既存 review/hold 通知従来通り(267-QA dedup 不変)
- [ ] 289 post_gen_validate 通知導線維持(救済失敗時は 289 ledger に流れる)
- [ ] guarded_publish_history scan 不変

### 4-D. 安全系(回帰禁止)
- [ ] 事実捏造禁止: src_title / metadata に **無い** 人名を rescue で title に挿入しない fixture
- [ ] 一軍/二軍混線 fixture → 救済しない、既存判定維持
- [ ] スコア矛盾 fixture → publish しない
- [ ] 死亡/重傷/救急/意識不明 token + 巨人選手 fixture → 救済しない(266-QA hard_stop 維持)
- [ ] duplicate guard 維持(263-QA 同 source_url 既 publish の rescue は禁止)

### 4-E. 環境不変
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] SEO/noindex/canonical/301 不変
- [ ] X 自動投稿 path 不変
- [ ] Team Shiny From 不変
- [ ] Scheduler 頻度変更なし
- [ ] 新 subtype 追加なし

### 4-F. コスト
- [ ] Gemini call 0 増(本変更で LLM 呼出追加なし、regex / metadata 由来のみ)
- [ ] 229-COST cache_hit 維持
- [ ] 282-COST preflight 不変

### 4-G. env flag
- [ ] flag OFF default で本番挙動不変(rescue 動かず、既存 skip 維持)
- [ ] flag ON で rescue 有効化
- [ ] flag toggle で挙動切替確認

### 4-H. baseline pytest
```
cd /home/fwns6/code/wordpressyoshilover
python3 -m unittest tests.test_weak_title_rescue -v 2>&1 | tail -20
python3 -m unittest discover tests 2>&1 | tail -10
# baseline (origin/master = 4be818d): 1851 tests / 7 pre-existing fails
# 期待: 1851 + N 新規 / failures=7 不変 / errors=0
```

## 5. deploy 要否

- commit + push のみ(本便)
- 本番反映は **fetcher (yoshilover-fetcher) image rebuild + flag ON** 必要
- deploy 便は別 fire(289 deploy 後 GH Actions green + user 明示 GO で起動)
- env flag で OFF/ON 切替推奨

## 6. rollback 条件

- commit revert で即時 rollback
- env flag remove で即時無効化(image rollback 不要)
- image rebuild 後問題発生時は前 image (`yoshilover-fetcher:4be818d`) に戻す

## 7. 完了条件(7 点 contract)

1. commit hash(290 impl)
2. pushed to origin/master
3. GH Actions Tests workflow = success(baseline 7 fails 維持)
4. (deploy 便で)fetcher image 反映 + flag ON
5. (deploy 後)live log で **A/B 7 候補 type が publish or review path に流れる**確認
6. (deploy 後)既存 publish/review/hold mail / 289 post_gen_validate 通知 不変
7. (deploy 後問題時)rollback path 確認可能

## 8. 重要 contract(user 明示)

- **「！」を足してバリデータ通すだけは禁止**:no_strong_marker narrow 例外条件 = **人名 + 具体イベント語の AND**
- **不明なものは publish しない**:rescue 失敗時は既存 skip 維持(289 ledger 経由 mail 化)
- **事実捏造禁止**:src_title / metadata に無い人名・数字・イベントを rescue で挿入しない
- **D/E 群対象外**:subtype 誤分類(295)/ MLB / グッズ系 は触らない
- 救済 candidate は **A 1 件 + B 6 件 = 7 件のみ**(audit ベース、新規 candidate も同 pattern なら自動救済 OK)

## 9. 不変方針(継承)

- ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- SEO/X/Scheduler/Team Shiny From / Gemini call 全部不変
- 新 subtype 追加なし
- 既存 publish/mail 導線壊さない
- 289 post_gen_validate 通知導線不変(救済失敗時は流れる)
