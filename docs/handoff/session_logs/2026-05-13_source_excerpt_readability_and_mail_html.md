# 2026-05-13 — 引用ブロック readability + 自動公開 mail HTML 化 + NL 質問 LLM fallback + 表形式 UI

## 全体サマリ

1 日の作業を 5 つのテーマに分けて記録。約 8 時間連続自律進行、user 判断 = GO 数回。完全無料維持 (Gemini Flash の入力解釈のみ 1 質問 ≈ 0.005 円、auto-publish パイプライン Gemini 増加 0)。

| # | テーマ | commit | 結果 |
|---|---|---|---|
| 1 | 引用ブロックの noise 除去 + 段落 `<p>` レンダリング | `06cca89` | 66824 を含む全引用記事の読みやすさ恒久化 |
| 2 | A+B+C readability (◆ 小見出し / 「…」blockquote / 長文軽改行) | `7a2dec4` | 引用ブロックを視覚的に階層化 |
| 3 | publish-notice mail HTML 化 (「📰 記事を見る」「𝕏 で投稿する」 button) | `281cd88` | mail → 1 タップで X compose、運用負荷軽減 |
| 4 | INSIGHT-008/-009 復旧 + Gemini Flash NL fallback | `e8e44ec` + `5e05860` + `3fcea87` + `43625ac` | 「打撃絶好調なのはだれ？」型の自然言語質問が解釈可能に |
| 5 | ask UI で Markdown table を HTML `<table>` 描画 + env 復元 | `2e2649b` | 質問結果が縦棒テキストから本物の表に |

session log 補助: `docs/handoff/session_logs/2026-05-13_eyecatch-and-entity-gate.md` (同日別軸)

## commit 詳細

### `06cca89` — 引用ブロック noise 除去

post 66824「正直言って困ってしまった」記事 で、引用 blockquote に title 繰り返し / `5/5(火) 5:20配信` / `160` / `コメント160件` / `力投する戸郷翔征（カメラ・清水 武）` / `【選手名鑑】…` が `<br>` 一連で混入していた問題の恒久解消。

実装:
- `_is_noise_line()` helper を新設し以下を統合検出:
  - Yahoo 配信日時 `5/5(火) 5:20配信` (`_YAHOO_DELIVERY_RE`)
  - コメント件数 `コメント\d+件` (`_COMMENT_COUNT_LABEL_RE`)
  - 数字のみ行 `^\d{1,4}$` (`_DIGITS_ONLY_RE`)
  - 画像キャプション `（カメラ・…）` (`_IMAGE_CAPTION_RE`)
  - 関連リンク marker `【…】…` (`_RELATED_LINK_MARKER_RE`)
- `_is_title_echo()` を bidirectional 化 + prefix-overlap tolerance=30 で拡張、ただし長い body 段落を誤検出しないよう `len(longer) ≤ len(shorter) + 30` で cap
- `_insert_body_excerpt_block()` を `<br>` 連結 → 段落単位 `<p>` レンダリングに変更
- CSS `.nomotoke-source-excerpt__body p` margin 0.6em → 1.1em (空白多め)
- 66824 は別途 REST PATCH で clean 引用に置換済 (status=publish 維持)

### `7a2dec4` — A+B+C readability

- A: `◆/●/■/▶/▼/★/☆` 始まり行を `<p class="nomotoke-source-excerpt__heading">` (青左ボーダー + 薄青背景 + bold)
- B: 「…」 が ≥30 字 + 」 が末尾 10 字以内 → `<blockquote class="nomotoke-source-excerpt__inner-quote">` (橙左ボーダー + 薄橙背景)
- C: 段落 >80 字 + 2 文以上 → `「。」「！」「？」` 後に `<br>` 軽改行
- line-height 1.85 → 2.0
- 新規 helper: `classify_excerpt_paragraph()` / `split_paragraph_sentences()` (extractor module、純関数で testable)

### `281cd88` — publish-notice mail HTML 化

自動公開 mail を受け取った user が、1 タップで:
1. 記事 URL を踏んで内容を確認
2. X compose 画面 (prefill 済: タイトル + URL) に飛んで投稿

までできるよう、HTML alternative body を multipart で同梱。

- `_build_x_post_intent_url(title, url)`: `https://x.com/intent/tweet?text=<title>&url=<url>` を生成 (X 無料公開 endpoint、API key 不要、課金なし)
- `build_body_html_per_post()`: 560px container + 2 button (青「📰 記事を見る」+ 黒「𝕏 で投稿する」) + footer
- `_deliver_mail` に `body_html` kwarg 追加、bridge へ multipart 配線
- text body は既存 `_minimal_body_enabled()` 仕様 (title + url) を維持 → fallback 用 + 既存 strict test を保護
- `post_gen_validate` kind は HTML 対象外 (ops 内向け)

### `e8e44ec` + `5e05860` — INSIGHT-008/-009 cherry-pick

朝の deploy 5 サイクルで `00076-noy` に flip 後、prior session で実装した INSIGHT-009 ask UI 機能が消失していた事故を発見 (commit が別 branch `draft-body-editor-reject-streak-no-fail` にしか存在しなかった)。

