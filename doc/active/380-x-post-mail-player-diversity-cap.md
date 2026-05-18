# 380-x-post-mail-player-diversity-cap

## status

- **status**: LIVE_DEPLOYED_OBSERVE
- **owner**: Codex
- **lane**: B
- **created**: 2026-05-18 JST
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/54
- **scope**: X 投稿候補 mail の同一選手偏りを抑制する

## user report

2026-05-18 user 指示:

- `巨人データXポスト案 — 朝 / 2026-05-18 07:00 JST` の mail で同じ選手ばかり出る
- DB 記録は最新でないといけない
- データだけでなくてもよい
- データ候補が足りない場合、同じ選手の記事ニュースに対する意見案でもよい
- 推測で補わない
- silent skip しない
- 自己評価 OK にしない
- 証拠を ticket に入れる

2026-05-18 follow-up user 指摘:

- 12:01 JST mail で浦田俊輔が 3 回出た
- 13:07 JST mail でも浦田俊輔が再度出た
- 1 通内の `max_per_player` だけでは、当日 / 直近24hの同一選手連発を止められない
- user-visible acceptance は未達

## follow-up design — player history dedup

現行の不足:

- GCS 24h dedup JSONL は `signature = metric|period_label|giants_only|position` を記録する
- `focus_player` は記録していない
- そのため 12:01 で `浦田俊輔` が複数回出ても、13:07 の候補選定では `浦田俊輔` が既出 player だと判定できない

実装する仕組み:

- 新規送信分の dedup JSONL に `focus_player`, `metric`, `period_label` を追加する
- 旧 JSONL record は `signature` のみでも読み続ける
- mail 生成時、直近24hの dedup JSONL から `focus_player` count を集計する
- `recent_player_counts` を `pick_candidates()` に渡す
- 候補選定時、直近24hに出た player は `avoid_player_names` に入れる
- ranking 内に別の巨人選手があれば、その player に差し替える
- 差し替え不能なら `player_history_skip` を log してデータ候補からは外す
- 候補数が足りなければ、news/opinion fallback を使う
- news/opinion fallback も直近24h既出 player は補充しない
- それでも候補不足の場合だけ、既存の starvation fallback により mail 0 件化を避ける。ただし skip / fallback は log に残す

想定 JSONL:

```json
{"ts":"2026-05-18T12:01:06+09:00","signature":"OPS|今月|False|None","focus_player":"浦田俊輔","metric":"OPS","period_label":"今月"}
```

必要 log:

- `Loaded 24h player history: ...`
- `player_history_alternate_selected ... skipped_player=浦田俊輔 previous_count=3 selected_player=...`
- `player_history_skip ... player=浦田俊輔 previous_count=3 reason=no_alternative`
- `news_opinion_fallback_player_history_skip ... player=浦田俊輔 previous_count=3 ...`

追加 acceptance:

- 12:01 -> 13:07 型の test で、12:01 既出 player が次回 data candidate の主役に再登場しない
- ranking 内に別の巨人 player がいれば差し替える
- news/opinion fallback は直近24h既出 player を補充しない
- GCS dedup JSONL は旧 `signature` only record と互換
- 新規 record は `focus_player` evidence を持つ
- skip / fallback は log に残り、silent skip しない

## evidence confirmed

### Gmail 実メール

- Gmail message id: `19e37f4bb23efcbb`
- subject: `🟠🐦📮【Xポスト案 8件】🌅朝｜直近データ 07:00 JST`
- body header: `📮 巨人データXポスト案 — 朝 / 2026-05-18 07:00 JST`
- sender: `y.sebata@shiny-lab.org`
- recipient: `fwns6760@gmail.com`

候補 8 件:

| # | player | metric | period |
|---|---|---|---|
| 1 | 岸田 行倫 | OPS | 直近10試合 |
| 2 | マルティネス | 防御率 | 直近5試合 |
| 3 | 平山 功太 | 出塁率 | 直近5試合 |
| 4 | キャベッジ | 長打率 | 直近5試合 |
| 5 | マルティネス | 奪三振率 | 直近5試合 |
| 6 | 則本昂大 | 与四球率 | 直近5試合 |
| 7 | 岸田 行倫 | 打率 | 直近10試合 |
| 8 | マルティネス | 被本塁打率 | 直近5試合 |

