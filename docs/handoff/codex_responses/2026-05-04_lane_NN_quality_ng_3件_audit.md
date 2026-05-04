# 2026-05-04 Lane NN 64432/64453/64461 quality NG audit

作成: 2026-05-04 JST  
scope: audit + design / read-only evidence consolidation / ticket assignment / handling judgment  
write scope used: `docs/handoff/codex_responses/2026-05-04_lane_NN_quality_ng_3件_audit.md`, `doc/active/assignments.md` only  
live mutation: none  
code change: none

## 0. namespace clarification

- user prompt 上の `262-QA-duplicate-publish-guard` に相当する live duplicate guard ticket は **`263-QA`** (`7667658`)。
- repo 内に standalone の `262-QA-duplicate-publish-guard.md` は無い。
- `262-QA` という表記は `doc/waiting/260-MKT-fan-original-article-types-and-templates.md` では「title-subject-name-required 延長」の歴史参照として残っているため、duplicate guard と混同しないこと。

## 1. consolidated evidence

| post_id | raw source title → rewritten title | live revision / template | validator / unlock path | body/template evidence | Giants relevance pass | root cause summary |
| --- | --- | --- | --- | --- | --- | --- |
| `64432` | `右アキレス腱炎からの復帰を目指す 投手がブルペン投球を実施` → `実施選手、昇格・復帰 関連情報` | `00187-74x` / `player_status_return` | `title_template_selected` only。`title_player_name_review` / `weak_subject_title_review` emitted なし | `social_body_template_applied` + `recovery_body_template_applied` が同居。cleanup backup では `GIANTS PLAYER WATCH` + `【発信内容の要約】` 空崩れ + generic background | Giants exclusive social source (`@sanspo_giants`) + recovery cue で pass | player-name backfill false negative。generic compound `実施選手` を named-subject 扱いし、277/weak-subject path が動かなかった |
| `64453` | `元巨人の上原浩治氏が井上尚弥と中谷潤人にあっぱれ「ラウンド中、息をするのも忘れるくらい」` → raw 近似 truncate | `00187-74x` / `fallback_clean_title` → `00188-469` / `fallback_clean_title` | `00187` では `article_skipped_post_gen_validate` (`fail_axis=["close_marker"]`)。`00188` では `fetcher_fan_important_narrow_exempt` (`reason="post_gen_close_marker_only"`, `keyword_hits=["元巨人"]`) で skip 解除 | subtype-specific body template log なし。cleanup backup では `GIANTS VOICE CHECK` + `【ニュースの整理】` / `【ここに注目】` / `【次の注目】` / `💬 ファンの声（Xより）`。巨人文脈なし | `元巨人` だけで OB / Giants relevance を通過 | relevance gate depth 不足。OB 非野球コメントを Giants article に昇格させ、JJ close-marker exempt が skip を上書き |
| `64461` | `ブルージェイズ・岡本和真が3戦連発の9号2ラン　9回に反撃の一発放つも及ばず、勝率5割復帰お預け` → `岡本和真、昇格・復帰 関連情報` | `00187-74x` / `player_status_return` → `00188-469` / `player_status_return` | `00187` では `article_skipped_post_gen_validate` (`fail_axis=["close_marker"]`)。`00188` では `fetcher_fan_important_narrow_exempt` (`keyword_hits=["復帰"]`) で skip 解除 | `notice_body_template_applied` (`notice_v1`) + `media_xpost_embedded` (`selector_type="npb_notice"`)。cleanup backup では `【対象選手の基本情報】` に `読売ジャイアンツ所属`、一方で lead は Blue Jays/MLB 文脈 | roster hit `岡本和真` + `復帰` cue。`is_giants_related()` は active-team guard を持たず pass | active team contamination。MLB/Blue Jays performance story を Giants return / notice template に誤配線 |

## 2. per-id root cause

### 64432

- title path:
  - `src/rss_fetcher.py:15621-15701` で `title_player_name_unresolved` 判定 → weak-title rescue → weak generated title review → weak subject title review → `title_template_selected` の順で通る。
  - 事故時 log では `title_template_selected` は出ているが、`title_player_name_review` / `weak_subject_title_review` は出ていない。
- direct code implication:
  - `src/title_player_name_backfiller.py:133-147` の `_title_already_has_named_subject()` は最後に `title_has_person_name_candidate(cleaned)` を返す。
  - `src/title_validator.py:373-383` の `title_has_person_name_candidate()` は kanji 連結語でも person-like token と見なす余地があり、`実施選手` のような generic compound を false positive で通しうる。
  - そのため `title_player_name_unresolved` が立たず、277 系 observability が出ない。
