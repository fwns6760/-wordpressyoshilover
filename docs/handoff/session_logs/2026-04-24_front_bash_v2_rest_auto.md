# front バシバシ便 v2 (2026-04-24 夕~夜 JST, REST 自動化完了)

Claude Code = yoshilover front 専任 owner の 2 ラウンド目。CSS push を REST 経由で完全自動化した。

## 役割変更 (memory に保存済)

- `/home/fwns6/.claude/projects/-home-fwns6-code-wordpressyoshilover/memory/user_role_front_owner.md`
- commit/push/deploy すべて Claude Code 管轄
- よしひろさんの手作業は**永久ゼロ**（plugin 有効化 1 回のみ済）

## CSS REST 自動化 (commit `f2c9eea`)

- `src/plugin-css-push/yoshilover-css-push.php` + `build/plugin-css-push/yoshilover-css-push.zip` 新設
- WP admin で ZIP upload + 有効化済 (2026-04-24 夜、よしひろさん 30 秒作業で完了)
- エンドポイント:
  - `GET /wp-json/yoshilover/v1/custom-css` → 現在 CSS + sha1 + bytes
  - `PUT /wp-json/yoshilover/v1/custom-css` body `{"css": "..."}` → 追加CSS 更新 + cache flush
- 認証: Basic auth (`WP_USER` / `WP_APP_PASSWORD` from `.env`、python-dotenv 経由)

## git index.lock 競合対策 (plumbing 3 段)

Codex が別便で index.lock 保持する場面があるため、以後 Claude Code は常に plumbing で commit:

```bash
IDX=/tmp/myidx_$$
GIT_INDEX_FILE=$IDX git read-tree HEAD
GIT_INDEX_FILE=$IDX git update-index --add <path>
TREE=$(GIT_INDEX_FILE=$IDX git write-tree)
HEAD_SHA=$(git rev-parse HEAD)
COMMIT=$(echo "$MSG" | git commit-tree "$TREE" -p "$HEAD_SHA")
git update-ref refs/heads/master "$COMMIT" "$HEAD_SHA"
git push origin master
```

Codex の `.git/index` と `.git/index.lock` に**一切触らない**。

## 今便で push した CSS batch (全 plumbing + REST 自動反映)

| # | commit | 内容 |
|---|---|---|
| 1 | `2ce3b9c` | topic-hub 巨人オレンジ hero strip (black panel + orange 5px + white cards + THIS WEEK) |
| 2 | `93b5864` | home 最近の投稿 / sidebar hover / SNS 巨人 3 色統一 |
| 3 | `67ccff2` | breaking-strip / article-bundles 外枠圧 |
| 4 | `ac6f086` | 関連記事 block + article-bundles card hover + T-028 RESOLVED |
| 5 | `bf8c972` | 本文 h2/h3/quote/table/hr/list 巨人統一 |
| 6 | `5a886ed` | 記事タイトル hero / eyecatch / breadcrumb / コメント |
| 7 | `8a2f148` | TOC / シェア / 前後ナビ |
| 8 | `13515c6` | c-pageTitle アーカイブ hero / eyecatch hover zoom (plumbing 初投入) |
| 9 | `f895e03` | footer 段組 / 検索フォーム pill |
| 10 | `080d5c3` | SWELL blocks (button / capbox / FAQ / step) |
| 11 | `d150c5b` | pagination pill / sp-bottom / figcaption |
| 12 | `7199a25` | swell-balloon / blogCard / notice / author box |
| 13 | `f2c9eea` | **yoshilover-css-push plugin** (REST 自動化仕込み) |
| 14 | `7093cde` | 本文可読性 (15.5 / line-height 1.85) + strong 巨人マーカー |
| 15 | `00f1d3f` | eyecatch 16:9 ratio lock + overlay + cat-label Oswald |
| 16 | `2af026f` | 404 / 検索 empty hero / X follow CTA / 本音ボタン pill |
| 17 | `281adef` | front-density subtype accent / 日付 Oswald / コメント pill |

(+ docs/session log commit `c894b54` from round 1)

## CSS 累計増加

- 初期: 43,166 bytes
- 現在: 85,702 bytes (+98%)
- 巨人 3 色 (orange #F5811F / black #1A1A1A / white) に寄せつつ、カテゴリ機能色 (`--blue` 等) は残す方針

## smoke 結果 (2026-04-24 夜、REST PUT 後)

- TOP / POST / CATEGORY 各ページで batch 10-18 の主要 18 ルールを inline `<style>` で検出
- DOM 回帰ゼロ (topic-hub=18 / sns=6 / bundles=90 / breaking=44 / related=1 変化なし)
- 旧 94KB の重複 bloat も REST PUT で解消

## 次の候補 (未着手)

- sidebar X banner の inline-style 上書き
- prosports family link の card pattern
- 記事末 yoshi-x-follow-cta を実 DOM に注入 (plugin 側 `the_content` filter)
- category 別の h2 accent color 分岐 (試合速報 orange / 選手情報 blue 等)
- 記事詳細 wide view (サイドバー折り畳み) トグル

## 関連 commit ログ

```
281adef front(home+meta): front-density subtype accent + 日付 Oswald + コメント数 pill
2af026f front(404+cta+respond-btn): 404 hero / X follow CTA / 本音ボタン巨人統一
00f1d3f front(eyecatch+cat-label): アイキャッチ 16:9 lock + hover overlay + カテゴリ chip Oswald
7093cde front(article-body v2): 本文可読性 + 巨人マーカー + 強調
f2c9eea front(infra): yoshilover-css-push plugin (REST PUT/GET for 追加 CSS)
7199a25 front(swell-balloon+blogcard+notice+author)
d150c5b front(pagination+sp-bottom+image)
080d5c3 front(swell-blocks)
f895e03 front(footer+search)
13515c6 front(archive+eyecatch)
8a2f148 front(post-detail v4)
5a886ed front(post-detail v3)
bf8c972 front(article-body)
ac6f086 front(post-detail v2)
67ccff2 front(post-detail)
93b5864 front(home+sidebar+sns)
2ce3b9c front(topic-hub)
```
