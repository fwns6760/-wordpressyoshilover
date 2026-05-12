# 326-QA thin article fan voice enrichment marker gate relax

## meta

- number: 326-QA
- type: thin article(RSS auto path)に `💬 ファンの声` block を出すための marker gate 緩和(narrow fix)
- status: BLOCKED_USER
- priority: P1
- owner: user GO 待ち
- implementation_owner: Codex / Claude after GO
- lane: B
- created: 2026-05-12
- doc_path: `doc/waiting/326-QA-thin-article-fan-voice-enrichment-marker-gate-relax.md`
- parent: `doc/active/MANUAL-INTAKE-QUALITY-PARITY-2026-05-08.md`(軸 B 採択の narrow 実装子 ticket)
- blocked_by: 親 ticket の軸 B(装飾 marker gate 緩和)を user が明示 GO すること
- related: `H3-STRUCTURE-UNIFY-2026-05-08.md`(`📣 関連投稿` 3 形式を `💬 ファンの声` に統合済、本 ticket は thin path 側にも反映させる位置づけ)
- note: 本便はこの Markdown 新規作成のみ。code edit、commit、push、deploy、env / scheduler 変更は GO 後まで保留

## 1. 今回の目的

直近 20 件 audit(2026-05-12 PM 実施)で **5/20 = 25%** の article が thin path で生成されており、`💬 ファンの声` H3 が **0 件**(本文中の X embed も 0)になっている。

該当 5 件(2026-05-12 サンプル):

- post 66656 中川皓太(無失点短報)
- post 66654 田和廉(無失点短報)
- post 66643 吉川尚輝(凱旋打)
- post 66641 戸郷翔征(失点短報)
- post 66601 戸郷翔征(逆転許し)

全部「短報系・選手 1 人の数行コメント」型。残り 15/20 は `💬 ファンの声` ≥1 で出ているため、**fan voice picker そのものは生きている**。問題は thin path で **enrichment 装飾 gate が早期 return** しているだけ。

この ticket では gate を狭く緩和し、thin path にも `💬 ファンの声` block(統合 X embed 含む)を出せるようにする。**本文長や自動化分岐は触らない**(親 ticket の軸 A / C は scope 外)。

## 2. 今回触る範囲

GO 後に触る想定の write scope は次に限定する。

- `src/tools/manual_intake.py` の `apply_rss_pipeline_enrichment` の marker gate(commit `927ac2c` 由来)
  - 候補修正案: `class="nomotoke-card-` の hard prefix match を `class="nomotoke-` prefix or `data-nomotoke-fan-voice="ready"` 等の opt-in attribute に緩和、または RSS auto path 側で marker を付けて配管に流す
  - 最終決定は GO 後の Phase 0 で 2-3 案を bench
- 必要に応じて RSS auto 側 template の `nomotoke-` marker 付与経路(`src/rss_fetcher.py` の v2 routing 出口)
- 関連 test(`tests/test_manual_intake*` / `tests/test_apply_rss_pipeline_enrichment*` / fixture-based audit)
- 本 ticket 自身 `doc/waiting/326-QA-thin-article-fan-voice-enrichment-marker-gate-relax.md`

## 3. 今回触らない範囲

- 親 ticket の軸 A(本文長を増やす)/ 軸 C(自動化分岐の作り直し)
- `fetch_fan_reactions_from_yahoo()` / `fetch_fan_reactions_with_grok()` 本体
- 公式・報道X の別 H3 復活(H3 統一済、ファンの声に merge 維持)
- publish / mail / scheduler / env / Cloud Run / Secret Manager / X API
- 既存 15/20 の full path article 出力(変えない)
- 同日に存在する duplicate publish 事故(319-QA-fetcher-topic-dedup の担当)
- 324-QA / 325-QA の fan_voice_pool 経路(別経路、本 ticket と衝突しない)
- WordPress 本番 mutation(REST GET 以外)

## 4. 影響範囲

- thin path で生成される RSS auto article(直近 25%、約 5/20 程度)に `💬 ファンの声` H3 と X embed が追加で出る
- full path article(15/20)の挙動は **不変**(既存 marker gate 通過は維持)
- mail / SEO / X 自動投稿 への影響なし(本文 enrichment のみ)
- 万一 thin path で fan reaction が 0 件しか拾えなければ H3 ごと出ない(既存の picker 仕様維持)

## 5. 実行予定テスト

