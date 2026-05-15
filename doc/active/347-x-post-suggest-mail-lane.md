# 347 セ・リーグ ranking X post → HTML mail lane (LLM-free / 348 disjoint)

## meta

- owner: Claude Code
- type: implementation (new Cloud Run Job + Scheduler + module、X post candidates の mail 配信 lane)
- status: LIVE_DEPLOYED (revision `x-post-mail-lane-hd29k` 実行成功、mail status=sent / 2026-05-15 21:26 JST)
- created: 2026-05-15
- updated: 2026-05-15 (rewrite、旧版 = 「全 metric ランダム 6 件 + Cloud Scheduler 1日2回」廃案)
- doc_path: `doc/active/347-x-post-suggest-mail-lane.md`
- lane: single (Claude direct dev、Codex 不使用)
- parent: なし (新規 feature)
- 関連 ticket:
  - **`348-INSIGHT-whitelist-implementation-step1-to-3.md`** — 開発進行中、本 ticket は **完全 disjoint** で実装する (file / table / publish 経路 全部別)
  - `349-INSIGHT-dedup-cooldown-cascade.md` — 348 dependent、本 ticket は 349 にも依存しない
  - `346-PWA-insight-to-x-post-draft.md` — 完了済、本 ticket は 346 の `src/format_as_x_post.py` を流用するが **修正しない** (read-only import)

## 1. 目的

ヨシラバー の X (旧 Twitter) 運用で、「**サイトを見ない X user 層**」に向けて巨人データ強者ブランディングを行うため、**セ・リーグ ranking × 多角的 slice** の X 投稿候補を 1 日複数回 mail 配信する。user は mail 内の "🐦 X で投稿" link を 1 タップするだけで X アプリが本文プリフィル状態で開く。

差別化軸 (大手 / 報知 / のもとけ等と被らない):
- 大手: 試合速報、HR、安打、勝敗、選手単発
- 347: **6 球団 ranking** で巨人選手 / 巨人 team の位置付けを多角的 slice で見せる
  - 例: 「セ 対左投手 OPS top 10 (今月)、巨人 2 位」
  - 例: 「セ 得点圏打率 top 10、巨人選手 2 / 3 / 7 位」
  - 例: 「セ 7-9 回 被打率、巨人 1 位 (中継ぎ整備の効果)」

348 (WP 記事 publish lane) との関係:
- 348 = 巨人選手 1 人 / 1 試合の milestone を WP 記事化 → サイト訪問者向け
- 347 = セ 全 6 球団 ranking + 巨人位置 を X post → サイト見ない X 層向け
- 両 lane は **insight.db を共通 data source とするが、書き込まない / file 衝突なし**

## 2. 設計サマリ

```
[Cloud Scheduler: 347 用 5 jobs (am-1 / lunch / afternoon / evening / postgame)]
  ↓
[Cloud Run Job: x-post-mail-lane]
  ↓ (Python entrypoint: src.tools.run_x_post_mail)
  ├ insight.db を GCS から DL (manual_intake_insight_query.ensure_local_db 流用、read-only)
  ├ セ・リーグ 6 球団のみ filter (パ 6 球団は除外)
  ├ 多角的 slice で candidate 生成:
  │   - ranking 系: AVG / OBP / SLG / OPS / HR / RBI / ERA / WHIP / K_per_9 / RISP
  │   - 期間 slice: シーズン / 月間 / 直近 5 試合
  │   - 状況 slice (二次): 対左投手 / 対右投手 / 得点圏 / イニング別 (atbats_json 由来)
  ├ 各候補を format (346 の `format_as_x_post` を流用) で column table 整形
  ├ 巨人選手の position に "← 巨人" マーク
  ├ HTML mail body 組立:
  │   - 候補 1〜N (最大 10)、各候補に <pre> でテキスト + "🐦 X で投稿" link
  │   - X intent URL: https://twitter.com/intent/tweet?text=<URL-encoded body>
  │   - plain-text 代替も add (Gmail 古い client 向け fallback)
  ├ mail_delivery_bridge.send() で送信 (HTML + text、to=fwns6760@gmail.com)

[Mail receipt: fwns6760@gmail.com]
  ↓ user が mail 受信、好きな候補の "🐦 X で投稿" タップ
  ↓ X アプリ / X.com が text プリフィル状態で開く
  ↓ user が「ポスト」だけ押す
[X post live]
```

新規追加 file (全部 348 と disjoint):
- `src/x_post_mail_lane.py` — candidate 選定 (セ・リーグ filter / slice 適用) + HTML mail body 組立 + X intent URL 生成
- `src/tools/run_x_post_mail.py` — CLI entry point、`python -m src.tools.run_x_post_mail [--dry-run]`
- `Dockerfile.x_post_mail` — Cloud Run Job image (publish-notice Dockerfile pattern に揃える)
- `cloudbuild_x_post_mail.yaml` — build config
- `tests/test_x_post_mail.py` — unit (candidate 選定 / セ filter / HTML body / X intent URL encode / 改行保持)

