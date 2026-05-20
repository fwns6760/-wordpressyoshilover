# 335-QA single-article title quality extension

## meta

- ticket: 335-QA-single-article-title-quality-extension
- owner: Claude Code
- status: PARTIAL_LANDED (2026-05-20 PM verify): `src/title_template_assembler.py` 内に 335-QA Phase 1 / Phase 2 / Phase 3 コメント付き code landed (literal quote / 反応 pattern / fact 重複圧縮)。 `src/title_validator.py` に `generic_noun_only_no_person_name` rejection rule landed。 `src/rss_fetcher.py` L11726 で `weak_reason = "generic_noun_only_no_person_name"` 経路に wire 済。 ただし production log で 今日の fire に該当 rejection token 観察なし (今日の content がそのパス trigger していない可能性、 user acceptance pending)
- priority: P1(本文品質改善、CLAUDE.md §9 title assembly 修正優先順位最上位)
- created: 2026-05-14
- numbering reserved in: README で追加予定
- related memory: `feedback_title_clickable_descriptive` / `feedback_title_no_ai` / `project_multi_source_digest_subtype`
- related closed: 250-QA-3 / 277-QA / 290-QA / 334-QA Phase 1-3b(digest 専用 title path、本 ticket は単記事 path)

## user intent(2026-05-14 chat、67169 / 67146 事例から導出)

post 67169(`「一生忘れない」巨人・坂本が逆転サヨナラ３ラン！通算３００号のメモリアル弾で２試合連続のサヨナラ勝…`)と post 67146(`岡本和真「エンターテイナー」`)が「クリックしようと思わない」title で、user から「今後ね」「恒久対応」指示。

**3 禁則 pattern**:
1. **短すぎ引用**: 6-8 字 quote(「一生忘れない」「エンターテイナー」)だけで文脈伝わらない
2. **event token 詰め込み**: 同じ事実の言い換えを 3 重(逆転サヨナラ / 300号メモリアル弾 / ２試合連続サヨナラ勝)
3. **末尾 `…` truncation**: 「結局?」感、クリック前から不完全な印象

## scope

`src/title_template_assembler.py` の単記事 pattern(A / B / F / G / O / N / M)を 3 禁則を回避する形に拡張。AI / LLM 一切なし(literal 制約は [[feedback_title_no_ai]] 継承)、forward-only(既存 published 記事の遡及修正なし)。

## goal

新規生成記事 title が以下を満たす:
- 引用 substring は **20-40 字 literal**(短すぎ disable、20 字未満は draft / review 落とし or 別 pattern)
- `…` truncation 廃止、natural break(句読点)で literal substring 切り出し
- event token は **1 つだけ**、同一事実の言い換え 2 つ目以降は detect + 圧縮
- 反応記事(他選手・監督への反応)pattern を追加: `主語 + 対象 + literal 引用 1-2 つ` 形式

## Phase 分割

### Phase 1: Pattern A の `…` truncation 廃止 + max_len 28 → 40

- `_first_quote(max_len=28)` を `_first_quote(max_len=40)` に拡張
- `…` 切り捨ては禁止、min_len = 20 で natural break 句読点(`。！？、`)で literal 切り出し
- min_len 未満の引用は `None` 返し(Pattern A 不適用 → caller fall-through、最終的に source title 維持 or 別 pattern)
- 既存 Pattern A 通過 test の expectation 更新(28→40)、新規 negative test(短 / 長すぎ / natural break)追加

**実装行数**: 約 50 行(_first_quote 改修 + 既存 test 更新 + 新規 test)

### Phase 2: 反応記事 pattern 追加

- 新 subtype `player_reaction`(他選手 / 監督への反応記事、本人の発言だが文脈は対象に祝福 / 評価)
- 新 `_assemble_pattern_R_reaction()`: `[主語選手名] + が + [対象選手 + 達成 fact] + を + [反応動詞 (祝福 / 称賛 等)]「[literal 引用 1-2 つ]」`
- 例 67146 fix: `岡本和真が坂本勇人の劇的通算300号を祝福「さすが」「エンターテイナー」`
- 反応動詞は source 由来の literal 抽出(祝福 / 称賛 / 反応 / 喜び 等)、AI 禁止
- 引用は 2 つまで literal 結合可(both source-verified 必須)

**実装行数**: 約 80 行

### Phase 3: event token 重複検出 + 圧縮

- 67169 のような「サヨナラ + メモリアル弾 + ２試合連続サヨナラ勝」型を detect
- 同一試合状態 fact が 2 つ以上検出されたら 1 つに圧縮(最長 / 最具体を採用)
- 数値 fact(300号 等)+ 試合状態 fact(サヨナラ 等)は別軸として共存可

**実装行数**: 約 60 行

### Phase 4: live canary

- noindex / X OFF 状態で 1 週間観察、title 適合率 / クリック誘発(可能なら) / source URL 失敗率 を測る

## 不可触リスト(hard constraints)

- AI / LLM call を新 path に持ち込まない([[feedback_title_no_ai]] 継承)
- 既存 published 記事の title 遡及修正なし(forward-only)
- 334-QA Phase 1-3b の digest title path(`_assemble_pattern_X_player_voice_digest`)を変更しない
- publish / mail / scheduler / env / Cloud Run / SEO / source 追加は本 ticket scope 外
- X 自動投稿への影響 0(本 ticket は title 生成 path のみ)
- 既存 pytest baseline 維持(増減 0、新 test 追加分のみ +)

## success criteria

- Phase 1: focused pytest +5-10 件、既存 25 件全 PASS、`…` 出現を新 path から駆逐
- Phase 2: 反応記事 pattern test +5-10 件、`pattern_R` literal contract 守られる
- Phase 3: event token 圧縮 test +5 件、源 fact 1 つ残り 2 つ目以降は drop
- Phase 4 canary: title 中で `…` 末尾 0 件、`「」` 内 ≥ 20 字 達成率 ≥ 80%、event 重複 0 件

## next action

Phase 1 narrow PR から着手。Phase 0 audit は 334-QA で実施済の延長で skip 可。
