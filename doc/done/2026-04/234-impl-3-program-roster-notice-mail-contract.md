---
ticket: 234-impl-3
title: 234 contract 反映(program_notice / roster_notice の mail UX narrow 反映)
status: CLOSED
owner: Codex A
priority: P1
lane: A
ready_for: codex_a_fire
created: 2026-04-29
related: 234-impl-1 (CLOSED)、234-impl-2 (CLOSED)、244 (CLOSED)
---

## 背景

234 contract `notice` / `program` subtype は CLOSED。234-impl-3 は notice / program subtype 内の **program_notice (番組告知)** と **roster_notice (出場選手登録系)** を narrow helper で識別し、234 contract 通り保守的な mail UX に倒す。

234-impl-2 と同じ helper pattern (subtype exact match + marker 検出 + override review 倒し)。

## scope (narrow)

### 1. src/publish_notice_email_sender.py (helper 追加 + mail UX 倒し override)

#### 1-A. 識別 helper:

```python
_PROGRAM_NOTICE_MARKER_RE = re.compile(r"(放送|配信|GIANTS TV|オンエア|テレビ|ラジオ|番組|出演)")
_ROSTER_NOTICE_MARKER_RE = re.compile(r"(出場選手登録|登録抹消|一軍登録|二軍降格|戦力外|引退|公示)")

def _is_program_notice(title: str, summary: str, subtype: str) -> bool:
    """subtype が `program` または `notice` で program marker hit"""
    normalized = str(subtype or "").strip().lower()
    if normalized not in {"program", "notice"}:
        return False
    blob = f"{title or ''}\n{summary or ''}"
    return bool(_PROGRAM_NOTICE_MARKER_RE.search(blob))

def _is_roster_notice(title: str, summary: str, subtype: str) -> bool:
    """subtype が `notice` で roster marker hit (program subtype は除外)"""
    normalized = str(subtype or "").strip().lower()
    if normalized != "notice":
        return False
    blob = f"{title or ''}\n{summary or ''}"
    return bool(_ROSTER_NOTICE_MARKER_RE.search(blob))
```

#### 1-B. mail UX 倒し override (`_resolve_mail_state` 周辺):

- `_is_program_notice` hit:
  - 234 contract: 投稿候補は出さない、`x_post_ready=false` 強制、`mail_class="review"`、reason=`program_notice_review`、prefix=`【要確認】`
  - body / summary に `日付` / `時刻` / `番組名` のいずれも無い場合のみ強制(完全 source 通りなら通常 path 維持)
- `_is_roster_notice` hit:
  - 234 contract: notice 系は基本 review 倒し、`x_post_ready=false` 強制、`mail_class="review"`、reason=`roster_notice_review`、prefix=`【要確認】`
  - 既存 path 既に review 倒しになっていれば touch しない(diff 0)
- 既存 `_first_team_subtype_review_reason` (234-impl-2) と同じ位置で chain 評価、衝突なし

### 2. tests/test_publish_notice_email_sender.py (5 fixture 追加、既存 fixture 不変)

- `test_program_notice_helper_hits_for_giants_tv_subject`
- `test_program_notice_review_forces_x_post_off`
- `test_roster_notice_helper_hits_for_registration`
- `test_roster_notice_review_forces_x_post_off`
- `test_clean_program_with_full_metadata_keeps_x_candidate` (regression: 完全 source 揃った program は通常 path 維持)

## 不可触

- subtype 文字列追加 (`program_notice` / `roster_notice` を src 識別子として使わない、helper 関数内 marker のみ)
- src/fixed_lane_prompt_builder.py / src/body_validator.py touch 禁止 (impl-5/6 scope)
- src/guarded_publish_evaluator.py / 244 / 242-B / 243 touch
- Gemini call 追加 / prompt 改修
- env / Secret / Scheduler / Cloud Run / WP REST
- 既存 fixture 1 件も変更しない

## acceptance (3 点 contract)

1. **着地**: 1 commit に src/publish_notice_email_sender.py + tests/test_publish_notice_email_sender.py のみ stage
2. **挙動**: 新規 5 fixture 全 pass、既存 fixture fail 0、234-impl-1/2 + 244 path 不変
3. **境界**: classify / 識別 logic / publish gate / Gemini / Cloud Run 不変

## commit message

`234-impl-3: program_notice / roster_notice mail UX narrow + fixtures`