集計:

- `マルティネス`: 3 / 8 件
- `岸田 行倫`: 2 / 8 件
- `平山 功太`: 1 / 8 件
- `キャベッジ`: 1 / 8 件
- `則本昂大`: 1 / 8 件

### X post mail 実行ログ

Cloud Run Job:

- job: `x-post-mail-lane`
- latest execution for this mail: `x-post-mail-lane-vfs6m`
- creation: `2026-05-17T22:00:03Z` = 2026-05-18 07:00 JST
- completion: `2026-05-17T22:00:47Z`
- status: `EXECUTION_SUCCEEDED`

Relevant logs:

- `2026-05-17T22:00:21Z` `Downloading insight.db cache (read-only)…`
- `2026-05-17T22:00:40Z` `insight.db freshness latest_game_date=2026-05-17 staleness_days=1 max=2 path=/tmp/insight_cache/insight.db`
- `2026-05-17T22:00:42Z` `Lineup focus unavailable: no lineup rows returned`
- `2026-05-17T22:00:42Z` `24h dedup left only 0 candidates (<3); retrying without dedup to avoid starving scheduled mail.`
- `2026-05-17T22:00:42Z` `Dedup fallback backfilled candidates: 0 -> 8`
- `2026-05-17T22:00:45Z` `mail send result: status=sent reason=None refused={}`
- `2026-05-17T22:00:45Z` `Recorded 8 dedup signatures (ok=True)`

Confirmed:

- The 07:00 mail did not use repo-local `data/insight/insight.db`.
- The 07:00 mail downloaded `/tmp/insight_cache/insight.db` read-only from the configured GCS bucket.
- At mail generation time, DB freshness was `latest_game_date=2026-05-17`, `staleness_days=1`, within `max=2`.

### Production GCS DB

Read-only production pull:

- command target: `/tmp/yoshilover-insight-debug-20260518.db`
- source bucket: `baseballsite-yoshilover-insight`
- source object: `insight.db`
- result: `ok=true`
- mode: `download_only`

Summary:

| field | value |
|---|---|
| latest_game_date | `2026-05-17` |
| latest_giants_game_date | `2026-05-17` |
| staleness_days | `1` |
| giants_staleness_days | `1` |
| size_bytes | `26914816` |
| games | `248` |
| batting_logs | `4464` |
| pitching_logs | `2007` |
| advanced_metric_snapshots | `64076` |
| article_candidates | `25513` |

GCS object metadata:

- `gs://baseballsite-yoshilover-insight/insight.db`
- Creation Time: `2026-05-18T01:01:30Z`
- Update Time: `2026-05-18T01:01:30Z`
- Content-Length: `26914816`
- Generation: `1779066090429557`

### Data insight scheduler / job

Scheduler:

- `data-insight-morning-trigger`: `0 7 * * *`, lastAttemptTime `2026-05-17T22:00:03Z`, ENABLED
- `data-insight-1000-trigger`: `0 10 * * *`, lastAttemptTime `2026-05-18T01:00:03Z`, ENABLED

Cloud Run Job:

