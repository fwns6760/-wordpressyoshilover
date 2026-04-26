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
| **PUB-004-D / 105** | P0 | IN_FLIGHT | Claude | 翌 JST 0:00 cap reset 後 ramp 再開(本日 66 件 publish 完了) |
| **135** freshness gate | P0 | CLOSED 済 → REVIEW | Claude / B | 142 で freshness 降格済、今後 hard_stop に戻すか判断保留 |
| **123** readiness guard | P1 | READY | Claude or A | 130 land 後 read-only 検査(105 ramp 安定性) |
| **124** cleanup apply | P1 | READY | Codex A | 130 land 後、site_component cleanup を 8 publish 済記事に live apply |
| **PUB-002-A** | reference | active | (parent runbook) | 130 evaluator base、現役参照 |

### 止まってる(waiting)

| ticket | priority | status | 待ち | 担当 |
|---|---|---|---|---|
| **128** SNS auto-publish | P1 | PARKED | 130 安定 + 127 連携 | Codex A 後で |
| **120 / 121 / 122** X chain | P1 | BLOCKED_USER | X live unlock(user) | User → A/B |
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
