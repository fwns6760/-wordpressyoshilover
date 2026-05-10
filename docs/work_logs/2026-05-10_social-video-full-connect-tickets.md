# Social Video Full Connect 作業記録

作成日: 2026-05-10 JST
状態: USER_GO待ち
この時点の許可変更: 本Markdown作成のみ

## 1. 今回の目的

YouTube / Instagram / OB動画ソースを、既存の安全な記事生成フローへ段階的に接続する。

主目的:

- YouTube動画をリンクではなくWordPressのYouTube埋め込みとして記事本文に出す。
- Instagram投稿も、登録済みソースと投稿URLがある場合にWordPressのInstagram埋め込みとして記事本文に出せるようにする。
- 巨人公式、巨人OB、巨人選手、巨人担当媒体の動画・SNS素材を拾える範囲を広げる。
- 実名が拾えない場合でも、主語欠落タイトルや不自然な本文で公開しない。
- 初期段階ではpublishを緩めず、review/draft中心で実データ確認できる形にする。

## 2. 今回触る範囲

予定する分割チケット:

### 318-A: YouTube source registry to intake connection

- `config/youtube_ob_sources.json`
- `config/rss_sources.json`
- `src/tag_page_scraper.py`
- `src/youtube_ob_source_registry.py`
- YouTubeチャンネルの取得対象拡張
- 取得結果のreview/draft導線

### 318-B: social_video_notice pipeline connection

- `src/social_video_notice_builder.py`
- `src/social_video_notice_validator.py`
- `src/tools/run_social_video_notice_dry_run.py`
- `src/rss_fetcher.py` または既存manual/review intakeの接続点
- YouTube / Instagram投稿を `social_video_notice` として本文生成へ接続

### 318-C: safe title fallback for nameless video/social sources

- `src/title_validator.py`
- `src/title_player_name_backfiller.py`
- `src/rss_fetcher.py`
- 実名なし素材向けの安全タイトル fallback
- `がV打` / `が15戦` / `選手が` のような主語欠落タイトルのpublish防止または自然タイトル化

### 318-D: Instagram registered-source URL intake

- `config/instagram_sources.json`
- `src/instagram_source_registry.py`
- `src/tools/run_social_video_notice_dry_run.py`
- 投稿URLありのInstagram記事雛形生成
- 自動巡回ではなく、登録済みアカウント + 投稿URL入力の安全接続

### 318-E: tests and dry-run evidence

- `tests/test_youtube_ob_source_registry.py`
- `tests/test_instagram_source_registry.py`
- `tests/test_social_video_notice_builder.py`
- `tests/test_social_video_notice_validator.py`
- 必要に応じて `tests/test_rss_fetcher_*.py`
- dry-runで本文に `wp-block-embed-youtube` / `wp-block-embed-instagram` が入ることを確認

## 3. 今回触らない範囲

- deploy
- git commit
- git push
- Cloud Run env変更
- Cloud Run service設定変更
- Cloud Scheduler変更
- Secret Manager変更
- GitHub Actions変更
- X投稿
- X API call
- mail通知ロジック
- SEO / noindex / canonical / 301
- WordPress本番記事の直接修正
- publish条件の緩和
- Instagramの無制限スクレイピング
- 未登録YouTube / 未登録Instagramアカウントの自動承認
- `.env` / secret / auth.json

## 4. 影響範囲

影響する可能性がある範囲:

- YouTube / Instagram / SNS動画素材のreview/draft生成
- social video系の記事タイトル
- social video系の記事本文
- WordPress oEmbedブロック生成
- social source registryの読み込み
- YouTube channel scraperの取得件数
- publish前のタイトル品質判定

影響しない想定の範囲:

- 既存RSSニュース記事の通常生成
- 既存X記事の通常埋め込み
- mail送信
- X自動投稿
- Cloud Run / Scheduler設定
- SEO設定
- WordPressカテゴリ構成

## 5. 実行予定テスト

作業前:

- 対象識別子の `rg`
- 既存YouTube / Instagram / social_video関連テスト確認

作業後:

- `python3 -m compileall src tests`
- 触ったPythonファイルのAST parse
- `python3 -m unittest tests.test_youtube_ob_source_registry`
- `python3 -m unittest tests.test_instagram_source_registry`
- `python3 -m unittest tests.test_social_video_notice_builder`
- `python3 -m unittest tests.test_social_video_notice_validator`
- 必要な `tests.test_rss_fetcher_*`
- `python3 -m pytest` baseline
- `git diff --check`

dry-run:

- YouTube動画URLで `social_video_notice` を生成し、`wp-block-embed-youtube` が入ること
- Instagram投稿URLで `social_video_notice` を生成し、`wp-block-embed-instagram` が入ること
- 未登録YouTube channelはrejectされること
- 未登録Instagram accountはrejectされること
- channel URL / profile URLだけでは記事化しないこと

本番fire後に必要な確認:

- このMarkdown作成時点ではfire禁止
- GO後にfireする場合は、fire前にユーザー確認
- fire後はログ、ERROR件数、作成記事数、review/draft数、publish数の数値diffを記録

## 6. STOP条件

以下を確認したら作業停止して報告する:

- 未登録ソースを安全扱いしている箇所を見つけた
- Instagram自動巡回に外部API / 認証 / 規約リスクが必要になる
- YouTube動画本文の発言内容を取得できず、動画タイトルだけで事実以上の本文を作りそうになる
- 実名なし素材で主語欠落タイトルがpublishされる可能性が残る
- `publish` 条件を緩めないと接続できない
- Cloud Run env / Scheduler変更が必要になる
- X投稿に触る必要が出る
- 既存RSS / X本線の挙動に広い副作用が出る
- baseline testに新規failureが出て原因を説明できない
- `.env` / secrets / auth.json が必要になる

## 7. 禁止事項

- このMarkdown作成後、ユーザーGO前にコード編集しない
- commitしない
- pushしない
- deployしない
- env変更しない
- scheduler変更しない
- Secret Manager変更しない
- GitHub Actions変更しない
- X投稿しない
- 本番WP記事を直接修正しない
- publish gateを勝手に緩めない
- 未登録SNSソースを自動でconfirmed扱いしない
- Instagram画像を転載・再アップロードしない
- YouTube動画の内容を見ていないのに発言内容を断定しない

## 8. 想定されるデグレ

- YouTube channel scraperの取得件数増加で実行時間が増える
- `media_quote_only` と `article_source` の境界を誤ると動画素材が大量に記事化される
- Instagram URLの形式差でvalidな投稿をrejectする
- YouTube shorts / live / youtu.be の正規化漏れ
- WordPress oEmbedがテーマ側で期待通り表示されない
- 実名なし動画タイトルが不自然な記事タイトルになる
- OBチャンネルの巨人以外話題を拾う
- 同一動画の重複記事化
- source registryのcandidate / hold / excluded扱いミス
- social_video_noticeが既存RSS本文生成と混ざり、通常記事に副作用が出る

## 9. 作業ログ欄

- 2026-05-10: ユーザー指示により、本Markdownのみ作成。コード編集、commit、push、deploy、env変更、scheduler変更は未実施。
- 2026-05-10: ユーザーGO後、実装には進まず、318-Aから318-Eまでのdoc-only分割チケットを `doc/waiting/` に作成。`doc/README.md` と `doc/active/assignments.md` に最小台帳追記。

## 10. Regression Memo欄

- 2026-05-10 deploy後確認で、YouTube source追加そのものではなく、X短文素材 `post_id=66147` に人名欠落タイトルが公開された事象を確認。
- 対策方針: ソース追加は継続しつつ、実名なし時は主語欠落タイトルではなく自然な巨人話題タイトルへfallbackする。
- YouTube / Instagram接続時も同じタイトル品質ガードを共通適用する。

## 作業後追記欄

### 1. 実際に変更したファイル

- `docs/work_logs/2026-05-10_social-video-full-connect-tickets.md`
- `doc/waiting/318-A-INGEST-youtube-source-registry-to-intake.md`
- `doc/waiting/318-B-INGEST-social-video-notice-pipeline-connection.md`
- `doc/waiting/318-C-QA-social-video-safe-title-fallback.md`
- `doc/waiting/318-D-INGEST-instagram-registered-url-intake.md`
- `doc/waiting/318-E-QA-social-video-full-connect-regression-pack.md`
- `doc/README.md`
- `doc/active/assignments.md`

### 2. diff概要

- YouTube / Instagram / OB動画の完全接続を5本のチケットに分割。
- 318-A: YouTube登録棚をintake候補へ接続するticket。
- 318-B: `social_video_notice` を実際のreview/draft生成入口へ接続するticket。
- 318-C: 実名なし素材の安全タイトルfallback ticket。
- 318-D: Instagram登録済みアカウント + 投稿URL intake ticket。
- 318-E: full-connect回帰テスト / dry-run evidence ticket。
- 102 boardとassignmentsに、318-A..Eの存在と不可触範囲を追記。
- コード、config、tests本体、deploy、env、scheduler、WP本番記事は未変更。

