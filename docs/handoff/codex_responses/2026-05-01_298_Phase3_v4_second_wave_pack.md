# 298-Phase3 v4 第二波対策 Pack

作成: 2026-05-01 JST  
mode: Lane A round 4 / doc-only / single-file diff  
scope: `docs/handoff/codex_responses/2026-05-01_298_Phase3_v4_second_wave_pack.md` 新規のみ

---

## 0. state lock

- `docs/ops/OPS_BOARD.yaml` の `298-Phase3-deploy` は **`ROLLED_BACK_AFTER_REGRESSION`**。
- live state は `publish-notice:1016670` を維持しつつ、`ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` は **OFF**。
- `2026-05-01 14:15 JST` post-rollback observe は `rolling 1h = 5-6 通`、`errors=0`、`silent skip=0`、`Team Shiny` 維持。
- ただし `2026-05-01 14:20 JST` に **第二波 risk OPEN** が記録済み。現状の静けさは 24h dedup の残り時間に依存しており、根治ではない。

参照正本:

- `docs/ops/OPS_BOARD.yaml`
- `docs/ops/POLICY.md` §18, §19, §22
- `docs/ops/INCIDENT_LIBRARY.md` anchor 1-13
- `docs/handoff/session_logs/2026-05-01_p1_mail_storm_hotfix.md`
- `docs/handoff/codex_responses/2026-05-01_codex_b_storm_permanent_fix.md`

---

## 1. 第二波 cardinality lock

`2026-05-01 14:20 JST` 時点の固定 facts:

- `backlog_only` pool 全体: **103 unique post_id**
- 第二波の再送対象として最も危険な morning storm group: **99 unique post_id** (`63003-63311` group)
- これら 99 件は `2026-05-01 09:00 JST` 帯で既に mail emit 済みだが、current path は `publish_notice_history` の **24h dedup** しか持たない
- よって `2026-05-02 09:00 JST` 前後に dedup が失効すると、**同じ 99 件が再 emit** される想定

運用インパクト:

- 想定 emit 総数: **99 通**
- `max_per_run=10` 前提でも約 **10 trigger / 約 50 分**で消化される
- 時間当たり換算は約 **99/50min ≒ 118.8 通/h** で、`MAIL_BUDGET 30/h` を大幅違反
- 日次は **99/100 通** をこの group だけで使い切るため、通常の `review` / `289` / publish notice が 1 通でも重なると **100/d 違反**

重要:

- `d44594a` 系の permanent dedup は **「一度 ledger に入った post_id の再送を止める」** 実装であり、**既に送ってしまった 99 件を自動で seed する機構はない**
- したがって **現行 v3 のまま再 ON しても first emit 99 通は防げない**

---

## 2. INCIDENT_LIBRARY anchor 適用

今回の v4 判断に直接効く anchor は以下。

| anchor | 今回の使い方 |
|---|---|
| 1 | `scan window` 拡大型 hotfix は採らない。`PUBLISH_NOTICE_REVIEW_WINDOW_HOURS=168` 再投入は永久禁止。 |
| 3 | 「自然終息したから safe」ではなく、`pool size / cap` と 24h dedup expiry で **第二波時刻を明示** する。 |
| 6 | `Expiry` は **`2026-05-02 09:00 JST` recurrent 前** を hard deadline に置く。 |
| 7 | `MAIL_BUDGET 30/h, 100/d` を超える案は default reject。 |
| 9 | `cap=10/run` 単独 safe 扱い禁止。今回も `cap` は維持し、防御は seed/persistent dedup 側で持つ。 |
| 10 | sink-side cutoff は許容。ただし **first emit storm を潰せる形** でなければ再発する。 |
| 11-13 | 実装後の deploy は `target=HEAD` 動的化、`git diff <deploy_target> HEAD -- src/ tests/` empty、clean build 前提。 |

---

## 3. 3 Case 比較

前提:

- 比較対象は **second-wave 99 件を 0 通にできるか**
- `real review` / `289 post_gen_validate` / `Team Shiny From` / `Gemini call delta` / `cap=10` / `24h dedup window` は不変を最優先
- Case 名は `2026-05-01 14:20 JST` session log 記法に合わせる

