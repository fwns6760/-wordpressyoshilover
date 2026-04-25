# PUB-005 x-post-gate

## meta

- owner: Claude Code(設計 + 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / X / SNS POST gate / controlled autopost
- status: READY(doc-first、実装は 119-122 の子 ticket で進める)
- parent: PUB-002 / PUB-002-A
- sibling: PUB-004 guarded-auto-publish-runner(WP publish lane、本 ticket とは別 lane)
- created: 2026-04-25
- policy lock: 2026-04-26(X / SNS は WP より厳格、Green only、one-time live unlock 後に controlled autopost)

## scope 線引き

| 制限対象 | 本 ticket スコープ | 別 ticket |
|---|---|---|
| X / SNS / 外部 POST | 本 ticket(PUB-005)= Green only + controlled autopost + daily cap | - |
| WordPress publish | 触らない | PUB-004(Red 以外 publish、autonomous) |
| X 検索 / X 収集 | 触らない | 別 lane |

## priority

P1(PUB-004 の公開品質が安定し、119 の候補選定が通ってから live 解禁へ進める)。
本 doc は umbrella で、実装は 119-122 の numbered tickets に分割する。

## purpose

X / SNS への POST は、WP publish より厳格な品質 gate を通す。
対象は WordPress 公開済み記事のうち、Green only + 強い source + title-body 一致 + speculative なし + sensitive なし + 同 game 重複なしの記事だけ。

運用方針は「毎投稿の user 確認」ではなく、one-time live unlock 後に daily cap 内の controlled autopost へ進める。
ただし最初の X API live 接続、credential 境界、初回 1 件 smoke は user 判断境界として止める。

## 重要制約(全 phase 共通)

- X 投稿対象は WordPress 公開済み Green 記事のみ
- Yellow / Red / cleanup 前提記事は X 投稿しない
- 未 publish の draft は対象外
- WP publish lane(PUB-004)とは独立し、PUB-004 が publish した記事の中から再選定する
- X API 認証情報(`X_API_KEY` 等)は `.env` 経由、実値表示禁止
- Grok / xAI API は使わない
- X 検索 / X 収集はこの解禁 lane に混ぜない
- daily cap は初期 1 件/日、安定後 3 件/日
- cron 化は最後。one-shot smoke と controlled rollout が安定するまで行わない

## X-side Red 条件(候補 evaluator で refuse)

WP publish が通っても、X POST 候補化では以下を refuse:

- source 弱い(primary 媒体 1 件未満、Twitter only、社内 source mapping なし)
- title が speculative(「どう見るか」「ポイントはどこ」「予想」「気になる」系)
- title-body が一致していない、または body が title 主張を支えていない
- injury / death / 登録抹消 / 診断 / 症状 言及あり
- 同一試合 / 同一選手の X 投稿が直近 24h で既出
- 4/17 事故と同質リスク
- 数値リスト型の記事(NPB 通算安打 ranking 等)で検証が弱い
- quote-heavy で出典が不明確
- cleanup 前提の site component / dev log / H3 sentence collapse が残っている

上記いずれかに該当した記事は X 候補から除外し、refuse reason を記録する。

## 不可触

- WordPress publish 機構(PUB-004 lane に任せる)
- `.env` / X API secret 表示
- `RUN_DRAFT_ONLY` flip
- Cloud Run env / scheduler
- automation.toml / Codex Desktop 側
- baseballwordpress repo
- front lane / plugin
- Grok / xAI API
- X 検索 / X 収集

---

## 分割(後続実装の見取り図)

### 119: x-post-eligibility-evaluator(read-only)

- 公開済み WP 記事を fetch し、PUB-002-A Green 条件 + X-side Red 条件で評価する
- 出力:
  - `x_eligible: [{post_id, title, link, why_eligible}]`
  - `x_refused: [{post_id, title, refuse_reasons}]`
- WP write なし
- X API call なし
- LLM call なし
- 既存 107 / `src/x_post_template_candidates.py` を後続文案候補生成の土台として扱う

### 120: x-post-autopost-queue-and-ledger

- 119 eligible + 107 template candidates を queue 化する
- `candidate_hash` で同一候補の二重投稿を防ぐ
- ledger 項目:
  - `post_id`
  - `article_url`
  - `template_type`
  - `candidate_hash`
  - `queued_at`
  - `posted_at`
  - `status`
- X API call なし

### 121: x-post-live-helper-one-shot-smoke

- queue 内の 1 件だけ X API で投稿する one-shot smoke
- dry-run default
- `--live` 必須
- secret 実値表示禁止
- Grok / xAI API 禁止
- `src/x_post_generator.py` の古い Grok/Gemini 経路を使わない
- 成功時は ledger を更新し、duplicate 再投稿を拒否する
- 最初の live smoke は one-time user unlock / credential boundary として止める

### 122: x-post-controlled-autopost-rollout

- controlled autopost の段階解禁
- 初期 daily cap 1 件
- 安定後 daily cap 3 件
- 投稿ごとの user 確認は不要
- cron 化はさらに後続判断
- failure / duplicate / cap 超過時は stop し、refuse reason を記録する

---

## 連携

- PUB-004(WP publish lane): publish 済記事の集合を生成、本 lane の input 候補
- PUB-002-A(判定 contract): Green / Yellow / Red の正本。本 lane は X-side Red を追加 strict
- 107 / PUB-005-A2: X 文案候補 dry-run。119/120 の後続で流用
- HALLUC-LANE-002: land 後に G3/G7/G8 の完全 verify 経路として統合
- `src/x_api_client.py`: 121 で live post helper の低レベル X API 経路として必要範囲のみ流用
- CLAUDE.md §18 + AGENTS.md `X_POST_DAILY_LIMIT` 準拠

## 完了条件(本 umbrella)

1. WP lane と X lane が独立した ticket として明示(PUB-004 / PUB-005)
2. X-side Red 条件が WP publish より strict なことが明文化
3. one-time live unlock 後の controlled autopost 方針が明文化
4. 119-122 の実装順と blocked state が固定
5. Grok / xAI API 禁止、X 検索 / X 収集の別 lane 扱いが明文化

## stop 条件

- X API credential / live post へ進む時(121)
- X 自動投稿 cron 化要望(122 の後続)
- X API rate limit 超過
- X 認証情報の表示 / 露出
- WP publish との連携で WP 側を改変したくなる
- Grok / xAI API を使おうとする
- X 検索 / X 収集を本 lane に混ぜようとする

## 関連 file

- `doc/102-ticket-index-and-priority-board.md`
- `doc/119-x-post-eligibility-evaluator.md`
- `doc/120-x-post-autopost-queue-and-ledger.md`
- `doc/121-x-post-live-helper-one-shot-smoke.md`
- `doc/122-x-post-controlled-autopost-rollout.md`
- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`
- `doc/PUB-004-guarded-auto-publish-runner.md`
- `src/x_post_template_candidates.py`
- `src/x_api_client.py`
