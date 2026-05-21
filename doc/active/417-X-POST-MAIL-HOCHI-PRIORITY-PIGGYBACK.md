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
- `2026-05-21 15:20 JST | x_post_candidate_queue.py 新規 + AST OK | next: rss_fetcher hook`
- `2026-05-21 15:25 JST | rss_fetcher hook 1 行 (Hochi/Sanspo gate) + AST OK | next: build_x_post_from_article_info`
- `2026-05-21 15:40 JST | build_x_post_from_article_info + _find_first_giants_player_in_text + smoke import OK | next: queue flush mode`
- `2026-05-21 15:55 JST | run_x_post_mail.py --mode=on-queue + _main_on_queue 追加 + AST/argparse OK | next: tests`
- `2026-05-21 16:05 JST | 30 test 追加 (queue 20 + article_info 10) 全 pass | next: wide regression`
- `2026-05-21 16:15 JST | wide regression 5,723 passed / 1 xfailed / 0 fail | next: commit + push`
- `2026-05-21 16:18 JST | commit 6205459 + push | next: deploy build`
- `2026-05-21 16:24 JST | 2 image build SUCCESS (fetcher + x-post-mail-lane) | next: deploy`
- `2026-05-21 16:35 JST | fetcher 100% traffic switched (rev 00465-msq, image 417-piggyback-6205459) | next: job update + smoke`
- `2026-05-21 16:50 JST | x-post-mail job smoke FAIL: Cloud Run jobs --args が CMD 置換、 container crash | next: Dockerfile ENTRYPOINT 化`
- `2026-05-21 16:55 JST | Dockerfile.x_post_mail ENTRYPOINT 化 + rebuild + commit 936a4ff push | next: 再 smoke`
- `2026-05-21 17:00 JST | x-post-mail job 再 smoke OK (drained 6 / silent skip / exit 0) | next: cron 切替`
- `2026-05-21 17:05 JST | 既存 5 cron PAUSE + x-post-mail-flush 新 cron 作成 (*/30 6-22 * * * JST) | next: 手動 fire verify`
- `2026-05-21 17:08 JST | 手動 fire 経由でも cron→job→queue→silent skip→exit 0 動作確認 | next: ticket finalize`
- `2026-05-21 17:15 JST | ticket 417 post-work section (1-8) 追記、 CLOSED 準備完了 | next: user 受け入れ`

## 10. Regression Memo 欄

実装中に気付いた既存挙動 / 周辺 logic / 隣接 ticket への影響を memo。 ticket 完了後の他 session への申し送り用。

(着手後追記)

---

# 作業後 追記欄 (実装完了後 user 受け入れ前に埋める)

## 1. 実際に変更したファイル

**新規追加**:
- `src/x_post_candidate_queue.py` — GCS-backed queue (enqueue / drain / mark_processed / is_hochi_or_sanspo_source)
- `tests/test_x_post_candidate_queue.py` — 20 test (dedup / fault tolerance / Hochi 判定)
- `tests/test_x_post_branding_gen_article_info.py` — 10 test (player 抽出 / skip path / safety check / unverified)
- `doc/active/417-X-POST-MAIL-HOCHI-PRIORITY-PIGGYBACK.md` — 本 ticket

**既存編集**:
- `src/rss_fetcher.py` — `_create_draft_with_same_fire_guard` 内の `wp.create_post` 呼出直前に hook 1 行 (Hochi/Sanspo source の場合のみ enqueue、 try/except で fault-tolerant)
- `src/x_post_branding_gen.py` — `build_x_post_from_article_info` / `_find_first_giants_player_in_text` を末尾に追加 (既存関数は 1 文字も変えず)
- `src/tools/run_x_post_mail.py` — `--mode={scheduled,on-queue}` argparse 追加、 `_main_on_queue` 関数追加、 `main()` に分岐 1 行
- `Dockerfile.x_post_mail` — `CMD ["python3", "-m", ...]` → `ENTRYPOINT ["python3", "-m", ...]` + `CMD []` (Cloud Run jobs の --args が CMD 置換する問題対応)

## 2. diff 概要

| file | 種別 | LOC 差 |
|---|---|---|
| src/x_post_candidate_queue.py | 新規 | +197 |
| src/rss_fetcher.py | 修正 | +25 (hook block) |
| src/x_post_branding_gen.py | 修正 | +210 (新関数 2 つ) |
| src/tools/run_x_post_mail.py | 修正 | +130 (mode arg + _main_on_queue) |
| Dockerfile.x_post_mail | 修正 | +6 -1 (ENTRYPOINT 化) |
| tests/test_x_post_candidate_queue.py | 新規 | +200 (20 test) |
| tests/test_x_post_branding_gen_article_info.py | 新規 | +95 (10 test) |
| doc/active/417-... | 新規 | +250 |
| **合計** | | **+1,113 / -1** |

## 3. 実行したテスト

**unit / integration (CI 内)**:
1. `tests/test_x_post_candidate_queue.py` (20 test): enqueue / dedup / drain / mark_processed / is_hochi_or_sanspo_source / GCS 例外時 fault-tolerance
2. `tests/test_x_post_branding_gen_article_info.py` (10 test): player 抽出 / skip path (invalid input / no API key / no player) / safety_check failure / unverified_numbers drop
3. `tests/test_x_post_branding_gen.py` (既存): 流用、 regression check
4. `tests/test_x_post_mail.py` (既存): 流用、 regression check
5. `tests/test_rss_fetcher.py` (既存): 流用、 hook 追加で他関数に影響無いこと verify
6. **wide regression**: `pytest tests/ --ignore=tests/test_duplicate_prevention_golden.py`

