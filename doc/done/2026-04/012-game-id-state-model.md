# 012 — game_id / source_id 束ねと試合状態管理

**フェーズ：** 開発本線の核  
**担当：** Codex A  
**依存：** 010 / 011

---

## 概要

巨人版速報サイトを「試合前・試合中・試合後」でつなぐための中核チケット。
1 試合から複数記事を安全に生むため、game_id / source_id の束ねと state 管理を設計・実装する。
正本要件は `docs/handoff/giants_agile_requirements.md` §4 / §5 / §7。親チケットは `doc/010-giants-lane-routing.md`（commit `28d4968`）と `doc/011-fixed-lane-templates.md`（commit `4dc0b2b`）。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`

---

## 決定事項

### 識別子設計

- `game_id` 定義:
  形式は `YYYYMMDD-<主催略称>-<対戦略称>` とし、例は `20260421-G-T`。`npb.jp` の試合ページを primary tier source として日付・主催・対戦を抽出し、同一試合には常に同じ game_id を返す。
- `source_id` 定義:
  A6 `src/source_id.py` の既存正規化に準拠する。tier 判定は A5 `src/source_trust.py` の `source_trust` を使い、`primary / secondary / rumor / unknown` を区別し、固定版レーンでは primary tier のみを許容する。
- 記事群の束ね方:
  1 試合の cluster は一次キーを `(game_id, subtype)` とし、subtype は A4 `CORE_SUBTYPES` の `pregame / postgame / farm / fact_notice / live_anchor` に固定する。1 試合から複数 subtype が派生する前提で、subtype ごとに 1 本を目安とする。

### 状態

- 試合前 state:
  state は `pre` とし、予告先発確定後から試合開始時刻までを指す。主対象 subtype は `pregame` で、`fact_notice` と試合前の `farm` も同じ state で扱う。
- 試合中 state:
  state は `live` とし、試合開始から試合終了までを指す。主対象 subtype は `live_anchor` で、同一 game_id に対して updating するアンカー 1 本を前提にする。
- 試合後 state:
  state は `post` とし、試合終了から翌日 06:00 までを指す。主対象 subtype は `postgame` で、試合結果としての `farm` もこの state で扱う。
- state 遷移条件:
  遷移は `pre` → `live` → `post` の単方向に固定し、トリガは `npb.jp` 試合ステータス変化または手動上書きとする。`post` → `live` などの逆遷移は禁止し、矛盾時は AIエージェント版へ差し戻す。

### 運用影響

- 試合前まとめ / ライブ速報アンカー / 試合後結果の関係:
  同じ game_id を共有し、違いは subtype のみとする。`pregame` / `live_anchor` / `postgame` は WP 内 related で連鎖表示し、整合 NG は AIエージェント版 review で補正する。
- 同一試合の重複 Draft 防止方針:
  Draft 層では `(game_id, subtype)` を一意制約として扱い、既存 Draft があれば update を優先して新規作成しない。subtype 境界が揺れる場合は固定版レーンへ入れず、AIエージェント版へ差し戻す。
- source 追加時の追記方針:
  固定版レーンで自動反映するのは primary tier 追加のみとする。secondary tier は参照扱いで本文追記までに留め、rumor / unknown tier は A5 既定に従って AIエージェント版へ差し戻す。

### 実装

- 変更対象ファイル:
  設計上の新設候補は `src/game_id.py` と `src/game_state.py`。consumer wiring 時の参照点は `src/source_id.py`、`src/source_trust.py`、A7 `src/tag_category_guard.py` とし、この 012 では doc 固定のみでコード実装は行わない。
- テスト観点:
  `game_id` 採番の idempotency、`(game_id, subtype)` 一意制約、`pre / live / post` の単方向遷移、rumor / unknown tier の差し戻し、primary tier 追加の自動反映を実装便で検証対象にする。
- bounded 実装便の分解:
  便 A は `game_id` 採番モジュール単体、便 B は state 遷移モジュール単体、便 C は `(game_id, subtype)` 重複防止ガード、便 D は consumer wiring の順で分ける。各便は前便 commit 後に依存解消して fire する。

---

## TODO

### 識別子設計

【×】`game_id` の定義を決める  
【×】`source_id` の定義を決める  
【×】1 試合に紐づく記事群の束ね方を決める  

### 状態

【×】試合前 state を定義する  
【×】試合中 state を定義する  
【×】試合後 state を定義する  
【×】state 遷移条件を明記する  

### 運用影響

【×】試合前まとめ / ライブ速報アンカー / 試合後結果の関係を明記する  
【×】同一試合の重複 Draft 防止方針を明記する  
【×】source 追加時の追記方針を明記する  

### 実装

【×】変更対象ファイルを特定する  
【×】テスト観点を列挙する  
【×】bounded 実装便 1 本に落とせる粒度へ分解する  

---

## 成功条件

- `game_id` と `source_id` の役割が明確  
- 試合前 / 中 / 後の state が定義されている  
- Codex が bounded な実装便を起票・実装できる粒度になっている
