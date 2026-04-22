# 067 — comment topic selector と comment記事 contract の固定

**フェーズ：** comment記事の核選定 contract(selector + lane 境界 + structured 初稿 + rule-first validator + bounded repair)
**担当：** Codex B
**依存：** 036, 040, 047, 064, article_quality_contract
**状態：** READY / **FIREABLE**(本線、2026-04-23 user 指示で 044 smoke pass 待ちから外す。doc+impl 一体、記事品質 contract として閉じる。runtime / WSL / observability とは分離)

## 1. why_now

- 今の違和感は文章力ではなく、**記事の核が選べていないこと**が主因。結果として、
  - **generic title**(`どう見る` / `本音` / `思い` 系)
  - **主語不足**(誰の発言か分からない)
  - **title-body mismatch**(title で言っている主語・局面・核が本文と合わない)
  - **総論化**(複数人束ね・比較・「コメントまとめ」化)
  が comment 記事で起きやすい。
- 040 は repair playbook = 後段の直し方。今回は **前段の selector + 初稿 contract**(核を 1 つ選び、structured 出力で書かせる段)を固定する。
- 036 初稿 prompt contract / 047 postgame 派生 emit / 040 repair / 064 X source 3 区分 のいずれも comment 記事の核選定そのものは扱っていない。067 でここを埋める。

## 2. purpose

- comment 記事を **1 speaker / 1 scene / 1 nucleus / 1 source** で閉じる。
- `どう見る` のような generic title / 総論化を validator で落とす。
- standalone に向かない素材は **postgame 本文へ吸収** する(standalone を無理に立てない)。
- title / lead を `主語 + 局面 + 発言の核` に揃える。
- Gemini 2.5 Flash に自由作文させず、**structured input(JSON)→ slot 固定出力** で書かせる。

## 3. comment記事 contract(1 speaker / 1 scene / 1 nucleus / 1 source)

067 の根幹ルール。comment 記事として fixed lane に入れるには以下 4 条件をすべて満たす。

- **1 speaker**: speaker は 1 人のみ(複数人束ねは不可)
- **1 scene**: scene は 1 つのみ(試合後 / 囲み / 公式 X / 公式媒体 のどれか 1 つ)
- **1 nucleus**: 発言の核は 1 つのみ(複数核を詰め込まない、残核は捨てるか postgame へ吸収)
- **1 source**: 媒体名または番組名を必須明記(Draft URL は不可、source_ref は名前のみ)

**分離ルール**: 比較記事 / 総論記事 / 複数人束ね記事 / `コメントまとめ` 型は **fixed comment lane に入れない**。該当素材は reaction / analysis 側へ分離する。

## 4. lane 境界

- **`どう見る` 系 / 解釈系 / 評論系 は comment lane に入れない** → reaction / analysis 側へ分離
- comment lane = **「誰が / どの局面で / 何を言ったか」** に限定(発言の fact と出典の紐付けまで)
- 複数試合横断 / 複数発言集約 / 比較評価 は comment lane 対象外

## 5. selector slots(核を選ぶ時に埋める 6 欄)

核を選ぶ時に、以下 6 slot を必ず埋める。埋まらない slot があれば standalone にしない。

- `speaker`: 誰が話したか(選手名 / 監督 / コーチ、役職つきで明確に、1 人)
- `source_ref`: どこで話したか(媒体名または番組名、Draft URL 禁止)
- `game_context`: いつ / どの試合後か / どの局面か(1 つ)
- `subject_entity`: 誰の / 何の話か(言及対象の選手 / 起用 / 打席 / 投球 / 采配)
- `quote_core`: 発言の核 1 つ(複数あっても 1 つに絞る、他は捨てるか postgame に吸収)
- `downstream_link`: 次の再訪理由(次の試合 / 継続観察 / 別記事への接続)

## 6. standalone 化条件(1/1/1/1 を満たす時のみ standalone)

- §3 の 1/1/1/1 を満たす
- §5 selector slots 6 欄すべて埋まる
- `downstream_link` がある
- 発言が postgame 本文に吸収するには独立性が強い

