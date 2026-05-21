# 417 X-POST-MAIL hochi-priority piggyback

## 1. meta

- **ticket id**: 417
- **owner**: Claude Code (session 2026-05-21)
- **priority**: P1
- **status**: IN_FLIGHT (= user GO 2026-05-21 15:00 JST、 code 編集着手)
- **lane**: x-post-mail (既存 lane の改修)
- **created**: 2026-05-21
- **related memory**:
  - [[feedback_hochi_priority_no_imitate]] (報知優先・narrative 模倣しない)
  - [[project_mlb_player_inclusion_policy]] (元巨人 OB MLB OK / 非元巨人 MLB NG)
  - [[feedback_data_insight_user_preferences_2026_05_15]] (Cloud Run 無料枠維持、 コスト気にする)
  - [[feedback_title_polisher_cap_policy]] (5/21 同日 commit、 cap policy lock)
- **related ticket**: 411 (X-POST brand voice persona)、 414 (X-POST brand voice quality framework)

## 2. 背景・目的

- **問題**: 朝 07:04 mail で 5/17 stale data (4 日前) を拾う事故 (user 報告 2026-05-21)。 試合中のリアルタイム話題が拾えていない。
- **目標**: 試合中の **話題化記事のみ** を即 X-post 候補化して mail
- **制約**: 完全無料 (Gemini Free Tier 内)、 既存 brand voice (フーガ/缶詰) 1 文字も変えない

### 設計概要 (v3、 2026-05-21 user 確定)

**アーキ**:
```
[Hochi/Sanspo RSS]
  ↓ (rss_fetcher 既存 polling、 5-15 分 cycle)
[rss_fetcher classifier] → NPB filter / roster validation / subtype 通過
  ↓ (Hochi / Sanspo source 該当時、 inline hook 1 行)
[x_post_candidate_queue 書込み] → 重複 skip (source_url 単位)
  ↓
[cron `*/30 6-22 * * *` で queue flush]
[Gemma 4 + 既存 prompt で X-post 候補生成]
  ↓
[mail 送信] (queue 0 件なら silent skip)
```

- cron: `*/30 6-22 * * *` 単 1 本 (17 時間 × 2 = 34 fires/日)
- 既存 5 便 (07/12/15/17:30/22:30) → 全 PAUSED
- 素材 source: **Tavily 廃止** → rss_fetcher が classify した raw RSS article info に置換
- 報知優先: rss_fetcher の `source_url` host / X handle 識別で 報知単独でも enqueue
- 非報知 source は別 ticket で扱う (現 ticket scope = 報知 + サンスポ のみ)
- model: **Gemma 4 維持** (推論起因 hallucination 0、 既存 voice 完全保持)
- 8 段 hallucination 防止 (既存 7 段 + verified_text hygiene 1 段)
- latency: 報知 RSS 配信 → mail 着信 = **5-45 分**

## 3. 今回触らない範囲 (= 不可触条件)

**書き方ルール 全部維持。 1 文字も変えない**:

| 領域 | 不可触 |
|---|---|
| `_SYSTEM_PROMPT_FUUGA` 本文 | 全文不変 |
| `_SYSTEM_PROMPT_KANDUME` 本文 | 全文不変 |
| `_build_system_prompt` の時間帯 hint | 不変 |
| persona 切替 logic (`select_branding_persona`) | 不変 |
| `_GEMMA_BRANDING_FORBIDDEN_PATTERNS` | 不変 |
| `_GEMMA_BRANDING_INFLAMMATORY_PATTERNS` | 不変 |
| `_gemma_branding_safety_check` | 不変 |
| `_extract_unverified_numbers` | 不変 |
| few-shot 例 (試合後・展望・試合中) | 不変 |
| Hard rule (順位 / rate 数字 / MLB / 炎上禁止) | 不変 |
| 長さ rule (220-280 / 180-280 / 140 字未満禁止) | 不変 |
| 数字 generalize rule | 不変 |
| 媒体名・URL・hashtag 禁止 | 不変 |
| `_recent_published_within_days` | 不変 |
| `select_post_type` | 不変 |
| `format_as_x_post` | 不変 |
| roster (`config/giants_roster.json`) | 不変 |
| insight.db の schema | 不変 |
| guarded-publish job | 不変 |
| publish-notice mail | 不変 |
| **rss_fetcher の既存関数本体 (classifier / NPB filter / stale skip / roster validation)** | **不変、 hook 呼出 1 行のみ追加** |
| **Gemma 4 model id (`gemma-4-31b-it`) / Gemini API 切替** | **行わない (推論起因 hallucination 防止)** |
| **WP REST API への書込み (PUT/POST)** | **なし** (read-only GET のみ、 queue は別 storage) |
| 既存 WP post (publish 済) | 不変 (forward-only) |
| 他 ticket (411/414/415/416 等) の active 範囲 | 不可触 |

## 4. 影響範囲

### 触る予定の file

