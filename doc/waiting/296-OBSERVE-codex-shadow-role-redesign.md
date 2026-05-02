# 296-OBSERVE-codex-shadow-role-redesign

| field | value |
|---|---|
| ticket_id | 296-OBSERVE-codex-shadow-role-redesign |
| priority | P1(GCP Codex 役割明確化、現状観察不能で危険) |
| status | DESIGN_DRAFTED + HOLD |
| owner | Claude(設計)→ user 判断後 Codex impl |
| lane | OBSERVE |
| ready_for | user 明示 GO + 短期 PAUSE 判断後 impl 起票 |
| blocked_by | (短期 PAUSE 判断 = user 別判断、本 ticket 設計はそれと並行可) |
| doc_path | doc/active/296-OBSERVE-codex-shadow-role-redesign.md |
| created | 2026-04-30 |

## 結論

**codex-shadow を停止して終わりではない**。**read-only 監査 Bot として作り直す**ための要件定義。
WP write 権限 OFF / Gemini 初期禁止 / */5 → 手動 or 1日1回 / GCS ledger 出力 / Claude が pull → Codex 別 lane で修正、という role に redesign。

**P0 stoppage の懸念に対する答え**: 本 redesign は **read-only Bot 化**(WP 書込 0 / publish-mail 経路 disjoint / scheduler 手動 or 低頻度 / disable 1 コマンド) → **publish/mail 停止 risk なし**(本 ticket 末尾の安全保証 section で詳細)。

## ⚠ 現状リスク(redesign 未実装、現 codex-shadow を放置した場合)

設置目的は記事修正だが、**現在の状態は debt = 設置目的に逆行している**。3 軸で明示:

### A. デグレ risk(本番事故の温床)

| risk | 現状根拠 |
|---|---|
| **WP 勝手書き換え可能性** | `CODEX_WP_WRITE_ALLOWED=true` ON、`MAX_POSTS_PER_RUN=5` で 1 run 5 post まで処理可、log 0 = 何 post 触ったか永遠に分からない |
| **publish/draft status 変更可能性** | 同上、本日 publish 5 件のうちどれを codex-shadow が触ったか **証明不能** |
| **silent regression 経路** | 観察不能な状態で本番 P0 incident が起きた場合、原因特定で **codex-shadow を否定/肯定できない**(SRE 観点で完全に不可) |
| **dependency invisible** | repo に src なし = この job が他の何に依存しているか追跡不能、deploy chain と無関係に動作 |
| **本日の P0 incident 連鎖** | 仮に本日 12:15 以降の publish 0 が codex-shadow 由来だった場合、観察手段がなく永久に sourceless 不明事故化 |

### B. コスト risk(silent な課金圧迫)

| risk | 現状根拠 |
|---|---|
| **Gemini call 不可視 cost** | `GEMINI_API_KEY` secret bound、call 数 log 0、課金は発生し得る、削減施策(229-COST / 282-COST)の効果計測を妨害 |
| **Cloud Run compute 課金** | */5 cron × 24h × 365 日 = **288 trigger/day 常時稼働**、各 run min-instance + container startup cost、idle でも累積 |
| **Anthropic Codex API 課金疑い** | `CODEX_AUTH_SECRET_NAME=codex-auth-json` + `CODEX_SHADOW_PROVIDER=codex` = OpenAI Codex API or 同等 LLM API call 可能性、call 数完全不可視 = 課金の上限不明 |
| **GCS / Logging cost** | log 0 だが run 痕跡(metadata, exit log)は残る、288 trigger/day × 30 日 ≒ **月 8640 trigger 分の Cloud Run + Logging 課金**(微小だが累積) |
| **削減施策との打ち消し** | 282-COST flag ON で Gemini -10〜30% 削減しても、codex-shadow の不可視 call が同等以上に消費していたら **net 0** |

### C. 不可視 risk(本番システムの債務)