満たさない時は standalone 化しない。該当素材は **postgame 本文の選手コメント欄へ吸収** する(B3 postgame template / 033 fact kernel と整合)。

## 7. Gemini 初稿 contract(structured input → slot 固定出力)

Gemini 2.5 Flash に自由作文させない。**入力は JSON、出力は slot 固定**。

### 入力項目(JSON)

- `speaker_name`
- `speaker_role`
- `scene_type`
- `game_id` or `null`
- `opponent` or `null`
- `scoreline` or `null`
- `team_result` or `null`
- `quote_core`
- `quote_source`
- `quote_source_type`
- `target_entity`
- `emotion`
- `trust_tier`

### 出力 slot

- `title`
- `fact_header`
- `lede`
- `quote_block`
- `context`
- `related`

### ルール

- Gemini は自由作文しない。slot を超える文章・段落を生成しない。
- comment lane では **H2/H3 原則なし**(slot 順で閉じる。見出し乱発を禁止)
- 入力 JSON に無い情報は生成しない(幻覚封じ)
- `game_id`/`opponent`/`scoreline`/`team_result` が `null` の時は、本文に試合結果を書かない(NO_GAME_BUT_RESULT を作らない)

## 8. title contract

### 必須要素

- **主語**(speaker = 誰が)
- **局面**(scene / 対象 / 試合文脈)
- **発言の核**(nucleus)

### 基本型 3 種

- **A**: `{speaker}、{scene / 対象}に「{nucleus}」`
- **B**: `{speaker}、{target}は「{nucleus}」と明かす`
- **C**: `{speaker}、{team_state / 試合文脈}に{emotion verb}「{nucleus}」`

### 禁止語 / 禁止型

以下の語・語尾・パターンを title に含んだ時点で validator fail(`TITLE_GENERIC`)。

- `どう見る`
- `本音`
- `思い`
- `語る`
- `コメントまとめ`
- `試合後コメント`
- `ドラ1コンビ`(複数人束ね禁止の具体例)
- `Xをどう見る`
- `Xがコメント`
- `Xについて語る`
- `注目したい` / `振り返りたい` / `コメントに注目` / `コメントから見えるもの` / `選手コメントを読む` / `~のコメントに迫る`

### 構造的禁止

- 主語なし title
- 局面なし title
- 核なし title(発言の核が title に反映されていない)
- 複数核を詰め込んだ title(1 title = 1 核)

## 9. lead contract(冒頭 2〜4 行)

冒頭 2〜4 行で以下を必ず読めるようにする(fact-first):

- 誰が
- いつ / どの試合後に / どの局面で
- 何を言ったか
- なぜ記事になるのか(downstream_link が何か)

### 禁止

- 抽象 lead / 感想始まり / 引用羅列始まり
- 主語 / 局面 / 発言の核 のいずれかが lead に欠落

## 10. validator(rule-first、hard / soft 分離)

rule-first の validator。LLM 判定は使わない(機械判定で閉じる)。

### hard fail(fixed comment lane で止める。repair せず agent lane へ routing、または該当素材は postgame 吸収 / 候補止め)

- `GAME_RESULT_CONFLICT`: 本文の試合結果と source 事実が矛盾
- `NO_GAME_BUT_RESULT`: `game_id`/`scoreline`/`team_result` が `null` なのに本文で結果を断定
- `SPEAKER_MISSING`: speaker 不明 / 主語なし
- `QUOTE_UNGROUNDED`: 引用発言の source が確認できない / source_ref なし
- `TITLE_BODY_ENTITY_MISMATCH`: title の主語・局面・核が本文で裏付けられない
- `SOURCE_TRUST_TOO_LOW`: 064 の reaction source 単独 / 一般ファン投稿由来

### soft fail(最大 2 ラウンドの bounded repair、2 ラウンドで解消しなければ agent lane)

