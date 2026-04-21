# next_action

## 1. 今回の目的

78便で判明した **title-only draft reuse × generic title collision bug**(直近 7 日 fire の 18.5% で distinct source が既存 draft に吸着し、生成 work が消える)を塞ぐ。implementation + test までで止め、deploy は 80便で user 判断を取って分離する。

目的は「distinct source は distinct draft として残す」「retry は従来どおり既存 draft reuse」の両立。

## 2. 変更対象

- `src/wp_client.py`
  - `find_recent_post_by_title()` / `create_post()` / `_reuse_existing_post()` 周辺
- `src/rss_fetcher.py`
  - `_rewrite_display_title_with_template()` およびその呼び出し経路(farm_result_score / game_pregame_generic / game_postgame_generic)
  - same-fire 内で処理済み source_url / post_id を覚えるローカルガード
- `tests/`
  - 新規 or 既存テストの拡張(3 本以上)
- 必要最小限の関連ヘルパー(scope 厳守)

## 3. やること

### A. WP draft reuse 条件の是正(`src/wp_client.py`)

- `find_recent_post_by_title()` の matching key を **`normalized_title + subtype + source_url`** に拡張
  - `subtype` は呼び出し側から渡す(未指定時は従来通り title-only で fallback 可、ただし呼び出し側は必ず渡す)
  - `source_url` はカスタムフィールド or meta(既存の `yl_source_url` 相当)で比較
- retry 想定(同一 source_url + 同一 title + 24h)では従来どおり既存 draft を reuse
- distinct `source_url` が同じ generic title にヒットしても **新規 draft を作る**
- `_reuse_existing_post()` は従来どおり `featured_media/categories/status` のみ更新(本文書き込み経路は今便 scope 外)

### B. same-fire guard(`src/rss_fetcher.py`)

- 1 fire の処理中に使った `(post_id, source_url)` を local set に記録
- 次 entry が同一 `post_id` を返そうとしたら
  - `source_url` が一致すれば reuse 維持
  - `source_url` が異なれば **新規 draft 作成に fallback**(WP 側でも A の条件で分かれるが二重防御)
- このガードは code レベルで、どちらの経路で collide しても distinct entry は distinct draft になること

### C. generic title template に識別子追加(`src/rss_fetcher.py`)

- `farm_result_score`: `巨人二軍 {score} 結果のポイント` → `{date_label} 巨人二軍 {score} 結果のポイント`(例: `4/20 巨人二軍 7-4 結果のポイント`)
- `game_pregame_generic`: `巨人戦 試合前にどこを見たいか` → `{opponent}戦({date_label}) 試合前にどこを見たいか`
- `game_postgame_generic`: `巨人戦 試合の流れを分けたポイント` → `{opponent}戦({date_label}) 試合の流れを分けたポイント`
- `{date_label}` は JST の `M/D` 形式、`{opponent}` は既存抽出経路から(不明時は従来 generic に fallback)
- これで collision 発生率を下げる(A/B が効いても、そもそも title collision が減る方が望ましい)

### D. Test(3 本必須 + regression)

- **T1**: 同一 fire・別 farm source_url・同一 score → post_id が分かれる
- **T2**: 同一 fire・別 pregame source_url・generic title → post_id が分かれる
- **T3**: 同一 source_url の retry(2 回目実行)→ 既存 draft reuse を維持(設計意図の regression guard)
- 既存 pytest 455 件の regression がないこと(特に `tests/test_lineup_subtype_boundaries.py` / `tests/test_title_rewrite.py`)

### E. pre-implementation の確認

- `_reuse_existing_post()` が meta(source_url)を読めるか、現状 custom field 名は何か(`yl_source_url` 等)を grep で確認
- `source_url` が meta に保存されていない場合は、保存経路(`create_post` 時に set)を追加するか、別 key で代替
- 追加しないと A の subtype + source_url 判定が機能しない

## 4. やらないこと

- **deploy しない**(80便で user 判断)
- 75便の subtype 境界ロジック変更
- `_reuse_existing_post()` の本文書き込み挙動変更(別便)
- close_marker 対処(別便)
- フロント rule 変更(別便)
- X 付与ルール変更(別便)
- scheduler / feature flag / secret / env 変更
- 75便 scope 外の dirty file を巻き込んだ commit

## 5. 成功条件

- `src/wp_client.py` の draft reuse 条件が `title + subtype + source_url` で判定される
- `src/rss_fetcher.py` に same-fire guard が入っている
- generic title 3 種に `{date_label}` / `{opponent}` 識別子が入っている
- T1/T2/T3 の test が pass
- 既存 pytest 455 件が regression なし
- 79便差分だけで独立 commit(他 dirty file を巻き込まない)
- deploy されていない(local 実装 + test まで)

## 6. テスト

- `PYTHONPATH=. pytest -q tests/` が全 green
- T1/T2/T3 を含む新規テストが pass
- 変更前では T1/T2 が fail、T3 が pass であることを確認(regression guard)

## 7. 結果の保存先

`docs/handoff/codex_responses/2026-04-20_79.md`

返答は **5 ブロック固定**:

1. changed files(path + 1 行説明)
2. 実施内容(A/B/C それぞれ何を変えたか、key / guard / title format)
3. test 結果(T1/T2/T3 と全体 pytest)
4. remaining risk(未 cover ケース、title 識別子追加による既存 URL slug / SEO 影響、meta 設計の注意)
5. 次に Claude が判断すべきこと(80便 deploy 判断に必要な観点)
