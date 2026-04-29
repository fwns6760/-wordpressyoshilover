# 249-INGEST live game ingestion expansion

## meta

- number: 249-INGEST
- type: ingestion / live-game backlog
- status: HOLD
- priority: P1
- owner: Meeting Codex / Claude planning
- implementation_owner: TBD after explicit user GO
- lane: B / infra after GO
- created: 2026-04-29
- depends_on: 247-QA-amend, postgame strict game-day observation, user explicit GO
- related: 246-MKT, 247-QA, 244 numeric guard, 230D scheduler overlap audit

## purpose

全打席速報や試合中更新を扱えるか検討する。

これは今すぐ実装しない。
Cloud Run / Scheduler / ingestion 負荷への影響が大きいため、ユーザー GO 必須。

## background

YOSHILOVER を「巨人ファンが試合前後に寄る場所」にするには、将来的に試合中の流れや全打席系の情報も価値になり得る。
ただし live ingestion はコスト・安定性・誤情報・重複投稿のリスクが高い。

## candidate scope

- 試合中の inning / at-bat signal を扱えるか調査
- live_update subtype の責務整理
- Cloud Scheduler cadence / overlap risk の再確認
- 投稿ではなく dry-run / candidate ledger から開始
- 234 / 244 の数字 guard を必ず通す

## non-goals

- いま実装しない
- 247-QA に混ぜない
- 246-MKT に混ぜない
- X API なし
- Gemini 追加呼び出しなし
- いきなり auto publish しない
- Cloud Run / Scheduler 変更は user GO なしで行わない

## risk

- Cloud Run 実行時間増加
- Scheduler overlap
- Gemini / GCP cost 増
- 試合中の誤情報
- 重複記事
- stale live update
- WP publish gate への影響

## GO condition

- 247-QA amend が完了
- postgame strict を試合日に観察
- 既存 fetcher / guarded-publish / draft-body-editor が安定
- user が Cloud Run / Scheduler 影響を理解して明示 GO

## HOLD condition

- 本文品質が不安定
- cost ledger が見えない
- Scheduler overlap が解消していない
- user がマーケより品質安定化を優先

## one-line contract

試合中 ingestion は魅力があるが重い。dry-run から。Cloud Run / Scheduler 変更は user GO 必須。デグレ厳禁。
