# Resolved Tickets

解決済みチケットのアーカイブ。

## フォーマット

```markdown
## T-XXX [優先度] タイトル

**発見日**: YYYY-MM-DD
**解決日**: YYYY-MM-DD
**解決者**: よしひろさん / Claude Opus / Codex / Claude Code
**対応内容**: 何をして解決したか
**関連commit**: <hash> （あれば）
```

---

## T-027 🟡 `yoshi-sidebar-rail` auto-inject が届いていない（**sidebar widget area が空が原因、dummy widget 追加で解消可能**）

**発見日**: 2026-04-24
**解決日**: 2026-04-24
**解決者**: Claude Code（front owner、PHP plugin flow 追跡）

**対応内容（root cause 特定）**:
- plugin は `add_action( 'dynamic_sidebar_before', 'yoshilover_063_auto_inject_sidebar_rail', 5, 2 )` で登録済
- `yoshilover_063_is_primary_sidebar_index()` は `'sidebar'` index を whitelist に含む（判定 OK）
- しかし `dynamic_sidebar_before` は **`dynamic_sidebar()` 関数が呼ばれた時のみ** fire する
- SWELL の sidebar.php は `is_active_sidebar('sidebar')` で条件チェック、**widget 0 件 → dynamic_sidebar() 呼ばれない → hook 発火しない**
- 実測: live の `<aside id="sidebar" class="l-sidebar">` 内部は空（widget 0）

**実質的な解消法（user 任意）**:
- WP admin → 外観 → ウィジェット → "sidebar" widget area に **任意の widget を 1 つ追加**（例: カスタム HTML に `[yoshilover_sidebar_rail]` shortcode）
- これで `dynamic_sidebar()` が呼ばれ、rail が auto-inject される
- もしくは plugin 側を `get_sidebar` action 等へ hook 変更するが、テンプレート配置的に副作用ありのため実施せず

**判定**: plugin bug ではなく WP の仕様 + SWELL のテンプレート条件。**widget 追加で即解消**する運用課題。

---

## T-028 🟡 `yoshi-front-card` の `.is-yoshi-front-density` scope（**false positive / 誤発見**）

**発見日**: 2026-04-24
**解決日**: 2026-04-24
**解決者**: Claude Code（front owner、再確認で誤発見と判明）

**対応内容**:
- 初回 curl では `yoshi-front-card` / `is-yoshi-front-density` が DOM 0 件で「未配線」と誤認識
- 再確認で `src/yoshilover-063-frontend.php:1085-1211` の `yoshilover_063_enqueue_front_density_assets()` が home/front_page で inline JS を出力し、`document.querySelectorAll('.p-postList__item').forEach(...)` で **クライアント側 DOM に `is-yoshi-front-density` と `yoshi-front-card__*` を注入**していることを確認
- `window.yoshilover063FrontDensity.cards` payload (15 件) と live HTML の `p-postList__item` link (15 件) が完全一致 → 実ブラウザでは正常動作
- curl は JS 実行しないため DOM 0 に見えるだけ
- `custom.css` の density scope は正しく効いている

**判定**: 誤発見。既存挙動で OK、修正不要。

**教訓**: JS 注入系の block を curl だけで検証するのは不十分。ブラウザでの実測 or JS に依存しない server-side スタイル検証が必要。

---

## T-017 🟠 fact_check メール 07:00 JST demo 落ち（hourly 化 warm 維持で実質解消）

**発見日**: 2026-04-18
**解決日**: 2026-04-19（2 日観察後、Claude Code 判定）
**解決者**: Codex（第16便 scheduler hourly 化） / Claude Code（MB-008 観察）

**対応内容**:
- Scheduler を `0 * * * *` hourly に変更（第16便 `ab349de`, revision `00135-rpc`）
- Cloud Run が常時 warm となり cold start demo 落ちが実質解消

**観察結果**:
- 原インシデント: `2026-04-17T22:00:11 UTC` (= 2026-04-18 07:00 JST) で `fact_check_email_demo` 発火
- 観察期間: 2026-04-18 〜 2026-04-19（48h 以上）
- `2026-04-18T22:00 UTC` (= 2026-04-19 07:00 JST) で `fact_check_email_skipped`（正常 0 件 skip）、demo 落ちなし
- `fact_check_email_demo` イベントは `2026-04-18T00:29 UTC` が最後、以降観測なし

