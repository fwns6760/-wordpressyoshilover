# Open Tickets

未解決のチケット一覧。チャットが消えても repo に残る監査記録。

**凡例:**
- 🔴 critical（本番品質に影響）
- 🟠 high（運用に影響）
- 🟡 medium（早めに解決したい）
- 🟢 low（いつでも）

---

## T-001 🔴 WP REST APIのstatus=draftフィルタが機能していない

**発見日**: 2026-04-18
**発見者**: Claude Code（監査役）
**影響**: acceptance_fact_checkが意図と違う対象（publish記事）を監査している

**事実**:
- `curl .../posts?status=draft&per_page=100&context=edit` で返る36件は全て `status=publish`
- `curl .../posts?status=publish` でも同じ36件
- `curl .../posts?status=any` でも同じ36件
- 単独GET（例: `posts/62483`）では正しく `status=draft` が返る
- つまり list API ではdraftが返らない（フィルタ不全 or WP側のカスタム挙動）

**根本原因**: 未特定（WPのhook/plugin/filterの可能性）

**暫定対応**:
- 個別post_idでの確認は信頼できる
- 件数カウントはSQLやWP管理画面を別途使う必要あり

**Codex向け指示書（原因調査）**:
```
WPのfunctions.phpやMU-plugin等で `pre_get_posts` / `rest_post_query` フィルタが
status=draft を除外していないか調査。plugin一覧も確認。
調査のみ。変更はしない。
```

---

## T-002 🔴 公開中の6記事にRED判定（事実誤記）

**発見日**: 2026-04-18
**発見者**: Claude Code（監査役）
**影響**: 公開済み記事に事実誤認が残っている（読者が誤情報に触れる状態）

**対象（全て WP_status=publish、HTTP 200で閲覧可能）**:

| post_id | subtype | 問題 |
|---------|---------|------|
| 62044 | lineup | venue: 甲子園 → 正: PayPay |
| 61981 | postgame | opponent: **阪神 → 正: 楽天**（重大） + venue: 甲子園→PayPay |
| 61886 | pregame | venue: 甲子園 → 正: PayPay |
| 61802 | lineup | venue: 東京ドーム → 正: PayPay |
| 61770 | lineup | venue: 東京ドーム → 正: PayPay + 参照元リンクなし |
| 61598 | postgame | venue: 東京ドーム → 正: PayPay + 参照元リンクなし |

**注**: これら6記事は日付が 2026-04-14 またはそれ以前。Phase A/B/B.5実装前に
生成/公開された可能性が高い（= 事故ではなく、旧ロジックの産物）。

**判断が必要**:
- 即draft戻し（修正前の非公開化）
- 自動fix実行（fact_checkの `auto_fix` フィールドに提案あり）
- そのまま放置（旧記事の一部として扱う）

**Codex向け指示書ドラフト（修正したい場合）**:
```
対象6記事に対して `python3 -m src.acceptance_auto_fix --post-id <id>` を実行し
auto_fixの提案を適用する。その後 fact_check で green になることを確認。
status=publish のまま修正する（draftに戻さない）。
テスト: pytest 全PASS確認。
```

---

## T-003 🟠 ヨシラバーの「現在のdraft件数」が不明

**発見日**: 2026-04-18
**発見者**: Claude Code（監査役）
**影響**: 受け入れ試験の計画が立てられない

**事実**:
- T-001でlist APIがdraft を返さない
- 個別GETで少なくとも 62483/62486/62489/62493 の4件はdraft
- 総draft数は不明（36ではない、それは全publish件数）

**確認手段の候補**:
- WP管理画面にログインして件数を見る
- Cloud Logging の `rss_fetcher_run_summary` の `draft_created` 累計を読む
- xserverのphpMyAdmin/SQLで `wp_posts WHERE post_status='draft'` をcount

**Codex向け指示書ドラフト**:
```
Cloud Logging から直近7日間の `draft_created` / `draft_updated` を集計し、
現在のdraft累計を推定。または rss_fetcher コードに「現在のdraft件数をログ出力」の
一回限りエンドポイントを追加して結果を取得。
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

**Yoshihiro側で確認が必要**: スマホのGmailで本日朝のメール本文の🔴セクションを見る

---

## T-005 🟡 `11_codex_prompt_library.md` の内容は再構築（原文保存ではない）

**発見日**: 2026-04-18
**発見者**: Claude Code（監査役、自己申告）
**影響**: 小。テンプレとしては機能するが「過去の実物」ではない

**対応**: Opus側のchat履歴に実際のプロンプトが残っていれば、後日差し替える

---

## T-006 🟡 Phase 3段階1のメール実受信確認が未完了

**発見日**: 2026-04-18
**発見者**: Yoshihiro + Claude Code
**影響**: 小。ログレベルでは送信成功を確認済み

**対応**: Yoshihiro側でスマホのGmailを確認（朝のメールを見る）

---

## チケット運用ルール

- 新規発見: このファイルに追記、IDは連番（T-007, T-008...）
- 解決時: `RESOLVED.md` へ移動（日付と対応内容付き）
- 優先度は状況に応じて更新してよい
- 各チケットに「Codex向け指示書ドラフト」を用意しておくと、コピペで実装依頼できる
