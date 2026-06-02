# 460 DATA-SITE cluster UX(検索/今日の注目/zero-row)+ team_role 誤ラベル follow-up

- **種別**: 実装 / **priority**: P2 / **effort**: S〜M
- **親**: 443 / 設計: `455...md` §12-0 / §13-4 / GH: #124
- **status**: PARTIAL_LIVE_VERIFIED (2026-06-02) — 今日の注目 + **選手検索box LIVE**、 zero-row のみ defer(user 判断)
- **検索box 着地(2026-06-02、commit `bd7cdc64`、image `data-site-publisher:search-box-bd7cdc6`)**: /data/ に client-side インクリメンタル検索 box。全テーブル(打者/投手/監督コーチ/育成/OB)の `/data/` リンク行を選手名で絞り込み(全角空白除去で部分一致、0件時のみ「見つかりません」)。progressive enhancement(JS 無効でも全リスト保持)。**`<script>` 除去懸念は解消**: WP publish ユーザ `unfiltered_html` 保有で JSON-LD/実行 JS とも stored content + **公開 HTML まで生存**を実ページ確認(`addEventListener("input"` が公開 /data/ に存在)。検索対象は `section[class*="ys-cluster"][class*="-table"]` 内に限定(intro ナビ除外)。test: cluster+publisher 25 pass。
- **実績**: commit `a572aa50`、image `data-site-publisher:hot-a572aa50`、execute SUCCESS。/data/ first view に「📈直近5試合の注目選手」カード(last_5_games OPS/ERA 上位、sample gate、pillar回遊)。verify = cluster page 73526 に 岸田OPS1.036/大城1.032/平山1.008/堀田防御率0.00/マルティネス1.80 反映確認。data-site test 105 passed。
- **defer(別途)**:
  - 選手検索box: WP が post content の `<script>` を除去する可能性があり、動作 verify が先 → 別途。
  - zero-row(`–`)抑制: 実選手を table から消すリスク + ロスター可視性とのトレードオフ → user 方針確認後。
- **team_role 確認(read-only)**: cluster fill / fetch_team_leaders は team_role 非依存(`team_code='g'`/name match)で**安全**。`data_site_query.py:1023/1027` の game-detail(lineups table)2箇所が `team_role='giants'` 依存 → lineups table の team_role 信頼性は別途検証要(batting_logs の誤ラベルとは別 table、未確認)。

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