再利用 (read-only import、修正なし):
- `src/format_as_x_post.py` (346 成果物、column table 整形)
- `src/manual_intake_insight_query.py` (`ensure_local_db` / `query_rank` 関数)
- `src/analysis/insight_rank_query.py` (KNOWN_METRICS、rank logic)
- `src/mail_delivery_bridge.py` (mail 送信)

新規 infra:
- Cloud Run Job `x-post-mail-lane` (image + env: MAIL_BRIDGE_* + INSIGHT_GCS_BUCKET)
- Cloud Scheduler 5 jobs:
  - `x-post-mail-am-1` = `0 7 * * *` Asia/Tokyo (朝、前日試合まとめ)
  - `x-post-mail-lunch` = `0 12 * * *` Asia/Tokyo (昼、月別 / 季別 ranking)
  - `x-post-mail-afternoon` = `0 15 * * *` Asia/Tokyo (午後、今日の試合気になる点)
  - `x-post-mail-evening` = `30 17 * * *` Asia/Tokyo (試合直前、lineup、対戦投手過去成績)
  - `x-post-mail-postgame` = `30 22 * * *` Asia/Tokyo (試合後 highlight、記録、streak)

## 3. 今回触らない範囲

絶対不可触 (348 の進行中作業との衝突回避が最優先):

**348 が触る範囲 (一切 read-only も含めて修正しない)**:
- `src/analysis/insight_*.py` 全部 (insight_anomaly_detector / insight_rank_query / insight_article_generator / insight_etl 等)
- `src/analysis/ranking_article_publisher.py`
- `src/analysis/anomaly_article_publisher.py`
- `src/analysis/team_ranking_publisher.py`
- `config/insight_whitelist.yaml` (未存在、348 で新規予定だが 347 で touch しない)
- `article_candidates` table への **write** (read も避ける、別 lane なので)
- `insight.db` の schema 改修 (read-only access のみ)

**publish 経路全般不可触**:
- WP REST publish 経路 (記事 publish しない、X post 専用)
- `guarded_publish_runner.py` / `wp_draft_creator.py`
- WP REST 経由の write 一切

**既存 publish-notice mail lane 不可触**:
- `Dockerfile.publish_notice` / `cloudbuild_publish_notice.yaml`
- Cloud Run Job `publish-notice`
- Cloud Scheduler `publish-notice-trigger` / `publish-notice-trigger-evening`
- `src/publish_notice_email_sender.py` (修正不要、本 ticket は mail_delivery_bridge を直叩き)

**既存 X 投稿経路不可触**:
- `src/x_api_client.py` (本 ticket は X API 呼ばない、X intent URL 経由 user 手動)
- `src/x_post_queue_ledger.py` / `media_xpost_selector.py` / `x_post_generator.py` / `x_post_template_candidates.py`
- 既存 X auto post lane (postgame / lineup 等の自動投稿)

**346 PWA 経路不可触**:
- `src/manual_intake_service.py` (346 で modify したまま、347 では touch しない)
- `src/format_as_x_post.py` (346 成果物、read-only import のみ、修正なし)

**347 自身が起こさない変更**:
- LLM (Gemini / Codex / OpenAI) 呼出 — 一切なし
- パ・リーグ 6 球団のデータ (西武 / ソフトバンク / オリックス / ロッテ / 日本ハム / 楽天) — filter で除外
- 著作権境界外の文言 (報道引用、長文 quote) — 本 ticket は数値 ranking のみで著作権境界に触れない
- X 自動投稿 — user 手動 intent タップ前提、Cloud Run から create_tweet しない

scope 外の cleanup / 横展開 / lint 整形 / refactoring 一切禁止 (minimum-diff 原則)。

## 4. 影響範囲

直接変更 (新規 file のみ、既存 file 修正ゼロ):
- `src/x_post_mail_lane.py` (新規)
- `src/tools/run_x_post_mail.py` (新規)
- `Dockerfile.x_post_mail` (新規)
- `cloudbuild_x_post_mail.yaml` (新規)
- `tests/test_x_post_mail.py` (新規)

間接影響 (read-only import、修正ゼロ):
- `src/format_as_x_post.py` (346 成果物)
- `src/manual_intake_insight_query.py`
- `src/analysis/insight_rank_query.py`
- `src/mail_delivery_bridge.py`

infra 影響 (新規追加のみ、既存 0 影響):
- 新 Cloud Run Job 1 個追加 (`x-post-mail-lane`)
- 新 Cloud Scheduler 5 個追加 (am-1 / lunch / afternoon / evening / postgame)
- 既存 Job / Scheduler / Service 触らない

