# 2026-05-08 afternoon: reliability emergency Part 2 (E+D+F + hochi/daily/X 拡張 deploy)

## 背景
朝 10:00 catchup 95 通実送信 OK 後、user 観察「飛ばなくなった」= 通常 fire の `drafts_created=1/fire` が露呈 (close_marker / placeholder_body / duplicate_sentence 軸で大量 skip 残)。bypass 4 path だけでは不十分。同時に hochi RSS = 404 dead で hochi 記事の 30-40% 完全ロスト確認。

## 本日 deploy された改善 (commit 3 本 + revision 00252-7x5)

### c83764d: E + D + F
- `ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL=1` (D): trusted family の post_gen_validate 全 fail axes bypass
- `ENABLE_POST_GEN_VALIDATE_REVIEW_DRAFT=1` (E): post_gen_validate fail を skip ではなく `【要review｜post_gen_validate】` prefix 付き draft 化
- `ENABLE_STALE_RSS_TRUSTED_BYPASS=1` + `STALE_RSS_WINDOW_TRUSTED_HOURS=48` (F): trusted RSS source の stale 24h → 48h 拡張
- tests +17 cases、regression 3350→3367

### 91d4a68: A (hochi tag scraper)
- src/tag_page_scraper.py 新設 (HTMLParser + re、bs4/lxml 追加なし)
- hochi tag page (`/tag/巨人`) → /articles/YYYYMMDD-CODE.html 抽出 → og 取得 → feedparser 互換 entries
- env flag `ENABLE_TAG_PAGE_SCRAPER=1` で gate
- config: 旧「スポーツ報知 巨人」(404 RSS) を tag scraper に置換
- tests +19 cases

### d7ebc1d: B (daily) + X 拡張 4 件
- daily.co.jp tag scraper (`/baseball/giants/index.shtml` curated)
- sponichi: tag page 廃止 → tonight scope 外 (sanspo も同様)
- X account 追加: @nikkan_giants / @daily_baseball / @numberweb / @sankei_news (RSSHub live verify 済)
- 候補 6 件は RSSHub 503 / empty で除外 (sponichi handle / baseballking_jp 等)
- YouTube /youtube routes も RSSHub 503 で外、要 RSSHub diagnose
- bug fix: `_is_ymd_within_window` の date window 計算 off-by-one + naive datetime JST 解釈明示化

## 数値
- baseline: drafts_created=1/fire (5/8 朝 11:00 fire 観測)
- 期待値: bypass full + scraper 効果で drafts_created 大幅増、stale 48h で 5/7 中段以降 hochi 記事も拾える
- cost 上乗せ: +$2.5-5/月 (F の Gemini call 増 + scraper の Gemini call)

## 検証 milestones
1. **13:00 JST (deploy 後 40 分) 第 1 回 fire**: drafts_created / hochi article URL 出現を flow_summary で観察
2. 14:00-16:00 daytime fires (3 回)
3. 17:00-21:00 game-time fires
4. **5/9 04:30 morning-catchup**: trusted bypass full の本実装効果
5. **5/9 06:00 publish-notice heartbeat**: 最終 verification gate (heartbeat mail 必着)

## 失敗時 rollback
- env 単独 rollback: `gcloud run services update --update-env-vars=ENABLE_TAG_PAGE_SCRAPER=0,ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL=0,...`
- revision rollback: `gcloud run services update-traffic yoshilover-fetcher --to-revisions=yoshilover-fetcher-00251-29x=100`

## sponichi/sanspo/youtube 残課題
- sanspo: search ?s= が任意 keyword で同 generic 結果 (filter 不在)、tag page 廃止 → site 構造再調査 or X 経由優先
- sponichi: static giants tag page 廃止、search も generic
- YouTube: RSSHub /youtube が 503、要 instance 側 diagnose
- 明日朝検証完了後に再検討

## 12:35 JST 自己 review + 修正

user の「忖度なしで正直 review」要請を受けて検証、**D bypass FULL は memory rule 違反 = 致命的事実誤認 publish risk** を発見:

- `feedback_publish_forward_must_check_gate_reason.md` の限定 6 STOP gate (本物重複 / placeholder / 事実破綻 / entity mismatch / 巨人と完全無関係 / 本文崩壊) を D bypass FULL は無視して全 axes bypass
- 致命的軸: entity_mismatch (active_team_mismatch) / placeholder_body / NO_GAME_BUT_RESULT / GAME_RESULT_CONFLICT / TITLE_BODY_ENTITY_MISMATCH 等
- memory rule: 「品質 gate 優先(デグレ停止 > 公開数)」と矛盾

