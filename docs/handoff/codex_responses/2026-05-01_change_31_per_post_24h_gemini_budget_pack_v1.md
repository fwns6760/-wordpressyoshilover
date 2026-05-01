# 改修-31 per-post 24h Gemini budget Pack v1

Date: 2026-05-01 JST  
Mode: Lane A round 31 / impl + test / deploy-held  
Pack class: cost-guard / USER_DECISION_REQUIRED

## Decision Header

```yaml
ticket: 改修-31-per-post-24h-gemini-budget
recommendation: HOLD  # 298-v4 24h 安定 + 293 FULL_EXERCISE_OK + 282 deploy 完了後に GO 化検討
decision_owner: user
execution_owner: Codex (impl) + Claude (push, deploy verify)
risk_class: low(metric + budget gate、既存挙動 default OFF)
classification: USER_DECISION_REQUIRED  # image rebuild + flag ON 時、budget 適用で挙動変化
user_go_reason: COST_GUARD_BUDGET_ENFORCEMENT
expires_at: 282 deploy 完了後
```

## 1. Conclusion

- 推奨は `HOLD`
- repo 実装と targeted test は完了
- image rebuild と `ENABLE_PER_POST_24H_GEMINI_BUDGET=1` は user `GO` 後にだけ進める

## 2. Scope

- `src/llm_call_dedupe.py`
  - per-post 24h budget env knob 追加
  - explicit Gemini attempt ledger event 追加
  - mixed ledger(`attempt row` / legacy `record_call` / cache-miss fallback)集計 helper 追加
- `src/rss_fetcher.py`
  - budget exhausted 時の visible review/hold skip path 追加
  - remaining budget に応じた retry cap 縮小
  - tripped log emission 追加
- `tests/test_per_post_24h_gemini_budget.py`
  - helper 4 cases + rss_fetcher integration 3 cases
- `docs/handoff/codex_responses/2026-05-01_change_31_per_post_24h_gemini_budget_pack_v1.md`

## 3. Non-Scope