- `TITLE_GENERIC`: §8 禁止語 / 禁止型のいずれか該当
- `TITLE_MISSING_SCENE`: title に局面欠落
- `TITLE_MISSING_NUCLEUS`: title に発言の核欠落
- `LEDE_TOO_VAGUE`: §9 lead contract 未達(抽象・感想・引用羅列始まり)
- `TOO_MANY_HEADINGS`: comment lane で H2/H3 乱発(§7 ルール違反)
- `PRONOUN_AMBIGUOUS`: 指示語・代名詞が誰を指すか不明
- `BODY_ORDER_BROKEN`: §7 出力 slot 順(`fact_header → lede → quote_block → context → related`)が崩れている

### 既存 ledger / quality contract tag との衝突

- 038 ledger / 040 repair playbook / 032 body contract / 033 fact kernel / 034 attribution の既存 fail_tag と新規 067 tag が衝突する場合、**既存正本を優先**して 067 側の tag 名を既存に寄せる正規化を Codex B 便の中で実施する
- 新規 tag を ledger schema に追加する場合は 038 ledger README との整合を取る(048 HOLD 解除時の ledger schema 拡張と competition しない、067 単独では schema を書き換えない)

## 11. Codex repair contract(bounded)

- **full rewrite 前提にしない**。1 fail_tag = 1 repairer の bounded repair。
- **hard fail は fixed lane で止める**(repair しない。agent lane routing か、postgame 吸収か、候補止め)
- **soft fail は最大 2 ラウンド repair**。2 ラウンドで解消しなければ agent lane へ。

### 修理範囲(tag → scope)

| fail_tag | scope |
|---|---|
| `TITLE_GENERIC` | `title` のみ |
| `TITLE_BODY_ENTITY_MISMATCH` | `title` + `lede`(hard fail だが agent lane での修理範囲として記録) |
| `GAME_RESULT_CONFLICT` | `fact_header` + `lede`(同上) |
| `TOO_MANY_HEADINGS` | body structure(slot 順への戻し) |
| `QUOTE_UNGROUNDED` | `quote_block` + source 明記(同上) |
| `TITLE_MISSING_SCENE` / `TITLE_MISSING_NUCLEUS` | `title` のみ |
| `LEDE_TOO_VAGUE` | `lede` のみ |
| `PRONOUN_AMBIGUOUS` | 該当 sentence のみ |
| `BODY_ORDER_BROKEN` | slot 並びのみ(内容は触らない) |

- 040 repair playbook と整合(1 Draft あたり Codex repair 上限 1 回 → 超過は escalated は 040 ルールを継承、067 の soft fail 2 ラウンドは 067 内部で閉じる bounded 処理として 040 の上限内に収める運用)

## 12. comment-specific rules(contract 補助)

- 本文先頭近く(`fact_header` or `lede` 直後)に **出典を必ず見せる**(source_ref 名前のみ、Draft URL 禁止)
- 誰が / どこで / 何を言ったかを最初に読めるようにする(§9 lead contract と整合)
- **064 の 3 区分を守る**: fact source の発言のみ title / `fact_header` / `quote_block` で断定可、topic source は primary recheck 前に断定禁止、reaction source は standalone 核に使わない
- 一般ファン投稿(reaction)は standalone 化素材として使わない(`SOURCE_TRUST_TOO_LOW` で hard fail)
- source が弱い(topic source 単独、一次確認未了)場合は standalone にしない。candidate 止まりで source_recheck を待つ

## 13. example contract(良い例 / 悪い例)

### 良い例

- `阿部監督、試合後に浅野の起用意図を説明`(基本型 A、speaker 1 / scene 1 / nucleus 1)
- `岡本、満塁本塁打後に「狙い通り」と手応え`(基本型 C、scoreline と emotion で試合文脈を載せる)
- `山崎、オフのキャンプ初日に「今年は打ちます」と宣言`(基本型 B)

### 悪い例(禁止理由つき)

- `巨人の試合後コメントをどう見る` — `TITLE_GENERIC`(禁止語「どう見る」「試合後コメント」)
- `ドラ1コンビが試合後に手応え、阿部監督も評価` — 1 speaker 違反(複数人束ね)
- `選手の本音に迫る` — `TITLE_GENERIC`(禁止語「本音」)
- `巨人コメントまとめ` — `TITLE_GENERIC`(禁止語「コメントまとめ」)+ 1 speaker 違反
- `Xがコメント` — `TITLE_GENERIC`(禁止型「Xがコメント」)+ nucleus 欠落

