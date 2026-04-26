# 171 codex-cli-shadow-runner(GCP migration 第 4)

## meta

- number: 171
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / shadow lane / Codex CLI integration
- status: **READY**(168/169/170 land 後、即 fire 可)
- priority: P0(Codex shadow lane を実 Codex CLI 呼び出しで動かす)
- lane: B
- created: 2026-04-26
- parent: 155 / 168 / 169 / 170 / ChatGPT phasing 155

## 背景

ChatGPT Plan mode 結論(B / D):
- Codex CLI を `codex exec --json` で非対話実行
- output は schema 出力 + `--output-last-message` 相当で stdout 混入に依存しない
- ChatGPT auth(auth.json)使う場合は `task_count=1`、同時実行禁止、実行後 auth.json refresh されたら Secret Manager へ writeback
- API key 利用なら通常 OpenAI API 課金で本番向き
- 本 ticket では **shadow lane 限定**(WP write 禁止、ledger に shadow_only 記録のみ)
- 170 で classify_error / RepairFallbackController は実装済、171 で stub `call_codex_stub` を実 `call_codex` に置換

## ゴール

`codex exec --json` を subprocess 呼び出しする `call_codex` 関数を実装、170 の RepairFallbackController と統合する。auth mode は API key / ChatGPT auth(auth.json)を分離、初期は ChatGPT auth(WSL `~/.codex/auth.json` 利用)を default。

## 仕様

### 新 module

- `src/codex_cli_shadow.py`
  - `call_codex(prompt, *, auth_mode="chatgpt_auth", codex_home=None, timeout=120) -> tuple[str, dict]`
    - `auth_mode="chatgpt_auth"`: `~/.codex/auth.json` 経由(default、Cloud Run Job では `/tmp/.codex/auth.json` を 172 で復元)
    - `auth_mode="api_key"`: 環境変数 `OPENAI_API_KEY` 経由
    - subprocess で `codex exec --json` 実行
    - timeout 引数で `subprocess.run(..., timeout=timeout)` 制御
    - stdout から JSON parse、`{"output": "...", "metadata": {...}}` 形式期待
    - parse fail → `CodexSchemaError` raise(170 classify で `schema_invalid` に分類)
    - exit non-zero → `CodexExecError(exit_code, stderr)` raise
    - return: `(text, meta_dict)`
  - `class CodexSchemaError(RuntimeError)`
  - `class CodexExecError(RuntimeError)`(`exit_code` / `stderr` attribute 持つ)
  - `class CodexAuthError(RuntimeError)`(401 / unauthorized 検出時、170 で `auth_fail_401` 分類対象)
  - `compute_codex_home(auth_json_path)` helper(`/tmp/.codex` or `~/.codex` を返す、172 で Cloud Run 側 path 設定に使う)
  - **絶対に auth.json の中身を log / stdout / exception message に含めない**(masked のみ)

### 170 統合

`src/repair_fallback_controller.py` の stub を実呼び出しに置換:
- `call_codex_stub` → `call_codex`
- error の class detection が 170 classify_error 経由で動くこと verify
- WP write は **shadow lane では絶対しない**(現状 controller で `RepairResult.body_text` 取得時に書く logic だが、provider="codex" の場合は ledger に `status="shadow_only"` 記録 + WP write skip に修正)

### 仕様 invariants(ChatGPT C / D 強制)

- Codex shadow output は **絶対に WP に書かない**(本 ticket での invariant、後 ticket で本線昇格判断するまで)
- 同 `auth.json` を複数 Codex call で並列利用しない(Cloud Run Job parallelism=1、本 ticket では `subprocess.run` 直列のみ test)
- timeout default 120s(ChatGPT D3 推奨値)
- schema parse fail → 即 fallback(170 controller path)
- auth.json 内容ログ禁止(本 ticket の Hard constraints + test で verify)

## 不可触

- WSL crontab 編集 / cron 時刻変更
- 既存 `--max-posts` / `--dry-run` / 168 ledger / 165 retry/backoff / 170 controller fallback 6 class 挙動変更禁止
- WP REST write の new endpoint 禁止
- Cloud Run deploy / Cloud Build / Dockerfile 触らない
- **実 Codex CLI 呼び出し test で実時間 subprocess.run 動作禁止**(mock で subprocess patch、test 内では実 codex exec 起動しない)
- Secret Manager touch 禁止(172 で実装)
- automation.toml / scheduler / .env / secrets / 既存 GCP services / baseballwordpress repo / WordPress / X
- requirements*.txt(stdlib + 既存 deps のみ、新 dep 禁止)
- `~/.codex/auth.json` 直接読込 / 表示 / commit 禁止
- 並走 task: なし(現状 in-flight Codex なし)

## acceptance

