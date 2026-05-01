# YOSHILOVER 運用 POLICY(永続正本)

本 doc は **repo 内 永続正本**。Claude memory / session_logs / 旧 doc と矛盾した場合は **本 doc 優先**。

最終更新: 2026-05-01
更新責任: Claude(自律 GO 範囲)/ user(USER_GO_REQUIRED 領域変更時)

---

## 1. Source of Truth(正本順序)

1. **`docs/ops/POLICY.md`**(本 doc):運用ルール正本
2. **`docs/ops/CURRENT_STATE.md`**:現在地正本
3. **`docs/ops/OPS_BOARD.yaml`**:ticket 状態正本(機械可読)
4. **`docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`**:user GO 判断 template
5. **`docs/ops/NEXT_SESSION_RUNBOOK.md`**:次回開始手順
6. `docs/handoff/session_logs/`:**履歴**(過去事実 / 不変、新規 ops 状態の正本ではない)
7. Claude memory(`~/.claude/projects/.../memory/`):**補助記憶**、正本ではない

矛盾検出時 → repo 正本(1-5)を優先、memory / session_logs を上位扱いしない。

---

## 2. USER_GO_REQUIRED 9 categories(user 判断必須範囲、限定列挙)

user を `DECISION_OWNER` にしてよい / `USER_GO_REQUIRED=true` にしてよいのは以下のみ:

| category | 該当例 |
|---|---|
| **PROD_DEPLOY** | image rebuild + service / job update / traffic 切替 |
| **FLAG_ENV** | env / flag 値変更(`gcloud run update --update-env-vars` / `--remove-env-vars`)|
| **SCHEDULER_CHANGE** | enable / disable / pause / resume / 頻度変更 |
| **COST_INCREASE** | Gemini call 増加(prompt 拡張 / TTL 短縮 / model 変更 / call site 追加 / cooldown 緩和)/ Cloud Run 課金影響大 |
| **SOURCE_ADD** | `config/rss_sources.json` 拡張 / 新 RSS endpoint 登録 |
| **SEO_CHANGE** | SEO / noindex / canonical / 301 / robots / sitemap |
| **PUBLICATION_POLICY** | duplicate guard 解除 / hard_stop 解除 / default-other 無制限化 / 公開基準緩和 / live_update ON / X 自動投稿 |
| **MAIL_ROUTING_MAJOR** | subject prefix 大改修 / dedup ロジック改修 / cap 改修 / Team Shiny From / SMTP / 通知対象大改修 |
| **IRREVERSIBLE** | rollback 不能変更(履歴削除 / secret rotation 不能化 / WP delete / 統合)/ cleanup mutation |

これ以外で user を `DECISION_OWNER` にしない / `USER_GO_REQUIRED=true` にしない。

### user は EXECUTION_OWNER にできない(永続)

- user は **作業者ではない**、user は高リスク判断の DECISION_OWNER のみ
- すべての ticket で `EXECUTION_OWNER ∈ {Claude, Codex, none}` 必須、user は不可
- Codex doc / mail / WP 等の作業は Claude or Codex が EXECUTION_OWNER として実行

---

## 3. Claude 自律 GO 10 categories(USER_GO_REQUIRED=false で進める)

| category | 該当作業 |
|---|---|
| **READ_ONLY** | gcloud describe / logging read / git status / WP REST GET / GCS read / 5 verify pattern |
| **DOC_ONLY** | doc / docs/ の md 編集(commit + push 含む、自律 GO 範囲) |
| **EVIDENCE_ONLY** | observation 結果記録、ledger sample 取得、KPI 集計 |
| **HANDOFF_UPDATE** | session log / CURRENT_STATE / OPS_BOARD / NEXT_SESSION_RUNBOOK 追記 |
| **TEST_DESIGN** | デグレ試験 / Acceptance test fixture 設計(impl 着手しない) |
| **ROLLBACK_CATALOG** | rollback target image 確認 / env flag 戻し方記録 / runbook |
| **BOARD_COMPRESSION** | ticket 統合 / 凍結 doc move 設計 / 状態整理 |
| **ACCEPTANCE_PACK_DRAFT** | user GO 必須案件の Acceptance Pack 13 項目整備 |
| **INCIDENT_ANALYSIS** | P0/P1 incident の root cause 解析 / ledger 解析 / log 解析 / 仮説検証(read-only)|
| **P0_P1_NARROW_HOTFIX** | §14 8 条件 全部 AND を満たす narrow hotfix 即時実行(Acceptance Pack 不要、user 明示 GO 不要、ただし事後報告必須)|

