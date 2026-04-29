---
ticket: 234-impl-4
title: 234 contract 反映(injury_recovery_notice / default_review の mail UX narrow 反映)
status: CLOSED
owner: Codex A (Round 2)
priority: P1
lane: A
ready_for: codex_a_fire (after 234-impl-3)
created: 2026-04-29
related: 234-impl-3 (program_notice / roster_notice、同 file 連続 commit)
---

## 背景

234-impl-3 の同 file (publish_notice_email_sender.py) 連続 narrow 追加。`injury_recovery_notice` と `default_review` を helper で識別 + mail UX 倒し。

## scope (narrow)

### 1. src/publish_notice_email_sender.py (helper 追加 + override)

#### 1-A. 識別 helper:

```python
_INJURY_RECOVERY_MARKER_RE = re.compile(r"(怪我|負傷|離脱|戦線復帰|復帰|右肩|左肩|右肘|左肘|手術|リハビリ|抹消|登録抹消)")
_DEFAULT_REVIEW_MARKER_SUBTYPES = frozenset({"default", "general", "unknown", ""})

def _is_injury_recovery_notice(title: str, summary: str, subtype: str) -> bool:
    """subtype が `notice` で injury / recovery marker hit"""
    normalized = str(subtype or "").strip().lower()
    if normalized != "notice":
        return False
    blob = f"{title or ''}\n{summary or ''}"
    return bool(_INJURY_RECOVERY_MARKER_RE.search(blob))

def _is_default_review(subtype: str) -> bool:
    """subtype が default / unresolved / 不明、234 contract で原則 review 倒し"""
    normalized = str(subtype or "").strip().lower()
    return normalized in _DEFAULT_REVIEW_MARKER_SUBTYPES
```

#### 1-B. mail UX 倒し override:

- `_is_injury_recovery_notice` hit:
  - source に診断名 / 復帰見込み が無い場合は強制 review (234 contract: 推測禁止、source 通り)
  - reason=`injury_recovery_notice_review`、prefix=`【要確認】`、x_post_ready=false
  - source に診断 / 復帰見込みが完全に揃っている場合は通常 path (false positive 回避)
- `_is_default_review` hit:
  - 234 contract: default は原則 x_post_ready=false、mail_class=review
  - reason=`default_review`、prefix=`【要確認】`
  - 既存 default path が既に review 倒しなら touch しない

### 2. tests (5 fixture 追加、既存 fixture 不変)

- `test_injury_recovery_notice_helper_hits_for_kega_marker`
- `test_injury_recovery_notice_review_forces_x_post_off`
- `test_default_review_helper_hits_for_unknown_subtype`
- `test_default_review_forces_x_post_off`
- `test_clean_injury_with_full_diagnosis_keeps_x_candidate` (regression)

## 不可触

- src/fixed_lane_prompt_builder.py / src/body_validator.py (impl-5/6 scope)
- 234-impl-3 で追加した helper を 1 行も変更しない、新規追加のみ
- subtype 文字列追加禁止
- その他 234-impl-1/2 / 244 / 242-B / 243 / 244-B 既存 logic 不変

## acceptance (3 点 contract)

1. **着地**: 1 commit に src/publish_notice_email_sender.py + tests/test_publish_notice_email_sender.py のみ
2. **挙動**: 新規 5 fixture 全 pass、既存 fixture fail 0
3. **境界**: 234-impl-3 helper / 既存 review path / Gemini / Cloud Run 不変

## commit message

`234-impl-4: injury_recovery_notice / default_review mail UX narrow + fixtures`
