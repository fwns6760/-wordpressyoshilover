# 451 XPOST video-nostalgia-radar 実装 (今日の動画候補3件をメールに)

> **2026-06-01 PIVOT (user)**: 「YouTube いらない」「X のポストから拾える?」「X に受け込む形」。
> 外部リンク (YouTube) は X でリーチが落ちるため、 **YouTube channel scan を廃止**し、
> **RSSHub で拾った巨人系 X account の投稿そのものを「引用RT/リプライ」候補**にする方式へ変更。
> X 内完結・本文に外部リンクを貼らない・一記事一本。 commit `deee586`、 metric `x_buzz_post`。
> live 確認: 実投稿から リチャード/吉川尚輝/竹丸和幸 の引用RT候補 (x.com/.../status/...) 生成。
> (旧 YouTube channel scan 実装 730bb2a〜833db70 は廃止。 §4 以下は旧設計の記録として残置)
>
> **半自動 + ヨシラバー voice (commit `a63e36d`)**: HTML メールに「🐦 引用RTで X に投稿」ボタン
> (`encode_x_quote_intent_url` = text=コメント&url=元ツイートの quote intent)。 タップ → X が
> 引用RT(コメント+元ツイート入り)で開く → 投稿押すだけ = 半自動。 X API 不使用 (client 側 intent)、
> 公開X自動投稿でもない (user が最後に押す)。 コメントは ヨシラバー voice の template
> (ファン目線・フルネーム・敬称なし・媒体ぶらず hashtag 無し、 LLM 不使用)。

## 1. ticket header

- **ticket id**: 451
- **status**: LIVE_DEPLOYED_VERIFIED (2026-06-01。 image `video-radar-eb2f583`、 ENABLE_X_POST_VIDEO_RADAR=1。 公開 X 自動投稿への昇格は別途 §11 user 判断)
  - verify: exec `x-post-mail-lane-kq85n` SUCCESS、 log「video_radar buzz players: 竹丸和幸18/リチャード5/…」
    「video_radar: built 3 candidates (scanned 38 channels)」「video_radar appended: base=2 video=3 total=5」「mail send result: status=sent」
  - **既知の改善余地 (Phase 2)**: buzz 選手 NER がタイトルに名前が出るだけ/誤検出の動画を拾うことがある
    (例: 岸田が検出された西武の動画)。 人がメールで選ぶ前提で許容だが、 Giants-relevance gate / NER 精度上げが次手
  - scope 更新 (user 2026-06-01): チャンネルは **全部対象** (status=excluded のみ除外)。 拾う基準は「懐かしい・ファンが面白い」
  - **X バズ駆動 (user「RSSハブ入れて」)**: 445 と同じ自前 RSSHub (X→RSS、 X API 不使用) で巨人系 X 4 account を読み、
    言及の多い = いま X でバズってる選手を検出 → その選手の公式/OB 動画を最優先 (+3「Xで話題」tag) で拾う
  - 実装: `src/video_radar.py` (load_radar_channels / classify_video / gather_radar_videos / fetch_buzzing_players)
    + `x_post_mail_lane.build_video_radar_candidates` + `run_x_post_mail` ENABLE_X_POST_VIDEO_RADAR (default OFF)
  - commit `730bb2a` (YouTube radar) → `eb2f583` (RSSHub buzz 駆動)。 tests 144 pass
  - live 確認: RSSHub buzz 本日 竹丸和幸18/リチャード5/佐々木俊輔3 等、 公式/OB 動画候補も生成確認
  - 出力は URL 紹介のみ・転載しない / Gemini・X API 不使用 / 追加課金なし (RSSHub は 445 用に既稼働)
- **owner**: Claude Code
- **lane**: x-post-mail-lane (候補生成のみ。 公開 X 自動投稿はしない)
- **created**: 2026-06-01
- **parent**: 450 (video-nostalgia-radar 設計 doc) — source of truth は 450
- **related**: 448 (data split 候補、 同じ candidate→mail パターン) / 385 (YouTube caption) / 449 (data content)
- **priority**: P2

## 2. ゴール

公式動画 (球団公式 YouTube RSS + 公式 X oEmbed 等) を read-only 巡回し、 当日の文脈
(試合 / スタメン / roster 変動 / 誕生日・記念日) とつながる動画を選んで、 既存 x-post-mail
候補メールに **「今日の動画候補 3 件」** として出す。 見どころ + data 文脈の下書きを添える。
**転載しない / 公式埋め込み前提 / 公開 X 自動投稿はしない (候補=メールまで)**。

