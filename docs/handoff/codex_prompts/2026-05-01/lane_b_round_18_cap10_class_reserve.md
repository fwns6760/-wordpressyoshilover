# Lane B round 18 — cap=10 class reserve impl(改修 #6、デプロイ直前まで)

## 目的

POLICY §19.9 mail storm 恒久対策補強。publish-notice scanner の cap=10/run の中に class 別 minimum 枠を実装:

- real review:3 minimum
- 289 post_gen_validate:2 minimum
- error notification:1 minimum
- 残 4 を guarded review / old_candidate / 293 preflight_skip で配分

cap=10 を超える混雑時、real review / 289 / error が消えないことを保証。本日 5/1 18:00-19:00 evidence では問題なかったが、混雑時の保険として実装。

「デプロイ直前まで」= impl + test + push、image rebuild + flag ON は user GO 後。

## 不可触リスト(Hard constraints)

- Cloud Run deploy / env / flag / Scheduler / SEO / source / Gemini / mail 触らない
- `git add -A` 禁止、明示 stage のみ
- 既存 cap=10 全体上限不変(class reserve の中で配分するだけ)
- 既存 dedup logic 不変、24h dedup 不変、permanent_dedup ledger 不変
- `src/mail_*` 触らない(LLM-free invariant 維持)
- `config/rss_sources.json` 触らない
- pytest baseline 2018/0 から regression なし

## scope

write_scope(narrow):
- `src/publish_notice_scanner.py`(cap allocation logic)
- `tests/test_publish_notice_scanner_class_reserve.py`(新規)

read-only(理解のため):
- 既存 cap=10 logic 全体
- POLICY §7 mail storm rules
- 5/1 storm evidence(INCIDENT_LIBRARY)

## 実装方針

1. cap=10 の中で class 別 reserve 計算:
   - notice_kind 別に candidate を group 化
   - class minimum 枠 を確保(real_review=3 / post_gen_validate=2 / error=1)
   - 残 4 を「先着」or「priority」で配分(現状 priority 順:real_review > guarded_review > 289 > preflight_skip > old_candidate)
2. class minimum 枠不在時の挙動:
   - real_review が 3 件未満 → 残枠を他 class へ譲渡(枠を浪費しない)
   - 同様 289 / error
3. cap=10 全体上限は維持(POLICY §7 整合)
4. unit test 5 cases 以上:
   - 混雑時 real_review 3 件 confirm
   - 289 reserve confirm
   - error reserve confirm
   - 余剰時 reserve 譲渡 confirm
   - 既存 priority order 維持 confirm

## env knob(default OFF、deploy 後 enable)

- `ENABLE_PUBLISH_NOTICE_CLASS_RESERVE` (default 0、現行 priority order 維持)
- `PUBLISH_NOTICE_CLASS_RESERVE_REAL_REVIEW` (default 3)
- `PUBLISH_NOTICE_CLASS_RESERVE_POST_GEN_VALIDATE` (default 2)
- `PUBLISH_NOTICE_CLASS_RESERVE_ERROR` (default 1)

flag OFF default = live-inert deploy で挙動 100% 不変、CLAUDE_AUTO_GO 候補。flag ON で reserve 適用(USER_DECISION_REQUIRED)。

## Pack v1(本 round で同時作成)

新 file: `docs/handoff/codex_responses/2026-05-01_change_30_cap10_class_reserve_pack_v1.md`

13 fields + 10a 7-point + 10b production-safe regression + 11 3-dim rollback:

```yaml
ticket: 改修-30-cap10-class-reserve
recommendation: HOLD  # 298-v4 24h 安定 + 293 deploy 完了後に GO 化検討
decision_owner: user
execution_owner: Codex (impl) + Claude (push, deploy verify)
risk_class: low-medium(scanner allocation 改修、既存 priority 維持)
classification: USER_DECISION_REQUIRED  # image rebuild + flag ON 時、混雑時の挙動変化
user_go_reason: MAIL_STORM_PROTECTION_ENHANCEMENT
expires_at: 298-v4 + 293 完了後
```

## 実施

1. existing scanner 読んで cap=10 logic 確認
2. impl + test を narrow scope で
3. pytest 実行、+0 regression
4. Pack v1 作成
5. `git add` 明示、`git diff --cached --name-status` 確認
6. commit message: `feat(mail-storm-protection): cap=10 class reserve (real_review/289/error minimum) - default OFF`
7. plumbing 3 段 fallback 装備
8. `git log -1 --stat`

push は Claude 後実行。

## 完了報告

```json
{
  "status": "completed",
  "changed_files": [
    "src/publish_notice_scanner.py",
    "tests/test_publish_notice_scanner_class_reserve.py",
    "docs/handoff/codex_responses/2026-05-01_change_30_cap10_class_reserve_pack_v1.md",
    "docs/handoff/codex_prompts/2026-05-01/lane_b_round_18_cap10_class_reserve.md"
  ],
  "diff_stat": "<n> files changed",
  "commit_hash": "<hash>",
  "test": "pytest <baseline>/0 → <new>/0",
  "remaining_risk": "none (default OFF, 既存 priority 維持)",
  "open_questions_for_claude": [],
  "next_for_claude": "git push origin master"
}
```

## 5 step 一次受け契約

- diff narrow(src 1 + tests 1 + Pack 1 + prompt 1)
- 内容 cap allocation 改修のみ、cap=10 全体上限不変
- pytest +0 regression 必須、新 test +N 0 fail
- scope 内
- rollback 可能(env remove で priority order 維持に戻る)
