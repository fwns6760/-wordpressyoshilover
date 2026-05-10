# 315-QA source featured media site extraction

## 1. 今回の目的

報知など Web 元記事に source 画像がある場合は、その画像をアイキャッチ候補として使えるようにする。

方針は固定する。

- source eyecatch を最優先する
- source 画像が取れない時だけ東京ドーム fallback に落とす
- generic SNS 画像、ロゴ、バナー、広告画像は使わない
- unrelated 既存 media や legacy Ichiro mixed media に戻さない
- 画像が取れなくても記事生成は止めない

## 2. 今回触る範囲

- `src/rss_fetcher.py`
- 必要なら `src/tag_page_scraper.py`
- 必要なら `src/player_eyecatch_resolver.py`
- `tests/test_featured_media_fallback.py`
- `tests/test_featured_media_helpers.py`
- 必要なら `tests/test_tag_page_scraper.py`
- 本 ticket 自身 `doc/waiting/315-QA-source-featured-media-site-extraction.md`

## 3. 今回触らない範囲

- publish
- mail
- scheduler
- env
- secrets
- Cloud Run 設定
- GitHub Actions
- SEO / schema
- 本文生成ロジック
- source 本文 excerpt ロジック
- Instagram 取り込み
- X 自動投稿
- WordPress 本番記事の手動修正
- WP media の手動 upload / 削除
- 指示外の source 追加
- `doc/README.md`
- `doc/active/assignments.md`

## 4. 影響範囲

- RSS / tag_scrape / social_news 経路の featured_media 候補選定
- source article の `og:image` / `twitter:image` / article image 抽出
- WP media upload / existing media reuse の入口
- 東京ドーム fallback の発動頻度
- 一覧・記事ページで表示されるアイキャッチの関連性

本線への影響はアイキャッチ候補選定に限定する。publish / mail / scheduler / env / Cloud Run 設定には直接影響させない。

## 5. 実行予定テスト

追加する再現テスト:

- 報知 tag_scrape 経路で、記事ページに `og:image` がある時は東京ドーム fallback ではなく source 画像候補を使う
- 報知の `hochi_news_sns` generic 画像は引き続き skip する
- Full-Count の `/wp-content/uploads/...` 画像を `ad` 誤判定で除外しない
- BaseballKing の `/wp-content/uploads/...` 画像を `ad` 誤判定で除外しない
- 日刊スポーツの source 画像 upload 成功パターンを壊さない
- デイリー / スポニチの `og:image` 候補を壊さない
- source 画像が全く無い場合だけ東京ドーム fallback になる
- legacy Ichiro mixed media `36062` が fallback として復活しない
- generic SNS / logo / banner / ad image は featured_media にしない
- image candidate が 0 の時でも記事生成は止めない

実行順:

1. 追加再現テストだけ実行して赤確認
2. コード修正
3. 追加再現テストを再実行して green 確認
4. 関連テスト実行
   - `python3 -m unittest tests.test_featured_media_fallback`
   - `python3 -m unittest tests.test_featured_media_helpers`
   - 必要なら `python3 -m unittest tests.test_tag_page_scraper`
   - 必要なら `python3 -m unittest tests.test_player_eyecatch_resolver`
5. 可能なら既存テスト全件
   - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 追加再現テストの赤確認ができない
- source 画像ではなく unrelated 既存 media を使う方向になる
- generic SNS 画像、ロゴ、バナー、広告画像をアイキャッチにするしかない
- source 画像が無い記事を止める必要が出る
- legacy Ichiro mixed media `36062` が復活する
- publish / mail / scheduler / env / secrets / Cloud Run 設定を触る必要が出る
- WP media の手動 upload / 削除が必要になる
- `python3 -m unittest discover -s tests` が通らない
- 既存のユーザー未コミット差分を戻す必要が出る

## 7. 禁止事項

- source と無関係な画像を選ぶ
- generic SNS 画像を記事アイキャッチにする
- ロゴ、バナー、広告、トラッキング画像をアイキャッチにする
- fallback を東京ドーム以外へ勝手に変更する
- WP media を手動で upload / 削除する
- publish / mail / scheduler / env / secrets / Cloud Run 設定に触る
- ついで修正をする
- `git add -A` を使う
- diff 提示前に commit する
- テスト未実行で commit / push / deploy する

## 8. 想定されるデグレ

- 広告除外条件を緩めすぎて広告画像が混ざる
- source 画像候補の重複排除が弱まり、WP media upload が増える
- generic SNS 画像を skip できなくなる
- source 画像候補 0 の記事で fallback が出なくなる
- 日刊スポーツなど既に source 画像 upload できている媒体を壊す
- 報知 tag_scrape で記事ページ再取得が増え、runtime が伸びる
- 画像候補ログが不足して原因追跡しづらくなる

## 9. 作業ログ欄

