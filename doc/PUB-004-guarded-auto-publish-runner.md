# PUB-004 guarded-auto-publish-runner (WordPress publish only)

## meta

- owner: Claude Code(設計 + 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / safe automation / **WordPress publish runner**
- status: READY(095-D close 後 P0.5 主線、PUB-002-B/C/D より優先)
- parent: PUB-002 / PUB-002-A
- consolidates: PUB-002-A 判定 contract / PUB-003 explicit-trigger contract
- sibling: **PUB-005 x-post-gate**(X / SNS POST 用、本 ticket とは別 lane、user 確認 fixed)
- created: 2026-04-25
- policy lock: 2026-04-25 21:55(WP publish は Red 以外 OK、X/SNS は別 lane で厳格管理)

## scope 線引き(2026-04-25 lock)

| 制限対象 | 本 ticket スコープ | 別 ticket |
|---|---|---|
| **WordPress publish** | ✓ 本 ticket(PUB-004)= Red 以外 publish | - |
| **X / SNS / 外部 POST** | ✗ 触らない | **PUB-005 x-post-gate**(Green only + user 確認) |
| mail(自分宛て) | 既存 095 cron に任せる | - |
| RUN_DRAFT_ONLY / Cloud Run env | 触らない | - |

## priority

**P0.5 高優先度。095-D close 後の本線。**

PUB-002-B/C/D は **後続の品質改善**として扱う。
本 ticket は「今ある Green だけを安全に自動 publish」する最小ループ。

## purpose

`RUN_DRAFT_ONLY=False` の一括解放ではなく、
**PUB-002-A の Red 条件に該当しない draft = Green + Yellow を安全に自動 WP publish** する runner を作る。

完璧な記事だけを選ぶのではなく、**危険な記事(Red)だけ止めて、サイト上で見ながら改善する**方針。
Yellow は publish 後に改善ログへ記録し、後続 PUB-002-B/C/D で品質 uplift する。

X / SNS への POST は本 ticket scope **外**(PUB-005 で別 lane 管理)。

## 重要制約(全 phase 共通)

- `RUN_DRAFT_ONLY=False` は **触らない**
- Cloud Run env は **触らない**
- **X 投稿なし**(REST status flip 単独で X 配線 fire しない、verified 2026-04-25)
- **noindex 維持**(site-level、status flip では変動しない)
- **`.env` / secret 表示禁止**(App Password 含む)
- **front / plugin / build artifacts 触らない**
- **publish-notice mail は既存 095 WSL cron に任せる**(本 runner は send 配線を持たない)
- **1 回最大 3 件**(burst cap、PUB-002-A 連動)
- **1 日最大 10 件**(daily cap、history 管理、JST 0:00 reset)
- **mail burst 5 通超で分割**(PUB-004-B が runner 内で 1 回 publish 数を制限、095 cron tick あたりの mail 配信を 5 通以下に保つ)
- **Red のみ publish 禁止**(本 runner は **Red 以外 = Green + Yellow を publish**、user policy 2026-04-25 21:50 lock)
- **Yellow は publish 後に改善ログへ記録**(後続 PUB-002-B/C/D の input、サイト上で見ながら改善する方針)
- **dry-run default**(`--live` 明示 gate 必須)
- live publish は `--live` + `--max <N≤3>` + `--daily-cap-allow` の 3 重 gate

## 判定 → 行動 (user policy 2026-04-25 21:50 lock)

| 判定 | 自動 publish | 改善ログ | 備考 |
|---|---|---|---|
| Green | ✓ | 不要 | そのまま publish |
| **Yellow** | **✓** | ✓ 記録 | publish 後に `logs/guarded_publish_yellow_log.jsonl` へ記録、後で改善対象 |
| Red | ✗ refuse | - | 絶対 publish しない、本 runner で hold |

## user 判断境界(2026-04-25 lock)

- **user 確認は原則不要**。Green 判定後、Claude は autonomous で `--live` publish 可
- user judgment が必要なのは **Red に近い危険記事を publish したくなった時のみ**(本 runner は Red を refuse するので通常発生しない)
- daily cap 10 / burst cap 3 / mail burst 5 / Green only / 上記 「重要制約」は host code で enforced(env / flag では緩められない)

## 不可触

- `RUN_DRAFT_ONLY` flip
- Cloud Run / scheduler env
- automation.toml / Codex Desktop 側
- `.env` / secrets / App Password
- `wp_client.py` 主体は流用のみ非改変
- front lane / plugin / build artifacts
- baseballwordpress repo
- 376 drafts 一括 publish
- WP plugin 設定 / X API

---

## 分割

## Red 条件(本 runner で refuse、user policy 2026-04-25 21:55 lock)

- source にない具体事実
- 明らかな誤情報
- title-body が完全に別物
- 別記事混入
- 未確認引用
- injury / death / 登録抹消 / 診断 / 症状
- 同一記事や同一試合の過剰重複
- X / SNS 投稿が発火しそう(WP plugin / hook で auto-tweet 配線がある post)
- 4/17 事故と同質リスク

これらは本 runner が refuse、それ以外(Green + Yellow)は publish。

### PUB-004-A: dry-run evaluator(WP write なし)

#### scope
- 新規 file: `src/tools/run_guarded_publish_evaluator.py`
- draft pool を scan(WP REST status=draft, orderby=modified, per_page=N、最大 100)
- 各 draft を **PUB-002-A の Green 10 条件 + Red 8 条件** で評価
- 出力: JSON list + 人間向け summary 両方
  - `green: [{post_id, title, reason_summary}]`
  - `yellow: [{post_id, title, blocking_conditions}]`
  - `red: [{post_id, title, red_flags}]`
- WP write **一切なし**(read-only)
- LLM call **なし**(pure Python、既存 071 validator 流用)
- 既存 `src/pre_publish_fact_check/extractor.py` の input 抽出経路を再利用

#### LLM 不在の暫定判定(HALLUC-LANE-002 待ち)

PUB-002-A の Green 10 条件のうち、本来 LLM 判定領域:
- **G3**(title-body 主語・事象 一致):071 validator で部分カバー、完全な意味整合は LLM 必要
- **G7**(数字 source 矛盾なし):打率異常値(`.400` 超)等の regex check のみ、source 一次照合は LLM 必要
- **G8**(source にない断定なし):body 内 named-fact と source_block / source_urls の cross-check は heuristic のみ

→ **PUB-004-A は G3/G7/G8 を `assumed pass` として処理**。
   出力 JSON の Green entry に `needs_hallucinate_re_evaluation: true` flag を付け、HALLUC-LANE-002 land 後に整合 re-evaluate する。

その他 Green 条件(G1 featured / G2 source URL / G4 fact-first title / G5 speculative なし / G6 冒頭 出典 / G9 noindex / G10 X 配線)は pure Python で完全判定可能。

#### CLI
```
python3 -m src.tools.run_guarded_publish_evaluator \
  --window-hours 72 \
  --max-pool 100 \
  --output /tmp/pub004a_eval.json \
  [--exclude-published-today]
```

#### 完了条件
- 96h pool 棚卸しで Green / Yellow / Red 件数表
- Green 候補 list が PUB-002-A 基準と 1 対 1 mapping
- WP write ゼロ(verify: smoke run で WP REST POST/PUT/DELETE call なし)
- 既存 publish 済 post を `--exclude-published-today` で除外可能

---

### PUB-004-B: guarded live publish(最大 3 件 / 1 回、最大 10 件 / 日、Green + Yellow publish / Red refuse)

#### scope
- 新規 file: `src/tools/run_guarded_publish.py`
- input: PUB-004-A evaluator output JSON(またはその場で再 evaluate)
- 各 Green candidate に対し **PUB-003 contract** を流用:
  1. preflight(status=draft, non-empty)
  2. backup(`backups/wp_publish/YYYY-MM-DD/post_<id>_<UTCISO>.json`)
  3. WP REST `update_post_status('publish')`
  4. postcheck(REST status=publish + public URL HTTP 200)
- burst cap: 1 invocation で **max 3 件**
- daily cap: history file `logs/guarded_publish_history.jsonl` で **当日 publish 数を tally、JST 0:00 reset**
- daily cap **10 件超過で stop**(skip 残り、refuse log)
- mail burst control: 1 invocation で publish 数 = 次 095 cron tick (`:15`) で送信される mail 数。**5 通超を予測したら invocation 内で publish を 3 件で打ち切り**(残りは次 invocation へ)
- dry-run default(`--live` なしで 「proposed publish list」 + diff だけ出す)
- `--live + --max-burst <=3 + --daily-cap-allow` 3 重 gate

#### history.jsonl 仕様

format: 1 line = 1 publish attempt(成功/失敗 とも record)
```jsonl
{"post_id": 63278, "ts": "2026-04-25T21:25:09+09:00", "status": "sent", "backup_path": "...", "error": null}
{"post_id": 63257, "ts": "2026-04-25T21:25:12+09:00", "status": "sent", "backup_path": "...", "error": null}
{"post_id": 99999, "ts": "2026-04-26T08:00:00+09:00", "status": "refused", "backup_path": null, "error": "preflight: not draft"}
```

- **JST 0:00 reset**: ts (JST) の date 部分が 当日 のものだけを daily cap count に含める
- **失敗候補は自動再試行しない**: 同 post_id が `status=refused` で record されている場合、次回 invocation で skip(reattempt は手動明示で history line 削除 or override flag 必要)
- 成功 record も skip 対象(同 post_id の重複 publish 防止)
- daily cap 計上対象は `status in {sent, refused}` 両方(skip は count しない、明確に publish 試行した数)

#### Yellow 改善ログ(別 file)

publish 後に Yellow 候補のみ追記:
- file: `logs/guarded_publish_yellow_log.jsonl`
- format: `{"post_id": ..., "ts": "...", "title": "...", "yellow_reasons": [...], "publish_link": "..."}`
- 用途: PUB-002-B / C / D の input(missing-source / subtype-unresolved / long-body 改善対象の継続的な supply)
- Yellow も publish するが、改善対象として可視化

#### CLI
```
python3 -m src.tools.run_guarded_publish \
  --input-from /tmp/pub004a_eval.json \
  --max-burst 3 \
  [--live]
  [--daily-cap-allow]
  --backup-dir /home/fwns6/code/wordpressyoshilover/backups/wp_publish/ \
  --history-path /home/fwns6/code/wordpressyoshilover/logs/guarded_publish_history.jsonl
```

#### 完了条件
- dry-run で proposed list 出力(WP write 0)
- live で max 3 件 publish + backup + postcheck 全 pass
- daily cap 5 超過で 6 件目以降 refuse
- 既存 095 WSL cron が次 :15 tick で publish-notice mail を 1 件 / publish で送信(本 runner は mail 配線なし)
- 失敗時 routing: backup 失敗 / preflight refuse / WP write 5xx で per-item refuse + JSON summary

---

### PUB-004-C: cron activation(PUB-004-B 安定後)

#### scope
- PUB-004-B が安定運用 1〜2 日 + 失敗 0 件確認後
- WSL cron に PUB-004-B の `--live` 実行を **1 日数回**(例: 朝 / 昼 / 夜 = `0 8,13,20 * * *`)で登録
- 毎時起動はしない(mail burst リスク + daily cap 余裕保持)
- crontab marker: `# PUB-004-WSL-CRON-AUTO-PUBLISH`
- burst cap 3 / daily cap 10 維持
- 095 publish-notice cron(`# 095-WSL-CRON-FALLBACK`)とは独立、別 line
- mail burst control: 1 cron tick で publish 数 ≤ 3 → 次 :15 095 cron tick で mail 配信 ≤ 3 通(burst cap 5 内)

#### 失敗 routing
- daily cap 超過: 何度 fire しても 6 件目以降 refuse(history で防御)
- WP REST 5xx: per-item refuse、次 cron tick で再試行
- backup 失敗: per-item refuse、no WP write
- 連続 3 cron tick 失敗 → `# PUB-004-WSL-CRON-AUTO-PUBLISH` 行を comment-out で disable + escalate

#### 完了条件
- cron 1 周回 安定運用(daily 1-3 publish + mail send + dedup 全 pass)
- rollback 経路明記(crontab 1 行 comment-out)

---

## 実装順(推奨)

1. **095-D close**(Phase 3 + 4 = 22:15 mail / 23:15 dedup verify、進行中)
2. **PUB-004-A 起票**(本 doc = 起票完了)
3. **PUB-004-A 実装**(Codex 便、pure Python evaluator、commit + Claude push)
4. PUB-004-A dry-run smoke で Green 候補が 0 件以上出るか確認
5. **PUB-004-B 実装**(Codex 便、guarded publish + dry-run default、commit + Claude push)
6. PUB-004-B dry-run smoke
7. PUB-004-B `--live` で 1 件 publish smoke
8. 095 cron で publish-notice mail 着信確認(user 1 op)
9. 安定 1〜2 日確認後、**PUB-004-C cron activation**(WSL crontab 1 行追加、Claude が直接実行可能)
10. 1 週間運用後に PUB-002-B/C/D の品質改善 ticket へ移行

---

## 依存 / 連携

- **PUB-002-A**(判定 contract)= Green 10 条件 / Red 8 条件の正本
- **PUB-003**(explicit-trigger publish contract)= 単発 publish の preflight + backup + postcheck の正本、本 runner は同 contract を batch 化
- **095 / 095-D**(WSL cron + publish-notice)= 公開後 mail 配信は既存 cron に任せる、本 runner は publish only
- **HALLUC-LANE-001**(extractor)= 入力 JSON 抽出層を共有、subtype 判定流用
- **PUB-002-B/C/D**(品質改善)= **本 ticket 完了後**に並走

## 完了条件(本 ticket 全体)

1. PUB-004-A dry-run evaluator が pure Python で動く
2. PUB-004-B guarded publish が dry-run + live 両 mode で動く
3. burst cap 3 / daily cap 5 が host code で enforced(env / flag では緩められない)
4. 既存 095 cron で publish-notice mail が自動配信される
5. 1 週間 安定運用後、PUB-004-C cron activation で完全自動化
6. 失敗時の rollback 経路が doc 化(crontab 1 行 comment-out)

## stop 条件

- daily cap 超過で 6 件目 publish 試行 → host code refuse、escalate
- backup 失敗で WP write → 本 ticket 違反、即停止
- noindex / X / Cloud Run env 触る変更 → scope 外、別 ticket
- LLM call が必要 → HALLUC-LANE-002 待ち、本 ticket scope 外
- creator 主線改修が必要 → 別 ticket、user 判断

## 関連 file

- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(Green / Red 判定 contract)
- `doc/PUB-003-explicit-approval-wp-rest-publish-lane.md`(本 chat 内では doc 化未済、PUB-003 の preflight/backup/postcheck pattern を本 runner で再利用)
- `doc/095-D-publish-notice-cron-live-verification.md`(WSL cron + mail 配信、本 runner は publish only で連携)
- `doc/PUB-002-B-missing-primary-source-publish-blocker-reduction.md`(後続、Green 条件 G2 の hit 率向上)
- `doc/PUB-002-C-subtype-unresolved-publish-blocker-reduction.md`(後続、subtype 判定強化)
- `doc/PUB-002-D-long-body-draft-compression-or-exclusion-policy.md`(後続、prose 長 policy)
- `src/wp_client.py`(`update_post_status` 流用、非改変)
- `src/pre_publish_fact_check/extractor.py`(入力抽出層、本 runner で再利用)
