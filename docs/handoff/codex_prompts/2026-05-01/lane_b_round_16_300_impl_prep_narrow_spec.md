# Lane B round 16 — 300-COST 実装準備 narrow spec

## 目的

300-COST(source-side guarded-publish 再評価 cost 削減)を実装直前まで進めるため、**narrow impl spec(write_scope + test cases + rollback anchor)** を doc 化。実装そのものはしない、deploy しない、production 不変。

audit 指摘:現行 ready pack は future deploy judgment 寄りで、active 実装 ticket / write_scope が未起票。本 round で narrow spec を 1 page 化し、実装便を fire 可能な状態にする(実装便は別 round で user GO 後)。

## 不可触リスト

- src / tests / scripts / config / .codex / quality-* / draft-body-editor 触らない(narrow spec は doc only)
- env / Scheduler / secret / image / WP / Gemini / mail 触らない
- `git add -A` 禁止
- `docs/ops/*` 触らない
- 既 `2026-05-01_300_COST_ready_pack.md` / `2026-05-01_300_COST_source_analysis_v2.md` / `2026-05-01_300_COST_pack_supplement.md` 削除しない

## scope (新規 file 1 + prompt 永続化、合計 2 path stage)

added (A):
- `docs/handoff/codex_responses/2026-05-01_300_COST_impl_prep_narrow_spec.md`
- `docs/handoff/codex_prompts/2026-05-01/lane_b_round_16_300_impl_prep_narrow_spec.md`(self-include)

## Pack 内容

### Decision Header

```yaml
ticket: 300-COST
recommendation: HOLD  # 298-v4 24h 安定 + 293 完了後に GO 推奨
decision_owner: user
execution_owner: Codex (impl) + Claude (push, deploy verify)
risk_class: medium-low (source-side dedupe、guarded-publish runner narrow fix)
classification: USER_DECISION_REQUIRED  # source-side behavior change
user_go_reason: SOURCE_DEDUPE_BEHAVIOR_CHANGE
expires_at: 5/2 09:00 JST Phase 6 + 24h 安定 + 293 deploy 後
```

### narrow impl spec(implementation 便 fire 用 contract)

1. **write_scope(touch する file、narrow)**:
   - `src/guarded_publish_runner.py`(または equivalent、現行 source-side cost 評価 path)
   - `tests/test_guarded_publish_runner_dedupe_idempotent.py`(新規)
   - `src/cron_eval.py`(idempotent ts append、必要時)
   - **読まないし触らない**: `src/publish_notice_*` / `src/mail_*` / `src/wordpress_*` / `src/gemini_*` / `config/rss_sources.json`

2. **change scope(挙動変化 narrow)**:
   - `cron_eval.json` の trigger ts を idempotent append(同一 post_id 2 度目 ts 上書きしない)
   - guarded-publish runner が同一 post_id 連続 evaluate 時、re-eval skip(POLICY §8 silent skip 0 維持のため log + ledger 残し)
   - 既存 backlog_only / refused / proposed 経路は不変
   - 既存 publish 経路は不変

3. **test cases(7 件以上想定)**:
   - 同一 post_id ledger 既存 → skip + log(silent skip 0)
   - 新規 post_id ledger 未存在 → 通常 evaluate
   - cron_eval.json idempotent ts append(2 度書きで file 不変)
   - backlog_only path 不変
   - refused path 不変
   - proposed path 不変
   - mail volume 不変(MAIL_BUDGET 影響なし)

4. **runtime rollback(POLICY §3.6 / §16.4)**:
   - env rollback: 該当 env knob 無し(impl は flag-less narrow change)、env rollback path = 該当なし
   - image rollback: prev image SHA `<implement 直前 SHA>` 記録、`gcloud run jobs update guarded-publish --image=<prev_SHA>`(2-3 min)
   - 注: env knob 化を含める場合は別 phase

5. **source rollback(POLICY §16.4 dimension 3)**:
   - `git revert <impl_commit_sha>` + push origin master
   - last known good source: `298-v4 deploy 完了 commit family`(`dab9b8e` / `10022c0` 直近)

6. **post-deploy verify plan(POLICY §3.5 7-point)**:
   - image / revision 一致
   - env / flag 一致(env なし or 該当 env のみ)
   - mail volume MAIL_BUDGET 内
   - Gemini delta ±5%(本来増えないはず、scanner 強化のみ)
   - silent skip 0
   - MAIL_BRIDGE_FROM 維持
   - rollback target written

7. **production-safe regression scope**(POLICY §3.4 整合):
   - allowed: read-only / log / health / mail count / env / revision / Scheduler obs / sample candidate / dry-run / existing notification route
   - forbidden: bulk mail / source addition / Gemini increase / publish criteria change / cleanup mutation / SEO / rollback-impossible / flag ON without GO / mail UNKNOWN experiment

8. **stop conditions**: rolling 1h sent>30 / silent skip>0 / errors>0 / 289減 / Team Shiny From変 / publish/review/hold/skip導線破損 / Gemini call >+5% / cache_hit ratio >±15%pt

9. **dependency**:
   - 298-v4 Phase 6 verify pass + 24h 安定
   - 293-COST image rebuild + flag ON 完了(同 image build cycle 整合)
   - pre-300 exact image digest/SHA capture(deploy 直前)

10. **estimated impl rounds**: 1-2(impl + test、Lane B 想定)
11. **estimated deploy rounds**: 1(image rebuild + deploy + post-deploy verify、user GO 後)
12. **user-facing 5-field format(POLICY §15.2)**:
   - 推奨: HOLD(本日時点)/ GO(298-v4 + 293 完了後)
   - 理由: source-side dedupe で Gemini call 削減、副作用なし、live-inert phase 1 経由可能
   - 最大リスク: 既存 dedupe path 破損 → silent skip 発生 → publish-notice mail 不整合
   - rollback 可能か: yes(env なし narrow image rollback、source revert 両方可)
   - user reply: `OK` / `HOLD` / `REJECT`

## 実施

1. 既 ready pack + supplement + source analysis v2 を grep し、現状の dependency / scope / test plan 反映
2. 新 file `docs/handoff/codex_responses/2026-05-01_300_COST_impl_prep_narrow_spec.md` 作成、上記 12 sections を埋める
3. 冒頭に「supersedes implementation-narrow scope of `2026-05-01_300_COST_ready_pack.md`」明記
4. `git add docs/handoff/codex_responses/2026-05-01_300_COST_impl_prep_narrow_spec.md docs/handoff/codex_prompts/2026-05-01/lane_b_round_16_300_impl_prep_narrow_spec.md`
5. `git diff --cached --name-status` で A 2 確認
6. commit message: `docs(handoff): 300-COST impl-prep narrow spec (write_scope + tests + 3-dim rollback + post-deploy verify)`
7. plumbing 3 段 fallback 装備
8. `git log -1 --stat` で 2 file changed 確認

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "docs/handoff/codex_responses/2026-05-01_300_COST_impl_prep_narrow_spec.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_b_round_16_300_impl_prep_narrow_spec.md"
  ],
  "diff_stat": "2 files changed (added)",
  "commit_hash": "<hash>",
  "test": "n/a (doc-only)",
  "remaining_risk": "none",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master"
}
```

## 5 step 一次受け契約

- diff 2 file (handoff 側のみ、src 不変)
- 内容 narrow impl spec doc only
- pytest +0(doc-only)
- scope 内
- rollback 不要(可逆 doc commit)
