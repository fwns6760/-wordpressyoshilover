# 2026-07-06 X-post リプ共感化 + MLB鮮度3h + 引用RTグラウンディング

user 指摘 3 件を同セッションで対応。

- 09:35 JST | user 決定 | ファンリプ=交流メイン、数字必須ダメ | reply_style="empathy" 新設 | commit 24474d71
- 09:40 JST | user 指摘 | MLBリプ候補も数字が変、相手の内容に合わせる | MLBリプも empathy 化
- 09:42 JST | user 指摘 | 古いMLBネタは上位表示しない、3H以内 | _mlb_watch_max_age_hours default 20h→3h
- 09:44 JST | user 指摘 | MLB引用RT🖼が元ポストと合っていない | video_sns prompt をグラウンディング強化 (プレー場面の無い投稿で場面創作禁止)
- 09:47 JST | commit 9ed19db1 (MLB 3点 + 7/3 未commit _mlb_voice_subject_and_note helper 取り込み)
- 09:50 JST | deploy | image x-post-mail-lane:reply-empathy-9ed19db1 | job 更新済
- 09:53 JST | dry-run verify | execution x-post-mail-lane-hvv6k Completed | fan_reply 3件生成 (旧: db_fact 無しは skip) / mlb_watch 1件 (鮮度3h内のみ) / mlb_reply 1件 / 大谷引用RTコメントは元投稿のプレー内容に即した文で gate 通過

## 実装メモ

- `build_quote_rt_comment(reply_style="empathy")`: 共感主・数字従。db_fact 必須 gate を通らない。逆張り/訂正/講釈/定型締め禁止は共通維持。文言は「同じファン仲間として」(MLB の非巨人視点 note と両立するため中立化)
- fan lane: db_fact は crc32(parent_text)%3==0 の約1/3のみ素材渡し (同型連続の回避)。媒体リプ (報知等) は従来の補足型のまま
- env: X_POST_MLB_WATCH_MAX_AGE_HOURS は prod 未設定 → code default 3h が有効
- tests: 429→400 (関連3file) 全pass。BuildQuoteRtCommentTests に set_llm_budget(None) の setUp 追加 (先行 test の budget leak で順序依存 fail していた既存脆弱性を修正)
- working tree に他セッションの未commit WIP が多数残存するため、commit は git apply --cached で自分の hunk のみ選別 stage (git add -A 禁止維持)

## 残課題 / 観察

- 次の実 mail 便でファンリプ/MLBリプの文面トーンを user が確認 (共感になっているか、数字が消えたか)
- MLB引用RT は鮮度3hで 0 件の便が増える見込み (埋め草で出さないのは仕様)
- 報知など媒体リプは補足型のまま。user から同様の指摘が出たら empathy 切替を検討

## 第2便 (同日 10:00-10:50 JST): ファンリプ数字全廃 + コメント速報文脈 + 記録/節目可読化

- user 追加指摘: ①ファンリプの数字は1/3でも不要(「交流に知識を見せつけてるだけ」) ②コメント速報が唐突(なぜの文脈を前に) ③記録/節目がポストとして見づらい(LLM可) ④「未確認の数字は足さず…」の内部ルール文が読者に漏れる
- 実装: fan lane db_fact 全廃 / build_comment_context_line (状況説明1行、記事lead根拠+数字門番+10〜60字gate) / record候補を build_plain_data_post で可読化 (budget_site=record_plain)
- flag: ENABLE_X_POST_COMMENT_CONTEXT=1 / ENABLE_X_POST_RECORD_PLAIN_LLM=1 (code default OFF、prod job env で ON。test/dev の helper 直呼びで実LLM発火させないため)
- 補助LLM専用小枠: comment_context / record_plain 各4回/便 (共有 non-reply 枠の枯渇に巻き込まれない別勘定、cap 増はコスト gate)
- 数字門番 NFKC 対応: 記事の全角数字(２０回１／３)を LLM が半角で書き戻すと literal 比較で全滅していた実測不具合を修正 (_extract_unverified_numbers + build_plain_data_post)
- commits: 4d05f6b4 / d43b1432 / c729a398、image nfkc-fix-c729a398 deploy 済
- dry-run verify (x-post-mail-lane-gsftp): record 可読化 4/4 built (76-94字) / comment_context 3 built + len=8 は min gate で正しく skip / fan_reply 純共感型 / Completed
- 残観察: comment_context の cap4 は候補建て順で消費 (最終mailに入らない候補で浪費しうる)。実mailで文脈付与率が低ければ lazy 生成 or cap 調整を検討
