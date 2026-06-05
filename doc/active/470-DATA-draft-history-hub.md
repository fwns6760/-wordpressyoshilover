# 470-DATA 巨人ドラフト史ページ /data/draft

- status: IN_FLIGHT（枠組み LIVE・本番公開ゲート OFF）
- owner: Claude
- created: 2026-06-05
- benchmark: https://www.my-favorite-giants.net/giants_data/draft/lot.htm
- user 確定（2026-06-05）:
  - データ範囲 = **全年代(1965-2024)揃えてから公開**
  - セクション = **全7枠を最初から作り、揃った順に公開（空は「準備中」）**

## 構成（実装済み）

- template: `src/data_site_template_draft.py`（全7セクション + トピックス、空は「準備中」表示）
- data 正本: `config/giants_draft_history.json`（事実のみ・推測で埋めない）
- publisher 配線: `src/data_site_publisher.py`、slug=`draft`・parent=cluster → `/data/draft/`
- 公開ゲート: `ENABLE_DATA_SITE_DRAFT`（既定 OFF）。**全年代整備完了まで本番非公開**。
- preview: `out/draft_preview.html`（ローカルで開いて構造確認可）

## 7セクション

1. ドラフト指名選手一覧（支配下・年度別）
2. 育成ドラフト指名選手一覧
3. ドラフト外入団選手一覧
4. 指名競合選手一覧（外れ1位）★ベンチの中核
5. スカウト名簿
6. OBスカウト名簿
7. 契約変更選手一覧

## データソース（正本）

- 年度別指名: Wikipedia `Template:読売ジャイアンツ{年}ドラフト指名選手`
  （`Category:読売ジャイアンツのドラフト指名選手テンプレート` に1965〜全年分そろっている）
  - 注: テンプレは**選手名のみ**。守備位置・所属は年度別ドラフト会議ページ / NPB公式から補完。
- 指名競合・外れ1位: 年度別ドラフト会議ページ（抽選結果）。
- スカウト名簿 / OBスカウト名簿 / 契約変更: 球団公式 / 報道（現役情報のため取得難・後回し可）。

## 現状シード

- 2024年: 支配下5名 + 育成6名（名前のみ Wikipedia テンプレで検証済）。位置・所属は未補完（空欄=「—」）。

## backfill TODO（次セッション以降）

1. 2024 の位置・所属を補完（roster と突合可能な現役は突合）。
2. 2023 → 2015 を年度別テンプレ + 会議ページから順次（名前+位置+所属+1位抽選）。
3. 指名競合・外れ1位（lot.htm 相当）を年度ごとに整備（ベンチ中核）。
4. 1965〜2014 を順次。ドラフト外入団は制度のあった年代のみ。
5. スカウト/OBスカウト/契約変更は球団公式確認後に投入。
6. 全年代そろったら `ENABLE_DATA_SITE_DRAFT=1` + cluster に導線チップ追加 → deploy。

## 不可触 / 注意

- 事実誤認NG。空欄は推測で埋めない。
- cluster 導線チップは**公開時に追加**（それまで dead link を作らない）。
