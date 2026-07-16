# 2026-07-16 persona voice alignment (X投稿とペルソナの合致改善)

## 背景

user「今のポスト内容とペルソナへの内容をもっと合致したほうがよい」→ 実ポスト監査
(x_engagement/posts 7/15-16 の38本) と `_SYSTEM_PROMPT_YOSHILOVER` を突き合わせ、
提案 P1-P3 + /live争点型 を user GO で実装。

追加 input: 2026-07-15 観戦ポスト「浦田 vs 吉川尚輝 セカンド争い + 立場表明」が
伸びた (user 報告)。争点+立場型を voice 正本の最優先パターンへ昇格
(memory: project_dispute_stance_post_won_2026_07_16)。

## 監査で確定したズレ

1. 定点締めが優等生アナウンサー調 (「〜ですね」「関心が集中していますね」)
   — extra_voice_note が です・ます強制 (2026-07-10 実装時選択) で persona 正本を上書き
2. MLB引用RTが感嘆+一般論 (「スケールが違いすぎて驚くよな」)
3. 語尾人格の混在 (ですね / だわ / 勝つぞー が同日混在)
4. thin post 素通り: 「李 健熙、李健熙は…あいさつを終えたか。」
   - 真因A: relaxed fallback (470) が 50字未満スカスカを致命的NG扱いしていない
   - 真因B: `_ensure_player_name_leads_post_text` が roster 表記「李 健熙」(空白入り)
     と LLM 文頭「李健熙」を空白差で不一致判定 → 二重 prefix
5. 予告先発の複数投稿は 2026-07-10 user GO の仕様 (朝/昼/試合前3回) — 重複ではない、不変更

## 実装 (commit a7202678, branch feat/yt-shorts-motion-and-player-diversity)

- morning_digest_post.py: 締め prompt をカジュアル語尾+1選手拾い+争点優先へ。
  `find_digest_tone_violation` (です・ます決定的gate) 追加。deterministic fallback もカジュアル化
- mlb_morning_digest_post.py: 同上 (tone gate は巨人定点から import 共用)
- x_post_branding_gen.py: persona 正本に争点+立場型を最優先昇格 (例G 追加)。
  relaxed fallback の 50字未満スカスカ (非live/非リプ) を致命的NG化
- manual_intake_service.py: `_LIVE_VOICE_NOTE` に ⑦争点型 (最優先) 追加
- tests: ToneGateTests(6) / RelaxedThinGateTests(2) / PlayerNameLeadSpaceInsensitiveTests(3)
  — 対象5 module 475 passed (baseline 432 passed)

## deploy

- ambient dirty (50 files, 他セッションWIP) は現行 prod image に既に入っている
  (両image 本日push済み) ため、working tree build が prod 一致。commit は自分の 8 file のみ明示stage
- cloud build: x-post-mail-lane `d62d90f9` / manual-intake-service `56186c23`
- build後 `gcloud run jobs update x-post-mail-lane` / `gcloud run services update manual-intake-service` で digest 再解決

## 残課題 / 観察

- 石塚裕惺「選手+ですます」型 post の生成元 lane 未特定 (露出小、次回監査で再発したら特定)
- 名言集/語録 lane は user 判断待ち (フォーマット企画として persona 対象外の推奨を提示済み)
- 次の毎時定点ポストで tone 反映を確認 (優等生調が出たら gate log `morning_digest comment gate drop: polite_tone` を見る)

## 第2便: 名言集lane改善 (同日、user方向指示→GO)

**user指示**: 読者ペルソナ=10〜30代。小林/坂本は良い(特に小林)、原/吉川は悪い。
原=ビジネス論が外れる、「今の巨人に足りないもの」に繋がる生き方の言葉なら響く。
吉川=記事の写真に合った実Xポストがあれば響く。画像がうまく取れていない。

**診断**: 小林の伸び=感情引用の中身(画像添付ではない、has_media 131/836)。
吉川のog:imageは媒体汎用ロゴ(jsports使い回し)でOGPカード死、原はYahoo URLリンク切れ。
fav実測: 小林12〜57 / 原1 (2026-07-13週次)。memory: project_meigen_lane_audience_fit_2026_07_16

**実装 (commit 59de65d0)**:
- lane: retired skip (番号保存) + X本文source_urlはx.com/twitter.com実ポストのみ
- 吉川feeder: 写真付き実Xポスト紐付け(RSSHub、新規記事のみマッチ可) + 汎用ロゴ除去
- GCS archive反映: 原14件retire→live39件 / 吉川16件ロゴ除去。
  backup = ops_manual_backups/meigen_20260716/
- **注記**: `src/tools/archive_yoshikawa_meigen.py` は前セッションの未commit WIP
  (git履歴なし、prod archiveを作った正本feeder)。本commitで初めて履歴化 (+515行の内訳
  ≈ 既存375 + 今回140)

**残**: 原の新規収集feederは repo に無い (archiveがどう作られたか不明)。次回収集時は
「生き方・勝負哲学・今の巨人に足りないもの」基準で。吉川backlogは実Xポスト遡及不可の
ためtext-only配信 (新規分から写真マッチ)。

## timeline

- 15:12 JST | commit | persona voice alignment | a7202678 | build fire
- 15:14 JST | build fire | x-post-mail d62d90f9 / manual-intake 56186c23 | 両SUCCESS
- 15:2x JST | deploy 反映 | jobs update x-post-mail-lane (image push 15:17) / services update manual-intake-service → rev 00163-s5j 100% | 次の毎時定点で tone 確認
- 備考: manual-intake の traffic に 00103 (tag: x-share) が残るのは意図的 pin、不変更
- 16:0x JST | 第2便 commit | meigen persona合致 | 59de65d0 | build eeb90840
- 16:1x JST | 第2便 deploy | meigen-mail-lane job → golden-59de65d0 | 次dispatch=17:00 JST で反映確認
