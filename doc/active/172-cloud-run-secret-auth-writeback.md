# 172 cloud-run-secret-auth-writeback(GCP migration 第 5、Codex auth lifecycle)

## meta

- number: 172
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / secret / auth lifecycle
- status: **READY**(168/169/170/171 land 後、即 fire 可)
- priority: P0(Codex shadow lane を Cloud Run で動かす前提、ChatGPT 認証手順実装)
- lane: B
- created: 2026-04-26
- parent: 155 / 168 / 171 / ChatGPT phasing 157 / ChatGPT 認証手順

## 背景

ChatGPT Pro plan auth.json を Cloud Run Job で安全に運用するため、以下手順を実装:

1. Cloud Run Job 起動時に Secret Manager から最新 auth.json 取得 → `/tmp/.codex/auth.json`
2. `codex exec` 実行(171 で実装済 `call_codex` 経由)
3. 実行前後で auth.json の sha256 比較
4. **変化した場合のみ** Secret Manager に新 version 追加(refresh token writeback)
5. auth.json 内容は **絶対にログ出力しない**(masked のみ)

## ゴール

`src/cloud_run_secret_auth.py` を実装、Cloud Run Job entry script から呼び出して auth.json lifecycle を管理する。

## 仕様

### 新 module

- `src/cloud_run_secret_auth.py`
  - `SecretAuthManager(secret_name="codex-auth-json", project_id="baseballsite", codex_home="/tmp/.codex")`
    - `restore() -> Path`: Secret Manager latest version → `<codex_home>/auth.json` に書き出し、chmod 600、return path
    - `compute_sha() -> str`: `<codex_home>/auth.json` の sha256 hex
    - `writeback_if_changed(sha_before: str) -> bool`: 現 sha と比較、変化あれば Secret Manager に新 version add、変化なければ skip。return: 書き戻したか
    - `cleanup() -> None`: `<codex_home>` 配下を削除(Cloud Run Job 終了前)
  - `class SecretAccessError(RuntimeError)`(gcloud fail)
  - `class SecretWritebackError(RuntimeError)`(gcloud add fail)
  - **絶対に auth.json の内容を log / stdout / exception message に含めない**(file path / sha256 / size のみ)

### gcloud 経由 implementation

- `restore()`:
  ```python
  subprocess.run(
      ["gcloud", "secrets", "versions", "access", "latest",
       "--secret", self.secret_name, "--project", self.project_id],
      capture_output=True, check=True
  )
  # stdout を file に書き出し、chmod 600
  ```
- `writeback_if_changed`:
  ```python
  subprocess.run(
      ["gcloud", "secrets", "versions", "add", self.secret_name,
       "--data-file", str(auth_path), "--project", self.project_id],
      capture_output=True, check=True
  )
  ```

### Cloud Run Job entry script

- `bin/codex_shadow_entrypoint.sh`(新規)
  - 起動時に `SecretAuthManager.restore()` 呼出(Python script 経由)
  - 本番 runner(`run_draft_body_editor_lane.py --provider codex --max-posts N`)実行
  - 終了後 `writeback_if_changed()` 呼出
  - `cleanup()` で auth.json 削除
- 実装は Python wrapper 推奨(bash script は薄く保つ)

### invariants

- auth.json 内容を一切ログに出さない
- auth.json file permission は 600(owner read/write only)
- gcloud subprocess の stderr に auth.json content が混じる可能性 → masked して log(具体: stderr 全文 log するなら `[REDACTED auth.json content]` で sanitize)
- Cloud Run Job parallelism=1(設定は別 ticket / 別 commit、本 ticket は code 側のみ)
- 同 auth.json を複数 process で読まない(restore 時 lock file or atomic rename で保証)

## 不可触

- WSL crontab 編集 / cron 時刻変更
- 既存 168 ledger / 165 retry / 170 controller / 171 codex shadow 挙動変更禁止
- WP REST write の new endpoint 禁止
- Cloud Run deploy / Cloud Build / Dockerfile 触らない(本 ticket は Python module + entry script、deploy は別 ticket)
- 実 gcloud subprocess 起動 test 禁止(mock で `subprocess.run` patch)
- 実 Secret Manager touch 禁止(test は mock)
- automation.toml / scheduler / .env / secrets / 既存 GCP services / baseballwordpress repo / WordPress / X
- requirements*.txt(stdlib subprocess + 既存 deps のみ、新 dep 禁止)
- `~/.codex/auth.json` 直接読込 / 表示 / commit 禁止
- 並走 task: なし(現状 in-flight Codex なし)

