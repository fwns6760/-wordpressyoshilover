# PUB-002-A publish candidate gate and article prose contract

## meta

- owner: Claude Code
- type: ops / publish gate / single-source-of-truth contract
- status: READY
- parent: PUB-002(少量手動公開と記事品質改善レーン)
- consolidates: PUB-002 / 085(title style)/ 040(repair playbook)/ 071(title-body-nucleus-validator)/ 078(nucleus-ledger-adapter)/ 079(nucleus-ledger-emitter)
- created: 2026-04-25
- updated: 2026-04-25 21:55(WP publish vs X/SNS で判定厳しさを変える明記、user policy lock)
- updated: 2026-04-25 22:30(title-body / source-body の深い矛盾検査は HALLUC-LANE-002 で完全 verify、PUB-004-A で rule-based 部分検査 + 限界明記)

## title-body mismatch / source-body contradiction の検査現状(2026-04-25 22:30 lock)

R2(title-body mismatch)/ G3(主語・事象 一致)/ G7(数字 source 矛盾なし)/ G8(source にない断定なし)の検査は **2 段階構成**:

| 段階 | 担当 | 検査範囲 | 限界 |
|---|---|---|---|
| **Phase 1**(現状、PUB-004-A) | 071/078/079 + rule-based | SUBJECT_ABSENT / EVENT_DIVERGE / MULTIPLE_NUCLEI / 異常値 regex / token 覆い率 | 意味整合 / 一次照合 / 文意レベル不足 |
| **Phase 2**(後続、HALLUC-LANE-002) | Gemini Flash adapter | 完全 verify(意味整合 + 一次照合 + unsupported claim 文意検出) | API 課金、user judgment 必要 |

PUB-004-A は Phase 1 で運用開始、Phase 2 は **品質強化レーン**(PUB-004 の前提**ではない**)として後追い統合。
詳細は `doc/HALLUC-LANE-002-llm-based-fact-check-augmentation.md`。

## purpose

noindex 小規模公開で「どの記事を publish してよいか」「文章がどうならOKか」を **1 枚に固定** する。
PUB-002 / 085 / 040 / 071 / 078 / 079 に散らばった条件を統合し、Claude が毎回迷わず **Green / Yellow / Red 判定**できる状態にする。

## 適用先で判定厳しさを変える(2026-04-25 21:55 lock)

本判定表は **WordPress publish と X / SNS POST で適用厳しさを変える**:

| 適用先 | 採用 ticket | publish/POST 対象 | refuse 対象 |
|---|---|---|---|
| **WordPress publish** | PUB-004 | **Green + Yellow**(危険な Red だけ止める方針) | Red |
| **X / SNS POST** | PUB-005 | **Green only** + 追加 X-side strict 条件 + user 確認 fixed | Yellow + Red + X-side Red |

→ 同 draft でも、WP publish では Yellow なら publish OK、X POST では Yellow は除外。

X-side 追加 strict 条件(PUB-005 詳細):
- source 弱い(primary 1 件未満 / Twitter only)
- title speculative
- title-body 不一致
- injury / death / 抹消 系
- 同一試合 24h 以内 重複
- 数値リスト型
- quote-heavy で出典不明確

## 前提

- X 投稿なし
- noindex 維持
- publish-notice mail は送ってよい
- 自動公開ではなく、小規模 publish
- `RUN_DRAFT_ONLY=False` はまだ触らない
- 376 drafts 一括公開は禁止
- front は別 Claude owner

---

## 1 枚 判定表

### Green: 公開可(そのまま publish)

**全 10 条件を満たす**:

| # | 条件 | 検証方法 |
|---|---|---|
| G1 | featured image あり | `featured_media > 0` |
| G2 | primary source URL あり | source_block マッチ(Yahoo!プロ野球 / 報知 / スポーツナビ / 日刊 / スポニチ / デイリー / サンケイ / 読売 / スポーツ報知)or 公式 X URL |
| G3 | title と body の主語・事象が一致 | 071 validator pass(SUBJECT_ABSENT / EVENT_DIVERGE / MULTIPLE_NUCLEI 不発火) |
| G4 | title は fact-first | 数値 / 選手名 / 事象が title 先頭、speculative phrase なし |
| G5 | speculative phrase なし | regex: `どう見[るた] / どこを / どこへ / どこか / 見たい / 見せ[るたい] / 予想 / 気になる / 狙いはどこ / 何を / どんな / どう並べ / どう動く / どう攻め / どう戦 / 誰だ / どう打 / どう起用 / どうな[るた] / なぜ / 何が / ？ / ?` 全て不該当 |
| G6 | 冒頭 2〜4 行で何の記事か分かる | body_text 先頭 200 chars で主語 + 事象 + 出典が読める |
| G7 | 数字・スコア・日付・選手名が source と矛盾しない | source 一次照合(可能な範囲)+ 異常値検知(打率 .400 超は要確認) |
| G8 | 本文が source にない断定をしていない | source_block / source_urls にない named-fact がない |
| G9 | noindex が維持 | site-level noindex 設定不変(WP REST status flip では変動しない) |
| G10 | X / SNS 自動投稿なし | WP REST update_post_status 単独では fetcher pipeline 経由の auto_tweet を発火しない(verified) |

### Yellow: 修正後公開可

**Green 条件を 1〜3 件のみ満たさず、かつ Red 条件に 1 つも該当しない**:

- 核は正しいが文章が薄い(prose 500-800 chars 程度)
- 見出しが少し浮く(`💬 〜?` `【注目ポイント】` 一般論)
- 数字確認が必要(打率 / 戦数カウント等の specific count claim、source 一次照合可能)
- source 表示が弱い(source_block に名前あるが本文中の inline link 不足)
- 軽い修正で publish 可能(WP admin で 3-5 行の deletion / 1 段落の compression)

### Red: 公開しない(hold)

**1 つでも該当したら hold**:

| # | Red 条件 | 例 |
|---|---|---|
| R1 | source にない具体事実 | source_block に記載のない年 / 数 / スコア / 選手名 |
| R2 | title-body mismatch | title が「巨人スタメン」だが body が試合結果 / コメント / 別記事 |
| R3 | 別記事混入 | body 中に別記事の lineup / 別試合の数字が紛れ込む |
| R4 | 未確認引用 | source X に明記なき player/coach quote、特に injury/状態関連 |
| R5 | injury / death / 登録抹消 / 試合結果が怪しい | 「故障」「離脱」「登録抹消」「コンディション不良」「アクシデント」「亡くな」「天国」「死去」「引退」「交代」「診断」「症状」「ケガ」 unverified |
| R6 | 同一試合の重複記事 | 同 game-day + 同 opponent の lineup / postgame が既 publish 済 |
| R7 | 数値リストだけで記事核が弱い | NPB 通算安打 ranking 形式 (`①(東映)3085 : ⑤(広島)2543`)、本文も補強なし |
| R8 | 4/17 事故と同質リスク | 公開前 draft に根拠のない具体事実、別記事由来の混入、未確認の引用 / 試合結果 / 選手状態 が読者に事実として見える状態 |

---

## 文章条件(prose contract)

公開する記事の本文は以下を満たす:

- **のもとけ型 fact-first** = 一次情報核 + 出典明示 + 推測を出典と区別
- **禁止 phrase**: 「どう見る」「何を見せるか」「本音は」「注目したい」「気になる」「予想」「ポイントはどこ」系
- **禁止 tone**: AI っぽい一般論(「初回の入りが鍵」「下位打線の流れに注目」等の boilerplate)
- **必須**: 参照元が本文の主張を支える(source_block + 該当箇所の明示)
- **1 記事 1 核**: 1 件の事象 / 1 名の選手 / 1 試合に絞る
- **冒頭契約**: 冒頭 2〜4 行で **主語・事象・出典** が分かる
- **混入禁止**: 関連記事ブロック / サイト部品(💬 〜?、【関連記事】、【先発投手】空、💬 ファンの声 X URL list)が本文の事実主張に混ざらない

