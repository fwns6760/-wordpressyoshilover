# 460 DATA-SITE cluster UX(検索/今日の注目/zero-row)+ team_role 誤ラベル follow-up

- **種別**: 実装 / **priority**: P2 / **effort**: S〜M
- **親**: 443 / 設計: `455...md` §12-0 / §13-4 / GH: #124
- **status**: READY

## 背景(深掘り・実取得)

- 索引 `/data` は WP標準ページに静的table、**検索/フィルタ/ソート/「今日の注目」無し**。更新日は文言のみ(日付なし)。
- fill率 約70%(捕手50%/内野56%)。**バグでなく出場機会**(`data_site_publisher.py:263/318` が logs 行ゼロで `–`、2捕手制で控え捕手は先発0=行0、姓バリアント全探索で真の不在を確認)。育成38は意図的に名前のみ(`data_site_template_cluster.py:258`)。
- **潜在バグ(fill率には無影響)**: `batting_logs.team_role='giants'` が対戦相手も含む誤ラベル(278試合中巨人46、佐藤輝明/菊池涼介等が 'giants' に混入)。現 fill/`fetch_team_leaders`(`data_site_query.py:1110` は `advanced_metric_snapshots.team_code='g'` scope)は team_role 非依存で無害だが、信じる処理があれば誤る。

## ゴール

1. 索引に **選手名検索**(かな/漢字/英の incremental)+ **「今日の注目」**(直近5試合HOT 自動抽出)+ 更新日バッジ(日付)。
2. **zero-row(`–`)選手を成績tableから抑制**し、別枠(ロスター一覧)へ。thin-page SEO回避。
3. **team_role='giants' 誤ラベルの follow-up**: 原因特定(ingest のラベリング)と、team_role を信頼する箇所の棚卸し→修正 or 明示非依存化。

## 対象

- `src/data_site_template_cluster.py` / `data_site_publisher.py`: 検索 UI・今日の注目・zero-row 抑制・更新日。
- `src/analysis/insight_etl.py`(team_role ラベリング)+ team_role 参照箇所 grep。

## やる / やらない

- やる: 検索/今日の注目/zero-row 抑制/更新日、team_role 棚卸しと最小修正、test。
- やらない: ingest 窓拡張(production 運用側)、出場機会の本質的 fill 向上(頭打ち)。

## 成功条件

- 索引で選手検索が効く、「今日の注目」が直近データで出る、zero-row が table から消える。
- team_role を信頼する箇所が無い(or 修正済)ことを grep で確認。
- targeted pytest green。

## 依存

なし。team_role 修正は read-only 棚卸し先行。
