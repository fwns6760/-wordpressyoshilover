# 170 repair-fallback-controller(GCP migration 第 3)

## meta

- number: 170
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / resilience / fallback
- status: **READY**(168 + 169 land 後、即 fire 可)
- priority: P0(Codex/OpenAI 失敗時に完全停止せず Gemini に切替、本線運用前提)
- lane: B
- created: 2026-04-26
- parent: 155 / 168 / 169 / ChatGPT phasing 156

## 背景

ChatGPT Plan mode 結論(C / G2):
- Codex CLI が schema 違反 output → 即 Gemini fallback、WP には絶対書かない
- 失敗 case 分類:
  - timeout(120s 超等)
  - 401 / unauthorized(auth fail)
  - 429(rate limit hit)
  - schema_invalid(JSON parse fail)
  - provider_error(その他)
- 各 failure class → ledger に記録 → Gemini result へ切替
- fallback 後は **無条件 publish しない**(WP write は通常 path の評価通過後のみ)

169 で provider stub(codex / openai_api)を ledger に skipped 記録するだけだったが、170 で実 fallback chain を完成させる。

## ゴール

`--provider codex` または `--provider openai_api` で fail した時、自動的に Gemini に切替えて修復継続する controller を実装。失敗 class を ledger の `error_code` + `provider_meta.fallback_from` + `provider_meta.fallback_reason` に記録。

## 仕様

### 新 module

- `src/repair_fallback_controller.py`
  - `class RepairFallbackController`:
    - `__init__(primary_provider, fallback_provider="gemini", ledger_writer)`
    - `execute(post, prompt) -> RepairResult`
      - primary_provider で試行
      - 失敗 class 分類
      - fallback_provider で再試行
      - ledger に primary 失敗 + fallback 成功 / 失敗 を 2 entry で記録
  - `class RepairResult(dataclass)`:
    - `provider`(最終的に採用した provider)
    - `fallback_used: bool`
    - `body_text` or `None`
    - `failure_chain: list[FailureRecord]`
  - `class FailureRecord(dataclass)`:
    - `provider`
    - `error_class`(`timeout` / `auth_fail_401` / `rate_limit_429` / `schema_invalid` / `provider_error` / `network_error`)
    - `error_message`
    - `latency_ms`
  - `classify_error(exception, http_code=None) -> str` helper
    - `urllib.error.HTTPError 401` → `auth_fail_401`
    - `urllib.error.HTTPError 429` → `rate_limit_429`
    - `urllib.error.HTTPError 5xx` → `provider_error`
    - `urllib.error.URLError` / `socket.timeout` → `network_error`
    - `TimeoutError`(独自定義 / 計測値超過) → `timeout`
    - `json.JSONDecodeError` → `schema_invalid`
    - その他 → `provider_error`

### provider call interface

- `call_provider(provider_name, prompt, api_key) -> tuple[str, dict]`(stub に対応する関数群)
  - `gemini`: 既存 `call_gemini`(165 retry/backoff 込み)
  - `codex`: `call_codex_stub`(本 ticket では stub return、171 で実装)
  - `openai_api`: `call_openai_api_stub`(本 ticket では stub return、後 ticket で実装)
- stub は random fail / random success の **test fixture** として動作可能(env で切替)

### ledger 記録

168 で land 済の `RepairLedgerEntry` を流用、本 ticket で追加:
- primary 失敗時: 1 entry(provider=primary, status=failed, error_code=<class>)
- fallback 成功時: 別 entry(provider=fallback, status=success, fallback_from=primary, fallback_reason=<class>)
- 両方失敗時: 2 entry(両方 status=failed)

### `run_draft_body_editor_lane.py` 統合

169 で追加した `--provider` 切替 path に、controller 経由の dispatch を追加:
- `--provider gemini` → 直接(controller 経由しない、既存)
- `--provider codex` → controller(primary=codex, fallback=gemini)
- `--provider openai_api` → controller(primary=openai_api, fallback=gemini)
- WP PUT path は controller の `RepairResult.body_text` が得られた場合のみ呼ぶ