| risk | 現状根拠 |
|---|---|
| **動作している証拠 0** | stdout 完全空、 GCS output 0、WP 痕跡 0 → 動いているかどうか永遠に分からない |
| **動作していない証拠 0** | 同上、停止して問題が起きるかどうか分からない = **disable 判断も unsafe**(影響評価不能) |
| **役割定義と実態の乖離** | memory 上の本来役割「draft repair + WP draft PUT」と現状の observable activity 0 が一致しない、設計意図が破綻している可能性 |
| **src 不在による audit 不能** | repo に src なし、私(Claude)も会議室 Codex も中身を読めない、bug があっても発見手段なし |
| **依存関係 graph 切断** | 他 job と連携しているか / 単独動作か / どの secret に依存しているか、repo から追跡不能 |
| **knowledge 喪失 risk** | この状態が長期化すると、設置者しか中身を知らない black box 化が進行、運用引き継ぎ不能になる |

### 合計リスク評価

- **3 軸全部「観察不能」がコア問題**:
  - A. デグレが起きても気付けない
  - B. コストが嵩んでも気付けない
  - C. 動いてるか動いてないかも分からない
- **本番システムに「分からない物」が常時稼働 = SRE 観点で最大級の debt**
- 設置目的(記事修正)を達成するには、**まず観察可能化が前提**(本 ticket の本旨)
- 「動かしたまま様子見」は許容できない、**redesign 着手 or PAUSE のどちらか**を選ぶ必要

### 推奨即時アクション(本 ticket impl とは独立、user 別判断)

```bash
# Quick PAUSE(現状リスク即時遮断、redesign 着手前の暫定措置)
gcloud scheduler jobs pause codex-shadow-trigger --location=asia-northeast1
```

PAUSE は **可逆 1 コマンド**、本日 publish 経路に trace 0 = PAUSE しても publish/mail 影響 0 仮説強い。redesign 完了まで PAUSE 維持、impl 後に redesign 版で再開。

### PAUSE に伴う失う機能の評価

- 「現状失う機能」**= 観察不能な何か** = 失っている可能性 / 元から失われていた可能性、両方あり得る
- redesign 後の機能 = post_id 単位 audit + 修正候補 ledger output(本来意図の明確化)
- 機能ロスとして失うのは「現状の動作仮説」のみ、redesign で **より明確な機能** で再獲得

## 1. 現状の codex-shadow の問題整理

### 観察結果(本日 audit、read-only)

| 観点 | 現状 | 問題 |
|---|---|---|
| **src code** | repo に **無し**(`grep src/ codex_shadow → 0 hits`、Dockerfile.codex_shadow のみ) | **audit 不能**、何しているか不明 |
| **stdout log** | `Container called exit(0)` のみ、application log **0 行** | 動いているか / Gemini 呼んでいるか / WP 触ったか **観測不能** |
| **GCS / ledger output** | observable な output **0** | 修正候補が誰の手元にも届かない |
| **WP write 権限** | `CODEX_WP_WRITE_ALLOWED=true` ← **本番書込 ON** | 観測不能なまま WP 触れる状態 = 危険 |
| **Gemini API** | `GEMINI_API_KEY` secret bound、call 数 log 不在 | **silent cost** リスク |
| **Scheduler 頻度** | `*/5 * * * *` ENABLED、24h × */5 = 288 trigger/day | 常時稼働、cost / 影響範囲 過大 |
| **WP write 観察** | 本日 publish 5 件 / draft 更新に codex-shadow 由来 trace なし | 実 effective work 0(空走り疑い) |
| **本来意図**(memory `feedback_two_codex_lanes_pinned.md`) | 178 で「draft 本文 repair + WP draft PUT」本線昇格 | 役割と現状の乖離不明 |

### 危険度評価

- 観察できないものを本番で動かす = debt
- WP write ON + Gemini API key bound + log silent = **「何かやっているかも」と「何もしていないかも」が区別不能**
- 本番事故時に「codex-shadow が原因」を否定/肯定できない = SRE 観点で不可

## 2. 新役割定義(redesign)

codex-shadow は以下を担当する **read-only audit Bot**:

