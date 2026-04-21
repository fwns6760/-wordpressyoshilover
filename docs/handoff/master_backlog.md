# Master Backlog — yoshilover

**最終更新**: 2026-04-19 JST
**運用**: 完了時に `【】` を `【×】` に書き換える。起票は Claude、判断は user、実装は Codex。
**判定軸**: MVP = 1人+AI でのもとけ再現、運用ループが閉じていること（機能単品ではない）

---

## Phase 1 — release 到達 TODO（20 本）

### 🔴 critical（release blocker / 1本）

- 【】 **MB-001** WP plugin `yoshilover-exclude-cat.php` を Xserver 反映（T-001 継承、user 権限必要）

### 🟠 high（release 必須 / 4本）

- 【】 **MB-002** publish 解放: `ENABLE_PUBLISH_FOR_MANAGER=1` + smoke + 監査（Codex）
- 【】 **MB-003** publish 解放: `ENABLE_PUBLISH_FOR_PREGAME=1` + smoke + 監査（Codex）
- 【】 **MB-004** publish 解放: `ENABLE_PUBLISH_FOR_FARM=1` + smoke + 監査（Codex）
- 【】 **MB-005** prompt: chain of reasoning 強制（事実→解釈→感想）で no_opinion 対策（Codex、T-021 第4弾）

### 🟡 medium（release 必須 / 12本）

- 【】 **MB-006** X 自動投稿 ON: postgame（`ENABLE_X_POST_FOR_POSTGAME=1` + `AUTO_TWEET_ENABLED=1`、Codex + user 判断）
- 【】 **MB-007** X 自動投稿 ON: lineup（`ENABLE_X_POST_FOR_LINEUP=1`、Codex + user 判断）
- 【×】 **MB-008** T-017 07:00 JST demo 落ち観察完了（2026-04-19、48h 観察 demo 再発なし → T-017 RESOLVED、Claude）
- 【×】 **MB-010** 選別ルール明文化（2026-04-19 完了、docs/editorial_policy.md §1）
- 【×】 **MB-011** subtype × カテゴリマトリクス明文化（2026-04-19 完了、docs/editorial_policy.md §2）
- 【×】 **MB-012** `docs/editorial_policy.md` 新設（2026-04-19 完了、MB-010/011 統合）
- 【×】 **MB-013** publish 解放条件 DoD 記述（2026-04-19 完了、docs/release_gate.md §1。threshold は user 調整余地あり）
- 【×】 **MB-014** X 解放条件 DoD 記述（2026-04-19 完了、docs/release_gate.md §2。threshold は user 調整余地あり）
- 【×】 **MB-015** rollback 条件記述（2026-04-19 完了、docs/release_gate.md §3）
- 【×】 **MB-016** `docs/daily_ops_checklist.md` 新設（2026-04-19 完了、Claude）
- 【×】 **MB-017** `docs/handoff/decision_log.md` 新設 + 過去判断遡及記録（2026-04-19 完了、Claude）
- 【】 **MB-019** T-021 第2弾 canary promote/kill 判断（ARTICLE_INJECT_TEAM_STATS、user → Codex）

### 🟢 release 後でも可（docs 整備 / 3本）

- 【×】 **MB-009** T-024 を RESOLVED.md に移動（2026-04-19 完了、Claude）
- 【】 **MB-018** canary tag `audit-notify-canary` を prod revision から削除（Codex）
- 【×】 **MB-020** AGENTS.md / PHASE-C-RUNBOOK.md / 08_next_steps.md 更新（2026-04-19 完了、Claude。OPEN.md 古記述点検は継続）

---

## Phase 2 — parking lot（18本）

