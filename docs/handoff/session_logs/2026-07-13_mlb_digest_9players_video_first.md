# 2026-07-13 MLB定点9人化 + 巨人引用RT記事型除外 (user 指示 2件)

- 14:35 JST | user「追加」 | MLB定点ポスト対象 3→9人 (日本人スター組6人、statsapi ID 実確認) | commit `b4888764` | tests 7 passed + 実 smoke 9選手/750字
- 14:47 JST | user「巨人の記事型引用SNSはでてこなくていい。動画型を多く」 | gather_buzz_posts で記事📰除外 (📷維持、MLB article_max 別経路不変)、トレンドペア 🎬+📷 のみ | commit `df2d0df8` | tests 299 passed
- 14:50 JST | build+deploy | Cloud Build `69a44dec` SUCCESS (2 commit を 1 build に束ね) | image `videofirst-df2d0df8` | Job generation 336
- env | `X_POST_VIDEO_RADAR_MAX` 9→12 (rollback = env 戻しのみ)
- 次 | 明朝 8-10時: 9選手定点 mail 確認 / 引用RT便: 📰消滅・🎬増を確認 / 429=0 24h観測 (0082428f) 継続
