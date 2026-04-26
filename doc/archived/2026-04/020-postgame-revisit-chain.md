# 020 — 1試合から複数の再訪理由を作る postgame 連鎖

**フェーズ：** のもとけ型再訪導線の中核  
**担当：** Codex B  
**依存：** 012, 013

---

## 概要

正本要件は `docs/handoff/giants_agile_requirements.md` §5 / §7 / §9。親チケットは `doc/012` (`d50a0dc`) / `doc/013` (`df77f6e`)。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`

のもとけ型で重要なのは、1試合を 1 本の記事で終わらせず、再訪理由を複数作ること。
このチケットでは `postgame` を中心に、試合結果から派生する記事の連鎖を整理する。

---

## 決定事項

### 連鎖の基本

- 基本記事:
  `CORE_SUBTYPES` のうち試合後の核は `postgame` に固定し、`game_id` + `subtype=postgame` の一意制約を `doc/012` に合わせて維持する。`postgame` は `doc/013` の AIエージェント版 review / repair ループ対象とする。
- 派生記事:
  主役選手の個別フォロー / 監督コメント / transaction 系 / 野球データ系 / `farm` 連動を基本とし、`fact_notice` または `farm` で切り出す。固定版レーンに戻すのは `postgame` accept 後の派生候補だけに限定する。
- 入口と出口:
  `live_anchor -> postgame -> 派生記事` を固定し、`live` 終了時に `live_anchor` を close、`post` 入りで `postgame` を発火する。`postgame` commit 後 24 時間以内だけ派生を許可し、それ以降はアーカイブ扱いにする。

### 派生条件

- 主役選手が明確:
  記事内で weight の高い選手タグが 1 件以上あり、直近 3 試合で同選手の派生未発行なら個別候補を作る。勝敗直結や特筆成績がない場合、weight が分散している場合は派生しない。
- 監督コメントが強い:
  戦術 / 選手評価 / 次戦方針のいずれかが明確で、引用長さが本文 300 字以上目安かつ source が `primary tier` のときだけ `fact_notice` 派生にする。「良かった」程度の薄いコメントは切り出さない。
- 公示・故障へつながる:
  試合当日または直後 24 時間以内に公示 / 故障 / 登録・抹消 / 契約発表が `primary tier` で確認できた場合だけ transaction 系を独立 `fact_notice` にする。rumor / unknown tier のみなら AIエージェント版で差し戻す。
- 記録・数字が大きい:
  チーム新記録 / 個人節目 / リーグ上位到達などを `primary tier` で確認できた場合だけデータ系派生を作る。タグ「野球データ」+ 該当選手タグを必須とし、単なる打率推移のような汎用更新では派生しない。

### 非機能

- 1試合 1記事で終わらせない:
  `postgame` を起点に、選手 / 監督 / transaction / データの最大 4 本まで派生可とする。1 試合 1 本で閉じず、再訪理由をタグ軸で分岐させる。
- ただし試合中の細切れ乱発はしない:
  `live` 中は `live_anchor` 1 本の update のみに限定し、派生は `post` state 後だけ許可する。1 試合 4 本を超える候補は次試合まで繰り延べる。
- mail / automation は触らない:
  本チケットは doc のみで、mail / automation / Gmail / SMTP / sendmail / scheduler / env / secret は不可触とする。`quality-monitor` / `quality-gmail` / `draft-body-editor` にも触れない。

---

## TODO

### 連鎖の基本

【×】postgame を核にする方針を明記する  
【×】派生記事の種類を列挙する  
【×】live_anchor -> postgame -> 派生記事 の流れを固定する  

### 派生条件

【×】主役選手派生の条件を決める  
【×】監督コメント派生の条件を決める  
【×】transaction 系派生の条件を決める  
【×】データ系派生の条件を決める  

### 非機能

【×】1試合 1記事で終わらせない方針を明記する  
【×】試合中の細切れ乱発を避ける制約を明記する  
【×】mail / automation に触らないことを明記する  

---

## 成功条件

- 1試合から複数の再訪理由を作る流れが説明できる  
- `postgame` が終点ではなく起点になる  
- 乱発ではなく、意味のある派生条件で区切れている  
