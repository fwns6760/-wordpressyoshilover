# 417 — manual_intake に Markdown table 入力 + Gutenberg `<!-- wp:table -->` block 出力

## status: PRE-WORK → IMPL → DEPLOY → POST-WORK (autonomous 進行)

## 背景

user 指摘 「これ (チケット情報 / チケット交換 / スコアブック) は記事として飛ぶ時に
表形式で情報を出したい」。 416 で article_type 3 種を追加したが、 render 先が
既存 `nomotoke_card_short_news_url_v1` (= `<p>` リード + 出典) の short-news
layout なので表として表示されない。 任意 Markdown table を受け入れて Gutenberg
`<!-- wp:table -->` block に変換する path を追加する。

## 設計案 A (採用)

- manual_intake_service の UI に textarea「表データ (Markdown table)」 を追加
- backend で Markdown table を parse → Gutenberg `<!-- wp:table -->` block に変換
- `render_short_news_url_card` の body 組立で lead の直後 (fact_card の前) に embed
- **textarea 空欄なら現状通り** = 既存 article_type 全件で完全互換
- 全 article_type で利用可能 (416 の 3 種に限定しない、 user 編集自由度を確保)

## 3. 今回触らない範囲

- `nomotoke_card_short_news_url_v1` 既存 body 構造 (冒頭リード / fact_card / X embed / 出典 h3 / closing)
  → 新 table block は **lead の直後 + fact_card の前** に追加するのみ、 既存 block の order / 内容は不変
- 他 renderer (postgame / lineup / manager_comment / player_comment / pregame_pitcher / video / official_notice)
- `_render_lineup_table` / `_render_inning_table` (既存 table helper、 改変なし)
- `src/wp_client.py` / 自動 RSS path (rss_fetcher)
- WP REST 既存記事 / X / publish-notice / x-post-mail-lane
- env / Secret / Scheduler / IAM / Dockerfile / cloudbuild_*.yaml
- 並走 session in-flight files (`src/x_post_branding_gen.py` / `src/analysis/pregame_themes.py` / `src/tools/run_x_post_mail.py` / `src/kobayashi_meigen_mail_lane.py` / `src/tools/run_kobayashi_meigen_mail.py` / `tests/test_kobayashi_meigen_mail.py`)
- 416 で追加した article_type 6 種 (ドラフト/2軍・育成/OB情報/補強・移籍/トレード/助っ人) + 直前の 3 種 (チケット情報/チケット交換/スコアブック) の OVERRIDES table mapping

## 4. 影響範囲

- `src/nomotoke_card_renderer.py`:
  - 新 helper `_render_markdown_table_block(markdown: str) -> str | None` (Markdown table を Gutenberg `<!-- wp:table -->` block に変換)
  - `render_short_news_url_card` で `data.get("table_markdown")` を読み、 非空なら lead 直後に embed
- `src/tools/manual_intake.py`:
  - `_wp_create_draft` で render に渡す data dict に `table_markdown` を流す path (CLI / API どちらでも受け取れるよう関数 signature 拡張)
  - `_try_render_via_nomotoke` で data dict に詰める
- `src/manual_intake_service.py`:
  - HTML に `<textarea name="table_markdown" placeholder="Markdown table 形式 (任意)...">` 追加
  - POST handler で `table_markdown` field を受け取り manual_intake CLI へ pass
  - dry-run API も同様
- `tests/test_nomotoke_card_renderer.py` (or 同 file): Markdown table parser test
- `tests/test_manual_intake.py`: `table_markdown` field pass-through test
- `tests/test_manual_intake_service.py`: HTML form / API field test
- cost: ¥0 (Cloud Build 1 回 + Cloud Run rebuild 1 回)

## 5. 実行予定テスト

| phase | test | 期待 |
|---|---|---|
| phase 1 (触る前 grep) | `grep -n "table_markdown\|wp:table\b" src/ tests/` | 既存使用 0 (`wp:table` は別 helper 経由のみ) |
| phase 2 | `python3 -m py_compile` 全 4 file | OK |
| phase 2 | `python3 -m pytest tests/test_nomotoke_card_renderer.py tests/test_manual_intake.py tests/test_manual_intake_service.py` | 全 pass、 regression 0、 新規 test pass |
| phase 3 | `curl /health` | 200 |
| phase 3 | `curl /` で `name="table_markdown"` textarea 出現 | 1 件出現 |
| phase 3 | dry-run POST に `table_markdown=` 値あり + URL → response の body HTML に `<!-- wp:table -->` 含む | 含有 |
| phase 3 | dry-run POST に `table_markdown` なし → 既存 body 構造 (lead + 出典) と完全一致 | regression 0 |

