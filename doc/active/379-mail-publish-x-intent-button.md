# 379-OPS mail 内「公開してX投稿画面へ」ボタン (draft → publish → X intent)

## meta

- status: DESIGN_REVIEW_NEEDED (377-OPS Phase 1C 完了 が前提依存)
- priority: P2 (運用効率改善、 user 判断必須は維持)
- owner: Claude
- created: 2026-05-18
- github_issue: TBD
- depends_on: 377-OPS Phase 1C (mail body_excerpt populate)

## user intent (2026-05-18 chat lock、 原文要約)

- 「完全自動公開・X 自動投稿はしない。 user 判断を必ず残す」
- 「自動化するのは公開作業と X 投稿画面を開く作業だけ」
- 「mail 本文を読んで判断、 出す記事だけ 1 click で WP draft→publish して X 投稿画面へ移動できるようにしたい」
- 「X 上の最後の『ポスト』ボタンは user が押す」

## 最終フロー (希望)

```
1. システムが記事候補取得
2. WP に原則 draft 保存 (377-OPS Phase 2)
3. mail に判断 card 配信 (本文 600-1000 字、 出典 URL、 WP 編集 link、 公開してX投稿画面へボタン)
4. user が mail 本文を読んで判断
5. mail 内「公開してX投稿画面へ」ボタンを click
6. 対象記事が WP で draft → publish に変更
7. 公開 URL 付きで X 投稿画面 (intent) が開く
8. X 上の最後の「ポスト」ボタンは user が押す
```

## scope

### A. mail 内ボタン追加

ボタン名 (lock): **「公開してX投稿画面へ」**

別表記禁止:
- 「公開してXに投稿」(自動投稿に見える) → NG

### B. ボタン押下時の処理

1. post_id と期限付き token を検証
2. 対象記事が `status=draft` の場合だけ `publish` に変更
3. `publish` 済みなら変更せず、 そのまま公開 URL を使う
4. publish 後、 公開 URL を取得
5. `https://x.com/intent/tweet` で X 投稿画面遷移
6. X 投稿画面に **記事タイトルと公開 URL** が入っている状態
7. X 上の最終投稿ボタンは user が押す (システムは押さない)

### C. 安全条件 (hard requirements)

- token は期限付き (推奨 60 分)
- 可能なら token は **1 回限り** (one-shot)
- 二重 click しても壊れない (idempotent)
- `draft` 以外の post は変更しない (publish 済 / private / trash は touch しない)
- publish 済記事は「すでに公開済み」として扱い再処理しない
- 失敗時は短い結果画面 (JSON or HTML)
- 実行 log 残す (post_id, token hash, result, timestamp)
- **mail セキュリティスキャナがリンクを踏んでも、 意図しない大量公開が起きない設計** (= GET でなく POST + confirmation step、 もしくは token 1 回限り + draft only)

## 非ゴール (絶対やらない)

- X API による自動投稿
- AUTO_TWEET 触らない
- SNS 自動投稿の追加
- user 判断なしの WP 自動公開
- 既存 publish 済記事の本文 / status を勝手に変更
- Scheduler 変更以外の Cloud Run env / Secret を勝手に変更
- SEO / noindex / canonical / 301 触らない
- Gemini call 増加

## 触ってよい候補 file (想定)

| file | 変更内容 |
|---|---|
| `src/publish_notice_email_sender.py` | mail template に「公開してX投稿画面へ」ボタンを追加。 URL は `{base}/publish-and-tweet?post_id=X&token=Y` |
| `src/server.py` (or 新規 endpoint) | `/publish-and-tweet` GET/POST endpoint。 token 検証 → draft なら publish → X intent URL に 302 redirect |
| `src/publish_button_token.py` (新規) | token 生成 / 検証 helper。 HMAC + 期限 + 1 回限り (in-memory cache or GCS) |
| `tests/test_publish_button_*.py` (新規) | E2E + security test |
| Cloud Run env | `PUBLISH_BUTTON_HMAC_SECRET` (Secret Manager 新規) |

