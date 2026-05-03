# BUG-003 + BUG-004+291 3-id publish status revert audit

更新日時: 2026-05-03 JST

## scope

- read-only audit only
- target ids: `64196`, `64198`, `64352`
- comparison ids: `64194`, `64343`
- broad-scan support id: `64259`
- live evidence used:
  - `gcloud logging read` (`baseballsite`, window `2026-05-03 09:00:00 JST` to `2026-05-03 16:30:00 JST`)
  - `gs://baseballsite-yoshilover-state/guarded_publish/guarded_publish_history.jsonl`
  - `gs://baseballsite-yoshilover-state/publish_notice/queue.jsonl`
- no code change / no deploy / no env change / no Scheduler change / no WP write

## limitation

- sandbox からの WP REST direct GET は `curl: (6) Could not resolve host: yoshilover.com` で失敗した。
- したがって **最終の exact non-publish state (`draft` / `private` / `trash`) は未検証**。
- `2026-05-03 16時台 JST` に `64196 / 64198 / 64352` が public GET で `401` だったこと、および `64194 / 64343` は publish 維持だったことは、Claude WSL 側の直接確認結果を前提事実として扱う。

## executive finding

1. `64196 / 64198 / 64352` は `2026-05-03 14:21-14:41 JST` 時点で publish-notice queue に現れているが、**current-day guarded terminal state は 3件とも `sent` ではない**。
2. 比較対象の `64194 / 64343` は同じ publish-notice suppress (`PUBLISH_ONLY_FILTER`) を踏んでいるが、**guarded terminal state は `sent`** で、16時台も publish 維持だった。
3. `cleanup_failed_post_condition` / `cleanup_backup_failed` / `publish_failed` は当該 window で `0`。**guarded-publish cleanup/postcheck failure が 3件を non-publish に戻した証拠はない**。
4. BUG-003 の「mail が飛んだら非公開化」仮説は、**時刻相関はあるが因果は弱い**。理由は:
   - publish-notice path に WP status write code がない
   - 同じ suppress を踏んだ `64194 / 64343` は publish 維持
   - `64196 / 64352` は suppress 後に追加の GCP-side mutation log がなく、`64198` も `REVIEW_RECENT_DUPLICATE` / `backlog_only` loop だけが続いている
5. 3件の共通点は `publish-notice` に見えている一方で、**guarded durable history 上は publish finalization (`status=sent`) に達していない**こと。BUG-003 で既知の publish bypass / silent status-upgrade リスクと整合する。

## primary evidence

### 1. publish-notice live filter change

- `publish-notice` job update: `2026-05-03 10:02:57 JST`
- live flag: `ENABLE_PUBLISH_ONLY_MAIL_FILTER=1`
- after this timestamp, per-post mail は `subject` ベースで `【公開済】` 以外が suppress される。

### 2. cleanup / publish failure absence

`2026-05-03 09:00-14:00 JST` window summary:

- `cleanup_failed_post_condition = 0`
- `cleanup_backup_failed = 0`
- `publish_failed = 0`
- `hourly_cap = 0`
- `burst_cap = 0`
- `daily_cap = 0`

Read:

- guarded-publish 後段の cleanup/cap/postcheck が 3件の revert を起こした証跡はない。

## 3-id timeline

### `64196`

Durable history:

- `2026-05-01 14:30:40 JST` `status=refused` `hold_reason=review_date_fact_mismatch_review`
- `2026-05-02 14:35:36 JST` `status=refused` `hold_reason=review_date_fact_mismatch_review`
- `2026-05-03 14:35:39 JST` `status=refused` `hold_reason=review_date_fact_mismatch_review`

Publish-notice queue:

- `2026-05-03 14:40:39 JST` `status=queued` `reason=review_date_fact_mismatch_review`
- `2026-05-03 14:41:11 JST` `status=suppressed` `reason=PUBLISH_ONLY_FILTER`
- subject: `【要review】「2026江戸前スーシーズ」グッズを発売🍣 ...`
- `publish_time_iso=2026-05-01T14:30:28+09:00`

Post-14:41 evidence:

- `2026-05-03 14:41:12-16:30 JST` の `gcloud logging read` で `post_id=64196` / `"post_id": 64196` の追加 mutation log は 0

Interpretation:

- queue 側では「published history を持つ review article」として再通知候補化されている
- guarded durable history では current-day terminal state は一貫して `refused`
- `16時台 JST` では public GET `401` 前提なので、direction は `publish -> non-publish`
- exact target state は未検証だが、**`draft` が第一候補**。`review_date_fact_mismatch_review` に戻っている形と整合する

### `64198`

Durable history:

