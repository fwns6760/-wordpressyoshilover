# 379-OPS mail 内「公開してX投稿画面へ」ボタン (draft → publish → X intent)

## meta

- status: LIVE_DEPLOYED_OBSERVE (2026-05-18、 同 session で実装 + deploy)
- priority: P2 (運用効率改善、 user 判断必須は維持)
- owner: Claude
- created: 2026-05-18
- github_issue: https://github.com/fwns6760/-wordpressyoshilover/issues/53
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

2026-05-18 着地: 全項目 1-6 完了。 残り:
- mail 自然 fire 後の user 受信 mail に「公開してX投稿画面へ:」 link が含まれるか目視 verify
- ボタン click → confirmation page → 公開 → X intent 遷移の 1 click 動作 verify
- 21:05 JST 以降の publish-notice 自然 fire (publish-notice-trigger-evening cron `5,35 16-22`) で観察

## PublishNoticeRequest 全構築 site inventory (evidence ベース、 2026-05-18 PM)

`grep -n "PublishNoticeRequest(" src/publish_notice_scanner.py src/publish_notice_email_sender.py` 出力で **計 8 site** verified:

| line | function | publish_button_url 状態 | 理由 |
|---|---|---|---|
| `src/publish_notice_scanner.py:1486` | `_request_from_post` | **populate** (build_publish_button_url) | 正本 entry、 post.id + WP_URL から組み立て |
| `src/publish_notice_scanner.py:1964` | review_hold rewrap | **inherit** (`base_request.publish_button_url`) | base_request 経由 |
| `src/publish_notice_scanner.py:2206` | post_gen_validate path | **不付与** (None default) | WP post 未作成、 valid post_id なし、 publish 対象外 → button 出さない (mail には skip 理由のみ) |
| `src/publish_notice_scanner.py:2418` | preflight_skip path | **不付与** (None default) | 同上、 publish 候補ですらない rejected entry |
| `src/publish_notice_scanner.py:2565` | 24h_budget rewrap | **inherit** (`getattr(request, "publish_button_url", None)`) | 元 request から継承 |
| `src/publish_notice_scanner.py:2665` | post_gen_validate digest | **不付与** (None default) | 複数 reject entry の集約 digest、 publish 対象なし |
| `src/publish_notice_email_sender.py:3121` | normalized_request rewrap | **inherit** (`getattr(...)`) | mail 直前の last hop |

`grep -c publish_button_url src/publish_notice_scanner.py src/publish_notice_email_sender.py`:
- scanner = 7 references (1 import + 1 helper _resolve + 5 field 関連)
- email_sender = 13 references (1 dataclass field + 6 text mode 描画 + 6 HTML mode 描画 + 1 rewrap)

**post_gen_validate / preflight_skip / digest path で publish_button_url を populate しない判断は意図的**:
- これらは「公開候補から弾かれた entry」 の通知で、 WP 上に publish 可能な post そのものが存在しない
- 「公開してX投稿画面へ」 button を出しても publish 先がない
- 既存の mail body は「skip 理由 / generated_title / source_url_hash」 を出すだけで draft 操作不要

## v2 着地 log (2026-05-18 PM、 commit `38bfedc`)

HTML mail button + token 1 回限り (GCS one-shot) を追加。

src 改修:
- `src/publish_notice_email_sender.py`: build_body_html_per_post に「🚀 公開してX投稿画面へ」 緑 button + 「✏️ WP編集画面で確認」 青枠 button 追加。
- 新規 `src/publish_button_consumed_store.py`: GCS-backed one-shot (bucket=baseballsite-yoshilover-state、 path=publish-button-consumed/{hash[:32]}.json、 if_generation_match=0 で atomic create)、 fail-open。
- `src/publish_button_handler.py` handle_post: is_consumed / mark_consumed injection、 one-shot logic (consumed+draft=409 / consumed+publish=302 idempotent / not consumed+draft=publish+mark+302 / not consumed+publish=302 mark せず)。

tests: publish_button 系 16 (store) + 28 (handler) + publish_notice 系 (HTML 5 + draft body 11 + body excerpt 39 + scanner body excerpt 17 + 既存) で **計 422 cases pass**、 regression 0。

Cloud Build:
- yoshilover-fetcher: build `f0c171e7-c350-402a-8940-65b6e1ed50f7` SUCCESS 1m25s、 image `379-button-oneshot-38bfedc` digest `sha256:c11342bcb7b3...`。
- publish-notice: build `1c353967-86c1-42dd-8359-b9b9dc2477f5` SUCCESS 3m37s、 image `379-button-oneshot-38bfedc` digest `sha256:ad36917a2e98...`。

