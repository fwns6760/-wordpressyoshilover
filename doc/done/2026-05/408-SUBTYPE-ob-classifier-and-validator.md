# 408-SUBTYPE-ob-classifier-and-validator

## 1. ticket header

- **status**: READY (407 design lock 確定後、 着手可能)
- **priority**: P2
- **owner**: Claude / **lane**: Claude
- **依存**: [[407]] design lock (subtype 名 / 判定軸 / validator 要件)
- **並走可**: [[409]] (scope disjoint、 ただし classify_category への追加便は直列)
- **設計 anchor**: `docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md` §4

## 2. ゴール

`ob` subtype を新設し、 元巨人 OB 記事を OB として振り分け、 既存 publish に regression を出さずに OB-aware validator を通す。

## 3. 実装 scope

### 3.1 新規 file

- `src/ob_name_table.py` (新規)
  - 元巨人 OB 名簿 (literal name string set)
  - 30-50 件程度の load-time set、 confidence high の literal match に使う
  - 出典: 既存 [[project_youtube_channel_expansion_candidates_2026_05_14]] + 監督・コーチ就任記事から拾える名前を初期 seed
  - 現役選手 (NPB 12 球団 + MLB 在籍中) は OB 名簿に**入れない**
  - MLB 在籍中の元巨人 (菅野 / 岡本) は OB 名簿に**入れる** ([[project_mlb_player_inclusion_policy]] と整合)
- `tests/test_ob_classifier.py` (新規)
  - 元巨人 OB 1 件 / 現役 1 件 / 元巨人 MLB 1 件 / 非元巨人 MLB 1 件 / 曖昧 1 件
  - confidence high のみ ob 判定、 曖昧は player_notice / general

### 3.2 既存 file への追加 (subtype 登録のみ、 既存 logic は不変)

- `src/rss_fetcher.py`
  - `classify_category()` (L22977): name table literal match + 「元巨人」/「OB」literal gate を追加、 confidence high のみ ob 返却
  - `PUBLISH_SUBTYPE_ENV_MAP` (L219): `ob` 用 env key 追加 (既定 `1`、 publish ON)
  - `X_POST_SUBTYPE_ENV_MAP` (L234): `ob` 用 env key 追加 (既定 `0`、 X 投稿 OFF、 §11 user 判断後 enable)
- `src/title_validator.py`
  - `TITLE_PREFIX_BY_SUBTYPE` (L15): `ob` 追加 (prefix なし、 「元巨人」/「OB」を first block 推奨だが必須ではない)
  - `REQUIRED_FIRST_BLOCK_BY_SUBTYPE` (L24): 既存 player と同等 (player 名 first block)
- `src/title_style_validator.py`
  - `FIXED_LANE_TO_EDITORIAL_SUBTYPE` (L18): ob lane 追加
  - `SUBTYPE_ALIASES` (L26): ob alias 整備
  - `SPECULATIVE_PHRASES_BY_SUBTYPE` (L69): ob は player と同等 (推測語彙 抑制弱め)
- `src/body_validator.py`
  - subtype `ob` 用 validator 追加 (`_is_ob_article` 新規)
  - 「今年の成績」「今シーズン」等の現役解釈フレーズを OB の現所属に resolve、 曖昧時は review 落とし
  - L572 / L660 の subtype dispatch に ob 分岐追加
- `src/source_attribution_validator.py`
  - `SPECIAL_REQUIRED_SUBTYPES` (L23): `ob` 追加 (「元巨人 / 現所属 ◯◯」併記必須)
  - 出典帯 format function に ob 専用 format 追加
- `src/baseball_numeric_fact_consistency.py`
  - `LENIENT_SUBTYPES` (L125): `ob` 追加 (OB current stats は外部 DB 不在、 LENIENT)
  - STRICT には**入れない**
- `src/event_key_publish_gate.py`
  - `GATEABLE_SUBTYPES` (L50): `ob` 追加
- `src/long_body_compression_audit.py`
  - `SUBTYPE_POLICY` (L35): `ob` policy 追加 (既定値、 farm 系より緩め)
  - `SUBTYPE_ALIASES` (L92): ob alias 整備
- `src/weak_title_rescue.py`
  - `_ALLOWED_RESCUE_SUBTYPES` (L41): `ob` 追加 (player と同等)
- `src/x_post_generator.py`
  - `VALID_ARTICLE_SUBTYPES` (L460): `ob` 登録 (enable flag は別ticket / §11)
- `src/postgame_revisit_chain.py`
  - revisit subtype 判定で ob 対応 (現状 FACT_NOTICE / FARM_SUBTYPE のどちらかに resolve、 ob は FACT_NOTICE 寄せ)

## 4. 不可触範囲

- [[407]] §6 共通不可触範囲全部
- 既存 player_notice / player / player_recovery の挙動 (ob 判定漏れは player_notice fallback で吸収)
- WP REST published 記事の subtype 書き換え

## 5. 実行予定テスト

### 5.1 baseline

- `git status --short` clean
- `pytest -q` 全件 baseline 取得、 collect / pass / fail / skip を [[407]] 設計 doc §9 に記録

### 5.2 新規 unit test

- `tests/test_ob_classifier.py`: 5 fixture (元巨人 OB / 現役 / 元巨人 MLB / 非元巨人 MLB / 曖昧)
- `tests/test_ob_body_validator.py`: 現役解釈ミス回避 2 fixture
- `tests/test_ob_source_attribution.py`: 「元巨人 / 現所属」併記 fixture
- `tests/test_ob_title_validator.py`: title prefix / rescue 経路 fixture

### 5.3 regression

- 既存 `tests/test_classify_category*.py` / `tests/test_title_*` / `tests/test_body_validator*.py` / `tests/test_source_attribution*.py` 全件 pass 維持
- pytest collect 数は増加のみ可、 既存 fail 増加禁止

### 5.4 dry-run

- `guarded_publish_runner` を `RUN_DRAFT_ONLY=1` 相当で OB fixture (元巨人 OB / 現役混入チェック / MLB OB) 3 件流す
- 出力 draft の subtype / title / 出典が想定通り
- 既存 postgame / lineup / player_notice の dry-run 出力に差分なし (baseline diff 0 行)

## 6. STOP 条件

[[407]] §7 + 追加:

- name table の false-positive で現役選手が OB 判定 → 即停止、 name table から除外
- name table の false-negative で既知 OB が player_notice に落ち続ける → review 落とし許容、 next iteration で fixture 追加
- MLB OB policy ([[project_mlb_player_inclusion_policy]]) との不整合検知 → 即停止

## 7. 受け入れ条件

- pytest baseline fail 数増加なし
- 新規 unit test 全 pass
- dry-run で OB 3 fixture が ob subtype に振り分けられ、 既存 subtype の出力に差分なし
- name table 30-50 件初期 seed が `src/ob_name_table.py` に literal で存在
- commit 直列 (`.git/index.lock` 衝突回避)
- [[407]] § 5.3 validator 要件の checklist 全項目完了
