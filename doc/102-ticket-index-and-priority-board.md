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

## 現行 active ticket 一覧(2026-04-26 23:30 JST 時点、dispatch board)

各 ticket = 1 row。下表で **priority / status / owner / lane / ready_for / next_action / blocked_by / user_action_required / write_scope / acceptance / repo_state / commit_state / next_prompt_path / last_commit** を確認。

### 102 ticket-index-and-priority-board

- **priority**: P0(meta dispatch board)
- **status**: READY(本 doc)
- **owner**: Claude Code
- **lane**: -(meta、Codex 不要)
- **ready_for**: 常時参照可
- **next_action**: doc commit便で 102/103/PUB-004-D + AGENTS/CLAUDE/README/current_focus 一括 sync
- **blocked_by**: -
- **user_action_required**: なし
- **write_scope**: doc/102-...md
- **acceptance**: 全 102-107 row が dispatch board 形式で記載 + Codex A/B pull rule 明文化
- **repo_state**: untracked(本セッション内更新中)
- **commit_state**: uncommitted
- **next_prompt_path**: -
- **last_commit**: -(初回 commit `4741eee` で 1 度 sync 済、以降 update が untracked)

### 103 publish-notice-cron-health-check (alias: -)

- **priority**: P0.5
- **status**: IN-FLIGHT(Codex A `b3m1kmcwy`、本セッション内 fire 済)
- **owner**: Codex A
- **lane**: A
- **ready_for**: -(in flight)
- **next_action**: 完了通知 → §31-A → Claude push
- **blocked_by**: -
- **user_action_required**: なし(autonomous)
- **write_scope**: src/publish_notice_cron_health.py + src/tools/run_publish_notice_cron_health_check.py + tests/test_publish_notice_cron_health.py
- **acceptance**: 4 軸切り分け(cron/publish/log/SMTP/history) + secret 値非表示 + dry-run only + tests pass
- **repo_state**: src 実装中、doc/103-...md は commit `4741eee` 済
- **commit_state**: in flight
- **next_prompt_path**: /tmp/codex_103_impl_prompt.txt
- **last_commit**: doc 部分 = `4741eee`(2026-04-26)

### 104 lineup-hochi-only-duplicate-suppression (alias: PUB-002-E)

- **priority**: P0.5
- **status**: **CLOSED**(commit `78f965d`、push 済、2026-04-26 07:07)
- **owner**: Codex B 完了
- **lane**: B
- **ready_for**: -
- **next_action**: 105 ramp 実行で本 ticket の効果(lineup 重複抑制)を live verify
- **blocked_by**: -
- **user_action_required**: なし
- **write_scope**: src/lineup_source_priority.py + tools + tests + src/guarded_publish_evaluator.py hook + tests/test_guarded_publish_evaluator.py
- **acceptance**: 報知ソース最優先 / game_id 単位 1 本 / 報知なし lineup_notice 除外 / prefix violation 検出 / 既存 17 tests + 新 9 tests pass
- **repo_state**: pushed
- **commit_state**: `78f965d`
- **next_prompt_path**: -
- **last_commit**: `78f965d`(2026-04-26)

### 105 all-eligible-draft-backlog-publish-ramp (alias: PUB-004-D)

- **priority**: P0.5
- **status**: READY(orchestration、新規 code なし)
- **owner**: Claude Code(autonomous orchestration)
- **lane**: -(Codex 不要、PUB-004-A + B 流用)
- **ready_for**: 即実行可(104 close 済)
- **next_action**: PUB-004-A で全 draft 棚卸し dry-run、件数表を user に報告
- **blocked_by**: なし(104 close 済)
- **user_action_required**: dry-run 件数表受領後に **`live publish ramp go` 1 ワード判断**
- **write_scope**: なし(read-only smoke + autonomous report)
- **acceptance**: 全 draft 件数表(Green / Yellow / Red / cleanup 件数) + user 1 ワード判断後の live ramp 開始(burst 3 / daily 10 cap 内)
- **repo_state**: doc/PUB-004-D-...md = commit `4741eee` 済
- **commit_state**: doc only `4741eee`(execution は 102 board が指揮)
- **next_prompt_path**: -(直接 `python3 -m src.tools.run_guarded_publish_evaluator --window-hours 999999 --max-pool 500 --format json`)
- **last_commit**: doc `4741eee`(2026-04-26)

### 106 speech-seed-intake-dry-run (alias: SPEECH-001)

