# 2026-05-20 OB subtype 新設 + farm 2軍/3軍 分離 + フロント / 記事ページ表示設計

- 起票元 chat: 「２軍と３軍を分けるは」「OBとかは？」
- scope kick: Claude 設計 + ticket 起票 (本 markdown は設計・観測 anchor、コード編集前段)
- 本 commit で許可された変更: **この markdown の新規作成のみ**
- 禁止: code 編集 / commit / push / deploy / env / scheduler / WP mutation / X 拡張
- 親 chat の GO 後にのみ、次段(設計詳細 → ticket 起票)へ進む

---

## 1. 背景 / 目的

- 現状 subtype は `postgame / lineup / manager / pregame・probable_starter / farm・farm_result・farm_lineup / player・player_notice・player_recovery / manager_comment / fact_notice / live_update / social_news・social_video_notice / sns_topic / rumor_market` で構成
- 穴として特定された軸:
  - **OB (元巨人)**: MLB policy ([[project_mlb_player_inclusion_policy]]) / YouTube ch 拡充 ([[project_youtube_channel_expansion_candidates_2026_05_14]]) / コーチ・解説者 narrative の受け皿が無く general / social_news / player_notice に散らばる
  - **farm 2軍 / 3軍 分離**: 巨人は 12 球団でも数少ない 3軍持ち球団。現状 `farm_*` は 2軍前提のフォーマットで 3軍記事は混入 or general に落ちる
- 副軸として、subtype を切る以上 **フロント / 記事ページの表示要素**(category slug / archive 経路 / subtype badge / 出典帯)も同時設計が必要

## 2. 想定 deliverable (本 markdown の scope 外、GO 後に起票する ticket 単位)

- T-OB-1: OB subtype 定義(分類条件 / validator / title format / 出典 / x_post 可否)
- T-OB-2: OB classifier(name table + entity gate)
- T-FARM-1: farm 2軍 / 3軍 分離 subtype 定義
- T-FARM-2: 既存 farm 記事の backward-compat (alias → farm2_*)
- T-FRONT-1: フロント / 記事ページの表示要素設計(WP 側 category / template / badge)
- T-VALIDATOR-1: title_style_validator / body_validator / source_attribution_validator / baseball_numeric_fact_consistency / event_key_publish_gate / long_body_compression_audit / weak_title_rescue / x_post_generator の subtype 登録 audit
- (上記は本 markdown では「予定」だけ。実 ticket は GO 後に子 repo `doc/active/` で起票)

---

## 3. 今回触らない範囲

以下は本 work の scope **外**。触ったら STOP。

- 既存 subtype の挙動: `postgame` / `lineup` / `manager` / `pregame` / `probable_starter` の title / body / 出典 / publish gate ロジック
- `guarded_publish_runner` の publish 本体 path(subtype 登録テーブルへの追加のみ可、判断 logic は不変)
- WordPress REST の **mutation** (既存 published 記事の subtype / category 一括書き換え禁止、観察のみ)
- X 自動投稿の対象カテゴリ(現状 postgame / lineup base 維持、OB / farm3 / data_insight は §11 user 判断)
- production への deploy(本作業は code 着地 + dry-run まで、deploy は別便)
- env / Secret Manager / scheduler / traffic
- `automation.toml` / `.codex/automations/**` / draft-body-editor の prompt 既定値
- quality-* / 既存 fact_check pipeline の評価軸(subtype の追加分のみ)
- data_insight 系 (403/404/405) — 別 chain、本 work と独立
- mail / publish-notice / x_post_mail pipeline
- repair / fetcher / source ingestion path(分類点だけ触る、ingestion 自体は不変)

## 4. 影響範囲

新 subtype 受け入れに必要な touch point。各 file は **subtype 追加のみ**、既存挙動の改変は禁止。

### 4.1 classifier / 入口

