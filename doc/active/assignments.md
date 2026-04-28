# assignments — 現場担当と次アクション

最終更新: 2026-04-28 JST(224 / 226 / 242-E CLOSED + doc/done move 反映 + image rebuild `c328772` 反映済 + Codex C/M 廃止 + 「今の3本」絞り込み)

## 最初に読む

- `doc/active/OPERATING_LOCK.md`
- `doc/README.md`(正本、詳細は全部こちら)
- `doc/active/assignments.md`(本 file、サマリ)

## 今の3本(これだけ見る)

| ticket | priority | status | 1 行要約 |
|---|---|---|---|
| **fetcher canary traffic switch** | P0.5 | READY_FOR_AUTH_EXECUTOR | 235/236-A の live 化のため `yoshilover-fetcher-00177-hip` (c328772、tag `live-update-canary`、0% traffic) を 100% へ切替が必要、env / Scheduler / Secret 不変、user 判断境界 |
| **63475 / 63470 手動 publish 判断** | P0.5 | BLOCKED_USER | 242-E live で hard_stop 解除確認済、本文も家族死(祖父)文脈で正常記事、user 個別 publish 判断待ち |
| **63844 / 242-B 起票候補** | P1 | READY | 巨人記事内に他球団投手(則本=楽天)が混入する entity-role mismatch 検出 narrow fix。spec 起票 + Codex B fire は別 commit、今夜は record のみ |

## 役割一覧

| 略号 | 役割 | 変更OK | 原則NG |
|---|---|---|---|
| **Claude** | 現場管理 / accept / push / 危険境界判断 | doc整理、Codex便accept、git push、read-only監査、auth executor(WP REST GET/PATCH、gcloud read-only/build/run job-or-service update、smoke) | src/tests直接編集、secret表示、live境界越え、git commit |
| **Codex A** | ops / GCP / WP / mail / publish runner / build / Cloud Run / fetcher / scheduler infra 開発 | WP REST、publish runner、mail、cron、persistence、build context (Dockerfile / cloudbuild yaml / .dockerignore) | X live post、secret表示、front dirty、Codex B同時編集の品質系 |
| **Codex B** | 品質 / evaluator / validator / SNS / X gate / mail本文系開発 | evaluator/validator/audit/quality/source/title/sns/x_post 系 + tests + spec doc | live変更、WP/X live、front dirty、Codex A同時編集の ops |
| **Codex-GCP** | Cloud Run / Scheduler 上の自動実行レーン | 設定済み Job/Scheduler 定期実行、許可済み WP write、SNS/SEO 監視、X dry-run | repo編集、git、secret、未許可 scope 拡張 |
| **Authenticated executor** | Claude shell / user shell / 将来 deploy executor | Cloud Build、Cloud Run update、Scheduler、IAM/Secret/env live | secret露出、未承認 scope、repo 未準備 |
| **User** | 最終判断 | X live unlock、secret/env/scheduler/scope拡張、重要公開判断、live mutation (traffic/Cloud Run update/WP publish 重要分) | - |

(Codex C / Codex-M は廃止、本日以降使わない)

## executor boundary(要約)

- Codex は repo 実装 / tests / Docker / Cloud Build config / runbook / read-only verify
- live mutation(Cloud Build、Cloud Run、Scheduler、IAM、Secret、env、traffic switch)は authenticated executor、ただし実際の実行は user 判断境界
- `READY_FOR_AUTH_EXECUTOR` = repo 完了 + auth shell 待ち
- `BLOCKED_USER` = user 個別判断待ち

## 1. 今すぐ動かす(P0 / P0.5)