- **priority**: P1
- **status**: **CLOSED**(commit `4f4b70d`、push 済、2026-04-26 06:52)
- **owner**: Codex B 完了
- **lane**: B(完了)
- **ready_for**: -
- **next_action**: 既存 comment_notice / fixed lane / PUB-004 への配線(別 ticket、本 ticket scope 外)
- **blocked_by**: -
- **user_action_required**: なし
- **write_scope**: src/speech_seed_intake.py + src/tools/run_speech_seed_intake_dry_run.py + tests/test_speech_seed_intake.py
- **acceptance**: comment_candidate / deferred_pickup / duplicate_like / reject 判定 + 8 tests pass + 既存 comment 系 29 tests pass
- **repo_state**: pushed
- **commit_state**: `4f4b70d`
- **next_prompt_path**: -
- **last_commit**: `4f4b70d`(2026-04-26)

### 107 x-post-template-candidate-dry-run (alias: PUB-005-A2)

- **priority**: P2
- **status**: **CLOSED**(commit `34a1bfa`、push 済、2026-04-26 06:58)
- **owner**: Codex A 完了
- **lane**: A(完了)
- **ready_for**: -
- **next_action**: live X 投稿は **PUB-005-B 以降 user 明示 trigger まで保留**(autonomous POST なし)
- **blocked_by**: -
- **user_action_required**: なし(live X = user judgment fixed、本 ticket scope 外)
- **write_scope**: src/x_post_template_candidates.py + src/tools/run_x_post_template_candidates_dry_run.py + tests/test_x_post_template_candidates.py
- **acceptance**: 4 template_type(quote_clip / fan_reaction_hook / program_memo / small_note)+ 280 chars + URL 含 + history dedup + 7 tests pass
- **repo_state**: pushed
- **commit_state**: `34a1bfa`
- **next_prompt_path**: -
- **last_commit**: `34a1bfa`(2026-04-26)

## Codex A / B pull rule(2026-04-26 lock)

### Codex A が空いた時

1. 102 board で `lane=A` かつ `status=READY` の最高 priority ticket を pull
2. 該当 ticket の `next_prompt_path` から prompt を読む
3. `--full-auto --skip-git-repo-check -C /home/fwns6/code/wordpressyoshilover` で fire
4. 完了通知 → Claude が §31-A 追認 → Claude push → 102 board 更新

### Codex B が空いた時

1. 102 board で `lane=B` かつ `status=READY` の最高 priority ticket を pull
2. なければ `lane=-`(任意 lane)で `status=READY` の bounded task(read-only docs / Article Safety / Quality / Tests / Docs)を pull
3. **Codex A と同 file を同時に触らない**(102 board の `write_scope` で衝突確認)
4. 持たない: front / .env / secret / Cloud Run env / `RUN_DRAFT_ONLY` / X 投稿
5. 同様に prompt 読む → fire → §31-A → push → board 更新

### 並走衝突防止

- 102 board の `write_scope` 列で disjoint かどうか確認
- `src/guarded_publish_evaluator.py` のような共通 hub を 2 lane が同時に触らない(直前 ticket land 待ち)
- `.git/index.lock` 衝突時は plumbing 3 段 fallback(prompt 標準装備)

## 採番 / alias 運用

- 102 以降は **数字連番**(`<number>-<topic>.md`)
- 既存 alias(PUB-002-E / PUB-004-D / SPEECH-001 / PUB-005-A2 等)は **維持**(既存 doc リネームしない)
- 新規 ticket = 102 board に 1 行追加 + `<number>-<topic>.md` 作成 + 既存 alias は cross-ref に書く

## 重要依存

- **105 の前に 104 close 必須**(✓ 達成、`78f965d`)
- 103 は 105 前に入れるのが望ましい(現 in flight)
- 106 は 105 後でよい(✓ 既に done、配線は別 ticket)
- 107 は外部拡散なので最後でよい(✓ done だが live POST は user 判断)
- **X live 投稿禁止**(PUB-005 lane で user 明示後のみ)
- **`RUN_DRAFT_ONLY=False` 禁止**
- **Cloud Run env 変更禁止**

## 次に動かすべき 1 本(2026-04-26 23:30 JST)

**105 dry-run 実行(Claude autonomous)= 全 draft 棚卸し件数表 → user 1 ワード判断**

理由:
- 104 close 済(lineup 重複抑制 land)= 105 前提達成
- 103(in flight)とは disjoint(105 = 既存 PUB-004-A + B 流用、新規 code なし)
- A/B 並走と無干渉で実行可(read-only smoke)
- user 報告後の live ramp 開始判断が今夜 / 明日朝の主線

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
