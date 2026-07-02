# 426: Artifact Registry safe cleanup preflight

## meta

- owner: Codex A
- type: ops-cost-reduction-preflight
- status: PREFLIGHT_STOPPED
- created: 2026-05-23
- updated: 2026-05-23
- priority: P0.5
- parent_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/97
- gh_issue: TBD

## 1. 背景

GCP cost read-only 監査で Artifact Registry repository `yoshilover` が約 98-103GB あることを確認した。
公式単価は 0.5GB free 後 $0.10/GB/month で、`yoshilover` だけで約 $10/月を超える可能性がある。

既に cleanup policy は存在するが、容量はまだ大きい。

## 2. 目的

削除前に live image / rollback image / cleanup policy の整合を確認し、安全に削れる version の条件を決める。
この ticket では Artifact の削除はしない。

## 3. 不可触リスト

- Artifact image / version / tag の delete
- cleanup policy update
- Cloud Run service / job update
- deploy
- Secret / env
- Scheduler
- WordPress / publish / mail / SEO / X

## 4. 影響範囲

対象 package:

- `yoshilover-fetcher`
- `manual-intake-service`
- `publish-notice`
- `x-post-mail-lane`
- `insight-nightly`
- `guarded-publish`
- その他 `yoshilover` repository 内 package

## 5. 実行手順

1. Cloud Run services / jobs の current image digest / tag を read-only で一覧化
2. Artifact cleanup policy の keep 条件と current live digest / tag を照合
3. package ごとの version count / age / tag state を確認
4. rollback に最低限残す範囲を決める
5. 削除候補を list 化する
6. user GO があるまで delete / policy update はしない

## 6. STOP条件

- live image digest が cleanup keep 条件に入っていない
- rollback image が特定できない
- current image と package の対応が不明
- Cloud Run / Scheduler / deploy の変更が必要になる
- 削除候補に current live image が含まれる

## 7. 成功条件

- 削除候補が package / digest / tag / age 付きで説明できる
- current live image は削除対象外と明記されている
- rollback image の保持方針が明記されている
- 実削除は別 user GO まで行わない

## 8. 実行ログ

- 2026-05-23: GitHub child issue 作成は `api.github.com` 接続失敗 / `gh` token invalid により未作成。parent Issue #97 は作成済み。
- 2026-05-23: Cloud Run services / jobs の current image を read-only で一覧化。
- 2026-05-23: 主な live image:
  - service `yoshilover-fetcher`: `yoshilover/yoshilover-fetcher:x-intent-with-url-b5dd821`
  - service `manual-intake-service`: `yoshilover/manual-intake-service:baseballking-og-fallback-1779416528`
  - job `publish-notice`: `yoshilover/publish-notice:prefilter-a32bd79`
  - job `x-post-mail-lane`: `yoshilover/x-post-mail-lane:player-dedup-60d18b5`
  - job `insight-nightly`: `yoshilover/insight-nightly:dedup-same-day-cap-d724f0c`
  - job `guarded-publish`: `yoshilover/guarded-publish:8262003`
  - job `guarded-publish-lane-zz`: `yoshilover/guarded-publish:0f5e95a`
- 2026-05-23: cleanup policy の keep tag list を確認。`baseballking-og-fallback-1779416528`, `x-intent-with-url-b5dd821`, `dedup-same-day-cap-d724f0c`, `player-dedup-60d18b5`, `8262003`, `0f5e95a` などは含まれている。
- 2026-05-23: `publish-notice` の現行 live tag `prefilter-a32bd79` は cleanup policy の keep tag list に含まれていない。
- 2026-05-23: Artifact Registry 上の `publish-notice:prefilter-a32bd79` digest は `sha256:1757e6fd...`。package version count は 25。
- 2026-05-23: STOP 条件「live image digest/tag が cleanup keep 条件に入っていない」に該当したため、削除候補作成と削除実行には進まず停止。
- 2026-05-23: Artifact image / version / tag delete は未実施。cleanup policy update も未実施。

## 9. 判定

現時点で Artifact Registry の即時削除は危険。

理由:

- `publish-notice` はメール導線で、Cloud Run Jobs の最大 cost driver。
- その現行 live image が cleanup keep tag list に入っていない。
- recent 20 keep により現時点では守られている可能性が高いが、今後の build 増加で押し出されると rollback / 現行保持の説明が弱くなる。

## 10. 次の安全手順

1. `publish-notice:prefilter-a32bd79` または現行 digest を cleanup keep 条件に追加する。
2. `gcloud artifacts repositories describe yoshilover` で keep 条件に入ったことを確認する。
3. その後、古い untagged / non-live / rollback 対象外 version だけを削除候補として package / digest / tag / age 付きで出す。
4. 実削除は別 ticket と別 user GO で 1 package ずつ行う。

## 11. 2026-07-02 実行と CLOSE(Claude 直接実行、2026-05-12 全権体制)

- user 指示「安くなるならやって。あと恒久的対策」により、preflight を超えて実削除+policy 更新を実行
- 手順: ①全 jobs/services の live image (tag→digest 解決) を保護リスト化 ②各 package 最新10+live を残して削除 ③恒久 policy 適用
- 結果: **132 versions 削除**(x-post-mail-lane 65→10 / yt-shorts-gen 32→10 / data-site-publisher 33→12 / manual-intake 28→10 / publish-notice 21→10 ほか、cloud-run-source-deploy 側も 12 削除)
- live image の削除件数: 0(全 live digest 保護を log で確認)
- PIN 検出: data-site-publisher の `cluster-slug-3e4b6d26` / `gsc-indexer-2364c3c3`(最新10圏外だが稼働中)→ policy `keep-live-pins` で恒久保護
- 恒久 policy(yoshilover / cloud-run-source-deploy 両 repo): delete-untagged-7d + **delete-older-30d(タグ付き含む)** + keep-recent-10 + keep-live-pins
- 付帯: `gs://baseballsite_cloudbuild` に 30日 lifecycle 設定
- 想定削減: 61GB → 15-20GB 目安、約 $6/月 → $1.5-2/月(AR size 反映は遅延あり、翌日確認)
- 実行 log: Claude session scratchpad `ar_cleanup_log.txt`(削除全件・PIN・live 保護の記録)
- status: CLOSED
