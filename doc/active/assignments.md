# assignments — 現場担当と次アクション

最終更新: 2026-04-27 JST(200 scanner subtype fallback close + 201 readiness_guard flaky ticket 追加 + 199 publish-notice rebuild runbook / blocked-user 追加 + 197 195 live deploy runbook / blocked-user 追加 + 198 190/191 keep ratify close + 196 ingestion 5分リアルタイム trigger 追加 + 195 article footer 手動X share corner 実装 + 194 publish-notice 5分cron化 + 192 doc hygiene retry + 188/187/186/185/184/183 close)

## 最初に読む

- `/home/fwns6/code/wordpressyoshilover/doc/active/OPERATING_LOCK.md`
- `/home/fwns6/code/wordpressyoshilover/doc/README.md`
- `/home/fwns6/code/wordpressyoshilover/doc/active/assignments.md`

## 役割一覧

| 略号 | 役割 | 変更OK | 原則NG |
|---|---|---|---|
| **Claude** | 現場管理 / accept / push / 危険境界判断 | doc整理、Codex便accept、git push、read-only監査 | src/tests直接編集(緊急narrow fixのみ)、secret表示、live境界越え |
| **Codex A** | ops / GCP / WP / mail / publish runner 開発 | WP REST、publish runner、mail、cron、GCP deploy helper、persistence、backup、queue、history、対応tests | X live post、secret表示、front dirty、Codex Bが同時に触る品質系ファイル |
| **Codex B** | 品質 / evaluator / validator / SEO / SNS / X gate / mail本文系の開発担当 | `src/*evaluator*`, `src/*validator*`, `src/*audit*`, `src/*quality*`, `src/*source*`, `src/*title*`, `src/*sns*`, `src/*x_post*`, mail本文/digest系のdry-run/gate/queue/ledger、対応`tests/test_*`、該当ticket doc。作った処理は原則GCP実行へ寄せる | `.env`, `logs/`, `build/`, Cloud Run/Scheduler/Secret Manager live変更、WP live write、X live post、front dirty、Codex Aが同時に触るopsファイル |
| **Codex-GCP** | Cloud Run / Scheduler 上で動く自動実行レーン | 設定済みJob/Schedulerの定期実行、GCS/Secret経由の状態利用、Cloud Logging出力、既存gate内の記事修復、`CODEX_WP_WRITE_ALLOWED` 等で許可済みのWP article write、SNS topic処理、SEO/quality監視、mail本文/digest生成、X gate/queueのdry-run実行 | repo編集、git操作、secret表示、未許可live scope拡張、未解禁X live post、Cloud Run/Scheduler/Secret Managerの新規変更 |
| **User** | 最終判断 | X live unlock、secret/env/scheduler/scope拡張、重要な公開方針判断 | - |

## 今の主線

| ticket | priority | status | 担当 | 次 action |
|---|---|---|---|---|
| **README**(旧102) | P0 | READY | Claude | dispatch board正本を維持 |
| **187 publish-notice scheduler URI v1 verify** | P0.5 | CLOSED | Codex / Claude | v1 URI verify は `0cc7cc3` に記録済み。step 2-4 は 188 Fix A 後の manual trigger success で実質完了 |
| **188 publish-notice scheduler IAM fix** | P0.5 | CLOSED | Codex / User / Claude | `74ccef6` runbook + invoker bind 完了。manual trigger `publish-notice-9rsjt` で 20 mail 送信成功 |
| **194 publish-notice scheduler 5分毎化** | P0.5 | REVIEW_NEEDED | Codex / Claude | `publish-notice-trigger` を `*/5 * * * *` へ変更済み。`2026-04-27 09:40 JST` natural tick execution `publish-notice-6x7f5` と rollback は `doc/active/194-publish-notice-scheduler-5min.md` に記録 |
| **195 article footer manual X share corner** | P0.5 | REVIEW_NEEDED | Codex / Claude | `src/yoshilover-063-frontend.php` に singular post footer の 3-candidate X share corner を追加。copy/intent/toggle 付き。live deploy は `197` runbook/user-side WP access 待ち |
| **196 ingestion 5分毎リアルタイム化** | P0.5 | REVIEW_NEEDED | Codex / Claude | `giants-realtime-trigger` を `*/5 * * * *` で新規作成済み。既存 `giants-*` と同じ `yoshilover-fetcher /run` + `seo-web-runtime@baseballsite.iam.gserviceaccount.com` を使用し、`2026-04-27 09:55 JST` natural tick HTTP 200 を確認 |
| **105 / PUB-004-D** | P0 | AUTO 5min cron | Codex-GCP + Claude監視 | RSS新着を5-15分内にauto publish、daily cap 100 |
| **042 draft-body-editor** | P0 | GCP本線 / 残WSLはgemini_auditのみ | Codex-GCP + Claude監視 | GCP上のCodex/Gemini repair、WP article write、品質/メール系実行を監視。WSL本線依存を戻さない |
| **155 GCP migration master** | P0.5 | IN_FLIGHT | Claude / A | 主要移行は完了。残りは162/163とX live系 |
| **147 X auto-post親ramp** | P0.5 | READY | Claude | 149/174 live smoke前提を整理 |
| **154 publish-policy** | reference | active | Claude | 現行公開方針の参照元 |

## 次に動かすREADY

