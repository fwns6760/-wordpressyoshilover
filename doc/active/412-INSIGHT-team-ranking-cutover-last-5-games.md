# 412-INSIGHT-team-ranking-cutover-last-5-games

## 1. ticket header

- **status**: READY (Claude 自律進行可能、 narrow fix、 403 Stage A4 follow-up)
- **priority**: P1 (team metric publish 全停止中、 cutover 完成度補強)
- **owner**: Claude / **lane**: Claude
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/86
- **発見**: 2026-05-20 21:00 fire 解析で `team_results` が `'scope': 'last_7d'` で `skip_dedup_cooldown` 多発、 [[403]] Stage A4 cutover に team_ranking が含まれていなかった

## 2. 事実 bug

`src/analysis/insight_nightly.py` L860-865 (推定):
```python
default_team_jobs = [
    {"metric": "HR", "scope": "last_7d"},
    {"metric": "AVG", "scope": "last_7d"},
    {"metric": "ERA", "scope": "last_7d"},
    ...
]
```

403 Stage A4 cutover (commit `03a49ee`) では default_jobs (publish_default_set) と counting_scopes と split scope を切替えたが、 **team_ranking call 経路の scope は last_7d のまま放置**。

21:00 fire の log で team_results が:
```
{'metric': 'HR', 'reason': 'cooldown_active', 'scope': 'last_7d', 'status': 'skip_dedup_cooldown'}
{'metric': 'AVG', 'reason': 'cooldown_active', 'scope': 'last_7d', 'status': 'skip_dedup_cooldown'}
{'metric': 'ERA', 'reason': 'cooldown_active', 'scope': 'last_7d', 'status': 'skip_dedup_cooldown'}
```

last_7d scope で過去 publish 済の team metric が dedup cooldown で blocked。

## 3. fix 方針 (narrow)

`insight_nightly.py` の team_ranking call で使う scope を `last_7d` → `last_5_games` に切替。 `team_ranking_publisher._scope_window` は 403 Stage A2 で last_N_games dispatch 済 (commit `dabe355`)、 backend は対応済。

## 4. affected files

- `src/analysis/insight_nightly.py` (team_ranking 呼出箇所、 grep 必要)
- tests があれば修正 (test_team_ranking 等)

## 5. 不可触

- team_ranking_publisher.py 本体 (Stage A2 で last_N_games 対応済)
- 348 whitelist / 349 cooldown / 356 quality gate
- env / Secret / Scheduler / DB schema
- [[403]] の他 cutover 経路 (default_jobs / counting / split — 既切替済)

## 6. 成功条件

- 次 fire (07:00 JST) で team_ranking が `scope=last_5_games` で動作
- `team_results` の status が `published` / `skip_max_per_run` 等正常応答 (dedup_cooldown last_7d ではなくなる)
- targeted tests pass + regression 0

## 7. 動作確認

- ローカル: targeted pytest 緑
- live deploy 後: 07:00 fire log で `scope=last_5_games` を確認、 team metric publish 1+ 件、 last_7d cooldown 0 件
