# 043 — local runtime の再起動後 auto recovery を正式化

**フェーズ：** ローカル常駐運用の無人化に向けた自動復帰設計
**担当：** Claude Code
**依存：** 042, 現行 Codex automations(`quality-gmail` / `quality-monitor` / `draft-body-editor`)

---

## why_now

- 042 で「再起動すると何が止まり、Codex / Claude を上げ直すと何が戻るか」は明確になったが、**手で上げる前提** のまま。
- 夜間 / 不意の Windows 再起動のたびに人手が必要で、完全無人運用に近づけない。
- メール不達や監視欠落を user が都度気にする運用が残り、039 delivery reliability の観測負担にも効いてくる。
- OS 再起動後に local runtime を **自動復帰** させる設計を 043 として正式化する。

## 042 との分離

- **042** = 手で上げる前提の **監査と最小復旧手順**(reboot で何が止まるか / Codex を起動すれば何が戻るか / Claude は cron runtime ではない境界)
- **043** = 自動復帰に近づけるための **設計**(何を自動で立ち上げるか / Codex app auto-start 要否 / automation ACTIVE 復帰条件 / Claude 非関与の再確認)
- 042 は ticket 単体で現状復旧を閉じる、043 は follow-up として無人化を進める
- 042 の決定事項(Claude は cron 必須 runtime ではない / missed run は次 tick から再開)を 043 も継承する

## purpose

- Windows 再起動後に、Codex runtime と local automation が **人手最小で自動復帰** する条件と手順を固定する。
- 自動化する境界を固定し、**自動化しない境界**(user 判断が残る項目)も明示する。
- 必要な follow-up(OS 設定便 / Codex 実装便)を 1 本に絞る。

## scope

### 自動復帰の対象 / 非対象

**対象(自動復帰を目指す)**
- Codex app の OS 起動時 auto-start(Windows スタートアップ or タスクスケジューラ)
- Codex automation `ACTIVE` 状態の reboot 跨ぎ維持
- `quality-gmail` / `quality-monitor` / `draft-body-editor` 3 本の次 tick 再開
- WSL の on-demand 起動(automation が WSL 経路を呼んだ時に wsl.exe が立ち上がる既定動作)

**非対象(手動 / user 判断を残す)**
- Windows 自動ログイン設定(セキュリティリスクが割に合わない、user 判断に残す)
- Claude 対話セッションの auto-start(Claude は管理レイヤ、cron 実行に不要)
- missed run の自動補填(042 決定を継承、次 tick から再開を正)
- 既存 automation の cadence 変更
- クラウド移行

### OS / app / automation 3 層の条件

**OS 層(Windows)**
- Windows が起動し user アカウントへのログインが完了していること(自動ログインは非対象)
- ネット接続が復帰していること(OS 既定動作に依存、tick 時点で判定)
- WSL が on-demand で起動できる状態を維持(wsl --shutdown / 破損があれば follow-up で対応)