### 通常時の即停止条件(自律 GO 中、P0/P1 incident でない場合)

以下のいずれかを満たす場合、自律 GO を即停止 + Acceptance Pack 化:
- src / tests / config / Dockerfile / cloudbuild yaml / requirements.txt 編集が必要
- deploy / env / flag / Scheduler / secret 変更が必要
- Gemini call 増加が必要
- mail 通知条件 大改修が必要
- USER_GO_REQUIRED 9 categories 領域に触れる

### P0/P1 incident 検出時の例外

**§14 8 条件 全部 AND を満たす場合のみ、env / scheduler narrow hotfix を Claude 自律即時実行可**(Acceptance Pack 不要、user 明示 GO 不要)。違反 1 つでも Codex 便経由 + Acceptance Pack。
silent skip / ledger silent / WP 直接 silent 等の修復は §6 により **必ず Acceptance Pack 経由**(自律 hotfix 範囲外)。

---

## 4. State 定義(必須 evidence)

| 状態 | 意味 | 必須 evidence |
|---|---|---|
| **CODE_DONE** | code 書き終わった | git diff 確認 + local pytest baseline 維持(failures 増加 0) |
| **PUSHED** | origin/master に push | `git log origin/master | grep <hash>` 確認 |
| **DEPLOYED** | image rebuild + service/job update 完了 | `gcloud run describe` で image tag 確認 |
| **LIVE_TRIGGERED** | 自然発火 trigger で 1 回以上 execute | execution log で exit 0 確認 |
| **USER_VISIBLE** | user が確認できる経路に到達 | mail / WP / dashboard 等で sample 観測 |
| **OBSERVED_OK** | user 期待値通りの挙動を 24h 等の期間観察済 | 24h log breakdown / Gmail sample / silent skip 0 / 既存導線維持 |
| **DONE** | OBSERVED_OK + close 条件達成 | OBSERVED_OK 全項目 + ticket close 判断 |
| **DOC_LOCAL** | doc 更新したが repo 未 push | local edit 完、commit 未 |
| **DONE_DOC_ONLY** | doc 更新 + commit + push 完了 + close 条件達成 | commit + push + repo 正本反映 |

evidence が無いものは **前段階のまま**(推測で進めない)。

### 廃止 state(本 reset 以降使わない)
- ~~DONE_PARTIAL~~:廃止。OBSERVE(production_health 統合)or HOLD のどれかに振り直す
- ~~NOT_DONE~~:廃止。OBSERVE / HOLD_NEEDS_PACK / FUTURE_USER_GO / FROZEN のどれかに必ず分類

---

## 5. HOLD 定義(必須 7 項目)

全 HOLD ticket に以下 7 項目を **必須付与**(OPS_BOARD.yaml に機械可読 schema 化):

```yaml
- ticket_id: <id>
  status: HOLD_NEEDS_PACK | FUTURE_USER_GO | HOLD_DESIGN | FROZEN
  decision_owner: user | Claude | Codex | ChatGPT
  execution_owner: Claude | Codex | none
  evidence_owner: Claude | Codex | user
  user_go_required: true | false
  user_go_reason: <9 categories のどれか or "n/a">
  next_review_at: <date or event>
  expiry: <date or condition>
```

### 解除条件のない HOLD は禁止

明示的な `next_review_at` + `expiry` 必須。「user GO 待ち」だけの HOLD 不可。

---

## 6. silent skip = P0(検知ルール)

以下のいずれかが検出された場合、**P0 即報告**(自律対処しない):

1. **ledger silent**: `*_history.jsonl` で `skip_reason` missing / null / empty な record
2. **mail 経路 silent**: skip event が log に出ているが publish-notice / mail に乗らない
3. **rss_fetcher 内 silent**: `_log_article_skipped_*` event 出力されたが ledger 永続化されない
4. **WP 直接 silent**: WP に書き込まれた / 削除されたが log / ledger に痕跡なし

silent skip 検出時:
- 自律 GO で fix 試みない(silent path 修復は Acceptance Pack 必須)
- user 即報告 + Acceptance Pack 化
- 一時 mitigation(env flag 戻し等)も user GO 必須

---

## 7. cost 監視ルール

