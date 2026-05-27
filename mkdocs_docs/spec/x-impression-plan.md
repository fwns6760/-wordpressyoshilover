# :rocket: X インプレッション向上プラン

!!! info "これは何"

    X (旧 Twitter) でヨシラバーアカウントの ==インプレッション (表示回数) を増やす== ための実装プラン。
    既存の仕組みと新規施策を整理して、 優先順位を付ける。

## :material-target: 基本戦略

X のインプを伸ばす 3 軸:

1. **目を引く投稿にする** — 画像 / 短文 / 結論先出し
2. **見られる時間に投稿する** — 試合中 / 試合直後 の peak window
3. **流れる場所を増やす** — ハッシュタグ / 公式連動 / 連投スレッド

## :material-check-circle: 既存 (production で稼働中)

| 仕組み | 実装場所 | 用途 |
| --- | --- | --- |
| 画像つき投稿 (share-x-cand) | `share_x_handler.py` + GCS PNG | 候補 mail から Web Share API で X app に画像送信 |
| server-side 画像投稿 CLI | `tools/post_x_with_image.py` | tweepy v1.1 media_upload + v2 create_tweet |
| ハッシュタグ自動付与 | `format_as_x_post.py:DEFAULT_HASHTAGS` | `#巨人 #ジャイアンツ` を投稿に自動付与 |
| 動的選手タグ | `publish_notice_email_sender.py:1357` | 検出選手名を `#選手名` として追加 |
| 時間帯ラベル | `x_post_mail_lane.py:203 _TIME_BANDS` | 朝 / 昼 / 午後 / 夕方 / 試合後 |
| 試合中追加発火 | scheduler `x-post-mail-flush-game-1/2` | 19,20,21 時の 15/30/45 分 |
| FAN_VOICE 参考引用 | `x_post_mail_lane.py:1247` | ファン文体模倣 |
| GEMMA_BRANDING | `x_post_branding_gen.py` | 報知 / サンスポ要約からの投稿候補 |
| 名言 BOT | `kobayashi_meigen_mail_lane.py`, `sakamoto_meigen_mail_lane` | 小林誠司 / 坂本勇人の名言投稿 |
| trend 抽出 | `sns_topic_fire_intake.py:282` | category × entity × trend bucket |

ただし `AUTO_TWEET_ENABLED=0` で ==自動投稿は OFF==。 X 投稿は user 手動運用。

## :material-rocket: 実装プラン (優先順位)

### :material-numeric-1-circle: Phase 1: 画像投稿の確実化 (XS)

**今**: mail の「📱 画像つきで X に投稿」 ボタン → Web Share API → 端末次第で画像落ち

**案**: ボタン → ==server-side X API で確実に画像つき投稿==

- 部品は揃っている (`tools/post_x_with_image.py` + `x_post_image_attach_x.py`)
- 必要なのは fetcher service に新 endpoint `/post-x-with-image` を追加して mail ボタンから叩く
- 期待効果: 画像つき投稿率 ≈ 60% → 95%+ ⇒ **インプ 2-3 倍**

### :material-numeric-2-circle: Phase 2: 試合直後 peak window 追加 (XS)

**今**: 試合後の投稿は 22:30 / 23:00 のスケジューラ

**案**: 試合終了直後の peak (21:30 / 21:45 / 22:00 / 22:15) にも候補発火

- `x-post-mail-flush-game-2` を `15,30,45 21 * * *` から `15,30,45 21-22 * * *` に拡張
- もしくは `giants-realtime-peak-15min` を `15,45 18-22 * * *` に拡張
- 期待効果: 試合終了直後の感情ピーク時にインプ集中

### :material-numeric-3-circle: Phase 3: 冒頭フック「結論先出し」 (S)

**今**: 1 行目は静的ヘッダー (例: 「セ・OPS ランキング 📊」)

**案**: 1 行目を ==数字 + 驚き== に置き換え (例: 「★坂本勇人 OPS .950 セリーグ 2 位★」)

- `format_as_x_post.py:226` 周辺の format を改修
- 「驚きの数字」 を冒頭、 ランキング表は 2 行目以降
- 期待効果: 完読率 ↑ → アルゴリズム評価 ↑ → インプ ↑

### :material-numeric-4-circle: Phase 4: トレンドハッシュタグ動的選択 (S)

**今**: `#巨人 #ジャイアンツ` 固定 + カテゴリ別タグ

**案**: 試合相手 / 注目選手 / 曜日で動的に追加 (例: `#G阪戦` `#tokyogiants` `#坂本勇人`)

- 既存の `sns_topic_fire_intake.py:trend_terms` を再利用
- `format_as_x_post.py:DEFAULT_HASHTAGS` を動的化
- 期待効果: ハッシュタグ検索流入

