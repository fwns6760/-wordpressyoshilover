# 017 — ホーム上部の「今日の試合」ハブ

**フェーズ：** 一軍試合ループの可視化  
**担当：** Codex A  
**依存：** 012, 014

---

## 概要

のもとけ型の「今日何が起きているか」を一目で見せるため、ホーム上部に `今日の試合` ハブを置く。
ここは 1 試合を `pregame / live / postgame` でつなぐ入口であり、固定版と AIエージェント版の分岐結果を読者に見せる起点でもある。
正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §5 / §7。親チケットは `doc/010` (`28d4968`) / `doc/012` (`d50a0dc`) / `doc/014` (`2d92405`)。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`

---

## 決定事項

### 役割

- ハブの目的:
  読者が「今日の巨人の試合」を最短で追える導線にする。
- ハブの目的:
  `game_id` と `meta.game_state` を入力にし、`doc/012` の `pre -> live -> post` 単方向 state で表示内容を切り替える。
- ハブの目的:
  1 試合から A4 `CORE_SUBTYPES` の `pregame / live_anchor / postgame / farm / fact_notice` へ再訪できる導線を作る。
- 入力条件:
  `game_id` は `doc/012` 定義の `YYYYMMDD-<主催略称>-<対戦略称>` を使う。
- 入力条件:
  `meta.game_state` は `pre / live / post` を使い、`game_id` 未確定の Draft はハブに出さない。

### 表示内容

- pregame:
  対戦カード、開始時刻、球場、予告先発、試合前まとめ記事への導線を出す。
- pregame のリンク記事:
  `subtype=pregame` を主導線とし、`fact_notice` の公示 / 予告先発関連を補助導線にする。固定版レーンの定型試合前まとめを前提にする。
- live:
  現在スコア、最新更新時刻、ライブ速報アンカー、関連 `fact_notice` 更新への導線を出す。
- live のリンク記事:
  `subtype=live_anchor` を主導線とし、交代・好打・差分追記の `fact_notice` を併記する。AIエージェント版の updating 1 本を前提にする。
- postgame:
  最終スコア、試合後まとめ記事、主要選手、関連 `fact_notice` への導線を出す。
- postgame のリンク記事:
  `subtype=postgame` を主導線とし、同日二軍結果があれば `farm` を補助導線にする。AIエージェント版の source 統合結果を前提にする。
- no game:
  当日試合が無い場合は次戦情報、直近の `postgame`、直近の `farm` を出す。
- no game のリンク記事:
  次戦の日付 / 対戦 / 場所 / 予告先発を添え、直近 `postgame` 1 本 + 直近 `farm` 1 本を基本にする。
- 状態別リンクサマリ:
  pregame は `pregame` / `fact_notice`、live は `live_anchor` + 差分追記の `fact_notice`、postgame は `postgame` / `farm`、no game は直近 `postgame` / 直近 `farm` をつなぐ。全状態で `fact_notice` は常時表示候補にする。

### 非機能

- ハブの入口:
  固定版レーン産の `pregame / farm / fact_notice` と、AIエージェント版産の `live_anchor / postgame` を同じハブに載せる。
- 読者への見え方:
  読者には固定版レーン / AIエージェント版の区別を見せず、route 判定結果だけを `doc/014` の `ALLOWED_CATEGORIES` とタグで露出する。
- 既存メール / monitor / automation:
  `quality-monitor` / `quality-gmail` / `draft-body-editor` は本便で不可触とする。
- 既存設定:
  Gmail / SMTP / sendmail / scheduler / automation / env / secret は触らない。
- published の扱い:
  WordPress への published write は行わず、Draft 表示前提の設計だけを固定する。
- `012` の state model に従い、`pregame -> live -> postgame` の単方向で表示を切り替える。
- game_id が未確定の Draft はハブに出さない。

---

## TODO

### 役割

【×】ホーム上部ハブの目的を 3 行で固定する  
【×】`game_id` / `meta.game_state` を入力にすることを明記する  

### 表示内容

【×】pregame の表示項目を決める  
【×】live の表示項目を決める  
【×】postgame の表示項目を決める  
【×】試合が無い日の表示項目を決める  
【×】各状態でリンクさせる記事タイプを決める  

### 非機能

【×】固定版 / AIエージェント版の両方の入口であることを明記する  
【×】automation / メール設定に触らないことを明記する  

---

## 成功条件

- `今日の試合` ハブが pre/live/post の 3 状態で説明できる  
- 1 試合から複数記事へ飛ぶ導線が明記されている  
- 既存運用に副作用を出さない  
