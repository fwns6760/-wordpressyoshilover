# 446 data-site Phase 1 full — 残り 54 player slug 整備 + 拡大

## 1. ticket header

- **ticket id**: 446
- **status**: LIVE_DEPLOYED (2026-05-29、 user 指示で実行)
- **owner**: Claude Code
- **lane**: data-site / phase 拡大
- **created**: 2026-05-28
- **priority**: P3 → 着手済 (user「選手のページを作って あとコーチマネージャ」)
- **parent**: 444 (data-site Phase 1.5)
- **github_issue**: PENDING

## 進捗 (2026-05-29 LIVE)

**31 → 112 page へ拡大完了** (commit `37c91a1` impl + `743fc59` footnote)

- 範囲 (user 確認済): 支配下選手85 (player 84 + 支配下降格 1) + 監督1 + コーチ27 = 112
  (slug dedup 後)。 育成23は一軍データ薄のため除外。
- **slug**: option B (手動) を採用。 75 名分 romaji を data_site_slug.py に hand-author
  (pykakasi 不使用、 URL/SEO 用、 表示は kanji)。 若手読みは推定含む forward-only。
- **対象選定**: config 手書き 31 名 → roster 直結 (load_data_site_target_names、
  role=player/shihaikako/coach/manager filter + slug dedup)。 roster 更新に自動追従。
- **監督・コーチ**: stats 無し → profile 型 page (役職 + 関連記事)、 cluster に専用
  「監督・コーチ 一覧」 表追加、 野手/投手表から除外。
- deploy: image `data-site-publisher:full-roster-37c91a1` → footnote `footnote-743fc59`、
  execution `data-site-publisher-2nt22` SUCCESS。 live verify: 野手46+投手38+監督コーチ28=112、
  /data/abe-shinnosuke (監督 profile)、 /data/utsumi-tetsuya (投手コーチ)、 /data/asano-shogo (新選手) 全 200。
- 残: 育成23名は別 phase (薄ページ SEO リスクのため需要観察後)。 若手 slug 読みの精査は forward-only。

## 2. 背景

ticket 444 で Phase 1.5 (一軍 active 31 player) まで実装済。 Phase 1 full = active=True AND role=player 全 84 名 (manager/coach 除く) で残り **54 player 追加** が必要。

block 真因: data_site_slug.py の `_PLAYER_SLUG_MAP` は 31 名分 hardcode、 残り 54 名分 romaji slug が未マッピング。 pykakasi 未 install、 手動で姓名 → romaji を 1 人ずつ調査 必要 (1 player 2-3 分 × 54 = 2-3 時間)。

## 進捗2 (2026-05-29 PM — 登録ポジション別 再編 LIVE)

user 追加指示「投/捕/内/外で分ける、育成は枠に、コーチ監督は軍別、生涯成績入れて」。

- **roster stale を NPB 公式名簿で是正**: ティマ昇格未反映(#013育成→#50外野手支配下)、
  16名を支配下に誤登録(実は育成)、26名「打者」未分類、石川達也=実は投手、
  森下暢仁=巨人に居ない(広島)等を発見。`config/data_site_player_class.json`(正本)化。
- **クラスター再編 (commit `d32af6e`)**: 支配下66を 投手32/捕手6/内野16/外野12 の4表 +
  育成38を「育成枠」一覧(個別ページ無し)+ 監督コーチ28を軍別(一軍11/二軍8/三軍7/巡回2)。
- 個別ページ対象 = 支配下66 + コーチ監督28 = 94(育成は枠のみ)。
- deploy: image `pos-split-d32af6e`、execution SUCCESS、live verify 済(クラスター6見出し +
  軍別4小見出し、石川達也=投手ページに是正)。test 46 passed。
- **残**: コーチ・監督の生涯成績(選手時代の通算)= insight.db に無いため公式記録 curation 必要(次便)。
  育成個別ページは未作成(枠一覧のみ、user 確認済)。旧16育成 個別ページは orphan として残置(削除は user 判断)。

## 3. options

### option A (推奨): pykakasi install + 自動 slug 生成

- requirements.txt に pykakasi 追加
- player_slug fallback で kanji name → romaji (pykakasi 経由) 自動変換
- 既存 hardcoded 31 名はそのまま (人名 reading 例外 例: 大勢=taisei、 通常 pykakasi だと taisei 出ない)
- 工数: 30 分 (install + 1 行 fallback)、 image rebuild 必要

### option B: 手動 slug 54 名追加

- 1 player ずつ姓名 → romaji 確認、 _PLAYER_SLUG_MAP に追記
- 工数: 2-3 時間 + reading 不明 player は別途 source 確認

### option C: kanji slug fallback

- 未知 player は kanji そのまま slug 化 (例: /data/中田歩夢/ = URL-encoded)
- 工数: 0 (既存 fallback 修正のみ)、 SEO 不利 (kanji slug は Google が抜き出しにくい)

### option D: 二軍 / 育成 は外す (scope 縮小)

- 「一軍 出場 record あり」 = 既に Phase 1.5 で 31 名 cover、 残り 54 名は 一軍出場ゼロの二軍 / 育成 / 怪我中
- SEO 流入 期待値低い、 Phase 1.5 で MVP 充足、 残り 54 は scope 外で OK
- 工数: 0、 ticket close

## 4. 推奨

**option D**: Phase 1.5 で MVP 充足、 残り 54 player は SEO 流入観察 (2-3 ヶ月) で需要確認後 option A or B で着手。 即時拡大の cost-benefit が薄い。

## 5. next action (user 判断)

- (推奨) ticket close、 Phase 1.5 で運用継続。 user が「全 player 欲しい」 と判断後 option A で再起動
- (代替) option A 着手 → Phase 1 full まで一気に拡大