### 修正実行 (12:35 JST)
env revert: `ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL=0`、新 revision 00253-c5x → traffic 100%。

修正後の state:
- D FULL: **無効** (限定 6 STOP gate 復活、致命的記事は publish せず)
- 限定 4 path bypass (朝 fix の安全 scope): 維持
- E review draft: 維持 (skip 軸の記事は 【要review】 prefix 付き draft 化、user 判断 queue へ)
- F stale 48h: 維持
- hochi/daily tag scraper: 維持
- X 4 account: 維持

### 残された debt
- PUBLISH_NOTICE_BURST_THRESHOLD=-1 (朝 fix で完全 OFF、雑) → 閾値 50 等に戻すべき (5/9 朝検証後)
- D の scope 限定実装 (code レベル): close_marker / weak_subject_title / duplicate_sentence / source_grounding_drift など軽微軸のみ bypass、致命的軸は維持。今は env 0 で実装は残存
- sponichi / sanspo の代替 source 探索 (今日断念)
- YouTube RSSHub /youtube routes 503 → instance diagnose

## 13:30 - 15:30 JST 追加対応(P2 incident + 残懸念対応)

### 13:01 incident: 65046 が「【要review】」prefix で publish 化された
- 真因: guarded-publish が title prefix 見ずに review-only draft を auto-publish
- fix commit `2487abf`: guarded_publish_evaluator に title prefix filter (`_GUARDED_PUBLISH_DO_NOT_PUBLISH_TITLE_PREFIXES`) 追加
- guarded-publish image rebuild + 再 deploy、scheduler PAUSE → fix 後 RESUME
- 13:00 fire の review draft 5 件 (65069-65073) は draft 維持実機確認済

### 14:00 fire incident: 10 件 publish が thin_body 判定で全件 revert
- 真因: hochi/sanspo 由来 oembed-only 本文薄記事を fetcher が auto-publish していた
- user 並行 commit (35b80b5 / 1fb7b12 / d6d1408) で thin_body_validator 緊急 enforce → 14:16 で 10 件 revert
- 私の 14:30 deploy で d6d1408 image apply → 15:00 fire 以降は本文薄記事を publish 化前に review draft 化(構造的予防)

### 14:30 mail 0 通 incident: PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=0 設定見落とし
- 朝 emergency fix で `=0` のまま、review queue path 全 skip 状態
- 私が見落として deploy 進めてた = 設定 audit 不足
- fix: env 1 行 `PUBLISH_NOTICE_REVIEW_MAX_PER_RUN=10`、即 apply

### 14:50 subtype gate anomaly: tag_scrape source が ENABLE_PUBLISH_FOR_FARM=0 を bypass
- 真因: `get_publish_skip_reasons` の subtype gate が source_type in {"news","social_news"} のみ対象、tag_scrape が gate 通過
- user 判断: A (farm 公開する方向) → ENABLE_PUBLISH_FOR_FARM=1 + S1 code fix は revert
- 連動して PLAYER=1 / MANAGER=1 / NOTICE=1 / PREGAME=1 も env apply (9 subtype ON、general のみ OFF)

### 15:10 重複防止 narrow fix
- 263-QA は guarded-publish 側で実装済 (image 2487abf に in)、しかし RUN_DRAFT_ONLY=0 で fetcher 直 publish path に効かない
- A (RUN_DRAFT_ONLY=1 切替): publish latency 0→30min 大幅変化、デグレ大
- B (allow_title_only_reuse=True 化、env-gated narrow): cross-source 同 title の reuse 化 = first publish wins
- user 選択: B (デグレ最小)
- commit `6b0554f`、ENABLE_FETCHER_CROSS_SOURCE_TITLE_REUSE=1 apply

## 5/8 PM 末 prod state(15:15 JST)

| 階層 | 状態 |
|---|---|
| fetcher revision | 00269-px2 / image 6b0554f |
| guarded-publish | image 2487abf(263-QA + Y2 review-only filter) |
| publish-notice | image b816f06-job、env apply: `BURST_THRESHOLD=50` / `REVIEW_MAX_PER_RUN=10` / `ENABLE_MORNING_HEARTBEAT_MAIL=1` |
| external-ping(新) | image 497934d、Cloud Run Job 新規、scheduler `0 6 * * *` JST |

