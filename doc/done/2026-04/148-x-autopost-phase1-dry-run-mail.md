# 148 x-autopost-phase1-dry-run-mail

## meta

- number: 148
- alias: 147-Phase1
- owner: Codex A
- type: ops / X dry-run + mail 文案確認
- status: **READY**(P0.5、即 fire 可)
- priority: P0.5
- lane: A
- created: 2026-04-26
- parent: 147

## 目的

X auto-post 再開の Phase 1。**実 X 投稿なし**で、直近 publish 5 件分の文案を build → mail 送信、user で文案 visual 確認。

## scope

- 入力: 119 Green-only filter + category 制限(試合速報/選手情報/首脳陣)= 直近 publish 5 件
- 文案 build: `src/x_post_template_candidates.py`(107 既装)使用
- mail 送信: `src/publish_notice_email_sender.py`(088 既装)or X 専用 dry-run mail 1 通
- 出力: 文案 5 件 + 元記事 URL + category + post_id を mail body に整形
- X API call **絶対なし**(`X_POST_AI_MODE` 切替不要、dry-run mail のみ)

## non-goals

- X API 実投稿
- WP write
- env 切替(本 phase は code-only dry-run)
- LLM call
- cron / scheduler

## acceptance

1. 直近 publish 5 件の文案 build 成功
2. mail 1 通 user 宛に送信(subject `[X-DRY-RUN] 文案 5 件確認`)
3. body に: post_id / title / category / X 文案(280 char 以内)/ 元 URL
4. X API call zero(grep verify)
5. baseline 1297/0 維持

## 完了後

- user 文案 visual 確認 → OK or fix → 149(Phase 2: 1 件 manual live)へ進む
