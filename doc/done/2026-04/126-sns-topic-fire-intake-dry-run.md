# 126 sns-topic-fire-intake-dry-run

## meta

- number: 126
- owner: Codex B
- lane: B
- priority: P0.5
- status: READY
- parent: 064 / 082 / 106
- created: 2026-04-26

## purpose

巨人ファンのSNS上で反応が出ている話題を「記事化候補の火種」として拾う。
SNS投稿本文の転載や個人アカウント露出は行わず、話題の傾向だけを候補化する。

## policy

- SNS is a signal, not a source of fact.
- SNS本文は保存しない / 表示しない / 記事本文へ引用しない。
- 個人アカウント名、ID、URLを候補出力に含めない。
- 炎上、誹謗中傷、個人攻撃、晒し、対立煽りは reject。
- 事実確認は 127 で公式 / 球団 / 報道 / RSS によって行う。
- 本 ticket は read-only / dry-run。WP draft / publish はしない。

## topic categories

- `player`
- `manager_strategy`
- `bullpen`
- `lineup`
- `farm`
- `injury_return`
- `transaction`
- `acquisition_trade`

## input sources

Use existing repo mechanisms before adding anything new:

- existing Yahoo realtime helper in `src/rss_fetcher.py`
- existing fan reaction precision rules from 082
- local fixture / JSON input for tests
- RSS index only as duplicate/news-overlap reference, not as fact confirmation in this ticket

No X API credentials, no Grok/xAI, no new paid API.

## output

One candidate is a topic cluster, not a quoted post:

```json
{
  "topic_key": "...",
  "category": "player",
  "entities": ["..."],
  "trend_terms": ["..."],
  "signal_count": 12,
  "source_tier": "reaction",
  "fact_recheck_required": true,
  "route_hint": "source_recheck",
  "unsafe_flags": []
}
```

## refuse / reject

- slur / insult / harassment terms
- individual account exposure required to explain the topic
- private person / family / rumor centering
- injury / diagnosis / roster move asserted only from SNS
- direct quote needed but source is only fan reaction
- too few matching signals
- same topic already covered by recent RSS/news article with high overlap

## acceptance

1. Topic clusters are emitted without post text, usernames, handles, or URLs.
2. Category classification covers the 8 MVP categories.
3. Unsafe / inflammatory topics are rejected.
4. `fact_recheck_required=true` is set for all SNS-derived candidates.
5. Output is JSON + human summary.
6. Tests cover player, strategy, bullpen, lineup, farm, injury/return, transaction, acquisition/trade, and unsafe rejection.
7. No WP write, no X API, no live publish, no secret read/display.

## suggested files

- `src/sns_topic_fire_intake.py`
- `src/tools/run_sns_topic_fire_intake.py`
- `tests/test_sns_topic_fire_intake.py`

## test command

```bash
python3 -m pytest tests/test_sns_topic_fire_intake.py
python3 -m src.tools.run_sns_topic_fire_intake --fixture <fixture.json>
```

## next

126 output feeds 127. It must not feed article generation or publish directly.
