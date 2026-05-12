# 2026-05-12 eyecatch source article image regression

## 1. 今回の目的

- post-deploy 品質確認で見つかったアイキャッチ異常を恒久的に止める。
- 対象は、報知などの記事ページ由来の記事で、該当記事の画像ではなく別記事・別媒体の画像が `featured_media` に流用される問題。
- 公開済み記事は直さず、今後の自動生成で同じ種類のアイキャッチを付けないようにする。
- 事実確認:
  - `post_id=66409 / 66407 / 66405 / 66403 / 66401 / 66390` は全て `featured_media=66041`。
  - `66041` は日刊スポーツの大城卓三ヘルメット直撃記事の画像。
  - Cloud Run logs で、報知記事 `https://hochi.news/articles/20260511-OHT1T51276.html` 等に対して `candidate_url=https://www.nikkansports.com/baseball/news/img/202605100001243-w500_0.jpg` が渡っていた。
  - 同じ報知記事ページを直接確認すると、該当 `og:image` は `https://hochi.news/images/2026/05/11/20260511-OHT1I51491-L.jpg` だった。
- 恒久対応:
  - `source_type=news/tag_scrape` は、entry summary 内のリンク画像ではなく、該当記事HTMLの `og:image` / 本文メイン画像を先に使う。
  - `social_news` の X 添付画像抽出は今回触らない。

## 2. 今回触る範囲

- `src/rss_fetcher.py`
  - `news/tag_scrape` の画像候補選択。
  - 該当記事HTMLから画像を確定する経路。
- 関連テスト
  - `tests/test_featured_media_helpers.py`
- 本作業記録 Markdown。

## 3. 今回触らない範囲

- 公開済み WP 記事本文 / title / status / featured_media の修正。
- WP 管理画面操作。
- env / Secret / Scheduler / Cloud Run 設定。
- publish / mail gate。
- X 投稿。
- source 追加、DAZN / 日テレ / 試合中ソース制御。
- アイキャッチ fallback media ID の env 変更。
- X / social_news の添付画像抽出ルール。
- frontend / CSS / AdSense。
- unrelated dirty files / logs / data / build artifacts。

## 4. 影響範囲

- RSS fetcher の記事作成時に設定される `featured_media`。
- 特に `source_type=news/tag_scrape` の記事ページ画像。
- 望ましい影響:
  - 報知記事は報知記事ページの `og:image` を使う。
  - 日刊記事は日刊記事ページの `og:image` を使う。
  - entry summary に別記事URLが混ざっても、それをアイキャッチ候補にしない。
  - 画像が使えない場合は既存ルールどおり fallback 側に流す。
- 注意:
  - 「画像がついていれば画像、何もなければ東京ドーム」という基本方針は壊さない。
  - 紙面スキャン・紙面告知でも、それが該当記事の画像なら今回の修正対象外。

## 5. 実行予定テスト

- 赤確認:
  - `tag_scrape` で entry summary に別媒体記事URLが混ざると、現状は別媒体画像を拾えることを再現する。
- 追加テスト:
  - `tag_scrape` は entry summary 内のリンク画像より、該当記事HTMLの `og:image` を優先する。
  - 該当記事HTMLの画像が取れた場合、別記事リンクの画像取得を呼ばない。
- 関連テスト:
  - `python3 -m unittest tests.test_featured_media_helpers`
  - `python3 -m unittest tests.test_yahoo_realtime.ArticleImageFetchTests`
  - `python3 -m unittest tests.test_featured_media_fallback`
- 全件:
  - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 公開済み記事の修正が必要になったら停止。
- env / Secret / Scheduler / Cloud Run 設定変更が必要になったら停止。
- `social_news` / X 添付画像ルール変更が必要になったら停止。
- 画像の内容判定へ広がりそうなら停止。
- 既存テスト全件が赤で、原因が今回差分以外と切り分けられない場合は停止。
- `410a101 fix: apply game live source policy` を deploy に混ぜる必要が出たら停止。

## 7. 禁止事項

- 記憶から再構成しない。
- silent skip しない。
- 自己評価 OK で済ませない。
- `git add -A` しない。
- 指示外のファイルを触らない。
- 公開済み WP 記事を直さない。
- source 追加やソース方針変更に広げない。
- アイキャッチ以外の title / 本文 / publish gate をついで修正しない。
- 個別媒体名の blacklist だけで済ませない。

## 8. 想定されるデグレ

- `tag_scrape` の entry summary にしか画像手がかりがない記事では fallback になる可能性。
- ただし `tag_scrape` は記事HTMLを取得する設計なので、該当記事HTMLの `og:image` を優先する方が正しい。
- `social_news` の X 添付画像抽出は今回触らないため、X画像取得の既存挙動は維持する想定。

## 9. 作業ログ欄

