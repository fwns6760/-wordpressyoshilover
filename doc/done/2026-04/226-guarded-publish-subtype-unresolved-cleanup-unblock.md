# 226 guarded publish subtype_unresolved cleanup failure unblock

## meta

- number: 226
- type: dev / quality / publish gate
- status: **CLOSED**(2026-04-28、commit `357a53c` landed、guarded-publish image rebuild `25f176b` で live 反映、subtype_unresolved + cleanup_failed_post_condition の safe case が Yellow 降格動作確認)
- priority: P0.5
- lane: **Codex B**(quality / evaluator / cleanup chain)
- created: 2026-04-27
- closed: 2026-04-28
- parent: 217 publish gate hotfix / 200 scanner subtype fallback / 224 entity-role consistency
- last_commit: `357a53c` 226: subtype_unresolved + cleanup_failed_post_condition の安全 case を publishable Yellow に降格

## background

マーケ運用上の「記事供給が止まる」問題、技術的には:
- 63809 / 63811 が refused
- error: `subtype_unresolved_no_resolution`
- hold_reason: `cleanup_failed_post_condition`

Scheduler / rss_fetcher / guarded-publish / publish-notice 全部 live で動いてるが、guarded-publish gate で **safe case まで refused** で発信されない → publish-notice emit=0、mail 来ない。

200 で scanner subtype fallback 実装済だが、evaluator / runner 側の `subtype_unresolved` / `cleanup_failed_post_condition` 判定が strict すぎる。

## goal

- subtype_unresolved を **scanner fallback 解決済 case で flag 立てない**
- cleanup_failed_post_condition の **危険 flag なし + body 残存 case** で publishable Yellow + warning に降格
- 危険 hard_stop flag(`death_or_grave_incident` / `unsupported_named_fact` / `obvious_misinformation` / `cross_article_contamination`)は **不変**
- 217 roster_movement_yellow / 224 awkward_role_phrasing と同 Yellow flag pattern 流用

## scope

- `src/guarded_publish_evaluator.py`: subtype_unresolved + cleanup_failed_post_condition の判定緩和
- `src/guarded_publish_runner.py`: yellow_log に reason 記録
- `tests/test_guarded_publish_evaluator.py`: 63809 / 63811 fixture + 緩和 case test
- `tests/test_guarded_publish_runner.py`: 関連 test 更新

## acceptance

- subtype_unresolved_no_resolution で不必要に止まらない
- cleanup_failed_post_condition の safe case が publishable Yellow に降格
- 危険記事は引き続き止まる(hard_stop 維持)
- 200 / 217 / 218 / 224 logic 不変
- pytest baseline 維持

## non-goals

- 大量公開 / Red 記事公開
- 危険 hard_stop flag 緩和
- WP live write / GCP deploy(別便)
- 200 scanner / 183 post-cleanup verify 変更

## next_action

- impl 進行中 `bhnmw4tc7`(Codex B fire 済)
- 完了通知 → 5 点追認 → push → guarded-publish rebuild + Job update(authenticated executor、別便)
- deploy 後、63809 / 63811 が publishable Yellow になるか自然 cron で verify

## related ticket

- 217 publish gate hotfix(injury_death 分解、roster_movement_yellow flag pattern)
- 200 scanner subtype fallback(本便で解決済 fallback を活かす)
- 218 manual_x_post_candidates 品質改善
- 224 article body entity-role consistency(awkward_role_phrasing flag pattern)
