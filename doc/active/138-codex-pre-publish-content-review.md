# 138 codex-pre-publish-content-review

## meta

- number: 138
- alias: -
- owner: Claude Code(設計)/ Codex A(実装)
- type: ops / publish gate / Codex content review chain
- status: READY(140 land 後 fire)
- priority: P0(105 ramp の前提、user 新方針 = 「全部自動公開 + Codex content review 必須」)
- lane: A
- created: 2026-04-26
- parent: 105 / 130 / 135 / PUB-004

## 目的

user 新方針(2026-04-26 PM): 「記事の中身を Codex で見てから、全部自動公開」。
105 burst publish 前に **Codex便で各 draft 本文 review** を挟み、`verdict=ok` のみ publish へ通す。
freshness gate(135)は audit 信号として残すが、Codex review が brand / factual / safety を最終判断。

## flow(3 step orchestration)

```
[eval pool] → publishable.json
   ↓
[pack builder] → /tmp/review_prompt.txt(各 publishable 候補の post_id + title + body 抜粋 + source_urls + content_date + freshness_class)
   ↓
[Codex review便] codex exec --full-auto < /tmp/review_prompt.txt > /tmp/verdict.json
   ↓ {post_id: ok/ng, reason}
[runner --filter-verdict] /tmp/verdict.json → ok のみ publish
```

## 実装(2 src tools + 1 runner option)

### src/codex_pre_publish_pack_builder.py(新規)

機能:
- 入力: publishable list(eval JSON 出力 → publishable=true entries)
- 各 entry の WP REST 経由で title + body excerpt(冒頭 500 chars + 末尾 200 chars)+ source_urls + content_date + freshness_class + subtype 取得
- review prompt 形式に整形(JSON list + prompt 指示)
- 出力: `/tmp/codex_review_prompt.txt`

review prompt 内容(Codex への指示 inline):
- 「以下の N 件 draft 本文を review。verdict {ok, ng} を JSON list で返す」
- review 観点(各 draft):
  1. factual safety: 数字 / 日付 / 選手名が source_urls の domain と整合
  2. freshness sanity: content_date が今日 or 直近で速報掲示板に適合
  3. brand fit: 速報掲示板 YOSHILOVER の tone(ファン視点 / 一次情報核)
  4. duplicate: pool 内同 title / 同 lineup の重複なし
  5. SNS leak: 本文に raw SNS post text / handle / URL なし
  6. structure: heading / dev_log_contamination / site_component_mixed なし(cleanup chain で解消可なら ok)
- 出力 format: `[{"post_id": N, "verdict": "ok|ng", "reasons": [...]}, ...]`

### src/tools/run_codex_pre_publish_pack.py(新規 CLI)

引数:
- `--input-from <eval.json>`(135 + 137 後 evaluator 出力)
- `--max-pool N`(default 50、cost 抑制)
- `--output <prompt.txt>`(default /tmp/codex_review_prompt.txt)
- `--format {prompt,json}`(prompt = Codex 投入用、json = debug)

### src/guarded_publish_runner.py 改修(--filter-verdict 追加)

引数追加:
- `--filter-verdict <verdict.json>`(default なし、指定時のみ Codex review 結果で filter)
- verdict.json schema: `[{post_id: N, verdict: "ok|ng", reasons: [...]}]`
- runner は input pool の post_id ∩ verdict.ok のみを candidate に絞る
- verdict.ng は hold(`hold_reason: codex_review_ng_<top_reason>`)

### tests

新規 8+ tests:
- `test_pack_builder_formats_publishable_list`
- `test_pack_builder_includes_source_urls_and_freshness`
- `test_pack_builder_excludes_unpublishable`
- `test_pack_builder_truncates_body_to_500_plus_200`
- `test_runner_filter_verdict_ok_publishes`
- `test_runner_filter_verdict_ng_held_with_reason`
- `test_runner_no_filter_verdict_works_as_before`(後方互換)
- `test_runner_partial_verdict_intersect_only`(verdict にない post_id も hold 扱い)

## baseline 維持 contract(必須)

- **suite collect 数 1276+ 維持**(新 tests 追加で 1284+)
- **既存 fail 数 0 を維持**(新規 fail 0)
- src/guarded_publish_evaluator.py 改変禁止(135/136 land 直後)
- 既存 runner CLI 後方互換維持(--filter-verdict なしで動く)
- WP REST GET のみ、書き込みなし

## 不可触

- src/wp_client.py / src/lineup_source_priority.py / src/published_site_component_audit.py
- src/sns_topic_*.py(別 lane)
- src/publish_notice_email_sender.py
- src/guarded_publish_evaluator.py(135/136 直後)
- LLM API call(Codex 便 spawn のみ、API 直叩きなし)
- mail real-send / X / SNS POST / WP write
- live publish(本 ticket は pack + filter logic のみ、actual publish は別 invocation)
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY`
- automation / scheduler / front / plugin / build
- requirements*.txt 改変
- baseballwordpress repo
- doc reorg
- `git add -A`
- **git push**

## acceptance

1. pack builder が publishable list → review prompt 出力
2. review prompt が Codex 用 format(JSON list + 指示)
3. runner に --filter-verdict 引数追加(後方互換維持)
4. verdict.ok のみ publish、ng は hold(reason 記録)
5. 既存 runner / evaluator tests pass
6. 新 tests 8+ pass
7. **suite collect 1284+ / 0 failed**(baseline 維持、デグレなし)
8. WP write zero / live publish なし(pack 段階)

## verify

- python3 -m pytest tests/test_codex_pre_publish_pack.py tests/test_guarded_publish_runner.py -v
- python3 -m pytest 2>&1 | tail -3(suite 1284+ pass / 0 failed)
- python3 -m pytest --collect-only -q | tail -3
- python3 -m src.tools.run_codex_pre_publish_pack --help

## 完了後 orchestration(Claude 直、本 ticket では実装しない)

```bash
# 1. eval pool
python3 -m src.tools.run_guarded_publish_evaluator ... --output /tmp/full_eval.json

# 2. pack builder
python3 -m src.tools.run_codex_pre_publish_pack --input-from /tmp/full_eval.json --output /tmp/codex_review_prompt.txt

# 3. Codex review (Claude が fire)
codex exec --full-auto -C /home/fwns6/code/wordpressyoshilover - < /tmp/codex_review_prompt.txt > /tmp/codex_verdict.json

# 4. publish OK only
python3 -m src.tools.run_guarded_publish --input-from /tmp/full_eval.json --filter-verdict /tmp/codex_verdict.json --max-burst 20 --live --daily-cap-allow
```

## 注意

- Codex review便 = 既存 lane(A/B/C)とは独立、orchestration 専用 fire
- review cost = Codex便 1 回(無料)、API call なし
- review prompt 中に SNS leak / secret 含めない(post body excerpt は cleanup 後の表示用)
- verdict NG は hold、削除しない(後で再 review or 別 cycle で publish 可)