- 【】 **MB-P2-01** 公式 / マスコミ X ポスト自動取得
- 【】 **MB-P2-02** 手動 URL 投入導線
- 【】 **MB-P2-03** prompt: subtype 別 temperature
- 【】 **MB-P2-04** audit axis: repetition
- 【】 **MB-P2-05** publish 解放: notice
- 【】 **MB-P2-06** publish 解放: recovery
- 【】 **MB-P2-07** publish 解放: social
- 【】 **MB-P2-08** publish 解放: player
- 【】 **MB-P2-09** publish 解放: general
- 【】 **MB-P2-10** X 自動投稿 解放: manager / pregame / farm / 他
- 【】 **MB-P2-11** コメント欄本格運用
- 【】 **MB-P2-12** 選手別深掘り連載
- 【】 **MB-P2-13** 過去データ可視化 / グラフ
- 【】 **MB-P2-14** 速報密度向上（試合中 5-15分更新ループ）
- 【】 **MB-P2-15** AdSense 最適化
- 【】 **MB-P2-16** Discord / 会員化
- 【】 **MB-P2-17** Podcast / 音声記事
- 【】 **MB-P2-18** タグベース導線強化（選手名 50+ 横断）

---

## 継続監査ループ（Claude 自律タスク、完了なし）

Phase 1 前後問わず **Claude が自律的に回し続ける**監査。one-shot チケットではないので 【】 / 【×】 管理対象外。trend 記録と改善提案起票に集約する。

### A. 本文精度監査（Flash 記事品質）

- **トリガー**: `audit-notify-6x` メール着信（JST 11/13/15/17/20/23）
- **観点**: audit 5軸（title_body_mismatch / thin_body / no_opinion / no_eyecatch / pipeline_error）の軸別件数トレンド、subtype / category 偏り、共通 Flash prompt 課題
- **起票判断**:
  - 同じ軸で連続 3 日 10 件/日以上 → 即 Codex 改善 prompt 起票
  - 散発 (1-2 件/日) → 2 週間観察、trend を見る
- **改善候補（cost 増なし）**: 材料境界明示 / chain of reasoning（MB-005）/ subtype 別 temperature
- **初回データ（2026-04-19、window=1440 対象 7 件）**: no_opinion 6 / title_body_mismatch 1 / 他 0。no_opinion 対策が的中見込み高 → MB-005 起票済

### B. ポスト精度監査（X 文案品質）

- **前提**: Phase 1 で `AUTO_TWEET_ENABLED=1` + postgame / lineup ON に切り替わった後から発動
- **観点**:
  - 文案と記事本文の整合（事実歪み / 誇張 / 煽り）
  - 読者反応（inpressions / engagement、後段で要検討）
  - 事故率（X rate limit / refused / 削除要請）
  - `AUTO_TWEET_REQUIRE_IMAGE` 違反
  - `X_POST_DAILY_LIMIT=10` 到達頻度
- **起票判断**:
  - 事故（誇張 / 事実歪み）1 件でも確認 → 即 rollback 相談（user 判断）
  - 文案品質（主観 / 1段深い視点）不足 → 2 週間観察後に X prompt 改善便
- **監査手段（実装必要）**: 現状 X 文案の audit endpoint は無い。Phase 1 で X 解放する時に audit-notify に X 軸追加 or 専用 endpoint 新設を検討（→ 将来 MB-P2 候補）

### C. 記事構造監査（記事の作り方の適切性）

- **目的**: Flash が「ちゃんと適した記事」を作っているかを構造レベルで見る。audit 5 軸（検出）では捕まらない、作り方そのものの適切性を確認
- **観点**:
  - subtype ごとの「あるべき構造」との乖離
    - postgame: 導入 / 試合経過 / 勝敗分岐 / 選手コメント / 一次情報リンク
    - lineup: スタメン表 / 相手投手 / 注目選手 / 一次情報リンク
    - manager: 発言引用 / 発言の文脈 / 解釈 / 一次情報リンク
    - pregame: 試合前提 / 先発予想 / 注目点 / 一次情報リンク
    - farm: 2 軍結果 / 選手動向 / 一次情報リンク
  - 見出し構成（H2 / H3 の使い方、段落分け）
  - 一次情報の配置（本文冒頭 vs 末尾）
  - 「のもとけらしさ」の 3 要素（一次情報核 / 転載要約で終わらない / ファン視点1段）が満たされているか
  - 関連記事ブロック（`yoshilover-related-posts`）が適切に挿入されているか
  - team batting stats 注入（flag ON 時）が自然か