| ticket | status | 担当 | 次 action |
|---|---|---|---|
| **fetcher canary traffic switch** | READY_FOR_AUTH_EXECUTOR | Authenticated executor / User | `yoshilover-fetcher-00177-hip` (c328772) に 100% traffic 切替、env 不変、235/236-A live 化 |
| **63475 / 63470 手動 publish 判断** | BLOCKED_USER | User → Claude (auth executor PATCH) | 242-E live で hard_stop 解除済、user が「publish / draft 維持 / 削除」を 1 ワード判断 |
| **63844 / 242-B 起票候補** | READY(spec 未起票) | Claude (spec) / Codex B (impl) | 別 commit で 242-B spec doc 起票 → Codex B narrow fix fire 候補(entity-role mismatch 検出)|
| **draft-body-editor live (232 + 229-B + 229-A)** | live(`c328772` で反映、cron 動作中) | Codex-GCP + Claude 監視 | 次 cron tick 以降の no_op_skip / content_hash_skip / cooldown 系 log 観察、24h Gemini cost diff 確認 |
| **guarded-publish live (217 / 224 / 226 / 242-A / 242-D / 242-D2 / 242-E)** | live(`25f176b` + `c328772` で反映、cron 動作中) | Codex-GCP + Claude 監視 | 通常 cron 動作、必要に応じ guarded-publish history で boundary 観察 |
| **publish-notice live (241 Reply-To omit / MKT-001 mail classification)** | live(`25f176b` deploy 済) | Codex-GCP + Claude 監視 | mail 通知正常、Reply-To omit + PC/mobile 通知発火確認済 |
| **105 / PUB-004-D auto publish** | AUTO 5min cron | Codex-GCP + Claude 監視 | RSS新着 → 5-15 分内 publish、daily cap 100 |
| **042 draft-body-editor base lane** | GCP 本線 | Codex-GCP + Claude 監視 | repair + WP write + 品質/メール系実行 |
| **155 GCP migration master** | IN_FLIGHT | Claude | 主要移行完了、残 162/163 と X live 系 |
| **154 publish-policy** | reference | Claude | 現行公開方針参照元 |
| **README**(旧 102) | 正本 | Claude | dispatch board 維持 |

## 2. 次に動かす(P1)

| ticket | status | 担当 | 次 action |
|---|---|---|---|
| **235 pre-Gemini duplicate news guard** | landed(`a162552`)、image rebuild 済(`c328772`)、fetcher canary 0% traffic で live blocker | Codex-GCP / Claude | fetcher canary traffic 100% 切替後 live 観察 |
| **236-A subtype rule-based generation** | landed(`952713b`)、image rebuild 済(`c328772`)、fetcher canary 0% traffic で live blocker | Codex-GCP / Claude | 同上 |
| **232 no-new-content no-LLM guard** | landed(`7d86cc2`)、image rebuild 済(`c328772`、draft-body-editor live) | Codex-GCP / Claude | 次 cron tick 以降 no_op_skip log 観察 |
| **229-B content_hash dedupe + refused cooldown** | landed(`6bcb286`)、image rebuild 済(`c328772`、draft-body-editor live) | Codex-GCP / Claude | 24h cooldown skip log 観察 |
| **229-A Gemini cost ledger** | landed(`25b5209`)、image rebuild 済(`c328772`、draft-body-editor live) | Codex-GCP / Claude | 24h ledger 観察 |
| **229-C prompt input compression** | 未実装 | Claude (spec) / Codex B (impl) | 235/236-A live 後の cost 観察結果次第で起票・fire 判断 |
| **238 night-draft-only mode** | doc 設計済(`4e6a24a`) | Claude / Codex A | 238-impl-1 (runner JST gate) から着手 |
| **179 repair learning log Firestore + GCS** | READY / 即 fire 可 | Codex B → Codex-GCP | FirestoreLedgerWriter + ArtifactUploader 実装 |
| **180 SNS topic intake lane separation** | READY | Claude / Codex B → Codex-GCP | SNS 入口と X 出口の境界明文化 |
| **205 GCP runtime drift audit** | READY | Codex A / Claude | image / Scheduler / 最新 execution / mail / GCS history drift 監査 |
| **210a-d primary source expansion** | READY | Codex B | 210a 完了、210c → 210b → 210d 順 |
| **201 readiness_guard flaky** | READY | Codex B | real-now 依存解消(34ac0d8 で部分対応済、追加 narrow ticket) |
| **162 gemini_audit GCP migration** | QUEUED | Claude / A | 残 WSL cron は gemini_audit のみ、影響軽微 |
| **163 quality-monitor GCP migration** | QUEUED | Claude / A → Codex-GCP | quality monitor / quality mail を GCP 化 |
| **149 X Phase 2 manual live 1** | READY / user 境界 | Claude / A | user の X live unlock 後 |

