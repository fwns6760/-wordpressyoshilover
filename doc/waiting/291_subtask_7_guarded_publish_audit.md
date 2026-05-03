# 291 subtask-7 guarded-publish gate reason audit

| field | value |
|---|---|
| ticket | BUG-004+291 subtask-7 |
| date | 2026-05-03 JST |
| mode | read-only |
| scope | fetcher narrow unlock 2 drafts -> guarded-publish gate reason audit |
| result | AT_RISK |

## conclusion

- `weak_title_narrow_unlock` で draft 化された 2 件は、どちらも `guarded-publish` に到達していた。silent path ではない。
- `post_id=64313`(farm / 森田駿哉) は `guarded-publish-s94zq` で `hard_stop_farm_result_placeholder_body` により deterministic に block された。これは gate 緩和対象ではない。
- `post_id=64311`(player / 阿部「野球って不思議だな」) は `guarded-publish-s94zq` で `review_duplicate_candidate_same_source_url` により publish されなかった。
- ただし `duplicate_of_post_id=64297` は同日 09:30 JST の fetcher log 上では `【三軍】巨人 vs 新潟選抜 ...` / `media_url=https://twitter.com/TokyoGiants/status/2050718230445215894` の別 source であり、`same_source_url` reason の整合性に疑義がある。
- よって本件は `publish gate 全体緩和` が必要なのではなく、`duplicate reason integrity` の narrow fix 候補があるため `AT_RISK` と判定する。

## phase 1: target draft identification

### target A: player sample

| item | value |
|---|---|
| title | `阿部「野球って不思議だな」 関連発言` |
| source_name | `スポーツ報知巨人班X` |
| source_url_hash | `56d3df6d85e92233` |
| source_url | `https://twitter.com/hochi_giants/status/2050667568357069237` |
| weak unlock | `2026-05-03 09:41:17 JST` |
| draft create log | `2026-05-03 09:41:24 JST` |
| post_id | `64311` |
| draft url | `https://yoshilover.com/?p=64311` |

evidence:

- `2026-05-03 09:36:27 JST` `article_skipped_post_gen_validate` with `skip_reason=weak_generated_title:no_strong_marker`
- `2026-05-03 09:41:17 JST` `weak_title_narrow_unlock`
- `2026-05-03 09:41:24 JST` `[WP] 記事draft post_id=64311`

### target B: farm sample

| item | value |
|---|---|
| title | `二軍 森田駿哉が２戦連続の快投 ３安打無失点で３勝目「変化球の精度も良くなっ…` |
| source_name | `スポーツ報知巨人班X` |
| source_url_hash | `1fa38579c416cfb2` |
| source_url | `https://twitter.com/hochi_giants/status/2050514017743999210` |
| weak unlock | `2026-05-03 09:41:28 JST` |
| draft create log | `2026-05-03 09:41:35 JST` |
| post_id | `64313` |
| draft url | `https://yoshilover.com/?p=64313` |

evidence:

- `2026-05-03 09:36:28 JST` `article_skipped_post_gen_validate` with `skip_reason=weak_generated_title:no_strong_marker`
- `2026-05-03 09:41:28 JST` `weak_title_narrow_unlock`
- `2026-05-03 09:41:35 JST` `[WP] 記事draft post_id=64313`

## phase 2: guarded-publish gate trace

### common execution

- `guarded-publish` execution: `guarded-publish-s94zq`
- observed window: `2026-05-03 09:45:38-09:45:40 JST`
- `proposed=[]`, `would_publish=0`

### target A: post_id=64311

guarded-publish evidence:

- `2026-05-03 09:45:38 JST` `jsonPayload.event=backlog_narrow_publish_eligible`
  - `post_id=64311`
  - `narrow_kind=allowlist`
  - `subtype=comment`
  - `age_hours=33.76`
  - `threshold_hours=48`
- same execution refused block:
  - `post_id=64311`
  - `reason=review`
  - `hold_reason=review_duplicate_candidate_same_source_url`
  - `duplicate_of_post_id=64297`
  - `duplicate_reason=same_source_url`

path interpretation:

- freshness / backlog:
  - `backlog_narrow_publish_eligible` が出ているため、backlog allowlist 自体は通っている
- terminal gate:
  - duplicate check で stop
- not observed as terminal reason:
  - numeric guard fail
  - placeholder fail
  - body_contract fail
  - hard_stop
  - stale / backlog_only
  - existing_publish_same_source_url

publish-notice follow-up:

- `2026-05-03 09:51:01 JST` `publish-notice-dhdd2`
  - `[skip] post_id=64311 reason=REVIEW_EXCLUDED`

### target B: post_id=64313

guarded-publish evidence:

- same execution refused block:
  - `post_id=64313`
  - `reason=hard_stop`
  - `hold_reason=hard_stop_farm_result_placeholder_body`
- same execution executed block:
  - `post_id=64313`
  - `status=refused`
  - `publish_link=""`

path interpretation:

- terminal gate:
  - placeholder/body quality hard stop
- not observed as terminal reason:
  - duplicate
  - backlog_only
  - freshness
  - numeric guard
  - existing_publish_same_source_url

