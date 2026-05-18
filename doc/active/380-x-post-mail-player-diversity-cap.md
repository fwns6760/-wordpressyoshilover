# 380-x-post-mail-player-diversity-cap

## status

- **status**: READY
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
