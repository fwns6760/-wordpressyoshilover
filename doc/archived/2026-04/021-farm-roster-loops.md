# 021 — 公示 / 昇降格 / 二軍の 3 ループ接続

**フェーズ：** 一軍外の更新OS整備  
**担当：** Codex A  
**依存：** 012, 014, 019

---

## 概要

巨人版は一軍試合だけではなく、公示 / 昇降格 / 二軍・若手の流れが重要。
このチケットでは、`公示 / 昇降格 / 二軍` を 3 ループとしてつなぎ、一軍試合ループと別軸で回る更新OSを定義する。
正本要件は `docs/handoff/giants_agile_requirements.md` §5 / §6 / §9。親チケットは `doc/012` (`d50a0dc`) / `doc/014` (`2d92405`) / `doc/019`。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`

---

## 決定事項

### 3 ループ

- 公示ループ:
  `npb.jp` 公示 / `giants.jp` お知らせの `primary tier` source を起点に、登録 / 抹消 / 予告先発 / 出場選手登録 / FA / 日本人メジャー移籍等を扱う。A4 `CORE_SUBTYPES` の `fact_notice`、category=`選手情報`、タグ `公示` + 選手名必須、`doc/019` の公示カード仕様に準拠する。
- 昇降格ループ:
  一軍 / 二軍間の移動、故障者リスト入り / 復帰、育成→支配下、支配下→育成を扱う。A4 `CORE_SUBTYPES` の `fact_notice` とし、タグは `公示` or `契約` + 選手名 + 移動方向、`source_trust` は公示の `primary tier` を優先し、X は `secondary tier` の補足だけに使う。
- 二軍・若手ループ:
  二軍試合結果は A4 `CORE_SUBTYPES` の `farm`、若手活躍や調整状況もここに束ねる。`giants.jp` 二軍試合 / 二軍順位の `primary tier` source を起点にし、選手個別 X は `secondary tier` 補足、タグは `ファーム` + 選手名 + 対戦相手 + 日付を基本にする。

### 接続

- 一軍試合への接続:
  公示 / 昇降格が一軍試合メンバーに影響する場合だけ、該当試合の `pregame / postgame` 本文に関連リンクを埋め込む。`doc/017` / `doc/020` を前提に、一軍側の `game_id` から派生参照を張り、影響の無い二軍内部移動は接続しない。
- 二軍との接続:
  `subtype=farm` は独立運用し、`doc/017` ハブでは `no game` または同日 farm 枠に表示する。一軍昇格 / 故障復帰の文脈では対応する公示 / 昇降格記事に関連付け、同日に一軍・二軍両試合がある日は `game_id` を別採番して並列表示する。
- タグ接続:
  横断軸は `ファーム / 公示 / 契約 / 選手名` とし、各記事に話題軸 1 件以上 + 選手名 1 件以上を必須にする。`doc/014` の `tag_category_guard` に合わせ、`TAG_TARGET_LOW`=15 以上 `TAG_MAX`=20 以下を維持し、`固定版レーン` と `AIエージェント版` の双方で同じ taxonomy を使う。

### 非機能

- 一軍試合 loop を壊さない:
  `doc/017` の `今日の試合` ハブの `pregame / live_anchor / postgame` 表示は本 loop 派生で書き換えない。一軍試合の `game_id` と公示 / 昇降格 / 二軍の `game_id` は別採番とし、二軍は別 prefix、公示は `game_id` 無しで扱う。`doc/020` の一軍 `postgame` 連鎖の派生本数上限には公示 / 昇降格を含めない。
- 既存 mail / automation は触らない:
  `quality-monitor` / `quality-gmail` / `draft-body-editor` は本便の対象外とする。Gmail / SMTP / sendmail / scheduler / env / secret / automation.toml / published write は触らず、WP write もしない。
- 固定版と AIエージェント版の routing は 010 / 011 / 014 を優先する:
  `固定版レーン` / `AIエージェント版` の判定は `doc/010` を正本とし、固定版レーン 6 型の境界は `doc/011`、`source_trust` と taxonomy は `doc/014` を正本とする。本書では routing ルールを新設せず、`giants_agile_requirements` の適用範囲を公示 / 昇降格 / 二軍へ拡張するだけに留める。

---

## TODO

### 3 ループ

【×】公示ループの対象を決める  
【×】昇降格ループの対象を決める  
【×】二軍・若手ループの対象を決める  

### 接続

【×】一軍試合 loop との接続条件を決める  
【×】二軍 loop との接続条件を決める  
【×】タグ接続の必須軸を決める  

### 非機能

【×】一軍試合 loop を壊さない制約を明記する  
【×】mail / automation に触らないことを明記する  
【×】routing の正本を 010 / 011 / 014 に置くことを明記する  

---

## 成功条件

- 公示 / 昇降格 / 二軍の 3 ループが説明できる  
- 一軍試合 loop との接続条件がある  
- 巨人版の更新OSが一軍以外にも広がる  
