# 318-D INGEST Instagram Registered URL Intake

作成日: 2026-05-10
状態: READY_DOC_ONLY
owner: Codex B
lane: B
親: 318 social-video full connect
前提: 313-QA Instagram Intake Nomotoke Style Expansion

## 目的

Instagramについて、まずは自動巡回ではなく「登録済みアカウント + 投稿URLあり」の安全な取り込みを作る。

Instagram APIや無制限スクレイピングには進まず、手動投入・レビュー投入・将来のqueue投入で使える入口を整える。

## 触る範囲

- `config/instagram_sources.json`
- `src/instagram_source_registry.py`
- `src/social_video_notice_builder.py`
- `src/social_video_notice_validator.py`
- `src/tools/run_social_video_notice_dry_run.py`
- 必要な manual/review intake接続点
- `tests/test_instagram_source_registry.py`
- `tests/test_social_video_notice_builder.py`
- `tests/test_social_video_notice_validator.py`

## 触らない範囲

- Instagram自動巡回
- Instagram API token / Meta app
- Instagram画像保存
- Instagram画像再アップロード
- caption全文転載
- publish条件
- scheduler
- Cloud Run env
- Secret Manager
- X投稿
- SEO / noindex / canonical / 301
- WordPress本番記事の直接編集

## 実装方針

- 入口は投稿URLとaccount handleを明示入力する。
- `confirmed` / `candidate` の登録済みsourceだけ許可する。
- `hold` / `excluded` / unknown は拒否する。
- 投稿URLは `/p/` `/reel/` `/tv/` のみ許可する。
- profile URLは拒否する。
- 本文はInstagram embed + source line + 短いcaption excerptに抑える。

## Acceptance

- 登録済みアカウント + 投稿URLで記事候補を作れる。
- 本文に `wp-block-embed-instagram` が入る。
- profile URLはrejectされる。
- unknown accountはrejectされる。
- 画像再アップロードがない。
- caption全文転載がない。
- 自動巡回は追加されない。

## 実行予定テスト

- `python3 -m compileall src tests`
- touched Python AST parse
- `python3 -m unittest tests.test_instagram_source_registry`
- `python3 -m unittest tests.test_social_video_notice_builder`
- `python3 -m unittest tests.test_social_video_notice_validator`
- 必要な intake接続テスト
- `python3 -m pytest` baseline
- `git diff --check`

## STOP条件

- Instagram API / secret が必要になる
- 自動巡回を入れないと成立しない
- 画像保存・再アップロードが必要になる
- caption全文転載に近づく
- 本人性を担保できないアカウントを通す必要がある
