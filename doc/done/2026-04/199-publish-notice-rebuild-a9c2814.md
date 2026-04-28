# 199 publish-notice rebuild a9c2814 live-state verify

- priority: P0.5
- status: CLOSED(superseded by later publish-notice rebuild `25f176b`)
- owner: Codex / Claude follow-up
- lane: A
- parent: 188 / 189 / 194

## Close note(2026-04-28)

- `a9c2814` 向け検証は後続の publish-notice image `25f176b` rebuild / smoke で superseded。
- MKT-001 / 222 / 241 は `25f176b` live image で確認済み。

## Background

- this ticket originally asked for a `publish-notice` rebuild / deploy toward the `a9c2814` code state
- local board state had remained `BLOCKED_USER`, but the actual runtime state needed fresh read-only verification
- this turn performs read-only verification only

## Read-Only Facts Confirmed

- Cloud Run Job `publish-notice` current image:
  - `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:23853cd`
- latest execution:
  - name: `publish-notice-wspgg`
  - result: `EXECUTION_SUCCEEDED`
  - completion: `2026-04-27 11:05:34 JST`
- recent executions exist on the `*/5` cadence:
  - `publish-notice-wspgg`
  - `publish-notice-4qlzn`
  - `publish-notice-9nmm7`
- Cloud Logging for the newest executions shows normal scanner exits such as:
  - `[scan] emitted=0 skipped=0 ...`
- Gmail inbox contains recent `[公開通知]` mail to `fwns6760@gmail.com`

## What Is Still Not Verified

- sample Gmail bodies still show `subtype: unknown`
- literal `manual_x_post_candidates` was not found in:
  - recent Cloud Logging searches
  - sampled Gmail message bodies
- therefore the original acceptance for X candidate visibility is still not satisfied

## Interpretation

- this ticket is no longer `BLOCKED_USER`
- the live runtime is moving:
  - image is already updated
  - executions are succeeding
  - mail is arriving
- however the observed mail body does not yet prove that the intended X candidate block is present
- keep the ticket in `REVIEW_NEEDED` until that gap is explained

## Important Context

- git commit `23853cd` is the doc-only ticket commit, and the live image tag now matches that short SHA
- `e78f088` (`200`) landed after `23853cd`, so the sampled `subtype: unknown` mail body is not evidence against the later scanner fallback fix

## Next Action

1. compare the current live mail body against the expected `1ac710b` / `b7a9e1f` behavior
2. decide whether the missing X candidate block is:
   - output truncation / observation artifact
   - runtime drift
   - a still-missing code path
3. if mutation is needed, open a separate narrow fix / redeploy ticket
4. use `205` as the broader read-only runtime drift audit ticket

## Guardrails Held

- Cloud Build submit: NO
- Cloud Run Job update: NO
- Scheduler change: NO
- IAM / Secret / env mutation: NO
- WP write: NO
- X post: NO
