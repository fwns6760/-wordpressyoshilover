# 299-QA flaky analysis

Date: 2026-05-01 JST  
Lane: Codex A (read-only / doc-only)  
Scope: `tests/test_postgame_strict_template.py` flaky / transient investigation only

## Summary

- Primary hypothesis: this is a `GeminiCacheManager` side-effect, not a product logic regression.
- The unstable surface is the strict slotfill cache path inside [`src/rss_fetcher.py`](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:4929), especially `_gemini_text_with_cache(...)` before the parse/review fallback.
- The target tests patch `_request_gemini_strict_text`, but they do **not** patch `_gemini_text_with_cache` or `_get_gemini_cache_manager`, so a warmed cache can bypass the mocked `raw_text`.
- Local evidence supports:
  - `0 failures` when the module is run from a fresh process in the current shell.
  - `1 pass / 2 fails` when the listed 3 tests are run in order in one process, because the first success-path test warms the strict cache and the next two sentinel tests read from that cache.
- Morning `3 failures` is most consistent with the same cache already being warm before the module started, or with a cache visibility difference between shells/executors.

## Target tests

Observed morning failures from `docs/ops/OPS_BOARD.yaml`:

1. `test_strict_feature_flag_on_postgame_uses_strict_template_path`
2. `test_strict_on_empty_response_returns_review_sentinel`
3. `test_strict_on_parse_fail_returns_review_sentinel`

Relevant implementation path:

- [`src/rss_fetcher.py:4929`](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:4929) strict postgame branch enters `_gemini_text_with_cache(...)`
- [`src/rss_fetcher.py:4981`](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:4981) parse result
- [`src/rss_fetcher.py:4983`](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:4983) `postgame_strict: parse_fail reason=%s -> review`
- [`src/postgame_strict_template.py:87`](/home/fwns6/code/wordpressyoshilover/src/postgame_strict_template.py:87) `parse_postgame_strict_json`
- [`src/rss_fetcher.py:4566`](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:4566) `_gemini_text_with_cache`
- [`src/rss_fetcher.py:4416`](/home/fwns6/code/wordpressyoshilover/src/rss_fetcher.py:4416) `_get_gemini_cache_manager`
- [`src/gemini_cache.py:89`](/home/fwns6/code/wordpressyoshilover/src/gemini_cache.py:89) `GeminiCacheManager`

## What the tests actually depend on

The sentinel helper in [`tests/test_postgame_strict_template.py:115`](/home/fwns6/code/wordpressyoshilover/tests/test_postgame_strict_template.py:115) patches:

- `_build_source_fact_block`
- `_request_gemini_strict_text`
- `_postgame_strict_validate`
- `_postgame_strict_has_sufficient_for_render`
- `_postgame_strict_render`
- `_validate_body_candidate`

It does **not** patch:

- `_gemini_text_with_cache`
- `_get_gemini_cache_manager`

That means the mocked `raw_text=""` and `raw_text="not-json"` are only used when cache lookup misses. If cache hits, the tests stop observing their own patched `raw_text`.

## Local evidence

### Pytest run 1

Command:

```bash
python3 -m pytest tests/test_postgame_strict_template.py -q
```

Result:

- `30 passed, 0 failed`
- current shell did **not** reproduce the morning `3 failures` with the full module run

### Pytest run 2

Command:

```bash
python3 -m pytest \
  tests/test_postgame_strict_template.py::PostgameStrictTemplateTests::test_strict_feature_flag_on_postgame_uses_strict_template_path \
  tests/test_postgame_strict_template.py::PostgameStrictTemplateTests::test_strict_on_empty_response_returns_review_sentinel \
  tests/test_postgame_strict_template.py::PostgameStrictTemplateTests::test_strict_on_parse_fail_returns_review_sentinel \
  -q
```

Result:

- `1 passed, 2 failed`
- `test_strict_feature_flag_on_postgame_uses_strict_template_path`: passed
- `test_strict_on_empty_response_returns_review_sentinel`: failed
- `test_strict_on_parse_fail_returns_review_sentinel`: failed

Failure shape:

- both failing tests returned a normal success tuple
- they did **not** return `_PostgameStrictReviewFallback`
- this is consistent with cached strict JSON being reused instead of the test’s patched `raw_text`

## Reproduction interpretation

### Confirmed minimal reproduction in current shell

The 3-test command above reproduces the flaky behavior in a narrow way:

1. `test_strict_feature_flag_on_postgame_uses_strict_template_path` executes the strict success path and saves a strict slotfill response for `https://example.com/postgame`.
2. The next two tests reuse the same `source_url` and same `prompt_template_id` (`postgame_strict_slotfill_v1`).
3. `_gemini_text_with_cache(...)` returns cached/generated strict JSON before `_request_gemini_strict_text` can return `""` or `"not-json"`.
4. The sentinel assertions fail because the function returns a normal rendered tuple.

### Why this is transient

It depends on cache visibility and process history:

- If the process starts without a visible strict cache entry, the first success-path test can pass.
- Once that process has warmed the strict cache, later tests in the same process can fail.
- If a cache entry is already visible at process start, all 3 morning failures become plausible:
  - the first test can fail because `mock_request.assert_called_once()` is bypassed
  - the next two can fail because they receive cached success JSON instead of sentinel-triggering raw text