## 5/8 PM 末 fetcher env state

- RUN_DRAFT_ONLY=0(自動 publish)
- ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS=1(限定 4 path、朝 fix)
- ENABLE_POST_GEN_VALIDATE_TRUSTED_BYPASS_FULL=0(D 無効化、限定 6 STOP gate 維持)
- ENABLE_POST_GEN_VALIDATE_REVIEW_DRAFT=1(E)
- ENABLE_STALE_RSS_TRUSTED_BYPASS=1 / STALE_RSS_WINDOW_TRUSTED_HOURS=48(F)
- ENABLE_TAG_PAGE_SCRAPER=1(A)
- ENABLE_FETCHER_CROSS_SOURCE_TITLE_REUSE=1(DUP narrow)
- subtype publish gate: postgame=1 / lineup=1 / recovery=1 / social=1 / farm=1 / player=1 / manager=1 / notice=1 / pregame=1 / general=0

## 5/8 PM 全 commit

- c83764d feat(rss_fetcher): E+D+F (review draft / trusted bypass full / stale 48h)
- 91d4a68 feat(tag_page_scraper): hochi tag page scraper (A)
- d7ebc1d feat: daily tag scraper + X 4 account 追加 (B + X 拡張)
- cb8b91b D self-review + env=0 revert
- 6992f4a feat: E2 review draft 致命軸 filter
- 7a85167 feat(tag_page_scraper): YouTube channel scraper + OB 4 channel (Y)
- 2487abf fix(guarded_publish): review-only title prefix filter (Y2、65046 incident fix)
- aae3c91 feat(rss_fetcher): T1 telemetry counters
- fea431e doc: MORNING-VERIFY-2026-05-09.md packet
- 497934d feat(external_ping): Cloud Run 独立 daily ping job (PING)
- b816f06 (用 publish-notice、別 commit) heartbeat 3 段 retry
- d6d1408 (user 並行) thin_body_validator 強化
- 6b0554f feat(rss_fetcher): cross-source title reuse env-gated (DUP narrow)

## sponichi / sanspo / YouTube channel 拡張 残

- sponichi.co.jp: static giants tag page 廃止、search も generic 結果(キーワード filter 効かず)、tonight 断念。後日 site 構造再調査
- sanspo.com: 同様、tag page 404、search 任意 keyword 同 generic 結果。tonight 断念
- YouTube: 4 channel(巨人公式 / 上原 / 元木 / 髙橋尚成)で初期動作。sponichi/sanspo OB / 川﨑(動画なし for now) は将来追加候補

## 16:08 JST 追加: publish-notice scheduler 5 分 offset 変更

### 動機
user 指摘「自動公開と mail が同時 飛んでない」 = scheduler `0,30` が fetcher の :00 fire と timing 衝突して mail lag 26-28 分発生。

### 変更
- `publish-notice-trigger` scheduler: `0,30 0-3,6-23 * * *` → **`5,35 0-3,6-23 * * *`**
- gcloud scheduler jobs update http で apply 済(16:08 JST)
- next fire: 16:35 JST

### 効果
- per_post mail lag 26-28 分 → **1-5 分**(fetcher :00 fire の publish を直後の :05 fire でスキャン)
- 16:00 fetcher fire 3 件 publish (65160/65164/65176) は 16:35 fire で mail 化(従来 16:30 から 5 分遅延だが、後続の 17:00 fire の publish は :05 fire で即時 mail に変わる)

### 5/9 朝への影響
- heartbeat 3 段 retry 時刻: 06:00/06:30/07:00 → **06:05/06:35/07:05**(5 分 shift)
- heartbeat code 条件 `hour == 6 OR (hour == 7 AND minute < 30)` 全部該当、3 段 fire 維持
- 04:30 catchup の publish が 05:05 / 05:35 fire で即 mail 化(従来 05:00/05:30 と同等)
- 06:05 fire で前夜蓄積分の per_post mail 大量 + heartbeat #1 飛来見込み

### risk
- 5/9 朝の本番初実機での 5 分 shift untested(ただし heartbeat 範囲 hour=6 内なので code 影響なし)
