# 298-Phase3 v4 本番反映 regression 試験計画(production deploy 後)

**作成**: 2026-05-01 17:30 JST(Lane B round 15 deploy 進行中)
**owner**: Claude(read-only verify、scope 内 EVIDENCE_ONLY)
**前提**: Lane B round 15(`bbnqyhph3`)= GCS pre-seed 104 post_id + `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1` env apply、本日 user GO「ならやる」受領済

---

## Phase 1: deploy 直後 verify(Codex 一次受け範疇、Lane B round 15 内)

| # | 試験 | 期待値 | 異常判定 |
|---|---|---|---|
| A1 | env apply 確認(`gcloud run jobs describe publish-notice`)| `ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE=1` 検出 | 不在なら fail、即報告 |
| A2 | 1 回目 trigger sent | sent=0(GCS pre-seed 104 post_id permanent_dedup skip)| sent>0 = first emit storm risk、§14 自律 rollback |
| A3 | errors | 0 全 trigger | errors>0 = stop |
| A4 | `OLD_CANDIDATE_PERMANENT_DEDUP` skip log | 104 件出現(scan 範囲内)| 0 件 = ledger 機能不全 |

## Phase 2: 不変方針 verify(同時並行、~10 min)

| # | 試験 | 期待値 |
|---|---|---|
| B1 | `MAIL_BRIDGE_FROM` | `y.sebata@shiny-lab.org` 維持 |
| B2 | `ENABLE_POST_GEN_VALIDATE_NOTIFICATION` | `1` 維持 |
| B3 | `PUBLISH_NOTICE_REVIEW_WINDOW_HOURS` | 不在維持 |
| B4 | fetcher image | `yoshilover-fetcher:4be818d` 不変 |
| B5 | publish-notice image | `publish-notice:1016670` 不変(env だけ apply)|

## Phase 3: regression 試験(observe 2-3 trigger、~15 min)

| # | 試験 | 期待値 | 異常判定 |
|---|---|---|---|
| C1 | 通常 review path 維持 | `【要確認】` yellow / `【要review｜post_gen_validate】` / `【要確認・X見送り】` 全 path 観測 | path 消失 = stop |
| C2 | silent skip | 0(POLICY §8)| > 0 = §14 自律 rollback |
| C3 | real review(cleanup_required / hard_stop) emit | 維持 | 減少 = stop |
| C4 | errors | 0 全 trigger | > 0 = stop |
| C5 | MAIL_BUDGET | 30/h・100/d 内 | violation = §14 自律 rollback |
| C6 | 17:01-17:10 mini-burst の post_id(104 pool 内) | sent=0(permanent_dedup skip)| sent>0 = ledger 機能不全 |

## Phase 4: 新規 backlog 入力 verify(deploy 後 1h、~19:30 JST)

| # | 試験 | 期待値 |
|---|---|---|
| D1 | new post(ledger 未登録) | first emit 1 度のみ + ledger 登録 |
| D2 | 既登録 post | permanent_dedup skip |
| D3 | cap=10 / 24h dedup | 維持 |

## Phase 5: cost / cache 不変(deploy 後 1h、~19:30 JST)

| # | 試験 | 期待値 | 異常判定 |
|---|---|---|---|
| E1 | Gemini call rate(env apply 前 vs 後 1h)| delta < ±5% | > +5% = stop |
| F1 | cache_hit ratio(直近 6h vs 後 6h)| ±5% 以内 | > ±15%pt = audit |

## Phase 6: 24h 安定確認(明日 5/2 朝 09:00 JST 周辺、第二波想定)

| # | 試験 | 期待値 | 異常判定 |
|---|---|---|---|
| G1 | rolling 1h sent | MAIL_BUDGET 30/h 内 | violation = §14 自律 rollback |
| G2 | cumulative since 09:00 JST(5/1)| MAIL_BUDGET 100/d 内 | violation = §14 |
| G3 | silent skip | 0 継続 | > 0 = stop |
| G4 | permanent_dedup skip count | 104+ 安定(新規追加で +N)| 0 = 機能不全 |
| G5 | real review / 289 / errors emit | 維持 | 減少 = stop |
| H1 | 5/1 朝 storm 99 post_id (63003-63311) sent | **0**(第二波防止)| > 0 = storm 再発、§14 自律 rollback |
| H2 | 13:35 storm 50 post_id (61938-62940) sent | **0** | > 0 = §14 |
| H3 | 直近 6h 追加 post (if any) | ledger 登録済 → sent=0 | sent=N(first emit 後 dedup)|

## Phase 7: rollback gate 確認(emergency 想定、計画のみ、実行は storm 再発検出時)

| # | 計画 | 実行条件 |
|---|---|---|
| I1 | env rollback command ready: `gcloud run jobs update publish-notice --region=asia-northeast1 --project=baseballsite --remove-env-vars=ENABLE_PUBLISH_NOTICE_OLD_CANDIDATE_ONCE` | 30 sec 内に rollback 可能 |
| I2 | image rollback: `:4be818d` 旧(必要時) | 2-3 min |
| I3 | ledger archive: `gsutil mv gs://baseballsite-yoshilover-state/publish_notice/publish_notice_old_candidate_once.json gs://...archive/<timestamp>.json` | 必要時のみ |
| I4 | §14 P0/P1 自律 rollback trigger | rolling 1h sent > 30 / silent skip > 0 / errors > 0 / 289 減 / Team Shiny 変 / publish-notice halt |

---

## 実行順序 + 実行者

1. **Phase 1-3**(Codex Lane B round 15 内、deploy 便完結内):自動、~20-30 min 内
2. **Phase 4-5**(Claude 単独 read-only、deploy 完了後 1h):~19:30 JST 頃
3. **Phase 6**(明日朝 09:00 JST 周辺、Claude session 再開時):~5/2 09:30 JST
4. **Phase 7**(emergency only、storm 再発検出時):§14 自律 rollback、Claude 即実行

---

## 関連 doc

- POLICY §3(Production Change 3 分類、298-v4 deploy = USER_DECISION_REQUIRED + user GO 受領済)
- POLICY §7(mail storm rules、第二波防止 + cardinality + max mails/h・d + stop condition + rollback)
- POLICY §8(silent skip policy、existing publish/review/hold mail 維持)
- POLICY §14(P0/P1 自律 hotfix 8 条件、本日 13:55 実績整合)
- INCIDENT_LIBRARY(2026-05-01 P1 mail storm 経緯)
- 298-v4 final READY pack(`fac5517`)
- 298-v4 robustness supplement(`dab9b8e`、cardinality 99/20/50/104/1)

## stop condition summary

| 検出 | 対応 |
|---|---|
| storm 再発(rolling 1h sent > 30) | §14 自律 rollback(env remove、30 sec)|
| silent skip 増加 | stop + 即報告(P0)|
| errors > 0 | stop + 即報告 |
| 289 / Team Shiny / 通常 review path 影響 | stop + 即報告(P1)|
| Gemini call > +5% | stop + 即報告(scope 外影響)|
| cache_hit ratio > ±15%pt | audit + 報告 |
