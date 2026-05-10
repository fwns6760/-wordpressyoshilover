# 318-C QA Social Video Safe Title Fallback

作成日: 2026-05-10
状態: REVIEW_NEEDED
owner: Codex B
lane: B
親: 318 social-video full connect
関連: 316-A / 317 / 66147 post-deploy observation

## 目的

実名が拾えない動画・SNS素材でも、不自然な主語欠落タイトルを出さずに自然な巨人話題タイトルへ逃がす。

狙いは「実名なしなら人間編集」ではなく、自動で安全タイトルに落として編集負担を減らすこと。

## 触る範囲

- `src/title_validator.py`
- `src/title_player_name_backfiller.py`
- `src/rss_fetcher.py`
- `src/social_video_notice_builder.py`
- 関連する `tests/test_title_*.py`
- 関連する `tests/test_rss_fetcher_*.py`
- `tests/test_social_video_notice_builder.py`

## 触らない範囲

- publish条件の緩和
- scheduler
- Cloud Run env
- Secret Manager
- mail通知
- X投稿
- SEO / noindex / canonical / 301
- WordPress本番記事の直接編集

## 実装方針

- 実名が拾えた場合は選手名・OB名入りタイトルを優先する。
- 実名が拾えないが巨人関連が明確な場合は、安全な媒体話題タイトルへfallbackする。
- 実名がなく内容も薄い場合は skip / review に落とす。
- `がV打` / `が15戦` / `が右前打` / `選手が` / `投手が` など主語欠落パターンを検出する。
- AI推測で実名を補完しない。

## 例

NG:

- `巨人は「母の日」に投打の新星が恩返し がV2点三塁打！ が15戦連続無失点！…`

OK:

- `巨人「母の日」に投打で話題 サンスポ巨人Xが投稿`
- `巨人OBの発言が話題 YouTubeで公開`
- `巨人公式が練習動画を公開`

## Acceptance

- 主語欠落タイトルはpublish候補タイトルにならない。
- 実名が取れた場合は実名を使う。
- 実名が取れない場合でも自然な安全タイトルへfallbackする。
- 実名推測はしない。
- `title_player_name_unresolved` が出た素材は欠落タイトルで通さない。
- YouTube / Instagram / X / RSS短文に共通適用できる。

## 実行予定テスト

- `python3 -m compileall src tests`
- touched Python AST parse
- `python3 -m unittest tests.test_title_validator`
- `python3 -m unittest tests.test_title_rewrite`
- `python3 -m unittest tests.test_rss_fetcher`
- 必要な新規fixtureテスト
- `python3 -m pytest` baseline
- `git diff --check`

## STOP条件

- 実名を推測で補完しないと成立しない
- 本当に巨人関連か判定できない素材を公開に進める必要がある
- publish gateを緩める必要がある
- 既存の通常RSSタイトルを広く変えてしまう

## 実装結果メモ

- 2026-05-10: 主語欠落パターン ` がV2点` / ` が15戦` を `orphan_particle_no_subject` として検出。
- 2026-05-10: `新星` / `投打` / `恩返し` を人名候補から除外。
- 2026-05-10: X / YouTube / Instagram 系ソースで実名補完が失敗し、欠落主語タイトルになった場合だけ、安全な媒体話題タイトルへfallback。
- 2026-05-10: `social_video_notice` のYouTube / Instagramタイトルにも同じ安全fallbackを追加。
- 2026-05-10: publish条件、mail、scheduler、Cloud Run env、Secret Manager、X投稿、SEO、WP本番記事は未変更。

## 実行結果

- `python3 -m compileall src tests`: PASS
- touched Python AST parse: PASS (`7` files)
- `python3 -m unittest tests.test_title_validator tests.test_title_player_name_backfill tests.test_social_video_notice_builder`: PASS (`52` tests)
- `python3 -m pytest tests/test_title_validator.py tests/test_title_player_name_backfill.py tests/test_social_video_notice_builder.py tests/test_rss_fetcher.py tests/test_title_rewrite.py tests/test_rss_x_short_player_routing.py`: PASS (`144` tests)
- `python3 -m pytest`: first sandbox run failed only on local `HTTPServer` socket permission (`3` failures in `tests/test_manual_intake_service.py`)
- `python3 -m pytest` with escalated local socket permission: PASS (`3570` passed, `3` warnings)

## 追加回帰テスト

- `tests/test_title_validator.py::TitleValidatorTests::test_is_weak_subject_title_orphan_particle_inside_title`
- `tests/test_title_player_name_backfill.py::TitlePlayerNameBackfillTests::test_fetcher_adapter_uses_safe_title_for_nameless_social_orphan_particle`
- `tests/test_social_video_notice_builder.py::SocialVideoNoticeBuilderTests::test_builder_uses_safe_title_for_nameless_orphan_particle_caption`
