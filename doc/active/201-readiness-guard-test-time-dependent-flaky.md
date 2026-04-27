# 201 readiness-guard test time-dependent flaky

## meta

- number: 201
- owner: Claude Code(起票) / Codex B(次便 fix)
- type: test-only / flaky cleanup
- status: **READY**
- priority: P1
- lane: B
- created: 2026-04-27
- depends:
  - 200 scanner subtype fallback(CLOSED `e78f088`)

## 背景

- 200 commit 後、scanner 限定 pytest は green だが、full pytest では 1 件だけ residual fail が残る。
- failing test は `tests/test_guarded_publish_readiness_guard.py::test_human_format_renders_summary`。
- failure は scanner 変更と完全に disjoint で、`src/publish_notice_scanner.py` / `tests/test_publish_notice_scanner.py` とは無関係。

## failure 事実

- test は `cli.main(["--history-path", ..., "--format", "human"])` を real clock で呼ぶ。
- fixture の history row は `2026-04-26T08:00:00+09:00` / `2026-04-26T09:00:00+09:00` に固定されている。
- production code 側は `datetime.now(JST)` ベースで 24h window を切るため、fire 時刻が進むと row が window 外に落ちる。
- その結果、rendered text が `summary: sent=1 refused=1 skipped=0` を満たさず fail する。
- `2026-04-27 11:00 JST` rerun では window が `2026-04-26T11:00:29+09:00` 以降になり、summary が `sent=0 refused=0 skipped=0` に崩れることを確認済み。

## 期待する fix

- 第一候補: test 内で fixed `now` を注入する。
- 実装案:
  - `src.tools.run_guarded_publish_readiness_check` に `now` 注入点を追加する
  - または test で `_now_jst` / `evaluate_guarded_publish_readiness` を patch して deterministic にする
  - `freezegun` のような新 dependency 追加は避ける
- fallback:
  - fixed `now` 注入が狭い diff で難しい場合のみ、summary assertion を時間依存しない形へ緩和する

## scope

- primary: `tests/test_guarded_publish_readiness_guard.py`
- if needed for testability only:
  - `src/tools/run_guarded_publish_readiness_check.py`
  - `src/guarded_publish_readiness_guard.py`

## do not

- `src/publish_notice_scanner.py` を再度触らない
- `tests/test_publish_notice_scanner.py` を巻き込まない
- `src/publish_notice_email_sender.py` を触らない
- WP / Cloud Run / Scheduler / Secret / X を触らない

## acceptance

1. `test_human_format_renders_summary` が実行日によらず stable に pass
2. full pytest の residual 1 fail を解消
3. 200 scanner commit との write scope 分離を維持
4. `git add -A` なし、doc / test の明示 stage のみ

## 関連ファイル更新先

- 新規: `doc/active/201-readiness-guard-test-time-dependent-flaky.md`
- 更新: `doc/README.md`
- 更新: `doc/active/assignments.md`
