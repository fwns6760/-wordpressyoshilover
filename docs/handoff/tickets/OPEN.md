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

## T-010 🟡 旧記事 5件の source_reference_missing（Aクラス残件）

**発見日**: 2026-04-18（T-007 再判定で分離）
**規模拡大・縮小の経緯**:
- 2026-04-18 朝: 当初 2 件（61770 / 61598）として起票
- 2026-04-18 昼: publish 全量監査で 19 件に拡大（🟠 昇格）
- 2026-04-18 夕: 第10便 `a08d875` で **B+C=14件 全解消**、**A=5件のみ残** → 🟡 に戻す

**現在の対象（A=5件）**:
- 61754（lineup） — 本文 HTML 内に source URL 自体がない
- 61596（postgame）
- 61598（postgame）
- 61572（lineup）
- 61600（postgame）

**特徴**: 本文 HTML 内に source URL 文字列が 0件。`extract_source_links()` 改修では回収不能な旧記事形式。

**対応方針候補**（残 Aクラス用）:
- (b) 記事側補填: 手動もしくはバッチで source URL を backfill
  - 各記事の evidence URL を調査して WP 側に追記
  - 5件なら手作業でも耐えられる規模
- (c) 旧記事除外ルール: post date / modified date 閾値で source_reference 検査対象外化
  - yellow を隠すだけで根治しない
  - 5件だけなら無理に入れる必要性は薄い

**推奨**: 5件なら (b) 手動 backfill が素直。ただしよしひろさん判断。

**関連**:
- 第9便調査: `docs/handoff/codex_responses/2026-04-18_09.md`
- 第10便実装: `docs/handoff/codex_responses/2026-04-18_10.md`
- 関連commit: `a08d875`

---

## T-014 🟡 subject: needs_manual_review（2件、T-010 から分離）

**発見日**: 2026-04-18（publish 全量 fact_check）
**対象追加日**: 2026-04-18 夕（第10便 `a08d875` 後の再監査で 61779 が同パターンで露出）
**発見者**: Claude Code（監査役）/ Codex 再監査
**影響**: 単発の yellow。受け入れ品質への影響は限定的

**対象**:

| post_id | status | title |
|---|---|---|
| 62003 | publish | 阿部監督「本当に自己犠牲ができる素晴らしい打者」 ベンチの狙いはどこか |
| 61779 | publish | 6試合連続で3得点以下…貧打にあえぐ巨人打線　大矢明彦氏「我慢の時期かもしれない」 |

**備考**:
- 61779 は当初 T-010 (Bクラス) に属していたが、第10便で `source_reference_missing` 解消後に subject yellow が残って本チケットに合流
- 2件とも `field=subject`, `cause=needs_manual_review`
- T-010 の `source_reference_missing` とは原因も対処も異なる

**調査事項**:
- subject 抽出ロジック（`_extract_subject_label()` 等）が何をもって manual_review に倒したか
- 同様パターンが他記事にないか
- subject の値が空／曖昧／複数候補のどれか

**優先度**: 🟡（2件、systemic ではない）

**Codex向け指示書ドラフト（仮）**:
```
p=62003 と p=61779 を `python3 -m src.acceptance_fact_check --post-id <id> --json` で実行し、
subject finding の詳細（current / expected / message）を取得。
_extract_subject_label() のどの分岐で manual_review 判定になったかを
ソース読み取りで特定し、原因種別（抽出失敗 / 値異常 / ルール側の問題）を切り分け。
結果を codex_responses に記録。修正要否は分析結果で判断。
```

---

## チケット運用ルール

- 新規発見: このファイルに追記、IDは連番（T-007, T-008...）
- 解決時: `RESOLVED.md` へ移動（日付と対応内容付き）
- 優先度は状況に応じて更新してよい
- 各チケットに「Codex向け指示書ドラフト」を用意しておくと、コピペで実装依頼できる