## 3. 安全ソース (450 §4 の confirmed のみ)

- ◎ 読売ジャイアンツ公式 YouTube (`config/youtube_video_sources.json` UCXxg0igSYUp0tqdd6luPEnQ)
- ○ DRAMATIC BASEBALL / DAZN ベースボール (同 config、 confirmed)
- △ OB 棚 (`config/youtube_ob_sources.json`) は status=confirmed のみ
- 公式 X は oEmbed のみ。 NPB 公式 YT は channel_id を web verify 後に追加 (別 read-only 便)
- 「Unknown channels are not silently confirmed」継承

## 4. 実装スコープ (Phase 1)

### 4.1 動画抽出 (read-only)
- 新 `src/video_radar.py`: 公式 YouTube RSS (`feeds/videos.xml?channel_id=...`) を取得し、
  各 entry から **タイトル / 動画URL / 公開日 / video_id** を抽出。
- タイトルから **選手名 (giants_roster alias) / 対戦相手 / 一軍-二軍 marker / 記念語** を抽出
  (既存 `_PROGRAM_MARKERS` / roster alias loader / NER 再利用)。
- LLM 不使用 (Gemini 増やさない)。 抽出は正規表現 + roster alias。

### 4.2 今日の文脈スコア
- insight.db (read-only) の `games` (当日対戦) / `lineups` (当日スタメン) / roster 変動 /
  誕生日 calendar と突合し、 各動画に「今日つながり度」スコアを付与。
- 型タグ (450 §5: 名場面回顧 / 今日とつながる / 若手過去 / 復帰昇格 / 記念日 等) を付与。

### 4.3 候補化 (448 と同じ Candidate→mail)
- `build_video_radar_candidates(...) -> list[Candidate]`: 上位 N(default 3)を Candidate 化。
  - `post_text`: 見どころ + 1 行 data 文脈 + 公式動画 URL (埋め込み紹介)。 選手フルネーム・敬称なし。
  - `draft_text`: 根拠 (公式チャンネル名 / 公開日 / video_id / 権利チェック印「公式埋め込みのみ」)。
  - `signature`: `video_radar|{video_id}` で dedup (同一動画の連投抑制)。
  - `metric`: `video_radar`。 `source_material_type`: `video_radar`。
- `run_x_post_mail.py`: `ENABLE_X_POST_VIDEO_RADAR` (default OFF) で pick_candidates 後に append
  (448 の data_split と同じ injection 点・同じ flag パターン)。

### 4.4 安全ゲート
- confirmed channel のみ巡回。 自前で動画ファイル/切り抜きを保存・再アップしない (URL 紹介のみ)。
- oEmbed/埋め込み可否を確認できないものは候補化しない (safe-by-default)。
- 非公式は原則使わない (450 §7)。

## 5. 触らない範囲

- 公開 X 自動投稿 path / X live posting (候補=メールまで)
- 既存 candidate builder (data_split / comment / news / fan) は不可触 (新 builder 追加のみ)
- rss_fetcher 本線 / publish-notice / guarded-publish / data-site publisher / scheduler / SEO・index
- Gemini call を増やさない。 X API は使わない (YouTube は公開 RSS、 X は oEmbed)

## 6. test 計画

- 動画抽出: RSS fixture からタイトル→選手/対戦/軍/記念語 抽出
- 文脈スコア: 当日 games/lineups と突合して「今日つながり」型が上位に来る
- 候補化: フルネーム・敬称なし、 公式 URL 含む、 signature dedup、 char count
- flag OFF で既存挙動不変 / pick_candidates 統合の回帰

## 7. cost / 副作用

- 公式 YouTube 公開 RSS の HTTP GET のみ (read-only)。 API key 不要、 追加コスト ¥0、 LLM 不使用
- 公開影響なし (メール候補。 user 手動投稿)

## 8. phase / next action

- **Phase 1** (本 ticket、 user GO 後): 公式 YT RSS + 当日文脈 + 候補→メール。 flag default OFF → 観察後 ON
- **Phase 2** (別 ticket): NPB 公式 YT 追加 / 記念日 calendar 拡充 / 公式 X oEmbed 巡回 / 型別精度調整
- **公開 X 自動投稿への昇格は §11 user 判断** (別途)
- 着手前に NPB 公式 YT channel_id の web verify 便 (read-only) を 1 本挟む
