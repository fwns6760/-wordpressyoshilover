# assignments — 現場担当と次アクション

最終更新: 2026-04-28 JST(241/242-D/242-D2 CLOSED + doc/done move反映 + 242-E narrow 起票 + image rebuild `25f176b` 反映済)

## 最初に読む

- `doc/active/OPERATING_LOCK.md`
- `doc/README.md`(正本、詳細は全部こちら)
- `doc/active/assignments.md`(本 file、サマリ)

## 今の3本(これだけ見る)

| ticket | priority | status | 1 行要約 |
|---|---|---|---|
| **242-E DEATH family-context** | P0.5 | READY | 祖父/祖母/おじいちゃん 等家族死を player-self death と区別、63475/63470 false positive を救う narrow fix |
| **226 guarded publish unblock** | P0.5 | IN_FLIGHT(`bhnmw4tc7` 着地済 `357a53c`) | 63809/63811 が `subtype_unresolved_no_resolution` で refused、safe case を Yellow に降格(doc-only close cleanup pending) |
| **224 entity-role consistency** | P0.5 | IN_FLIGHT(`bif6lgn6p` 着地済 `84ed848`) | `〜投手となって` 等不自然構文 detector + safe rewrite + Yellow flag(doc-only close cleanup pending) |

## 役割一覧

| 略号 | 役割 | 変更OK | 原則NG |
|---|---|---|---|
| **Claude** | 現場管理 / accept / push / 危険境界判断 | doc整理、Codex便accept、git push、read-only監査 | src/tests直接編集、secret表示、live境界越え、git commit |
| **Codex A** | ops / GCP / WP / mail / publish runner 開発 | WP REST、publish runner、mail、cron、persistence | X live post、secret表示、front dirty、Codex B同時編集の品質系 |
| **Codex B** | 品質 / evaluator / validator / SNS / X gate / mail本文系開発 | evaluator/validator/audit/quality/source/title/sns/x_post 系 + tests + spec doc | live変更、WP/X live、front dirty、Codex A同時編集の ops |
| **Codex-M** | 一時 manager / board hygiene / numbering / prompt prep | README、assignments、status sync、runbook整理 | src/tests、live mutation、secret |
| **Codex-GCP** | Cloud Run / Scheduler 上の自動実行レーン | 設定済み Job/Scheduler 定期実行、許可済み WP write、SNS/SEO 監視、X dry-run | repo編集、git、secret、未許可 scope 拡張 |
| **Authenticated executor** | Claude shell / user shell / 将来 deploy executor | Cloud Build、Cloud Run update、Scheduler、IAM/Secret/env live | secret露出、未承認 scope、repo 未準備 |
| **User** | 最終判断 | X live unlock、secret/env/scheduler/scope拡張、重要公開判断 | - |

## executor boundary(要約)

- Codex は repo 実装 / tests / Docker / Cloud Build config / runbook / read-only verify
- live mutation(Cloud Build、Cloud Run、Scheduler、IAM、Secret、env)は authenticated executor
- `READY_FOR_AUTH_EXECUTOR` = repo 完了 + auth shell 待ち

## 1. 今すぐ動かす(P0 / P0.5)

| ticket | status | 担当 | 次 action |
|---|---|---|---|
| **242-E DEATH family-context narrow** | READY | Codex B → Claude/auth executor | `DEATH_OR_GRAVE_INCIDENT_RE` 発火直前に family-context 共起 skip を追加、63475/63470 type 救う、player-self death/grave injury 真陽性は維持 |
| **63475 / 63470 手動 publish 判断** | pending(本文確認済、family death 文脈、placeholder なし) | User → Claude | 242-E live 反映 or user 直接判断後に手動 publish |
| **226 doc-only close cleanup** | pending(commit 済、doc IN_FLIGHT のまま) | Codex C / Codex-M | 226 status を CLOSED へ更新 + doc/done/2026-04 へ移動 |
| **224 doc-only close cleanup** | pending(commit 済、doc IN_FLIGHT のまま) | Codex C / Codex-M | 224 status を CLOSED へ更新 + doc/done/2026-04 へ移動 |
| **217 wp publish all-mode hotfix** | live 反映済(`b03890c` → image rebuild `25f176b` で deploy) | - | 完了扱い、follow-up は別 ticket |
| **219 / MKT-001 mail classification** | live(`5246da9` deploy 済) | Codex B / Claude | 件名 prefix 6 class + 本文 metadata 動作中 |
| **222 X intent link** | live(`5246da9` deploy 済) | Codex B / Claude | スマホ 1 タップ X compose 動作中 |
| **223 / MKT-007 Gmail triage ops** | doc 完了(`5246da9`) | User | Gmail label/filter 手動設定 |
| **105 / PUB-004-D auto publish** | AUTO 5min cron | Codex-GCP + Claude 監視 | RSS新着 → 5-15 分内 publish、daily cap 100 |
| **042 draft-body-editor** | GCP 本線 | Codex-GCP + Claude 監視 | repair + WP write + 品質/メール系実行 |
| **155 GCP migration master** | IN_FLIGHT | Claude | 主要移行完了、残 162/163 と X live 系 |
| **154 publish-policy** | reference | Claude | 現行公開方針参照元 |
| **README**(旧 102) | 正本 | Claude | dispatch board 維持 |

