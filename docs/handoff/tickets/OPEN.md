# Open Tickets

未解決のチケット一覧。チャットが消えても repo に残る監査記録。

**凡例:**
- 🔴 critical（本番品質に影響）
- 🟠 high（運用に影響）
- 🟡 medium（早めに解決したい）
- 🟢 low（いつでも）

---

## T-001 🟠 WP REST APIのstatus=draftフィルタが機能していない（真犯人判明・修正待ち）

**発見日**: 2026-04-18
**原因特定日**: 2026-04-18（Codex 調査結果）
**発見者**: Claude Code（監査役）
**影響**: acceptance_fact_checkがlistAPI経由でdraftを扱えない（T-003で代替手段確立済）

**真犯人**: `src/yoshilover-exclude-cat.php` の `pre_get_posts` フック
- `is_admin()` でスキップしているが REST リクエストでは admin 判定にならない
- 結果として `$query->set('post_status', 'publish')` が REST collection query にも効き、
  `?status=draft` / `?status=any` も publish に書き換わる
- 単独 GET（`/posts/{id}`）は collection query を経由しないので影響なし

**暫定対応**: T-003 の `src/draft_inventory_from_logs.py` で代替可能（優先度🟠に降格）

**修正方針**:
1. `REST_REQUEST` 中はこの plugin を効かせない（`if (defined('REST_REQUEST') && REST_REQUEST) return;`）
2. または true front-end query のみに条件を絞る
3. `post_status=publish` の強制はテーマ用一覧 query のみに限定

**Codex向け指示書ドラフト（修正実装）**:
```
src/yoshilover-exclude-cat.php:16-44 の pre_get_posts フック先頭で
`if (defined('REST_REQUEST') && REST_REQUEST) return;` を追加し、
REST collection query からこのプラグインを除外する。
修正後、WP に差し替えて以下を確認:
- curl .../posts?status=draft&context=edit でdraftのみが返ること
- curl .../posts?status=publish でpublishのみが返ること
- テーマ側のフロント一覧で除外カテゴリ動作が保たれていること
deployはよしひろさん承認後。
```

---

## T-002 🟡 公開中の6記事RED判定 — **疑陽性の可能性（T-007パーサーバグ由来）**

**発見日**: 2026-04-18
**再評価日**: 2026-04-18（T-007 調査結果を受けて降格）
**発見者**: Claude Code（監査役）
**影響**: 判定根拠が壊れている可能性があり、現状の判定では修正判断できない

**対象（全て WP_status=publish、HTTP 200で閲覧可能）**:

| post_id | subtype | 当初の「問題」 | 信頼性 |
|---------|---------|----------|--------|
| 62044 | lineup | venue: 甲子園 → 正: PayPay | ⚠️ venue fallback疑陽性の可能性 |
| 61981 | postgame | opponent: 阪神 → 正: 楽天 + venue | ⚠️ venue は疑陽性、opponent は未検証 |
| 61886 | pregame | venue: 甲子園 → 正: PayPay | ⚠️ venue fallback疑陽性の可能性 |
| 61802 | lineup | venue: 東京ドーム → 正: PayPay | ⚠️ venue fallback疑陽性の可能性 |
| 61770 | lineup | venue + 参照元リンクなし | ⚠️ venue fallback疑陽性の可能性 |
| 61598 | postgame | venue + 参照元リンクなし | ⚠️ Codex spot check で venue fallback 異常再現 |

**重要な更新（T-007報告より）**:
- `_fetch_npb_schedule_snapshot()` の date block 切り出しミスで venue が誤って `PayPay` に化ける
- 61981 と 61598 は Codex の spot check で venue fallback の異常を再確認
- つまり **T-002 の venue 判定は信用できない**（パーサーバグの疑陽性）
- 61981 の opponent 阪神→楽天は別経路なので別途要確認

**やるべきこと**: **T-007 のパーサー修正完了後、6件を再 fact_check**
- もし全てgreenに転じたら T-002 は RESOLVED へ
- もし本当にREDが残ったら、その時点で修正判断
- 疑陽性のまま修正を走らせると、正しい記事を壊す危険あり

**Codex向け指示書ドラフト（T-007 修正完了後に再実行）**:
```
以下6件を acceptance_fact_check で再判定:
62044 / 61981 / 61886 / 61802 / 61770 / 61598
結果を docs/fix_logs/{date}_t002_recheck.md に出力。
修正は行わず判定のみ。
```

---

## T-004 🟠 今朝のfact checkメールの中身を未確認

**発見日**: 2026-04-18
**発見者**: Claude Code（監査役）
**影響**: T-002のRED 6件がメールで通知されたかどうか不明

**事実**:
- `fact_check_email_sent` ログは 2026-04-18T00:36:57 に出ている
- T-002の6REDは過去（~4-14）のpublish記事。今朝のメールはこの6件を含むか？
- 送信先: `fwns6760@gmail.com`

**よしひろさん側で確認が必要**: スマホのGmailで本日朝のメール本文の🔴セクションを見る

---

## T-005 🟡 `11_codex_prompt_library.md` の内容は再構築（原文保存ではない）

**発見日**: 2026-04-18
**発見者**: Claude Code（監査役、自己申告）
**影響**: 小。テンプレとしては機能するが「過去の実物」ではない

**対応**: Opus側のchat履歴に実際のプロンプトが残っていれば、後日差し替える

---

