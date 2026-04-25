# PUB-005 x-post-gate

## meta

- owner: Claude Code(設計 + 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / X / SNS POST gate / quality fixed
- status: READY(PUB-004 安定後の起票候補、本 ticket は doc-first)
- parent: PUB-002 / PUB-002-A
- sibling: **PUB-004 guarded-auto-publish-runner**(WP publish lane、本 ticket とは別 lane)
- created: 2026-04-25
- policy lock: 2026-04-25 21:55(X / SNS は WP より厳格、user 確認 fixed)

## scope 線引き(2026-04-25 lock)

| 制限対象 | 本 ticket スコープ | 別 ticket |
|---|---|---|
| **X / SNS / 外部 POST** | ✓ 本 ticket(PUB-005)= Green only + user 確認 | - |
| **WordPress publish** | ✗ 触らない | PUB-004(Red 以外 publish、autonomous) |

## priority

P1(PUB-004 完了 + 1 週間運用後の起票候補)
本 ticket は **doc-first** = 起票だけ、実装は X 解放判断後。

## purpose

X / SNS への自動 POST は、WP publish より厳格な品質 gate を通す。
完璧な記事(Green only + 強い source + title-body 一致 + speculative なし + injury/death なし + 同 game 重複なし)だけを X 候補として選ぶ。
最終的な POST は **当面 user 確認 fixed**(autonomous POST しない)。

## 重要制約(全 phase 共通)

- **X / SNS POST は user 明示 trigger 後にのみ実行**(autonomous POST 禁止、本 ticket lock)
- **WordPress 公開済み記事の中からのみ X 候補化**(未 publish の draft は対象外)
- WP publish lane(PUB-004)とは独立、PUB-004 が publish した記事の中から再選定
- X API 認証情報(`X_API_KEY` 等)は `.env` 経由、表示禁止
- X 投稿後の rate limit / cost に配慮(1 日 X_POST_DAILY_LIMIT 内、CLAUDE.md §18 準拠)

## X-side Red 条件(本 runner で refuse)

WP publish が通っても、X POST 候補化では以下を refuse:

- source 弱い(primary 媒体 1 件未満、Twitter only、社内 source mapping なし)
- title が speculative(「どう見るか」「ポイントはどこ」「予想」「気になる」系)
- title-body 完全一致していない、または body が title 主張を支えていない
- injury / death / 登録抹消 / 診断 / 症状 言及あり
- 同一試合 / 同一選手の X 投稿が直近 24h で既出
- 4/17 事故と同質リスク
- 数値リスト型の記事(NPB 通算安打 ranking 等)
- quote-heavy で出典が不明確

→ 上記いずれかに該当 → X 候補から除外、PUB-005 で hold。

## 不可触

- WordPress publish 機構(PUB-004 lane に任せる)
- `.env` / X API secret 表示
- `RUN_DRAFT_ONLY` flip
- Cloud Run env / scheduler
- automation.toml / Codex Desktop 側
- baseballwordpress repo
- front lane / plugin

---

## 分割(後続実装の見取り図)

### PUB-005-A: x-candidate evaluator(read-only、WP publish 済から選定)

#### scope
- 新規 file: `src/tools/run_x_post_evaluator.py`
- WP REST `status=publish` から直近 N 件 fetch(orderby=date desc)
- 各 post を **PUB-002-A Green 条件 + X-side Red 条件**で評価
- 出力: JSON
  - `x_eligible: [{post_id, title, link, why_eligible}]`
  - `x_refused: [{post_id, title, refuse_reasons}]`
- WP write **なし** / X API call **なし** / LLM call **なし**(pure Python)
- HALLUC-LANE-002 land 後に G3/G7/G8 の re-evaluation 経路を追加

### PUB-005-B: x-post-helper(user 明示 trigger 必須)

#### scope
- 新規 file: `src/tools/run_x_post_helper.py`
- input: PUB-005-A output(x_eligible list)
- user trigger: `x_post: <post_id>` 明示
- 各 candidate に対し:
  1. preflight(post status=publish 確認、X-side Red 条件 再 evaluate)
  2. X 投稿文案生成(既存 `src/x_post_generator.py` 流用)
  3. user に投稿文案を 1 件提示、`approve` / `reject` 1 ワード判断
  4. approve なら X API POST(`src/x_api_client.py` 流用、`X_API_KEY` 等は `.env`)
  5. 投稿後 history 記録(`logs/x_post_history.jsonl`)
- daily cap: `X_POST_DAILY_LIMIT`(既定 env 値、CLAUDE.md §18 準拠)
- autonomous POST **なし**(user trigger + approve fixed)
- dry-run default(`--live` 明示で X API 実 POST)

### PUB-005-C: cron 化(現時点 scope 外)

X 自動投稿は user policy で fixed = 当面 cron 化しない。
将来の判断時に別 ticket。

---

## 連携

- **PUB-004**(WP publish lane): publish 済記事の集合を生成、本 lane の input 候補
- **PUB-002-A**(判定 contract): Green / Yellow / Red の正本、本 lane は X-side Red を追加 strict
- **HALLUC-LANE-002**(LLM 検出): land 後に G3/G7/G8 の完全 verify 経路として統合
- **既存 `src/x_post_generator.py` / `src/x_api_client.py`**: 投稿文案生成 + X API client、本 lane で流用(改変なし、流用のみ)
- CLAUDE.md §18 + AGENTS.md `X_POST_DAILY_LIMIT` 準拠

## 完了条件(本 ticket、doc-first)

1. WP lane と X lane が独立した ticket として明示(PUB-004 / PUB-005)
2. X-side Red 条件が WP publish より strict なことが明文化
3. user 確認 fixed(autonomous POST なし)が明文化
4. 後続実装(PUB-005-A/B)の見取り図が固定
5. 本 ticket は doc-first、実装は X 解放判断後

## stop 条件

- X 自動投稿への autonomous 解放要望 → 本 ticket scope 外、別 ticket(`PUB-005-D-x-autonomous-fire`)
- X API rate limit 超過 → 本 runner で daily cap 内に強制制限
- X 認証情報の表示 / 露出 → 本 ticket 違反、即停止
- WP publish との連携で WP 側を改変したくなる → 本 ticket scope 外、PUB-004 へ移管

## 関連 file

- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(Green / Red 判定 contract)
- `doc/PUB-004-guarded-auto-publish-runner.md`(WP publish lane、本 ticket の input 集合)
- `src/x_post_generator.py`(投稿文案生成、流用)
- `src/x_api_client.py`(X API client、流用)
- AGENTS.md / CLAUDE.md §18(X 投稿運用ルール)
