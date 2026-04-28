# 150 x-autopost-phase3-trigger-on-cap1

## meta

- number: 150
- alias: 147-Phase3
- owner: Claude Code / Codex A
- type: ops / X auto-post trigger ON
- status: BLOCKED_TICKET(149 close 後 fire)
- priority: P0.5
- lane: Claude / A
- created: 2026-04-26
- parent: 147
- blocked_by: 149

## 目的

X auto-post Phase 3。`X_POST_AI_MODE=auto` + `X_POST_DAILY_LIMIT=1` で **WP publish trigger 連動 auto X 投稿 ON**。

## scope

- env 切替(user op):
  - `X_POST_AI_MODE` = `none` → `auto`
  - `X_POST_DAILY_LIMIT` = `1`
  - `X_POST_AI_CATEGORIES` = `試合速報,選手情報,首脳陣`(維持)
- WP publish 後 `x_published_poster_trigger.py` 経路で auto X 投稿
- 119 Green-only + 120 ledger duplicate guard 通過のみ
- daily cap 1 件 enforce
- ledger に毎回記録
- 7 日観察(事故 0 / failure 0 確認)

## non-goals

- 2 件以上 daily cap
- cron 化(後続 ticket)
- Yellow / Red 投稿
- category 拡張

## acceptance

1. WP publish 後自動 X 投稿(category 該当のみ、Green only)
2. daily cap 1 件 enforce(2 件目 refused)
3. duplicate refused
4. failure 時自動連投なし
5. 7 日 stable で 151(cap 3)へ

## 完了後

- 7 日 stable → 151 へ ramp
- 事故発生 → 中断 + cause 修正 narrow
