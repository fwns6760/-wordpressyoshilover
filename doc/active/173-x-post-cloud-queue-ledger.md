# 173 x-post-cloud-queue-ledger(GCP migration X 投稿 lane 第 1)

## meta

- number: 173
- owner: Claude Code(設計 / 起票)/ Codex(実装、push しない、Claude が push)
- type: dev / schema / queue / migration foundation
- status: **READY**(168 と disjoint 並列 fire 可)
- priority: P0.5(X 投稿 lane の foundation、unlock 時に即動かす準備)
- lane: A
- created: 2026-04-26
- parent: 155 / GCP migration master / ChatGPT phasing 158

## 背景

ChatGPT Plan mode 結論(2026-04-26、F1):
- repair-provider-ledger(168)の schema v0 が決まったあとなら、X 投稿側 ledger も並列着手 OK
- X 投稿は現状 OFF(149 BLOCKED_USER)、unlock 時に Cloud Run + queue で即動かせるよう foundation を先行整備
- WP 公開済 Green 記事だけを candidate にし、二重投稿防止 / daily cap / TTL 切れ skip を ledger で管理

## ゴール

X 投稿 lane の **queue + ledger schema v0** を実装する。X API live call なし、Cloud Run deploy なし、X token 触らず、純粋に schema + adapter + dedup logic を local で完成させる。

## schema v0(ChatGPT E1-E8 + queue 設計)

### x_post_queue entry

```json
{
  "schema_version": "x_post_queue_v0",
  "queue_id": "uuid4",
  "candidate_hash": "sha256(post_id + canonical_url + body_excerpt)",
  "source_post_id": 12345,
  "source_canonical_url": "https://yoshilover.com/...",
  "title": "...",
  "post_text": "...(140 char 以内、URL 含む)",
  "post_category": "lineup|postgame|breaking|notice|comment",
  "media_urls": [],
  "account_id": "main|brand2|...",
  "ttl": "ISO8601(投稿期限、breaking=2-3h / notice=24h / evergreen=72h)",
  "status": "queued|posted|failed_retryable|failed_terminal|expired|skipped_duplicate|skipped_daily_cap",
  "queued_at": "ISO8601 JST",
  "scheduled_at": "ISO8601 JST(いつ投稿予定か、Cloud Scheduler tick で claim)",
  "posted_at": "ISO8601 JST or null",
  "x_post_id": "snowflake or null",
  "retry_count": 0,
  "last_error_code": null,
  "last_error_message": null,
  "idempotency_key": "candidate_hash + account_id"
}
```

### x_post_ledger entry(成功 / 失敗 / skip 全記録)

```json
{
  "schema_version": "x_post_ledger_v0",
  "run_id": "uuid4",
  "queue_id": "(参照)",
  "account_id": "main",
  "status": "posted|failed_retryable|failed_terminal|expired|skipped_duplicate|skipped_daily_cap",
  "x_post_id": "snowflake or null",
  "x_user_id": "1234567890 or null",
  "started_at": "ISO8601",
  "finished_at": "ISO8601",
  "rate_limit_remaining": 0,
  "rate_limit_reset": "ISO8601",
  "error_code": null,
  "error_message": null
}
```

## queue / dedup logic 仕様

### dedup(二重投稿防止)

- `idempotency_key = candidate_hash + account_id` で unique
- 同 key が queue 内 / ledger 内 status=posted で存在 → enqueue 拒否(`skipped_duplicate`)
- candidate_hash 一致 = 「同じ記事 / 同じ本文要約」見なし、誤投稿防止

### daily cap

- account_id ごとに daily cap(env / config から)
- ledger の posted_at で当日 count、cap 到達後の enqueue → `skipped_daily_cap`
- breaking category は cap 計算外 オプション(env で切替)

### TTL 切れ skip

- queue claim 時に `ttl` 過ぎてたら `expired` で ledger 記録、X API 呼ばず終了

### category 別 default TTL(ChatGPT G4)

- breaking: 2-3 時間
- notice (記事公開通知): 24 時間
- evergreen: 72 時間
- default: 24 時間

## 仕様

### 新 module

- `src/x_post_queue_ledger.py`
  - dataclass `XPostQueueEntry`(全 schema field)
  - dataclass `XPostLedgerEntry`(全 schema field)
  - `QueueWriter` abstract base
    - `JsonlQueueWriter(path)` — local JSONL append
    - `FirestoreQueueWriter(client, collection)` — stub class(connection なし、interface のみ)
  - `LedgerWriter` 同パターン
  - `compute_candidate_hash(post_id, canonical_url, body_excerpt)` helper
  - `make_idempotency_key(candidate_hash, account_id)` helper
  - `judge_dedup(queue_writer, ledger_writer, key)` helper(returns "duplicate"|"ok")
  - `judge_daily_cap(ledger_writer, account_id, cap, breaking_excluded=False)` helper
  - `judge_ttl_expired(entry, now)` helper
  - `default_ttl_seconds(category)` helper
  - `QueueLockError` / `QueueWriteError` exception class

