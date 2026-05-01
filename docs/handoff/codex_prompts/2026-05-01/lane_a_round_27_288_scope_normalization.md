# Lane A round 27 — 288-INGEST scope normalization + phase split

## 目的

audit (Lane A round 23) 指摘:288-INGEST の active ticket は fallback / trust / phase 1-4 を含む multi-phase scope だが、ready pack は narrow source-add (3 source 追加) scope。両者の scope normalization を doc-only で実施し、ready pack 側を active ticket と一致させる。phase split で source 追加 直前まで 進める。

doc-only。code / deploy / production 不変。source 追加しない。

## 不可触リスト

- src / tests / scripts / config / .codex / quality-* / draft-body-editor 触らない
- env / Scheduler / secret / image / WP / Gemini / mail 触らない
- `config/rss_sources.json` 触らない(source 追加しない)
- `git add -A` 禁止
- `docs/ops/*` 触らない
- 既 `2026-05-01_288_INGEST_*` file 削除しない、保存

## scope (新規 file 1 + prompt 永続化、合計 2 path stage)

added (A):
- `docs/handoff/codex_responses/2026-05-01_288_INGEST_pack_v3_scope_phase_split.md`(scope normalization + phase split、active ticket と整合、`OK/HOLD/REJECT` + §3.5 + §16.4 反映)
- `docs/handoff/codex_prompts/2026-05-01/lane_a_round_27_288_scope_normalization.md`(self-include)

冒頭に「supersedes `2026-05-01_288_INGEST_ready_pack.md`(narrow source-add phase artifact)」明記、active ticket scope(fallback / trust / phase 1-4)と integrate。

## Pack 内容(13 fields + 10a/10b、ACCEPTANCE_PACK_TEMPLATE 整合 + multi-phase split)

### Decision Header

```yaml
ticket: 288-INGEST
recommendation: HOLD  # source 追加直前まで完了、user GO 後に phase 1 から順次
decision_owner: user
execution_owner: Codex (impl) + Claude (push, source-add deploy verify)
risk_class: medium-high  # source addition + Gemini call increase + mail volume increase potential
classification: USER_DECISION_REQUIRED  # SOURCE_ADD + COST_INCREASE
user_go_reason: SOURCE_ADD+COST_INCREASE+MAIL_VOLUME_IMPACT
expires_at: 298-v4 24h 安定 + 293/282 完了 + Pack 13 fields UNKNOWN 解消後
```

### multi-phase scope split(active ticket と integrate)

ready pack の 「3 source add narrow」を以下 4 phase に展開、各 phase 別 user GO + Pack:

- **Phase 1: candidate visibility contract**(source 追加前段、silent skip 0 確認の前提)
- **Phase 2: fallback + trust score impl**(narrow source-add、CLAUDE_AUTO_GO 候補 if live-inert)
- **Phase 3: source追加(3 source、live mail / Gemini call 影響)**(USER_DECISION_REQUIRED、本 round の主 target)
- **Phase 4: post-add stabilization + cost trend audit**(24h 観察 + Pack v4)

### 13 fields(ACCEPTANCE_PACK_TEMPLATE)

1. **Conclusion**: 推奨 HOLD(298-v4 + 293/282 完了 + 各 phase precondition 満足後に user GO で phase 1 から順次 GO 化)
2. **Scope**:
   - Phase 1: candidate visibility contract 確認(read-only)
   - Phase 2: fallback + trust score narrow impl(Codex 便、CLAUDE_AUTO_GO 候補 if live-inert)
   - Phase 3: 3 source 追加(`config/rss_sources.json` 編集、live mail + Gemini call 影響、USER_DECISION_REQUIRED)
   - Phase 4: 24h post-add observe + cost audit
3. **Non-Scope**: image 変更(Phase 2 は narrow code change 想定)/ Scheduler / SEO / publish 基準変更 / 全 phase 跨いだ一括 GO
4. **Current Evidence**:
   - active ticket: `doc/active/288-INGEST-source-coverage-expansion.md` multi-phase scope
   - existing Pack: `26ede3a`(draft) + `5f8b966`(supplement) + `ade62fb`(unknown resolution) + `7fd760f`(ready pack)
   - prod state: 298-v4 OBSERVED_OK
5. **User-Visible Impact**:
   - Phase 1: なし(read-only)
   - Phase 2: なし(narrow code change、flag OFF default 想定)
   - Phase 3: 新規 source 由来 candidate 増加 → review mail 増加(MAIL_BUDGET 30/h 内設計必須)
   - Phase 4: なし(observe)