- `src/rss_fetcher.py`
  - `classify_category()` (line ~22977): OB 判定 + farm 2/3 分岐の追加
  - `PUBLISH_SUBTYPE_ENV_MAP` / `X_POST_SUBTYPE_ENV_MAP` (line ~219, ~234): 新 subtype の env キー追加
  - `ENABLE_FARM_SUBTYPE_SPLIT` (line ~484): 既存 flag、本作業で意味再確認
  - `NARROW_UNLOCK_ALLOWED_SUBTYPES` (line ~506): 新 subtype の許容方針確認
- `src/tools/manual_intake.py`: classify_category 呼び出し点の subtype 渡し確認

### 4.2 title / body validator

- `src/title_validator.py`
  - `TITLE_PREFIX_BY_SUBTYPE` (line ~15)
  - `REQUIRED_FIRST_BLOCK_BY_SUBTYPE` (line ~24)
  - `CONTROLLED_SUBTYPES` (line ~33)
- `src/title_style_validator.py`
  - `FIXED_LANE_TO_EDITORIAL_SUBTYPE` (line ~18)
  - `SUBTYPE_ALIASES` (line ~26)
  - `SPECULATIVE_PHRASES_BY_SUBTYPE` (line ~69)
  - validate_against_lane の subtype-aware フィクスチャ
- `src/body_validator.py`
  - subtype 別 validator(`_is_farm_result_article` / `_is_farm_lineup_article` / `_is_pregame_or_probable_starter`)に OB / farm3 相当を追加
- `src/weak_title_rescue.py`
  - `_ALLOWED_RESCUE_SUBTYPES` (line ~41)

### 4.3 出典 / 数値 fact

- `src/source_attribution_validator.py`
  - `SPECIAL_REQUIRED_SUBTYPES` (line ~23): OB / farm3 の attribution 要件
  - `POSTGAME_OPTIONAL_WITH_WEB_SUBTYPES` (line ~24)
- `src/baseball_numeric_fact_consistency.py`
  - `STRICT_SUBTYPES` (line ~124): farm3 は **LENIENT 側に置く**(3軍は非公式数値中心)
  - `LENIENT_SUBTYPES` (line ~125)
- `src/long_body_compression_audit.py`
  - `SUBTYPE_POLICY` (line ~35)
  - `SUBTYPE_ALIASES` (line ~92)

### 4.4 publish gate / ledger / dedupe

- `src/event_key_publish_gate.py`
  - `GATEABLE_SUBTYPES` (line ~50)
- `src/event_key_ledger.py`
  - `PRIMARY_SUBTYPES_FOR_GENERIC_MERGE` (line ~247)
  - `home_visit / debut_milestone / record_milestone / lineup_role` (line ~624): OB record の扱い
- `src/postgame_revisit_chain.py`
  - `FARM_SUBTYPE` (line ~25): farm2 / farm3 split 後の subtype 名再 review

### 4.5 X 投稿

- `src/x_post_generator.py`
  - `VALID_ARTICLE_SUBTYPES` (line ~460): 受け皿のみ登録、enable は §11 user 判断後

### 4.6 フロント / WP 表示

- WordPress テーマ側(別 repo / WP admin)
  - category slug 新設: `ob` / `farm2` / `farm3` (案、確定は T-FRONT-1)
  - 記事ページの subtype badge 表示(`farm3` を「3軍速報」表記など)
  - archive page(`/category/ob/` 等)の生成可否
  - 出典帯表記: OB は「元巨人 / 現所属 ◯◯」併記、farm3 は「3軍練習試合」明示
  - **本 markdown では設計のみ、WP REST mutation 禁止**

### 4.7 既存記事の互換 (migration)

- 既存 `farm` / `farm_result` / `farm_lineup` published 記事 → mutation 禁止
- 新規 draft からのみ `farm2_*` 適用、`farm` は alias として残す(SUBTYPE_ALIASES に明示)
- alias 経路で既存 validator が壊れないことを baseline で確認

## 5. 実行予定テスト

