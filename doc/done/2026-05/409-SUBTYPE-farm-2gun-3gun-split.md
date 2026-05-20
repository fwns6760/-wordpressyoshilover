# 409-SUBTYPE-farm-2gun-3gun-split

## 1. ticket header

- **status**: READY (407 design lock 確定後、 着手可能)
- **priority**: P2
- **owner**: Claude / **lane**: Claude
- **依存**: [[407]] design lock
- **並走可**: [[408]] (scope disjoint、 ただし classify_category への追加便は直列)
- **設計 anchor**: `docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md` §4

## 2. ゴール

既存 `farm` / `farm_result` / `farm_lineup` を 2軍 / 3軍 で分離し、 巨人特有の 3軍持ち体制を活かす narrative を可能にする。 既存 farm 記事は alias 経路で挙動不変を維持。

## 3. 実装 scope

### 3.1 新規 subtype

- `farm2_result` (2軍 イースタン公式戦の結果)
- `farm2_lineup` (2軍 スタメン / 試合前)
- `farm3_practice` (3軍 練習試合 / オープン戦)
- `farm3_player` (3軍 個人 narrative / 育成選手 spotlight)

### 3.2 alias (backward-compat)

- `farm` → `farm2_result` または `farm2_lineup` (context 判定)
- `farm_result` → `farm2_result`
- `farm_lineup` → `farm2_lineup`
- 既存 farm fixture の出力 hash が alias 経路で**不変** (regression 0)

### 3.3 既存 file への追加

- `src/rss_fetcher.py`
  - `classify_category()` (L22977): 2軍/3軍 判定 logic 追加
    - source URL / source title literal: `イースタン` / `2軍 公式戦` / `フューチャーズ` → farm2、 `3軍` / `育成` / `練習試合` / `オープン戦` → farm3
    - 育成選手 (背番号 3 桁) 含有率: 高 → farm3 寄せ
    - 試合形式 literal: 公式 → farm2、 練習 → farm3
    - 曖昧時 farm2_* fallback (既存挙動と等価)
  - `PUBLISH_SUBTYPE_ENV_MAP` (L219): farm2_* / farm3_* 用 env key 追加 (既定 `1`、 publish ON)
  - `X_POST_SUBTYPE_ENV_MAP` (L234): farm2_* は既存 farm と同 (X 投稿 OFF)、 farm3_* は OFF (§11 user 判断後 enable)
  - `ENABLE_FARM_SUBTYPE_SPLIT` (L484): 既存 flag、 本 ticket で意味再確認 + 新 split に re-purpose
  - `NARROW_UNLOCK_ALLOWED_SUBTYPES` (L506): farm_result alias 経路維持、 farm3_practice は追加検討
- `src/title_validator.py`
  - `TITLE_PREFIX_BY_SUBTYPE` (L15): farm2_* (既存 farm prefix 維持) / farm3_* (「3軍」/「育成」prefix 必須)
  - `REQUIRED_FIRST_BLOCK_BY_SUBTYPE` (L24): farm3 は 3軍試合名 / 育成選手名を first block 必須
- `src/title_style_validator.py`
  - `FIXED_LANE_TO_EDITORIAL_SUBTYPE` (L18): farm2 / farm3 lane 追加
  - `SUBTYPE_ALIASES` (L26): `farm` → `farm2_*` alias 明示
  - `SPECULATIVE_PHRASES_BY_SUBTYPE` (L69): farm3 は farm2 より緩め (3軍報道は非公式中心)
- `src/body_validator.py`
  - `_is_farm_result_article` / `_is_farm_lineup_article` (L315 / L322) を farm2_* に rename、 farm3_* 用 validator 新規追加
  - `_is_farm3_practice_article` / `_is_farm3_player_article` 新規
  - L572 / L660 の subtype dispatch に farm2_* / farm3_* 分岐追加
- `src/source_attribution_validator.py`
  - `POSTGAME_OPTIONAL_WITH_WEB_SUBTYPES` (L24): farm2_* 追加 (既存 farm 同等)
  - `SPECIAL_REQUIRED_SUBTYPES` (L23): farm3_* 追加 (出典帯に「3軍」「非公式」明示必須)
- `src/baseball_numeric_fact_consistency.py`
  - `STRICT_SUBTYPES` (L124): farm2_result / farm2_lineup 追加 (公式数値 STRICT 維持)
  - `LENIENT_SUBTYPES` (L125): farm3_practice / farm3_player 追加 (非公式数値 LENIENT)
