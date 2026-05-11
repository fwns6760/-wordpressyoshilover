# 2026-05-11 eyecatch source image regression work log

## 1. 目的

最近のアイキャッチが「出典画像がある時は出典画像、何もなければ東京ドーム fallback」という期待ルール通りに見えない問題を、実装前に記録・切り分けする。

## 2. 現時点の観測

- 直近20本の公開記事で、東京ドーム fallback `media_id=65953` が複数回使われている。
- X投稿本文に画像付き投稿の埋め込みがある記事でも、`featured_media=65953` へ落ちている例がある。
- 代表例:
  - `66325`: ジャイアンツ球場 / 戸郷投手のX投稿、`featured_media=65953`
  - `66362`: 坂本勇人 / 母の日のX投稿、`featured_media=65953`
  - `66367`: セ・リーグ打撃成績、`featured_media=65953`
  - `66309`: セ・リーグ公示、`featured_media=65953`
- 現時点の疑いは、X / social_news 系の画像候補抽出が弱く、画像付き投稿を「画像なし」と扱っていること。

## 3. 今回触らない範囲

- publish 条件
- mail 通知
- scheduler
- Cloud Run service / job 設定
- Cloud Run env
- Secret Manager
- GitHub Actions
- SEO / noindex / canonical / 301
- X投稿 / X API / 自動投稿
- frontend / AdSense / scroll UI
- WP本番記事の手動修正
- 既存公開記事の一括修正
- `RUN_DRAFT_ONLY`
- `PUBLISH_REQUIRE_IMAGE`
- unrelated docs / logs / build artifacts

## 4. 影響範囲

直接影響する可能性:

- `social_news` / X投稿由来の記事の `featured_media` 選定
- RSS entry / feedparser entry からの画像候補抽出
- 出典画像が取れない時の東京ドーム fallback 発動頻度
- `featured_media_missing` / `featured_media_observation_missing` の観測量

影響させない範囲:

- 記事本文生成
- タイトル生成
- 公開 gate の基準
- publish / mail / scheduler の実行頻度
- X投稿文生成
- フロント表示CSS

## 5. 実行予定テスト

実装 GO 後に、先に再現テストを追加して赤確認する。

- `tests/test_yahoo_realtime.py` または `tests/test_featured_media_helpers.py`
  - X / social_news entry の `media_content` / `media_thumbnail` / enclosure / image-like metadata から画像URLを抽出できること。
  - `pbs.twimg.com/media/...?...format=jpg` のように拡張子が query にある画像URLを候補として保持すること。
  - `hochi_news_sns` / `sponichi_sns` / logo / icon / generic OGP は候補として優先しない、または upload 前に skip されること。
  - 画像候補がある場合、東京ドーム fallback へ落ちないこと。
  - 画像候補が本当にない場合だけ fallback が残ること。
- targeted:
  - `python3 -m unittest tests.test_yahoo_realtime`
  - `python3 -m unittest tests.test_featured_media_helpers`
  - `python3 -m unittest tests.test_featured_media_fallback`
- touched Python がある場合:
  - `python3 -m py_compile <touched files>`
  - `python3 -m compileall <touched files>`
  - AST parse check
- 可能なら:
  - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 再現テストの赤確認ができない。
- X画像取得に認証情報、secret、X API live call が必要になる。
- 画像取得のために外部 source 追加や scheduler 変更が必要になる。
- 画像候補抽出の修正が publish gate / mail / frontend / SEO に波及する。
- 出典画像ではなく無関係な画像を拾うリスクが高い。
- logo / SNS generic / 広告画像を安全に除外できない。
- 既存の未コミット差分を戻す必要が出る。
- live 設定変更や deploy が必要になる。

## 7. 禁止事項

