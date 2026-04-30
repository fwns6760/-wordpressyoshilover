# 278-QA-rt-title-cleanup

| field | value |
|---|---|
| ticket_id | 278-QA-rt-title-cleanup |
| priority | P2 (品質改善 series 3/4) |
| status | READY_FOR_FIX |
| owner | Claude (audit/draft) → Codex (実装委譲) |
| lane | QA |
| ready_for | Codex narrow 実装便 fire(277/279 完了後) |
| blocked_by | (なし、独立。277 と scope disjoint なら並走可) |
| doc_path | doc/active/278-QA-rt-title-cleanup.md |
| created | 2026-04-30 |
| series | 277(title player name) → 279(mail subject) → **278**(RT cleanup) → 280(summary excerpt) |

## 1. 目的

RT 始まり / 公式 X 断片 / グッズ告知系のタイトルを読みやすく整える。RT prefix を落とし、商品名 / 企画名 / イベント名を title 先頭に出す。グッズ・イベント系は off_field として扱う。巨人無関係 RT は止める。

## 2. 背景

会議室 Codex 監査結果:

NG 例:
- 「RT 読売巨人軍 グッズ情報 NEW ERA®カジュアル...」

OK 期待:
- 「NEW ERA®カジュアルキャップ新商品が登場」

巨人無関係 RT は subtype や hard_stop で止める。

## 3. Codex に渡す作業範囲(write scope)

### 実装前確認(read-only first)
1. RT 系 title が生成される path 特定:
   - X 由来 source(`source_kind=twitter` / `source_kind=official_x`)の title 生成 path
   - `src/yoshilover_fetcher*` か `src/sns_topic_publish_bridge*` あたり
2. RT prefix 検出 helper が既にあるか確認(重複実装回避)
3. グッズ / イベント系の subtype 判定(`off_field` / `goods_notice` 等)が既にあるか確認
4. 巨人無関係性の検出(team token / player name の不在検出)が既にあるか確認

### 実装(narrow fix only)
- title head の `RT` / `RT @user` / `RT 〜` prefix を strip する narrow helper
- グッズ・イベント系 source title から商品名 / 企画名を extract して title 先頭に出す
- 巨人無関係 RT(team token / player name 不在 + RT prefix)は subtype=off_field か review fallback
  - 既存 `subtype_evaluator` 系を使う、新規 subtype は追加しない
- RT 元発言者を残したい場合は body 側に保持、title からは外す

### 触ってよい file (write scope 候補)
- `src/title_normalizer*.py` または新規 narrow helper
- `src/yoshilover_fetcher*.py` (RT title narrow fix)
- `src/sns_topic_publish_bridge.py` (要確認、pre-existing dirty)
- `tests/test_title_*.py` / `tests/test_rt_*.py`

### 不可触 file
- `.github/workflows/**`
- `src/guarded_publish_runner.py`
- `src/publish_notice*`
- `src/draft_body_editor*` (本 ticket 外)
- automation / scheduler / env / secret / `.codex/automations/**`
- 新 subtype 追加禁止(既存の `off_field` 等を使う)

## 4. 実装前に必要な確認(Codex 必須)

- [ ] RT prefix 検出 helper の既存有無
- [ ] X 由来 source の title 生成 path 特定
- [ ] off_field / goods_notice 等の subtype 既存判定 logic
- [ ] 巨人 team token list の置き場(関連性判定)
- [ ] 277-QA との scope 重複確認(両者 title 系、disjoint なら並走可)

## 5. 必須デグレ試験(acceptance test 設計)

### 5-A. タイトル品質
- [ ] fixture: title=「RT 読売巨人軍 グッズ情報 NEW ERA®カジュアルキャップ」 → 「NEW ERA®カジュアルキャップ新商品が登場」
- [ ] fixture: title=「RT @TokyoGiants 試合速報」+ team token 有 → RT 落として title 整形
- [ ] fixture: title=「RT @other_team 関係ない投稿」 → subtype=off_field or review fallback
- [ ] fixture: title=「RT」のみ・本文無し → review reason `rt_title_unresolved`
- [ ] fixture: title=「RT」を含むが文中(prefix 以外) → unchanged

### 5-B. 公開・通知導線(回帰禁止)
- [ ] 候補があるのに publish 0 が継続しない
- [ ] silent hold / silent backlog を作らない
- [ ] off_field 判定された RT は draft または review に流れる(silent drop しない)

### 5-C. 安全系(回帰禁止)
- [ ] 死亡 / 重傷 / 救急搬送 / 意識不明系の hard_stop は不変
- [ ] duplicate guard 不変
- [ ] 巨人無関係でも危険系 token があれば優先で止まる
- [ ] 事実捏造禁止(RT 元発言者を別人に書き換えない)

### 5-D. mock / fixture coverage
- [ ] 新 helper を呼ぶ全 test mock に method 定義
- [ ] X source fixture を test に追加(既存 fixture が tweet 系か確認)

### 5-E. 必須コマンド
```
cd /home/fwns6/code/wordpressyoshilover
python3 -m unittest discover tests 2>&1 | tail -10
# 期待: 1820 + 新規 N tests, failures=0, errors=0
```

## 6. deploy 要否

- commit + push のみ
- 本番 image rebuild は **HOLD**(別便で判断)
- 本 fix は draft 生成段階で効く

## 7. rollback 条件

- 本 ticket commit を revert すれば即時 rollback
- image rebuild 後問題発生時は前 image に traffic 戻す
- env flag 新規追加しない

## 8. 優先順位

- series 内: **3/4**
- 理由: 量は多いが、影響度は 277(人名抜け)/ 279(件名)より下
- 277 と scope disjoint なら並走可、要 Codex 監督確認

## 9. 今 vs 後

- 今: ticket 起票 + デグレ試験設計
- 実装: 277 / 279 完了後、または scope disjoint 確認後並走
- 後: image rebuild は user 明示 GO 後
- HOLD 条件: 277-QA と同じ
