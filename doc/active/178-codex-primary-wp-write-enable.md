# 178 codex-primary-wp-write-enable(Codex shadow → 本線昇格、WP write 許可)

## meta

- number: 178
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / config / lane promotion
- status: **READY**(177 land 後、即 fire 可。本 ticket は code 変更のみ、177 deploy と並列 OK)
- priority: P0.5(Codex 本線運用、user 明示意向)
- lane: B
- created: 2026-04-26
- parent: 155 / 170 / 171 / 177 / ChatGPT C section(本線昇格)

## 背景

171 で Codex shadow lane 実装、177 で GCP deploy 中。
**ただし shadow invariant**:
- `wp_write_allowed=False` hardcode
- ledger に `status="shadow_only"` 記録のみ
- Codex 出力は WP に書かない

user 指示「Codex で記事直す」(本線化したい):
- shadow から primary lane 昇格
- WP write 許可
- ledger は引き続き全 entry 記録(provider 比較継続)

## ChatGPT 助言からの逸脱と user 判断

ChatGPT Plan mode B 結論:
- 「Codex 本線運用は OpenAI ToS 観点でグレー」
- 「shadow 100 件以上 ledger 比較後の本線昇格を推奨」

**user 明示判断で本線化**(2026-04-26 PM):
- ledger は引き続き運用、品質悪化検知で即 rollback 可
- ChatGPT Pro $100 plan の fair use 内で運用
- 失敗時は 170 fallback controller で Gemini 自動切替

## ゴール

`--provider codex` で Cloud Run Job が動いた時、**WP write を許可**(ledger に `status="success"` 記録、shadow_only ではない)。

ただし:
- env / CLI flag で **opt-in 制**(default は shadow 維持、deployment ごとに有効化)
- 失敗時 170 controller が Gemini fallback、WP write は最終 1 回(170 invariant 維持)

## 仕様

### env / flag 追加

`src/repair_fallback_controller.py`:
- 新 env var: `CODEX_WP_WRITE_ALLOWED=true|false`(default: `false`、shadow 維持)
- `RepairResult.wp_write_allowed` の判定 logic:
  ```python
  if provider == "codex":
      wp_write_allowed = os.environ.get("CODEX_WP_WRITE_ALLOWED", "false").lower() == "true"
  else:
      wp_write_allowed = True
  ```

`src/tools/run_draft_body_editor_lane.py`:
- 既存の `RepairResult.wp_write_allowed` 経由 WP PUT 判定 logic は不変(170/171 で land 済)

### Cloud Run Job env 追加(177 deploy の延長で別 commit)

177 で `codex-shadow` Cloud Run Job 作成済 → 本 ticket land 後、Cloud Run Job env に **`CODEX_WP_WRITE_ALLOWED=true`** を追加(別 deploy commit、Codex が gcloud で update)。

### tests

- `tests/test_repair_fallback_controller.py`:
  - `CODEX_WP_WRITE_ALLOWED=false` で provider="codex" → wp_write_allowed=False(既存、shadow 維持)
  - `CODEX_WP_WRITE_ALLOWED=true` で provider="codex" → wp_write_allowed=True(新規、本線)
  - provider="gemini" / "openai_api" は env 影響なし、wp_write_allowed=True
  - env 未設定 → False(default、shadow)

### ledger semantics

- Codex success + WP write 成功 → status="success"(従来の shadow_only ではない)
- Codex success + env disabled(shadow 維持時) → status="shadow_only"(既存通り)
- Codex fail → 170 fallback Gemini → status="success"(Gemini 経由)、ledger に Codex fail + Gemini fallback の 2 entry(170 で land 済)

## 不可触

- WSL crontab(全行)
- 既存 src 大半:
  - 170 controller の error class / fallback chain logic 不変
  - 171 codex_cli_shadow の call_codex 不変(provider 切替は controller 側)
  - 168 ledger schema 不変
  - 165 retry/backoff 不変
- requirements*.txt 触らない
- automation.toml / .env / secrets / Cloud Run Job env 直接編集(本 ticket は code のみ、env 設定は別 commit)
- baseballwordpress repo
- WordPress / X / 既存 GCP services / Secret Manager / GCS bucket
- 並走 task touching file 触らない:
  - `b3ngiu1an`(160): `Dockerfile.guarded_publish` / `bin/guarded_publish_entrypoint.sh` / `cloudbuild_guarded_publish.yaml` / `doc/active/160-deployment-notes.md`
  - `b200f9azk`(177): `Dockerfile.codex_shadow` / `cloudbuild_codex_shadow.yaml` / `doc/active/177-deployment-notes.md`

## acceptance

1. `src/repair_fallback_controller.py` に `CODEX_WP_WRITE_ALLOWED` env 判定追加
2. `tests/test_repair_fallback_controller.py` に env 切替 4 case test 追加(true/false × provider 4 種 = 8 case 程度)
3. pytest baseline 1404(167 v2 land 後)+ 新 tests
4. **default(env 未設定)= shadow 維持**(safety default)
5. env=true → Codex provider で wp_write_allowed=True
6. ledger semantics: env=true で Codex 成功時 status="success"、shadow_only 出ない
7. WP write / Cloud Run deploy / push: 全て NO(本 ticket は code のみ、Cloud Run Job env update は 178b 別 commit)
8. 165 / 168-173 / 156-167 で land 済の挙動を一切壊さない

## Hard constraints

- 並走 task touching file 触らない
- `git add -A` 禁止、stage は **`src/repair_fallback_controller.py` + `tests/test_repair_fallback_controller.py`** だけ
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 1404 維持、pre-existing fail 0 維持
- 新 dependency 禁止
- env default は **必ず false**(shadow 維持、safety lock)
- Cloud Run Job env update は本 ticket scope 外(別 commit / 178b で実施)
- 168 / 170 / 171 / 172 で land 済の挙動を一切壊さない

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_repair_fallback_controller.py -v 2>&1 | tail -20
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
# CLI smoke
python3 -c "
import sys, os; sys.path.insert(0, '.')
from src.repair_fallback_controller import RepairFallbackController
# default (env unset)
print('default:', os.environ.get('CODEX_WP_WRITE_ALLOWED', 'unset'))
# enable
os.environ['CODEX_WP_WRITE_ALLOWED'] = 'true'
print('after set:', os.environ.get('CODEX_WP_WRITE_ALLOWED'))
"
```

## Commit

```bash
git add src/repair_fallback_controller.py tests/test_repair_fallback_controller.py
git status --short
git commit -m "178: Codex primary wp_write enable via CODEX_WP_WRITE_ALLOWED env (default false, shadow 維持、env=true で本線昇格)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

```
- changed files: <list>
- pytest collect: 1404 → <after>
- pytest pass: 1404 → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash>
- env default = false 確認: yes
- env=true で provider="codex" wp_write_allowed=True 確認: yes
- ledger semantics: status="success" / "shadow_only" 切替 verify
- WP write / Cloud Run deploy / push: 全て NO
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- 170 controller logic を破壊する必要発覚 → 即停止 + 報告
- 168 ledger schema 変更が必要 → 即停止 + 報告(schema は v0 fix)
- pytest 1404 を割る → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告

## 完了後の次便

- **178b**: 177 で land 済 Cloud Run Job `codex-shadow` の env に `CODEX_WP_WRITE_ALLOWED=true` 追加(gcloud run jobs update)→ 本線稼働開始
- 178b 後 1-2 日 observation、ledger で品質確認
- 品質悪化検知時、env=false に戻し shadow 復帰(rollback 1 コマンド)
