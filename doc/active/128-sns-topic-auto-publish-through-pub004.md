# 128 sns-topic-auto-publish-through-pub004

## meta

- number: 128
- owner: Codex A / Claude orchestration
- lane: A
- priority: P1
- status: PARKED
- blocked_by: 127 close + PUB-004 readiness
- parent: 127 / PUB-004 / PUB-002-A
- created: 2026-04-26

## purpose

127 が作成した `draft_ready` 記事を、既存 PUB-004 gate に通して自動 WordPress publish まで進める。
user の記事ごとの確認は不要に寄せるが、生SNS話題から直接publishしない。

## policy

- 自動publishは 127 の source recheck pass 済 draft のみ。
- publish 判断は既存 PUB-004-A / PUB-004-B を使う。
- Red は publish しない。
- Yellow は PUB-004 policy に従うが、SNS由来の Yellow は `yellow_log` に必ず記録する。
- noindex / mail / publish-notice は既存運用に任せる。
- X/SNS post はしない。

## flow

1. 126: SNS topic fire intake
2. 127: source recheck + WP draft generation
3. 128: run PUB-004 evaluator against those drafts
4. publishable entries go through PUB-004-B guarded publish
5. publish history / yellow log / cleanup log are written by existing PUB-004 paths
6. publish-notice mail is handled by existing 095 cron

## safety gates

- 127 `source_recheck_passed=true`
- draft status only
- PUB-004 evaluator publishable
- burst cap 3
- daily cap follows PUB-004
- backup before content cleanup / publish
- postcheck public URL 200
- history dedup

## non-goals

- direct publish from SNS signal
- raw SNS quote article
- X/SNS post
- Cloud Run env / `RUN_DRAFT_ONLY`
- new scheduler until dry-run and one live burst are safe
- index decision

## acceptance

1. Only 127-created source-rechecked drafts are considered.
2. PUB-004 evaluator is mandatory before publish.
3. Red refused; no bypass flag.
4. Dry-run shows would_publish / refused / reasons.
5. Live mode respects PUB-004 burst/daily caps and backup/history.
6. No X/SNS post occurs.
7. Tests or smoke fixtures prove SNS-derived draft cannot bypass source recheck.

## suggested files

- `src/sns_topic_publish_bridge.py`
- `src/tools/run_sns_topic_publish_bridge.py`
- `tests/test_sns_topic_publish_bridge.py`

## test command

```bash
python3 -m pytest tests/test_sns_topic_publish_bridge.py tests/test_guarded_publish_runner.py
python3 -m src.tools.run_sns_topic_publish_bridge --fixture <drafts.json> --dry-run
```

## activation

After dry-run and one safe live burst, this lane may be connected to the broader PUB-004 automation.
No separate cron is added in this ticket unless PUB-004 readiness allows it.
