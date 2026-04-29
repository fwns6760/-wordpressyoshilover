---
ticket: 234-impl-1
title: 234 contract 反映(farm_result / farm_lineup の mail / X 候補 contract narrow 実装)
status: CLOSED
owner: Claude (起票) / Codex A (実装)
priority: P1
lane: A
ready_for: codex_a_fire (242-B 着地後)
created: 2026-04-28
related: 234 (parent contract REVIEW_NEEDED), 242-A (farm/farm_lineup escalate suppression CLOSED), 242-D2 (farm_result classifier CLOSED), 225 (X candidate quality), 231 (review label / mail UX)
---

## 背景

234 contract doc (REVIEW_NEEDED) は 6 subtype × 5 軸の contract を定義済(`doc/reference/234-article-subtype-template-contract.md`)。
parent doc は path 1 (publish_notice_email_sender 反映) を 234-impl-1 として推奨。

ただし user 指示で **farm_result / farm_lineup の 2 subtype のみ** に narrow 化する:
- 6 subtype 一括は scope 大、デグレ risk
- farm_result / farm_lineup は 242-A / 242-D2 で classifier / evaluator は narrow 整備済、mail UX 側だけ未反映
- 既存 lineup / postgame / farm / notice / program / default の mail logic は **絶対に変えない**

234 contract doc 上は farm subtype の subset として farm_result / farm_lineup を扱う設計だが、
src 上は既に独立 subtype 文字列として存在(evaluator の `PLACEHOLDER_BODY_TARGET_SUBTYPES = {"farm", "farm_result"}` 等で参照済)。
本 ticket では **farm_result / farm_lineup の subtype 別 mail UX path** を `_manual_x_article_type` 周辺と `_resolve_mail_state` 周辺に narrow 追加。

## ゴール

**narrow**: farm_result / farm_lineup 2 subtype のみ mail / X 候補 contract 反映。

具体:
- `src/publish_notice_email_sender.py` の `_manual_x_article_type` に farm_result / farm_lineup の専用 templates を追加
- mail summary / x_post_ready の subtype 別判定で farm_result / farm_lineup の慎重 default を強制
- 既存 farm / lineup / postgame / notice / program / default の mail path は **完全不変**
- tests fixture で 4 subtype combination(farm_result clean / farm_result dirty / farm_lineup clean / farm_lineup dirty)を担保
- H3 required 化に逃げない、Gemini 呼び出し追加なし、prompt 改修なし

## scope (narrow)

### 1. `src/publish_notice_email_sender.py` (narrow 追加、既存 logic 不変):

#### 1-A. `_manual_x_article_type` (line 648-) に farm_result / farm_lineup branch 追加:

- `farm_result` の templates: `["article_intro", "farm_watch", "inside_voice"]`
  - `fan_reaction_hook` は **絶対に含めない**(234 contract: farm 系は fan hook より numeric / watch point 優先)
  - `inside_voice` は「一軍への示唆を source 事実 1 文で言える時のみ」だが、本 ticket ではテンプレ列挙のみ。実際の出力可否は既存 dirty 判定に従う

- `farm_lineup` の templates: `["article_intro", "farm_watch"]`
  - `inside_voice` も `fan_reaction_hook` も **含めない**(234 contract notice / lineup の保守側に近い扱い)
  - スタメン名前主体、2 候補のみ

- 既存 normalized_subtype 判定の **末尾 elif として追加**(既存 lineup/postgame/farm/notice/program 判定の後)
- 既存 farm 判定(line 706: `templates = ["article_intro", "farm_watch", "inside_voice", "why_it_matters"]`)は **触らない**

#### 1-B. mail UX 側 `_resolve_mail_state` 周辺の subtype 別 default(narrow):

- farm_result: subtype 信頼度低 / dirty / past_date のとき `mail_class="review"` + prefix `【要確認】` を強制(234 contract 通り)
- farm_lineup: 同上、加えて「past_date stale」検出時は `x_post_ready=false` 強制(stale lineup の誤発火防止)
- 既存の mail_class 判定 logic(_MAIL_CLASS_CONFIGS / `_resolve_mail_state` 等)は **追加 branch のみ**、既存 path 完全不変

### 2. tests (narrow):