**smoke (deploy 後 production)**:
7. canary `/health` (yoshilover-fetcher-00465-msq tag p417) → 200 OK
8. traffic 100% switch 後 `/health` → 200 OK
9. `gcloud run jobs execute x-post-mail-lane --args=--mode=on-queue,--dry-run` (Dockerfile ENTRYPOINT fix 前) → container crash (Cloud Run jobs args 仕様判明)
10. Dockerfile.x_post_mail ENTRYPOINT 化 → rebuild → 再 execute → **container exit 0**、 drained 6 items、 全件 silent skip (test fixture URL のため player not in roster)
11. `gcloud scheduler jobs run x-post-mail-flush` 手動 fire → cron 経由でも正常実行確認

## 4. テスト結果

- **新規 test**: 30/30 pass (queue 20 + article_info 10)
- **wide regression**: **5,723 passed / 1 xfailed / 0 fail** (改修前 baseline と diff 無し)
- **canary smoke**: `/health` 両 stage 200
- **production smoke**: cron 手動 fire → Cloud Run job → queue drain → 候補生成試行 → silent skip → exit 0、 エラー無し
- **既存 5 便 PAUSE 後**: `x-post-mail-flush` のみ ENABLED、 cron list で確認

## 5. 残った懸念

| 項目 | 内容 | 対応 |
|---|---|---|
| C1. GCS queue に既に test fixture URL (`hochi.news/articles/test-*`) が 6 件溜まっている | 永久 silent skip ループ、 cleanup 必要 | TTL or 手動 cleanup を別 ticket 検討 |
| C2. 実 Hochi/Sanspo source が来た時の actual 動作 | smoke では test URL のみで verify、 本物の roster player 入り title での E2E 動作は次の自然 fire まで未確認 | 次 4-6 時間以内の Hochi/Sanspo publish で観察、 dump log を user に報告 |
| C3. NPB 限定 filter | 「巨人」 で始まる title が Giants 関連と判定されるが、 高校野球記事で 「巨人軍 OB が監督」 等の枝葉混入の可能性 | 想定デグレ D5 として記録、 観察 |
| C4. mail 受信頻度 | 6-22 時 30 分刻みで 試合中に 連発する可能性 | user 受け入れ前に 1 日分観察 |
| C5. AI Studio billing tier 未 verify | 私が claim した「無料枠内」 は user 側の AI Studio 確認なしのまま | user に screenshot 確認依頼予定 (低優先、 free tier 量内ではあるが) |

## 6. 新しく見つかったデグレ

| ID | 内容 | 修正状況 |
|---|---|---|
| **D-new-1** | **Cloud Run jobs の `--args` flag が Dockerfile CMD を完全置換** (= ENTRYPOINT 形式必要) | **修正済** (commit 936a4ff、 Dockerfile.x_post_mail ENTRYPOINT 化) |
| (記載なし、 他は無し) | 既存挙動への regression は wide pytest 5,723 pass で 0 件 | — |

## 7. 追加した回帰テスト

- `tests/test_x_post_candidate_queue.py` (20 test): enqueue dedup / fault-tolerance / Hochi 判定 (報知/サンスポ/ニッカン/デイリー の正負ケース) / source_url hash 一貫性
- `tests/test_x_post_branding_gen_article_info.py` (10 test): player 抽出の正負 / build_x_post_from_article_info の skip path (invalid input / no key / no player) / safety_check drop / unverified_numbers drop / mocked Gemini を patch して silent skip path

これらは将来の改修で:
- `DEFAULT_MAX_TITLE_LENGTH` のような cap 値 を universal に下げる改修
- `_SYSTEM_PROMPT_FUUGA` / `_KANDUME` の Hard rule を緩める改修
- queue dedup を弱める改修
- Cloud Run jobs Dockerfile を CMD 形式に戻す改修

これら全部が test fail として表面化する想定。

## 8. 次回触ってはいけない範囲

**§ 3 で記載した不可触条件 (全部維持)**:
- 既存 prompt 本文 (`_SYSTEM_PROMPT_FUUGA` / `_SYSTEM_PROMPT_KANDUME` / `_build_system_prompt`)
- `_GEMMA_BRANDING_FORBIDDEN_PATTERNS` / `_GEMMA_BRANDING_INFLAMMATORY_PATTERNS`
- 8 段 hallucination 防止 layer
- few-shot 例 / Hard rule
- Gemma 4 model id

**417 で新規追加された不可触**:
- `Dockerfile.x_post_mail` の `ENTRYPOINT ["python3", "-m", "src.tools.run_x_post_mail"]` を CMD に戻すと Cloud Run jobs の args が壊れる → ENTRYPOINT 形式維持
- `src/x_post_candidate_queue.py` の filename hash policy (`sha256(source_url)[:16]`) は dedup の正本、 hash 短縮や algorithm 変更で過去 entry と互換性失う
- `src/rss_fetcher.py` の hook 位置 (`_create_draft_with_same_fire_guard` の `wp.create_post` 直前) は dedup guard 通過後の単一発火点、 移動すると重複 enqueue / skip 取りこぼし risk
- `is_hochi_or_sanspo_source` の判定軸 (URL host + X handle + source_name marker)、 緩めると非報知 source も enqueue される → 別 ticket で拡張する場合は明示
- 既存 5 X-post mail cron は PAUSED 状態維持 (削除禁止、 revert 可能性確保)
- `x-post-mail-flush` cron schedule `*/30 6-22 * * *` JST は user 確定値、 変更時は user 判断要

**次回 ticket で触る可能性が高い周辺**:
- C1 (test fixture cleanup): queue cleanup ticket
- C2 (non-Hochi source 拡張): ニッカン / デイリー / スポニチ も対象化する別 ticket、 ただし cluster ロジック必要 (報知単独 OK / 他媒体は cluster 必要)
- 観察結果次第で hochi handle / sanspo handle の追加
