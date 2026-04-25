# 102 ticket index and priority board

## meta

- owner: Claude Code
- type: index / priority board
- status: READY(2026-04-26 採番方針 lock)
- created: 2026-04-26

## 採番方針

- **既存数字 ticket(〜101)の続き**で連番(102, 103, 104, ...)を振る
- 新しい `YOSHI-001` 体系は作らない
- 過去の alias 名(PUB-002-E / PUB-004-D / SPEECH-001 / PUB-005-A2 等)は **alias** として残し、正式チケット名 = 数字先頭(`<number>-<topic>.md`)へ統一
- **既存 ticket doc はリネームしない**(履歴と既存 cross-ref 維持)
- 102 以降の新規 doc は数字先頭で命名
- 古い alias は次の集中整理タイミングで `<number>-...md` に redirect or merge 候補

## 現行 active ticket 一覧(2026-04-26 22:00 JST 時点、8 列 + 状態反映)

| number | alias | title | priority | status | owner | next_action | blocked_by | user_action_required | repo_state | commit_state |
|---|---|---|---|---|---|---|---|---|---|---|
| **102** | - | ticket index and priority board | meta | READY | Claude Code | doc commit便で 102/103/PUB-004-D 一括 sync | - | なし | doc/102-...md(本 doc、untracked)| **uncommitted** |
| **103** | - | publish-notice cron health check (dry-run) | P1 | READY(doc 起票完了)| Claude Code(doc)/ Codex(impl)| 104 close 後の slot で Codex impl fire、4 軸切り分け、実メール送信なし | 104 close(slot 開放)| なし | doc/103-...md(untracked)、src 未実装 | **uncommitted** |
| **104** | PUB-002-E | lineup-hochi-only duplicate suppression | **P0.5** | **IN-FLIGHT** | Codex B `bo6ivxsje` | 完了通知 → §31-A → Claude push | - | なし(autonomous) | 実装中: src/lineup_source_priority.py + tools + tests + PUB-004-A hook | **in flight** |
| **105** | PUB-004-D | all-eligible-draft-backlog publish ramp | **P0.5** | READY(orchestration、新規 code なし) | Claude Code | 104 close 後、PUB-004-A で全 draft 棚卸し dry-run、件数表 user 報告 | 104(lineup 重複抑制) | dry-run 件数表受領後に **`live publish ramp go` 1 ワード判断** | doc/PUB-004-D-...md(untracked、`PUB-004-D` alias)| **uncommitted**(105 番号で 102 から参照) |
| **106** | SPEECH-001 | speech-seed-intake dry-run | P1 | **CLOSED** | Codex B 完了 | 既存 comment_notice / fixed lane / PUB-004 への配線(別 ticket) | - | なし | 実装済: src/speech_seed_intake.py + tools + tests | **`4f4b70d`**(push 済) |
| **107** | PUB-005-A2 | x-post template-candidate dry-run | P1 | **CLOSED** | Codex A 完了 | live X 投稿は PUB-005-B 以降 user 明示 trigger まで保留 | - | なし | 実装済: src/x_post_template_candidates.py + tools + tests | **`34a1bfa`**(push 済) |

### 次に動かすべき 1 本

**A: doc commit便 fire(102 + 103 + PUB-004-D 3 doc 一括 sync、Codex commit only / Claude push)**

理由:
- 3 doc untracked → chat 切れ lost リスク解消
- A slot 即 fire 可、disjoint(B = 104 src 改修、本便 = doc only)
- cap reset 維持(現 0 ahead)、軽量

### 続く chain

1. doc commit便完了 + Claude push → A slot 開放
2. **B: 103 publish-notice cron health check 実装 fire**(Codex A、scope: src/publish_notice_cron_health.py + tools + tests)
3. 104(B 並走中)完了 → push → B slot 開放
4. **105 dry-run 実行**(Claude autonomous、PUB-004-A で全 draft 棚卸し、件数表 user 報告)
5. user `live publish ramp go` 1 ワード → 105 live ramp(burst 3 / daily 10 cap 内)

## 関連 ticket(別 priority、参考)

| number | alias | title | priority | status |
|---|---|---|---|---|
| - | PUB-002 | 少量手動公開と記事品質改善レーン(親 runbook、完了済) | P0.5 / 完 | CLOSED(後継 PUB-004 / PUB-005)|
| - | PUB-002-A | publish candidate gate and article prose contract | meta(判定 contract) | READY |
| - | PUB-002-B/C/D | missing-source / subtype-unresolved / long-body 品質改善 | P2-P3 | QUEUED(PUB-004 安定後) |
| - | PUB-003 | explicit approval WP REST publish lane | meta(契約) | READY(単発 publish 用に保持) |
| - | PUB-004 | guarded-wordpress-publish-runner(parent) | P0.5 | A=`53561b6` / B=`f451f17` 着地済 |
| - | PUB-005 | x-sns-post-gate(parent) | P1 | doc-first、A2 進行中(=107) |
| - | HALLUC-LANE-001 | pre-publish fact-check lane 土台 | P1 | CLOSED(commit `96ba574`)|
| - | HALLUC-LANE-002 | LLM-based fact-check augmentation | P1 | doc-first(課金 = user judgment) |
| - | 088 | publish-notice real-send smoke and mail gate | P0.5 | CLOSED 候補(2026-04-25) |
| - | 093 | Codex Desktop automation tick recovery | P1 | OPEN(user op = app restart) |
| - | 095 | publish-notice cron activation | P0.5 | CLOSED(WSL fallback、`# 095-WSL-CRON-FALLBACK`) |
| - | 095-D | publish-notice cron live verification | P0.5 | **CLOSED**(2026-04-25 Phase 1-4 全 pass)|
| - | 095-E | WSL cron reboot resilience | P2 | OPEN(user op = PC reboot) |
| - | DOTENV-LOAD-088 | publish-notice runner load_dotenv 追加 | P1 | CLOSED(commit `c974fda`) |
| - | CI-001 | requirements-dev pytest 追加 | P2 | CLOSED(commit `1c6ac9c`) |

## 次に動かすべき 1 本

**104(PUB-002-E)完了通知 → §31-A + Claude push → 105(PUB-004-D)dry-run 実行**

理由:
- 104 = 全 draft backlog 公開(105)の前提、lineup 重複抑制
- 105 dry-run = 全 draft 棚卸し件数表で user に「どれだけ publish 可能か」を可視化
- 105 live ramp = burst 3 / daily 10 cap 内、user の `live publish ramp go` 1 ワード判断後

## 採番運用ルール(継続)

- 新規 ticket 起票時は本 board(102 doc)を更新、`<number>-<topic>.md` で命名
- alias は既存記号を維持(PUB-002-E 等)、移行は段階的
- 番号は **連番**(欠番禁止)、102 → 103 → 104 ...
- priority: P0.5(主線)/ P1(品質強化)/ P2(後続改善)/ P3(reserve)
- status: PROPOSED → READY → IN-FLIGHT → CLOSED / OPEN(user op 待ち)/ BLOCKED

## 不可触

- 既存 ticket doc のリネーム / 削除
- alias 廃止(段階的移行のみ)
- code 変更
- env / secret / logs / front
- automation.toml / scheduler / .env / Cloud Run env
- baseballwordpress repo
- `git add -A`

## 関連 file

- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`
- `doc/PUB-004-guarded-auto-publish-runner.md`
- `doc/PUB-004-D-all-eligible-draft-backlog-publish-ramp.md`(105 alias)
- `doc/PUB-005-x-post-gate.md`
- `doc/HALLUC-LANE-002-llm-based-fact-check-augmentation.md`
