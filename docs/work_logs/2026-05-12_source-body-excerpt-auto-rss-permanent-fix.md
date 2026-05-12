# 2026-05-12 source body excerpt 自動RSS恒久対応

## 1. 今回の目的

- 自動 RSS path(報知/日刊スポーツ/スポニチ/デイリー/サンスポ等の `source_type=news / tag_scrape`)で生成される draft / publish 記事に、元記事本文からの 600 字 literal 抜粋ブロックを **新規挿入** する。
- 既存の `src/tools/manual_intake.py` 側にしかない `_maybe_insert_source_body_excerpt` 相当の挿入路を、`src/rss_fetcher.py` の自動取り込み path にも適用する。
- 過去の polluted excerpt(近隣記事/別記事の文章混入)の再発を防ぐため、context match guard(`ef5fe7b` 由来の `_source_excerpt_matches_context`)も新経路に適用する。ただし guard 本体は今回触らない、新経路への移植のみ。
- 600 字 cap は manual_intake と同じ `SOURCE_BODY_EXCERPT_MAX_CHARS = 600` を共有。
- 対象は **今後の自動生成記事のみ**。過去 publish の WP 記事は触らない。
- 事実確認:
  - 直近 publish 30 件中、`class="nomotoke-source-excerpt"` block を含むのは 1 件のみ(29/30 で missing)。
  - `src/rss_fetcher.py` の git history 全期間で `_maybe_insert_source_body_excerpt` / `extract_article_body_excerpt` / `nomotoke-source-excerpt` を含む commit がゼロ → 自動 RSS path には最初から実装されていない gap。
  - manual_intake 側は 5/11 22:07 の `ef5fe7b` で guard が追加され、context match で reject されるケースが発生中。

## 2. 今回触る範囲

- `src/rss_fetcher.py`
  - 自動 RSS の draft / publish 直前の `content_html` 組み立て位置に、`_maybe_insert_source_body_excerpt` 相当の呼び出しを追加。
  - `_article_raw_html` を既に fetch 済の `source_type in {"news", "tag_scrape"}` で適用。
- `src/tools/manual_intake.py`
  - 既存関数(`_maybe_insert_source_body_excerpt` / `_source_excerpt_matches_context` / `_insert_body_excerpt_block` / `_source_excerpt_context_terms` / `_compact_source_excerpt_context` / `SOURCE_BODY_EXCERPT_MAX_CHARS`)を **import 経由で再利用**。関数本体は今回触らない。
  - もし import 循環や視認性で都合悪い場合のみ、関数を `src/source_article_body_extractor.py` 側に移して両者から呼ぶ最小リファクタを検討。リファクタする場合も挙動は同一を保証。
- `src/source_article_body_extractor.py`
  - `extract_article_body_excerpt` は本体変更なし(再利用のみ)。
- 関連テスト
  - `tests/test_rss_fetcher_*.py`(新規追加 + 既存影響確認)
  - `tests/test_source_article_body_extractor.py`(回帰)
  - `tests/test_manual_intake*.py`(回帰)
- 作業ログ Markdown(本ファイル)

## 3. 今回触らない範囲

- 公開済み WP 記事の本文 / title / status / featured_media / excerpt の修正(過去記事は一切触らない)
- WP 管理画面操作
- env / Secret / Scheduler / Cloud Run 設定
- publish / mail / X 投稿 gate
- フロント / CSS / theme / Plugin / AdSense
- アイキャッチ関連の path(今日別作業で完了済)
- source 追加、DAZN / 日テレ / 試合中ソース制御
- LLM (Gemini) prompt の構造変更 / source_body 渡し方
- `ef5fe7b` の `_source_excerpt_matches_context` guard 本体ロジック(緩和は別 ticket、今回は移植のみ)
- `SOURCE_BODY_EXCERPT_MAX_CHARS` の数値変更
- manual_intake 側の挙動変更
- `nomotoke-source-excerpt` block の HTML / CSS 構造変更
- social_news(X tweet source)経路への適用 ※ 主対象外、別 ticket
- 個別媒体名の blacklist / whitelist 拡張
- unrelated dirty files / logs / data / build artifacts

## 4. 影響範囲

- 今後の自動 RSS draft / publish の本文に `<aside class="nomotoke-source-excerpt">…</aside>` block が新規挿入される。
- 影響対象カテゴリ: `source_type=news` または `source_type=tag_scrape` で `_article_raw_html` を取得済の record。
- 影響媒体: hochi.news / www.nikkansports.com / www.sponichi.co.jp / www.daily.co.jp / www.sanspo.com など news_publisher。
- 望ましい影響:
  - 報知/日刊/sponichi 等の自動 draft で本文に 600 字 literal 抜粋 + 出典が入る。
  - user の手入力負担(毎回 paste)が消える。
  - 「他の記事のも載せてた」polluted excerpt は guard で reject される(これは manual_intake と同じ挙動を新経路にも適用)。
- 潜在的な副作用:
  - 本文長が +500-600 字、見た目変化(noindex 期間中は SEO 影響無視可)。
  - 既存 `nomotoke-source-excerpt` class が site theme 側で対応済かは要確認。
  - context match で reject されるケースは block 挿入なし(現状と同じく excerpt block 0 字)、改善しないケースは残る。
  - block 挿入位置が既存の source 出典ブロックと近接した場合、見た目が並ぶ可能性。

## 5. 実行予定テスト

- 赤確認(red-first):
  - 自動 RSS path の draft 生成で、`source_type=news` + 該当記事 HTML あり + title マッチする excerpt が抽出される条件で、現コードでは `nomotoke-source-excerpt` block が挿入されないことを確認するテストを書き、修正前は赤で確認。
