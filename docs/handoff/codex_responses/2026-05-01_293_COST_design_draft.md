# 293-COST design draft(Claude 一次受け、impl HOLD、Pack draft / test plan / rollback plan)

**作成**: 2026-05-01 13:30 JST
**status**: 設計 draft、impl 未着手、commit pending(Phase 3 close 後にまとめて 1 commit)
**owner**: Claude(decision_owner=user / execution_owner=Codex / evidence_owner=Claude)
**user_go_required**: true(MAIL_ROUTING_MAJOR、ただし本 draft 段階は HOLD 推奨)

---

## 1. 仕様整理

### 目的
preflight skip event を **user-visible 化**(silent skip 0 維持、POLICY §6 遵守)。
**282-COST flag ON の前提 ticket**(POLICY §7 順序固定: 293 → 282、逆順禁止)。

### 背景
- 282-COST = `ENABLE_GEMINI_PREFLIGHT=1` で preflight gate ON、cost 削減が目的
- 現状 flag OFF = preflight 動かない、skip event 0、影響なし
- 282 を flag ON すると preflight skip が発生しうる、その event が **mail に乗らないと silent skip**(POLICY §6 P0)
- → 293 で preflight skip を mail に乗せる、その後 282 を flag ON で安全

### 観測対象
- preflight skip event(skip_layer="preflight"、skip_reason 必須)
- ledger 記録 → publish-notice scanner で emit → mail subject `【要review｜preflight_skip】`
- 289 post_gen_validate(skip_layer="post_gen_validate")と **並列 path**、shared cap=10 で competition

---

## 2. scope(touched_files、impl 着手前)

### src/ 編集予定 (impl HOLD、本 draft では設計のみ)
1. `src/rss_fetcher.py`(preflight call site、skip event 出力に skip_layer / skip_reason 必須化)
2. `src/post_gen_validate.py` または別 helper(preflight skip と post_gen_validate skip の共通 ledger schema 定義)
3. `src/cloud_run_persistence.py`(新 ledger `preflight_skip_history.jsonl` の GCS sync)
4. `src/publish_notice_scanner.py`(`scan_preflight_skip_history` 関数追加、subject prefix `【要review｜preflight_skip】`、shared cap=10 で 289 と competition)

### new env(全 default OFF)
- `ENABLE_PREFLIGHT_SKIP_NOTIFICATION` (default 0、本 ticket 自身 toggle)
- `PREFLIGHT_SKIP_LEDGER_PATH` (default `/tmp/pub004d/preflight_skip_history.jsonl`)
- `PREFLIGHT_SKIP_DEDUPE_KEY_FIELDS` (default `source_url_hash,subtype`)

### Not in scope
- 282-COST flag ON 自体(別 ticket)
- Gemini call 増加(本 ticket は scanner / persistence / ledger だけ touch、Gemini 呼び出しは 282-COST で活性化)
- Scheduler / SEO / Team Shiny / X 自動投稿 / source 追加 / 290 / 298

---

## 3. test plan(7 cases)

### 新規 test cases
1. `tests/test_preflight_skip_notification.py::test_preflight_skip_emit_to_mail_when_flag_on`
   - flag ON + preflight skip event → mail subject 【要review｜preflight_skip】 emit
2. `tests/test_preflight_skip_notification.py::test_preflight_skip_silent_skip_0_when_flag_off`
   - flag OFF + preflight skip event 想定なし(282 flag OFF 前提)→ scanner 走らない
3. `tests/test_preflight_skip_notification.py::test_preflight_skip_dedupe_24h_window`
   - 同一 dedupe_key 24h 内重複 → REVIEW_RECENT_DUPLICATE skip
4. `tests/test_preflight_skip_notification.py::test_preflight_skip_shared_cap10_with_post_gen_validate`
   - 289 emit + preflight skip emit、合算 cap=10 / run 維持
5. `tests/test_preflight_skip_notification.py::test_preflight_skip_silent_event_logged_when_skip_reason_missing`
   - skip_reason missing → POLICY §6 silent skip 検出 → P0 record
6. `tests/test_publish_notice_email_sender.py::test_send_keeps_yoshilover_subject_when_preflight_skip_path`
   - subject prefix 【要review｜preflight_skip】 に YOSHILOVER 維持
7. `tests/test_cloud_run_persistence.py::test_entrypoint_restores_and_uploads_preflight_skip_ledger`
   - 新 state file の GCS sync(download / upload)