### Gemini call 増加検知
1. **24h Gemini call 数監視**: deploy 前後で +20% 超 → user 報告
2. **cache_hit ratio 監視**: 75% baseline、急変動(±15%pt 超)→ 真因 audit
3. **同 source_url_hash 重複 call**: 1 source per 24h で複数 call → dedup 不全 報告
4. **新 call site 検出**: src/rss_fetcher.py 等の grep、追加は user GO 必須(`USER_GO_REASON=COST_INCREASE`)

### Cloud Run / GCS / Logging 増加
1. **Cloud Build 1 日最大 1 回**(P0/P1 incident 時のみ追加可、commit message に「P0/P1 例外」明記)
2. Cloud Run min-instance ≠ 0 → idle cost 検出 → user GO で見直し
3. GCS write volume 急増 detection
4. **Codex fire 1 日最大 2 件**(P0/P1 incident 時のみ追加可、本日 2026-05-01 は P1 mail storm で 4 件 fire = 例外発動済)
5. **UNKNOWN cost impact は GO 禁止**(Acceptance Pack で定量化できない場合は最低 HOLD)

### コスト削減と候補消失防止の順序(永続、固定)

**順序を間違えると候補消失で記事品質が落ちる**。固定順序:

1. skip / hold / review / publish の **可視性**
2. **silent skip 0** 維持
3. **candidate disappearance risk** の計測(数値化)
4. preflight skip を **user-visible** にする(289 系)
5. cache / Gemini call / token 影響 の観測
6. 上記 1-5 が安定後に **282-COST flag ON**

**293-COST(統一観測 ledger)は 282-COST(preflight gate flag ON)の前提**。
282-COST を flag ON してから 293 で可視化するのは禁止(逆順)。

---

## 8. clean build 必須(deploy 前 gate)

`gcloud builds submit .` は worktree 全体を tar 送信 = dirty file が image に混入 risk。

### deploy 前 必須手順
1. `git stash -u`(全 untracked + modified を退避)or `/tmp/<commit_hash>` clean export 経由 build
2. `git log <prev_image_commit>..<new_image_commit>` で commit 一覧確認
3. HOLD ticket 該当 commit 検出時 → build 前停止 + Acceptance Pack 化
4. `git diff --cached --name-status` 後の commit が deploy 対象 commit と一致確認
5. build 後 image digest と commit hash の対応 doc 化

### 違反時
build context 汚染検出 → image rollback + user 報告 + Acceptance Pack 化

---

## 9. Acceptance Pack 必須 13 項目(user GO 提示時の固定 format)

詳細 template は `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` 参照。

### 禁止 pattern(本 policy 違反)
- Acceptance Pack なしの「進めてよいですか?」「確認お願い」(全面禁止)
- 候補 2-3 並列で user に選ばせる(推奨 1 つに圧縮)
- Cost impact / Stop condition / Expiry / Rollback 省略
- 不安なら user に聞くのではなく **Acceptance Pack を作る**

### 推奨判断の決め方
- 全 13 項目埋まる + Cost impact ≤ 想定 + Rollback 1 コマンド可能 → **GO 推奨**
- Preconditions 未達 / Cost impact 不明 / Rollback 不能 → **HOLD 推奨**
- Scope に IRREVERSIBLE 含む or 公開影響大 → **REJECT 推奨**(scope 縮小して再 Pack)

---

## 10. 新規 ticket 起票ルール

| 条件 | 起票可否 |
|---|---|
| P0 Safety incident 検出時 | **必須起票** |
| 既存 ticket と scope disjoint + 統合困難 | OK(自律 GO) |
| user 明示 GO で起票指示 | OK |
| 上記以外 | **既存 ticket への追記を優先**(新規禁止) |

特に下記は **新規禁止、既存追記**:
- silent skip 経路 → 289 / 291 / 292 / 293 親に追記
- 品質改善 → 277 / 290 / 278-280 親に追記
- cost 削減 → 229-COST / 282 / 293 親に追記

---

## 11. report format(user 向け)

### 自律 GO で完了時(user 確認不要)
```
1. 更新したファイル
2. diff 要約
3. code diff 0
4. deploy / env / flag / Scheduler / Gemini call / mail 条件変更 0
5. 次に user GO が必要なものの有無(0 or Acceptance Pack 提示)
```

### user GO 必要時
**Acceptance Pack 13 項目** で提示。User reply format: `GO` / `HOLD` / `REJECT` のみ。

