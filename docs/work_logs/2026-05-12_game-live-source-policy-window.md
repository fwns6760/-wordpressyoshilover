# 2026-05-12 試合中ソース制御 / DAZN映像レーン 作業記録

## 1. 今回の目的

試合中と試合後で、拾うソースの役割を分ける。

今回決める方針は、試合中に多メディアを拾いすぎて重複・ノイズ・同一プレー量産が増えることを防ぎつつ、DAZN / 日テレ系公式 YouTube などの「巨人の良いプレー映像」は取りこぼさないようにすること。

現時点の方針:

- 試合中は報知系 + DAZN に絞る。
- DAZN はニュース本文の主ソースではなく、巨人の良いプレー映像シグナルとして扱う。
- DAZN は他球団投稿が多いので、巨人関連だけを強く絞る。
- 試合後は多メディアを広く拾う。
- 試合後は報知以外の映像 source も拾う。特に `DRAMATIC BASEBALL` / DAZN YouTube / 巨人公式 YouTube を候補にする。
- 試合後動画は 1 動画 1 記事にせず、原則 1 試合 1 本の「映像まとめ」へ束ねる。
- 「拾う」と「公開記事化」は分ける。試合後に全部拾っても、同じ試合結果記事を量産しない。
- まずは平日ナイター想定で、試合中 window は `17:00-21:30 JST` とする。
- デーゲーム window は今回の初期 scope には入れない。
- AI 事故源として、記憶から再構成 / silent skip / 自己評価 OK を禁止する。

この Markdown 作成時点では、許可する変更は本 Markdown の新規作成のみ。
コード編集・config 編集・commit・push・deploy・env変更・scheduler変更は禁止。

## 2. 今回触る範囲

この時点で触る範囲は、この作業記録 Markdown の新規作成のみ。

- `docs/work_logs/2026-05-12_game-live-source-policy-window.md`

GO 後の実装候補は、以下に限定する。

- 既存 source / role / scheduler / job / config の read-only audit
- 試合中 window 判定の設計
- source role の設計
  - `game_live_primary`
  - `game_live_video_signal`
  - `game_live_verify`
  - `postgame_article_source`
  - `review_only`
- DAZN 巨人映像投稿の抽出条件
- 試合後 YouTube 映像 source の抽出条件
  - `DRAMATIC BASEBALL` (`@ntv_baseball`)
  - DAZN ベースボール YouTube
  - 読売ジャイアンツ公式 YouTube
  - 日テレスポーツ公式 YouTube は review-only 候補
- 報知系 live source の抽出条件
- 試合後多メディア取得の再開条件
- 重複防止のための `game_id / inning / player / event_type` などの検討
- 必要な場合だけ、最小 config / code 修正
- 本 Markdown への作業後追記

## 3. 今回触らない範囲

- 公開済み WP 記事本文 / status
- publish / mail 条件
- Cloud Run env
- Scheduler
- Secret Manager
- GitHub Actions
- X API の live post
- X API 有料 read の追加
- DAZN 動画の保存 / 再配布 / ダウンロード
- YouTube 動画の保存 / 再配布 / ダウンロード
- 画像 / アイキャッチ fallback policy
- 本文品質チケットの修正内容
- manual-intake-service の今回 deploy 済み修正
- RSS / draft-body-editor の本文情報量 follow-up
- noindex / canonical / 301
- frontend / CSS / AdSense UI
- unrelated dirty files

## 4. 影響範囲

GO 後に実装する場合の想定影響範囲:

- 試合中の自動取得対象 source
- 試合中の候補記事数
- DAZN 公式野球 X の巨人関連動画候補
- 報知系 live source の優先度
- 試合後の多メディア取得対象
- 試合後の YouTube 映像候補
- 1 試合 1 本の映像まとめ候補
- 同一試合 / 同一プレーの重複抑制
- dry-run / review-only 出力

公開済み記事は対象外。

## 5. 実行予定テスト