## 14. accept(受入確認)

実装 fire 後の accept 判定は以下 5 点で閉じる。

1. comment 記事が **1 speaker / 1 scene / 1 nucleus / 1 source** で閉じている
2. generic title が validator で落ちる(§8 禁止語 / 禁止型が fixed comment lane に残らない)
3. **「どう見る」系が fixed comment lane に残らない**(lane 境界が機能)
4. **`TITLE_BODY_ENTITY_MISMATCH` / `GAME_RESULT_CONFLICT` hard fail が機能する**(title-body mismatch を hard で止める)
5. Gemini 初稿が slot 固定で短く、Codex repair が bounded(1 fail_tag = 1 scope)に収まる

## 15. non_goals

- published 書き換え(Phase 4 まで禁止)
- source expansion(014 / 037 / 064 の範囲で扱う、067 では広げない)
- X API / automation / mail 変更
- 047 派生 emit 条件そのものの再設計(047 は postgame 連鎖の emit、067 は comment の核選定で役割分離)
- ML / LLM 判定 validator(rule-first で閉じる)
- route / trust / source_id / game_id の変更
- 大きい設計 doc を増やす(本 ticket は comment 記事の「核選定 + 初稿 contract + validator + bounded repair」に閉じる)
- 040 の repair 手順書を 067 で書き換える(067 は前段 selector + 初稿 contract + validator、040 は既存 playbook)
- ledger schema 変更(048 HOLD 解除時に別 ticket で扱う、067 は既存 schema に寄せる)

## 16. success_criteria(観測で測る)

- **generic comment title が observation window で 0 件**(§8 禁止語一覧に一致する title が出ない)
- comment standalone 記事の **主語 / 局面 / 核が title で判別できる**(§8 必須要素が全部入っている)
- **`TITLE_BODY_ENTITY_MISMATCH` hard fail が機能**(title と本文の主語・局面・核が矛盾した時に止まる)
- **引用羅列だけの記事が有意に減る**(lead に fact がある比率が上がる、`LEDE_TOO_VAGUE` fail 率低下)
- **standalone に向かない素材は postgame へ吸収される**(067 selector で standalone 不可と判定された素材が postgame 本文で消化)
- **複数人束ね / 総論 / `どう見る` 系 が fixed comment lane に残らない**(lane 境界 §4 遵守)

## 17. fire 前提 / 既存 fire 順との関係

- **本線 fireable**(2026-04-23 user 指示で 044 smoke pass 待ちから外す)。理由 = 067 は comment 記事 contract / rule-first validator / bounded repair の話で、runtime 復旧と分離して進められる。validator は既存 fixture / 既存 Draft で閉じるため、runtime 復帰に依存しない
- **042 は runtime 復旧の別線として継続**(主因 = Codex automation の WSL 実行文脈)。**044 は恒久対策として保持**。**039 は quality-gmail 単独不達時だけ**。067 本線はこれらと同時進行、互いに blocker にしない
- **doc+impl 一体** で 1 便に収める(§31-C 一体化、Codex B 便で doc + selector + structured Gemini prompt + rule-first validator + bounded repairer + tests を 1 commit)
- 067 は **040 / 036 / 047 / 064 / 032 / 033 / 034 の整合に載る追加 contract**(既存 ticket を壊さない)
- 047 postgame 派生 emit、060 SNS 2 アカ、061 自動投稿(止め)、065 mail 下書き bridge(runtime 回復後 blocked 維持)、062 hub、063 hub impl(parked)、048(HOLD 維持)、reserve 群は動かさない
- 本線位置: **047 ✓ → 067 本線 fireable → [048 HOLD 解除判定] → 060 並走 → 061 止め**
- accept 後の observation は runtime 復帰 / 044 smoke pass 後に合流(accept 自体は runtime に依存しない)

## 18. scope 不可触(Hard constraints)

