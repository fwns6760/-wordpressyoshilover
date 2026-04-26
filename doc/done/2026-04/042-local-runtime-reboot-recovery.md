# 042 — local runtime reboot recovery の監査と復旧手順固定

**フェーズ：** ローカル常駐運用の安定化  
**担当：** Claude Code  
**依存：** 039, 現行 Codex automations(`quality-gmail` / `quality-monitor` / `draft-body-editor`)

---

## 概要

- 現行運用はクラウド常駐ではなく、Windows ローカル PC 上の Codex automation を前提にしている。
- 再起動時に「何が止まり、何を起動し直せばどこまで戻るか」が曖昧だと、メール不達や監視欠落を user が都度気にする運用になる。
- 本 ticket は reboot で止まる runtime を棚卸しし、`Codex を起動すれば戻るもの`、`Claude を起動し直す必要があるもの`、`人手確認が要るもの` を固定する。

## why_now

- quality-gmail / quality-monitor / draft-body-editor はいずれも `execution_environment = local` の Codex automation であり、ローカル PC とネット接続に依存する。
- 実地確認では、automation 定義ファイルは `C:\\Users\\fwns6\\.codex\\automations\\` に残る一方、Windows の startup item / scheduled task に Codex / Claude の自動起動登録は見つからなかった。
- Codex 実行プロセスは存在するが、Claude プロセスは常駐確認できず、runtime path と管理 path を分けて考える必要がある。

## purpose

- reboot で止まるもの / 残るもの / 起動し直せば戻るものを 1 ticket で読めるようにする。
- quality-gmail を含む local automation の最小復旧手順を固定する。
- 「Codex を起動すれば cron は戻るが、Claude は管理用であり cron 実行自体の必須 runtime ではない」という境界を明確にする。

## 監査結果(現時点)

### 残るもの

- repo / ticket / docs / handoff ファイル
- `C:\\Users\\fwns6\\.codex\\automations\\quality-gmail\\automation.toml`
- `C:\\Users\\fwns6\\.codex\\automations\\quality-monitor\\automation.toml`
- `C:\\Users\\fwns6\\.codex\\automations\\draft-body-editor\\automation.toml`
- Codex 側の sqlite state / logs
- WordPress 側の既存 Draft / post 状態

### 止まるもの

- 実行中の Codex app / codex.exe プロセス
- in-flight の automation 実行
- その瞬間に送信・監視・dry-run 中だった処理
- Claude の対話セッション(開いていれば)

### 現行 automation 依存

- `quality-gmail`
  - Codex automation
  - local 実行
  - Windows shell
  - `\\\\wsl.localhost\\Ubuntu\\home\\fwns6\\code\\wordpressyoshilover\\logs\\quality_monitor\\` 読取
  - Gmail integration
- `quality-monitor`
  - Codex automation
  - local 実行
  - `wsl.exe bash -lc "... python3 -m src.tools.run_quality_monitor ..."`
- `draft-body-editor`
  - Codex automation
  - local 実行
  - WSL workspace / Python runner

### 起動項目の監査

- Windows Scheduled Task に `Codex` / `Claude` / `OpenAI` / `Anthropic` の自動起動タスクは確認できなかった。
- Windows StartupCommand に `Codex` / `Claude` / `OpenAI` / `Anthropic` の自動起動項目は確認できなかった。
- Codex app プロセスは確認できた。
- Claude 常駐プロセスは確認できなかった。

## 決定事項

### reboot 後の runtime 判定

- `Codex automation` は定義ファイルが残っても、**実行中プロセスは reboot で止まる**。
- 従って、reboot 後は `Codex` を再起動しない限り `quality-gmail` / `quality-monitor` / `draft-body-editor` は回らない前提で扱う。
- `Claude` は管理・判断レイヤであり、cron automation の実行そのものに必須ではない。
- ただし、handoff 更新 / ticket 管理 / gate 判定を再開するには Claude セッションを開き直す必要がある。

### 最小復旧手順

1. Windows PC を起動し、ネット接続を確認する
2. Codex app を起動する
3. Codex automation が残っていることを確認する
4. WSL と WordPress 接続に到達できることを確認する
5. 次の scheduled tick で `quality-monitor` / `quality-gmail` / `draft-body-editor` が再開することを確認する
6. Claude 管理便を再開する場合のみ、Claude セッションを開き直す

### 確認対象

- `quality-monitor` の最新 jsonl 追記
- `quality-gmail` の受信実績
- `draft-body-editor` の最新 dry-run 出力
- missed run は自動補填前提にしない。**次の tick から再開** を正とする

### stop 条件

- Codex app を起動しても automation が `ACTIVE` で復帰しない
- WSL が起動せず `quality-monitor` / `draft-body-editor` が失敗する
- Gmail integration まで含めて `quality-gmail` が送れない
- Windows 再起動後に Codex app の常駐再開が不安定

### 非目標

- クラウド移行
- OS 起動時の自動ログイン / 自動アプリ起動の実装
- automation の cadence 変更
- env / secret / mail recipient の変更

---

## TODO

【】reboot で残るもの / 止まるものを固定する  
【】Codex automation 3 本の local 依存を固定する  
【】Windows startup item / scheduled task に自動起動が無いことを監査結果として明記する  
【】`Codex を起動すれば cron は戻るが、Claude は管理レイヤ` という境界を固定する  
【】最小復旧手順を 6 ステップで固定する  
【】復旧確認対象(`quality-monitor` / `quality-gmail` / `draft-body-editor`)を固定する  
【】missed run は次 tick から再開とする方針を明記する  
【】必要なら follow-up ticket(自動起動 or クラウド移行)へ分岐できる形にする  

---

## 成功条件

- reboot 後に何を起動し直せばどこまで戻るかが 1 ticket で読める。
- quality-gmail を含む local automation の復旧確認対象が明確。
- user が「再起動したら全部だめなのか」を毎回聞かなくて済む。
- follow-up が必要な場合に、runtime 問題として切り出せる。
