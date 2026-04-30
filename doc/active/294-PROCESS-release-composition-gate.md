# 294-PROCESS-release-composition-gate

| field | value |
|---|---|
| ticket_id | 294-PROCESS-release-composition-gate |
| priority | P1(release management、HOLD ticket 暗黙 carry 再発防止) |
| status | DESIGN_DRAFTED |
| owner | Claude(設計)→ user 判断後 Codex impl |
| lane | PROCESS |
| ready_for | user 明示 GO で impl 起票 |
| blocked_by | (なし) |
| doc_path | doc/active/294-PROCESS-release-composition-gate.md |
| created | 2026-04-30 |

## 1. 目的

image rebuild deploy 前に **target image に含まれる commit 一覧を必ず user に提示** する gate を追加。HOLD 中 ticket が別 deploy に **暗黙 carry** されることを防ぐ。

## 2. 背景

### 2026-04-30 incident
- 205-COST が user 明示 HOLD だったが、289-OBSERVE deploy で publish-notice image を `:dc02d61 → :4be818d` に切替た際に **間の 22bc09b commit(205-COST publish-notice src 変更)が暗黙 carry**
- 結果は容認(cost 削減方向、デグレなし)だが process としては再発 risk
- 詳細:doc/active/205-COST-publish-notice-incremental-scan-retroactive-accept.md

### 真因
- deploy 便 prompt に「prev → new image tag 間の commit 一覧 verify」step がない
- HOLD ticket 自動検出機構がない
- deploy report 後 retroactive verify が user 負担

## 3. 対象範囲

### 範囲内
- deploy 便 Codex prompt の **「step 0: release composition verify」** 標準化
- 各 deploy 便で `git log <prev_image_commit>..<new_image_commit>` を Final report 冒頭に出力
- HOLD ticket 一覧との照合(user 提示)
- HOLD 該当時の **build 前停止 + open_questions**

### 範囲外
- 既存 deploy ticket への遡及修正
- doc/done 配下の retroactive 修正

## 4. user-visible な受け入れ条件

1. 全 deploy 便 prompt に「release composition verify」step 標準化
2. deploy report の冒頭に「### release composition」section
   - 含まれる commit list(hash + message 1 行目)
   - 各 commit の HOLD/active status(doc/active/* / doc/waiting/* と照合)
   - HOLD 該当 0 確認 or HOLD 該当の明示
3. HOLD 該当 commit 検出時:
   - **build を実行しない**(image 不在のまま停止)
   - Final report で `open_questions_for_claude` に明示
   - user 判断後に next step
4. 既存 deploy 便への影響:本 ticket impl 後の deploy 便 prompt 全部に reflect

## 5. 必須デグレ試験

### A. deploy 便 prompt template の更新
- [ ] step 0 で `git log` 実行 + commit 一覧出力
- [ ] HOLD ticket list と照合 logic
- [ ] HOLD 該当時 build 前停止 fixture(test 化、別 mock で deploy simulate)

### B. 既存 deploy 経路維持
- [ ] 281-QA / 282-COST / 277-QA pattern の deploy 便が引き続き通る(HOLD 該当無し)
- [ ] HOLD 該当無し時は既存 deploy 経路と挙動同じ
- [ ] release composition section が deploy report に追加されるだけ、build 動作不変

### C. HOLD list の管理
- [ ] HOLD list source = `doc/waiting/*.md` + 明示的 hold 状態の active ticket(status=DESIGN_DRAFTED 等)
- [ ] HOLD list 更新は手動 or 自動?(impl 時判断)

### D. 環境不変
- [ ] env / Scheduler / SEO / X / Team Shiny / Gemini call 全部不変(本 ticket は process 改善のみ)

## 6. impl 案(参考、impl 時 Codex 検討)

### A. deploy 便 prompt template に標準 step 追加
- 既存 deploy 便 prompt の冒頭に:
  ```
  ## step 0: release composition verify
  
  prev_image_commit=<old image tag commit>
  new_image_commit=<head>
  
  git log $prev_image_commit..$new_image_commit --oneline
  
  HOLD ticket 確認:
  for each commit hash, ticket_id を抽出 → doc/waiting/<ticket>.md or doc/active/<ticket-with-HOLD>.md と照合
  
  HOLD 該当 0 → 続行
  HOLD 該当 ≥ 1 → 停止 + open_questions for user
  ```
- Codex prompt template の boilerplate に組み込み

### B. CLAUDE.md ルール追加
- §32 等の新 section で「deploy 便 fire 前に release composition verify 必須」明文化

### C. 自動化 helper(future)
- `scripts/release_composition_check.sh`(deploy 便 prompt から呼ぶ helper)
- 入力:prev image tag, new image tag
- 出力:commit 一覧 + HOLD 該当判定

## 7. deploy 要否

- impl 自体は **deploy 不要**(process / doc 改善)
- Codex prompt template 更新 → 次の deploy 便から適用
- スクリプト追加なら commit + push のみ

## 8. rollback 条件

- 本 ticket impl を revert すれば deploy 便 prompt が元に戻る
- HOLD 該当検出 logic が誤検知した場合は手動 override(`--skip-composition-check` flag 等)

## 9. 優先順位

- 全体:289 完遂 + 24h 安定後の整理 phase
- 本日 incident で必要性判明、近日中に着手推奨

## 10. owner

- Claude:設計 + Codex prompt template 更新
- Codex:helper script(必要時)
- user:HOLD 該当時の最終判断

## 11. 不変方針(継承)

- 本 ticket は **process 改善のみ**、コード挙動変更なし
- deploy 経路の挙動不変
- HOLD list 管理を user 負担にしない(自動照合推奨)
