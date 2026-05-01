# 改修-29 cache hit split metric Pack v1

supersedes none (new subtask)

Date: 2026-05-01 JST  
Mode: Lane A round 29 / impl-ready / deploy-held  
Pack class: metric-addition / USER_DECISION_REQUIRED

## Decision Header

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

## 1. Conclusion

- 推奨は `HOLD`
- repo 実装は live-inert 前提で先行可能
- image rebuild と `ENABLE_CACHE_HIT_SPLIT_METRIC=1` は user `GO` 後にだけ進める

## 2. Scope

- `src/llm_call_dedupe.py` に split metric ledger helper と `dedupe_hit` 記録を追加
- `src/gemini_cache.py` に lookup hit kind 判定 helper を追加
- `tests/test_cache_hit_split_metric.py` を追加
- prompt file と本 pack を追加

## 3. Non-Scope

- Cloud Run deploy
- env apply / flag ON
- Scheduler
- SEO / source / Gemini provider 切替
- mail routing
- cache key / cooldown / dedupe の既存挙動変更

## 4. Current Evidence

- cache hit kind は `exact_hit` / `cooldown_hit` / `dedupe_hit` / legacy `unknown`
- split metric ledger は default OFF
- default path は `logs/cache_hit_split_metric_ledger.jsonl`
- focused pytest: `27 passed, 0 failed`

## 5. User-Visible Impact

- default OFF のため production 影響は `0`
- flag ON 後も output は observability 追加のみ
- publish / review / hold / skip 判断ロジックは不変

## 6. Mail Volume Impact

- `NO`
- mail class / recipient / sender / cap に変更なし

## 7. Gemini / Cost Impact

- Gemini call increase: `NO`
- token increase: `NO`
- cache reuse behavior change: `NO`
- cost impact は metric file append 分のみで軽微

## 8. Silent Skip Impact

- `NO`
- hit/miss 判定や skip route を変えず、記録の粒度だけ追加

## 9. Preconditions

- 293 deploy 系の安全確認完了
- 298-v4 24h stability close
- Phase 6 verify pass
- flag ON は user 明示 `GO`

## 10. Tests

- helper classification: `exact_hit`
- helper classification: `cooldown_hit`
- `record_call(..., skip_reason=content_hash_dedupe)` で `dedupe_hit` metric emit
- flag OFF default no-op
- legacy row backward compatibility = `unknown`

## 10a. Post-Deploy Verify Plan (POLICY §3.5 7-point)

- image / revision: target image が expected digest と一致
- env / flag: `ENABLE_CACHE_HIT_SPLIT_METRIC` が `0` または unset のまま live-inert deploy
- metric file: flag OFF 中は新規 split ledger rows `0`
- runtime errors: `Traceback` / `ModuleNotFoundError` / exit non-zero `0`
- gemini cache path: `cache_hit_reason` / cache return behavior に差分なし
- dedupe path: `content_hash_dedupe` skip behavior に差分なし
- rollback target: image rollback or env remove が即時可能

## 10b. Production-Safe Regression Scope

- safe regression scope は cache/dedupe observability のみ
- publish output、mail output、WP write、Scheduler、Gemini request count は不変
- acceptable result は `+N tests / 0 fail` のみ

## 11. Rollback (POLICY §3.6 / §16.4 3 dimensions)

- Tier 1 runtime env: `ENABLE_CACHE_HIT_SPLIT_METRIC` を remove または `0` に戻す
- Tier 1 runtime image: pre-change image digest へ rollback
- Tier 2 source: `git revert <this commit>` で helper/test/doc を戻す

## 12. Stop Conditions

- cache hit / miss 挙動に変化
- dedupe skip path に変化
- split metric が flag OFF でも出力される
- pytest regression `> 0`
- deploy verify で runtime error 発生

## 13. User Reply

- `GO` / `HOLD` / `REJECT`