### 異常検出時(silent skip / errors / 未確認状態)
**P0 即報告**:何が起きたか / 影響範囲 / 即時対処の有無 / Acceptance Pack 化必要性

---

## 12. 不変方針(永続、本フェーズ NEVER 触らない)

- `ENABLE_LIVE_UPDATE_ARTICLES=0` 維持
- Team Shiny From `y.sebata@shiny-lab.org` 維持
- SEO/noindex/canonical/301 不変
- X 自動投稿 OFF
- duplicate guard 全解除なし(narrow 緩和のみ可)
- Scheduler 頻度変更なし(現フェーズ NEVER)
- 既存 fixed_lane prompt text 不変
- 新 subtype 追加なし
- prosports 修正なし

これらを変更する場合 = **フェーズ変更**、user 明示 GO 必須(Acceptance Pack with `USER_GO_REASON=PUBLICATION_POLICY` or `SEO_CHANGE` 等)。

---

## 13. 関連 doc

- `docs/ops/CURRENT_STATE.md`:現在地正本(active board)
- `docs/ops/OPS_BOARD.yaml`:ticket 状態機械可読正本
- `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md`:user GO 提示 template
- `docs/ops/NEXT_SESSION_RUNBOOK.md`:次回開始手順
- `docs/handoff/session_logs/2026-05-01_ops_reset.md`:本 policy の起源履歴(履歴扱い、運用 active 正本ではない)
- `docs/handoff/session_logs/2026-04-30_*.md`:過去 session 履歴(履歴扱い)

---

## 14. P0/P1 incident 時の自律 hotfix 範囲(永続、user 明示 GO 不要、2026-05-01 user 新方針反映)

**mail storm / publish stuck / 継続中のユーザー体感破壊 等、即時止血が必要な P0/P1 incident** に限り、以下 **8 条件 全部 AND を満たす場合**、Claude が **Acceptance Pack なし / user 明示 GO なしで即時 hotfix 判断 + 実行可**。

### 必須条件(全部 AND、1 つでも違反したら Codex 便経由 + Acceptance Pack)

1. **継続中のユーザー体感破壊**: P0/P1 級 incident 進行中(static / 想定内のみは自律 hotfix 範囲外)
2. **修正範囲 narrow**: 1 service or 1 job の env / scheduler 操作のみ(複数同時禁止、code 変更 0)
3. **Gemini call 増加なし**: prompt 拡張 / TTL 短縮 / model 変更 / call site 追加なし
4. **Team Shiny From 変更なし**: `MAIL_BRIDGE_FROM=y.sebata@shiny-lab.org` 維持
5. **既存通知全停止ではない**: 289 post_gen_validate / 通常 publish notice / その他通知導線が 1 つ以上残る
6. **rollback が 1 コマンドまたは明確**: `gcloud run jobs update --remove-env-vars=...` or `--update-env-vars=...` で 30 秒以内に元の状態に戻せる
7. **実施後 verify 条件が明確**: 次 trigger sent=N / errors=0 等、自動観察可能な定量指標
8. **SEO / source 追加 / Scheduler 変更 / publish 基準緩和 に触れない**: §12 不変方針維持

### 実行後の必須記録(全部、自律実行ゆえ事後報告で完結)

1. session log(`docs/handoff/session_logs/<date>_<topic>.md`)に 1 行追記: `HH:MM JST | hotfix | <ticket_id> | <env_action> | <next>`
2. OPS_BOARD.yaml `active:` に hotfix ticket を 1 件作成(retroactive OK、24h 内に追加、評価 7 軸 OWNER 付与)
3. 次 trigger 結果を read-only verify(sent / errors / Team Shiny From / 289 通知 / Gemini call delta)
4. user に **事後報告**(完了報告 5 項目: env action / 次 trigger 結果 / errors / rollback 要否 / 影響範囲)
5. effect 不足検出時 → code fix Acceptance Pack へ escalate(自律で code fix 着手しない)

### 禁止される hotfix(必ず Codex 便経由 + Acceptance Pack)

- src / tests / config / Dockerfile / cloudbuild yaml / requirements.txt 編集
- image rebuild + deploy
- 複数 env / 複数 service / Scheduler 頻度 同時変更
- Gemini call 増加
- mail 全停止(publish-notice 全停止 / scheduler PAUSE)
- WP REST mutation
- secret rotation
- Team Shiny From 変更
- 不可逆操作(履歴削除 / WP delete / 統合 等)
- silent skip / ledger silent / WP 直接 silent 修復(§6 により Acceptance Pack 必須)
- SEO / noindex / canonical / 301 / robots / sitemap 変更
- source 追加(`config/rss_sources.json` 拡張)
- publish 基準緩和(duplicate guard 解除 / hard_stop 解除)