## 触らない範囲 (再確認)

- X API 関連全部
- AUTO_TWEET 関連
- 既存 publish flow (X 投稿関連)
- SNS 自動投稿コード
- SEO / noindex
- 既存公開記事の本文・ステータス
- Gemini 関連

## 完了条件

1. mail 内に「公開してX投稿画面へ」ボタンが出る
2. ボタン 1 回で WP draft → publish → X 投稿画面表示 まで進む
3. X 投稿画面に 投稿文 + 記事 URL が入っている
4. X 上の最後の「ポスト」は user が押す
5. X 自動投稿は発生しない
6. mail スキャナが踏んでも大量公開しない
7. publish 済記事は touch しない
8. 二重 click で壊れない
9. token 期限切れで publish しない
10. 存在しない post_id で失敗する
11. 実装テスト (security + happy path) が pass

## test 要件

メールボタン:
- draft 記事で「公開してX投稿画面へ」を押すと publish に変わり、 X intent へ遷移
- X intent に title と公開 URL が入る
- publish 済記事は status 変更せず X intent へ進む
- 存在しない post_id では失敗
- 無効 token / 期限切れ token では publish しない
- 二重 click で壊れない
- X API 投稿が発生しない (network mock で X API endpoint を call していないこと)

## 既知の risk

| risk | 対処 |
|---|---|
| mail スキャナが GET ボタンを踏んで自動 publish | confirmation page を挟む or POST 化、 token 1 回限り、 draft 以外無視 |
| token 漏洩で第三者 publish | HMAC + 短期限 (60分) + 1 回限り、 mail 受信者前提 (user 自身) |
| HMAC secret 漏洩 | Secret Manager 管理、 rotation 手順 doc 化 |
| publish 済記事への誤操作 | status check で draft 以外は publish しない |
| X intent URL の URL escaping ミス | url encode 厳格 test、 日本語 title / & / # 含む test |
| Cloud Run endpoint への DoS | rate limit (per-IP 60req/min)、 access log |

## 前提依存

- **377-OPS Phase 2 (RUN_DRAFT_ONLY=True env apply)** 完了 必須
  - これが無いと全 subtype draft 化されず、 ボタンが publish 済記事に対して動くだけになる
- **377-OPS Phase 1C (mail に body_excerpt populate)** 完了 必須
  - これが無いと user は mail で本文判断できず、 ボタン押す判断材料が無い
- **378-evening-peak-fetch-15min** (本日着地) ← 関連、 必須ではない

## cost

- Cloud Run endpoint 追加: free tier 内 (新規 endpoint 1 つ、 想定 req <100/日)
- Secret Manager `PUBLISH_BUTTON_HMAC_SECRET` 1 件追加: $0.06/月
- mail 送信容量: +200-400 bytes/card (ボタン HTML 分)、 無視範囲
- 合計: 約 +$0.06/月

## next action

1. 377-OPS Phase 1C 完了待ち (mail body populate)
2. user に本 ticket の設計詳細を 7 点提示 → 設計確定
3. token design (HMAC + 期限 + 1 回限り の実装方式)
4. mail スキャナ対策 (confirmation page 方式 vs POST-only 方式) を 決定
5. test scenario 確定
6. 実装

## user GO 待ち事項 (現時点)

- 本 ticket の設計詳細 (token 仕様、 confirmation page 方式)
- 377-OPS Phase 2 + Phase 1C 完了後の着手判断

## 関連 ticket / memory

- `[[377-OPS]]` (全 subtype draft + mail body、 Phase 1C / Phase 2 未着手)
- `[[378-evening-peak-fetch-15min]]` (本日着地、 fetch 頻度向上)
- `[[feedback_publish_forward_must_check_gate_reason]]` (公開境界、 X 投稿 user 手動)
- `[[feedback_publish_vs_xpost_3_gate]]` (公開と SNS 分離、 「公開は広めに、 ポストは厳しく、 事実ミス絶対 NG」)
- 「X API 自動投稿は絶対しない / AUTO_TWEET 触らない」memory rule
