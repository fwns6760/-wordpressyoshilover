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

## T-010 🟡 公開中 2件の source_reference_missing（yellow）

**発見日**: 2026-04-18（T-007 再判定で分離）
**発見者**: Claude Code（監査役）
**影響**: 小。venue 疑陽性は解消したが、参照元リンクが欠落しており yellow 扱い

**対象**:

| post_id | subtype | title |
|---------|---------|------|
| 61770 | lineup | 【巨人】「レギュラーは決まってません。結果残せば使います」阿部監督… |
| 61598 | postgame | 解説陣が巨人・坂本勇人にエール「背中でチームを引っ張って」 |

**背景**: T-002 で当初 RED とされていた6件のうち、T-007 修正後に yellow に下がった2件。
事実誤記ではなく、記事内の参照元（source）リンクが欠落している問題。

**対応の選択肢**:
- 放置（yellow許容）
- 参照元を手動で埋める
- 該当記事を draft 戻し

**優先度**: 低。受け入れ試験の阻害にはならない。

---

## T-012 🟡 acceptance_fact_check が歴史参照の「○日○○戦」を opponent と誤認する（false positive）

**発見日**: 2026-04-18
**発見経緯**: p=62527 修正時（第6便 Codex 報告）に顕在化
**発見者**: Codex / Claude Code 監査
**影響**: 記事側の修正が正しくても red 判定が継続することがある。受け入れ試験の信頼性に影響

**現象**:
- 現状の `acceptance_fact_check` は、本文中の過去試合参照（例: `4日DeNA戦`）を current opponent と誤認して red 判定することがある。
- 記事修正ではなく fact_check 判定ロジック側の改善対象。

**実例**:
- p=62527 でヤクルト戦の記事に残る `4日DeNA戦と並んで今季最多8得点` の記述（5箇所）を opponent=DeNA として拾い、summary 側修正後も red 継続
- `docs/handoff/codex_responses/2026-04-18_06.md` 参照

**修正方針（案）**:
- 本文中の `○日○○戦` / `○月○日○○戦` のような過去試合参照パターンを opponent 抽出から除外
- または、summary ブロック / title 側の opponent 表記を優先してマッチングし、本文は補助扱いにする
- T-007 と似た構造のパーサー側補正

**Codex向け指示書ドラフト**:
```
src/acceptance_fact_check.py の opponent 抽出ロジックを見直し、
本文中の「○日○○戦」のような過去試合参照を current opponent から除外する。
- 正規表現例: (\d{1,2}日)(DeNA|ヤクルト|阪神|広島|中日|巨人|ロッテ|楽天|...)戦
- 既存の opponent 抽出に対して「先行する日付トークン」を持つものは skip
- 修正後、p=62527（draft）で green になること、および
  regression として「歴史参照を含む記事」のテストを1本追加する。
```

---

## T-011 🟠 T-007 修正 + auto_fix/notifier を Cloud Run に反映（deploy 未実施）

**発見日**: 2026-04-18
**発見者**: Claude Code（監査役）
**影響**: **Cloud Run は依然として旧 fact_check パーサー**。次の Scheduler 発火で新記事が誤判定される

**未反映のcommit**:
- `ba97edc` fix: harden fact check game reference parsing（T-007）
- `957f458` feat: add acceptance auto-fix dry run workflow
- `10fa214` T-003 draft_inventory_from_logs + 他

**必要な作業**:
- Cloud Build or `gcloud run deploy` で最新 master を Cloud Run に反映
- env変更は不要（`RUN_DRAFT_ONLY=1` / `ENABLE_PUBLISH_FOR_*=0` 維持）
- 反映後、次の Scheduler 発火（7:00/12:00/17:00/22:00 JST いずれか）で新パーサーの動作を確認

**よしひろさんの承認が必要**: deploy 実行の是非

**Codex向け指示書ドラフト**:
```
Cloud Run `yoshilover-fetcher` に最新 master (ba97edc) を deploy。
env変数は現状維持（RUN_DRAFT_ONLY=1, ENABLE_PUBLISH_FOR_*=0）。
deploy 後に以下を確認:
1. revision が進んでいる（00131 以降）
2. smoke test: scheduler の手動 trigger で新 revision が発火、
   fact_check_email_sent ログが出る
3. 次の scheduled 発火メール本文が正常
差し戻しが出たら revision を 00130-nxg に戻す（rollback 手順を
docs/phase_c_runbook.md 参照）。
```

---

## チケット運用ルール

- 新規発見: このファイルに追記、IDは連番（T-007, T-008...）
- 解決時: `RESOLVED.md` へ移動（日付と対応内容付き）
- 優先度は状況に応じて更新してよい
- 各チケットに「Codex向け指示書ドラフト」を用意しておくと、コピペで実装依頼できる