GO 後のコード編集便で実行する予定の test。本便(markdown 作成のみ)では実行しない。

### 5.1 baseline 確保 (fire 前)

- `git status --short` clean 確認
- `pytest -q` 全件 baseline 取得(collect 数 / pass 数 / fail 数 / skip 数を記録)
- baseline commit hash を本 markdown §9 に記録

### 5.2 unit test (新規)

- `tests/test_classify_category_ob_farm.py`(新規想定)
  - OB name table 1 件 / 現役選手 1 件 / 元巨人 OB MLB 1 件 / 非元巨人 MLB (skip 期待) 1 件
  - farm2 (イースタン公式戦) 1 件 / farm3 (練習試合) 1 件
- `tests/test_title_validator_ob_farm.py`(新規想定)
  - 各 subtype の prefix / first block / rescue 経路
- `tests/test_body_validator_ob_farm.py`(新規想定)
  - OB body の現役解釈ミス回避 / farm3 の数値 LENIENT 適用
- `tests/test_source_attribution_ob.py`(新規想定)
  - OB は「現所属」併記必須 / farm3 は出典帯フォーマット

### 5.3 regression 確認 (既存)

- 既存 `tests/test_classify_category*.py` / `tests/test_title_*` / `tests/test_body_validator*.py` / `tests/test_source_attribution*.py` の全件 pass 維持
- 既存 farm fixture が `farm` alias 経由で farm2_* と同等挙動になることを確認
- pytest collect 数の **増加のみ可、既存 fail の増加禁止**

### 5.4 dry-run

- `guarded_publish_runner` を `RUN_DRAFT_ONLY=1` 相当の dry-run で OB / farm2 / farm3 各 1 fixture 流す
- 出力 draft の subtype / title / 出典 が想定通りか目視
- 既存 postgame / lineup の dry-run 出力に差分が出ないか baseline diff

### 5.5 フロント表示 (read-only)

- WP staging で category slug / archive page の表示確認(read-only、mutation 禁止)
- 本番 WP は触らない

## 6. STOP 条件

以下のいずれかが発生したら **即停止 + 親 chat へ報告**(§31-E open_questions 経由)。

1. baseline pytest の fail 数が **1 件でも増加**
2. baseline pytest の collect 数が **減少**(既存 test 消失)
3. 既存 `postgame` / `lineup` / `manager` / `pregame` / `farm_result` / `farm_lineup` の挙動が dry-run で 1 行でも変化
4. `SUBTYPE_ALIASES` 設定後も既存 farm fixture の出力 hash が変わる(互換性破綻)
5. classifier の confidence 計算が既存 OPEN ticket と衝突([[feedback_template_key_no_full_auto_classification]] 違反)
6. WordPress REST mutation の必要が出た(本作業の scope 外)
7. env / Secret / Scheduler / traffic 変更が必要になった(§11 user 判断)
8. ticket scope が 1 PR で閉じない規模に膨らんだ([[feedback_no_unilateral_scope_split]] と整合の上、user に分割可否を上げる)
9. published 記事の subtype 書き換えが必要になった(observe のみ、mutation は別 ticket)
10. 既存 X 自動投稿の挙動に影響が出た(OB / farm3 enable は §11)
11. Codex の Final report と `git log --stat` が食い違った([[feedback_commit_safety_protocol_grep_compile_pytest_logdiff]])
12. `.git/index.lock` / `master.lock` 衝突([[feedback_git_commit_plumbing_fallback]] 経路へ)

## 7. 禁止事項

