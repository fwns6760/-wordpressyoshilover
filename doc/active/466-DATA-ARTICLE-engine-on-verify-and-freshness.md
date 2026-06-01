# 466 DATA-ARTICLE エンジン ON verify + 新鮮さ cadence 最適化

- **種別**: verify + 実装 / **priority**: P1(新鮮さ=唯一の明確勝ち筋) / **effort**: S(verify)〜M
- **親**: 443 / 設計: `455...md` §16 / §17 Phase2D / GH: #130
- **status**: READY(read-only verify 先行)

## 背景(深掘り 1次source・要 production verify)

- データ記事エンジン全体が `ENABLE_DATA_INSIGHT_AUTO_DRAFT`(`insight_nightly.py` L89-90、default `"0"`)依存。**prod で `1` か未確認**。off なら記事ストリームが止まっている。
- Scheduler の発火便数/時刻は repo 非保持(GCP 側)。**新鮮さ(試合後即時生成)が実働しているか未確認**。
- 唯一の明確な勝ち筋が「更新頻度」(§15)なので、ここが実働していないと戦略の前提が崩れる。

## ゴール

1. **read-only verify**: prod の `ENABLE_DATA_INSIGHT_AUTO_DRAFT` 実値、`insight-nightly` Job の Scheduler cadence/直近 execution、直近の `【巨人データ】` post 生成実績(WP)を確認。
2. off / 不足なら: フラグ ON / cadence 調整(試合後即時に寄せる)を deploy(§11 user-gate: scheduler/env 変更は user 判断)。

## 対象

- read-only: `gcloud run jobs executions list`、scheduler describe、WP REST で直近 `【巨人データ】` post 確認。
- 変更系(env/scheduler)は **user 判断後**に実施。

## やる / やらない

- やる: read-only verify(自律)、結果報告、必要なら変更案提示。
- やらない: **env/scheduler を user 判断なしに変更**(§11 境界)、publish 直書き。

## 成功条件

- エンジン ON/OFF と新鮮さ cadence の実態が確定。
- off/不足なら user 判断を1件で上げ、go 後に最小変更で ON / cadence 最適化。

## 依存

§11 user-gate(env/scheduler 変更)。verify 自体は自律。
