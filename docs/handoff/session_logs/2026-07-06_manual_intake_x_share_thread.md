# 2026-07-06 manual-intake 記事X共有 (おりポス+リプ) v1

user 決定の経緯: 記事URLをおりポスに貼るとXの外部リンク抑制でインプ低下 →
「チラ見せ→URL誘導」型は採らず「おりポスで価値を出し切る+URLはリプ」型で確定。
おりポスにはアイキャッチをネイティブ添付 (画像が消える不満の解消)。

## 実装 (commit 98682962)

- src/manual_intake_x_share.py 新規: 公開記事一覧 / 素材取得 / 型判定 (comment/data/news) /
  flash-lite 下書き (数字・URL・ハッシュタグ・媒体名の門番、fallback あり) /
  post_thread (v1.1 media_upload → create_tweet → in_reply_to リプ)
- manual_intake_service.py: GET /x-share-recent / GET /x-share-draft?post_id= /
  POST /x-share-thread + 🔗記事共有タブ UI (weighted 280 カウンタ CJK=2/URL=23、confirm付き)
- tests/test_manual_intake_x_share.py 新規 (weighted計算/型判定/fallback/thread mock/endpoint)、54 pass

## deploy

- image manual-intake-service:x-share-98682962、revision 00103-tqk
- env 追加: GEMINI_API_KEY=secret gemini-api-key:latest (無料枠キー)
- 旧 traffic は revision 固定 (tag ogfallback) だったため、tag x-share で no-traffic smoke →
  /x-share-recent (5件取得) / /x-share-draft?post_id=102490 (知念大成記事で LLM 下書き生成、
  main weighted 202 / reply 134 / 画像取得OK) を verify 後、100% 切替。main URL 動作確認済
- /x-share-thread の実投稿はまだ発火していない (公開副作用のため user の初回手動操作で)

## 残課題 / v2 候補

- おりポス文末の「期待したい」等の優等生締めが門番未適用 (voice gate はリプ lane 系のみ)。
  実運用の文面を見て _voice_quality_ok 相当を足すか判断
- v2: データ記事はアイキャッチでなくスタッツ表/引用カード画像 (437 の CJK フォント事故歴が
  あるため font 同梱検証を先に)
- v2: x-engagement 週次に share_type 別集計 (構造化ログ x_share_thread_posted を突き合わせ)
- v3: 投稿予約キュー (朝7-8時 / PRIME帯)