## 不可触

- WSL crontab 編集 / cron 時刻変更 一切禁止
- 既存 `--max-posts` / `--dry-run` / 168 ledger 注入 / 165 retry/backoff 挙動変更禁止
- WP REST write の new endpoint 禁止
- Cloud Run deploy / Cloud Build / Dockerfile 触らない
- Codex / OpenAI API live call 禁止(本 ticket は controller + stub のみ、171 で codex 実装)
- Secret Manager touch 禁止
- automation.toml / scheduler / .env / secrets / 既存 GCP services / baseballwordpress repo / WordPress / X
- requirements*.txt(stdlib + 既存 deps のみ)
- 並走 task touching file(現状 並走なし、念のため)

## acceptance

1. `src/repair_fallback_controller.py` module 存在(controller + dataclass + helper)
2. `tests/test_repair_fallback_controller.py` で:
   - primary success → fallback 不発火
   - primary timeout / 401 / 429 / 5xx / schema_invalid / network_error 各々で fallback 発火 verify
   - primary fail + fallback success → ledger 2 entry 確認
   - primary fail + fallback fail → ledger 2 entry 全 failed
   - classify_error helper 全 6 class
3. `src/tools/run_draft_body_editor_lane.py` の `--provider codex` / `--provider openai_api` path を controller 経由に書き換え
4. `tests/test_run_draft_body_editor_lane.py` で provider fallback 統合 test 追加
5. pytest baseline 1368(169 land 後)+ 新 tests
6. WP write / Codex live call / OpenAI API live call / Cloud Run deploy / push: 全て NO
7. cron 時刻不変 verify

## Hard constraints

- 並走 task: なし
- `git add -A` 禁止、stage は **`src/repair_fallback_controller.py` + `tests/test_repair_fallback_controller.py` + `src/tools/run_draft_body_editor_lane.py` + `tests/test_run_draft_body_editor_lane.py`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 1368 維持、pre-existing fail 0 維持
- 新 dependency 禁止
- `time.sleep` 実時間待ち禁止(test では mock)
- Codex / OpenAI client 実 connection 試行禁止
- 既存挙動を一切壊さない(全既存 tests pass 必須)

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_repair_fallback_controller.py tests/test_run_draft_body_editor_lane.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
```

## Commit

```bash
git add src/repair_fallback_controller.py tests/test_repair_fallback_controller.py src/tools/run_draft_body_editor_lane.py tests/test_run_draft_body_editor_lane.py
git status --short
git commit -m "170: repair-fallback-controller (Codex/OpenAI fail → Gemini fallback、failure 6 class 分類、ledger 2 entry 記録、stub interface)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。**ただし sandbox read-only で plumbing も失敗したら、明示的に open question で報告**(Claude が writable env で commit する)。

## 完了報告

```
- changed files: <list>
- pytest collect: 1368 → <after>
- pytest pass: 1368 → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash or "not created, claude commit needed">
- failure classes: timeout / auth_fail_401 / rate_limit_429 / provider_error / network_error / schema_invalid (6) verify
- fallback chain ledger 2 entry: yes
- stub interface(codex / openai_api): random fail/success 切替 verify
- 既存挙動破壊: なし
- WP write / live API call / Cloud Run deploy / push: 全て NO
- cron 時刻不変 verify: yes
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- 既存 call_gemini / 165 retry/backoff の挙動変更が必要 → 即停止 + 報告
- 168 ledger schema の change が必要 → 即停止 + 報告(schema は v0 fix)
- pytest 1368 を割る → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告

## 完了後の次便

- 171 codex-cli-shadow-runner(stub を実 Codex CLI 呼び出しに置換、shadow lane 限定)
- 172 cloud-run-secret-auth-writeback(API key 経路、auth.json は shadow 用補助)
