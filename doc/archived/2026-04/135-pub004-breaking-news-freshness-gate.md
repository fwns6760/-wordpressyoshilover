# 135 pub004-breaking-news-freshness-gate

## meta

- number: 135(user 指定 134 はリナンバー、134 = 本日 doc reorg で `35fb67c` 使用済)
- alias: -
- owner: Claude Code(設計)/ Codex A(実装)
- type: ops / publish gate / freshness audit
- status: **READY**(P0、105 ramp の前提、即 fire)
- priority: **P0**
- lane: A
- created: 2026-04-26
- supersedes: なし(130 hard_stop set 拡張)
- parent: 130 / 105 / PUB-002-A

## 目的

YOSHILOVER は **速報掲示板**。古いニュースを「今日の新着」として自動公開しない。
本日 4/26 10:23 PM の 105 第 1 burst(20 件 sent)で **4/24 created の draft が今日新着扱いで publish された**疑い。

original cause:
- PUB-004 backlog ramp が古い draft を判定対象にした
- modified は cleanup / 再評価で更新されるため信用しない
- 鮮度判定が evaluator に存在しなかった

修正:
- evaluator に **freshness gate** 追加
- created_at + 本文内 date 表現 + source date を見る
- subtype 別 freshness threshold で hard_stop 化
- 既 publish 済 20 件は本 ticket では **削除しない**(audit 出力のみ)

## Freshness policy(subtype 別 threshold)

| subtype | threshold | 超過時 |
|---|---|---|
| `lineup` / `pregame` / `probable_starter` | **6 時間** | hard_stop(`expired_lineup_or_pregame`)+ 試合開始後推定も hard_stop |
| `postgame` / `game_result` | **24 時間** | hard_stop(`expired_game_context`)|
| `roster` / `injury` / `registration` / `recovery` | **24 時間** | hard_stop(既存 `injury_death` も維持)|
| `comment` / `speech` / `program` / `off_field` / `farm_feature` | **48 時間** | hold(`stale_for_breaking_board`)|
| その他(default) | **24 時間** | hold(`stale_for_breaking_board`)|

**重要**: 4/24 記事を 4/26 に出すのは **不可**(全 subtype で stale)。

## 追加 hard_stop flags

- `stale_for_breaking_board`(default 24h 超)
- `expired_lineup_or_pregame`(lineup/pregame 6h 超 or 試合開始後推定)
- `expired_game_context`(postgame 24h 超)

## evaluator 出力追加 field

各 entry に:
- `content_date`(`YYYY-MM-DD` 形式、source date 優先 → なければ created_at の date 部分)
- `freshness_age_hours`(now JST - content_date、float)
- `freshness_class`: `fresh` / `stale` / `expired`
- `freshness_reason`(threshold 適用 + subtype 名 + 算出根拠)

summary に:
- `fresh_count`
- `stale_hold_count`
- `expired_hold_count`

human summary に:
- stale top list(post_id / title / content_date / age_hours / subtype / freshness_reason)

## content_date 算出 logic

優先順位:
1. **source date**(source URL から取れる published date / dateline)
2. **本文内日付表現**(`4月24日` / `2026-04-24` / `4/24` / `日付:` 等の regex)
3. **created_at**(WP post 本体の date field)
4. **modified は使わない**(cleanup / 再評価で更新されるため信用しない)

## 影響範囲

- src/guarded_publish_evaluator.py:
  - HARD_STOP_FLAGS set に 3 新 flag 追加
  - freshness_check() 関数追加
  - evaluate_post() 内で freshness 判定 + 出力 field 追加
  - summary に fresh_count / stale_hold_count / expired_hold_count 追加
- tests/test_guarded_publish_evaluator.py:
  - 4/24 created の draft が 4/26 now で publishable=false 確認
  - modified=4/26 でも created_at=4/24 なら hold
  - lineup/pregame 6h 超 hold
  - postgame 24h 超 hold
  - comment/program/off_field 48h 以内 publishable
  - default 24h 超 hold
  - source date があれば created_at より優先
- 必要なら src/pre_publish_fact_check/extractor.py:
  - 本文内日付表現抽出 helper(必要時のみ)

## 不可触

- src/guarded_publish_runner.py(evaluator 結果使うが runner logic 不変)
- src/wp_client.py / src/lineup_source_priority.py / src/published_site_component_audit.py
- src/sns_topic_*.py / src/publish_notice_email_sender.py(別 lane)
- LLM call / mail real-send / X / SNS POST / WP write
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY`
- automation / scheduler / front / plugin / build
- requirements*.txt 改変
- baseballwordpress repo
- **4/26 10:23 publish 済 20 件の自動削除/非公開化**(audit 出力のみ、削除は別 ticket judge)
- `git add -A`
- **git push**

## acceptance

1. 3 新 hard_stop flags 実装 + HARD_STOP_FLAGS set 追加
2. freshness_check() 関数 + subtype 別 threshold 適用
3. evaluator 出力に content_date / freshness_age_hours / freshness_class / freshness_reason 追加
4. summary に fresh_count / stale_hold_count / expired_hold_count 追加
5. human summary に stale top list 追加
6. modified を鮮度判定に **使わない**(test で verify)
7. source date があれば created_at より優先
8. 既存 evaluator/runner tests pass(suite 1248 baseline 維持、新 tests 追加で 1256+)
9. 新 fail 0(デグレなし lock)
10. WP write zero / live publish なし

## verify

- python3 -m pytest tests/test_guarded_publish_evaluator.py -v(新 + 既存全 pass)
- python3 -m pytest 2>&1 | tail -3(suite 1256+ pass / 0 failed)
- python3 -m pytest --collect-only -q | tail -3(1256+ collected)
- 105 dry-run 再実行: `python3 -m src.tools.run_guarded_publish_evaluator --window-hours 999999 ... --output /tmp/pub004d/full_eval_v3_freshness.json` で fresh_count / stale_hold_count / expired_hold_count visible

## 完了後 actions

1. 105 dry-run 再実行(fresh-only ramp planning)
2. 4/26 10:23 publish 済 20 件の `possibly_stale_published` audit(read-only WP REST GET、Claude 直)
3. 必要なら別 ticket 136 で「possibly_stale_published を non-public に戻す」judge

## 注意

本 ticket は「公開速度を落とす」ためではなく、**速報掲示板として古いニュースを今日の新着に見せない**ための安全 gate。
135 後も fresh な記事は autonomous で publish して良い(105 lock 維持)。
