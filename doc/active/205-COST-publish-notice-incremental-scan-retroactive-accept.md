# 205-COST-publish-notice-incremental-scan-retroactive-accept

| field | value |
|---|---|
| ticket_id | 205-COST-publish-notice-incremental-scan |
| priority | P2(retroactive accept) |
| status | **LIVE_RETROACTIVE_ACCEPT**(2026-04-30 16:42 JST に 289 deploy 経由で暗黙 carry) |
| owner | Claude(管理) / Codex(impl 22bc09b) |
| lane | COST |
| ready_for | (本 ticket 完了、release management 観点で記録) |
| blocked_by | (なし) |
| doc_path | doc/active/205-COST-publish-notice-incremental-scan-retroactive-accept.md |
| created | 2026-04-30 |
| commit | `22bc09b`(2026-04-30 朝、CI green) |
| live_image | `publish-notice:4be818d`(289 deploy 経由) |
| accept_mode | **retroactive**(user 明示 hold だったが 289 deploy で暗黙 carry、process violation として記録) |

## 1. 経緯

### 朝 (~13:00 JST)
- user 判断: **205-COST hold**(P0 観察中、publish-notice rebuild risk 回避)
- 理由: publish-notice rebuild = mail 経路 touch、P0 デグレ risk

### 16:42-17:00 JST(289 deploy)
- **暗黙 carry**: `publish-notice:dc02d61 → :4be818d` の image 切替で、間の commit `22bc09b`(205-COST)が **publish-notice src(`publish_notice_scanner.py`)に変更を含む**ため、image に carry された
- 検出:**deploy 後の retroactive verify**(私が user 指摘で 17:10 JST 頃確認)
- 観測:`[scan] emitted=10 skipped=27110 cursor_before=...+09:00 cursor_after=...+09:00` = cursor-based incremental scan が live 動作

### 17:15 JST(retroactive accept)
- user 判断: **rollback しない、retroactive accept**
- 理由:rollback = 289 post_gen_validate 通知も失う、205-COST は cost 削減方向で挙動破壊性なし

## 2. 205-COST 内容(commit 22bc09b)

publish-notice の scan logic を **full-scan → cursor-based incremental scan** に変更:
- `cursor_before` / `cursor_after` で前回 scan 位置を track
- 新規 record のみ評価 = scan 計算量削減
- recent_window 安全網(古い record も一定期間内なら拾う)
- `emitted=0 reason log` 追加(silent 防止)
- Team Shiny From 不変、267-QA dedup 不変

## 3. live 観察(2026-04-30 16:55 JST 以降)

- cursor 前進中、scan 動作正常
- `skipped=27110+`(初回 full-scan 状態の名残)→ 次第に減少予想
- emitted=10/run(289 cap 維持)
- mail send success、errors=0
- Team Shiny From `y.sebata@shiny-lab.org` 維持確認
- publish/review/hold mail 経路維持(17:10 JST sent=1 post_id=64104 確認)

## 4. process violation 記録

### 違反内容
- user 明示 hold ticket が、別 ticket(289)の image rebuild で **暗黙 carry された**
- deploy 前に build に含まれる commit 一覧を user に提示していなかった
- HOLD ticket 混入の自動検出機構なし

### 影響評価
- 結果挙動:cost 削減方向、デグレなし、observation 通る
- 結果容認だが、**process としては再発 risk**

## 5. 再発防止(294-PROCESS-release-composition-gate で別 ticket 化)

以下を policy 化:
- publish-notice / fetcher / 他 image rebuild 前に **`git log <prev_image_tag>..<new_image_tag>` の commit 一覧を user に提示**
- HOLD ticket 該当 commit があれば **build 前に停止**、user 明示 GO 必要
- deploy report の「### release composition」section 必須化(carry commit 全部明記)

## 6. 完了条件(retroactive accept として)

- [x] live 動作確認(cursor scan、mail emit、error 0)
- [x] Team Shiny From 維持
- [x] 既存 publish/review/hold mail 経路維持(17:10 sent=1 確認)
- [x] 289 deploy report への「205-COST carried」明記(本 doc 経由)
- [ ] 294-PROCESS-release-composition-gate 起票(別 task)

## 7. 関連 ticket

- 22bc09b 自体は単独 ticket file 無し(本 doc が retroactive 起票)
- 289-OBSERVE-post-gen-validate-mail-notification(本 carry の親)
- 294-PROCESS-release-composition-gate(再発防止、本 ticket から派生)
- doc/waiting/205-gcp-runtime-drift-audit.md(別 ticket、205 番衝突は CLAUDE.md numbering policy 違反だが既歴史)