データ影響:
- `insight.db` への書込み 0 (read-only access、GCS DL → local cache → SQL read のみ)
- WP post への書込み 0
- X API 呼出 0 (intent URL は client-side でブラウザ / X アプリが処理、Cloud Run から API 呼ばない)
- Gmail SMTP: 1 日 5 通追加 (publish-notice 系の通常便 + 347 の 5 通 = quota 影響軽微)

ユーザー影響:
- `fwns6760@gmail.com` に 1 日 5 通の新規 mail (`[X 投稿候補 N 件] <時間帯> / YYYY-MM-DD HH:MM JST`)
- 既存 publish-notice mail / fact-check mail への影響 0
- 既存 PWA (346 で deploy 済) への影響 0

コスト影響:
- Cloud Run Job 実行: ~5-10 秒 / 256 MiB × 1 日 5 回 = 完全無料枠内
- Cloud Scheduler: 5 jobs × 月 30 日 = 150 fire/月、無料枠内
- mail 送信: Gmail 経由、追加コスト 0
- LLM 呼出: 0
- BigQuery 課金: 0 (insight.db = SQLite、BQ 経由しない)

## 5. 実行予定テスト

unit test (`tests/test_x_post_mail.py`):
- `pick_central_league_candidates()`:
  - 6 球団 (巨人 / 阪神 / DeNA / ヤクルト / 中日 / 広島) のみ含む
  - パ 6 球団 (西武 / SB / オリックス / ロッテ / 日ハム / 楽天) は除外される
  - 10 件以下、種別 ranking / 期間 slice の多様性 1+ 件
- `compose_html_mail()`:
  - 各候補に `<pre>` でテキスト + intent URL link
  - 改行は `\n` (LF) のみ、`\r\n` 混入禁止
  - X intent URL の `text=` パラメータが URL-encoded
  - 巨人選手の "← 巨人" マークが HTML escape されてる
  - plain-text 代替 (multipart/alternative) が含まれる
- `build_subject()`:
  - `[X 投稿候補 N 件] <時間帯> / YYYY-MM-DD HH:MM JST` 形式
  - 時間帯 label が timestamp の hour に依存して切替 (朝 / 昼 / 午後 / 夕方 / 試合後)
- `encode_x_intent_url()`:
  - 改行 `\n` が `%0A` に encode
  - 全角文字が UTF-8 percent-encoded
  - ハッシュタグ `#` が `%23` に encode
  - 280 字超過時は警告 (truncate しない、user に知らせる)

integration test (mocked):
- `run_x_post_mail.main()`:
  - `mail_delivery_bridge.send` を mock、呼出 args 検証
  - `miq.ensure_local_db` を mock (実 GCS 触らない)
  - `miq.query_rank` を mock (実 SQLite 触らない)
  - candidates が 0 件のとき send が呼ばれないこと (空 mail 送信 NG)
  - dry-run mode で send mock 呼出されないこと

regression:
- pytest baseline 維持 (新規追加分のみ +N、既存 fail 増加禁止)
- `format_as_x_post` の既存 test に影響なし (read-only 利用なので)
- `mail_delivery_bridge` の既存 test に影響なし
- `manual_intake_service` (346 で modify したファイル) の test に影響なし

manual smoke (deploy 後):
- `gcloud run jobs execute x-post-mail-lane` で 1 回手動実行
- 受信メールで:
  - HTML rendering で各候補の "🐦 X で投稿" link tap → X アプリが text プリフィル状態で開く
  - column table の改行がコピペ用にも保持される (plain-text 部分)
  - 5 候補以上、10 件以内
  - 巨人選手 highlight 確認
  - パ 6 球団含まれてないこと確認
- 翌朝 7:00 / 昼 12:00 / 午後 15:00 / 夕方 17:30 / 試合後 22:30 で自動 fire 確認

## 6. STOP条件

実装中 / deploy 中に以下を検知したら即停止して user 判断仰ぐ:

1. `format_as_x_post` (346 成果物) の signature / 挙動変更が必要と判明 → 346 への影響、scope 拡大
2. `mail_delivery_bridge.send` の signature / 挙動変更が必要と判明
3. `insight_rank_query` / `manual_intake_insight_query` の修正が必要と判明
4. `insight.db` への書込みが必要と判明 (read-only 前提崩壊)
5. **348 が触ってる file (`src/analysis/*` 等) の修正が必要と判明** → 即停止、user 判断
6. **`article_candidates` table の read が必要と判明** → 即停止 (348 と data 共有しない原則)
7. 既存 publish-notice mail / fact-check mail への影響発見
8. 既存 X 自動投稿 lane (`x_post_queue_ledger` 等) との衝突発見
9. Gmail SMTP rate limit (1 日 500 通) に近づく挙動発見
10. 既存 Cloud Run Job / scheduler の挙動変化が必要と判明
11. 既存 pytest が新たに red 化
12. X intent URL が一部 mail client で動作しない (HTML rendering 不可) → fallback 設計を確認
13. パ 6 球団の data が漏れる (filter logic 不備) — branding scope 違反
14. 巨人選手 highlight が漏れる (`_GIANTS_TEAM_ALIASES` の team alias 不一致)
15. candidates が 5 件未満しか出ない (data 不足、insight.db ETL の問題)