- job: `insight-nightly`
- latest execution: `insight-nightly-p85s6`
- creation: `2026-05-18T01:00:03Z` = 2026-05-18 10:00 JST
- completion: `2026-05-18T01:01:33Z`
- status: `EXECUTION_SUCCEEDED`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/insight-nightly:44g-hr-ranking-242aab2`
- env includes `INSIGHT_GCS_BUCKET=baseballsite-yoshilover-insight`

### Repo-local DB

Local file:

- path: `data/insight/insight.db`
- mtime: `2026-05-14T22:01:21`
- latest_game_date: `2026-05-13`
- staleness_days as of 2026-05-18 07:00 JST: `5`

This is stale, but it is not the production source of truth.

Existing doc evidence from `doc/active/358-INSIGHT-local-production-db-pull.md`:

- production source of truth is GCS `insight.db`
- local `data/insight/insight.db` is a generated artifact
- default pull writes to `/tmp`, not repo-local DB
- `--replace-local` is required to overwrite repo-local DB

Therefore:

- The stale local file explains why a local check showed old data.
- It does not prove production DB or the 07:00 mail used old data.
- Production DB and x-post-mail logs show latest game date `2026-05-17`.

## current code evidence

- `src/x_post_mail_lane.py:1148-1155` `_combo_signature()` is `metric|period_label|giants_only|position`; player is not part of the key.
- `src/x_post_mail_lane.py:1158-1167` `_period_family_key()` is `metric|giants_only|position`; player is not part of the key.
- `src/x_post_mail_lane.py:827-829` returns the first Giants row when no lineup focus is active.
- `src/x_post_mail_lane.py:1544-1582` `used_focus_player_keys` is only active when `focus_names` is present.
- `src/tools/run_x_post_mail.py:299-312` retries without lineup focus when lineup focus produces too few candidates.

Confirmed from code:

- 24h dedup is combo-based, not player-based.
- Same metric multi-window repetition is suppressed.
- Same player across different metrics is not generally capped.
- On this run, lineup focus was unavailable, so the focus player spread path did not apply.
- Current 347 lane explicitly says `article_candidates` is never read or written, so news/opinion fallback is not implemented in the current lane.

## implementation evidence — 2026-05-18 JST

Changed files:

- `src/x_post_mail_lane.py`
- `src/tools/run_x_post_mail.py`
- `tests/test_x_post_mail.py`

Implemented:

- Same-player cap added to `pick_candidates()` with default `max_per_player=2`.
- When a ranking's top Giants row is an already-used player, `_top_giants_row(..., avoid_player_names=...)` now selects the next available Giants row before repeating the same player.
- Repeated-player candidates are deferred into `repeat_backlog`; they are restored only when needed and only under the cap.
- Logs added for:
  - `player_diversity_alternate_selected`
  - `player_diversity_cap_skip`
  - `player_diversity_duplicate_fallback`
  - `player_diversity_backlog_cap_skip`
- Data-first behavior remains: metric ranking candidates are selected before fallback.
- If data candidates do not fill the mail, `run_x_post_mail` can add public RSS/Atom source-backed news/opinion candidates.
- News/opinion fallback uses only:
  - source title
  - source URL
  - source excerpt/summary if present
  - active Giants roster alias detection
- News/opinion fallback does not call:
  - LLM
  - X API
  - WP API
  - `article_candidates`
  - production DB/GCS write
- Mixed data + news/opinion mail changes the label from `巨人データXポスト案` to `巨人Xポスト案`, and the subject purpose to `データ+ニュース意見`.

Verification commands:

- `python3 -m py_compile src/x_post_mail_lane.py src/tools/run_x_post_mail.py tests/test_x_post_mail.py`
- `python3 -m pytest -q tests/test_x_post_mail.py`
  - result: `89 passed, 3 warnings in 1.62s`
- `python3 -m unittest tests.test_x_post_mail`
  - result: `Ran 89 tests in 0.513s` / `OK`

Targeted test evidence:

- `test_player_diversity_uses_next_giants_row_before_repeating`
  - proves next Giants row is selected before repeating the same player.
- `test_player_diversity_caps_same_player_when_no_alternative`
  - proves no-alternative duplicate fallback is capped at 2.
- `test_news_opinion_candidate_uses_source_evidence_label`
  - proves news/opinion candidate carries source URL/title evidence and mixed mail label is not data-only.
- `test_detect_giants_player_name_requires_source_alias`
  - proves player detection requires a source text alias match.
- `test_news_opinion_fallback_fills_sparse_data_candidates`
  - proves sparse data candidates can be supplemented before mail send.

Not changed:

- Cloud Scheduler: unchanged.
- Cloud Run env / Secret: unchanged.
- SMTP credential / recipient: unchanged.
- WP publish / WP existing posts: unchanged.
- X API / SNS live post: unchanged.
- production GCS DB upload/write: unchanged.

## 12:01 JST regression report and live deploy — 2026-05-18 JST

User report:

- `12時のメールなおってないよ。`

Confirmed 12:01 mail:

- Gmail message id: `19e3907b7bdba8e5`
- subject: `🟠🐦📮【Xポスト案 8件】🌞昼｜直近数字 12:01 JST`
- body header: `📮 巨人データXポスト案 — 昼 / 2026-05-18 12:01 JST`
- candidate count: `8`

Candidate player count:

- `浦田俊輔`: 3 / 8
- `マルティネス`: 3 / 8
- `岸田 行倫`: 1 / 8
- `則本昂大`: 1 / 8

Confirmed cause:

- `x-post-mail-lane` at the 12:01 run was still using old image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:376-lineup-spread-e488052`.
- Therefore commit `31aa4e7 fix: cap x post mail player repeats` was not live for the 12:01 mail.

