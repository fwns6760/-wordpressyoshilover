# 415-INSIGHT-vs-left-right-pitcher-split

## 1. ticket header

- **status**: CLOSED LIVE_DEPLOYED_VERIFIED ((a) approx + (b) strict 両方 LIVE 並列稼働)
  - **(a) approach LIVE**: starter 限定 approx で commit `378249d` + `f621457` landed、 wire `insight_nightly.py` L300-310 (last_10_games scope L/R loop)、 post 69963 「吉川尚輝 対右投手打率 0.412」 publish 確認
  - **(b) strict LIVE**: commit `dd4f5cc` で at_bat_details + npb_pitcher_throws JOIN の per-PA strict aggregator + publisher 完成、 dedup key 別 (VS_LR_STRICT vs VS_LR) で (a) と並列 publish。 production verify (2026-05-21 15:00 JST fire):
    - post 70055 「佐々木 対左投手 (per-PA) 打点 2 で巨人内 1 位 (直近10試合)」
    - post 70057 「ダルベック 対右投手 (per-PA) 打点 1 で巨人内 1 位 (直近10試合)」
  - GH Issue #91 close 候補
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

**2026-05-20 PM 更新**: 415 (b) source も無料で同定済 — `playbyplay.html` (= [[405]] と同 source) に「（投手交代） A → B」 marker + per-PA 打者名 + 結果が記載。 [[405]] 実装 (per-PA detail table) と statefully overlap、 同時実装が効率的 (= 共通 parser + table)。

### MVP status

approach (a) は **2026-05-20 PM landed 済** (commit pending、 image `415-vs-lr-mvp` gen 81 deploy 済)。 production dry-run で「キャベッジ 対左投手打率 0.263」 等 verify。 limitation: starter 限定、 reliever 対戦は集計外 (article body に明記)。

## 4. user 判断 pending

(a) approx ですぐやる / (b) 重工事だが本気で精度確保 のどちらを選ぶか。 spec 「最近 30 打席対左 .280」 の信頼性が要件次第。

## 5. 不可触

- [[403]] / [[404]] 既 cutover 経路
- 348 whitelist / 349 cooldown / 356 quality gate
- env / Secret / Scheduler / DB schema (本 ticket 単独では何も変えない)

## 6. 着手判断

user が approach (a) or (b) を指定 + GO で着手。 現状 PARKED で重要 ticket として doc 保持。
