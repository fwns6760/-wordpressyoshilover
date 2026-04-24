# Open Tickets

未解決のチケット一覧。チャットが消えても repo に残る監査記録。

**凡例:**
- 🔴 critical（本番品質に影響）
- 🟠 high（運用に影響）
- 🟡 medium（早めに解決したい）
- 🟢 low（いつでも）

---

## T-001 🟠 WP REST APIのstatus=draftフィルタが機能していない（コード修正完了・本番未適用）

**発見日**: 2026-04-18
**原因特定日**: 2026-04-18（Codex 調査結果）
**修正完了日**: 2026-04-18（第17便、`f09cffc`）
**発見者**: Claude Code（監査役）
**影響**: acceptance_fact_checkがlistAPI経由でdraftを扱えない（T-003で代替手段確立済）

**真犯人**: `src/yoshilover-exclude-cat.php` の `pre_get_posts` フック
- `is_admin()` でスキップしているが REST リクエストでは admin 判定にならない
- 結果として `$query->set('post_status', 'publish')` が REST collection query にも効き、
  `?status=draft` / `?status=any` も publish に書き換わる
- 単独 GET（`/posts/{id}`）は collection query を経由しないので影響なし

**暫定対応**: T-003 の `src/draft_inventory_from_logs.py` で代替可能

**第17便（2026-04-18 夜）コード修正完了**:
- `src/yoshilover-exclude-cat.php` の `pre_get_posts` 先頭 + `posts_where` 先頭に REST ガード追加
  ```php
  if ( defined( 'REST_REQUEST' ) && REST_REQUEST ) { return; }
  ```
- `php -l` OK / `git diff` 2箇所追加のみ / 379 tests passed
- commit: `f09cffc fix(exclude-cat): skip REST requests so ?status=draft works`
- response doc: `docs/handoff/codex_responses/2026-04-18_17.md`（`36785cf`）
- WP (Xserver) への反映は未実施

**残タスク（第18便想定）**:
1. 修正済み `src/yoshilover-exclude-cat.php` を WP 側へ差し替え
2. 実機確認: `curl .../wp-json/wp/v2/posts?status=draft&context=edit` で draft が返ること
3. `curl .../posts?status=publish` で publish のみが返ること
4. テーマ側フロント一覧で除外カテゴリ動作が保たれていること
5. 実機確認 OK なら T-001 → RESOLVED

**ブロッカー**: Xserver SSH 接続情報、または WP admin での plugin 差し替え権限

---

## T-005 🟡 `11_codex_prompt_library.md` の内容は再構築（原文保存ではない）

**発見日**: 2026-04-18
**発見者**: Claude Code（監査役、自己申告）
**影響**: 小。テンプレとしては機能するが「過去の実物」ではない

**対応**: Opus側のchat履歴に実際のプロンプトが残っていれば、後日差し替える

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

## T-021 🟡 記事本文の「薄さ」対策（第2弾 canary 検証中）

**発見日**: 2026-04-18 夜
**発見者**: よしひろさん（「このサイトだから書けること × AI だから」）
**影響**: 他サイト要約との差別化・読み応え

**第21便 調査結論**（`codex_responses/2026-04-18_21.md`）:
- 本文コア実文字数 290〜546（HTML 装飾で見た目だけ厚い）
- 主因: min_chars 低い (160/220) + source-only で差別化材料禁止
- 推奨方針: 過去記事への内部リンク自動挿入（「ヨシラバーだから書ける」軸）

---

### 第1弾: 過去記事リンク自動挿入 ✅ 解消扱い（2026-04-18）

**実装**: 第27便 `9ae1169`（src/rss_fetcher.py + tests、389 passed）
**deploy**: 第28便 `ba81438` → revision `yoshilover-fetcher-00138-mqn`、traffic 100%

**第28便 smoke 結果**:
- 手動 trigger 200、drafts_created=2 / publish_count=0 / error_count=0
- draft 62600 に `<div class="yoshilover-related-posts">` と `【関連記事】` を確認
- draft 62598 は候補 0 件で省略（期待通り）

**実機 publish 確認（第31便 `d81a49e`）**:
- post_id=62618（status=publish、`巨人3-4 敗戦の分岐点はどこだったか`）に
  `<div class="yoshilover-related-posts">` + 「【関連記事】」を WP REST で確認
- post_id=62600（status=draft）にも同ブロック残存
- 第2弾 deploy 後（revision `yoshilover-fetcher-00139-k7h`）でも回帰なし

**次アクション**: なし（第1弾は監査・運用継続のみ。新規問題が出れば別チケットで起票）

---

### 第2弾: team batting stats の opt-in 注入（flag 既定 OFF）

**第29便 調査結論**（`codex_responses/2026-04-18_29.md`）:
- 既存 `fetch_giants_batting_stats_from_yahoo()` は試合速報 lineup 以外で未使用
- strict prompt 群には `source_fact_block` / `source_day_label` しか渡っておらず、数値材料が prompt に入っていない

**実装**: 第30便 `b7f20d8`（src/rss_fetcher.py + `.env.example` + tests/test_team_stats_prompt.py、397 passed）
- `_format_team_batting_stats_block` 追加
- `_build_gemini_strict_prompt` / `_build_game_strict_prompt` / `_build_manager_strict_prompt` に `team_stats_block` 引数追加
- env flag `ARTICLE_INJECT_TEAM_STATS`（既定 `"0"`）で制御、試合速報 / 首脳陣 のみ対象
- 取得失敗は空文字で続行、flag OFF 時は現行と完全同一挙動（回帰テストで担保）

