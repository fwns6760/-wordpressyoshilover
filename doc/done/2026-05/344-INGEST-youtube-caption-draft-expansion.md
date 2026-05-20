# 344-INGEST YouTube 字幕 → draft 化 + ch 拡充 + title filter

## meta

- ticket: 344-INGEST-youtube-caption-draft-expansion
- owner: Claude Code
- status: DESIGN_LOCKED / READY_FOR_PHASE_1A_IMPL
- priority: P1 (動画 source 解禁、巨人特化媒体としての content 幅拡充)
- created: 2026-05-14
- 採番: 3 source verify 済 (doc/ + gh issue + grep all 全部 344 未使用)
- depends_on: なし
- related memory: `project_youtube_channel_expansion_candidates_2026_05_14` / `project_mlb_player_inclusion_policy` / `feedback_title_no_ai` / `feedback_publish_forward_must_check_gate_reason`

## user intent (2026-05-14 chat lock)

「YouTube 動画も記事化したい。文字起こし → 編集 → 公開だが、**publish は user 手動**で着地させたい。OB ch を全部追加、title に巨人 / 現役 / OB を含む動画だけ拾う」

## scope

YouTube 動画 source 解禁:
1. 既存 11 ch + 新規 26 ch を ingest 対象に追加(計 37 ch)
2. `youtube-transcript-api` で公開字幕を pull(無料)
3. title filter (巨人 / 現役巨人選手 / 元巨人 OB) で巨人 relevance ない動画 skip
4. ヒット動画は WP draft 生成 (auto-publish 抑制、X 投稿 OFF)
5. 動画 draft 専用 batch mail (1 日 1 通) で user に通知
6. user が draft editor で手直し → 手動 publish

## design lock

### ingest 条件 (title filter、いずれか 1 つで pass)

- 「巨人 / ジャイアンツ / 読売」keyword
- 現役 巨人選手名 (`config/giants_roster.json` 既存)
- 元巨人 OB 名 (新規 `config/giants_ob_roster.json` 30 名 hardcode)

### 動作 flow

```
動画 entry 取得 (channel page scrape)
  ↓
title filter
  ↓ pass
youtube-transcript-api で字幕 pull (公開字幕、無料)
  ↓
WP draft 生成
  - status="draft" 確定
  - body に caption literal 600-1500字 + 出典明示 + YouTube embed (oEmbed)
  - X 自動投稿 OFF
  ↓
batch mail (1 日 1 通、複数 draft list)
  ↓
user 手動 publish
```

## ch 構成 (既存 11 + 新規 26 = 37)

### 既存 production (11、`config/youtube_ob_sources.json`)

- 球団公式: 読売ジャイアンツ
- メディア: DRAMATIC BASEBALL / DAZNベースボール
- 巨人 OB: 上原浩治 / 元木大介 / 髙橋尚成 / デーブ大久保 / 岡崎郁 / 槙原寛己 / 江川卓 / 清原和博

### 新規追加 (26)

巨人 OB 3 + 他球団 OB 17 + 解説団体 2 + メディア 4。詳細は `project_youtube_channel_expansion_candidates_2026_05_14` 参照。
channel_id 不明 ch は YouTube web で verify してから add。

## phase 分割

| Phase | scope | 着手条件 |
|---|---|---|
| **Phase 1a** | caption fetch helper + title filter + draft 抑制 + batch mail (既存 11 ch で動く) + 元巨人 OB roster 整備 | 即着手可 |
| **Phase 1b** | 新規 26 ch を `youtube_ob_sources.json` に add (channel_id verify 必要、`max_age_days=2 / article_limit=5` 抑制 start) | Phase 1a 動作確認後 |
| **Phase 2** | 観察期間後の limit 拡大 / mail 頻度調整 / OB roster 拡充 | data 蓄積 1-2 週間後 |

## 不可触 (hard constraints)

- LLM / AI 不使用 (`feedback_title_no_ai` 継承)
- auto publish なし (`status="draft"` 確定)
- auto X 投稿なし
- 既存 RSS / X / web 記事 publish flow は touch なし (additive、新 path のみ)
- 公開済み記事の遡及修正なし (forward-only、`feedback_publish_forward_must_check_gate_reason`)
- master branch への direct push なし (`hotfix-eyecatch-hashtag` branch 使用)
- 球団公式 12 球団追加なし (巨人公式のみ)

## 成功条件

### Phase 1a
- caption pull 成功率 ≥ 80% (既存 11 ch の動画で test)
- title filter で 巨人 keyword / 現役 / OB 検出時のみ ingest、それ以外 skip
- WP draft 生成、status="draft" 確定 (production で publish=false 確認)
- batch mail (1 日 1 通) で list 通知

### Phase 1b
- 新規 26 ch の channel_id 全て verify (3 source check: YouTube page / channel about / video URL)
- 26 ch fetch で Cloud Run timeout (300s) 超過なし
- 1 ch fail でも他処理続行 (try/except 個別隔離)

### Phase 2
- draft → publish 率 ≥ 50% (user 手直し後)
- draft / mail 量が user 許容範囲 (1 日数十件以下)

## cost

- youtube-transcript-api: ¥0 (Python lib)
- YouTube channel page fetch: ¥0
- caption fetch: ¥0 (公開 endpoint)
- Cloud Run: ¥0 (free tier 大幅余裕、egress 22MB/月 vs 1GB 枠、vCPU 45,000 sec/月 vs 360,000 枠)
- LLM: ¥0 (不使用)
- Mail: ¥0 (既存 Gmail SMTP 無料枠)
- **合計**: **¥0/月**

## risk + 対処

| risk | 対処 |
|---|---|
| YouTube rate limit / IP block | 26 ch fetch 個別 try/except 隔離、caption fetch 間 1-2s sleep |
| OB ch 非巨人話 noise | title filter で skip、漏れたら user draft 確認時 reject |
| draft / mail 過多 | batch mail (1 日 1 通) + max_age_days=2 / article_limit=5 抑制 start |
| 元巨人 OB 漏れ | 30 名 hardcode start、Phase 2 で WebSearch 拡充 |
| 著作権 | 600 字 literal 引用 + 出典明示 + oEmbed = 引用法 32 条範囲 |

## 改修対象 file (Phase 1a 想定)

- 新規: `config/giants_ob_roster.json` (30 名 hardcode)
- 新規: `src/youtube_caption_fetcher.py` (字幕 pull helper、try/except 隔離)
- 拡張: `src/tag_page_scraper.py` (`fetch_youtube_channel_entries` に title filter + caption 添付)
- 拡張: `src/rss_fetcher.py` (動画 marker 検出時 status="draft" 確定 + X 投稿 OFF)
- 新規: `src/youtube_draft_batch_mail.py` (batch mail sender、Scheduler 別 endpoint)
- 拡張: `requirements.txt` (`youtube-transcript-api` 依存追加)
- tests: `tests/test_youtube_caption_fetcher.py` / `tests/test_youtube_title_filter.py`

## next action

Phase 1a 着手 → narrow PR(file ごと small commit、minimum-diff 維持)→ Phase 1b は user 確認後に 26 ch 段階追加。
