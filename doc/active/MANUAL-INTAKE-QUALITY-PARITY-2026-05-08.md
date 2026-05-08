# MANUAL-INTAKE-QUALITY-PARITY-2026-05-08

| field | value |
|---|---|
| ticket_id | MANUAL-INTAKE-QUALITY-PARITY-2026-05-08 |
| priority | P1(品質改善、5/8 audit で発見) |
| status | DESIGN_REQUIRED |
| owner | user (方針判断) → Claude/Codex (実装) |
| lane | QA |
| created | 2026-05-08 |
| doc_path | doc/active/MANUAL-INTAKE-QUALITY-PARITY-2026-05-08.md |
| origin | 5/8 PM session、user 質問「手動更新の、自動更新と同じレベルで出せる？」 |
| user_decision_required | gap の「どの軸」を直すか:本文長 / 装飾 / 自動化 / その他 |

## 1. 結論(調査済)

**現状、本番で 手動 (manual-intake) と 自動 (RSS auto-fetcher) は 同レベルではない**。
ただし「level」の定義によって、どちらが上かが入れ替わる:

| 比較軸 | 手動 manual-intake | 自動 RSS auto-fetcher | 勝者 |
|---|---|---|---|
| **本文長・情報密度** | ~500-1500 chars 構造化カード | ~4000-7000 chars Gemini 長文 | 自動 |
| **装飾(ToC / 関連 / 順位表 / 次戦 / X embed / share / tag chip / AI badge / 4-CTA / JSON-LD)** | 全装飾 ON | 装飾なし | 手動 |
| **自動化(URL 入力不要)** | URL + article_type 入力必要 | 自動 fire | 自動 |

## 2. 技術的根因(コード調査済)

### 装飾 enrichment の gate

`src/tools/manual_intake.py` の `apply_rss_pipeline_enrichment`(commit `927ac2c` で導入):

```python
def apply_rss_pipeline_enrichment(content_html, ...) -> str:
    if not content_html or 'class="nomotoke-card-' not in content_html:
        return content_html  # ← marker なしは即 return、装飾 0
```

**装飾は body に `class="nomotoke-card-` marker がある時だけ走る。**

### 各 path の marker 付与状況

| path | template_key 経路 | nomotoke marker | enrichment |
|---|---|---|---|
| **手動 manual-intake (WP admin form)** | `MANUAL_ARTICLE_TYPE_OVERRIDES` → 必ず `nomotoke_card_*` | ✓ 付く | ✓ 走る |
| **3 auto jobs (broadcast / lineup / postgame)** | manual-intake image を共有 → `nomotoke_card_*` | ✓ 付く | ✓ 走る |
| **RSS auto-fetcher (yoshilover-fetcher)** | `_select_template_v2()` → `postgame_strict` / `score_lite` / `manager` 等 **非 nomotoke** | ✗ 付かない | ✗ skip |

### prod env 確認

- `ENABLE_RSS_TEMPLATE_ROUTING_V2=1` のみ ON(rss_fetcher の v2 routing、非 nomotoke 系)
- `ENABLE_NOMOTOKE_RSS_CARD_ROUTING` は **設定なし**(nomotoke RSS routing は OFF)
- `src/nomotoke_rss_router.py` 自身が「Used only from the dry-run CLI and tests」と明記、production 経路に組まれていない

### live post 実証(2026-05-08 11:30 JST 時点、直近 5 本)

```
id=65044 | nomotoke=True  | 1238 chars | 中日戦 放送案内      ← broadcast-auto job
id=65043 | nomotoke=False | 4674 chars | スポーツ報知ファーム ← RSS Gemini path
id=65037 | nomotoke=False | 7448 chars | ウィットリー先発     ← RSS Gemini path
id=65034 | nomotoke=False | 4482 chars | お菓子屋情報        ← RSS Gemini path
id=64800 | nomotoke=True  |  602 chars | 9回完封負け         ← postgame-auto job
```

→ 5 本中 2 本(40%)だけ marker 付与、それ以外は marker なし、enrichment skip

## 3. 5/8 朝 commit `927ac2c` の評価

commit msg: 「After this commit, the auto-fired RSS pipeline produces bodies with the same readers' blocks ... the manual-intake form path already produces.」

- 配管(`apply_rss_pipeline_enrichment` 関数)は通った
- ただし 肝心の **marker 付与経路**(nomotoke_rss_router production 統合 / `ENABLE_NOMOTOKE_RSS_CARD_ROUTING` 有効化)が未着工
- 結果:**配管だけあって本管が繋がってない**

## 4. parity 達成のための残作業案

| # | 項目 | 工数 | risk | scope |
|---|---|---|---|---|
| 1 | 3 auto jobs を `manual-intake-service:d34072a` に rebuild + redeploy(現 `b432801` から `0bf8900`/`d34072a` 反映) | 30-60 分 | 低、他 5/8 sibling deploy で動作実績あり | auto job image rebuild |
| 2 | `nomotoke_rss_router.py` を rss_fetcher.py の本番 path に統合(現状 dry-run only)| 数日(2055 行 module wire-in、副作用検証) | 中-高、RSS 全本数の挙動が変わる | RSS pipeline 大型工事 |
| 3 | `ENABLE_NOMOTOKE_RSS_CARD_ROUTING=1` を fetcher env に追加(2 完了後)| 5 分 | 低(2 が前提)| env 変更 |
| 4 | nomotoke_rss_router の「RSS-only NG」テンプレ(lineup / postgame / live_at_bats / player_stats / broadcast)を埋めるための facts fetch 拡張 | 数日 - 1 週間 | 高、新規 NPB / Yahoo / X fetch 経路 | MVP scope 外、phase 拡張 |

## 5. user 判断必要事項

**user が「手動だけ直す」と明示したので**、上記 #1〜#4 はいずれも対象外。
本 ticket は **「手動 (manual-intake) を何の軸で直すか」を user が決めるための土台資料** として残す。

候補(user に提示済):

- **A 本文長/情報密度**: manual-intake の出力を 4000+ chars Gemini 本文相当に厚くする(現 ~500-1500 chars)
- **B 装飾を更に厚く**: 既に nomotoke 装飾あるが、まだ足りない要素を増やす
- **C 自動化**: manual-intake のユーザー入力を減らす(URL だけで article_type 自動判定する精度を上げる、等)
- **D 別**: 上記以外、user が見えてる具体的 gap

## 6. 次セッション着手手順

1. user に「A / B / C / D のどれか」を聞く
2. 軸が決まったら、対応する narrow ticket を起票(本 ticket は親、子 ticket で実装)
3. 実装 → tests → commit → push → image rebuild + redeploy(必要なら)→ 検証

## 7. 参照

- 本日 5/8 朝 commit `927ac2c NOMOTOKE-RSS-PIPELINE-ENRICHMENT-001` — 配管追加
- 本日 5/8 朝 commit `0bf8900 NOMOTOKE-INTAKE-FALLBACK-SHELL-001` — manual-intake fallback でも装飾を維持
- 本日 5/8 朝 commit `d34072a NOMOTOKE-INTAKE-AUDIT-TIER12-001` — manual-intake T1+T2 audit fix
- `src/tools/manual_intake.py` — manual-intake 本体、`apply_rss_pipeline_enrichment` も同所
- `src/nomotoke_rss_router.py` — dry-run only、production 未統合
- `src/nomotoke_card_renderer.py` — nomotoke renderer 本体
- `src/rss_fetcher.py` `_select_template_v2()` — RSS の現 template_key 選択器、非 nomotoke 系