### CLI smoke

- `python3 -m src.tools.run_x_post_queue_smoke --dry-run` で:
  - 既存 `logs/guarded_publish_history.jsonl` から最新 publish 5 件読む
  - 各々 enqueue 試行(dry-run なので queue 書込まず stdout JSON)
  - dedup / daily cap / TTL 判定結果を表示

## 不可触

- **X API live call 一切禁止**(本 ticket は schema + adapter のみ)
- X OAuth token / Secret Manager touch 禁止
- 既存 X 関連 src(`src/x_*` 等あれば)挙動変更禁止
- 168 並走中なので **`src/repair_provider_ledger.py`** / **`src/tools/draft_body_editor.py`** / **`tests/test_repair_provider_ledger.py`** に絶対触らない
- WP REST write の new endpoint 禁止
- Cloud Run deploy / Cloud Build / Dockerfile 触らない
- automation.toml / scheduler / .env / secrets / WSL crontab / 既存 GCP services / baseballwordpress repo / WordPress
- requirements*.txt(本 ticket は stdlib + 既存 deps のみ、新 dep 追加禁止)

## acceptance

1. `src/x_post_queue_ledger.py` module 存在、2 dataclass + 2 writer + 5 helper + 2 exception
2. `tests/test_x_post_queue_ledger.py` で:
   - schema v0 全 field validate
   - JsonlQueueWriter append + read back
   - JsonlLedgerWriter append + read back
   - duplicate idempotency_key で `skipped_duplicate`
   - daily cap 到達で `skipped_daily_cap`
   - TTL 切れ で `expired`
   - breaking category で daily cap 除外オプション動作
   - candidate_hash 計算が deterministic(同 input で同 hash)
   - default_ttl_seconds(category) 全 5 category 値返す
3. `src/tools/run_x_post_queue_smoke.py` 新規(CLI、dry-run のみ)
4. tests/test_run_x_post_queue_smoke.py でCLI smoke verify(mock data、dry-run、X API 呼ばれない)
5. pytest baseline 1343(168 in flight 中 drift 加味)+ 新 tests
6. WP write / X API live call / Cloud Run deploy / push: **全て NO**
7. cron 時刻不変

## Hard constraints

- **並走 task `bx8ao0it9`(168)が touching する file 触らない**: `src/repair_provider_ledger.py` / `src/tools/draft_body_editor.py` / `tests/test_repair_provider_ledger.py`
- `git add -A` 禁止、stage は **`src/x_post_queue_ledger.py` + `tests/test_x_post_queue_ledger.py` + `src/tools/run_x_post_queue_smoke.py` + `tests/test_run_x_post_queue_smoke.py`** だけ明示
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止(commit までで止める、Claude が push)
- pytest baseline 維持、pre-existing fail 0 維持
- 新 dependency 禁止(stdlib + 既存 deps)
- Firestore client は stub interface のみ、実 connection 試行禁止
- X API client(tweepy 等)import 禁止

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_x_post_queue_ledger.py tests/test_run_x_post_queue_smoke.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
# CLI smoke
python3 -m src.tools.run_x_post_queue_smoke --dry-run 2>&1 | head -20
# crontab 不変 verify
crontab -l | grep -E "draft_body_editor|pub004|publish_notice" | head -5
```

## Commit

```bash
git add src/x_post_queue_ledger.py tests/test_x_post_queue_ledger.py src/tools/run_x_post_queue_smoke.py tests/test_run_x_post_queue_smoke.py
git status --short
git commit -m "173: x-post-cloud-queue-ledger schema v0 (queue + ledger dataclass + JSONL/Firestore stub adapter, dedup/daily_cap/TTL judgment, dry-run smoke CLI)"
```

`.git/index.lock` 拒否時(168 並走で衝突可能性)→ plumbing 3 段(write-tree / commit-tree / update-ref)で fallback。

## 完了報告

```
- changed files: <list>
- pytest collect: <before> → <after>
- pytest pass: <before> → <after>(pre-existing fail 維持: 0)
- new tests: <count>
- commit hash: <hash>
- queue schema fields: 17 (確認)
- ledger schema fields: 11 (確認)
- writers: 2 (Jsonl 実装 + Firestore stub) × 2 (queue + ledger)
- dedup / daily_cap / TTL judgment: 全 pass
- CLI smoke: dry-run 出力確認
- X API live call / Cloud Run deploy / push: 全て NO
- crontab 不変 verify: yes
- remaining risk: <if any>
- open question for Claude: <if any>
```

## stop 条件

- 168 と同 file 触る必要発覚 → 即停止 + 報告
- pytest baseline を割る → 即停止 + 報告
- write scope 外を触る必要 → 即停止 + 報告
- X API client / Secret Manager touch が必要 → 即停止 + 報告(別 ticket)

## 完了後の次便

ChatGPT phasing:
- 169 cloud-run-repair-job-skeleton(168 着地後)
- 174 x-api-cloud-run-live-smoke(173 着地後)
