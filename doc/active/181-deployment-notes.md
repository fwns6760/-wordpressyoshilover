# 181 deployment notes

## Scope

- ticket: 181 readability audit + narrow fix
- branch base: `52d34ac`
- hard constraints respected:
  - no WP write
  - no Cloud Run deploy
  - no push
  - no new dependency
  - no touch:
    - `src/repair_fallback_controller.py`
    - `tests/test_repair_fallback_controller.py`
    - `doc/active/178-codex-primary-wp-write-enable.md`

## Audit input

- spec requested: latest 50 `publish` posts via WP REST GET
- sandbox result: live WP GET failed because `yoshilover.com` name resolution was unavailable in this environment
- failing smoke:

```text
RuntimeError: [WP] request failed after 4 attempts (記事一覧取得 status=publish):
ConnectionError(MaxRetryError(... Failed to establish a new connection:
[Errno -2] Name or service not known))
```

- fallback used for this ticket audit:
  - `logs/guarded_publish_history.jsonl`
  - `logs/cleanup_backup/*.json`
- sample selection:
  - `status=sent`
  - backup file exists
  - sorted by `sent_at || ts` desc
  - latest 50 published snapshots only

## Audit result

5-axis audit was run against backup `title.rendered` and rendered body text. For lead detection, branding / link / heading lines were skipped and truncated preview lines were collapsed to the following full sentence when they were a prefix.

| issue axis | count | representative post_id | note |
| --- | ---: | --- | --- |
| `title_subject_missing` | 1 | `63668` | title starts with particle and loses the player subject |
| `title_clause_cut` | 32 | `63668, 63663, 63149, 63145, 63133, 63125, 63358, 63344` | title was already cut before downstream rewrite/body generation |
| `lead_too_abstract` | 0 | - | no top-50 hit with current heuristic |
| `lead_subject_absent` | 1 | `63668` | same root cause as subject-loss title |
| `opening_duplicate_sentence` | 30 | `63668, 63663, 63149, 63133, 63125, 63350, 63342, 63339` | same opening fact sentence is rendered twice |

### Top 3 issue selection

1. `title_clause_cut` (`32`)
2. `opening_duplicate_sentence` (`30`)
3. `title_subject_missing` (`1`)

`lead_subject_absent` also appeared on `63668`, but it shares the same root cause and was handled by the same subject-recovery fix.

## Narrow fixes

### 1. title clause cut

- file: `src/rss_fetcher.py`
- change:
  - added `_prepare_source_title_context()`
  - stopped using the early `raw_title[:40]` preview as the processing title
  - kept `40` chars only for log preview
- effect:
  - rewrite / subject extraction / body generation now receive the full source title
  - reduces subject loss and clause-cut titles caused by premature truncation

### 2. title subject recovery

- file: `src/rss_fetcher.py`
- change:
  - `_extract_subject_label()` now recovers subject from summary when the title starts with a particle or generic placeholder
  - generic `出場` candidate is blocked from being treated as a player subject
  - status-title rendering preserves explicit `...選手` only when that literal label exists in the source text
  - fan reaction team queries now use role-aware labels such as `戸郷翔征投手 巨人` where that was the existing expected behavior
- effect:
  - fixes cases like `63668`
  - keeps existing title / query expectations intact

### 3. opening duplicate sentence

- file: `src/rss_fetcher.py`
- change:
  - `build_news_block()` now applies render-only dedupe after structure normalization
  - if the summary sentence is repeated again at the start of the first content section, the duplicate render line is dropped
- effect:
  - preserves existing validator input while removing duplicated opening sentences from rendered body output

## Tests

- updated:
  - `tests/test_title_rewrite.py`
  - `tests/test_build_news_block.py`
- added coverage for:
  - full title context is preserved for processing
  - summary fallback recovers missing subject
  - generic placeholder title rewrites recover player name
  - structured-body render drops duplicated opening sentence

## Verify

- `python3 -m pytest`
  - result: `1416 passed, 3 warnings`
- `python3 -m pytest --collect-only -q`
  - result: `1416 tests collected`
- delta vs fire-time baseline:
  - collect: `1409 -> 1416`
- live WP REST smoke:
  - failed in sandbox due DNS / name resolution, so audit evidence for this ticket is based on local publish backups only

## Operational note

- WP write / Cloud Run deploy / push: all `NO`