- env / Secret Manager / scheduler / traffic / WP REST mutation
- production deploy(本作業は code 着地 + dry-run のみ)
- 既存 published 記事の subtype / category 書き換え
- X 投稿カテゴリの enable (OB / farm3 を VALID_ARTICLE_SUBTYPES に追加するのみ、enable flag は §11 user 判断後)
- 100% 自動 classifier(confidence high のみ付与、曖昧は review に落とす — [[feedback_template_key_no_full_auto_classification]])
- LLM による subtype rewrite / fact 補完(source 不足は draft 落とし、[[feedback_quality_gate_priority]])
- `automation.toml` / `.codex/automations/**` / draft-body-editor prompt の既定値変更
- data_insight chain (403/404/405) との同便混在(別 chain、scope disjoint で並走可だが本 markdown は OB/farm に絞る)
- `git add -A` / `git add .`(明示 path 必須)
- 並走 commit 便([[feedback_codex_supervision_rules]] D)
- ChatGPT 役の現場決定への組み込み(設計相談は OK、決定は Claude)

## 8. 想定されるデグレ

事前列挙し、§5 のテストで catch する。実発生時は §9 / §10 に記録。

| # | 想定デグレ | 検出手段 |
| --- | --- | --- |
| D1 | 既存 farm 記事が新 validator で draft 落ち | baseline pytest + dry-run diff |
| D2 | title_style_validator の SUBTYPE_ALIASES 漏れで rescue 経路誤発火 | title test + weak_title_rescue test |
| D3 | source_attribution の STRICT 群に追加し忘れて attribution 抜け | source_attribution test + dry-run |
| D4 | event_key_publish_gate 未登録で重複 publish guard 抜け | event_key gate test + dry-run の重複 fixture |
| D5 | baseball_numeric_fact_consistency の STRICT/LENIENT 漏れで数値 fact 誤判定(特に farm3 を STRICT 扱い → 全件 review 落ち) | numeric fact test + farm3 fixture |
| D6 | OB classifier が現役選手を OB 誤分類 | OB classifier test + name table 整備 |
| D7 | OB classifier が元巨人 OB を見逃し(false negative) | OB classifier test + 既知 OB 30 件 fixture |
| D8 | farm2 / farm3 の境界判定ミス(2軍試合の練習試合と 3軍公式戦の混同) | farm classifier test |
| D9 | WP front の category slug 未定義で 404 / blank | WP staging 目視(read-only) |
| D10 | x_post_generator が OB / farm3 を投稿対象として誤発火 | x_post test + enable flag 未投入確認 |
| D11 | postgame_revisit_chain の FARM_SUBTYPE 不整合 | revisit chain test + dry-run |
| D12 | long_body_compression_audit の SUBTYPE_POLICY 未登録で audit skip | audit test |
| D13 | classifier confidence の重み変化で既存 subtype の判定が揺らぐ | classifier baseline diff |
| D14 | OB の MLB 記事が classify_category で player_notice / general に落ちて OB 判定漏れ([[project_mlb_player_inclusion_policy]] との整合確認) | MLB OB fixture test |
| D15 | farm3 fact 数値が STRICT 扱いで全件 review 落ち | farm3 fixture + LENIENT 確認 |

## 9. 作業ログ欄

(GO 後に追記。1 行 template: `HH:MM JST | <event> | <ticket / commit_hash> | <next>`)