- 追加テスト:
  - hochi 記事 HTML + title マッチ excerpt → block 挿入される
  - hochi 記事 HTML + title 不一致(別記事文混入)excerpt → block 挿入されない(guard 動作)
  - source_type=social_news → block 挿入されない(scope 外維持)
  - 既に excerpt block が混入していたら重複挿入しない(idempotent)
  - 600 字を超える本文は 600 字で切られる
  - raw_html が空 / 取得失敗のとき block 挿入なし
- 関連テスト:
  - `python3 -m unittest tests.test_rss_fetcher_body_contract_fail_ledger`
  - `python3 -m unittest tests.test_source_article_body_extractor`
  - `python3 -m unittest tests.test_manual_intake`(回帰なし確認)
  - `python3 -m unittest tests.test_featured_media_helpers tests.test_featured_media_fallback`(unrelated path に影響しないこと確認)
- 全件:
  - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 公開済み記事の修正(本文 / featured_media / status / title)が必要になったら停止
- env / Secret / Scheduler / Cloud Run 設定変更が必要になったら停止
- ef5fe7b の `_source_excerpt_matches_context` guard 本体ロジック変更が必要になったら停止(別 ticket)
- `SOURCE_BODY_EXCERPT_MAX_CHARS` の数値変更が必要になったら停止
- LLM (Gemini) prompt 構造変更が必要になったら停止
- publish flow の publish_status / featured_media 等他要素を巻き込む必要が出たら停止
- 全件 suite が今回差分起因で赤になり、原因が今回差分以外と切り分けられない場合は停止
- 自動側 `_maybe_insert_source_body_excerpt` 適用で manual_intake 側に副作用が出る場合は停止
- import 循環 / 再利用設計で manual_intake の関数本体を変えないと成立しない設計が必要になった場合は停止し、再設計 → user 再確認

## 7. 禁止事項

- 記憶から再構成しない
- silent skip しない
- 自己評価 OK で済ませない
- `git add -A` しない
- 指示外のファイルを触らない
- 公開済み WP 記事を直さない
- source 追加やソース方針変更に広げない
- アイキャッチ系を巻き込まない
- title / publish gate / LLM prompt をついで修正しない
- 個別媒体名の blacklist / whitelist だけで済ませない
- `ef5fe7b` の guard 本体ロジックを今回緩めない / 強めない
- 過去 publish 記事の文字数 / 本文を上書きする処理を実装しない
- env / scheduler / secret / Cloud Run 設定の変更を伴う実装をしない

## 8. 想定されるデグレ

- context match guard で過剰 reject → 本来挿入されるべき excerpt が出ない(現状と同じ reject 挙動を引き継ぐので新規デグレではないが、改善もしない)
- block 挿入で本文長が +500-600 字、CSS / レイアウト崩れ(theme 側未対応の場合)
- block 挿入位置によっては既存 source 出典 / 関連リンクブロックと並走 / 重複
- 重複挿入防止 idempotent 判定が漏れて 2 回挿入される可能性
- 自動 path で raw_html が大きく fetch コストが想定外に増える(`_article_raw_html` 既取得済を再利用するため通常は増加しない想定)
- social_news 経路で意図せず block 挿入(scope 外と早期 return 必須)
- `extract_article_body_excerpt` が `_article_raw_html` から空文字を返した時に block 挿入されないのは設計通り
- import 構造変更で manual_intake 側の動作が壊れる

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-12 17:35 JST | 作業記録 Markdown 作成、user GO 待ち | 本ファイル作成のみ実施、code は一切触らず |

## 10. Regression Memo欄

- これは「アイキャッチ」「title」「LLM 本文生成」とは独立した「源 literal 抜粋ブロック」問題。
- root cause: `_maybe_insert_source_body_excerpt` が `src/tools/manual_intake.py` のみで呼ばれ、`src/rss_fetcher.py` の自動 path には実装されていない gap。
- 過去の polluted excerpt(他記事混入)は ef5fe7b で guard 追加された。過剰 reject も発生中だが、本 ticket では guard 本体は触らない、新経路への移植のみ。
- 600 字 cap 自体は manual_intake 既設の `SOURCE_BODY_EXCERPT_MAX_CHARS=600` を再利用。
- 今後の自動 draft で literal block が出ることが期待、過去 record は触らない(user 方針)。
- 関連 ticket / commit:
  - 8cfe494 (5/10) `312-QA: raise manual excerpt cap to 600` ← manual のみ 360→600
  - 66c1442 (5/10) `312-QA: expand manual intake source excerpts`
  - 7d342bc (5/11) `314 315: expand source excerpts and media extraction`
  - 0f47c5f (5/11) `fix: fetch source excerpt for social article urls`
  - d5e40a2 / 68a4c84 (5/11) `fix: clean source body excerpts`
  - 24cd9cb / 9797462 (5/11) `fix: guard source excerpt context`
  - 1743c70 / f876c7c (5/11) `test: cover source excerpt context drift`
  - ef5fe7b (5/11 22:07) `fix: guard source excerpts against polluted summaries` ← title terms only に絞り込み
- 同経路の social_news 適用 / guard 緩和は別 ticket で扱う。

## 作業後追記欄

(GO 後の作業完了時に以下を追記)

### 1. 実際に変更したファイル

### 2. diff概要

### 3. 実行したテスト

### 4. テスト結果

### 5. 残った懸念

### 6. 新しく見つかったデグレ

### 7. 追加した回帰テスト

### 8. 次回触ってはいけない範囲
