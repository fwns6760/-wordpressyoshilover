# 2026-06-11 トップページ データブロック コンパクト化 (063 v0.22.0)

- 13:40 JST | 事象確認 | user報告「トップ表示が変・ユーザビリティ崩れ」 | headless screenshot (desktop 1280 / mobile 390) | 原因=データカードが v0.18.0 の5枚→v0.21.17 で14枚に増殖、モバイルでブロック高さ約1700px、速報帯が約2画面下に押し出し
- 13:45 JST | 修正 | 063 plugin | a6446e15 (v0.22.0) | カードを縦型大判→アイコン+タイトル横並びチップ型、モバイルはリード文/サブテキスト非表示。高さ mobile 約1700→370px / desktop 約900→390px。内部リンク14本・h3アンカーは全維持。ローカルPHP stub renderでプレビュー検証済
- 13:47 JST | zipビルド | build/063-v22-wp-admin/yoshilover-063-frontend.zip | next=user手動upload (wp-admin プラグイン置換) + WP Rocketキャッシュクリア → `?nc=` でverify