| case | touched_files | env_knobs | impl_complexity | test_surface | blast_radius | rollback_method | 効果 | 副作用 |
|---|---|---|---|---|---|---|---|---|
| **Case A: ledger seed mode** | `src/publish_notice_scanner.py`<br>`src/cloud_run_persistence.py`<br>`tests/test_publish_notice_scanner.py`<br>`tests/test_cloud_run_persistence.py`<br>`tests/test_post_gen_validate_notification.py`<br>`tests/test_publish_notice_email_sender.py` | 既存: `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1`<br>新規案: `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_SEED=1` | **medium (4/10)**<br>既存 ledger を再利用し、`__seed_complete_at` などの bootstrap metadata を同一 object に持つ narrow 追加で済む | **7 cases**<br>scanner 4 / persistence 1 / integration 2 | **low**<br>`hold_reason=backlog_only` かつ current wave seed に限定。`real review` / `cleanup_required` / `289` は既存 path 維持 | まず env remove で即停止<br>完全 rollback は `env remove + image revert + ledger archive restore` | **99 → 0 想定**。既知 99 件を first emit 前に permanent ledger へ bootstrap seed し、その後は「新規 backlog_only は 1 回だけ emit」の既存 once-only 契約へ戻れる | seed 対象 99 件は再送 mail が来なくなる。ledger archive/restore discipline が必要 |
| **Case D: backlog_only mute mode** | `src/publish_notice_scanner.py`<br>`tests/test_publish_notice_scanner.py`<br>`tests/test_post_gen_validate_notification.py`<br>`tests/test_publish_notice_email_sender.py` | 新規案: `ENABLE_PUBLISH_NOTICE_BACKLOG_ONLY_MUTE=1` | **low (2/10)**<br>scanner で `hold_reason=backlog_only` を全 skip | **4-5 cases**<br>scanner regressions 中心 | **medium**<br>`backlog_only` path 全体を mute するので user-visible semantics が変わる | env remove + image revert | **99 → 0 は確実** | future の新規 `backlog_only` まで全部 0 通になる。`old candidate once` の「最初の 1 回は見せる」契約を壊す |
| **Case F: GCS pre-seed** | repo code **0**<br>live object only: `gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json`<br>必要なら runbook doc のみ | 既存: `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1` のみ | **repo 1/10 / ops 6/10**<br>コード変更不要だが live state surgery | **manual verify only**<br>CI で守れない | **medium**<br>runtime code は既存のままでも、state object 破損/seed 漏れが即 live 影響になる | archived object を restore、必要なら env remove + image revert | **99 → 0 は可能**。既存 99 件だけを ledger へ直接書き込めば future 新規 ID は once-only のまま | reproducibility が弱い。CI 不在。seed 対象の取り違え、archive 漏れ、object 破損時の切り戻しが一段重い |

補足:

- Case A は **現在の `d44594a` permanent dedup を活かす narrow extension**
- Case D は **mail storm 停止だけなら一番速い**が、`backlog_only` の visibility contract を切る
- Case F は **repo diff 最小**だが、`POLICY §18` 的には evidence が live object 操作へ偏り、再実行可能性が低い

---

## 4. 推奨 Case

### 推奨: **Case A (ledger seed mode)**

推奨理由:

1. **blast radius 最小**  
   既存 `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` の ledger contract をそのまま使い、差分を `backlog_only` seed bootstrap に限定できる。`real review` / `289` / `Team Shiny` / `Gemini` / `cap=10` / `24h dedup` を触らない。

2. **user 体感影響が最小**  
   Case D と違い、future の新規 `backlog_only` まで mute しない。今回の 99 件だけを「既に 2026-05-01 に一度 user に届いた candidate」とみなして permanent ledger に carry できる。

3. **rollback が明快**  
   即時停止は env remove、完全復元は `image revert + ledger archive restore` で足りる。Case F のような ad-hoc な live object 手作業を標準運用にしなくてよい。

4. **impl 効率がよい**  
   `d44594a` の old-candidate once 実装と既存テスト群を流用できる。ゼロから新 path を作るより narrow。

### Case A の具体イメージ

- 既存 ledger: `publish_notice_old_candidate_once.json`
- 新規 seed flag: `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_LEDGER_SEED=1`
- first bootstrap 時だけ:
  - `hold_reason=backlog_only`
  - `min_age_days >= 3`
  - current second-wave pool に該当
  - かつ ledger 未登録
  - の post_id を **emit せず ledger へ書く**
