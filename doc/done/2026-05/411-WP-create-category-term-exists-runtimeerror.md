# 411-WP-create-category-term-exists-runtimeerror

## 1. ticket header

- **status**: CLOSED LIVE_DEPLOYED_VERIFIED (commit `cb279a9` で wp_client.py L1454 `except (requests.HTTPError, RuntimeError)` + L1473 `elif "term_exists" in msg:` で wrap 経路対応、 test `tests/test_411_wp_create_category_term_exists.py` RuntimeError + HTTPError 両経路 cover、 GH Issue #85 close 2026-05-21 01:25 UTC、 user 1次source 監査済)
- **priority**: P1 (publish_default_set の rate metric 全 4 件 publish 失敗中、 cutover 効果半減)
- **owner**: Claude / **lane**: Claude
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/85
- **発見**: 2026-05-20 21:00 fire (insight-nightly-v22bx) で `publish_giants_centric_ranking_draft` 4 件全部 `RuntimeError: [WP] HTTPエラー（カテゴリ作成）: 400 ... term_exists ... term_id=675`

## 2. 事実 bug

`src/wp_client.py`:

- L1454 `create_category` は `except requests.HTTPError` で term_exists を catch して既存 ID を返す設計
- ところが L1513 `_raise_for_status` が `requests.HTTPError` → `RuntimeError` に wrap して raise
- → `create_category` の `except requests.HTTPError` が catch 不能 → RuntimeError がそのまま caller に propagate

結果: 既存カテゴリ (term_id=675) との衝突で 400 が返るたび publish_giants_centric_ranking_draft の `wp_client_obj.create_post` 呼出が失敗。

## 3. 影響

- 21:00 fire の publish_default_set rate metric 全 4 件 (OPS / AVG / OBP / SLG `last_5_games`) 失敗
- publish_player_counting_split_draft も同じ pattern で create_category 呼ぶため、 vs 球団 split 経路も影響
- 403 Stage A4 cutover の効果が半減

## 4. fix 方針 (narrow)

`create_category` の except に `RuntimeError` も追加し、 message 内に `term_exists` を含む場合は既存 ID を search で返す:

```python
except (requests.HTTPError, RuntimeError) as e:
    msg = str(e)
    if "term_exists" in msg:
        for cat in self.get_categories():
            if cat.get("name") == name:
                return cat["id"]
    print(f"[WP] カテゴリ作成失敗: {name!r}, error={e}")
    return 0
```

`resolve_category_id` でも同 pattern 適用検討 (一度 fix 確認後)。

## 5. 不可触

- `_raise_for_status` 本体 (wrap 仕様自体は変えない、 caller 側で対応)
- 他 WP REST endpoint
- 348 whitelist / 349 cooldown / 356 quality gate
- env / Secret / Scheduler / DB schema
- [[403]] の scope vocabulary 切替

## 6. 成功条件

- targeted pytest pass (wp_client / create_category test 追加)
- next fire で create_category 400 error 0 件
- 既存 category (term_id=675) ある時 publish 成功確認

## 7. 動作確認

- ローカル: targeted pytest 緑
- live deploy 後: 自然 fire で `RuntimeError: HTTPエラー（カテゴリ作成）` の 0 件確認
- post 増加 (publish_default_set 4 件 + 既存 counting 3 件 = 計 7 件目安)
