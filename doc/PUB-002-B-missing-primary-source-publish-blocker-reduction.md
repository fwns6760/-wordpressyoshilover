# PUB-002-B missing-primary-source publish blocker reduction

## meta

- owner: Claude Code(棚卸し + 設計、実装は Codex 便)
- type: ops / publish blocker reduction / source recovery
- status: READY(72h draft 棚卸し未着手)
- priority: P2(**PUB-004 安定運用後の品質改善**として後続、PUB-002-A の Green G2 hit 率向上 = PUB-004-B publish 候補増加に直結、user policy 2026-04-25 21:55 lock)
- parent: PUB-002 / PUB-002-A
- created: 2026-04-25

## purpose

公開候補から落ちている `missing_primary_source` を減らす。
72h 以内 draft で source URL が取れていない記事を棚卸しし、body 内 source footer / meta / original URL から安全に復元できる経路を設計する。

## 背景

PUB-002-A の Green G2 = 「primary source URL あり」が hit しない draft が多い。
4/24 観測時点で `missing_primary_source: 45` 件(master_backlog 記載、086 land 前の数値)。
本日(4/25)`089 editor-source-url-body-fallback` ✓ 着地で `_extract_source_urls` に body `参照元` footer fallback 追加済 → 一部解消したが、未確認。

## 不可触

- 実 publish / X 投稿 / RUN_DRAFT_ONLY flip
- front / plugin / build artifacts
- secrets / .env / automation / scheduler
- creator 主線の大改修(narrow 修正のみ)
- baseballwordpress repo

## 棚卸し手順(Claude 側、read-only)

### Step 1: 72h draft pool 取得

```python
from src.wp_client import WPClient
c = WPClient()
drafts = c.list_posts(status="draft", per_page=100, orderby="modified", order="desc")
# filter modified within 72h
```

### Step 2: missing_primary_source 検出

各 draft で:
- `body_text` 内 PRIMARY_SRC regex (`Yahoo!プロ野球|報知|スポーツナビ|日刊スポーツ|スポニチ|デイリー|サンケイ|スポーツ報知|読売新聞`) hit / not hit
- `source_block` 抽出(本文末尾 `参照元:` footer)
- `source_urls` 抽出(body_html 内 http(s) URL list)
- meta fields 内 `_yoshilover_source_url` / `original_url` / `canonical_source_url` 等(089 関連)の確認
- title / excerpt 内に source 名だけ書かれているケース(URL なし)

### Step 3: 原因分類

| 原因タグ | 内容 | 想定件数 | 復元可能性 |
|---|---|---|---|
| `no_source_anywhere` | 本文 / footer / meta いずれにも source 痕跡なし | ? | low(creator 側 fix 必要) |
| `source_name_only` | 「報知新聞」等 名前のみ、URL なし | ? | medium(name → 公式 URL mapping 可) |
| `footer_only_no_url` | `参照元:` footer に名前 + 改行、URL 別行 / 抽出失敗 | ? | high(089 footer fallback で拾える、要 verify) |
| `meta_only_no_body` | meta に source URL あり、body には未表示 | ? | high(meta → body inline link 補完で解決) |
| `twitter_only` | Twitter URL のみ、primary 媒体なし | ? | low(twitter は primary とみなさない方針) |
| `social_news_subtype` | RSS / X 由来で primary 媒体 mapping なし | ? | low(社内 source mapping 表が必要) |

### Step 4: 最小修復案

- `footer_only_no_url`: 089 fallback の効果を confirm(Codex `_extract_source_urls` の追加 grep)
- `source_name_only`: name → 公式 URL の static mapping table を `src/source_name_to_url.py` に持つ narrow便
- `meta_only_no_body`: editor 側で meta の source_url を body 末尾に inline 出力する narrow便
- `no_source_anywhere`: creator fix(別 ticket、本 ticket scope 外)
- `twitter_only`: PUB-002-A G2 で意図的に hold 維持(変更なし)

### Step 5: Codex 実装便 prompt 起草

棚卸し結果と原因分類が揃ったら、優先度高い 1〜2 修復案を Codex 便 prompt 化:

- `_extract_source_urls` regex 強化 narrow(footer_only_no_url 系)
- `src/source_name_to_url.py` 新規 + editor adapter narrow(source_name_only 系)

## 完了条件

1. 72h draft の `missing_primary_source` 件数判明
2. 原因分類(6 タグ前後)+ 件数表が揃う
3. 最小修復案 3〜5 件提示、Yellow / Green への昇格見込み件数推定
4. Codex 実装便 prompt が 1〜2 本起草される(本 ticket 内に貼る)
5. PUB-002-A の Green G2 hit 率上昇予測値が出る

## 関連 file

- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(G2 検証要件)
- `src/_extract_source_urls`(089 fallback、再 verify 対象)
- commit `c0c91a0`(089 land = body footer fallback 追加)
- commit `f3ee1d5`(090 = X / Twitter primary domain extension)

## stop 条件

- 棚卸し対象が 100 drafts 超 → 本 ticket scope = 72h、超えたら別 ticket
- 修復案が published 記事の書き換えを必要とする → 本 ticket scope 外、別 ticket(`PUB-002-B-published-rewrite`)
- creator 主線の大改修が必要 → escalate user 判断
