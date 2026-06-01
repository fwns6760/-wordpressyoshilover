# 465 DATA-ARTICLE title の発見ドリブン化(機械テンプレ脱却・no-AI維持)

- **種別**: 実装 / **priority**: P2(差別化C・CTR/長尾SEO) / **effort**: M
- **親**: 443 / 設計: `455...md` §16 / §17 Phase2C / GH: #129
- **status**: READY(title rule の確定先行)

## 背景(深掘り 1次source)

データ記事 title は全て機械 f-string(`【巨人データ】{選手}、{指標}{値}で{league}{順位}位（{scope}）`)。**「発見/驚き」を表現できていない**。memory の title rule([[feedback_title_no_ai]] / [[feedback_title_clickable_descriptive]])= 3-token literal・no-AI・末尾truncation禁止 は維持必須。

## ゴール

no-AI rule を**維持したまま**、数値の**対比/驚き**を title に literal で載せる。例:
- 現状: `【巨人データ】吉川尚輝、終盤打率.286でセ3位（直近30日）`
- 改善: `【巨人データ】吉川尚輝、終盤.286は序盤.194の1.5倍 競り合いに強い（直近30日）`
- = source 数値の対比(序盤/終盤・本拠/ビジター差・順位変動)を literal 組み立てで「発見」化。LLM rewrite はしない。

## 対象

- `config/insight_whitelist.json` の `title_format`(case A-D, L113-131)+ 各 publisher の title 組み立て。
- `insight_title_guard`(period suffix)維持。

## やる / やらない

- やる: 対比型 title pattern(case 追加)、driver となる数値の選定ロジック、test。
- やらない: **LLM/AI で title 生成**、煽り誇張(事実から外れる)、末尾 `…` truncation、媒体名混入。

## 成功条件

- 主要角度の title が「発見/対比」を literal で表現、no-AI / 60字以内 / truncation無 を維持。
- title rule の regression test green(既存 title guard を壊さない)。

## 依存

title rule(どの対比を driver にするか case 設計)を確定してから実装。
