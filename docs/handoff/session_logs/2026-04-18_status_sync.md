# 状態同期メモ — 2026-04-18 夕方時点（Codex / Claude Code 共有用）

## 完了 ✅

- **第11便 T-015**: Cloud Run deploy `00133-gvf`（a08d875）
- **第12便 T-014 調査**: 62003 非再現 / 61779 (Y) 抽出ミス 確定
- **第13便 T-010 backfill**: A=5件の source URL 補填、4件 green + 61754 別軸 yellow
- **第14便 T-016 観測性**: send_email() に Message-ID / refused_recipients / smtp_response 追加（01ed7b2）
- **第15便 Scheduler**: `0 7,12,17,22 * * *` → `*/30 * * * *`（完了、ab49c6c に response doc あり）
- **T-016 根本原因判明**: Gmail スレッド化で「届いてない」ように見えていた、SMTP 経路は健全
- **第16便 コード実装 + Cloud Run deploy**: 新 revision `00135-rpc` traffic 100%（16:46:57 JST 昇格）

## 未完了（第16便の残作業） ⏳

1. smoke test の完了確認
2. Scheduler を `*/30 * * * *` → `0 * * * *` に更新
3. 手動 trigger 1 回 + ログ確認（send / skip のどちらかが出ること）
4. `docs/handoff/codex_responses/2026-04-18_16.md` 作成
5. Codex local commit `ab349de` を origin/master へ push

## 現在の実態（実測）

| 項目 | 状態 |
|---|---|
| origin/master 最新 | `ab49c6c docs(handoff): add codex response 15` |
| Cloud Run traffic | `yoshilover-fetcher-00135-rpc` 100% |
| Scheduler `fact-check-morning-report` | `*/30 * * * *` ENABLED |
| Codex local 未 push commit | `ab349de`（第16便 実装本体） |

## チケット状況

- **RESOLVED 移動待ち**（第16便完了で確定）:
  - T-016 🔴（Gmail スレッド化誤検知 + 第15便 scheduler 変更）
  - T-018 🟡（運用サマリ追加、第16便に統合）
- **様子見**:
  - T-017 🟠（cold start demo 落ち。30分〜1時間稼働で常時 warm → 2-3日観察後 RESOLVED 候補）
- **継続 OPEN**:
  - T-001 🟠（Xserver 接続情報待ち、ブロック中）
  - T-014 🟡（subject:needs_manual_review 4件、WONTFIX 寄せ）
  - T-004 🟠 / T-005 🟡 / T-006 🟡（よしひろさん確認待ち）

## 第16便仕様（再開時参照）

依頼書: `docs/handoff/codex_requests/2026-04-18_16.md`（a42f9cc）

- Scheduler 最終: `0 * * * *`
- 件名フォーマット: `ヨシラバー MM/DD HH:00 🔴N 🟡M ✅K`
- 送信判定: 直近1時間窓に post あり OR 全体に red あり → 送信、どちらもなし → skip
- 本文に運用サマリ（T-018）追加
- env 変更禁止、観測性（Message-ID / refused / smtp_response）維持

## Codex 再開用コピペ

```
第16便（docs/handoff/codex_requests/2026-04-18_16.md）の残作業を続行してください。

現状:
- コード変更は ab349de で local commit 済み（未 push）
- Cloud Run revision 00135-rpc に deploy 済み、traffic 100%
- Scheduler は未だ `*/30 * * * *`

残作業:
1. smoke test 完了確認（scripts/cloud_run_smoke_test.sh）
2. Scheduler を `0 * * * *` に更新
3. 手動 trigger 1回 → ログで send/skip 判定確認
4. response doc 作成（docs/handoff/codex_responses/2026-04-18_16.md）
5. ab349de を origin/master へ push

state sync メモ: docs/handoff/session_logs/2026-04-18_status_sync.md
```