1. **公開済み WP 記事 / draft 記事の post_id 単位品質監査**
2. **修正候補の抽出**(detected_issue + repair_type 分類)
3. **修正案の作成**(proposed_title / proposed_summary、ただし保存のみ、apply はしない)
4. **GCS ledger 出力**(`repair_candidates.jsonl`)
5. **Claude / 後段 Codex への入力材料作成**

### 役割境界(他経路と分担)

| 役割 | 担当 |
|---|---|
| 修正候補抽出(本 ticket) | **codex-shadow(redesign 後)** |
| 採否判断 / 優先順位 | **Claude** |
| 修正 ticket 起票 | **Claude** |
| impl + commit | **別 Codex lane**(local Codex A or B) |
| push | **Claude** |
| deploy / WP 反映判断 | **user 判断** |
| rollback 判断 | **user 判断** |

**codex-shadow は WP に直接書き込まない**(write 経路は guarded-publish 専管)。

## 3. 入力データ

codex-shadow が **read-only** で読むもの:

- **WP REST GET**:
  - `/wp/v2/posts?status=publish&per_page=N&orderby=date&order=desc`(直近 N 件公開)
  - `/wp/v2/posts/<post_id>`(個別 post)
  - 必要 fields: id / date_gmt / title / content / excerpt / status / categories / meta
- **GCS ledger 読み取り**(read-only):
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
  - `gs://baseballsite-yoshilover-state/post_gen_validate/post_gen_validate_history.jsonl`(289 ledger)
  - `gs://baseballsite-yoshilover-state/preflight_skip/...`(293 ledger、impl 後)
- **fetcher 由来 metadata**(GCS state 経由):
  - source_url / source_title / source_url_hash / content_hash / subtype 等
- **Cloud Logging**(read-only):
  - 直近 24h の publish / mail / fetcher event(集計用)

## 4. 出力 ledger 仕様

### GCS path
`gs://baseballsite-yoshilover-state/codex_shadow/repair_candidates.jsonl`

### 1 行 1 候補、JSON フィールド
```json
{
  "ts": "2026-04-30T18:00:00+09:00",
  "post_id": 64104,
  "url": "https://yoshilover.com/64104",
  "wp_status": "publish",
  "current_title": "投手陣が乱れ楽天に連敗 中山礼都が猛打賞 ...",
  "proposed_title": "中山礼都が猛打賞、投手陣不振で楽天に連敗",
  "current_summary": "(なし)",
  "proposed_summary": "二軍試合結果。中山礼都2安打...",
  "source_url": "https://twitter.com/...",
  "source_title": "【二軍】巨人vs楽天 中山礼都猛打賞 投手陣乱れ...",
  "subtype": "farm_result",
  "detected_issue": "weak_summary_missing",
  "issue_severity": "P1",
  "repair_type": "summary_backfill",
  "confidence": "medium",
  "requires_human_review": true,
  "gemini_call_made": false,
  "reason": "summary が空、source_title から regex で生成可",
  "do_not_auto_apply": true
}
```

### Field 仕様

- **ts**: ISO 8601 JST
- **post_id**: WP int
- **wp_status**: `publish` / `draft` / `private` / `pending`
- **current_***: 現状の WP 値
- **proposed_***: codex-shadow 提案値(applyしない、Claude/Codex 経由でのみ反映)
- **detected_issue**: 後述 13 種から 1 つ以上(複数は array 化)
- **issue_severity**: `P0` / `P1` / `P2`
- **repair_type**: `title_backfill` / `summary_backfill` / `subtype_reclassify` / `dedup_remove` / `do_not_publish` / `do_not_x_post` / `human_review_only`
- **confidence**: `high` / `medium` / `low`(regex 確信度)
- **requires_human_review**: bool(true なら Claude 必須レビュー)
- **gemini_call_made**: bool(本 ticket 初期 false 固定)
- **do_not_auto_apply**: bool(常に true 推奨、自動 apply は禁止)

## 5. 権限設計

### 必須(初期)