## 6. STOP 条件

- syntax error / pytest regression / Cloud Build fail / Cloud Run revision 起動 fail
- `/health` ≠ 200 / textarea が UI に出現しない
- table_markdown 空 で render body が 416 commit 後 baseline と非一致 (regression)
- table_markdown 非空 で `<!-- wp:table -->` block が body に embed されない
- Markdown 不正 (例: `|` のない row、 header / separator 欠落) で renderer が exception を投げる (graceful fallback 必要)
- 並走 session dirty file が staged に混入
- WP REST mutation / env / Secret / Scheduler 変更を誘発

## 7. 禁止事項

- 既存 render 他 7 種 (postgame / lineup / manager_comment / player_comment / pregame_pitcher / video / official_notice) への touch
- 既存 `_render_lineup_table` / `_render_inning_table` helper の改変
- `nomotoke_card_short_news_url_v1` の既存 body block (lead / fact_card / X embed / 出典 / closing) の order / 内容変更
- `config/categories.json` / WP REST mutation / env / Secret / Scheduler / IAM 変更
- 並走 session in-flight files の編集
- `git add -A` / `--no-verify` / 署名回避 / force push / main push
- Markdown parser に外部 lib 依存 (再発明含めて pure Python の minimal parser)
- 416 で追加した OVERRIDES 3 entry の改変

## 8. 想定されるデグレ

| カテゴリ | 想定デグレ | 検知方法 | 対応 |
|---|---|---|---|
| Markdown 不正入力 | header / separator 欠落で renderer exception → manual_intake POST が 500 | unit test で broken Markdown を渡す | helper は `None` 返却で graceful fallback、 例外は内部 catch |
| WP block 形式 | Gutenberg `<!-- wp:table -->` の payload 形式違反で WP が block を生 HTML として出力 | live POST → WP draft で block 検査 | WP 公式 spec に従い `<figure class="wp-block-table"><table>...</table></figure>` で包む |
| XSS / HTML injection | user が `<script>` を Markdown cell に書く → 出力にそのまま echo | cell 値を `_esc` (既存 helper) で escape | 既存 `_esc` を使用 |
| pipe escape | cell 内に `\|` がある場合の分割 | unit test | 単純 `|` split のみ対応、 escape は v2 で対応 (現状 unsupported を documented) |
| 既存 short_news regression | `table_markdown` 空 path で body が 1 byte でも変わる | golden test (既存 body string 完全一致) | helper は 空 input で None 返し、 caller は None なら append しない |
| dropdown / form UI | UI 既存 form 順序が変わる、 既存 field が消える | live HTML 確認 | textarea は既存 form の末尾追加、 既存 field 順は維持 |
| 並走 session staged 混入 | 私の commit に並走 session dirty file が混入 | `git diff --cached --name-status` で必ず verify | 明示 path add のみ |

## 9. 作業ログ欄

(作業実施時に 1 行 / event)

- _(implementation start)_

## 10. Regression Memo 欄

- AI 事故源 meta-rule:
  - 「自己評価 OK」 罠: Markdown parser は実 input で多 case 検証する (header あり / なし / separator 違反 / cell 空 / 改行コード差異 / leading・trailing pipe / 全角 pipe など)。
  - 「silent skip」 罠: Gutenberg `<!-- wp:table -->` の payload format を WP REST に投げて実 draft で render 結果を 1 次 verify する。
  - 「記憶再構成」 罠: 直前まで「nomotoke_card_short_news_url_v1 が body をどう assemble するか」 を一次 source (sed -n) で再 read、 想像で書かない。
- 並走 session: 416 でも safely 完了したが、 本 ticket でも明示 `git add <files>` + `git diff --cached --name-status` で 2 重 verify。
- WP block 仕様変更 risk: Gutenberg `<!-- wp:table -->` の payload format は WP 6.x 系で安定だが、 念のため live deploy 後 WP draft 編集画面で block 認識 / table 化を user 1 次確認。

---

## (作業後追記欄 — 実施後埋める)

### 1. 実際に変更したファイル

### 2. diff 概要

### 3. 実行したテスト

### 4. テスト結果

### 5. 残った懸念

### 6. 新しく見つかったデグレ

### 7. 追加した回帰テスト

### 8. 次回触ってはいけない範囲
