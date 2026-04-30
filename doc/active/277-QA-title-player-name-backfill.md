# 277-QA-title-player-name-backfill

| field | value |
|---|---|
| ticket_id | 277-QA-title-player-name-backfill |
| priority | P1 (品質改善 series 1/4、最優先) |
| status | READY_FOR_FIX |
| owner | Claude (audit/draft) → Codex (実装委譲) |
| lane | QA |
| ready_for | Codex narrow 実装便 fire |
| blocked_by | (なし、独立) |
| doc_path | doc/active/277-QA-title-player-name-backfill.md |
| created | 2026-04-30 |
| series | 277(title player name) → 279(mail subject) → 278(RT cleanup) → 280(summary excerpt) |

## 1. 目的

「選手」「投手」「チーム」「巨人スタメン が〜」など人名抜けタイトルを source title / body / summary / speaker / player_name / metadata から **取れる場合は補完** する。

YOSHILOVER は noindex 全公開寄り運用。タイトルが弱いから silent hold するのではなく、補完できるなら publish / review 通知に流す。補完できない場合は review 理由を明確化して通知する(silent hold 禁止)。

## 2. 背景

会議室 Codex 監査結果(本日確認):

NG 例:
- 「選手、登録抹消 関連情報」
- 「投手コメント整理 ベンチ関連の発言ポイント」
- 「巨人スタメン が「2番・二塁」で今季初先発」(主語抜け)

OK 期待:
- 「〇〇選手が登録抹消、球団発表を確認」
- 「〇〇投手「〜」試合後コメント」
- 「吉川尚輝選手が「2番・二塁」で今季初先発」

## 3. Codex に渡す作業範囲(write scope)

### 実装前確認(read-only first)
1. 現タイトル生成 path を特定:
   - `src/yoshilover_fetcher*` (fetcher の title 生成)
   - `src/draft_body_editor*` (draft body editor の title 修整)
   - `src/sns_topic_publish_bridge*` (SNS topic 系)
   - `src/fixed_lane_prompt_builder*` (fixed lane の title)
2. 「選手」「投手」「チーム」「スタメン が」が title head に出る具体 path を特定
3. 既存の player name 補完 helper が無いか確認(重複実装回避)
4. metadata に `speaker` / `player_name` / `subject_player` 等の field がある場合は活用

### 実装(narrow fix only)
- title generator に **player name backfill helper** を追加
  - 入力: 既存 title + source title + body + summary + metadata.speaker + metadata.player_name
  - 出力: 人名が取れたら title 先頭または主語位置に挿入、取れなければ unchanged
  - 役職を明示: 選手 / 投手 / コーチ / 監督 / 氏(metadata.role が取れる場合)
- 取れない場合: title unchanged + review reason に `title_player_name_unresolved` を emit
- silent hold は禁止(従来 publish / review path を維持)

### 触ってよい file (write scope 候補)
- `src/yoshilover_fetcher*.py` (title 生成 path narrow fix のみ)
- `src/draft_body_editor*.py` (title 修整 path narrow fix のみ)
- `src/title_normalizer*.py` または新規 helper file
- `tests/test_title_*.py` (新規/既存 fixture 拡張)

### 不可触 file
- `.github/workflows/**`
- `src/guarded_publish_runner.py` (P0 復旧 chain)
- `src/publish_notice*` (279/280 で別便)
- `src/sns_topic_publish_bridge.py` (pre-existing dirty 残り、278 RT cleanup 検討時のみ慎重)
- automation / scheduler / env / secret / `.codex/automations/**`
- WP REST 直接呼び出し path (本番影響)

## 4. 実装前に必要な確認(Codex 必須)

- [ ] 現タイトル生成 path の path / 関数名を session log に記録
- [ ] 既存の player name 抽出 helper(`extract_player_name` / `metadata_helper` 等)が無いか確認
- [ ] metadata schema(speaker / player_name / role)を確認
- [ ] backfill 後のタイトル長制限(WP / mail subject)を確認
- [ ] silent hold path が無いことを baseline 確認(現状 review reason emit が動いているか)

## 5. 必須デグレ試験(acceptance test 設計)

### 5-A. タイトル品質
- [ ] fixture: source body に「吉川尚輝」記載 + 既存 title「巨人スタメン が「2番・二塁」で今季初先発」 → backfilled「吉川尚輝選手が「2番・二塁」で今季初先発」
- [ ] fixture: 「投手コメント整理」+ metadata.speaker「山田太郎」 → 「山田太郎投手「〜」試合後コメント」
- [ ] fixture: 人名 source 不在 → title unchanged + `review_reason=title_player_name_unresolved` emit
- [ ] fixture: 「選手」「投手」「チーム」だけのタイトル → backfill 試行 or review reason emit
- [ ] fixture: backfill 候補 2 名以上 → 既定で先頭、両名併記禁止(別便で扱う)

### 5-B. 公開・通知導線(回帰禁止)
- [ ] 候補があるのに publish 0 が継続しない(既存挙動維持)
- [ ] silent hold / silent backlog を作らない
- [ ] review reason は logger に emit、publish-notice が拾える形式

### 5-C. 安全系(回帰禁止)
- [ ] 死亡 / 重傷 / 救急搬送 / 意識不明系の hard_stop は不変
- [ ] duplicate guard 不変
- [ ] 事実捏造禁止(source/metadata に無い人名を入れない)

### 5-D. mock / fixture coverage(275-QA 反省)
- [ ] 新 helper を呼ぶ全ての test mock に該当 method を定義
- [ ] sns_topic_publish_bridge / draft_body_editor / fetcher 系の test fixture を調査し、AttributeError 系の broken mock を防ぐ

### 5-E. 必須コマンド
```
cd /home/fwns6/code/wordpressyoshilover
python3 -m unittest discover tests 2>&1 | tail -10
# baseline: 1820 tests, failures=0, errors=0
# 期待: 1820 + 新規 N tests, failures=0, errors=0
```

## 6. deploy 要否

- **commit + push のみ**(Codex commit、Claude push)
- 本番 image rebuild は **HOLD**(P0 観察中、別便で判断)
- title backfill は draft 生成段階で効くので image 更新が反映条件
- 反映時は user 明示 GO 後、image rebuild 1 lane (yoshilover-fetcher または draft-body-editor) を別便で

## 7. rollback 条件

- 本 ticket commit を revert すれば即時 rollback 可
- image rebuild 後の問題発生時は、前 image (`yoshilover-fetcher:453ee24` 等) に traffic 戻す
- env flag は新規追加しない(rollback 簡素化)

## 8. 優先順位

- series 内: **1/4 (最優先)**
- 全体: P0 観察 / CI 緑 / 費用観察より下、メール件名 (279) より上
- 理由: 人名抜けは記事の根本的価値毀損、最影響大

## 9. 今 vs 後

- **今: ticket 起票 + デグレ試験設計 + Codex narrow 実装(commit + push)**
- 後: image rebuild + 本番反映 (P0 観察安定後、user 明示 GO)
- HOLD 条件:
  - live_update ON / ENABLE_LIVE_UPDATE_ARTICLES=1 / SEO / X 自動投稿は触らない
  - duplicate guard 全解除しない
  - default/other 無制限公開しない
  - 新 subtype 追加しない
  - publish-notice 通知導線を壊さない
  - Team Shiny From を変更しない