### 通常の自律 GO 10 categories との関係

- §3 通常自律 GO は env/flag 変更を **即停止条件** として規定
- 本 §14 は P0/P1 incident 時の例外として、`P0_P1_NARROW_HOTFIX` category 経路で env / scheduler narrow hotfix 即時実行を許可
- 例外発動時:実行前に 1 行返答 「P1 hotfix として ... を自律実行します(§14 8 条件全部 AND 確認済)」+ 8 条件 check list 提示
- 自律実行後即 user に事後報告(5 項目 完了報告)

### 例(参考、2026-05-01 P1 mail storm hotfix)

```
[5/1 09:33 JST] storm 継続中、env=168 削除を §14 8 条件 全部 AND 確認 → Claude 自律実行 OK
 → `gcloud run jobs update publish-notice --remove-env-vars=PUBLISH_NOTICE_REVIEW_WINDOW_HOURS`
 → 09:35 trigger sent=10 継続(env 単独原因ではない確定)→ §14 効果不足検出 → code fix Acceptance Pack へ escalate

8 条件 check:
- 継続中ユーザー体感破壊 ✓(09:00-09:30 60 通連続)
- scope narrow ✓(publish-notice 1 job env 1 個)
- Gemini call 増加なし ✓
- Team Shiny From 不変 ✓
- 通知全停止ではない ✓(default 24h scan に戻る)
- rollback 1 コマンド ✓
- verify 条件明確 ✓(次 trigger sent 観察)
- SEO/source/Scheduler/publish 基準緩和に触れない ✓
```

---

## 15. Outcome Ledger format(永続、完了 evidence 記録)

各 ticket の `OBSERVED_OK` / `DONE` evidence は OPS_BOARD.yaml `done:` section に **以下 format 固定** で永続記録:

```yaml
- id: <ticket_id>
  status: DONE | DONE_DOC_ONLY
  decision_owner: <owner>
  execution_owner: <owner>
  evidence_owner: <owner>
  user_go_required: <bool>
  user_go_reason: <9 categories or n/a>
  evidence: |
    <観測 evidence、可能な限り定量>
    例:
    - 24h sent=N errors=N silent=N
    - Gmail sample N+ thread
    - cache_hit ratio N% (sample/total)
    - commit hash <sha> push 完了
    - GH Actions run <id> success
    - image tag <tag> rev <rev>
  next_action: "(close)" | "<follow-up if any>"
  next_review_at: n/a | <date>
  expiry: n/a | <date>
```

### evidence 必須要素(可能な限り、unknown は明示)

- **定量**: sent / errors / silent / sample 数 / cache hit ratio / pytest pass 数
- **commit/push**: hash + `git log origin/master | grep <hash>` 確認
- **deploy**: image tag + revision(`gcloud run describe`)
- **live**: trigger execute 確認(exit 0 + log)
- **user**: Gmail / WP / dashboard sample 1 件以上

### evidence 不足のまま `done:` に入れない

- evidence 0 → done に上げない、status は前段階維持(CODE_DONE / PUSHED / DEPLOYED / OBSERVED_OK)
- evidence 不明 → "unknown - X 経路で観察必要" 明記、ticket は OBSERVE に置く

### Ledger compaction(自律 GO)

- `done:` に 50 件以上溜まった場合、Claude 自律 GO で月次別 archive(`docs/ops/done_archive/2026-MM.md`)に分離
- OPS_BOARD.yaml `done:` は **直近 30 日 / 直近 30 件** のみ active 表示
- archive は履歴扱い(§1 source of truth 6 と同等、active 正本ではない)

### 既存 done entry も本 format に揃える

- 過去の done entry で本 format 違反があれば、自律 GO で format 補正(evidence 追記、不足は "unknown" 明記)

---

## 16. doc commit / staging 規律(再発防止、永続)

本日 2026-05-01 観測 sin から学習した規律:

### 再発防止 1: untracked のまま「永続化済」と書かない

**事象**: 前回 session で docs/ops/ 5 file を作成したが untracked のまま、CURRENT_STATE / OPS_BOARD の DONE entry に「永続化完了」と誤記述。1 session 跨ぎでデータ消失リスク。

