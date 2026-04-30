# 280-QA-summary-excerpt-cleanup

| field | value |
|---|---|
| ticket_id | 280-QA-summary-excerpt-cleanup |
| priority | P2 (品質改善 series 4/4) |
| status | READY_FOR_FIX |
| owner | Claude (audit/draft) → Codex (実装委譲) |
| lane | QA |
| ready_for | Codex narrow 実装便 fire(279 完了後、scope 重複検討) |
| blocked_by | 279-QA (publish-notice src 重複の可能性、scope 確認後並走可) |
| doc_path | doc/active/280-QA-summary-excerpt-cleanup.md |
| created | 2026-04-30 |
| series | 277(title player name) → 279(mail subject) → 278(RT cleanup) → **280**(summary excerpt) |

## 1. 目的

メール本文の summary / excerpt をユーザーが判断できる内容に整える。`summary: (なし)` を減らし、元記事断片の重複と絵文字過多を抑え、review/hold 理由を具体化する。

## 2. 背景

会議室 Codex 監査結果:

NG:
- summary: (なし) で判断できない
- 元記事断片の重複
- 絵文字過多
- review 理由が「本文確認推奨」のような抽象表現で止まる

OK 期待:
- summary が常に意味のある 1-3 行
- source 名 / subtype / publish 時刻 / URL / reason は維持
- review/hold 理由は具体的(例「発言者不明」「subtype unresolved」「duplicate guard hit」)

## 3. Codex に渡す作業範囲(write scope)

### 実装前確認(read-only first)
1. publish-notice の summary / excerpt 生成 path 特定:
   - `src/publish_notice*` 内
2. 既存 summary 生成 logic と (なし) になる条件を確認
3. review reason の現 format 確認(「本文確認推奨」だけで終わる path)
4. excerpt 由来の元記事断片重複の発生 path
5. 絵文字を入れる path 特定(prompt or post-processor)
6. 277-QA で導入予定の `review_reason=title_player_name_unresolved` 等との整合確認
7. 279-QA の subject classifier との重複機能がないか確認

### 実装(narrow fix only)
- summary 生成 helper を整理:
  - 1 行目: subtype 別の判断要素(例「発言者: 〇〇 / subtype=postgame / age=2h」)
  - 2 行目: 元記事 source 名 + URL
  - 3 行目: review/hold reason の具体化(下記 mapping)
- review reason 具体化 mapping:
  - `title_player_name_unresolved` → 「タイトルから人名特定不可、source body も人名未掲載」
  - `subtype_unresolved` → 「subtype=default/other で 24h 経過、明示 subtype が取れず」
  - `duplicate_same_source_url` → 「同 source URL の publish 既存(post_id=N)」
  - `hard_stop_*` → 「hard_stop reason: <token list>」
  - その他 → 既存 reason をそのまま渡す
- 絵文字の overuse を抑制(冒頭 1 個まで、本文中の連続絵文字を strip)
- 元記事断片の重複を 1 箇所のみに(title と body 両方に同文を出さない)

### 触ってよい file (write scope 候補)
- `src/publish_notice*.py` (summary/excerpt narrow fix)
- `tests/test_publish_notice*.py` (summary fixture 拡張)
- 新規 helper: `src/mail_summary_builder.py` 等

### 不可触 file
- `.github/workflows/**`
- `src/guarded_publish_runner.py`
- `src/yoshilover_fetcher*` / `src/draft_body_editor*` (本 ticket 外)
- `src/sns_topic_publish_bridge.py` (pre-existing dirty)
- automation / scheduler / env / secret / `.codex/automations/**`
- SMTP / Team Shiny From 関連
- 279-QA で触る subject classifier path(scope 重複時は 279 完了後 narrow に)

## 4. 実装前に必要な確認(Codex 必須)

- [ ] summary/excerpt 生成 logic と (なし) 条件
- [ ] review reason の token と message mapping の現状
- [ ] excerpt 由来重複の発生箇所
- [ ] 絵文字混入 path
- [ ] 277/279 で emit 予定の review_reason との整合
- [ ] 205-COST incremental との衝突なし確認

## 5. 必須デグレ試験(acceptance test 設計)

### 5-A. summary 品質
- [ ] fixture: 通常 publish → summary 1-3 行、subtype/source/age 記載
- [ ] fixture: review/title_player_name_unresolved → reason 具体化文言
- [ ] fixture: hold/duplicate_same_source_url → reason に既存 post_id 記載
- [ ] fixture: hold/hard_stop_death → reason 具体化
- [ ] fixture: 元記事に絵文字 5 個 → summary は 1 個まで
- [ ] fixture: source body と title が同文 → summary に 1 度のみ表示

### 5-B. mail 通知のデグレ試験(回帰禁止)
- [ ] summary が空 (なし) のメールを出さない
- [ ] publish/review/hold/古い候補通知が引き続き届く
- [ ] Team Shiny From / 送信先 不変
- [ ] GitHub noreply 通知を巻き込まない
- [ ] 同一 post_id の通知爆発禁止(267-QA dedup 維持)

### 5-C. publish-notice 内部(回帰禁止)
- [ ] cursor-based scan の挙動を破壊しない
- [ ] 279-QA subject classifier との衝突なし
- [ ] silent draft / backlog / hold を作らない

### 5-D. コスト系のデグレ試験(回帰禁止)
- [ ] Gemini call を増やしていない(summary 生成は LLM 呼び出さない、既存 metadata から構築)
- [ ] log 爆発を増やさない(各 trigger で log 行数 baseline 比較)

### 5-E. mock / fixture coverage
- [ ] 新 helper を呼ぶ全 mail send mock に method 定義
- [ ] 各 reason mapping の fixture を追加

### 5-F. 必須コマンド
```
cd /home/fwns6/code/wordpressyoshilover
python3 -m unittest discover tests 2>&1 | tail -10
# 期待: 1820 + 新規 N tests, failures=0, errors=0
```

## 6. deploy 要否

- commit + push のみ
- 本番反映は publish-notice job image rebuild + update 必要(別便、user 判断)
- 279-QA と bundle するのが効率的(同 job)

## 7. rollback 条件

- 本 ticket commit を revert すれば即時 rollback
- 本番 image rebuild 後問題発生時は前 image (`:dc02d61` 系列)に job revision 戻す
- env flag 新規追加しない

## 8. 優先順位

- series 内: **4/4**
- 理由: summary 改善は判断補助の最後の lap、件名(279)で粗判断できれば summary 改善は次点
- 279 と scope 重複(publish-notice src)なので 279 完了後に narrow lane で実施

## 9. 今 vs 後

- 今: ticket 起票 + デグレ試験設計 + Codex narrow 実装(279 完了後、commit + push)
- 後: publish-notice image rebuild は 279 と bundle で user 判断
- HOLD 条件: 277-QA と同じ + Team Shiny From 不変 + 267-QA dedup 不変