- user GO 前にコード編集しない。
- user GO 前に commit / push / deploy しない。
- `git add -A` しない。
- env / secret / scheduler / Cloud Run 設定を変更しない。
- WP本番記事を直接編集しない。
- X API を叩かない。
- Xへ投稿しない。
- frontend / AdSense / CSS をついでに触らない。
- 東京ドーム fallback を独断で無効化しない。
- 関連しない本文品質 / タイトル / カテゴリ分類を同じ作業に混ぜない。

## 8. 想定されるデグレ

- X投稿のカード画像ではなく、プロフィール画像やロゴを拾う。
- 動画投稿でサムネイルではなく不適切な画像を拾う。
- `pbs.twimg.com` の小さい variant を拾い、粗いアイキャッチになる。
- query付き画像URLの dedupe が効かず、同じ画像を重複 upload する。
- generic SNS OGP を画像あり扱いし、東京ドームより悪い画像になる。
- 画像候補抽出が増え、RSS fetcher の外部HTTP回数が増える。
- fallback 発動が減った結果、アイキャッチなし記事が増える。

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-11 JST | work log作成 | user指示により、コード編集前の作業記録Markdownのみ作成。コード編集・commit・push・deploy・env変更・scheduler変更は未実施。 |
| 2026-05-11 JST | 回帰テスト追加 | user GO により、X / social feed の `media_content` / `media_thumbnail` が source image 候補として抽出されるべきことを `tests/test_yahoo_realtime.py` に追加。production code は未編集。 |
| 2026-05-11 JST | 赤確認 | `python3 -m unittest tests.test_yahoo_realtime.ArticleImageFetchTests` で追加2件が失敗し、現行実装が X media metadata を silent skip していることを確認。 |
| 2026-05-11 JST | 実装 | `_extract_entry_image_urls()` で `media_content` / `media_thumbnail` の `url` を既存 `_add()` 経由で画像候補に加えるよう修正。 |
| 2026-05-11 JST | green確認 | targeted / 構文 / full suite を実行。sandbox full suite は localhost bind 制限で3 error、権限付き再実行で `Ran 3424 tests ... OK`。 |
| 2026-05-11 JST | commit | `10d2df8 fix: extract social media thumbnails for eyecatch` を作成。 |
| 2026-05-11 JST | deploy | user GO により、後続 commit `ef5fe7b` と合わせて `yoshilover-fetcher` image `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:ef5fe7b` として build/deploy。new revision `yoshilover-fetcher-00310-smb`、traffic 100%。env / scheduler 変更なし。 |
| 2026-05-11 JST | post-deploy確認 | `/health` は HTTP 200 OK。主要 env は `RUN_DRAFT_ONLY=0`、`AUTO_TWEET_ENABLED=0`、`PUBLISH_REQUIRE_IMAGE=1`。新 revision の直近 ERROR ログなし。 |
| 2026-05-11 JST | post-deploy追加確認 | `manual-intake-service` / 3 auto jobs も後続の source excerpt 修正反映のため `manual-intake-service:ef5fe7b` に更新。`postgame-auto-bg2fj` / `publish-notice-8fvs7` は `EXECUTION_SUCCEEDED`。13:30Z 以降の対象 ERROR log なし。 |
| 2026-05-11 JST | live記事確認 | 22:30 JST の `postgame-auto` は既存 post `66139` 再利用で新規記事作成なし。最新公開記事8件は read-only 確認で空本文なし。次回 X / social feed の画像付き新規記事で fallback 回避を継続観測する。 |

## 10. Regression Memo欄

- 期待ルールは「出典画像がある時は出典画像、何もなければ東京ドーム fallback」。
- 直近の問題は、ルールそのものよりも `social_news` / X投稿の画像候補抽出が弱く、画像付き投稿でも候補ゼロ扱いになっている可能性が高い。
- 修正する場合は、まず `_extract_entry_image_urls()` 周辺に限定する。
- `src/wp_client.py` の publish / create_post 基本挙動は原則触らない。
- `src/player_eyecatch_resolver.py` の fallback policy は原則触らない。
- `media_id=65953` の画像サイズ問題は別論点。今回の主目的は「出典画像があるのに fallback へ落ちる」問題。