**判定**: 問題再発せず、hourly warm 維持で実質解消を確認。T-017 RESOLVED。

**再発時の処置**（将来の参考）:
- `src/fact_check_notifier.py:358-372` の `_load_gmail_app_password()` に secret empty retry を追加
- `/fact_check_notify` handler 起動時の warm-up secret fetch 追加

**関連 ticket**: MB-008（master_backlog 側の観察チケット、同時 close）

---

## T-024 🟡 監査結果の自動メール通知（`/audit_notify` endpoint + Cloud Scheduler）

**発見日**: 2026-04-18 夜
**解決日**: 2026-04-19（実装は第35便 deploy 時に完了、台帳移動は MB-009 として 2026-04-19 実施）
**解決者**: Codex（第35便実装 + deploy） / Claude Code（台帳移動）

**対応内容**:
- `yoshilover-fetcher` に `GET /audit_notify` 新設（認証 `X-Secret: $RUN_SECRET` 再利用）
- 監査軸 4 + pipeline: `title_body_mismatch` / `thin_body` / `no_opinion` / `no_eyecatch` / `pipeline_error`
- Cloud Scheduler `audit-notify-6x` 作成、`0 2,4,6,8,11,14 * * *` UTC（JST 11/13/15/17/20/23）
- 監査対象: `draft` + `publish`、`window_minutes` 既定 60 内に作成/更新された記事
- `AUDIT_OPINION_USE_LLM=0` 既定（ルール判定）
- 0 件時メール送信 skip、件名 `[yoshilover] 問題 N 件（...）`
- 本便スコープ外: `repetition` 軸は先送り（→ Phase 2 MB-P2-04）

**Prod revision**: `yoshilover-fetcher-00143-luj`（tag `audit-notify-canary` 残存、削除は MB-018）

**関連**: 依頼書 `docs/handoff/codex_requests/2026-04-18_35.md` / 回答 `docs/handoff/codex_responses/2026-04-18_35.md`

---

## T-022 🟠 週末 18-19 時 JST の `/run` scheduler gap（解決）+ T-023 平日 18-19 時 filter（WONTFIX）

**発見日**: 2026-04-18 夜（「18時発火よわい」）
**解決日**: 2026-04-18 夜
**解決者**: Codex（第22-23便調査+修正、第25便 WONTFIX 根拠）

**T-022 対応**:
- 第22便で土曜 18:00-19:59 の scheduler gap（`giants-weekend-eve: 0,30 20-22`）を定量化
- 第23便で `giants-weekend-eve` を `0,30 18-22 * * 0,6` に更新（手動 trigger 200 / drafts_created=3 / rollback 不要）

**T-023 WONTFIX 根拠（第25便）**:
- 7d weekday 18-19 JST は 8 サンプル。pregame 11 prepared / 0 created / pass_rate 0%、postgame/lineup/farm は 100% 通過
- 最多 skip_reason: `not_giants_related=474`, `sns_polluted=188`, `history_duplicate=175`
- 高レバレッジ要因は `pregame_started` だが、2026-04-17 の 18:00 試合開始と同時発火 → 過剰ではない
- policy として正常動作。18-19 時は pregame window と重なる構造的要因

**関連 commit**: `f902b81`（23 response / scheduler fix） / `8c5a276`（25 response / WONTFIX 根拠）

---

## T-019 🟠 post_id=62584 アイキャッチ欠損（調査 + 修正）

**発見日**: 2026-04-18 夜（よしひろさん WP 目視）
**解決日**: 2026-04-18 夜
**解決者**: Codex（第19便調査、第20便修正）

**対応内容**:
- 第19便で 62584 / 62585 / 62587 の 3件が同一経路（X 警告絵文字 SVG URL `abs.twimg.com/emoji/v2/svg/26a0.svg`）で featured_media=0 と特定、social_news/X 由来の局所 systemic 判定
- 第20便で修正 deploy（T-020 と一体）

**関連 commit**: `3fb5381`（調査 response） / `ab4b978`（実装）

---

