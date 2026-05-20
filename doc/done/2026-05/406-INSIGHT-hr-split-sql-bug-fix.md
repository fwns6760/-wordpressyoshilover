# 406-INSIGHT-hr-split-sql-bug-fix

## 1. ticket header

- **status**: CLOSED (LIVE_DEPLOYED_VERIFIED 2026-05-20 20:00 JST、 bl.HR error 過去 5 日 175 件 → 0 件 verified)
- **priority**: P1 (5/20 logs で確認された既存機能の壊れ、 publish が落ちている)
- **owner**: Claude / **lane**: Claude
- **依存**: なし ([[403]] と並走可能、 narrow fix)
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/78

## 2. 背景 / 事実 bug

2026-05-20 12:00 JST `insight-nightly-ndtvf` 実行 logs に以下の 7 件 error:

```
error=OperationalError:no such column: bl.HR;metric=HR;split=opponent=d
error=OperationalError:no such column: bl.HR;metric=HR;split=opponent=db
error=OperationalError:no such column: bl.HR;metric=HR;split=opponent=c
error=OperationalError:no such column: bl.HR;metric=HR;split=opponent=s
error=OperationalError:no such column: bl.HR;metric=HR;split=opponent=t
error=OperationalError:no such column: bl.HR;metric=HR;split=home_away=away
error=OperationalError:no such column: bl.HR;metric=HR;split=home_away=home
```

warn message: `player_counting_split_publish_failed`

HR の opponent split (vs 中日 / DeNA / 広島 / ヤクルト / 阪神) + home_away split (ホーム / アウェイ) **全 7 split が SQL レベルで落ちて publish 0 件**。 [[348]] の `data_ranking_player_counting_HR_split` 経路が deploy 後ずっと壊れていた可能性。

## 3. 原因確定 (audit 済、 2026-05-20)

`src/analysis/ranking_article_publisher.py`:

- L253 `aggregate_player_counting_stat`: L278 で `stat_col == "HR" and table == "batting_logs"` のとき `aggregate_player_hr_from_atbats` に dispatch している (正常)
- L937 `aggregate_player_counting_stat_split`: **同じ dispatch が無い**。 L984-995 で `SELECT bl.player_canonical, ..., SUM(bl.{safe_col})` を発行、 `safe_col='HR'` のとき `bl.HR` を SELECT するが、 `batting_logs` schema には `HR` 列が存在しない (HR は `atbats_json` 内の打席結果テキストから集計する必要がある)

`batting_logs` schema 確認 (`data/insight/schema.sql` L48-65):
- 列: game_id, team_role, slot_order, position, player_display, player_canonical, is_sub, **AB, R, H, RBI, SB**, atbats_json, team_name
- HR は AB / R / H / RBI / SB の counting には無い、 `atbats_json` の per-PA result (例 `中本` 等の文字列 marker) から集計が必須

## 4. fix 方針 (narrow)

`aggregate_player_counting_stat_split` (L937) の冒頭に、 `aggregate_player_counting_stat` (L278) と同じ HR dispatch を追加。 dispatch 先の `aggregate_player_hr_from_atbats` は split_field / split_value を受けない signature のため、 split 対応版 `aggregate_player_hr_from_atbats_split` を新規追加 (or 既存関数を拡張)。

### 4.1. 候補 fix (推奨)

```python
def aggregate_player_counting_stat_split(
    conn, *, stat_col, table, scope, split_field, split_value,
    today=None, top_n=10, league=None,
) -> list[dict]:
    # 406 fix: HR は batting_logs に列が無い、 atbats_json 集計に dispatch
    if stat_col == "HR" and table == "batting_logs":
        return aggregate_player_hr_from_atbats_split(
            conn, scope=scope, split_field=split_field, split_value=split_value,
            today=today, top_n=top_n, league=league,
        )
    # ... 既存 logic
```

新規 helper `aggregate_player_hr_from_atbats_split`:
- 既存 `aggregate_player_hr_from_atbats` (HR を atbats_json から re marker 集計) を base に、 `JOIN games g` で `g.{split_field} = ?` filter を追加

### 4.2. affected files

- `src/analysis/ranking_article_publisher.py` (L937 fix + L187 helper の split 版追加)
- `tests/test_ranking_article_publisher.py` (or 既存 test file、 HR split case 2-3 件追加)

### 4.3. 不可触

- `batting_logs` schema 変更なし (HR 列追加しない、 atbats_json を信頼)
- 他 metric (H / RBI / SB / K / W 等) の split は変更しない
- 348 whitelist / 349 cooldown / 356 quality gate の他 check
- env / Secret / Scheduler / publisher の caller 側 / title format
- [[403]] の scope vocabulary 切替

## 5. 成功条件

- pytest: 新規 HR split case 2-3 件 green、 既存 regression 0
- production DB copy: `aggregate_player_counting_stat_split(stat_col='HR', ..., split_field='opponent', split_value='t')` で rows が返る (OperationalError なし)
- live deploy 後 1 nightly: log に `player_counting_split_publish_failed` HR error 0 件、 HR opponent / home_away split publish が新規に出る可能性 (cooldown 等で 0 でも error 出ない事を確認)

## 6. 動作確認

- ローカル: targeted pytest green
- production DB copy preview: HR split SELECT が ERROR なし
- live deploy 後: 翌朝 (07:00 JST) の自然 fire 観察、 logs に bl.HR error 0 件確認

## 7. 並走可否

- [[403]] (期間 cut 切替) と **完全に独立** な fix
- [[403]] は scope vocabulary を入れ替えるが、 本 ticket は HR split の SQL dispatch を直すだけ
- 同じ `ranking_article_publisher.py` を touch するため commit 順序は 1 本ずつ直列 (CLAUDE.md §31-D)
- どちらを先に着地させても問題なし、 本 ticket は narrow fix のため先行可能