## 作業後追記欄

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `tests/test_yahoo_realtime.py`
- `docs/work_logs/2026-05-11_eyecatch-source-image-regression.md`

### 2. diff概要

- `src/rss_fetcher.py`
  - `_extract_entry_image_urls()` で entry の `media_content` / `media_thumbnail` を確認。
  - 各 item の `url` を既存 `_add()` に通し、既存の絶対URL化 / generic除外 / dedupe / `max_images` 制限をそのまま利用。
- `ArticleImageFetchTests` に、X投稿由来 entry の `media_content` から `pbs.twimg.com/media/...?...format=jpg` を抽出する回帰テストを追加。
- `ArticleImageFetchTests` に、X投稿由来 entry の `media_thumbnail` から `pbs.twimg.com/media/...?...format=jpg` を抽出する回帰テストを追加。
- 作業ログへ、回帰テスト追加と赤確認の結果を追記。

### 3. 実行したテスト

- `python3 -m unittest tests.test_yahoo_realtime.ArticleImageFetchTests`
- `python3 -m unittest tests.test_yahoo_realtime tests.test_featured_media_helpers tests.test_featured_media_fallback`
- `python3 -m py_compile src/rss_fetcher.py tests/test_yahoo_realtime.py`
- `python3 -m compileall src/rss_fetcher.py tests/test_yahoo_realtime.py`
- `python3 -m unittest discover -s tests`
- `python3 -m unittest discover -s tests` (sandbox localhost bind failure のため権限付き再実行)

### 4. テスト結果

- 赤確認: `Ran 4 tests ... FAILED (failures=2)`
- 失敗した追加テスト:
  - `test_extract_entry_image_urls_uses_x_media_content_metadata`
  - `test_extract_entry_image_urls_uses_x_media_thumbnail_metadata`
- 既存の linked article / curl fallback テストは同一クラス内で通過。
- 修正後 targeted: `Ran 4 tests ... OK`
- 関連 targeted: `Ran 67 tests ... OK`
- `py_compile`: OK
- `compileall`: OK
- sandbox full suite: `Ran 3424 tests ... FAILED (errors=3)`
  - `tests/test_manual_intake_service.py::LiveServerSmokeTest` の localhost socket bind が `PermissionError: [Errno 1] Operation not permitted`
- 権限付き full suite: `Ran 3424 tests in 56.813s ... OK`

### 5. 残った懸念

- live source で実際に `media_content` / `media_thumbnail` が届くかは、次の自動生成 window または deploy 後ログ観測で確認が必要。
- 今回は `media_content` / `media_thumbnail` に限定し、enclosure / links の画像MIME抽出は未実装。
- deploy / runtime 反映は完了。ただし 22:30 JST の `postgame-auto` は既存 post 再利用で新規記事作成なし。次回の自動生成 window で、X / social feed の画像付き投稿が東京ドーム fallback に落ちないことは継続観測が必要。

### 6. 新しく見つかったデグレ

- 今回の赤確認で、X / social feed の `media_content` / `media_thumbnail` が `_extract_entry_image_urls()` で抽出されないことを確認。
- 修正後のテストでは新規デグレなし。

### 7. 追加した回帰テスト

- `tests/test_yahoo_realtime.py::ArticleImageFetchTests::test_extract_entry_image_urls_uses_x_media_content_metadata`
- `tests/test_yahoo_realtime.py::ArticleImageFetchTests::test_extract_entry_image_urls_uses_x_media_thumbnail_metadata`

### 8. 次回触ってはいけない範囲

- publish / mail / scheduler / env / Cloud Run 設定
- X API / X投稿
- frontend / AdSense / CSS
- WP本番記事の直接編集
- `src/player_eyecatch_resolver.py` の fallback policy
