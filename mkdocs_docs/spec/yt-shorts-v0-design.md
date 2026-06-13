# YouTube Shorts 自動生成 v0 設計(yt-shorts Phase 1)

status: Phase 1.5 repo 実装 + OAuth secret setup helper 完了(2026-06-13)。user 側 OAuth / Secret Manager 登録は完了。deploy / Scheduler / live mail は未実行
位置づけ: 収益化ではなく **サイト/X への導線・認知装置**。巨人市場の飽和に対し「データ図解ショート」枠(実況切り抜き勢と非競合)を取る。

## ゴール / 非ゴール

- ゴール: 1日1本、既存データ資産から60秒縦型動画を自動生成 → YouTube private upload → mail承認 → buttonで公開のループを回す
- 非ゴール(Phase 1.5ではやらない): 収益化、長尺解説、実況/切り抜き、完全無人公開、複数本/日

## 制約(lock)

1. **映像・写真の権利**: 試合映像/中継スクショ/マスコミ写真/選手写真は1秒も使わない。自前生成の図表・テキスト・イラスト素材のみ(完全権利安全)
2. **追加課金ゼロ**: VOICEVOX(self-host、無料・クレジット表記必須) / matplotlib+PIL / ffmpeg / YouTube Data API(quota無料)。LLMは既存Gemini無料枠のみ
3. **数字はLLMに生成させない**: 台本テンプレにデータ直挿し。LLMは語り口調整のみで、生成後に数値一致verifyを通らなければabort(数値guard)
4. **公開はuser承認後**: Phase 1.5は private upload + mail button 承認。完全自動公開はPhase 2のuser判断
5. 選手名はフルネーム・敬称なし、ヨシラバーボイス(データ辛口×巨人愛)はX-postと同ruleを流用

## アーキテクチャ(Cloud Run Job `yt-shorts-gen`、新規)

```
1. ネタ選定   notable payload 再利用(_build_notable_data_from_targets 相当)
              優先度: 連続記録更新 > 週間MVP(月曜) > 好調指標 > 年俸コスパ > MLBの2人
2. 台本生成   テンプレ文型 + Gemini flash(無料枠)で語り口調整 → 数値guard verify
3. フレーム   matplotlib/PIL で 1080x1920 静止フレーム3〜5枚(サイトと同オレンジ系トーン)
4. 音声       VOICEVOX engine(同Job内で 127.0.0.1 起動、常駐サービスなし)。47〜55秒、推奨voice=青山龍星(男声・落ち着き、辛口系に合う)
5. 合成       ffmpeg: フレーム+音声+字幕焼き込み(無音視聴対応) → MP4 → GCS保存
6. private upload YouTube Data API `videos.insert` で `privacyStatus=private`
7. 承認mail   既存mail基盤と同経路。動画GCS署名URL+YouTube確認URL+公開button+台本全文+元データを送付
8. 公開       mail button → fetcher `/yt-shorts-publish` → YouTube Data API `videos.update` で `privacyStatus=public`
```

## 動画フォーマット(60秒)

- 0-3s   フックカード(例「泉口友汰、7試合連続安打中」)
- 3-45s  データ展開カード/グラフ 2〜3枚(1枚10〜15秒)
- 45-55s ひとこと辛口+巨人愛締め(ヨシラバーボイス)
- 55-60s CTA「詳細はヨシラバーで」。概要欄に `/data/notable?v=yt` リンク(導線計測用パラメータ)
- 概要欄にVOICEVOXクレジット表記(利用規約)

## スケジュール / コスト

- scheduler 1本(毎朝7:30 JST、前夜試合反映後・MLB朝更新前) → +$0.10/月
- 動画生成 1本数分のCloud Run実行 → 無料枠内
- 合計増分: 月¥15程度

## ファイル構成

- `src/yt_shorts_topic.py` — ネタ選定(優先度ロジック)
- `src/yt_shorts_script.py` — 台本テンプレ+数値guard
- `src/yt_shorts_render.py` — フレーム生成+ffmpeg合成
- `src/yt_shorts_gen.py` — orchestrator(選定→台本→render→TTS→GCS→YouTube private upload→mail)
- `src/yt_shorts_youtube.py` — YouTube Data API HTTPS client(refresh token / resumable upload / privacy update)
- `src/yt_shorts_youtube_token.py` — `/yt-shorts-publish` 用 HMAC token
- `src/yt_shorts_publish_handler.py` — mail公開button handler(GET確認 / POST公開)
- `Dockerfile.yt_shorts` / `cloudbuild_yt_shorts.yaml`
- `scripts/setup_yt_shorts_phase15_gcp.sh` — authenticated executor 用 live deploy helper(Cloud Build + fetcher update + Job create/update、Scheduler は既定skip)
- `tests/test_yt_shorts_topic.py` / `tests/test_yt_shorts_script.py` / `tests/test_yt_shorts_render.py`
- `bin/run_yt_shorts_with_voicevox.sh` — Job開始時だけ公式VOICEVOX CPU engineをlocal起動して終了時に停止

