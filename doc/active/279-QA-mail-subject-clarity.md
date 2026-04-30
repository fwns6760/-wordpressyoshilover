# 279-QA-mail-subject-clarity

| field | value |
|---|---|
| ticket_id | 279-QA-mail-subject-clarity |
| priority | P1 (品質改善 series 2/4) |
| status | READY_FOR_FIX |
| owner | Claude (audit/draft) → Codex (実装委譲) |
| lane | QA |
| ready_for | Codex narrow 実装便 fire(277 完了後) |
| blocked_by | (なし、独立。277 と scope disjoint=publish-notice src のみなので並走可) |
| doc_path | doc/active/279-QA-mail-subject-clarity.md |
| created | 2026-04-30 |
| series | 277(title player name) → **279**(mail subject) → 278(RT cleanup) → 280(summary excerpt) |

## 1. 目的

メール件名だけで **公開済み / 要 review / hold / 古い候補 / X 見送り** の状態が判別できるようにする。GitHub 通知と混ざらず、subtype と freshness も件名で見える。Team Shiny From は維持。

## 2. 背景

会議室 Codex 監査結果:

NG: 件名が「【要確認】〜 | YOSHILOVER」だけで、公開済みなのか review なのか hold なのかが分からない。古い候補も同じ prefix。

OK 期待(件名例):
- 【公開済｜lineup】巨人二軍スタメン、丸佳浩が1番左翼
- 【要review｜postgame】〇〇投手コメント:発言者確認が必要
- 【hold｜duplicate】同一 source_url 重複候補
- 【要確認(古い候補)｜comment】〇〇コーチ発言メモ

## 3. Codex に渡す作業範囲(write scope)

### 実装前確認(read-only first)
1. publish-notice job の subject 生成 path 特定:
   - `src/publish_notice*` (現 image `:dc02d61` 由来)
2. mail_type / mail_class / subtype / freshness が既に内部で持たれているか確認:
   - 公開済み = `kind=per_post status=sent` で `record_type=publish`
   - 要 review = 267-QA 由来 review/hold notification record
   - hold = 同上、reason=duplicate / hard_stop
   - 古い候補 = age > 24h の backlog 由来
3. 既存 prefix 「【要確認】」「【公開】」等の生成 logic を確認
4. Team Shiny From が維持されているか確認(変更禁止)

### 実装(narrow fix only)
- subject prefix を以下に拡張(既存 prefix を rename ではなく拡張):
  - **【公開済｜<subtype>】<title>**
  - **【要review｜<subtype>】<title>**
  - **【hold｜<reason>】<title>** (reason=duplicate / hard_stop_*)
  - **【要確認(古い候補)｜<subtype>】<title>** (age > N h backlog)
  - **【X見送り｜<subtype>】<title>** (X post suppress 候補、当面 publish/review path のみで OK)
- subject 生成 helper を 1 関数に集約
- GitHub 通知混入を防ぐため、subject に固有 token (例「| YOSHILOVER」)維持
- Team Shiny From / 送信先 fwns6760@gmail.com は不変

### 触ってよい file (write scope 候補)
- `src/publish_notice*.py` (subject 生成 narrow fix)
- `tests/test_publish_notice*.py` (subject fixture 拡張)
- 新規 helper: `src/mail_subject_classifier.py` 等

### 不可触 file
- `.github/workflows/**`
- `src/guarded_publish_runner.py` (P0 復旧 chain)
- `src/yoshilover_fetcher*` / `src/draft_body_editor*` (本 ticket 外)
- `src/sns_topic_publish_bridge.py` (pre-existing dirty)
- automation / scheduler / env / secret / `.codex/automations/**`
- SMTP 設定 / Team Shiny From 関連 env

## 4. 実装前に必要な確認(Codex 必須)

- [ ] publish-notice の record schema(`kind`, `record_type`, `reason`, `subtype`, `age` 等)
- [ ] 現 subject 生成 path の関数名と call site
- [ ] 既存 subject prefix 一覧と current 生成 logic
- [ ] freshness/age threshold の置き場(既存 24h 等の定数)
- [ ] 205-COST incremental scan(未 deploy)との衝突がないか確認
- [ ] 267-QA の review/hold notification 形式を破壊しないか確認

## 5. 必須デグレ試験(acceptance test 設計)

### 5-A. mail subject 品質
- [ ] fixture: publish 通知 → 「【公開済｜lineup】〜」
- [ ] fixture: review 通知 → 「【要review｜postgame】〜:発言者確認が必要」
- [ ] fixture: hold/duplicate → 「【hold｜duplicate】〜」
- [ ] fixture: hold/hard_stop_death → 「【hold｜hard_stop_death】〜」
- [ ] fixture: 古い backlog (age > 24h) → 「【要確認(古い候補)｜comment】〜」
- [ ] fixture: 全 subject に「| YOSHILOVER」固有 token 含む

### 5-B. mail 通知のデグレ試験(回帰禁止)
- [ ] publish 通知が届く
- [ ] review / hold 通知が届く
- [ ] 古い候補通知が届く
- [ ] 同一 post_id の通知爆発が起きない(267-QA dedup 維持)
- [ ] **Team Shiny / y.sebata@shiny-lab.org 系 From を維持**
- [ ] From / To を勝手に変更しない
- [ ] GitHub noreply 通知を巻き込まない(subject 固有 token で分離)

### 5-C. publish-notice 内部挙動(回帰禁止)
- [ ] cursor-based scan の挙動を破壊しない(現状 dc02d61 で動作中)
- [ ] 205-COST incremental は未 deploy なので image 反映時の衝突確認
- [ ] silent draft / silent backlog / silent hold を作らない

### 5-D. mock / fixture coverage(275-QA 反省)
- [ ] mail send 系 mock に新 prefix 対応 method 追加
- [ ] subject_classifier helper を呼ぶ全 test mock 整合

### 5-E. 必須コマンド
```
cd /home/fwns6/code/wordpressyoshilover
python3 -m unittest discover tests 2>&1 | tail -10
# 期待: 1820 + 新規 N tests, failures=0, errors=0
```

## 6. deploy 要否

- commit + push のみ
- 本番反映は **publish-notice job image rebuild + update** 必要(別便、user 判断)
- 205-COST も同 job、bundle するか別 lane で出すか要相談
- P0 mail 経路を壊さないため、deploy 前に staging-like dry run 推奨

## 7. rollback 条件

- 本 ticket commit を revert すれば即時 rollback
- 本番 image rebuild 後問題発生時は前 image (`:dc02d61`) に job revision 戻す
- env flag 新規追加しない

## 8. 優先順位

- series 内: **2/4**
- 理由: 件名は user の判断速度に直結、人名抜け(277)と並んで影響大
- 277 と scope disjoint(fetcher/draft_body_editor vs publish-notice)なので並走可

## 9. 今 vs 後

- 今: ticket 起票 + デグレ試験設計 + Codex narrow 実装(commit + push)
- 後: publish-notice image rebuild + job update(P0 観察安定後、user 明示 GO)
- HOLD 条件: 277-QA と同じ + Team Shiny From 不変
