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
2026-05-14 | COMMIT_5_DONE | YouTube force-draft gate: publish_skip_reasons.append("youtube_source_force_draft") を YouTube source 検出時に追加、auto-publish + X 自動投稿 連動 OFF | baseline 118/118 PASS、0 regression。commit e1c1af5 push 済
2026-05-14 | COMMIT_6_DONE | YouTube caption section: _maybe_append_youtube_caption_section + _extract_youtube_video_id helper、enriched_content 末尾に caption literal 600字 + 出典 + YouTube embed (additive, idempotent), HTML escape | tests 13 case PASS、baseline 91/91 PASS、0 regression。commit dfc49da push 済
2026-05-14 | POLICY_FLIP | user lock 変更: force-draft → auto-publish + title prefix で識別 (mail 新規 path 不要)。理由: 既存 mail logic を触らず安全側、title prefix で user 手動編集判断 補助 | (commit 7 で実装)
2026-05-14 | COMMIT_7_DONE | revert force-draft (commit #5) + add 【YouTube】title prefix in _create_draft_with_same_fire_guard (idempotent) | baseline 133/133 PASS、0 regression。commit 61b3ed5 push 済
2026-05-14 | DEPLOY | gcloud builds submit (1m54s SUCCESS) → gcloud run deploy → rev yoshilover-fetcher-00388-r6p (sha256 be2caa5ac15...) → traffic flip 100% + tag yt-344-61b3ed5 → /health 200 | Phase 1a 本番 LIVE 完了
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

### 新規 (7 file)
- `config/giants_ob_roster.json` (31 元巨人 OB hardcode)
- `src/giants_ob_roster.py` (roster loader + matching)
- `src/youtube_caption_fetcher.py` (字幕 fetch wrapper、try/except 隔離)
- `src/youtube_title_filter.py` (巨人 keyword + 現役 + OB OR ロジック)
- `tests/test_giants_ob_roster.py` (13 case)
- `tests/test_youtube_caption_fetcher.py` (13 case)
- `tests/test_youtube_title_filter.py` (13 case)
- `tests/test_rss_fetcher_youtube_integration.py` (11 case)
- `tests/test_rss_fetcher_youtube_caption_section.py` (13 case)
- `tests/test_rss_fetcher_youtube_title_prefix.py` (6 case)
- `doc/active/344-INGEST-youtube-caption-draft-expansion.md` (ticket doc)
- `docs/work_logs/2026-05-14_344-INGEST-youtube-caption-draft.md` (本 file)

### 拡張 (2 file)
- `requirements.txt` (+youtube-transcript-api 追加)
- `src/rss_fetcher.py` (+_is_youtube_post_url / _check_youtube_giants_filter /
  _extract_youtube_video_id / _maybe_append_youtube_caption_section /
  _maybe_apply_youtube_title_prefix helper、entry loop に YouTube filter
  並行 OR、_create_draft_with_same_fire_guard で title prefix + caption section
  injection)

## 12. diff 概要

7 commits chain (5fa899a → 7764de0 → fd263a3 → 5231e41 → e1c1af5 → dfc49da → 61b3ed5 → policy flip → 61b3ed5)
合計約 +1100 行 (src 約 350 行 + tests 約 600 行 + config + doc)。

主要 src 変更:
- requirements.txt: +1 (youtube-transcript-api)
- src/rss_fetcher.py: +約 200 行 (5 helper 関数 + entry loop integration + draft creation hook)
- src/giants_ob_roster.py: +85 行 (新規)
- src/youtube_caption_fetcher.py: +95 行 (新規)
- src/youtube_title_filter.py: +57 行 (新規)
- config/giants_ob_roster.json: +約 200 行 (31 OB)

minimum-diff 維持 (commit ごとに narrow scope、既存 method の改変は
最小、新規 method として additive)。

## 13. 実行したテスト

各 commit ごとに pytest baseline 走らせ、累計:
- `pytest tests/test_giants_ob_roster.py` (13 case)
- `pytest tests/test_youtube_caption_fetcher.py` (13 case)
- `pytest tests/test_youtube_title_filter.py` (13 case)
- `pytest tests/test_rss_fetcher_youtube_integration.py` (11 case)
- `pytest tests/test_rss_fetcher_youtube_caption_section.py` (13 case)
- `pytest tests/test_rss_fetcher_youtube_title_prefix.py` (6 case)
- `pytest tests/test_rss_fetcher.py` (28 case、既存 baseline)
- `pytest tests/test_tag_page_scraper.py` (36 case、既存 baseline)
- `pytest tests/test_player_voice_digest_clusterer.py` / `_body_renderer.py` (既存)

最終確認 (commit 7 後):
```
pytest tests/test_rss_fetcher_youtube_*.py tests/test_giants_ob_roster.py \
       tests/test_youtube_caption_fetcher.py tests/test_youtube_title_filter.py \
       tests/test_rss_fetcher.py tests/test_tag_page_scraper.py
```

AST + py_compile + JSON 全 commit 前に実行 (commit_safety_protocol 準拠)。

## 14. テスト結果

最終 baseline (commit 7 後):
- **133 passed、0 failed、3 warnings (既存 deprecated、本 ticket と無関係)**
- 0 regression (既存 test 不変)
- 新規 test 累計 +69 case

## 14b. 本番 deploy verify

- build SUCCESS (1m54s、image sha256:be2caa5ac15...)
- deploy SUCCESS (rev yoshilover-fetcher-00388-r6p)
- traffic 100% flip (tag yt-344-61b3ed5)
- /health 200 OK
- Cloud Run 設定不変 (env / Scheduler / Secret 全部 touch なし)

## 15. 残った懸念

| 項目 | 内容 | 検証必要 timing |
|---|---|---|
| 字幕 API rate limit / IP block | 26 ch 未追加(既存 11 ch のみ動作)。Phase 1b で 26 ch 追加時に注意。Cloud Run egress IP が youtube に block されると全 caption fetch 失敗 (ただし try/except で main flow 壊さない設計) | 朝 06:00 fire 後 youtube_caption_section_appended log 観察 |
| caption が auto-generated で誤字 | Whisper レベル精度なし、user 手動編集前提 | 実際 publish された動画で確認、許容範囲か user 判断 |
| YouTube 動画の draft が auto-publish されて user 想定外 | 公開済 mail 件名に【YouTube】prefix で識別可、user は不要なら WP admin で削除 | 朝 fire 後の mail で確認 |
| OB roster 31 名以外の OB 動画 | filter 漏れ → ingest されない (現状) | Phase 2 で WebSearch 拡充 |
| caption section の表示崩れ | CSS 未確認、`nomotoke-youtube-caption` class は新規で既存 CSS なし | 実 publish で表示確認、CSS 追加要なら別 ticket |
| Phase 1b 26 ch 追加 | channel_id verify 必要、user 提供 or WebSearch ベース | user GO 後 |
| 整合: 既存 youtube_ob_sources.json と rss_sources.json の重複 | 11 ch 内 4 ch 重複 (既存 design)、本 ticket では touch せず | 別 ticket で整理判断 |

## 16. 新しく見つかったデグレ

なし。
- 既存 publish flow への副作用 0 (additive integration、既存 method は最小限の if/elif 分岐追加のみ)
- 0 regression (133/133 baseline 維持)
- impl 中に既存挙動の不審点も発見せず

## 17. 追加した回帰テスト

新規 test file 6 ファイル、計 69 case:

| file | case 数 | 内容 |
|---|---|---|
| `test_giants_ob_roster.py` | 13 | OB roster load / alias 検出 / canonical name unique |
| `test_youtube_caption_fetcher.py` | 13 | mock 経由 lib 動作 / 例外時空文字 fallback / max_chars trim |
| `test_youtube_title_filter.py` | 13 | 巨人 keyword / 現役 / OB / no_match / matcher 例外 fall-through |
| `test_rss_fetcher_youtube_integration.py` | 11 | _is_youtube_post_url / _check_youtube_giants_filter |
| `test_rss_fetcher_youtube_caption_section.py` | 13 | _extract_youtube_video_id / _maybe_append_youtube_caption_section / HTML escape |
| `test_rss_fetcher_youtube_title_prefix.py` | 6 | _maybe_apply_youtube_title_prefix / idempotent / non-YouTube unchanged |

既存 test に追加した case: 0 (新規 file で追加、既存 test を破壊せず)

## 18. 次回触ってはいけない範囲

| 領域 | 理由 |
|---|---|
| `src/youtube_title_filter.py` の `_GIANTS_KEYWORDS` tuple | rss_fetcher 既存 GIANTS_KEYWORDS と意図的に同期、ずらすと is_giants_related と挙動不整合 |
| `_create_draft_with_same_fire_guard` 冒頭の title prefix logic | 全 callsite (main/review) で自動適用、ここを skip すると prefix 外れる |
| `_maybe_append_youtube_caption_section` 内の idempotency check | "nomotoke-youtube-caption" string match で再入防止、変更 = 二重挿入 risk |
| `config/giants_ob_roster.json` の `name` field | filter logic が canonical name lookup する、別 form に変えると整合崩れ |
| `requirements.txt` の youtube-transcript-api | Cloud Run image build 依存、削除すると import fail で main flow stop |
| 既存 `is_giants_related` 関数 | YouTube filter と並行 OR で参照、改変は両方 review 必要 |
| 既存 `youtube_ob_sources.json` の 11 ch | Phase 1b で 26 ch 追加予定、この 11 ch 自体は touch せず維持 |
| force-draft gate (commit #5) は revert 済 | 再有効化したい場合は commit #7 ロジック (POLICY_FLIP) を再評価必要 |

---

## 19. 完了 summary

344-INGEST Phase 1a 全 chain LIVE deploy 完了:
- 既存 11 YouTube ch で OB title filter 動作 (巨人 keyword + 現役 + 元巨人 OB のいずれかで pass)
- caption literal 600字 + 出典 + YouTube embed が 自動 publish 記事 body 末尾に挿入
- title 先頭に【YouTube】prefix 付与で mail 件名 + WP admin で識別容易
- LLM 不使用、cost ¥0/月、Cloud Run free tier 内
- 既存 publish flow への副作用 0、0 regression

次 session (Phase 1b):
- 新規 26 ch を `youtube_ob_sources.json` に段階追加 (channel_id verify 必要)
- `max_age_days=2 / article_limit=5` 抑制 start で観察ベース
- (Phase 2) OB roster 拡充 (WebSearch ベース、現状 31 名 → 50-100 名)

---

(written by Claude Code, 2026-05-14、user GO 待ち)