## T-020 🟠 アイキャッチ emoji SVG 除外拡張 + 画像 fallback + deploy

**発見日**: 2026-04-18 夜（Claude Code、T-019 第19便結果から起票）
**解決日**: 2026-04-18 夜
**解決者**: Codex（第20便実装 + deploy）

**対応内容**:
- `src/wp_client.py` / `src/rss_fetcher.py` の `_get_image_candidate_exclusion_reason()` を `re.search(r"\babs(?:-\d+)?\.twimg\.com/emoji/", low)` に拡張（`abs-0` / `abs` / 将来の `abs-1..` を一網打尽）
- `_upload_featured_media_with_fallback()` 追加、`_article_images` の 2件目以降へ順次 fallback、成功時は `featured_media_fallback_used` INFO
- `featured_media_observation_missing` に `primary_url` / `candidate_count` / `source_type` 追加（空時は出さない）
- unit test 追加: `test_wp_client.py` 2件 + `test_featured_media_fallback.py` 2件 = **383 passed**
- deploy: revision `yoshilover-fetcher-00137-q77`（traffic 100%）
- 62560 副次追跡: `_article_images` が空だった可能性、SVG 系とは別原因、本便では修正対象外

**関連 commit**: `ab4b978`
**新 revision**: `yoshilover-fetcher-00137-q77`

---

## T-004 🟠 今朝の fact_check メールの中身を未確認

**発見日**: 2026-04-18
**解決日**: 2026-04-18（夜、よしひろさん受信確認）
**解決者**: よしひろさん

**対応内容**:
- スマホ Gmail でメール通知の受発信を確認
- T-016 解決で Gmail スレッド化誤検知が判明しており、送信・配送は健全
- 1時間おき hourly メール化 + skip-on-empty（第16便）で運用に組み込み済み

---

## T-006 🟡 Phase 3段階1のメール実受信確認が未完了

**発見日**: 2026-04-18
**解決日**: 2026-04-18（夜、よしひろさん受信確認）
**解決者**: よしひろさん

**対応内容**:
- スマホ Gmail でメール到達を確認
- Scheduler は最終形 `0 * * * *` Asia/Tokyo で稼働中（第16便）
- skip-on-empty + 24h 運用サマリ + 件名 hourly 形式が運用に組み込み済み

---

## T-016 🔴 fact_check メール：ログ上は送信成功なのに Gmail に届かない（Gmail スレッド化誤検知）

**発見日**: 2026-04-18
**解決日**: 2026-04-18（第14便観測性 + 第15便 30min + 第16便 1h + skip）
**解決者**: Codex（実装）/ Claude Code（依頼ドラフト・監査）/ よしひろさん（判断・受信確認）

**経緯**:
- 朝: よしひろさん「Gmail に届いてない」報告 → 配送バグ疑い（🔴 起票）
- 第14便（`01ed7b2`）: `send_email()` に `Message-ID` / `refused_recipients` / `smtp_response` 追加
- 調査結果: SMTP 経路健全（250 OK / refused={}）、**Gmail スレッド化で subject 同一メールがまとまって「1通しか届いてない」ように見えていた**（rfc822msgid 検索で Main tab に実在確認）
- 第15便（`ab49c6c`）: Scheduler `0 7,12,17,22 * * *` → `*/30 * * * *`（30分おき）
- 第16便（`ab349de`, revision `00135-rpc`）: Scheduler `0 * * * *` + `_should_send_email()` で skip-on-empty + 件名 `ヨシラバー MM/DD HH:00 🔴N 🟡M ✅K`

**成果物**:
- コード: `src/fact_check_notifier.py`（`_should_send_email` / 件名刷新 / 観測性維持）
- Scheduler: `0 * * * *` Asia/Tokyo ENABLED
- ログ: `fact_check_email_sent` / `fact_check_email_skipped` に `reason` / `posts_in_last_hour_count` 追加
- 手動 trigger 観測: skip 分岐で `reason=no_change_no_red` 確認

**関連commit**: `01ed7b2`, `ab49c6c`, `ab349de`, `157b4f0`

---

## T-018 🟡 fact-check メールに運用サマリ（作成数・公開数）を追加

