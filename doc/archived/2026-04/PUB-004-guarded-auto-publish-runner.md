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
- **1 回最大 20 件(default) / hard cap 30 件**(burst cap、host code で 1-30 range enforce)
- **1 日最大 100 件**(daily cap、history 管理、JST 0:00 reset)
- **mail burst は 131 layering 前提**(per-post 通知 + 10 件ごと summary + alert、runner 側 suppress なし)
- **Red のみ publish 禁止**(本 runner は **Red 以外 = Green + Yellow を publish**、user policy 2026-04-25 21:50 lock)
- **Yellow は publish 後に改善ログへ記録**(後続 PUB-002-B/C/D の input、サイト上で見ながら改善する方針)
- **dry-run default**(`--live` 明示 gate 必須)
- live publish は `--live` + `--max-burst <N≤30>` + `--daily-cap-allow` の 3 重 gate

## 判定 → 行動 (user policy 2026-04-25 21:50 lock)

| 判定 | 自動 publish | 改善ログ | 備考 |
|---|---|---|---|
| Green | ✓ | 不要 | そのまま publish |
| **Yellow** | **✓** | ✓ 記録 | publish 後に `logs/guarded_publish_yellow_log.jsonl` へ記録、後で改善対象 |
| Red | ✗ refuse | - | 絶対 publish しない、本 runner で hold |

## user 判断境界(2026-04-25 lock)

- **user 確認は原則不要**。Green 判定後、Claude は autonomous で `--live` publish 可
- user judgment が必要なのは **Red に近い危険記事を publish したくなった時のみ**(本 runner は Red を refuse するので通常発生しない)
- daily cap **100** / burst cap default **20**(hard cap **30**)/ Green + repaired_publishable / 上記 「重要制約」は host code で enforced(env / flag では緩められない)

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

#### G3/G7/G8 の rule-based 部分検査 + 限界明記(2026-04-25 22:30 lock)

「assumed pass」ではなく、**できる範囲で検査し、限界を明記**する方針。
完全 verify は HALLUC-LANE-002(品質強化レーン、別 ticket)で後追い統合。

| 項目 | 071 既存 | PUB-004-A で追加 | 限界(HALLUC-LANE-002 待ち) |
|---|---|---|---|
| **G3** title-body | SUBJECT_ABSENT / EVENT_DIVERGE / MULTIPLE_NUCLEI | title 主語 token 抽出 + body 先頭 200 chars 出現 check | 意味整合(同義語 / 言い換え) |
| **G7** 数字 source 矛盾 | なし | 異常値 regex(`.400+` 打率 / 試合スコア > 99 / 異常な戦数 等)+ 数字出現箇所 ±50 chars source_block 近傍 token check | 一次照合(実値 vs source 記載値) |
| **G8** source 不在断定 | なし | body 内 player name 抽出 + source_urls/source_block の token 覆い率 ≥ X% 判定 | 文意レベルの「source にない断定」検出 |

その他 Green 条件(G1 featured / G2 source URL / G4 fact-first title / G5 speculative なし / G6 冒頭 出典 / G9 noindex / G10 X 配線)は pure Python で完全判定可能。

PUB-004-A 出力 JSON の Green/Yellow entry に `needs_hallucinate_re_evaluation: true` flag を付け、HALLUC-LANE-002 land 後に再 evaluate。

#### 追加検査(本文構造 + cleanup 候補、2026-04-25 22:30 lock)

PUB-002-A R2 (title-body mismatch) / R8 (4/17 同質) に加えて、本文構造系を別判定:

| 検出名 | 検査内容 | 既定扱い |
|---|---|---|
| `heading_sentence_as_h3` | H3 が 30 chars 以上 + 文末 keyword 含 + 句読点「。」or 主述判定 + 数字 / 選手名含有 = 本文文が H3 化 | **`auto_cleanup_candidate`**(Red ではない、cleanup で p に戻す) |
| `dev_log_contamination` | 連続 5 行以上に dev keyword 2 種 + 含む / `<pre>` `<code>` block / Codex / Claude / Traceback 等含有 | **`auto_cleanup_candidate`**(削除明確なら publish 可、曖昧なら hold)|
| `weird_heading_label` | ラベル H3 だが内容が合っていない(後続段落と subject 不一致) | **Yellow**(改善ログ、publish OK) |
| `site_component_mixed_into_body` | `💬 〜?` `【関連記事】` 等の site 部品が本文に混入 | 末尾 30% 集中 = **Yellow** / 中盤 30-70% 範囲 = **Red** |

