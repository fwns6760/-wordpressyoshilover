# 440 - X-impression spec timing 5: lineup 直後 trigger

## meta

- status: CLOSED
- priority: P2
- owner: Claude
- lane: x-impression / scheduler
- created: 2026-05-27
- closed: 2026-05-27
- doc_path: doc/done/2026-05/440-XIMPR-lineup-immediate-trigger.md
- spec: mkdocs_docs/spec/x-impression-plan.md item 5 「出稿タイミングを決める」

## 背景

spec/x-impression-plan.md item 5「出すタイミング」 のうち「スタメン直後」 が
既存 scheduler で抜けていた:

- 試合前: `x-post-mail-flush` 0 6-22 / `data-insight-pregame-trigger` 17:00 ◯
- **スタメン直後: 抜け** (lineup は `lineup-auto-pregame` 0,15,30,45 17-18 で
  fetch されるが、 x-post-mail は次の hourly flush まで最大 60 分待ち)
- 試合中強イベント: `x-post-mail-flush-game-1` 15,30,45 19-20 ◯
- 試合直後: `x-post-mail-flush-game-2` 15,30,45 21-22 ◯

## 実施

`x-post-mail-flush-lineup` scheduler を新規作成:

- schedule: `15,30,45 17-18 * * *` (Asia/Tokyo)
- target: 既存 `x-post-mail-lane` Job (Cloud Run Job HTTP trigger、 同 SA)
- 既存 `x-post-mail-flush` (0 6-22) と組み合わせて、 17-18 JST は 0/15/30/45
  の 15 分間隔で flush、 lineup fetch (lineup-auto-pregame と同 cadence) の
  直後に x-post 候補 mail が出る

## 受け入れ条件

- [x] scheduler ENABLED
- [x] 既存 4 scheduler (`flush` / `flush-game-1` / `flush-game-2` /
      `lineup-auto-pregame`) に競合無し
- [ ] 次の 17-18 JST 帯で実 fire 確認 + lineup-直後 mail 到達確認

## blast radius

- mail 数 increase: 17-18 JST に 6 fire 追加 (× 1 mail target)
- cost: Cloud Run Job invocation 6 回/日 (無視可能、 既存無料枠内)
- rollback: `gcloud scheduler jobs delete x-post-mail-flush-lineup` で即可

## Codex scope 重複回避

Codex は spec/x-impression-plan の Phase 1 / 6-10 (X API spend cap 関連)
を別途扱う。 本 ticket は scheduler infra のみで、 src コード touch 無し。