- body path:
  - cleanup backup では raw lead に player 名が無いまま `social_v1` / `recovery_v1` が混在し、`【発信内容の要約】` セクションが実質空崩れ。
  - title だけの問題ではなく、recovery 系 section も subject 欠落のまま render されている。
- existing ticket relationship:
  - **277-QA** は該当する。実装 commit は `8e9f5d8`、session sync は `27166c5`。
  - ただし **277 単独では未閉塞**。この case は `実施選手` false positive を残している。
  - **290-QA** (`c14e269`) も pattern 上は直撃する。`related_info_escape` rescue 既存案があり、64432 はまさにその family。
  - ただし live revisions `00187-74x` / `00188-469` の env には `ENABLE_WEAK_TITLE_RESCUE` が無く、290 rescue は incident path に載っていない。

### 64453

- title path:
  - rewritten title 自体は `fallback_clean_title` で raw 近似。title rewrite corruption が主因ではない。
  - `00187-74x` では `close_marker` で stop されていた。
  - `00188-469` で `ENABLE_FETCHER_FAN_IMPORTANT_NARROW_EXEMPT=1` が live になり、`keyword_hits=["元巨人"]` だけで skip 解除された。
- relevance path:
  - `src/rss_fetcher.py:13512-13521` の `is_giants_related()` は keyword / exclusive source / roster hit の 3 本柱。
  - 64453 は `元巨人` を含むため、OB 話題を Giants-related として通しうる。
  - ただし内容は boxing commentary で、野球/巨人の current ops relevance が弱い。
- body path:
  - `GIANTS VOICE CHECK` 系 generic body が入り、`【次の注目】` まで巨人文脈なく延ばしている。
  - つまり classifier 問題が本文 template で増幅された形。
- existing ticket relationship:
  - **250-QA-1** は quote_count=0 padding 抑止であり、off-topic relevance そのものは扱わない。
  - **250-QA-3** は weak generated title review であり、raw 近似 title の 64453 を止める ticket ではない。
  - **248-MKT-2** は same-game linking で scope 外。
  - 既存 ticket に綺麗な受け皿が無く、**new narrow filter ticket が必要**。

### 64461

- title / classifier path:
  - raw source は冒頭から `ブルージェイズ・岡本和真` で MLB 文脈だが、title template は `player_status_return` を選択している。
  - `00187-74x` では `close_marker` で止まり、`00188-469` の JJ exempt で `keyword_hits=["復帰"]` により skip が外れた。
  - `src/rss_fetcher.py:13512-13521` の `is_giants_related()` は roster hit があれば `not _is_other_team_transfer_story(...)` で pass するが、これは transfer-story しか見ていない。active affiliation を見ない。
- body path:
  - `notice_body_template_applied` / `notice_v1` が選ばれ、さらに `media_xpost_embedded` が `selector_type="npb_notice"` として公示ポスト枠に入っている。
  - cleanup backup 内で、lead は Blue Jays/MLB、本文は `読売ジャイアンツ所属` と書いており、title/body/template の全層で entity contamination が起きている。
  - `x_post_ai_generated` preview でも `巨人復帰後` と hallucinate しており、article-only mismatch に留まらない。
- existing ticket relationship:
  - **242-B** (`16304f2`) は「巨人 prefix + 他球団選手」型 detector で、63844 型 hallucination を narrow に止めるもの。64461 は raw source 自体が Blue Jays であり、**current 242-B scope だけでは不足**。
  - **244 / 244-followup** は numeric/severity 系で主因ではない。
  - したがって **new structural ticket が必要**。242 family extension か独立 child にするのが妥当。

## 3. handling judgment (no live execution in this lane)

| post_id | recommended action | judgment | rationale |
| --- | --- | --- | --- |
| `64432` | default `B`, conditional `A` | **B unless manual subject confirmation exists** | current logs / cleanup backup / source title だけでは player 名を安全に復元できない。source article or source post context から主語を確定できる運用者がいるなら narrow title/body repair で `A` 可。それが無い状態での PUT は unsafe |
| `64453` | backlog 化 | **B** | relevance 弱で publish quality NG だが、事実誤認よりは ranking/selection failure。unpublish 境界には乗せない。existing publish 維持 + backlog/ticket 可視化が妥当 |
| `64461` | unpublish 推奨 | **C (user boundary)** | Blue Jays/MLB article を Giants return/article として publish した entity contamination は致命的。user が live mutation を許可するなら draft 戻し優先。即 mutation しない場合でも critical backlog として `B` 扱いで残す |

