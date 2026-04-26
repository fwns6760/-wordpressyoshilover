# 169 cloud-run-repair-job-skeleton(GCP migration 第 2)

## meta

- number: 169
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / runner / migration foundation
- status: **READY**(168 着地 `70009aa` 後、173 と disjoint 並列可)
- priority: P0(GCP migration 第 2、queue/ledger 連携の入口)
- lane: B
- created: 2026-04-26
- parent: 155 / 168 / ChatGPT phasing 154

## 背景

ChatGPT Plan mode 結論(2026-04-26、D 節):
- 既存 `run_draft_body_editor_lane.py` は WSL cron 専用で、queue / ledger / provider 切替に対応してない
- Cloud Run Jobs で動かせるよう、CLI args を以下に拡張すべき:
  - `--limit N`(処理件数上限)
  - `--dry-run`(WP write しない)
  - `--provider gemini|codex|openai_api`(provider 選択)
  - `--queue-path` / `--ledger-path`(input queue + output ledger path、GCP 移行で GCS / Firestore に切替予定)
- 168(repair-provider-ledger)で実装した schema v0 を活用、ledger 書込は既存 path 流用

## ゴール

`src/tools/run_draft_body_editor_lane.py` に Cloud Run Jobs 互換の CLI args を追加し、queue / ledger 経由の repair 実行 path を整備する。**既存 WSL cron 経路の挙動は不変**(168 で land 済 ledger 注入もそのまま)。

## 仕様

### 既存 CLI 拡張(後方互換維持)

現状: `python3 -m src.tools.run_draft_body_editor_lane --max-posts N`
追加 args:

| arg | default | 用途 |
|---|---|---|
| `--limit` | None | --max-posts と同義(GCP 風命名 alias、既存 --max-posts は維持) |
| `--dry-run` | False | WP PUT skip(既存 `--dry-run` flag 維持、明示 alias) |
| `--provider` | `gemini` | `gemini` / `codex` / `openai_api`(現状 `gemini` のみ実装、他は stub return + ledger 記録) |
| `--queue-path` | None | input post queue file(JSONL)、None なら従来通り WP REST から fetch |
| `--ledger-path` | `logs/repair_provider_ledger/<JST>.jsonl` | 168 で land 済 default 維持 |

### provider 切替 logic

- `--provider gemini` → 既存 `call_gemini` path(165 retry/backoff 込み)
- `--provider codex` / `--provider openai_api` → **本 ticket では stub**、`NotImplementedError` 投げず、ledger に `status="skipped", error_code="provider_not_implemented_yet"` 記録して exit 0
- 後続 ticket(170 fallback / 171 codex shadow)で実装

### queue-path 経由 fetch logic

- `--queue-path /tmp/repair_queue.jsonl` 指定時:
  - 既存 WP REST `list_posts` skip
  - JSONL から post entry 読込(各行 = `{"post_id": N, "content": {...}, "title": {...}, "meta": {...}}` 想定)
  - 順次 process(--limit 上限まで)
- `--queue-path` 未指定時 → 既存挙動維持(WP REST fetch)

### 既存挙動への影響

- WSL cron(`2,12,22,32,42,52 * * * *`)は既存 args(`--max-posts 3`)で起動、変化なし
- 165 retry/backoff、168 ledger 注入は維持
- 042 cron 出力 JSON format 不変

## 不可触

- WSL crontab 編集 / cron 時刻変更 一切禁止
- 既存 `--max-posts` / `--dry-run` flag の挙動変更禁止(後方互換)
- 165 retry/backoff logic 改変禁止
- 168 ledger 書込 logic 改変禁止
- WP REST write の new endpoint 禁止
- Cloud Run deploy / Cloud Build / Dockerfile 触らない
- Codex / OpenAI API live call 禁止(本 ticket は stub、170/171 で実装)
- automation.toml / scheduler / .env / secrets / 既存 GCP services / baseballwordpress repo / WordPress / X
- requirements*.txt(stdlib + 既存 deps のみ、新 dep 禁止)
- **並走 task `bgn2tj0bp`(173 X queue ledger)が touching する file 触らない**: `src/x_post_queue_ledger.py` / `src/tools/run_x_post_queue_smoke.py` / `tests/test_x_post_queue_ledger.py` / `tests/test_run_x_post_queue_smoke.py`

## acceptance

1. `src/tools/run_draft_body_editor_lane.py` に 4 新 args 追加(`--limit` / `--dry-run` 既存 / `--provider` / `--queue-path` / `--ledger-path`)
2. `--provider gemini` で既存挙動完全維持(WSL cron tick 出力同一)
3. `--provider codex` / `--provider openai_api` で stub return + ledger 記録 + exit 0
4. `--queue-path` 指定時 JSONL から fetch、未指定時 WP REST(既存)
5. `tests/test_run_draft_body_editor_lane.py` に新 tests 追加(provider 切替 / queue-path / limit alias / 既存 --max-posts 後方互換)
6. pytest baseline 1351(168 land 後)+ 新 tests
7. WP write / Gemini live call(test 内)/ Cloud Run deploy / push: 全て NO
8. cron 時刻不変 verify

## Hard constraints

- **並走 task `bgn2tj0bp`(173)と file 完全 disjoint**(173 = X 関連 / 169 = repair runner、絶対衝突なし)
- `git add -A` 禁止、stage は **`src/tools/run_draft_body_editor_lane.py` + `tests/test_run_draft_body_editor_lane.py`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 1351 維持、pre-existing fail 0 維持
- 新 dependency 禁止
- 165 / 168 で land 済の挙動を一切壊さない(既存 tests 全 pass 必須)

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_run_draft_body_editor_lane.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3  # 1351+ 新
# CLI smoke (既存挙動)
python3 -m src.tools.run_draft_body_editor_lane --max-posts 0 --dry-run 2>&1 | head -5
# CLI smoke (新 args)
python3 -m src.tools.run_draft_body_editor_lane --limit 0 --provider codex --dry-run 2>&1 | head -10
```

## Commit

```bash
git add src/tools/run_draft_body_editor_lane.py tests/test_run_draft_body_editor_lane.py
git status --short
git commit -m "169: cloud-run-repair-job-skeleton (--limit / --provider / --queue-path / --ledger-path 追加、provider stub、後方互換維持)"
```

`.git/index.lock` 拒否時(173 並走で衝突可能性)→ plumbing 3 段(write-tree / commit-tree / update-ref)で fallback。

## 完了報告

```
- changed files: <list>
- pytest collect: 1351 → <after>
- pytest pass: 1351 → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash>
- 新 args: --limit / --provider / --queue-path / --ledger-path 追加 verify
- 既存 --max-posts / --dry-run 後方互換: pass
- provider stub (codex / openai_api): ledger に skipped 記録 verify
- queue-path JSONL fetch: 動作 verify
- WP write / Gemini live call / Cloud Run deploy / push: 全て NO
- cron 時刻不変 verify: yes
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- 既存 cron 出力 JSON format 変更が必要 → 即停止 + 報告(本 ticket scope 外)
- 165 retry/backoff / 168 ledger 注入の挙動変更が必要 → 即停止 + 報告
- pytest 1351 を割る → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告

## 完了後の次便

- 170 repair-fallback-controller(Codex/OpenAI fail → Gemini fallback)
- 171 codex-cli-shadow-runner(Codex shadow lane 実装)
