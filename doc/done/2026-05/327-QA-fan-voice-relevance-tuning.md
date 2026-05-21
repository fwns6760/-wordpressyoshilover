# 327-QA fan voice relevance tuning(subject context + handle cap + h3 dedup)

## meta

- number: 327-QA
- type: fan voice picker relevance / handle diversity / HTML postprocess dedup
- status: CLOSED LIVE_DEPLOYED_VERIFIED (commit `8d7fdd3` (subject context + handle cap + h3 dedup) + `bf8ca53` (Yahoo realtime fallback) 両方 fetcher 現 image `title-cap-warn-07d24d2` に landed、 env `ENABLE_FAN_REACTION_SUBJECT_CONTEXT_REQUIRED=1` + `ENABLE_FAN_REACTION_HANDLE_CAP=1` 確認、 h3 dedup は default ON、 全 3 fix が production で active)
- priority: P1
- owner: Claude
- created: 2026-05-13
- doc_path: `doc/active/327-QA-fan-voice-relevance-tuning.md`

## 1. 背景(2026-05-13 audit)

prod 直近 19 件 audit で 2 つの劣化 pattern を観測。

### A. 同一ハンドル独占

post 66788(井上温大 25 歳誕生日)で `@noraneko0122` が **6 件中 4 件**を占有。1 記事の `💬 ファンの声` block が 1 ユーザに偏る。

### B. 重複 `💬 ファンの声` h3 + filler

post 66752 / 66788 で `<h3>💬 ファンの声</h3>` が 2 回出る:

1. AI 生成 `【投稿で出ていた内容】` → h3_normalizer が `💬 ファンの声` に変換 + filler「整理します」段落のみ
2. rss_fetcher が後段で `<h3>💬 ファンの声（Xより）</h3>` + 実 X embed を出力

→ 1 つ目は中身ゼロ filler、2 つ目に X embed という不可解な見栄え。

### C. user 報告: 「巨人ファンでない関係のないファンの声が多い」

記事 subject(選手名 / 話題)に触れない汎用 巨人 post が混入する。現在の `_reaction_focus_score >= 2` primary 判定では、`_reaction_can_fill_shortage` 経由で subject 不在の reserve も拾われている。

## 2. fix(landed in this commit)

### fix 1: subject context 必須 (default OFF / opt-in)

`src/rss_fetcher.py:fetch_fan_reactions_from_yahoo` の candidate filter loop に、`_reaction_has_subject_context(text, title, summary, category)` が True でないなら drop する gate を追加。

- env flag: `ENABLE_FAN_REACTION_SUBJECT_CONTEXT_REQUIRED`(default `0`)
- helper: `_fan_reaction_subject_context_required_enabled()`(`src/rss_fetcher.py:2321`)
- 既存テスト fixture が generic-keyword mock なので default ON にすると 8 件 fail、default OFF で互換性維持
- prod env で `=1` 設定して活性化

### fix 2: 同一 handle cap (default OFF / opt-in)

`src/rss_fetcher.py:fetch_fan_reactions_from_yahoo` の selection loop に、1 記事内で同一 handle が cap(既定 2)を超えたら skip する logic を追加。

- env flag: `ENABLE_FAN_REACTION_HANDLE_CAP`(default `0`)
- 数値 env: `FAN_REACTION_HANDLE_CAP`(default `2`)
- helper: `_fan_reaction_handle_cap_enabled()` / `_fan_reaction_handle_cap()`
- prod env で `=1` 設定して活性化、cap は既定 2 のまま

### fix 3: h3 dedup post-pass (default ON)

`src/h3_normalizer.py` に `_dedupe_fan_voice_h3()` を追加、`normalize_h3_in_html` 末尾で呼ぶ。

- env flag: `ENABLE_FAN_VOICE_H3_DEDUP`(default `1` = ON)
- 同一 label `💬 ファンの声` の h3 を 1 つに集約。残すのは:
  1. `twitter-tweet` を含む section が最優先
  2. それ以外は body_len 最大
  3. 同点なら最後の section
- 削除側は h3 と本文を section ごと丸ごと除去
- idempotent