**対策**:
- doc 永続化評価 = `git ls-files <path>` で tracked 確認 + commit hash 記録
- CURRENT_STATE / OPS_BOARD entry の evidence に必ず実 commit hash(`git log` で確認可能なもの)を書く
- 「commit 予定」「push 予定」と書いた場合、同 session 内で完遂してから DONE 化
- session 終了前に `git status --short docs/ops/ docs/handoff/` で untracked / modified が残っていないか self-verify

### 再発防止 2: Codex 並走中の git add stage 残り混入

**事象**: Claude が `git add` した file が、Codex の `git commit` に巻き込まれて 1 commit に統合された(2026-05-01 commit `0b64078` で観測)。

**対策**:
- Claude が git add した直後は、できる限り speedy に git commit まで進める(stage 残し時間の最小化)
- 並走 Codex 便には commit 前に `git diff --cached --name-status` で想定外 path 確認指示(Codex prompt に標準装備)
- 想定外 path 検出時は `git reset HEAD <path>` で stage 戻し、再度明示 path で stage(memory: feedback_index_state_verify_before_commit.md)
- commit 単位の責任分離(Claude commit / Codex commit)が崩れた場合、commit message に「巻き込み混入」を明記して追跡可能化

### 再発防止 3: 明示 path のみ git add(`git add -A` / `git add .` 禁止)

memory: `feedback_doc_folder_policy_permanent.md` の永続適用。

- `git add -A` / `git add .` は untracked sensitive(`.env` / credentials / build artifacts)を巻き込む risk
- Claude は常に明示 path: `git add docs/ops/POLICY.md docs/ops/CURRENT_STATE.md ...`
- Codex prompt にも明示 path 指示(prompt template 標準装備)

### 再発防止 4: doc 移動は同 commit で path / OPS_BOARD entry も update

`feedback_doc_folder_policy_permanent.md` の永続適用。

- ticket status 変更で doc を `doc/active/` → `doc/done/YYYY-MM/` に move する場合、同 commit で move + OPS_BOARD entry status 更新
- 中途 commit(move のみ + entry 別 commit)は board と現実の乖離を生む

### 再発防止 5: session 終了前 self-verify checklist

session 終了前(または long pause 前)に 1 度だけ実行:

```bash
cd /home/fwns6/code/wordpressyoshilover
git status --short                         # untracked / modified 0 が望ましい
git log origin/master..HEAD --oneline      # local commit 未 push 0 が望ましい
git ls-files docs/ops/ | wc -l             # 5 file tracked であること
```

untracked / unpushed が残っている場合、明示理由を session log に 1 行追記してから停止。

---

## 17. Claude 一次受け徹底ルール(永続、user 接点を絞る)

**Claude = 現場責任者 / Codex = 現場開発者 / user = 高リスク判断者**。3 役割の境界を厳守。

### Claude が必ずやること(一次受け)

1. **Codex 生回答 / 長文監査 / 細かい log を user に直接流さない**(全面禁止)
2. Codex completion report を読む → リスク判定 → repo 正本に記録 → Acceptance Pack に圧縮 → user には GO/HOLD/REJECT のみ求める
3. 軽い迷い / 境界判定で user に聞かない、迷ったら **Acceptance Pack を作る**(Pack 未完成なら HOLD_NEEDS_PACK)
4. user 提示は次の format に固定:
   - **結論**: GO / HOLD / REJECT
   - **理由**: 1-3 行
   - **user 必要返答**: GO / HOLD / REJECT のみ

### user に出してはいけないもの

- Codex 生 doc / Acceptance Pack 13-18 項目の全文(関連 file path のみで OK)
- pytest 結果の long log
- gcloud / gsutil / git の生 output
- 「進めていいですか?」(全面禁止、§9 と整合)
- 候補 2-3 並列で user に選ばせる(§9 と整合、推奨 1 つに圧縮)

### Codex commit boundary(永続)

- Codex commit / Claude push が原則(memory: feedback_codex_commit_claude_push.md)
- Claude commit は **doc-only 運用立て直し scope** + user 明示 GO 範囲で例外可
- 両者に共通: `git add -A` 禁止、明示 path のみ、`git diff --cached --name-status` verify 必須(§16)

---

## 18. Acceptance Pack 必須 18 項目(永続、UNKNOWN 検出時 HOLD)

§9 の 13 項目に加え、以下 5 項目を **必須**(全部 YES / NO / UNKNOWN で記入):

