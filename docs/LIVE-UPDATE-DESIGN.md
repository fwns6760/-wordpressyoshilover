# Live Update Body Design

2026-04-17 時点の `live_update` 本文型に関する調査メモです。結論は、`live_update_v1` という新しい独立テンプレを今すぐ追加する必要はありません。再開時に必要なのは、新規テンプレ新設よりも、既存の `live_update` 専用処理を `game_v1` の正式 subtype として整理することです。

## 結論

- `live_update` は完全に未整備ではない
- 4/14 に実際に生成された途中経過記事には、`📊 現在の試合状況` と `👀 ここまでの見どころ` が入っていた
- したがって「social型に吸われるだけ」「完全に汎用 fallback だけ」という認識は、現行コードには当てはまらない
- ただし `lineup` / `postgame` のように `game_v1` の正式 subtype としては整理されていない
- `ENABLE_LIVE_UPDATE_ARTICLES=0` を維持したまま、今回は設計記録のみ残す

## 現状の routing

### 1. Yahoo 固定ページの 3 経路

- `スタメン補完`
- `途中経過補完`
- `試合後補完`

コード上の状態:

- `スタメン補完` は gate なし
- `途中経過補完` だけ `ENABLE_LIVE_UPDATE_ARTICLES` が必要
- `試合後補完` は gate なし

該当実装:

- `src/rss_fetcher.py`
  - `_build_yahoo_lineup_candidate`
  - `_build_yahoo_live_update_candidate`
  - `_build_yahoo_postgame_candidate`

### 2. 本文型の扱い

`lineup` と `postgame` は `GAME_REQUIRED_HEADINGS` に入っており、`game_v1` の正式 subtype として扱われています。

一方 `live_update` は次のような状態です。

- `LIVE_UPDATE_KEYWORDS` による subtype 判定はある
- live_update 用の fallback 文面はある
- live_update 用の試合状況カードと見どころブロックもある
- しかし `GAME_REQUIRED_HEADINGS` に `live_update` が無い
- そのため `_is_game_template_subtype()` では `live_update` が false になり、`game_v1` の formal な適用経路から外れている

## 実記事で確認できた本文構造

### 4/14 の途中経過記事

確認できた draft:

- `61969` `巨人9回 途中経過のポイント`
- `61971` `巨人８回 途中経過のポイント`
- `61975` `巨人6回 途中経過のポイント`

確認できた見出し構造:

1. `【ニュースの整理】`
2. `📊 現在の試合状況`
3. `👀 ここまでの見どころ`
4. `【試合のポイント】`
5. `【次の注目】`

`61975` ではさらに `💬 ファンの声（Xより）` も確認。

つまり、過去の live_update 記事はすでに「試合状況カード + 見どころ」を持つ途中経過専用の形になっていました。

### 現在の lineup / postgame

確認した draft:

- `62426` `巨人戦 試合の流れを分けたポイント`
- `62441` `巨人阪神戦 試合の流れを分けたポイント`
- `62459` `巨人阪神戦 田中将大先発でどこを見たいか`

見出し構造:

- postgame
  1. `【試合結果】`
  2. `📊 今日の試合結果`
  3. `👀 勝負の分岐点`
  4. `【ハイライト】`
  5. `【選手成績】`
  6. `【試合展開】`
- pregame
  1. `【変更情報の要旨】`
  2. `【具体的な変更内容】`
  3. `【この変更が意味すること】`

## 必要性判断

### 新しい `live_update_v1` を今すぐ作る必要はあるか

結論:

- いま新しく独立テンプレを切る必要はない

理由:

1. 過去の live_update 記事は、すでに live_update 専用の見出しと要約カードを持っていた
2. 既存コードにも live_update 向けの fallback / closing / summary block がある
3. 問題は「テンプレが無い」ことではなく、「`game_v1` の正式 subtype として整理されていない」こと
4. 途中経過記事は過去に荒れた実績があり、停止中の機能をいま大きく触るのはリスクが高い

### 汎用 fallback や social 型で代用できるか

結論:

- social 型で代用するのは不適切
- 汎用 fallback だけでも不十分

理由:

- live_update では `現在の回 / スコア / 流れ / 次の分岐点` が必要
- social 型は source tweet の整理が主で、試合状況カードを前提にしていない
- 汎用 fallback だけでは試合中の「今どこを見るべきか」が弱い

### 3 経路を同じ型で扱うべきか

結論:

- `スタメン / 途中経過 / 試合後` を同じ型にするべきではない
- ただし別テンプレを乱立させる必要もない
- `game_v1` の subtype として分けるのが妥当

整理:

- `lineup` -> 現行 `game_v1/lineup`
- `live_update` -> 将来 `game_v1/live_update` として formalize
- `postgame` -> 現行 `game_v1/postgame`

## 将来再開する場合の設計方針

### 方針

`live_update_v1` を新設するのではなく、`game_v1` の subtype `live_update` を正式化する。

### 望ましい構造

1. `【ニュースの整理】`
   - 現在の回
   - いまのスコア
   - 流れが動いた場面
2. `📊 現在の試合状況`
   - 現在
   - スコア
   - 流れ
   - 相手
3. `👀 ここまでの見どころ`
   - 次に動くポイントを 2〜3 点
4. `【試合のポイント】`
   - ここまでの材料を短く整理
5. `【次の注目】`
   - 継投 / 次打席 / 次の1点など
6. 任意で `💬 ファンの声（Xより）`

### Gemini prompt の強化ポイント

- 実況の時系列をだらだら並べない
- `今この時点で押さえるべき3点` に絞る
- スコアだけで終わらせず、`どこで流れが変わったか` を明示する
- 次に見るべきポイントを 1〜2 個に絞る
- 試合終了記事の語り方を混ぜない

## 再開前に必要な実装整理

`ENABLE_LIVE_UPDATE_ARTICLES=1` に戻す前に、少なくとも次は必要です。

1. `GAME_REQUIRED_HEADINGS` に `live_update` を追加
2. `_is_game_template_subtype()` 経由で `live_update` を `game_v1` の正式 subtype に入れる
3. strict prompt も `game` 系の正式経路に寄せる
4. `game_body_template_applied` に `subtype=live_update` が出る状態にする
5. 再開時は `途中経過補完` だけを短期間監視し、古い途中経過記事の再発がないか確認する

## 今回の判断

- `ENABLE_LIVE_UPDATE_ARTICLES=0` は維持
- 今回は実装しない
- `live_update` は「不要」ではなく「独立テンプレ新設は不要、正式 subtype 化が将来必要」という整理に留める

## 判断根拠として確認した投稿

- `61969` `巨人9回 途中経過のポイント`
- `61971` `巨人８回 途中経過のポイント`
- `61973` `巨人阪神戦 終盤の一打で何が動いたか`
- `61975` `巨人6回 途中経過のポイント`
- `62426` `巨人戦 試合の流れを分けたポイント`
- `62441` `巨人阪神戦 試合の流れを分けたポイント`
- `62459` `巨人阪神戦 田中将大先発でどこを見たいか`
