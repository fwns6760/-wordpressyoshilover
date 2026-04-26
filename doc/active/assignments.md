# assignments — ticket 担当者割り当て

最終更新: 2026-04-26 evening(13 ticket close + done/ 移動、158 in flight、159 user judgment 待ち)

## エージェント

| 略号 | 担当 | 主な仕事 | 不可触 |
|---|---|---|---|
| **Claude** | 現場管理 / 私 | 監査 / 起票 / Codex 便 accept(5 点追認)/ git push / doc 整理 / 105 ramp orchestration | src/tests 直接編集(緊急 narrow fix のみ) |
| **Codex A** | 実装本線 | ops / publish runner / mail / cron / WP REST / backup / history / commit(push なし) | git push / live publish / X / SNS / .env / scheduler |
| **Codex B** | 品質改善 + review | evaluator / validator / duplicate / source / subtype / tests / review / narrow fix | A と src 衝突避ける / git push / WP write / live publish |
| **User** | 最終判断 | publish 公開許可 / X live unlock / scheduler / .env 値 / scope 拡張 | - |

## 現在のチケット担当 (doc/active/ + doc/waiting/)

### 今動かす(active)

| ticket | priority | status | 担当 | 次 action |
|---|---|---|---|---|
| **README**(旧 102) | P0 | READY | Claude | board 維持 / dispatch 正本 |
| **PUB-004-D / 105** | P0 | **AUTO 5min cron**(PUB-004-C 化、2026-04-26 PM 起動)| Cron + Claude 監視 | RSS 新着 → 5-15 分内 auto publish、daily cap 100 件 / 24h |
| **124** cleanup apply | P1 | CLOSED `d25d02c` | A 完了 | live apply は Claude が手動 trigger(--live)|
| **135** freshness gate | P0 | **CLOSED `ef9e21d`**(impl + 3 hard_stop flag + 4 出力 field、pytest 1321 pass)| A 完了 | 速報掲示板 stale-publish 防止 gate 稼働 |
| **042** draft-body-editor WSL cron | P0 | **LIVE `2,12,22,32,42,52`**(2026-04-26 14:12 JST 起動、--max-posts 3、Gemini Flash 課金許容)| Cron + Claude 監視 | 376 backlog → ~1.5 日消化見込 |
| **123** readiness guard | P1 | CLOSED `77d4c8b` | A | history audit module land、105 ramp 監視に使用 |
| **147** X auto-post 親 ramp | P0.5 | READY | Claude | Phase 1-5 設計 / orchestration |
| **148** X Phase 1 dry-run mail | P0.5 | **CLOSED `cc9fe16`** | Codex A 完了 | 直近 publish 5 件文案 build + mail、X API zero、user 文案確認 待ち |
| **149** X Phase 2 manual live 1 | P0.5 | READY(148 done)| Claude / A | user 確認後 1 件 manual_post live |
| **150** X Phase 3 trigger ON cap 1 | P0.5 | BLOCKED(149) | Claude / A | 149 OK 後 env auto + daily 1、WP trigger 連動 |
| **PUB-002-A** | reference | done | (parent runbook supersede 154) | 130 evaluator base、移動済 `doc/done/2026-04/` |
| **154** publish-policy(現行)| reference | active | (current runbook) | 130 / 135 / 137 / 141-146 反映 |
| **155** GCP migration master | P0.5 | IN_FLIGHT(Phase 1a-1c / 165 / 168-173 done、158/159/162-164/174-175 残)| Claude / A | 158 in flight、その後 Phase 1e (159 WSL disable) は user 判断 |
| **156** Phase 1b 042 Cloud Run deploy | P0.5 | **CLOSED `c5adfa3`** → done/ 移動済 | A 完了 | WSL cron 042 並走中、disable は Phase 1e (159) |
| **157** Phase 1c Cloud Scheduler trigger 042 | P0.5 | **CLOSED `94f4784`** → done/ 移動済 | A 完了 | 17:32 JST tick auto execute pass、WSL 042 並走中 |
| **158** Phase 1d Secret Manager + GCS persistence | P0 | **IN_FLIGHT `bsyflz2d0`**(v2 再 fire、stop 条件訂正後) | A | env Secret 化 + cursor 永続化、WSL 042/095 disable 解除条件 |
| **161** Phase 3 publish-notice GCP migration | P0.5 | **CLOSED `7655d9f`** → done/ 移動済 | A 完了 | image push + Job create + Scheduler 15 * * * *、placeholder /data 残(158 で解消) |
| **165** Gemini + WP REST resilience | P0.5 | **CLOSED `3aa2cd1`** → done/ 移動済 | A 完了 | API 一時 outage で cron 無駄停止しない |
| **166** Cloud Run failure alert | P1 | BLOCKED(157 deploy 後 fire 可)| Claude / A | mail 通知配線、近日 fire |
| **167** GCP billing alert | P1 | **REWORK 必要**(JPY billing で USD budget reject)| Claude / A | $10/30/50 → ¥1500/4500/7500 で再 fire |
| **168** repair-provider-ledger v0 | P0 | **CLOSED `70009aa`** → done/ 移動済 | B 完了 | GCP migration foundation、schema v0 18 fields |
| **169** cloud-run-repair-job-skeleton | P0 | **CLOSED `85ae5a6`** → done/ 移動済 | B 完了 | --provider / --queue-path / --ledger-path 追加 |
| **170** repair-fallback-controller | P0 | **CLOSED `d56e298`** → done/ 移動済 | B 完了 | 6 failure class + Gemini fallback chain |
| **171** codex-cli-shadow-runner | P0 | **CLOSED `0981ee2`** → done/ 移動済 | B 完了 | call_codex 実装、shadow lane invariant(WP write 禁止)|
| **172** cloud-run-secret-auth-writeback | P0 | **CLOSED `cbe05b0`** → done/ 移動済 | B 完了 | SecretAuthManager + entrypoint script、auth.json 内容ログ禁止 |
| **173** x-post-cloud-queue-ledger v0 | P0.5 | **CLOSED `9ef3772`** → done/ 移動済 | A 完了 | X 投稿 lane foundation、unlock 時即動 |
| **159** Phase 1e WSL cron 042 disable | P1 | BLOCKED_USER(158 land + observation 1 日後) | User → Claude | 1 ワード go で WSL cron 行 disable |
| **162** Phase 4 gemini_audit GCP migration | P1 | QUEUED | Claude / A | 158 land 後 fire 可 |
| **163** Phase 5 quality-monitor / quality-gmail GCP migration | P1 | QUEUED | Claude / A | 162 land 後 fire 可 |
| **174** x-api-cloud-run-live-smoke | P0.5 | BLOCKED_USER(149 X live unlock 後)| User → A | live X API smoke 1 回 |
| **175** x-controlled-autopost-cloud-rollout | P0.5 | BLOCKED(174 後)| Claude / A | daily cap ramp |