**発見日**: 2026-04-18
**解決日**: 2026-04-18（第16便に統合）
**解決者**: Codex（実装）/ Claude Code（依頼ドラフト・監査）/ よしひろさん（機能要望）

**経緯**:
- よしひろさん要望「何通作ったか、将来は何通ポストして公開したか見れるようになる」
- 第16便で email 刷新と同時実装
- Cloud Logging の `rss_fetcher_run_summary` / `rss_fetcher_flow_summary` を集計する helper を `src/fact_check_notifier.py` に追加
- メール本文に📊セクション挿入（drafts_created / created_subtype_counts / skip_duplicate / skip_filter / error_count / x_post_count）
- publish は Phase C 未解放のため `0件（Phase C 未解放）` 表示
- 集計失敗時は `集計取得失敗` 表示で送信は継続

**関連commit**: `ab349de`, `157b4f0`

---

## T-010 🟡 旧記事の source_reference_missing（全クラス対応完了）

**発見日**: 2026-04-18（T-007 再判定で分離）
**解決日**: 2026-04-18（第10便 B+C 解消 + 第13便 A backfill）
**解決者**: Codex（第10便: extractor拡張 / 第13便: 記事 backfill）/ Claude Code（依頼ドラフト）/ よしひろさん（承認）

**経緯**:
- 朝: 2件として起票（61770 / 61598）
- 昼: publish 全量監査で 19 件に拡大（🟠 昇格）
- 夕: 第10便 `a08d875` で **B+C=14件 全解消**（`extract_source_links()` に P1-P4 4パターン追加）
- 夜: 第13便 で **A=5件 全 backfill**（nikkansports / baseballking / sanspo から source URL 特定 → WP 記事末尾に `出典:` ブロック追記）

**第13便 backfill 実績**:
| post_id | source_url | 再監査結果 |
|---|---|---|
| 61754 | nikkansports.com/.../202604120001706.html | yellow（別軸 subject → T-014） |
| 61596 | baseballking.jp/ns/692717/ | green |
| 61598 | baseballking.jp/ns/692712/ | green |
| 61572 | nikkansports.com/.../202604120001188_m.html | green |
| 61600 | baseballking.jp/ns/692702/ | green |

**結論**:
- `source_reference_missing` は publish 全量で 0 件
- publish 全量 red 0 維持、yellow は `subject:needs_manual_review` 4件のみ（T-014 に集約）
- regression なし（62527 / 61981 green 維持）

**関連commit**: `a08d875`（第10便 extractor） / 第13便は WP 記事更新のみ（repo diff なし）
**関連レポート**:
- `docs/handoff/codex_responses/2026-04-18_09.md`（調査）
- `docs/handoff/codex_responses/2026-04-18_10.md`（B+C 実装）
- `docs/handoff/codex_responses/2026-04-18_13.md`（A backfill）

---

## T-015 🟠 T-010 (a) 修正を Cloud Run に反映

**発見日**: 2026-04-18
**解決日**: 2026-04-18（第11便 Codex 実装）
**解決者**: Codex（deploy 実行）/ Claude Code（依頼ドラフト）/ よしひろさん（承認）
**対応内容**:
- Cloud Run `yoshilover-fetcher` に master HEAD (`a08d875`) を source deploy（`git archive` 経由）
- new revision: `yoshilover-fetcher-00133-gvf`
- image digest: `sha256:0915cc1bfbef588ba62c638035cfecd128ddb4c971492418e1e09632480af71d`
- env 変更なし（`RUN_DRAFT_ONLY=1` / `AUTO_TWEET_ENABLED=0` / `PUBLISH_REQUIRE_IMAGE=1` 維持）
- smoke test 通過
- scheduler `giants-weekend-pre` 手動 trigger 成功、new revision `/run`: `draft_only=true`, `error_count=0`
- `severity>=ERROR` on new revision: 0 件

**関連commit**: `396f238`
**関連レポート**: `docs/handoff/codex_responses/2026-04-18_11.md`

---

## T-013 🟠 T-012 修正を Cloud Run に反映

