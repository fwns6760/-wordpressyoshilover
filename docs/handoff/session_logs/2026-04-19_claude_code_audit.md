# 2026-04-19 Claude Code 監査セッションログ

## 本セッションの焦点

user 指示 Q6: 「本文とかログ読んで。俺もわからない」 → C 軸 記事構造監査（MB-005 前提再評価）

## 主要発見

### 1. chain of reasoning は既に全 Phase 1 subtype prompt に埋め込まれている

`_chain_of_reasoning_prompt_rules()` (`src/rss_fetcher.py:2996`) が以下全てで適用済:

- manager (L3057) 【次の注目】
- game[postgame] (L3335) 【試合展開】
- game[lineup] (L3312) 【注目ポイント】
- game[lineup 変更版] (L3354) 【この変更が意味すること】
- game[pregame] (L3312 経由)
- farm_lineup (L3391) 【注目選手】
- farm (L3414) 【一軍への示唆】

規定の締め語彙: 「気になります」「注目です」「見たいところです」「と思います」
`OPINION_MARKERS` (`src/audit_notify.py:56-71`) はこの 4 語彙＋11 語彙をカバー

### 2. 実記事の出力は chain of reasoning を執行していない

**postgame #62618** (`2026-04-18T20:54 mod`):
```
【試合展開】
巨人1失策、ヤクルト0失策。
```
→ 事実 1 行のみ。解釈なし、感想なし、OPINION_MARKERS 欠落

**lineup #62591** (`2026-04-18T05:00`):
```
【注目ポイント】
反応を見ると、初回の入り方と上位打線の流れを早めに見たい空気が強いです。
```
→ 「見たい空気」は `OPINION_MARKERS` の「見たいところです」に該当しない。文体も編集部観察であってファン視点ではない

### 3. 根本原因：prompt 内部矛盾

`_build_game_strict_prompt` (L3298, 3321):

```
冒頭: 「新しい事実・数字・比較・感想を足さないでください。」
      ↑ 全体ルール、blanket ban

中盤: 【試合展開】で事実→解釈→感想の close を書け（L3335）
     締めに「気になります」等の OPINION_MARKERS を使え
     ↑ chain of reasoning 指示
```

→ Flash は冒頭の「感想を足さない」を優先し、chain of reasoning の感想 close を無視
→ 結果: `no_opinion` 監査 6/7 = 86% が発生

### 4. user の Q5 直感は正しい

user 発言: 「制限を増やすと文字少ない、制限をゆるめるとはるしネーション」
→ まさに prompt 内部で strict/free が衝突している状態。chain of reasoning 追加 (MB-005 未着手扱い) は既に試みられていて、strict に shadowed されている

## MB-005 への影響

**MB-005 の当初 premise は無効**:
- 「chain of reasoning を足せば no_opinion が減る」 → 既に足してある
- 減っていない理由は strict blanket ban の shadowing

**新しい軸で書き直し必要**:
1. prompt 内部の contradiction を解消
2. 「感想を足さない」の例外として締め 1 文を除外する or blanket ban を削除
3. cost 中立（prompt text 変更のみ）

## 推奨次アクション（user 判断待ち）

prompt 修正 1 便:

- `src/rss_fetcher.py:3298`, `:3321`, `:3342` の冒頭 blanket ban 文言を以下のいずれかに変更:
  - 案 A: 「新しい事実・数字・比較は足さないでください」（感想を除外）
  - 案 B: 冒頭は現状維持、chain of reasoning 側に「※冒頭の『感想を足さない』ルールの例外として、締め 1 文のみファン視点の感想を書いてよい」を追加
  - 案 C: 冒頭を「source にある事実のみ使う。感想は締めの 1 文だけ許可」に書き換え

test 戦略: 本番 deploy 後 1 週間 `no_opinion` 件数を観察。`title_body_mismatch` が増えなければ OK。

## 記事サンプル全文

上記分析は `#62618` `#62591` の `content.rendered` を WP REST `https://yoshilover.com/wp-json/wp/v2/posts/{id}` から直接取得して実施。source 自体は `rss_fetcher.py` の strict path を通過して Flash 生成されたもの。

## 未確認事項

- #62609 #62594 の full 本文チェック（ログで十分なら skip 可）
- Cloud Logging 上での Flash 生成 payload 直接観察（prompt と raw response を確認）
- `ENABLE_ENHANCED_PROMPTS=1` の補足ルールが contradiction を緩和 or 悪化させているか
