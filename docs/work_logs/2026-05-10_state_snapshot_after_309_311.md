# 2026-05-10 state snapshot after 309-311

## 1. current live

- service: `yoshilover-fetcher`
- project: `baseballsite`
- region: `asia-northeast1`
- latest ready revision: `yoshilover-fetcher-00291-86k`
- latest created revision: `yoshilover-fetcher-00291-86k`
- traffic target:
  - `yoshilover-fetcher-00291-86k = 100%`

## 2. current branch

- branch: `draft-body-editor-reject-streak-no-fail`

## 3. recent commits

- `15beaa6` `docs: record 2026-05-10 rollout log`
- `28b10a9` `311: expand short notice x reactions safely`
- `f87af66` `310: expand player manager x reactions safely`
- `2b48482` `309: expand postgame tables and x reactions safely`
- `11215f1` `308: stop scoreboard-only postgame thin bodies`
- `679be71` `feat: add player stats tables`

## 4. ticket state

### 308-QA

- title: `thin body audit and fix`
- code / tests: completed
- commit: completed
- deploy: **not deployed**
- intent:
  - stop `65801`-class scoreboard-only thin-body publish

### 309-QA

- title: `postgame table and X reaction expansion`
- code / tests: completed
- commit: completed
- deploy: completed
- included in live revision: yes

### 310-QA

- title: `player / manager X reaction expansion`
- code / tests: completed
- commit: completed
- deploy: completed
- included in live revision: yes

### 311-QA

- title: `short notice X reaction expansion`
- code / tests: completed
- commit: completed
- deploy: completed
- included in live revision: yes

## 5. operational verification status

### verified

- `309 / 310 / 311` are in live revision `00291-86k`
- `guarded-publish` natural execution succeeded after `311` deploy
- `publish-notice` natural execution succeeded after `311` deploy
- `00291-86k` had `severity>=ERROR = 0` at post-deploy safe check time
- `/health = OK`

### still pending

- direct inspection of one **newly published article generated after `00291-86k`**
  - verify:
    - rendered tables
    - X reaction fit
    - no subjective / strange / empty body

## 6. important caveats

### ticket docs are not normalized

- `308 / 309 / 310 / 311` ticket markdown files still live under `doc/waiting/`
- their `meta.status` values were not updated to final deploy-complete states
- reason:
  - today priority was code / test / deploy safety
  - close / archive normalization was intentionally deferred

### worktree is not clean

- repo still contains many unrelated modified / untracked files
- next work must keep explicit path staging only
- do not infer clean state from latest deploy success

## 7. next safe action

1. observe the first newly published article after `00291-86k`
2. if article quality is fine, close/archive `309 / 310 / 311`
3. handle `308` deploy decision separately so it does not silently mix with later tickets
