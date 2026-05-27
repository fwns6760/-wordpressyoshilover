# 439 - DATA-INSIGHT publish queue restore 7 signals (user override 2026-05-27)

## meta

- status: REPO_IMPL_TESTED (deploy 待ち)
- priority: P1
- owner: Claude
- lane: data-insight / publish queue
- created: 2026-05-27
- doc_path: doc/active/439-DATA-INSIGHT-publish-queue-restore-7-signals.md
- supersedes_partial: 2026-05-15 commit `f8c9e57` 「マニアック detectors drop」 user 判断

## 背景

user 報告 「データ記事 (ポスト編) が同じネタばかり」。 真因調査で:

- render 関数 15 種 (`_RENDERERS` map) は実装済
- `ALL_ANOMALY_SIGNALS` tuple が 8 種限定 → 7 種 detector candidate が
  publish queue (`publish_anomaly_drafts` → `fetch_pending_anomalies`)
  から弾かれていた
- 削除元は 2026-05-15 commit `f8c9e57` (memory
  `feedback_data_insight_user_preferences_2026_05_15` 「サバメ NG」 と整合)

## user 判断

2026-05-27 user 明示 「全部」: 「同じネタばかり」 を解消するため、
5/15 で drop した 7 signal を ALL_ANOMALY_SIGNALS に **復活**。
metric whitelist (insight_whitelist) で block される 3 種 (BABIP / FIP /
STAT_DELTA) は publish 実件数を next-day observe で確認、 必要なら
whitelist 側の更新を follow-up ticket で扱う。

## 実施 (repo)

- `src/analysis/insight_anomaly_detector.py` ALL_ANOMALY_SIGNALS を
  8 → 15 entries に拡張 (BABIP / FIP / GIANTS_TOP / PACE_HR / HIDDEN_OPS /
  HIT_STREAK / STAT_DELTA を復活)
- 既存 comment block を 5/15 履歴 + 5/27 override の二段構成に更新
- 既存 detector / render / result dict は 5/15 lock 時点で全 signal 対応済、
  追加実装不要 (minimum-diff)

## tests

- `pytest tests/test_insight_anomaly_detector.py` 16 passed
- ALL_ANOMALY_SIGNALS を動的 iterate する test なので tuple 拡張で自動 cover

## 受け入れ条件

- [x] ALL_ANOMALY_SIGNALS = 15 entries
- [x] targeted pytest pass
- [ ] deploy (insight-nightly Job image rebuild + 次 nightly fire)
- [ ] next-day observe で publish 実件数 / signal mix 確認、 BABIP / FIP /
      STAT_DELTA が whitelist block で 0 件なら follow-up 起票
- [ ] visual variety 確認 (若手 quota 新 eyecatch 当選含む)

## blast radius

- publish 数増 (signal 8 → 15、 推定 +30-50% draft 量)
- cost: detector 自体は既に nightly で全 signal run 済、 計算 cost 増無し。
  publish 数増による Cloud Run guarded-publish / mail / WP REST 増 minor
- rollback: ALL_ANOMALY_SIGNALS を 8 entries に戻す revert commit で即可