## 3. マーケ運用

| ticket | status | 担当 | 次 action |
|---|---|---|---|
| **MKT-001 / 219 mail classification** | CLOSED / live | Codex B / Claude 完了 | 件名 prefix + metadata 反映済、marketing done へ移動済 |
| **MKT-007 / 223 Gmail triage ops** | CLOSED(doc 完了) | User | runbook は done へ移動済、Gmail label/filter 手動設定はuser運用 |
| **MKT-008 / 225 X candidate quality** | REOPENED(本体着地、225-A safety fix `bss84x1u1` 進行中) | Codex B | x_post_ready=false で本文表示抑止、修正完了後 publish-notice rebuild |
| **MKT-002 gmail label runbook** | PARKED(waiting) | Claude / Codex A | MKT-001/MKT-007 安定後 |
| **MKT-003 daily manual X workflow** | PARKED(waiting) | Claude / Codex A | MKT-001 後 |
| **MKT-004 X candidate quality scoring** | PARKED(waiting) | Claude / Codex A | MKT-001 出力例前提 |
| **MKT-005 weekly marketing digest** | PARKED(waiting) | Claude / Codex A | 日次運用安定後 |
| **MKT-006 manual X feedback ledger** | PARKED(waiting) | Claude / Codex A | 手動 X 投稿 feedback 蓄積方針 |

## 4. 待ち(user / 外部 / auth executor)

| ticket | status | 待ち | 担当 |
|---|---|---|---|
| **fetcher canary traffic switch** | READY_FOR_AUTH_EXECUTOR | user 判断 + traffic 切替実行 | User → Claude (auth executor) |
| **63475 / 63470 (家族死 false positive)** | BLOCKED_USER(draft 隔離中、242-E live で hard_stop 解除確認済) | user 個別 publish 判断 | User → Claude (auth executor PATCH) |
| **63844 (則本 hallucination)** | draft 隔離中、242-B 起票待ち | 242-B(他球団選手 entity-role mismatch detector)実装後、本文修正 or 削除判断 | User → Codex B |
| **174 x-api-cloud-run-live-smoke** | BLOCKED_USER | 149 X live unlock | User → A |
| **197 195 live deploy** | READY_FOR_AUTH_EXECUTOR | fresh zip / default-off canary / WP 反映 / enable / rollback | Authenticated executor |
| **175 x-controlled-autopost-cloud-rollout** | BLOCKED | 174 smoke 成功 | Claude / A |
| **128 SNS auto-publish** | PARKED | 180 完了後 | Codex A |
| **151 X Phase 4 cap3 ramp** | PARKED | 150 + 7 日 stable | Claude / A |
| **152 X 全カテゴリ拡張** | PARKED | 147 phase 5 stable | Future |
| **113 / HALLUC-LANE-002** | PARKED | Gemini live cost 境界 | User go 待ち |
| **095-E WSL cron reboot** | BLOCKED_USER | PC reboot 時 | User |
| **PUB-005 X gate parent** | PARKED | X live unlock | User → A |

## 5. 完了大物(圧縮)