GO 後、まず read-only audit で現状を確認する。

- 実装前 rg / grep
  - `rss_sources.json`
  - `DAZN`
  - `DAZNJPNBaseball`
  - `DRAMATIC BASEBALL`
  - `ntv_baseball`
  - `youtube`
  - `UCpj_nD9850tykDqIrjtIXdg`
  - `UCyeDNNizMGbVsn_8Ttc3FIw`
  - `UCXxg0igSYUp0tqdd6luPEnQ`
  - `hochi`
  - `game_id`
  - `lineup-auto`
  - `postgame-auto`
  - `broadcast-auto`
  - `source role`
  - `scheduler`
- 現在の source role / source type の棚卸し
- 現在の 17:00-21:30 に動く scheduler / job の read-only 確認
- 再現テスト赤
  - 試合中 window では報知 + DAZN 以外の通常メディアを live article source にしない
  - DAZN 投稿は巨人関連語がない場合除外
  - DAZN 投稿が巨人戦でも相手チームだけの好プレーなら除外
  - DAZN 投稿が巨人選手 + 強イベント + 動画なら候補化
  - 21:30 以降は多メディア取得に戻る
  - 試合後 YouTube は巨人関連タイトルだけ候補化
  - `DRAMATIC BASEBALL` は postgame video source として扱う
  - 日テレスポーツ公式は review-only に留める
  - 同じ `game_id` のハイライト / 好プレー短尺を 1 試合 1 本に束ねる
  - デーゲームは今回 window の対象外
- 修正後 targeted test
- 関連 test
- 変更 Python がある場合は `compileall`
- 変更 Python がある場合は AST parse
- `python3 -m unittest discover -s tests`

deploy / scheduler 変更が必要になった場合は、別 GO 後に実施する。

## 6. STOP条件

以下の場合は停止する。

- 17:00-21:30 を既存 scheduler だけでは安全に表現できない場合
- Scheduler 変更が必要になった場合
- Cloud Run env 変更が必要になった場合
- X API 有料 read が必要になった場合
- DAZN の利用が embed / link を超えて、保存 / 再配布 / 直接転載になりそうな場合
- YouTube の利用が embed / link を超えて、保存 / 再配布 / 直接転載になりそうな場合
- YouTube channel ID / handle / RSS URL を一次確認できない場合
- source URL / channel ID / RSS URL を記憶や推測で補いそうになった場合
- 除外理由 / skip reason / review reason を記録できない場合
- 実テスト・dry-run・ログ確認なしに「OK」と判断しそうになった場合
- DAZN 投稿の巨人関連判定が弱く、他球団投稿が混ざる場合
- 放送局 YouTube の巨人関連判定が弱く、他競技 / 他球団 / 番組宣伝が混ざる場合
- 試合中に報知以外の多メディア記事が混ざる場合
- 試合後の「全部拾う」が、同一試合結果記事の量産につながる場合
- デーゲーム対応を同じ便で入れたくなる場合
- 公開済み記事修正が必要になった場合
- publish / mail / env / scheduler / Secret に触る必要が出た場合
- unrelated dirty files を巻き込みそうな場合
- full suite が赤のまま原因説明できない場合

## 7. 禁止事項

- 記憶からソース仕様を再構成する
- 調べた URL ではなく、記憶上の URL / handle / channel ID を config に入れる
- silent skip で理由を残さない
- 自己評価 OK だけで終える
- テスト / dry-run / readback / log evidence なしに正常判定する
- 試合中に多メディアを無差別に拾う
- DAZN の他球団投稿を巨人記事候補に混ぜる
- DAZN 動画を保存 / 再配布 / ダウンロードする
- YouTube 動画を保存 / 再配布 / ダウンロードする
- channel ID / RSS URL を未確認のまま config に入れる
- 放送局 YouTube を無差別に article source にする
- X API live post を行う
- publish / mail 条件をついでに変える
- env / scheduler / Secret / GitHub Actions をついでに変える
- `git add -A`
- ついで修正
- frontend / AdSense UI 変更
- 公開済み WP 記事変更

