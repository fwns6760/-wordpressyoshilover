# 452 data-site 状況別データ深化 + データ堀の投資判断

## /data/schedule(日程・結果)LIVE(2026-06-01)

- 新規ページ `/data/schedule`(`data_site_template_schedule.py` + `fetch_giants_schedule` + publisher 配線)。
  巨人の日程・結果を月別・1行1試合(勝=緑/負=灰・スコア・本拠地ビジター)で表示。games 由来・追加source無し。
- image `data-site-publisher:schedule-b655062` / execution `kjdgc` / 20 tests pass。
- **live verify: `https://yoshilover.com/data/schedule` http200、52試合行・5月/4月/3月ブロック表示**。
- 残りページ: /data/team(球団ランキング)/ /data/leaders(各種記録)/ /data/legends hub。leaders は並行アクター 453(順位)と要調整。

## Phase B LIVE_DEPLOYED_VERIFIED(2026-06-01)

- 曜日別 / 月別 / 交流戦別 split を選手ページに追加、image `data-site-publisher:phaseB-860c592`、
  execution `d5xx6`、115 pillar 更新。**live verify: 吉川尚輝 + 岸田行倫 で3 section 表示(cache回避済)**。
- **verify 中に root cause bug を発見・修正**: target 名(`岸田行倫` 空白なし)と insight.db
  `player_canonical`(`岸田 行倫` 空白あり)の不一致で split query が空振り。曜日/月/交流戦/イニングの
  WHERE を `REPLACE(...' ','')` 比較に修正。吉川は元々一致で OK、岸田は修正後 OK。
- 並行アクターの UI 刷新(`cef367f` ys-card/オレンジ/順位バッジ)と同居して deploy(結合 48-63 tests pass)。

### ✅ 広域 name-match bug 修正完了 LIVE(2026-06-01、user「バグがあるなら修正」)

- `data_site_query.py` の **全 fetch(9箇所)の `player_canonical = ?` を `REPLACE(...' ','')` 空白無視マッチに統一**。
  → venue / opponent / 打順別 / season / recent / streak / 投手 / NPB順位バッジ(453)が、target名(空白なし)
  と insight.db canonical(空白あり)不一致の選手(岸田 等)でも全て出るように。
- image `data-site-publisher:namefix-5840dbc` / execution `q5ndp` / 63 tests pass。
- **live verify: 岸田行倫ページに 今シーズン/打順別/vs各球団/本拠地ビジター/曜日別/月別/交流戦 全 section 復活**。
- data サイト全体の品質穴(spacing-mismatch 選手の section 欠落)を解消。

## 実装状況(2026-06-01、Phase B 一次)

- **コード完成・検証済(未commit、HOLD)**: 曜日別 / 月別 / 交流戦別 split を実装。
  - `data_site_query.py`: `SplitStat` + `fetch_weekday_split_stats` / `fetch_month_split_stats` / `fetch_interleague_split_stats`(+ `_fetch_player_game_rows` / `_bucket_splits` / `_opp_code`、`_PA_TEAM_CODES`)。
  - `data_site_template_pillar.py`: `_build_weekday_split_html` / `_build_month_split_html` / `_build_interleague_split_html` + フィールド3 + assembly 配線。
  - `data_site_publisher.py`: 3 split の info 配線 + import。
  - `tests/test_data_site_query.py`: `DateBasedSplitTests`(曜日/月/交流戦)。
  - 検証: **48 tests pass**、prod データで岸田ページに3 section render OK(月別.167→.255→.407、交流戦.444 等)。
- **HOLD 理由(user 判断「2」)**: `data_site_template_pillar.py` 等を **並行アクターが UI CSS刷新(ys-card 化)+453順位バッジで未commit大改修中**。衝突回避のため、**並行アクターの template 刷新が commit された後に**私の builder を上に乗せて commit + deploy する。
- **再開条件**: 並行アクターの template refactor が commit される / user 指示。再開時に builder を再確認(grep)→ commit → image rebuild → execute → live verify。

## 0. ゴール(正本、2026-06-01 user 確定)

> **巨人“専門”の決定版データサイトで、Google 検索(SEO)に勝つ。**
> 総合サイト(baseballdata.jp)とも巨人特化サイト(my-favorite-giants.net)とも、
> **巨人に関しては検索で上回る**。武器は ①巨人特化の深さ ②差別化された切り口(状況別)
> ③UI/UX ④構造化データ ⑤鮮度。データpage = SEO 資産(速報は noindex)。

**勝ち方の現実(正直)**:

- head term(「巨人 打率ランキング」等)は相手の**多年蓄積+ドメイン権威**が強く短期では困難。
- **短期で勝てる = ロングテール + 鮮度 + リッチリザルト**(選手×状況クエリ、「◯◯ 最近 調子」、構造化データ)。差別化で取る。
- head term まで取りに行く = **多年データ(Phase C、一次ソース取り込み)+ 継続的な権威構築**が必要。

**データ源の原則(法務)**: ベンチのページを**転載しない**(著作権/ToS、§11)。数字は公共事実なので
**一次ソース(NPB 公式 box score、既存経路の延長)から自前取り込み**する。

### SEO / Google 設計の軸(現物確認した既存資産の上に積む)

