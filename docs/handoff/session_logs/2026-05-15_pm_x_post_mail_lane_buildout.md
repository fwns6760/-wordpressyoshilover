# 2026-05-15 PM session handoff — X post mail lane buildout (347/350/351)

status: **NOT CLOSED** — 完成度未到達、明日以降観察 + 追加改善継続

## 1. 本日 LIVE になったもの (実 production 反映済)

### A. Mail schedule alignment (朝に user 依頼で実施)

- `publish-notice-trigger` → `5 6-15 * * *` (昼 :05、10 回/日)
- `publish-notice-trigger-evening` → `5,35 16-22 * * *` (夕-夜 :05/:35、14 回/日、新規作成)
- 自動公開 (`guarded-publish`) の 5 分後に整列、深夜は静か

### B. yoshilover.com 旧 404 を 410 化 (SEO ブランディング救済)

- WP plugin `Gone Response` install + active (v1.1、自動 404 → 410 変換)
- Top page = 200 維持、現存 publish 1490 件 = 200 維持、旧 1000+ 件 = 410 へ
- 大量 404 が「壊れたサイト」signal を出していた懸念に対する治療
- ただし「指名検索順位 落ちた」根本原因は **noindex 戦略 (1 page のみ index)** にもあり、user 戦略として承知

### C. prosports subdomain ブランド bleed 修正 (user 手動)

- 固定ページ「運営者情報」から `ヨシラバー (Yoshilover)` 文字列削除
- 著者表示名 `ヨシラバー` → `fwns6760` に変更
- prosports は別 WP install のため Claude REST 経由触れず、user 自身で対応

### D. ticket 346 — PWA に X 投稿 tab 追加 (LLM-free / 346 disjoint)

- 新 endpoint: `GET /x-post-draft` + `POST /x-post-direct`
- 新 module: `src/format_as_x_post.py` (LLM-free Python テンプレ、ranking / focus / 巨人 highlight / 280 字 cap)
- PWA に「🐦 X 投稿 (データ)」tab、自然言語入力 → textarea + [X 投稿] button → 1 タップ X 投稿
- Cloud Run `manual-intake-service` revision 346-x-post-1778828826 100% traffic
- X API secret を `seo-web-runtime` SA に grant (IAM 修復、1 revision 死亡から復旧)
- doc/active/346-PWA-insight-to-x-post-draft.md
- commit `934007a`

### E. ticket 347 — X post 候補 mail 配信 lane (新 Cloud Run Job + Scheduler 5 個)

- 新 Cloud Run Job: `x-post-mail-lane`
- 新 Cloud Scheduler 5 個: am-1 (7:00) / lunch (12:00) / afternoon (15:00) / evening (17:30) / postgame (22:30) JST
- `src/x_post_mail_lane.py` で セ・リーグ 6 球団 filter (パ 6 球団排除) + insight.db rank query + HTML mail with X Web Intent URL
- mail 1 通 ≤ 10 candidates、各候補に 🐦 X で投稿 button (1 タップで X アプリが本文プリフィル)
- mail_delivery_bridge 経由で SMTP 送信、to=`fwns6760@gmail.com`
- doc/active/347-x-post-suggest-mail-lane.md
- commit `3fc973c`

### F. ticket 350 — 347 精度改善 (period 明示 + 規定打席 threshold)

- header の vague label (今シーズン / 今月 / 直近30日) を **concrete date range** に置換
  - season: `開幕〜5/15 累積`
  - monthly: `5/1〜5/15`
  - last30: `4/15〜5/15`
- 規定 sample size 表記: `規定打席 30+` (batting) / `規定投球回 30+` (ERA)
- min_central_rows: 3 → 5 (厳格化)
- min_sample default: 10 → 30 (module + CLI 揃え)
- doc/active/350-x-post-mail-precision-improvements.md
- commit `925703b`

### G. ticket 351 — variation 拡張 (combo 10 → 22)

