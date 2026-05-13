# 2026-05-13 — source-excerpt readability + mail HTML 化 + scheduler 調整

## 目的

1. 公開記事の引用ブロック (`nomotoke-source-excerpt`) が「日付 / コメント件数 / 画像キャプション / 関連リンク marker」を混入し `<br>` 一連で繋がっていた読みにくさを恒久解消
2. 自動公開 mail を「title + url の text のみ」から「HTML + 記事確認ボタン + 𝕏 投稿ボタン」に拡張、user の「mail → 記事確認 → X 投稿」運用を 1-2 タップで完結
3. 17-21 時帯の RSS realtime polling コスト最適化

## commit (3 本、いずれも hotfix-eyecatch-hashtag branch)

| hash | scope | 概要 |
|---|---|---|
| `06cca89` | src/source_article_body_extractor.py / src/tools/manual_intake.py / src/custom.css / tests | Yahoo noise 5 種除去 + title-echo bidirectional + 段落 `<p>` レンダリング + CSS margin 1.1em |
| `7a2dec4` | 同上 + extractor helper 追加 | A+B+C readability — ◆ 小見出し青ラベル / 「…」 独立 blockquote 橙ラベル / 長文文末 `<br>` 軽改行 / line-height 2.0 |
| `281cd88` | src/publish_notice_email_sender.py / tests | mail に HTML alternative 追加、青「📰 記事を見る」 + 黒「𝕏 で投稿する」 button 2 個、X intent URL は無料 endpoint |

## 設計判断 (recap)

### 引用ブロック (06cca89)

- **noise 検出 (新規 helper `_is_noise_line`)**:
  - Yahoo 配信日時: `5/5(火) 5:20配信` (`_YAHOO_DELIVERY_RE`)
  - コメント件数: `コメント\d+件` (`_COMMENT_COUNT_LABEL_RE`)
  - 数字のみ行: `^\d{1,4}$` (`_DIGITS_ONLY_RE`)
  - 画像キャプション: `（カメラ・…）` (`_IMAGE_CAPTION_RE`)
  - 関連リンク marker: `【…】…` (`_RELATED_LINK_MARKER_RE`)
- **title-echo**: 既存の asymmetric check (`title_clean in head`) が body の短いタイトル vs WP の長い title (＋出版社 suffix) で fail していた。`_is_title_echo` を bidirectional + prefix-overlap (tolerance=30) で拡張。長い body 段落を誤検出しないよう `len(longer) ≤ len(shorter) + 30` で cap
- **レンダリング**: `<br>` 連結 → `paragraphs.split("\n")` の各非空行を `<p>` で wrap

### A+B+C 強化 (7a2dec4)

- **A. 小見出し**: `◆/●/■/▶/▼/★/☆` 始まり行を `<p class="nomotoke-source-excerpt__heading">` (青左ボーダー + 薄青背景 + bold)
- **B. 独立 blockquote**: `「…」` が ≥30 字 + 」が末尾 10 字以内 → `<blockquote class="nomotoke-source-excerpt__inner-quote">` (橙左ボーダー + 薄橙背景)
- **C. 文末改行**: 段落 >80 字 + 2 文以上 → `「。」「！」「？」` 後に `<br>` 軽改行

これら 3 つは pure rule-based、LLM 不使用、追加コスト 0。

### mail HTML (281cd88)

- `_build_x_post_intent_url(title, url)` 新設: `https://x.com/intent/tweet?text=<title>&url=<url>` を生成。X 無料公開 endpoint、API key 不要、課金なし
- `build_body_html_per_post()` 新設: 560px container + 2 button + footer
- multipart alternative: `_BridgeMailRequest.html_body` は既存対応 (line 24-25)、HTML/text 両方添付
- text body は既存 `_minimal_body_enabled()` 仕様 (title + url) を維持 → fallback 用 + 既存 strict test を保護
- `post_gen_validate` kind は HTML 対象外 (ops 内向け)

## deploy (5 サイクル)

| service / job | before → after | 流れ |
|---|---|---|
| manual-intake-service | 00072-vug → 00074-jij | 06cca89 build → no-traffic → smoke → 100% flip |
| yoshilover-fetcher | 00445-tug → 00451-bas | 同上 |
| manual-intake-service | 00074-jij → 00076-noy | 7a2dec4 build → no-traffic → smoke → 100% flip |
| yoshilover-fetcher | 00451-bas → 00453-pet | 同上 |
| publish-notice (Job) | image:b816f06-job → 281cd88 | 281cd88 build → `gcloud run jobs update` |