Pre-deploy job evidence:

- job: `x-post-mail-lane`
- generation: `19`
- latest execution: `x-post-mail-lane-rgp25`
- latest execution creation: `2026-05-18T03:00:04Z` = 2026-05-18 12:00 JST
- latest execution completion: `2026-05-18T03:01:09Z`
- image before deploy: `x-post-mail-lane:376-lineup-spread-e488052`

Deploy performed:

- build source: clean `git archive 31aa4e7` export `/tmp/x-post-mail-deploy-31aa4e7-7OoXxc`
- Cloud Build: `ba632b1d-0bdd-4a09-b314-e7b8b3ea1c3e`
- Cloud Build status: `SUCCESS`
- image tag: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:380-player-diversity-31aa4e7`
- image digest: `sha256:64e78e6f799dedc16323c49df502dc2d07c4d0cbb545ab549f899368a9e9666c`
- Cloud Run Job update: success
- job generation after deploy: `20`
- image after deploy: `x-post-mail-lane:380-player-diversity-31aa4e7`

Changed live:

- Cloud Run Job image only.

Unchanged live:

- Cloud Scheduler: unchanged.
- Cloud Run env / Secret: unchanged.
- SMTP credential / recipient: unchanged.
- WP publish / WP existing posts: unchanged.
- X API / SNS live post: unchanged.
- production GCS DB upload/write: unchanged.

Dry-run note:

- A dry-run execution attempt `x-post-mail-lane-bjs5v` used `--args=--dry-run`.
- Cloud Run treated `--args` as a replacement for the Dockerfile CMD and tried to execute `--dry-run` directly.
- Result: `Application exec likely failed`; exit code `1`.
- This did not send mail. Gmail search after the attempt still showed only the 12:01 `Xポスト案` mail for 2026-05-18.
- Job template itself remains args-free and points to the corrected image, so scheduled execution will use the Dockerfile CMD.

Live verification mail:

- Manual execution: `x-post-mail-lane-d6w4h`
- execution creation: `2026-05-18T04:07:08Z` = 2026-05-18 13:07 JST
- execution image digest: `sha256:64e78e6f799dedc16323c49df502dc2d07c4d0cbb545ab549f899368a9e9666c`
- execution status: `Completed=True`, `succeededCount=1`
- log: `insight.db freshness latest_game_date=2026-05-17 staleness_days=1 max=2`
- log: `Dedup fallback backfilled candidates: 0 -> 8`
- log: `News/opinion fallback filled candidates: 8 -> 10`
- log: `mail send result: status=sent reason=None refused={}`
- log: `Recorded 10 dedup signatures (ok=True)`
- Gmail message id: `19e39446c4ac0f79`
- subject: `🟠🐦📮【Xポスト案 10件】🌞昼｜データ+ニュース意見 13:07 JST`
- body header: `📮 巨人Xポスト案 — 昼 / 2026-05-18 13:07 JST`

13:07 candidate focus player count:

| # | player | type |
|---|---|---|
| 1 | キャベッジ | data |
| 2 | 浦田俊輔 | data |
| 3 | マルティネス | data |
| 4 | 平山 功太 | data |
| 5 | 戸郷翔征 | data |
| 6 | 岸田 行倫 | data |
| 7 | 井上温大 | data |
| 8 | 則本昂大 | data |
| 9 | 山瀬 慎之助 | news/opinion fallback |
| 10 | 竹丸 和幸 | news/opinion fallback |

Result:

- same-player repeat in candidate focus: `0`
- data candidates: `8`
- news/opinion fallback candidates: `2`
- mixed label used: `巨人Xポスト案` / `データ+ニュース意見`

## follow-up implementation evidence — 2026-05-18 JST

Changed files:

- `src/x_post_mail_lane.py`
- `src/tools/run_x_post_mail.py`
- `tests/test_x_post_mail.py`
- `doc/active/380-x-post-mail-player-diversity-cap.md`
- `doc/README.md`
- `doc/active/assignments.md`

Implemented:

- GCS dedup JSONL reader split into record reader + signature set + player count derivation.
- Existing `signature` only dedup records remain readable.
- New dedup writes can include `focus_player`, `metric`, and `period_label`.
- `pick_candidates()` now accepts `recent_player_counts`.
- Recent player counts are normalized and added to `avoid_player_names` before selecting the Giants row.
- If the top Giants row is a recent player and another Giants row exists, the other player is selected.
- If no alternate exists, `player_history_skip` is logged with `previous_count`.
- News/opinion fallback also skips players in recent player history and logs `news_opinion_fallback_player_history_skip`.
- If player history + news/opinion fallback leave zero candidates, the runner logs that fact and relaxes player history only as a last-resort zero-mail prevention fallback.

Verification commands:

- `python3 -m py_compile src/x_post_mail_lane.py src/tools/run_x_post_mail.py tests/test_x_post_mail.py`
  - result: PASS
- `python3 -m compileall -q src/x_post_mail_lane.py src/tools/run_x_post_mail.py tests/test_x_post_mail.py`
  - result: PASS
- `python3 -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8'), filename=p) for p in ['src/x_post_mail_lane.py','src/tools/run_x_post_mail.py','tests/test_x_post_mail.py']]; print('AST OK')"`
  - result: `AST OK`
