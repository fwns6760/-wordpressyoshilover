---
ticket: 254-QA
title: 投手回数表記揺れ正規化 helper(`6` / `6.0` / `6回1/3` / `6.1` / `6回2/3` 統一)
status: READY
owner: Codex B
priority: P1
lane: B
ready_for: codex_b_fire
created: 2026-04-29
related: 244 numeric guard / 244-followup subtype-aware severity
---

## 目的

投手成績(投球回 = innings)の表記揺れで `check_consistency` が false negative(本来 fact 一致なのに mismatch 判定で legacy review 倒し)するのを防ぐ。

例:
- source 「戸郷 6回1/3 投げて 3失点」
- generated 「戸郷 6.1 回 3失点」
- 現状: `extract_pitcher_team_stats` で innings 文字列が違うため照合失敗 → false negative
- 正規化後: `6.1` ≡ `6回1/3` ≡ `6 1/3` 同じと判定 → 正しく fact 一致

## scope (narrow、postgame 関連)

### 1. src/baseball_numeric_fact_consistency.py に新 helper 追加

```python
import fractions

def normalize_innings(value) -> str | None:
    """投手回数表記を正規化文字列に統一。
    入力: "6" / 6 / "6.0" / 6.0 / "6.1" (=6回1/3) / "6回1/3" / "6回 1/3" / "6 1/3" / "6.2" (=6回2/3) / "6回2/3" / "6 2/3"
    出力: "6_0" / "6_1/3" / "6_2/3" 等の統一文字列、parse 不能 / null は None
    """
    # 文字列 normalize
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # "6回" 系除去
    s = s.replace("回", " ").strip()
    # "6.1" / "6.2" を "6 1/3" / "6 2/3" にマップ(MLB / NPB stats 慣習)
    if re.match(r"^\d+\.[12]$", s):
        whole, frac = s.split(".")
        return f"{int(whole)}_{1 if frac == '1' else 2}/3"
    # "6.0" → "6_0"
    if re.match(r"^\d+\.0$", s):
        return f"{int(s.split('.')[0])}_0"
    # "6 1/3" / "6 2/3" → "6_1/3" / "6_2/3"
    m = re.match(r"^(\d+)\s+([12])/3$", s)
    if m:
        return f"{m.group(1)}_{m.group(2)}/3"
    # "6" → "6_0"
    if re.match(r"^\d+$", s):
        return f"{s}_0"
    return None  # parse 不能
```

### 2. extract_pitcher_team_stats での適用

既存 `extract_pitcher_team_stats` で innings 抽出時、生文字列でなく `normalize_innings()` 経由で正規化形式を返す。
比較側(`_check_pitcher_team_stat_confusion` / `check_consistency` 内 source/body 照合)も正規化形式で比較。

### 3. 244-followup subtype-aware severity との関係

- 244-followup の severity 判定は不変
- normalize_innings は extract 段階の精度向上のみ
- subtype 別 strict/lenient 分類は touch 不要

### 4. tests (narrow、新規 fixture 7-10 件、既存 fixture 不変)

- `test_normalize_innings_integer` (`6` → `6_0`)
- `test_normalize_innings_decimal_zero` (`6.0` → `6_0`)
- `test_normalize_innings_decimal_one_third` (`6.1` → `6_1/3`)
- `test_normalize_innings_decimal_two_third` (`6.2` → `6_2/3`)
- `test_normalize_innings_kanji_one_third` (`6回1/3` → `6_1/3`)
- `test_normalize_innings_space_one_third` (`6 1/3` → `6_1/3`)
- `test_normalize_innings_invalid_returns_none` (`abc` → None)
- `test_normalize_innings_null_returns_none` (None → None)
- `test_pitcher_innings_match_with_different_notations`(source `6.1` + body `6回1/3` → 一致判定)
- `test_pitcher_innings_mismatch_returns_fail`(source `6.1` + body `7.0` → 不一致判定維持)

### 5. write_scope (明示 stage、git add -A 厳禁)

- src/baseball_numeric_fact_consistency.py(narrow append)
- tests/test_baseball_numeric_fact_consistency.py(7-10 fixture 追加)

## 不可触

- 244 既存 hard_stop / review / pass 判定 logic
- 244-followup subtype-aware severity branch
- 244-B / 244-B-followup repair path
- 234-impl-* body_validator
- src/rss_fetcher.py / src/guarded_publish_evaluator.py / src/publish_notice_email_sender.py
- src/postgame_strict_template.py(247-QA、独立)
- env / Secret / Scheduler / Cloud Run / WP / X API / Gemini call 数
- 既存 fixture 1 件も変更しない、追加のみ
- ambient dirty 巻き込み

## デグレ防止 contract

- normalize_innings は **既存 extract_pitcher_team_stats の戻り値型を変えない**(string 戻り維持、内部正規化のみ)
- 比較 logic 内で normalize 経由にするだけ、既存 logic 不変
- normalize 失敗(None)時は既存挙動 fallback(従来通り生文字列比較)
- false positive(実際異なる innings を一致判定)1 件でも疑いがあれば実装止めて Claude に report
- false negative 改善(表記揺れで誤 mismatch)が主目的、保守側

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 2 file のみ stage、git add -A 禁止
2. **挙動**: 新規 fixture 全 pass、既存 fixture fail 0、pytest baseline 維持
3. **境界**: 244 / 244-B / 234-impl-* / Gemini call 数 / Cloud Run / Scheduler すべて不変

## commit message

`254-QA: pitcher innings notation normalization helper (6 / 6.0 / 6.1 / 6回1/3 unified) + fixtures`

## non-goals

- check_consistency の severity 判定変更
- subtype-aware severity logic 変更
- starter_innings 以外の数字正規化(score / hits 等は scope 外)
- score 正規化(別 ticket、本 ticket 範囲外)