- 新 combo 12 件追加:
  - 先月 (4/1〜4/30 closed range) × OPS / AVG
  - 直近 7 日 × OPS
  - 直近 14 日 × OPS / AVG
  - 守備位置別 (捕 / 二 / 遊 / 三) × OPS
  - 巨人内 ranking (球団内 top) × OPS / AVG / ERA
- `(date, hour) seeded shuffle` で多様性確保、deterministic
- doc/active/351-x-post-mail-variation-expansion.md
- commit `2939448`

## 2. 完成度として残ってる懸念

### 高優先 (近いうち判断したい)

1. **mail rendering の user 実機検証**
   - 4 通の smoke mail (21:26 / 21:55 / 21:59 / 22:10 / 22:36) が `fwns6760@gmail.com` に届いてるはず
   - Gmail で HTML rendering / 🐦 X 投稿 button 動作 / column table 見やすさ を user 目視で評価必要
   - 致命的に見栄え悪い箇所が見つかったら明日中に followup ticket

2. **mail 連日同じ ranking の risk**
   - 351 で shuffle 入れたが、22 combo 中 同じ pool だから「驚きが伸びない」可能性あり
   - 1-2 週観察後に「直近 5 試合 / 10 試合 (game-count base)」追加可否を判断
   - 追加するなら **352** として起票、`games` table 直 SELECT で実装 (348 と soft 重複あり、hard 衝突なし)

3. **直近 7 日 / ERA 今月 等で セ 5 未満 skip 頻発する可能性**
   - 5/15 時点で 規定打席 30+ 投手が セ で揃わない事象が production smoke で確認
   - シーズン進行 (試合数増) で自然解消する見込み、ただし明朝 7:00 mail で何 candidates 出るかは未確認

### 中優先 (1-2 週後判断)

4. **「指名検索 ヨシラバー」順位回復の観察**
   - 本日 410 化 + subdomain ブランド cleanup 完了
   - Google 再クロールに 2-4 週、order-of-magnitude では「壊れシグナル除去」効果が出るはず
   - GSC で「ヨシラバー」検索パフォーマンスを観察 (user 側で見る、自動レポートなし)
   - 順位戻り始めたら現状維持、戻らなければ category index 解放 (今は意図的に noindex) を検討

5. **mail 5 通 / 日 の本数調整**
   - 多すぎ感ある場合、scheduler を pause / 削減 (現状 ENABLED のまま)
   - user 体感で「気にならない」レベルなら維持

6. **347 lane の dedup なし問題**
   - 連続 mail で同じ metric / 同じ player が並ぶ可能性
   - 349 (publish lane の dedup) とは別 lane、mail 内 dedup は未実装
   - 必要なら 353 等で軽い 24h dedup 追加 (mail 内のみ、insight.db に書き込まない)

### 低優先 (348 / 349 進捗依存)

7. **348 (insight whitelist + 直近 N 試合 + 月別 / 週別 aggregation) 実装待ち**
   - status: READY (user GO 待ち、数値 lock 必要)
   - 348 ship 後に 347 / 351 と 「直近 5/10 試合」 logic の alignment / refactor が可能
   - 今は急がない (347 lane の variation で代替できてる)

8. **349 (dedup-cooldown-cascade) 待ち**
   - status: READY (348 完了後着手推奨、user 数値確定 pending)
   - 347 lane の dedup と別 lane、衝突しない

9. **`games` table 直 SELECT による 直近 N 試合 logic**
   - 348 と soft 重複あり、ただし production 衝突なし
   - 「games table の column 名 / 行存在 / Giants-only かどうか」は本日 verify 未完
   - 必要なら 352 で実装、その時 games table 実 schema を pytest local で SELECT 経由 verify

## 3. 明日以降の優先順位 (Claude 開始時の参考)

