# 089 Editor extracts source URL from body HTML as fallback when meta is empty

## meta

- owner: Codex B(narrow Python 実装)
- type: impl ticket(autonomous range)
- status: BLOCKED on 086 close(Codex 便直列維持)
- created_at: 2026-04-24 23:00 JST
- deps: 083(editor prose-judgment)/ 084(pagination overflow graceful)/ wp_client.py 既存 meta key 規約
- target_repo: `/home/fwns6/code/wordpressyoshilover`

## why_now

- 22:00 editor smoke で `missing_primary_source: 45 件`(in-window 86 件中 52%)が editor candidate を上げない最大ボトルネック
- 直接 probe で確認:
  - WP REST `?_fields=meta&context=edit` が返す meta に `_yoshilover_source_url` / `yl_source_url` が **0 件**
  - 同じ draft の body HTML には `参照元: <a href="https://www.nikkansports.com/...">` 形で source URL が **100% 存在**
- 真因: WP REST は **private meta key**(underscore `_` prefix)を `register_meta(show_in_rest=true)` 経由で明示登録しないと expose しない。`_yoshilover_source_url` は server 側に登録されていない、または登録 PHP plugin が live deploy 古い
- 結果: creator 側は `wp_client.create_post(..., source_url=post_url)` で meta 書き込みを試みているが、editor 側 `_extract_source_urls(post)` が REST 経由で読み戻せない = データ自体は WP DB にある可能性高い、ただし editor からは見えない
- editor を 45 件 unblock するには、(A) WP server 側で `register_meta` を expose、または (B) editor 側で body HTML 由来の fallback 抽出を追加、のいずれか
- (B) は **pure Python / autonomous / blast radius editor 内**で済む = 089 として narrow 化

## purpose

- editor の `_extract_source_urls(post)` に **body HTML の `参照元: <a href="...">` footer 由来の fallback** を追加
- meta 由来 source URL が空のときだけ body 由来を使う(meta が正しく入っている場合は既存挙動維持)
- editor productivity を 45 件 unblock(in-window 86 件中の 52% を candidate 化)
- 実 publish には触らず editor refine の入口を広げるだけ

## non_goals

- WP server 側 `register_meta(show_in_rest=true)` の登録(別 ticket、front Claude / PHP plugin 領域、089-A として将来別途)
- creator 側(`src/rss_fetcher.py` / `wp_client.py`)の meta 書き込み logic 変更
- body HTML parser を全面導入(stdlib regex で十分、`html.parser` 不要)
- editor の rewrite logic 本体 / safety guard / pagination logic
- mail chain / publish / X API / automation
- baseballwordpress repo
- front lane

## scope(編集対象、最小 diff)

### `src/tools/run_draft_body_editor_lane.py`

- `_extract_source_urls(post)` 関数(line 380 付近)を拡張
- 既存 logic で meta 由来 URL を取得 → 空だった場合のみ body HTML から正規表現抽出
- 抽出 pattern: `参照元[:\s]*<a[^>]+href="([^"]+)"`(stdlib `re` で対応、複数 match は first hit を採用)
- meta 由来があれば従来通り(既存挙動 untouched)
- body HTML が無い / pattern hit 0 の場合は空 list 返す(現状と同じ)

### `tests/test_run_draft_body_editor_lane.py`

- 既存 test ファイルに 4 case 追加:
  - **meta あり、body あり**: meta 由来を採用(従来挙動、回帰確認)
  - **meta なし、body footer あり**: body 由来 URL を採用(NEW behavior、本 ticket 本旨)
  - **meta なし、body footer なし**: 空 list(従来挙動、回帰確認)
  - **meta なし、body 複数 footer**: first hit を採用(closed behavior 確認)

### `doc/089-editor-source-url-body-fallback.md`(本 file)

- 完了時に【×】 mark を追記(`## TODO` 節にチェックリスト追加)

## 不可触(staged file 全てで diff 0、§31-B)

- `src/wp_client.py`(meta 書き込み logic、本 ticket は editor 側のみ)
- `src/rss_fetcher.py`(creator 主線)
- `src/tools/run_notice_fixed_lane.py`(route 層)
- `src/tools/draft_body_editor.py`(083 で touch 済、本 ticket は別関数、不可触)
- `src/title_body_nucleus_validator.py`(071)
- `src/title_style_validator.py`(086 land 後の新規 module、本 ticket は無関係で不可触)
- `src/source_trust.py` / `src/source_id.py` / `src/game_id.py`
- `src/postgame_revisit_chain.py` / `src/first_wave_promotion.py`
- `src/eyecatch_fallback.py` / `src/repair_playbook.py` / `src/fact_conflict_guard.py`
- `src/x_post_generator.py` / `src/x_published_poster*.py`
- `src/mail_delivery_bridge.py` / `src/morning_analyst_email_sender.py` / `src/x_draft_email_*.py` / `src/ops_status_email_sender.py` / `src/publish_notice_email_sender.py` / `src/publish_notice_scanner.py`(072-076)
- `src/nucleus_ledger_adapter.py` / `src/nucleus_ledger_emitter.py`(078/079)
- `src/social_video_notice_*` / `src/x_source_notice_*`(080/081)
- `src/article_parts_renderer.py`
- `src/fixed_lane_prompt_builder.py`(086 で touch、本 ticket は editor 側のみ)
- `automation.toml` / scheduler / secret / env / X API
- `doc/030`〜`doc/088` 本体(本 ticket は新規 doc/089 のみ)
- WP 書込 / published / WP DB / `register_meta` PHP plugin
- baseballwordpress repo
- front lane 全部

## acceptance

- meta 由来 source URL があれば従来通り(既存 test 全 pass、回帰なし)
- meta 由来 0 + body 由来あり → body 由来採用(NEW)
- meta 由来 0 + body 由来 0 → 空 list(従来通り)
- 22:00 smoke 後の在庫(`missing_primary_source: 45 件`)が想定 30+ 件 unblock(45 件すべての body に footer がある前提では 100% 解消、実態は 80-100%)
- pytest suite green(現状 1014、想定 +4 = 1018)
- 不可触 list diff 0
- 1 commit に閉じる

## fire 順序

- **086 land 後**(Codex 便直列維持、`.git/refs/heads/master.lock` 衝突回避)
- 086 → 089 の 2 連続が安全
- fire コマンド: `codex exec --full-auto --skip-git-repo-check -C /home/fwns6/code/wordpressyoshilover < /tmp/codex_089_prompt.txt > /tmp/codex_089_run.log 2>&1`

## 後続(089-A、conditional、本 ticket では作らない)

- WP server 側で `_yoshilover_source_url` を `register_meta(show_in_rest=true)` で expose する PHP plugin / hook 追加
- 089 (Python fallback)で十分動く前提で、089-A は **しばらく寝かす**(必要性は 1 週間 observation で判断)
- owner: front Claude(PHP 領域)
- scope: 1 PHP plugin or 既存 yoshilover-* plugin に hook 追加 = small

## TODO

- 【×】`src/tools/run_draft_body_editor_lane.py` の `_extract_source_urls(post)` を meta 優先 + body footer fallback の 2 段抽出へ更新
- 【×】`tests/test_run_draft_body_editor_lane.py` に meta 優先 / body fallback / empty / first-hit の 4 case を追加
- 【×】`python3 -m unittest discover -s tests` で full suite green を確認
- 【×】staged scope を `doc/089` + `src/tools/run_draft_body_editor_lane.py` + `tests/test_run_draft_body_editor_lane.py` の 3 file に限定して commit/push