- `WP_URL` / `WP_USER`(read-only access 確認)
- **`WP_APP_PASSWORD` 削除推奨**(read-only path には不要、WordPress 公開 API は authentication 不要)
- GCS read-only(`guarded_publish_history.jsonl` / `post_gen_validate_history.jsonl` / etc)
- GCS write(`codex_shadow/repair_candidates.jsonl` のみ、限定)
- Cloud Logging read

### 削除 / 無効化

- **`CODEX_WP_WRITE_ALLOWED=false`**(明示 false に変更、env flag 経由)
- `GEMINI_API_KEY` 初期は **secret binding 解除**(call 0 維持、binding 残ると誤発火 risk)
- `MAX_POSTS_PER_RUN=20` 等で audit window 制限(現 5 → 20 に拡大、ただし Gemini call 0 なので cost 微増)
- `CODEX_AUTH_SECRET_NAME`(codex-auth-json):必要性再評価、不要なら削除

### IAM

- service account を **read-only IAM role** に絞る:
  - GCS object viewer(対象 bucket のみ)
  - GCS object creator(`codex_shadow/` prefix のみ write 可)
  - Cloud Logging viewer
- WP write 用 IAM 設定があれば剥奪

## 6. Scheduler 設計

### 初期(redesign impl 直後)

- **`codex-shadow-trigger` PAUSE 維持**
- **手動 trigger only**(`gcloud run jobs execute codex-shadow ...` user 明示実行)
- 1 run で 24h 分の post 監査 → ledger 出力

### 24h 観察後(stable 確認)

- **1 日 1 回**(例:`0 7 * * *` 毎朝 7:00 JST)
- env flag `ENABLE_CODEX_SHADOW_DAILY=1` で有効化、default OFF
- 結果 ledger を毎朝 review

### 中期(複数日安定後)

- 必要なら **6h ごと**(`0 */6 * * *`)
- それでも */5 常時稼働には戻さない(復活禁止)

## 7. Gemini 利用ルール

### 初期(redesign impl)

- **Gemini call 完全禁止**
- env flag `ENABLE_CODEX_SHADOW_GEMINI=0`(default、touch しない)
- regex / source_title / WP title / metadata だけで監査

### 将来(必要性が確認された場合)

- env flag `ENABLE_CODEX_SHADOW_GEMINI=1` 別判断 で有効化
- **1 run あたり call 上限**(例:max 5 call/run)、超えたら skip
- **gemini_call_made を ledger に必ず出す**
- Gemini で本文書き換え禁止(あくまで判定補助、proposed_* は regex 由来優先)

### 監査
- Gemini call 数を `gs://.../codex_shadow/gemini_call_log.jsonl` に永続記録
- 24h で集計可能、cost trend 可視化

## 8. 検出したい問題(13 種)

| # | detected_issue | severity | repair_type | regex / 検出方法 |
|---|---|---|---|---|
| 1 | 事実ミス疑い | **P0** | human_review_only | スコア / 日付 / 球場 で source と WP title 不一致 |
| 2 | 一軍/二軍混線疑い | **P0** | human_review_only | title「巨人 4-2」+ 本文「二軍」混在等 |
| 3 | スコア矛盾 | **P0** | do_not_publish | source_title / body 内のスコアが矛盾 |
| 4 | 危険表現(死亡/重傷/救急) | **P0** | do_not_publish | hard_stop token + 巨人選手名 |
| 5 | publish/mail 影響 | **P0** | human_review_only | mail subject prefix 不整合等 |
| 6 | 人名抜け / generic noun head | P1 | title_backfill | title head 「選手/投手/チーム」のみ |
| 7 | 「コメント整理」「関連情報」「発言ポイント」 | P1 | title_backfill | escape phrase 検出 |
| 8 | summary なし / 空 | P1 | summary_backfill | excerpt が空 or `(なし)` |
| 9 | source_title と WP title の大ズレ | P1 | title_backfill | 編集距離 / token overlap が低い |
| 10 | RT 始まり title | P2 | title_backfill | title head が「RT 」 |
| 11 | 元記事断片の混入 | P2 | summary_backfill | summary に絵文字過多 / fragment |
| 12 | duplicate っぽい記事 | P1 | dedup_remove | 同 source_url の publish 既存(263-QA cross check) |
| 13 | MLB / 巨人混線(菅野ロッキーズ等) | P1 | do_not_publish | チーム token mismatch |

