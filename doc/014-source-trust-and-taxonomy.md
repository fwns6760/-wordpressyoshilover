# 014 — source trust・カテゴリ・タグ設計

**フェーズ：** 情報源と分類の固定  
**担当：** Claude Code  
**依存：** 010

---

## 概要

のもとけ型を参考に、カテゴリは粗く、タグは細かく設計する。
source trust も同時に固定し、固定版レーンと AIエージェント版レーンの分類ミスを減らす。
正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §6 / §9。親チケットは `doc/010-giants-lane-routing.md` (`doc/010`, commit `28d4968`)。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`。

---

## 決定事項

### source trust

- 主 source:
  `giants_agile_requirements` §4 と A5 `src/source_trust.py` を基準に、公式 / NPB / 主要媒体 RSS を主 source とする。設計上は `primary tier` と呼び、固定版レーンで唯一許容する。
- X の扱い:
  X は本文参照に使う従 source とし、設計上は `secondary tier` とする。巨人公式 / 選手公式 / 報道公式の投稿も本書では secondary と扱い、単独 source では Draft を作らない。
- 断定禁止:
  X 単独 source の記事は AIエージェント版へ差し戻す。A5 `source_trust` の `rumor` / `unknown` は除外し、`primary tier` の裏取りが取れない場合は公開しない。
- manager_recommendation:
  `src/source_trust.py` の現実装には X handle を `primary` 扱いする箇所があるが、014 の設計決定は「X は全て `secondary tier`」。consumer wiring 便で整合を取る前提にする。

### カテゴリ

- 親カテゴリ固定:
  A7 `src/tag_category_guard.py` の `ALLOWED_CATEGORIES` に合わせ、親カテゴリは `試合結果` / `スタメン` / `選手情報` / `その他` の 4 件で固定する。
- 粗く保つ方針:
  category は粗く固定し、細分化はタグで吸収する。新カテゴリ追加は user 判断とし、既定の `ALLOWED_CATEGORIES` を崩さない。
- 置き方:
  一軍 / 二軍とも試合記事は category=`試合結果` とする。番組情報と他球団を含む一般 `プロ野球` は category=`その他` とし、タグで `番組` / `プロ野球` を付け、固定版レーンの routing もこの割当でそろえる。

### タグ

- 選手タグ:
  巨人所属選手は選手名タグを必ず 1 件付与する。他球団選手は対戦文脈など必要時のみ付与し、主役でない場合は付けすぎない。
- 業務タグ:
  subtype=`farm` は `ファーム` 必須、subtype=`fact_notice` の公示は `公示` 必須、契約更改 / トレード / 入団 / 退団は `契約` 必須、統計中心記事は `野球データ` 必須とする。
- 試合結果タグ数:
  1 軍試合結果は `1軍` + 対戦相手 + 日付、2 軍試合結果は `ファーム` + 対戦相手 + 日付を必須にする。総タグ数は A7 `tag_category_guard` の `TAG_TARGET_LOW`=15 以上 `TAG_MAX`=20 以下を守る。

---

## TODO

### source trust

【×】公式 / NPB / 主要媒体 RSS を主 source として定義する  
【×】X を従 source として定義する  
【×】X 単独で断定しないルールを明記する  

### カテゴリ

【×】巨人版の親カテゴリ案を列挙する  
【×】カテゴリを細かく割りすぎない方針を明記する  
【×】試合結果 / 番組情報 / プロ野球 の置き方を決める  

### タグ

【×】選手タグの方針を決める  
【×】`ファーム` / `公示` / `契約` / `野球データ` のタグ方針を決める  
【×】1軍試合結果 / 2軍試合結果 のタグ方針を決める  

---

## 成功条件

- source trust が 3 行で説明できる  
- カテゴリは粗く、タグは細かくの方針が明文化されている  
- 固定版 / AIエージェント版の分類に使える taxonomy になっている
