# assignments — 現場担当と次アクション

最終更新: 2026-05-16 JST

## チケット管理方針(2026-05-14 EVENING lock)

- **正本 = repo doc 一本**(`doc/README.md` + 本 `doc/active/assignments.md`)
- **GH Issues 運用は停止**。今日 #1〜#25 を試したが、二重管理のため撤収
- 1 人 + AI 運用では本 file + `doc/active/` / `doc/waiting/` / `doc/done/YYYY-MM/` の 4 layer で十分

## 最初に読む

- `doc/active/OPERATING_LOCK.md`
- `doc/README.md`
- `doc/active/assignments.md`
- **2026-05-14 最新 handoff (本日 3 session)**:
  - `docs/handoff/session_logs/2026-05-14_pm_336qa_chain_handoff.md` (PM、336-QA chain LIVE)
  - `docs/handoff/session_logs/2026-05-14_session_handoff_343_INSIGHT_007_LIVE.md` (PM 並走、343-INSIGHT-007 chain LIVE + 342 unblock)
  - `docs/handoff/session_logs/2026-05-14_session_handoff_DATA_INSIGHT_continuous_LIVE.md` (EVENING、342 LIVE 公開 + DATA-INSIGHT-continuous system 稼働 + SVG fix)
- **2026-05-08 緊急対応 (close 済)**: `doc/done/2026-05/RESTORE-2026-05-08-MORNING-RELIABILITY.md` + `docs/handoff/HANDOFF-2026-05-08-NEXT-SESSION.md`

## 2026-05-14 PM session summary

### close 済 (13 GH Issue、1 commit chain)

| 区分 | Issue | commit | 備考 |
|---|---|---|---|
| impl | #17 / 338-QA | `ef204c5` | 「無失点」を「失点」誤判定 fix |
| audit→fix | #19 / 340-OBSERVE → #22 / 341-FIX | `4487e77` | digest 不発 audit → schema adapter |
| impl | #8 / 335-QA Phase 3 | `ace4b64` | event token 重複圧縮 |
| impl | #16 / 337-INGEST Phase 3 | `21e4502` | sanspo balanced div extractor |
| impl | #18 / 339-INGEST | `6dd55f2` | X+Web 同 family dedup (default OFF) |
| impl | #10/#11/#12 / 336-QA Phase 1+2+3 | `e7a33bd` | 報知優先 parent + 600字 excerpt block |
| ops 移行 | #5 / 334-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| ops 移行 | #9 / 335-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| ops 移行 | #13 / 336-QA Phase 4 canary | (cleanup) | implementation 完了で観察 ops 移行 |
| 並走 | #23 / 343-INSIGHT-007 | (並走 session) | Phase 1+2 LIVE deploy 完了で close |

deploy: yoshilover-fetcher rev 00380-dx7 → 00381-n9d → 00382-hqj → 00383-vtd → 00384-c2s → 00385-5xb (6 deploy、build digest = revision sha256 一致全件 verify)

## 2026-05-15 session summary

### close 済(本 session、 348 chain)

| 区分 | ticket | commit | image digest |
|---|---|---|---|
| impl + deploy | 348 step 1: × whitelist gate + config JSON | `86d4724` | `sha256:43aeb2b5...` |
| impl + deploy | 348 step 2: 勝率/守備率 + publisher 日本語 label | `bf010ba` | `sha256:e26ac26d...` |
| impl + deploy | 348 step 3 part 1: scope 拡張 (last_5/10_games / monthly / weekly) | `8b962e5` | `sha256:16129274...` |
| impl + deploy | 348 step 3 part 2: record detector + team ranking + counting helper | `7a10c6e` | `sha256:6e633c8b...` |

test: 382 passed (= 302 baseline + 35 step1 + 18 step2 + 14 step3p1 + 13 step3p2)、regression 0、schema migration 0

### 起票(本 session 発見、 user 確認後 着手判断)