**app 層(Codex)**
- Codex app が OS 起動後に自動で立ち上がること(Windows スタートアップフォルダへ shortcut 配置、またはタスクスケジューラで起動時トリガ)
- Codex app 起動時に既存 `C:\Users\fwns6\.codex\automations\` の 3 automation が `ACTIVE` として読み込まれること(既定挙動、042 で確認済)
- sqlite state / logs が reboot を跨いで保持されること(既定挙動、042 で確認済)

**automation 層(3 本)**
- `quality-gmail`: OS 起動後の次 hourly tick(10:00-23:59 JST 窓内なら次の :00)で `[src:qm] / [src:stale] / [src:none]` いずれかの 4 行メールが送信されること
- `quality-monitor`: OS 起動後の次 hourly tick(:45)で `logs/quality_monitor/<date>.jsonl` に 1 行追記されること
- `draft-body-editor`: OS 起動後の次 hourly tick で `logs/draft_body_editor/<date>.jsonl` に 1 行追記されること(dry-run、published 不可触)

### Claude の位置づけ(042 継承)

- Claude は cron 実行の **必須 runtime ではない**。auto-start 対象にしない。
- Claude は管理・判断・起票・gate 判定の層。reboot 後に Claude セッションを開くのは user が管理便を回したい時のみ。
- handoff 更新 / ticket 管理 / accept 追認は Claude 再開後に手動で行う(043 scope 外)。

### 復帰確認(3 automation)

reboot 後、次 tick 到達時に以下を観測:

| automation | 確認 file | 期待 | 異常時の判定 |
|---|---|---|---|
| quality-monitor | `logs/quality_monitor/<JST date>.jsonl` | 新規行追加 | WSL 経路 fail / 039 段階 2 失敗 |
| quality-gmail | Gmail inbox `fwns6760@gmail.com` | subject `[src:qm/stale/none]` で 1 通 | 039 段階 3 or 4 失敗 |
| draft-body-editor | `logs/draft_body_editor/<JST date>.jsonl` | 新規行追加 | Codex app 再起動失敗 or WSL 経路 fail |

### follow-up 推奨(1 本に絞る)

- **推奨 follow-up**: `Codex app を Windows スタートアップフォルダに shortcut 配置する設定便`
  - owner: user 手動(Claude は GUI 操作を持たない、Codex は OS 設定を触れない)
  - 可逆、コスト増なし、既定 user ログイン前提で自動ログインは不要
  - 設定後は 043 の復帰確認 3 点で検証
- 他候補(タスクスケジューラ登録 / 自動ログイン / WSL auto-start)は **非採用**(複数案を散らさない方針、スタートアップフォルダで十分)
- user 手元作業のため Codex 便は **現時点で不要**

### 不可触

- クラウド移行
- scheduler cadence 変更
- env / secret / mail recipient 変更
- 既存 ticket の fire 順変更
- quality-gmail の内容変更(029 scope)
- quality-gmail の配信経路 contract(039 scope)
- 042 の決定事項(Claude は cron 必須 runtime ではない / missed run は次 tick から再開)

## success_criteria

- 夜間再起動後、Codex app と local automation の **復帰条件が 1 ticket で読める**。
- **人手が必要な箇所と不要な箇所** が本文で一意に分かる(user 手動 = Codex app スタートアップ配置のみ)。
- `quality-monitor` / `quality-gmail` / `draft-body-editor` 3 本について、再起動後の **確認項目が固定** される。
- follow-up が必要な場合、Codex / OS 設定 / user 手動のどれにやらせるかまで切り出せる(現状 user 手動 1 本)。

## non_goals

- クラウド移行
- scheduler cadence 変更
- env / secret / mail recipient 変更
- 既存 ticket の fire 順変更
- quality-gmail の内容変更
- Windows 自動ログイン実装
- Claude 対話セッションの auto-start

## acceptance_check

- auto recovery の対象 / 非対象が明確(本文 scope 節で一意)
- Codex 自動起動の必要性が明記されている(Windows スタートアップフォルダ配置推奨)
- Claude が自動復帰の必須 runtime ではないことが明記されている(042 継承)
- 再起動後の確認手順が ticket 単体で読める(3 automation × 確認 file × 異常判定の表)
- follow-up が 1 本に絞られている(複数案を散らしていない)

## TODO

【】042 との分離(手動復旧 vs 自動復帰)を明記する
【】自動復帰の対象 / 非対象を固定する
【】OS / app / automation の 3 層で自動復帰条件を固定する
【】Codex app auto-start 要否を Windows スタートアップフォルダ配置で推奨する
【】Claude は cron 必須 runtime ではない境界を 042 から継承して明記する
【】missed run は次 tick から再開を 042 から継承して明記する
【】3 automation の復帰確認 file / 期待 / 異常判定を表で固定する
【】Windows 自動ログインを非目標として明記する
【】クラウド移行 / scheduler 変更 / env / secret / mail を不可触として明記する
【】follow-up は user 手動のスタートアップフォルダ配置 1 本に絞ると明記する

## 成功条件

- 再起動後 user が「Codex app を開く」以外の手を動かさず、次 tick で 3 automation が復帰する状態を目指せる設計
- 自動化できない境界(自動ログイン / Claude auto-start)を散らさず、user 判断 1 点に閉じる
- 039 delivery reliability の観測と整合(auto recovery で段階 1 cron fire が自動的に戻る前提)
- follow-up で Codex 便が必要になっても、043 本文から最小 prompt が起草できる粒度