- **手法**: Claude が実記事を subtype ごとに 2-3 件 sampling で読む（週 1 頻度、もしくは audit メール異常時）
- **起票判断**:
  - 構造的問題が 同一 subtype 内で 3 件続く → prompt builder 改善便を起票
  - 単発の文体揺れ → 観察継続、起票しない
  - 「のもとけらしさ」3 要素のいずれかが常態的に欠落 → prompt 改善便
- **既存関連チケット**: MB-005（chain of reasoning）/ T-021 第1弾（関連記事挿入、解消済）/ T-021 第2弾（team stats 注入、検証中）

### D. 継続監査の記録先

- 恒久知見 → CLAUDE.md に追記
- セッション観察 → `docs/handoff/session_logs/YYYY-MM-DD_claude_code_audit.md`
- trend 数値 → master_backlog.md §継続監査ループ に月次で追記

---

## 観察・保留（3本、Phase 1 blocker ではない）

- 【】 **T-005** prompt library 原文差し替え（低優先、Opus chat 履歴に実物あれば）
- 【】 **T-014** subject needs_manual_review 4件（WONTFIX 寄せ保留、systemic 化したら昇格）
- 【】 **T-021 第2弾** canary `ARTICLE_INJECT_TEAM_STATS=1` 検証（→ MB-019 で判断）

---

## 既完了（19本）

- 【×】 **T-002** 61981 opponent 誤記修正（阪神→楽天）
- 【×】 **T-003** draft 件数可視化 `draft_inventory_from_logs`（`10fa214`）
- 【×】 **T-004** 朝の fact_check メール受信確認
- 【×】 **T-006** Phase 3段階1 メール実受信確認
- 【×】 **T-007** fact_check パーサー修正（score/venue fallback、`ba97edc`）
- 【×】 **T-008** 62527 title 修正（DeNA→ヤクルト）
- 【×】 **T-010** `source_reference_missing` 全解消（`a08d875` + 第13便 backfill）
- 【×】 **T-011** T-007 修正を Cloud Run 反映（revision `00131-mpn`）
- 【×】 **T-012** fact_check: 歴史参照 opponent 誤認修正（`d6e19eb`）
- 【×】 **T-013** T-012 修正を Cloud Run 反映（revision `00132-lgv`）
- 【×】 **T-015** T-010 修正を Cloud Run 反映（revision `00133-gvf`）
- 【×】 **T-016** fact_check メール Gmail スレッド化誤検知 + hourly + skip-on-empty
- 【×】 **T-018** fact_check メール運用サマリ追加
- 【×】 **T-019** 62584 アイキャッチ欠損調査（emoji SVG、`3fb5381`）
- 【×】 **T-020** アイキャッチ emoji SVG 除外拡張 + fallback（revision `00137-q77`）
- 【×】 **T-021 第1弾** 過去記事リンク自動挿入（revision `00138-mqn`）
- 【×】 **T-022** 土曜 18-19 JST scheduler gap 解消（`f902b81`）
- 【×】 **T-023** 平日 18-19 JST filter WONTFIX 根拠（`8c5a276`）
- 【×】 **T-024** `/audit_notify` endpoint + `audit-notify-6x` scheduler（revision `00143-luj`、実態 done / 台帳整合は MB-009）

---

## Reference

### 1. Phase 1 release 条件（7本、全完了で release）

1. publish subtype: **postgame / lineup + manager / pregame / farm の 5種**（→ MB-002/003/004）
2. X 自動投稿: **postgame / lineup のみ ON**（→ MB-006/007）
3. 一次情報リンク: `yoshilover-related-posts` + 出典ブロック継続（✅）
4. audit 監視: `audit-notify-6x` 稼働（✅）
5. fact check pipeline 継続（✅）
6. prompt 改善 1本: no_opinion 対策（→ MB-005）
7. 運用 blocker 解消: T-001 / T-017 / T-024（→ MB-001/008/009）

### 2. MVP 成立条件（7項目 / 運用ループ視点）

