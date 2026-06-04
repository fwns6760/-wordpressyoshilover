# 471 DATA-ARTICLE ⑥ 現役 vs レジェンド対比 — OB年度別データ前提

- **種別**: データ基盤 + 実装 / **priority**: P2(差別化・物語性高、ただし fact精度critical) / **effort**: L
- **親**: 設計 `mkdocs_docs/spec/data-articles-no1-design.md` §2⑥ / §10(解除仕様)
- **status**: BLOCKED_USER(着手=user 判断待ち。scope 大 + 事実誤認=致命的NGのため独断不可)
- **lane**: データ記事 post エンジン(A lane)
- **blocked_by**: OB 684 の年度別データ不在 + 着手 GO 未取得

## なぜ止まっているか(2026-06-04 実測)

⑥「{age}歳時点、{player}は{legend}を超えるか(通算{stat}比較)」を出すには **両者の年度別累計** が要る。

| 必要データ | 現役(現Giants) | OB(レジェンド) |
|---|---|---|
| 年度別成績 | ✅ `npb_career.json`(467) | ❌ **無し**(`ob_legends_full`=career総計のみ、`years`は文字列) |
| 生年月日 | ✅ | △ 628/684(56名欠損→対象外) |
| npb_id | ✅ roster解決 | ❌ 無し |

→ **唯一のブロッカー = OB側 年度別データ**。これが無いと「松井の27歳時点 通算本塁打」が出せない。

## 着手手順(設計 §10 準拠)

1. **PoC(案A・推奨)**: OB通算は ja.wikipedia 抽出済。同記事の「年度別成績」表を追加 parse。
   **ground-truth 21名で 年度別累計→総計 が `npb` 総計と一致するか検算**(467 と同じ検算ロジック)。npb_id 不要。
   - 案B(NPB公式)は OB の npb_id 解決手段が無くコスト高 → 案A 不成立時のみ。
2. PoC 成功 → **684 拡張**: 別 GCS object(例 `ob_career_yearly.json`)へ日次1回 ingest
   (`npb_career_ingest` パターン踏襲、publish 非ブロック)。
3. **⑥ 実装**: `career_milestone.py` / `alltime_ranking.py` と同様 env gate + 既定 draft、title case F。

## fact 精度ゲート(publish 前必須・致命的NG回避)

- age = シーズン年 − 生年(birth 必須、欠損OBは対象外)。
- 「同年齢時点 通算」= その age 以下の年度別を累計。**累計→通算total の検算を通ったOBのみ**対象。
- 1件でも不確かなら draft 落とし(LLM 補完禁止)。比較は同一指標・同一 age 定義のペアのみ。

## 受入条件

- ground-truth 21名で年度別累計が総計と一致。
- age時点比較が手検証と一致した上で draft 化(初期は X 自動投稿せず draft のみ、§11)。

## 次の判断(user)

**案A PoC(21名で年度別 scrape+検算)に GO するか。** 成功なら 684 拡張→⑥ 実装へ進む。
PoC は read-only 検証(WP 書き込みなし)なので低リスク。GO 後は A lane で着手可。
