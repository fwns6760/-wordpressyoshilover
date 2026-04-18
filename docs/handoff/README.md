# ヨシラバー開発 引き継ぎドキュメント

このディレクトリはヨシラバー開発の完全な引き継ぎ情報を集約しています。
新規Claudeチャット・新しいCodexセッション・Claude Codeセッションに
移行する際の参照点です。

## 読む順序

### 必須（最初に読む）
1. [00_project_overview.md](00_project_overview.md) — プロジェクト全体像
2. [03_current_state.md](03_current_state.md) — 今の本番状態
3. [07_current_position.md](07_current_position.md) — 今ここ（現在地）
4. [08_next_steps.md](08_next_steps.md) — 次の一歩
5. [01_roles_and_rules.md](01_roles_and_rules.md) — 役割と運用ルール（必須）
6. [06_failure_patterns.md](06_failure_patterns.md) — 避けるべき失敗（必須）

### 時間があれば
- [02_implemented_systems.md](02_implemented_systems.md) — 実装済み全量
- [04_work_history.md](04_work_history.md) — 2日間の作業履歴
- [05_roadmap.md](05_roadmap.md) — ロードマップ
- [10_chat_migration.md](10_chat_migration.md) — 移行手順
- [11_codex_prompt_library.md](11_codex_prompt_library.md) — Codexプロンプト実例集
- [12_yoshihiro_communication_style.md](12_yoshihiro_communication_style.md) — 口調・反応パターン
- [13_strategy_deep_dive.md](13_strategy_deep_dive.md) — 戦略議論の深掘り
- [14_x_posting_examples.md](14_x_posting_examples.md) — Xポスト実例集

### 会話ログ（詳細な経緯）
- [conversation_logs/](conversation_logs/) 配下

### 監査・チケット（チャット消失時の引き継ぎ用）
- [tickets/OPEN.md](tickets/OPEN.md) — **未解決チケット一覧（最重要）**
- [tickets/RESOLVED.md](tickets/RESOLVED.md) — 解決済みアーカイブ
- [session_logs/](session_logs/) — Claude Codeセッションの監査ログ

**チャットが消えた時の復帰手順**:
1. `README.md` を読む（このファイル）
2. `tickets/OPEN.md` で未解決の課題を把握
3. `session_logs/` の最新ファイルでClaude Codeが何をやっていたか確認
4. `07_current_position.md` で全体の現在地を確認

## 最終更新
2026-04-18 朝

## 重要事項（必ず守る）
- **env変更ルール**: 必ず既存進行中Claudeチャット経由。新規チャットからは絶対にenvを触らない
- **体力減らしモード遵守**: Yoshihiroの判断コストを最小化する設計を維持
- **Phase C公開は段階的に**: カテゴリ単位、受け入れ試験合格後のみ
- **テスト354本を割らない**: 全変更後に `pytest` でグリーンを確認

## 関連する重要ファイル（このdocs/handoff/外）
- `docs/phase_c_runbook.md` — Phase C運用手順（本番操作の正）
- `docs/acceptance_test_checklist.md` — 受け入れ試験チェックリスト
- `docs/operation_logs.md` — Cloud Loggingクエリ集
- `docs/phase_3_step1_setup.md` — メール通知セットアップ手順
- `docs/roadmap.md` — Phase D〜Fロードマップ
- `AGENTS.md` — Codex向け設計書（全体設計の正）
