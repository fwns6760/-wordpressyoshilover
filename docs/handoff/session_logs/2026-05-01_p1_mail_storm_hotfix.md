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
09:48 | codex A 完了 | 298 | bc1e5c0 着地、env-only 2 案 + Acceptance Pack draft、gcloud auth fail で観察未完 | doc review
09:49 | codex B 完了 | 298 | 0b64078 着地、Option B 推奨 + Acceptance Pack draft、impl + test 設計 | user 提示準備
09:50 | docs/ops/ update v1 | 298 | POLICY §14 §15 追加 / CURRENT_STATE 298 ACTIVE 化 / OPS_BOARD 298 entry 追加 | commit 0b64078 (Codex B 巻き込み混入で 1 commit に統合)
09:55 | user 方針修正受領 | 298 | 主目的=運用立て直し、§14 を user 明示 GO 不要 8 条件に変更、§3 自律 GO 10 categories 化 | POLICY 再更新
10:00 | docs/ops/ update v2 | 298 | POLICY §3 10 categories(INCIDENT_ANALYSIS / P0_P1_NARROW_HOTFIX 追加)/ §14 user 明示 GO 不要化 8 条件 / 298 を Phase 1 + Phase 2 active 分割 | commit 5fe7fad push
10:05 | user 判断受領 | 298 | Phase1=条件付きGO(storm 継続中なら)/ Phase2=GO(impl + test + commit + push、deploy はまだ HOLD)| storm 現状確認
10:07 | storm 自然終息確認 | 298-Phase1 | 09:50 JST sent=10 第一波最後 / 09:55 JST 以降 sent=0 維持 / 累積 90 通で完結 | Phase1 HOLD 確定(実行せず)
10:10 | Phase2 Codex impl 便 fire | 298-Phase2 | persistent sent ledger Option B impl + test + commit + push、deploy はしない | Codex 完了待ち
10:21 | impl + push | 298-Phase2 | d44594a | docs update + deploy Pack final
10:30 | user 方針再整理受領 | 298 | 運用 OS 立て直し only / Phase3 1 Pack 条件付き段階化 / mail 通知大改修 HOLD / 通知体系 全体再設計 HOLD / MAIL_BUDGET + user 通知絞り込み追加 | POLICY §17-§24 追加
11:00 | docs/ops/ update v3 | 298+299+300 | POLICY §17 一次受け §18 18 項目 §19 体感事故 §20 本日 GO scope §21 正本階層 §22 MAIL_BUDGET §23 user 通知絞り込み / TEMPLATE 18 項目化 / INCIDENT_LIBRARY.md 新規 / 299-QA OBSERVE 起票 / 300-COST FUTURE 起票 / 298-Phase3 Pack 18+5 項目 OPS_BOARD embed | commit + push
11:10 | 運用 OS MVP 完了報告 | - | user 11:30 期限内 / ACTIVE 0 / OBSERVE 2 / READY 0 / HOLD_NEEDS_PACK 4 / FUTURE_USER_GO 7 / FROZEN 16 / DONE 5 / mail storm 停止確認 / user 必要判断 = 明日朝 298-Phase3 1 Pack | -
11:20 | structural cleanup | 298-Phase3 / RUNBOOK | OPS_BOARD 298-Phase3 を hold_needs_pack 配下に short entry で追加(詳細 pack は anchor 配下維持)/ NEXT_SESSION_RUNBOOK §1 必読 + §7 関連 doc を POLICY §21 §24 整合化 / CURRENT_STATE HOLD_NEEDS_PACK + FUTURE_USER_GO 表 整合化(298-Phase3 + 300-COST 反映)| commit + push
12:00 | mail status verify | - | 09:55-10:55 JST 約 1h sent=0 連続 + 10:25 sent=1(通常 review 単発)/ MAIL_BUDGET 30/h 内、storm 終息確定、第二波 5/2 09:00 想定変わらず | user 「mail OK?」確認
12:05 | user GO Phase3 deploy | 298-Phase3 | 「デグレなしでデプロイをやって」受領、Claude 一次受け、Codex deploy 便 fire 開始 | 報告 → fire
12:10 | Codex Phase 3 deploy fire | 298-Phase3 | bg bpn4zeuqg / image rebuild from ffeba45 → flag OFF deploy → 2-3 trigger 観察 → 条件 OK で flag ON → 1-2 trigger 観察、不変方針 全部維持 | Codex 完了待ち、Claude 並行で運用立て直し継続
12:15 | docs/ops/ update v6 | 298-Phase3 | OPS_BOARD active entry を Pack finalize → deploy 進行中に書換 / CURRENT_STATE USER_VISIBLE_NOW 0 件 + HOLD_NEEDS_PACK 3 + FUTURE_USER_GO 7 の 3 分類化 + 58→29 差分 1 行説明 / OBSERVE 統合(299-QA を sub_observe_items 配下) | commit + push
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
