# 152 x-autopost-all-categories-expansion

## dropped note(2026-04-29)

- status: DROPPED
- reason: Dropped. Broad X API autopost expansion is obsolete under the GPTs/manual posting policy.

## meta

- number: 152
- alias: -
- owner: Claude Code(future 設計)
- type: ops / X auto-post category 拡張
- status: DROPPED(future、147 phase 5 安定後)
- priority: P2
- lane: future
- created: 2026-04-26
- parent: 147

## 目的

現 X auto-post の category 制限(`試合速報 / 選手情報 / 首脳陣` = postgame/lineup/manager 3 種)を、**全 publish カテゴリへ拡張**する将来 ticket。

## 現状制約

- `X_POST_AI_CATEGORIES=試合速報,選手情報,首脳陣`
- pregame / farm / off_field / comment 等は X 投稿対象外

## 拡張案(将来検討)

- 段階的に追加: pregame 追加 → farm 追加 → ...
- 各 category 別 daily cap?
- category 別 template 切替?
- 拡張時は人気ジャンル先行

## 不可触(現時点)

- 全 implementation 凍結
- 147 phase 1-4 land + 7-30 日 stable 観察 後に解凍判断

## 次 action

147 phase 5 安定後 user 判断 → 設計 + 実装 fire
