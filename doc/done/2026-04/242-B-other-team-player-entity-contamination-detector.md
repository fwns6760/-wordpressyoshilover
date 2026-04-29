---
ticket: 242-B
title: 他球団所属選手の entity contamination detector(63844 型 hallucination 抑止)
status: CLOSED
owner: Claude (起票) / Codex A (実装)
priority: P1
lane: A
ready_for: codex_a_fire
created: 2026-04-28
related: 242 (parent incident), 224 (article-body entity-role consistency CLOSED), 113-A (HALLUC candidate router)
---

## 背景

242 incident で 63844 が「巨人記事本文に **則本昂大(楽天投手)** を巨人選手として混入」状態で publish された。
relevance gate / fact gate は通っているが、これは LLM hallucination の entity-level 失敗(実在する選手を、所属の違うチーム文脈で混入)。

既存の 224 (`src/article_entity_role_consistency.py`) は「awkward role phrasing 文体崩れ」の rewrite 専門で、**team-prefix hallucination 検出は scope 外**。
242-B はこの穴を narrow に塞ぐ:「巨人:<実在他球団選手名>」形式の hallucination を **publish 前に detect → review/draft hold**。

## ゴール

**narrow**: 63844 の正確な変種(「<巨人 prefix>:<他球団所属の実在選手名>」)のみ検出。

具体:
- detector を追加(rule-based、Gemini 呼び出しなし、外部 API なし)
- 既知の **他球団主力選手 minimal seed roster**(5-10 名、fixture)で照合
- detect された場合、guarded_publish_evaluator から Yellow/hold(review/draft 倒し)へ
- 既存の publish 通過 logic は **絶対に広げない**(false negative は OK、false positive を出さない設計)

## scope (narrow)

### 1. 新規 file: `src/article_entity_team_mismatch.py`

- function: `detect_other_team_player_in_giants_article(title: str, body_text: str) -> list[dict]`
- 戻り: detect された (team_prefix, player_name, owning_team, position, span) のリスト
- pattern: `(?P<team>巨人|読売|ジャイアンツ)[\s:：]+(?P<name>[実在他球団選手名])` の正規表現
- seed roster (5-10 名、固定):
  - 則本昂大 → 楽天
  - 山本由伸 → ドジャース(2026 時点、元オリックス)
  - 佐々木朗希 → ドジャース(2026 時点、元ロッテ)
  - 村上宗隆 → ヤクルト
  - 岡本和真 → 巨人(陽性 control)…**いや巨人選手は seed に入れない**(false positive 源)
  - 近藤健介 → ソフトバンク
  - 柳田悠岐 → ソフトバンク
  - 山川穂高 → ソフトバンク(2026)
- seed は **module 内の constant dict** として持つ(YAML / JSON 外部依存なし)
- false positive 防御:
  - 「対戦相手」「vs」「との対戦」「打席」「対 <team>」等の文脈マーカーが近接(±50 char)していたら **suppress**(楽天との試合言及で則本登板の正当な記述を巨人選手として hold しない)
  - title が「対 <team>」/「<team> 戦」を含む場合は detect しない(対戦相手記事は scope 外)

### 2. `src/guarded_publish_evaluator.py` 統合(narrow):

- `_other_team_player_contamination_flag(title, body_text) -> bool` 追加
- 既存の medical_roster / placeholder_body / death_or_grave 同様に **flag 1 つ追加**
- 反映先: `judgment` を Yellow に倒し、reasons に `other_team_player_contamination` を追加
- **既存の Yellow → publish 経路は変えない**(238 night-draft-only で publish 抑止される設計と整合、live は draft 戻し)
- **publish gate を広く緩めない / 既存 Green → Yellow への降格はしない**(detector hit 限定)

### 3. tests:

- 新規 `tests/test_article_entity_team_mismatch.py`(8 fixture):
  - 真陽性: 「巨人:則本昂大が登板」(63844 type)
  - 真陽性: 「巨人:山本由伸」「ジャイアンツ:佐々木朗希」
  - 真陰性: 「巨人:岡本和真」(seed に岡本は入れない、未知名は detect しない)
  - 真陰性: 「巨人 vs 楽天 則本昂大が先発」(対戦相手言及 → suppress)
  - 真陰性: 「楽天・則本昂大が巨人を抑え」(team prefix が巨人でない → detect しない)
  - 真陰性: title「対楽天戦展望」+ 本文「則本」(title マーカー → suppress)
  - 真陰性: 「則本氏」(team prefix なし、単独言及 → detect しない)
  - 真陰性: 巨人選手のみの本文(roster 該当なし → 0 件)

- 既存 `tests/test_guarded_publish_evaluator.py` に 2 fixture 追加:
  - 63844 fixture: detector hit → judgment=yellow + reasons に `other_team_player_contamination`
  - 通常 postgame fixture: detector miss → 既存判定 (green/yellow) 不変

### 4. write_scope (明示 stage、git add -A 厳禁):

- `src/article_entity_team_mismatch.py`(新規)
- `src/guarded_publish_evaluator.py`(flag 1 つ追加、既存 logic 不変)
- `tests/test_article_entity_team_mismatch.py`(新規)
- `tests/test_guarded_publish_evaluator.py`(2 fixture 追加)

## 不可触 (絶対に触らない)

- `src/article_entity_role_consistency.py` (224 既 land、touch 不要)
- 既存 evaluator の medical_roster / placeholder_body / death_or_grave / family_context logic
- 235 / 236-A / 232 / 229-* の cost lane logic
- Gemini call 追加 / 削除 / prompt 改修
- Web 検索 / browser / 外部 API / external roster fetch
- WP REST / WP publish / draft 変更
- env / Secret / Scheduler / Cloud Run / RUN_DRAFT_ONLY
- automation.toml / cron
- publish gate を広く緩める / 既存 Green → Yellow への降格(detector hit 限定のみ)
- prompt 全体改修 / Gemini 入力変更
- 247/248 等 H3 required 化系の logic touch

## デグレ防止 contract

- 既存 fixture(test_guarded_publish_evaluator.py 全件)が 100% pass を維持
- detector を OFF にした場合、既存の judgment = 完全一致 (regression test 含意)
- false positive 1 件でも疑いがあれば実装止めて review/draft 側に倒す(user 明示)
- seed roster は 8 名以下に絞る(過剰 hold 防止)
- 「対戦相手言及 suppress」を必ず実装(対戦カード記事の broad hold を回避)

## acceptance (3 点 contract)

1. **着地**: 1 commit に上記 4 file のみ stage、git add -A 禁止
2. **挙動**: 新規 8 fixture 全 pass、既存 evaluator test fail 0、pytest baseline 維持
3. **境界**: 評価 logic / publish gate / Gemini call / Cloud Run / Scheduler / Secret / WP すべて不変、detector hit 時のみ Yellow 1 段加算

## commit 規約

- git add -A 禁止、明示 path のみ stage
- commit message: `242-B: other-team player entity contamination detector (63844 type narrow fix) + fixtures`
- push は Claude が後から実行
- `.git/index.lock` 拒否時は plumbing 3 段 fallback

## 完了後の Claude 判断事項

- pytest baseline 確認 + commit accept
- git push (Claude 実行)
- 63844 の draft 戻し / unpublish 判断は user 専決(本 ticket 範囲外)
- live 反映 (guarded-publish image rebuild) は別判断、234-impl-1 着地後に bundle するか単独か検討

## non-goals

- 全選手の roster API 連携(scope 大幅拡大)
- Gemini に「他球団選手判定」を追加投げ(Gemini call 増加禁止)
- title-body mismatch 全般の検出(別 ticket)
- prompt 改修で hallucination 自体を抑える(別 ticket、本 ticket は publish 直前 gate)
- 既存 224 の rewrite logic 修正(unrelated)
- 226 / 242-A の判定 logic 修正(unrelated)