## 8. 想定されるデグレ

- 試合中に報知以外を切ることで、速報候補が減る
- 報知が遅い試合では試合中記事が薄くなる
- DAZN の巨人判定が厳しすぎて良い映像を取りこぼす
- DAZN の巨人判定が緩すぎて他球団映像が混ざる
- 17:00-21:30 固定だと延長戦や遅延に弱い
- 17:00-21:30 固定だと土日デーゲームに対応できない
- 21:30 以降の多メディア取得で、同一試合結果記事が増えすぎる
- 試合後 YouTube を拾いすぎて、1 動画 1 記事の量産になる
- 日テレスポーツ公式から他競技 / 番組ニュースが混ざる
- DRAMATIC BASEBALL / DAZN / 巨人公式 YouTube の同一プレー重複が増える
- source role 追加で既存 routing test が落ちる
- job / scheduler の境界を誤ると publish / mail に波及する

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-12 JST | work log 作成 | user 方針「試合中は報知 + DAZN。DAZN は巨人の良いプレー映像。試合後は多メディアを全部拾う。試合中 window は 17:00-21:30」を別チケットとして記録。コード編集・config編集・commit・push・deploy・env変更・scheduler変更は未実施。 |
| 2026-05-12 JST | 試合後動画 ticket 化 | user 方針「試合後の巨人ファインプレー集など、日テレ / 放送局 YouTube も欲しい」を反映。`DRAMATIC BASEBALL` / DAZN YouTube / 巨人公式 YouTube / 日テレスポーツ review-only を候補化。Markdown 追記のみで、コード編集・config編集・commit・push・deploy・env変更・scheduler変更は未実施。 |
| 2026-05-12 JST | URL確認 | 実ページ / feed readback で確認。`DRAMATIC BASEBALL` YouTube = `@ntv_baseball` / `UCpj_nD9850tykDqIrjtIXdg`、巨人公式 YouTube = `@YOMIURI_GIANTS` / `UCXxg0igSYUp0tqdd6luPEnQ`、DAZN YouTube = `@DAZNJapanBaseball` / `UCyeDNNizMGbVsn_8Ttc3FIw`。`@DAZNJPNBaseball` は YouTube では 404、DAZN 公式Xとして RSSHub `200` を確認。 |
| 2026-05-12 JST | 再現テスト赤 | `tests.test_rss_fetcher_observability` と `tests.test_youtube_ob_source_registry` に失敗テストを追加。未実装 helper / 未登録 DAZN registry で expected red を確認。 |
| 2026-05-12 JST | 実装修正 | `rss_fetcher` に試合中 source policy を追加。試合あり + `17:00-21:30 JST` のみ、`game_live_primary` / `game_live_video_signal` 以外の source fetch を skip し、skip event と run summary に理由を残す。 |
| 2026-05-12 JST | config修正 | 報知系に `game_live_primary`、DAZN X に `game_live_video_signal` + `media_quote_only` + `review_only` を追加。YouTube review source に DAZNベースボールを追加し、巨人公式 / DRAMATIC BASEBALL / DAZN に `postgame_video_source` を明示。 |
| 2026-05-12 JST | テスト緑 | targeted / related / JSON / compileall / full suite を実行。sandbox 内 full suite は localhost socket 権限で3件失敗、権限付き再実行で `3437 tests OK`。deploy / env / scheduler / WP公開記事変更は未実施。 |

## 10. Regression Memo欄