## 4. ticket assignment and follow-up design

### 4.1 64432

- existing ticket to attach:
  - `277-QA-title-player-name-backfill` (`8e9f5d8`, sync `27166c5`)
  - `290-QA-weak-title-rescue-backfill` (`c14e269`, default OFF)
- recommended ticket update note (not committed):
  - 64432 proves `_title_already_has_named_subject()` / `title_has_person_name_candidate()` still false-positive on generic compounds such as `実施選手`.
  - add incident note that `title_player_name_unresolved` log did not emit on live rev `00187-74x`.
  - add note that 290 rescue is still not in live env because `ENABLE_WEAK_TITLE_RESCUE` was absent on `00187-74x` and `00188-469`.
- draft follow-up ticket (do not commit):
  - provisional title: `277-B-QA generic compound subject false-positive guard`
  - scope:
    - reject generic compounds like `実施選手` / `起用選手` / `登板投手` as named-subject candidates
    - preserve current 277 behavior for real named subjects
    - do not touch publish/mail/runtime outside title backfill predicates

### 4.2 64453

- existing ticket fit:
  - no clean existing fit in `250-QA-*`, `248-MKT-*`, `246-MKT`.
- recommended update note (not committed):
  - mention in quality backlog / ops note that `元巨人` only signal is insufficient for publish when the topic is non-baseball commentary.
- draft new ticket (do not commit):
  - provisional title: `former-giants non-baseball relevance filter`
  - scope:
    - if Giants signal is only `元巨人` / OB marker, require baseball/Giants topical marker in title+summary
    - boxing/TV/general celebrity commentary should route to review/skip
    - do not change current player/manager/news article templates

### 4.3 64461

- existing ticket fit:
  - adjacent: `242-B` (`16304f2`) entity contamination detector
  - insufficient: current 242-B only covers `巨人 prefix + 他球団選手` narrow hallucination
- recommended update note (not committed):
  - record 64461 as a new variant: active non-Giants affiliation present in raw source, but classifier/template rewrote it into Giants return/notice.
- draft new ticket (do not commit):
  - provisional title: `active-team mismatch guard for player_status_return / notice templates`
  - scope:
    - add active-team conflict guard before `player_status_return` / `notice_v1`
    - block or review when source title contains explicit non-Giants team prefix (`ブルージェイズ`, MLB markers) while roster-hit player name belongs to a Giants mapping path
    - maintain small deterministic mapping / marker table; no external roster API

## 5. proposed updates for Claude review only (not committed)

### 277-QA append proposal

- incident evidence: post `64432`
- note:
  - raw source title lacked player name, rewritten title became `実施選手、昇格・復帰 関連情報`
  - live rev `00187-74x` emitted `title_template_selected` but did **not** emit `title_player_name_review`
  - likely cause is `title_has_person_name_candidate()` false-positive on generic compound `実施選手`
  - acceptance needs one more predicate hardening or explicit `GENERIC_COMPOUND_NO_NAME` block

### 290-QA append proposal

- incident evidence: post `64432`
- note:
  - 64432 is an exact `related_info_escape` family example
  - live rev `00187-74x` / `00188-469` lacked `ENABLE_WEAK_TITLE_RESCUE`, so 290 rescue was not active during this incident
  - if 290 is adopted, this case should be part of canary/live verification set

### 242-family append proposal

- incident evidence: post `64461`
- note:
  - current 242-B scope stops `巨人 + 他球団選手` hallucination
  - 64461 is broader: raw source already states Blue Jays, but title/body/template path still reclassifies to Giants return/notice
  - new child ticket should live under 242 family or equivalent entity mismatch series

## 6. final judgment

- `64432`: quality NG confirmed. existing 277 applies, but closure requires either 290 enablement or a narrow 277 predicate hardening. live handling recommendation is `B`, with `A` only after manual subject confirmation.
- `64453`: quality NG confirmed. root cause is relevance selection, not title corruption. keep published, backlog as `B`, and add a new OB/non-baseball relevance filter ticket.
- `64461`: quality NG confirmed. this is a structural active-team contamination incident. recommend `C` (unpublish) at user boundary; if no immediate live mutation, keep as critical backlog with a new entity/team mismatch ticket.

## 7. commit scope for this lane

- commit allowed:
  - `docs/handoff/codex_responses/2026-05-04_lane_NN_quality_ng_3件_audit.md`
  - `doc/active/assignments.md`
- do not commit in this lane:
  - ticket body edits for `277-QA`, `290-QA`, `242-*`
  - new ticket drafts
  - any `src/*`
