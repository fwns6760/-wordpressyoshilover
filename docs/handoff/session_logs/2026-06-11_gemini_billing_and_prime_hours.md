# 2026-06-11 Gemini課金調査 + 3.5-flash prime hours窓

- 09:55 JST | user が AI Studio から有料キー(baseballsite所属 253683bb)削除 | 課金停止
- 10:10 JST | 調査確定: 6/10 ¥100台の真因 = ローカル.envの有料キーで3.5-flash paid実行(Claudeのdry-run)。prodは元から無料キー(gen-lang) | memory記録済
- 10:15 JST | wordpressyoshilover/.env を無料キーへ差し替え | 課金経路ゼロ
- 10:25 JST | quota実測: 3.5-flash無料枠=20回/日・5回/分(リセットJST16時頃)、3.1-flash-lite=500回/日 | quota API
- 10:35 JST | feat commit b9581aee: X_POST_GEMINI_PRIME_HOURS_JST(既定17-23)で3.5を試合時間帯に温存、窓外はlite直行。429時lite fallbackをx_post_generatorにも追加 | tests 163 green
- 10:45 JST | deploy: x-post-mail-lane job + yoshilover-fetcher service(rev 00517) = image prime-hours-b9581aee | /health 200
- next | 夕方17時以降のログで「窓内のみ3.5使用」をverify + 明日billing ¥0確認