**発見日**: 2026-04-18
**解決日**: 2026-04-18（第8便 Codex 実装）
**解決者**: Codex（deploy 実行）/ Claude Code（依頼ドラフト）/ よしひろさん（承認）
**対応内容**:
- Cloud Run `yoshilover-fetcher` に master HEAD (`d6e19eb`) を source deploy
- new revision: `yoshilover-fetcher-00132-lgv`
- image digest: `sha256:f922ab5b43de664e84d1ca25d5acc8bd905a1aa12c1ba5f24b020c315ff72738`
- env 変更なし（`RUN_DRAFT_ONLY=1` / `AUTO_TWEET_ENABLED=0` / `PUBLISH_REQUIRE_IMAGE=1` 維持）
- smoke test 通過
- scheduler 手動 trigger 成功、new revision `/run`: `draft_only=true`, `error_count=0`
- `severity>=ERROR` on new revision: 0 件

**関連commit**: `8db4fb4`
**関連レポート**: `docs/handoff/codex_responses/2026-04-18_08.md`

---

## T-012 🟡 acceptance_fact_check が歴史参照の「○日○○戦」を opponent と誤認する（false positive）

**発見日**: 2026-04-18
**解決日**: 2026-04-18（第7便 Codex 実装）
**解決者**: Codex（実装・テスト）/ Claude Code（依頼ドラフト）/ よしひろさん（承認）
**対応内容**:
- `src/acceptance_fact_check.py` に `HISTORICAL_GAME_REF_RE` と `TEAM_MATCH_RE` を導入
- `_extract_team_mentions()` を regex finditer による **本文出現順** 抽出に変更（従来は `TEAM_PATTERN` 定義順）
- `_extract_opponent()` で historical reference span 内の team は current opponent 候補から除外
- regression test 1 本追加（`test_extract_opponent_ignores_historical_game_reference`）
- `python3 -m unittest discover -s tests` → **367 passed, OK**
- live 再判定:
  - p=62527 → `result=green`, `findings=[]`
  - p=61981 → `result=green` 維持（regression なし）

**備考**: parser 側修正のみ。Cloud Run への deploy は **T-013** で追跡。

**関連commit**: `d6e19eb`
**関連レポート**: `docs/handoff/codex_responses/2026-04-18_07.md`

---

## T-011 🟠 T-007 修正 + auto_fix/notifier を Cloud Run に反映

**発見日**: 2026-04-18
**解決日**: 2026-04-18（第4便 Step 1）
**解決者**: Codex（deploy 実行）/ Claude Code（依頼ドラフト）/ よしひろさん（承認）
**対応内容**:
- Cloud Run `yoshilover-fetcher` に master HEAD (`ba97edc`) を source deploy
- new revision: `yoshilover-fetcher-00131-mpn`
- env 変更なし（`RUN_DRAFT_ONLY=1` / `AUTO_TWEET_ENABLED=0` / `PUBLISH_REQUIRE_IMAGE=1` 維持）
- smoke test 通過（traffic 100% / latest ready revision が `00131-mpn`）
- scheduler 手動 trigger で `/run` 実行確認: `draft_only=true`, `error_count=0`

**備考**: resolved by `00131-mpn` deploy + smoke test pass

**関連レポート**: `docs/handoff/codex_responses/2026-04-18_04.md`

---

## T-002 🟠 公開中 p=61981 の opponent 誤記（阪神→楽天）

**発見日**: 2026-04-18
**解決日**: 2026-04-18（第5便 Codex 実装）
**解決者**: Codex（実装）/ Claude Code（依頼ドラフト）/ よしひろさん（判断）
**対応内容**:
- `WPClient` 経由で live post `61981` を取得
- title: `巨人阪神戦 試合の流れを分けたポイント` → `巨人楽天戦 試合の流れを分けたポイント`
- summary ブロックの `相手=阪神` → `楽天`
- 本文中の `大ファンだった阪神との初対戦` → `大ファンだった楽天との初対戦`（opponent 誤認箇所のみ）
- `acceptance_fact_check --post-id 61981` → `result=green`, `findings=[]` 確認
- status=publish のまま

**関連レポート**: `docs/handoff/codex_responses/2026-04-18_05.md`

---

## T-008 🟠 post_id 62527 タイトル DeNA → ヤクルト の自動修正判断