---

## publish 前チェックリスト(運用、Claude 側 1 分以内)

```
[ ] G1 featured image あり (REST: featured_media > 0)
[ ] G2 primary source 検出 (body_text 内 PRIMARY_SRC regex hit)
[ ] G3 071 validator pass (subject/event 一致)
[ ] G4 title fact-first (数値 / 名 / 事象先頭)
[ ] G5 speculative phrase 不在 (SPECULATIVE regex 不発火)
[ ] G6 冒頭 200 chars で主語 + 事象 + 出典が読める
[ ] G7 数字 source と矛盾なし (異常値 .400 超等手動 check)
[ ] G8 source にない断定なし (source_urls + source_block 整合)
[ ] G9 noindex 維持 (site-level、status flip では変動しない)
[ ] G10 X / SNS auto-post 配線なし (REST status flip 単独では fire しない)

Red 該当なし:
[ ] R1 source 不在 named-fact なし
[ ] R2 title-body mismatch なし
[ ] R3 別記事混入なし
[ ] R4 未確認引用なし
[ ] R5 injury/death/抹消/試合結果 怪しさなし
[ ] R6 同一試合重複なし (既 publish post と game-day + opponent 一致しない)
[ ] R7 数値リスト形式で核なし、ではない
[ ] R8 4/17 同質リスクなし
```

判定 logic:
- **Red 1 件でも該当 → hold(publish しない)**
- **Green 全 10 + Red 全不該当 → publish そのまま**
- **Green 1〜3 件不足 + Red 全不該当 → Yellow(軽修正後 publish)**

---

## 運用

- Claude が候補を **自分で絞る**(user に大量候補を投げない)
- 原則 **3〜5 件まで** / 1 batch
- 6 件以上の publish / mail burst になりそうなら **止める**
- 判定と結果を本 ticket または session_log に記録する
- 本 ticket は contract、判定実行は PUB-002 workflow + PUB-003 trigger で行う

## 完了条件

1. Green / Yellow / Red の判定表が **1 枚に固定**(本 ticket の "1 枚 判定表" 節)
2. publish 前チェックリスト ができる(本 ticket の "publish 前チェックリスト" 節)
3. Claude が user に毎回迷わせず進められる(本 ticket を read-only 参照、判定は autonomous)

## 不可触

- `RUN_DRAFT_ONLY=False` flip
- 376 drafts 一括公開
- front lane / plugin
- automation / scheduler / .env / secrets
- baseballwordpress repo
- X API / Cloud Run

## 関連 file

- `doc/PUB-002-launch-small-manual-publish-and-quality-improvement.md`(親 ticket、本 ticket は判定 contract)
- `doc/085-title-style-analysis-and-contract-refresh.md`(title style 8 共通 rule + 10 subtype contract)
- `src/title_body_nucleus_validator.py`(071 validator、G3 検証)
- `src/repair_playbook.py`(040 repair、Yellow 修正手順)
- `src/nucleus_ledger_adapter.py` / `src/nucleus_ledger_emitter.py`(078/079、ledger 配線)
- `src/tools/run_pre_publish_fact_check.py`(HALLUC-LANE-001、Phase 2 LLM 接続後 = Red 自動検出強化)

## 補足: HALLUC-LANE-002 連携(後続)

LLM 実検出(HALLUC-LANE-002)が稼働後、本 ticket の Green/Yellow/Red 判定は detector の output(severity 5 段 + 9 risk_type + suggested_fix)と 1 対 1 mapping:

- detector `overall_severity = none` + `is_4_17_equivalent_risk = false` → Green
- detector `overall_severity in {low, medium}` + `safe_to_publish_after_fixes = true` → Yellow
- detector `overall_severity in {high, critical}` or `is_4_17_equivalent_risk = true` → Red

それまでは本 ticket の手動判定表を Claude が回す。