- 試合中と試合後を同じ source policy にしない。
- 試合中は報知系を主軸にし、DAZN は巨人の良いプレー映像シグナルとして扱う。
- 巨人公式は必要なら確認用。試合中速報の主ソースにはしない。
- DAZN は他球団投稿が多い。巨人語 / 巨人選手 / 巨人戦 / 強イベント / 動画ありの条件で強く絞る。
- DAZN 単独で即 publish しない。まず review / draft が安全。
- 試合後は多メディアを広く拾う。ただし同一 topic を束ね、同じ試合結果記事を量産しない。
- 試合後動画は報知とは別レーン。`DRAMATIC BASEBALL` / DAZN / 巨人公式 YouTube を優先し、日テレスポーツ公式は review-only から始める。
- YouTube は embed / link のみ。保存 / 再配布 / ダウンロードはしない。
- YouTube source は channel ID / RSS URL を確認してから config 化する。
- 試合後映像は 1 動画 1 記事にしない。原則 `game_id` 単位で 1 本の映像まとめに束ねる。
- AI 事故源は「記憶から再構成」「silent skip」「自己評価 OK」。この3つが発生しそうなら止める。
- URL / channel ID / RSS URL は、repo 内設定と外部一次情報または実 feed readback で確認する。
- skip / review / exclude には理由を残す。
- 「動いたはず」ではなく、テスト・dry-run・readback・ログの evidence で完了判断する。
- 17:00-21:30 はまずナイター用。デーゲームは別判断。
- 実装時は、再現テスト赤 → 修正 → 追加テスト緑 → 関連緑 → 全件緑の順に進める。

## 試合後動画 source 候補メモ

実装前に URL / channel ID / RSS の再確認が必要。

### 優先候補

- `DRAMATIC BASEBALL`
  - handle: `@ntv_baseball`
  - channel: `https://www.youtube.com/@ntv_baseball`
  - channel_id: `UCpj_nD9850tykDqIrjtIXdg`
  - rss: `https://www.youtube.com/feeds/videos.xml?channel_id=UCpj_nD9850tykDqIrjtIXdg`
  - role候補: `postgame_video_source`
  - 用途: 巨人戦の好プレー / 走塁 / 守備 / ハイライト / 中継映像由来の短尺

- `DAZNベースボール YouTube`
  - channel_id候補: `UCyeDNNizMGbVsn_8Ttc3FIw`
  - rss候補: `https://www.youtube.com/feeds/videos.xml?channel_id=UCyeDNNizMGbVsn_8Ttc3FIw`
  - role候補: `postgame_video_source`, `review_only`
  - 用途: 試合後ハイライト / 短尺好プレー / ホームラン / ファインプレー
  - 注意: 実装前に YouTube feed で公式性と最新投稿を再確認する

- `読売ジャイアンツ公式 YouTube`
  - channel_id: `UCXxg0igSYUp0tqdd6luPEnQ`
  - rss: `https://www.youtube.com/feeds/videos.xml?channel_id=UCXxg0igSYUp0tqdd6luPEnQ`
  - role候補: `official_video_source`
  - 用途: 公式動画 / インタビュー / 舞台裏 / 球団発表系

### review-only 候補

- `日テレスポーツ公式`
  - channel_id候補: `UCWt0yfrBaUk148rxaOp4b4w`
  - rss候補: `https://www.youtube.com/feeds/videos.xml?channel_id=UCWt0yfrBaUk148rxaOp4b4w`
  - role候補: `review_only`
  - 理由: スポーツ全般のため、巨人以外 / 他競技 / 番組系ノイズが多い可能性がある

## 作業後追記

### 1. 実際に変更したファイル

- `src/rss_fetcher.py`
- `config/rss_sources.json`
- `config/youtube_video_sources.json`
- `config/youtube_ob_sources.json`
- `tests/test_rss_fetcher_observability.py`
- `tests/test_youtube_ob_source_registry.py`
- `tests/test_game_live_source_policy_config.py`
- `docs/work_logs/2026-05-12_game-live-source-policy-window.md`

### 2. diff概要

