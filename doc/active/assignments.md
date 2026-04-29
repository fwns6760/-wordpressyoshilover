# assignments — 現場担当と次アクション

最終更新: 2026-04-29 JST

## 最初に読む

- `doc/active/OPERATING_LOCK.md`
- `doc/README.md`
- `doc/active/assignments.md`

## いま active に残すもの

| ticket | status | 判定 | 次 action |
|---|---|---|---|
| **234-impl-7 probable_starter / pregame body hardening** | READY_FOR_AUTH_EXECUTOR | **必要。repo実装済み** | 試合前・予告先発系の source anchor / post-gen check 実装済み。次は image rebuild 判断 |
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

## いま動かす指示

### 234-impl-7: repo 実装済み、live 反映待ち

目的:

- 試合前・予告先発系で、AI が未確定スコア、未確定打順、source/meta にない投手名を本文へ足すのを止める。
- 数字・選手名は AI が考えない。source/meta にあるものだけ使う。

制約:

- Gemini call 追加なし
- Web/API 追加なし
- prompt 全体改修なし
- template 全体一括実装なし
- postgame / farm / notice / program / default の既存挙動を変えない
- `git add -A` 禁止、明示 path のみ
- デグレ厳禁

write scope:

- `src/fixed_lane_prompt_builder.py`
- `src/body_validator.py`
- `tests/test_body_validator.py`
- `tests/test_fixed_lane_prompt_builder.py`
- `doc/active/234-impl-7-probable-starter-pregame-body-hardening.md`

acceptance:

- good pregame / probable_starter fixture は通る
- source にない score / lineup / pitcher name は fail axis になる
- 既存 fixture fail 0
- live deploy は別判断

### Claude: live 監視 + rebuild 判断

- fetcher / guarded-publish / publish-notice / draft-body-editor の failure pattern を監視
- `ModuleNotFoundError`, `Traceback`, HTTP 500, timeout, exit(1) は即 rollback 判断
- WP publish / draft patch / env / Scheduler / Secret / RUN_DRAFT_ONLY は勝手に変更しない
- 234-impl-7 の live 反映時は fetcher / draft-body-editor image rebuild を検討し、/run 直接 curl は使わない

## 役割

| 略号 | 役割 | やること |
|---|---|---|
| **Claude** | 現場管理 / accept / push / live監視 | 開発しない。src/tests編集しない。commitしない |
| **Codex A** | ops / GCP / WP / mail / build / scheduler infra | live mutation は authenticated executor 境界を守る |
| **Codex B** | evaluator / validator / article quality / numeric / template | 234-impl-7 など品質系を narrow に実装 |
| **User** | 最終判断 | 重要な live mutation / WP記事判断 / scope拡張だけ判断 |

Codex C / Codex-M は使わない。