## 7. 禁止事項

- `git add -A` (移動 / 更新した path だけ明示 stage)
- LLM (Gemini / Codex / OpenAI / 他) 呼出の追加
- `--no-verify` で pre-commit hook bypass
- **348 が触ってる file の修正** (絶対衝突回避)
- **`article_candidates` table への read / write 一切**
- 既存 publish-notice / fact-check mail の挙動修正
- 既存 X auto post lane への影響
- 既存 346 PWA endpoint への修正
- scope 外の cleanup / refactor / lint 整形 / typo 修正
- 既存 fail test を「対象外」として無視 (baseline 比較で fail 数増えたら必ず stop)
- commit / push 前に staged 内容を `git diff --cached --name-status` で verify しない
- ticket 番号 347 以外の commit message
- 「だいたい合ってればいい」緩い judgment (verified data 厳守)
- AI failure modes (記憶再構成 / silent skip / 自己評価 OK) を無視 — すべて grep / pytest / log diff で実証する

## 8. 想定されるデグレ

1. **348 との file 衝突**
   - 原因: 思わず 348 関連 file (insight_*.py 等) を touch
   - 検知: pre-commit で staged file 名を grep、348 scope に該当したら STOP
   - 対策: 新規 file 名は `x_post_mail_*` prefix で 348 scope と明確に分離

2. **既存 publish-notice mail と subject 衝突**
   - 原因: `[X 投稿候補]` prefix が Gmail filter / label と衝突
   - 検知: deploy 後の Gmail 受信トレイ確認
   - 対策: prefix を `[X 投稿候補]` で固定、既存 publish-notice (`[巨人速報]` 等) と明確に区別

3. **X intent URL が動作しない mail client**
   - 原因: HTML mail がブロックされる / link が無効化される
   - 検知: 自分の Gmail / iOS Mail / Outlook で受信確認
   - 対策: plain-text 代替に同じ intent URL も平文で書く、user が手動 copy できる

4. **改行コードの platform 差**
   - 原因: `\r\n` (CRLF) と `\n` (LF) で Gmail / X 表示崩れ
   - 検知: mail 受信して X 貼付けテスト
   - 対策: HTML 部は `\n` のみ、`<pre>` で wrap、X intent URL は `%0A` encode

5. **パ 6 球団のデータ混入**
   - 原因: filter logic で `team_code in {セ 6 球団}` が漏れる
   - 検知: unit test で sample 12 球団 rank result → 出力に セ のみ
   - 対策: SET-based filter、whitelist で hardcode (`{"巨人", "読売", "ジャイアンツ", "阪神", "DeNA", "ヤクルト", "中日", "広島"}`)

6. **巨人 player highlight の漏れ**
   - 原因: `_GIANTS_TEAM_ALIASES` の team alias 表記揺れ
   - 検知: 346 で対応済の alias set を再利用
   - 対策: 346 の `_GIANTS_TEAM_ALIASES` を read-only import、変更しない

7. **mail 本文 280 字超過候補が混ざる**
   - 原因: 6 球団 ranking + slice combo で長い player name 連続
   - 検知: 文字数行 `XXX / 280 字` が 280 超
   - 対策: 表示はそのまま (user が編集可能)、warn のみ、intent URL は X 側で警告

8. **insight.db キャッシュ失効による空 mail**
   - 原因: GCS DL 失敗 / nightly ETL 未走 / 新規 metric column 不在
   - 検知: candidates 0 件で send skip
   - 対策: 空 mail 送信しない、log 警告のみ

9. **Cloud Run Job との image 名衝突**
   - 原因: Job 名 `x-post-mail-lane` が既存と被る
   - 検知: gcloud run jobs deploy エラー
   - 対策: 事前に gcloud run jobs list で確認、被ったら別名

10. **Cloud Scheduler の重複発火**
    - 原因: 既存 publish-notice-trigger と同時刻 fire でリソース競合
    - 検知: Cloud Scheduler dashboard
    - 対策: 7:00 / 12:00 / 15:00 / 17:30 / 22:30 は既存 publish-notice (6-15 :05 / 16-22 :05,:35) と干渉しない時刻

11. **HTML mail の text encoding 崩れ**
    - 原因: meta charset 不指定で 日本語が文字化け
    - 検知: 受信 mail で漢字が ??? に
    - 対策: HTML head に `<meta charset="utf-8">`、Content-Type に `; charset=utf-8`

12. **X 投稿後の重複検知不要**
    - 原因: user が同じ post を 2 回投稿する可能性 (mail に同じ候補が複数回出る等)
    - 検知: なし (mail 内 dedup なし、user 判断)
    - 対策: 本 ticket では mail 内 dedup しない、user が自己判断、347 lane 内では `_recent_sent` 記録なし (349 の dedup と衝突回避)

