# 183 publish-gate aggressive relax(verify + flag 大幅緩和)

## meta

- number: 183
- owner: Claude Code(設計 / 起票)/ Codex B(実装)
- type: dev / quality / config relax
- status: **CLOSED**
- priority: P0.5(全公開モード強化、publish 流量大幅増、user 明示意向)
- lane: B
- created: 2026-04-26
- landed_in: `f5b91a3`

## 背景

182 で prose_length 緩和(100→50)着地。
ただし他の post-cleanup verify + evaluator hard_stop が依然 strict、yellow 6 件 / 18 candidate のうち publishable は限定的。

user 指示「結構緩めてよい」: **全公開モード強化**、quality 度外視で流量優先、ledger は別途記録(184)。

## ゴール

publish gate を大幅緩和:
- post-cleanup verify 3 種を warning_only 降格(reject せず log 残して publish 通す)
- evaluator hard_stop 数種を repairable_flag 降格(no-op 化)
- 結果: 18 candidate の大半が publish 通る見込

## 仕様

### Phase A: post-cleanup verify 緩和(`src/guarded_publish_runner.py`)

`_post_cleanup_check` line 225-275 の 4 verify のうち、`body_empty` 以外を **warning_only**(log 残し、True return)に降格:

| verify | 現状 | 新挙動 |
|---|---|---|
| `body_empty` | reject(False return) | **不変**(本当に空は publish 不可) |
| `prose_lt_50`(182 で 50 化) | reject | reject(MIN_PROSE_AFTER_CLEANUP env で override 可) |
| `title_subject_missing` | reject | **warning_only**(log + ledger に記録、publish 通す) |
| `source_anchor_missing` | reject | **warning_only** |
| `source_hosts mismatch` | reject | **warning_only** |

env opt-out 可:
- `STRICT_TITLE_SUBJECT=true` → 旧 reject 挙動復活
- `STRICT_SOURCE_ANCHOR=true` → 同上
- `STRICT_SOURCE_HOSTS=true` → 同上

default は **warning_only**(緩和、publish 通す)。

### Phase B: evaluator hard_stop 緩和(`src/guarded_publish_evaluator.py`)

`HARD_STOP_FLAGS` set から以下 2 件を **REPAIRABLE_FLAGS** に降格(135 同パターン):
- `subtype_unresolved`(subtype 不明 → publish 可)
- `heading_sentence_as_h3`(heading order 違反 → publish 可)

`REPAIRABLE_FLAG_ACTION_MAP` に no-op action 追加(`warning_only:relaxed_for_breaking_board`)。

### Phase C: tests

- `tests/test_guarded_publish_runner.py`:
  - `title_subject_missing` シナリオ: default で publish 通る verify(warning_only)
  - `STRICT_TITLE_SUBJECT=true` で reject 復活 verify
  - 同様に source_anchor / source_hosts
- `tests/test_guarded_publish_evaluator.py`:
  - `subtype_unresolved` flag → repairable で publishable=True verify
  - `heading_sentence_as_h3` flag → repairable で publishable=True verify
  - 既存 5c845a8(135 降格)同パターン test 拡張

## 不可触

- WSL crontab(全行)
- Cloud Run Job env 直接編集(本 ticket は code のみ、env 設定は別 commit)
- 168 ledger schema 不変
- 165 / 170 / 171 / 172 / 178 等で land 済の挙動を一切壊さない
- automation.toml / .env / secrets / Cloud Run / Scheduler / Storage
- baseballwordpress repo
- WordPress / X
- requirements*.txt
- 他の hard_stop flag(unsupported_named_fact / obvious_misinformation / cross_article_contamination 等)→ **不変**(safety、危険な flag は維持)
- 並走 task touching file 触らない:
  - 184(ledger integration)が touching: `bin/*entrypoint.sh` / `src/cloud_run_persistence.py` / `src/repair_provider_ledger.py`

## acceptance

1. ✓ post-cleanup verify 3 種 warning_only 降格 + env strict mode 復元可
2. ✓ HARD_STOP_FLAGS から 2 件 remove + REPAIRABLE_FLAGS に追加
3. ✓ tests 8-12 件追加(各 verify の default + strict 切替 verify)
4. ✓ pytest baseline(182 land 後)+ 新 tests pass
5. ✓ 既存挙動 invariant: body_empty reject / prose_lt_50 reject / 危険 hard_stop flag 維持
6. ✓ live publish / Cloud Run deploy / push: 全て NO

## Hard constraints

- 並走 task `b5068cqna`(182)/ 184 と touching file 完全 disjoint
- `git add -A` 禁止、stage は **`src/guarded_publish_runner.py` + `src/guarded_publish_evaluator.py` + `tests/test_guarded_publish_runner.py` + `tests/test_guarded_publish_evaluator.py`** だけ
- 既存 dirty(`M CLAUDE.md`)/ 既存 untracked: 触らない
- `git push` 禁止
- pytest baseline 維持、pre-existing fail 0 維持
- 新 dependency 禁止
- 危険 hard_stop flag(unsupported_named_fact / obvious_misinformation / cross_article_contamination)触らない(safety lock)
- 165 / 168-182 で land 済の挙動を一切壊さない

## Verify

```bash
cd /home/fwns6/code/wordpressyoshilover
python3 -m pytest tests/test_guarded_publish_runner.py tests/test_guarded_publish_evaluator.py -v 2>&1 | tail -30
python3 -m pytest 2>&1 | tail -5
python3 -m pytest --collect-only -q 2>&1 | tail -3
```

## Commit

```bash
git add src/guarded_publish_runner.py src/guarded_publish_evaluator.py tests/test_guarded_publish_runner.py tests/test_guarded_publish_evaluator.py
git status --short
git commit -m "183: publish-gate aggressive relax (post-cleanup verify 3 種 warning_only + hard_stop 2 件降格、env strict mode 復元可、全公開モード強化)"
```

`.git/index.lock` 拒否時 → plumbing 3 段 fallback。

## 完了報告

- changed files
- pytest collect: <before> → <after>
- new tests: count
- warning_only 化: title_subject / source_anchor / source_hosts 3 件 verify
- hard_stop 降格: subtype_unresolved + heading_sentence_as_h3 2 件 verify
- env strict mode 復元 verify: yes
- 危険 hard_stop flag 不変 verify: yes(unsupported_named_fact / obvious_misinformation / cross_article_contamination)
- 既存挙動破壊: なし
- WP write / Cloud Run deploy / push: 全て NO
- commit hash

## stop 条件

- 危険 hard_stop flag に手をつける必要発覚 → 即停止 + 報告(別 ticket、user 判断)
- 既存 test 大規模影響 → 即停止 + 報告
- 並走 task scope と衝突 → 即停止 + 報告
- pytest baseline を割る → 即停止 + 報告
