# YouTube Shorts 自動生成 v0 設計(yt-shorts Phase 1)

status: 設計確定(2026-06-12 user GO)、実装未着手
位置づけ: 収益化ではなく **サイト/X への導線・認知装置**。巨人市場の飽和に対し「データ図解ショート」枠(実況切り抜き勢と非競合)を取る。

## ゴール / 非ゴール

- ゴール: 1日1本、既存データ資産から60秒縦型動画を自動生成 → mail承認 → YouTube投稿のループを回す
- 非ゴール(Phase 1ではやらない): 収益化、長尺解説、実況/切り抜き、完全無人公開、複数本/日

## 制約(lock)

1. **映像・写真の権利**: 試合映像/中継スクショ/マスコミ写真/選手写真は1秒も使わない。自前生成の図表・テキスト・イラスト素材のみ(完全権利安全)
2. **追加課金ゼロ**: VOICEVOX(self-host、無料・クレジット表記必須) / matplotlib+PIL / ffmpeg / YouTube Data API(quota無料)。LLMは既存Gemini無料枠のみ
3. **数字はLLMに生成させない**: 台本テンプレにデータ直挿し。LLMは語り口調整のみで、生成後に数値一致verifyを通らなければabort(数値guard)
4. **公開はuser承認後**: Phase 1はmail配信+user手動アップロード。自動公開はPhase 2のuser判断
5. 選手名はフルネーム・敬称なし、ヨシラバーボイス(データ辛口×巨人愛)はX-postと同ruleを流用

## アーキテクチャ(Cloud Run Job `yt-shorts-gen`、新規)

```
1. ネタ選定   notable payload 再利用(_build_notable_data_from_targets 相当)
              優先度: 連続記録更新 > 週間MVP(月曜) > 好調指標 > 年俸コスパ > MLBの2人
2. 台本生成   テンプレ文型 + Gemini flash(無料枠)で語り口調整 → 数値guard verify
3. フレーム   matplotlib/PIL で 1080x1920 静止フレーム3〜5枚(サイトと同オレンジ系トーン)
4. 音声       VOICEVOX engine(同Job内 or sidecar)。47〜55秒、推奨voice=青山龍星(男声・落ち着き、辛口系に合う)
5. 合成       ffmpeg: フレーム+音声+字幕焼き込み(無音視聴対応) → MP4 → GCS保存
6. 承認mail   既存mail基盤と同経路。動画GCS署名URL+台本全文+元データを送付
7. 投稿       Phase 1 = user手動アップロード(チャンネル開設のみuser作業)
```

## 動画フォーマット(60秒)

- 0-3s   フックカード(例「泉口友汰、7試合連続安打中」)
- 3-45s  データ展開カード/グラフ 2〜3枚(1枚10〜15秒)
- 45-55s ひとこと辛口+巨人愛締め(ヨシラバーボイス)
- 55-60s CTA「詳細はヨシラバーで」。概要欄に `/data/notable?v=yt` リンク(導線計測用パラメータ)
- 概要欄にVOICEVOXクレジット表記(利用規約)

## スケジュール / コスト

- scheduler 1本(毎朝7:30 JST、前夜試合反映後・MLB朝更新前) → +$0.10/月
- 動画生成 1本数分のCloud Run実行 → 無料枠内
- 合計増分: 月¥15程度

## ファイル構成(新規予定)

- `src/yt_shorts_topic.py` — ネタ選定(優先度ロジック)
- `src/yt_shorts_script.py` — 台本テンプレ+数値guard
- `src/yt_shorts_render.py` — フレーム生成+ffmpeg合成
- `src/yt_shorts_gen.py` — orchestrator(選定→台本→render→TTS→GCS→mail)
- `Dockerfile.yt_shorts` / `cloudbuild_yt_shorts.yaml`
- `tests/test_yt_shorts_topic.py` / `test_yt_shorts_script.py`(renderはsmoke)

## 事故ガード

- 数値guard: 台本中の全数字が元データと一致しなければabort+失敗mail(silent skip禁止)
- 1日1本cap
- 生成失敗時はmailで失敗通知

## 効果測定 / 撤退基準

- 概要欄リンク `?v=yt` でサイト流入を計測、YouTube Studioで再生数/視聴維持率
- 4週間運用 → 平均視聴維持率と再生数をレビューし、継続 / フォーマット変更 / 撤退をuser判断

## Phase分割

- Phase 1(本設計): 生成→mail→user手動アップロード
- Phase 1.5: YouTube Data API自動アップロード(限定公開→承認で公開)。OAuth refresh tokenをSecret Manager
- Phase 2: 自動公開+企画型(あの日の巨人 等)+本数増(user判断)

## user作業(1件のみ)

- YouTubeチャンネルの新規開設(ブランドアカウント推奨)。Phase 1はmail+手動アップロードなので、実装と並行で間に合えばOK
- **完了(2026-06-12)**: チャンネル開設済 = 「BaseBall Academy ヨシラバー」 https://www.youtube.com/@baseballacademy9623