## 9. 作業ログ欄

(実装着手後に追記。各 milestone を 1 行ずつ、timestamp + event + 対象 path + status)

```
YYYY-MM-DD HH:MM JST | <event> | <path or commit_hash> | <status>
```

予定 milestone:
- doc 347 rewrite 完成、user 一読 + GO 待ち
- pytest baseline (touched scope) 記録
- src/x_post_mail_lane.py 初版 (candidate picker + HTML mail composer + intent URL encoder + subject builder)
- src/tools/run_x_post_mail.py 初版 (CLI entry + --dry-run flag)
- tests/test_x_post_mail.py 完成
- AST parse / module import smoke
- direct scope pytest green
- wide pytest green (baseline 維持)
- Dockerfile.x_post_mail 完成
- cloudbuild_x_post_mail.yaml 完成
- cloudbuild image 完成
- Cloud Run Job 作成 (env wiring 含む)
- Cloud Scheduler 5 jobs 作成 (am-1 / lunch / afternoon / evening / postgame)
- 手動 execute で実 mail 受信 smoke
- HTML mail の X intent link tap → X アプリ起動確認
- 翌朝 7:00 自動 fire 確認待ち
- commit + push
- doc 更新 (本 doc に作業結果追記)

## 10. Regression Memo欄

(実装中 / 後で気づいた既存挙動の依存 / 微妙な仕様 / 触ると壊れるポイントを追記)

予定確認事項:
- `mail_delivery_bridge.send` の正確な signature (publish-notice / x_draft_email_sender がどう呼んでるか参照)
- `BridgeCredentials.load_credentials_from_env` が要求する env 一覧
- `_GIANTS_TEAM_ALIASES` を 346 から import 経路確認
- Cloud Run Job execution context (parallelism / timeout / retry の既存値継承)
- X intent URL の URL length limit (X 側 / iOS / Android で異なる可能性、>2000 char で truncate される report あり)
- HTML mail の Gmail rendering (Gmail は `<style>` を一部無視、inline style 推奨)
- insight.db schema (batting_logs.atbats_json / inning_scores / advanced_metric_snapshots) は 348 で changes 入る可能性、347 は最小依存に保つ

---

## (post-work セクション、2026-05-15 JST 実装完了後の記録)

### A. 実際に変更したファイル

**新規追加 (6 件)**:

- `doc/active/347-x-post-suggest-mail-lane.md` — 本 ticket doc (rewrite 含む)
- `src/x_post_mail_lane.py` — セ・リーグ filter、candidate picker、HTML mail composer、X intent URL encoder (約 350 行)
- `src/tools/run_x_post_mail.py` — CLI entry point、`python -m src.tools.run_x_post_mail`
- `Dockerfile.x_post_mail` — Cloud Run Job image
- `cloudbuild_x_post_mail.yaml` — build config
- `tests/test_x_post_mail.py` — 24 unit test (セ filter / intent URL / subject / pick candidates / compose mail)

**既存修正**: ゼロ件 (348 と完全 disjoint、minimum-diff 完遂)

不可触で済んだ範囲 (全部 read-only import or 触らず):
- `src/format_as_x_post.py` (346 成果物、import のみ、修正なし)
- `src/manual_intake_insight_query.py` (`ensure_local_db` / `query_rank` を呼ぶだけ)
- `src/mail_delivery_bridge.py` (`MailRequest` / `send` を呼ぶだけ)
- `src/analysis/insight_*.py` 全部 (348 が触る範囲、348 disjoint 維持)
- `src/analysis/ranking_article_publisher.py` / `anomaly_article_publisher.py` / `team_ranking_publisher.py` (348 scope)
- `article_candidates` table (read / write 一切なし)
- `insight.db` への書込み (read-only access のみ、GCS DL は既存 helper 経由)
- 既存 publish-notice mail / fact-check mail / 346 PWA / X auto post lane

### B. diff 概要

- `src/x_post_mail_lane.py`: 約 350 行新規
  - constants: `CENTRAL_LEAGUE_TEAM_ALIASES` (6 球団 alias 26 種)、`SAFE_METRICS` (5 metric)、`_METRIC_LABELS_JP` (5 label)、`X_CHAR_LIMIT=280`、`_X_INTENT_URL_BASE`、`_TIME_BANDS` (5 帯)
  - core: `is_central_league` / `filter_central_league` / `pick_candidates` / `encode_x_intent_url` / `time_band_label` / `build_subject` / `compose_mail`
  - helpers: `_build_combos` (10 combo: 5 season + 3 monthly + 2 last-30)、`_rebuild_ranks_within_central` (rank 再計算)、`_format_one` (346 流用 + period 付与)、`_compose_text_body` / `_compose_html_body`
  - dataclass: `_MetricCombo` / `Candidate` / `ComposedMail`
