# 413-INSIGHT-pitcher-last-n-games-min-sample-gap

## 1. ticket header

- **status**: READY (Claude 自律進行可能、 narrow fix、 403 Stage A3 follow-up)
- **priority**: P2 (リリーフ投手の publish 機会喪失、 starter は影響なし)
- **owner**: Claude / **lane**: Claude
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/87
- **発見**: 2026-05-20 21:00 fire 解析で マルティネス ERA / K_per_9 last_5_games `insufficient_sample` (sample=5 IP, min=10) で publish skip

## 2. 事実 gap

`src/analysis/insight_quality_gate.py` の `min_sample_for_metric` 関数:

```python
if scope:
    if is_batter:
        scope_specific = {
            "last_3_games": 8,
            "last_5_games": 12,
            "last_10_games": 20,
        }
        if scope in scope_specific:
            return scope_specific[scope]
        # ...
    if is_pitcher:
        if scope.startswith("last_") and scope.endswith("_appearances"):
            return 0
        if scope.startswith("last_") and scope.endswith("_ip"):
            ...
# fallback
if is_pitcher:
    return int(thresholds.get("min_sample_pitcher_ip", 10))
```

**gap**: 投手 metric (ERA / K_per_9) で scope=`last_5_games` の場合、 `_appearances` / `_ip` suffix にマッチせず → fallback 10 IP に到達。 リリーフ投手は last_5_games (= 巨人 5 試合 window) で 1-3 IP しか投げない → 常に skip。

21:00 fire 証拠:
```
'focus_player': 'マルティネス', 'metric_name': 'ERA',
'sample_size': 5, 'scope': 'last_5_games', 'min_sample': 10,
'status': 'skip_data_quality_sample', 'reason': 'insufficient_sample'
```

## 3. 影響

- リリーフ投手 (マルティネス / 高梨雄平 / バルドナード 等) の rate metric publish 機会喪失
- starter (戸郷 / 山崎伊織 等) は last_5_games で 25-30 IP 投げるため影響なし
- 403 cutover で「last_5_games default」 にしたが、 投手 rate には適していない

## 4. fix 方針 (narrow)

オプション A (推奨): 投手 last_N_games scope の min_sample を audit-based 値に下げる
- last_3_games: 2 IP (リリーフ 1 試合 1 IP 想定)
- last_5_games: 3 IP
- last_10_games: 5 IP

```python
if is_pitcher:
    pitcher_games_min = {
        "last_3_games": 2,
        "last_5_games": 3,
        "last_10_games": 5,
    }
    if scope in pitcher_games_min:
        return pitcher_games_min[scope]
    # ... existing appearances / ip dispatch
```

オプション B: 投手 rate metric の default scope を `last_5_appearances` に変更 (publish_default_set の per-role 分岐)、 batters は last_5_games 維持
- 複雑、 別 ticket (403 Stage C 寄り)

本 ticket はオプション A の narrow fix。

## 5. 不可触

- 348 whitelist / 349 cooldown / 356 quality gate の他 check
- 打者 metric の min_sample (Stage A3 で確定値)
- env / Secret / Scheduler / DB schema
- [[403]] の他 cutover 経路

## 6. 成功条件

- targeted pytest pass (投手 last_5_games min_sample = 3 等)
- 次 fire でマルティネス / 高梨 ERA last_5_games が publish 候補化 (cooldown 等の他 gate は別問題)
- regression 0

## 7. 動作確認

- ローカル: targeted pytest 緑
- live deploy 後: 07:00 fire log で投手 last_5_games の `insufficient_sample` 件数減少確認