実装時の安全側既定:

- `python -m src.yt_shorts_gen` は dry-run。`--live` を渡した時だけ GCS upload + 承認 mail。
- YouTube upload はさらに `--youtube-private-upload` または `YT_SHORTS_YOUTUBE_PRIVATE_UPLOAD=1` が必要。`--live` だけでは従来通りYouTubeへ触らない。
- GCP Job image は公式 `voicevox/voicevox_engine:cpu-latest` をベースにし、`VOICEVOX_BASE_URL=http://127.0.0.1:50021` を既定にする。別常駐Serviceは作らない。
- local smoke だけ `--allow-silent-tts` で無音 wav を許可。
- Phase 1.5 は YouTube API へ private upload するが、公開は mail button の user click まで行わない。

## GCP 最安構成 lock(2026-06-13)

- `yt-shorts-gen` は Cloud Run Job 1 本。常駐 Cloud Run Service は作らない。
- VOICEVOX は同一コンテナ内で `/opt/voicevox_engine/run --host 127.0.0.1 --port 50021 --disable_mutable_api` としてバックグラウンド起動し、MP4生成後に停止する。
- `YT_SHORTS_EMBEDDED_VOICEVOX=1` が既定。検証時だけ `0` にして外部 `VOICEVOX_BASE_URL` を使える。
- GCS 上の MP4 は承認用。bucket lifecycle で 14〜30 日削除を推奨。
- Scheduler は新規なら 7:30 JST 1 本だけ。さらに安くする場合は既存朝便から Job execute へ相乗りする。

## Phase 1.5 半自動公開 flow(2026-06-13)

- `yt-shorts-gen --live --youtube-private-upload`:
  - MP4をGCSへ保存
  - YouTubeへ `privacyStatus=private` で upload
  - `FETCHER_PUBLIC_BASE_URL` または `YT_SHORTS_APPROVAL_BASE_URL` から `/yt-shorts-publish?video_id=...&token=...` を生成
  - HTML mail に「MP4を開く」「YouTubeで確認」「Studioで編集」「公開する」を出す
- `GET /yt-shorts-publish`: token検証 + 確認画面だけ。状態変更なし
- `POST /yt-shorts-publish`: token検証後、対象 `video_id` の `privacyStatus` を `public` に変更
- token:
  - env `YT_SHORTS_APPROVAL_TOKEN_SECRET` 優先、なければ `PUBLISH_BUTTON_TOKEN_SECRET` fallback
  - 既定TTLは7日
- YouTube OAuth:
  - 必要scope: `https://www.googleapis.com/auth/youtube`
  - `YT_SHORTS_YOUTUBE_CLIENT_ID`
  - `YT_SHORTS_YOUTUBE_CLIENT_SECRET` または `YT_SHORTS_YOUTUBE_CLIENT_SECRET_NAME`
  - `YT_SHORTS_YOUTUBE_REFRESH_TOKEN` または `YT_SHORTS_YOUTUBE_REFRESH_TOKEN_SECRET_NAME`
  - 実値はchat / log / commitへ出さない
- 注意: YouTube公式仕様上、2020-07-28以降に作成された未監査API project の `videos.insert` upload は private 制限になる可能性がある。`/yt-shorts-publish` の `videos.update` が `forbiddenPrivacySetting` 等で失敗する場合は、YouTube API project audit を通すか、Phase 1 の手動uploadに戻す。

## 事故ガード

- 数値guard: 台本中の全数字が元データと一致しなければabort+失敗mail(silent skip禁止)
- 1日1本cap
- 生成失敗時はmailで失敗通知
- live upload 後は承認mail前に `uploaded` history を先に書く。SMTP失敗時も同日の重複生成を避ける

## Phase 1 repo validation(2026-06-13)

- 対象テスト: `python3 -m pytest -q tests/test_yt_shorts_topic.py tests/test_yt_shorts_script.py tests/test_yt_shorts_render.py tests/test_yt_shorts_gen.py`
- local smoke: `python3 -m src.yt_shorts_gen --topic-json <fixture> --allow-silent-tts --no-mail --output-dir /tmp/yt_shorts_smoke`
- compile: `python3 -m compileall -q src/yt_shorts_topic.py src/yt_shorts_script.py src/yt_shorts_render.py src/yt_shorts_gen.py`
- AST parse: `python3 - <<'PY' ... ast.parse(...) ... PY`

## Phase 1.5 live executor steps(未実行)

OAuth / Secret Manager setup は user authenticated shell で完了済み:

- `yt-shorts-youtube-client-id`
- `yt-shorts-youtube-client-secret`
- `yt-shorts-youtube-refresh-token`
- `yt-shorts-approval-token-secret`

