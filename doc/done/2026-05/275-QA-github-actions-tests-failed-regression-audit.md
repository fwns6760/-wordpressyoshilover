# 275-QA-github-actions-tests-failed-regression-audit

| field | value |
|---|---|
| ticket_id | 275-QA-github-actions-tests-failed-regression-audit |
| priority | P1 (P0 公開復旧 観察継続中、P0 再発時はそちら最優先) |
| status | AUDIT_DONE / READY_FOR_FIX |
| owner | Claude (audit) → Codex (修正委譲、user GO 後) |
| lane | QA |
| ready_for | 修正 Codex 便 fire(user GO 後) |
| blocked_by | (なし、独立) |
| doc_path | doc/active/275-QA-github-actions-tests-failed-regression-audit.md |
| created | 2026-04-30 |

## 1. 結論:本番影響あり / なし

**本番影響なし**(test mock 不整合のみ、src 動作は正常)。

ただし **CI が常時赤 = 本番デグレ検知不能** = 受け入れ不可。修正必須。

## 2. 今回変更起因 / 既存問題(切り分け)

| エラー種別 | 件数 | 起源 commit | 本日 P0 起因 / 既存 | 修正対象 |
|---|---|---|---|---|
| `AttributeError: SyntheticDraftWPClient.list_posts` | **5 件** | **263-QA (`7667658`、04-29)** で `wp_client.list_posts()` を `_duplicate_guard_posts` に追加 | **本日 P0 起因(04-29)** | `src/sns_topic_publish_bridge.py:53` `SyntheticDraftWPClient` mock に `list_posts` method 追加 |
| `'pregame_score_fabrication' != 'NO_GAME_BUT_RESULT'` | **1 件** | 04-26 以前から(test_fact_conflict_guard.py:159) | **既存 ambient (P0 起因ではない)** | `tests/test_fact_conflict_guard.py` または body validator 側 |

## 3-5. 落ちている workflow / job / test

- **workflow**: `Tests` (`.github/workflows/tests.yml`)
- **job**: `unittest`
- **test 6 件 (latest a175f24 run id 25142915062)**:
  1. `test_sns_topic_publish_bridge.SNSTopicPublishBridgeTests.test_roster_movement_draft_is_publishable_yellow` — AttributeError
  2. `test_sns_topic_publish_bridge.SNSTopicPublishBridgeTests.test_sns_derived_yellow_logged_into_yellow_log` — AttributeError
  3. (他 3 件、test_sns_topic_publish_bridge 系 同じ AttributeError)
  4. `test_fact_conflict_guard.FactConflictGuardFixedLaneTests.test_body_validator_escalates_hard_fail_tags_without_repair` (expected_tag='NO_GAME_BUT_RESULT') — AssertionError

## 6. 失敗理由

### A. SyntheticDraftWPClient AttributeError 5 件 (P0 起因)

`src/guarded_publish_runner.py:1722` で `wp_client.list_posts(...)` を呼ぶ:
```python
def _duplicate_guard_posts(wp_client, status):
    rows = wp_client.list_posts(...)
```

これは 263-QA (`7667658`、04-29) で重複検出のために追加された。

しかし `src/sns_topic_publish_bridge.py:53` の `SyntheticDraftWPClient` test mock は `get_post / update_post_fields / update_post_status / debug_snapshot` のみで、`list_posts` 未定義。

→ test 内 `bridge.run_sns_topic_publish_bridge()` が `runner.run_guarded_publish()` を経由する際に AttributeError。

### B. fact_conflict_guard AssertionError 1 件 (ambient)

`tests/test_fact_conflict_guard.py:159`:
- expected: `NO_GAME_BUT_RESULT`
- actual: `pregame_score_fabrication`

stop_reason 判定の category が変わった可能性(別 ticket で文字列を変更してテストが追従していない)。本日 P0 修正の commit には含まれない。

## 7. 最初に赤くなった commit

| 観点 | commit |
|---|---|
| **last green run** | `cc6d2b1` (2026-04-29 00:23 UTC = 09:23 JST) |
| **first fail in last 200 runs** | `147507c` (2026-04-26 01:15 UTC = 10:15 JST、132 ticket、別 issue) |
| **last green just before today P0** | `a0398aa` (255/256、2026-04-29 06:30 UTC) より前 |
| **本日 P0 commit chain (全 fail)** | `7667658` (263-QA) → `7fb23b2` (257-QA) → `672ede6` (266-QA) → `b0f27fc` (260-MKT) → `dc02d61` (267-QA) → `d58941b` (269-QA) → `d7c7b07` (270-271-QA) → `a175f24` (273-QA) |

→ 04-26 から既に赤継続(別 issue)、本日 04-29 P0 fix で **5 件追加 fail**(SyntheticDraftWPClient mock 不在)。

## 8. local pytest との差分

- local pytest は `pytest -x` で先頭 fail 検知時 stop → 「pre-existing fail = 1 件のみ」と判定
- CI は `unittest discover` で全 test 回す → fail 6 件露出
- **local 用 baseline 偽装が起きていた**(本セッションの 04-30 朝の修正中に確認済み、memory `feedback_accept_pytest_baseline_required.md` 参照)
- 全数 baseline には `pytest -x` ではなく `pytest --co + pytest -q tests/` (without -x) を使う必要

## 9. 修正方針

### 修正案 A: test mock 更新(P0 起因 5 件、最優先)