- **`src/x_post_candidate_queue.py` (新規)**: sqlite-backed queue、 `enqueue(article_info)` / `drain(max_count)` / dedup by source_url、 idempotent
- **`src/rss_fetcher.py`**: 報知/サンスポ classify 後の hook 1 行追加 (`x_post_candidate_queue.enqueue(article_info)`)、 既存関数本体は不変
- **`src/x_post_branding_gen.py`**: 新関数 `build_x_post_from_article_info(article_info, persona)` 追加 (Tavily 不使用 path、 既存 prompt 流用)。 既存関数は不変
- **`src/x_post_mail_lane.py` + `src/tools/run_x_post_mail.py`**: 新 mode `--mode=on-queue` 追加 (queue drain → 候補生成 → mail)、 既存 5 便用 mode は不変・並存
- `tests/test_x_post_candidate_queue.py` (新規): enqueue / drain / dedup / race 動作
- `tests/test_x_post_mail_lane.py` (既存): 新 fixture 追加 (報知単独 / 非報知 skip / NPB filter / hallucination 防止)
- `tests/test_rss_fetcher.py` (既存、 当該テスト関数のみ): hook が classify 後に enqueue を 1 度呼ぶ verify
- Cloud Scheduler: 既存 5 cron PAUSE + 新 1 cron `x-post-mail-flush` 追加 (test 後)
- `cloudbuild_x_post_mail.yaml` / `Dockerfile.x_post_mail`: 不変 (code 変更だけで image 再 build)
- `cloudbuild.yaml` (rss_fetcher 用 root Dockerfile) / 既存 image build: 不変、 rss_fetcher 再 build のみ

### 影響を受ける外部 system

- **追加 RSS polling: 0** (既存 rss_fetcher を流用)
- **追加 WP REST API call: 0** (queue は別 storage、 WP は read-only でも今回は不要)
- queue storage (sqlite local or GCS): 月 数百 entry / 数 KB
- Gemma 4 text gen: 月 ~3,060 call、 1500 RPD 無料枠の 6.8%
- Cloud Run job (invocation): 月 ~1,020 (cron 34 fire/日)、 無料枠内
- Gmail / SMTP (mail 送信頻度 増)、 ただし queue 0 件時は silent skip = mail spam なし

## 5. 実行予定テスト

### unit / integration test (CI 内)

1. **queue enqueue 1 件**: `enqueue(article_info)` 後 `drain(1)` で同じ entry が返る
2. **queue dedup**: 同じ source_url を 2 度 enqueue しても 1 件しか drain されない
3. **queue 0 件 drain**: empty queue で `drain()` は `[]` を返す
4. **queue race**: 並列 enqueue 時にも entry 数が正しく一致 (sqlite WAL or file lock)
5. **rss_fetcher hook**: Hochi/Sanspo source URL を持つ article が classify 完了時に `enqueue()` が 1 度呼ばれる、 非該当 source では呼ばれない
6. **`build_x_post_from_article_info`**: queue item を入力に Gemma 4 を呼び、 280 字以内・voice 制約遵守の post が返る
7. **既存 `_extract_unverified_numbers` 統合**: verified_text に存在しない数字を含む生成は drop
8. **既存 `_gemma_branding_safety_check` 統合**: 炎上 pattern hit したら drop
9. **NPB filter (rss_fetcher 側既存)**: 高校野球 source URL は classifier で reject される (= enqueue されない)、 既存 test 流用
10. **MLB OB filter**: 元巨人 MLB (菅野等) は通る、 非元巨人 MLB は rss_fetcher 側で skip 済 → enqueue されない
11. **queue flush mode**: `--mode=on-queue` で queue を drain、 候補を mail compose、 queue を mark-as-processed
12. **flush silent skip**: queue 空時は mail を送らない

### smoke test (deploy 後 production)

13. **canary dry-run**: `--dry-run` で `--mode=on-queue` を 1 fire 走らせ、 mail 送信なしで candidate 生成のみ verify
14. **traffic-on smoke**: rss_fetcher 新 revision を no-traffic で deploy → 自然 fire 1 回観察 → queue entry 確認 → x-post-mail-lane で flush smoke
15. **既存 5 便 PAUSE 後** に新 cron `x-post-mail-flush` だけ動くこと verify
16. **新 cron の actual fire timing** が cron expression 通り

### baseline pytest

17. 全 pytest 通過 (改修前 baseline と diff、 既存 fail を新規回帰扱いしない)
18. `tests/test_x_post_branding_gen.py` 全 pass
19. `tests/test_x_post_mail_lane.py` 全 pass
20. `tests/test_x_post_candidate_queue.py` 全 pass (新規)
21. `tests/test_rss_fetcher.py` 全 pass (hook 追加で他関数に regression が無い verify)

## 6. STOP 条件 (= 即停止 + user 報告)

以下のどれかに該当したら **即停止**、 deploy 進めず user に escalate:

