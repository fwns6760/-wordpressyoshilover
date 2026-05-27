# 438 - DATA-INSIGHT young-player eyecatch scrape (user override 2026-05-27)

## meta

- status: CLOSED
- priority: P2
- owner: Claude
- lane: data-insight / eyecatch
- created: 2026-05-27
- closed: 2026-05-27
- doc_path: doc/done/2026-05/438-DATA-INSIGHT-young-player-eyecatch-scrape-override.md
- supersedes_partial: scripts/fetch_player_eyecatch_wikipedia.py docstring 「Out of scope: 巨人公式 / NPB 公式 image scrape」

## 背景

`config/player_eyecatch_map.json` に画像 MISSING の 16 名のうち、 若手 1 軍候補
7 名 (石塚裕惺 / 田和廉 / 平山功太 / 三塚琉生 / 岡田悠希 / 小濱佑斗 / 竹丸和幸)
が team fallback (巨人マーク media 63578) になっており、 data-insight
記事の visual variety を圧迫していた。 萩原哲は 2025-11 退団報道のため除外、
竹丸和幸を追加。

## user 判断

2026-05-27 user 明示 「yahoo もつかう」: 既存 `fetch_player_eyecatch_wikipedia.py`
docstring の Out of scope (Yahoo スポーツナビ / 一球速報 portrait の scrape)
を若手 quota visual variety 目的で **override**。 source URL は WP /media
caption / description に必ず記録、 後追い差し替え可能とする。

## 実施

- `scripts/scrape_player_eyecatches_yahoo.py` 新規 (one-off uploader、
  dry-run / commit 2 mode、 caption に source URL 自動付与)
- 7 名 upload: media id 72777-72783
  - 石塚裕惺 / 田和廉 / 平山功太 / 三塚琉生 / 竹丸和幸 = Yahoo スポーツナビ
  - 岡田悠希 = Wikimedia Commons (CC-BY-SA)
  - 小濱佑斗 = 一球速報 (Omyutech)
- `config/player_eyecatch_map.json` 追記 + `.bak-2026-05-27` backup
- `scripts/fetch_player_eyecatch_wikipedia.py` docstring に override 注記

## 受け入れ条件

- [x] 7 名分 media upload 完了 (id 72777-72783)
- [x] caption に source URL 記録 (1 件 verify 済: media 72777)
- [x] map 追記 + backup
- [x] script docstring の override 明記

## follow-up

- 439 (Phase A): ALL_ANOMALY_SIGNALS 復活で publish queue 変動後、
  若手 selection に新 eyecatch が当たるか next-day observe