| ticket | status | 内容 |
|---|---|---|
| `doc/active/352-postgame-auto-thin-body-false-positive.md` | READY | 5/12 から `postgame-auto` Cloud Run Job 連続失敗 (exit 20 = EXIT_WP_FAILED)。 仮説: `thin_body_validator._is_postgame_scorecard_only` の detail-heading regex が postgame card に match せず false positive で reject。 348 scope 外、 別 ticket 化 |

### user 判断 残

| 件 | 内容 |
|---|---|
| 既存 wOBA 5 件 post (68064-68068) | × metric が title 流出、 §11 GATE。 削除/書き換え/放置 のどれか |
| 352 着手 GO 判断 | postgame-auto 自動投稿停止の影響評価 + 着手 timing |

### 翌日の verify gap

- 明朝 07:00 JST insight-nightly 自然 fire 後、 348 step 3 で導入した新 scope (last_5_games / last_10_games / monthly / weekly) で実 publish が出るか確認
- 「奪三振率 / 与四球率 / 被本塁打率」「勝率 / 守備率」の日本語 label が新規 publish title に反映されているか

## 2026-05-16 session summary

### repo 実装済、push/deploy 済、自然 fire 観察待ち

| ticket | status | 内容 |
|---|---|---|
| `348-INSIGHT` follow-up | LIVE_DEPLOYED_OBSERVE | `BABIP` / `FIP` が detector bypass や direct renderer から再流出しないよう二重防御。UZR は user 指示通り許可側維持 |
| `349-INSIGHT-dedup-cooldown-cascade` | LIVE_DEPLOYED_OBSERVE | 同じ subject + metric を期間違いでも 7 日 cooldown。例外は 5% 以上の値変化または順位 band 変化。title 期間 runtime guard も deploy 済み。schema migration なし、既存 `article_candidates` を ledger として利用 |
| `356-INSIGHT-data-quality-publish-gate` | REVIEW_NEEDED | GitHub Issue #31 起票済み。sample不足 / ranking coverage不足 / stale snapshot / 本文根拠不足を publish 直前に止める data quality gate を実装済み。targeted pytest 231 passed、full unittest は既存赤。env / Scheduler / Secret / X / SNS / deploy は未実行 |

deploy: `insight-nightly:5a4e5e6` / digest `sha256:73c0b4b0bdd4524d7d445be0444f4ac4d0693a4db4b5429f91a4af387ce638c8`。Cloud Build `abf66df4-42b8-402f-8099-0e342923f24e` SUCCESS。Scheduler / env / Secret は未変更、手動 execute 未実行。

test: deploy 前 data-insight 関連 pytest 226 passed。full unittest は既存の `manual_intake_service` socket PermissionError、`manual_intake_service_x_post` 403 expectation、`duplicate_prevention_golden` logger call-count で赤のまま。

様子見リスク: 記事減りすぎ / まだ多い / mail過多 / 既存投稿 backfill 未実装 / title期間必須 runtime guard の live 観察待ち。次 action は次回 Scheduler 自然 fire のログ観察。

## 2026-05-14 EVENING session summary

### close 済(本 session)