**heading_sentence_as_h3 検出条件(doc 固定)**:
- H3 が 30 chars 以上
- 以下の文末 keyword いずれか含む: `〜した` / `〜している` / `〜していた` / `〜と語った` / `〜と話した` / `〜を確認した` / `〜を記録した` / `〜と発表した` / `〜となった` / `〜を達成した`
- または H3 内に句読点 `。` 含有
- かつ 数字 or 選手名 含有
- かつ 見出しではなく本文 1 文に見える(主語+述語が成立)

**短いラベル型 H3 は許容**(`試合結果` `スタメン` `出典` `関連情報` `ファンの声` `コメント` `2軍戦` `今日のポイント` 等、ラベルと中身が合っていない場合のみ `weird_heading_label` Yellow)。

**dev_log_contamination 検出 pattern(doc 固定)**:
- `Traceback (most recent call last)` / `^[a-zA-Z_]+Error: `
- `python3 -m` / `git diff` / `git log` / `git push`
- `wsl.exe` / `cmd /c` / `bash -lc`
- `<pre>` / `<code>` block 全文
- `--full-auto` / `--skip-git-repo-check`
- `commit_hash` / `task_id` / `bg_id` / `bg_`(以降 8 桁英数)
- `[scan] emitted=` / `[result] post_id=` / `status=sent` / `status=suppressed`
- `tokens used` / `changed_files` / `open_questions`
- 上記 pattern いずれかが連続 5 行以上に **2 種以上**含まれる block を検出

**site_component_mixed_into_body 中盤判定**:
- 出現位置 = prose 文字数ベースで判定
- 末尾 30%(全体の後ろ 30% 範囲)集中 → Yellow(削除しても本文成立)
- 中盤 30-70% 範囲に存在 → Red(文脈分断)

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

### PUB-004-B: guarded live publish(最大 20 件 / 1 回 default、hard cap 30、最大 100 件 / 日、Green + Yellow publish / Red refuse、cleanup 込)

#### scope
- 新規 file: `src/tools/run_guarded_publish.py`
- input: PUB-004-A evaluator output JSON(またはその場で再 evaluate)
- 各 Green / Yellow candidate に対し **PUB-004 専用 publish-with-cleanup contract**(PUB-003 とは別契約、PUB-003 は status flip のみの最小契約として保持):
  1. **preflight**(status=draft, non-empty title / content)
  2. **backup**(cleanup 前 1 本、`backups/wp_publish/YYYY-MM-DD/post_<id>_<UTCISO>.json`、cleanup 込みで rollback 可能)
  3. **cleanup**(必要時のみ、下記 「cleanup 仕様」 参照)
  4. **cleanup 後の本文 check**(空 / 核崩れ / source 表記消失 = abort、publish しない)
  5. **WP REST publish**(`update_post_fields(post_id, status='publish', content=cleaned_html)` または content 不変の場合は `update_post_status`)
  6. **postcheck**(REST status=publish + public URL HTTP 200)
  7. **log 記録**:
     - `cleanup_log`: cleanup 内容の before/after diff
     - `yellow_log`: Yellow 判定 + 改善対象記録
     - `history_log`: publish attempt 全件(成功/失敗)

#### cleanup 仕様(PUB-004 専用 contract、PUB-003 と分離)

cleanup 対象(PUB-004-A で `auto_cleanup_candidate` 判定された場合のみ):
- **`heading_sentence_as_h3`** → 該当 H3 を `<p>` に変換(タグ置換のみ、内容は不変)
- **`dev_log_contamination`** → 該当 block を削除(削除明確な場合のみ)
- 削除が曖昧(dev keyword が散在 / コードブロック境界不明) → cleanup せず hold

cleanup 後 abort 条件(publish しない):
- 本文が空(prose < 100 chars)
- 記事核が崩れる(title の主語 token が body から消失)
- source 表記消失(source_block / source_urls が cleanup で削除されてしまう)

