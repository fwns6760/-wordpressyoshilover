# 415-INSIGHT-vs-left-right-pitcher-split

## 1. ticket header

- **status**: PARKED (重要、 user 判断後着手、 approach 選択 pending)
- **priority**: high (user 明示「左右選手は重要」 2026-05-20 PM)
- **owner**: Claude / **lane**: Claude
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/91
- **split from**: [[404]] (404 の vs 左右投手 sub-feature を独立 ticket 化)
- **related**: [[403]] (期間 cut 体系 lock 済)

## 2. 目的

打者 × vs 左右投手 platoon split。 「対左投手 直近30打席 .280 / 対右 .250」 等の fan-facing 切り口。

## 3. feasibility (2026-05-20 audit)

**核心問題**: NPB box の `atbats_json` は per-PA result text のみで、 **per-PA 対戦投手情報なし** = 「岡本が 4 PA 立ったうち、 何 PA 対左か」 が直接取得不可。

**2 approach 候補**:

### (a) starter 限定 approx

- 「打者 1-3 PA = starter 対戦と仮定」
- starter の throws を roster JSON から lookup
- 列追加: `pitching_logs.pitcher_throws TEXT` ('L'/'R'/'S')
- 制約: starter が 5-6 回降板 → 7-9 PA 中 starter 対戦は 3-4 PA のみ、 残りは reliever (各 inning 別投手) で精度低下
- 工数: 2h (schema + roster fill + 限定 publisher)
- 精度: 低 (リリーフ含む split が出ない)

### (b) inning-by-inning data 追加 ingest

- NPB box の inning-by-inning pitcher record を解析
- 各 inning に誰が投手か、 打者の PA がどの inning か追跡
- 列追加: `atbats_json` 拡張 + `pitching_logs.start_inning`/`end_inning`
- 工数: 6-8h (NPB box table 構造解析、 inning marker parse、 atbats_json 拡張、 backfill)
- 精度: 高 (per-PA L/R 正確に追跡)

## 4. user 判断 pending

(a) approx ですぐやる / (b) 重工事だが本気で精度確保 のどちらを選ぶか。 spec 「最近 30 打席対左 .280」 の信頼性が要件次第。

## 5. 不可触

- [[403]] / [[404]] 既 cutover 経路
- 348 whitelist / 349 cooldown / 356 quality gate
- env / Secret / Scheduler / DB schema (本 ticket 単独では何も変えない)

## 6. 着手判断

user が approach (a) or (b) を指定 + GO で着手。 現状 PARKED で重要 ticket として doc 保持。