- deploy / image rebuild / env apply / Scheduler
- `src/publish_notice_*` / `src/mail_*`
- `config/rss_sources.json`
- Gemini provider / prompt template / cache key / cooldown 仕様変更
- cache-hit split metric(#1)の schema / ledger path 変更
- cache-miss circuit breaker(#2)の threshold / order / semantics 変更
- WP write / SEO / source 追加 / mail volume 変更

## 4. Current Evidence

- baseline targeted pytest(before):
  - `tests/test_llm_call_dedupe.py`
  - `tests/test_cache_hit_split_metric.py`
  - `tests/test_cache_miss_circuit_breaker.py`
  - result: `17 passed, 0 failed`
- post-change targeted pytest(after):
  - above 3 files + `tests/test_per_post_24h_gemini_budget.py`
  - result: `24 passed, 0 failed`
- compile check:
  - `python3 -m compileall src/llm_call_dedupe.py src/rss_fetcher.py tests/test_per_post_24h_gemini_budget.py`
- current source baseline before this round:
  - `4d70a266e82733dc60345c16e83a22167cae6768`
- current fetcher runtime rollback anchor from existing deploy packs:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d`

## 5. User-Visible Impact

- current round itself: production impact `0`
- future image rebuild with flag OFF:
  - behavior should remain `100%` unchanged
  - new budget path stays unreachable
- future flag ON:
  - same `post_id` gets at most `PER_POST_24H_GEMINI_BUDGET_LIMIT` Gemini calls in a rolling `24h`
  - over-limit call is routed to existing visible review/hold skip path
  - retry count inside a single invocation is capped by remaining budget

## 6. Mail Volume Impact

- `NO`
- mail class / sender / subject / recipient / cap に変更なし
- budget trip は fetcher 内の review/hold reason only で、mail path実装そのものは不触

## 7. Gemini / Cost Impact

- Gemini call increase: `NO`
- token increase: `NO`
- cost protection after future flag ON:
  - sixth and later call within the same `post_id` / `24h` window is blocked
  - retry loop also shrinks to remaining slots, so one invocation cannot overshoot the per-post budget
- flag OFF runtime cost delta: `0`

## 8. Silent Skip Impact

- `NO`
- over-limit path uses explicit `skip_reason=per_post_24h_gemini_budget_exhausted`
- `emit_gemini_call_skipped` + preflight skip history + warning log を通す
- hidden skip / log-only drop は増やしていない

## 9. Preconditions

All must be `YES` before GO.

| precondition | judgment | note |
|---|---|---|
| `298-v4` 24h stability close | **NO** | prompt contractどおり close待ち |
| `293 FULL_EXERCISE_OK` | **NO** | deploy verify chain未完 |
| `282` deploy 完了 | **NO** | fetcher系 live change の先行条件 |
| targeted pytest green | **YES** | `24 passed, 0 failed` |
| diff narrow(`src 2 + tests 1 + pack 1`) | **YES** | scope内で完了 |

## 10. Tests

- helper:
  - flag disabled でも inert
  - explicit attempt rows + legacy gemini rows count
  - cache-hit split metric row is ignored
  - cache-miss fallback counts old rows when explicit attempt rows are absent
  - 24h rolling reset releases budget automatically
- integration:
  - limit reached -> rss_fetcher skip path / history / review reason
  - remaining budget shrinks `attempt_limit`
  - cache-miss breaker(#2) precedence remains intact

## 10a. Post-Deploy Verify Plan (POLICY §3.5 7-point)

1. fetcher image/revision is the intended rebuilt image and service starts cleanly
2. `ENABLE_PER_POST_24H_GEMINI_BUDGET` stays absent/off for live-inert deploy
3. `PER_POST_24H_GEMINI_BUDGET_LIMIT` stays absent or default and produces no behavior change while flag is off
4. `gemini_call_skipped` / preflight history / warning logs show no unexpected `per_post_24h_gemini_budget_exhausted` rows during flag-OFF observe
5. cache-hit split metric(#1) and cache-miss breaker(#2) logs keep their prior semantics
6. publish / review / hold visible paths remain present, with silent skip still `0`
7. rollback anchors are captured before GO:
   - exact pre-change fetcher image digest
   - current service revision
   - this round source commit hash

## 10b. Production-Safe Regression Scope

- allowed:
  - Cloud Run `yoshilover-fetcher` image/revision/env describe
  - fetcher logs for `gemini_call_skipped`, `gemini_cache_miss_breaker`, `per_post_24h_gemini_budget`
  - preflight skip history observation
  - visible publish/review/hold parity checks
- forbidden:
  - Scheduler mutation
  - extra source ingestion
  - mail routing changes
  - prompt/provider changes
  - bulk replay that increases Gemini traffic

## 11. Rollback (POLICY §3.6 / §16.4 3 dimensions)

### Tier 1 runtime env

- command:

```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite \
  --region=asia-northeast1 \
  --remove-env-vars=ENABLE_PER_POST_24H_GEMINI_BUDGET,PER_POST_24H_GEMINI_BUDGET_LIMIT
```

- expected time: `~30 sec`

### Tier 1 runtime image

- preferred rollback target:
  - exact pre-change fetcher image digest captured immediately before rebuild
- current canonical stable anchor from existing packs:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:4be818d`
- expected time: `~2-3 min`

### Tier 2 source

- command:

```bash
git revert <impl commit hash>
git push origin master
```

- use when runtime-only rollback is insufficient or source itself is wrong

### Last known good

- source baseline before this round: `4d70a266e82733dc60345c16e83a22167cae6768`
- runtime image anchor for future GO: `yoshilover-fetcher:4be818d`

## 12. Stop Conditions

- flag OFF deployで `per_post_24h_gemini_budget_exhausted` が出る
- cache hit / cache miss / breaker semantics drift
- visible review/hold path disappears or silent skip appears
- retry cap changes call behavior for unrelated posts
- pytest regression `> 0`
- fetcher startup/runtime error(`Traceback`, `ModuleNotFoundError`, exit non-zero)

## 13. User Reply

`GO` / `HOLD` / `REJECT`
