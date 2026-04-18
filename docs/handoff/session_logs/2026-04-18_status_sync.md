# 状態同期メモ — 2026-04-18 夜時点（Codex / Claude Code 共有用）

## 完了 ✅

- **第11便 T-015**: Cloud Run deploy `00133-gvf`（a08d875）
- **第12便 T-014 調査**: 62003 非再現 / 61779 (Y) 抽出ミス 確定
- **第13便 T-010 backfill**: A=5件の source URL 補填、4件 green + 61754 別軸 yellow
- **第14便 T-016 観測性**: send_email() に Message-ID / refused_recipients / smtp_response 追加（01ed7b2）
- **第15便 Scheduler**: `0 7,12,17,22 * * *` → `*/30 * * * *`（ab49c6c）
- **T-016 根本原因判明**: Gmail スレッド化で「届いてない」ように見えていた、SMTP 経路は健全
- **第16便 T-016/T-018 完了**（ab349de, revision `00135-rpc`, origin/master=157b4f0）:
  - `_should_send_email()` 導入（hourly_window_has_posts / red_present / no_change_no_red）
  - 件名 `ヨシラバー MM/DD HH:00 🔴N 🟡M ✅K`
  - 直近24h 運用サマリ helper（rss_fetcher_run_summary / flow_summary 集計）
  - Scheduler `0 * * * *` Asia/Tokyo ENABLED
  - 手動 trigger 観測: `fact_check_email_skipped` reason=`no_change_no_red` 確認
  - test 379 passed
- **T-016 / T-018 RESOLVED 移動済み**

## 現在の実態（実測）

| 項目 | 状態 |
|---|---|
| origin/master 最新 | `157b4f0 docs(handoff): add codex response 16` |
| Cloud Run traffic | `yoshilover-fetcher-00135-rpc` 100% |
| Scheduler `fact-check-morning-report` | `0 * * * *` Asia/Tokyo ENABLED |
| env | `RUN_DRAFT_ONLY=1` / `AUTO_TWEET_ENABLED=0` / `PUBLISH_REQUIRE_IMAGE=1` |

## チケット状況

- **RESOLVED（2026-04-18）**:
  - T-010 🟡（旧記事 source_reference_missing 全解消）
  - T-016 🔴（Gmail スレッド化誤検知判明 + 1時間 skip-on-empty メール化）
  - T-018 🟡（運用サマリ追加、第16便に統合）
- **様子見**:
  - T-017 🟠（cold start demo 落ち。1時間おき稼働で常時 warm → 2-3日観察後 RESOLVED 候補）
- **継続 OPEN**:
  - T-001 🟠（pre_get_posts 真犯人判明、REST_REQUEST 除外の修正待ち）
  - T-004 🟠 / T-005 🟡 / T-006 🟡（よしひろさん確認待ち）
  - T-014 🟡（subject:needs_manual_review 4件、WONTFIX 寄せ、systemic 化したら昇格）

## 次の動き候補

1. **T-017 2-3 日様子見** → 07:00 JST run のログ観測（demo に倒れないか）
2. **T-001 修正便**（`src/yoshilover-exclude-cat.php` の `pre_get_posts` で REST_REQUEST 除外）
3. **Phase C 公開解放**（MVP 公開向け、よしひろさん判断）
4. **T-014 WONTFIX 判断**（4件確認後）

## 2〜3日後の観測確認項目（T-017）

```bash
# 07:00 JST run のログ確認
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="yoshilover-fetcher" AND (jsonPayload.event="fact_check_email_sent" OR jsonPayload.event="fact_check_email_skipped" OR jsonPayload.event="fact_check_email_demo") AND timestamp>="2026-04-19T22:00:00Z"' \
  --project baseballsite --limit 10 --format json \
  | jq '.[].jsonPayload | {event, reason, timestamp}'
```

- `fact_check_email_demo` が 07:00 JST で出なければ T-017 RESOLVED
- 出続けるなら第17便（`_load_gmail_app_password()` 修正）