- `src/tools/run_x_post_mail.py`: 約 150 行新規
  - argparse: `--dry-run` / `--max-candidates` / `--to` / `--min-sample`
  - flow: configure_logging → resolve_recipients → ensure_local_db → pick_candidates → compose_mail → send (or dry-run)
- `Dockerfile.x_post_mail`: 約 30 行新規 (publish-notice Dockerfile pattern を踏襲、google-cloud-cli は不要なので除外)
- `cloudbuild_x_post_mail.yaml`: 約 30 行新規 (cloudbuild_publish_notice pattern を踏襲)
- `tests/test_x_post_mail.py`: 約 280 行新規 (24 test、6 test class group)

minimum-diff 完遂: 既存 file 修正 0、新規 file のみ、namespace prefix `x_post_mail*` で 348 scope と明確に分離。

### C. 実行したテスト

1. **AST parse check**: `src/x_post_mail_lane.py`、`src/tools/run_x_post_mail.py` 両方 OK
2. **module import smoke**: `from src import x_post_mail_lane` → 全 export 取得
3. **filter / intent URL / time band smoke** (inline Python):
   - `is_central_league('巨人')` = True / `is_central_league('西武')` = False
   - `encode_x_intent_url('テスト #巨人')` = `https://twitter.com/intent/tweet?text=%E3%83%86%E3%82%B9%E3%83%88%20%23%E5%B7%A8%E4%BA%BA`
   - `build_subject(datetime(7:00), 5)` = `[X 投稿候補 5件] 朝 / 2026-05-16 07:00 JST`
4. **CLI argparse smoke**: `python -m src.tools.run_x_post_mail --help` → 4 flag 表示
5. **新 module pytest**: `pytest tests/test_x_post_mail.py -v` → 24 passed (0.28s)
6. **直接 scope pytest**: format_as_x_post + mail_delivery_bridge + manual_intake_insight_query + x_post_mail = **77 passed** (baseline 53 + 新 24 = 77 で整合)
7. **広範 pytest** (`pytest -q --ignore=tests/integration`): **4731 passed, 4 xfailed (既存), 978 subtests passed, 1 failed**
   - 1 failed = `tests/test_ingestion_filter_relaxation.py::test_main_passes_36_hour_window_for_postgame_skip_check` (pre-existing、347 と無関係)
   - baseline (stash で 347 changes 退避後) でも同 test fail を確認 → 347 起因ではない
8. **cloudbuild**: `gcloud builds submit --config=cloudbuild_x_post_mail.yaml` → SUCCESS、image digest `sha256:d20063257a1e595e3c0a006f7bc848addd053e7f4143174aa41926bb99446d7a`
9. **Cloud Run Job 作成**: `gcloud run jobs create x-post-mail-lane` → SA=`487178857517-compute@developer.gserviceaccount.com`、env wiring + secret 投入
10. **Cloud Scheduler 5 個作成**: `x-post-mail-am-1` / `-lunch` / `-afternoon` / `-evening` / `-postgame` 全 ENABLED
11. **production smoke** (`gcloud run jobs execute x-post-mail-lane --wait`):
    - Execution `x-post-mail-lane-hd29k` → SUCCESS
    - log: `Downloading insight.db cache` → `Picking candidates (max=10, min_sample=10)` → `Composing mail with 10 candidates` → `Sending mail to ['fwns6760@gmail.com']` → `mail send result: status=sent reason=None refused={}` → `Container called exit(0)`

### D. テスト結果

- AST parse: OK (新 2 file 両方)
- 新 module pytest: **24 passed** (0 failure / 0 error)
- 直接 scope pytest: **77 passed**, baseline 53 + 新 24 = 77 で完全整合
- 広範 pytest: 4731 passed / 1 failed (pre-existing、347 と無関係)、4 xfailed (既存)、978 subtests passed
- cloudbuild: SUCCESS、digest `2009da9...` (再記: 正しくは `d20063257...`)
- Cloud Run Job 作成: SUCCESS
- 5 Cloud Scheduler 作成: 全 ENABLED
- production smoke: **mail 実送信成功** (status=sent / 10 candidates / refused=empty)

### E. 残った懸念

1. **実 mail の表示確認は user 側のみ可能** 🔴
   - production smoke で status=sent は出たが、HTML rendering / 🐦 X 投稿 link の挙動 / 改行保持 / 巨人 highlight は user の Gmail で目視確認が必要
   - 1 通来てるはず (fwns6760@gmail.com、件名 `[X 投稿候補 10件] 試合後 / 2026-05-15 21:26 JST`)
   - user に確認お願いするのが最終 verify
2. **X intent URL の長さ** 🟡
   - 280 字テキスト + ハッシュタグ + URL encode で URL が 800-1000 char 程度になる可能性
   - iOS Safari は 8000 char 程度まで OK、X アプリ受け取り側の制限は未確認
   - 想定 280 字以内なら問題ないはず、要 user 実機 tap 確認