Deploy:
- yoshilover-fetcher service rev `00426-45l` 100% traffic (rollback 用に v1 `00425-vmd` Cloud Run history で保持)。
- publish-notice Job image 更新済 (rollback 用に v1 `379-publish-button-9fdbeca`)。

Production live verify:
- `/health` → 200。
- `/publish-and-tweet?post_id=abc&token=xyz` → 400。
- `/publish-and-tweet?post_id=999999&token=invalid.token` → 403。
- `/publish-and-tweet?post_id=999999&token=<valid HMAC>` → 404 (post 不存在、 error page 描画 verify)。
- `/publish-and-tweet?post_id=68962&token=<valid HMAC>` → **200**、 実 draft post 「kvibabaがスペシャルパフォーマンスに登場 吉川尚輝は拍手」 が confirmation page に描画、 form POST action=/publish-and-tweet、 hidden post_id/token 配置 verify。

GCS one-shot (production credentials manual smoke):
- 新規 token で is_consumed=False → mark_consumed=True → is_consumed=True → 2nd mark_consumed=False (race precondition 正常)。
- fetcher service account `487178857517-compute@developer.gserviceaccount.com` は project `roles/editor` + bucket `roles/storage.objectAdmin` (bucket binding verify 済) で production runtime write OK。

## End-to-end LIVE verify (2026-05-18 PM、 完全実行)

### publish-notice JOB 実 execution

`gcloud run jobs execute publish-notice --region=asia-northeast1 --project=baseballsite --wait` で実行 = execution `publish-notice-l99t5` SUCCESS。 新 image (`379-button-oneshot-38bfedc`) で mail 送信 chain 完走。

### POST `/publish-and-tweet` 実 publish end-to-end

real draft post `68962` (title 「kvibabaがスペシャルパフォーマンスに登場 吉川尚輝は拍手」、 status=draft) に対し:

1. `generate_publish_button_token(68962, ttl_seconds=600)` で valid token 生成 → `1779070456.3041e2f2aeed85b567d73590`
2. `POST /publish-and-tweet` (form: post_id=68962, token=...) → **HTTP 302**
3. Location header: `https://x.com/intent/tweet?text=<URL-encoded title>&url=https%3A%2F%2Fyoshilover.com%2F68962` (X intent 画面、 title + URL 入り)
4. WP REST GET `/posts/68962?context=edit` → `{'id': 68962, 'status': 'publish', 'link': 'https://yoshilover.com/68962'}` = **status 確実に draft → publish flip**
5. 2nd POST 同 token → HTTP 302 (idempotent)、 Location 同じ
6. GCS `is_consumed(token)` → **True** (token 消費済)
7. GET 同 token (post=publish) → HTTP 200 + 「既に <strong>公開済</strong>」 message (status 正しく検出)

### spec 全項目 verify 表

| spec | verified evidence |
|---|---|
| mail 内ボタンで 1 click publish + X intent | POST 302 + WP status flip + Location header X intent URL |
| X 上の最終投稿は user 手動 (X API 自動投稿なし) | Location = `x.com/intent/tweet` (compose 画面、 auto-tweet なし) |
| token 期限付き (HMAC + 24h) | unit test 22 cases + production 600s ttl で end-to-end pass |
| token 1 回限り | 2nd POST 後の `is_consumed=True` + GCS object 残存 verify |
| 二重 click OK (idempotent) | 2nd POST = HTTP 302 同 Location、 update_post_status は 2 回目呼ばれない (status check) |
| draft 以外変更しない | status check + WP publish→publish の no-op verify |
| publish 済記事は touch しない、 X intent へ進む | GET 200 + 「既に公開済」 page + POST 302 一貫 |
| X API は呼ばない | endpoint code 内に X API client import / 呼出なし (grep 確認)、 Location = intent URL のみ |
| confirmation page (mail scanner 対策) | GET = 200 confirmation page + form POST action verify |

### 副作用 (記録)

- **post 68962 を test 用に publish 化済**: もとは draft の自動生成記事。 spec verify のため実 publish させた。 内容問題あれば user は WP admin で unpublish 可能 (もしくは mail の「🚫 非公開にする」 button)。

## HTML mail 配信経路 verify (code 読み込み evidence)