加えて X 投稿向けの suppress 候補:
- 14. X 投稿しない方がよい記事:`do_not_x_post`(評論/小ネタ系で X 投稿 cap 浪費するもの)
- 15. 古すぎる記事:age > 72h で publish された後の audit、`human_review_only`
- 16. 本文薄い記事:`body_length < N` で `summary_backfill` or `human_review_only`

## 9. 必須デグレ試験

### A. WP 書込 absolute 禁止
- [ ] WP write 権限 OFF assert(`CODEX_WP_WRITE_ALLOWED=false` 確認)
- [ ] WP REST PUT/POST/DELETE 呼出 0(test stub で全 endpoint mock + assert called=False)
- [ ] publish/draft/private status 変更 0 fixture
- [ ] 既存 codex-shadow が WP に書き込んでいないこと(本 ticket 起票時点で 0 確認、impl 後も維持)

### B. publish/mail 導線不変
- [ ] guarded-publish job 触らない(image / env / Scheduler 不変 assert)
- [ ] publish-notice job 触らない(同上)
- [ ] 267-QA dedup / 289 post_gen_validate 通知 不変
- [ ] Team Shiny From `y.sebata@shiny-lab.org` 不変

### C. Gemini call 増禁止
- [ ] 初期 impl で Gemini stub 呼出回数 0 assert
- [ ] env flag `ENABLE_CODEX_SHADOW_GEMINI` 未設定 or 0 で call 0
- [ ] 229-COST cache_hit 維持、282-COST preflight 不変

### D. ledger 出力可視化
- [ ] `repair_candidates.jsonl` GCS write fixture
- [ ] stdout に `post_id / detected_issue / repair_type / gemini_call_made` 出力 fixture
- [ ] 空 run でも理由(scanned=N / candidates_emitted=0 / reason=...)出力 fixture
- [ ] silent run = 0 assert(必ず log 出力)

### E. 環境不変
- [ ] ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- [ ] SEO/noindex/canonical/301 token 不在
- [ ] X 自動投稿 path 触らない
- [ ] Scheduler 頻度を user 明示 GO なしに変更しない(`*/5` 復活禁止 fixture)

### F. rollback / disable
- [ ] `gcloud scheduler jobs pause codex-shadow-trigger` 1 コマンドで disable
- [ ] env flag remove で機能無効化
- [ ] image revert で完全元戻し
- [ ] disable 状態で publish/mail 経路に影響 0 確認

### G. 受け入れ条件 verify
- [ ] codex-shadow の役割が明確(本 ticket section 2)
- [ ] 何を見ているか log で分かる(stdout 仕様)
- [ ] 何を出したか GCS で分かる(ledger 仕様)
- [ ] 修正候補が Claude に渡せる(GCS pull で読める)
- [ ] WP を勝手に変えない(D 試験 + 権限設計)
- [ ] コストが見える(Gemini call 数 ledger + Cloud Run 課金 default 0 増)
- [ ] 低頻度 / 手動で安全に動かせる(Scheduler 設計)

## 10. 最小実装案

### Phase 1: src を repo に取り込む(audit 可能化)

- 現 codex-shadow image src の repo 化:
  - `src/codex_shadow/` ディレクトリ新設
  - 既存 image source を抜き出して repo 配下に置く(私の現在の audit では Dockerfile.codex_shadow しか見えていない、impl 時は image 解析 or 別 repo から取得)
  - その時点で stdout log emit 強化 + Gemini call binding 解除 + WP write OFF
- env flag `ENABLE_CODEX_SHADOW_REDESIGN` default OFF(impl 時は OFF default、再開時に user 明示 ON)

### Phase 2: 検出 logic narrow 実装(13 種から優先 5 種)

優先 5 種:
- #6 人名抜け / generic noun head
- #7 escape phrase
- #8 summary なし
- #12 duplicate
- #2 一軍/二軍混線