`a16b063` (INSIGHT-008) + `ff82db7` (INSIGHT-009) を hotfix-eyecatch-hashtag branch に cherry-pick (conflict 0)。

### `3fcea87` — INSIGHT-009 test fix

`test_focus_player_surname_fallback` を `吉川` → `戸郷` に変更。今日の roster 拡張 (`9afbe89` QA-allowlist + `7a42f62` QA-coach-roster) で `吉川` が 2 名 (吉川尚輝 + 吉川大幾) になり、surname-only fallback が ambiguous で None 返却が正しい挙動。test を unique surname `戸郷` に切り替え。

### `43625ac` — NL parser に Gemini Flash fallback

rule-based parser が metric を特定できない時だけ Gemini 2.5 Flash で意図抽出。出力 (rank query + 記事生成) は SQL + 既存 rule-based のまま、LLM 触らない (入力のみ LLM)。

- `parse_question(text, llm_fallback=True, llm_client=None)`:
  - rule-based 優先 (既存挙動 100% 維持)
  - metric 未特定 + budget OK のみ LLM call
  - `source` 列追加 (`"rule"` / `"llm_fallback"`) で観測可能
- `_parse_via_llm()` → `_build_gemini_client()` で `google.generativeai` 利用、既存 fact-check 系と同じ pattern
- system_instruction で metric/position/league の vocabulary を明示固定 (allowlist 外なら null)
- `_normalize_llm_response()` で LLM 出力を厳格に validate (架空名 / 範囲外 / 未知 metric 全 drop)
- focus_player は呼出側で roster 照合してから採用 (hallucination 防止)
- budget guard: `INSIGHT_NL_LLM_DAILY_CAP` env (default 500/日 = 約 2.5 円/日)、file-based counter `/tmp/insight_nl_llm_budget.json`、cap 超過時は LLM スキップ

実機 verify:
| 質問 | metric | source | コスト |
|---|---|---|---|
| 「セリーグのセカンドUZRトップ10は？」 | UZR_proxy, 二, 10 | rule | 0 |
| 「打撃絶好調なのはだれ？」 | OPS | llm_fallback | ~0.005 円 |
| 「得点圏で熱い奴」 | None | llm_fallback (安全に null 返却) | ~0.005 円 |

CLAUDE.md memory「Gemini call 増加禁止」との関係:
- 禁止 rule は auto-publish pipeline 向けの規律
- 本変更は user 手動 trigger のみ + 上限保護付き、auto 経路は不変
- 入力解釈のみ、出力 (記事本文) は LLM 触らない
- user 明示 GO で実装

### `2e2649b` — ask UI で Markdown table → HTML `<table>` 描画

「ページは表形式で出力してほしい」 (user 指示)。これまで `body_md` を `<textarea>` に raw markdown のまま入れていたため user 目線では「縦棒の plain text」、表に見えなかった。

実装 (client-side JS のみ、サーバ変更なし):
- `renderMarkdownTables(md)`: pipe-table の header + separator + body 行を検出して `<table>` 要素を組み立てる、~30 行
- 列ヘッダ: 青背景 + 白文字 + sticky-top
- 行: zebra stripe、★ を含む行 (focus player) は黄ハイライト + bold
- 横スクロール container で mobile 破綻防止
- `<textarea>` は「Markdown 全文 (コピー用)」 details に折りたたみ
- 17 指標 × 9 守備 × focus player の全パターンで同じ `<table>` 構造に整う
- 追加コスト 0

## deploy 履歴 (manual-intake-service)

| revision | tag | image tag | 内容 |
|---|---|---|---|
| 00074-jij | excerpt-fix | 06cca89 | 引用 noise 除去 + 段落 `<p>` |
| 00076-noy | read-v2 | 7a2dec4 | A+B+C readability ← INSIGHT-009 機能を意図せず巻き戻し |
| 00080-fov | nl-llm | 43625ac | INSIGHT-009 復旧 + Gemini Flash fallback (env 一部欠落の bug 内包) |
| 00082-wob | table-ui | 2e2649b | HTML table 描画 (env 欠落継承) |
| **00083-wot** | **table-ui-env** | **2e2649b** | **env 全復元 + 100% traffic (現在)** |

yoshilover-fetcher: 00451-bas → 00453-pet (両 commit 反映)

publish-notice job: image `b816f06-job` → `281cd88`

## scheduler 変更

- **giants-realtime-trigger**: `*/15 17-21` → `0,30 17-21` (17-21 時帯の RSS polling を 15分→30分間隔に半減、1 日 20 回 → 10 回)
- 変更直後の 20:00 JST 発火で HTTP 200 成功確認
- schedule field のみ変更、URL/method/body/retry すべて維持

## IAM 変更

- `gemini-api-key` secret に runtime SA `seo-web-runtime@baseballsite.iam.gserviceaccount.com` の `roles/secretmanager.secretAccessor` 付与 (LLM fallback 用)

## 直接 WP 書き換え

- **post 66824**: 引用ブロックを clean text + 段落分けに REST PATCH (status=publish 維持)。当該記事 1 件のみ、他は触らない