- 2026-05-12 JST:
  - user 指摘: デグレは本文タイトルではなくアイキャッチ。
  - `post_id=66409 / 66407 / 66405 / 66403 / 66401 / 66390` が同じ `featured_media=66041` を共有していることを WP REST で確認。
  - `66041` は日刊スポーツの大城卓三ヘルメット直撃記事画像と確認。
  - Cloud Run logs で、報知記事URLに日刊スポーツ画像URLが `candidate_url` として渡っていたことを確認。
  - 対象報知記事HTMLを直接取得し、該当 `og:image` が報知ドメインに存在することを確認。
  - user 指摘により、紙面スキャンそのものは今回の修正対象ではなく、「該当記事のアイキャッチを拾う」ことが正しい仕様と再整理。
  - 再現テスト赤: `tests.test_featured_media_helpers.FeaturedMediaHelperTests.test_tag_scrape_prefers_source_article_html_image_over_entry_linked_image` が未実装 helper で赤。
  - 修正: `news/tag_scrape` の画像候補は該当記事HTMLから抽出する経路へ集約。
  - 追加テスト緑、関連テスト緑、全件回帰テスト緑を確認。

## 10. Regression Memo欄

- これは「元ポストの絵文字装飾をシステムが作った」問題ではない。
- これは「紙面スキャンを出す/出さない」の問題でもない。
- 問題は、報知記事に対して日刊スポーツの別記事画像が `featured_media` として流用されたこと。
- 既存方針の正しい解釈:
  - 元記事URLを見る。
  - そのサイトの該当記事の `og:image` / メイン画像を拾う。
  - それをアイキャッチにする。
  - なければ fallback。
- 修正は X 画像抽出や紙面画像判定ではなく、`news/tag_scrape` の画像候補を該当記事HTMLに固定すること。
- `social_news` title / 本文品質問題とは別タスク。今回は featured_media の候補選択だけを見る。

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_featured_media_helpers.py`
- `docs/work_logs/2026-05-12_eyecatch-social-paper-image-regression.md`

### 2. diff概要

- `src/rss_fetcher.py`
  - `_extract_source_article_image_urls()` を追加。
  - `news/tag_scrape` は entry summary のリンク画像ではなく、該当記事HTMLの画像抽出結果を使うように変更。
  - `social_news` は従来どおり entry 側の画像候補を使い、なければ article HTML に fallback。
- `tests/test_featured_media_helpers.py`
  - `tag_scrape` で別媒体記事URLが summary に混ざっていても、該当記事HTMLの `og:image` を優先する回帰テストを追加。

### 3. 実行したテスト

- `python3 -m unittest tests.test_featured_media_helpers.FeaturedMediaHelperTests.test_tag_scrape_prefers_source_article_html_image_over_entry_linked_image`
- `python3 -m unittest tests.test_featured_media_helpers`
- `python3 -m unittest tests.test_yahoo_realtime.ArticleImageFetchTests`
- `python3 -m unittest tests.test_featured_media_fallback`
- `python3 -m unittest discover -s tests`
- `python3 -m unittest discover -s tests` を sandbox socket 制限回避のため権限付きで再実行

### 4. テスト結果

- 追加テスト:
  - 初回赤: helper 未実装で `AttributeError`
  - 修正後緑: `Ran 1 test ... OK`
- 関連テスト:
  - `tests.test_featured_media_helpers`: `Ran 9 tests ... OK`
  - `tests.test_yahoo_realtime.ArticleImageFetchTests`: `Ran 4 tests ... OK`
  - `tests.test_featured_media_fallback`: `Ran 6 tests ... OK`
- 全件回帰テスト:
  - sandbox 内初回: `3438 tests` 中、ローカル socket 作成制限で `test_manual_intake_service.LiveServerSmokeTest` 3件が `PermissionError`
  - 権限付き再実行: `Ran 3438 tests in 81.174s OK`

### 5. 残った懸念

- 公開済み記事の `featured_media` は user 指示どおり未修正。
- 今回は deploy 未実施。

### 6. 新しく見つかったデグレ

- なし。

### 7. 追加した回帰テスト

- `test_tag_scrape_prefers_source_article_html_image_over_entry_linked_image`
  - 報知 tag scrape 記事の entry summary に日刊スポーツ記事URLが混ざっても、報知記事HTMLの `og:image` を使うことを固定。
  - 該当記事HTMLの画像がある場合、別記事リンク画像の fetch を呼ばないことを固定。

### 8. 次回触ってはいけない範囲

- 公開済み WP 記事本文 / title / status / featured_media。
- env / Secret / Scheduler / Cloud Run 設定。
- source 追加、DAZN / 日テレ / 試合中ソース制御。
- X / social_news 添付画像抽出ルール。
- publish / mail gate。
- frontend / CSS / AdSense。
