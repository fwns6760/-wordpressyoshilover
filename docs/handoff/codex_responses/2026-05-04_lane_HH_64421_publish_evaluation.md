# 2026-05-04 Lane HH 64421 publish evaluation

## mode

- request type: live ops, read-only audit first
- target: `post_id=64421`
- scope: `64421` only
- code / config / runtime mutation: none
- final verdict: `STOP`

## Step 1 read-only audit

### fetcher / draft creation

- `2026-05-03 20:30:34 JST`
  - `title_template_selected`
  - `source_url=https://twitter.com/hochi_giants/status/2051036146163929091`
  - `category=選手情報`
  - `article_subtype=player`
  - `template=player_status_return`
  - `original_title=巨人・山崎伊織、復帰戦でまさか わずか２球で緊急降板 右肩違和感…詳細は「僕もまだ分からない」`
  - `rewritten_title=山崎伊織、昇格・復帰 関連情報`
- `2026-05-03 20:30:38 JST`
  - `記事ガードレール発動`
  - `unverified_numbers=['5月3日']`
  - `bad_score=false`
  - `fabricated_result=false`
- `2026-05-03 20:30:39 JST`
  - `title_collision_detected`
  - `source_url=https://twitter.com/hochi_giants/status/2051036146163929091`
  - `rewritten_title=山崎伊織、昇格・復帰 関連情報`
  - `existing_post_url=https://twitter.com/hochi_giants/status/2050810966955151617`
  - `existing_title=【巨人】山崎伊織「明日診てみないと…」復帰戦でアクシデント 緊急降板から３０分後に球場出る`
- `2026-05-03 20:30:40 JST`
  - `media_xpost_embedded`
  - primary source:
    - `https://twitter.com/hochi_giants/status/2051036146163929091`
  - secondary source:
    - `https://twitter.com/SportsHochi/status/2051035487561773348`
  - `notice_body_template_applied`
  - `social_body_template_applied`
- `2026-05-03 20:30:40 JST`
  - `[WP] 記事draft post_id=64421 title='山崎伊織、昇格・復帰 関連情報'`
- `2026-05-03 20:30:41-42 JST`
  - `[下書き止め] post_id=64421 reason=draft_only`
  - `[下書き維持] post_id=64421 reason=draft_only image=あり`

### guarded-publish

- execution: `guarded-publish-m8jkd`
- `2026-05-03 20:35:41 JST`
  - `refused` block contains:
    - `post_id=64421`
    - `reason=hard_stop`
  - adjacent JSON lines in the same block show:
    - `hold_reason=hard_stop_lineup_duplicate_excessive`
  - `executed` block contains:
    - `post_id=64421`
    - `status=refused`
    - `backup_path=null`

### publish-notice

- execution: `publish-notice-cclxb`
- `2026-05-03 20:41:05 JST`
  - `[skip] post_id=64421 reason=REVIEW_EXCLUDED`

### related same-day evidence

- earlier same-day draft:
  - `post_id=64356`
  - `2026-05-03 05:35:29 JST`
  - same `template=player_status_return`
  - same `rewritten_title=山崎伊織、昇格・復帰 関連情報`
  - source:
    - `https://twitter.com/hochi_giants/status/2050810966955151617`
- same-day published Yamasaki incident article:
  - public title:
    - `２球で緊急降板した山崎伊織に「詳しくは聞いてないので分からない」杉内コーチ`
  - `post_id=64402`
  - fetcher source:
    - `https://www.nikkansports.com/baseball/news/202605030001621.html`

### note on GCS history

- direct `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl` read was attempted.
- in this sandbox, `gcloud storage cat` hit `credentials.db` write/auth-copy issues, so I could not independently dump the final JSONL row.
- for this audit I treated the `guarded-publish-m8jkd` stdout fragments as the authoritative live-history proxy, because that execution emits the same per-post refusal/executed data immediately before the history upload step.

## Step 2: 5 questions

### Q1. title / source / subtype

- title: `山崎伊織、昇格・復帰 関連情報`
- primary source: `https://twitter.com/hochi_giants/status/2051036146163929091`
- secondary source: `https://twitter.com/SportsHochi/status/2051035487561773348`
- subtype: `player`
- category: `選手情報`

### Q2. why REVIEW_EXCLUDED?

- `publish_notice_scanner` excludes guarded rows when:
  - `status in {sent,publish,published}`
  - `judgment in {red,hard_stop}`
  - `hold_reason` starts with `hard_stop`
  - or `hold_reason` is in the explicit excluded set
- 64421 was already in `guarded-publish` as:
  - `reason=hard_stop`
  - `hold_reason=hard_stop_lineup_duplicate_excessive`
- therefore `publish-notice` skipped it as `REVIEW_EXCLUDED`.

### Q3. real duplicate?

- exact `duplicate_of_post_id` was not surfaced in the available 64421 log fragments.
- however, this is not a clean publish candidate:
  - there is same-day title collision against an earlier Yamasaki return/injury article source
  - the same rewritten title already existed earlier on `2026-05-03 05:35 JST` as `post_id=64356`
  - same-day published Yamasaki incident coverage already exists as `post_id=64402`
  - guarded-publish classified 64421 into a duplicate-family hard stop, not a repairable review hold
- operational verdict:
  - `publish-forward` safe targetとしては **duplicate cluster stop**
  - つまり Lane HH の自動 publish 候補としては `NO`

### Q4. placeholder / body_contract NG / fact break?

- placeholder hard stop: **not observed**
- body_contract fail: **not observed**
- clear numeric / score_order / date_fact_mismatch hard stop: **not observed**
- fetcher warning only:
  - `unverified_numbers=['5月3日']`
- body quality evidence:
  - `notice_body_template_applied`
  - `social_body_template_applied`
  - draft + image were created successfully

### Q5. can it go to publish if otherwise clean?

- verdict: **No**
- reason:
  - the terminal guarded result is already `hard_stop`
  - the stop class is duplicate-family, not cleanup-required or review-only
  - same-day Yamasaki injury/return coverage is already clustered on-site

## Step 3 verdict

- result: `B. stop`
- stop basis:
  - duplicate-family guarded hard stop
  - same-day collision with prior Yamasaki recovery/injury coverage
- non-stop conditions:
  - Giants relevance: yes
  - placeholder/body_contract fatality: no
  - clear numeric/score/date hard stop: no

## Step 4 outcome

- skipped
- no backup created
- no history row delete
- no rerun of `run_guarded_publish`
- no WordPress mutation
- no mail side effect

## Step 5 verify

- 64421 public URL: none
  - `https://yoshilover.com/64421` is still not public
- publish-notice `sent` timestamp: none
- final state: draft remains

## Step 6 completion record

### outcome summary

- publish candidate: `NO`
- publish-forward executed: `NO`
- final outcome: `draft 維持`

### rollback

- no live mutation was performed, so rollback is not required.
- if this needs to be revisited later, the safe path is:
  1. read the current draft body for `64421`
  2. compare it against published `64402` and earlier Yamasaki return/injury drafts
  3. only if a materially distinct fact angle exists, use manual editorial rewrite instead of guarded history deletion

### recommended next user action

- if the goal is strict lane safety: keep `64421` stopped.
- if the user still wants this topic published, do **manual editorial differentiation** first:
  - retitle away from the generic `昇格・復帰 関連情報`
  - make the body center a fact not already carried by `64402`
  - then re-evaluate as a new manual rescue, not a narrow auto publish-forward.
