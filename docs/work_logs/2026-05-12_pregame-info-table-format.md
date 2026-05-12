# 2026-05-12 pregame info table-format rendering

> **チケット種別**: 別ticket(`2026-05-12_hochi-fresh-pregame-backlog-publish-policy.md` とは独立。あちらは公開ゲートの修正、こちらは本文の描画形式)
> **現状ステータス**: SPEC ONLY / NOT YET IMPLEMENTED
> **本commitで許可される変更**: 本Markdown作成のみ。コード編集 / commit / push / deploy / env / scheduler 変更は禁止

## 1. 今回の目的

- 試合前情報の本文(スタメン / 予告先発 / 開幕投手 / ベンチ控え / 公示 等)を **HTML 表形式 `<table>` で描画**し、視認性と情報密度を高める。
- 巨人特化メディアとして、のもとけ級の structured presentation を試合前情報に揃える。
- 文章プロセ形式や箇条書きでは読み取りづらかった「打順 / 守備位置 / 選手名」「先発予告(投手名 / 防御率)」「公示(登録 / 抹消 / 入替日)」を 1 表で見せる。
- 対象 subtype:
  - `lineup`(スタメン表 + ベンチ控え表)
  - `probable_starter`(予告先発表)
  - `pregame`(試合前情報の構造化部分)
  - `farm_lineup`(二軍スタメン表)
  - `roster`(公示一覧表)
- 対象 subtype の本文に表が組めない場合(情報不足 / fact不足)は、従来の prose 描画に fallback する(silent skip しない)。
- HTML は WordPress 公開記事の本文に直接含める(plugin / shortcode 経由ではなく、生 `<table>` で classes 付き)。

## 2. 今回触る範囲

- 本文 renderer / body composition 層(例: `src/article_body_renderer.py` 相当、または `rss_fetcher.py` 内の body composition path)
  - 各 subtype ごとに table builder を追加(`_render_lineup_table`, `_render_probable_starter_table`, `_render_roster_table` 等)
  - 既存の prose / bullet block を表 block に差し替え、または前段に挿入
- 必要なら fact 抽出 / structured field の保持
  - 既存の lineup deduplication / source priority logic から、batting_order / position / player_name / pitcher_era 等の structured field を retain して renderer に渡す
- frontend CSS(必要なら最小限)
  - `yoshilover-063-frontend` 側、または theme custom.css に `.yoshilover-pregame-table` 用のレスポンシブ table style
  - mobile narrow viewport で table が崩れないスクロール / 折り返し対応
- 関連テスト
  - renderer 単体テスト(各 subtype の HTML output snapshot)
  - structured field 欠損時の prose fallback 確認テスト
- 本Markdown(本作業記録)

## 3. 今回触らない範囲

- **`guarded-publish` 公開ゲート / backlog narrow 判定**(別 ticket `hochi-fresh-pregame-backlog-publish-policy` で扱う)
- evaluator のフラグ判定 / freshness threshold
- RSS source 追加 / 削除 / URL 変更
- `config/rss_sources.json`
- Cloud Run env / Secret / Scheduler / GitHub Actions
- Cloud Run deploy
- publish / mail 全体条件
- X 投稿 / X カード描画
- アイキャッチ選定 / featured media
- 公開済み既存記事の retrofit(本 ticket は新規生成記事のみ対象、既存記事の rerender は別便)
- 試合後系 subtype(`postgame` / `game_result` / `farm_result`)
- 監督・選手コメント `comment`(試合前後問わず prose 維持、表化対象外)
- 怪我情報 `injury`(prose 維持、表化対象外)
- お知らせ `notice`(prose 維持、表化対象外)
- AdSense slot / sidebar widgets / sticky scroll behavior
- 既存 H3 / H2 構造の根本変更(別 ticket `H3-STRUCTURE-UNIFY-2026-05-08` で扱う)
- unrelated dirty files / logs / build artifacts
- Gemini prompt の自由生成圧力(表 HTML の生成は LLM ではなく renderer 側で deterministic に組む)

## 4. 影響範囲