14. **Gemini call increase**: YES / NO / UNKNOWN
15. **Token increase**: YES / NO / UNKNOWN
16. **Candidate disappearance risk**: YES / NO / UNKNOWN
17. **Cache impact**: YES / NO / UNKNOWN
18. **Mail volume impact**: YES / NO / UNKNOWN

### UNKNOWN 検出時の自動判定

- いずれかが UNKNOWN → 推奨判断は **最低 HOLD**(GO 推奨禁止)
- UNKNOWN を YES/NO に確定するために、追加観察 / read-only verify / Codex 設計便を起こす
- 確定後に Pack を再提示

### 全項目 NO + 全項目 evidence 揃う場合のみ GO 推奨可

不安要素 1 つでも残るなら HOLD 推奨が default。

---

## 19. mail storm を P1 体感事故として永続記録(本日 2026-05-01 起源)

mail storm のような **コスト事故ではない user 体感事故** を P1 として正式分類。

### 体感事故の定義
- Gemini call 0 でも user 体感を直接壊す事象
- mail 過多 / 通知無音 / publish 急減 / X 直撃 / WP front 大規模変動

### P1 体感事故 検出時の手順
1. §14 8 条件 で narrow hotfix 自律実行 OR Acceptance Pack 経由
2. `docs/ops/INCIDENT_LIBRARY.md` に 1 page post-mortem 記録(再発防止 anchor)
3. OPS_BOARD active に entry(severity=P1)、24h 内 close
4. 真因 fix が必要なら 別 ticket(P2 deferred)起票

### INCIDENT_LIBRARY 参照義務
- 次の P1 hotfix 判断時、Claude は INCIDENT_LIBRARY.md を必ず参照
- 過去事例で同じ境界判定をしている場合、その判断を踏襲(または明示的な逸脱理由を記載)

---

## 20. 本日 GO scope 永続化(2026-05-01 user 明示)

### 今日 GO する scope(運用 OS 立て直し only)
- repo 正本 5 file 永続化
- チケット 58 → ACTIVE 最大 2 / OBSERVE 最大 1 / READY 最大 3 / HOLD_NEEDS_PACK / FUTURE_USER_GO / FROZEN / DONE への圧縮
- OWNER 7 軸分離 + user EXECUTION_OWNER 禁止
- Claude 一次受け徹底(§17)
- Acceptance Pack 18 項目化(§18)
- mail storm を P1 体感事故として記録(§19)
- INCIDENT_LIBRARY.md 新規

### 今日 HOLD(個別施策、deploy / flag / source 変更全部)
- 290-QA deploy / 282-COST flag ON / 288 source 追加 / Scheduler 変更 / SEO 変更 / live_update 変更 / Gemini call 増加 / mail 通知条件 大改修 / Growth 施策 / X 自動投稿 / cleanup mutation / codex-shadow 再開
- 298-Phase3 deploy(本日は Pack 整備まで、deploy は明日以降の別 user GO)
- Codex による **実装準備 / test 追加 / local 検証 / commit/push 候補作成** は Claude 一次受け範囲で OK、本番反映は Acceptance Pack 後

### 今日 REJECT(永続)
- user を default OWNER にする
- Acceptance Pack なしの「進めていいですか?」
- Codex 生回答を user 直送
- READY を Pack 未完成で使う
- DONE_PARTIAL / NOT_DONE の復活
- FROZEN / DEEP_FROZEN を通常 board に大量表示
- 「ついでに 1 個だけ」の小変更
- 時間があるから全部やる scope 拡大(時間は **観察 / 証跡 / rollback / Pack 整備** に使う)

---

## 21. 関連 doc(階層、§13 補足、永続正本は 3 つ)

**正本 3 つ**(repo 真正本):
1. `docs/ops/CURRENT_STATE.md` — 現在地
2. `docs/ops/OPS_BOARD.yaml` — ticket 状態機械可読
3. `docs/ops/POLICY.md` — 本 doc(運用ルール)

**補助正本 2 つ**:
4. `docs/ops/ACCEPTANCE_PACK_TEMPLATE.md` — user GO 提示 template(18 項目)
5. `docs/ops/NEXT_SESSION_RUNBOOK.md` — 次回開始手順
6. `docs/ops/INCIDENT_LIBRARY.md` — P1 体感事故 post-mortem ライブラリ