## 3. 触らない範囲

- publish / mail / scheduler / Cloud Run config / Secret / X API / SEO
- `_reaction_focus_score` 本体 / `_reaction_matches_precise_source_context` / `_build_fan_reaction_focus_terms`
- 309-QA / 310-QA / 311-QA で landed 済 subtype 別 cap / strict match
- 324-QA / 325-QA / 326-QA(別 scope)
- `nomotoke_card_renderer.py` の `_x_embed_block`(別経路)
- `media_xpost_selector.py`(報道 X 引用、別 lane)

## 4. test

- 既存: `tests/test_h3_normalizer.py` / `tests/test_yahoo_realtime.py` baseline 68 passed → 76 passed(+8 new)
- 新規: `FanReactionRelevanceTuningTests`(3 件、subject context required / handle cap / defaults off)
- 新規: `TestFanVoiceH3Dedup`(5 件、dedup keep twitter / single h3 unchanged / idempotent / longer body / flag off keeps both)
- full pytest baseline: 3831 passed / 1 pre-existing fail(`test_game_live_primary_sources_are_hochi_only`、本 ticket 起因 0)

## 5. env flip plan(post-deploy)

deploy 完了後、Cloud Run `yoshilover-fetcher` service env に追加:

```
ENABLE_FAN_REACTION_SUBJECT_CONTEXT_REQUIRED=1
ENABLE_FAN_REACTION_HANDLE_CAP=1
```

h3 dedup は default ON のため env 不要。

## 6. verify(post env flip)

- 次回 `/run`(30 分ごと cron)で `yahoo_fan_reactions_*` log を観察
- 直近 5 件の publish で:
  - `💬 ファンの声` h3 が 1 つだけ
  - X embed 数(空 filler section 除去後)
  - 同一 handle ≤ 2 件
- regression: publish 数 / エラー 数 / 投稿失敗が増えないこと

## 7. 326-QA-fallback 追加(同 commit、2026-05-13)

### 背景

audit で 19 件中 **10 件(53%)が rich-source path で fan voice ゼロ**を発見。これらは `body_too_thin` で nomotoke renderer が拒否 →
`_render_nomotoke_intake_fallback_shell` が `nomotoke-card-divider/footer` で wrap → `apply_rss_pipeline_enrichment` の marker gate (`'class="nomotoke-card-'`) は通過するが、`_build_x_embeds_block_safe`(cached pool)が空を返すため fan voice block が追加されない。

### fix(default ON)

`src/tools/manual_intake.py` に `_build_fan_voice_yahoo_fallback_block()` + `_fan_voice_yahoo_fallback_enabled()` を追加。`apply_rss_pipeline_enrichment` の X embeds block 出力箇所で、cached pool が空時 Yahoo realtime fan reactions(`fetch_fan_reactions_from_yahoo` lazy import)を fallback として fetch + render。

- env flag: `ENABLE_FAN_VOICE_YAHOO_FALLBACK`(default `1` = ON)
- fetch 失敗 / 0 件 / 全 URL 空 → 何も追加しない(regression 0)
- 既存 X embeds(`📲 関連 X 投稿` aside)経路は不変、空時のみ補完
- render format は `rss_fetcher.py:17453` と整合(`<h3>💬 ファンの声（Xより）</h3>` + `yoshilover-x-embed-compact`)
- h3 dedup pass で fix 3 と整合

### test

- `tests/test_manual_intake.py::FanVoiceYahooFallbackTests`(7 件、helper unit + 5 integration scenarios)
- 新 baseline: 76 + 7 = 83 touched-module tests pass

### baseline regression(再評価)

- src 変更前 baseline: 3864 passed / 1 fail(`test_game_live_primary_sources_are_hochi_only`)
- src + tests 変更後: 3869 passed / 1-3 fail(`test_event_key_ledger.py` 内 2 件が flaky、test 順序依存、test_event_key_ledger 単独 33 pass)
- `test_event_key_ledger.py` は 2026-05-13 09:56 JST 追加(commit `c86b21f`、別 work)、本 ticket と無関係
- src behavior 起因の regression は 0
