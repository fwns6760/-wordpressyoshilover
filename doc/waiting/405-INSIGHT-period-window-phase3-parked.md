# 405-INSIGHT-period-window-phase3-parked

## 1. ticket header

- **status**: PARKED (重工事、 pitch-by-pitch source 確保から、 当面着手しない)
- **priority**: low (shadow ticket、 議論された案を忘れないため残す)
- **owner**: Claude / **lane**: Claude
- **stage**: Phase 3 / 段階式 ([[403]] / [[404]] の最終 follow-up)
- **依存**: [[project_data_insight_period_scope_2026_05_20]] memory
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/81

## 2. 目的

ファン視点 cut のうち **pitch-by-pitch (1 球単位) source が必要なため当面着手しない案** を shadow ticket として保管する。 [[403]] / [[404]] で取り込んだ cut の延長で、 さらに細かい状況別の split を実装したくなった時にここから再開する。

## 3. scope (parked)

### 3.1. 打席内カウント別

- 初球打ち打率 (1 球目で結果が出た打席のみ集計)
- 2 ストライク後打率 (追い込まれてから decision がついた打席)
- 3 ボール後打率
- 投球数別 (10 球以上の粘り打席 .XXX)

**障壁**: NPB box は per-PA result の text marker のみ提供、 pitch-by-pitch data なし。 別 source 必要 (有料 sports data API or NPB BIS feed)。

### 3.2. 走者状況別 (得点圏以外)

- 満塁時打率
- 二塁単独時打率
- 一三塁時打率
- 走者なし時の本塁打率
- 一二塁時の犠飛率

**障壁**: atbats_json に走者 state が入っていない。 NPB box の per-PA marker (「○」 「●」 等) は得点圏のみ。 詳細 split には別 source 必要。

### 3.3. 球場別 (本拠地以外)

- 甲子園での打率
- マツダスタジアムでの本塁打率
- ハマスタでの ERA

**障壁**: `games.home_away` (本拠地 / ビジター) はあるが、 ビジター内で球場名を区別する列が無い。 `games.opponent` × `home_away='away'` で代替可能だが、 「中日 vs 巨人 (バンテリン)」「広島 vs 巨人 (マツダ)」 等の球場別 split は ETL 軽改修で対応可能 (実は Phase 2 寄り)。

## 4. 着手判断条件

以下のいずれかが揃ったら [[403]] / [[404]] の安定後に再開:

1. pitch-by-pitch data の安定 source 確保 (有料 API 契約 or 別 scraping target)
2. NPB BIS 等の official feed access 取得
3. user から「ファンが特に欲しい cut」 が再指定

## 5. 不可触

- [[403]] / [[404]] が固めた cut 体系
- 既存 publisher の title format
- env / Secret / Scheduler / DB schema (本 ticket 単独では何も変えない)

## 6. 関連 memory

- [[project_data_insight_aggressive_publishing]] — 「閾値超えたら全部 publish」 方針、 Phase 3 は閾値設定の前提となる sample 自体が不足のため除外
- [[feedback_data_insight_user_preferences_2026_05_15]] — サバメ NG line 維持、 Phase 3 の細分も whitelist 範囲内のみ
