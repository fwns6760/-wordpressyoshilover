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
12:25 | Codex Phase 3 preflight stop | 298-Phase3 | bg bpn4zeuqg は preflight で停止(target ffeba45 != HEAD 65e46bd / 私の v6 doc-only commit が原因)/ live mutation 0、image build 0 / Claude src+tests diff 確認 = ffeba45 と HEAD 等価(0 行)| 再 fire 判断
12:30 | Codex Phase 3 deploy 再 fire | 298-Phase3 | bg b3h13kthv / target = HEAD 動的、src+tests 等価宣言で preflight 通過設計 / 不変方針 全部維持、user GO 11:00「デプロイをやって」継続 | Codex 完了待ち、Claude 並行で品質部隊 1 画面回答済
12:50 | Codex retry stop(pytest gate 不一致)| 298-Phase3 | bg b3h13kthv 完了、preflight pytest 0 failures(朝 3 failures は transient / env 依存)、gate 期待値 3 と不一致で deploy stop / live mutation 0 / publish-notice 旧 image:4be818d 維持 | gate 修正 + 再 fire
12:55 | user 推奨判断受領 | 298-Phase3 | Phase 3 deploy 継続 GO、追加 user 確認不要、完了後 8 項目 1 画面報告 / 17:00 production_health_observe 実施 OK / 追加 Codex fire(新規 lane / 新規 ticket)/ mail 大改修 / Scheduler / SEO / source / Gemini 増は HOLD | v3 prompt で Phase 3 continuation fire
13:00 | Codex Phase 3 deploy v3 fire | 298-Phase3 | bg /tmp/codex_phase3_deploy_v3.log / pytest gate を「failures = 0 increase」に修正(transient 3 failures は flaky 判定、299-QA は別途 flaky 整理)/ continuation lane | Codex 完了で 8 項目報告
13:01 | pytest gate pass | 298-Phase3 | `pytest -q` = `2008 passed / 0 failed` | clean export + build 進行
13:03 | clean export + hold-carry verify | 298-Phase3 | `/tmp/yoshi-deploy-head` 作成 / `git diff ffeba45 HEAD -- src/ tests/` empty / `4be818d..HEAD` に `c14e269` 含むが `ENABLE_WEAK_TITLE_RESCUE` 未設定で live effect なし | Cloud Build
13:06 | image rebuild success | 298-Phase3 | Cloud Build `d9b78304-c172-4c1a-88ff-c84045857198` 成功 / new image `publish-notice:1016670` digest `sha256:644a0ff30494bd41c078ea4a08179ba8b41ad507a66af47677c6c430176059e2` | flag OFF deploy
13:08 | flag OFF deploy + observe green | 298-Phase3 | job generation `40` / image digest deploy / env unchanged / trigger `02:20Z sent=1 errors=0` + `02:25Z sent=1 errors=0` / `post_gen_validate` path present / silent skip 0 | flag ON apply
13:09 | flag ON apply | 298-Phase3 | job generation `41` / `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1` / image unchanged | flag ON observe
13:24 | flag ON observe green | 298-Phase3 | trigger `02:35Z sent=10 errors=0` + `02:40Z sent=10 errors=0` / first batch ids `61938-62039` / second batchは first batch を `OLD_CANDIDATE_PERMANENT_DEDUP` skip しつつ new ids `62070-62396` 送信 / forbidden `63003-63311` sent 0 / rolling 1h sent `24` / since 09:00 JST `125` | doc-only report commit + push
13:35 | flag ON 後 storm 再発検出 | 298-Phase3 | 02:35-02:56 UTC = 11:35-11:56 JST flag ON 後 5 trigger 連続 sent=10、累積 50+ 通、post_id 範囲 62455-62940(MIN_AGE_DAYS=3 以上の old backlog pool first emit storm)/ rolling 1h ~142 通、MAIL_BUDGET 30/h 完全違反 / permanent_dedup 機能(post_id 重複 0)| §14 8 条件 全部 AND 確認、Claude 自律 rollback 判定
13:55 | Phase3 flag rollback 自律実行 | 298-Phase3 | gcloud run jobs update publish-notice --remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE / env 不在 verify、Team Shiny / 289 / live_update / Scheduler / Gemini 全部不変、image は new(:1016670)維持で permanent_ledger 機能無効化 = deploy 前等価挙動 | post-rollback observe
14:15 | post-rollback observe | 298-Phase3 | 直近 16 trigger(03:00-04:15 UTC = 12:00-13:15 JST)sent 累計 8 通 / rolling 1h 5-6 通 / 【要確認(古い候補)】 emit 0 件 / 通常 path 全部観測(【要review｜post_gen_validate】1 / 【要確認】3 / 【要確認・X見送り】1 / 【巨人】1)/ errors=0 / silent skip 0 / Team Shiny 維持 / state ROLLED_BACK_AFTER_REGRESSION / HOLD_NEEDS_PACK | 第二波 risk OPEN
14:20 | 第二波 cardinality estimate | 298-Phase3 | backlog_only pool unique post_id = 103 / 5/1 朝 storm group(63003-63311)= 99 unique post_id、24h dedup expire 5/2 09:00 JST で再 emit 想定 ~99 通(MAIL_BUDGET 100/d ギリギリ違反、30/h 完全違反)| 安全策 4 案(Case A ledger seed mode / Case D backlog_only mute / Case F GCS pre-seed / Case E 受容)、impl + deploy 必要のため明日朝間に合わない可能性高
14:30 | チケット消化モード受領 | - | user 方針:時間判断は user / Claude はリスク・デグレ・コスト ゲート / OK 条件 9/9 pass / 298-Phase3 ROLLED_BACK_AFTER_REGRESSION 維持 / 次 = 293-COST 補強 → 299-QA / 300-COST 並走 | 進行
14:40 | 293-COST v2 enhance + push | 293-COST | Codex Lane A v2(30c8204、711 行 read-only 解析 + impl 順序 4 commit + ledger schema yaml + test 7 cases JSON fixture + rollback Phase A/B/C)を Claude 補強(§8 Acceptance Pack 18 項目 final + §9 282-COST flag ON 前提整理 + §10 追加 rollback + §11 完了状態)| commit 7f2f3e9 push、298 ROLLED_BACK + 293 補強完了
14:50 | Codex 2 lane 並走 fire | 299-QA + 300-COST | Lane A bog1ws7xr(299-QA flaky / transient 解析、pytest 2 round + 真因仮説 + 観察条件 + close 条件)/ Lane B btdil79om(300-COST source-side guarded-publish 再評価 read-only 解析、cost 見積 + Option C-narrow impl 案 + rollback plan)、両 lane disjoint scope / read-only / doc-only / impl 禁止 / single-file diff each / Codex push なし(Claude push)| Codex 完了で追認 + 8 項目 Decision Batch 報告
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
