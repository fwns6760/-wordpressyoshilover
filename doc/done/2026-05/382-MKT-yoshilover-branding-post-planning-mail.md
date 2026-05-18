# 382-MKT yoshilover branding post planning mail

status: CLOSED
owner: Codex
lane: A
created: 2026-05-18 JST
closed: 2026-05-19 JST
github_issue: #56
scope: Existing x-post-mail branding candidate copy from fresh Giants topics and DB-verified numbers

## User problem

- user lock: 目的はブランディング。「ヨシラバーのポストを見たい」と思わせる。
- user lock: 記事は WordPress 側で出す。X では記事を読ませるためのポスト案が必要。
- user correction: X Premium / Hermes 連携は現時点でできていないため、チケットから外す。
- user correction: `Xのみんなの声` も目的外なので外す。
- user correction: 数値は使ってよいが、DB と照合できるものだけにする。
- hard rule: 推測で補わない。隠さない。自己評価で OK にしない。証拠だけ出す。

## Current decision

- This ticket is not an X Search / Hermes OAuth ticket.
- This ticket is not an article-body `皆の声` / fan voice ticket.
- This ticket is only for editable Yoshilover branding post proposals inside the existing x-post-mail lane.
- X account integration status: not connected.
- X Search status: removed from this scope.
- Fan voice X Search ticket #57 is canceled by user request.
- Final implementation uses the existing x-post-mail mail, schedule, UI, and buttons. No new mail, Scheduler, Secret, or env was created.

## Evidence already verified

- `command -v hermes` returned no path in this environment.
- `@yoshilover6760` OAuth consent has not been completed in this work.
- No Hermes auth artifact has been saved to Secret Manager.
- No GCP Hermes smoke Job has run.
- Existing repo implementation can generate mail-only branding post proposals:
  - `src/brand_radar.py`
  - `src/tools/run_brand_radar_mail.py`
  - `tests/test_brand_radar.py`
- Existing implementation does not call X live posting and does not mutate WP.

## Implementation contract

### Inputs

- Fresh Giants article sources from `config/rss_sources.json`:
  - `news`
  - `tag_scrape`
  - `social_news` only if article sources are insufficient
- Optional data support from insight DB only when explicitly wired and freshness is proven.

### Candidate priority

1. Fresh Giants article topic, 0-6h.
2. Fresh Giants article topic, 6-24h.
3. Weekly / magazine context if Giants-specific.
4. Data support only as a supporting angle, not as the whole post theme.

### Final post text rule

The X copy must be Yoshilover's framing, not a copied article title. The 2026-05-18 GitHub Issue #56 comment supersedes the earlier `{記事URL}` placeholder draft.

Must not include:

- Article URL.
- Hashtag.
- `ヨシラバーで整理しました`.
- Site-induction copy.
- Fabricated fan reaction.

Representative shapes:

```text
{選手名}のコメントで気になるのは、結果よりも今の立場。

{DB照合済みの短い数字文}
数字だけで結論は出せないけど、次にどの場面で使われるかは見ておきたい。
```

```text
複数の媒体で名前が出てくる時は、少し意味がある。

単発のニュースではなく、流れになりかけている話題。
今の巨人でどう扱われるかを見たい。
```

### Numeric rule

- Numeric claims may be used only when DB-verified.
- Article-title numbers are not automatically trusted.
- If a number is not DB-verified, remove or generalize it in the X post proposal.
- The mail must show a note such as `unverified_numeric_claim_omitted_from_post_text` when a source title contained an unverified number.
- DB freshness must be visible before numeric claims are allowed.

Examples:

- Source title: `打率.160でも…坂本勇人が必要なワケ`
- Unverified X proposal phrase: `打率の数字でも…坂本勇人が必要なワケ`
- DB-verified X proposal phrase may include the exact number only after the DB check records the evidence.

### Must not include

- X Search claim.
- Hermes OAuth claim.
- `Xでは...` / `X上では...` / `みんなの声`.
- Fabricated fan reaction.
- Unverified score, rank, injury, roster status, batting average, ERA, OPS, inning, hit count, RBI, or quote.

## Implementation landed

