# 192 doc hygiene retry

## meta

- number: 192
- owner: Codex
- type: doc-only / git retry
- status: COMPLETED
- priority: P0.5
- lane: B
- created: 2026-04-27
- parent: 189 / 190 / 191

## Background

- 前便 189 doc hygiene は working tree 更新まで完了していたが、commit が未確定のまま残っていた。
- その後 `189` 番は別 Codex セッションでも使用され、manual X candidate 系の landed commit と番号衝突の可能性が生じた。
- 本 retry は ticket 番号を `192` に振り直し、残っていた doc-only 変更を整理し直すもの。

## Scope

- `doc/README.md`
- `doc/active/assignments.md`
- `doc/active/190-publish-notice-manual-x-candidates-impl.md`
- `doc/active/191-publish-notice-manual-x-candidates-spec.md`
- `doc/done/2026-04/183-publish-gate-aggressive-relax.md`
- `doc/done/2026-04/184-ledger-integration-cloud-run.md`
- `doc/done/2026-04/186-scan-limit-pagination-and-history-dedup-narrow.md`
- `doc/done/2026-04/187-publish-notice-scheduler-uri-v1-fix.md`
- `doc/done/2026-04/188-publish-notice-scheduler-iam-fix.md`
- `doc/done/2026-04/189-publish-notice-contextual-manual-x-candidates.md`
- `doc/done/2026-04/deploy-rebuild-2026-04-26-evening.md`

## Work Performed

- 183 / 184 / 186 / 187 / 188 と deploy rebuild note を `doc/active/` から `doc/done/2026-04/` へ整理した。
- 183 / 184 / 187 / 188 の ticket doc 先頭 status を close 後の状態に合わせて補正した。
- board / assignments 側の 183-191 反映済み差分を温存し、189 の parent を 190 / 191 参照へ補正した。
- 190 / 191 を active ticket として保持し、manual X candidate の番号衝突整理を継続できる状態にした。

## Git Observation

- mount 上は `/home/fwns6/code/wordpressyoshilover/.git` が read-only 表示だった。
- ただし retry 時点では doc-only の通常 git path も再試行対象とし、必要時のみ plumbing fallback へ切り替える。