| 軸 | 現状(verified) | 強化方針 |
|---|---|---|
| 構造化データ | JSON-LD `SportsPlayer/SportsTeam/BreadcrumbList/CollectionPage/ItemList/WebSite/PropertyValue` 実装済 | stats を表構造化 + `dateModified`(鮮度シグナル) |
| 内部リンク | パンくず / 関連選手 / 関連記事 / cluster戻り 実装済 | cluster→選手→記事→状況別 の網を密に |
| index 方針 | データ/SNS=index、速報=noindex(2026-05-29 確定) | 薄ページ index 希釈を避ける |
| 権威(E-E-A-T) | 404→410 で回復中、出典明記 | 一次ソース + 出典の一貫表示 |
| 差別化コンテンツ | 球場別/打順別/序中終盤 等(ベンチが弱い) | 曜日別/月別/交流戦別(Phase B)で長尾を増やす |
| 鮮度 | 毎日更新 | 「今の調子」クエリを取る(彼らは静的) |
| ページ体験/UI | カード様式 | モバイル/速度/見やすさ(UI/UXで勝つ) |

→ KPI: **検索流入 / index 数 / 対象クエリ順位 / リッチリザルト表示**(PV単体でなく検索面)。

## 保留 TODO(記録、本丸ではない)

- **サイトタイトル変更(user 手動)**: WP管理画面 → SEO SIMPLE PACK → 一般設定 → サイトのタイトルを
  `ヨシラバー｜巨人 成績・データ・速報掲示板` に変更。
  - 状況(2026-06-01 現物確認): WP コア blogname は API で変更済だが、`<title>`/`og:site_name` は
    **SEO SIMPLE PACK 3.6.2 が上書き**しており REST から触れない → **user 手動が必要**。
  - 変更後、Claude が live `<title>`/og を再 verify。
  - 優先度: 低(本丸=データ SEO 差別化。タイトルは後でよい)。

## 1. ticket header

- **ticket id**: 452(450/451 は並行アクターの video-radar が使用中のため 452)
- **status**: DRAFT(user 受け入れ待ち)
- **owner**: Claude Code
- **lane**: data-site / insight.db(read-side)
- **created**: 2026-06-01
- **priority**: P2(data サイト差別化。443/444 Phase 1.5 の上に積む)
- **parent**: 444(data-site Phase 1.5)
- **spec**: `mkdocs_docs/spec/data-site-situational-splits.md`
- **関連**: 447(RISP/対左右 = Phase C 依存)

## 2. 背景(現物確認 2026-06-01)

ベンチ(`baseballdata.jp` / `my-favorite-giants.net`)を WebFetch で確認。両者は
**多年蓄積(2011〜)+ 守備 + 順位表 + 網羅的状況別**を持つ。一方 YOSHILOVER の
`insight.db` は現物 COUNT で:

- games = `2026-03-27`〜`2026-05-31`(今季のみ)
- `standings_snapshots` 0 / `fielding_logs` 0 / `at_bat_details.batter_canonical` 非NULL 0

user 方針:「見やすさ、データでも勝つ」。→ 2 フェーズに分解。

## 3. Phase B(本ticketの実装対象、追加source無し・¥0)

今季 box score から **追加取得なしで作れる状況別スプリット**を /data/ 選手ページに追加し、
「今季の細かさ + UI」でベンチに勝つ。

- 曜日別 / 月別 / 交流戦vsリーグ戦 別 打率(`games.game_date` + `game_id` の NPB コードから導出。
  導出可を岸田行倫の実データで verify 済: `f-g`=交流戦 / `g-t`=リーグ戦)
- 直近試合の1行ログ(`batting_logs`)
- 投手は既存(前回登板/防御率)維持、曜日/月別は対象外(サンプル不足)

詳細・受け入れ条件・UI・不可触は **spec** を正とする。

### 実装対象(想定)

- `src/data_site_query.py`: `fetch_weekday_split` / `fetch_month_split` / `fetch_interleague_split` / `fetch_recent_game_log`(全て read-only、`team_code='g'`/player_canonical 絞り)
- `src/data_site_template_pillar.py`: 対応 `_build_*_html` 4 section + assembly 配線
- `src/data_site_publisher.py`: PillarPlayerInfo 配線
- `tests/`: 各 split の集計 + 表示テスト

### 受け入れ(spec §4 準拠)

- 4 section が出場データのある選手で出る / 数字が DB と一致 / 打数0区分は非表示 /
  新規 source・Gemini・課金 増なし / 既存+新規テスト pass / live 1選手 verify。

## 4. Phase C(投資判断 = 別ticket化、本ticketでは着手しない)

「データ網羅でベンチに勝つ」に必要だが **現データゼロ**:

| 項目 | 現状 | 必要な投資 |
|---|---|---|
| 多年データ(2011〜) | 今季のみ | 過去年 box の取り込み source + ETL |
| 守備成績 | `fielding_logs` 0 | 守備データ source |
| 順位表/勝敗表 | `standings_snapshots` 0 | 順位 source or 算出 |
| 得点圏/対左右 | `at_bat batter_canonical` 0 | backfill(447) |

→ source拡張 + コスト(月単位)を伴うため **user 投資判断(§11 課金・scope)**。
別ticketで「どのデータ源をいくらで入れるか」を見積もってから着手。本ticketには含めない。

## 5. 次アクション

- user が **Phase B 着手を承認**したら、spec に沿って実装(¥0・read-only・deploy 1回)。
- Phase C は別途「データ源調査ticket」を起こし、source候補とコストを出してから user 判断。

## 6. 不可触(Phase B)

多年/守備/順位表/RISP / 投手曜日月別 / 既存 article path / Scheduler / featured_media / X lane。