- `src/source_trust.py` / `src/source_id.py` / `src/game_id.py` — 触らない
- `src/tools/run_notice_fixed_lane.py` route 判定層 — 触らない(046 first wave / 047 派生 emit の境界維持)
- `src/postgame_revisit_chain.py`(047 本体) — 触らない
- `src/repair_playbook.py`(040 本体) — 触らない(067 bounded repairer は 040 の API を呼ぶのみ、書き換え不可)
- `src/fixed_lane_prompt_builder.py`(036 本体) — 触らない(067 は comment-subtype 限定の structured prompt で新規 module として切る)
- `src/eyecatch_fallback.py`(041) — 触らない
- `automation.toml` / scheduler / env / secret / mail 経路 — user 承認必須、067 では触らない
- `docs/handoff/ledger/` schema — 触らない(048 HOLD 解除時の ledger schema 拡張と競合させない、067 は既存 schema の fail_tag 命名に寄せる)
- published 書き込み経路 — Phase 4 まで禁止
- Codex A 領域(046 / 047 / 028 T1 / 037 pickup boundary)— diff 0

## 19. 実装ガイド(Codex B 向け、参考)

- **selector**: `src/comment_topic_selector.py` 新規 or 既存 classify 層に module 追加。§5 slots 6 欄を抽出
- **Gemini 初稿 contract**: `src/comment_lane_prompt_builder.py` 新規(036 本体と分離、comment-subtype 限定)。§7 入力 JSON schema + 出力 slot 固定を prompt に織り込む
- **rule-first validator**: `src/comment_lane_validator.py` 新規。§10 hard / soft fail を実装(禁止語 regex / 主語抽出 / source 紐付け / title-body entity 一致判定)
- **bounded repairer**: `src/comment_lane_repair.py` 新規 or 040 repair_playbook の extension。§11 tag → scope map を実装、2 ラウンド上限
- **standalone 不可時 routing**: postgame 吸収へ routing する分岐(047 境界は触らず、067 側で「吸収候補」を出力して 047 emit に渡すだけ)
- **tests**: §13 良い例 / 悪い例 各 minimum 4 パターン + hard fail 6 tag + soft fail 7 tag の validator fail パターン + bounded repair の 2 ラウンド収束パターン
- 既存 validator(030 title / 032 body / 033 fact kernel / 034 attribution)と重複判定は避ける。067 は comment-subtype 限定で切る(subtype gate で入口を絞る)
- doc/067 の **TODO 【】** を埋める形で 1 commit に doc + impl + tests を収める(§31-C 一体化)

## TODO

- 【×】 §3 comment記事 contract(1/1/1/1)を実装する(subtype gate 判定込み)
- 【×】 §4 lane 境界(`どう見る`系を comment lane から除外、reaction / analysis へ routing)を実装する
- 【×】 §5 selector 6 slot の抽出ロジックを実装する
- 【×】 §6 standalone 化条件判定 gate を実装する(不可時は postgame 吸収へ routing)
- 【×】 §7 Gemini 初稿 contract(structured JSON 入力 → slot 固定出力)を prompt + builder で実装する(comment-subtype 限定 module)
- 【×】 §8 title contract(基本型 A/B/C、禁止語、禁止型、構造的禁止)の validator を実装する
- 【×】 §9 lead contract(冒頭 2〜4 行、fact-first)の validator を実装する
- 【×】 §10 rule-first validator(hard fail 6 tag + soft fail 7 tag)を実装する(LLM 判定を使わない)
- 【×】 既存 ledger / quality contract との tag 名衝突を解消する正規化を入れる(既存正本優先)
- 【×】 §11 Codex bounded repair(tag → scope map、soft fail 2 ラウンド上限、hard fail は fixed lane で止める)を実装する
- 【×】 §12 comment-specific rules(出典先出し、064 3 区分遵守、reaction 除外、source 弱い時の候補止め)を実装する
- 【×】 §13 良い例 / 悪い例 各 4 パターン + fail パターン の tests を追加する
- 【×】 §14 accept 5 点を tests で固定し、observation window 合流は runtime recovered 後に確認する
- 【×】 本 doc を 1 commit に含める(doc+impl+tests 一体、§31-C)
