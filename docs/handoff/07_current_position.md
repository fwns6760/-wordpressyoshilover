# 今ここ（2026-04-18 夜の現在地）

## 今日完了したこと（2026-04-18）

### RESOLVED（7チケット）

- T-007（venue/score 誤抽出の根本修正）
- T-011（T-007 Cloud Run deploy）
- T-012（fact_check の `○日○○戦` 歴史参照 false positive 修正）
- T-013（T-012 deploy）
- T-015（T-010 (a) `extract_source_links()` 拡張 deploy）
- T-016（fact_check メール配送 metadata 観測性強化、Gmail スレッド化誤検知判明）
- T-018（1時間おき fact-check メール化 + skip-on-empty + 24h 運用サマリ）

### T-001 コード修正完了（本番反映は第18便）

- `src/yoshilover-exclude-cat.php` の `pre_get_posts` / `posts_where` 両フック先頭に
  `if (defined('REST_REQUEST') && REST_REQUEST) return;` を追加（第17便、`f09cffc`）
- `php -l` OK / python test 379 passed
- WP (Xserver) 反映は Xserver SSH 接続情報が揃い次第、第18便で実施

### publish 全量 fact_check 監査（新parser）

- publish 36件: green 16 / yellow 20 / **red 0**
- yellow 20 の内訳:
  - `source_reference_missing`: 19件（うち 14件は T-010 (a) で解消、A クラス 5件は backfill で 1件解消、4件残）
  - `subject: needs_manual_review`: T-014 対象 4件
- red 0件維持は T-007 / T-012 修正の成果

## インフラ実態（2026-04-18 夜時点）

| 項目 | 状態 |
|---|---|
| Cloud Run revision | `yoshilover-fetcher-00135-rpc`（traffic 100%） |
| origin/master 最新 | `3cb457b docs(handoff): close T-001 code fix, update session log for 便17` |
| テスト数 | 379 passed |
| Scheduler `fact-check-morning-report` | `0 * * * *` Asia/Tokyo ENABLED（毎時 hourly） |
| env | `RUN_DRAFT_ONLY=1` / `AUTO_TWEET_ENABLED=0` / `PUBLISH_REQUIRE_IMAGE=1` |
| Phase C publish フラグ 20個 | 全て `0`（待機） |
| ローカル環境 | `php 8.3.6` 導入済（以後 PHP 便で Codex が自律 lint 可能） |

## 残 OPEN チケット

- **T-001 🟠**: コード修正完了、本番反映待ち（Xserver SSH 接続情報 or WP admin plugin 差し替え権限）
- **T-004 🟠**: 今朝の fact_check メール受信確認（よしひろさん側 Gmail 確認）
- **T-005 🟡**: `11_codex_prompt_library.md` の再構築扱い（低優先度）
- **T-006 🟡**: Phase 3 段階1 メール実受信確認（よしひろさん側 Gmail 確認）
- **T-010 🟡**: source_reference_missing Aクラス 5件（低優先度、systemic ではない）
- **T-014 🟡**: subject needs_manual_review 4件（WONTFIX 寄せ保留、systemic 化したら昇格）
- **T-017 🟠**: 07:00 JST cold start demo 落ち（hourly 化で warm 維持見込み、2-3日観察中）

## Claude Opus（壁打ち）の状態

- 戦略・設計レビュー用。日常の監査 / チケット管理 / Codex 依頼書作成は Claude Code に一本化
- Phase C 解放判断など、よしひろさんの意思決定が重い局面では Opus で壁打ちしてから Codex 実行

## Codex の状態

- 最後の実装: 第17便 `f09cffc`（T-001 REST ガード）
- 次の作業待ち: Phase C 解放判断が出れば env 変更 + deploy、または T-001 第18便（Xserver 情報入手後）

## 現在地の一言

**Phase C 公開解放の判断ゲートに到達済み**。受け入れ試験の代わりに publish 全量 fact_check
監査を実施済みで、red 0件 / yellow は systemic でない。あとはよしひろさんが
`ENABLE_PUBLISH_FOR_POSTGAME=1` / `_LINEUP=1` + `RUN_DRAFT_ONLY=0` への切替を判断するだけ。
