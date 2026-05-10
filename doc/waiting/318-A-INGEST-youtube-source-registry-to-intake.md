# 318-A INGEST YouTube Source Registry To Intake

作成日: 2026-05-10
状態: READY_DOC_ONLY
owner: Codex B
lane: B
親: 318 social-video full connect
前提: 317-QA OB YouTube Review-Only Intake

## 目的

`config/youtube_ob_sources.json` に登録済みの巨人公式・放送・OB YouTubeチャンネルを、実際の取り込み候補として扱えるようにする。

初期接続は review/draft 優先。動画を大量に自動公開するのではなく、登録済みチャンネルから取得した動画を `social_video_notice` 候補に渡せる状態にする。

## 触る範囲

- `config/youtube_ob_sources.json`
- `config/rss_sources.json`
- `src/tag_page_scraper.py`
- `src/youtube_ob_source_registry.py`
- 必要な `tests/test_youtube_ob_source_registry.py`
- 必要な `tests/test_tag_page_scraper.py`

## 触らない範囲

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
- YouTube Data API / OAuth / secret
- YouTube文字起こし取得
- 動画コメント欄

## 実装方針

- 既存 `youtube_channel` scraper を優先して使う。
- `youtube_ob_sources.json` の `confirmed` / `candidate` だけを候補にする。
- `hold` / `excluded` は候補化しない。
- `media_quote_only` と `article_source` の境界を明示する。
- 初期は `review-only` / `draft` へ寄せ、publish gateは緩めない。
- 巨人文脈が薄い動画は候補化しない。

## Acceptance

- 登録済みYouTubeチャンネルだけが取得候補になる。
- 未登録チャンネルは安全扱いされない。
- `excluded` sourceは候補にならない。
- YouTube動画URLは `https://www.youtube.com/watch?v=...` に正規化される。
- チャンネルURLだけでは記事化しない。
- 初回実装でpublish条件は変わらない。
- ログに YouTube source別の取得件数が出る。

## 実行予定テスト

- `python3 -m compileall src tests`
- touched Python AST parse
- `python3 -m unittest tests.test_youtube_ob_source_registry`
- `python3 -m unittest tests.test_tag_page_scraper`
- 必要な `python3 -m pytest tests/test_youtube_ob_source_registry.py tests/test_tag_page_scraper.py`
- `git diff --check`

## STOP条件

- YouTube API key / OAuth / secret が必要になった
- 動画本文や発言内容を自動取得しないと成立しない
- 巨人無関係のOB雑談まで拾うしかない
- publish条件を緩めないと接続できない
- scheduler / env / deploy が必要になる