build 経路: `cloudbuild_manual_intake_service.yaml` / root `Dockerfile` / `cloudbuild_publish_notice.yaml` を `_TAG=<sha>` substitution で叩く。

## 直接 WP 書き換え (1 件)

- **post 66824** 「正直言って困ってしまった」堀内恒夫氏 記事
  - 旧引用ブロック: title 繰り返し + 5/5(火) 5:20配信 + 160 + コメント160件 + 力投する戸郷翔征（カメラ・清水 武）+ 本文 + 【選手名鑑】… を `<br>` 一連
  - 新引用ブロック: 段落 5 つを `<p style="margin:0 0 1.1em">` で wrap (空白多め)、noise 全除去
  - REST PATCH 1 回、status=publish 維持
  - user 「66824 直接 + システム恒久」両方の指示

## scheduler 変更 (1 件)

- **giants-realtime-trigger**: `*/15 17-21 * * *` → `0,30 17-21 * * *`
  - 17-21 時帯の RSS realtime polling を 15 分→30 分間隔に半減
  - 1 日 20 回 → 10 回
  - 変更直後の 20:00 JST 発火で HTTP 200 成功確認
  - schedule field のみ変更、URL/method/body/retry すべて維持

## verification (Phase 3 log diff)

- pytest: extractor 26 / manual_intake 89+39 subtests / publish_notice 193+33 subtests、regression 0
- AST + py_compile: PASS
- Cloud Build: 3 image SUCCESS
- Cloud Run revision describe: 全 image 新タグに切り替わり確認
- /health smoke: manual-intake `{"ok": true}`, fetcher `OK`
- 全 17 ENABLED scheduler 最新発火確認、stop 0
- extractor 単体 smoke: Yahoo fixture で noise 5 種すべて removed、body 3 行 preserved

## 「30 分 mail 来ない」事象の真因 (user 質問への精査)

- publish-notice の 19:46 JST run: `sent=0 suppressed=10`
- suppressed 10 件の内訳:
  - 4月の過去 post 8 件 (id=63082, 63091, 63093, 63127, 63155, 63182, 63184, 63186) — `【要確認】` review pending
  - post_gen_validate 2 件 — RSS 生成段階 skip
- `PUBLISH_ONLY_FILTER` env で意図的に publish 系のみ通す設定、review/skip 系は user に送らない
- 実 publish (66xxx) は 19:16 run で sent=4 / 19:31 run で sent=2 で全部送信済
- 19:31 以降の publish 0 件 → 19:46 run で sent=0、user 体感「30 分来ない」

軽微 observation: 過去 63xxx post が毎回 emit され続けている (履歴有のはずなのに) — suppress で実害なしだが scanner state cleanup を別 ticket で検討余地

## 規模感

- 約 420 行追加 (コード 250 / test 170)
- 17 件 test 追加
- 約 6 時間連続自律進行
- user 判断 = GO のみ数回 (66824 patch GO / A+B+C 全部 GO / HTML mail A GO / scheduler 変更指示)
- 完全無料 (X API 不使用 / Gemini 増加 0 / 新 source 0 / build 5 回分のコストのみ)

## 残し / 次回観察

- 次の自動 publish (giants-realtime / postgame-auto-daily 等) で HTML mail の実機表示を user 確認
- 引用ブロックの段落 `<p>` レンダリングが今後 publish される全記事で発火
- Yahoo 以外の媒体 (hochi.news / sponichi 等) で別 noise pattern が出れば pattern 追加
- 63xxx post の毎回 emit 件は別 ticket 候補 (P3)

## 触らなかったもの (constraints 遵守)

- WP DB / wp_posts / wp_postmeta / wp_options (66824 の content REST PATCH 以外)
- noindex / canonical / SEO 設定
- X API (intent URL のみ、無料 endpoint)
- Gemini call (増加 0)
- source 追加 (Yahoo / 報知 / sponichi 既存のみ)
- PAUSED scheduler 13 件 (giants-weekday-pre/post / weekend 系 / yoshilover-fetcher-job 等) — 触らない
- secret / env 値 (env 変更 0)