- `python3 -m pytest -q tests/test_x_post_mail.py`
  - result: `94 passed, 3 warnings`
- `python3 -m unittest tests.test_x_post_mail`
  - result: `Ran 94 tests` / `OK`
- `git diff --check -- src/x_post_mail_lane.py src/tools/run_x_post_mail.py tests/test_x_post_mail.py doc/active/380-x-post-mail-player-diversity-cap.md doc/README.md doc/active/assignments.md`
  - result: PASS

Targeted test evidence:

- `test_recent_player_history_uses_next_giants_row`
  - proves a 12:01 already-seen `浦田俊輔` history causes the next candidate to choose `平山 功太`.
- `test_load_recent_player_counts_from_dedup_records`
  - proves GCS dedup JSONL `focus_player` records become player counts and legacy signature-only records do not break parsing.
- `test_record_dedup_signatures_can_write_focus_player_fields`
  - proves new records include `focus_player`, `metric`, and `period_label`.
- `test_news_opinion_fallback_skips_recent_history_player`
  - proves news fallback does not re-add a recent-history player.
- `test_player_history_zero_candidate_relaxes_as_last_resort`
  - proves history is relaxed only after zero candidates remain, to avoid a missing scheduled mail.

## follow-up live deploy evidence — 2026-05-18 JST

Deploy source:

- git archive source commit: `157b26b`
- reason: repo HEAD advanced to unrelated commit `3c1612d` after this fix; x-post-mail image was built from explicit commit `157b26b` so unrelated `rss_fetcher.py` change was not mixed into this deploy.
- export dir: `/tmp/x-post-mail-deploy-380-history-JKGrR6`

Cloud Build:

- build id: `8dad3a83-bda3-4a0d-8103-befda9656915`
- status: `SUCCESS`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:380-player-history-157b26b`
- digest: `sha256:15cd06766cdc4ee6a3780ce3a25bba2ee3ddbe482d3b0a56d0116f3a9914ecd1`
- finishTime: `2026-05-18T05:01:33.653114Z`

Cloud Run Job update:

- job: `x-post-mail-lane`
- generation: `21`
- Ready condition: `True`
- image: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/x-post-mail-lane:380-player-history-157b26b`
- operation id: `cf3224c4-123b-42cc-b044-4f3e776ead51`

Scheduler evidence:

