# 477-XPOST-daygame-mode-auto-wiring

- status: READY
- priority: P2
- owner: Claude
- lane: dev
- created: 2026-07-03
- blocked_by: なし (ただし 7/4 デイゲームで現行手動 override の運用実績を見てから着手)

## 背景

デイゲーム対応が半自動のまま:

- `game_day_gate` (2026-07-02) は NPB 公式月間日程から当日巨人戦の開始時刻を取り、
  試合帯 scheduler 便 (`--window=game` / `--window=lineup`) の発火を
  「開始-15分〜開始+4h」「開始-2h〜開始」に自動で寄せる。ここは全自動。
- しかし便の中身の「試合中モード」判定 `x_impression_timing_label`
  (リプ対象の動画ハンドル拡張 / 鮮度ゲート / トーン) は壁時計
  (19:00-21:45=試合中) + `X_POST_MAIL_EXTRA_GAME_DATE/START/END` env のまま。
- そのためデイゲームごとに job env の手動更新が必要
  (6/7 と 7/4 は手動で DATE=当日, START=13:45, END=18:00 を設定)。

## ゴール

デイゲームでも env 手動更新なしで、試合中モードが NPB 開始時刻に自動追従する。

## 実装案 (仮置き)

- `run_x_post_mail.main()` の game_day_gate 判定後、開始時刻が取れた場合に
  プロセス内で extra-game 窓 (start-15m 〜 start+4h) を lane に伝える
  (env 経由 `os.environ` セット or lane のモジュール変数 setter)。
- `--window` なしの毎時便 (`x-post-mail-flush`) もモードを合わせたい場合は
  gate の fetch 結果を軽量キャッシュ (例: GCS or /tmp、当日 date キー) して
  label 判定側から参照する案を検討。fetch 失敗時は現行の壁時計に fail-open。
- 既存 env override は非常用に残す (env が優先)。

## 不可触

- scheduler の cron 定義 (発火帯は現行のまま)
- 夜試合の既存ラベル境界 (17:15/19:00/21:45) の変更
- publish 系 lane

## 受け入れ条件

- デイゲーム日に env 未設定でも、開始-15m〜+4h が in_game_strong 扱いになる
- ナイター日の挙動が現行と完全一致 (regression tests)
- NPB fetch 失敗時は現行挙動 (壁時計 + env) に fail-open