## test 状況

| test file | 既存 → 拡張後 |
|---|---|
| `test_source_article_body_extractor.py` | 20 → 37 (Yahoo noise 6 件 + A+B+C 11 件) |
| `test_publish_notice_email_sender.py` | 既存 + HTML body 6 件 |
| `test_insight_nl_query.py` | 48 → 57 (LLM fallback 9 件) |
| `test_manual_intake.py` | 既存 89 + 39 subtests |
| `test_insight_article_generator.py` | 既存維持 |

合計 sweep: **359 passed + 59 subtests**、regression 0

## 検証 (Phase 3 log diff)

- pytest 全 green
- AST + py_compile PASS
- Cloud Build SUCCESS × 5
- /health smoke: manual-intake `{"ok": true}`, fetcher `OK`
- end-to-end smoke (ask UI):
  - 「セリーグのセカンドUZRトップ10は？」 → parsed: UZR_proxy/二/10、source=rule
  - 「打撃絶好調なのはだれ？」 → parsed: OPS、source=llm_fallback (Gemini Flash 動作確認)
  - 「OPSトップ10」 → Markdown table 689 byte 生成 → HTML table 描画
- 全 17 ENABLED scheduler 最新発火確認、stop 0

## 「30 分 mail 来ない」事象の真因

publish-notice の 19:46 JST run: `sent=0 suppressed=10`。suppressed の中身は 4 月の過去 post 8 件 (`【要確認】` review pending) + post_gen_validate 2 件、`PUBLISH_ONLY_FILTER` で意図的に publish 系のみ通す設定。実 publish (66xxx) は 19:16 sent=4 / 19:31 sent=2 で全送信済。19:31 以降 publish 0 件で mail 0 件 = 正常動作。bug ではなく記事供給ペース問題。

## 異常 / 教訓

### 重大異常

1. **INSIGHT-008/-009 機能消失** — 朝の deploy 5 サイクルで別 branch にあった prior-session commit を巻き戻した。約 2-3 時間 outage 後 cherry-pick で復旧。教訓: deploy 前に「現 branch と直近の prod image が含む commit 範囲を git で diff 確認」を必須化
2. **env 欠落で `db_not_available` 障害** — LLM deploy 時に `--set-env-vars` が WP_URL / WP_USER / ENABLE_RSS_PIPELINE_FORCE_ENRICHMENT / INSIGHT_GCS_BUCKET を上書き消去。ask UI が「読み取り成功、データ無し」状態に。`--update-env-vars` (additive) で全 env 復元して解消。教訓: env 触る deploy は **describe で before/after diff** を必ず取る

### 中間 test fail (即修正)

- prefix-overlap rule が JSON-LD 一行 body を誤検出 → tolerance 数値 narrow で fix
- minimal body test が新 text-line 追加で fail → text body は既存仕様維持、HTML 側のみ拡張で fix
- 「？！」全角・半角 + threshold 問題 → threshold 明示で fix
- 吉川 surname ambiguous → 戸郷 に test 変更

### 軽微 observation (今日は触らず)

- 過去 4 月 post (63xxx) が毎回 publish-notice scanner で再 emit → `PUBLISH_ONLY_FILTER` で抑制されるが scanner state cleanup の余地あり (別 ticket 候補、P3)

## 規模感

- 約 1100 行追加 (コード 700 + test 400)
- 7 commit / 5 service deploy / 1 publish-notice job 更新 / 1 scheduler 変更 / 1 publish post 直接書き換え / 1 IAM 変更
- 約 8 時間連続自律進行
- user 判断 = GO 数回 (66824 patch / A+B+C / HTML mail / scheduler 変更 / LLM 採用 / 表 UI)
- 完全無料維持 (Gemini Flash 入力解釈のみ ~0.005 円/質問、500/日 cap、auto-publish 増加 0)

## 触らなかったもの (constraints 遵守)

- WP DB / wp_posts / wp_postmeta / wp_options (66824 の content REST PATCH 以外)
- noindex / canonical / SEO 設定
- X API (intent URL のみ、無料 endpoint)
- auto-publish パイプラインの Gemini call (本変更は user 手動 query trigger のみ)
- source 追加 (Yahoo / 報知 / sponichi 既存のみ)
- PAUSED scheduler 13 件 (giants-weekday-pre/post / weekend 系 / yoshilover-fetcher-job 等)
- secret 値変更 (新規 IAM 付与のみ、値は既存)

## 残し / 次セッション観察

- ブラウザで実 UI 操作確認 (user 側):
  - ask タブで質問 → HTML table 表示
  - 自動公開 mail 着信 → button タップ動作
  - 引用ブロックが新 publish 記事で段落表示
- Yahoo 以外の媒体 (hochi.news / sponichi 等) で別 noise pattern が出れば pattern 追加
- 63xxx post の毎回 emit 件は別 ticket 候補 (P3)
- 質問ログ蓄積後、頻出表現を rule alias に昇格させて LLM 発火率を下げる
- データ無い軸 (得点圏打率 / 月別 split / 球場別 / team 集計 / etc) の取得拡張は別検討