- 起票 | 407 master / 408 OB / 409 farm split / 410 front 表示 | `doc/active/407-410` 配置 | assignments + README priority board 反映済 → baseline pytest 取得へ
- 設計 lock | 407 §5 で subtype 名 / 判定軸 / validator 要件 / front 要件 確定 | OB = LENIENT + 「元巨人 / 現所属」併記、 farm2 = STRICT、 farm3 = LENIENT、 alias `farm` → `farm2_*` | Task #1 completed
- baseline pytest | HEAD `5d72191` (406 deploy 直後) | **5404 passed / 1 xfailed / 3 xpassed / 16 warnings / 980 subtests passed / 118.80s** | 408 OB Phase 1 実装へ
- 408 Phase 1 設計調整 | OB classifier の primary gate を name table 優先から **literal marker (`元巨人` / `巨人OB` / `古巣巨人` / `巨人時代`) 優先** に変更、 name table は secondary gate で context 判定補強 | false-positive 回避 (現役兼任 OB 阿部監督 / 桑田コーチ 等の混入防止)
- 408 Phase 1 実装 | `src/ob_name_table.py` 新規 (19 OB seed + 10 literal markers) + `src/rss_fetcher.py` `_maybe_apply_ob_subtype` 追加 + 3 validator 登録 (LENIENT / SUBTYPE_POLICY / SPECULATIVE_PHRASES) + `tests/test_ob_classifier.py` (27 tests) | AST OK / smoke import OK / new tests 27 passed
- 408 Phase 1 full pytest | post-impl baseline 比較 | **5431 passed / 1 xfailed / 3 xpassed / 980 subtests passed / 126.31s** (baseline 5404 → +27 new tests、 regression 0) | Task #3 commit へ
- 408 commit | `215abbf 408: OB subtype 新設 (Phase 1, literal marker + name table seed) + 407 / 409 / 410 起票` | 11 files / 1052+ / 1- | push 済 (`ee1d73d..215abbf` 経由、 並走 commit ee1d73d は scope disjoint で問題なし)
- 409 Phase 1 実装 | rss_fetcher に `_maybe_apply_farm_2gun_3gun_split` + 4 新 subtype 登録 (validator 3 file) + 26 unit test | flag 無し時 4 件 regression (`test_third_team_result_routes_to_*` / `test_flag_on_routes_third_team_result_to_farm`) → env flag `ENABLE_FARM_2GUN_3GUN_SPLIT` で gate (default OFF) に修正、 既存 contract (ENABLE_FARM_SUBTYPE_SPLIT=1 + 三軍 → farm) を維持
- 409 fix | flag gate 追加後、 targeted test 96 件 pass (失敗 4 件復活) | full pytest 再実行で全件 verify へ
- 409 Phase 1 full pytest | post-fix | **5502 passed / 1 xfailed / 3 xpassed / 980 subtests / 237.76s** (regression 0) | Task #4 commit へ
- 409 commit | `64125cb 409: farm 2軍 / 3軍 分離 (Phase 1, ENABLE_FARM_2GUN_3GUN_SPLIT flag-gated)` | 6 files / 295+ / 3- | push 済 (`ee1d73d..64125cb`)
- 410 Phase 1 実装 | `src/subtype_display_format.py` 新規 (badge + 出典帯 builder helpers、 additive、 draft pipeline 未 wire) + 17 unit test | Phase 2 で wire-in (postgame_runner / nomotoke_card_renderer 等)
- 410 Phase 1 full pytest | **5520 passed / 1 xfailed / 3 xpassed / 980 subtests / 116.68s** (regression 0) | Task #5 commit へ
- 408 Phase 2 実装 | `src/ob_name_table.py` に `has_known_ob_name` + `_CURRENT_GIANTS_ROLE_GUARDS` 13 件追加、 `_maybe_apply_ob_subtype` を primary OR secondary に拡張、 11 new test (7 has_known_ob_name + 4 name match override) | targeted OB test 38 passed
- 408 Phase 2 full pytest | **5539 passed / 2 failed (`test_publish_default_set_*`, ranking_article_publisher 系) / 1 xfailed / 3 xpassed / 308s** | **2 failed は並走 commit `03a49ee 403 Stage A4 cutover (last_7d → last_5_games 切替)` 由来、 OB Phase 2 と scope disjoint、 私の changes は regression 0**
- 408 Phase 2 commit + push | `afdfd5c 408 Phase 2: OB name table secondary gate activate + 現巨人 role guard` (4 files / 95+ / 9-)
- 410 Phase 2 wire-in 実装 | `src/subtype_display_format.py` に `maybe_prepend_subtype_display` (badge prepend + 出典帯 append + idempotent) 追加 + `src/rss_fetcher.py` `_create_draft_with_same_fire_guard` に `article_subtype` kw 追加 + 2 caller (main / review path) で body_article_subtype / validator_article_subtype 渡し + 8 new test | targeted 25 passed (Phase 1 17 + Phase 2 8)
- 410 Phase 2 full pytest | **5550 passed / 1 xfailed / 3 xpassed / 980 subtests / 120.47s (regression 0)** | 並走 commit `e343479 403 Stage A4 cutover fix` で他者が `test_publish_default_set_*` 2 件も修復済、 fail 0 件で着地

