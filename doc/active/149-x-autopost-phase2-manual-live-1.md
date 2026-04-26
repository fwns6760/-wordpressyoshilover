# 149 x-autopost-phase2-manual-live-1

## meta

- number: 149
- alias: 147-Phase2
- owner: Claude Code(orchestration)/ Codex A(必要なら helper)
- type: ops / X live POST 1 件 manual smoke
- status: BLOCKED_TICKET(148 close 後 fire)
- priority: P0.5
- lane: Claude / A
- created: 2026-04-26
- parent: 147
- blocked_by: 148

## 目的

X auto-post Phase 2。**1 件だけ live POST** で X 投稿経路 + account 表示確認。trigger 連動はまだ ON にしない、`manual_post.py` 単独 fire。

## scope

- 148 で OK 出た文案から 1 件選定(post_id 指定)
- `python3 -m src.manual_post --post-id <ID> --x-only --live` 実行(or 同等 CLI)
- ledger に `posted_at` 記録
- X account timeline で visual 確認 = user op
- duplicate guard 確認

## non-goals

- 2 件以上 live
- trigger 連動 ON
- daily cap 設定
- WP write

## acceptance

1. 1 件だけ live POST 成功
2. tweet ID + URL が log に記録
3. duplicate 再投稿拒否(同 post_id を再 fire → refused)
4. secret 値 log/chat に表示なし
5. user 確認後 150 へ

## 完了後

- user OK → 150(trigger ON + daily cap 1)へ
- 投稿問題発見 → 中断 + 修正 narrow 起票
