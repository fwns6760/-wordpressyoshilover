# 302-OPS-local-claude-cron-runner

| field | value |
|---|---|
| ticket_id | 302-OPS-local-claude-cron-runner |
| priority | P1(userを時計係・起動役にしないためのローカル自律runner) |
| status | IMPLEMENTED_LOCAL_DRY_RUN_READY / HOLD_BEFORE_ENABLE |
| lane | OPS / LOCAL_AUTOMATION |
| owner | Claude(運用設計) -> Codex(実装) -> user(有効化判断のみ) |
| repo | /home/fwns6/code/wordpressyoshilover |
| created | 2026-05-02 |
| production_apply | なし |

## 目的

Claude `/loop` の自律wakeが不安定で、userが時計係・起動役になっている。

GCP checker新規構築はいったん行わず、まずローカルPC / WSL上で Claude Code CLI を定期起動する仕組みを作る。

PCが起動している間だけ、YOSHILOVERの状態確認・必要なsafe action判断・state報告が進む状態を目指す。

## 重要な非目的

- ClaudeをGCPへ移さない。
- Claude API / Vertex AI Claude は使わない。
- GCP checkerは作らない。
- Task Scheduler登録はこのticketでは実行しない。
- cron有効化はこのticketでは実行しない。
- 本番deploy / env apply / flag ON / rollback はしない。

## 成果物

- `docs/ops/LOCAL_CLAUDE_CRON_RUNNER.md`
- `scripts/ops/claude_state_check_runner.sh`
- `prompts/ops/claude_state_check_prompt.md`
- `scripts/ops/register_windows_task.ps1`
- `scripts/ops/unregister_windows_task.ps1`
- `docs/ops/LOCAL_CLAUDE_CRON_ACCEPTANCE_PACK.md`

## 実装方針

- 初期モードは `--dry-run`。
- `--dry-run` はClaude CLIを起動せず、前提確認・prompt確認・ログ出力のみ行う。
- 実行する場合だけ `--run` を明示する。
- `claude -p` の非対話モードを使う。
- lock directoryで多重起動を防ぐ。
- timeoutで暴走を防ぐ。
- 出力は `logs/ops/claude_state_check/YYYY-MM-DD_HHMMSS.log` に残す。
- 失敗時もlogとexit codeを残す。
- Windows Task Scheduler登録スクリプトは作成のみ。実行しない。

## 運用分類

このticketの実装・doc・dry-runは `CLAUDE_AUTO_GO` 相当のローカル準備。

以下は `USER_DECISION_REQUIRED`:

- Task Scheduler登録
- 実際の定期起動開始
- `--run` を定期タスクにする
- safe deploy実行を許可するpromptへ変更

以下は引き続き禁止:

- flag ON
- env変更
- Scheduler変更(GCP)
- SEO変更
- source追加
- Gemini call増加
- mail量増加
- cleanup mutation

## 完了条件

- commit済み
- push済み
- 実行ファイル作成済み
- dry-run手順あり
- Task Scheduler登録は未実行
- userに必要な判断は「有効化するかどうか」だけ
- 既存本番挙動への影響0
