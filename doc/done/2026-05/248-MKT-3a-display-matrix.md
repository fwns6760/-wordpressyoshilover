# 248-MKT-3a: subtype × 表示先 matrix

## 目的

front 系の各 section で「どの subtype を、どこに、出すか / 出さないか」を明示。

## 基本判定(yoshilover_063_should_show_in_front)

1. auto-post カテゴリ (id 673) 除外
2. 弱い title 除外 (12 文字未満 + blacklist phrase)
3. NG subtype 除外 (`default` / `default_review` / `article` / `notice` 単体 / `""`)
4. (オプション) gameish 限定

## subtype × 表示先 matrix

| subtype | reader label | 観戦ガイド 「まず見る」 | 観戦ガイド 「試合後」 | 観戦ガイド 「若手・二軍」 | 観戦ガイド 「今日のチェック」 | 同 game 関連 | 記事束 |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|
| lineup | スタメン確認 | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| pregame | 試合前の見どころ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| probable_starter | 予告先発 | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| postgame | 試合後の整理 | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| game_result | 試合結果 | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| coach_comment | ベンチの見方 | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| player_comment | 選手コメント | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| farm_result | 二軍結果 | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ |
| farm_lineup | 二軍スタメン | ❌ | ❌ | ✅ | ❌ | ✅ | ✅ |
| farm_player_result | 若手・二軍メモ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| farm | 二軍・若手 | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| roster_notice | 登録・抹消 | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| injury_recovery_notice | 復帰・コンディション | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| program_notice | 番組・配信 | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| default | (除外) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| default_review | (除外) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| article | (除外) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| notice 単体 | (除外) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

## 共通 wrapper

`yoshilover_063_should_show_in_front($post, $opts = array())` で 4 helper を集約。
新 section / 新 helper は本 wrapper を使うこと(既存 caller は段階移行)。

## 関連 ticket / 既存資産

- reader label: 246-MKT v0 (`d2e1708`)
- 弱い title: 246-MKT v0
- gameish 判定: 既存 line 3363
- auto-post 除外: 245 (`b9268b1`)
- 同 game 関連: 248-MKT-2 (`04309ae`)
- 観戦ガイド: 246-MKT v0