1. 追加再現テスト(赤確認 → 緑確認)
   - thin path body(`nomotoke-card-` marker 無し / `nomotoke-` 系 marker 有り)に enrichment が走り `💬 ファンの声` block が出る
   - 既存 full path body(`nomotoke-card-` marker 有り)では出力 diff = 0(既存挙動維持)
   - thin path で fan reaction 0 件のときは H3 ごと出ない(空 H3 を埋め草で出さない)
   - 別試合 / 別カード / 別日付の reaction は混ぜない(既存 strict match 維持)
2. fixture-based regression
   - 5 件の thin path post(66656 / 66654 / 66643 / 66641 / 66601 系の fixture)で `💬 ファンの声` 追加を確認
   - 15 件の full path post fixture で出力差分 0 を確認
3. related unit tests
   - `tests/test_manual_intake*`
   - `tests/test_apply_rss_pipeline_enrichment*`(or 同等)
   - `tests/test_rss_fetcher*`
   - `tests/test_nomotoke_card_renderer*`
4. full suite
   - `python3 -m unittest discover -s tests`

## 6. STOP条件

- 親 ticket の軸が user 判断で確定するまで実装開始しない
- gate 緩和で full path article の `💬 ファンの声` 件数 / order / 文言が変わったら STOP(精度回帰)
- 別試合 / 別選手の混入が thin path で起きたら STOP
- `fetch_fan_reactions_*` 本体に手が伸びそうになったら STOP(scope 違い、別 ticket)
- 公式・報道X を別 H3 として復活させそうになったら STOP(H3 統一仕様違反)
- 全件テスト green を満たせない場合 STOP

## 7. 禁止事項

- 親 ticket の軸 A(本文長を増やす)を本 ticket に混ぜない
- 親 ticket の軸 C(自動化分岐の作り直し)を本 ticket に混ぜない
- thin path 本文の Gemini 増生成(LLM 本文補完禁止 policy 違反)
- publish / mail / scheduler / env / Cloud Run / X API 変更
- X 自動投稿 / SEO / featured_media への副次変更
- 319-QA(duplicate publish)を本 ticket scope に含めない

## 8. 想定されるデグレ

- gate 緩和の判定文言を間違えると、`<aside class="nomotoke-...">` を含む別文脈 body にも誤適用される
- thin path に Yahoo strict match の弱い reaction が混ざる(既存 strict 維持で防止)
- `💬 ファンの声` の H3 重複(thin path 側で 1 個、full path enrichment 後でもう 1 個)→ 必ず idempotent な insertion guard を付ける

## 9. 作業ログ欄

| timestamp | action | note |
|---|---|---|
| 2026-05-12 PM JST | ticket 作成 | user 指示により Markdown 新規作成のみ実施。親 ticket 軸 B 採択の narrow 実装子 ticket |

## 10. Regression Memo欄

### current observation

- 親 ticket: `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08` で `apply_rss_pipeline_enrichment` の `class="nomotoke-card-` marker gate を発見済
- RSS auto path の template_key(`postgame_strict` / `score_lite` / `manager` 等)は **非 nomotoke 系**で marker を付けないため早期 return
- 2026-05-12 PM の直近 20 post audit で 5/20 = 25% が該当
- 配管(commit `927ac2c`)はあるが marker 経路が未統合という結論

### guard hypothesis

- guard A: gate 緩和は **idempotent**(既に enrichment 済みの body には再適用しない)
- guard B: thin path への enrichment は既存 `fetch_fan_reactions_from_yahoo` の strict match に乗せ、新しい picker は作らない
- guard C: `💬 ファンの声` H3 一本化を維持(`📣 公式・報道X` を別 H3 として復活させない)
- guard D: full path output diff = 0 を fixture で固定

## 11. 関連 ticket

- 親: `MANUAL-INTAKE-QUALITY-PARITY-2026-05-08`(軸 B 採択待ち、user 判断 5 日間 pending)
- 同時期実装: `H3-STRUCTURE-UNIFY-2026-05-08`(H3 12 set 統一、関連投稿 → ファンの声 merge)
- 別経路: `324-QA-fan-voice-whitelist-rss-source-registration` + `325-QA-fan-voice-whitelist-rss-picker-integration`(fan_voice_pool 経路、本 ticket と直交)
- 同日 dup 事故: `319-QA-fetcher-topic-dedup-and-slot-fill`(本 ticket scope 外)

## 12. user 判断点(明日朝に上げるもの)

- 親 ticket で **軸 B**(装飾 marker gate 緩和)を採択するかの最終 OK
- 採択 OK なら本 ticket(326-QA)を READY 化 → Codex / Claude 実装着手
