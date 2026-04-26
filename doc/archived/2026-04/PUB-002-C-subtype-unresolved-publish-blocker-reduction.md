# PUB-002-C subtype-unresolved publish blocker reduction

## meta

- owner: Claude Code(分類設計、実装は Codex 便)
- type: ops / publish blocker reduction / subtype routing
- status: READY(72h draft 棚卸し未着手)
- priority: P2(**PUB-004 安定運用後の品質改善**として後続、user policy 2026-04-25 21:55 lock)
- parent: PUB-002 / PUB-002-A
- created: 2026-04-25

## purpose

`subtype_unresolved` で公開候補から落ちる記事を減らす。
title / body / meta から subtype 判定できないパターンを分類し、`lineup / farm / comment / social_video / notice` などに安全に寄せる rule を作る。

## 背景

HALLUC-LANE-001 extractor の `inferred_subtype` は title 先頭 / 含有 keyword で 10 ブランチ判定:
`lineup / probable_starter / farm / notice / comment / injury / postgame / pregame / program / other`

→ 多くが `other` に落ちる(辞書 first-match miss)= subtype 不明 = PUB-002-A の判定 logic で本来該当する safety rule が外れる。

例(本日 棚卸しで見えたパターン):
- `巨人スタメン NPB通算安打 ① （東映）3085 ：…` → 数値 ranking 形式、lineup branch hit するが本来別 subtype
- `三塚琉生、フォーム変更のポイントはどこか` → 投手 / プロセス記事、`other` 落ち
- `阿部監督「きっかけにしてほしい」 ベンチの狙いはどこか` → 監督 quote、`comment` branch (「コメント」literal) 不該当
- `ＣＬＵＢ ＧＩＡＮＴＳデー 会員限定Ｔシャ…` → off-field promotional event、判定対象外

## 不可触

- creator 主線の大改修(narrow 修正のみ)
- 自動公開
- front / plugin
- automation / scheduler / .env / secrets
- baseballwordpress repo

## 棚卸し手順(Claude 側、read-only)

### Step 1: 72h draft の subtype 分布

```python
from src.pre_publish_fact_check.extractor import infer_subtype
# OR run_pre_publish_fact_check --mode extract
# subtype 別件数集計
```

### Step 2: `other` 落ち pattern 分類

| 候補 subtype | 代表 keyword / pattern | 想定マッピング先 | 安全性 |
|---|---|---|---|
| `coach_comment` | 「監督」「コーチ」「Ｃ」+「」quote | comment(現 branch を sub-typing) | 中(quote 系は Red 注意) |
| `pitcher_focus` | 投手名 + 「投球」「完封」「降板」 | postgame(投手フォーカス) | 高 |
| `batter_focus` | 打者名 + 「猛打賞」「マルチ安打」「適時打」 | postgame(打者フォーカス) | 高 |
| `farm_postgame` | 「二軍」+ 試合結果 / 投打 | farm に集約 | 高 |
| `farm_player_note` | 「二軍」+ 個別選手 note | farm に集約 | 高 |
| `promotional_event` | 「Ｔシャツ」「グッズ」「ＣＬＵＢ ＧＩＡＮＴＳ」 | `off_field` 新 branch / hold 推奨 | 中(公開判断別ルート) |
| `process_speculation` | 「フォーム変更」「調整」+ 「ポイントはどこか」 | speculative title で Red 該当 | 低(R5/R7 対象) |
| `roster_move` | 「昇格」「合流」「帯同」+ 選手名 | notice 拡張 / `roster_move` 新 branch | 中(injury 隣接で R5 注意) |

### Step 3: 安全に寄せられる pattern を選定

- 高安全: `pitcher_focus` / `batter_focus` / `farm_postgame` / `farm_player_note` を postgame / farm にマッピング
- 中安全: `coach_comment` / `roster_move` は subtype 判定だけ拡張、PUB-002-A の Red 判定で別途 gate
- 低安全(除外): `process_speculation` / `promotional_event` は subtype 判定不要で `other` 維持、Red 落とし

### Step 4: 実装候補

- `src/pre_publish_fact_check/extractor.py` の `infer_subtype` heuristic 拡張(順序 first-match の追加 branch)
- 新 branch:
  - `coach_comment`: title contains 「監督」「コーチ」「Ｃ」+ 「」 → coach_comment
  - `pitcher_focus`: title contains 投手 keyword (「完封」「降板」「Ｋ」「奪三振」「無失点」) → postgame
  - `roster_move`: title contains 「昇格」「合流」「帯同」「抹消」(injury 隣接 keyword 除外)→ notice
  - `promotional_event`: title contains 「Ｔシャツ」「グッズ」「ＣＬＵＢ ＧＩＡＮＴＳ」「会員限定」 → `off_field`(新)
- 順序: 既存 lineup / probable_starter / farm / notice / comment / injury / postgame / pregame / program → other より前に新 branch を入れる

### Step 5: tests 方針

`tests/test_pre_publish_fact_check_extractor.py` に subtype branch test を拡張:
- 各新 branch 1 サンプル title
- order-sensitive test(同 title が複数 branch に該当時の first-match 検証)
- `other` に落ちる title を意図的に 1 サンプル(全 branch miss 確認)

## 完了条件

1. 72h draft の subtype 別件数表
2. `other` 落ち pattern の代表サンプル(各 5〜10 件)
3. 除外すべき危険パターン(`process_speculation` / `promotional_event` 等)の Red 判定根拠
4. 安全に寄せられる新 branch 案 3〜5 件 + 実装 prompt 草案
5. tests 方針(branch カバレッジ + order test)
6. Codex 実装便 prompt が 1 本起草される(本 ticket 内に貼る)

## 関連 file

- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(Red R5 = injury / R7 = 数値リストの判定要件)
- `src/pre_publish_fact_check/extractor.py`(`infer_subtype` 拡張対象)
- `tests/test_pre_publish_fact_check_extractor.py`(branch test 追加対象)
- `doc/PUB-002-B-missing-primary-source-publish-blocker-reduction.md`(隣接 ticket、source 軸)

## stop 条件

- 新 branch が 5 件超 → over-engineering、PUB-002-C scope 内は 3〜5 件まで
- creator 主線(`src/rss_fetcher.py`)の大改修が必要 → 別 ticket に escalate
- 全 draft 一括 re-classify が必要 → 本 ticket scope 外(extract 時点判定のみ)