**deploy**: 第31便 `d81a49e` → revision `yoshilover-fetcher-00139-k7h`、traffic 100%（flag OFF）

**第31便 OFF smoke 結果**:
- 手動 trigger `/run` HTTP 200、drafts_created=6 / error_count=0
- `article_team_stats_injected=0`（flag OFF 担保）
- post_id=62618 / 62600 本文に「【参考：巨人打者の今季主要指標」**含まれず**（OFF 担保）
- 第1弾 `yoshilover-related-posts` div は両 post で残存（回帰なし）
- rollback 未実施

**次アクション（第2弾）**:
1. 第32便で **canary revision** に `ARTICLE_INJECT_TEAM_STATS=1` を載せて `--no-traffic --tag canary-team-stats` で flag ON smoke（prod traffic は 00139-k7h 維持、tag URL に直接 POST）
2. 第32便 clean なら 24h 後に第33便（観察便、prod 側 `article_team_stats_injected=0` と第1弾 related-posts 継続を再確認）
3. 第33便 clean なら第34便で promote 判断（prod env に `ARTICLE_INJECT_TEAM_STATS=1` を `--update-env-vars` 追加）— よしひろさん側判断

---

## T-025 🟠 WP draft title-only reuse が distinct source を誤吸着（#78 診断、7日 18.5% 汚染、post_id 62795 11 fire 集中）

**発見日**: 2026-04-20
**発見者**: Codex #78 診断
**影響**: generic rewritten title と 24h title-only reuse が重なると、別 source の draft 生成 work が既存 draft に吸着して消える

**既知の事実**:
- 直近 7 日で 46 fire / 248 fire が汚染（18.5%）
- `post_id=62795` に 11 fire が集中
- 原因は `wp_client.find_recent_post_by_title()` が title-only で直近 draft を再利用していたこと

**対応方針**:
- draft reuse 条件を `source_url` 一致必須に変更
- same-fire で同一 rewritten title に別 source が来た場合は distinct source をログに残す
- retry / 手動復旧の title-only reuse は opt-in に限定

---

## T-026 🟡 `yoshi-today-giants` が未配線（plugin 実装だけあって DOM に出ていない）

**発見日**: 2026-04-24
**発見者**: Claude Code（監査役、front_refresh 便 read-only 確認）
**影響**: plugin に render / shortcode `[yoshilover_today_giants_box]` と CSS があるが、トップにも記事詳細にも DOM 0。実運用導線として存在しない

**実測**:
- `https://yoshilover.com/` DOM に `yoshi-today-giants` クラス 0 件（CSS 定義のみ 116 hits）
- `https://yoshilover.com/62965` DOM に `yoshi-today-giants` クラス 0 件
- `src/yoshilover-063-frontend.php` には `yoshilover_today_giants_box` shortcode 登録あり（line 38 周辺）

**判断保留**:
- 意図して未配線なのか、配線忘れなのか不明
- 「今日の巨人」を sidebar に出す価値があるかはよしひろさん判断

**次アクション**:
- よしひろさんに「`yoshi-today-giants` は使うか / 使わないか」だけ確認
- 使うなら配線便を立てる、使わないなら shortcode / CSS ごと削除便を立てる

---

## T-027 🟡 `yoshi-sidebar-rail` auto-inject が届いていない

**発見日**: 2026-04-24
**発見者**: Claude Code（監査役、front_refresh 便 read-only 確認）
**影響**: plugin 側で `add_action( 'dynamic_sidebar_before', 'yoshilover_063_auto_inject_sidebar_rail', 5, 2 )` に登録されているが、`yoshi-sidebar-rail` クラスが DOM 0 件。sidebar-rail の POPULAR / CATEGORY / TOPIC chips がどこにも出ていない

**実測**:
- `https://yoshilover.com/` DOM に `yoshi-sidebar-rail` クラス 0 件（CSS 定義のみ 147 hits）
- `https://yoshilover.com/62965` DOM に `yoshi-sidebar-rail` クラス 0 件
- body class は `-sidebar-on -frame-on-sidebar` で sidebar は有効
- `yoshilover_063_should_render_sidebar_rail()` / `yoshilover_063_is_primary_sidebar_index()` の判定条件でフィルタ外されている可能性

**調査事項**（Codex 調査便向け）:
- `yoshilover_063_auto_inject_sidebar_rail` が firing しているか（`error_log` 仕込み or xdebug）
- `yoshilover_063_is_primary_sidebar_index()` が受け取る `$index` の実値
- SWELL の sidebar index 名（`sidebar-1` / `swell_sidebar` / `widget-area` のどれか）
- `yoshilover_063_should_render_sidebar_rail()` の戻り値

---

---

## チケット運用ルール

- 新規発見: このファイルに追記、IDは連番（T-007, T-008...）
- 解決時: `RESOLVED.md` へ移動（日付と対応内容付き）
- 優先度は状況に応じて更新してよい
- 各チケットに「Codex向け指示書ドラフト」を用意しておくと、コピペで実装依頼できる
