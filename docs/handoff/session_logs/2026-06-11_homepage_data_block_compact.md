# 2026-06-11 トップページ データブロック コンパクト化 (063 v0.22.0)

- 13:40 JST | 事象確認 | user報告「トップ表示が変・ユーザビリティ崩れ」 | headless screenshot (desktop 1280 / mobile 390) | 原因=データカードが v0.18.0 の5枚→v0.21.17 で14枚に増殖、モバイルでブロック高さ約1700px、速報帯が約2画面下に押し出し
- 13:45 JST | 修正 | 063 plugin | a6446e15 (v0.22.0) | カードを縦型大判→アイコン+タイトル横並びチップ型、モバイルはリード文/サブテキスト非表示。高さ mobile 約1700→370px / desktop 約900→390px。内部リンク14本・h3アンカーは全維持。ローカルPHP stub renderでプレビュー検証済
- 13:47 JST | zipビルド | build/063-v22-wp-admin/yoshilover-063-frontend.zip | next=user手動upload (wp-admin プラグイン置換) + WP Rocketキャッシュクリア → `?nc=` でverify
- 13:55 JST | デスクトップ追加調査 | user「デスクトップにおいて」 | WP REST read-only | 真因2=sidebar-1のwidget 0個(30個全部wp_inactive_widgets落ち、テーマ更新等でwidget外れの典型)→ <aside id=sidebar>が空のまま右280pxが全面空白。rail自動注入hookはdynamic_sidebar()未発火で不発
- 13:58 JST | 修正 | 063 plugin | v0.22.1 | buffer fallback: 空aside検出時のみad slot+railを直接注入(dedup=rail class)。注入regexはlive HTML実物でマッチ検証済。zip再ビルド済(build/063-v22-wp-admin)
- 残課題 | wp_inactive_widgetsの30 widget復元(WP側設定変更=user判断領域)は未実施。railで埋まるため必須ではない。widget手動復元時もdedupで二重表示なし
- 14:05 JST | 追加 | 063 plugin | v0.22.2 | user指示「交流戦の導線をトップにおく」→ データカード4枚目に ⚔️セ・パ交流戦 (/data/interleague、正規URL=スラッシュなし200確認) 追加、計15枚。コンパクト維持(速報帯ファーストビュー内)をプレビュー検証済。zip再ビルド済
