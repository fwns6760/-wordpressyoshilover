---
ticket: 234-impl-2
title: 234 contract 反映(`postgame` / `lineup` 一軍記事の mail / X 候補 contract narrow 実装)
status: CLOSED
owner: Claude (起票) / Codex A (実装)
priority: P1
lane: A
ready_for: codex_a_fire
created: 2026-04-28
related: 234 (parent contract REVIEW_NEEDED), 234-impl-1 (farm_result / farm_lineup CLOSED), 244 (X numeric suppress CLOSED), 225 (X candidate quality), 231 (review label / mail UX)
---

## 背景

234 contract (REVIEW_NEEDED) は 6 subtype × 5 軸の contract を定義済。
234-impl-1 (`75d9407`) で farm_result / farm_lineup の mail UX contract を narrow 反映済。
234-impl-2 は **既存 `postgame` / `lineup` subtype の中で「一軍記事」(farm / 二軍 / 三軍 marker が無い)** に対して template contract を narrow 反映する。

**B 解釈確定 (2026-04-28 user 明示)**:
- 新規 subtype 文字列追加 (`first_team_postgame` / `first_team_lineup`) は **しない**
- classify_category / subtype 識別 logic は touch しない
- 既存 subtype `postgame` / `lineup` を reuse、本文 / title / metadata の二軍・ファーム marker で「一軍」判定する narrow helper のみ追加

## ゴール

**narrow**: `postgame` / `lineup` subtype のうち farm / 二軍 / 三軍 marker が **無い** もの = 一軍記事に対して、`_manual_x_article_type` と mail UX 側で contract 反映。

具体:
- src/publish_notice_email_sender.py に
  - 一軍判定 helper (`_is_first_team_article(title, summary, subtype)` 等、最小)
  - `_manual_x_article_type` 内の `postgame` / `lineup` branch で **一軍 only の templates path** を narrow 追加
  - mail UX 側で一軍 postgame の score/key event 不足や、一軍 lineup の past_date / lineup 欠落に対する review 倒し narrow 追加
- 既存 `farm_result` / `farm_lineup` (234-impl-1) と 244 numeric suppress branch と完全独立、disjoint
- tests fixture 4 件 (一軍 postgame clean / dirty、一軍 lineup clean / past_date)
- 既存 fixture (postgame / lineup / farm_result / farm_lineup / notice / program / default) 全件 pass 維持

## scope (narrow)

### 1. src/publish_notice_email_sender.py (narrow 追加、既存 logic 不変)

#### 1-A. 一軍判定 helper

- `_is_first_team_article(title: str, summary: str, subtype: str) -> bool`
  - subtype が `postgame` または `lineup` の **exact match** 限定(farm_result / farm_lineup / pregame 等は対象外、最小 scope)
  - title / summary に **二軍 marker** が **無い** ことを確認:
    - markers = `("二軍", "三軍", "ファーム", "イースタン", "ウエスタン", "farm", "Farm", "FARM")`
  - markers が title または summary に **1 つでも hit** → return False (二軍記事として除外)
  - markers が **無い** + subtype が `postgame` or `lineup` → return True (一軍記事)
  - その他 (subtype が違う) → return False
- 外部 roster / API は参照しない、文字列マッチのみ

#### 1-B. `_manual_x_article_type` (line 648-) に一軍 branch narrow 追加

- 既存 `if normalized_subtype == "lineup":` (line 702) と `elif normalized_subtype == "postgame":` (line 704) は既存 templates をそのまま使う
- ただし `_is_first_team_article(title, summary, subtype)` が True の場合、234 contract 通り一軍 templates を保証:
  - 一軍 postgame: `["article_intro", "postgame_turning_point", "inside_voice", "fan_reaction_hook"]` (現状 line 704 と同じ → 変更不要なら touch しない)
  - 一軍 lineup: `["article_intro", "lineup_focus", "inside_voice", "fan_reaction_hook"]` (現状 line 702 と同じ → 変更不要なら touch しない)
- **既存 templates が contract と一致するなら、本 ticket では _manual_x_article_type は touch せず、mail UX 側 review 倒しのみ実装**
- Codex A が inspect して、既存 templates が 234 contract 通りなら branch 追加は最小化

#### 1-C. mail UX 側 (`_resolve_mail_state` 周辺) review 倒し narrow

- 一軍 postgame で **score / key event 不足** の場合 → `mail_class="review"` + reason `first_team_postgame_review` + prefix `【要確認】`
- 一軍 lineup で **past_date stale** または **lineup 欠落** の場合 → `mail_class="review"` + `x_post_ready=false` + reason `first_team_lineup_review`
- score / key event / lineup 検出は本文 / summary の regex 軽量 marker のみ(244 module 流用は非対象、本 ticket は一軍 specific の最小判定)
  - score marker: `\d+[-対]\d+`
  - key event marker: `決勝打` / `本塁打` / `先制` / `逆転` 等
  - lineup marker: `1番` / `2番` / `先発` / `スタメン`
