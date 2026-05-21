# 416 — manual_intake チケット系 article_type 追加 (チケット情報 / チケット交換 / スコアブック)

## status: PRE-WORK (Markdown のみ着地、 user GO 待ち)

## 背景

user 指摘「チケット情報、 チケット交換、 スコアブックなどの記事も出したい (巨人の)」。
直前 commit `8dc5e54` で 6 種 article_type (ドラフト / 2軍・育成 / OB情報 / 補強・移籍 /
トレード / 助っ人) を追加し manual-intake を 11 → 17 種にしたばかり。 本 ticket はその
延長で、 巨人ファン向け運用情報系 3 種を更に追加する narrow fix。

config/categories.json 既存 8 active category 内で完結 (新 WP category 解放なし =
user 判断境界 §11 不要、 自律可)。

## 追加予定 article_type (3 種)

| article_type | route 先 category | subtype | template_key |
|---|---|---|---|
| チケット情報 | 球団情報 (669) | ticket | nomotoke_card_short_news_url_v1 |
| チケット交換 | 球団情報 (669) | ticket_trade | nomotoke_card_short_news_url_v1 |
| スコアブック | 試合速報 (663) | scorebook | nomotoke_card_short_news_url_v1 |

## auto_guess 拡張 keyword

| keyword (title / summary 内) | → article_type |
|---|---|
| 「チケット先行販売」 / 「チケット予約」 / 「販売スケジュール」 / 「シーズンチケット」 | チケット情報 |
| 「チケットトレード」 / 「公式リセール」 / 「リセール販売」 / 「ファン同士で譲渡」 | チケット交換 |
| 「スコアブック」 / 「スコアシート」 / 「スコア表」 | スコアブック |

---

## 3. 今回触らない範囲

- `src/tools/manual_intake.py` の **その他 path**
  - 触るのは `ARTICLE_TYPE_OVERRIDES` dict 末尾への 3 entry 追加
  - `_auto_guess_article_type` 末尾への keyword 検出 1 ブロック追加
  - 既存 17 entry / 既存 auto_guess priority 順 は一切並べ替え / 改変しない
- `src/manual_intake_service.py` (UI dropdown は `ARTICLE_TYPE_CHOICES` から動的生成、 HTML 側不変)
- `src/nomotoke_card_renderer.py` (既存 `short_news_url_v1` renderer 流用、 改変なし)
- `config/categories.json` (WP category 既存 8 件、 追加なし)
- `src/rss_fetcher.py` の `classify_category` / subtype router (自動 RSS path)
- `src/wp_client.py` (WP REST 既存 path)
- WP 既存記事 / X 投稿 / publish-notice / x-post-mail-lane
- env / Secret Manager / Scheduler / IAM / Dockerfile / cloudbuild
- 並走 session の in-flight files (絶対触らない):
  - `src/x_post_branding_gen.py`
  - `src/analysis/pregame_themes.py`
  - `src/tools/run_x_post_mail.py`
  - `src/kobayashi_meigen_mail_lane.py`
  - `src/tools/run_kobayashi_meigen_mail.py`
  - `tests/test_kobayashi_meigen_mail.py`

## 4. 影響範囲

- **src/tools/manual_intake.py**
  - `ARTICLE_TYPE_OVERRIDES` に 3 entry 追加 (17 → 20)
  - `_auto_guess_article_type` 末尾に keyword 検出 1 ブロック追加 (return "コラム" 直前)
- **tests/test_manual_intake.py**
  - `test_choices_tuple_includes_auto_and_overrides` の hard count 18 → 21 update
  - 新規 3 種 auto_guess 用 test class 追加 (5-8 件想定)
- **Cloud Run manual-intake-service**
  - image rebuild + deploy で UI dropdown 18 → 21 種に
  - cost ¥0 (Cloud Build 1 回、 無料枠内)
- **既存 path / 既存 17 entry / dropdown 既存表示順 / category mapping**: 全て不変

## 5. 実行予定テスト