**履歴**(正本ではない):
- `docs/handoff/session_logs/` — session 単位履歴
- `docs/handoff/codex_responses/` — Codex 履歴
- `docs/handoff/codex_requests/` — 旧依頼書(現在 inline prompt 主流)

**記憶補助**(正本ではない):
- `~/.claude/projects/.../memory/` — Claude 補助記憶、矛盾時 repo 優先

mail / Gmail 通知は **Ops Board ではない**(user 通知 / 異常検知 / 要確認の入口)、状態は OPS_BOARD.yaml に戻す。

---

## 22. MAIL_BUDGET(永続、user 体感事故 防止)

### 通知量上限(永続、SLO 化)

| 指標 | 上限 | violation 検出時 |
|---|---|---|
| **Max mails/hour** | 30 通/h(全 publish-notice path 合算)| P1 体感事故扱い、§14 自律 hotfix 検討 |
| **Max mails/day** | 100 通/d(同上)| P1 体感事故扱い、Acceptance Pack 必須 |
| **Max old_candidate emit/day** | 0 通/d(298-Phase3 deploy + flag ON 後)| storm 再発検出、即 P1 |

### 禁止 env(永続、再投入禁止、本日 2026-05-01 起源)

- `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168` 再投入禁止(本日 P1 storm trigger 確定)
- `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS` 24h 以外への変更全般、user 明示 GO + Acceptance Pack 必須(`USER_GO_REASON=MAIL_ROUTING_MAJOR`)
- `PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=0` も実質 mail 全停止に近く禁止(289 と shared cap で巻き添え)

### 単独 safe net 扱い禁止

- **`cap=10/run` だけで safe 扱い禁止**: cap 単独では pool 増加時に cap × N trigger で大量 emit、24h で最大 2880 通可能性
- safe net = `cap` × `dedup window` × `pool size 制限(persistent ledger)` × `MAIL_BUDGET monitor` の 4 重防御
- いずれか欠けたら Pack 必須項目に追加

---

## 23. user 通知絞り込みルール(永続、user 接点圧縮)

### Claude が user に出してよい通知の限定列挙

1. **P0 incident**(silent skip / publish 急減 / WP 直接書込 / secret 露出 等)
2. **P1 incident**(MAIL_BUDGET 違反 / mail storm / 通知無音 / X 直撃 / publish stuck)
3. **user GO required**(USER_GO_REQUIRED 9 categories の Acceptance Pack 提示時、**USER_VISIBLE_NOW** カテゴリのみ)
4. **resolved 通知**(P0/P1 を close した時、1 行で完了報告)

### USER_VISIBLE_NOW = READY の user-facing alias(永続)

user に「今この瞬間提示する判断」は **USER_VISIBLE_NOW** カテゴリに限定。

| カテゴリ | user 提示するか | 状態 |
|---|---|---|
| **USER_VISIBLE_NOW**(= READY 同義) | YES(1 行で提示) | Acceptance Pack 完成済 + Decision 記入済 + user 即返答可能 |
| HOLD_NEEDS_PACK | **NO**(user に見せない) | Pack 未完成、Claude 一次受けで integrating 中 |
| FUTURE_USER_GO | **NO**(user に見せない) | Pack 提示 timing 未到来、precondition 未達 |

user GO 必須 N 件を user に **N 件まとめて見せる運用は禁止**。Claude が USER_VISIBLE_NOW に絞って提示。

### user に出してはいけないもの(永続、§17 と整合)

- Codex 生 doc / completion report 全文
- Claude / Codex 長文監査 / 細かい作業完了の逐次報告
- pytest 結果 / gcloud / git の生 output
- 「進めていいですか?」「ちょっと相談です」(Pack 化 or 自律進行)
- 個別 ticket 進捗の逐次共有(active board 1 view で済むものを別途 push しない)

### 通知 escalation 判定(Claude 自律)

- P2 以下 → user 通知しない、OPS_BOARD entry 更新のみ
- P1 ↑ → 体感事故扱いで user 通知、§14 / §19 連動
- 不明 → 内部判定 / Claude 一次受け、user に投げない

---

## 24. 関連 doc(階層、§13 / §21 統合)

正本 / 補助正本 / 履歴 / 記憶補助 の 4 階層は §21 で確定。
本セッション(2026-05-01)以降の追記:
- §22 MAIL_BUDGET → INCIDENT_LIBRARY.md と連動
- §23 user 通知絞り込み → §17 Claude 一次受けと整合
