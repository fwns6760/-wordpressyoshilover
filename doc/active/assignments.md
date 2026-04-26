# assignments — ticket 担当者割り当て

最終更新: 2026-04-26

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
| **PUB-004-D / 105** | P0 | IN_FLIGHT | Claude | 翌 JST 0:00 cap reset 後 fresh-only ramp(135 復活で stale 自動公開停止)|
| **135** freshness gate | P0 | **REVERTED 142 → HARD_STOP 復活**(`e302187`)| Claude | 古い draft 自動公開停止、新着のみ ramp |
| **123** readiness guard | P1 | CLOSED `77d4c8b` | A | history audit module land、105 ramp 監視に使用 |
| **124** cleanup apply | P1 | READY | Codex A | 130 land 後、site_component cleanup を 8 publish 済記事に live apply |
| **147** X auto-post 親 ramp | P0.5 | READY | Claude | Phase 1-5 設計 / orchestration |
| **148** X Phase 1 dry-run mail | P0.5 | **CLOSED `cc9fe16`** | Codex A 完了 | 直近 publish 5 件文案 build + mail、X API zero、user 文案確認 待ち |
| **149** X Phase 2 manual live 1 | P0.5 | READY(148 done)| Claude / A | user 確認後 1 件 manual_post live |
| **150** X Phase 3 trigger ON cap 1 | P0.5 | BLOCKED(149) | Claude / A | 149 OK 後 env auto + daily 1、WP trigger 連動 |
| **PUB-002-A** | reference | active | (parent runbook) | 130 evaluator base、現役参照 |

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
