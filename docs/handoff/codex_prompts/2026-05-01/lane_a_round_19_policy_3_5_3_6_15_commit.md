# Lane A round 19 — POLICY §3.5 + §3.6 + §15 + §14.5 row commit + push

## 目的

Claude が `docs/ops/POLICY.md` に追加した以下を 1 commit で永続化:

- §3.5 Post-Deploy Verify Checklist(7 項目)
- §3.6 Rollback Mechanism 2-tier(runtime + source)
- §15 Field-Lead Discipline & User Interface Format(15.1〜15.6)
- §14.5 298-Phase3 v4 row 更新(USER_DECISION_REQUIRED → 本日 user GO 受領済 deploy 完了、根拠列も「本日 19:30 JST『ならやる』受領」に更新)

本日 user 明示の strengthening。298-v4 deploy 経験 + user 依存度低減 directive 反映。

**round 19 retry**: 前回 run は §14.5 row 更新を unexpected diff として stop したが、Claude 側で明示的に scope に含めることを判断。current state 反映として正当。

## 不可触リスト(Hard constraints)

- src / tests / scripts / config / .codex/automations / quality-* / draft-body-editor 一切触らない
- `docs/ops/POLICY.md` 以外の doc 触らない
- env / Scheduler / secret / image / WP / Gemini call 一切触らない
- `git add -A` 禁止、`git add docs/ops/POLICY.md` のみ
- Lane B round 15 (`bbnqyhph3`) は完了 close 済 、scope disjoint

## 実施

1. `git status --short` で `docs/ops/POLICY.md` が modified、他に staged 残骸なし確認
2. `git diff docs/ops/POLICY.md` で §3.5 / §3.6 / §15 の追加 diff のみ確認
3. 想定外 diff があれば即 stop、Claude に報告
4. `git add docs/ops/POLICY.md`
5. `git diff --cached --name-status` で `M docs/ops/POLICY.md` 1 行のみ確認
6. commit message:

```
docs(ops): POLICY §3.5 post-deploy 7-point + §3.6 2-tier rollback + §15 field-lead discipline

本日 user 明示 strengthening、298-v4 deploy 経験 + user 依存度低減 directive 反映。

§3.5 Post-Deploy Verify Checklist (7 項目):
image / env / mail volume / Gemini delta / silent skip / MAIL_BRIDGE_FROM / rollback target

§3.6 Rollback Mechanism 2-tier:
- Tier 1 runtime (env remove 30 sec / image・revision 前へ 2-3 min)
- Tier 2 source (git revert + push、history rewrite 不可)
両方必須

§15 Field-Lead Discipline:
- 15.1 Claude responsibilities(技術 / デグレ / コスト / mail / rollback / Codex pool / 次便 / Pack / 推奨)
- 15.2 user-facing 5-field format(推奨 / 理由 / 最大リスク / rollback / 一言)
- 15.3 禁止行為(user 質問・複数候補・技術判断委譲・idle 発見・relay)
- 15.4 UNKNOWN 処理(user に投げない、Claude が潰す → 潰せなければ推奨 HOLD)
- 15.5 user は現場監督ではない、判定だけ
- 15.6 適用境界 4 状態
```

7. `git commit -m "<message>"` 実行
8. commit 失敗時 plumbing 3 段(write-tree / commit-tree / update-ref)で fallback
9. `git log -1 --stat` で commit 着地確認(`docs/ops/POLICY.md` 1 file changed のみ)

## 完了報告(Final report、JSON)

```json
{
  "status": "completed",
  "changed_files": ["docs/ops/POLICY.md"],
  "diff_stat": "1 file changed, ~110 insertions(+), 1 deletion(-)",
  "commit_hash": "<hash>",
  "test": "n/a (doc-only)",
  "remaining_risk": "none",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master"
}
```

## 5 step 一次受け契約

- diff 1 file (POLICY.md) のみ
- §3.5 / §3.6 / §15 内容のみ追加
- pytest +0(doc-only)
- scope 内
- rollback 不要(可逆 doc commit)