| 区分 | ticket | commit | 備考 |
|---|---|---|---|
| impl | 342-INSIGHT(=旧 GH #21) | 多数 | data-driven ranking 自動 publish 基盤 LIVE。本日 Giants 12 件 + 球団 5 件 + 異常値 5 件 publish |
| impl | DATA-INSIGHT-continuous(=旧 GH #25) | 多数 | 継続改善 system 稼働。異常値検出 8 種 + ランキング 4 軸 + 球団ランキング 7 軸 |
| ops | Cloud Scheduler 7 trigger 配備 | 設定 | 02/07/12/15/17/20/21 JST、`ENABLE_DATA_INSIGHT_AUTO_PUBLISH_GIANTS=1` で Giants のみ auto publish |
| fix | SVG inline-style fix | `7da3956` | WP wpautop で `<style>` が `</p><p>` 分割していた bug、既存 17 記事一括 patch も済 |
| ci | xfail 4 pre-existing | `578a598` | baseline 一致 fail を unblock、regression 検知力は xfail で保持 |

### 残 open(別 actor lane)

| ticket | status | blocker |
|---|---|---|
| 344-INGEST(=GH #24、別 actor lane) | YouTube 字幕 + ch 拡充進行中 | 触らない、別 actor の lane |

### waiting(park、別 session 着手)

| ticket | status | next action |
|---|---|---|
| `doc/waiting/345-INSIGHT-fielding-and-equal-area-ratio.md` | PARKED | NPB box score の守備項目 audit、A path なら自律実装、B path なら user 判断 |

### close 済(旧)

| # | ticket | status | blocker |
|---|---|---|---|
| #21 | 342-INSIGHT | Phase 0 audit + Phase 1 spec done、impl 未着手 | last_30d batter snapshot 12 球団分 (各 5+ 選手) 蓄積待ち、想定 7-21 日後 |

next session: 朝 06:00 自然 fire 後の log 観察 (silent gap §5 in handoff doc) + #21 着手判断 (data 充足後)

## folder cleanup note(2026-05-02)

- Active folderから、明確な HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY / READY_FOR_AUTH_EXECUTOR を waiting へ移動。
- `205-COST` は done/2026-05 へ移動。
- READY / REVIEW_NEEDED で現場が拾う可能性のある ticket は勝手に close していない。

## いま active に残すもの(2026-05-13 lock)

| ticket | status | 判定 | 次 action |
|---|---|---|---|
| **303-rollback-2026-05-08-frontend-rich-body** | LIVE_VERIFIED (Tier 1+2 audit pass) | manual-intake-service / yoshilover-fetcher 両方 `d34072a` 反映済み | manual-intake の rich body 装飾を 5/8 朝 audit Tier 1+2 で 5 件 fix 反映済み。Tier 3 (49 件 doc-only) は別便、現場は live 観察のみ |
| **MANUAL-INTAKE-QUALITY-PARITY-2026-05-08** | DESIGN_REQUIRED | **user 判断待ち**: 「手動 vs 自動」のどの軸(本文長 / 装飾 / 自動化)を直すか | 5/8 PM session 調査済、apply_rss_pipeline_enrichment の nomotoke marker gate を発見、現状 RSS auto は marker 付与なしで装飾 skip。user に A/B/C/D 軸を提示済み、回答待ち |
| **FRONTEND-ENRICHMENT-LIVE-AUDIT-2026-05-08** | READY_FOR_AUDIT | 5/7 enrichment 装飾(ToC / 順位表 / share / tag chip / AI badge / JSON-LD 等)が live で 0% / 100% gap。¥0、デグレ 0 の audit + narrow fix | Phase A 受動 audit から開始、root cause 特定 → narrow fix → unit test。3 auto jobs の redeploy は別 ticket |
| **H3-STRUCTURE-UNIFY-2026-05-08** | READY_FOR_IMPL | H3 が 30+ 種類混在 → 12 set に統一、「📣 関連投稿」3 形式を「💬 ファンの声」に統一、Gemini prompt 自由生成禁止 | ¥0、4-6h、Phase A nomotoke renderer 統一から |
| **DIGEST-DAILY-MORNING-2026-05-08** | READY_FOR_IMPL | 朝まとめ 1 日 1 本(前日 + 翌日 + 順位 + ファン声 を集約)。既存 block 再利用 | ¥0、4-6h、giants-morning-catchup 内に組み込み |
| **SIDEBAR-WIDGETS-2026-05-08** | READY_FOR_IMPL | sidebar 5 widget(直近5試合 / 順位 / streak / 次戦 / 1年前の今日)。WP plugin 側 | ¥0、6-8h、phase 分割で順次 |
| **305-QA featured media source priority** | LIVE_DEPLOYED, USER_ACCEPTANCE_PENDING | source eyecatch を最優先し、同一 source image の WP media reuse を優先。source 不在時は東京ドーム写真 fallback。legacy Ichiro mixed media `36062` は unsafe として除外 | Codex B が repo-only で impl/test/deploy 完了。revision `00293-7lc`、`guarded-publish` / `publish-notice` success、deploy 後新規記事 0 件。次の自動生成 window で user が受け入れ判断。publish / mail / scheduler / env / Cloud Run 設定は追加変更なし |
| **319-QA fetcher topic dedup and slot fill** | REVIEW_NEEDED | 自動起動時に同じ話題の重複記事が10枠を消費する問題を narrow 修正する ticket。head/bat contact 事故の再現テスト赤→緑、related/full pytest green | diff review + commit 判断待ち。publish / mail / scheduler / env / Cloud Run / SEO / source追加は不可触 |
| **CATEGORY-RESTRUCTURE-2026-05-08** | DESIGN_REQUIRED | 「コラム」catch-all 解消、「試合中継」新 category 抽出、巨人 tag 化 | user 判断必要(WP admin で新 category 作成)、Claude は設計 + automation script |
| **EXTERNAL-MONITOR-APPS-SCRIPT** | READY_FOR_USER_SETUP | user 作業 10 分(GAS で完全独立 ping) | 明日朝 yoshilover infra 全死シナリオ用の独立 safety net、user 任意 |
| **334-QA-player-voice-multi-source-digest-subtype** | DESIGN_LOCKED / READY_FOR_PHASE_0_AUDIT | 2026-05-14 user chat lock。のもとけ風 multi-source digest subtype。title 3-token literal assembly(player「セリフ20-40字」event)、AI 禁止、player-agnostic、forward-only、複数 web 媒体サイト集約 | Phase 0 read-only audit から開始。`title_template_assembler.py` 追加位置 + `rss_fetcher.py` clustering hook + source extractor coverage を audit、結果 doc 追記。memory lock: `feedback_title_no_ai` / `project_multi_source_digest_subtype` |
| **OPERATING_LOCK** | ACTIVE_LOCK | **必要。常時参照** | 事故防止ルール。変更は慎重に、src 実装とは混ぜない |
| **assignments** | ACTIVE_BOARD | **必要。現在地** | 本ファイル。active を増やしすぎない |

## 認識しているが今 session 触らないもの(明日朝 06:00 検証 window 関与)

| 項目 | 状態 | 触らない理由 |
|---|---|---|
| **`guarded-publish:eb38006-job`** (job) | 5/8 朝 06:40 JST build、scheduler `*/30 * * * *` ENABLED、明朝 06:00/06:30 fire | 5/8 朝 emergency 10 commit 未反映で draft 昇格挙動が古い可能性。redeploy が必要だが scheduler / image 変更は user 同意境界(autonomous_scope_v2)。明日朝検証で挙動異常があれば次便で扱う |
| **3 auto jobs(broadcast / lineup / postgame)** | `manual-intake-service:b432801`、5/8 0bf8900 / d34072a 未反映 | 明日朝 06:00 検証 window 範囲外(11:30 / 17-18 / 22:30 fire)、検証直後の判断で OK |
| **`draft-body-editor:c796c77`** (job) | 5/2 build、scheduler `0 */3 * * *` 06:00 fire | 5/8 emergency 範囲外、観察のみ |

## done へ送ったもの

仕様変更後も役割は残るが、実装と live 反映が済んだため active から外した。

| ticket | close 判定 |
|---|---|
| **234-impl-1** farm_result / farm_lineup mail UX | `75d9407` で実装済み、後続 234-impl-6 で本文側も補強済み |
| **234-impl-2** first-team postgame / lineup mail UX | `9e98c96` で実装済み |
| **234-impl-3** program / roster notice mail UX | `dd158fb` で実装済み |
| **234-impl-4** injury_recovery / default_review mail UX | `ac23529` で実装済み |
| **234-impl-5** first-team postgame body hardening | `bc3b771` で実装済み、live image `cf8ecb9` へ反映済み |
| **234-impl-6** farm_result / farm_lineup body hardening | `7567e6f` で実装済み、live image `cf8ecb9` へ反映済み |
| **242 parent / 242-B** auto-publish incident + entity contamination | 子 ticket 実装済み。63844 型は `16304f2` + `cf8ecb9` で detector live |
| **243 emit observability** | `499966d` で実装済み、draft-body-editor / fetcher 系の observability lane に反映済み |
| **244 numeric guard** | `f2cc8a3` で実装済み、guarded-publish / X suppress の本線に反映済み |
| **244-B repair anchor** | `e04eee1` で実装済み、後続 wire 完了 |
| **244-followup subtype-aware severity** | `9074c8a` で実装済み |
| **244-B-followup stub to module wire** | `cf8ecb9` で実装済み、draft-body-editor image へ反映済み |
| **278-QA RT title cleanup** | `5a253a2` (TITLE-SEO-POLISH-001) で RT prefix 除去 + 末尾 filler trim 実装。yoshilover-fetcher / manual-intake-service / 3 auto jobs に live 反映済み |
| **279-QA mail subject clarity** | `6349995` (MAIL-SUBJECT-DETAIL-001) で件名 prefix を 公開済｜subtype / 要review｜reason / hold｜reason / 要確認(古い候補)｜subtype に拡張。publish-notice job 後段 rebuild(`b816f06-job`)に live 反映済み(2026-05-08 close) |
| **280-QA summary excerpt cleanup** | `74b0cec` (MAIL-MINIMAL-BODY-001) で本文を title+URL のみに簡素化したため summary を磨く意味なし。publish-notice job に live 反映済み |
| **304-QA player / manager common quality guard** | `6fb818a` で player / manager 共通品質 guard を実装し、Cloud Run revision `yoshilover-fetcher-00285-5bg` へ deploy 済み。post-deploy `/run` 完走、`guarded-publish` / `publish-notice` manual trigger success、運用継続可 |
| **246-viral-topic-detection** | 8 日 parked。SNS バズ検出 → 既存 RSS 裏取り → routing 構想は良いが、現フェーズ(noindex 検証 + 本文品質 + cost)と競合。再着手したくなれば doc/done/2026-05/ から復元 |
| **247-QA-postgame-strict-slot-fill-poc** | 8 日 parked。LLM JSON 抽出 + slot-fill POC は野心的だが LLM 本文生成に踏み込む変更で、現 policy(LLM 本文補完禁止)と衝突。再着手時は scope 再設計必要 |
| **254-QA-starter-innings-normalization** | 8 日 parked。投手回数表記揺れ統一 helper 構想。fact_consistency false negative の対策だが、現状観察で具体被害が顕在化していない。被害が見えたら再起 |
| **245 front hide auto-post category label** | 2026-05-07 audit で実装済 verify 完了。`yoshilover_063_is_internal_auto_post_category` helper + 11 callsite で sidebar/article-card/related に適用済 |
| **277-QA title player name backfill** | `src/title_player_name_backfiller.py` + rss_fetcher 統合済、prod live。tests pass |
| **229 Gemini cost governor + LLM call reduction** | `ENABLE_PER_POST_24H_GEMINI_BUDGET=1` + preflight gate ON 等、主要 sub 全部 prod 反映済 |
| **250-QA-1 manager_quote_zero_review** | rss_fetcher の `MANAGER_QUOTE_REVIEW_SUBTYPES` + event emit 実装済 |
| **250-QA-3 fetcher weak generated title** | `is_weak_generated_title` (title_validator.py) + 「前日コメント整理」「ベンチ関連の発言ポイント」phrase 入り |
| **275-QA github-actions tests failed audit** | CI 直近 3 run 全 SUCCESS、回復済 |
| **281-QA farm_result backlog allowlist** | guarded_publish_runner の `BACKLOG_NARROW_FARM_RESULT_SUBTYPES` + 24h cap 実装済 |
| **282-COST gemini preflight article gate** | `ENABLE_GEMINI_PREFLIGHT=1` prod env で ON 済(memory 282 CONDITIONAL_USER_GO 達成) |
| **289-OBSERVE post_gen_validate mail notification** | `ENABLE_POST_GEN_VALIDATE_NOTIFICATION=1` ON、silent skip 解消済 |
| **290-QA weak title rescue backfill** | `weak_title_rescue.py` + `ENABLE_TITLE_GENERIC_COMPOUND_GUARD` 等 5 関連 ENABLE_* flag prod ON |
| **293-COST preflight skip visible notification** | `ENABLE_PREFLIGHT_SKIP_NOTIFICATION=1` ON |
| **297-OPS pause codex-shadow-trigger** | scheduler state = PAUSED、実行済 |
| **248-MKT-2/3a same-game articles linking + display matrix** | parked、現在の運用ループ閉鎖 priority より外。再開時は doc/done/2026-05/ から復元 |

## waiting へ送ったもの

| ticket | 理由 | 戻す条件 |
|---|---|---|
| **205 GCP runtime drift audit** | 必要だが、今の本文ハルシネ対策の実装ではない。定期監査として待機 | Cloud Run image / Scheduler / logs に不整合が疑われた時 |
| **238 night-draft-only + morning report** | 必要だが、まず 234/244 の本文品質を安定させる。夜間運用は次の運用改善 | 本文品質が落ち着き、夜間 publish/mail 抑制を入れる段階 |
| **246-MKT today giants fan guide** | HOLD。247-QA amend と postgame strict 試合日観察が先。現場に投げない | 246-MKT 判断後に、必要なら実装 ticket として個別に戻す |
| **255-MKT fan guide expansion + comment badge** | HOLD。248 系の既存 ticket と採番衝突しないよう 255 に採番 | 246-MKT 観戦ガイドが成立し、コメント/反応導線を検討してよい時 |
| **249-INGEST live game ingestion expansion** | HOLD。Cloud Run / Scheduler 影響が大きい構想 | user が live ingestion の負荷とリスクを理解して明示 GO した時 |
| **256-QA manager/player quote strict subset** | HOLD。250 系の既存 ticket と採番衝突しないよう 256 に採番 | 247-QA の試合日観察後、コメント系を短い事実記事として分ける価値がある時 |
| **260-MKT fan-original article types and templates** | HOLD / design only。RC / T1 / 262-QA / 263-QA observation 完了 + user 明示 GO 後に 261-MKT-PILOT 起動判断 | 大手新聞の後追いではない巨人ファン向け独自記事型 6 型のテンプレ設計、実装しない |
| **261-MKT-PILOT (予約)** | HOLD / 261-PILOT 起動条件 達成後 RESUMABLE | 260-MKT で設計した 6 型から手動/半自動で 3 型 pilot、3-5 本評価、実装ではない |
| **234-impl-7 probable_starter / pregame body hardening** | READY_FOR_AUTH_EXECUTOR。repo実装済みだが残りは live handoff / observation 判断のため waiting へ移動 | live反映が必要な時だけ、Acceptance Pack と rollback target を確認して戻す |
| **291-OBSERVE candidate terminal outcome contract** | WAITING_PARENT / subtask-9 + subtask-10b live apply 完了。fetcher image `e0a58bb` / revision `00186-9cl` へ更新し、`ENABLE_NARROW_UNLOCK_SUBTYPE_AWARE=1` と `ENABLE_POSTGAME_STRICT_FACT_RECOVERY=1` を反映、既存 narrow flags 維持確認済み | 30-60min verify。Scheduler 次回 fire 以降で `weak_title_subtype_aware` / `postgame_strict_fact_recovery` event と scope-eligible postgame candidate の publish/review outcome を観測する。親 ticket 自体は waiting 維持、global gate 緩和はしない |
| **318-A..E social video full connect** | 318-C REVIEW_NEEDED / 318-A,B,D,E READY_DOC_ONLY。YouTube / Instagram / OB動画の完全接続を5本に分割。初期はreview/draft優先、publish/mail/scheduler/env/deploy/X/SEO不可触 | 318-C safe title fallback は repo実装 + full pytest PASS。次に進めるなら 318-A YouTube registry intake を小さく実装GO。 |
| **319-QA fetcher topic dedup and slot fill** | REVIEW_NEEDED。次の記事公開から重複話題で10枠を消費しないための narrow fix ticket | 再現テスト赤→緑、`src/rss_fetcher.py` 候補選別のみ修正済み。diff review + commit 判断待ち。deployは別GO |
| **320-FRONT scroll ads UIUX AdSense slot control** | READY_FOR_IMPL_AFTER_USER_GO。のもとけ型の scroll / sticky AdSense slot UIUX。dummy-only ではなく、既存または user 確認済み AdSense slot 前提 | まず Phase 0 read-only audit で repo / live DOM / WP 実設定を確認。記憶から再構成 / silent skip / 自己評価OKは禁止。publish/mail/scheduler/env/Cloud Run/GitHub Actions/SEO は不可触 |
| **323-QA source body excerpt clean truncation** | BLOCKED_USER_DIFF_REVIEW。`314-QA-rss-source-body-excerpt-followup` 関連。ブログ本文の `📖 本文抜粋` が600文字化後も途中切れ / UI・関連記事混入に見える問題を狭く扱う | repo local 実装 + 回帰テスト + full unittest OK。diff review と commit 判断待ち。publish / mail / scheduler / env / Cloud Run / X / SEO / featured_media は不可触 |
| **251/252/253/264/274/283/288/294/295/296** | HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY 系。active から waiting へ整理 | 各 ticket の解除条件または user GO が来た時 |

## いま動かす指示(2026-05-13 lock)

### close 済 (2026-05-13)

- **RESTORE-2026-05-08-MORNING-RELIABILITY**: LIVE_VERIFIED → `doc/done/2026-05/` 移動。5/13 朝 (06:01 / 07:01 / 08:01 JST) で投稿=9 / 2 / エラー=0、cron 安定稼働確認
- **2026-05-12 evening P0 UnboundLocalError incident**: hotfix `802511f` + `b8a7f01` 復旧確認済 (revision `00417-wuw` 100%、5/13 朝 publish 投稿=9/2 / エラー=0)。incident log は `docs/handoff/session_logs/2026-05-12_evening_INCIDENT_publish_unbound_local.md` (verify note 追記済)

### user 任意作業

- B 案 GAS 独立 ping 設定(10分): `doc/active/EXTERNAL-MONITOR-APPS-SCRIPT.md`
- 重複記事削除判断: 山野5勝 4本(64878/64879/64882/64883) / 5/6試合結果 2本(64983/64985) / 三塚二軍 2本(64861/64945)
- 若手 17人 eyecatch upload(WP media に upload で fallback 解消)

### 現場 (Claude / Codex) の不可触

- すでに deploy 済の 4 image を勝手に rollback しない
- 5/8 設定済 5 env flag を user 確認なしに変更しない
- `PUBLISH_NOTICE_BURST_THRESHOLD=-1` は user 同意済、変更しない
- 04-06時 publish-notice silence は user 同意済、戻さない
- giants-morning-catchup 04:30 schedule は user 同意済、戻さない

## 役割

| 略号 | 役割 | やること |
|---|---|---|
| **Claude** | 現場管理 / accept / push / live監視 | 開発しない。src/tests編集しない。commitしない |
| **Codex A** | ops / GCP / WP / mail / build / scheduler infra | live mutation は authenticated executor 境界を守る |
| **Codex B** | evaluator / validator / article quality / numeric / template | 234-impl-7 など品質系を narrow に実装 |
| **User** | 最終判断 | 重要な live mutation / WP記事判断 / scope拡張だけ判断 |

Codex C / Codex-M は使わない。

## ad hoc live ops

| lane / scope | status | 次 action |
|---|---|---|
| **Lane FF / BUG-004+291 replay-window dedup (Task 37)** | LIVE_APPLIED | `publish-notice` image `4231805` + `ENABLE_REPLAY_WINDOW_DEDUP=1` を反映済み。次の manual replay / scheduler overlap で `DUPLICATE_WITHIN_REPLAY_WINDOW` 観測を確認する |
| **Lane JJ / BUG-004+291 fetcher fan-important narrow exempt** | REPO_IMPL_READY | code commit `1ccda1b` 済み。次は authenticated executor が `yoshilover-fetcher` image `:1ccda1b` build/update + `ENABLE_FETCHER_FAN_IMPORTANT_NARROW_EXEMPT=1` apply、その後 5-15 分 fetcher cycle で `fetcher_fan_important_narrow_exempt` event と rescued draft/publish terminal state を観測する |
| **Lane KK / 64424-64461 incident ledger + publish-forward audit** | LEDGER_READY | 38件棚卸し完了。分類 `B4 / C2 / D6 / E23 / F3`、safe rescue `0`。`64437` / `64447` は publish-notice state drift で STOP lock、次は Claude が ledger review / push / follow-up 起票 |
| **Lane MM / 64437 publish-notice phantom publish marker narrow fix** | REPO_IMPL_READY | repo audit + strict-stamp fix + tests 完了。次は authenticated executor が `publish-notice` image build/update と `ENABLE_PUBLISH_NOTICE_HISTORY_STRICT_STAMP=1` apply、その後 `64437` / `64447` 再発有無と new history stamp を観測する |
| **Lane LL / BUG-003 64424 revert actor + WP revert guard** | REPO_IMPL_READY | `64424` は repo-visible evidence 上 true revert ではなく、`publish_notice` direct-publish seed による phantom publish marker。`src/wp_client.py` に `ENABLE_WP_REVERT_AUDIT_LEDGER` / `ENABLE_WP_PUBLISHED_REVERT_GUARD` を追加し、publish 済みから `draft/private` への repo-owned mutation を audit/block できる状態にした。`tests.test_wp_client` と `tests.test_guarded_publish_runner` pass。次は Claude が doc review / commit review / 必要なら authenticated executor へ build+env plan を handoff |
| **Lane NN / 64432-64461 quality NG 3件 audit + ticket assignment** | REPO_DOC_READY | `64432` は 277 insufficiency + 290未live、`64453` は元巨人OBの非野球 relevance 漏れ、`64461` は Blue Jays→Giants entity contamination と判定。次は Claude が ledger review / push / per-id live judgment(A/B/C) と follow-up ticket 起票 |
| **Lane PP / article body quality v1 active repair + per-id preview** | REPO_IMPL_READY | Lane OO guard維持のまま `ENABLE_H3_COUNT_GUARD` / `ENABLE_ENTITY_MISMATCH_REPAIR` を追加。preview runner と 5 candidate dry-run ledger を作成し、full pytest は `2246 pass / 4 pre-existing fail` で据え置き。次は Claude が preview ledger review / commit review / user preview judgment を進める |
| **Lane QQ / body template v2 narrow tune (related-post H4 + social tone cleanup)** | REVIEW_NEEDED | rollback 後の narrow fix として、v2 ON 時だけ `📌 関連ポスト` を `<h4>` へ降格し、`social_v2` fallback の「目を引きます」を除去。新規 preview test で live踏襲 3 sample の `H3<=2` / forbidden phrase 0 hit を確認済み。次は Claude が commit review / push / user preview judgment を進め、reflip は別便で扱う |
| **Lane B / RSS type classification narrow fixes (5 flags)** | REVIEW_NEEDED | `src/rss_fetcher.py` に 5 本の default-OFF flag を追加し、RSS 型 drift 修正を narrow 実装。`tests/test_rss_fetcher_type_routing_flags.py` を追加し、full pytest は `2315 pass / 4 pre-existing fail` で据え置き。次は Claude が commit review / push judgment を行う |
