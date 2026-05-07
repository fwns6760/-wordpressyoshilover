---
ticket: 250-QA-1
title: manager / coach / player_comment 系で quote_count=0 の本文生成を止めて review 倒し
status: READY
owner: Codex B
priority: P0(user 手直し負担軽減、即効)
lane: B
ready_for: codex_b_fire
created: 2026-04-29
related: 247-QA / 234-impl-3/4 / post 63952 実例
---

## 背景

post 63952 (4/29 13:51 JST、subtype=manager) の実生成内容で **致命的問題**:

- title「前日コメント整理 ベンチ関連の発言ポイント」(人名なし、generic)
- body: `quote_count: 0` のまま render → LLM 自由作文で「2026 年シーズン好調…」「ベンチ内の連携も重要」等の **source にない展望・一般論 padding**
- 川相 (source X 投稿に存在)が「コーチ」とだけ抽出されて人名落ち
- **234-impl-* / 244 / 247-QA いずれもカバーされていない layer**(247-QA は postgame のみ)

→ user の手直し原因の主要源、即塞ぐ必要

## 目的

manager / coach / player_comment 系 subtype で **quote_count == 0 の本文生成を止める**(review 倒し、legacy 自由生成へ戻さない、publish しない)。

publish 数より user 手直し削減を優先。

## scope (narrow、最小 diff、2 file)

### 1. src/rss_fetcher.py(narrow append)

#### 1-A. `manager_body_template_applied` emit 直前(or template render entry)で gate 判定

```python
# 既存 manager body 生成 logic 周辺で:
MANAGER_QUOTE_REVIEW_SUBTYPES = frozenset({"manager", "coach", "player_comment", "player_quote", "manager_quote", "coach_quote"})

def _should_review_zero_quote_manager(article_subtype: str, quote_count: int) -> bool:
    """quote_count=0 で manager / coach / player_comment 系なら review 倒し対象"""
    return (
        str(article_subtype or "").strip().lower() in MANAGER_QUOTE_REVIEW_SUBTYPES
        and int(quote_count) == 0
    )
```

#### 1-B. 既存 manager body template render 直前で判定

manager_body_template_applied event の emit 直前(or 該当 helper の入口)で:

```python
if _should_review_zero_quote_manager(article_subtype, quote_count):
    logger.warning(json.dumps({
        "event": "manager_quote_zero_review",
        "subtype": article_subtype,
        "title": title,
        "source_name": source_name,
        "reason": "quote_count_zero",
    }, ensure_ascii=False))
    # 247-QA-amend pattern: legacy 自由生成へ戻さず review 倒し
    # 既存 review path reuse(skip filter / draft 抑止 / publish skip 経路)
    return _existing_review_skip_path(...)
```

`_existing_review_skip_path` は 247-QA-amend で reuse した既存資産:
- `_log_article_skipped_post_gen_validate` + 既存 `continue` draft-suppress branch
- 新規 review path 作らない

### 2. tests narrow(既存 fixture 不変、新規 4-5 件追加)

`tests/test_rss_fetcher_*.py`(該当 test file、grep で確認):

- `test_manager_zero_quote_routes_to_review`(subtype=manager, quote_count=0 → review)
- `test_coach_zero_quote_routes_to_review`(subtype=coach, quote_count=0 → review)
- `test_player_comment_zero_quote_routes_to_review`
- `test_manager_with_quote_renders_normally`(subtype=manager, quote_count>0 → 既存 path 維持)
- `test_postgame_zero_quote_unaffected`(subtype=postgame で quote_count=0 → 本 ticket 対象外、既存挙動)

## 不可触

- postgame / lineup / farm / pregame / probable_starter / notice / program subtype は touch 禁止
- 247-QA strict path / postgame_strict_template.py touch 禁止
- 234-impl-* body_validator touch 禁止
- 244 / 244-followup / 244-B / 244-B-followup touch 禁止
- 既存 manager body template logic 本体は touch 禁止(judgment 1 つ追加のみ)
- LLM call 追加 / Gemini retry / 新 LLM
- Cloud Run / Scheduler / Secret / X API / WP REST 設定変更
- 既存記事本文の変更
- ambient dirty 巻き込み

## デグレ防止 contract

- review fallback は 247-QA-amend で実証済 path reuse(新 path 作らない)
- 既存 caller (`manager_body_template_applied`) は判定通過時 全く同じ挙動
- LLM call 数 0 増(template 生成 skip だけ、Gemini 呼ばれていれば既に呼ばれた後の判定)
- false positive(良 manager 記事を review 倒し)= quote_count>0 なら通す設計、low risk
- log は明示(後段で集計可能)

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 2 file のみ stage、git add -A 禁止
2. **挙動**: 新規 5 fixture pass、既存 fixture fail 0、postgame / lineup / farm 等 完全不変
3. **境界**: 247-QA / 234-impl-* / 244 / Cloud Run / Scheduler すべて不変

## commit message

`250-QA-1: manager/coach/player_comment quote_count=0 review fallback (LLM 自由作文 padding 抑止)`

## 完了報告 (必須)

- changed files (path + 行数)
- _should_review_zero_quote_manager signature + 対象 subtype list
- judgment 追加位置(file:line)
- review fallback 経路(247-QA-amend reuse 確認)
- 新規 fixture pass + 既存 fixture pass
- pytest collect / pass / fail (全体 baseline 比、scope 外 既存 fail は本 ticket 関係なし明記)
- LLM call 数 0 増 確認 (yes/no)
- postgame / lineup / farm 不変 確認 (yes/no)
- false positive 候補 0 (yes/no)
- commit hash
- next Claude 判断: push、250-QA-3 sequential fire
