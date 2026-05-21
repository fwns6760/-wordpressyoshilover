# 418-QA 日刊ゲンダイ本文抜粋が短い meta fallback になる問題

## meta

- ticket: 418-QA-nikkan-gendai-source-body-excerpt
- status: LIVE_DEPLOYED_VERIFIED
- owner: Codex
- lane: B
- created: 2026-05-21
- GitHub Issue: PENDING (api.github.com connection failed from this environment)

## user request

2026-05-21 user:

- `https://www.nikkan-gendai.com/articles/view/sports/387913` の post `70027` で引用文字が少ない理由を確認。
- 既存 post `70027` は今後でよい。
- 自動 RSS と手動投入の両方に入れる。

## root cause

Cloud Logging confirmed manual-intake-service created / published post `70027` and source excerpt fell back to meta description:

- `source_body_excerpt_meta_fallback extractor_len=0 meta_len=55`
- `source_body_excerpt_inserted excerpt_len=55`

原因は `src/source_article_body_extractor.py` が `www.nikkan-gendai.com` の本文構造を拾えず、本文抽出結果が 0 文字になったこと。引用上限 `SOURCE_BODY_EXCERPT_MAX_CHARS = 1200` に当たったわけではない。

## scope

Write scope:

- `src/source_article_body_extractor.py`
- `tests/test_source_article_body_extractor.py`
- this ticket / board docs only

Runtime scope:

- deploy to `manual-intake-service`
- deploy to `yoshilover-fetcher`

Do not touch:

- existing WP post `70027`
- WordPress published articles
- Cloud Scheduler
- Secret Manager
- env vars / `RUN_DRAFT_ONLY`
- X / SNS / mail lanes
- unrelated dirty files

## implementation

- Add a `www.nikkan-gendai.com`-specific fallback inside the shared source body extractor.
- Anchor extraction around H1 / published date lines, then stop at pagination / ranking / site chrome markers.
- Keep this in `extract_article_body_excerpt` so both manual-intake-service and automatic RSS paths inherit the same behavior.
- Add a fixture-backed test that verifies Nikkan Gendai-style HTML returns article body text, not short meta description.

## validation

Repo checks:

- `python3 -m py_compile src/source_article_body_extractor.py tests/test_source_article_body_extractor.py`
- `python3 -m compileall src/source_article_body_extractor.py`
- AST parse over touched Python files
- `python3 -m pytest tests/test_source_article_body_extractor.py tests/test_source_article_body_extractor_balanced_div.py`
- `git diff --check -- src/source_article_body_extractor.py tests/test_source_article_body_extractor.py`

Deploy checks:

- manual-intake-service Cloud Build `554e10ac-ba83-4a34-9dd1-96ce8d2494a3` success
- yoshilover-fetcher Cloud Build `d21dac0a-7646-4067-a673-978572afb5b0` success
- manual-intake-service image `manual-intake-service:418-nikkan-563f92b`
- yoshilover-fetcher image `yoshilover-fetcher:418-nikkan-563f92b`
- manual-intake-service revision `manual-intake-service-00094-wf2` 100% traffic, `/health` -> `{"ok": true}`
- yoshilover-fetcher revision `yoshilover-fetcher-00466-tjs` 100% traffic, `/health` -> `OK`
- new revision ERROR logs 0 for both services after deploy

## status log

- 2026-05-21: root cause confirmed from GCP logs. Implemented shared extractor fallback and fixture test. Local targeted tests pass.
- 2026-05-21: deployed to both manual-intake-service and yoshilover-fetcher. Existing WP post `70027` was not modified.