1. `src/codex_cli_shadow.py` module(call_codex + 3 exception + compute_codex_home helper)
2. `tests/test_codex_cli_shadow.py`:
   - subprocess mock で success → `(text, meta)` return
   - subprocess timeout → `subprocess.TimeoutExpired` propagate(170 classify で `timeout` に)
   - exit code 1 / stderr → `CodexExecError`
   - exit code 401-related stderr keyword → `CodexAuthError`
   - JSON parse fail → `CodexSchemaError`
   - auth.json path passing(masked、内容は log に出さない)
   - auth_mode="api_key" で `OPENAI_API_KEY` env 渡る verify
3. `src/repair_fallback_controller.py` 更新:
   - `call_codex_stub` → `call_codex` 置換
   - provider="codex" 時、`RepairResult` に `wp_write_allowed=False` flag 追加(shadow lane 限定の signal)
4. `tests/test_repair_fallback_controller.py` 更新:
   - provider="codex" の RepairResult が `wp_write_allowed=False` で返ること
   - controller fallback chain で codex success → ledger に `status="shadow_only"`、Gemini fallback path 走る verify
5. `src/tools/run_draft_body_editor_lane.py` 更新:
   - `RepairResult.wp_write_allowed=False` の時 WP PUT skip + ledger 記録のみ(`shadow_only`)
6. pytest baseline 1374(170 land 後)+ 新 tests
7. **WP write 発生条件**: `provider != "codex"` AND `RepairResult.wp_write_allowed=True` のときのみ
8. live publish / 実 Codex CLI / Cloud Run deploy / push: 全て NO
9. cron 時刻不変

## Hard constraints

- 並走 task: なし
- `git add -A` 禁止、stage は **5 file**(`src/codex_cli_shadow.py` + `tests/test_codex_cli_shadow.py` + `src/repair_fallback_controller.py` + `tests/test_repair_fallback_controller.py` + `src/tools/run_draft_body_editor_lane.py` + 必要なら `tests/test_run_draft_body_editor_lane.py`)
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止(commit までで止める、Claude が push)
- pytest baseline 1374 維持、pre-existing fail 0 維持
- 新 dependency 禁止(stdlib subprocess + 既存 deps)
- **auth.json 中身を log / stdout / exception message / commit に絶対残さない**(masked のみ)
- subprocess test では `subprocess.run` を mock、実 codex exec 起動禁止
- Cloud Run Job 環境変数(`CODEX_HOME=/tmp/.codex`)前提を hardcode しない、env / arg で柔軟に
- 165 / 168 / 169 / 170 で land 済の挙動を一切壊さない

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_codex_cli_shadow.py tests/test_repair_fallback_controller.py tests/test_run_draft_body_editor_lane.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
# CLI smoke (mock subprocess、実 Codex 呼ばない)
python3 -c "
import sys; sys.path.insert(0, '.')
from unittest import mock
from src.codex_cli_shadow import call_codex, CodexExecError
with mock.patch('subprocess.run') as m:
    m.return_value.returncode = 0
    m.return_value.stdout = '{\"output\": \"hello\", \"metadata\": {}}'
    text, meta = call_codex('test', auth_mode='chatgpt_auth', timeout=10)
    print('text:', text, 'meta:', meta)
"
```

## Commit

```bash
git add src/codex_cli_shadow.py tests/test_codex_cli_shadow.py src/repair_fallback_controller.py tests/test_repair_fallback_controller.py src/tools/run_draft_body_editor_lane.py
# tests/test_run_draft_body_editor_lane.py 触ったなら追加
git status --short
git commit -m "171: codex-cli-shadow-runner (call_codex 実装、subprocess mock test、wp_write_allowed=False で shadow lane 限定、auth.json 内容ログ禁止)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。**plumbing も失敗したら open question 報告**(Claude が writable env で commit、169/170 で実証済)。

## 完了報告

```
- changed files: <list>
- pytest collect: 1374 → <after>
- pytest pass: 1374 → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash or "not created, claude commit needed">
- call_codex 実装: yes(subprocess mock test pass)
- exception classes: CodexSchemaError / CodexExecError / CodexAuthError 3 件 verify
- auth_mode 切替: chatgpt_auth / api_key 2 mode test
- shadow lane invariant: provider="codex" → wp_write_allowed=False、WP PUT skip verify
- auth.json 内容ログ漏洩 check: なし(grep で auth.json 出力箇所 0 件)
- 170 controller との統合: stub → 実呼び出し置換 verify
- WP write / live Codex CLI / Cloud Run deploy / push: 全て NO
- cron 時刻不変 verify: yes
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- subprocess mock では再現できない実環境依存 issue 発覚 → 即停止 + 報告(172 で実環境 setup 後判定)
- 170 controller の挙動変更が必要(本 ticket scope 外)→ 即停止 + 報告
- pytest 1374 を割る → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告
- auth.json 中身が log / stdout に漏れる箇所発覚 → 即停止 + 報告

## 完了後の次便

- **172 cloud-run-secret-auth-writeback**(`/tmp/.codex/auth.json` Secret Manager 復元 + sha256 比較 + writeback、ChatGPT 認証手順実装)
