# 015 — Observation Ticket と受け入れ基準

**フェーズ：** 管理人の監視ルール固定  
**担当：** Claude Code  
**依存：** 010, 013, 014

---

## 概要

Claude Code が管理人として継続監視するための Observation Ticket と accept / reject ルールを固定する。
user を毎便介在させないための土台。
正本要件は `giants_agile_requirements` §7 / §8 / §9。親チケットは `doc/010` (`28d4968`) / `doc/011` (`4dc0b2b`) / `doc/012` (`d50a0dc`) / `doc/013` (`df77f6e`) / `doc/014` (`2d92405`)。
※ handoff docs は `/home/fwns6/code/baseballwordpress/docs/handoff/`

## 決定事項

### Observation Ticket

- `quality-monitor` 継続生成
  - Cloud Run / scheduler で `quality-monitor` job が継続生成され、直近 24h で新規監査エントリが 1 件以上あることを expected_behavior とする。
  - 連続失敗 3 回で Observation Ticket を起票し、7 日間新規生成 0 件なら user への最小判断 escalation に切り替える。

- `quality-gmail` の `[src:qm]` prefix 安定
  - `quality-gmail` は `quality-monitor` 由来メールを `[src:qm]` prefix で 24h 内に到達させ、別 src による prefix 逸脱を出さないことを expected_behavior とする。
  - prefix 変動なしが 48h 継続で安定扱いとし、変動検出時は Observation Ticket を起票する。

- subtype 境界の再発率監視
  - A4 `CORE_SUBTYPES` (`pregame / postgame / farm / fact_notice / live_anchor`) について、直近 20 本 Draft の誤判定件数と同一境界の連続誤判定数を signal とする。
  - 同一 subtype 境界の誤判定が 3 本連続で出た場合、または AIエージェント版 の差し戻し率が直近 20 本で 30% 超になった場合に起票する。

- 5 テンプレ崩れ監視
  - `doc/011` の固定版レーン対象 6 型（番組情報 / 公示 / 予告先発 / 野球データ / 二軍 / 定型試合前まとめ）ごとに、本文ブロック順崩れ率を signal とする。
  - A7 `tag_category_guard` の `TAG_TARGET_LOW` / `TAG_MAX` 範囲外発生率、および title template fallback 発生率のいずれかが 20% を超えたら起票する。

- `draft-body-editor` の `skip_reason` 傾向監視
  - `draft-body-editor` は直近 50 件の `skip_reason` 上位 3 件を継続把握し、新規カテゴリ出現を異常 signal とする。
  - 同一 `skip_reason` が 10 件連続で発生した場合も起票し、修正便候補の優先順位付けに使う。

### accept / reject

- accept 条件
  - doc 更新便は TODO の未完了記号が 0 件、必須語が本文に登場、対象 ticket の scope 内、最終報告 JSON の `todo_remaining: 0` を満たしたときに accept とする。
  - code 実装便は対象ファイルのみ変更、tests green、`quality-monitor` / `quality-gmail` / `draft-body-editor` を未 touch、automation / env / secret 未 touch を満たすことを条件にする。
  - commit 便は単一 file stage、push 無し、`Co-Authored-By` 無し、hook pass または hook なしを条件とし、AIエージェント版 Draft は `doc/013` の review 観点全通過と repair 後 fail pattern なしを要件に含める。

- reject 条件
  - 事実誤認、プライバシー、差別、著作権の疑義が 1 つでもある場合、または source が rumor / unknown tier のみの場合は reject とする。
  - 想定外の他ファイル diff、automation / env / secret への touch、TODO 残存、必須語欠落、scope 逸脱があれば reject とする。
  - commit 便で multi-file、push 済み、`Co-Authored-By` 付きのいずれかに該当した場合も reject とする。

- 次便起票の条件
  - accept 済み便には commit 便を紐付け、同一 scope に bounded な consumer wiring / テスト / wiring の後続便が残る場合は同時に起票する。
  - blocker を検出した場合は、原因仮説と次便 prompt を同時に起票し、`giants_agile_requirements` の「監査で止めない」前提に合わせて観測だけで終わらせない。
  - docs-only 便の次は必ず現場便へ落とし、Observation Ticket は read-only 観測便や smoke run 便への接続条件として使う。

### 既存ルール

- `go` を毎便 user に聞かないルールとの整合
  - publish ON ルートの平時運用では、postgame / lineup など既定方針内の便は Claude Code が `go` を user に都度聞かず進める。
  - docs-only / read-only / 可逆 / 既定方針内 / コスト増なしの便も同様に進行し、本 Observation Ticket は「事故検知時のみ user に最小判断を上げる境界値」を定義する。

- docs-only の次は現場便へ落とすルールとの整合
  - 本 `015` は docs-only 便のため、accept 後の次便は consumer wiring 実装 / `quality-monitor` 観測拡張 / smoke run などの bounded な現場便を必須とする。
  - 同一論点で docs-only / read-only が 1 便続いた時点で次便を現場便へ固定し、`doc/016` は全 ticket 終結の最終 docs-only 便としてのみ例外扱いにする。

---

## TODO

### Observation Ticket

【×】`quality-monitor` 継続生成の監視項目を定義する  
【×】`quality-gmail` が `[src:qm]` で安定する監視項目を定義する  
【×】subtype 境界の再発率監視項目を定義する  
【×】5 テンプレの崩れ有無の監視項目を定義する  
【×】draft-body-editor の skip_reason 傾向監視項目を定義する  

### accept / reject

【×】Claude Code の accept 条件を列挙する  
【×】Claude Code の reject 条件を列挙する  
【×】次便起票の条件を列挙する  

### 既存ルール

【×】`go` を毎便 user に聞かないルールとの整合を明記する  
【×】docs-only の次は現場便へ落とすルールとの整合を明記する  

---

## 成功条件

- Claude Code が見る Observation Ticket が一覧化されている  
- accept / reject / 次便起票の条件が明文化されている  
- user を日常 relay から外す運用に使える
