# 318-B INGEST Social Video Notice Pipeline Connection

作成日: 2026-05-10
状態: BLOCKED_BY_318_A
owner: Codex B
lane: B
親: 318 social-video full connect
前提: 313-QA Instagram Intake Nomotoke Style Expansion / 317-QA OB YouTube Review-Only Intake

## 目的

既存の `social_video_notice` builder / validator / dry-run CLI を、rss/manual/review intake のどこか安全な入口に接続する。

YouTube / Instagram の動画・投稿を、リンクだけではなく WordPress embed block を含む記事本文候補として生成できるようにする。

## 触る範囲

- `src/social_video_notice_builder.py`
- `src/social_video_notice_validator.py`
- `src/tools/run_social_video_notice_dry_run.py`
- `src/rss_fetcher.py` または既存manual/review intake接続点
- `tests/test_social_video_notice_builder.py`
- `tests/test_social_video_notice_validator.py`
- 必要な intake 接続テスト

## 触らない範囲

- publish条件の緩和
- mail通知
- scheduler
- Cloud Run env
- Secret Manager
- GitHub Actions
- X投稿
- SEO / noindex / canonical / 301
- WordPress本番記事の直接編集
- 画像の保存・再アップロード
- YouTube / Instagram本文の長文転載

## 実装方針

- `source_platform=youtube` は `wp-block-embed-youtube` を必須にする。
- `source_platform=instagram` は `wp-block-embed-instagram` を必須にする。
- source header、source URL、account name / handle を本文に明示する。
- caption / video title は短い literal excerpt に限定する。
- LLM自由作文で動画内容を補完しない。
- 接続初期は review/draft まで。自動publish対象にしない。

## Acceptance

- YouTube URL入力から `social_video_notice` 記事候補を生成できる。
- Instagram投稿URL入力から `social_video_notice` 記事候補を生成できる。
- 本文にWordPress embed blockが入る。
- profile URL / channel URLだけはrejectされる。
- 画像再アップロードを含む本文はvalidatorで拒否される。
- unknown sourceはrejectされる。
- publish gateは変わらない。

## 実行予定テスト

- `python3 -m compileall src tests`
- touched Python AST parse
- `python3 -m unittest tests.test_social_video_notice_builder`
- `python3 -m unittest tests.test_social_video_notice_validator`
- `python3 -m unittest tests.test_instagram_source_registry tests.test_youtube_ob_source_registry`
- 必要な intake接続テスト
- `python3 -m pytest` baseline
- `git diff --check`

## STOP条件

- publishに接続しないと成立しない
- LLMで動画内容を補完する必要が出る
- Instagram API / YouTube API secret が必要になる
- 既存RSS本文生成と混線する
- 通常RSS / X記事に副作用が出る
