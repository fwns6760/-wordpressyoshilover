# 180 SNS topic intake to publish lane separation(doc-only 整理)

## meta

- number: 180
- owner: Claude Code(設計 / 起票)/ Codex B(実装、必要時のみ別 ticket で fire)
- type: doc-only / lane separation / contract
- status: **READY**(doc-only 整理、即着手可)
- priority: P0.5
- lane: B
- created: 2026-04-26
- depends:
  - 126 SNS topic fire intake(CLOSED `5bfe892`)
  - 127 SNS source recheck and draft builder(CLOSED `2669faa`)
  - 128 SNS topic auto-publish through PUB-004(PARKED、本 ticket 完了が再開前提)
  - PUB-004 publish gate(`doc/done/2026-04/PUB-004-D-...md` / 現行 154 publish-policy)
  - PUB-005 X post gate(`doc/waiting/PUB-005-x-post-gate.md`)

## 背景

repo に以下が並んでいるが、「SNS / X を使う」という言葉が混ざりやすく、**記事ネタ収集レーンと X 投稿レーンの境界が分かりにくい**:

| 既存 ticket | 役割 | 状態 |
|---|---|---|
| 126 SNS topic fire intake | SNS 話題を candidate として取り込む | CLOSED |
| 127 SNS source recheck and draft builder | candidate を primary source で recheck + Draft 化 | CLOSED |
| 128 SNS topic auto-publish through PUB-004 | recheck 済 Draft を PUB-004 gate 経由 publish | PARKED |
| PUB-005 / 147-175 | 公開済み記事を X 投稿(別 lane) | BLOCKED_USER / 部分 IN_FLIGHT |

→ 用語整理 + 境界明文化が必要。

## 整理する考え方(本 ticket の正本)

- **SNS / X 話題検知 lane** = **記事ネタの入口**(126 / 127 / 128 が担当)
- **X 投稿 lane** = **公開済み記事を外へ出す出口**(PUB-005 / 147-175 が担当)
- この 2 lane は **別物として扱う**、混ぜない
- SNS で盛り上がってる**だけ**の話題を直接 publish しない
- SNS 投稿本文の**転載**禁止
- **個人アカウント晒し**禁止
- 炎上 / 誹謗中傷 / 煽り は拾わない
- SNS 由来候補は **必ず source recheck**(127)を通す
- SNS 由来候補は **必ず PUB-004 gate** を通す
- SNS 由来記事は **初期 X 自動投稿対象から除外**、または X eligibility で追加厳格化

## SNS topic lane(126/127/128)の判定 5 種

| 判定 | 意味 | 次 action |
|---|---|---|
| `draft_ready` | source recheck pass + Draft 化完了 | 128 で PUB-004 gate 経由 publish |
| `candidate_only` | candidate に登録、recheck 未完 | 127 で recheck 待ち |
| `hold_sensitive` | sensitive(個人攻撃 / 炎上 / プライバシー懸念)| 人手判断、自動進めない |
| `duplicate_news` | 既出 news / 重複 candidate | dedup skip |
| `reject` | 採用基準外(raw quote 単独 / 個人アカ / 炎上煽り / 誹謗中傷 等) | 候補から除外、ledger に reject 理由記録 |

## reject 条件(明文化)

以下のいずれかに該当する SNS topic は `reject`:
- raw SNS quote をそのまま記事化(本文転載)
- 個人アカウント名 / @handle が記事 title / lead に露出
- 炎上 / 誹謗中傷 / 煽り の twitter chain
- 主要媒体 / 公式 / 中の人 以外の trust tier T3 未満の単独 source
- primary recheck で確認できない speculation / rumor

## SNS 由来記事の X 自動投稿境界

- **初期(PUB-005 unlock 直後 1-2 weeks)**: SNS 由来記事は **X 自動投稿対象外**
- **以降**: PUB-005 / X eligibility evaluator(119)に SNS 由来 flag(`source_origin == "sns_topic"`)を見て**追加 gate**(daily cap 別枠 / 人手 review 必須 等)
- 通常 publish(WP)は SNS 由来も他経路と同じ PUB-004 gate を通れば OK、X 投稿だけ厳しくする

## 128 再開前の前提条件(本 ticket 完了が条件)

128(SNS topic auto-publish through PUB-004)の `blocked_by` に **「180 完了」を追加**。
180 で SNS lane の判定 / reject 条件 / X 投稿境界が明文化されてから 128 を fire する。

## do(本 ticket scope)

- 126 / 127 / 128 の関係を本 doc で整理
- SNS topic lane の判定 5 種 + reject 条件を明文化
- SNS 由来候補 = source recheck 必須 + PUB-004 gate 必須を明文化
- SNS 由来記事 = 初期 X 自動投稿対象外、または追加 gate を明文化
- raw SNS quote / 個人アカ / 炎上 / 誹謗中傷 reject 条件明示
- 128 の `blocked_by` に「180 完了」追加(同 commit で 128 doc 更新)
- PUB-005(X post gate)doc に「SNS 由来記事は初期 X autopost 対象外、または追加 gate 対象」記述追加
- README + assignments に 180 row 追加

## do not(絶対禁止)

- X API live call
- SNS 投稿本文の転載
- 個人アカウント晒し
- 2 ちゃんまとめ風の記事化
- raw SNS signal から直接 publish(必ず source recheck + PUB-004 gate)
- SNS 由来記事の自動 X 投稿(初期は除外、後で追加 gate)
- PUB-004 / PUB-005 gate の bypass
- code 変更(本 ticket は doc-only)
- WP write
- mail 送信
- env / secret 変更
- 既存 ticket のリネーム
- `git add -A`

## acceptance

1. ✓ 180 ticket が `doc/active/` に作成
2. ✓ `doc/README.md` に 180 row 追加
3. ✓ `doc/active/assignments.md` に 180 行追加
4. ✓ 128(`doc/waiting/128-sns-topic-auto-publish-through-pub004.md`)の `blocked_by` または `next_action` に「180 完了」を見える形で追加
5. ✓ PUB-005(`doc/waiting/PUB-005-x-post-gate.md`)に「SNS 由来記事は初期 X autopost 対象外、または追加 gate 対象」記述追加
6. ✓ code 変更なし(`git diff src/ tests/ requirements.txt` 空)
7. ✓ WP write なし、X API call なし、mail 送信なし、env / secret 変更なし

## 関連ファイル更新先

- 新規: `doc/active/180-sns-topic-intake-to-publish-lane-separation.md`(本 file)
- 更新: `doc/README.md`(180 row 追加)
- 更新: `doc/active/assignments.md`(180 row 追加)
- 更新: `doc/waiting/128-sns-topic-auto-publish-through-pub004.md`(blocked_by に 180 追加)
- 更新: `doc/waiting/PUB-005-x-post-gate.md`(SNS 由来記事の X 自動投稿境界 追記)

## 完了後の運用

- 128 を再開する判断は 180 land 後 + user go の 2 条件
- SNS lane の reject 条件 / 判定 5 種は本 doc を正本として 040 repair_playbook / 048 formatter にも参照される(必要時別 ticket で wire up)
- PUB-005 unlock 時、X 投稿 eligibility evaluator(119)で SNS 由来 flag を見るよう変更が必要(別 ticket、本 ticket scope 外)
