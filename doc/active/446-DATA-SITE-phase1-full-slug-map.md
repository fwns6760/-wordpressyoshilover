# 446 data-site Phase 1 full — 残り 54 player slug 整備 + 拡大

## 1. ticket header

- **ticket id**: 446
- **status**: DRAFT (defer、 user 判断待ち)
- **owner**: Claude Code
- **lane**: data-site / phase 拡大
- **created**: 2026-05-28
- **priority**: P3 (Phase 1.5 で 31 player ある = MVP 充足、 Phase 1 full は SEO 流入観察後 検討)
- **parent**: 444 (data-site Phase 1.5)
- **github_issue**: PENDING

## 2. 背景

ticket 444 で Phase 1.5 (一軍 active 31 player) まで実装済。 Phase 1 full = active=True AND role=player 全 84 名 (manager/coach 除く) で残り **54 player 追加** が必要。

block 真因: data_site_slug.py の `_PLAYER_SLUG_MAP` は 31 名分 hardcode、 残り 54 名分 romaji slug が未マッピング。 pykakasi 未 install、 手動で姓名 → romaji を 1 人ずつ調査 必要 (1 player 2-3 分 × 54 = 2-3 時間)。

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
