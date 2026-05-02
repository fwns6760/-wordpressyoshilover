# assignments — 現場担当と次アクション

最終更新: 2026-05-02 JST

## 最初に読む

- `doc/active/OPERATING_LOCK.md`
- `doc/README.md`
- `doc/active/assignments.md`

## folder cleanup note(2026-05-02)

- Active folderから、明確な HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY / READY_FOR_AUTH_EXECUTOR を waiting へ移動。
- `205-COST` は done/2026-05 へ移動。
- READY / REVIEW_NEEDED で現場が拾う可能性のある ticket は勝手に close していない。

## いま active に残すもの

| ticket | status | 判定 | 次 action |
|---|---|---|---|
| **245 front hide internal auto-post category label** | READY | **必要。いま動かす** | Front画面に内部カテゴリ「自動投稿」が出るのを止める。カテゴリ削除ではなく表示除外のみ |
| **277-QA title player name backfill** | REVIEW_NEEDED | **必要。impl 済み** | helper + fetcher integration + 1826 tests pass。次は Claude review と push 判断 |
| **279-QA mail subject clarity** | READY_FOR_FIX | **必要。277 の次** | publish-notice 件名だけで公開済み / review / hold / 古い候補を判別できるようにする。今回は doc-only |
| **278-QA RT title cleanup** | READY_FOR_FIX | **必要。279 の次** | RT prefix / 公式X断片 / グッズ告知系 title を整形する。今回は doc-only |
| **280-QA summary excerpt cleanup** | READY_FOR_FIX | **必要。series 最後** | publish-notice 本文 summary / excerpt の判断材料を改善する。今回は doc-only |
| **229 Gemini cost governor + LLM call reduction** | REVIEW_NEEDED | **必要。継続監視** | fetcher 100% 後の Gemini call / skip / ledger を見て、229-C prompt compression をやるか決める |
| **OPERATING_LOCK** | ACTIVE_LOCK | **必要。常時参照** | 事故防止ルール。変更は慎重に、src 実装とは混ぜない |
| **assignments** | ACTIVE_BOARD | **必要。現在地** | 本ファイル。active を増やしすぎない |

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
| **291-OBSERVE candidate terminal outcome contract** | DESIGN_DRAFTED。BUG-004+291 の publish=0 原因分解 / narrow unlock / 292 durable ledger 方針を同一 doc に統合済み | 289 / 293 は repo 実装 evidence あり。live visibility 確認 + user GO が揃うまで waiting 維持。global gate 緩和はしない |
| **251/252/253/264/274/283/288/294/295/296** | HOLD / BACKLOG / DESIGN_ONLY / READY_FOR_USER_APPLY 系。active から waiting へ整理 | 各 ticket の解除条件または user GO が来た時 |

## いま動かす指示

### 234-impl-7: waiting へ移動

- repo 実装済みだが、残りは live handoff / observation 判断。
- active 実装 lane ではないため `doc/waiting/` に退避。
- 再開時は Acceptance Pack / rollback target / post-deploy verify を確認してから扱う。

### Codex A / front-scope: 245 を実装

目的:

- 画面に内部カテゴリ `自動投稿` を出さない。
- category id `673` / slug `auto-post` / name `自動投稿` は内部管理用として front 表示から除外する。

制約:

- WP category 自体は削除しない
- 既存 post の category 付け替えなし
- Python backend / GCP / WP publish / X / Gemini に触らない
- `src/yoshilover-063-frontend.php` の narrow fix
- `php -l` pass

## 役割

| 略号 | 役割 | やること |
|---|---|---|
| **Claude** | 現場管理 / accept / push / live監視 | 開発しない。src/tests編集しない。commitしない |
| **Codex A** | ops / GCP / WP / mail / build / scheduler infra | live mutation は authenticated executor 境界を守る |
| **Codex B** | evaluator / validator / article quality / numeric / template | 234-impl-7 など品質系を narrow に実装 |
| **User** | 最終判断 | 重要な live mutation / WP記事判断 / scope拡張だけ判断 |

Codex C / Codex-M は使わない。
