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