- `2026-05-01 14:35:36 JST` `status=refused` `hold_reason=review_duplicate_candidate_same_source_url`
- `2026-05-02 14:35:36 JST` 以降 `status=skipped` `hold_reason=backlog_only`
- `2026-05-03 14:40-16:25 JST` も `status=skipped` `hold_reason=backlog_only` が 5 分周期で継続

Publish-notice queue:

- `2026-05-03 14:40:39 JST` `status=queued` `reason=backlog_only`
- `2026-05-03 14:41:11 JST` `status=suppressed` `reason=PUBLISH_ONLY_FILTER`
- subject: `【要確認(古い候補)】新イニング間イベント 「RINOKA’s BEEEATS!」 ...`
- `publish_time_iso=2026-05-01T14:30:34+09:00`

Post-14:41 evidence:

- `2026-05-03 14:45:42 JST` から `16:25:59 JST` まで:
  - guarded-publish: `"post_id": 64198` line が 5 分周期で継続
  - publish-notice: `[skip] post_id=64198 reason=REVIEW_RECENT_DUPLICATE` が 5 分周期で継続

Interpretation:

- 3件の中で最も強く **draft/backlog candidate loop** が見えている
- `16時台 JST` public GET `401` とも整合するため、**`publish -> draft` 仮説が最有力**
- exact target state は未検証だが、`private` / `trash` を示す証拠は 0

### `64352`

Durable history:

- `2026-05-03 14:15:39 JST` `status=refused` `hold_reason=review_date_fact_mismatch_review`

Publish-notice queue:

- `2026-05-03 14:20:40 JST` `status=queued` `reason=review_date_fact_mismatch_review`
- `2026-05-03 14:21:09 JST` `status=suppressed` `reason=PUBLISH_ONLY_FILTER`
- subject: `【要review】阿部監督「野球って不思議。いろいろなことを考えさせられた」 ベンチ関連発言`
- `publish_time_iso=2026-05-03T14:10:55+09:00`

Post-14:21 evidence:

- `2026-05-03 14:21:10-16:30 JST` の `gcloud logging read` で `post_id=64352` / `"post_id": 64352` の追加 mutation log は 0

Interpretation:

- queue の `publish_time_iso` は same-day publish visibility を示すが、guarded durable history は same-day `refused`
- つまり **publish visibility と guarded terminal state が同じ post_id で乖離**している
- `16時台 JST` public GET `401` 前提なので direction は `publish -> non-publish`
- exact target state は未検証だが、**`draft` が第一候補**。理由は hold family が `review_date_fact_mismatch_review` で統一されているため

## comparison: stable 2 ids

### `64194`

Durable history:

- `2026-05-03 14:35:39 JST` `status=sent` `cleanup_success=true`

Publish-notice queue:

- `2026-05-03 14:40:38 JST` `status=queued` subject starts `【公開済】`
- `2026-05-03 14:41:11 JST` `status=suppressed` `reason=PUBLISH_ONLY_FILTER`
- reclassified subject: `【要確認】「こどもの日」グッズを発売...`

Read:

- same suppress path を踏んでも `16時台 JST` publish 維持

### `64343`

Durable history:

- `2026-05-03 14:05:37 JST` `status=sent` `cleanup_success=true`

Publish-notice queue:

- `2026-05-03 14:10:33 JST` `status=queued` subject starts `【公開済】`
- `2026-05-03 14:10:58 JST` `status=suppressed` `reason=PUBLISH_ONLY_FILTER`
- reclassified subject: `【要確認】立岡「立岡コーチとともに…」 関連発言`

Read:

- same suppress path を踏んでも `16時台 JST` publish 維持

## mutation-source ranking

### 1. most likely: WP-side or out-of-band status mutation on non-anchored posts

What this means:

- manual WP operation
- WP plugin / WP cron / external automation
- legacy published post being reclassified without current guarded `sent` anchor

Evidence:

- revert 3件は current-day guarded terminal state が `sent` ではない
- stable 2件は current-day guarded terminal state が `sent`
- `cleanup_failed_post_condition` / `cleanup_backup_failed` / `publish_failed` は 0
- `64196 / 64352` は suppress 後の GCP mutation log がない
- `64198` も later evidence は `backlog_only` / `REVIEW_RECENT_DUPLICATE` loop だけ

Confidence: `medium`

### 2. likely contributing risk, but not proven immediate actor: BUG-003 publish bypass / silent status upgrade

Relevant repo risks:

- `src/rss_fetcher.py:finalize_post_publication()` direct publish bypass
- `src/wp_client.py:_reuse_existing_post()` silent draft-like status upgrade

Evidence:

- BUG-003 static auditで publish-notice / cron-health / X-poster 側に demotion path は未検出
- 逆に publish-state と guarded durable history が乖離しうる bypass/upgrade path は存在
- `64352` の same-day `publish_time_iso` vs same-day `guarded_history.status=refused` は、この「ledger に乗らない publish visibility」と整合する