publish-notice follow-up:

- `2026-05-03 09:51:01 JST` `publish-notice-dhdd2`
  - `[skip] post_id=64313 reason=REVIEW_EXCLUDED`

## local ledger / file inspection

- local `logs/guarded_publish_history.jsonl` and `logs/guarded_publish_yellow_log.jsonl` stop at `2026-04-26` and contain no rows for:
  - `post_id=64311`
  - `post_id=64313`
  - `source_url_hash=56d3df6d85e92233`
  - `source_url_hash=1fa38579c416cfb2`
- therefore the local repo copies are stale proxies for this audit window and cannot be used as authoritative evidence for 2026-05-03 09:36-10:50 JST.
- local `logs/cleanup_backup/` also has no files for `64311` or `64313`.

## phase 3: silent path check

- `silent before guarded-publish`: not detected
  - both targets have fetcher draft-create logs and then appear in `guarded-publish-s94zq`
- `silent inside guarded-publish`: not detected
  - both targets have explicit terminal reasons in guarded-publish output
- `silent after guarded-publish`: not detected
  - both targets appear in publish-notice as `REVIEW_EXCLUDED`

## reason-integrity risk on post_id=64311

`review_duplicate_candidate_same_source_url` itself is an allowed gate, but the recorded target is suspicious:

- `duplicate_of_post_id=64297`
- fetcher logs for `64297` at `2026-05-03 09:30 JST` show:
  - title: `【三軍】巨人 vs 新潟選抜 HARD OFF ECOスタジアム新潟🏟 8時…`
  - media/source url: `https://twitter.com/TokyoGiants/status/2050718230445215894`
  - subtype: `farm_lineup` -> resolved `farm`
- this does not match the source of `64311`:
  - `https://twitter.com/hochi_giants/status/2050667568357069237`
  - title: `阿部「野球って不思議だな」 関連発言`
  - subtype path: `player` -> guarded allowlist log says `comment`

This means:

- the candidate was not silent; it was explicitly blocked
- but the recorded `same_source_url` duplicate target appears inconsistent with available source evidence
- the narrow follow-up should be on duplicate mapping integrity, not on relaxing the duplicate gate

## phase 4: narrow unlock -> publish return minimal condition

### user-confirmed publish recovery boundary

BUG-004+291の回収対象は、publish gate全体緩和ではなく、以下の高信頼記事タイプに限定する。

- 試合結果記事: 当日 + 巨人対象 + 相手 + スコアがsource/title/meta/bodyから取れるもの。sourceにない投手成績は本文に書かない。
- 監督・コーチコメント: 一部引用でもsourceが明確なら救う。postgameへ雑分類しない。
- 選手コメント: 選手名とコメント元が明確ならscoreなしでもplayer_commentとして救う。
- 二軍結果: farm_resultとして、二軍 / 相手 / スコアが取れるなら救う。
- 二軍スタメン: farm_lineupとして、スタメン表 / 打順 / 選手名が取れるなら救う。
- pregame / 予告先発: probable_starter / pregame / lineupは救う。ただし試合後の古いpregameは出さない。
- 昇格・降格・復帰・二軍落ち・若手記事: notice / roster_notice / injury_recovery_notice / farm_player_result等へ寄せる。

維持する禁止境界:

- live update断片、placeholder本文、body_contract fail、numeric guard fail、YOSHILOVER対象外、source_urlなし、subtype不明、review/hold理由あり、重複記事、stale postgame、何の記事かわからないweak titleはpublishしない。
- duplicate guardは緩めない。今回のsubtask-8候補はduplicate bypassではなく、duplicate target integrityの修正に限定する。

### no fix needed for 64313

- `hard_stop_farm_result_placeholder_body` is a correct gate class to keep closed
- do not relax:
  - placeholder
  - body contract / publishable quality
  - hard stop behavior

### narrow fix candidate for 64311

proposed subtask count: `1`

subtask proposal:

- `BUG-004+291 subtask-8`(same parent chain, no new ticket number)
- scope:
  - audit/fix `review_duplicate_candidate_same_source_url` target selection for backlog allowlist / narrow unlock candidates
- minimum acceptance:
  - before assigning `duplicate_of_post_id`, require exact `source_url_hash` match, not only a broader or stale key
  - write both candidate hash and duplicate target hash/source into history/log
  - if the target fails exact match, do **not** silently drop; record an integrity-failure class and continue deterministic evaluation
- explicit non-goals:
  - do not bypass duplicate exclusion
  - do not loosen stale/postgame strict/hard stop gates
  - do not change publishability thresholds

## final judgment

- `post_id=64313`: CLEAN per-post outcome
  - deterministic hard stop, no follow-up needed beyond keeping the gate closed
- `post_id=64311`: AT_RISK per-post outcome
  - terminal reason exists, but duplicate target integrity is suspect

Overall ticket-level result: `AT_RISK`

- because the 2 drafts were not silently skipped, but one of the two blocking reasons likely points to the wrong duplicate target
- this is a narrow duplicate-mapping integrity problem, not a justification for gate relaxation
