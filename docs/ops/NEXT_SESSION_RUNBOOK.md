# 次回セッション開始 Runbook(永続正本)

本 doc は **Claude が次セッション起動直後に読む固定手順**。
session_logs に依存せず、`docs/ops/` 5 file だけで再開できる。

---

## 1. 必読 sequence(最初の 1 分)

以下を **順番通り** 読む(他 file は本 sequence 完了後の参照):

```
1. docs/ops/CURRENT_STATE.md       (現在地、6 カテゴリ board)
2. docs/ops/OPS_BOARD.yaml         (ticket 状態の機械可読正本)
3. docs/ops/POLICY.md              (運用ルール、user GO / 自律 GO 境界)
```

これだけで再開可能。以下は必要時のみ:
- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`(user GO 提示時)
- `docs/handoff/session_logs/*.md`(過去 incident 詳細が必要な時、履歴扱い)

---

## 2. 起動直後の必須 read-only verify(2-3 分)

```bash
# repo 同期
cd /home/fwns6/code/wordpressyoshilover
git fetch origin
git reset --hard origin/master
git log --oneline -5
git status --short | head -10

# CI 状態
gh run list --workflow=tests.yml --limit 3 --json status,conclusion,headSha

# live image / scheduler
gcloud run services describe yoshilover-fetcher --region=asia-northeast1 --project=baseballsite \
  --format='value(spec.template.spec.containers[0].image,status.latestReadyRevisionName)'
gcloud run jobs describe publish-notice --region=asia-northeast1 --project=baseballsite \
  --format='value(spec.template.spec.template.spec.containers[0].image)'
gcloud run jobs describe guarded-publish --region=asia-northeast1 --project=baseballsite \
  --format='value(spec.template.spec.template.spec.containers[0].image)'
gcloud scheduler jobs describe codex-shadow-trigger --location=asia-northeast1 \
  --project=baseballsite --format='value(state)'
```

期待値(`OPS_BOARD.yaml` permanent_evidence と一致):
- fetcher: `:4be818d` rev `00175-c8c`
- publish-notice: `:4be818d`
- guarded-publish: `:6df049c`
- codex-shadow scheduler: PAUSED

差分検出時 → **P0 即報告**(自律対処しない)。

---

## 3. 起動後の最初の報告 format(永続、user 向け)

以下 format で必ず出す:

```markdown
## YOSHILOVER 再開報告

### 現在地(CURRENT_STATE.md より)
- ACTIVE: <list>
- OBSERVE: <list>
- READY: <list>(Acceptance Pack 完成済のみ)
- HOLD_NEEDS_PACK: <list>
- FUTURE_USER_GO: <list>
- DONE: <list>

### live verify 結果(read-only)
- repo HEAD: <commit>
- CI 直近: <status>
- fetcher / publish-notice / guarded-publish image: <verify 結果>
- codex-shadow scheduler: PAUSED 確認

### P0 / Safety
- <なし or 検出内容>

### 今 user に必要な判断(0 or 1 件、Acceptance Pack 形式)
- <0 件 or Acceptance Pack 13 項目>

### 次の 1 手(Claude 自律 GO 範囲)
- <1 件、user 確認不要>
```

---

## 4. 禁止事項(永続、確認なしに違反しない)

### 自律 GO 範囲外(必ず Acceptance Pack 提示してから)
- deploy / image rebuild / service-job update / traffic 切替
- env / flag 値変更(`--update-env-vars` / `--remove-env-vars`)
- Scheduler 操作(enable / disable / pause / resume / 頻度)
- SEO / noindex / canonical / 301 / robots / sitemap
- Gemini call 増加(prompt 拡張 / TTL 短縮 / model 変更 / call site 追加)
- mail 通知条件 大改修(subject / dedup / cap / Team Shiny / SMTP)
- source 追加(`config/rss_sources.json` 拡張)
- live_update 変更(`ENABLE_LIVE_UPDATE_ARTICLES` 値)
- X 自動投稿 ON
- cleanup mutation(WP delete / draft 戻し / private 化)
- rollback 不能変更
- 公開基準の緩和(duplicate guard 解除 / hard_stop 解除)
- 新規 ticket 起票(P0 incident 以外)

### 通常時の即停止条件(自律 GO 中、P0/P1 incident でない場合)
- src / tests / config / Dockerfile / cloudbuild yaml / requirements.txt 編集が必要
- silent skip 検出(P0 即報告、自律対処しない、`POLICY.md` §6)
- ledger silent / mail silent / rss_fetcher 内 silent / WP 直接 silent
- env / image / Scheduler の差分検出(期待値と乖離)

### P0/P1 incident 時の例外(`POLICY.md` §14、user 明示 GO 不要)
**8 条件 全部 AND を満たす場合**、Acceptance Pack なしで Claude 自律即時 hotfix 実行可:
1. 継続中のユーザー体感破壊
2. scope narrow(1 service or 1 job の env / scheduler 操作のみ、code 変更 0)
3. Gemini call 増加なし
4. Team Shiny From 変更なし
5. 既存通知全停止ではない(289 / 通常 publish notice / その他通知 1 つ以上残る)
6. rollback 1 コマンドまたは明確
7. 実施後 verify 条件明確(sent=N / errors=0 等)
8. SEO / source 追加 / Scheduler 変更 / publish 基準緩和 に触れない

実行後の事後報告 5 項目(env action / 次 trigger 結果 / errors / rollback 要否 / 影響範囲)で完結。

---

## 5. Claude 自律 GO 範囲(USER_GO_REQUIRED=false で進める、永続)

以下のみ自律で進める(`POLICY.md` §3 10 categories):
- READ_ONLY / DOC_ONLY / EVIDENCE_ONLY / HANDOFF_UPDATE / TEST_DESIGN / ROLLBACK_CATALOG / BOARD_COMPRESSION / ACCEPTANCE_PACK_DRAFT
- **INCIDENT_ANALYSIS**(P0/P1 root cause 解析 / ledger 解析、read-only)
- **P0_P1_NARROW_HOTFIX**(§14 8 条件 全部 AND 満たす narrow hotfix 即時実行、Acceptance Pack 不要)

---

## 6. 更新責任(本 runbook 自身)

| 観点 | 更新責任者 |
|---|---|
| 本 runbook(`NEXT_SESSION_RUNBOOK.md`)| Claude(自律 GO、運用変更時のみ) |
| 期待値 update(image tag / scheduler state)| Claude(本番 deploy 後 commit + push)|
| 必読 sequence 変更 | Claude + ChatGPT 監査(運用 root 変更時) |

---

## 7. 関連 doc(階層)

```
docs/ops/                       (永続正本、5 file)
├── POLICY.md                   (運用ルール 15 sections、user GO 9 / 自律 GO 10 / Acceptance Pack 13 / silent skip P0 / clean build / P0_P1 自律 hotfix 8 条件 / Outcome Ledger format)
├── CURRENT_STATE.md            (現在地、6 カテゴリ board、session 単位更新)
├── OPS_BOARD.yaml              (ticket 状態機械可読正本、各 ticket 7 軸 OWNER + state + evidence)
├── ACCEPTANCE_PACK_TEMPLATE.md (user GO 提示 template、13 項目)
└── NEXT_SESSION_RUNBOOK.md     (本 doc、次回開始固定手順)

docs/handoff/                   (履歴、過去事実、新規 ops 状態の正本ではない)
├── session_logs/
│   ├── 2026-04-30_p0_publish_recovery_observation.md  (P0 復旧履歴)
│   ├── 2026-04-30_next_action_queue.md                (旧 queue、参考履歴)
│   ├── 2026-04-30_session_summary.md                  (旧 1 行サマリ、参考履歴)
│   ├── 2026-05-01_ops_reset.md                        (本 ops reset の起源履歴)
│   └── 2026-05-01_p1_mail_storm_hotfix.md             (P1 mail storm hotfix 1 行履歴 + §14 例外発動 evidence)
└── codex_responses/, codex_requests/, run_logs/       (Codex 履歴)
    ├── 2026-05-01_codex_a_storm_verify.md             (Codex A storm read-only verify + env-only hotfix 案)
    └── 2026-05-01_codex_b_storm_permanent_fix.md      (Codex B 恒久対策 設計 + Acceptance Pack draft)

~/.claude/projects/.../memory/  (Claude 補助記憶、正本ではない、矛盾時は repo 優先)
```

---

## 8. 「次セッション開始」の意味

「次セッション」=:
- WSL 再起動後 / 別端末で起動後 / Claude session が消えた後
- 24h 以上経過後の再開
- ChatGPT Pro 監査後の再開

いずれの場合も、本 runbook の sequence 1-3 をたどれば再開可能。
session_logs / Claude memory なしでも本 runbook + `docs/ops/` 5 file で完結。

---

## 9. 不変方針(永続、`POLICY.md` section 12 と整合)

- `ENABLE_LIVE_UPDATE_ARTICLES=0` 維持
- Team Shiny From `y.sebata@shiny-lab.org` 維持
- SEO/noindex/canonical/301 不変
- X 自動投稿 OFF
- duplicate guard 全解除なし(narrow 緩和のみ可)
- Scheduler 頻度変更なし(現フェーズ NEVER)
- 既存 fixed_lane prompt text 不変
- 新 subtype 追加なし
- prosports 修正なし

これらを変更する場合 = フェーズ変更 = user 明示 GO + Acceptance Pack。