| 範囲 | 内容 |
|---|---|
| **156-161 / 165-167 / 168-173 / 177-178** | GCP 移行 第 1 波(042/PUB-004-C/publish-notice deploy + Scheduler + Secret/GCS + alert + repair ledger + Codex shadow + wp_write enable) |
| **183-186 / 192-194** | publish gate 緩和、ledger integration、entrypoint exclude-today 除去、scan_limit narrow、doc hygiene、scheduler 5min |
| **187-189 / 195-201** | scheduler URI/IAM fix、X candidates 拡張、article footer share corner、ingestion realtime、scanner subtype fallback、readiness flaky |
| **202-211 / 213-216** | operating policy clarify、ratify、accident restore、doc reconciliation、worktree cleanup、plumbing fallback protocol |
| **217-225** | publish gate hotfix(63795 unblock)、ingestion filter 緩和、send result persistence、4 段階 audit、source coverage、source_trust 拡張、editor whitelist sync、marketing board split、auto_post category 止血、件名分類、Gmail triage、X intent link、entity-role consistency、X candidate quality |
| **241 mail-header reply-to self-recipient** | CLOSED 2026-04-28(`894db98`、image rebuild `25f176b` で live 反映、smoke v5 + PC/mobile 通知 yes/yes 確認) |
| **242 incident** | doc `21897c0`、incident 全体記録 |
| **242-A medical_roster narrow** | CLOSED 2026-04-28(`bd5c442`、farm/farm_lineup/lineup subtype 限定 escalate 抑止 + 5 fixture、image rebuild `25f176b` で live) |
| **242-D placeholder body blocker** | CLOSED 2026-04-28(`a224add`、63845 type placeholder body publish blocker + 6 fixture、image rebuild `25f176b` で live) |
| **242-D2 farm_result classifier alignment** | CLOSED 2026-04-28(`25f176b`、cheap classifier + scoped lineup exclusion + review hold + 11 fixture、image rebuild で live、sample 5 件 verify で narrow 設計通り動作確認) |
| **242-E DEATH family-context narrow** | CLOSED 2026-04-28(`c328772`、family-context skip helper + 6 fixture、guarded-publish image rebuild `c328772` で live、dry-run + boundary fixture verify pass) |
| **224 entity-role consistency awkward rewrite** | CLOSED 2026-04-28(`84ed848`、awkward_role_phrasing detector + safe rewrite + Yellow flag、guarded-publish image rebuild `25f176b` で live) |
| **226 guarded-publish subtype_unresolved unblock** | CLOSED 2026-04-28(`357a53c`、subtype_unresolved + cleanup_failed_post_condition の safe case を Yellow 降格、guarded-publish image rebuild `25f176b` で live) |
| **fetcher build context fix** | landed 2026-04-28(`44fc20d`、`.dockerignore` `!config/` `!config/**` 追加、fetcher build 復旧、yoshilover-fetcher Service `c328772` deploy 済 = canary 0% traffic) |
| **draft-body-editor rebuild (Gemini cost lane 232 + 229-B + 229-A)** | live 2026-04-28(image `c328772`、Job update 完了) |

## fire rule(autonomous lock、要約)

- READY/IN_FLIGHT を Claude が即 fire 可と判断したら user 確認なしで Codex 投げる
- live publish / WP / X / SNS / scheduler / `.env` / secret / scope 拡張 / traffic switch は user 判断
- live GCP mutation は authenticated executor、Codex auth fail は `READY_FOR_AUTH_EXECUTOR`
- デグレなし lock:全 prompt に baseline 数値 + 維持 contract、accept で 5 点追認
- status 変更時は ticket doc 移動 + README `doc_path` + assignments 更新を同/直後 commit
- `git add -A` 禁止、明示 path のみ stage
- 216 protocol 遵守(plumbing fallback、staged D/A 混入 prevention、attach 前 verify)
- Claude commit 禁止(`feedback_claude_no_development_absolute.md` + `feedback_claude_commit_boundary_strict.md`、commit は Codex 専任)
- template_key 100% auto 分類禁止(`feedback_template_key_no_full_auto_classification.md`、confidence high のみ付与、曖昧は review/draft)
- hard_stop 緩和は narrow fix 強制(`feedback_hard_stop_narrow_fix_rule.md`、subtype/pattern 限定 + 4 fixture 必須)
- Codex C / Codex-M 廃止(2026-04-28)、ops / build / Cloud Run / fetcher / scheduler infra は Codex A、品質 / evaluator は Codex B