## T-006 🟡 Phase 3段階1のメール実受信確認が未完了

**発見日**: 2026-04-18
**発見者**: よしひろさん + Claude Code
**影響**: 小。ログレベルでは送信成功を確認済み

**対応**: よしひろさん側でスマホのGmailを確認（朝のメールを見る）

**2026-04-18 午前追記（Codex報告経由）**:
- Scheduler は 7:00 / 12:00 / 17:00 / 22:00 JST の1日4回に変更済
- `fact_check_email_sent` ログ確認済、実メール送信まで成功
- メール本文に「自動修正候補 / 差し戻し推奨 / 手動確認必要」の3セクション追加済

---

## T-007 🔴 fact_check パーサーバグ — score/venue の fallback が誤値を拾う

**発見日**: 2026-04-18
**原因特定日**: 2026-04-18（Codex 調査結果）
**発見者**: Claude Code（監査役）→ Codex 調査
**影響**: **本件が直らない限り fact_check / auto_fix / 受け入れ試験の結果は信用できない**

**真犯人**（Codex報告 `docs/handoff/codex_responses/2026-04-18.md`）:

1. `src/acceptance_fact_check.py:311-328` `_source_reference_facts()`
   - source URL の title/description/text を連結し、その raw 全文に `_extract_score()` をかけている
2. `_extract_score()` のパターンが `(\d{1,2})[-－–](\d{1,2})` と素朴すぎる
   - p=62518 の source URL に含まれる **UUID 断片 `4725-97a1` から `25-97` を誤抽出**
3. `src/acceptance_fact_check.py:356-375` `_fetch_npb_schedule_snapshot()`
   - 月間日程ページを文字数切り出しで処理しており、ズレると別試合の venue を拾う
4. `src/acceptance_fact_check.py:518-570` `_check_game_facts()`
   - `reference.get("score") or source_facts.get("score")` で、live reference が空だと
     誤抽出値が採用される
5. evidence URL は `reference["evidence_urls"][0]` 固定
   - 実際は source URL 由来の誤値でもレポート上は NPB / Yahoo game ref のせいに見える

**影響範囲（判明分）**:
- **直接表面化**: 62518（score=25-97, venue=PayPay の両方）
- **score 同種誤抽出（潜在）**: 62527, 62540 — いずれも source facts 側 score=19-4
- **venue fallback 異常（疑陽性）**: T-002 の6件（62044/61981/61886/61802/61770/61598）
  - Codex spot check で 61981, 61598 は再現確認済
- **受け入れ試験全体**: 現在の fact_check 結果は全体として信用できない

**修正方針**（Codex提案、未実装）:

1. `source_facts` からの score 抽出を停止 — raw page text 全体への `_extract_score()` 禁止、
   structured source のみ許可
2. `_fetch_npb_schedule_snapshot()` の切り出しを文字数ベースから HTML 構造ベースに変更
3. `_check_game_facts()` で expected 値の供給元に応じて evidence URL を分ける
   - reference 由来 → game reference URL
   - source_facts 由来 → source URL
4. 62518 を regression test 化

**Codex向け指示書ドラフト（修正実装）**:
```
docs/handoff/codex_responses/2026-04-18.md の T-007 修正方針1〜4を実装:
- _source_reference_facts() から score/venue の raw text 抽出経路を削除
  （structured source のみ許可）
- _fetch_npb_schedule_snapshot() を HTML 構造ベースの切り出しに書き換え
- _check_game_facts() で evidence URL を supply origin ごとに分岐
- regression test 追加: 62518 ケース + UUID 断片からの score 抽出が起きないこと

修正後の検証:
1. pytest 全 PASS (現状 362 tests)
2. 以下 post_id を acceptance_fact_check で再判定し結果を
   docs/fix_logs/{date}_t007_post_fix_recheck.md に出力:
   62518 / 62527 / 62540 / 62044 / 61981 / 61886 / 61802 / 61770 / 61598
3. deploy/env変更は本依頼では実施しない（よしひろさん承認後）
```

---

## T-008 🟡 post_id 62527 タイトル DeNA → ヤクルト の自動修正判断

**発見日**: 2026-04-18
**発見者**: Codex の acceptance_auto_fix dry-run
**影響**: 公開中記事のタイトルに誤対戦相手。読者に誤情報

**事実**（`docs/fix_logs/2026-04-18.md` より）:
- p=62527 postgame「巨人DeNA戦 大城卓三は何を見せたか」
- 実試合は巨人 vs ヤクルト
- auto_fix 候補: WP title の `DeNA` → `ヤクルト` 置換（1箇所一致、whitelist 通過、楽観ロックあり）

**よしひろさんの判断が必要**: 自動修正を実行する / 手動で確認してから実行 / draft戻し

**Codex向け指示書ドラフト（自動修正実行）**:
```
p=62527 に対して acceptance_auto_fix を dry-run ではなく本番モードで実行し、
title の `DeNA` → `ヤクルト` 置換を適用。適用後に fact_check を再実行して
title_rewrite_mismatch が解消したことを確認。status は publish のまま。
```

---

## チケット運用ルール

- 新規発見: このファイルに追記、IDは連番（T-007, T-008...）
- 解決時: `RESOLVED.md` へ移動（日付と対応内容付き）
- 優先度は状況に応じて更新してよい
- 各チケットに「Codex向け指示書ドラフト」を用意しておくと、コピペで実装依頼できる