**発見日**: 2026-04-18
**解決日**: 2026-04-18（第5便 title / 第6便 body summary）
**解決者**: Codex（実装）/ Claude Code（依頼ドラフト）/ よしひろさん（切り分け判断）
**対応内容**:
- title: `巨人DeNA戦 大城卓三は何を見せたか` → `巨人ヤクルト戦 大城卓三は何を見せたか`（第5便）
- summary ブロック `相手=DeNA` → `ヤクルト`（第6便）
- 本文中の `4日DeNA戦と並んで今季最多8得点` は過去試合への言及なので **5箇所すべて保持**
- 記事側の要件はすべて満たした

**備考**: 記事側修正後も fact_check は `result=red` 継続だが、これは本文中の歴史参照（`4日DeNA戦`）を current opponent と誤認する false positive。記事問題ではないため T-008 は RESOLVED 扱い。fact_check 側は **T-012** で分離追跡。

**関連レポート**: `docs/handoff/codex_responses/2026-04-18_05.md`, `docs/handoff/codex_responses/2026-04-18_06.md`

---

## T-007 🔴 fact_check パーサーバグ — score/venue の fallback が誤値を拾う

**発見日**: 2026-04-18
**解決日**: 2026-04-18
**解決者**: Codex（実装・テスト・再判定）/ Claude Code（ドラフト・監査）
**対応内容**:
- `_source_reference_facts()` から raw text ベースの score/venue 抽出を停止
- `_fetch_npb_schedule_snapshot()` を HTML 構造ベースへ書き換え
- `_fetch_game_reference()` を structured fallback 化、`evidence_by_field` 導入
- `_check_game_facts()` で evidence URL を supply origin 別に分岐
- regression test 3本追加（UUID断片抽出しない / NPB row 正しく読む / evidence URL 分岐）
- 366 passed

**再判定結果**（`docs/fix_logs/2026-04-18_t007_post_fix_recheck.md`）:
- 🔴 → ✅: 62518（完全解消）, 62044, 61886, 61802（T-002 Aクラス疑陽性）
- 🔴 → 🟡: 61770, 61598（T-002 Cクラス、T-010 へ分離）
- 🔴 → 🔴 継続: 62527（T-008、真の title mismatch）, 61981（T-002、真の opponent 誤記）
- ✅ → ✅: 62540（変化なし）

**関連commit**: `ba97edc`

---

## T-002 Aクラス（T-007疑陽性確定分） — 公開中 3件は green 確認済

**発見日**: 2026-04-18
**解決日**: 2026-04-18（T-007 修正後の再判定）
**解決者**: Codex 再判定 / Claude Code 監査
**対応内容**: fact_check パーサー修正により venue fallback 疑陽性が解消、いずれも green。実記事の修正は不要。

- 62044 lineup（venue 甲子園→PayPay は疑陽性）
- 61886 pregame（venue 甲子園→PayPay は疑陽性）
- 61802 lineup（venue 東京ドーム→PayPay は疑陽性）

**備考**: 真のRED扱いだった残り3件は以下に分割:
- 61981（opponent 阪神→楽天、真のRED）→ **T-002（OPEN）**
- 61770, 61598（source_reference_missing、yellow）→ **T-010（OPEN）**

**関連commit**: `ba97edc`

---

## T-003 🟠 ヨシラバーの「現在のdraft件数」が不明

**発見日**: 2026-04-18
**解決日**: 2026-04-18
**解決者**: Codex（実装）/ Claude Code（依頼ドラフト）
**対応内容**:
- 案B（Cloud Logging 候補 post_id + WP 単独 GET）を採用
- `src/draft_inventory_from_logs.py` と `tests/test_draft_inventory_from_logs.py` を追加
- CLI: `python3 -m src.draft_inventory_from_logs --days 7 [--json]`
- T-001 の list API 不全を迂回、single GET で status=draft を確定できる

**確認された現在の draft 件数（2026-04-18時点）**:
- **total: 77 件**
- subtype 別: lineup=29, player=11, farm=11, postgame=9, manager=7, pregame=4, general=3, farm_lineup=2, roster=1
- category 別: 試合速報=42, 選手情報=11, 首脳陣=7, ドラフト・育成=13, コラム=3, 補強・移籍=1

**関連commit**: `10fa214`

---

