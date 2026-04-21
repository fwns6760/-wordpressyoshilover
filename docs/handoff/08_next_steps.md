# 次の一歩（2026-04-19 以降）

**このファイルの位置付け**: 2026-04-18 までは Phase C 段階管理用だったが、2026-04-19 に MVP 枠組みが「Phase C 段階」→「のもとけ再現 Phase 1」に切り替わったため、当ファイルは **master_backlog への誘導スタブ** として運用する。

## 単一ソース

release 進捗と次の一手はすべて `docs/handoff/master_backlog.md` を見る:

- Phase 1 release TODO 20 本（🔴 critical / 🟠 high / 🟡 medium / 🟢 release 後）
- 3 者分担（user 判断 / Codex 実装 / Claude docs・監査）
- release readiness 指標
- 実環境スナップショット（revision / env flag / Scheduler）

## 判断軸

- Phase 1 成立条件 7 項目: `CLAUDE.md §MVP 定義 §Phase 1 リリース条件`
- MVP 成立条件 7 項目（運用ループ視点）: `CLAUDE.md §MVP 定義 §成立条件`

## 過去判断の追跡

- `docs/handoff/decision_log.md`（2026-04-19 新設）

## 日次運用

- `docs/daily_ops_checklist.md`（2026-04-19 新設）

---

## 旧 Phase C 記述（2026-04-18 までのスナップショット、参考）

Phase C 3 段階設計（Stage1: publish 解放 / Stage2: X 投稿優先カテゴリ / Stage3: フル運用）は `docs/PHASE-C-RUNBOOK.md` に保全。Phase 1 枠組みでは:

- Stage1 相当 → 既完了（postgame / lineup publish 解放済み、`ENABLE_PUBLISH_FOR_POSTGAME=1` / `LINEUP=1`）
- 次: manager / pregame / farm publish 解放（MB-002 / 003 / 004）
- その後: X 自動投稿 ON（MB-006 / 007、postgame / lineup のみ）

## 関連 log

- `docs/handoff/session_logs/` 配下の監査セッションログ
- `docs/handoff/codex_responses/` 配下の Codex 回答
- `docs/handoff/tickets/OPEN.md`（bug 台帳、release backlog ではない）
- `docs/handoff/tickets/RESOLVED.md`（解決チケットアーカイブ）
