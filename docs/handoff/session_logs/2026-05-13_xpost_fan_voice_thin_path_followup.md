# 2026-05-13 — X post / ファンの声 thin path follow-up(明日の作業 entry log)

> 本 file は 2026-05-12 PM session の調査結果を翌朝の作業者(Claude / Codex / user)が
> そのまま拾えるよう、観察事実 / 既存 ticket / 問題点 / 次 action を 1 file に圧縮した。

## context

- 2026-05-12 PM 実施。user 質問「サイトにあるXの私の声のポストだよRSSで拾ってるもの。消えてない?」
- 同 session で 324-QA / 325-QA fan voice whitelist RSS ticket を起票・scaffolding 実装(commit `a32f285` / `9120618` / `53cac10`)
- 326-QA thin article fan voice enrichment marker gate relax ticket を本日同 session で追加起票
- 本 file は明日朝に user / 作業者が拾うための entry point

## 1. 本日(5/12 PM)発見した問題点

### 1-A. thin path article で `💬 ファンの声` が出ない

直近 20 post audit(2026-05-12 PM、yoshilover.com 公開 site):

| 指標 | 件数 | 補足 |
|---|---|---|
| ファンの声 ≥1 入り | **15/20 = 75%** | 大半は正常に出ている |
| thin path(H3≤1、ファンの声 0) | **5/20 = 25%** | 全部「短報・選手 1 人系」 |
| full path(H3≥3) | 10/20 | 正常 |

thin path 該当 post(5/12 公開分):

- 66656 中川皓太(無失点短報)
- 66654 田和廉(無失点短報)
- 66643 吉川尚輝(凱旋打)
- 66641 戸郷翔征(失点短報)
- 66601 戸郷翔征(逆転許し)

### 1-B. 真因(調査済、5/8 から既知)

`src/tools/manual_intake.py` の `apply_rss_pipeline_enrichment`(commit `927ac2c`)に `class="nomotoke-card-` の marker gate がある。RSS auto path の template_key(`postgame_strict` / `score_lite` / `manager` 等)は **非 nomotoke 系**なので marker が付かず、enrichment が早期 return → `💬 ファンの声` H3 / X embed が注入されない。

### 1-C. 既知の関連事故(本日 audit で再確認)

| 現象 | 該当 ticket | status |
|---|---|---|
| thin path で ファンの声 0 | `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08`(parent) | DESIGN_REQUIRED、user 軸判断 5 日 pending |
| 同 thin path narrow fix(本ticket) | `326-QA-thin-article-fan-voice-enrichment-marker-gate-relax`(child) | BLOCKED_USER(本日 5/12 起票) |
| 同日 10 秒差で双子 publish(66654 + 66649) | `319-QA-fetcher-topic-dedup-and-slot-fill` | REVIEW_NEEDED、diff review + commit 判断待ち |
| 公式・報道X が 0/20 表示 | `H3-STRUCTURE-UNIFY-2026-05-08` | 統合済(`📣 関連投稿` 3 形式を `💬 ファンの声` に merge、これは正常)|

### 1-D. 本日 commit と production の関係

| commit | 内容 | deploy 状態 | 影響 |
|---|---|---|---|
| `a32f285` | 324-QA / 325-QA ticket file 化 | doc-only | なし |
| `53cac10` | 5/12 PM session log | doc-only | なし |
| `9120618` | 324-QA fan_voice_pool source registration scaffolding(src/rss_fetcher.py 97 insertions + tests 143 insertions) | **未 deploy**(Cloud Run image 未更新) | production 0 |

→ 本日 thin path 5/20 が ファンの声 0 になっている現象は **本日 commit 由来ではない**。5/8 から続く既存挙動。

## 2. 明日朝に user に上げる判断点(1 件)

判断してほしいこと:
親 ticket `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08` の修正軸を決める

選択肢:

- **A. 本文長**: thin path 本文を Gemini で長文化(LLM 本文補完禁止 policy と衝突しないか別途確認)
- **B. 装飾 marker gate 緩和**(推奨): marker hard match を緩和、thin path にも `💬 ファンの声` enrichment を適用、`326-QA` が narrow 実装担当
- **C. 自動化分岐の作り直し**: thin body 作る branch そのものを消す(scope 大、デグレ risk 高)
- **D. A + B + C 複合**

推奨 **B**: 既に narrow 実装ticket(326-QA)を用意済み、write scope は `src/tools/manual_intake.py` のみ、デグレ risk 低、本日 audit で 25% improvement が見込める。

返答形式: `A` / `B` / `C` / `D` / 「触らない」

## 3. user GO 後の作業手順(明日以降)

