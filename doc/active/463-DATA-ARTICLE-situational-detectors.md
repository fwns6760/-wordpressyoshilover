# 463 DATA-ARTICLE 状況系 新角度 detector(サヨナラ/逆転/殊勲打/得点差別)

- **種別**: 実装 / **priority**: P2(parity + 差別化B) / **effort**: M
- **親**: 443 / 設計: `455...md` §16 / §17 Phase1+2B / GH: #127
- **status**: READY(データ派生可能性を先行 verify)

## 背景(深掘り 1次source)

- B は **殊勲打 / 得点差別打率** を持つ。A は **サヨナラHR DB(読み物)** を持つ。yoshilover は**いずれも未実装**。
- 重要: `at_bat_details.result_text`(「左中間ソロホームラン」「中前タイムリーツーベース」等 literal)+ `inning_no`/`half` + `inning_scores` で **サヨナラ/逆転/決勝打/得点差別 は派生可能**。だが **検知コードが repo に皆無**(walkoff/サヨナラ/逆転 grep 0件、深掘り確定)。

## ゴール

新 detector + 記事化:
1. **サヨナラ打/HR**(最終回 with 勝ち越し決着、result_text + inning_scores 判定)
2. **逆転打**(打席前後で勝敗逆転)
3. **殊勲打/決勝打**(B parity)
4. **得点差別打率**(ビハインド/同点/リード別、B parity)

`insight_anomaly_detector` 系に検知を追加 → `anomaly_article_publisher` で記事化 → dedup(349)/quality gate(356)経由。

## 対象

- `src/analysis/insight_anomaly_detector.py`(検知追加)、`anomaly_article_publisher.py`(renderer)、`insight_whitelist.json`(角度登録)。
- 判定ロジックは `at_bat_details` + `inning_scores` の read-side。

## やる / やらない

- やる: 上記4検知 + 記事化 + dedup/gate 接続 + test。
- やらない: pitch-level、ETL大改修(read-side派生のみ)、publish直書き(draft経由)。

## 成功条件

- サヨナラ/逆転/殊勲打/得点差別 の記事が production データで生成(draft)、dedup/gate を通る。
- 誤検知0(result_text/inning_scores の判定を fixture で固める)。
- targeted pytest green、production DB で1件 verify。

## 依存

`at_bat_details.result_text` / `inning_scores` の populate を production verify 先行。
