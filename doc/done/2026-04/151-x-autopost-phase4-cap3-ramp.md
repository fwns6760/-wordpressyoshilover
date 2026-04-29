# 151 x-autopost-phase4-cap3-ramp

## dropped note(2026-04-29)

- status: DROPPED
- reason: Dropped. X API ramp-up is obsolete under the GPTs/manual posting policy.

## meta

- number: 151
- alias: 147-Phase4
- owner: Claude Code / Codex A
- type: ops / X auto-post daily cap 1 → 3 ramp
- status: DROPPED(150 + 7 日 stable 後 fire)
- priority: P1
- lane: Claude / A
- created: 2026-04-26
- parent: 147
- blocked_by: 150 + 7 日観察

## 目的

X auto-post Phase 4。`X_POST_DAILY_LIMIT` = 1 → 3 引き上げ。

## scope

- env 切替(user op): `X_POST_DAILY_LIMIT` = `1` → `3`
- 他 setting 維持
- 引き続き 119 Green / 120 duplicate / failure stop / category 制限

## acceptance

1. daily cap 3 件 enforce
2. 7-30 日 stable で cron 化判断(別 ticket)

## 完了後

- 30 日 stable → cron 化検討
- 事故発生 → cap revert + 修正