| phase | test | 期待 |
|---|---|---|
| phase 1 (触る前 grep) | `grep -n "チケット\|スコアブック\|scorebook\|ticket_trade" src/ tests/` | 既存使用箇所 = 0 確認 |
| phase 2 (書いた後) | `python3 -m py_compile src/tools/manual_intake.py` | OK |
| phase 2 | `python3 -m py_compile tests/test_manual_intake.py` | OK |
| phase 2 | `python3 -c "import ast; ast.parse(open('src/tools/manual_intake.py').read())"` | OK |
| phase 2 | `python3 -m pytest tests/test_manual_intake.py -x --tb=short` | 既存 104 + 新規 5-8 = 109-112 件 全 pass、 regression 0 |
| phase 3 (fire 後) | `curl -s -o /dev/null -w "%{http_code}\n" https://manual-intake-service.../health` | 200 |
| phase 3 | `curl -s https://manual-intake-service.../ \| grep -oE '<option value="[^"]+"' \| wc -l` | 21 |
| phase 3 | grep で新 3 種 (チケット情報 / チケット交換 / スコアブック) が live HTML に出現 | 3/3 出現 |
| phase 3 | 既存 17 種 + auto が live HTML に出現 | 18/18 維持 |

## 6. STOP 条件

以下のいずれかで作業中断、 user に報告:

- py_compile / ast.parse で syntax error
- pytest baseline で既存 104 件中 1 件でも fail (regression 検出)
- 新規 test が pre-deploy で fail
- Cloud Build SUCCESS しない (image push fail)
- Cloud Run deploy が revision 起動 fail / traffic routing fail
- deploy 後 `/health` が 200 を返さない
- deploy 後 dropdown に新 3 種のいずれかが出現しない、 または既存 17 種が消失
- 並走 session の dirty file (§3 不可触 list) が staged に紛れ込む (`git diff --cached --name-status` で発覚時即 reset)
- ARTICLE_TYPE_OVERRIDES の既存 17 entry / 既存 auto_guess path に意図しない diff が混入
- WP category 名 spelling 不一致 (`球団情報` / `試合速報` が `config/categories.json` の name と一致しない)
- 並走 session が私の commit と push race して force push が誘発される (force push 禁止、 fetch + rebase or 待機で対応)

## 7. 禁止事項

- `src/manual_intake_service.py` / `src/nomotoke_card_renderer.py` の編集
- `config/categories.json` 変更 (新 WP category 解放は user 判断 §11)
- WP REST mutation (category create / category delete / publish / unpublish)
- env / Secret Manager / Scheduler / IAM / traffic split / Dockerfile 変更
- 並走 session in-flight files の編集 (file disjoint 必須)
- `git add -A` / `git add .` (明示 path 指定のみ)
- `--no-verify` での hook 回避
- `--no-gpg-sign` / `-c commit.gpgsign=false` 等の署名回避
- Codex 並列 fire (Claude 1 直列、 §31-D commit便 lock)
- main branch への push (`feat/377-phase1c-mail-body-excerpt` 維持)
- force push (`git push -f`)
- 既存 17 entry の並べ替え / cleanup / lint 整形を依頼外で混ぜる (minimum-diff 厳守)

## 8. 想定されるデグレ

| カテゴリ | 想定デグレ | 検知方法 | 対応 |
|---|---|---|---|
| keyword 過剰 hit | 「チケット」 単独語が generic ニュース記事の本文に出現して誤 route | dry-run + 既存 auto_guess path test 全部再 run | 「チケット情報」 「チケット予約」 等 複合語限定で keyword 定義、 単独「チケット」 は使わない |
| 既存 path 競合 | 「スコアブック」 検出が 試合結果 score-pattern path より先に hit して球場結果記事を誤 route | _auto_guess_article_type の priority 順序を read 確認 | 新 path は **既存 path の後** (return "コラム" の直前) に配置、 priority 順守 |
| ARTICLE_STYLE_MANUAL_TYPES 影響 | 現在 {コラム, ニュース} の set に新 3 種が誤って入り body layout が article-style に化ける | 該当 set を再 read、 新 3 種を一切追加しない | 不変 (新 3 種は short-news 風 layout) |
| dropdown 表示順 | dropdown の表示順が user 期待と違う (新 3 種が中間に挟まる) | live HTML で order 確認 | `ARTICLE_TYPE_OVERRIDES` の末尾に追加 = dropdown 末尾に出現、 既存順維持 |
| WP category name spelling | `球団情報` / `試合速報` 表記が `config/categories.json` と微妙に違う (例: 全角・半角 / 中点) | 1 次 source 突合 | コード上で literal を `config/categories.json` から copy、 単体 grep で完全一致確認 |
| pytest hard count | `test_choices_tuple_includes_auto_and_overrides` の 18 → 21 update 忘れ | pytest run で発覚 | 同一 commit 内で test 更新 |
| 並走 session staged 混入 | 私の commit に並走 session の dirty file が staged で紛れ込む (過去 260-MKT で 262-QA staged 混入事故あり) | `git diff --cached --name-status` で必ず verify | 明示 `git add src/tools/manual_intake.py tests/test_manual_intake.py` のみ |