Confidence: `medium`

### 3. unlikely: guarded-publish cleanup / republish / postcheck failure

Evidence:

- `cleanup_failed_post_condition = 0`
- `cleanup_backup_failed = 0`
- `publish_failed = 0`
- cap系も 0

Confidence: `low`

### 4. unlikely as direct cause: mail trigger / publish-notice send path

Evidence:

- same suppress path を踏んだ `64194 / 64343` は publish 維持
- publish-notice code path は BUG-003 static auditで WP status mutation なし
- current queue result は `suppressed`, not `sent`

Confidence: `low`

## BUG-003 time-correlation verdict

Verdict: **time-correlated but not causally supported**

Why:

1. filter apply timestamp is `2026-05-03 10:02:57 JST`
2. target queue suppress timestamps are:
   - `64352`: `2026-05-03 14:21:09 JST`
   - `64194 / 64196 / 64198`: `2026-05-03 14:41:11 JST`
   - `64343`: `2026-05-03 14:10:58 JST`
3. final non-publish observation is `2026-05-03 16時台 JST`
4. **same suppression family hit stable posts too**
5. no WP status write path was found in mail code, and no guarded cleanup failure event exists in the same window

Conclusion:

- mail path can explain why the 3件 looked confusing in publish-notice
- mail path does **not** explain why only 3/5 became non-publish later

## subtype / source pattern

### revert 3 ids

| post_id | queue subject family | guarded last hold family | publish-time pattern |
|---|---|---|---|
| `64196` | goods / event (`【要review】`) | `review_date_fact_mismatch_review` | old publish (`2026-05-01`) |
| `64198` | inning event / old candidate (`【要確認(古い候補)】`) | `backlog_only` | old publish (`2026-05-01`) |
| `64352` | manager / bench comment (`【要review】`) | `review_date_fact_mismatch_review` | same-day publish (`2026-05-03`) |

Read:

- 3件すべて同一 subtype ではない
- ただし **all three are non-`sent` on guarded durable history**
- `review_date_fact_mismatch_review` cluster (`64196`, `64352`) と `backlog_only old_candidate` cluster (`64198`) に分かれる

## broad scan boundary

Window `2026-05-03 09:00-16:30 JST`:

- numeric post_ids that entered publish-notice queue: `23`
- of those, last guarded durable history status was not `sent`: `14`

Observed same-shape at-risk ids beyond the requested 3:

- `64259`
- `64080`
- `64085`
- `64167`
- `64169`
- `64331`
- `64177`
- `64183`
- `64201`
- `64368`
- `64207`

Important boundary:

- only `64196 / 64198 / 64352` are confirmed by Claude WSL as non-publish in `2026-05-03 16時台 JST`
- the additional 11 ids are **same-shape queue/history mismatches only**
- expanding them to current WP status verification should be a separate follow-up ticket

## recommended next action

1. **authenticated WP-side verification**
   - Claude / user shell で `context=edit` or admin-side status trace
   - capture `status`, `modified`, `modified_gmt`, `author`, `slug`, and if possible revision/meta trail for `64196 / 64198 / 64352`
   - goal: exact direction (`publish -> draft/private/trash`) と mutation timestamp の固定

2. **BUG-003 hardening**
   - route all publish status changes through one guarded helper
   - remove or make explicit `_reuse_existing_post()` publish upgrade
   - write durable `status_before`, `status_after`, `caller`, `source lane`, `post_id`, `ts` on every WP status mutation

3. **publish-notice contract tightening**
   - do not treat non-`sent` guarded rows as publish-like without an explicit lane marker
   - current queue/history mismatch is operationally confusing even when it is not the revert source

4. **follow-up ticket if user wants wider blast-radius check**
   - scan the 11 additional same-shape ids above for current WP status
   - do not bundle that expansion into this 3-id audit

## USER_DECISION_REQUIRED

`yes`

Reason:

- exact final target state of the 3 reverted posts is still unverified from this sandbox
- the next decisive step is WP-side authenticated observation, not more repo-only inference
- there are 11 additional same-shape ids that should not be expanded without explicit scope approval

## open questions

1. `64196 / 64198` were already carrying `publish_time_iso=2026-05-01`. What actor kept them publish-visible into `2026-05-03` while guarded durable history stayed non-`sent`?
2. `64352` has same-day `publish_time_iso=14:10:55 JST` but same-day guarded durable history `status=refused` at `14:15:39 JST`. Which path created that publish visibility?
3. For the 3 reverted posts, is the exact current state `draft`, `private`, or `trash`?
4. Are there WP plugin / cron / admin actions between `2026-05-03 14:21 JST` and `16時台 JST` that touched only non-anchored posts?
