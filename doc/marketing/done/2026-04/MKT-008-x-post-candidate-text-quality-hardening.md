# MKT-008 X post candidate text quality hardening

## dropped note(2026-04-29)

- status: DROPPED
- reason: Dropped. X post candidate wording is handled by the private GPTs assistant; repo stays focused on article/numeric safety guards.

## meta

- number: MKT-008
- alias: 225
- type: dev / marketing quality
- status: DROPPED
- priority: P0.5
- lane: Codex B
- created: 2026-04-27
- parent: MKT-001(219 mail classification)/ 222 X intent link
- related: 224(article body entity-role consistency)

## background

公開通知メールに embed される X 投稿候補(218 で品質改善済)を、コピペ → X 投稿の現場運用でさらに堅牢化:
- 218 で raw summary cleanup / notice_event 判定 / default subtype dirty 抑制を実装
- 222 で X intent URL 1 タップ追加
- それでも残る品質課題:
  - 半角スペース / 改行の乱れ
  - 連続記号(`!!` / `…` 等)整形
  - ハッシュタグの重複 / 順序
  - URL 末尾改行 / 不要 trailing 文字
  - 280 字 cap 直前で切れた文末の整形
  - notice / sensitive subtype での候補抑止強化

## goal

X 投稿候補テキストの「コピー → 投稿で違和感ゼロ」を実現する最終研磨層。

## scope

- 半角/全角スペース正規化
- 連続記号 `!!` `??` `…` のlimit化
- ハッシュタグ末尾統一(`#巨人 #ジャイアンツ` 等の標準 set 適用 or override)
- URL 末尾整形
- 280 字直前 truncation の文末整形(`…` で切る、句読点で終わる)
- subtype 別の cap 別途(default は短く、postgame は長め等)
- sensitive subtype(notice / 怪我 / 死亡)= candidates 抑止強化(218 + 217 と整合)

## affected files(候補)

- `src/publish_notice_email_sender.py`(218 / 222 と同 file、build_manual_x_post_candidates 周り)
- `tests/test_publish_notice_email_sender.py`

## acceptance

- 既存 218 / 222 logic 不変
- スペース / 記号 / ハッシュタグ / URL の整形 detector + applier
- 280 字 cap 維持
- sensitive subtype の候補抑止強化
- copy-ready 化 verify(fixture test)

## non-goals

- 文体の意味的書き換え(NLP / LLM 不使用)
- ハッシュタグ自動拡張(別便、手動 user override)
- WP live write / GCP deploy(別便)

## next_action

- 225 本体は `873fcf0` で着地済(空白/記号/ハッシュタグ/URL/280字 整形 + sensitive 抑止)
- **225-A safety fix 進行中**(`bss84x1u1`):x_post_ready=false / mail_class=review|warning|urgent で manual_x_post_candidates を mail 本文に出さない、X intent link も抑止
- 225-A 完了後に publish-notice rebuild + Job update(authenticated executor)で live 反映

## 225-A 追加 fix scope

- post_id 63323 相当(subtype=notice / mail_class=review / x_post_ready=false / reason=cautious_subtype_review)で manual_x_post_candidates が mail 本文に出ていた bug
- 内部生成 logic は維持(queue.jsonl 等)、mail body 表示のみ gate
- 代替表示「[X 投稿候補] 要確認のため非表示」

## related ticket

- MKT-001 (219) publish-notice marketing mail classification
- 218 X candidates 品質改善(summary cleanup / notice_event)
- 222 mobile one-tap X compose link
- 224 article body entity-role consistency(品質向上の本文側)
