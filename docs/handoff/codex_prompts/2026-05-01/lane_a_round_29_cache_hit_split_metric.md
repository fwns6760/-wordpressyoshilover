# Lane A round 29 — cache_hit 種別分離 metric impl(改修 #1、デプロイ直前まで)

## 目的

POLICY §19.6 cache_hit 99% 構造依存への対策。`logs/llm_call_dedupe_ledger.jsonl` で観測する cache_hit を以下 3 種類に分離して metric 出力:

- `exact_hit`(同一 post_id + 同一 content_hash + 同一 prompt_template_id + 同一 model)
- `cooldown_hit`(24h cooldown 期間内の早期 reuse)
- `dedupe_hit`(post_id + content_hash level dedupe)

合算 hit ratio だけでは「prompt_template_id 変更時の雪崩」が検知できない。種別分離で予兆把握。

「デプロイ直前まで」= impl + test + push、image rebuild + flag ON は user GO 後。

## 不可触リスト(Hard constraints)

- Cloud Run deploy / env / flag / Scheduler / SEO / source / Gemini / mail 触らない
- `git add -A` 禁止、明示 stage のみ
- 既存 cache key / dedupe logic 不変(metric 追加だけ、挙動不変)
- `src/publish_notice_*` / `src/mail_*` 触らない(LLM-free invariant 維持、§19.5)
- `config/rss_sources.json` 触らない
- pytest baseline 2018/0 から regression なし(+N 0 fail のみ許容)

## scope

write_scope(narrow):
- `src/llm_call_dedupe.py` または equivalent(metric 出力 path)
- `src/gemini_cache.py` または equivalent(cooldown_hit 判定)
- `tests/test_cache_hit_split_metric.py`(新規)

read-only(理解のため):
- `logs/llm_call_dedupe_ledger.jsonl` 構造
- `src/gemini_*.py` 全般

## 実装方針

1. 既存 ledger jsonl に新 field 追加(後方互換、defaults to "unknown" for old entries)、または新 metric ledger 別 file
2. cache hit 判定時に種別を decide:
   - 同一 (post_id, content_hash, prompt_template_id, model) → `exact_hit`
   - cache 内に entry あるが prompt_template_id / model 異なる → `cooldown_hit`(24h cooldown 適用)
   - post_id + content_hash dedupe → `dedupe_hit`
3. metric output path:既存 jsonl に `hit_kind` field を追加、または別 metric jsonl
4. unit test 4 cases 以上(各種類 + miss + 後方互換)

## env knob(default OFF、deploy 後 enable)

- `ENABLE_CACHE_HIT_SPLIT_METRIC` (default 0、追記のみ、既存挙動 100% 不変)
- `CACHE_HIT_SPLIT_METRIC_LEDGER_PATH`(default `logs/cache_hit_split_metric_ledger.jsonl`)

`flag OFF default` = live-inert deploy で挙動 100% 不変、CLAUDE_AUTO_GO 候補。flag ON で metric 開始(USER_DECISION_REQUIRED、別 phase)。

## Pack v1(本 round で同時作成)

新 file: `docs/handoff/codex_responses/2026-05-01_change_29_cache_hit_split_pack_v1.md`

13 fields + 10a 7-point + 10b production-safe regression + 11 3-dim rollback + Decision Header + supersedes none(新規 ticket subtask):

```yaml
ticket: 改修-29-cache-hit-split-metric
recommendation: HOLD  # 298-v4 24h 安定 + Phase 6 verify pass + 293 deploy 完了後に GO 化検討
decision_owner: user
execution_owner: Codex (impl) + Claude (push, deploy verify)
risk_class: low(metric 追加のみ、既存挙動 100% 不変)
classification: USER_DECISION_REQUIRED  # image rebuild + flag ON 時
user_go_reason: COST_GUARD_METRIC_ADDITION
expires_at: 298-v4 + 293 完了後
```

## 実施

1. existing src/ 読んで impl boundary 確認
2. impl + test を narrow scope で実装
3. pytest 実行、+0 regression 確認(baseline 2018/0 → 2018+N/0)
4. Pack v1 作成
5. `git add` 明示 stage(src + tests + Pack + prompt)、`git diff --cached --name-status` 確認
6. commit message: `feat(cost-guard): cache hit split metric (exact/cooldown/dedupe) - default OFF`
7. plumbing 3 段 fallback 装備
8. `git log -1 --stat` 確認

push は Claude 後実行。

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "src/llm_call_dedupe.py(or equivalent)",
    "src/gemini_cache.py(or equivalent)",
    "tests/test_cache_hit_split_metric.py",
    "docs/handoff/codex_responses/2026-05-01_change_29_cache_hit_split_pack_v1.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_a_round_29_cache_hit_split_metric.md"
  ],
  "diff_stat": "<n> files changed",
  "commit_hash": "<hash>",
  "test": "pytest <baseline>/<fail> → <new>/<fail>",
  "remaining_risk": "none (metric add only, default OFF)",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master"
}
```

## 5 step 一次受け契約

- diff narrow(src 2-3 file + tests 1 + Pack 1 + prompt 1)
- 内容 metric 追加のみ、既存挙動不変
- pytest +0 regression 必須、新 test +N 0 fail
- scope 内
- rollback 可能(env remove + image rollback + git revert)