regex / source_title / WP title / metadata 比較で検出可能、Gemini 不要。

### Phase 3: ledger 出力 + Claude pull path

- `gs://baseballsite-yoshilover-state/codex_shadow/repair_candidates.jsonl` write
- Claude が `gcloud storage cat` で pull 可能
- proposed_* は applyしない、Claude 採否判断後に別 ticket で Codex 修正便 fire

### Phase 4: 残り 8 種 + Gemini 補助(将来)

- 検出種の追加
- Gemini 補助の env flag 経由有効化(別 ticket)
- 1日1回 Scheduler 復活(手動から自動へ昇格、別判断)

## 11. 実装する場合の対象 file

### write scope

- `Dockerfile.codex_shadow`(現 image を base に env / entry point 修正)
- `cloudbuild_codex_shadow.yaml`(build config 整理)
- `src/codex_shadow/`(新規 directory、既存 image source の repo 取り込み)
  - `__main__.py`(entry point)
  - `audit_runner.py`(主 logic)
  - `wp_reader.py`(read-only WP REST)
  - `ledger_writer.py`(GCS write)
  - `issue_detectors.py`(13 種検出 logic)
  - `proposal_builder.py`(proposed_title / proposed_summary 生成、regex のみ)
- `tests/test_codex_shadow_audit.py`(新規)
- `doc/active/296-OBSERVE-*.md`(本 file、status 更新)

### 不可触

- `.github/workflows/**`
- `src/guarded_publish_runner.py`
- `src/publish_notice*`
- `src/yoshilover_fetcher*` / `src/rss_fetcher.py`
- `src/draft_body_editor*`
- `src/sns_topic_publish_bridge.py`
- `src/gemini_preflight_gate.py`(282-COST scope)
- `src/title_player_name_backfiller.py` / `src/weak_title_rescue.py`(277/290 scope)
- `src/gemini_cache.py` / `src/llm_call_dedupe.py`(229-COST 不変)
- automation / scheduler / env / secret(本 ticket scope 外)
- prosports / SEO / X 自動投稿 / Team Shiny From / WP REST 直接書込 path

## 12. deploy 要否

- impl 完了 → codex-shadow image rebuild + job update 必要
- env vars 変更:
  - `--remove-env-vars=GEMINI_API_KEY`(初期 binding 解除)
  - `--remove-env-vars=WP_APP_PASSWORD`(read-only path で不要)
  - `--update-env-vars CODEX_WP_WRITE_ALLOWED=false`
  - `--update-env-vars MAX_POSTS_PER_RUN=20`
- Scheduler 操作:
  - **暫定**: `gcloud scheduler jobs pause codex-shadow-trigger`(redesign 完了まで PAUSE)
  - **redesign 完了後**: 手動 trigger only、自動再開は別判断

## 13. rollback / disable 手順

### Quick disable(impl 後でも常時可能、1 コマンド)
```bash
gcloud scheduler jobs pause codex-shadow-trigger --location=asia-northeast1
```
復活:
```bash
gcloud scheduler jobs resume codex-shadow-trigger --location=asia-northeast1
```

### Full rollback(impl 内容 revert)
```bash
gcloud run jobs update codex-shadow --region=asia-northeast1 --project=baseballsite \
  --image=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/codex-shadow@sha256:6ba7d75668070282f642a46a1fe72150013ed04de6226186568afc62c4722fc8
```
(現行 image digest、redesign 失敗時の安全帯)

### env flag 即時無効化
```bash
gcloud run jobs update codex-shadow --region=asia-northeast1 --project=baseballsite \
  --remove-env-vars=ENABLE_CODEX_SHADOW_REDESIGN
```

## 14. HOLD 解除条件(impl 起票前)

1. **codex-shadow-trigger PAUSE 完了**(user 明示 GO 後、暫定停止)
2. **本 ticket 設計を user 確認**
3. **既存 image source を repo に取り込む方針確定**(image 解析 / 元 repo 探索 / scratch 実装 のどれか)
4. **user 明示 GO**

## 15. 安全保証(user の「これで大丈夫?また止まらない?」への回答)