### 止まってる(waiting)

| ticket | priority | status | 待ち | 担当 |
|---|---|---|---|---|
| **128** SNS auto-publish | P1 | PARKED | 130 安定 + 127 連携 | Codex A 後で |
| **151** X Phase 4 cap 3 ramp | P1 | PARKED | 150 + 7 日 stable | Claude / A |
| **152** X 全カテゴリ拡張 | P2 | PARKED | 147 phase 5 stable 後 | Future |
| **HALLUC-LANE-002 / 113** | P1 | PARKED | Gemini live cost 境界 | User go 待ち |
| **095-E** WSL cron reboot | P2 | BLOCKED_USER | PC reboot | User |
| **PUB-005** X gate parent | P1 | PARKED | X live unlock | User → A |

## fire rule(autonomous lock)

- Claude が READY/IN_FLIGHT を「即 fire 可」に判断したら、user 確認なしで Codex A/B に投げる
- live publish / WP write / X / SNS / scheduler / .env 関連は user 判断
- デグレなし lock: 全 prompt に baseline 数値 + 維持 contract embed、accept 時 5 点追認
- doc folder policy: status 変更時 git mv + doc_path 更新を同 commit で

## 本日完了便(2026-04-26、commit hash 順)

`0253b2a` 119 / `5bfe892` 126 / `269e1f4` 113 adapter / `2669faa` 127 / `147507c` 132 / `867d90f` 130 / `06a1315` 133 / `6979899` 131 / `35fb67c` 134 reorg / `573a169` 140 / `5f27058` 142 / `4f7963d` 141 / `5b01662` 145 / `afc7ba9` 125 AdSense slot / `c433b89` 146 SNS reject 拡張 / 加 105 ramp 66 件 publish 実行