- 試合日かつ `17:00-21:30 JST` の間だけ、source fetch 前に試合中 source policy を適用。
- 許可 role は `game_live_primary` / `game_live_video_signal` のみ。
- 試合中に除外した source は `game_live_source_policy_skip` event で理由・source名・roleを記録。
- run summary に `game_live_source_policy_active` / `game_live_source_policy_window` / `game_live_source_policy_skipped_sources` を追加。
- 報知系 source に `game_live_primary` を付与。
- DAZN公式Xを `media_quote_only` + `game_live_video_signal` + `review_only` として追加。
- DAZN YouTube を `@DAZNJapanBaseball` / `UCyeDNNizMGbVsn_8Ttc3FIw` で confirmed registry に追加。
- 巨人公式 / DRAMATIC BASEBALL / DAZN の YouTube source に `postgame_video_source` と `review_only` を明示。
- `@DAZNJPNBaseball` は YouTube ではなく X 用として扱うメモを config に残した。

### 3. 実行したテスト

- `python3 -m unittest tests.test_rss_fetcher_observability tests.test_youtube_ob_source_registry`
- `python3 -m unittest tests.test_rss_fetcher_observability tests.test_youtube_ob_source_registry tests.test_game_live_source_policy_config`
- `python3 -m unittest tests.test_tag_page_scraper tests.test_social_video_notice_validator tests.test_youtube_ob_source_registry tests.test_game_live_source_policy_config`
- `python3 -m compileall src/rss_fetcher.py tests/test_rss_fetcher_observability.py tests/test_youtube_ob_source_registry.py tests/test_game_live_source_policy_config.py`
- `python3 -m json.tool config/rss_sources.json`
- `python3 -m json.tool config/youtube_video_sources.json`
- `python3 -m json.tool config/youtube_ob_sources.json`
- `python3 -m unittest discover -s tests`
- sandbox 権限で localhost socket が禁止されたため、同じ全件テストを権限付きで再実行。

### 4. テスト結果

- 再現テスト赤: helper 未実装 / DAZN registry 未登録で expected red。
- targeted: `18 tests OK`
- related: `65 tests OK`
- JSON: 3 config とも parse OK
- compileall: OK
- full suite sandbox: `3437 tests`, `errors=3`。原因は `HTTPServer(("127.0.0.1", 0))` の `PermissionError: Operation not permitted`。
- full suite 権限付き再実行: `3437 tests OK`

### 5. 残った懸念

- 今回は平日ナイター window のみ。デーゲームは別判断。
- 試合が延長して 21:30 を超えた場合、21:30 以降は多メディア取得に戻る。
- DAZN X は `media_quote_only` / `review_only` であり、単独記事化はしない。
- YouTube 動画は review source 登録まで。試合後の「1試合1本の映像まとめ」生成ロジックは今回未実装。
- `check_giants_game_today()` が試合検出に失敗した場合、試合中 policy は発動しない。

### 6. 新しく見つかったデグレ

- 新規の機能デグレは現時点で確認なし。
- 既存の sandbox 制約として、全件テスト中の localhost HTTPServer は権限なしだと失敗する。

### 7. 追加した回帰テスト

- 試合中 window で通常 `article_source` がブロックされること。
- `game_live_primary` の報知、`game_live_video_signal` の DAZN が許可されること。
- `21:30 JST` 境界で試合中 policy が終了すること。
- `_main()` が試合中に非live sourceを fetch せず、skip event と summary を出すこと。
- `rss_sources.json` の `game_live_primary` が報知系だけであること。
- DAZN X が article source ではなく video signal / review-only であること。
- postgame video source に巨人公式 / DRAMATIC BASEBALL / DAZN が登録されていること。
- DAZN YouTube registry が `media` / `confirmed` で lookup できること。

### 8. 次回触ってはいけない範囲

- 公開済み WP 記事本文 / status
- publish / mail 条件
- env / Secret / Scheduler / Cloud Run 設定
- X API live post / 有料 read
- DAZN / YouTube 動画の保存・再配布・ダウンロード
- アイキャッチ policy
- manual-intake-service 本文密度修正
- frontend / AdSense UI
- unrelated dirty files