- `x-post-mail-am-1`: `0 7 * * *`, ENABLED
- `x-post-mail-lunch`: `0 12 * * *`, ENABLED
- `x-post-mail-afternoon`: `0 15 * * *`, ENABLED
- `x-post-mail-evening`: `30 17 * * *`, ENABLED
- `x-post-mail-postgame`: `30 22 * * *`, ENABLED
- `x-post-mail-extra-20260517-game`: `0 14,16,17 17 5 *`, ENABLED

Not executed:

- No post-update manual `gcloud run jobs execute` was run.
- Reason: manual execute sends an additional real email. Post-update user-visible mail acceptance remains pending until the next natural fire.
- Latest execution shown by job describe was `x-post-mail-lane-l9652` / `EXECUTION_SUCCEEDED`, created at the 15:00 JST scheduler fire before the generation 21 image update; it is not evidence of the new image running.

Not changed:

- Cloud Scheduler definitions: unchanged.
- Cloud Run env / Secret: unchanged.
- SMTP sender / recipient: unchanged.
- WP / X / SNS / production DB: unchanged.

## implementation contract

変更してよい:

- `src/x_post_mail_lane.py`
- `src/tools/run_x_post_mail.py` if needed for config / logging only
- `tests/test_x_post_mail.py`
- Optional new read-only helper for recent Giants news/opinion fallback, if data-only diversity cannot fill the mail
- 本 ticket / board docs

変更しない:

- Cloud Scheduler
- Cloud Run env / Secret
- SMTP credential
- WP publish / WP 既存記事
- X API / SNS live post
- `insight-nightly` article publish lane
- production DB / GCS upload
- source article mutation

## desired behavior

- X 投稿候補 mail 1 通内で、同じ player が上位候補を占有しない。
- First pass は distinct player を優先する。
- ある metric ranking の top Giants row が既出 player の場合、同じ ranking 内の次の Giants row を候補にできるなら差し替える。
- 代替 row がない場合だけ duplicate player 候補を backlog へ回す。
- 候補数が不足する場合は mail 枯れを避けるため duplicate player を fallback として戻してよい。ただし default では同一 player `2` 件までを upper bound にする。
- どの player が cap で後回し / fallback になったかを log に残す。silent skip しない。
- 24h combo dedup と 374 の starvation fallback は維持する。
- Data candidates remain the first choice.
- If distinct-player data candidates are insufficient, the mail may include news/opinion X post candidates for different players.
- News/opinion fallback must be evidence-backed:
  - source article title
  - source URL or WP post URL
  - source excerpt / existing draft excerpt if used
  - detected player name
- News/opinion fallback must not invent facts, quotes, statistics, or claims from memory.
- If a mail mixes data and news/opinion candidates, the subject/body label must not imply that every candidate is data-only. Use a mixed label such as `巨人Xポスト案` or candidate-level labels `データ` / `ニュース意見`.

## acceptance

- Fixture: 2026-05-18 mail 型の 8 候補を再現し、`マルティネス 3/8` / `岸田 行倫 2/8` が発生する現状 test を先に赤で固定する。
- 修正後、十分な代替 Giants row がある fixture では同一 player は 1 件までになる。
- 代替 row が足りない fixture では同一 player は最大 2 件までで、候補数を 0 にしない。
- Data candidates aloneで distinct player が足りない fixture では、recent news/opinion fallback で別 player 候補を補充する。
- News/opinion fallback candidate は source title / source URL / excerpt / player detection evidence を mail card または log に持つ。
- News/opinion fallback candidate は source に無い quote / 数字 / 断定を作らない。
- `focus_player_names` がある時の既存 lineup spread 挙動は壊さない。
- `dedup_set` がある時の combo dedup は壊さない。
- 374 の dedup starvation fallback は壊さない。
- `period-family skip` は維持する。
- skip / fallback は structured log で evidence 化する。
- 実装 verify では production GCS DB を read-only pull し、`latest_game_date` / `latest_giants_game_date` を記録する。

## stop conditions

- player cap のため候補 mail が 0 件になる設計は不可。
- production DB / GCS upload が必要になったら stop。
- Scheduler / env / Secret 変更が必要になったら stop。
- X API / SNS live post が必要になったら stop。
- 本番 DB を取得できない状態で「本番修正確認済み」と書かない。
