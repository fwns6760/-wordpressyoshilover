# Acceptance Test Checklist

明日の受け入れ試験で subtype ごとに見る項目を固定する。判断者は Yoshihiro、監査役は Claude、修正実装は Codex。

## 優先順位

| 優先度 | subtype | 理由 | 目安サンプル数 |
|---|---|---|---|
| 最優先 | `postgame` | 情報量が多く、本文型も安定 | 10件 |
| 最優先 | `lineup` | スタメン系は需要が高く、判定しやすい | 10件 |
| 優先 | `manager` | 専用本文型が安定 | 8件 |
| 優先 | `notice` | 専用本文型が安定 | 8件 |
| 慎重 | `pregame` | 文面角度は入ったが、試合前の粒度差が大きい | 8件 |
| 慎重 | `recovery` | 故障情報の粒度差が大きい | 8件 |
| 慎重 | `farm` | 2軍記事は元ソース差が大きい | 8件 |
| 慎重 | `social` | B.5 との整合を見る必要がある | 8件 |
| 慎重 | `player` | 話題範囲が広い | 8件 |
| 慎重 | `general` | fallback 含みで幅が広い | 8件 |
| 保留 | `live_update` | publish 禁止のため受け入れ対象外 | 0件 |

## 進め方

- 1日あたり 2-3 subtype までに絞る
- 30分ごとに区切り、1ブロックで 1 subtype を見る
- 1ブロック終了ごとに 5 分休憩を入れる
- ADHD 配慮として「sample を全部見切る」より「重大欠陥の有無を早めに判定する」を優先する

## 役割分担

| 役割 | 担当 | 役割内容 |
|---|---|---|
| 判断 | Yoshihiro | 合格 / 差し戻しの最終判断、publish 解放判断 |
| 監査 | Claude | ログ確認、リスク指摘、判断材料の整理 |
| 実装 | Codex | 差し戻し修正、テスト追加、deploy |

## 共通チェック項目

全 subtype でまず見る項目:

1. タイトルが自然で、同日の他記事と衝突していない
2. カテゴリ / subtype が期待どおり
3. 本文が 3-4 セクション以上で崩れていない
4. featured image が付いている
5. ソースURLと本文の要点が一致している
6. X preview が不自然でない

共通の合格基準:

- 重大欠陥 0
- sample の 8 割以上で軽微欠陥も許容範囲

## subtype 別チェック

### `postgame`

- スコア、勝敗、決定打の軸が本文で明確
- タイトルが「何を決めた試合か」を表している
- 選手名・数字が不自然に欠けていない
- 試合後コメントが本文に自然に入っている
- X preview が postgame 用の温度感になっている
- B.5 対象なら引用が過剰でない

合格基準:

- 10件中8件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_POSTGAME=1
```

### `lineup`

- 試合相手、球場、開始時刻が自然に入っている
- スタメンの注目点が本文で読める
- 若手 / 主力の見どころがズレていない
- featured image が付いている
- X preview が「どこを見る？」系で自然
- 試合前記事なのに postgame 文脈になっていない

合格基準:

- 10件中8件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_LINEUP=1
```

### `manager`

- 監督 / コーチ発言の主語が明確
- quote 中心で崩れていない
- ベンチワークや起用意図が拾えている
- タイトルが選手記事に寄っていない
- B.5 報道引用が妥当
- X preview が監督コメントの温度感に合っている

合格基準:

- 8件中7件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_MANAGER=1
```

### `notice`

- 登録 / 抹消 / 合流 / 戦力外の種別が明確
- 対象選手名が欠けていない
- 背景説明が 1 段深く入っている
- タイトルが単調すぎない
- 公示ポスト引用が妥当
- X preview が notice 専用分岐に乗っている

合格基準:

- 8件中7件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_NOTICE=1
```

### `pregame`

- 相手 / 球場 / 開始時刻が自然
- 先発や注目選手の軸がある
- 試合前記事として温度感が合っている
- postgame と誤認しないタイトル
- X preview が試合前向けの問いかけになっている
- featured image が付いている

合格基準:

- 8件中6件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_PREGAME=1
```

### `recovery`

- 選手名と回復状況が明確
- 故障部位 / 復帰段階が不自然でない
- 一軍復帰時期の含みが本文にある
- タイトルが notice と混線していない
- X preview が recovery 分岐の温度感になっている
- featured image が付いている

合格基準:

- 8件中6件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_RECOVERY=1
```

### `farm`

- 2軍 / ファーム文脈が明確
- 若手 / 育成視点が本文に出ている
- lineup 系なら並びの意味が読める
- player 記事に誤分類していない
- featured image が付いている
- X preview が farm 用の温度感に合っている

合格基準:

- 8件中6件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_FARM=1
```

### `social`

- 発信元の扱いが明確
- B.5 の引用が適切で過剰でない
- 本文が source tweet の言い換えだけで終わっていない
- タイトルが報道ソースに引っ張られすぎていない
- featured image が付いている
- X preview が social 専用分岐に乗っている

合格基準:

- 8件中6件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_SOCIAL=1
```

### `player`

- 選手名が明確
- 話題の軸が 1 本に絞れている
- notice / recovery と混線していない
- タイトルが generic すぎない
- featured image が付いている
- X preview が player 専用分岐に乗っている

合格基準:

- 8件中6件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_PLAYER=1
```

### `general`

- fallback 記事でも本文の主題が読める
- タイトルが曖昧すぎない
- 他 subtype に振れなかった理由が納得できる
- featured image が付いている
- X preview が不自然でない
- 重要記事を general へ逃がしすぎていない

合格基準:

- 8件中6件以上 OK、重大欠陥 0

公開コマンド例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_PUBLISH_FOR_GENERAL=1
```

## 差し戻し時の Codex 依頼テンプレ

```text
依頼: 受け入れ試験差し戻し

対象 subtype: <postgame / lineup / manager / notice / pregame / recovery / farm / social / player / general>
対象 post_id: <12345, 12346>
問題:
- タイトル:
- 本文:
- 画像:
- B.5引用:
- X preview:

やってほしいこと:
- 原因調査
- 修正
- 回帰テスト追加

禁止事項:
- 他 subtype へ影響する変更を広げない
```

## 合格後の操作メモ

- まず publish フラグだけ `1`
- 数日観察後に X フラグだけ `1`
- 最後に `AUTO_TWEET_ENABLED=1`

X フラグ解放の例:

```bash
gcloud run services update yoshilover-fetcher \
  --project baseballsite \
  --region asia-northeast1 \
  --update-env-vars ENABLE_X_POST_FOR_POSTGAME=1
```