## 9. 作業ログ欄

(作業実施時に 1 行 / event で追記、 format: `HH:MM JST | event | ticket | task_id/commit_hash | next`)

- 11:35 JST | GO 受領、 phase 1 grep 開始 | 416 | - | phase 2 edit
- 11:36 JST | phase 1 grep 完了 「スコアブック / scorebook / ticket_trade」 既存使用 0、 「チケット」 keyword は rss_fetcher 内 球団情報 routing に既存 (整合性 OK)、 subtype `ticket` は metadata 内別用途と namespace 衝突なし | 416 | - | edit 着手
- 11:38 JST | phase 2 edit 完了 ARTICLE_TYPE_OVERRIDES に 3 entry 追加 + _auto_guess_article_type に 416 path 1 ブロック追加 (priority: 最初は末尾配置 → fail 後 既存 path より先頭に移動)、 test 9 件追加 + hard count 18 → 21 update | 416 | - | pytest 確認
- 11:39 JST | 初回 pytest 2 fail (test_scorebook / test_ticket_trade、 score pattern + generic「トレード」 が先 hit) → 416 path block を 試合結果 path / generic「トレード」 path より **先頭** (公示 path 直前) に移動 | 416 | - | pytest 再実行
- 11:40 JST | pytest 全 pass (111 passed, regression 0) | 416 | - | phase 3 commit/push/build/deploy/verify

## 10. Regression Memo 欄

(過去事故と今回での再発防止)

### AI 事故源 meta-rule (記憶再構成 / silent skip / 自己評価 OK) — 直近反省

- 直前 commit `8dc5e54` で article_type を 11 → 17 にしたばかり = baseline は **18 entry** (auto + 17)。新 target = **21 entry**。 test hard count `18 → 21` update を絶対忘れない。
- 「チケット」 keyword が monorepo 全体で他用途 (例: 既存 WP tag / event_key / config) で使われていないか **phase 1 grep で必ず 1 次 verify**。 過去「ジャイアンツ」 を block label に入れて巨人サイト記事大半 block 事故 (2026-05-18) と同類の罠を防ぐ。
- 1 次 source 確認なしに「同名異人」「該当なし」 等の judgment を出さない (eyecatch 作業で 松本剛 / リチャードを誤って MANUAL_REVIEW にした事故、 直近)。
- 自己評価「regex OK」 で進めない。 全 license / keyword regex は実 label / 実 input で test 実行して全 case verify (今 session の license regex 罠と同様)。

### 並走 session 衝突

- branch `feat/377-phase1c-mail-body-excerpt` で別 session が `src/x_post_branding_gen.py` / `src/analysis/pregame_themes.py` / `src/tools/run_x_post_mail.py` / `src/kobayashi_meigen_mail_lane.py` / `src/tools/run_kobayashi_meigen_mail.py` / `tests/test_kobayashi_meigen_mail.py` を dirty に保有。
- 私の commit には **絶対** 混ぜない。 明示 `git add <2 files>` のみ、 `git diff --cached --name-status` で staged が 2 file だけかを確認してから commit。
- push race の可能性: 並走 session が私の前に push した場合は `git fetch` + 確認 → 必要なら commit 順 retry。 force push 禁止。
- 過去事故: 260-MKT commit に 262-QA staged が混入 (2026-04-29)。 同種の罠を完全防止。

### Cloud Run deploy / verify

- deploy 自体は速いが、 「証拠だけ」 ルール下で副作用 verify を silent skip する傾向あり (2026-05-18 反省)。 deploy 後の必須 verify:
  - `/health` 200
  - dropdown HTML の option 数 = 21
  - 新 3 種が literal で出現
  - 既存 17 種が literal で維持
- いずれか fail なら即 STOP + user 報告 (silent retry 禁止)。

---

## (作業後追記欄 — GO 後にここから埋める)

### 1. 実際に変更したファイル

### 2. diff 概要

### 3. 実行したテスト

### 4. テスト結果

### 5. 残った懸念

### 6. 新しく見つかったデグレ

### 7. 追加した回帰テスト

### 8. 次回触ってはいけない範囲
