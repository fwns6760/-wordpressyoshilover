# LOCAL_CLAUDE_CRON_ACCEPTANCE_PACK

Ticket: 302-OPS-local-claude-cron-runner

## Recommendation

HOLD for auto-enable.

GO for local dry-run / self-test.

## Scope

Create a local WSL/Windows Task Scheduler runner that can periodically start Claude Code CLI for YOSHILOVER state checks.

Initial mode is dry-run only.

## Risk

| risk | level | mitigation |
|---|---:|---|
| 多重起動 | low | lock directory |
| 暴走 | low | timeout |
| 本番変更 | low in dry-run | dry-run default, prompt禁止事項 |
| Claude usage cost | none in dry-run | `--run` only after user GO |
| mail増加 | none | runner sends no mail |
| Gemini増加 | none | runner does not call Gemini |
| secrets露出 | low | no secret read, prompt forbids secret output |

## Rollback / Stop

Task未登録ならrollback不要。

Task登録後:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ops\unregister_windows_task.ps1
```

実行中停止:

```bash
pkill -f claude_state_check_runner.sh
```

lock残り:

```bash
rm -rf /tmp/yoshilover_claude_state_check.lock
```

## Additional Cost

- dry-run: 0
- Task Scheduler: 0
- `--run`: Claude Code CLI利用分のみ
- Gemini: 0
- X API: 0
- GCP mutation: 0

## User Work

必要なuser判断は1つだけ:

```text
Task Schedulerをdry-runで有効化するか
```

その後、安定すれば別判断:

```text
dry-runから--runへ切り替えるか
```

## Existing Ticket Impact

- 293-COST: 状態確認対象。flag ONはしない。
- 298-Phase3 v4: 24h安定確認対象。rollbackはしない。
- 300-COST: post-deploy異常確認対象。deployはしない。
- 282-COST: USER_DECISION_REQUIRED条件確認対象。flag ONはしない。

## Pre-run Checklist

- [ ] `bash -n scripts/ops/claude_state_check_runner.sh`
- [ ] `scripts/ops/claude_state_check_runner.sh --self-test`
- [ ] `scripts/ops/claude_state_check_runner.sh --dry-run`
- [ ] `powershell -ExecutionPolicy Bypass -File scripts/ops/register_windows_task.ps1 -WhatIf`
- [ ] `powershell -ExecutionPolicy Bypass -File scripts/ops/unregister_windows_task.ps1 -WhatIf`
- [ ] Task Scheduler未登録
- [ ] GCP変更なし
- [ ] env/flag変更なし
- [ ] mail量増加なし
- [ ] Gemini call増加なし

## Acceptance

- runner script exists and is executable
- prompt exists
- docs exist
- dry-run writes log
- self-test passes
- lock prevents duplicate run
- timeout path is documented
- Task registration script exists but has not been executed
- no production behavior changed
