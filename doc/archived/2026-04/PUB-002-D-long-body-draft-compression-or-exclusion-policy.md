# PUB-002-D long-body draft compression or exclusion policy

## meta

- owner: Claude Code(policy 設計、実装は narrow Codex 便)
- type: ops / publish blocker reduction / prose length policy
- status: READY(72h draft 棚卸し未着手)
- priority: P3(**PUB-004 安定運用後の品質改善**として後続、user policy 2026-04-25 21:55 lock)
- parent: PUB-002 / PUB-002-A
- created: 2026-04-25

## purpose

`body_too_long` / `prose_too_long` の下書きを、公開前にどう扱うか決める。
圧縮して公開候補に戻すのか、当面は除外するのか、subtype 別に判断基準を作る。

## 背景

PUB-002-A の current 閾値 = `prose 500..3500 chars`(PUB-002-A の Yellow 認定 / Green 認定で使用)。
- 上限超過 = `prose_too_long` で publish 候補から除外
- 下限未満 = `prose_too_short` で除外(別 issue、本 ticket scope 外)

本日 観測:
- 63284 (佐々木俊輔 猛打賞) = 1785 chars
- 63307 (石塚裕惺 緊急昇格) = 1234 chars
- 63489 (DeNA戦 lineup) = ~6728 HTML chars(本日 publish 済、prose 換算 ~3500-4000)
- 63405 (ドラ4位 皆川岳飛 lineup) = 6728 HTML chars(本日 publish 済)

→ 本日 publish 2 件はどちらも閾値ギリギリ or 超過、軽圧縮済 / 既圧縮対象。

長い body の構造的要因:
- AI tone 見出し 3〜5 行(`💬 〜?` `【注目ポイント】` 一般論)
- `【関連記事】` ブロックで他記事 title 列挙
- `💬 ファンの声（Xより）` で Twitter URL list
- スタメン情報の二重化(表 + 一覧 + 簡易リスト)
- 「先発投手の情報は元記事で確認できる範囲をそのまま押さえておきたい」等の一般論段落

## 不可触

- 大量自動 rewrite(本 ticket は policy のみ、実装は narrow 便)
- published 記事の書換(本 ticket scope は draft のみ)
- `RUN_DRAFT_ONLY` 解除
- creator 主線の大改修
- automation / scheduler / .env / secrets
- baseballwordpress repo

## 棚卸し手順(Claude 側、read-only)

### Step 1: 72h draft の prose 長分布

```python
# 統計: <500 / 500-1000 / 1000-2000 / 2000-3500 / >3500 別件数
```

### Step 2: 長い body の構造分析(>3500 系を 5〜10 件サンプル)

各 draft で:
- AI tone 見出し行数(`💬` で始まる行 count)
- `【関連記事】` ブロックの行数
- Twitter URL list の URL 数
- スタメン情報の二重化判定(同一 lineup が表 + 一覧 + 簡易リストで複数回出現)
- 「元記事で〜」「〜と思います」「〜したいところ」等の一般論段落 count

### Step 3: subtype 別 policy 案

| subtype | 上限目安 | 圧縮可否 | 除外条件 |
|---|---|---|---|
| `lineup` | 3500 chars | 高(AI tone 見出し / 関連記事 / Twitter 削除で 30-40% 圧縮可) | 圧縮後も 3500 超 → hold |
| `postgame` | 3500 chars | 中(scoreline + 1 plays 中心、削れる行少ない) | 4000 超 → hold |
| `farm` | 2500 chars | 高(短い factual note 中心、AI tone が割合大) | 圧縮後も 2500 超 → hold |
| `comment` | 2000 chars | 低(quote 中心、削ると本筋失う) | 2500 超 → hold |
| `notice` | 1500 chars | 高(短文発表系) | 2000 超 → hold |
| `pregame` | 1500 chars | 中(speculative 多い、別 Red 該当の可能性) | 2000 超 → hold |
| `probable_starter` | 1500 chars | 高(投手紹介 + 統計、AI tone 削減で短縮可) | 2000 超 → hold |
| `injury` | 該当なし | - | PUB-002-A R5 で全 hold |
| `program` | 1500 chars | 高(放送情報、削れる) | 2000 超 → hold |

### Step 4: 安全な 1 本実装候補

最も効果が高いのは「**AI tone 見出し 3 行 + 一般論 1 段落の自動削除**」(WP admin 手動でも user が今日繰り返してきた操作)。

- 対象: 抽出済 input JSON の body_text 内 `💬 このニュース、どう見る？` `💬 先に予想を書く？` `💬 みんなの本音は？` 行 + `【注目ポイント】` 直下 1 段落
- 範囲: HALLUC-LANE-001 apply の suggested_fix 形式に乗せる(operation=delete、find_text exact match)
- 安全性: dry-run 必須(--live で WP write)、user approval YAML 経由、backup あり
- 既に 5-gate refuse mechanism (PUB-002-A 連携) で重大事故防止
- → 新規実装ではなく、HALLUC-LANE-001 を「AI tone 削減 detector」として使う形(detector が dry stub から「該当 phrase 検出ルール」へ昇格、`HALLUC-LANE-001-A`)

### Step 5: Codex 実装便 prompt 候補

- `HALLUC-LANE-001-A`: detector の dry stub を「決定論的 AI tone 検出 rule」に置換
  - 入力: extract output
  - 検出: `💬 〜?` 系 / 「初回の入りが鍵」「下位打線の入り」等 boilerplate phrase
  - 出力: contract output JSON、operation=delete + find_text exact
  - LLM 不要(pure regex)
  - apply --live で WP REST 経由削除
  - これで PUB-002-D の Yellow 修正路が automation 化

## 完了条件

1. 72h draft の prose 長分布表
2. 長い body の構造要因 5 軸の集計(AI tone / 関連記事 / Twitter / 二重化 / 一般論)
3. subtype 別 policy 表(上限 + 圧縮可否 + 除外条件)
4. Yellow 修正方針(`HALLUC-LANE-001-A` 案 = AI tone 決定論検出)
5. Red 除外条件(subtype 別上限超過 + 圧縮不可で hold)
6. Green に戻せる条件(圧縮後 prose < 上限 かつ Red 不該当)
7. 1 本だけの安全な実装候補(`HALLUC-LANE-001-A` Codex 便 prompt 草案)

## 関連 file

- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(prose 500..3500 閾値の親)
- `doc/PUB-002-B-missing-primary-source-publish-blocker-reduction.md`(隣接 ticket、source 軸)
- `doc/PUB-002-C-subtype-unresolved-publish-blocker-reduction.md`(隣接 ticket、subtype 軸)
- `src/pre_publish_fact_check/detector.py`(現 dry stub、`HALLUC-LANE-001-A` で実装拡張対象)
- `src/pre_publish_fact_check/applier.py`(5-gate refuse、Yellow 修正の WP write 経路)

## stop 条件

- subtype 別 policy が 5 件超に膨らむ → 8 subtype + injury 除外 = 上限 9
- 圧縮ロジックが LLM 必須になる → HALLUC-LANE-002(escalate)へ移管、本 ticket scope 外
- published 記事の書き換えが必要 → 別 ticket(`PUB-002-D-published-rewrite`)
- creator 主線改修が必要 → 別 ticket、user 判断