6. **Mail Volume Impact**:
   - Phase 1-2: なし
   - Phase 3: expected +N mail/h(N 数値は phase 3 Pack で確定)、MAIL_BUDGET 30/h・100/d 内設計必須
   - Phase 4: 24h 観察 trend
7. **Gemini / Cost Impact**:
   - Phase 1: なし
   - Phase 2: なし(narrow code change)
   - Phase 3: source 追加で Gemini call +M%(M 数値は phase 3 Pack で確定、UNKNOWN 解消必須、目安 +10-20% 想定)
   - Phase 4: 24h cost trend
8. **Silent Skip Impact**:
   - Phase 1-3 全て:silent skip 0 維持(POLICY §8、新 source 候補も visible publish/review/hold/skip 経由)
9. **Preconditions**:
   - 298-v4 Phase 6 verify pass + 24h 安定
   - 293-COST image rebuild + flag ON 完了
   - 282-COST flag ON 完了 + 24h 安定
   - 291/295/293→282 dependency chain 確認
   - phase 3 直前で:expected mail/h + Gemini delta exact 数値確定 + rollback path 確認
10. **Tests**:
   - phase 1: read-only verify only
   - phase 2: unit + integration + mail flow + rollback test
   - phase 3: source add smoke + 24h regression + mail volume verification
   - phase 4: observe trend audit
10a. **Post-Deploy Verify Plan(POLICY §3.5 7-point、phase 3 用)**:
   - image / revision: phase 2 deploy 後 image 維持
   - env / flag: 該当 env 反映確認
   - mail volume: rolling 1h<30、24h<100
   - Gemini delta: exact 数値範囲内(phase 3 Pack で確定)
   - silent skip: 0 維持
   - MAIL_BRIDGE_FROM 維持
   - rollback target: source revert + env remove + image rollback 全 path 記録
10b. **Production-Safe Regression Scope**:
   - allowed: read-only / log / health / mail count / env / revision / Scheduler obs / sample candidate / dry-run / existing notification route
   - forbidden: bulk mail / unknown source addition / publish criteria change / cleanup mutation / SEO / rollback-impossible / flag ON without GO / mail UNKNOWN
11. **Rollback(POLICY §3.6 / §16.4 3 dimensions)**:
   - Tier 1 runtime env: 該当 env knob があれば `gcloud run jobs update <job> --remove-env-vars=<flag>`(30 sec)
   - Tier 1 runtime image: phase 2 narrow code change を含む場合、prev image SHA へ戻す(2-3 min)
   - Tier 2 source: `git revert <bad_commit>` + `config/rss_sources.json` revert + push origin master
   - last known good: 298-v4 deploy 完了 commit family + 293/282 deploy 完了 image SHA
12. **Stop Conditions**: rolling 1h sent>30 / silent skip>0 / errors>0 / 289減 / Team Shiny変 / Gemini call >+5%(phase 3 expected delta 超過時) / publish/review/hold/skip導線破損 / source-add 由来 storm pattern 検出
13. **User Reply**: 一言 `OK` / `HOLD` / `REJECT`(各 phase 別、phase 1 / 2 / 3 / 4 ごとに別 Pack で 5-field format 提示)

## 実施

1. 既 `docs/handoff/codex_responses/2026-05-01_288_INGEST_ready_pack.md` + supplement + unknown resolution + active ticket `doc/active/288-INGEST-source-coverage-expansion.md` 確認、scope の差異を抽出
2. 新 file 作成: 上記 13 fields + Decision Header + 4 phase split + active ticket scope と integrate、supersedes 明記
3. `git add docs/handoff/codex_responses/2026-05-01_288_INGEST_pack_v3_scope_phase_split.md docs/handoff/codex_prompts/2026-05-01/lane_a_round_27_288_scope_normalization.md`
4. `git diff --cached --name-status` で A 2 確認
5. commit message: `docs(handoff): 288-INGEST Pack v3 scope normalization + 4-phase split (active ticket scope sync)`
6. plumbing 3 段 fallback 装備
7. `git log -1 --stat` で 2 file changed 確認

push は Claude 後実行。

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "docs/handoff/codex_responses/2026-05-01_288_INGEST_pack_v3_scope_phase_split.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_a_round_27_288_scope_normalization.md"
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

- diff 2 file (handoff 側のみ、ops + active ticket 不変)
- 内容 scope normalization + 4-phase split のみ、source 追加なし
- pytest +0(doc-only)
- scope 内
- rollback 不要(可逆 doc commit)
