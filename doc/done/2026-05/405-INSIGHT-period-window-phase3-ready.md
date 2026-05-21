# 405-INSIGHT-period-window-phase3-parked

## 1. ticket header

- **status**: CLOSED LIVE_DEPLOYED_VERIFIED (全 Phase 1/2a/2b/2c/3a/3b/3c 完成 + production fire publish 確認)
  - Phase 1 parser (`f777f4c`): per-PA 走者状況 + count + 投手追跡
  - Phase 2a schema (`dc0d294`): at_bat_details table + 4 indexes
  - Phase 2b ingest (`dc0d294`): upsert_at_bat_details + parse_rbi_from_result_text
  - Phase 2c scraper (`485af09`): build_playbyplay_url + ingest_giants_playbyplay_recent_games
  - Phase 3a (`a4f90b9`): 走者状況別 aggregator + publisher (満塁 / 1・3塁 / 2・3塁)
  - Phase 3b (`a4f90b9`): 打席内カウント別 aggregator + publisher (first_pitch / two_strike)
  - Phase 3c (`a4f90b9`): vs 球団別 aggregator + publisher (5 セ・リーグ相手)
  - wire (`485af09`): insight_nightly に ingest + 10 cut publisher 配線
  - production verify (2026-05-21 15:00 JST fire、 image `insight-nightly:team-cap-8`):
    - 405 Phase 3a: post 70039 (吉川 満塁時) / 70041 (ダルベック 1・3塁時) / 70043 (浦田 2・3塁時)
    - 405 Phase 3b: post 70045 (佐々木 初球打ち) / 70047 (キャベッジ 2ストライク後)
    - 405 Phase 3c: post 70049 (大城 対ヤクルト) / 70051 (キャベッジ 対DeNA) / 70053 (浦田 対中日)
  - GH Issue #81 close 候補
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

**source (2026-05-20 確定)**: NPB 公式 `https://npb.jp/scores/YYYY/MMDD/SLUG/playbyplay.html` で per-PA `X-Y より` (count) + 結果 (`空振り三振` / `中安打` 等) を parse 可能 (sample game で実 verify 済、 無料 source)。

### 3.2. 走者状況別 (得点圏以外)

- 満塁時打率
- 二塁単独時打率
- 一三塁時打率
- 走者なし時の本塁打率
- 一二塁時の犠飛率

**source (2026-05-20 確定)**: NPB 公式 `playbyplay.html` で per-PA 走者状況 (`1塁` / `2塁` / `3塁` / `1・2塁` / `1・3塁` / `2・3塁` / `満塁` / `&nbsp;`=無走者) と打者名 / 結果が table 列で並んでいる (sample game で実 verify 済、 無料 source)。

### 3.3. 球場別 (本拠地以外)

- 甲子園での打率
- マツダスタジアムでの本塁打率
- ハマスタでの ERA

**障壁**: `games.home_away` (本拠地 / ビジター) はあるが、 ビジター内で球場名を区別する列が無い。 `games.opponent` × `home_away='away'` で代替可能だが、 「中日 vs 巨人 (バンテリン)」「広島 vs 巨人 (マツダ)」 等の球場別 split は ETL 軽改修で対応可能 (実は Phase 2 寄り)。

## 4. 着手判断条件

**2026-05-20 PM 更新**: free source 確保 (`playbyplay.html`) で着手判断条件は満たされた。 残課題は実装 scope の大きさ (6-8h):

1. **playbyplay.html parser** 新規 (1 game の parse + 全球団化、 stable HTML 構造で regex 抽出可)
2. **per-PA detail table** 新設 (player_canonical / game_id / inning / outs / runners_state / count_balls / count_strikes / result_text / current_pitcher)
3. **3 aggregators**: 打席内カウント別 / 走者状況別 / 球場別
4. **3 publishers**: 各 cut の ranking publish
5. **tests + build + deploy**

= 1 session 跨ぎで段階実装が現実的。 spec lock 済み、 次 session で 1 cut ずつ着手可能。

## 5. 不可触

- [[403]] / [[404]] が固めた cut 体系
- 既存 publisher の title format
- env / Secret / Scheduler / DB schema (本 ticket 単独では何も変えない)

## 6. 関連 memory

- [[project_data_insight_aggressive_publishing]] — 「閾値超えたら全部 publish」 方針、 Phase 3 は閾値設定の前提となる sample 自体が不足のため除外
- [[feedback_data_insight_user_preferences_2026_05_15]] — サバメ NG line 維持、 Phase 3 の細分も whitelist 範囲内のみ
