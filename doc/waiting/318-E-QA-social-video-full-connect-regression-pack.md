# 318-E QA Social Video Full Connect Regression Pack

作成日: 2026-05-10
状態: BLOCKED_BY_318_A_TO_D
owner: Codex B
lane: B
親: 318 social-video full connect

## 目的

318-Aから318-Dまでの接続が、既存RSS / X / publish / mail / SEOへ副作用を出していないことを確認する回帰パックを作る。

特に、動画ソース拡張で大量記事化・主語欠落タイトル・空embed・重複記事が増えないことを確認する。

## 触る範囲

- `tests/test_youtube_ob_source_registry.py`
- `tests/test_instagram_source_registry.py`
- `tests/test_social_video_notice_builder.py`
- `tests/test_social_video_notice_validator.py`
- 必要な `tests/test_rss_fetcher_*.py`
- 必要な dry-run fixture
- 必要なら `docs/work_logs/2026-05-10_social-video-full-connect-tickets.md`

## 触らない範囲

- production deploy
- Cloud Run env
- scheduler
- secrets
- GitHub Actions
- X投稿
- WordPress本番記事
- publish gate緩和
- mail通知ロジック
- SEO / noindex / canonical / 301

## Regression対象

- YouTube動画URL正規化
- YouTube channel URL拒否
- YouTube unknown channel拒否
- Instagram post/reel/tv URL許可
- Instagram profile URL拒否
- unknown / hold / excluded source拒否
- WordPress embed必須
- reuploaded image拒否
- caption / video titleの短文利用
- 主語欠落タイトルfallback
- 同一動画重複防止
- `media_quote_only` の大量記事化防止
- 通常RSS記事への副作用なし
- X投稿なし

## Acceptance

- 318-Aから318-Dの主要経路に回帰テストがある。
- dry-runでYouTube / Instagramの本文embedを確認できる。
- publish / mail / scheduler / env / SEOに触っていないことを報告できる。
- full baselineで新規failureがない、または既存failureとして説明できる。
- fireした場合はログと数値diffを記録する。

## 実行予定テスト

- `python3 -m compileall src tests`
- touched Python AST parse
- `python3 -m unittest tests.test_youtube_ob_source_registry tests.test_instagram_source_registry tests.test_social_video_notice_builder tests.test_social_video_notice_validator`
- 追加した `tests/test_rss_fetcher_*.py`
- `python3 -m pytest`
- `git diff --check`

## STOP条件

- baselineで新規failureが出る
- 既存RSS / X本線の挙動が変わる
- publish数が想定外に増える可能性がある
- fire後ログでERROR増加
- 作成記事に空本文・変なタイトル・主観本文が出る
