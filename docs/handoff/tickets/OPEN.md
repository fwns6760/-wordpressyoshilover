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

**調査結果**（第9便 `codex_responses/2026-04-18_09.md`）:

19件の分類結果（A=5 / B=12 / C=2）:

| 分類 | 件数 | 意味 | 代表 post_id |
|---|---:|---|---|
| A | 5 | 旧記事形式。本文内に source URL 自体がない | 61754 / 61596 / 61598 / 61572 / 61600 |
| B | 12 | URL はあるが source block 不在 or unsupported な裸リンク形式 | 61939 / 61816 / 61799 / 61576 / 61574 / 61556 / 61554 / 61773 / 61776 / 61812 / 61770 / 61779 |
| C | 2 | 構造化参照ブロックはあるが extractor 未対応 | 61947 / 61946 |

**主因**: 「source が無い記事」ではなく「source が本文にあるのに extractor が見えていない記事」が多い（B+C=14/19）。**parser coverage 問題**として整理するのが妥当。

**抽出漏れパターン**:
- `【引用元】` 見出し + 次段落アンカー（C）
- `引用元:` / `出典:` / `参考:` ラベル付き段落（B）
- 本文末尾の小文字 footer リンク（B）
- `[[1]](url)` 形式（B）

**対応方針（確定）**:
- **第一優先: (a) `extract_source_links()` の抽出パターン拡張** → **19件中 14件を即時カバー見込み**
- 残る A=5 は (a) 実装後に再監査し、(b) 記事側補填 / (c) 旧記事例外ルール のいずれかで処理

**次便 (第10便) で依頼する実装スコープ**:
- 対象: `src/draft_audit.py` の `extract_source_links()`
- 追加パターン 4種（上記）+ `tests/` にregression テスト
- 受け入れ: B+C=14件のうち 12件以上で `source_reference_missing` 解消、A=5 はそのまま残ってよい
- deploy は本便ではやらない（次々便で別途）

**優先度**: 🟠（red ではないが publish 半数以上に効いており、受け入れ品質指標の母集団に影響）

**関連レポート**: `docs/handoff/codex_responses/2026-04-18_09.md`

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