cleanup 安全装置:
- backup 必須(cleanup 前)、backup 失敗で cleanup 中止
- diff log 必須(cleanup 内容の before/after を `logs/guarded_publish_cleanup_log.jsonl` に記録)
- 1 invocation 内で max 20 件 cleanup(burst cap default、hard cap 30)、それ以上は次 invocation へ持ち越し

#### cleanup_log format

```jsonl
{"post_id": 63278, "ts": "2026-04-26T08:00:00+09:00", "cleanups": [{"type": "heading_sentence_as_h3", "before": "<h3>...</h3>", "after": "<p>...</p>", "reason": "30+ chars + 文末 keyword + 数字含有"}, {"type": "dev_log_contamination", "before": "Traceback...", "after": "(deleted)", "reason": "連続 5 行 dev keyword 2 種"}], "publish_link": "https://yoshilover.com/63278"}
```

#### original PUB-003 contract との関係

- **PUB-003**: 単発 publish、status flip のみ、content 不変、cleanup なし(最小契約)
- **PUB-004 publish-with-cleanup**: batch publish、status flip + content update + cleanup 副作用、本 ticket 専用契約
- 両者は併存(PUB-003 は手動 publish 用に保持、PUB-004 は autonomous batch 用)
- burst cap: 1 invocation で default **20 件**(hard cap 30、host code で 1-30 range enforce)
- daily cap: history file `logs/guarded_publish_history.jsonl` で **当日 publish 数を tally、JST 0:00 reset**
- daily cap **100 件超過で stop**(skip 残り、refuse log)
- mail burst control: 131 layering(per-post 通知 + 10 件ごと summary + alert)で suppress しない
- dry-run default(`--live` なしで 「proposed publish list」 + diff だけ出す)
- `--live + --max-burst <=30 + --daily-cap-allow` 3 重 gate

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
- daily cap 計上対象は `status == sent` のみ(refused / skipped は count しない、実際に publish できた件数だけを budget として扱う)

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
  --max-burst 20 \
  [--live]
  [--daily-cap-allow]
  --backup-dir /home/fwns6/code/wordpressyoshilover/backups/wp_publish/ \
  --history-path /home/fwns6/code/wordpressyoshilover/logs/guarded_publish_history.jsonl
```

#### 完了条件
- dry-run で proposed list 出力(WP write 0)
- live で max 20 件 publish(hard cap 30)+ backup + postcheck 全 pass(10 件ごと round trip)
- daily cap 100 超過で 101 件目以降 refuse
- 既存 095 WSL cron が次 :15 tick で publish-notice mail を 1 件 / publish で送信(本 runner は mail 配線なし)
- 失敗時 routing: backup 失敗 / preflight refuse / WP write 5xx で per-item refuse + JSON summary

---

### PUB-004-C: cron activation(PUB-004-B 安定後)

#### scope
- PUB-004-B が安定運用 1〜2 日 + 失敗 0 件確認後
- WSL cron に PUB-004-B の `--live` 実行を **1 日数回**(例: 朝 / 昼 / 夜 = `0 8,13,20 * * *`)で登録
- 毎時起動はしない(mail burst リスク + daily cap 余裕保持)
- crontab marker: `# PUB-004-WSL-CRON-AUTO-PUBLISH`
- burst cap default 20(hard 30)/ daily cap 100 維持
- 095 publish-notice cron(`# 095-WSL-CRON-FALLBACK`)とは独立、別 line
- mail burst control: 131 layering で per-post + 10 件 summary + alert(suppress しない)

#### 失敗 routing
- daily cap 超過: 何度 fire しても 101 件目以降 refuse(history で防御)
- WP REST 5xx: per-item refuse、次 cron tick で再試行
- backup 失敗: per-item refuse、no WP write
- 連続 3 cron tick 失敗 → `# PUB-004-WSL-CRON-AUTO-PUBLISH` 行を comment-out で disable + escalate

#### 完了条件
- cron 1 周回 安定運用(daily 1-60 publish + mail send + dedup 全 pass)
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
3. burst cap default 20(hard 30) / daily cap 100 が host code で enforced(env / flag では緩められない)
4. 既存 095 cron で publish-notice mail が自動配信される
5. 1 週間 安定運用後、PUB-004-C cron activation で完全自動化
6. 失敗時の rollback 経路が doc 化(crontab 1 行 comment-out)

## stop 条件

- daily cap 超過で 101 件目 publish 試行 → host code refuse、escalate
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
