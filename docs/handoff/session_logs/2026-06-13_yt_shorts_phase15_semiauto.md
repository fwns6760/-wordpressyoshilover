# 2026-06-13 YouTube Shorts Phase 1.5 半自動公開 repo 実装

## user request

- 「半自動化はできない？」
- 「値段はあまりかわらない？」
- 「ではGO」

## scope

動画生成済みMP4を YouTube へ private upload し、HTML mail の button で user が公開する flow を repo 実装する。

## implemented

- `src/yt_shorts_youtube.py`
  - OAuth refresh token から access token を取得
  - YouTube Data API resumable upload で `privacyStatus=private`
  - `videos.list` + `videos.update` で `privacyStatus=public`
  - runtime dependency は既存 `requests` のみ
- `src/yt_shorts_youtube_token.py`
  - YouTube video_id 用 HMAC + expiry token
  - `YT_SHORTS_APPROVAL_TOKEN_SECRET` 優先、`PUBLISH_BUTTON_TOKEN_SECRET` fallback
- `src/yt_shorts_publish_handler.py`
  - `GET /yt-shorts-publish`: confirmation page
  - `POST /yt-shorts-publish`: token verify → YouTube public化
- `src/server.py`
  - fetcher service に `/yt-shorts-publish` route を追加
- `src/yt_shorts_gen.py`
  - `--youtube-private-upload` / `YT_SHORTS_YOUTUBE_PRIVATE_UPLOAD=1`
  - live時のみ private upload
  - HTML mail に YouTube確認 / Studio編集 / 公開button を追加
  - YouTube upload済みも日次cap対象として扱う

## safety

- `--live` だけでは YouTube API に触らない。`--youtube-private-upload` が必要。
- YouTube upload は private / unlisted のみ許可。public upload は承認endpoint側だけ。
- GET endpoint は状態変更なし。POSTだけ `privacyStatus=public` に変更。
- Secret実値は docs / logs / commit に書かない。
- 完全自動公開は未実装。
- YouTube公式仕様上、未監査API project の upload は private viewing 制限になる可能性がある。承認buttonの public 化が403なら API audit か手動upload fallback が必要。

## live executor remains

- YouTube Data API enable
- OAuth consent / refresh token 取得
- Secret Manager 登録
- fetcher service deploy
- yt-shorts-gen Job update
- 手動1回 smoke: private upload + mail + button public化
- Scheduler 追加は user確認後