## acceptance

1. `src/cloud_run_secret_auth.py` module(SecretAuthManager + 2 exception)
2. `tests/test_cloud_run_secret_auth.py`:
   - subprocess mock で restore success → file 作成 + chmod 600 verify
   - restore で gcloud fail → `SecretAccessError`
   - writeback_if_changed で sha 同じ → gcloud add 呼ばれない、return False
   - writeback_if_changed で sha 違う → gcloud add 呼ばれる、return True
   - writeback で gcloud fail → `SecretWritebackError`
   - cleanup で codex_home 削除 verify
   - **auth.json 内容が log / exception message / return value に出ない**(grep で sentinel content verify)
3. `bin/codex_shadow_entrypoint.sh` 新規(Python wrapper script、薄く)
4. `tests/test_codex_shadow_entrypoint.py`(entry script の Python wrapper 部分 unit test、subprocess mock)
5. pytest baseline 1383(171 land 後)+ 新 tests
6. live gcloud / Codex / WP / Cloud Run deploy / push: 全て NO
7. cron 時刻不変

## Hard constraints

- 並走 task: なし
- `git add -A` 禁止、stage は **`src/cloud_run_secret_auth.py` + `tests/test_cloud_run_secret_auth.py` + `bin/codex_shadow_entrypoint.sh` + `tests/test_codex_shadow_entrypoint.py`**(必要なら追加 1-2 file)
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 1383 維持、pre-existing fail 0 維持
- 新 dependency 禁止(stdlib subprocess + hashlib + 既存 deps)
- **auth.json 中身を log / stdout / exception message / commit / mail に絶対残さない**(masked のみ)
- subprocess test では `subprocess.run` を mock、実 gcloud / 実 codex 起動禁止
- gcloud subprocess の stderr に auth.json content が混じる可能性をテスト + sanitize logic 必須
- Cloud Run Job 環境 hardcode しない(env / arg で柔軟化)
- 165 / 168 / 169 / 170 / 171 で land 済の挙動を一切壊さない

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_cloud_run_secret_auth.py tests/test_codex_shadow_entrypoint.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
# CLI smoke (mock subprocess、実 gcloud 呼ばない)
python3 -c "
import sys; sys.path.insert(0, '.')
from unittest import mock
from src.cloud_run_secret_auth import SecretAuthManager
with mock.patch('subprocess.run') as m:
    m.return_value.returncode = 0
    m.return_value.stdout = b'{\"auth_mode\": \"chatgpt\", \"tokens\": {\"refresh_token\": \"...\"}}'
    mgr = SecretAuthManager(codex_home='/tmp/.codex_test_smoke')
    p = mgr.restore()
    print('restored to:', p)
    sha = mgr.compute_sha()
    print('sha:', sha[:16])
    mgr.cleanup()
"
```

## Commit

```bash
git add src/cloud_run_secret_auth.py tests/test_cloud_run_secret_auth.py bin/codex_shadow_entrypoint.sh tests/test_codex_shadow_entrypoint.py
git status --short
git commit -m "172: cloud-run-secret-auth-writeback (SecretAuthManager + entrypoint script、auth.json restore + sha 比較 + writeback、内容ログ禁止)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

```
- changed files: <list>
- pytest collect: 1383 → <after>
- pytest pass: 1383 → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash or "not created, claude commit needed">
- SecretAuthManager 4 method 実装: yes(restore / compute_sha / writeback_if_changed / cleanup)
- exception classes: SecretAccessError / SecretWritebackError 2 件 verify
- auth.json 内容ログ漏洩 check: なし(grep + test sentinel verify)
- gcloud subprocess mock test: pass
- entry script: bin/codex_shadow_entrypoint.sh 作成 verify
- live gcloud / Codex / WP / Cloud Run deploy / push: 全て NO
- cron 時刻不変 verify: yes
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- gcloud CLI が container に入っていない可能性 → 即停止 + 報告(別 ticket で base image 検討)
- subprocess mock では再現できない実環境依存 issue → 即停止 + 報告
- pytest 1383 を割る → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告
- auth.json 中身が log / stdout に漏れる箇所発覚 → 即停止 + 報告

## 完了後の次便

- **157 Cloud Scheduler trigger for 042 Cloud Run Job**(`2,12,22,32,42,52 * * * *` GCP 側、WSL cron は並走維持)
- **158 Secret Manager env(WP/Gemini key)for 042 Cloud Run Job**
- **159 WSL cron 042 disable**(GCP 042 安定 1 日確認後、user 判断)
