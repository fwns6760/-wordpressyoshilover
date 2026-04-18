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

**2026-04-18 午前追記（Codex報告経由）**:
- Scheduler は 7:00 / 12:00 / 17:00 / 22:00 JST の1日4回に変更済
- `fact_check_email_sent` ログ確認済、実メール送信まで成功
- メール本文に「自動修正候補 / 差し戻し推奨 / 手動確認必要」の3セクション追加済

---

## T-007 🔴 post_id 62518 で score が `25-97` という異常値

**発見日**: 2026-04-18（Codex の acceptance_auto_fix dry-run 出力から）
**発見者**: Claude Code（監査役）
**影響**: 根拠データ生成ロジック（rewrite元）のバグ可能性。放置すると再発する

**事実**（`docs/fix_logs/2026-04-18.md` より）:
- p=62518 postgame「巨人8-2 勝利の分岐点はどこだったか」
- fact_check の findings: `score` / `game_fact_alignment_failure`
  - 記事側: `8-2`（正しい）
  - 根拠側: `25-97`（明らかに異常）
- auto_fix は「根拠側に合わせて 8-2 → 25-97 に置換」という提案を出している
- Codex は score を whitelist 外にして自動修正から除外（正しい判断）

**疑い**:
- スコア抽出パーサーが誤った要素を拾っている（ページビュー数？打率？）
- または別試合の数値が混入している
- 同じ根拠データが他記事の判定にも使われている可能性

**Codex向け指示書ドラフト（調査）**:
```
p=62518 の fact_check が参照している根拠データ（ref / source）を特定し、
score に `25-97` が入った理由を調査。スコア抽出ロジックを点検し、
他の post_id でも同種の異常値が出ていないか grep で確認。
調査のみ、修正は別チケット。
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

**Yoshihiroの判断が必要**: 自動修正を実行する / 手動で確認してから実行 / draft戻し

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