- bootstrap 完了後は ledger metadata `__seed_complete_at` を残し、以後は **既存 v3 と同じ once-only** に戻す

これにより:

- **既知の 99 件**: `99 → 0`
- **future の新規 backlog_only**: first emit `1` 回のみ、その後 permanent dedup
- **real review / 289**: unchanged

---

## 5. impl 順序(commit 分割案)

### commit 1: Case A scaffold

- `Case A` を正式選択
- `publish_notice_scanner` に seed mode 定数/metadata key を追加
- flag OFF(default) では **100% no-op** を固定
- `cloud_run_persistence` 側は既存 ledger object をそのまま restore/upload する contract を明文化

### commit 2: scanner / persistence 実装

- scanner:
  - bootstrap seed branch を追加
  - `__seed_complete_at` を見て one-shot seed 完了を判定
  - seeded post_id は `emit 0` で ledger 登録
  - seed 完了後は current v3 once-only path に戻す
- persistence:
  - same ledger object の download/upload を seed metadata 含めて維持
  - archive/restore を想定した ledger shape を壊さない

### commit 3: tests 5-7 cases

- 下記 test plan 7 cases を追加/更新
- targeted green:
  - `tests/test_publish_notice_scanner.py`
  - `tests/test_cloud_run_persistence.py`
  - `tests/test_post_gen_validate_notification.py`
  - `tests/test_publish_notice_email_sender.py`

### commit 4: deploy 前 pytest baseline + clean build

- `pytest -q` baseline を取り、new failures `0` を記録
- clean export で deploy payload を固定
- `git diff <deploy_target> HEAD -- src/ tests/` empty を確認
- hold carry 混入なし確認
- build/redeploy はこの commit 後の Claude push / authenticated executor lane

注記:

- commit 4 は repo diff `0` でもよい。証跡を repo に残す必要がある場合のみ doc-only follow-up を許容

---

## 6. test plan (7 cases)

1. **既存 backlog_only entries が 24h dedup expire しても再 emit 0**  
   - seed 済み 99 件を再度 scanner に流しても `OLD_CANDIDATE_PERMANENT_DEDUP` で止まること

2. **新規 backlog_only entries の first emit 1 度のみ(永続 dedup)**  
   - seed 完了後に初めて出た over-threshold backlog_only は 1 回だけ queue され、2 回目以降は permanent dedup に落ちること

3. **real review / 289 / errors / yellow / Team Shiny path 不変**  
   - `cleanup_required` / real `review` / `post_gen_validate` / sender / error path の subject, cap carryover, From が不変
   - ここでの `yellow` は `backlog_only` mute ではない既存 review path を指す

4. **cap=10 / 24h dedup window 不変**  
   - `review_max_per_run=10` と 24h recent dedup の baseline contract が壊れていないこと

5. **flag OFF (default) で挙動 100% 不変**  
   - new env 未設定時に current v3 scanner 結果と差分 0

6. **rollback で挙動 100% 戻る**  
   - `env remove + image revert + ledger archive restore` 後、seed なし baseline と同じ scanner 結果に戻ること

7. **storm 再現 fixture で 99 件 first emit 抑制 verify**  
   - `63003-63311` group 相当の 99 post_id fixture を流し、seed mode で queued mails `0` を検証

想定追加/更新 test 名:

- `tests/test_publish_notice_scanner.py::test_seeded_backlog_only_entries_do_not_re_emit_after_24h_expiry`
- `tests/test_publish_notice_scanner.py::test_new_backlog_only_entry_after_seed_completes_emits_once_then_dedups`
- `tests/test_publish_notice_scanner.py::test_seed_mode_flag_off_keeps_baseline_behavior`
- `tests/test_cloud_run_persistence.py::test_entrypoint_preserves_seed_metadata_in_old_candidate_ledger`
- `tests/test_post_gen_validate_notification.py::test_seed_mode_does_not_reduce_post_gen_validate_capacity`
- `tests/test_publish_notice_email_sender.py::test_seed_mode_keeps_team_shiny_from_and_subject_contract`
- `tests/test_publish_notice_scanner.py::test_seed_mode_suppresses_ninety_nine_second_wave_fixture`

---

## 7. Acceptance Pack 18 項目 final draft

