# 376-QA-person-tag-routing-and-noindex

## meta

- status: REVIEW_NEEDED
- priority: P0.5
- owner: Codex
- lane: B
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/49
- created: 2026-05-17

## user lock

- 選手タグはあらかじめ全部作る。
- タグアーカイブはまず noindex。
- 記事カテゴリは今の大分類を維持する。
- 選手記事はカテゴリに関係なく、該当する選手タグへ自然に束ねる。
- 2 選手が明示されている記事は 2 人分の人物タグを付ける。
- 首脳陣と OB も同じ人物タグ方針に含める。
- AI の「記憶から再構成」「silent skip」「自己評価 OK」は禁止。

## implementation

- `src/person_tag_router.py`
  - 巨人 roster / OB registry から人物タグ候補を作る deterministic router。
  - LLM 不使用。
  - 曖昧な短姓 alias は skip し、`ambiguous_alias:*` を残す。
  - 2 選手以上の明示 hit は複数人物タグとして返す。
  - `一軍` / `二軍` / `三軍` / `速報` / `監督コメント` / `OB解説` などの文脈タグも rule-based で返す。

- `src/tools/sync_wp_person_tags.py`
  - 事前に WP tag を作る専用 CLI。
  - runtime の記事生成 path では tag を作らない。
  - `--dry-run` で作成予定 tag を JSON 出力。

- `src/wp_client.py`
  - `create_post` / `create_draft` payload に `tags` を追加可能にした。
  - `get_tags` / `resolve_tag_id` / `resolve_tag_ids` / `create_tag` を追加。
  - 既存 draft reuse 時は draft 系 status のみ tag backfill する。publish 済み post は不用意に tag 更新しない。

- `src/rss_fetcher.py`
  - WP draft 作成 chokepoint で人物 / 文脈タグを既存 WP tag ID に解決して付与。
  - 存在しない tag は作らず、`missing_tags` として `person_tag_routing` log に残す。
  - person hit なし / ambiguous も `skip_reasons` に出す。

- `src/yoshilover-post-noindex.php`
  - 個別記事 default noindex は維持。
  - `is_tag()` archive は `wp_robots` と `X-Robots-Tag` で `noindex, follow`。

## acceptance

- 新規 RSS 記事に、タイトル / 要約で明示された巨人選手・首脳陣・OBの既存 WP tag が自動付与される。
- 2 選手記事では 2 人分の人物 tag が付く。
- runtime では未知 tag を作らない。
- missing / no hit / ambiguous は log に残り、silent skip にならない。
- タグアーカイブは noindex。
- 既存カテゴリ分類は変更しない。
- X API / Scheduler / Secret / Cloud Run env は変更しない。

## validation

- `python3 -m py_compile src/person_tag_router.py src/wp_client.py src/rss_fetcher.py src/tools/sync_wp_person_tags.py`
- `python3 -m pytest tests/test_person_tag_router.py tests/test_wp_client_create_category.py tests/test_yoshilover_post_noindex_php.py tests/test_rss_fetcher_person_tags.py -q`
- `python3 -m pytest tests/test_wp_client.py tests/test_wp_client_create_category.py -q`
- `python3 -m pytest tests/test_duplicate_prevention_golden.py tests/test_rss_fetcher_reliability_2026_05_08.py tests/test_rss_fetcher_categories.py tests/test_rss_fetcher_person_tags.py -q`
- `DISABLE_NPB_ROSTER_FETCH=1 python3 src/tools/sync_wp_person_tags.py --dry-run`

## live state

- repo implementation done.
- live WP tag sync not executed.
- Cloud Run deploy not executed.
- Scheduler / env / Secret unchanged.
- X / SNS post unchanged.
