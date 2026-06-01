# data-site 目標設計図(ベンチマーク2サイトに向けて)

> 種別: 設計図(証拠only。ベンチ機能は 2026-06-01 WebFetch、自社データは insight.db 現物 COUNT で verify)
> 対象 ticket: `452-DATA-SITE-situational-depth.md` / ゴール正本は 452 §0
> 作成: 2026-06-01 / status: DRAFT
> 目的: ベンチ(`baseballdata.jp` / `my-favorite-giants.net`)の機能を**巨人特化で上回る**ための
>   全体IA + 機能マッピング。何を「今(Phase B、¥0)」作り、何を「投資(Phase C)」に回すかを固定。

## 1. ベンチが持つ機能(WebFetch 確認、2026-06-01)

- **baseballdata.jp**(全12球団・多年): 打撃/投手指標、独自 HR-WPO、状況別(所属/リーグ戦/交流戦/曜日/球場/月/打順/先発途中/対戦チーム)、チーム別12球団、年度選択2011-2026、打撃/投手タブUI。
- **my-favorite-giants.net**(巨人特化・多年): オフ補強/公示/負傷者リスト、年度別個人成績、先発ローテ一覧、スタメン、背番号推移、歴代通算/シーズンランキング、試合日程結果カレンダー、CS/日本S/オープン戦成績、チーム成績/カード別勝敗/監督別、投打守備、順位表、メモリアルアーチ、階層メニュー+検索+サイトマップ。

## 2. 自社データの現実(insight.db 現物 COUNT)

games 2026-03-27〜05-31(今季のみ) / standings 0 / fielding 0 / at_bat batter_canonical非NULL 0。
→ 多年・守備・順位表・RISP は**現状ゼロ**(Phase C 投資)。

## 3. 目標サイト IA(巨人特化)

```
/data/ (cluster: 全選手ハブ)
  ├─ /data/<player>/  選手ページ(本丸 = SEO ロングテール)
  │     季別成績 / 直近 / 打順別 / 球場別 / 対球団 / 序中終盤
  │     ★追加: 曜日別 / 月別 / 交流戦vsリーグ戦 / 試合別ログ (Phase B)
  │     投手: 前回登板 / season / (救援)防御率
  │     構造化(SportsPlayer)+ 関連選手 + 関連記事 + dateModified
  ├─ /data/team/      チーム成績(打率/防御率の球団内・セ内ランキング)★新規B
  ├─ /data/schedule/  日程・結果カレンダー(games から)★新規B
  ├─ /data/lineup/    スタメン履歴 / 先発ローテ(lineups/pitching_logs)★新規B
  ├─ /data/roster/    公示・登録抹移・負傷(記事テキスト由来、出典明記)△半B
  └─ /data/ranking/   歴代/通算ランキング ← 多年データ前提 = Phase C
```

## 4. 機能マッピング(ベンチ機能 → 我々の実装 → 可否)

| ベンチ機能 | 我々の実装 | データ源(verified) | 区分 |
|---|---|---|---|
| 選手 季別成績 | 既存 season section | batting/pitching_logs | ✅済 |
| 打順別/球場別/対球団/序中終盤 | 既存 split section | batting_logs + game_id | ✅済 |
| **曜日別/月別/交流戦別** | 新規 split(Phase B) | game_date + game_id コード | 🟢B(¥0) |
| **試合別ログ** | 新規(直近N試合) | batting_logs(game×player) | 🟢B |
| **チーム成績/球団ランキング** | /data/team(打率/防御率順位) | 全球団 logs 集計 | 🟢B |
| **日程・結果カレンダー** | /data/schedule | games | 🟢B |
| **スタメン/先発ローテ** | /data/lineup | lineups/pitching_logs | 🟢B |
| 公示/登録抹消/負傷者 | /data/roster(記事由来) | RSS記事テキスト(出典明記) | 🟡半B(転載不可) |
| 投手詳細(前回登板) | 既存(先発=前回登板/救援=防御率) | pitching_logs | ✅済 |
| **守備成績** | — | fielding_logs **0** | 🔴C(source投資) |
| **順位表/勝敗表** | — | standings **0** | 🔴C |
| 得点圏/対左右 | — | at_bat batter_canonical **0** | 🔴C(447) |
| **多年(2011〜)/歴代ランキング/背番号推移** | — | 今季のみ | 🔴C(多年取り込み投資) |
| 独自指標(HR-WPO 等) | サバメ系は publish-NG 方針 | — | 方針外 |
| 階層メニュー/検索/サイトマップ | cluster + 内部リンク + page-sitemap | 既存 | ✅一部済、UIで強化 |

凡例: ✅済 / 🟢B=今すぐ¥0 / 🟡半B=記事由来で限定 / 🔴C=投資判断。

## 5. フェーズ計画

- **Phase B(¥0・追加source無し、ゴール直結)**: §4 の 🟢 を実装。選手ページ split 拡張 + /data/team + /data/schedule + /data/lineup。→ 巨人特化の網羅を今季データで一気に上げ、SEO ロングテール面を拡大。
- **SEO技術(小)**: dateModified / stats表の構造化 / 内部リンク密度 / UI・モバイル。
- **Phase C(投資・別ticket)**: 守備 source / 順位表 / 多年取り込み(一次ソース、ベンチ転載しない) / RISP backfill。head term と歴代を取りに行く。コスト見積り後に user 判断。

## 6. 構築状況(2026-06-01 現物)

- ✅ live: 既存 /data/ 選手ページ(season+各split+投手)、cluster、SNSリアルタイム、毎朝Xデータ候補メール。
- ⛔ 未構築: §4 の 🟢B(曜日/月/交流戦/試合別、team/schedule/lineup ページ)、🔴C 全部。
- = **本設計図に対し、構築は「既存部分のみ完了、Phase B 以降は未着手」**。