- 新規生成される `lineup` / `probable_starter` / `pregame` / `farm_lineup` / `roster` 記事の本文 HTML
- WordPress 公開時の article body
- フロント側 article 表示(theme CSS が table style を保つかに依存)
- 影響しない想定:
  - publish 判定の通る / 通らない
  - RSS 取得件数
  - メール通知 / publish-notice
  - X 投稿
  - 既存 publish 済記事(retrofit しない)
  - SEO 評価軸(現フェーズは noindex 検証中、SEO は対象外)
- 望ましい影響:
  - スタメン / 予告先発 / 公示の情報が一目で把握できる
  - のもとけ比の情報密度向上
  - モバイル / PC 両方で読みやすい table 表示

## 5. 実行予定テスト

- renderer 単体:
  - `_render_lineup_table`: 9 打順 + 守備位置 + 選手名 が table HTML として出力される
  - `_render_lineup_table`: ベンチ控え section が含まれる(rows 数任意)
  - `_render_probable_starter_table`: 投手名 + 利き腕 + 防御率 を含む 1 行 table
  - `_render_roster_table`: 登録 / 抹消 / 入替日 列を含む table
  - `_render_farm_lineup_table`: 一軍 lineup と同形式 (9 打順) で表示
- structured field 欠損時:
  - lineup で打順情報が取れない → prose fallback、`<table>` を生成しない、warning log のみ
  - probable_starter で防御率欠損 → `<table>` 内で「-」placeholder、行は維持
- HTML 妥当性:
  - 生成 HTML が WordPress block editor に取り込まれて壊れない(`<table>` `<thead>` `<tbody>` `<tr>` `<td>` のみ、JS や style 属性なし)
  - class 名(例 `yoshilover-pregame-table`)が固定
- regression:
  - 既存の prose body 生成 path は subtype が対象外の場合に変化しない
  - 既存 snapshot test が green を保つか、必要なら snapshot を一斉更新(意図変更を明示)
- 関連テスト:
  - `python3 -m unittest tests.test_<renderer module>`
  - `python3 -m unittest tests.test_rss_fetcher` 等で body composition path が壊れていないことを確認
- 全件:
  - `python3 -m unittest discover -s tests`

## 6. STOP条件

- structured field が安全に抽出できず、推測で組み立てる必要がある場合(打順情報 / 投手情報 / 公示情報が freeform text にしかない場合)
- HTML `<table>` を含む本文が WordPress REST API 経由で正しく保存できない場合
- mobile viewport で table が壊れる、テーマ CSS で意図せず非表示になる場合
- 既存 prose 描画 path に副作用が出て、対象外 subtype まで影響する場合
- Gemini prompt 経由で table HTML を生成しないと回らない設計になった場合(deterministic renderer で組めない場合)
- 全件テストが赤で、今回差分との関係を切り分けられない場合
- env / Scheduler / Cloud Run / deploy 変更が必要になった場合
- 公開済み既存記事の retrofit に scope が広がった場合

## 7. 禁止事項

- 記憶から再構成しない
- silent skip しない
- 自己評価 OK で済ませない
- `git add -A` しない
- Gemini / LLM に table HTML を生成させない(deterministic に renderer 側で組む)
- HTML に inline `style` 属性 / JS / `<script>` を入れない
- 公開済み記事を遡って書き換えない
- 試合後系 subtype に拡大しない
- comment / injury / notice を表化しない(prose 維持)
- env / Scheduler / Cloud Run 変更を本便に混ぜない
- source 追加・削除を本便に混ぜない
- 別 ticket `hochi-fresh-pregame-backlog-publish-policy` の差分と本便を 1 commit に混ぜない(必ず別 commit)
- AdSense / sidebar / H3 統一など他 ticket の scope を引き込まない
- 表 fallback 失敗を warning log で済ませず、prose で必ず描画する

## 8. 想定されるデグレ

- table HTML がテーマ CSS と衝突して画面崩れ
- mobile narrow viewport で table が overflow し、横スクロール / 折り返しが効かない
- 公開済み prose 記事と新規 table 記事の混在で読者に違和感が出る(retrofit はしないため恒久的に併存)
- structured field 抽出ロジックが既存の prose 抽出と分岐し、片方しか更新されないことで long-term の整合が壊れる
- 同話題重複検出が table 化前後で representative text が変わり、duplicate guard が誤動作
- snapshot test の更新で意図と異なる変更を見落とす
- table 中身に Player 名の同姓誤マッチが入り、`23fa8d5` (related_player same-surname guard) の保護が間接的に弱まる
- ベンチ控え 7-8 名の長い行が table に入ると、モバイルで縦に長くなりすぎる