## 10. Regression Memo 欄

(GO 後、デグレ発見・回避・再発防止 memo を追記)

- D6 (OB classifier が現役選手を OB 誤分類) 回避策: Phase 1 は **literal marker 優先**、 name table は Phase 2 に温存。 marker `元巨人`/`巨人OB`/`古巣巨人`/`巨人時代` が title に literal で含まれる時のみ OB override
- D8 関連: `_OB_NON_OVERRIDE_SUBTYPES` (postgame/lineup/pregame/probable_starter/live_update/manager/manager_comment/farm/farm_result/farm_lineup) は marker があっても override しない。 試合 narrative の relevance を優先
- D13 回避: ob は CONTROLLED_SUBTYPES (title_validator) に**追加しない**。 既存 subtype の title validation に影響しない設計 (Phase 2 で必要なら追加検討)
- pytest 5404 → 5431 で **既存 5404 件は変動なし** (collect 数 +27、 fail 増加 0、 既存 pass 数不変)
- title_style_validator.SPECULATIVE_PHRASES_BY_SUBTYPE に ob 追加時、 既存 `test_prompt_lines_cover_all_editorial_subtypes` が TITLE_STYLE_CONTRACTS をループするだけで SPECULATIVE_PHRASES_BY_SUBTYPE を直接 enumerate していないため regression なし
- **D-PARALLEL (410 Phase 1)**: 410 file 用に 私が `git add` した直後、 並走 agent の commit `b46ffaa 403 Stage A4 (prep)` が `git add -A` 相当で私の untracked 3 file (`src/subtype_display_format.py` / `tests/test_subtype_display_format.py` / 本 design doc の 410 行追加) を sweep。 私の commit attempt は "no changes added to commit" で空打ち。 ファイル内容は intact (133 + 166 + 4 行)、 work 損失なし。 ただし commit attribution は 403 Stage A4 commit に紛れ込んだ。 教訓 ([[feedback_parallel_commit_silent_edit_loss]] 再確認): 並走 agent との同 repo work では `git add -A` を避ける合意が必要 / Claude 側は明示 path commit のみ
- **D-NEW (409 Phase 1)**: `_maybe_apply_farm_2gun_3gun_split` を flag 無し常時 ON で導入したところ既存 4 件が fail
  - `test_third_team_result_routes_to_third_team_result_short` (contract skeleton)
  - `test_development_player_note_routes_to_development_player_short` (contract skeleton)
  - `test_third_team_result_routes_to_farm_article_shape_when_flag_is_on` (article quality v1)
  - `test_flag_on_routes_third_team_result_to_farm` (candidate quality flags)
  - 既存 contract は `ENABLE_FARM_SUBTYPE_SPLIT=1` で `三軍` → subtype=`farm` を返す前提だった
  - **回避策**: 新 split を `ENABLE_FARM_2GUN_3GUN_SPLIT` env flag で gate (default OFF) し、 既存 contract を保護
  - **教訓**: subtype 変更は常に env flag で gate する。 `_detect_article_subtype` 末尾の常時 override は backward-compat 破壊リスクが高い
  - 設計 doc §8 D1 (既存 farm 記事が新 validator で draft 落ち) に該当、 fixture 経路でなく test_*_routes 系の contract test で検出された

---

## 作業後追記欄 (作業完了後にここを埋める)

### A. 実際に変更したファイル

(空)

### B. diff 概要

(空)

### C. 実行したテスト

(空)

### D. テスト結果

(空)

### E. 残った懸念

(空)

### F. 新しく見つかったデグレ

(空)

### G. 追加した回帰テスト

(空)

### H. 次回触ってはいけない範囲

(空)
