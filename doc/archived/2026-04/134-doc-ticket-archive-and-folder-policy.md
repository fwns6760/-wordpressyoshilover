# 134 doc-ticket-archive-and-folder-policy

## meta

- number: 134(132 は本日 baseline restore で使用済、133 は 127 schema fix で使用済のためリナンバー)
- alias: -
- owner: Claude Code(設計)/ Codex C(実装、git mv + board update)
- type: ops / doc reorg / folder policy 永続 rule
- status: READY(C lane で fire)
- priority: P0.5
- lane: C / Claude-managed doc 整理
- created: 2026-04-26

## 目的

doc/ 直下のチケットを **状態別フォルダ**へ整理し、CLOSED と未完了を一目で見分けられるようにする。
今後すべてのチケット運用で folder policy を遵守する **永続 rule** を確立。

## 急ぎ理由

- 102 board と doc/ 直下の見え方がズレている
- CLOSED が直下に残っていて把握しづらい(本日 11 件 CLOSED が混在)
- READY / REVIEW_NEEDED / BLOCKED が同じ階層 → A/B 振り分け遅い
- 今日のような大量起票日(13+ commit)で **二重 fire リスク**

## folder policy(永続 rule、本 ticket land 後 全便で遵守)

| status | 配置先 |
|---|---|
| READY / IN-FLIGHT | `doc/active/` |
| REVIEW_NEEDED | `doc/review/` |
| BLOCKED_USER / BLOCKED_EXTERNAL / PARKED | `doc/blocked/` |
| CLOSED | `doc/archived/YYYY-MM/` |

**例外(doc/ 直下に残す)**:
- `doc/102-ticket-index-and-priority-board.md`(board 本体)
- `doc/PUB-004-*` / `doc/PUB-005-*` / `doc/PUB-002-*` 親 runbook(複数 ticket から参照)
- `doc/001-099` 系 project foundation docs(reference、status 管理対象外)

## 運用タイミング(永続 rule)

| 段 | event | 必須作業 |
|---|---|---|
| 1 | チケット作成 | 102 board に row + `doc_path` 追加 / `doc/active/<n>-<topic>.md` に作成 |
| 2 | Codex 実装完了 | status=REVIEW_NEEDED / `doc/active/` → `doc/review/` git mv |
| 3 | Claude 確認完了 | status=CLOSED / `doc/review/` → `doc/archived/YYYY-MM/` git mv(同 commit)|
| 4 | user/外部待ち | status=BLOCKED_*/PARKED / `doc/active/` or `doc/review/` → `doc/blocked/` git mv |
| 5 | re-open | status を READY 等に戻す + `doc/active/` へ git mv |

**移動 commit 規律**:
- 移動だけの commit でも OK
- `git add -A` 禁止、対象 path を明示 stage
- 移動と同じ commit で 102 board の `doc_path` field 更新

## 本 ticket の初期 reorg 対象(2026-04-26 時点)

### archived/2026-04/(CLOSED、11 件)
- `103-publish-notice-cron-health-check.md`(`d6548ba`)
- `108-existing-published-site-component-cleanup-audit.md`(`84b91ce`)
- `109-missing-primary-source-blocker-reduction.md`(`94c6186`)
- `110-subtype-unresolved-blocker-reduction.md`(`99e9f1c`)
- `111-long-body-compression-or-exclusion.md`(`deea3bd`)
- `112-title-prefix-and-lineup-misclassification-fixtures.md`(`28b0dec`)
- `117-adsense-ad-unlock-policy-and-css-toggle.md`(`0555733`)
- `119-x-post-eligibility-evaluator.md`(`0253b2a`)
- `126-sns-topic-fire-intake-dry-run.md`(`5bfe892`)
- `127-sns-topic-source-recheck-and-draft-builder.md`(`2669faa`)
- `130-pub004-hard-stop-vs-repairable-before-publish.md`(`867d90f`)

### active/(READY / IN-FLIGHT、5 件)
- `123-pub004-auto-publish-readiness-and-regression-guard.md`
- `124-published-cleanup-apply-runner.md`
- `125-adsense-manual-ad-unit-embed.md`
- `128-sns-topic-auto-publish-through-pub004.md`
- `131-publish-notice-burst-summary-and-alerts.md`
- `134-doc-ticket-archive-and-folder-policy.md`(本 ticket)

### review/(REVIEW_NEEDED、1 件)
- `118-pub004-red-reason-decision-pack.md`

### blocked/(BLOCKED_*/PARKED、3 件)
- `120-x-post-autopost-queue-and-ledger.md`
- `121-x-post-live-helper-one-shot-smoke.md`
- `122-x-post-controlled-autopost-rollout.md`

### doc/ 直下に残す(変更なし)
- `102-ticket-index-and-priority-board.md`
- `001-099` 系 project foundation docs(全 約 90 件)
- `PUB-002-*` / `PUB-004-*` / `PUB-005-*` 親 runbook

### 削除(working tree dirty 残骸、HEAD では既 deleted)
- `130-pub004-hard-stop-vs-soft-cleanup-split.md`(DOC-SYNC-14 で削除済、working tree 残)
- `131-publish-notice-batch-suppress.md`(同上)

## やらないこと

- src 変更
- tests 変更
- live publish
- X / SNS POST
- `.env` / logs / build 触る
- `git add -A`
- 001-099 系 project foundation docs の移動
- 親 runbook の移動

## acceptance

1. 4 folder(`doc/active/`, `doc/review/`, `doc/blocked/`, `doc/archived/2026-04/`)が作成される
2. 11 CLOSED ticket が archived/2026-04/ に配置
3. 6 active(本 ticket 含)が active/ に配置
4. 1 REVIEW_NEEDED が review/ に配置
5. 3 BLOCKED_*/PARKED が blocked/ に配置
6. 102 board の各 100+ row に `doc_path` field 追加
7. 102 board に folder policy section 追加(本 ticket の policy 内容)
8. doc/ 直下に **未分類** ticket(100+ range)が残らない(102/PUB-*/001-099 のみ)
9. **suite baseline 1238/0 維持**(src/tests 触らないので変化なし)

## verify

- `find doc -maxdepth 3 -type f -name "*.md" | sort | head -50`
- `ls doc/active/ doc/review/ doc/blocked/ doc/archived/2026-04/`
- 102 board の `doc_path` field と実 path 一致(grep verification)
- 旧 path 参照を grep(`grep -rn "doc/130-pub004-hard-stop-vs-soft-cleanup\|doc/131-publish-notice-batch-suppress" doc/`)
- `git diff --stat` が doc/ 配下のみ
- `python3 -m pytest --collect-only -q | tail -3`(1238 維持)
- `python3 -m pytest 2>&1 | tail -3`(1238 pass / 0 failed)

## 完了条件

- doc/ 直下に未分類 ticket(100+)が残らない
- CLOSED が archived に移動済
- 現在動かすものが active にある
- blocked が一目で分かる
- 102 board から全部辿れる(`doc_path` field 経由)

## 永続 rule の memory 化(本 ticket land 後)

- `feedback_doc_folder_policy_permanent.md` を memory に追加
- 全 Codex 便 prompt に「ticket status 変更時 folder mv 必須」を embed