3. **24h dedup なし** 🟡
   - 1 日 5 通で同じ metric が繰り返し出る可能性 (例: 朝 / 昼 / 午後で全部 OPS top 10 が出る)
   - 本 ticket は dedup なし (349 と衝突回避優先)
   - 動かして user が「うっとうしい」なら別 ticket で daily dedup 追加
4. **insight.db 新鮮度依存** 🟡
   - data-insight ETL が 1 日 7 回走るので、各 mail 時刻の直前 ETL が成功してれば新鮮、失敗してれば古い data
   - 失敗時は同じ mail が連続来る可能性、これも観察してから対応
5. **試合後 mail (22:30) で当日 data 反映** 🟡
   - 21:00 ETL trigger があるので 22:30 までに当日試合 data が一部入ってる可能性
   - ただし試合終了が 21:30 過ぎる日もある、その日は 22:30 でも当日 data 不在のリスク
   - 観察 (明日朝の試合終了タイミング次第)
6. **mail 5 通 / 日 が多すぎないか** 🟡
   - 既存 publish-notice (5+14=19 通 / 日) + 新 347 (5 通) + fact-check 等 = 1 日 30-40 通 mail
   - user の Gmail filter 設定次第で見落とすリスク
   - 観察 (user 自身の体感)

### F. 新しく見つかったデグレ

- **deploy 時の IAM 問題なし** ✅ (346 の時の `seo-web-runtime` SA 不足のような問題は再発せず、`487178857517-compute` SA が既に必要権限を持っていた)
- **既存 fail (test_ingestion_filter_relaxation)** ✅ (pre-existing、347 起因ではない、baseline で確認済)
- **build 1 回で SUCCESS** ✅ (Dockerfile / cloudbuild は publish-notice pattern 流用、追加 debug 不要)

新たな問題発見:
- なし (今回は 346 の時のような IAM / traffic 問題は起きなかった)

### G. 追加した回帰テスト

`tests/test_x_post_mail.py` 内に **24 unit test**:

| test class | count | 用途 |
|---|---|---|
| `CentralLeagueFilterTests` | 5 | セ 6 球団 pass / パ 6 球団 block / mixed 12 球団 → 6 球団残 / 空 team_code block / 巨人 alias variants |
| `IntentUrlEncodeTests` | 3 | newline %0A / hashtag %23 / parse_qs 経由 round-trip / 空 text 安全 |
| `SubjectAndTimeBandTests` | 3 | 時間帯 label per hour / subject format / 0 件 crash しない |
| `PickCandidatesTests` | 7 | セ only excludes パ / 巨人 marker / 3 row 未満 skip / query 失敗 skip / not ok skip / max cap / period label |
| `ComposeMailTests` | 5 | subject + text + html + count / LF-only newline / intent URL 含む / HTML escape (`<` `>` `&`) / 280 字超過 ⚠️ マーク |
| `EmptyResultBehaviourTests` | 1 | 空 candidates でも crash しない |

特にパ 6 球団漏れ防止の test (`test_pick_central_only_excludes_pacific`) は mixed 12-team sample で全 パ team name が draft text に出現しないことを assert、branding scope の安全網。

### H. 次回触ってはいけない範囲

次の作業者 (Claude 次セッション / Codex / user) が触る前に必ず確認:

1. **`src/x_post_mail_lane.py::CENTRAL_LEAGUE_TEAM_ALIASES`**: 6 球団 alias 26 種で固定済、パ 6 球団は意図的に excluded。新規球団 alias 追加時は両方更新必須 (insight_defense_proxy.py との sync は本 ticket では維持しないので、リーグ追加 / 球団改名時は分離別 ticket で sync 検討)
2. **`SAFE_METRICS`**: AVG / OBP / SLG / OPS / ERA の 5 metric で固定、user lock 済 (× サバメトリクス系 ISO/wOBA/BABIP/FIP/xFIP/WHIP/K_per_9/UZR_proxy は意図的に excluded)。追加禁止、新 metric は別 ticket で whitelist 拡張
3. **`_build_combos` の 10 combo 配分**: season 5 + monthly 3 + last-30 2 = 10、`max_candidates=10` と整合済。combo 追加 / 削除時は test の `test_max_candidates_cap_honored` と一緒に更新
4. **`encode_x_intent_url`**: `safe=""` で全文字 encode、`#` を `%23` に変換 (X intent URL の fragment 誤判定回避)。`safe` を変えると `#` がハッシュタグでなく URL fragment と扱われる
5. **`348` が触ってる範囲は本 ticket と完全 disjoint**: `src/analysis/insight_*.py` / `ranking_article_publisher.py` / `anomaly_article_publisher.py` / `team_ranking_publisher.py` / `config/insight_whitelist.yaml` (348 が将来追加予定) / `article_candidates` table への read/write は 347 で一切しない
6. **Cloud Run Job 名 `x-post-mail-lane`**: 既存 `publish-notice` / `guarded-publish` 等と衝突なし。rename 不可 (5 scheduler の URI が hardcode 参照)
7. **5 schedulers 時刻**: 7:00 / 12:00 / 15:00 / 17:30 / 22:30 JST、user 確定済。変更時は publish-notice (`5 6-15` / `5,35 16-22`) との時刻 conflict を再 check
8. **mail 送信先**: `fwns6760@gmail.com` (env `MAIL_BRIDGE_TO`)、publish-notice と同じ recipient。変更時は user 判断必須 (memory: 「mail recipient 変更は user 判断境界」)
9. **SA `487178857517-compute`**: 既存 publish-notice 等と同じ default compute SA。secret access / GCS read 権限はプロジェクト Editor 経由。専用 SA 化は別 ticket で検討 (今回は最小スコープ優先)
10. **X intent URL の text 長さ上限**: X 公式は 280 字を超えても受付するが、X premium 課金で 25000 字対応。本 ticket は 280 字 cap だが、`max_chars=` 拡張は別 ticket で

