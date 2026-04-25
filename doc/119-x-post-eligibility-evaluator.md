# 119 x-post-eligibility-evaluator

## meta

- owner: Codex B
- lane: B
- priority: P0.5
- status: READY
- alias: PUB-005-A
- parent: PUB-005
- created: 2026-04-26

## purpose

WordPress 公開済み記事から、X 投稿してよい Green 記事だけを read-only で選ぶ。
X API / WP write / mail / LLM は一切使わず、X 解禁の最初の安全な入口にする。

## scope

- 公開済み WP 記事のみを対象にする
- PUB-002-A の Green 条件を満たす候補だけ `eligible`
- Yellow / Red / cleanup 前提記事は `refused`
- X-side Red 条件を満たす記事は `refused`
- 既存 107 / `src/x_post_template_candidates.py` は後続文案候補生成の土台として参照する
- JSON と human summary を出す

## non-goals

- X API live post
- WP write
- mail real-send
- LLM / Gemini / Grok / xAI
- X 検索 / X 収集
- Cloud Run / Scheduler / `RUN_DRAFT_ONLY`
- queue / ledger 作成(120)

## expected output

- `x_eligible`: `post_id`, `title`, `link`, `why_eligible`
- `x_refused`: `post_id`, `title`, `refuse_reasons`
- summary: total / eligible / refused / top refusal reasons

## X-side Red conditions

- primary source が弱い
- title が speculative
- title-body が一致しない
- injury / death / 登録抹消 / 診断 / 症状を含む
- 同一試合 / 同一選手の X 投稿が直近 24h で既出
- 4/17 事故と同質リスク
- 数値リスト型で検証が弱い
- quote-heavy で出典が弱い
- cleanup 前提の site component / dev log / H3 sentence collapse が残る

## acceptance

- published only
- Green only
- Yellow / Red refused
- X-side Red refused with reason
- JSON output and human summary exist
- tests cover eligible / refused / published-only / duplicate-like history cases
- WP write zero
- X API call zero
- secret read/display zero

## suggested files

- `src/x_post_eligibility_evaluator.py`
- `src/tools/run_x_post_eligibility_evaluator.py`
- `tests/test_x_post_eligibility_evaluator.py`

## verification

```bash
python3 -m pytest tests/test_x_post_eligibility_evaluator.py
python3 -m src.tools.run_x_post_eligibility_evaluator --fixture <fixture.json>
```