#### 2-A. `tests/test_publish_notice_email_sender.py` (or 該当 test file、grep で確定) に新規 4 fixture 追加:

- fixture 1: subtype=`farm_result`, clean (数字あり/source あり/notable player あり) → templates に `farm_watch` + `inside_voice` 含む、`fan_reaction_hook` 含まれない
- fixture 2: subtype=`farm_result`, dirty (numeric weak) → mail_class=review、prefix `【要確認】`、X 候補 `article_intro` のみ
- fixture 3: subtype=`farm_lineup`, clean (today + lineup あり) → templates `["article_intro", "farm_watch"]`、`inside_voice`/`fan_reaction_hook` 含まれない
- fixture 4: subtype=`farm_lineup`, past_date / stale → x_post_ready=false 強制、mail_class=review

#### 2-B. 既存 fixture の regression 担保:

- 既存 `subtype=farm` (素 farm) fixture が変更なく pass することを確認(本 ticket は farm 触らない)
- 既存 `subtype=lineup` / `postgame` fixture も完全 pass 維持

### 3. write_scope (明示 stage、git add -A 厳禁):

- src/publish_notice_email_sender.py (narrow 追加、既存 logic 不変)
- tests/test_publish_notice_email_sender.py (4 fixture 追加、既存 fixture 不変)

(test file 名は grep で確認、別名であれば該当 file に追加)

## 不可触 (絶対に触らない)

- 234 contract doc (`doc/reference/234-article-subtype-template-contract.md`) — 別 commit
- 既存 lineup / postgame / farm / notice / program / default の mail / X 候補 logic
- `src/guarded_publish_evaluator.py` (242-A/D/D2/E live、評価 logic 不変)
- `src/rss_fetcher.py` prompt template / Gemini 入力(229-C scope)
- `src/draft_body_editor.py` 本体
- `src/article_entity_team_mismatch.py` (242-B、本 ticket と独立)
- `src/llm_cost_emitter.py` / 243 で追加した emit observability
- 235 / 236-A / 232 / 229-* の cost lane logic
- Gemini call 追加 / 削除 / prompt 改修
- Web 検索 / browser / 外部 API
- WP REST / WP publish / draft 変更
- env / Secret / Scheduler / Cloud Run / RUN_DRAFT_ONLY
- automation.toml / cron
- publish gate を広く緩める / 既存 Green → Yellow への降格(本 ticket は mail UX のみ、publish 判定 unchanged)
- H3 required 化 / template structure 強制
- 6 subtype 一括反映(本 ticket は farm_result / farm_lineup のみ)

## デグレ防止 contract

- 既存 fixture 全件 pass を維持(既存 fixture は 1 件も変更しない)
- 既存 farm / lineup / postgame / notice / program / default の mail 出力は完全に同じ(diff 0)を担保
- false positive(誤 review 倒し)1 件でも疑いがあれば実装止めて Claude に report
- farm_result / farm_lineup の判定は subtype 文字列 exact match のみ(部分 match で farm まで巻き込まない)

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 2 file のみ stage、git add -A 禁止、明示 path
2. **挙動**: 新規 4 fixture 全 pass、既存 fixture fail 0、pytest baseline 維持
3. **境界**: 評価 logic / publish gate / Gemini call / Cloud Run / Scheduler / Secret / WP / 既存 mail UX path すべて不変

## commit 規約

- git add -A 禁止、明示 path のみ stage
- commit message: `234-impl-1: farm_result / farm_lineup mail UX contract narrow + fixtures`
- push は Claude が後から実行
- `.git/index.lock` 拒否時は plumbing 3 段 fallback

## 完了後の Claude 判断事項

- pytest baseline 確認 + commit accept
- git push (Claude 実行)
- live 反映 (publish-notice image rebuild) は別判断、243 / 242-B との bundle rebuild を検討
- 234 contract doc 側に「farm_result / farm_lineup row」を追加するか別 commit で判断

## non-goals

- 6 subtype 一括反映(scope 大幅拡大)
- H3 required 化 / template body structure 強制
- Gemini に「subtype 別 prompt」を追加投げ(Gemini call 増加禁止)
- prompt 改修(229-C scope)
- evaluator / publish gate logic 修正(242 系 scope)
- 234 contract doc 編集(別 commit)
- README / assignments 編集(別 commit)
