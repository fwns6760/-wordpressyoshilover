# Lane A round 31 — 改修 #3 per-post 24h Gemini budget impl

## 目的

POLICY §19.7 cost guard #3 — 同一 post_id で 24h 以内 Gemini call 上限を設け、retry / fallback / regenerate が積み重なる時のコスト保護。default OFF flag。

「デプロイ直前まで」 = impl + tests + Pack v1 + rollback plan、image rebuild + flag ON は user GO 後。

## 不可触リスト(Hard constraints)

- **production 不触**(deploy / env apply / Scheduler / SEO / source 追加 / Gemini call 増加 / mail 量増加 全禁止)
- `git add -A` 禁止、明示 stage のみ
- 既存 Gemini call logic 不変、budget は default OFF flag 経由でのみ enable
- mail path LLM-free invariant 維持(POLICY §19.5、`src/publish_notice_*` / `src/mail_*` 触らない)
- `config/rss_sources.json` 触らない
- pytest baseline regression なし(+N 0 fail のみ許容)
- 既存 cache_hit split metric(改修 #1、commit `e7e656c`)+ cache miss circuit breaker(改修 #2、commit `91ddfdf`)に touching せず integration

## scope (narrow)

write_scope:
- `src/llm_call_dedupe.py` または equivalent(per-post 24h budget ledger 拡張)
- `tests/test_per_post_24h_gemini_budget.py`(新規)
- `docs/handoff/codex_responses/2026-05-01_change_31_per_post_24h_gemini_budget_pack_v1.md`(Pack v1)

read-only:
- 改修 #1 + #2 既 impl(integration 確認)
- 既存 ledger 構造(`logs/llm_call_dedupe_ledger.jsonl`)

## 実装方針

1. per-post_id 24h rolling window で Gemini call count 計測
2. threshold env knob:
   - `ENABLE_PER_POST_24H_GEMINI_BUDGET`(default 0)
   - `PER_POST_24H_GEMINI_BUDGET_LIMIT`(default 5、同一 post 24h で 5 call まで)
3. 上限到達時挙動:
   - 該当 post の Gemini call → review/hold path へ(POLICY §8 silent skip 0 維持、reason 明示)
   - log emission for visibility
4. budget 解除条件:24h rolling window で count 自動 decrement
5. unit test 5+ cases(各 budget 状態 + 上限到達時 review 経路 + budget reset + integration with #1/#2)

## env knob default(全 OFF、live-inert)

- `ENABLE_PER_POST_24H_GEMINI_BUDGET=0`
- `PER_POST_24H_GEMINI_BUDGET_LIMIT=5`(参考値、env 不在時 default 5)
- 既存 #1 / #2 env 不変

flag OFF default = live-inert deploy で挙動 100% 不変、CLAUDE_AUTO_GO 候補。flag ON で budget 適用(USER_DECISION_REQUIRED)。

## Pack v1(本 round で同時作成)

`docs/handoff/codex_responses/2026-05-01_change_31_per_post_24h_gemini_budget_pack_v1.md`:

13 fields + 10a Post-Deploy Verify Plan(POLICY §3.5 7-point)+ 10b Production-Safe Regression Scope + 11 Rollback(POLICY §3.6 / §16.4 3 dimensions、env / image / **GitHub source revert** 全 dim 明記)+ 12 Stop Conditions + 13 User Reply。

Decision Header:
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

11. Rollback(POLICY §3.6 / §16.4 3 dimensions、必須):
- Tier 1 runtime env: `gcloud run services/jobs update --remove-env-vars=ENABLE_PER_POST_24H_GEMINI_BUDGET,PER_POST_24H_GEMINI_BUDGET_LIMIT --region=asia-northeast1`(30 sec)
- Tier 1 runtime image: prev image SHA(deploy 直前 capture)へ traffic 戻し(2-3 min)
- Tier 2 source: `git revert <impl commit hash>` + push origin master(commit 由来事故時)
- last known good: 直近安定 commit + image SHA

## 実施

1. existing src 読んで impl boundary 確認(改修 #1/#2 と整合)
2. impl + tests を narrow scope で
3. pytest 実行、+0 regression 確認
4. Pack v1 作成(上記 form)
5. `git add` 明示 stage(src + tests + Pack + prompt)、`git diff --cached --name-status` 確認
6. commit message: `feat(cost-guard): per-post 24h Gemini budget - default OFF`
7. plumbing 3 段 fallback 装備
8. `git log -1 --stat`

push は Claude 後実行。

## 完了報告

```json
{
  "status": "completed",
  "changed_files": ["..."],
  "diff_stat": "<n> files changed",
  "commit_hash": "<hash>",
  "test": "pytest <baseline>/<fail> → <new>/<fail>",
  "remaining_risk": "none (default OFF)",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master"
}
```

## 5 step 一次受け契約

- diff narrow(src 1-2 file + tests 1 + Pack 1 + prompt 1)
- 内容 budget impl のみ、既存挙動不変、default OFF
- pytest +0 regression 必須
- scope 内
- rollback 可能(env remove + image rollback + git revert 3 dim)