- 既存 mail_class 判定 logic (`_MAIL_CLASS_CONFIGS` / `_resolve_mail_state` の broad path) は **touch しない**、一軍判定 hit 時の override branch のみ

### 2. tests (narrow):

`tests/test_publish_notice_email_sender.py` に 4 fixture 追加 (既存 fixture 不変):
- fixture 1: subtype=`postgame`, 一軍 (title に "二軍" 無し), clean (score + key event あり) → mail_class="x_candidate"、X templates に `fan_reaction_hook` 含む
- fixture 2: subtype=`postgame`, 一軍, score 不足 → mail_class="review"、prefix "【要確認】"、reason "first_team_postgame_review"
- fixture 3: subtype=`lineup`, 一軍, clean (今日 + lineup) → mail_class="x_candidate"、X templates `lineup_focus` 含む
- fixture 4: subtype=`lineup`, 一軍, past_date / lineup 欠落 → mail_class="review"、x_post_ready=false、reason "first_team_lineup_review"

regression fixture 1 件追加(必須):
- fixture 5: subtype=`postgame`, **二軍** (title に "二軍") → 一軍判定 False → 既存 path 通過、判定 不変(本 ticket で何も変えない)

### 3. write_scope (明示 stage、git add -A 厳禁):
- src/publish_notice_email_sender.py
- tests/test_publish_notice_email_sender.py

## 不可触 (絶対に触らない)

- 234 contract doc
- 既存 farm_result / farm_lineup branch (234-impl-1、`75d9407`)
- 244 X numeric suppress branch (244、`f2cc8a3`)
- src/guarded_publish_evaluator.py (244 / 242 系)
- src/baseball_numeric_fact_consistency.py (244)
- src/article_entity_team_mismatch.py (242-B)
- src/tools/draft_body_editor.py (244-B)
- src/llm_cost_emitter.py / src/rss_fetcher.py / src/tools/run_draft_body_editor_lane.py (243)
- classify_category / subtype 識別 logic
- Gemini / LLM call 追加
- prompt 改修
- Web / 外部 API
- env / Secret / Scheduler / Cloud Run / RUN_DRAFT_ONLY
- WP REST / publish / draft patch
- automation.toml / cron
- H3 required 化 / template structure 強制
- 234 contract 全 6 subtype 一括反映(本 ticket は postgame / lineup 一軍のみ)
- ambient dirty (logs/ / build/ / .codex / data/) 巻き込み
- doc/active/assignments.md / doc/README.md 編集

## デグレ防止 contract

- 既存 fixture 全件 pass 維持(全 test file の既存 fixture 1 件も変更しない、追加のみ)
- 二軍 / farm marker hit fixture (regression 5) で「本 ticket で挙動が変わらない」ことを担保
- 既存 farm_result / farm_lineup / 244 X suppress / 234-impl-1 path は出力 diff 0
- false positive(良 一軍記事を review 倒し)1 件でも疑いがあれば実装止めて Claude に report
- score / lineup marker は **本文 / summary の単純 regex のみ**、Gemini 呼び出し禁止
- 一軍判定 helper は **subtype exact match + 二軍 marker 否定** の最小 logic、helper 内で外部依存禁止

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 2 file のみ stage、git add -A 禁止、明示 path
2. **挙動**: 新規 5 fixture 全 pass、既存 fixture fail 0、pytest baseline 維持
3. **境界**: classify_category / subtype 識別 logic / 既存 mail UX path / Gemini / Cloud Run / Scheduler / Secret / WP すべて不変、一軍判定 hit 時のみ review 倒し / templates 強化 narrow

## commit 規約

- git add -A 禁止、明示 path のみ stage
- commit message: `234-impl-2: postgame/lineup first-team mail UX contract narrow + fixtures`
- push は Claude が後から実行
- `.git/index.lock` 拒否時は plumbing 3 段 fallback

## 完了後の Claude 判断事項

- pytest baseline 確認 + commit accept
- git push (Claude 実行)
- live 反映 (publish-notice rebuild) は user 明示 GO 済(本 ticket scope 内、tests pass 後 deploy/smoke 自律実行)
- canary 00185-zay 監視と並走、conflict なし

## non-goals

- 6 subtype 一括反映
- H3 required 化 / template body structure 強制
- subtype 文字列追加 (`first_team_postgame` / `first_team_lineup`)
- classify_category 触る
- Gemini に「一軍判定」を投げる
- prompt 改修
- evaluator / publish gate logic 修正
- WP draft 触る
- 234 contract doc 編集
- README / assignments 編集(別 commit)
