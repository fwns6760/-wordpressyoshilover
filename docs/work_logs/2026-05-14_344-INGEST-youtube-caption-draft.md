# 2026-05-14 作業記録 — 344-INGEST YouTube 字幕 → draft 化 + ch 拡充 + title filter

## 1. 概要

YouTube 動画 source 解禁 ticket。既存 11 ch + 新規 26 ch を ingest 対象、`youtube-transcript-api` で公開字幕 pull、title filter (巨人 / 現役 / OB) で絞り、ヒット動画は WP draft 生成 (auto-publish 抑制) + batch mail で user に通知し、user 手動 publish。

## 2. 目的

- 巨人 OB 解説動画 (古田 / 里崎 / 高木豊 / 巨人 OB 8 等) を yoshilover content に追加
- 字幕 literal 引用 (600-1500字) + 出典明示 + YouTube embed で著作権適正範囲内
- LLM 不使用、Cloud Run 既存リソース内、cost ¥0/月
- publish 判断は user 手動で残す (編集 + 著作権 gate を user に保つ)

## 3. 今回触らない範囲

- 既存 RSS / X / web 記事 publish flow (新 path のみ additive)
- 公開済み記事の遡及修正 (forward-only policy 厳守)
- master branch (全 commit は `hotfix-eyecatch-hashtag` branch、PR 化は user 判断)
- 球団公式 12 球団追加 (巨人公式のみ維持)
- 既存 11 ch の channel_id / max_age_days / article_limit
- Cloud Run env / Scheduler schedule / state
- WP noindex / SEO / canonical 設定
- Gemini API call 設定 (本 ticket は LLM 不使用、既存 Gemini 設定 不変)
- X 自動投稿 path (動画 source は X 投稿せず、既存 X path に影響 0)
- mail 既存 publish-notice flow (動画 draft 専用 batch mail は別 endpoint)
- giants_roster.json (現役選手、別 ticket 管理)
- INSIGHT 系 (DB / nightly job、別系統)

## 4. 影響範囲

### 新規追加 file
- `config/giants_ob_roster.json` — 元巨人 OB 30 名 hardcode (新規)
- `src/youtube_caption_fetcher.py` — youtube-transcript-api wrapper、try/except 隔離 (新規)
- `src/youtube_draft_batch_mail.py` — batch mail sender (新規、別 Cloud Run endpoint or 既存 mail flow 拡張で対応検討)
- `tests/test_youtube_caption_fetcher.py` (新規)
- `tests/test_youtube_title_filter.py` (新規)
- `tests/test_giants_ob_roster.py` (新規、roster load + lookup)

### 拡張 file
- `src/tag_page_scraper.py` — `fetch_youtube_channel_entries` に title filter + caption 添付 logic 追加
- `src/rss_fetcher.py` — 動画 candidate 検出時の status="draft" 確定 path 追加 (publish 抑制)
- `requirements.txt` — `youtube-transcript-api` 依存追加
- `Dockerfile` — pip install 確認 (requirements.txt 経由なら自動)

### Phase 1b 想定 (本 work log scope 外、別 fire)
- `config/youtube_ob_sources.json` — 26 ch 追加 (channel_id verify 後)

## 5. 実行予定テスト

### 単体テスト (新規)
- `test_youtube_caption_fetcher.py`:
  - 公開字幕あり動画で caption pull 成功 (mock or fixture)
  - 字幕無し動画で空 string 返し (例外で main flow 壊さない)
  - rate limit 例外時の throttle 挙動
  - 文字数 trim (600-1500字 範囲)
- `test_youtube_title_filter.py`:
  - 巨人 keyword (巨人 / ジャイアンツ / 読売) hit で pass
  - 現役巨人選手名 hit で pass
  - 元巨人 OB 名 hit で pass
  - 上記いずれも無い title で skip
  - 大谷翔平など非元巨人 MLB は skip ([[project_mlb_player_inclusion_policy]] 整合)
- `test_giants_ob_roster.py`:
  - JSON load 成功
  - 30 名 entry 全部 lookup 可能
  - 重複 name 無し

### 統合テスト
- `test_tag_page_scraper.py` 既存に YouTube 動画 candidate に caption + draft marker 添付確認 case 追加
- `test_rss_fetcher.py` 既存に 動画 marker 検出時 status="draft" 確定 confirm case 追加
- 既存 publish flow への regression 0 を pytest baseline で確認

### baseline pytest
- 既存 baseline 維持 (新規 test 増分のみ +、既存 0 regression)
- 想定: 新規 ~20 case + 既存 ~150-200 case = 0 fail

## 6. STOP 条件

以下のいずれかで impl 中断 → user 判断:

- 既存 pytest baseline で regression 1 件以上 出現
- youtube-transcript-api install で Cloud Run image build fail
- 既存 11 ch fetch で 50% 以上 fail (rate limit / IP block 兆候)
- caption pull が連続 3 動画以上 例外で main flow に影響
- WP REST で auto-publish 抑制が効かず動画 draft が publish される
- mail 量 想定 (1 日 1 通 batch) を超える 1 fire 内大量送信
- 既存 RSS / X / web 記事の publish flow に副作用 (件数 / 内容変化)
- Cloud Run timeout (300s) 超過
- Cloud Run free tier 課金 警告

## 7. 禁止事項

