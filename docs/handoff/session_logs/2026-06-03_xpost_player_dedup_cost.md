# 2026-06-03 X-post 同一選手 重複生成 cost 削減

user 主訴: 試合中/翌日に同じ選手が多数ポスト→投稿できないのに LLM 費用無駄 (多媒体が同選手を扱うため)。

- 09:4x JST | 第1 fix commit 44b66773 | データranking追加 path `_pick_gemma_branding_players`: 同一選手 窓内3回→2回(env X_POST_MAIL_GEMMA_PLAYER_MAX_PER_WINDOW)+ 24h cooldown(env X_POST_MAIL_GEMMA_PLAYER_COOLDOWN_HOURS)。誤記 "24h" コメント修正 | next=deploy
- 09:5x JST | smoke ld8ds 実ログで主因判明 | queue 417 drain が記事 item を1件ずつ build_x_post_from_article_info→Gemini に通すが player dedup 無し、則本昂大×5+ で大半 drop | next=主因 fix
- 09:5x JST | 第2 fix commit a5e60fcf | build_x_post_from_article_info に Gemini 前 player gate (seen_player_keys=within-run 1生成 / skip_player_keys=cooldown+cap、team-wide 巨人 は cap 対象外)。drain() は item 非除去=次 fire 再取得で 1 fire 1 選手 1 call の自然 rate 制御 | next=deploy+verify
- 10:0x JST | deploy image qdedup-a5e60fc + Job update | x-post-mail-lane | next=smoke verify
- 10:0x JST | smoke qglzz 一次確認 OK | queue 10件中 8件 Gemini 前 skip(player_cooldown_or_cap)、Gemini 5回(旧9-10)、exit0/no error | DONE

env knob(全て可逆): X_POST_MAIL_GEMMA_PLAYER_MAX_PER_WINDOW(既定2) / X_POST_MAIL_GEMMA_PLAYER_COOLDOWN_HOURS(既定24、0で無効)。