次の live mutation は Codex sandbox ではなく、authenticated executor が repo root で実行する。

```bash
scripts/setup_yt_shorts_phase15_gcp.sh
```

script が行うこと:

1. `cloudbuild_yt_shorts.yaml` で `yt-shorts-gen` image を build/push
2. root `Dockerfile` で `yoshilover-fetcher` image を build/pushし、`/yt-shorts-publish` route を service へ反映
3. `yoshilover-fetcher` service に YouTube OAuth / approval token secret bindings を追加(`--update-secrets`)
4. Cloud Run Job `yt-shorts-gen` を create/updateし、`--live --youtube-private-upload` args と mail bridge + YouTube secret bindings を設定
5. Scheduler は既定で作らない。private upload + mail + publish button smoke が通った後だけ `CREATE_SCHEDULER=1 scripts/setup_yt_shorts_phase15_gcp.sh`

1回だけ live smoke を同 script 末尾で実行したい場合:

```bash
EXECUTE_LIVE_SMOKE=1 scripts/setup_yt_shorts_phase15_gcp.sh
```

1. Cloud Build: `gcloud builds submit --config cloudbuild_yt_shorts.yaml --substitutions _TAG=yt-shorts-<shortsha> .`
2. Cloud Run Job `yt-shorts-gen` を新規作成または更新。env/secret は既存 mail bridge と `YT_SHORTS_GCS_BUCKET`、YouTube OAuth secret、`FETCHER_PUBLIC_BASE_URL` を使う
3. fetcher service image に `/yt-shorts-publish` endpoint を deploy
4. まず `--topic-json` + `--allow-silent-tts` + `--no-mail` 相当で render smoke
5. 次に `--live --youtube-private-upload` を手動executeし、private upload + HTML mail を1通だけ確認
6. user がmailから公開buttonを押し、YouTube上でpublic化を確認。未監査API project制限で403になる場合はここでSTOP
7. user 承認後だけ Scheduler 1本(毎朝 7:30 JST)を作成。完全自動公開はまだしない

## 効果測定 / 撤退基準

- 概要欄リンク `?v=yt` でサイト流入を計測、YouTube Studioで再生数/視聴維持率
- 4週間運用 → 平均視聴維持率と再生数をレビューし、継続 / フォーマット変更 / 撤退をuser判断

## Phase分割

- Phase 1: 生成→mail→user手動アップロード
- Phase 1.5(本設計): YouTube Data API自動アップロード(private→承認でpublic)。OAuth refresh tokenをSecret Manager
- Phase 2: 自動公開+企画型(あの日の巨人 等)+本数増(user判断)

## user作業(1件のみ)

- YouTubeチャンネルの新規開設(ブランドアカウント推奨)。Phase 1はmail+手動アップロードなので、実装と並行で間に合えばOK
- **完了(2026-06-12)**: チャンネル開設済 = 「BaseBall Academy ヨシラバー」 https://www.youtube.com/@baseballacademy9623

## user作業(Phase 1.5 OAuth)

完全代行できない箇所は **Google Cloud Consoleで Desktop OAuth client を作る操作** と、ブラウザで YouTube channel owner として許可する操作。API有効化とSecret Manager登録は helper script で実行できる。

1. Google Cloud Console で project `baseballsite` を開く
2. APIs & Services → Credentials → Create credentials → OAuth client ID
3. Application type = `Desktop app`
4. 生成された `client_id` / `client_secret` を手元に控える(チャットには貼らない)
5. authenticated shell で実行:

```bash
python3 scripts/setup_yt_shorts_youtube_oauth.py --project baseballsite
```

script が行うこと:

- `youtube.googleapis.com` を enable
- `client_id` / `client_secret` を端末で入力
- browser に OAuth URL を開く
- YouTube channel owner account で許可
- refresh token を取得
- Secret Manager に以下を保存
  - `yt-shorts-youtube-client-id`
  - `yt-shorts-youtube-client-secret`
  - `yt-shorts-youtube-refresh-token`
  - `yt-shorts-approval-token-secret`

Secret 実値は terminal / chat / commit に出さない。

2026-06-13 user 実行結果:

- OAuth callback: `OAuth completed. You can close this tab and return to the terminal.`
- Secret Manager 登録完了。Secret 実値は chat に貼られていない
- runtime mapping:
  - `YT_SHORTS_YOUTUBE_CLIENT_ID=yt-shorts-youtube-client-id:latest`
  - `YT_SHORTS_YOUTUBE_CLIENT_SECRET=yt-shorts-youtube-client-secret:latest`
  - `YT_SHORTS_YOUTUBE_REFRESH_TOKEN=yt-shorts-youtube-refresh-token:latest`
  - `YT_SHORTS_APPROVAL_TOKEN_SECRET=yt-shorts-approval-token-secret:latest`
