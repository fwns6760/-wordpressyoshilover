# 147 x-autopost-phased-resume

## meta

- number: 147
- alias: PUB-005-resume / 120-122 統合
- owner: Claude Code(orchestration)/ Codex A(env / smoke 実装)
- type: ops / X live post 段階解禁
- status: PARKED(X API live automation paused; manual X posting via GPTs/Gmail flow is current)
- priority: P0.5(MVP 公開後拡散導線、X 復活)
- lane: A
- created: 2026-04-26
- parent: PUB-005 / 119(eligibility)/ 120-122(ramp child)

## 経路(user lock)

- **WP publish trigger 連動 auto X post**(`x_published_poster_trigger.py` 経路、過去実績再開)
- 補助: `manual_post.py` で手動 1 件 fire 可能
- category 制限: **試合速報 / 選手情報 / 首脳陣**(現 env、postgame/lineup/manager subtype 相当)
- 全 publish カテゴリ拡張は **152 別 ticket** で future

## 5 phase ramp(段階解禁)

### Phase 1: dry-run 文案確認(148)
- `X_POST_AI_MODE=safe`(or 既存 dry-run flag)に切替
- 直近 publish 5 件分の文案 build → mail で送信 + visual 確認
- X API 実投稿なし
- user で文案 OK 判断

### Phase 2: 1 件 manual smoke(149)
- `manual_post.py` で 1 件選定 + live POST(post_id 指定)
- X account 表示確認 = user op
- ledger に `posted` 記録
- **user 確認後**次 phase

### Phase 3: trigger ON + daily cap 1(150)
- `X_POST_AI_MODE=auto` 切替
- WP publish trigger 連動 = publish 後自動 X 投稿
- daily cap = 1 件
- 119 Green-only filter + 120 ledger duplicate guard 通過のみ
- 7 日観察

### Phase 4: daily cap 1 → 3(151)
- 7 日事故なしで daily cap 引き上げ
- 引き続き Green-only / duplicate guard / failure stop 維持

### Phase 5: cron 化(別 ticket)
- 122 安定後、別 ticket で cron 化判断

## env 切替表(設計、実値は user 確認)

| phase | X_POST_AI_MODE | X_POST_DAILY_LIMIT | X_POST_AI_CATEGORIES |
|---|---|---|---|
| 1 (148) | safe(dry-run only) | 0 | 試合速報,選手情報,首脳陣 |
| 2 (149) | none(manual_post 単独) | manual で N/A | 同上 |
| 3 (150) | auto | 1 | 同上 |
| 4 (151) | auto | 3 | 同上 |
| 5 (cron) | auto | 3 | 同上 |

## 不可触

- X 検索 / X 収集(別 lane)
- Grok / xAI API(過去 Grok 経路 deprecated)
- Yellow / Red 記事の投稿
- WP write / cleanup(本 ticket は X 投稿のみ)
- LLM real call(本 ticket は文案 build に既存 src 流用)
- `.env` の値変更 = user op(secret は user が直接編集)
- automation / scheduler 改変
- baseballwordpress repo
- `git add -A` / git push

## 既装 infra(再利用)

- `src/x_api_client.py`(create_tweet via tweepy)
- `src/x_published_poster.py`(WP publish 連動)
- `src/x_published_poster_trigger.py`(trigger 経路)
- `src/manual_post.py`(手動 fire CLI)
- `src/x_post_template_candidates.py`(107 文案 generator)
- `src/x_post_eligibility_evaluator.py`(119 Green-only filter)
- `.env`: 7 X credentials ready(X_API_KEY 等)

## acceptance(全 phase)

1. Phase 1-4 順次 land、各 phase で前段の安定確認後に次 phase 進む
2. Green only(119 経由)
3. duplicate guard(120 ledger)
4. category 制限(env で enforce)
5. failure 時自動連投なし
6. secret 値表示なし
7. baseline 1297/0 維持(各 phase commit で)

## 次 action

148(Phase 1 dry-run 5 件 mail 確認便)を A に fire。

## 関連 ticket

- 119 x-post-eligibility-evaluator(CLOSED `0253b2a`)
- 120 x-post-autopost-queue-and-ledger(本 147 ramp に統合、別便で実装)
- 121 x-post-live-helper-one-shot-smoke(149 phase 2 で代替)
- 122 x-post-controlled-autopost-rollout(150-151 phase 3-4 で代替)
- PUB-005 x-post-gate(parent runbook)
- 152 x-autopost-all-categories-expansion(future、全 publish 対象拡張)
