---
ticket: 234-impl-7
title: 234 contract 反映(probable_starter / pregame の本文 hardening)
status: READY_FOR_AUTH_EXECUTOR
owner: Codex B
priority: P1
lane: B
ready_for: image_rebuild_after_commit
created: 2026-04-29
related: 234-impl-5 (postgame body hardening、CLOSED)、234-impl-6 (farm body hardening、CLOSED)
---

## 背景

2026-04-29 update:

- implementation landed in repo worktree and targeted tests passed
- live反映は fetcher / draft-body-editor image rebuild 側の判断に分離
- env / Scheduler / Secret / WP / RUN_DRAFT_ONLY は変更しない

234-impl-5/6 で postgame / farm_result / farm_lineup の本文 hardening 完了。
234-impl-7 は **試合前系**(probable_starter / pregame)に同 pattern narrow 適用。

試合前段階で AI が **未確定 score / 未確定 lineup / 推測投手名** を勝手に書くのを抑止。

## scope (narrow、最小 diff、4 file 想定)

### 1. src/fixed_lane_prompt_builder.py (`probable_starter` contract `fallback_copy` 強化)

`CONTRACTS["probable_starter"]` の `fallback_copy` tuple に **2 行追加**(既存行不変):
- `"source/meta にない数字(過去の通算成績、防御率、勝敗数等)を本文に書かない。numeric weak の場合は『公式発表待ち』『source 記載なし』で止める。"`
- `"source/meta にない選手名(対戦相手の打者名、控え選手名等)を本文に書かない。先発・予告投手以外の名前は推測で足さない。"`

234-impl-5/6 で追加した postgame / farm_result の fallback_copy は **1 行も touch しない**。
他 CONTRACTS (program / notice) も touch しない。

`pregame` 用に新規 contract は **作らない**(subtype 文字列追加禁止)。

### 2. src/body_validator.py (probable_starter / pregame post-gen check)

#### 2-A. FAIL_AXES に追加 (impl-5/6 entry の隣):
- `"pregame_score_fabrication"` (試合前なのに score を本文に書く = 嘘)
- `"pregame_pitcher_name_unverified"` (source にない先発投手名を本文に書く)
- `"pregame_lineup_fabrication"` (確定前 lineup を本文に書く)

#### 2-B. helper 関数追加 (impl-5/6 helper 隣接位置):

```python
_PREGAME_SCORE_BAN_RE = re.compile(r"\d+\s*[-対]\s*\d+")  # score 表記
_LINEUP_FABRICATION_MARKER_RE = re.compile(r"(1番|2番|3番|4番|5番)")  # 確定前 lineup

def _is_pregame_or_probable_starter(title: str, body_text: str, subtype: str) -> bool:
    normalized = str(subtype or "").strip().lower()
    return normalized in {"pregame", "probable_starter"}

def _validate_pregame_anchor(
    title: str,
    body_text: str,
    source_context: dict | None,
    subtype: str,
) -> list[str]:
    fail_axes: list[str] = []
    if not _is_pregame_or_probable_starter(title, body_text, subtype):
        return fail_axes

    source_blob = " ".join(_source_ref_texts(source_context or {}))

    # score fabrication: source に score 表記が無いのに body に score がある
    body_scores = set(_PREGAME_SCORE_BAN_RE.findall(body_text))
    source_scores = set(_PREGAME_SCORE_BAN_RE.findall(source_blob))
    if body_scores - source_scores:
        fail_axes.append("pregame_score_fabrication")

    # pitcher name fabrication: source にない選手名が「先発」「予告」近接で出る
    body_names = set(re.findall(r"[一-龥々ァ-ヴーA-Za-z]{2,10}", body_text))
    source_names = set(re.findall(r"[一-龥々ァ-ヴーA-Za-z]{2,10}", source_blob))
    suspect_names = body_names - source_names
    for name in suspect_names:
        for keyword in ("先発", "予告", "予定"):
            pos = body_text.find(name)
            if pos < 0:
                continue
            window = body_text[max(0, pos-15):pos+len(name)+15]
            if keyword in window:
                fail_axes.append("pregame_pitcher_name_unverified")
                break
        if "pregame_pitcher_name_unverified" in fail_axes:
            break

    # lineup fabrication: source に「1番〜」が無いのに body にある
    if _LINEUP_FABRICATION_MARKER_RE.search(body_text) and not _LINEUP_FABRICATION_MARKER_RE.search(source_blob):
        fail_axes.append("pregame_lineup_fabrication")

    return fail_axes
```

#### 2-C. validator 統合:

- 既存 `validate_body_candidate` 内、impl-5/6 の subtype 別 dispatch 隣に追加:
  ```python
  if subtype in ("pregame", "probable_starter"):
      fail_axes.extend(_validate_pregame_anchor(title, body_text, source_context, subtype))
  ```
- 既存 fail_axes 検出 logic は不変、追加のみ
- 234-impl-5 (postgame) / 234-impl-6 (farm) との subtype 別 disjoint 担保

### 3. tests (4 fixture 追加、既存 fixture 不変)

`tests/test_body_validator.py` に追加:
- `test_pregame_score_fabrication_blocks` (source 無 score、body に `1-2` → fail)
- `test_pregame_pitcher_name_unverified_blocks` (source にない選手が「先発」近接 → fail)
- `test_pregame_with_full_source_facts_passes` (regression: good full-source pregame、fail 0)
- `test_probable_starter_with_only_official_pitcher_passes` (regression: probable_starter で source 投手のみ → fail 0)

`tests/test_fixed_lane_prompt_builder.py` に optional 1 fixture:
- `test_probable_starter_contract_fallback_copy_includes_no_fabrication_anchor`

## 不可触

- 234-impl-5 で追加した postgame fail_axis / fallback_copy / helper は 1 行も変更しない
- 234-impl-6 で追加した farm fail_axis / fallback_copy / helper は 1 行も変更しない
- src/publish_notice_email_sender.py touch 禁止 (impl-3/4 scope)
- 244 / 244-B / 244-followup / 244-B-followup / 242-B / 243 系 既存 logic 不変
- subtype 文字列追加禁止
- Gemini call 追加 / prompt 改修
- env / Secret / Scheduler / WP / RUN_DRAFT_ONLY
- 既存 fixture 1 件も変更しない、追加のみ

## デグレ防止 contract

- 既存 fixture 全件 pass を維持
- regression fixture (good full-source pregame、source 投手のみ probable_starter) で「本 ticket で挙動変わらない」担保
- impl-5/6 subtype (postgame / farm_result / farm_lineup) との衝突なし(subtype 別 disjoint check)
- false positive 1 件でも疑いがあれば実装止めて Claude に report

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 4 file のみ stage、git add -A 禁止
2. **挙動**: 新規 fixture 全 pass、既存 fixture fail 0、pytest baseline 維持
3. **境界**: publish_notice_email_sender / 評価 logic / Gemini / Cloud Run 不変

## commit message

`234-impl-7: probable_starter/pregame body hardening (source anchor + post-gen check) + fixtures`