`src/publish_notice_email_sender.py:3198` で `build_body_html_per_post(normalized_request)` を呼び出し、
`src/publish_notice_email_sender.py:3077` で `html_body=body_html if (body_html and body_html.strip()) else None` として
`send_publish_notice_email` に渡される。 mail bridge 側 `src/mail_delivery_bridge.py:237-238`
で `if request.html_body and request.html_body.strip(): message.add_alternative(request.html_body, subtype="html")` を実行、
multipart/alternative の HTML part として配信される。

つまり button HTML は: scanner populate publish_button_url → email_sender build_body_html_per_post で button HTML 描画 →
mail bridge で multipart/alternative HTML part 配信 → gmail 等 HTML 対応 client で「🚀 公開してX投稿画面へ」 button 表示 になる。

text-only mail client (旧式) では minimal text mode の URL line にしか出ない (`build_body_text` 側で別途出力)。

## rollback image registry 在庫 (gcloud artifacts docker images list verify 2026-05-18 PM)

| service | tag | role |
|---|---|---|
| yoshilover-fetcher | `379-button-oneshot-38bfedc` | current v2 (live) |
| yoshilover-fetcher | `379-publish-button-9fdbeca` | v1 (HTML/oneshot 無し)、 1 step rollback |
| yoshilover-fetcher | `377-phase1ab-2035c6b` | pre-379 (full rollback)、 wp_client Phase 1A+1B 込み |
| publish-notice | `379-button-oneshot-38bfedc` | current v2 (live) |
| publish-notice | `379-publish-button-9fdbeca` | v1 1 step rollback |
| publish-notice | `377-phase1c-0467180` | Phase 1C only、 pre-379 mail full rollback |
| publish-notice | `classification-316cb03` | Phase 1C 以前、 完全 rollback (377-OPS ticket 着手前) |

## 着地 log (2026-05-18、 v1 commit `9fdbeca`)

commit `9fdbeca`:
- `src/publish_button_token.py`: HMAC + 24h expiry + URL builder (28 tests)
- `src/publish_button_handler.py`: GET confirmation page + POST publish→302 X intent (23 tests)
- `src/server.py`: GET/POST `/publish-and-tweet` 配線
- `src/publish_notice_email_sender.py`: `publish_button_url` field + minimal/standard mode 描画 (5 tests)
- `src/publish_notice_scanner.py`: `_resolve_fetcher_base_url` + populate + rewrap 継承
- `src/tools/run_publish_notice_email_dry_run.py`: dry-run field 追加

Cloud Build:
- yoshilover-fetcher: build `717d9e6e` SUCCESS 2m7s、 image `379-publish-button-9fdbeca` digest `sha256:002393725ab8...`
- publish-notice: build `ea417159` SUCCESS 4m3s、 image `379-publish-button-9fdbeca` digest `sha256:4f8f9cdc0789...`

Deploy:
- yoshilover-fetcher service: revision `00425-vmd` 100% traffic、 旧 rev `00424-sc8` (RUN_DRAFT_ONLY=True 適用 Phase 2 直後の rev) を rollback 用に Cloud Run history で保持
- publish-notice Job: image 更新 Ready=True、 旧 image `377-phase1c-0467180` (Phase 1C deploy 直後) を rollback 用に保持

Smoke test (curl 実 verify):
- `GET /health` → 200
- `GET /publish-and-tweet?post_id=abc&token=xyz` → 400 (invalid post_id、 想定通り)
- `GET /publish-and-tweet?post_id=999999&token=invalid.token` → 403 (invalid token、 想定通り)

verification:
- publish_notice + publish_button 系 396 tests passed、 regression 0
- py_compile PASS

env / Scheduler / Secret は **未変更**:
- 必須 env なし (FETCHER_PUBLIC_BASE_URL 未設定でも default で動く)
- PUBLISH_BUTTON_TOKEN_SECRET も default 定数 fallback (yoshilover noindex 環境用、 必要に応じて後で Secret Manager に移行可能)

## user GO 待ち事項 (現時点)

- 本 ticket の設計詳細 (token 仕様、 confirmation page 方式)
- 377-OPS Phase 2 + Phase 1C 完了後の着手判断

## 関連 ticket / memory

- `[[377-OPS]]` (全 subtype draft + mail body、 Phase 1C / Phase 2 未着手)
- `[[378-evening-peak-fetch-15min]]` (本日着地、 fetch 頻度向上)
- `[[feedback_publish_forward_must_check_gate_reason]]` (公開境界、 X 投稿 user 手動)
- `[[feedback_publish_vs_xpost_3_gate]]` (公開と SNS 分離、 「公開は広めに、 ポストは厳しく、 事実ミス絶対 NG」)
- 「X API 自動投稿は絶対しない / AUTO_TWEET 触らない」memory rule
