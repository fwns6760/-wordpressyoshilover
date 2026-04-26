# 127 sns-topic-source-recheck-and-draft-builder

## meta

- number: 127
- owner: Codex A / B depending on implementation slice
- lane: A/either
- priority: P1
- status: PARKED
- blocked_by: 126 close
- parent: 126 / 064 / 067 / PUB-002-A
- created: 2026-04-26

## purpose

126 のSNS話題候補を、公式 / 球団 / 報道 / RSS で再確認し、記事化してよいものだけ WordPress draft または候補リストにする。

## policy

- SNS反応は本文の根拠にしない。
- SNS本文の転載、個別ポスト引用、アカウント晒しをしない。
- 事実の根拠は公式 / 球団 / 報道 / RSS。
- source recheck が通らないものは draft にしない。
- draft生成は自動でよいが、publish は 128 / PUB-004 gate まで進めない。

## source recheck rules

Route each 126 candidate:

- `draft_ready`: primary source confirmed, duplicate not excessive, article angle is safe
- `candidate_only`: topic is interesting but fact source is missing or weak
- `hold_sensitive`: injury / diagnosis / family / harassment / rumor risk
- `duplicate_news`: already covered by recent RSS/news
- `reject`: unsafe or unusable

## draft rules

Draft must be written as a normal YOSHILOVER article candidate:

- no SNS post text
- no usernames / handles / fan account URLs
- no "SNSで話題"だけの見出し
- short fan trend mention is allowed as tendency only
- title/body fact comes from confirmed source
- source links are official/reporting/RSS, not fan reaction
- `noindex` remains unchanged by this lane

## output

- JSON summary of routed candidates
- optional WP draft creation for `draft_ready`
- all created drafts must include:
  - `source_recheck_passed=true`
  - `sns_topic_seed=true`
  - `topic_category`
  - `source_urls`
  - `publish_gate_required=true`

## non-goals

- WP publish
- X/SNS post
- X API / paid API
- Grok / xAI
- automatic index decision
- raw SNS quote article
- 2chまとめ風 article

## acceptance

1. 126 candidates are source-rechecked before draft generation.
2. `draft_ready` requires confirmed non-SNS source.
3. Weak / sensitive / duplicate topics are held or rejected.
4. WP draft generation is automatic only for `draft_ready`.
5. Draft body contains no raw SNS post text or account identifiers.
6. JSON summary + draft IDs are reported.
7. No publish occurs.
8. Tests cover source confirmed, source missing, sensitive hold, duplicate news, and no raw SNS leakage.

## suggested files

- `src/sns_topic_source_recheck.py`
- `src/tools/run_sns_topic_source_recheck.py`
- `tests/test_sns_topic_source_recheck.py`

## test command

```bash
python3 -m pytest tests/test_sns_topic_source_recheck.py
python3 -m src.tools.run_sns_topic_source_recheck --fixture <intake.json> --dry-run
```

## next

127 output feeds 128. Publish is not allowed in 127.