```markdown
## Acceptance Pack: 298-Phase3-v4-second-wave-case-A

- **Decision**: HOLD(現時点は doc-only。Case A 採用までは確定、impl/test/deploy evidence 待ち)
- **Requested user decision**: Case A(ledger seed mode) を 298-Phase3 の第二波対策として実装・test・deploy 準備まで進めることを承認するか
- **Scope**: `publish_notice` の old-candidate once path に bootstrap seed を追加し、既知 99 件(`63003-63311` group)を permanent ledger へ carry した上で second wave を 0 通化する
- **Not in scope**: `guarded_publish_runner` source semantics 変更、`PUBLISH_NOTICE_REVIEW_WINDOW_HOURS` 再投入、Scheduler 頻度変更、Team Shiny From 変更、289 path 変更、Gemini call 増加、WP mutation、SEO、X、自動 source 追加
- **Why now**: `2026-05-02 09:00 JST` 前後に 24h dedup が失効すると、既知 99 件が再 emit され `MAIL_BUDGET 30/h` と `100/d` を同時に壊す見込み。current v3 のままでは first emit 99 件を防げない
- **Preconditions**:
  - `298-Phase3` は `ROLLED_BACK_AFTER_REGRESSION` のまま維持
  - Case A 実装 commit 1-3 完了
  - `pytest -q` baseline new failures = 0
  - clean build export 完了
  - 17:00 JST production health で `errors=0`, `silent skip=0`, `Team Shiny` 維持
- **Cost impact**: Cloud Build 1 回、GCS state file は既存 `publish_notice_old_candidate_once.json` の metadata/entries 微増のみ、Gemini call 追加 0
- **User-visible impact**: `2026-05-02 09:00 JST` second wave の `【要確認(古い候補)】` 99 通は 0 通想定。future の新規 backlog_only は 1 回だけ見える。`real review` / `289` / 通常 publish notice は維持
- **Rollback**: 即時停止は env remove。完全 rollback は `env 1 コマンド + image revert + ledger archive restore`
- **Evidence**:
  - impl commits(1-3)
  - `pytest -q` green
  - scanner/persistence targeted tests green
  - 99 fixture suppress = 0
  - deploy 前 clean export
  - deploy 後 observe で `real review` 減少 0 / `289` 減少 0 / errors 0
- **Stop condition**: `real review` emit 減、`289` emit 減、`Team Shiny From` 変化、`errors > 0`、`silent skip` 増、`MAIL_BUDGET 30/h or 100/d` 違反
- **Expiry**: `2026-05-02 06:00 JST` user 提示 cutoff / hard deadline `2026-05-02 09:00 JST`
- **Recommended decision**: GO(条件付き。commit 1-4 完了 + evidence 揃い次第)
- **Recommended reason**: blast radius 最小、user 体感影響最小、rollback 容易、既存 v3 permanent ledger を再利用できるため impl 効率も最良
- **Gemini call increase**: NO
- **Token increase**: NO
- **Candidate disappearance risk**: NO(既に `2026-05-01` に通知済みの 99 件を carry するだけで、future の新規 backlog_only / real review path は消えない)
- **Cache impact**: NO
- **Mail volume impact**: YES(reduction、定量は second wave `99 → 0` 想定)

User reply format: 「GO」/「HOLD」/「REJECT」のみ
```

判定メモ:

- `POLICY §18` の厳密運用では 14-18 の UNKNOWN が 1 つでもあれば HOLD
- Case A は `Mail volume impact=YES` が intentional reduction であり、これは reject 要因ではない
- よって最終 user 提示前の残 task は **UNKNOWN を 0 にすること** と **99 fixture suppress evidence** の取得

---

## 8. lane handoff

- Claude:
  - `298-Phase3 ROLLED_BACK_AFTER_REGRESSION` entry に本 v4 doc を reference 追加
  - `2026-05-02 06:00 JST` user 提示用に 1 行要約へ圧縮
- Codex(次便):
  - Case A で narrow 実装
  - single-scope で `scanner + persistence + tests`
  - `git add -A` 禁止、single ticket、single purpose

結論:

- **推奨 Case は A**
- **D は速いが mute が広すぎる**
- **F は code diff 0 の代わりに live state surgery が重い**
- 第二波 99 件を確実に潰しつつ future `backlog_only` の first visibility を残す案としては **A が最も整合的**