1. 親 ticket の軸を B で固定、status を `DESIGN_REQUIRED` → `READY_FOR_IMPL` に更新
2. 326-QA を `BLOCKED_USER` → `READY` に更新、`doc/waiting/` → `doc/active/` に移動
3. 326-QA §2 write scope に従い、Phase 0 で 2-3 案 bench(gate 緩和の判定文言)
4. fixture-based regression test を先に書く(本日 audit の 5 post + 15 post fixture)
5. gate 緩和 impl → 全件テスト green → diff 提示 → commit → push → Cloud Run image rebuild → no-traffic deploy → /health 確認 → traffic 移行 → 翌朝再 audit で 5/20 → 0/20 に近づくか確認
6. full path 15 post の出力 diff = 0 を fixture で確認(回帰なし)
7. 326-QA → REVIEW_NEEDED → CLOSED

## 4. 本日 commit の取り扱い(明日朝 verify)

- `9120618`(324-QA scaffolding)は repo に landed、未 deploy。326-QA とは scope が完全に直交なので、326-QA 実装で巻き込まない
- 325-QA(picker integration)は **handle curation 未着のため未着手**、326-QA とは別経路(whitelist 別 lane)、direct conflict なし
- 別作業者の `npb_playbyplay_extractor` import block(10 lines)が src/rss_fetcher.py に未 commit で working tree に存在。本日 私の commit には混ぜていない(revert → 再 apply → 復元の手順で分離済み)。明日朝の作業前に `git status --short` で再確認、別作業者が commit しているか / dirty のままか判断

## 5. 次 session entry checklist(明日朝、作業者が読む)

- [ ] 本 file(`2026-05-13_xpost_fan_voice_thin_path_followup.md`)
- [ ] 親 `doc/active/MANUAL-INTAKE-QUALITY-PARITY-2026-05-08.md`
- [ ] 子 `doc/waiting/326-QA-thin-article-fan-voice-enrichment-marker-gate-relax.md`
- [ ] 同 session の前段 log `2026-05-12_pm_324_325_fan_voice_whitelist_tickets.md`
- [ ] `git log --since="2026-05-12 12:00" --oneline` で本日 commit 確認
- [ ] `git status --short` で working tree dirty 確認(別作業者 WIP 残存有無)

## 6. 直近 20 post audit raw data(参考)

| id | date | H3 数 | fan | X 個別 | title 抜粋 |
|---|---|---|---|---|---|
| 66656 | 2026-05-12T20:30:39 | 1 | 0 | 0 | 中川皓太がまたも０封！... |
| 66654 | 2026-05-12T20:30:35 | 1 | 0 | 0 | ドラ２・田和廉がまたしても... |
| 66652 | 2026-05-12T20:30:31 | 3 | 1 | 0 | 中川皓太、失点 |
| 66649 | 2026-05-12T20:30:25 | 3 | 1 | 0 | ドラ２・田和廉がまたしても...(twin) |
| 66643 | 2026-05-12T20:01:04 | 1 | 0 | 0 | 吉川尚輝が凱旋打 |
| 66641 | 2026-05-12T20:00:58 | 1 | 0 | 0 | 戸郷翔征が５回に坂倉に痛恨 |
| 66639 | 2026-05-12T20:00:54 | 3 | 2 | 0 | 吉川尚輝「勝ってプレゼント」 |
| 66637 | 2026-05-12T20:00:47 | 3 | 2 | 0 | 戸郷翔征「天下統一」 |
| 66635 | 2026-05-12T20:00:41 | 3 | 2 | 0 | 大城卓三「風に乗ってくれました」 |
| 66633 | 2026-05-12T20:00:33 | 2 | 1 | 0 | 増田陸、打点に発言 |
| 66630 | 2026-05-12T19:46:47 | 2 | 1 | 0 | 岐阜のファンに勝利を |
| 66627 | 2026-05-12T19:46:41 | 3 | 1 | 0 | 二軍 1-0 DeNA |
| 66624 | 2026-05-12T19:46:33 | 3 | 1 | 0 | 二軍 1-0 DeNA(twin) |
| 66621 | 2026-05-12T19:46:24 | 2 | 1 | 0 | 投手 + 鵜飼い と記念撮... |
| 66618 | 2026-05-12T19:46:15 | 3 | 2 | 0 | グッズを「デデーン...」 |
| 66615 | 2026-05-12T19:46:07 | 2 | 1 | 0 | ミニのぼりと小林誠司... |
| 66609 | 2026-05-12T19:45:48 | 2 | 1 | 0 | 岐阜開催記念 |
| 66606 | 2026-05-12T19:45:38 | 4 | 1 | 0 | 一軍 vs 広島 ぎふしん長良川 |
| 66603 | 2026-05-12T19:45:24 | 4 | 1 | 0 | 一軍 vs 広島(twin) |
| 66601 | 2026-05-12T19:30:30 | 1 | 0 | 0 | 戸郷翔征 ４回満塁ピンチ |

X 個別カウントが全件 0 なのは `📣 公式・報道X` H3 が `H3-STRUCTURE-UNIFY-2026-05-08` で `💬 ファンの声` に統合済の正常挙動(別事故ではない)。