### 維持 assertion(既存 test 全 green)
- `tests/test_post_gen_validate_notification.py`(289 path 完全維持)
- `tests/test_publish_notice_email_sender.py`(Team Shiny / subject 維持)
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_*`(298 / yellow / cleanup_required path 維持)
- `tests/test_publish_notice_scanner.py::test_scan_guarded_publish_history_old_candidate_*`(298 永続 ledger 維持)

---

## 4. rollback plan

### Phase A(env で即無効化)
```bash
gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite \
  --remove-env-vars=ENABLE_PREFLIGHT_SKIP_NOTIFICATION
```
30 秒以内に挙動戻る、image そのまま。

### Phase B(image revert、env 効かない場合)
```bash
gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite \
  --image=<293-impl 直前の image SHA>
```

### Phase C(GCS state file 削除、ledger 異常時)
```bash
gsutil rm gs://baseballsite-yoshilover-state/publish_notice/preflight_skip_history.jsonl
```
※ history 残したい場合は archive 退避

---

## 5. Acceptance Pack 18 項目 draft(impl + test + commit 後 update 予定)

```markdown
## Acceptance Pack: 293-COST-impl-and-deploy

- Decision: HOLD(impl + test 未、298 安定確認後の起票検討)
- Requested user decision: 293-COST impl + test + commit + push を進めるか(deploy + flag ON はさらに別 Pack)
- Scope: §2 参照(src 4 file + new test file + ledger + 3 new env default OFF)
- Not in scope: 282-COST flag ON / Gemini call 増加 / Scheduler / SEO / Team Shiny / 298 / 290
- Why now: 282-COST flag ON の前提として preflight skip visible 化が必要(POLICY §7 順序固定)
- Preconditions:
  * 298-Phase3 deploy + 24h 安定確認済(2026-05-02 13:24 JST 以降)
  * 17:00 JST production_health_observe pass
  * 299-QA flaky 判定 close
- Cost impact: Gemini call 0(scanner / persistence / ledger touch のみ、Gemini 呼び出しは 282-COST で活性化)/ Cloud Build 1 回(impl 完了後 deploy 時)
- User-visible impact: 【要review｜preflight_skip】 mail が 282 flag ON 後に出る(289 通知と並列、shared cap=10)
- Rollback: §4 Phase A/B/C
- Evidence: 設計 doc 完了 / impl + test green + commit hash / push origin/master / 24h 観察
- Stop condition: 289 emit 減少 / Team Shiny 変化 / silent skip 増 / Gemini call 増(本 ticket 経由) / cap=10 違反
- Expiry: 2026-05-15(282-COST flag ON 想定 timing 前)
- Recommended decision: HOLD(impl evidence 未、298 安定 + 17:00 production_health_observe 結果待ち)
- Recommended reason: 282 前提 ticket だが、298 close まで impl 着手しない方が安全(scope 純度、blast radius 制御)
- Gemini call increase: NO
- Token increase: NO
- Candidate disappearance risk: NO(silent skip 防止が目的、disappearance 逆方向)
- Cache impact: NO
- Mail volume impact: YES(reduction 方向、silently 消えていた preflight skip を user-visible 化、282 flag ON 後に新 mail 経路出現)

User reply format: 「GO」/「HOLD」/「REJECT」のみ
```

---

## 6. 関連

- `docs/ops/POLICY.md` §7(293 → 282 順序、逆順禁止)
- `docs/ops/POLICY.md` §6(silent skip P0、必ず Acceptance Pack 経由)
- `docs/ops/POLICY.md` §18(Acceptance Pack 18 項目)
- `docs/ops/OPS_BOARD.yaml` `future_user_go.293-COST-deploy`(本 ticket、本 draft で前段固める)
- `docs/handoff/codex_responses/2026-05-01_codex_b_storm_permanent_fix.md`(298 Option B 設計、parallel pattern 参考)

---

## 7. next action

1. **本日**: 本 draft で設計確定、impl 着手しない、commit は 298-Phase3 close 後にまとめて 1 commit
2. **明日以降**: 17:00 production_health_observe pass + 298 24h 安定確認 → 293 impl 便を Codex に fire(Acceptance Pack 経由 user GO 後)
3. **再来日以降**: 293 impl + test + commit + push 完了 → 293 deploy + flag ON 別 Pack で user GO → 282-COST flag ON への前提解除
