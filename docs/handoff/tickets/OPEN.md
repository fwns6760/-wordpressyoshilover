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

## T-014 🟡 subject: needs_manual_review（publish 全量残件）

**発見日**: 2026-04-18（publish 全量 fact_check）
**対象拡張日**: 2026-04-18 夕（第13便 T-010 backfill 後の再監査で 61754/61897/61903 合流）
**発見者**: Claude Code（監査役）/ Codex 再監査
**影響**: 単発の yellow。受け入れ品質への影響は限定的

**対象（publish 側 4件、分類確定）**:

| post_id | subject | evidence_url | 分類 |
|---|---|---|---|
| 61754 | 相手投手 | nikkansports.com/.../202604120001706.html | (Z) source coverage（title 抽出ずれ） |
| 61779 | 阿部監督 | baseballking.jp/ns/692794/ | (Y) 抽出ミス（本文後半の別主体拾う）|
| 61897 | **戸郷翔征投手** | nikkansports.com/.../202604130000570.html | **(X) 肩書差異**（source は「戸郷翔征」） |
| 61903 | 阿部監督 | https://hochi.news/（site root!）| (Z) source coverage 不足 |

**備考**:
- 62003 は第12便調査で **非再現 green** 判明（対象外）
- 61754 は第13便 T-010 backfill 後に subject yellow が顕在化
- いずれも `field=subject`, `cause=needs_manual_review`
- 4件が (X)/(Y)/(Z) に分散 → **systemic ではない、混在**

**第12便 Codex 調査結果（要約）**:
- 62003: 非再現（source_urls=[] で subject check 発火しない、(Z) source coverage 不足の過去痕跡）
- 61779: `_extract_subject_label()` が本文後半の「阿部監督」を拾う、本来の主体は「大矢明彦氏」、(Y) 抽出ミス

**推奨方針**: **WONTFIX 寄せ保留**
- 根治するには `_extract_subject_label()` の狭いルール追加（title 側の `○○氏「...」` を優先）が必要だが、4件のため優先度低
- 同じ傾向が systemic に拡大したら昇格検討

**対象拡張確認タスク**（後日 or 次の余裕便で）:
- 61897 / 61903 の finding 詳細取得（(X)/(Y)/(Z) 分類）
- 4件全部が (Y) 抽出ミスなら狭い extract_subject_label() 修正の費用対効果が上がる

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

## T-017 🟠 fact_check メール 07:00 JST が demo モードに倒れる（password 空）

**発見日**: 2026-04-18
**発見者**: Claude Code（T-016 調査で分離）
**影響**: 朝の fact_check メールが実送信されてない（12:00/17:00/22:00 JST は SMTP 成功している可能性）

**事実**:
- 2026-04-17T22:00:11 UTC = 2026-04-18 07:00 JST の scheduler 実行で `fact_check_email_demo` 発火
- `_load_gmail_app_password()` が空文字を返した（demo モード条件）
- **`fact_check_secret_unavailable` イベントは出てない** → Exception 経路ではない
- 07:00 JST は Cloud Run コールドスタート直後（`STARTUP TCP probe succeeded` 直後 8 秒で `fact_check_notify_started`）
- 9:36 JST 以降の run は同じ secret で SMTP login 成功

**仮説**:
- (A) コールドスタート直後に Secret Manager から base64 decode した結果が空文字で返る競合
- (B) `GMAIL_APP_PASSWORD` env 変数が 07:00 run 時だけ何らかの理由で空（なさそう）
- (C) `_fetch_secret_from_secret_manager` が rare path で empty body を返し、`.strip()` で空文字化

**コード該当**: `src/fact_check_notifier.py:358-372` の `_load_gmail_app_password()`
- 現状: Exception 時のみ `fact_check_secret_unavailable` ログ。成功だが空のケースは無言で demo へ

**優先度**: 🟠（1日4便のうち1便が届かない → 実質 75% 稼働）

**Codex向け指示書ドラフト（仮）**:
```
src/fact_check_notifier.py:358-372 の _load_gmail_app_password() を修正:
1. secret fetch 成功だが中身が空文字のケースを明示ログ化:
   fact_check_secret_empty(secret_name, length, direct_env_used) を追加
2. empty 返り時に 1回だけ retry（GCP side の transient 対策）
3. 07:00 JST scheduler が Cloud Run コールドスタートなら、起動直後 warm-up に
   secret fetch を入れるか、or /fact_check_notify ハンドラ内で明示的に retry

deploy 後、翌 07:00 JST run を観測して demo に倒れないことを確認（自然発火待ち）。
T-016 の第14便で SMTP 経路が健全と判明してる前提で本便に入る。
```

**2026-04-18 夜追記（T-016 第16便後）**:
- Scheduler が `0 * * * *`（毎時発火）に変更された（第16便 `ab349de`, revision `00135-rpc`）
- 1時間おき稼働で Cloud Run が常時 warm → cold start demo 落ちが実質解消する見込み
- 2〜3 日観察して、07:00 JST run が `fact_check_email_sent` or `fact_check_email_skipped`（`reason=no_change_no_red`）に倒れれば RESOLVED
- もし依然 `fact_check_email_demo` が出るようなら上記コード修正（retry + warm-up）を第17便で実施

---

## チケット運用ルール

- 新規発見: このファイルに追記、IDは連番（T-007, T-008...）
- 解決時: `RESOLVED.md` へ移動（日付と対応内容付き）
- 優先度は状況に応じて更新してよい
- 各チケットに「Codex向け指示書ドラフト」を用意しておくと、コピペで実装依頼できる
