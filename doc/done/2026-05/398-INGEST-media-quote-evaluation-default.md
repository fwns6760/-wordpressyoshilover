# 398-INGEST media_quote_evaluation default guard

## meta

- ticket: 398-INGEST-media-quote-evaluation-default
- status: CLOSED
- owner: Codex A
- lane: A
- priority: P0.5
- created: 2026-05-20
- github_issue: #73
- parent_observation: 395 manual YouTube run

## user request

`media_quote_evaluation` error has candidate-loss risk, so fix it.

## live evidence

2026-05-20 11:02 JST manual fetcher run:

- log: `[ERROR] 公開失敗: cannot access local variable 'media_quote_evaluation' where it is not associated with a value`
- same run created official YouTube draft `post_id=69846`, so this is not a
  YouTube intake failure.
- risk: one non-YouTube/X candidate was counted as error, and repeated errors
  could reduce useful draft creation before the request-level timeout.

## scope

- Add per-entry safe defaults for `media_quote_evaluation` and `media_quotes`.
- Keep existing media quote selector behavior unchanged when it runs normally.
- Make post-create observability logging safe when a branch leaves no selector
  result.

## write scope

- `src/rss_fetcher.py`
- `tests/test_rss_fetcher_media_quote_defaults.py`
- `doc/active/398-INGEST-media-quote-evaluation-default.md`
- `doc/README.md`
- `doc/active/assignments.md`

## do not touch

- Cloud Run env / Secret Manager
- Cloud Scheduler config
- `RUN_DRAFT_ONLY`
- WP existing posts
- X live posting
- frontend files
- unrelated staged changes for other tickets

## implementation summary

- Added per-entry safe defaults:
  - `media_quote_evaluation = {"quotes": [], "selector_type": "none", "is_target": False}`
  - `media_quotes = []`
- Kept normal selector behavior unchanged, but made the selector assignment
  tolerate a falsey result and read quotes via safe `.get("quotes")`.
- Added a regression guard test that keeps the defaults before selector
  evaluation and post-create media quote logging.

## validation evidence

- `python3 -m unittest tests.test_rss_fetcher_media_quote_defaults tests.test_media_xpost_selector tests.test_media_xpost_observation_logs` passed: 27 tests.
- `python3 -m compileall src/rss_fetcher.py tests/test_rss_fetcher_media_quote_defaults.py` passed.
- `git diff --check -- src/rss_fetcher.py tests/test_rss_fetcher_media_quote_defaults.py doc/active/398-INGEST-media-quote-evaluation-default.md doc/README.md doc/active/assignments.md` passed.
- commit `6969375` (`398: guard media quote evaluation defaults`).
- Cloud Build `14880fed-c77f-44a1-b168-b5705561bf12` SUCCESS.
- image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:398-media-quote-default-6969375`.
- image digest `sha256:67df1d62ad72f6ae76fd952ef3c2e2c2ca7807cbdd1feb5f7260965d6dd75337`.
- Cloud Run service `yoshilover-fetcher` deployed to revision `yoshilover-fetcher-00452-glk`, latest revision 100% traffic.
- `/health` returned `OK`.
- New revision startup log observed; new revision ERROR log count 0.

## next action

Closed on 2026-05-20 after deploy / health / ERROR 0 verification.
Natural fire acceptance observation is not held in this ticket; create a separate ticket if needed.
