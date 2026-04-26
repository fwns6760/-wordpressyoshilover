# 109 missing-primary-source-blocker-reduction

## meta

- number: 109
- alias: PUB-002-B
- owner: Claude Code(設計)/ Codex B(実装)
- type: ops / publish blocker reduction / source recovery
- status: READY(B 補充候補)
- priority: P1
- lane: CodexB
- created: 2026-04-26(102 board 採番、本体仕様は alias `doc/PUB-002-B-...md` を参照)

## 仕様詳細

→ **`doc/PUB-002-B-missing-primary-source-publish-blocker-reduction.md`** を参照(本 109 doc は board 採番のみ、リネームせず)

## write_scope

- 新規 module: `src/missing_primary_source_recovery.py`
- 新規 CLI: `src/tools/run_missing_primary_source_audit.py`
- 新規 tests: `tests/test_missing_primary_source_recovery.py`
- 既存 `src/_extract_source_urls`(089 fallback)流用、改変禁止
- 既存 `src/wp_client.py`(get_post / list_posts)流用、改変禁止

## acceptance

1. 72h draft の `missing_primary_source` 件数判明
2. 原因分類 6 タグ + 件数表(`no_source_anywhere` / `source_name_only` / `footer_only_no_url` / `meta_only_no_body` / `twitter_only` / `social_news_subtype`)
3. 最小修復案 3-5 件提示、Yellow / Green 昇格見込み件数推定
4. WP write ゼロ
5. tests pass

## test_command

```
python3 -m pytest tests/test_missing_primary_source_recovery.py -v
python3 -m unittest discover -s tests 2>&1 | tail -3
```

## next_prompt_path

`/tmp/codex_109_impl_prompt.txt`(本 ticket fire 時に Claude が用意)

## 不可触

- WP REST POST/PUT/DELETE
- creator 主線 `src/rss_fetcher.py` の大改修(narrow 修正のみ可)
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY`
- front / plugin / build
- baseballwordpress repo
- `git add -A` / `git push`(Claude が後で push)
