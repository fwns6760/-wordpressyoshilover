# 071 Title-Body Nucleus Validator

## why_now

- 記事品質 contract の最上位は `title assembly -> subtype 境界 -> 本文ブロック順`
- 現在は title と body 冒頭の核ずれを全 subtype 横断で止める narrow validator がない
- 067 は comment lane 専用であり、全 subtype の title-body 核一致は別便で独立実装する

## purpose

- title の主語と事象が body 冒頭の主語と事象に整合しているかを rule-based に判定する
- LLM なし、runtime wiring なしで dry-run 観測できる最小 validator を追加する

## scope

- 新規 module `src/title_body_nucleus_validator.py`
- 公開 API は `validate_title_body_nucleus(title, body, subtype, *, known_subjects=None)`
- 新規 CLI `src/tools/run_title_body_nucleus_dry_run.py`
- 新規 test `tests/test_title_body_nucleus_validator.py`
- 対象 subtype は `postgame / lineup / manager / pregame / farm`
- 判定対象は title と body 冒頭 2-4 行の nucleus alignment のみ

## 判定軸

### 1. SUBJECT_ABSENT

- title 主語が body 冒頭 2-4 行に一度も現れない
- `known_subjects` があればその exact match を最優先する
- 監督表記やチーム別名は軽い同値判定を許容する

### 2. EVENT_DIVERGE

- title 主語と body 主語は同一だが、title 事象と body 事象の category が異なる
- closed set 優先で判定する
- 例: `昇格 vs 登板`, `先発 vs 2軍練習`, `15号 vs 守備`

### 3. MULTIPLE_NUCLEI

- body 冒頭段落に独立主語が 2 人以上あり、それぞれに独立事象が付く
- 1 記事 1 核違反として fail にする
- comment lane 固有 contract ではなく、全 subtype 共通の narrow 判定として扱う

## 主語抽出

- 優先順位は `known_subjects -> 公示番号/背番号 -> 巨人/ジャイアンツ -> 監督表記 -> 漢字名 -> カタカナ名`
- title は先頭寄りの match を採る
- body は独立主語 (`Xは`, `Xが`, `Xも`) を優先し、なければ一般 heuristic にフォールバックする

## 事象抽出

- closed set 優先
- 対象例: `登録`, `抹消`, `昇格`, `先発`, `4番起用`, `勝利`, `敗戦`, `引き分け`, `n号`, `n安打`, `n打点`, `登板`, `継投`, `采配`, `守備`, `練習`
- fallback は末尾動詞句 heuristic

## subtype 補助

- `postgame`: body 冒頭に `勝 / 敗 / 引き分け / score` の result support があるかを見る
- `lineup / pregame`: body 冒頭に `先発オーダー / スタメン / 先発投手 / 予告先発` 系の signal があるかを見る
- `manager`: 監督主語を body 主語抽出で優先する
- `farm`: body 冒頭で `一軍` signal が強く、`二軍 / 2軍 / ファーム` signal がない混在を fail 補助に使う

## 出力 schema

```python
NucleusAlignmentResult(
    aligned: bool,
    title_subject: str | None,
    title_event: str | None,
    body_subject: str | None,
    body_event: str | None,
    reason_code: str | None,
    detail: str | None,
)
```

- pass は `aligned=True`, `reason_code=None`
- fail は `reason_code in {SUBJECT_ABSENT, EVENT_DIVERGE, MULTIPLE_NUCLEI}`
- `detail` は opening excerpt や category 差分の短い説明に限定する

## non_goals

- runtime pipeline への接続
- automation.toml / scheduler / env / secret 変更
- LLM 判定、外部 API 呼び出し、形態素解析導入
- published 記事の修正や WP 書込
- 067 / 068 / 041 / 061-P1 / 063 lane の変更や再利用

## success_criteria

- validator が pure Python stdlib のみで動作する
- dry-run CLI が fixture JSON を読んで ok/fail preview を出せる
- `SUBJECT_ABSENT / EVENT_DIVERGE / MULTIPLE_NUCLEI / known_subjects 優先` の test が通る
- happy path で `postgame / lineup / manager` を通し、suite 全体も崩さない

## acceptance_check

1. `ast.parse` で `src/title_body_nucleus_validator.py` が parse clean
2. `tests/test_title_body_nucleus_validator.py` が 12 case 以上 pass
3. pytest collection errors が 0
4. full suite pass
5. dry-run fixture 6 件で `aligned=3 / failed=3` を確認
6. staged files は本 ticket の 4 file のみ
7. 067 / 068 / 041 / 061-P1 / 063 front / automation.toml / doc/062 / doc/067 は diff 0
