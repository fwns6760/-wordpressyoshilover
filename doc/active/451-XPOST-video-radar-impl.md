# 451 XPOST video-nostalgia-radar 実装 (今日の動画候補3件をメールに)

## 1. ticket header

- **ticket id**: 451
- **status**: READY_FOR_IMPL (実装は user GO 後。 公開 X 自動投稿への昇格は別途 §11 user 判断)
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
