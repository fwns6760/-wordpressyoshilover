# 217 緊急 hotfix:WP publish gate 原則公開化

## meta
- number: 217
- type: hotfix / dev
- status: CLOSED
- priority: P0(緊急 hotfix)
- lane: Codex(impl)/ Claude(dispatch)
- created: 2026-04-27
- parent: 183 publish gate aggressive relax / 200 scanner subtype fallback

## Close note(2026-04-28)

Follow-up guarded-publish images `25f176b` / `c328772` superseded this live handoff. Current precision fixes are tracked in 242-A / 242-D / 242-D2 / 242-E and the remaining 242-B candidate.

## background
- 63795 が `hard_stop:injury_death` で refused 連発
- WP publish 流量大幅減、ファン視点 roster movement(怪我 / 復帰 / 昇格 / 抹消)が一律 hard_stop
- X 自動投稿は user 手動運用なので publish 自体は緩める方針

## 実装内容(3 commit)
- `b36c30c` 217: ingestion filter 緩和(実質、番号衝突 — 後で **218** renumber 必要)
  - src/rss_fetcher.py: not_giants_related keyword 拡張 + 公式 SNS 例外化 + social_too_weak threshold 緩和 + stale_postgame 36h 拡張
  - tests/test_ingestion_filter_relaxation.py: 10 tests
- `579401a` 217: 緊急 hotfix WP publish gate 原則公開化(本体)
  - src/guarded_publish_evaluator.py: injury_death を分解
    - `death_or_grave_incident` → HARD_STOP 維持(死亡 / 危篤 / 重症 / 入院 / 手術 / 全治長期 / source なし診断断定)
    - `roster_movement_yellow` → publishable Yellow(抹消 / 登録 / 昇格 / 降格 / 合流 / 離脱 / 復帰 / 軽症 / IL / 入団 / 引退 + source あり)
  - src/guarded_publish_runner.py: yellow_log に warning + manual_x_post_block_reason 記録
  - src/publish_notice_email_sender.py: roster_movement_yellow は manual_x_post_candidates suppressed + mail body に [Warning]
  - tests: 63795 fixture + 10+ tests
- `b03890c` 217: death_or_grave_incident を HARD_STOP_FLAGS に明示追加(補完)

## next_action
- **GCP 反映**(authenticated executor):
  - guarded-publish image 再 build + Job update(b03890c tag)
  - publish-notice image 再 build + Job update(同上)
  - draft-body-editor は本便 scope 外、不要
- 反映後、63795 を再判定(publishable Yellow 期待)
- mail 送信内容で `[Warning] roster movement 系記事、X 自動投稿対象外` 確認
- 7 日観察で誤検出 / 過剰公開なし verify

## 番号衝突注記
- `b36c30c` は実質 **ingestion filter 緩和**(commit message 「217」だが内容は別 scope)
- 後続 doc-only 便で **218** に renumber 整理予定(commit hash 不変、board 上で 218 として記録)

## acceptance
- 63795 publishable Yellow 化 verify
- death / 重大事故 / source なし診断 は HARD_STOP 維持 verify(危険 hard_stop flag 不変)
- mail に warning + X 候補 suppressed verify
- pytest 1498 pass / 1 fail(readiness flaky 既知)維持

## not goals
- web scraper 追加(210d 別便)
- source 拡張(210b 完了済、scraper 待ち)
- X live 自動投稿(手動運用継続)

## 関連 commit
- `b36c30c` ingestion filter 緩和(実質 218)
- `579401a` publish gate hotfix 本体
- `b03890c` hard-stop set 補完