| 過去本日 incident | 本 redesign での防止策 |
|---|---|
| post_gen_validate silent skip | **本 Bot は publish path に介入しない**(observe only)、silent skip は 289 で別途解消済 |
| 205-COST 暗黙 carry | 本 ticket 単独 image rebuild、他 ticket と commit 履歴混ぜない |
| dirty worktree contamination | 294-PROCESS clean export 経由 build を必須化 |
| publish/mail 停止 | **本 Bot は publish/mail 経路に touch しない**(role 定義で明確化、デグレ試験 B で assert) |
| WP 勝手書き換え | **WP write 権限 OFF**(env flag false、test で write 0 assert) |
| Gemini 暴走 | **初期 Gemini binding 解除**(secret binding 削除 + env flag default OFF) |
| Scheduler 復活で */5 暴走 | **手動 trigger only 開始** + 復活は別判断 |

### Guarantee

- **publish/mail 停止リスク = 0**(read-only Bot、publish path と完全 disjoint)
- **WP 勝手書込リスク = 0**(write 権限 OFF + IAM 制限 + test で assert)
- **Gemini 暴走リスク = 0**(初期 binding 解除、有効化は別判断)
- **disable 時の影響 = 0**(現状 trace 0 = 動作 0、PAUSE しても publish/mail に影響無し)
- **rollback 1 コマンド可能**(env flag remove or scheduler pause)

「また止まらないか?」への直答:
**止まらない**。理由は本 Bot が publish/mail/Scheduler/env を **一切 touch しない設計** + **disable 1 コマンド** + **read-only 権限のみ**。万一 audit logic に bug があっても、出力先は GCS ledger のみ = 本番影響 0。

## 16. 不変方針(継承)

- ENABLE_LIVE_UPDATE_ARTICLES=0 維持
- Team Shiny From / SEO / X / Scheduler / 既存 publish-mail 導線 全部不変
- 新 subtype 追加なし
- duplicate guard 全解除なし
- Gemini call 増加なし(初期 0、将来は flag 経由のみ)
- 既存 fixed_lane prompt text 不変

## 17. 関連 ticket

- 289-OBSERVE post_gen_validate notification(silent skip 通知化、本 Bot は重複監査経路にしない)
- 290-QA weak title rescue(本 Bot 検出 #6 #7 と被る、ただし本 Bot は事後監査、290 は fetcher 段階救済 = 役割異なる)
- 291-OBSERVE candidate terminal outcome contract(本 Bot 出力も 5 terminal state に乗せる前提)
- 293-COST preflight skip notification(同 ledger pattern 流用可)
- 294-PROCESS release composition gate(本 Bot deploy にも適用)
- 295-QA subtype evaluator misclassify fix(本 Bot 検出 #2 と協調、ただし本 Bot は detection、295 は判定 logic 修正)

## 18. 完了条件(7 点 contract)

1. commit hash(296 impl)
2. pushed to origin/master
3. GH Actions Tests workflow = success
4. (deploy 便で)codex-shadow image 反映 + env flag 設計通り
5. (deploy 後)手動 trigger で `repair_candidates.jsonl` GCS write 確認
6. (deploy 後)既存 publish/review/hold mail / 289 通知 / Team Shiny From 全部不変
7. (deploy 後問題時)scheduler pause + env flag remove で 1 コマンド disable 確認

## 19. 不採用 option(検討したが取らない)

- **codex-shadow 完全停止 + 削除**:不採用、本来意図(post_id 単位 audit)は YOSHILOVER 品質改善に valuable
- **Claude / 会議室 Codex に統合**:不採用、24h 自動稼働 + GCP 環境という固有特性を活かせない、session 離散な Claude には代替不可
- **WP write 権限維持で write 機能拡張**:不採用、観察不能なまま write は debt 拡大、まず read-only で観察可能化 + 信頼確立後の判断

## Folder cleanup note(2026-05-02)

- Active folder????? waiting ????
- ????????deploy?env????????
- ?????? ticket ? status / blocked_by / user GO ??????
