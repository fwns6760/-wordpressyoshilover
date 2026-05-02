# LOCAL_CLAUDE_CRON_RUNNER

## 目的

Claude `/loop` のwake不安定で user が時計係・起動役になる状態を減らす。

ローカルPC / WSL上で Claude Code CLI を定期起動し、YOSHILOVERの状態確認を自動化する。

これはGCP checkerではない。
Claude API / Vertex AI Claudeも使わない。
PCが起動している間だけ動けばよい。

## 仕組み

```text
Windows Task Scheduler
  -> wsl.exe -d Ubuntu -- bash -lc '/home/fwns6/code/wordpressyoshilover/scripts/ops/claude_state_check_runner.sh --dry-run'
       -> repoへcd
       -> lockで多重起動防止
       -> git status / required files / gcloud / claude存在確認
       -> promptを確認
       -> logs/ops/claude_state_check/YYYY-MM-DD_HHMMSS.log へ記録
       -> dry-runではClaude CLIを起動しない
```

実際にClaudeを動かす場合は、Task Schedulerの引数を `--run` に変える。
初期は `--dry-run` のままにする。

## 前提

- Windows + WSL2 / Ubuntu
- repo: `/home/fwns6/code/wordpressyoshilover`
- Claude Code CLI: `claude`
- gcloud auth済み
- PCが起動している間だけ動けばよい
- PCスリープ時は停止してよい

## 起動方法

手動dry-run:

```bash
cd /home/fwns6/code/wordpressyoshilover
scripts/ops/claude_state_check_runner.sh --dry-run
```

自己診断:

```bash
cd /home/fwns6/code/wordpressyoshilover
scripts/ops/claude_state_check_runner.sh --self-test
```

Claude CLIを実際に起動する手動run:

```bash
cd /home/fwns6/code/wordpressyoshilover
scripts/ops/claude_state_check_runner.sh --run
```

Windows Task Scheduler登録案の確認:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ops\register_windows_task.ps1 -WhatIf
```

実登録は user GO 後のみ。

## 停止方法

Task Scheduler未登録なら何もしない。

登録済みの場合:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ops\unregister_windows_task.ps1
```

実行中プロセスを止める場合:

```bash
pkill -f claude_state_check_runner.sh
```

lockが残った場合:

```bash
rm -rf /tmp/yoshilover_claude_state_check.lock
```

ただし、実行中プロセスがないことを確認してから消す。

## 失敗時の扱い

- runnerの失敗はlogに残す。
- 失敗しても本番には影響しない。
- exit codeはlog末尾に残る。
- timeout時はexit code 124。
- lock中ならexit code 75。

## コスト影響

- dry-run: 0円。Claude CLIを呼ばない。
- `--run`: Claude Code CLI利用分のローカル/契約上の利用枠を消費する可能性がある。
- Gemini call: 0。
- X API: 0。
- GCP API: read-only query分のみ。通常は小さい。
- mail量: 0。runner自体はmail送信しない。

## セキュリティ注意点

- secretsをrepoに保存しない。
- logにsecret実値を出さない。
- promptはread-only/dry-run前提にする。
- `--run` でも flag/env/deploy/rollbackは禁止。
- Claude CLIのpermission modeはrunner側で `plan` を既定にする。

## userが見るべきもの

- 有効化するかどうか
- dry-run logが正常か
- `--run` を許可するか
- Task Schedulerを登録するか

## userが見なくてよいもの

- gcloud queryの細部
- git statusのambient dirty細部
- state判断に関係しない通常log
- Codex lane内部の細かい途中出力

## ログ

```text
logs/ops/claude_state_check/YYYY-MM-DD_HHMMSS.log
logs/ops/claude_state_check/latest.log
logs/ops/claude_state_check/index.tsv
```

`logs/` は通常git管理しない。

## 初期推奨

1. `--self-test`
2. `--dry-run`
3. Task Schedulerをdry-runで登録するか判断
4. 数回安定後、必要なら `--run` を検討
