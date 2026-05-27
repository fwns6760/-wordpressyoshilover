# 442 - DATA-INSIGHT Phase B: cohort 比較 enrichment

## meta

- status: CLOSED (repo + tests OK, deploy 待ち)
- priority: P1
- owner: Claude
- lane: data-insight / render augment
- created: 2026-05-27
- closed: 2026-05-27
- doc_path: doc/done/2026-05/442-DATA-INSIGHT-cohort-comparison-enrichment.md
- parent: 439 (publish queue restore 7 signals)

## 背景

439 で signal 復活したが、 各 anomaly 記事の本文は「単独数字」 のまま
(例: 「OPS 0.950」 とだけ)。 user 報告「同じネタばかり」 を解消するには
metric 値そのもの以外の切り口 (cohort 比較) を入れて 同じ metric でも
「対 league 平均 +0.080」 / 「1 位 田中 0.420 まで -0.130」 等の補助
context で記事 variety を出す必要がある。

## 実施

`src/analysis/anomaly_article_publisher.py`:

- 新規 `_compute_league_cohort_stats()`: 1 query で league AVG + COUNT、
  1 query で top1 (player, team, value) を取得。 league filter (セ/パ)
  対応。 data 不足 / error 時は `{}`。
- 新規 `_format_cohort_diff_rows()`: cohort + player_value から
  「平均との差」 「1 位との差」 の markdown table 2 行を生成。
- `_render_unified_article()`: cohort 計算 + 「このデータについて」 table
  に 2 行 prepend (cohort 空時は no-op)。

cohort 値は player_rank_info 由来の value を base に diff 計算。
data 不足時 (snapshot_date 無し / AVG None / top1 無し) は cohort_rows=[]
で empty に fallback、 既存 body と完全互換。

## verify

- `pytest tests/test_insight_quality_gate.py tests/test_milestone_article_ranking_table.py tests/test_insight_step3_scope_expansion.py`: 23 passed
- in-memory db smoke: 6 player の OPS sample で「+0.022 (平均 0.798)」
  「−0.130 (1 位: A(g) 0.950)」 形式で出ることを確認
- AST OK

## 受け入れ条件

- [x] cohort helper 2 関数追加 + 1 query AVG / 1 query top1
- [x] _render_unified_article に cohort_rows 挿入 (空時 no-op)
- [x] 既存 23 tests pass (body format 既存 assert に regression 無し)
- [ ] deploy (`insight-nightly` Job 既 image rebuild、 anomaly publish path も
      同 image) + 次 publish で 「| 平均との差 |」 / 「| 1 位との差 |」 row 確認
- [ ] 「同じネタばかり」 解消 next-day observe (cohort 行が記事 variety 体感
      に効くか定性確認)

## Codex scope 重複回避

Codex は spec/x-impression-plan Phase 6-10 (X API spend cap 関連) と
mail/x_post lane を扱う。 本 ticket は `anomaly_article_publisher.py` 内
WP article render path で、 Codex の x_post_* / share-x-cand path とは
完全別 module、 衝突無し。

## blast radius

- WP anomaly 記事の 「このデータについて」 table が 2 行増 (cohort data
  取れた時のみ)
- DB load: nightly publish 中 1 候補あたり 2 extra SELECT (AVG / top1)、
  insight.db read-only で軽い
- rollback: 該当 commit revert で即可、 body format 互換 (cohort_rows
  空時は旧形式と一致)