## 2. 次に動かす(P1)

| ticket | status | 担当 | 次 action |
|---|---|---|---|
| **235 pre-Gemini duplicate news guard** | landed(`a162552`)、image rebuild 待ち | Codex-GCP / Claude | draft-body-editor / fetcher rebuild 後 live 観察 |
| **232 no-new-content no-LLM guard** | landed(`7d86cc2`)、image rebuild 待ち | Codex-GCP / Claude | draft-body-editor rebuild 後 live 観察 |
| **236-A subtype rule-based generation** | landed(`952713b`)、image rebuild 待ち | Codex-GCP / Claude | draft-body-editor rebuild 後 live 観察 |
| **229-A Gemini cost ledger** | landed(`25b5209`)、image rebuild 待ち | Codex-GCP / Claude | rss_fetcher / draft-body-editor rebuild 後 24h ledger 観察 |
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
| **MKT-001 / 219 mail classification** | live | Codex B / Claude | 件名 prefix + metadata 反映済 |
| **MKT-007 / 223 Gmail triage ops** | doc 完了 | User | Gmail label/filter 手動設定 |
| **MKT-008 / 225 X candidate quality** | REOPENED(本体着地、225-A safety fix `bss84x1u1` 進行中) | Codex B | x_post_ready=false で本文表示抑止、修正完了後 publish-notice rebuild |
| **MKT-002 gmail label runbook** | PARKED | Claude / Codex-M | MKT-001/MKT-007 安定後 |
| **MKT-003 daily manual X workflow** | PARKED | Claude / Codex-M | MKT-001 後 |
| **MKT-004 X candidate quality scoring** | PARKED | Claude / Codex-M | MKT-001 出力例前提 |
| **MKT-005 weekly marketing digest** | PARKED | Claude / Codex-M | 日次運用安定後 |
| **MKT-006 manual X feedback ledger** | PARKED | Claude / Codex-M | 手動 X 投稿 feedback 蓄積方針 |

## 4. 待ち(user / 外部 / auth executor)

| ticket | status | 待ち | 担当 |
|---|---|---|---|
| **174 x-api-cloud-run-live-smoke** | BLOCKED_USER | 149 X live unlock | User → A |
| **197 195 live deploy** | READY_FOR_AUTH_EXECUTOR | fresh zip / default-off canary / WP 反映 / enable / rollback | Authenticated executor |
| **175 x-controlled-autopost-cloud-rollout** | BLOCKED | 174 smoke 成功 | Claude / A |
| **128 SNS auto-publish** | PARKED | 180 完了後 | Codex A |
| **151 X Phase 4 cap3 ramp** | PARKED | 150 + 7 日 stable | Claude / A |
| **152 X 全カテゴリ拡張** | PARKED | 147 phase 5 stable | Future |
| **113 / HALLUC-LANE-002** | PARKED | Gemini live cost 境界 | User go 待ち |
| **095-E WSL cron reboot** | BLOCKED_USER | PC reboot 時 | User |
| **PUB-005 X gate parent** | PARKED | X live unlock | User → A |
| **63844 (則本 hallucination)** | draft 隔離中、242-B 起票待ち | User → Codex B | 242-B(他球団選手 entity-role mismatch detector)を実装後、本文修正 or 削除判断 |
| **63475 / 63470 (家族死 false positive)** | draft 隔離中、242-E 着地待ち | Codex B → User | 242-E narrow fix landed + image rebuild 後、live verify で hard_stop 解除確認 → 手動 publish 判断 |

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
| **242-A medical_roster narrow** | CLOSED 2026-04-28(`bd5c442`、farm/farm_lineup/lineup subtype 限定 escalate 抑止 + 5 fixture) |
| **242-D placeholder body blocker** | CLOSED 2026-04-28(`a224add`、63845 type placeholder body publish blocker + 6 fixture) |
| **242-D2 farm_result classifier alignment** | CLOSED 2026-04-28(`25f176b`、cheap classifier + scoped lineup exclusion + review hold + 11 fixture、image rebuild で live 反映、sample 5 件 verify で narrow 設計通り動作確認) |

## fire rule(autonomous lock、要約)

- READY/IN_FLIGHT を Claude が即 fire 可と判断したら user 確認なしで Codex 投げる
- live publish / WP / X / SNS / scheduler / `.env` / secret / scope 拡張は user 判断
- live GCP mutation は authenticated executor、Codex auth fail は `READY_FOR_AUTH_EXECUTOR`
- デグレなし lock:全 prompt に baseline 数値 + 維持 contract、accept で 5 点追認
- status 変更時は ticket doc 移動 + README `doc_path` + assignments 更新を同/直後 commit
- `git add -A` 禁止、明示 path のみ stage
- 216 protocol 遵守(plumbing fallback、staged D/A 混入 prevention、attach 前 verify)
- Claude commit 禁止(`feedback_claude_no_development_absolute.md` + `feedback_claude_commit_boundary_strict.md`、commit は Codex 専任)
- template_key 100% auto 分類禁止(`feedback_template_key_no_full_auto_classification.md`、confidence high のみ付与、曖昧は review/draft)
- hard_stop 緩和は narrow fix 強制(`feedback_hard_stop_narrow_fix_rule.md`、subtype/pattern 限定 + 4 fixture 必須)