| 日時 | 内容 | 結果 |
| --- | --- | --- |
| 2026-05-10 JST | user 受け入れ確認で「全部東京ドームになった」と報告 | 調査 ticket 化 |
| 2026-05-10 JST | read-only 本番記事確認 | 報知記事群は `featured_media=65953` 東京ドーム fallback が連続 |
| 2026-05-10 JST | read-only 実HTML確認 | 報知ページには `og:image` が存在する |
| 2026-05-10 JST | read-only 本番ログ確認 | 日刊スポーツ記事では source 画像 upload 成功例あり |
| 2026-05-10 JST | read-only 実HTML確認 | Full-Count / BaseballKing は `og:image` があるが、現行 `fetch_article_images()` が 0 |
| 2026-05-10 JST | read-only 原因確認 | `/wp-content/uploads/...` の `uploads` 内 `ad` が広告除外条件に誤ヒットする疑い |

## 10. Regression Memo欄

- 現行仕様は source eyecatch 優先、source 不在時だけ東京ドーム fallback。
- 東京ドーム fallback media id は `65953`。
- legacy Ichiro mixed media `36062` は unsafe として戻さない。
- 報知サンプル `https://hochi.news/articles/20260510-OHT1T51210.html` は `og:image` を持つ。
- それでも本番 post `65963` は `featured_media=65953` へ落ちた。
- 日刊スポーツ post `65961` は source 画像 media `65960` が入り、Web source 画像経路自体は動いている。
- Full-Count / BaseballKing は `og:image` があるが、現行抽出が 0 を返す。

## 作業後追記

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_featured_media_helpers.py`
- `doc/waiting/315-QA-source-featured-media-site-extraction.md`

### 2. diff概要

- `fetch_article_images()` の HTML 取得部分と画像候補抽出部分を分離し、取得済み HTML からも画像候補を抽出できるようにした。
- `/wp-content/uploads/...` の `uploads` に含まれる `ad` を広告画像と誤判定しないよう、広告除外条件を path segment ベースに変更。
- 既存候補が generic SNS 画像だけの場合は、記事ページを再取得して source 画像候補を追加するようにした。
- generic SNS 画像、ロゴ、バナー、広告画像の skip 方針は維持。
- source 画像が取れない場合は従来どおり東京ドーム fallback に落とし、記事生成は止めない。

### 3. 実行したテスト

- 赤確認:
  - `python3 -m unittest tests.test_featured_media_helpers.FeaturedMediaHelperTests.test_refetch_article_images_when_existing_candidates_are_generic tests.test_featured_media_helpers.FeaturedMediaHelperTests.test_fetch_article_images_keeps_wp_uploads_paths tests.test_featured_media_helpers.FeaturedMediaHelperTests.test_fetch_article_images_keeps_baseballking_uploads_paths`
- green 確認:
  - `python3 -m unittest tests.test_featured_media_helpers.FeaturedMediaHelperTests.test_refetch_article_images_when_existing_candidates_are_generic tests.test_featured_media_helpers.FeaturedMediaHelperTests.test_fetch_article_images_keeps_wp_uploads_paths tests.test_featured_media_helpers.FeaturedMediaHelperTests.test_fetch_article_images_keeps_baseballking_uploads_paths`
  - `python3 -m unittest tests.test_featured_media_helpers tests.test_featured_media_fallback`
  - `python3 -m unittest discover -s tests`

### 4. テスト結果

- 追加再現テストは修正前に赤を確認。
- 修正後、追加再現テストは green。
- 関連テスト green。
- `python3 -m unittest discover -s tests` は通常 sandbox では local HTTPServer の socket 作成が `PermissionError: [Errno 1] Operation not permitted` で 3 error。
- 同じ全件テストをローカル socket 許可付きで再実行し、`Ran 3377 tests in 63.479s OK`。

### 5. 残った懸念

- 報知など source 側の HTML / meta 仕様変更時には画像候補が取れず、東京ドーム fallback になる可能性は残る。
- generic 判定は維持したため、source 画像が generic しか無い記事は fallback のままになる。
- 記事ページ再取得が発生するため、generic 候補しか無い記事では実行時間が少し伸びる可能性がある。

### 6. 新しく見つかったデグレ

- 今回差分による新規デグレはテスト上確認なし。
- 既存全件テストは sandbox の socket 制限では失敗したが、許可付き再実行では通過。

### 7. 追加した回帰テスト

- 既存候補が報知 generic SNS 画像のみの場合、記事ページ source 画像を再取得して候補に追加すること。
- Full-Count の `/wp-content/uploads/...` 画像を `ad` 誤判定で落とさないこと。
- BaseballKing の `/wp-content/uploads/...` 画像を `ad` 誤判定で落とさないこと。

### 8. 次回触ってはいけない範囲

- publish
- mail
- scheduler
- env
- secrets
- Cloud Run 設定
- GitHub Actions
- SEO / schema
- 本文生成ロジック
- source 本文 excerpt ロジック
- Instagram 取り込み
- X 自動投稿
