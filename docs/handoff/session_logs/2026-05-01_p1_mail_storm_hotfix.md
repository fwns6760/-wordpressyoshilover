# 2026-05-01 P1 mail storm hotfix(履歴)

`docs/ops/CURRENT_STATE.md` / `OPS_BOARD.yaml` 298-MAIL-STORM-HOTFIX entry が active 正本。本 file は履歴扱い(POLICY §1)。

## 1 行履歴(時系列、JST)

```
09:00 | env apply | 298 | PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168 (user 明示 GO §14 例外発動) | storm 観察
09:05 | sent=10 trigger 1 | 298 | publish-notice */5 trigger 開始 | storm 確認
09:30 | sent=10 trigger 6 | 298 | 累積 60 通 | env 戻し判断
09:33 | env remove | 298 | PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168 削除 (user 明示 GO §14 例外) | 09:35 trigger verify
09:35 | sent=10 trigger continued | 298 | env 削除しても storm 継続 = env=168 単独原因ではない | Codex A/B 並行 fire
09:43 | codex A/B fire | 298 | bg b2ymllzsv (read-only verify + 最小 hotfix 案) / bg bdm147ppc (3 案比較 + Acceptance Pack 起草) | Claude 本体は運用立て直し
09:50 | docs/ops/ update | 298 | POLICY §14 §15 追加 / CURRENT_STATE 298 ACTIVE 化 / OPS_BOARD 298 entry 追加 | commit + push
```

## hotfix 経過 evidence(数値)

- ledger:`gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl` 28.81 MiB
- tail 200 records:103 unique post_ids、各 post_id が 09:30:45 + 09:35:47 で 2 record(=trigger 毎再評価で fresh ts)
- 全件 status=skipped / judgment=yellow / hold_reason=backlog_only
- emit subject prefix:【要確認(古い候補)】 (= `_guarded_publish_subject_prefix(hold_reason="backlog_only")`)

## 不変方針 維持確認(09:35 時点)

- `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` ✓
- `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` ✓
- `ENABLE_LIVE_UPDATE_ARTICLES=0` ✓
- X 自動投稿 OFF ✓
- Scheduler 頻度不変 ✓
- code 変更 0 ✓
- Gemini call 増加 0 ✓

## 次のアクション

1. Codex A 完了 → 最小 hotfix 案 review(env or scheduler narrow)
2. Codex B 完了 → 恒久対策 Acceptance Pack 提示(scope: code fix scanner / persistent ledger / 等)
3. user GO 受領 → Codex 実装便 + image rebuild + deploy
4. deploy 後 sent=0 verify + 24h 観察 → close

## 関連

- `docs/ops/POLICY.md` §14(P0/P1 自律 hotfix 範囲、本 incident 起源で永続化)
- `docs/ops/POLICY.md` §15(Outcome Ledger format、本 incident 完了 evidence の format)
- `docs/ops/CURRENT_STATE.md` ACTIVE 298 entry
- `docs/ops/OPS_BOARD.yaml` active: 298 entry
- `docs/handoff/codex_responses/2026-05-01_codex_a_storm_verify.md`(Codex A 完了後生成)
- `docs/handoff/codex_responses/2026-05-01_codex_b_storm_permanent_fix.md`(Codex B 完了後生成)