- LLM / Gemini call の追加 ([[feedback_title_no_ai]] 継承)
- auto publish (`status="publish"` の自動設定)
- auto X 投稿 (動画 source は X 連携しない)
- 既存 RSS / X / web 記事 path の動作変更
- 公開済み記事の body / title / status / meta mutation (forward-only)
- master branch への direct push or force push
- 球団公式 12 球団追加
- 字幕 全文転載 (1500字超過、出典明示なし、oEmbed 併設なし)
- Scheduler 新規 job 作成 (本 ticket は既存 fetcher 内 path 拡張のみ)
- env flag 新規追加 (本 ticket は config + roster + scraper 拡張のみで完結、flag 増やさない)
- ENABLE_PLAYER_VOICE_DIGEST_DETECTION 等 既存 flag の touch
- Secret Manager / Cloud Scheduler / Cloud Run service config の変更 (deploy 時の image 更新のみ)

## 8. 想定されるデグレ

| デグレ | risk level | 検知方法 | 対処 |
|---|---|---|---|
| 既存 11 ch fetch が新 filter で副作用 | 🟡 中 | tests/test_tag_page_scraper.py の既存 case + 本番 fire 後 ingest 件数 比較 | filter は default OFF flag で抑制可能設計に |
| caption pull が main fetch flow を block | 🟡 中 | try/except 個別 wrap test + Cloud Run timeout 観察 | exception で空文字 fallback、log だけ |
| draft flag (status="draft") が他 source 路に伝播 | 🟢 低 | 動画 marker 検出条件が限定的、既存 path テスト維持 | marker 名前は専用、既存 source_type に追加 |
| mail batch が 1 日複数発火 | 🟡 中 | mail 受信量を 24h 観察 | batch send は 1 日 1 回 cron / 累積 buffer |
| youtube-transcript-api dep 追加で image size + cold start 増 | 🟢 軽微 | Cloud Run cold start latency 比較 | pure Python lib、軽量 |
| YouTube IP block で全 ingestion 停止 | 🔴 高 (発生時) | fetch fail rate 監視 | 既存 11 ch 観察、26 ch 追加は段階的 (Phase 1b) |
| OB roster 漏れで 関連動画 を skip | 🟢 軽微 | 観察 + 漏れ判明時に Phase 2 で追加 | hardcode 30 名 start、user 報告で拡充 |
| WP draft 量増で WP DB / admin 負荷 | 🟢 軽微 | WP admin 表示確認 | max_age_days=2 / article_limit=5 抑制 start |

## 9. 作業ログ欄

```
YYYY-MM-DD HH:MM JST | event | 内容 | result
```

(本 work log GO 後に Claude Code が逐次追記)

```
2026-05-14 (作成時) | DESIGN_LOCKED | 本 work log Markdown 起票、user GO 待ち | doc-only
2026-05-14 (GO) | START | user GO 受領、Phase 1a 着手 | baseline pytest 103/103 PASS (test_tag_page_scraper + test_rss_fetcher + test_player_voice_digest_clusterer + test_player_voice_digest_body_renderer)
2026-05-14 | COMMIT_1_PLAN | OB roster JSON + requirements.txt + roster load helper + tests | scope 開始
2026-05-14 | COMMIT_1_DONE | config/giants_ob_roster.json (31 OB) + requirements.txt (+youtube-transcript-api) + src/giants_ob_roster.py + tests/test_giants_ob_roster.py | pytest 13/13 + baseline 103+13=116/116 PASS、0 regression。commit 5fa899a push 済
2026-05-14 | COMMIT_2_DONE | src/youtube_caption_fetcher.py (字幕 fetch wrapper、try/except 隔離) + tests/test_youtube_caption_fetcher.py | pytest 13/13 PASS、mock 経由 lib 動作 verify (lib インストール local 済 = `pip install --user --break-system-packages youtube-transcript-api`)。commit 7764de0 push 済
2026-05-14 | COMMIT_3_DONE | src/youtube_title_filter.py (巨人 keyword + 現役 player + OB OR ロジック、reason 返却) + tests/test_youtube_title_filter.py (13 case) | pytest 13/13 PASS。commit fd263a3 push 済
2026-05-14 | COMMIT_4_DONE | rss_fetcher integration: _is_youtube_post_url + _check_youtube_giants_filter helper 追加、entry loop で is_giants_related と並行 OR で YouTube 専用 filter 適用、skip 時 youtube_title_filter_skip 構造化ログ | tests/test_rss_fetcher_youtube_integration.py 11 case PASS、baseline rss_fetcher 28 不変、計 0 regression。commit 5231e41 push 済
2026-05-14 | COMMIT_5_DONE | YouTube force-draft gate: publish_skip_reasons.append("youtube_source_force_draft") を YouTube source 検出時に追加、auto-publish + X 自動投稿 連動 OFF | baseline 118/118 PASS、0 regression
```

## 10. Regression Memo 欄

(本 ticket で新たに見つかった既存挙動の不審点 / 既存テスト不在の領域 / 次回触る時の注意点を時系列に記録)

```
YYYY-MM-DD | finding | 内容 | 推奨対応
```

(空、impl 開始時から逐次追記)

---

# 作業後追記欄 (user GO + Claude impl 完了後に追記)

## 11. 実際に変更したファイル

(impl 完了後に追記、git diff --name-only ベース)

## 12. diff 概要

(file ごとの追加/削除行数 + 変更要旨、git diff --stat ベース)

## 13. 実行したテスト

(pytest コマンド + 範囲、新規 test file list)

## 14. テスト結果

(pytest 出力の pass/fail count、regression 0 確認)

## 15. 残った懸念

(impl 後に明らかになった silent gap / 観察必要事項)

## 16. 新しく見つかったデグレ

(impl 中に判明した既存挙動の不審点)

## 17. 追加した回帰テスト

(新規 test file の case list、既存 test に追加した case)

## 18. 次回触ってはいけない範囲

(本 ticket landed 後、次の作業者が触ると壊しやすい領域 + 推奨除外 list)

---

(written by Claude Code, 2026-05-14、user GO 待ち)
