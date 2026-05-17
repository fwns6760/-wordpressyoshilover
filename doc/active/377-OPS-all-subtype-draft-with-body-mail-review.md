# 377-OPS 全 subtype draft 化 + 本文付き mail で user 手動公開フロー

## meta

- status: DESIGN_LOCKED / READY_FOR_IMPL
- priority: P1 (事故防止 + SEO 品質担保)
- owner: Claude
- created: 2026-05-17
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/51

## user intent (2026-05-17 chat lock)

- 「今公開状態にしている。 ただ、 事故が起きるから下書きにして mail を送ってもらう。 それで判断して公開ボタンを押したものを公開にしたい」
- 「本文を読みたい」(mail 内で内容判断したい)
- 「お金はかからないなら全部がいいよね。 いずれ SEO 考えても」 → **全 subtype draft** 採用

## scope

publish 経路の全自動公開を停止し、 user 手動公開フローへ移行する。

1. **全 subtype draft 強制**:
   - 既存 `RUN_DRAFT_ONLY` env flag を `True` に切替 (or 同等の固定 gate)
   - subtype 例外なし (lineup / postgame / 公示 / news / x_short / 社会 / data-insight / YouTube 等 全部)
2. **mail に本文を埋め込む**:
   - 既存 `publish_notice_email_sender.py` の template を拡張
   - 各 draft 1 件あたり: **title (40 字) + 本文サマリ 600-1000 字 + 出典 URL + wp-admin edit link**
   - mail 1 通に複数 draft を list 形式で集約 (既存 batch 設計を踏襲)
3. **mail trigger を draft 作成時に変更**:
   - 既存 `publish_notice_scanner` は publish 時に発火 → draft 作成時に変更
   - 朝 (06:30 JST) / 昼 (12:00) / 夕 (17:30) / 夜 (22:00) の 4 便 (既存 Scheduler 流用)
   - draft 0 件なら mail 送信 skip
4. **wp-admin edit link**:
   - mail 内 link: `https://yoshilover.com/wp-json/wp/v2/posts/<id>?context=edit` ではなく `https://yoshilover.com/wp-admin/post.php?post=<id>&action=edit`
   - user が WP login 済 cookie ある状態でクリック → 編集画面 → 「公開」ボタン

## 不可触

- 既存 publish 済記事 (retroactive 変更なし、 forward-only)
- X / SNS 自動投稿 (既に OFF 維持、 状況不変)
- wp-admin / WP plugin 構成 (login 経路は user 既存)
- env / Secret は最小変更 (RUN_DRAFT_ONLY=True のみ追加)
- Scheduler は既存 publish-notice trigger 流用 (新規 trigger 追加なし)
- 公示の subtype 検出 logic (377 とは独立、 376 / 069144 chain 別軸)

## flow 図

```
[既存]
fetch → article 生成 → publish (auto) → mail 通知 (publish 後)

[377 後]
fetch → article 生成 → draft 確定 →
  → 4 便 mail (本文付き list)
  → user mail で内容判断
  → OK なら mail 内 admin link click
  → WP 編集画面で「公開」ボタン
```

## 改修対象 file (想定)

| file | 変更内容 |
|---|---|
| Cloud Run env (`yoshilover-fetcher`) | `RUN_DRAFT_ONLY=True` 追加 |
| `src/wp_client.py` | RUN_DRAFT_ONLY=True 時 全 create_post を status=draft に強制 (既存 logic 拡張) |
| `src/publish_notice_scanner.py` | trigger を「publish 検出」→「draft 検出」に変更、 24h window 内の draft list 生成 |
| `src/publish_notice_email_sender.py` | mail template に本文サマリ (600-1000 字、 first H2 抜粋) + wp-admin edit link + 出典 URL を追加 |
| `src/publish_notice_scanner.py` の subtype filter | 全 subtype を mail 通知対象に (現状 一部限定なら) |
| tests/test_*_draft_mode.py / tests/test_publish_notice_email_*.py | 新規 mail 本文 / draft mode test |

## 成功条件

1. fetcher が新規記事を作る時、 全 subtype が `status="draft"` で WP に landed
2. 既存 publish 済記事は変更なし
3. 朝/昼/夕/夜 の publish-notice trigger 発火時、 24h window 内の draft list mail が送信される
4. mail 本文に **title + 本文サマリ 600-1000 字 + wp-admin edit link** が含まれる
5. wp-admin link クリックで user が WP 編集画面に到達 → 「公開」ボタンで publish 可能
6. X / SNS / Scheduler / Secret / WP既存記事 は不変

## risk + 対処

| risk | 対処 |
|---|---|
| 試合スタメンが時刻通り公開されない (試合前に user が承認しないと表示されない) | user lock 「全 subtype OK」を尊重、 user 朝/昼 mail check で対応 |
| mail サイズ膨張 (本文 1000 字 × N 件) | 1 mail 上限 5-10 件、 N 件超は次便繰越 or summary 化 |
| wp-admin link が expired / cookie 切れ | user は WP に login し直し |
| 既存 publish lane の test が draft 化で fail | draft 期待値の test 修正 (期待値を draft に変更) |
| Cloud Run env 変更 (RUN_DRAFT_ONLY=True) で他 lane に副作用 | RUN_DRAFT_ONLY は server.py で参照済、 wp_client 側で full enforce 形に拡張 |

## cost

- 全部 ¥0 (env flag 切替、 mail 既存 SMTP 流用、 Cloud Run free tier 内)
- LLM 不使用 (memory rule [[feedback_title_no_ai]] 維持)

## phase

| phase | scope | gate |
|---|---|---|
| **Phase 1** | RUN_DRAFT_ONLY=True 切替 + wp_client draft 強制 + 既存 publish-notice mail template 拡張 (本文 + admin link) | targeted pytest pass |
| **Phase 2** | publish-notice scanner trigger を draft 検出に変更 + 4 便 Scheduler 流用 verify | mail 受信 verify |
| **Phase 3** | 翌日朝の receive verify + 既存 publish 済記事の non-mutation 確認 | user 受け入れ確認 |

## 関連 ticket / memory

- `[[feedback_title_no_ai]]` (LLM 不使用)
- `[[feedback_publish_forward_must_check_gate_reason]]` (公開境界、 X 投稿 user 手動)
- `[[feedback_publish_vs_xpost_3_gate]]` (公開と SNS 分離)
- 344-INGEST Phase 1a-7 (YouTube 経路は既に draft 化、 force-draft revert され auto-publish 戻ったが、 本 377 で再び draft 化される)
- 376-QA-person-tag-routing-and-noindex (人物タグ noindex 進行中)

## next action

着手前 7 点を user に提示 → user GO 後 Phase 1 から narrow PR で実装。
