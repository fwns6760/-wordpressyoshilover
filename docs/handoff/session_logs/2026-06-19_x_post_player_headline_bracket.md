# 2026-06-19 X投稿 見出し【選手名】化

- 1?:?? JST | impl | x_post_player_headline_bracket | x_post_generator.py | user指示「【巨人】は冗長→【選手名】+改行」を実装。build_post_with_meta で deterministic/AI 出力の見出し先頭が主役選手名なら「【選手名】\\n残り」へ整形。PLAYER_TAGS 未登録の新加入選手は先頭名regexで拾う。team視点(巨人、…)/source視点(巨人公式が…)/lineup/data/live_update は変換しない。ENABLE_X_PLAYER_HEADLINE_BRACKET(default ON)。tests 44+ green。deploy未実施(user go待ち)。
- 2?:?? JST | impl | x_post_player_headline_bracket | x_post_generator.py(AI prompt) | AI生成便(Grok/Gemini)にも「1選手中心なら1行目【選手名】+改行」ルールをプロンプトへ追加。後処理は冪等(先頭【なら素通り)。tests 51 green。
- 3?:?? JST | impl | x_post_player_headline_bracket | x_post_generator.py | AI事故源対策: AI便の【選手名】見出しをプロンプト頼みから決定論へ変更。選手名は実タイトルから採取(_ai_protagonist_name)、コードで強制(_force_ai_player_headline)、AIが付けた【】は剥がして貼り直し。複数選手/チーム話題は強制しない。tests +4(AI mock) 48 green / 570 non-image green。deploy未。
