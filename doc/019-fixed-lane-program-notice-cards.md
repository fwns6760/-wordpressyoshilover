# 019 — 番組情報 / 公示 / 予告先発の固定版カード

**フェーズ：** 固定版レーンの量産面強化  
**担当：** Codex B  
**依存：** 011, 014

---

## 概要

固定版レーンの中でも、`番組情報 / 公示 / 予告先発` は更新頻度が高く、型も安定している。
ここをカード型・短記事型として揃え、Gemini Flash 単独でも崩れにくい状態にする。
正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §9。親チケットは `doc/011` (`4dc0b2b`) / `doc/014` (`2d92405`)。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`。

---

## 決定事項

### 3 型の役割

- 番組情報:
  放送・配信・出演情報を短く高速に Draft 化する。`subtype=fact_notice` の一部として扱い、category は `その他`、タグ `番組` を必須にする。
  `doc/011` の巨人公式 / 関連番組 RSS の `primary tier` source を直接使う。
- 公示:
  登録 / 抹消 / FA などの事実通知を誤読なく Draft 化する。`subtype=fact_notice`、category は `選手情報`、タグ `公示` を必須にする。
  `doc/011` の `npb.jp` 公示 / `giants.jp` お知らせの `primary tier` source を直接使う。
- 予告先発:
  今日の試合ハブと接続する固定カードとして扱う。固定版レーンでは `CORE_SUBTYPES` の `pregame` に置き、事実通知面では `fact_notice` 寄りの運用にする。
  category は `試合結果`、タグ `予告先発` を必須にし、`doc/011` の `npb.jp` 予告先発 / `giants.jp` の `primary tier` source を直接使う。

### カード仕様

- 番組情報カード:
  番組名 / 放送日時 / 放送局 or 配信 platform / 出演者(判明分) / 出典リンクを必須にする。
  A7 `src/tag_category_guard.py` の `tag_category_guard` に合わせ、タグは `番組` + 放送日 + 出演者名を優先し、総数は 15〜20 を目安にする。
- 公示カード:
  選手名 / 公示種別(登録・抹消・FA 等) / 対象日 / 影響(起用変更等) / 出典リンクを必須にする。
  タグは `公示` + 選手名 + 種別 + 日付を優先する。
- 予告先発カード:
  試合日 / 対戦カード / 両軍予告先発 / 球場 / 直近成績(短く) / 出典リンクを必須にする。
  タグは `予告先発` + 投手名(両軍) + 対戦相手 + 試合日を優先する。
- title / body 短縮ルール:
  title は `doc/011` の template に準拠し、超過時は日付 / 選手名 / 種別などの優先キーを先頭固定で短縮する。
  body は `doc/011` のブロック順を維持し、カード型は 3〜5 ブロックまでに絞る。短縮で欠落が出る場合は末尾に「※ 詳細は出典リンクを参照」を付ける。

### 非機能

- primary source 前提:
  `giants_agile_requirements` §4、A5 `src/source_trust.py` の `source_trust`、`doc/014` を基準に、すべて `primary tier` の source のみで Draft 化する。
  category は A7 `tag_category_guard` の `ALLOWED_CATEGORIES` 内に固定し、3 型は固定版レーンの `CORE_SUBTYPES` の `fact_notice / pregame` に収める。
- rumor / unknown 除外:
  `source_trust` が `rumor` / `unknown`、または secondary 以下の source は固定版レーンへ入れない。単一 source で完結しないもの、複数 source 統合が要るものは AIエージェント版へ差し戻す。
- mail / automation 不可触:
  `quality-monitor` / `quality-gmail` / `draft-body-editor` は本便の対象外とする。Gmail / SMTP / sendmail / scheduler / env / secret / published write は触らない。

---

## TODO

### 3 型の役割

【×】番組情報の役割を固定する  
【×】公示の役割を固定する  
【×】予告先発の役割を固定する  

### カード仕様

【×】番組情報カードの必須項目を決める  
【×】公示カードの必須項目を決める  
【×】予告先発カードの必須項目を決める  
【×】各カードの title / body 短縮ルールを決める  

### 非機能

【×】primary source 前提を明記する  
【×】rumor / unknown を固定版に入れないことを明記する  
【×】mail / automation に触らないことを明記する  

---

## 成功条件

- 3 型の固定カード仕様が説明できる  
- Flash 単独でも崩れにくい最小項目が揃っている  
- 014 の source trust と矛盾しない  
