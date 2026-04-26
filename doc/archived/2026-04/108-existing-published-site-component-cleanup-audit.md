# 108 existing-published-site-component-cleanup-audit

## meta

- number: 108
- alias: -
- owner: Claude Code(設計 + 起票)/ Codex B(実装)
- type: ops / quality audit / detector 強化(read-only)
- status: READY(B slot 補充候補)
- priority: P0.5
- lane: CodexB
- created: 2026-04-26

## 目的

本日 publish 8 件の C 簡易 audit で **site_component_heavy が全件 hit**(`💬 〜?` `【関連記事】` 等が 5-8 hits)。
PUB-004-B cleanup 機能は今後 publish 分のみ適用、**既存公開記事の post-hoc cleanup は別経路**が必要。

本 ticket = **既存公開記事を read-only で audit**、cleanup 候補を整理 + detector 強化。
**WP write しない**(本 ticket scope = audit + detector 強化、write は別 ticket = 113 以降)。

## 重要制約(全 phase 共通)

- **WP write 一切禁止**(本 ticket は read-only audit + fixture 検証)
- live publish / mail / X 一切なし
- `RUN_DRAFT_ONLY` flip / Cloud Run env / `.env` / secret / front 全部不可触
- `git add -A` 禁止 / `git push` 禁止(Claude が後で push)

## write_scope

- 新規 module: `src/published_site_component_audit.py`
- 新規 CLI: `src/tools/run_published_site_component_audit.py`(read-only WP REST GET、site_component pattern grep)
- 新規 tests: `tests/test_published_site_component_audit.py`(fixture-based、live WP 不要)
- PUB-004-B 既設 detector(`heading_sentence_as_h3` / `dev_log_contamination` / `weird_heading_label` / `site_component_mixed_into_body`)を流用 / 改変なし

## acceptance

1. WP REST `status=publish` の直近 N 件(`--limit 50` 等)を read-only GET
2. 各 publish post に対し PUB-004-B cleanup detector を適用、site_component / heading_sentence / dev_log block を検出
3. 出力: JSON list + human summary
   - `cleanup_proposals: [{post_id, title, link, detected_types: [], proposed_diff_preview: "..."}]`
   - `clean_posts: [post_id, ...]`
   - `summary: {total, with_proposals, by_type}`
4. WP write **ゼロ**(verify: smoke run で WP REST POST/PUT/DELETE call なし)
5. live X / mail なし
6. tests pass(fixture で各 detector 分岐 + secret 漏洩 0)

## test_command

```
python3 -m pytest tests/test_published_site_component_audit.py -v
python3 -m unittest discover -s tests 2>&1 | tail -3
python3 -m src.tools.run_published_site_component_audit --help
```

## next_prompt_path

`/tmp/codex_108_impl_prompt.txt`(本 ticket fire 時に Claude が用意、本 doc 完成後)

## 不可触

- WP REST POST/PUT/DELETE(本 ticket は GET only)
- `.env` / secret / Cloud Run env / `RUN_DRAFT_ONLY`
- automation / scheduler
- front / plugin / build
- baseballwordpress repo
- 既存 PUB-004-B `src/guarded_publish_runner.py`(detector 流用、改変禁止)
- X / SNS POST

## 後続 ticket(本 ticket scope 外)

- `113-published-cleanup-apply-runner`: 本 ticket の audit 結果から WP REST update_post_fields で cleanup 適用(書き込み系、user 判断必要)
- `114-...`: その他 cleanup 範囲拡張

## 関連 file

- `doc/PUB-004-guarded-auto-publish-runner.md`(cleanup contract 正本)
- `src/guarded_publish_runner.py`(detector 既設)
- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(R8 site component 判定)
- 本日 publish 8 件 audit 結果(C 簡易 audit、本 chat 内記録)