- `src/event_key_publish_gate.py`
  - `GATEABLE_SUBTYPES` (L50): farm2_* / farm3_* 追加
- `src/event_key_ledger.py`
  - `PRIMARY_SUBTYPES_FOR_GENERIC_MERGE` (L247): farm2_* / farm3_* 追加
  - `home_visit / debut_milestone / record_milestone / lineup_role` (L624): farm3 record の扱い 確認 (debut_milestone は farm3 で発火する想定)
- `src/long_body_compression_audit.py`
  - `SUBTYPE_POLICY` (L35): farm2_* (既存 farm 同等) / farm3_* (緩め) 追加
  - `SUBTYPE_ALIASES` (L92): `farm` → `farm2_result` alias、 `farm_result` / `farm_lineup` も alias 整備
- `src/weak_title_rescue.py`
  - `_ALLOWED_RESCUE_SUBTYPES` (L41): farm2_* / farm3_* 追加検討 (既存 farm は不在、 後方互換のため farm 系全部を rescue 対象外に維持する案も検討)
- `src/x_post_generator.py`
  - `VALID_ARTICLE_SUBTYPES` (L460): farm2_* / farm3_* 登録 (enable は §11)
- `src/postgame_revisit_chain.py`
  - `FARM_SUBTYPE` (L25): farm2 / farm3 に分岐 (revisit 対象を farm2 限定にするか farm3 含めるかを 410 設計で確定)

### 3.4 既存 fixture / test の rename

- `tests/test_body_validator_farm_result.py` 等 farm 系 test の fixture を `farm` / `farm_result` alias 経由で farm2_* と同等挙動になることを確認するテストに追加
- 既存 test は **削除しない**、 alias 経路の regression test として保持

## 4. 不可触範囲

- [[407]] §6 共通不可触範囲全部
- 既存 published farm 記事の subtype 書き換え (WP mutation 禁止)
- 既存 farm test の delete (alias regression test として保持)
- `ENABLE_FARM_SUBTYPE_SPLIT` flag の既存 ON / OFF 既定値の変更 (本 ticket では re-purpose のみ、 既定値変更は別 ticket で user 判断)

## 5. 実行予定テスト

### 5.1 baseline

- `git status --short` clean
- `pytest -q` 全件 baseline 取得

### 5.2 新規 unit test

- `tests/test_farm2_farm3_classifier.py` (新規)
  - 2軍公式戦 / 3軍練習試合 / 3軍個人 narrative / 曖昧 (farm2 fallback) 4 fixture
- `tests/test_farm3_body_validator.py` (新規)
  - farm3_practice / farm3_player の subtype dispatch + LENIENT 数値 fixture
- `tests/test_farm_alias_regression.py` (新規)
  - 既存 farm / farm_result / farm_lineup fixture が farm2_* alias 経由で出力 hash 一致

### 5.3 regression

- 既存 `tests/test_body_validator*.py` / `tests/test_title_*.py` / `tests/test_source_attribution*.py` 全件 pass 維持
- 既存 farm fixture の出力 hash が alias 経路で**完全一致** (1 byte でも変わったら STOP)

### 5.4 dry-run

- `guarded_publish_runner` で farm2_result / farm2_lineup / farm3_practice / farm3_player 各 1 fixture (計 4 件) を `RUN_DRAFT_ONLY=1` 相当で流す
- 既存 farm fixture を別途流し、 出力に差分なしを確認
- 既存 postgame / lineup の dry-run 出力に差分なし

## 6. STOP 条件

[[407]] §7 + 追加:

- 既存 farm fixture の出力 hash が alias 経路で 1 byte でも変動 → 即停止
- farm2 / farm3 境界判定が曖昧で 50% 以上が fallback 経路に落ちる → classifier ロジック見直し
- 既存 NARROW_UNLOCK 経路への影響 (NARROW_UNLOCK_ALLOWED_SUBTYPES に farm_result が含まれる、 alias で farm2_result に解決される必要)

## 7. 受け入れ条件

- pytest baseline fail 数増加なし
- 新規 unit test 全 pass
- 既存 farm fixture の alias 経路 hash 完全一致
- dry-run で farm2 / farm3 各 fixture が想定 subtype に振り分けられ、 既存 subtype 出力に差分なし
- commit 直列
- [[407]] § 5.3 validator 要件の farm 系 checklist 全項目完了