## 9. 作業ログ欄

### 2026-05-12 PM(spec only、本 Markdown 作成のみ)

- user 指示: 試合前情報(スタメン / 開幕投手 / ベンチ控え 等)を全て表形式 (`<table>`) で描画したい
- 本 Markdown を作成し、scope / 触らない範囲 / テスト / STOP / 禁止事項 / 想定デグレを定義
- コード編集 / commit / push / deploy / env / scheduler 変更は本 commit で禁止
- 実装は user GO 後、別便で着手

### 2026-05-12 PM 追加(investigation 結果 → scope 再判定要、user 指示で本 session 着手なし)

- **重要発見**: `src/nomotoke_card_renderer.py`(2415 行)に **table renderer が既に実装済み**
  - `_render_lineup_table` / `_render_inning_table` / `_render_atbat_table` / `_render_pitching_table` / `_render_broadcast_table` / `_render_stats_table`
  - public renderer: `render_lineup_card` / `render_postgame_card` / `render_official_notice_card` / `render_pregame_pitcher_card`
  - 11 個の `TEMPLATE_KEY_*` 定数(`LINEUP` / `POSTGAME` / `PREGAME_PITCHER` / `OFFICIAL_NOTICE` / `BROADCAST` / `LIVE_AT_BATS` / `PLAYER_STATS` / `MANAGER_COMMENT` / `PLAYER_COMMENT` / `VIDEO` / `SHORT_NEWS_URL`)
- 起動経路: `src/tools/manual_intake.py` / `src/tools/run_postgame_from_yahoo.py` / `src/tools/run_broadcast_from_yahoo.py` / `src/tools/run_player_stats_from_npb.py` 等から `select_renderer(template_key)` 経由で呼び出し
- 既存 ticket `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08` と関連: 装飾 enrichment は body の `class="nomotoke-card-"` marker gate に依存、RSS auto path は marker 付与なしで装飾 skip、配管(`927ac2c`)はあるが marker 経路未統合
- つまり本 ticket の実体は「新規にゼロから table renderer を作る」ではなく「既存 nomotoke renderer を auto-publish の特定 subtype で起動する wiring」になる可能性が高い
- **user 判断(2026-05-12 PM)**: 「既存はやらなくていい」→ 本 ticket は本 session で実装しない。spec は本 Markdown に保持、後日再開する場合は以下を必ず再判定:
  1. 本 ticket と `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08` の重複を整理(別 ticket として並走 / 一つに統合 / どちらか close のいずれか)
  2. scope を「新規 renderer 作成」から「既存 renderer の wiring 完成」に書き直すかどうかを再決定
  3. 「§3 触らない範囲」と「§4 影響範囲」を新 scope に合わせて改訂

(以降、再着手時にここへ append)

## 10. Regression Memo欄

- これは公開ゲートの問題ではない(別 ticket で扱う)
- これは RSS 取得 / mail 通知 / X 投稿の問題でもない
- 表形式化は **新規生成記事のみ**対象、公開済み記事は触らない
- 表データに欠損があるときは prose fallback で必ず描画(silent skip 禁止)
- LLM に HTML を組ませない(deterministic renderer で組む、prompt drift 防止)
- 関連 ticket:
  - `2026-05-12_hochi-fresh-pregame-backlog-publish-policy.md`(公開ゲート、別便)
  - `H3-STRUCTURE-UNIFY-2026-05-08`(H3 構造統一、別便)
  - `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08`(手動 vs 自動の品質差、別便)
  - `FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08`(enrichment 装飾の live audit、別便)

---

## 作業後追記欄

> **本 commit では作業後追記欄は空のまま**。user GO 後の実装便で埋める。

### 1. 実際に変更したファイル

(未実装)

### 2. diff概要

(未実装)

### 3. 実行したテスト

(未実装)

### 4. テスト結果

(未実装)

### 5. 残った懸念

(未実装)

### 6. 新しく見つかったデグレ

(未実装)

### 7. 追加した回帰テスト

(未実装)

### 8. 次回触ってはいけない範囲

(未実装)
