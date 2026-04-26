# 064 — X source 3区分 contract の固定(事実 / 話題 / 反応)

**フェーズ：** source trust 補強 contract
**担当：** Claude Code
**依存：** 014, 060, 062
**状態：** READY(doc-only、実装 ticket ではない)

## なぜ今これか

- UGCっぽく広く拾いたい一方で、勝敗・試合有無・公示・予告先発・故障・コメント主体などの事実事故は絶対に防ぎたい。
- 現行 014 は「X は従 source / secondary」で止まっており、`fact source / topic source / reaction source` の 3 区分が正本化されていない。
- 060 は SNS運用 contract、062 は SNS反応表示 contract であり、X source 区分そのものの正本ではない。
- のもとけ型に寄せるには「広く拾う」と「狭く断定する」を同時に成立させる source 境界が必要。

## 目的

- X 情報を `fact source / topic source / reaction source` の 3 区分で固定する。
- UGCっぽく広く拾う運用と、記事本文の事実を狭く断定する運用を両立させる。
- Claude / Codex が同じ X 投稿を見た時に、candidate 化 / 断定 / 反応表示の境界を一致して判断できる状態にする。

## 固定する contract

### 1. fact source
本文の事実として断定してよい X source。

- 球団公式 X
- NPB 公式 X
- 球団一次発表に準ずる明確な公式 X
- 公式コメント主体が確認できる一次 X

**用途**
- title の断定文
- 本文冒頭の fact block
- fixed lane の事実根拠

### 2. topic source
記事候補を立てるきっかけとして使ってよい X source。
ただし、primary recheck 前に断定してはいけない。

- 主要媒体 X
- 記者 X
- TV / ラジオ発言を要約した報道 X
- メディア速報ポスト
- 話題化の起点になる報道アカウント投稿

**用途**
- candidate 化
- source_recheck の起点
- AI lane / deferred / hold 判断の材料

### 3. reaction source
回遊・熱量・SNS反応表示にだけ使ってよい X source。
事実断定には使わない。

- ファン反応
- quote / repost
- 感想系投稿
- 話題化している反応群
- コメント的 X 投稿

**用途**
- 記事下 SNS 反応表示
- topic hub 補助
- comment-first 運用の話題補強

## 用途の境界(固定)

- `fact source` のみが title / 本文 fact / fixed lane 断定の根拠になれる。
- `topic source` は candidate 化まではよいが、primary recheck 前に title / 本文 fact へ上げない。
- `reaction source` は記事下 SNS 反応 / hub 話題補助のみ。fact block には入れない。
- X 単独で「勝った / 負けた / 試合があった / 故障した / 登録抹消された」を断定しない。
- 事実と反応を同じ block に混ぜない。

## 禁止事項

- ファン反応から勝敗を断定しない。
- 記者 X 単独で故障や昇降格を確定扱いしない。
- quote / repost を一次情報扱いしない。
- 試合事実と矛盾する X 断片を title / fact block に上げない。
- `reaction source` を本文の勝敗・スコア・試合有無・公示・予告先発・故障の根拠にしない。

## 既存 ticket との関係

- `014` = source trust の土台
- `060` = 公式 / 中の人 X の運用 contract
- `062` = 記事下 SNS 反応表示 contract
- `064` = X source 区分 contract

## 成功条件

- 「X は全部同じ情報ではない」を 3 行で説明できる。
- Claude / Codex が同じ X 投稿を見た時、`fact / topic / reaction` の振り分けを一致して判断できる。
- `広く拾う / 狭く断定する` が ticket 本文で読める。
- 勝敗・試合有無・公示・予告先発・故障・コメント主体について、X 単独で断定しない例が本文にある。

## 非目標

- route 実装変更
- `src/source_trust.py` 修正
- X API / automation / 投稿自動化
- hub / front 実装
- ledger schema 追加
- SNS要約文の自動生成

## acceptance_check

- ticket 単体で 3 区分の定義・用途・禁止事項が読める。
- 014 / 060 / 062 との関係が 1 段落で説明されている。
- `UGCっぽく広く拾うが、事実断定は狭くする` が明文化されている。
- runtime 復旧(044)や既存 fire 順を止めないことが明記されている。

## runtime 復旧 / 既存 fire 順との関係

- 本 ticket は doc-only contract。044 runtime 復旧 routing を止めない。
- 既存 fire 順(046 ✓ → 047 ✓ → [048 HOLD] → 060 並走 → 061 止め)を変更しない。
- 実装副作用なし。route / src/source_trust.py / X API / automation は触らない。
