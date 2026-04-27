# assignments — 現場担当と次アクション

最終更新: 2026-04-27 JST(assignments 圧縮 + 226 doc 起票)

## 最初に読む

- `doc/active/OPERATING_LOCK.md`
- `doc/README.md`(正本、詳細は全部こちら)
- `doc/active/assignments.md`(本 file、サマリ)

## 今の3本(これだけ見る)

| ticket | priority | status | 1 行要約 |
|---|---|---|---|
| **226 guarded publish unblock** | P0.5 | IN_FLIGHT(`bhnmw4tc7`) | 63809/63811 が `subtype_unresolved_no_resolution` で refused、safe case を Yellow に降格 |
| **224 entity-role consistency** | P0.5 | IN_FLIGHT(`bif6lgn6p` 着地済 `84ed848`) | `〜投手となって` 等不自然構文 detector + safe rewrite + Yellow flag |
| **225 / MKT-008 X candidate quality** | P0.5 | REOPENED(本体 `873fcf0`、225-A safety fix `bss84x1u1` 進行中) | x_post_ready=false で manual_x_post_candidates 本文非表示 + X intent link 抑止(post_id 63323 相当) |

## 役割一覧

| 略号 | 役割 | 変更OK | 原則NG |
|---|---|---|---|
| **Claude** | 現場管理 / accept / push / 危険境界判断 | doc整理、Codex便accept、git push、read-only監査 | src/tests直接編集、secret表示、live境界越え |
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
| **226 publish gate unblock** | IN_FLIGHT(`bhnmw4tc7`) | Codex B | subtype_unresolved + cleanup_failed_post_condition の safe case を Yellow 降格 |
| **224 entity-role consistency** | 完了済(`84ed848`)、deploy 待ち | Codex B | guarded-publish rebuild に同梱 |
| **217 wp publish all-mode hotfix** | REVIEW_NEEDED(`b03890c`)、deploy 待ち | Authenticated executor | guarded-publish + publish-notice rebuild、63795 再判定 |
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
| **MKT-008 / 225 X candidate quality** | REOPENED(本体着地、225-A safety fix 進行中) | Codex B | x_post_ready=false で本文表示抑止、修正完了後 publish-notice rebuild |
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

## 5. 完了大物(圧縮)

| 範囲 | 内容 |
|---|---|
| **156-161 / 165-167 / 168-173 / 177-178** | GCP 移行 第 1 波(042/PUB-004-C/publish-notice deploy + Scheduler + Secret/GCS + alert + repair ledger + Codex shadow + wp_write enable) |
| **183-186 / 192-194** | publish gate 緩和、ledger integration、entrypoint exclude-today 除去、scan_limit narrow、doc hygiene、scheduler 5min |
| **187-189 / 195-201** | scheduler URI/IAM fix、X candidates 拡張、article footer share corner、ingestion realtime、scanner subtype fallback、readiness flaky |
| **202-211 / 213-216** | operating policy clarify、ratify、accident restore、doc reconciliation、worktree cleanup、plumbing fallback protocol |
| **217-225** | publish gate hotfix(63795 unblock)、ingestion filter 緩和、send result persistence、4 段階 audit、source coverage、source_trust 拡張、editor whitelist sync、marketing board split、auto_post category 止血、件名分類、Gmail triage、X intent link、entity-role consistency、X candidate quality |

## fire rule(autonomous lock、要約)

- READY/IN_FLIGHT を Claude が即 fire 可と判断したら user 確認なしで Codex 投げる
- live publish / WP / X / SNS / scheduler / `.env` / secret / scope 拡張は user 判断
- live GCP mutation は authenticated executor、Codex auth fail は `READY_FOR_AUTH_EXECUTOR`
- デグレなし lock:全 prompt に baseline 数値 + 維持 contract、accept で 5 点追認
- status 変更時は ticket doc 移動 + README `doc_path` + assignments 更新を同/直後 commit
- `git add -A` 禁止、明示 path のみ stage
- 216 protocol 遵守(plumbing fallback、staged D/A 混入 prevention、attach 前 verify)