## Concrete cache evidence

- strict cache local path currently present:
  - `/tmp/gemini_cache/29/292fe03766cd9637.json`
- `292fe03766cd9637` is the source hash for `https://example.com/postgame`
- cached prompt template id in that file:
  - `postgame_strict_slotfill_v1`
- cached content hash observed in the file:
  - `982f657e7c7b2ccca6df500a9b3a124a006af39ad997f3e9c33077110cbf570d`
- that content hash matches the strict success-path test’s full `source_block`

The current file content after local reproduction was updated at roughly `2026-05-01 13:31 JST`, which aligns with the success-path test warming the cache during this investigation.

## Order / env / parallel assessment

### Most likely root cause

`cache + process order + shared source_url`

This is the strongest explanation because:

- the failing tests share the same `source_url`
- the strict branch uses a shared cache manager
- the tests mock the inner request, not the cache wrapper
- the narrow 3-test run reproduces the two sentinel failures immediately after the success-path test

### Env dependency

Also plausible and probably part of the morning/noon split.

Reason:

- [`src/gemini_cache.py:103`](/home/fwns6/code/wordpressyoshilover/src/gemini_cache.py:103) uses `GeminiCacheManager.from_env()`
- [`src/gemini_cache.py:204`](/home/fwns6/code/wordpressyoshilover/src/gemini_cache.py:204) may consult GCS through `GCSStateManager.download(...)` when `gcloud` is on PATH
- [`src/cloud_run_persistence.py:119`](/home/fwns6/code/wordpressyoshilover/src/cloud_run_persistence.py:119) returns `False` on missing remote object, and [`src/gemini_cache.py:210`](/home/fwns6/code/wordpressyoshilover/src/gemini_cache.py:210) then unlinks the local file before parsing
- if GCS visibility/auth/missing-object behavior differs by shell or executor, the first lookup can alternate between:
  - cache visible
  - cache bypassed
  - local cache pruned

That explains how:

- morning Claude run could see `3 failures`
- noon/current full-module run could see `0 failures`

### File race

Secondary only.

There is no locking in [`src/gemini_cache.py:217`](/home/fwns6/code/wordpressyoshilover/src/gemini_cache.py:217) when writing `/tmp/gemini_cache/...json`, so concurrent workers could race. But the reproduced failure shape is a clean success-tuple reuse, not a corrupted JSON/cache-file symptom.

### Random / time-dependent logic

Low confidence as primary cause.

- no randomness is involved in the strict parse/review branch
- no clock-based branching exists in the failing parse path itself
- time only matters indirectly through cache cooldown and cache visibility

### `pytest-xdist` / parallel-N

- local check: `xdist_installed=0`
- I could not run an xdist reproduction in this environment
- theoretical risk remains if another executor uses parallel workers because `/tmp/gemini_cache` is shared and unlocked

## Reproduction conditions to record

### Reproduces

- run the 3 listed tests in one process, with the success-path test first
- keep the same `source_url` (`https://example.com/postgame`)
- allow the real `_gemini_text_with_cache(...)` and real cache manager path to run

### Reproduces all 3 morning failures

Most likely when:

- a strict cache entry for the same `source_url` + `postgame_strict_slotfill_v1` is already visible before the test module starts

### Does not reproduce reliably

- fresh process / full module run where the first lookup misses or bypasses the cache
- shells/executors where GCS-backed cache visibility differs

## OBSERVE vs real P0/P1

Keep this as `P3 OBSERVE`, not a real P0, while all of the following stay true:

1. production behavior shows no article-generation outage and no live content corruption tied to this path
2. failure stays local to pytest and depends on cache/process history
3. full-module regression gates continue to show `0 failure increase`
4. no new test outside `tests/test_postgame_strict_template.py` starts failing from the same cause
5. no evidence appears that live `postgame_strict` is routing good articles to review incorrectly at runtime

Escalate above `P3` only if one of these changes:

1. full pytest starts failing reproducibly from a clean process
2. morning/noon variance disappears and the same command fails deterministically
3. production observe shows real `postgame_strict` review-routing regressions

## Close condition proposal

Recommended close threshold: `N = 3` consecutive `0 failure` observations for the official module gate:

```bash
python3 -m pytest tests/test_postgame_strict_template.py -q
```

Close only when all are true:

1. the module gate above is `0 failures` for 3 consecutive fresh-process runs
2. no new `299-QA` evidence is added in `production_health_observe`
3. full pytest shows no increase attributable to `postgame_strict`

Reason for `N = 3`:

- same-day evidence already swung from `3 failures` to `0 failures`
- `N = 2` is too weak for a cache/history-sensitive flaky
- `N = 3` is enough for a `P3 OBSERVE` close without pretending the diagnostic trio is solved by code

## Conclusion

- Best current root-cause hypothesis: shared strict cache, not parser logic.
- The narrow local reproduction is real (`1 pass / 2 fails`) and lines up with test order.
- The exact morning `3 failures` likely needed a pre-warmed cache visible before test start, or different cache visibility in Claude’s shell.
- Current recommendation: keep `299-QA` in `OBSERVE`, record this as cache/process-history-sensitive, and use the next `production_health_observe` at `2026-05-01 17:00 JST` as the close checkpoint.