- `src/x_post_mail_lane.py`
  - Existing x-post-mail candidates now include branding-oriented post drafts with no article URL, no hashtag, no `ヨシラバーで整理しました`, and no site-induction copy.
  - Unverified RSS / comment / trend numbers are not placed in the post text.
  - DB-verified numbers may be used when the candidate has DB fact evidence.
  - Comment x DB number combination is allowed only for same full name, active Giants player, source comment material, matching topic family, and DB fact evidence.
  - Ambiguous surname-only candidates are rejected when multiple Giants players share the surname.
- `src/tools/run_x_post_mail.py`
  - Existing job entrypoint remains the deployment path.
- `tests/test_x_post_mail.py`
  - Tests cover the branding copy contract, numeric omission / DB evidence rules, and ambiguous-name guard.
- `src/brand_radar.py`
  - Fresh article collector from `config/rss_sources.json`.
  - Article sources prioritized over official/social X sources.
  - General RSS summary-only Giants hits rejected unless the title/source is Giants-specific or a known Giants player is in the title.
  - Mail-only post proposal builder.
  - X live post and WP mutation are not performed.
  - Paid xAI API remains disabled by default.
  - User-facing mail copy now treats X Search as removed by scope.
  - Unverified numeric claims are omitted/generalized in the post proposal.
- `src/tools/run_brand_radar_mail.py`
  - Default dry-run.
  - `--send` required for real mail delivery.
- `tests/test_brand_radar.py`
  - Tests cover article-first ordering, source priority, no X/WP mutation, no paid X Search call by default, and removed X Search user-facing copy.

## Out of scope

- Hermes OAuth.
- X Premium account connection.
- X Search.
- Article body `皆の声` / fan voice improvement.
- X live posting.
- WP publish / draft creation.
- Existing WP article mutation.
- Secret / Scheduler / Cloud Run env changes until explicitly approved.

## Acceptance

- [x] Ticket has GitHub Issue linked: #56.
- [x] Repo-only tests prove fresh article candidates outrank data-only candidates.
- [x] Repo-only tests prove official/social X is lower priority than newspaper / specialist / magazine sources when fresh article sources exist.
- [x] Repo-only tests prove no X live post or WP mutation is possible from this lane.
- [x] Mail fixture contains source URL and source time.
- [x] User-facing mail does not claim X Search / Hermes / fan voice evidence.
- [x] Paid xAI API is disabled by default.
- [x] Unverified numeric claims are omitted/generalized in the X post proposal.
- [x] DB numeric verification is wired before exact numeric claims are allowed in the existing x-post-mail candidate path.
- [x] Live GCP deploy executed on existing x-post-mail lane.
- [x] Existing Scheduler cadence was left unchanged.

## Verification

- `python3 -m py_compile src/brand_radar.py src/tools/run_brand_radar_mail.py tests/test_brand_radar.py` PASS.
- `python3 -m unittest tests.test_brand_radar` PASS: 18 tests.
- `python3 -m src.tools.run_brand_radar_mail --source-limit 0 --print-body` PASS:
  - dry-run only
  - no network
  - no send
  - body shows `external_reaction_scope: removed_by_user_request`
  - no X live post / WP mutation
- `python3 -m py_compile src/x_post_mail_lane.py src/tools/run_x_post_mail.py tests/test_x_post_mail.py` PASS.
- `python3 -m compileall -q src/x_post_mail_lane.py src/tools/run_x_post_mail.py tests/test_x_post_mail.py` PASS.
- `python3 -m unittest tests.test_x_post_mail` PASS: 101 tests.
- `python3 -m unittest discover -s tests` PASS after follow-up commit `1013716`: 4435 tests OK.
- Cloud Build `1629e082-f0c6-4b99-a1c0-a53cd9fd3d1f` SUCCESS.
- Cloud Run Job `x-post-mail-lane` generation 23 Ready=True with image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:382-branding-4507257`.
- Natural Scheduler execution `x-post-mail-lane-psp2s` at 2026-05-19 07:00 JST completed successfully:
  - `Composing mail with 10 candidates`
  - `mail send result: status=sent`
  - `Recorded 10 dedup signatures (ok=True)`
  - no ERROR logs for the execution.
- Not performed: manual job execute, X live post, WP write, env / Secret / Scheduler changes.

## Do not touch

- `.env`
- secret values
- Cloud Scheduler
- Cloud Run env
- existing WP posts
- X API live posting
- `RUN_DRAFT_ONLY`
- unrelated frontend/plugin files
