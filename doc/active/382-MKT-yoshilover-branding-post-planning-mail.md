# 382-MKT yoshilover branding post planning mail

status: REVIEW_NEEDED
owner: Codex
lane: A
created: 2026-05-18 JST
github_issue: #56
scope: Yoshilover branding X-post planning mail from fresh Giants articles and DB-verified numbers

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
- This ticket is only for editable Yoshilover branding post proposals.
- X account integration status: not connected.
- X Search status: removed from this scope.
- Fan voice X Search ticket #57 is canceled by user request.

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

### Post text rule

The X copy must be Yoshilover's framing, not a copied article title.

Required shape:

```text
この話題、巨人ファンの見方が分かれそうです。
{話題の核}
ヨシラバーでは{topic_type}として、事実とファン目線を分けて整理しました。
{記事URL}
#巨人 #ジャイアンツ
```

`{記事URL}` is a placeholder for the published Yoshilover article URL. The mail is a proposal, so the user can edit before posting.

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
- [ ] DB numeric verification is wired before exact numeric claims are allowed.
- [ ] Live GCP deploy / Scheduler cadence is explicitly approved and executed.

## Verification

- `python3 -m py_compile src/brand_radar.py src/tools/run_brand_radar_mail.py tests/test_brand_radar.py` PASS.
- `python3 -m unittest tests.test_brand_radar` PASS: 18 tests.
- `python3 -m src.tools.run_brand_radar_mail --source-limit 0 --print-body` PASS:
  - dry-run only
  - no network
  - no send
  - body shows `external_reaction_scope: removed_by_user_request`
  - no X live post / WP mutation

## Do not touch

- `.env`
- secret values
- Cloud Scheduler
- Cloud Run env
- existing WP posts
- X API live posting
- `RUN_DRAFT_ONLY`
- unrelated frontend/plugin files