1. rss_fetcher の Hochi/Sanspo classify 完了点が安全に hook 1 行で挿入できない (= 既存関数を分解しないと無理) 場合 → 別設計検討、 user 判断要
2. 既存 8 段 hallucination gate のいずれかを下げないと実装できない場合
3. 既存 prompt (`_SYSTEM_PROMPT_FUUGA` / `_SYSTEM_PROMPT_KANDUME`) の変更が必要になった場合
4. queue storage (sqlite) が rss_fetcher の並列 fire と race condition を test で再現
5. baseline pytest が新規 fail を出した場合 (= 既存機能 デグレ)
6. rss_fetcher の hook 追加で既存 NPB filter / roster validation の挙動が変わる場合
7. queue dedup が同じ source_url を 2 度 enqueue する事故を test で再現
8. 既存 5 便 PAUSE で 別 lane に影響が出る場合 (publish-notice 等)
9. 1 fire で Gemma 4 call が 30+ になる (= 月 30,000+ 想定、 無料枠 risk)
10. user から「止めて」 指示
11. Codex 並走 lane が同 file を touch して conflict 発生

## 7. 禁止事項

**今回の改修で 絶対やらないこと**:

- prompt 本文の変更 (1 文字も)
- 既存 5 便 cron の **削除** (PAUSE のみ、 revert 可能性確保)
- 既存 Gemini API key の rotation / 変更
- AI Studio で billing tier を上げる
- Secret Manager 変更
- WP DB direct write
- 既存 publish 済 post の修正 / 削除 / title 書き換え
- 既存 ledger entry の削除 / 改ざん
- 並走する Codex / 別 session の workspace 侵食
- `git add -A` (明示 stage のみ)
- `git push --force`
- `--no-verify` で hook skip
- minimum-diff 逸脱 (lint 整形 / 横展開 / unrelated cleanup 混入)
- 観察期間なしの 100% traffic 即切替 (canary → smoke 後)
- master / main への直接 commit (feat branch 経由)
- ChatGPT 役 / user に細かい確認を投げ続ける (推奨 1 案で進める)
- user 受け入れ前に「LIVE_DEPLOYED_VERIFIED」 と claim する

## 8. 想定されるデグレ

### High risk

- D1. **既存 5 便利用者 (= user 自身)** が PAUSE で 朝 / 昼 / 夜 mail を失う → user 受け入れ前に新 cron が確実に動くこと verify
- D2. **rss_fetcher の hook 追加**が classify 後の例外 path で 2 重 enqueue する → queue dedup で吸収するが、 race 時に mail に同記事 2 回露出
- D3. **verified_text hygiene** で raw extract を絞りすぎ、 verified_text が薄く Gemma が roster 名以外 hallucinate

### Medium risk

- D4. **rss_fetcher fire 中に queue write fail** → article 取りこぼし (= 該当記事の X-post 生まれない)、 silent loss
- D5. **queue ledger が雪だるま式に肥大** (古い entry の cleanup 必要、 cron で削除 or 自然 TTL)
- D6. **rss_fetcher 並列 fire で queue write race condition** → 重複 enqueue (= 同記事 2 mail)
- D7. 報知 X handle list が古く、 新規記者 handle を識別できない (= 取りこぼし)
- D8. Cloud Run job invocation 月量 (rss_fetcher + x_post_mail) が他 service と合算で無料枠超過
- D9. queue storage (sqlite) を rss_fetcher / x_post_mail-lane の **別 Cloud Run service が共有できない** (sqlite は同一 fs 前提)、 GCS or 別 storage に切替必要 → 設計変更

### Low risk

- D10. mail 着信頻度が user 期待 (30 分刻み) より多すぎ / 少なすぎ
- D11. 報知 RSS feed の format 変更 / 一時的 down で rss_fetcher が article を取りこぼし
- D12. Gemma 4 response 遅延 で cron timeout

## 9. 作業ログ欄

時系列で 1 行ずつ追記する。

- `2026-05-21 14:00 JST | ticket 417 作成 v1 | PRE_GO | next: user GO 待ち`
- `2026-05-21 15:00 JST | ticket v3 update | GO | rss_fetcher hook + queue + cron flush 設計 lock、 Gemma 4 維持、 user 開発 GO 出た`
- `2026-05-21 15:05 JST | TaskCreate 12 件 set up | next: rss_fetcher hook point locate`

## 10. Regression Memo 欄

実装中に気付いた既存挙動 / 周辺 logic / 隣接 ticket への影響を memo。 ticket 完了後の他 session への申し送り用。

(着手後追記)

---

# 作業後 追記欄 (実装完了後 user 受け入れ前に埋める)

## 1. 実際に変更したファイル

(着手後追記)

## 2. diff 概要

(着手後追記)

## 3. 実行したテスト

(着手後追記)

## 4. テスト結果

(着手後追記)

## 5. 残った懸念

(着手後追記)

## 6. 新しく見つかったデグレ

(着手後追記)

## 7. 追加した回帰テスト

(着手後追記)

## 8. 次回触ってはいけない範囲

(着手後追記)
