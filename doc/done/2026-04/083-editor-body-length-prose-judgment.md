# 083 Editor Body Length Prose Judgment

## Why

`draft-body-editor` lane の `body_too_long` 判定が HTML 全文長(`len(body)`)を見ていたため、2026-04-24 夜の publish lane 監査では 376 drafts 中 375 件が skip された。主因は creator が出力する decoration HTML であり、実 prose は短い draft まで editor 候補から外れていた。

## What

- editor の長さ判定を HTML char から prose char へ切り替える
- prose 抽出は stdlib `html.parser.HTMLParser` で text-only を組み立てる
- `script` / `style` 内テキストは除外する
- 連続空白は単一 space に正規化する
- prose 上限 `CURRENT_BODY_MAX_CHARS = 1200` は維持する
- creator output / decoration HTML / rewrite 本体 / safety guard / runner 制御は変更しない

## Non-Goals

- creator 側の decoration 削減
- front 表示変更
- editor rewrite ロジックの改造
- guard 条件の追加や緩和
- automation / scheduler / env / secret の変更
- 別 lane の改修

## Acceptance

1. `_extract_prose_text` の単体テストが通る
2. HTML は長いが prose は短い full-template draft が editor candidate に上がる
3. 真に prose が長い draft は引き続き `body_too_long` で skip される
4. `python3 -m unittest discover -s tests` が green
5. 083 の不可触ファイルは diff 0 を維持する