1. **user から mail 体感フィードバック受領** ← 最優先、品質確認
2. **致命的問題あれば即 followup ticket** (352 等)
3. 1-2 週は **観察フェーズ**、code 大規模変更なし
4. 348 / 349 の user GO が来たら別 lane として進める

## 4. 触らない範囲 (明日も継続維持)

- 348 が触る範囲: `src/analysis/insight_*.py` / `ranking_article_publisher.py` / `anomaly_article_publisher.py` / `team_ranking_publisher.py` / `article_candidates` table
- 346 PWA: `src/manual_intake_service.py` / `src/format_as_x_post.py` (read-only import のみ)
- WP REST publish 経路 / X API 直叩き / Gemini / Codex / OpenAI 一切
- 既存 publish-notice mail / fact-check mail / X auto post lane

## 5. AI failure mode 再注意 (user の最重要 carry-over)

「**記憶から再構成 / silent skip / 自己評価 OK**」が最大の事故源。次セッションでも以下徹底:

- claim する前に `grep` / `pytest` / `gcloud describe` / log diff で **実 source から verify**
- spec doc を rewrite する時 base にする「現状」は必ず file を re-read してから書く (memory に頼らない)
- 推測 / hedge 文言を見かけたら user に honest に「これは未 verify です」と即明示
- 本日も 2 度ほど (348 spec の period 表記 / build 3 回 etc.) user に指摘されて自己訂正したケースあり、教訓として残す

## 6. 重要 git refs (明日継続用)

- branch: `hotfix-eyecatch-hashtag` (origin と sync 済)
- 本日 commit:
  - `934007a` 346 PWA insight to X post draft
  - `3fc973c` 347 セ・リーグ ranking X post mail lane
  - `925703b` 350 mail 精度改善 (date range + 規定打席)
  - `2939448` 351 variation 拡張 (combo 10→22)
- 本日 push: 4 commit すべて remote 反映済

## 7. 重要 GCP refs

- Cloud Run Job: `x-post-mail-lane` (image `351-variations`)
- Cloud Run Service: `manual-intake-service` (image `346-x-post-pwa`)
- Cloud Scheduler: 5 個 x-post-mail-* / 2 個 publish-notice-* / 既存全部 ENABLED
- 直近 execution: `x-post-mail-lane-49m58` (22:36 JST、10 candidates、status=sent)

## 8. open ticket 一覧 (close 待ち / 観察)

- `doc/active/346-PWA-insight-to-x-post-draft.md` — LIVE
- `doc/active/347-x-post-suggest-mail-lane.md` — LIVE
- `doc/active/350-x-post-mail-precision-improvements.md` — LIVE
- `doc/active/351-x-post-mail-variation-expansion.md` — LIVE (本 ticket)
- `doc/active/348-INSIGHT-whitelist-implementation-step1-to-3.md` — READY (user GO 待ち)
- `doc/active/349-INSIGHT-dedup-cooldown-cascade.md` — READY (348 後)

## 9. 本日学んだこと (失敗 / 改善 / メタ)

1. **scope 縛りすぎで build 3 回しちゃった件** (350): 「precision」テーマで CLI default を後から修正 → cloudbuild submit が無駄に走った。次回は scope に「CLI default も module default と揃える」を最初から含める
2. **shuffle 導入で既存 test 全 fail した件** (351): determine 性が変わるだけで既存 assert が壊れる、test を「全 pool から該当 feature を find する」形に rewrite で対応
3. **`_is_giants` NameError** (351): 346 の private function を借りようとして失敗、x_post_mail_lane.py 内に新規定義で解消
4. **「期間が入ってない」 user 指摘** (350): `今シーズン` のような vague label は precision テーマで NG、最初から concrete date range にすべきだった
5. **「衝突するの？」 user 質問で過剰保守を訂正** (351): 348 と「hard 衝突なし、soft 重複は許容」を verify ベースで判断、最初から正しく判断したい

---

(本 doc は明日の作業開始時に最初に読むこと)
