# Lane A round 30 — 改修 #2 cache miss circuit breaker impl

## 目的

POLICY §19.7 cost guard #2 — cache 大量 miss 時 Gemini call 雪崩を自動 brake。1h miss 率閾値超過で Gemini path → review/hold 倒し。default OFF flag。

「デプロイ直前まで」= impl + test + commit + push、image rebuild + flag ON は user GO 後。

## 不可触リスト

- production 不触(deploy / env / Scheduler / SEO / source / Gemini call 増加 / mail 量増加 全禁止)
- `git add -A` 禁止
- 既存 cache logic 不変、circuit breaker は default OFF flag 経由でのみ enable
- mail path LLM-free invariant 維持
- `config/rss_sources.json` 触らない
- 改修 #1 commit `e7e656c` の cache_hit split metric は不変、本 round で参照のみ

## scope (narrow)

write_scope:
- `src/llm_call_dedupe.py` or `src/gemini_cache.py`(circuit breaker logic 追加)
- `tests/test_cache_miss_circuit_breaker.py`(新規)

read-only:
- `logs/llm_call_dedupe_ledger.jsonl`(miss rate baseline 把握)
- 改修 #1 cache_hit split metric の `exact_hit` / `cooldown_hit` / `dedupe_hit` 別計測(integration 確認)

## 実装方針

1. 1h rolling window で miss 率計測(`miss_count / total_count`)
2. threshold env knob:
   - `ENABLE_GEMINI_CACHE_MISS_BREAKER`(default 0)
   - `GEMINI_CACHE_MISS_BREAKER_THRESHOLD`(default 0.5、50% miss で trip)
   - `GEMINI_CACHE_MISS_BREAKER_WINDOW_SECONDS`(default 3600、1h window)
3. trip 時挙動:
   - Gemini call の代わりに review path へ(POLICY §8 silent skip 0 維持、reason 明示)
   - log emission for visibility
4. trip 解除条件:
   - 自動:miss rate が threshold 下回ったら自動 reset
   - 手動:env remove で全停止

## Pack v1

`docs/handoff/codex_responses/2026-05-01_change_31_cache_miss_breaker_pack_v1.md`(13 fields + 10a + 10b + 11 3-dim rollback + 12 + 13)

## 完了後 commit + push

通常 flow。Codex sandbox blocker 時 Claude fallback。
