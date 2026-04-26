# 168 repair-provider-ledger(GCP migration 第 1 ticket)

## meta

- number: 168
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / schema / ledger / migration foundation
- status: **READY**(独立、即 fire 可、156 deploy / 165 resilience 着地後の主線)
- priority: P0(GCP 移行の foundation、これなしで provider 比較 / fallback / Codex shadow / X 投稿 全 ticket 進めない)
- lane: B
- created: 2026-04-26
- parent: 155 / GCP migration master

## 背景

ChatGPT Plan mode 結論(2026-04-26):
- GCP 移行 OK、本線は Gemini Flash + OpenAI API key fallback、Codex CLI は shadow 固定
- 全 8 ticket(repair-provider-ledger / cloud-run-repair-job-skeleton / repair-fallback-controller / codex-cli-shadow-runner / cloud-run-secret-auth-writeback / x-post-cloud-queue-ledger / x-api-cloud-run-live-smoke / x-controlled-autopost-cloud-rollout)の **第 1 = repair-provider-ledger** 必須
- 理由: ledger なしで provider 比較 / fallback / Codex shadow / publish public side effect / X 投稿 全部事故る

## ゴール

repair lane(現在 Gemini Flash 単一 provider)に **共通 ledger schema v0** を実装する。Gemini / Codex / OpenAI API いずれの provider 経由でも同 schema で記録できる。WP write は増やさない、Codex live call なし、cron 時刻変更なし。

## schema v0(ChatGPT 確定)

```json
{
  "schema_version": "repair_ledger_v0",
  "run_id": "uuid4",
  "lane": "repair",
  "provider": "gemini|codex|openai_api",
  "model": "gemini-2.5-flash|gpt-4o-mini|gpt-4o|chatgpt-pro",
  "source_post_id": 123,
  "input_hash": "sha256",
  "output_hash": "sha256",
  "artifact_uri": "gs://... or local file://...",
  "status": "success|failed|skipped|shadow_only",
  "strict_pass": true,
  "error_code": null,
  "idempotency_key": "post_id + input_hash + provider",
  "created_at": "ISO8601 JST",
  "started_at": "ISO8601 JST",
  "finished_at": "ISO8601 JST",
  "metrics": {
    "input_tokens": 0,
    "output_tokens": 0,
    "latency_ms": 0,
    "body_len_before": 0,
    "body_len_after": 0,
    "body_len_delta_pct": 0.0
  },
  "provider_meta": {
    "raw_response_size": 0,
    "fallback_from": null,
    "fallback_reason": null,
    "quality_flags": []
  }
}
```

`metrics` / `provider_meta` は後から追加可能(forward compatible)。

## strict_pass 定義(ChatGPT C4)

```python
strict_pass = (
  json_schema_valid
  and hard_stop_flag_resolved
  and fact_check_pass
  and no_new_forbidden_claim
  and -0.20 <= body_len_delta_pct <= 0.35
)
```

## 仕様

### 新 module

- `src/repair_provider_ledger.py`
  - dataclass `RepairLedgerEntry`(全 schema field)
  - `LedgerWriter` abstract base
    - `JsonlLedgerWriter(path)` — local JSONL append
    - `FirestoreLedgerWriter(client, collection)` — stub class(connection なし、interface のみ、phase 後で本物化)
  - `compute_input_hash(post)` / `compute_output_hash(text)` helper
  - `make_idempotency_key(post_id, input_hash, provider)` helper
  - `judge_strict_pass(entry, hard_stop_flags_resolved, fact_check_pass, no_new_forbidden, body_len_delta_pct)` helper
  - `LedgerLockError` / `LedgerWriteError` exception class
  - `with_lock(idempotency_key)` context manager(local file lock 実装、Firestore lease は stub interface のみ)

### 既存挙動への影響

- `src/tools/draft_body_editor.py` の `call_gemini` 呼び出し path に **ledger 書込み 1 行追加**(provider="gemini", model="gemini-2.5-flash"、JSONL writer 使用)
- WP write / Gemini call の挙動は **不変**
- ledger 出力 path = `logs/repair_provider_ledger/<JST date>.jsonl`(WSL 上、GCP Phase で GCS / Firestore に切替)

## 不可触

- WP REST write の new endpoint 追加禁止
- Cloud Run deploy / Cloud Build / Dockerfile 触らない
- Secret Manager touch 禁止
- Codex CLI / OpenAI API live call 禁止(本 ticket は schema + Gemini path への ledger 注入のみ)
- 既存 Gemini call 挙動変更禁止(retry / backoff / 出力 parse 不変、165 land 状態維持)
- 既存 cron 時刻変更禁止
- automation.toml / scheduler / .env / secrets / WSL crontab / 既存 GCP services / baseballwordpress repo / WordPress / X
- requirements*.txt(本 ticket は stdlib + 既存 deps のみ、新 dep 追加禁止)