### :material-numeric-5-circle: Phase 5: 公式 X タグ付け (S)

**今**: 投稿本文に公式 @ メンション無し

**案**: 記事 source の公式 X (例: `@TokyoGiants` `@hochi_giants`) を投稿に含める

- oEmbed 主従関係を守る範囲で
- 既存 `x_api_client.py:90` の監視リストから引用
- 期待効果: 公式 / 媒体からの RT / リプライ流入

### :material-numeric-6-circle: Phase 6: 連投スレッド (Reply Chain) (S-M)

**今**: 1 試合 1 ツイート

**案**: 280 字 × 複数ツイートで thread 投稿 (リプライチェーン)

- tweepy v2 `create_tweet(in_reply_to_tweet_id=)` で連結
- データ系記事 (打順別成績 / 9 イニング分析) と相性◎
- 期待効果: thread はインプ 1.5-2 倍 (X アルゴリズム評価)

### :material-numeric-7-circle: Phase 7: 試合中ライブ投稿 (M)

**今**: lineup-auto / postgame-auto の 1 試合 1-2 ツイート

**案**: 得点 / 投手交代 / ピンチごとに自動投稿 (1 試合 9 ツイート級)

- `lineup-auto` / `postgame-auto` の延長
- 試合進行 webhook / RSS 監視
- 期待効果: 試合あたりインプ 9 倍

### :material-numeric-8-circle: Phase 8: Quote retweet (M)

**今**: 引用 RT 無し

**案**: 公式 X 投稿を quote tweet 形式で引用

- tweepy v2 `create_tweet(quote_tweet_id=)`
- 既存 X-post 監視 (`x_api_client.py:90`) と組合せ
- 期待効果: 公式信頼性 + 著作権 OK + 拡散範囲拡大

### :material-numeric-9-circle: Phase 9: X アンケート (poll) (M)

**今**: ポール無し

**案**: 試合前後に「今夜の MVP は?」 等のポール投稿

- tweepy v2 `create_tweet(poll=...)`
- 期待効果: 投票自体がエンゲージメント生成 → インプ拡大

### :material-numeric-10-circle: Phase 10: fan_voice UGC リポスト (M)

**今**: fan_voice_pool は候補 mail で参考引用のみ

**案**: user 確認の上、 quote retweet で UGC 流通

- 既存 `fan_voice_pool` GCS データを再利用
- 期待効果: ファンコミュニティのエンゲージメント拡大

## :material-account-tie: user 判断境界 (§11 該当)

下記 2 つは ==user 判断== が必要 (実装は可能だが解禁判断は user):

### :material-numeric-11-circle: 自動投稿の解禁

- 現状: `AUTO_TWEET_ENABLED=0` + 全 subtype `ENABLE_X_POST_FOR_*=0`
- 解禁すれば 1 日 10 件まで自動投稿可 (`X_POST_DAILY_LIMIT=10`)
- 判断境界: §11「X 投稿解放」
- 推奨: subtype 別段階解禁 (postgame だけ ON → lineup → manager → ...) で safe ramp

### :material-numeric-12-circle: X API Basic tier アップグレード

- 現状: Free tier (write OK / read 401)
- Basic tier ($200/月) で実現可能: 投稿後インプ実測 / トレンド読み取り / 他人 timeline 監視
- 判断境界: §11「コスト増」
- 推奨: Phase 1-6 完了後の効果測定タイミングで検討

## :material-table: 優先順位サマリ

| 番号 | 案 | 実装コスト | 期待効果 | 着手順 |
| --- | --- | --- | --- | --- |
| 1 | 画像投稿確実化 | XS | ★★★ | **1** |
| 2 | peak window 追加 | XS | ★★ | **2** |
| 3 | 冒頭フック改善 | S | ★★ | 3 |
| 4 | トレンドタグ動的化 | S | ★★ | 4 |
| 5 | 公式 @ メンション | S | ★ | 5 |
| 6 | 連投スレッド | S-M | ★★★ | 6 |
| 7 | 試合中ライブ投稿 | M | ★★★ | 7 |
| 8 | Quote retweet | M | ★★ | 8 |
| 9 | poll | M | ★★ | 9 |
| 10 | UGC リポスト | M | ★★ | 10 |
| 11 | 自動投稿解禁 | (user GO) | ★★★★ | user 判断 |
| 12 | Basic tier | (user GO) | ★★ | user 判断 |

## :material-link: 関連 spec

- [X 投稿候補メール (x-post-mail)](x-post-mail.md)
- [通知メール (publish-notice)](publish-notice.md)
- [メール lane の住み分け](mail-lanes.md)
- [Cloud Scheduler 一覧](../operations/scheduler.md)