1. 情報源の定期取得（RSS / 公式・マスコミ X / 手動投入）
2. 自動選別 → 記事候補化
3. WP 安定生成（タイトル / 本文 / カテゴリ / アイキャッチ / 一次情報 / 関連記事）
4. のもとけらしさ（一次情報核 / ファン視点1段 / 巨人特化カテゴリ網羅）
5. 品質事故の自動検知
6. 運用コスト低（1日5〜10分、スマホ確認、「公開/しない」のみ）
7. 公開後の拡散導線

### 3. MVP でまだ要らない（起票しても延期 or 却下）

1. コメント欄の本格運用
2. 試合中フル自動実況
3. LINE 通知
4. SEO 磨き込み
5. UI 凝った作り込み
6. AdSense 最適化
7. 完全スマホ完結運営

### 4. のもとけ観察（`dnomotoke.com`、2026-04-19）

| 軸 | のもとけ | yoshilover Phase 1 方針 |
|---|---|---|
| 記事量 | 20-30本/日 | 10本/日目標 |
| 主要 subtype | 公示/首脳陣/選手/故障/2軍/試合速報 | postgame/lineup + manager/pregame/farm |
| 一次情報 | 監督・選手コメント直引用 | source link ブロック継続 |
| ファン視点 | 率直な感情表現 | chain of reasoning で強制 |
| X 連携 | 先出し → 記事化 | postgame / lineup のみ ON |
| コメント | 366件/記事 | Phase 2 送り |

### 5. 運用ループ 5本 と現状態

1. **情報収集ループ** — RSS ✅ / X 取得 ⚪ Phase 2 / 手動投入 ⚪ Phase 2
2. **記事生成ループ** — 選別・生成・関連記事 ✅ / team_stats canary 🟢 / prompt 改善 🔵 MB-005
3. **品質監視ループ** — fact_check ✅ / audit_notify ✅ / 5軸 ✅
4. **publish ループ** — postgame/lineup ✅ / manager/pregame/farm 🔵 MB-002〜004 / WP反映 🔴 MB-001
5. **X 連携ループ** — 文案生成 ✅ / postgame/lineup 自動投稿 🔵 MB-006/007

### 6. 実環境スナップショット（2026-04-19 JST）

| 項目 | 値 |
|---|---|
| Cloud Run | `yoshilover-fetcher` / project `baseballsite` / region `asia-northeast1` |
| 100% traffic | `yoshilover-fetcher-00143-luj`（tag=`audit-notify-canary` 残存） |
| 残 revision | `00117-kes` (stage1) / `00141-cen` (canary-team-stats) |
| `RUN_DRAFT_ONLY` | `0` |
| `AUTO_TWEET_ENABLED` | `0` |
| `PUBLISH_REQUIRE_IMAGE` | `1` |
| `ENABLE_PUBLISH_FOR_POSTGAME` / `LINEUP` | `1` / `1` |
| 他 `ENABLE_PUBLISH_FOR_*` | `0`（9種） |
| 全 `ENABLE_X_POST_FOR_*` | `0` |
| `ENABLE_ENHANCED_PROMPTS` | `1` |
| `ARTICLE_INJECT_TEAM_STATS` | prod 未設定（canary のみ `1`） |
| Scheduler `audit-notify-6x` | ENABLED `0 2,4,6,8,11,14 * * * UTC` |
| Scheduler `fact-check-morning-report` | ENABLED hourly |
| Scheduler giants-* 群 | ENABLED |
| Scheduler `yoshilover-fetcher-job` | PAUSED |

### 7. release readiness

**Phase 1 release blocker**: **MB-001 のみ**（user 権限提供待ち）
他 16 本は並行解消可能。

**Phase 1 進捗**: 0 / 17 完了（release 必須分）
**Phase 1 全体**: 0 / 20 完了（release 後 docs 込み）
**全量**: 0 / 60 完了（既完了 19 を除く残タスク 41）

### 8. 3者分担（Phase 1 残 20 本）

| 担当 | 本数 | チケット |
|---|---|---|
| user 判断 | 2 | MB-001 / MB-019 |
| Codex 実装 | 7 | MB-002 / 003 / 004 / 005 / 006 / 007 / 018 |
| Claude docs・監査 | 11 | MB-008 / 009 / 010 / 011 / 012 / 013 / 014 / 015 / 016 / 017 / 020 |

---
