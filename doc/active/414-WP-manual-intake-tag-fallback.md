# 414-WP-manual-intake-tag-fallback

## 1. ticket header

- **status**: READY (Claude 自律進行可能、 narrow fix、 387 part 3)
- **priority**: P1 (manual_intake 経路の全 post が tag=0 = 内部リンク 0)
- **owner**: Claude / **lane**: Claude
- **github_issue**: https://github.com/fwns6760/-wordpressyoshilover/issues/89
- **発見**: 2026-05-20 21:05 JST 387 part 2 解析中、 manual_intake.py に person_tag_router 経路 0 件確認 (grep `tag_ids` / `route_tag_names` / `_ensure_player_tag` 全 0 件)

## 2. 事実 gap

`src/tools/manual_intake.py` の `_wp_create_draft` (L4279) は `wp.create_post(...)` を呼ぶが **tags 引数を渡していない**。

結果: manual_intake 経由 (NTV / 福島民友 等の手動 URL intake) の全 post が tag=0、 chip 出ない / 内部リンク 0。

evidence (2026-05-20):
- post 69537 「巨人・阿部監督...福島民友新聞社」 tags=[]
- post 69524 「スタジアム...」 tags=[]
- post 69522 「テレビ番組情報...」 tags=[]

## 3. fix 方針 (narrow、 [[387]] part 1 / 2 と同 pattern)

`_wp_create_draft` に `tag_ids` 引数追加。 caller (L4673) で:
1. `person_tag_router.route_tag_names(title, summary, category, article_subtype, ...)` を呼ぶ
2. `resolve_existing_wp_tag_ids` で WP tag ID に解決
3. 0 件なら fallback `[850]` (速報 tag)
4. `_wp_create_draft(..., tag_ids=tag_ids)` で渡す

`wp.create_post` は既に tags 引数対応済。

## 4. affected files

- `src/tools/manual_intake.py`:
  - `_wp_create_draft` signature 拡張
  - main intake flow (L4528-4673 area) で tag 解決を挟む

- `tests/test_manual_intake_*.py` (該当があれば fallback test 追加)

## 5. 不可触

- person_tag_router 本体
- wp_client.create_post (既に tags 対応済)
- 348 whitelist / 349 cooldown / 356 quality gate
- env / Secret / Scheduler / DB schema
- [[387]] part 1 (data-insight) / [[387]] part 2 (rss_fetcher)
- 既存 publish 済記事の retroactive tag 追加 (forward only)

## 6. 成功条件

- targeted pytest pass (tag_ids が wp.create_post に渡る + 空時 [850] fallback)
- 次 manual_intake run で post.tags >= 1 確認

## 7. 動作確認

- ローカル: targeted pytest 緑
- live deploy 後: manual_intake-service で新規 URL intake、 WP REST GET で post.tags >= 1 確認
