# HALLUC-LANE-002 LLM-based fact-check augmentation

## meta

- owner: Claude Code(設計 + 起票)/ Codex(実装、push しない、Claude が push)
- type: ops / quality augmentation / LLM detector integration
- status: **doc-first 起票のみ**(実装 fire は user 明示 trigger 後、Gemini API 課金 = CLAUDE.md §11 user judgment 8 類型該当)
- priority: P1(PUB-004 安定運用後の品質強化レーン、PUB-004 の前提**ではない**)
- parent: HALLUC-LANE-001(土台 = extract / detect dry stub / approve YAML / backup / apply)
- siblings: PUB-004(WP publish runner、本 ticket と独立)/ PUB-002-A(判定 contract、本 ticket land 後に統合)
- created: 2026-04-25
- policy lock: 2026-04-25 22:00(PUB-004 前提でなく品質強化レーンとして起票、user 指定)

## scope 線引き

| 項目 | 本 ticket(HALLUC-LANE-002)| HALLUC-LANE-001(既設、土台) | PUB-004(WP publish runner) |
|---|---|---|---|
| extract / approve YAML / backup / apply | ✗ 流用 | ✓ 既設 | - |
| **detect 実 LLM 接続** | ✓ **本 ticket** | dry stub のみ | - |
| WP publish 実行 | ✗ | ✗ | ✓ |
| Green / Yellow / Red 判定 | ✓ LLM 判定で完全 verify | rule-based のみ | rule-based + 本 ticket 結果取り込み |
| 課金 | ✓ Gemini API | なし | なし |

## purpose

PUB-002-A の Green 10 条件のうち、LLM 判定領域を完全 verify する:
- **G3** title-body 主語・事象 一致(意味整合 / 同義語 / 言い換え)
- **G7** 数字・スコア・日付・選手名 source 矛盾なし(一次照合)
- **G8** body 内 named-fact が source にない断定でない(文意レベル)

→ rule-based では取りきれない **source-body contradiction** / **unsupported claim** / **numeric mismatch** を Gemini Flash で検出。
PUB-004-A の `needs_hallucinate_re_evaluation: true` flag を本 ticket land 後に再 evaluate、Green 判定の confidence を底上げ。

## PUB-004 との関係(前提でなく augmentation)

- **PUB-004 ship 順は本 ticket より先**(PUB-004 = rule-based partial check で運用開始、本 ticket land を待たない)
- 本 ticket land 後、PUB-004-A の rule-based 判定に LLM 判定を **オプション統合**(`--use-hallucinate-002` flag 等)
- 既存 PUB-004 publish された記事の品質 follow-up にも使用可(post-publish audit)

## 重要制約

- **Gemini API 課金 = user judgment 8 類型該当**(CLAUDE.md §11)
- 実装 fire 前に user 明示 trigger 必須
- 課金上限 / rate limit / batch サイズは本 ticket 内で固定(別 narrow ticket 不要)
- Gemini 以外の LLM 採用は本 ticket scope 外(別 ticket)
- pure Python + `google-generativeai` SDK 追加(requirements.txt に dep 追加)
- LLM call 結果は cache(`logs/hallucinate_cache.jsonl`)で同 post_id の重複 call 防止

## 不可触

- WP write(本 ticket は read-only judgment 強化のみ、publish は PUB-004 lane)
- HALLUC-LANE-001 の既設 contract / extract / approve YAML / backup / apply(改変なし、流用のみ)
- PUB-004 の既存 rule-based logic(改変なし、追加 flag で統合)
- automation / scheduler / .env / secrets / Cloud Run env
- baseballwordpress repo
- front lane

## 分割(後続実装の見取り図)

### HALLUC-LANE-002-A: Gemini Flash adapter 実装

#### scope
- 新規 file: `src/pre_publish_fact_check/llm_adapter_gemini.py`
- HALLUC-LANE-001 detector の `LLMAdapter` ABC を実装
- input: contract input JSON(extractor 出力)
- output: contract output JSON(severity / risk_type / suggested_fix)
- Gemini Flash call、prompt は user 提供 fact-check contract を system prompt として使用
- cache: `logs/hallucinate_cache.jsonl`(post_id + content_hash で dedup)
- 課金 cap: 1 invocation で N posts(N は env / flag で設定可、既定 5)
- error handling: rate limit / timeout / invalid JSON で graceful refuse(stub fallback)

#### CLI
```
python3 -m src.tools.run_pre_publish_fact_check --mode detect --live \
  --input-from /tmp/extracted.json \
  --output /tmp/findings.json
```

(既存 HALLUC-LANE-001 CLI の `--live` flag が初めて実装される、現在は `NotImplementedError`)

### HALLUC-LANE-002-B: PUB-004-A への統合

#### scope
- PUB-004-A evaluator に `--use-hallucinate-002` flag 追加
- Green / Yellow 候補に対して Gemini detect を call
- 結果を Green/Yellow/Red 判定に反映(LLM が high severity 出したら Red 落とし)
- cache 効果で 2 回目以降 call 0 円
- `needs_hallucinate_re_evaluation: true` flag を `false` に置き換え

### HALLUC-LANE-002-C: post-publish audit

#### scope
- 既 publish 記事に対して定期 audit
- LLM detect で post-hoc Red 検出 → user に escalation(rollback 候補)
- 課金は audit batch ごとに上限管理

---

## 依存 / 連携

- **HALLUC-LANE-001**(土台): detector ABC を実装、その他流用
- **PUB-002-A**: 判定 contract 正本、本 ticket land 後に G3/G7/G8 を完全 verify として更新
- **PUB-004-A**: rule-based partial check に LLM 判定を統合(B phase)
- **PUB-004-B**: post-publish audit 経路で本 ticket 利用可(C phase)
- `src/pre_publish_fact_check/detector.py`(既設、LLMAdapter ABC 流用)
- `requirements.txt`(`google-generativeai` 追加)
- `.env`(Gemini API key、表示禁止)

## 完了条件(本 ticket、doc-first まで)

1. doc 起票完了(本 file)
2. PUB-004 との関係(前提でなく augmentation)が明文化
3. Gemini Flash adapter 実装の 3 phase(A/B/C)が見取り図化
4. 課金 / cache / rate limit の安全装置が doc 化
5. 実装 fire は user 明示 trigger 後(本 ticket scope = doc-first まで)

## stop 条件

- Gemini API 課金が user 想定額超 → 本 runner で cap 内に強制制限
- API key の表示 / 露出 → 即停止
- LLM 判定が rule-based より厳しすぎて Green が 0 件 → 設定 tuning(prompt + threshold)
- 他 LLM 採用要望 → 本 ticket scope 外、別 ticket(`HALLUC-LANE-002-D-other-llm`)

## 関連 file

- `doc/PUB-002-A-publish-candidate-gate-and-article-prose-contract.md`(判定 contract、本 ticket land 後に G3/G7/G8 完全 verify として更新)
- `doc/PUB-004-guarded-auto-publish-runner.md`(WP publish runner、本 ticket と独立、後で統合)
- `src/pre_publish_fact_check/detector.py`(HALLUC-LANE-001 既設、本 ticket で `--live` 実装)
- `src/pre_publish_fact_check/applier.py`(HALLUC-LANE-001 既設、cleanup contract と並走)
- CLAUDE.md §11(user judgment 8 類型 = API 課金 増加)
- CLAUDE.md §17(コスト制約 = Gemini 2.5 Flash 前提)
