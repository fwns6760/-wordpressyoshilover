# 080 Social Video Notice Lane

## Purpose

Instagram と YouTube の投稿・動画を、`social_video_notice` subtype の独立記事として扱うための contract / builder / validator / dry-run CLI を追加する。

## Boundary

- 対象 platform は `instagram` と `youtube` のみ
- 他 platform は列挙しない
- account allowlist はこの段階では持ち込まない
- 1 source = 1 nucleus = 1 article を固定する

## Supported Platforms

- `instagram`
- `youtube`

## Payload Schema

`SocialVideoNoticePayload`

- `source_platform`
- `source_url`
- `source_account_name`
- `source_account_type`
- `media_kind`
- `caption_or_title`
- `published_at`
- `supplement_note`

## Article Schema

`SocialVideoNoticeArticle`

- `subtype`
- `title`
- `body_html`
- `badge`
- `nucleus_subject`
- `nucleus_event`
- `source_platform`
- `source_url`
- `source_account_name`
- `source_account_type`
- `media_kind`
- `published_at`

## Body Layout

`body_html` は次の 2〜3 行で構成する。

1. 出典行
2. caption / title 由来の事実要約 1 文
3. `supplement_note` がある場合だけ補足 1 文

embed HTML や thumbnail は持ち込まず、link-based article として成立させる。

## Validator Hard Fail

- `SOURCE_MISSING`
- `UNSUPPORTED_PLATFORM`
- `SOURCE_BODY_MISMATCH`
- `MULTIPLE_NUCLEI`
- `OPINION_LEAK`
- `TITLE_BODY_MISMATCH`

## Badge Metadata

一覧向け metadata として `badge = {"platform": ..., "media_kind": ...}` を article に保持する。

## 071 Reuse

title / body nucleus 一致判定は ticket 071 の `validate_title_body_nucleus(...)` を再利用する。
`MULTIPLE_NUCLEI` はそのまま返し、`SUBJECT_ABSENT` と `EVENT_DIVERGE` は `TITLE_BODY_MISMATCH` に写像する。

## Non-Goals

- front consumption の配線
- account allowlist
- embed HTML / oEmbed / thumbnail
- 他 platform 向け lane
- automation wiring
- 実 API fetch
- publish 経路
- mail chain 連携
- eyecatch 連携