### 3. 実行したテスト

- docs-only変更のためPythonテストは未実行。
- `git diff --check`

### 4. テスト結果

- `git diff --check`: PASS

### 5. 残った懸念

- 318-A..Eは起票のみ。実装は未着手。
- 実装順は安全上、318-C safe title fallbackを先に入れるか、318-Aをreview-onlyで先に入れるかを次のGOで決める必要がある。

### 6. 新しく見つかったデグレ

- なし。docs-only変更。

### 7. 追加した回帰テスト

- なし。docs-only起票。

### 8. 次回触ってはいけない範囲

- publish条件
- mail通知
- scheduler
- Cloud Run env
- Cloud Run service設定
- Secret Manager
- GitHub Actions
- X投稿
- SEO / noindex / canonical / 301
- WordPress本番記事の直接編集
- YouTube / Instagram API secret
- Instagram画像再アップロード

## 318-C 実装追記

### 1. 実際に変更したファイル

- `src/title_validator.py`
- `src/title_player_name_backfiller.py`
- `src/rss_fetcher.py`
- `src/social_video_notice_builder.py`
- `tests/test_title_validator.py`
- `tests/test_title_player_name_backfill.py`
- `tests/test_social_video_notice_builder.py`
- `doc/active/318-C-QA-social-video-safe-title-fallback.md`
- `doc/README.md`
- `doc/active/assignments.md`
- `docs/work_logs/2026-05-10_social-video-full-connect-tickets.md`

### 2. diff概要

- ` がV2点` / ` が15戦` のように、空白・句読点の後から `が` でイベントが始まる主語欠落タイトルを `orphan_particle_no_subject` として検出。
- `新星` / `投打` / `恩返し` を人名候補から除外し、実名として誤採用しないようにした。
- X / YouTube / Instagram 系ソースで実名補完が失敗し、欠落主語タイトルになった場合だけ、安全な媒体話題タイトルへfallback。
- `social_video_notice` のYouTube / Instagram記事タイトルにも同じ安全fallbackを追加。
- 318-C ticketを `doc/waiting/` から `doc/active/` へ移動し、状態を `REVIEW_NEEDED` に更新。

### 3. 実行したテスト

- `python3 -m compileall src tests`
- touched Python AST parse
- `python3 -m unittest tests.test_title_validator tests.test_title_player_name_backfill tests.test_social_video_notice_builder`
- `python3 -m pytest tests/test_title_validator.py tests/test_title_player_name_backfill.py tests/test_social_video_notice_builder.py tests/test_rss_fetcher.py tests/test_title_rewrite.py tests/test_rss_x_short_player_routing.py`
- `python3 -m pytest`
- `python3 -m pytest` with escalated local socket permission

### 4. テスト結果

- `python3 -m compileall src tests`: PASS
- touched Python AST parse: PASS (`7` files)
- `python3 -m unittest tests.test_title_validator tests.test_title_player_name_backfill tests.test_social_video_notice_builder`: PASS (`52` tests)
- targeted pytest: PASS (`144` tests)
- baseline pytest first run: FAIL only because sandbox denied local `HTTPServer` socket (`3` failures in `tests/test_manual_intake_service.py`)
- baseline pytest escalated rerun: PASS (`3570` passed, `3` warnings)

### 5. 残った懸念

- 安全fallbackは実名を推測しないため、X本文・動画タイトルに実名がない場合は実名タイトルにはならない。
- 複数人物が本文にいて頻度差がない場合は中立タイトルへ寄せる既存挙動を維持。
- 今回はrepo実装のみ。deploy / fire / live log確認は未実施。

### 6. 新しく見つかったデグレ

- なし。

### 7. 追加した回帰テスト

- `tests/test_title_validator.py::TitleValidatorTests::test_is_weak_subject_title_orphan_particle_inside_title`
- `tests/test_title_player_name_backfill.py::TitlePlayerNameBackfillTests::test_fetcher_adapter_uses_safe_title_for_nameless_social_orphan_particle`
- `tests/test_social_video_notice_builder.py::SocialVideoNoticeBuilderTests::test_builder_uses_safe_title_for_nameless_orphan_particle_caption`

### 8. 次回触ってはいけない範囲

- publish条件
- mail通知
- scheduler
- Cloud Run env
- Cloud Run service設定
- Secret Manager
- GitHub Actions
- X投稿
- SEO / noindex / canonical / 301
- WordPress本番記事の直接編集
