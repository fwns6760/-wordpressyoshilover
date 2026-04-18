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

## T-010 🟠 publish 記事の source_reference_missing が系統的に発生（19件／過半）

**発見日**: 2026-04-18（T-007 再判定で分離）
**規模拡大確認日**: 2026-04-18（publish 全量 fact_check で判明）
**発見者**: Claude Code（監査役）
**影響**: publish 記事 36 件中 **19 件** が `source_reference_missing` yellow。個別問題ではなく母集団全体に効く系統的問題。受け入れ品質指標の信頼性に影響

**実数**（2026-04-18 時点、`acceptance_fact_check --status publish --since all` 実行）:

- publish total: **36件**
- green: 16件
- yellow: **20件**
  - うち `source_reference_missing`: **19件**
  - うち `subject: needs_manual_review`: 1件（**T-014** で分離）
- red: 0件

**対象 post_id（19件全量）**:
- 61947 / 61946 / 61939 / 61816 / 61812 / 61799 / 61779 / 61776 / 61773 / 61770 / 61754 / 61596 / 61572 / 61598 / 61600 / 61576 / 61574 / 61556 / 61554

**サンプル挙動**（p=61947）:
```json
{
  "source_urls": [],
  "findings": [{
    "severity": "yellow",
    "field": "source_reference",
    "message": "参照元リンクが本文に見つからない",
    "cause": "source_reference_missing",
    "proposal": "source_url を再確認し、参照元ブロックを補う",
    "fix_type": "manual_review"
  }]
}
```
`source_urls=[]` → `extract_source_links()` で参照元URLが**1本も検出できていない**。

**原因仮説**:
1. 旧記事フォーマットで source reference block（「参考: URL」「出典: …」等の構造化ブロック）が未導入
2. 本文中に URL 文字列として埋まっているが、`extract_source_links()` の抽出パターンが追随していない
3. 記事生成時点で source を埋め込んでいなかった世代（古い draft からの publish）

**対応方針候補**:
- (a) `extract_source_links()` の抽出パターン拡張（本文 URL / footer リンクも拾う）
- (b) 記事側を後追いで改修（source block を手動 or バッチで補填）
- (c) 「古い記事は source_reference 検査対象外」の除外ルール（yellow を抑制）
- 優先度: まず (a) の抽出ロジック拡張を試す。それでも拾えない記事があれば (b)／(c) を検討

**対応の切り分け**:
- fact_check 側（パーサー）問題なら Codex 修正 → deploy
- 記事側（コンテンツ）問題なら acceptance_auto_fix 拡張 or 手動補填

**優先度**: 🟠（red ではないが publish 半数以上に効いており、受け入れ品質指標の母集団に影響）

**Codex向け指示書ドラフト（仮）**:
```
src/draft_audit.py の extract_source_links() と
src/acceptance_fact_check.py の _source_reference_facts() を見直す。
以下のいずれかで source URL を検出できるようにする:
- 本文末尾の「参考:」「出典:」「source:」等のラベル付きブロック
- 記事本文中の裸の URL（nikkansports.com / sponichi.co.jp / hochi.news 等の既知ドメイン）
- 画像キャプション内のリンク
修正後、p=61947 を含む T-010 対象 19 件で
`extract_source_links()` が非空を返すようになった件数を確認。
```

---

## T-014 🟡 p=62003 の subject: needs_manual_review（T-010 から分離）

**発見日**: 2026-04-18（publish 全量 fact_check）
**発見者**: Claude Code（監査役）
**影響**: 単発の yellow。受け入れ品質への影響は限定的

**対象**:
- post_id: 62003
- title: 阿部監督「本当に自己犠牲ができる素晴らしい打者」 ベンチの狙いはどこか
- status: publish

**finding**:
- `field=subject`, `cause=needs_manual_review`
- T-010 の `source_reference_missing` とは原因も対処も異なるため分離

**調査事項**:
- subject 抽出ロジック（`_extract_subject_label()` 等）が何をもって manual_review に倒したか
- 同様パターンが他記事にないか（本件は 62003 のみ）
- subject の値が空／曖昧／複数候補のどれか

**優先度**: 🟡（単発、systemic ではない）

**Codex向け指示書ドラフト（仮）**:
```
p=62003 を `python3 -m src.acceptance_fact_check --post-id 62003 --json` で実行し、
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