## acceptance

1. `src/repair_provider_ledger.py` module 存在、dataclass + 2 writer class + 4 helper + 2 exception 実装
2. `tests/test_repair_provider_ledger.py` で以下 pass:
   - schema v0 全 field validate(missing field で error)
   - JsonlLedgerWriter append 後 read back 一致
   - duplicate idempotency_key で `LedgerLockError`
   - strict_pass 全 5 条件の truth table(2^5 = 32 case の代表 pattern)
   - body_len_delta_pct 計算(before=100, after=85 → -15%)
   - fallback_from / fallback_reason 記録(provider=openai_api, fallback_from=codex)
   - FirestoreLedgerWriter stub class が呼べる(実 connection は mock、interface 確認のみ)
3. `src/tools/draft_body_editor.py` の Gemini call path に ledger 1 行追加(既存 1338 baseline + 165 land 後 1343 → 新 ledger tests + 042 path への ledger 注入 test = 1343 + 5-8 程度)
4. `logs/repair_provider_ledger/2026-04-26.jsonl` が dry-run で出力される(local mock data)
5. WP write / Gemini live call / Cloud Run deploy / push: **全て NO**
6. cron 時刻不変 verify(crontab 触っていない確認)

## Hard constraints

- **並走 task なし時に fire**(現状 in-flight Codex なし、156 push 済 / 165 push 済 / 167 commit なし)
- `git add -A` 禁止、stage は **`src/repair_provider_ledger.py` + `tests/test_repair_provider_ledger.py` + `src/tools/draft_body_editor.py`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 1343 維持(165 land 後)、pre-existing fail 0 維持
- `time.sleep` 実時間待ち禁止(test では mock)
- Firestore client は **stub interface のみ**、実 connection 試行禁止(phase 後で別 ticket)
- 新 dependency 追加禁止(stdlib + 既存 deps のみ)

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_repair_provider_ledger.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3  # 1343 + 新
# CLI smoke (mock data でledger出力)
python3 -c "
import sys; sys.path.insert(0, '.')
from src.repair_provider_ledger import JsonlLedgerWriter, RepairLedgerEntry, compute_input_hash, make_idempotency_key
import datetime
w = JsonlLedgerWriter('/tmp/ledger_smoke.jsonl')
input_h = compute_input_hash({'id': 1, 'content': {'rendered': 'test'}})
key = make_idempotency_key(1, input_h, 'gemini')
e = RepairLedgerEntry(
    schema_version='repair_ledger_v0', run_id='test-run', lane='repair',
    provider='gemini', model='gemini-2.5-flash', source_post_id=1,
    input_hash=input_h, output_hash='out_h', artifact_uri='file:///tmp/test',
    status='shadow_only', strict_pass=False, error_code=None, idempotency_key=key,
    created_at='2026-04-26T15:50:00+09:00', started_at='2026-04-26T15:50:00+09:00',
    finished_at='2026-04-26T15:50:01+09:00', metrics={}, provider_meta={}
)
w.write(e)
print(open('/tmp/ledger_smoke.jsonl').read())
"
# crontab 不変 verify
crontab -l | grep "draft_body_editor\|pub004\|publish_notice" | head -5
```

## Commit

```bash
git add src/repair_provider_ledger.py tests/test_repair_provider_ledger.py src/tools/draft_body_editor.py
git status --short
git commit -m "168: repair-provider-ledger schema v0 (JSONL + Firestore stub adapter, strict_pass judgment, idempotency lock, Gemini path への ledger 注入)"
```

`.git/index.lock` 拒否時 → plumbing 3 段(write-tree / commit-tree / update-ref)で fallback。

## 完了報告

```
- changed files: <list>
- pytest collect: 1343 → <after>
- pytest pass: 1343 → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash>
- schema v0 fields: 14 (確認)
- strict_pass conditions: 5 (確認)
- writers: JsonlLedgerWriter (実装) + FirestoreLedgerWriter (stub)
- Gemini path への ledger 注入: yes
- ledger output sample: logs/repair_provider_ledger/2026-04-26.jsonl(行数)
- WP write / Gemini live call / Cloud Run deploy / push: 全て NO
- crontab 不変 verify: yes
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- 既存 Gemini call の挙動変更が必要 → 即停止 + 報告(本 ticket scope 外)
- pytest 1343 を割る → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告
- Firestore client 実 connection が必要 → 即停止 + 報告(phase 後)

## 完了後の次便

ChatGPT phasing 順に従い:
- 169 = cloud-run-repair-job-skeleton(skeleton 起票 + fire)
- 170 = repair-fallback-controller
- 171 = codex-cli-shadow-runner
- 172 = cloud-run-secret-auth-writeback
- 173 = x-post-cloud-queue-ledger
- 174 = x-api-cloud-run-live-smoke
- 175 = x-controlled-autopost-cloud-rollout
