# 2026-07-03 yt-shorts 品質総点検 (「あまりにもひどい」user指摘対応)

## 経緯

- 午前の別セッションで user「Youtubeショートが質が低い。洗練されてない」→ 監査で6問題特定 → user「直して他にもない？あまりにもひどい」(GO) 直後にセッション落ち。修正は未着地だった
- 本セッションで全4フォーマット(data / ranking / standings / legend)の実物mp4をGCSからDLしフレーム監査 → 前セッション指摘を全件実物確認 + 追加でデータ事故1件発見

## 確認した問題と対処

1. **データ版レイアウト事故**: 黒ピル「数字で見る巨人」が見出しに重なる → ピル廃止 + カード拡大
2. **同一情報の三重表示**(見出し/下部字幕バー/記録日) → 全フォーマットで下部字幕バー廃止、1画面1メッセージ化
3. **K/9 無説明** → METRIC_EXPLANATIONS 新設(K/9・BB/9・OPS・WHIP)、カード2に平易説明ピル
4. **ポエム定型文**「結果だけでなく流れまで見る」 → fan_comment(ファン目線コメント rotate)に差し替え
5. **standings ゲーム差 `--` 事故**(7/2便で実発生: 首位タイ2位でNPB公式gbが`--`のまま描画) → 勝敗差からの自前計算 + 首位タイ表示対応。回帰テスト追加
6. **standings 画面半分空白** → 6球団順位表カード新設(巨人行highlight、首位差列)
7. **動きが弱い** → Ken Burns zoom 1.08→1.15 / opening 1.12→1.20 / drift 40→70px

## commit

- `ff176259` yt-shorts: VOICEVOX同梱イメージのbuild構成をcommit(6/13からprod運用中だった未commit分: Dockerfile.yt_shorts / cloudbuild / bin/run_yt_shorts_with_voicevox.sh / .dockerignore / gcp_job_config test)
- `c6c3ce46` yt-shorts: 品質総点検(render / script / standings + 回帰テスト2本)
- branch: feat/yt-shorts-motion-and-player-diversity(従来のyt-shorts線と同じ)
- tests: yt_shorts 系 68 passed(66 + standings回帰2)

## 第2弾 (user追加指示「読み方がへん / ネタ選び / ビジュアル / クオリティかなり上げる」)

- **読み**: `5b43cbb4`
  - K/9 のナレーションを「ケーナイン」→「奪三振率」(BB/9→与四球率)
  - 小数の整数部の桁ごと読み事故を修正: 11.28「一一点二八(いちいち…)」→「十一点二八」(_int_to_kanji 位取り変換)
  - 回帰テスト追加 (test_two_digit_decimal_reads_as_positional_number)
- **表示**: カード見出し/タイトル/カード2ラベルも K/9→奪三振率 等の一般名(METRIC_DISPLAY)。topic.label は原値のまま(number guard 系は無変更)
- **ネタ選び**: METRIC_APPEAL_BONUS 新設。本塁打90/打点70/盗塁・セーブ・勝利60/打率・安打55/防御率50 … K/9 15/WHIP 10/BB/9 5。玄人指標が数値の大きさだけで毎回勝つ構造を解消
- **映像**: カード間 concat ハードカット→ crossfade 0.45s(合計27s不変、offsets=カード境界)。背景に淡い斜めアクセント(data=orange / standings=blue / legend=gold)
- **zoom据え置きの理由**: 1.08 超はカード終端で footer 文字(下から86px)が crop 域(1920*(1-1/zoom)/2)に入るため。コードにコメント化済み
- tests: 69 passed(ffmpeg 実合成 + 27.000s + max-zoom フレームの chrome 無傷を目視確認)

## 残課題(次便候補)

- legend版: 選手写真がカード1のみ(2026-06-15 user lock「全カードに選手ビジュアル」のlegend適用は未)
- データ版カード2「ここがポイント」note文の情報量(元記事由来の具体性強化)
- 数字カウントアップ演出(静止画→動きの追加強化案、ffmpeg per-frame 必要で保留)

## deploy

- (下記に追記)

## deploy (追記)

- 12:5x JST | build | Cloud Build 12393859 SUCCESS | image yt-shorts-gen:quality-c6c3ce46 (第1弾、Job未適用のままsupersede)
- 12:0x JST | build | Cloud Build 93b0f3e8 SUCCESS (3m24s) | image yt-shorts-gen:quality-5b43cbb4 (第1+2弾)
- 12:1x JST | deploy | yt-shorts-gen Job generation 39 | image quality-5b43cbb4 | env/secret/scheduler 無変更
- 12:1x JST | smoke | 確認用1本を強制生成 (execution yt-shorts-gen-f9pvs, --ignore-daily-cap) → 承認メールで user が新ルック+読みを直接確認する導線
- 12:1x JST | incident | 強制1本目 execution yt-shorts-gen-f9pvs FAILED | ModuleNotFoundError src.data_site_jersey_source | 原因: committed コードが import する farm/jersey source module が未 commit で、clean worktree build に入らなかった(従来の dirty tree 同梱 build では偶然動作)。ae7b6cef で 2 module を commit、image quality-ae7b6cef で再 build → Job 更新 → 再実行
