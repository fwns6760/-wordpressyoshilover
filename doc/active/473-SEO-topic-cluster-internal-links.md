# 473-SEO トピッククラスター内部リンク（編成クラスタ）

- status: GOING_LIVE / owner: Claude / 2026-06-05 / user GO
- 目的: SEO強化。data表の選手名→選手ページ内部リンク + 編成クラスタ(draft/fa/trade)横リンク + 構造化データ
- 実装:
  - src/data_site_internal_link.py: linkify(名前→/data/<slug>/、ページ有る人だけ) / roster_moves_nav(クラスタ横リンク) / breadcrumb_jsonld
  - src/tools/build_player_slug_map.py → config/data_site_player_slugs.json(958キー、WP全選手ページ name→slug)
  - draft/fa/trade テンプレに linkify 適用 + 横リンクバー + JSON-LD
- 効果(render実測): 内部リンク draft400 / fa35 / trade743 ≈1,178本新規。legendsは既に名前リンク済。
- クラスタ地図: ピラー=/data/、編成クラスタ=draft↔fa↔trade 相互リンク、各表名→選手ページ(縦リンク)
- 運用: 選手ページ増時は build_player_slug_map 再実行→config更新→再ビルド
- 次候補: 各選手ページから draft/fa/trade への逆リンク、編成ピラーページ新設、網羅ページ量産
