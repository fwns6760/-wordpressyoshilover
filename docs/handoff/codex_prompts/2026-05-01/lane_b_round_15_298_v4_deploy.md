# Lane C round 1 prompt: 298-Phase3 v4 deploy(Case F GCS pre-seed mode)

You are Codex (Lane C round 1, deploy lane). 298-Phase3 v4 deploy(user GO 受領済「ならやる」、本日中 deploy + storm 再発検出時 §14 自律 rollback).

Working directory: /home/fwns6/code/wordpressyoshilover
Project: baseballsite, Region: asia-northeast1, Job: publish-notice
Latest commit: HEAD(本日 push 済、image content = src + tests 等価 with d44594a + ffeba45)

[ticket]
298-Phase3 v4 deploy(USER_DECISION_REQUIRED user GO 受領済、Case F GCS pre-seed + flag ON、第二波防止)

参照(全 commit 着地済):
- v4 final READY pack: docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_final_ready_pack.md(fac5517、Case A 推奨)
- v4 robustness supplement: Lane B round 14 進行中(`bum1usgj7`、Case F GCS pre-seed 詳細)
- INCIDENT_LIBRARY: 4abe1d5(本日 13:35 storm 再発 経緯)
- 298 stability evidence pre: aa6a8eb

[goal - Case F GCS pre-seed mode、最 narrow]
1. **GCS pre-seed**:
   - guarded_publish_history.jsonl tail から hold_reason=backlog_only かつ MIN_AGE_DAYS=3 以上(post.date < now - 3d)の post_id を抽出
   - target post_id 範囲:5/1 朝 storm group(63003-63311)+ 直近 6h 追加 backlog post(scanner skip 経路)
   - 想定 ~99-110 post_id
   - 各 post_id を `publish_notice_old_candidate_once.json` 形式で build
   - gsutil cp で `gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json` upload(既存上書き or 新規作成)
2. **publish-notice job env apply**:
   - `gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --update-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`
   - image 不変(現状 `publish-notice:1016670`、impl `d44594a` 含む persistent ledger code 既 deploy 済)
3. **observe 1-2 trigger**(*/5、~10 min):
   - sent=0 維持(99 post_id permanent_dedup skip 確認)
   - errors=0
   - 289 post_gen_validate emit 不変
   - Team Shiny `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` 不変
   - silent skip 0
4. **storm 再発検出時 §14 自律 rollback**:
   - rolling 1h sent > 30 検出 → `gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` 自律実行
   - 本日 13:55 実績整合(§14 P0/P1 自律 hotfix)

[hard constraints]
- DO NOT image rebuild(現 image `:1016670` 維持)
- DO NOT 他 env 変更(MAIL_BRIDGE_FROM / 289 / Scheduler / live_update / Team Shiny 全部不変)
- DO NOT WP REST mutation
- DO NOT 他 job/service mutation(fetcher / guarded-publish / draft-body-editor 不可触)
- DO NOT install packages
- target post_id range は guarded_publish_history.jsonl tail から evidence-based 抽出(hardcoded 99 数値ではなく実 ledger 確認)
- pre-seed JSON format は scanner side の expected schema と整合(コード read で確認)
- gsutil cp 失敗時 stop + 報告

[completion report - 7 fields]
- pre_seeded_post_ids_count: <N>
- pre_seeded_range: <min_post_id>-<max_post_id>
- gcs_object_path: gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json
- env_applied: ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1 (yes/no)
- observe_trigger_1_sent: <N>
- observe_trigger_2_sent: <N>
- next_action_for_claude: "298-v4 deploy 完了、5/2 09:00 JST 第二波防止 verify は明日朝 log 確認(read-only)"

[dialogue rule]
- gsutil / gcloud auth fail → stop + Claude 報告(Claude 代行実行)
- pre-seed JSON schema 不明 → src/publish_notice_scanner.py + cloud_run_persistence.py read で確認
- 観察で異常検出(sent burst / errors / 289 減 / Team Shiny 変)→ 即 rollback + 報告