`src/sns_topic_publish_bridge.py:53` の `SyntheticDraftWPClient` に `list_posts` method を追加:
```python
def list_posts(self, *, status=None, per_page=None, source_url=None, **kwargs):
    """既存 self._posts dict から条件 filter で list 返却"""
    rows = []
    for post_id, payload in self._posts.items():
        if status and str(payload.get("status") or "").lower() != str(status).lower():
            continue
        rows.append(dict(payload))
    return rows
```

**src 修正(test mock 拡張)であって `src/guarded_publish_runner.py` の本番 logic は触らない**。

### 修正案 B: fact_conflict_guard ambient 1 件(後回し可)

判定文字列 `pregame_score_fabrication` vs `NO_GAME_BUT_RESULT` のどちらが正かを user/ticket 起源の意図確認。今回の P0 修正と無関係。

### workflow 設定変更は **しない**

- `tests.yml` の構成は妥当
- skip / disable / continue-on-error は **入れない**(ノイズ化を防ぐ user 指示)
- Node.js 20 deprecation 警告あるが annotations のみ、test fail とは無関係(別 ticket 検討)

## 10. デグレ試験 pass/fail

(本 ticket は audit、まだ修正 commit なし。修正 Codex 便 fire 後に確認)

| カテゴリ | 試験 | 期待 |
|---|---|---|
| 公開導線 | publish 0 が継続しない | OK 維持(273-QA で復旧、10:46 で 3 件 publish) |
| メール通知 | publish/review/hold/yellow 全送信 | OK 維持(267-QA path 不変、10:50 sent=2) |
| 安全系 | 死亡/重傷/duplicate 全解除なし | OK 維持(266-QA / 263-QA / 269-QA narrow logic 不変) |
| 禁止事項 | live_update OFF / SEO 不変 | OK 維持(env / Cloud Run 触らない) |
| コスト | Gemini call 増えていない | OK(228-COST/229-COST 並走中、本 ticket は test mock のみ追加) |

→ **修正案 A のみで P0 試験は全 pass 見込み**(本番 src 触らない、test mock 拡張のみ)。

## 11. Codex へ投げる作業範囲(user GO 後)

```
ticket: 275-QA-fix-test-mock-list-posts (修正)
scope (narrow):
  - src/sns_topic_publish_bridge.py:53 の SyntheticDraftWPClient class に list_posts method を追加
  - status / source_url / per_page filter サポート
  - 263-QA 由来 5 件 test pass 確認
fixture:
  - test_sns_topic_publish_bridge.py の既存 5 fixture が pass する
  - list_posts 経由の duplicate guard 動作確認(既存 fixture 活用)
不可触:
  - src/guarded_publish_runner.py (本番 logic)
  - src/wp_client.py (本番)
  - その他 src
  - workflow.yml
  - test skip / continue-on-error
  - Team Shiny From / publish-notice / Cloud Run / Scheduler / env / Secret
  - live_update / SEO / Gemini / X
  - duplicate guard logic (263-QA / 269-QA narrow は維持)
acceptance:
  - 1 commit に src/sns_topic_publish_bridge.py + (必要なら fixture 微調整) のみ stage
  - GitHub Actions Tests workflow が緑になる(残り 1 件 test_fact_conflict_guard は別 ticket)
  - 既存 fixture 0 件 fail
push: Claude
deploy: 不要(test mock のみ、本番 image 影響なし)
```

(別途 fact_conflict_guard 1 件は **276-QA(後回し)** として別 ticket、本 P1 fix とは分離)

## 12. workflow を止めずに直せるか

**直せる**。

- `.github/workflows/tests.yml` 不変
- `unittest discover` 構成不変
- skip / continue-on-error 一切なし
- 本番 src 不変
- test mock の足りない method を 1 つ追加するだけ

CI が緑に戻る = 本番デグレ検知が機能する状態に復活。

## 完了条件(user 受け入れ条件)

| # | 項目 | 修正後の確認方法 |
|---|---|---|
| 1 | GitHub Actions Tests workflow 緑 | `gh run list --workflow=tests.yml --limit=1 --json conclusion` = success |
| 2 | 常時赤ノイズ解消 | 連続 3 commit で緑(deploy なしの test-only 修正なので即効) |
| 3 | 本番デグレ検知として機能 | 故意に src を壊す → CI red になることを別途確認可能 |
| 4 | デグレ試験 pass(§10 5 カテゴリ) | 修正 Codex 便で確認、報告に含める |
| 5 | Cloud Run / Scheduler / env / publish-notice / From 不変 | 本 ticket は doc + test mock のみ、cloud 触らない |

## 不可触(Hard constraints)

- workflow disable
- テスト skip / continue-on-error
- GitHub 通知だけ消して終了
- Cloud Run 変更
- Scheduler 変更
- env / Secret 変更
- publish-notice 変更
- Team Shiny From 変更
- Gmail フィルタ対応(別 ticket 274-OPS で扱い済)
- duplicate guard 全解除
- 本番 src 修正(本 audit 範囲では mock のみ)

## 関連 ticket

- **274-OPS**: Gmail フィルタ(通知ノイズ受信側退避、本 ticket とは独立)
- **263-QA**: `7667658` で `wp_client.list_posts` 追加(P0 起因の test fail trigger)
- **267-QA**: publish-notice 拡張(本 ticket 影響なし)
- **270/271/273-QA**: backlog narrow(本 ticket 影響なし)
- **276-QA(後追い、別 ticket)**: fact_conflict_guard `pregame_score_fabrication` vs `NO_GAME_BUT_RESULT` ambient 1 件

## rollback

修正 commit revert で復旧(test mock の追加なので revert で元の状態に戻る、本番影響ゼロ)。