| ticket | priority | status | 担当 | 次 action |
|---|---|---|---|---|
| **179 repair learning log Firestore + GCS** | P0 | READY / 即fire | Codex B → Codex-GCP | FirestoreLedgerWriter + ArtifactUploaderを実装し、GCP実行へ接続 |
| **180 SNS topic intake lane separation** | P0.5 | READY | Claude / Codex B → Codex-GCP | SNS入口とX出口の境界をdoc-onlyで明文化し、SNS topic処理をGCP実行前提に整理 |
| **201 readiness_guard flaky** | P1 | READY | Codex B | `tests/test_guarded_publish_readiness_guard.py::test_human_format_renders_summary` の real-now 依存を fixed `now` 注入または狭い assertion 調整で解消 |
| **162 gemini_audit GCP migration** | P1 | QUEUED / 後回し可 | Claude / A | 残WSL cronはgemini_auditのみ。影響軽微なので急がない |
| **163 quality-monitor / quality-gmail GCP migration** | P1 | QUEUED | Claude / A → Codex-GCP | quality monitor / quality mail本文生成をGCP化 |
| **149 X Phase 2 manual live 1** | P0.5 | READY / user境界 | Claude / A | userのX live unlock後、1件だけmanual post |

## user / 外部待ち

| ticket | priority | status | 待ち | 担当 |
|---|---|---|---|---|
| **174 x-api-cloud-run-live-smoke** | P0.5 | BLOCKED_USER | 149のX live unlock後 | User → A |
| **197 195 live deploy manual X share corner** | P0.5 | BLOCKED_USER | Xserver 実接続情報 + WP root path + option false を先置きできる user-side shell / WP admin access | User / Claude |
| **199 publish-notice rebuild a9c2814** | P0.5 | BLOCKED_USER | user shell で `publish-notice` の Cloud Build / Job image update / verify を実行。Codex sandbox の `gcloud` は active account credential invalid で read-only verify 時点停止 | User / Claude |
| **175 x-controlled-autopost-cloud-rollout** | P0.5 | BLOCKED | 174 smoke成功 | Claude / A |
| **128 SNS auto-publish** | P1 | PARKED | 180で入口/出口境界整理後 | Codex A |
| **151 X Phase 4 cap3 ramp** | P1 | PARKED | 150 + 7日stable | Claude / A |
| **152 X全カテゴリ拡張** | P2 | PARKED | 147 phase 5 stable | Future |
| **113 / HALLUC-LANE-002** | P1 | PARKED | Gemini live cost境界 | User go待ち |
| **095-E WSL cron reboot** | P2 | BLOCKED_USER | PC reboot時 | User |
| **PUB-005 X gate parent** | P1 | PARKED | X live unlock | User → A |

## 最近完了した大物

| ticket | 状態 | 意味 |
|---|---|---|
| **156 / 157 / 158** | CLOSED | 042 Cloud Run deploy、Scheduler、Secret Manager + GCS persistence完了 |
| **159 / 160 / 161** | CLOSED | WSL publish lane disable、PUB-004-C GCP化、publish-notice GCP化完了 |
| **165 / 166 / 167** | CLOSED | Gemini/WP REST resilience、Cloud Run failure alert、billing alert完了 |
| **177** | CLOSED `a5ef56a` | Codex shadow GCP deploy完了 |
| **178** | CLOSED `9754b53` | GCP Codex primary wp_write enable。Codex-GCPが記事修復/書き込みを担う前提を解禁 |
| **181** | CLOSED `5b21543` | タイトル主語欠落 + 本文可読性narrow fix完了 |
| **200** | CLOSED `e78f088` | publish_notice_scanner に REST subtype 欠落時の fallback 推論を追加し、lineup/postgame/farm/notice/program/default の 5+1 分類と scanner tests を着地 |
| **183 / 184 / 185 / 186** | CLOSED | publish gate 緩和、ledger integration、entrypoint `--exclude-published-today` 一時除去、scan_limit/history dedup narrow 完了 |
| **187 / 188** | CLOSED | publish-notice scheduler URI v1 verify と IAM fix runbook整理、Fix A 実行 + execution `9rsjt` で 20 mail verify 完了 |
| **189** | CLOSED | 公開通知メールの手動X投稿候補を subtype selector 方式へ拡張。notice/sensitive gate、inside_voice条件、URL最大3 |
| **190 / 191** | CLOSED | publish-notice mail の manual X candidates を keep ratify。user 認容「ポストも乗るんだよね。公開記事に。」、`1ac710b` / `b7a9e1f` freeze、`195` frontend 整合確認まで正式 scope 化 |
| **168-173** | CLOSED | repair provider ledger、job skeleton、fallback、Codex shadow runner、auth writeback、X queue ledger完了 |
| **176** | CLOSED `91069f0` | share buttons Twitter/Facebook fix完了。live deploy後の目視smokeは別途 |

## fire rule(autonomous lock)

- Claude がREADY/IN_FLIGHTを「即fire可」に判断したら、user確認なしでCodex A/Bに投げる
- live publish / WP write / X / SNS / scheduler / `.env` / secret / scope拡張はuser判断
- Codex-GCPはGCP上の記事修復・許可済みWP article write・SNS topic処理・SEO/quality監視・mail本文/digest生成・X gate dry-runの実行レーンであり、repo編集者ではない
- デグレなしlock: 全promptにbaseline数値 + 維持contractを入れ、accept時は5点追認
- status変更時は ticket doc移動 + README `doc_path` + assignments更新を同commitまたは直後doc-only commitで揃える
- `git add -A`禁止。変更pathだけ明示stage