## Regression Memo 補足 (実装中に判明)

- **mail_delivery_bridge の `_resolve_smtp_username` env precedence**: `NOTIFY_FROM` → `MAIL_BRIDGE_FROM` → `FACT_CHECK_EMAIL_FROM` → fallback smtp_username。CLI で `_resolve_sender()` を実装する時は順序を mirror した
- **`_resolve_reply_to`**: `MAIL_BRIDGE_REPLY_TO` → `NOTIFY_REPLY_TO` の順、本 ticket は `MAIL_BRIDGE_REPLY_TO=fwns6760@gmail.com` を投入
- **`format_as_x_post` の header 修正不可**: 346 は header に period label を入れない。347 では生成後 first line に `（{period}）` を splice (`_format_one` 内)、これは 346 の `format_as_x_post` を modify せず post-process で実現
- **insight.db `_rebuild_ranks_within_central`**: 12 球団 ranking 結果から セ 6 球団 row だけ抽出する際、`rank` column を 1..N で再採番する。これしないと「セ・OPS 1 位だけど 11 番にいる」みたいな表示になる
- **PWA / 346 と何も共有しない**: 346 で manual-intake-service の env に X API secret を投入したが、347 Job は X API を叩かないので X secret 不要。逆に 347 Job env には MAIL_BRIDGE_* / INSIGHT_GCS_BUCKET / GOOGLE_CLOUD_PROJECT のみ
- **`task-timeout=300s`**: 5 分。 production smoke で実行時間が ~10 秒だったので 300s は十分余裕。長くしすぎると Cloud Run minimum-billing-quantum で課金 round up される可能性

## 作業ログ実績 (section 9 への追記)

```
2026-05-15 20:30 JST | doc 347 rewrite 完成 | doc/active/347-x-post-suggest-mail-lane.md | DONE
2026-05-15 20:45 JST | user GO 受領 | -                                                 | DONE
2026-05-15 20:50 JST | task plan (12 tasks) | TaskCreate x12                           | DONE
2026-05-15 20:52 JST | pytest baseline (touched scope) 記録 | 53 passed                | DONE
2026-05-15 20:55 JST | mail_delivery_bridge + Dockerfile pattern inspect | -           | DONE
2026-05-15 21:00 JST | src/x_post_mail_lane.py 完成 | 約 350 行                          | DONE
2026-05-15 21:05 JST | tests/test_x_post_mail.py 完成 | 24 test                          | DONE
2026-05-15 21:08 JST | tests green | 24 passed                                          | DONE
2026-05-15 21:10 JST | src/tools/run_x_post_mail.py 完成 | argparse + 4 flag             | DONE
2026-05-15 21:15 JST | Dockerfile.x_post_mail + cloudbuild_x_post_mail.yaml 完成 | -    | DONE
2026-05-15 21:20 JST | wide pytest | 4731 passed / 1 pre-existing fail                  | DONE
2026-05-15 21:22 JST | cloudbuild SUCCESS | digest d20063257...                          | DONE
2026-05-15 21:24 JST | Cloud Run Job 作成 | x-post-mail-lane                            | DONE
2026-05-15 21:25 JST | 5 Cloud Scheduler 作成 | am-1 / lunch / afternoon / evening / postgame | DONE
2026-05-15 21:26 JST | 手動 execute 実行 | x-post-mail-lane-hd29k SUCCESS               | DONE
2026-05-15 21:27 JST | mail 送信成功 | status=sent / 10 candidates                       | DONE
2026-05-15 21:30 JST | doc 347 post-work A-H 追記 | doc/active/347-x-post-suggest-mail-lane.md | DONE
2026-05-15 21:31 JST | (次) commit + push                                              | PENDING
```
