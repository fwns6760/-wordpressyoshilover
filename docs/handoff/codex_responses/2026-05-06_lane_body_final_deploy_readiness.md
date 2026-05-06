# Lane BODY-FINAL deploy readiness packet (本 session deploy 不実行、明日以降 user GO 後)

作成日: 2026-05-06 12:25 JST
作成者: Claude Code (session-level lock 解除中)
スコープ: doc-only (deploy 手順整理、実 deploy は user GO 後)

## 1. 現 live 状態

### 1-1. 既に live ON (確認済、env audit 2026-05-06 12:23 JST)
| flag | scope |
|---|---|
| `ENABLE_BODY_DUP_REDUCTION` | rss_fetcher (body 段) |
| `ENABLE_TITLE_GENERIC_COMPOUND_GUARD` | rss_fetcher (title) |
| `ENABLE_TITLE_HASHTAG_NAME_RECOVERY` | rss_fetcher (title) |
| `ENABLE_DUPLICATE_SENTENCE_GUARD` | rss_fetcher (body) |
| `ENABLE_ACTIVE_TEAM_MISMATCH_GUARD` | rss_fetcher (entity) |
| `ENABLE_BODY_LEAD_PARAPHRASE_GUARD` | rss_fetcher (lead) |
| `ENABLE_ENTITY_MISMATCH_REPAIR` | rss_fetcher (Lane PP repair) |

### 1-2. 残り MISSING (deploy 候補 6 個)
| flag | scope | risk |
|---|---|---|
| `ENABLE_FORBIDDEN_PHRASE_FILTER` | rss_fetcher (NG phrase) | LOW (rewrite + detect) |
| `ENABLE_H3_COUNT_GUARD` | rss_fetcher (post_gen_validate) | LOW (3+ reject、Lane PP H4 降格 path) |
| `ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR` | rss_fetcher (Theme3) | MEDIUM (deterministic 削除 + review) |
| `ENABLE_QUOTE_INTEGRITY_GUARD` | rss_fetcher (Lane OO) | LOW (壊れた quote reject) |
| `ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR` | rss_fetcher (Theme3) | MEDIUM (短文化過剰 risk) |
| `ENABLE_SOURCE_GROUNDING_STRICT` | rss_fetcher (Lane OO) | MEDIUM-HIGH (review queue 増、誤検出 risk) |

## 2. 現 image / commit 状態

```
fetcher service image: yoshilover-fetcher:bcce73d (live, revision 00215-92l)
commits in image (chronological 古→新):
  - 5528fc9 freshness base
  - 7d7e44d title hashtag-recovery (1 flag)
  - bf29bcc P0 publish_notice two-phase
  - c7e91af Theme3 BODY-FINAL bundle (5 fix、新 ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR / 既存拡張)
  - ea61f0d Theme2 stale freshness wiring
  - 5191adc Lane 5 RSS fixture pack
  - bcce73d Python 3.11 fix (live)

未 image: 1f3e393 (BODY-FINAL audit + 1 NG phrase 「原文のニュアンスを残しながら」追加)
  - rebuild 必要なら image tag = 1f3e393 で再 build
  - rebuild なしで live deploy 可能 (現 bcce73d image は他 5 NG phrase + heading rewrite 完備)
```

## 3. deploy 手順 (BODY-FINAL、本 session 内では実行しない)

### 3-α. 任意: image rebuild (1 NG phrase 追加分含めるなら)
```bash
cd /home/fwns6/code/wordpressyoshilover
gcloud builds submit --project=baseballsite \
  --tag=asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/yoshilover-fetcher:1f3e393 .
```
推定 4-6 min。追加効果は marginal (1 NG phrase だけ)、急ぎ不要なら skip 可。

### 3-β. flip 順 (1 個ずつ、各 1-2 cycle 観察)

| Phase | flag | risk | 観察項目 |
|---|---|---|---|
| **B1** | `ENABLE_FORBIDDEN_PHRASE_FILTER=1` | LOW | `phrase_*` rewrite trace、duplicate_sentence 増えない |
| **B2** | `ENABLE_QUOTE_INTEGRITY_GUARD=1` | LOW | `quote_integrity_*` reject 件数、誤検出なし |
| **B3** | `ENABLE_H3_COUNT_GUARD=1` | LOW | `h3_count:too_many_h3` reject、Lane PP repair で H4 降格動作 |
| **B4** | `ENABLE_SOURCE_GROUNDING_DRIFT_REPAIR=1` | MEDIUM | `source_grounding_drift:*` repair / review、本文薄化なし |
| **B5** | `ENABLE_SHORT_SOURCE_BODY_SHRINK_REPAIR=1` | MEDIUM | short article 増加、source-faithful 維持 |
| **B6** | `ENABLE_SOURCE_GROUNDING_STRICT=1` | MEDIUM-HIGH | review queue 増、auto-publish 急減チェック |

各 phase で:
```bash
gcloud run services update yoshilover-fetcher \
  --project=baseballsite --region=asia-northeast1 \
  --update-env-vars=<flag>=1 --quiet
```

### 3-γ. 各 phase 共通 verify
- run_summary 1-2 cycle 完走、error_count=0
- ERROR / Traceback / OOM / 「【まとめ】10件」 0
- duplicate_sentence 増加なし
- drafts_created が急減しない (前 baseline 比、cycle あたり)
- Lane 1 P0 / Lane 2 stale freshness / 既存 7 BODY flag 維持
- /health 200

## 4. STOP 条件 (deploy 中)

- duplicate_sentence 急増
- drafts_created 2 cycle 連続 0 (前 baseline で +ある場合)
- publish_success 急減
- mail storm
- timeout 再発 (publish-notice 900s)
- OOM / GCP CRITICAL
- 「【まとめ】10件」 reactivation
- container start fail
- env drift (target 以外の flag が変わる)
- review queue 過剰 増 (B6 SOURCE_GROUNDING_STRICT で特に注意)

## 5. rollback コマンド (各 phase)

```bash
# B1 rollback
gcloud run services update yoshilover-fetcher \
  --project=baseballsite --region=asia-northeast1 \
  --remove-env-vars=ENABLE_FORBIDDEN_PHRASE_FILTER --quiet

# B2-B6 同様 (--remove-env-vars=<flag>)
```

最後に ON した flag だけ rollback、既存 7 BODY flag + Lane 1 P0 + Lane 2 RSS-FINAL は維持。

## 6. 想定効果 (live observation で初めて確定)

- B1: AI 風 NG phrase が出力 / 検出されなくなる (rewrite + detect)
- B2: 壊れた quote (中途半端な「」) を含む draft を review hold
- B3: H3 が 3+ の draft を reject、Lane PP path で H4 降格 repair
- B4: source 外 score / quote / team / actor 文を deterministic 削除 or review
- B5: 短い source に長文 template が当たった case を short body へ縮約
- B6: source-grounded でない draft を review queue へ routing

## 7. user 確認境界 (本 session で実行しない)

本 packet は doc-only。flip は user 明示 GO 後。

## 8. 関連 commit
- Theme3 bundle: `c7e91af`
- Title hashtag-recovery: `7d7e44d`
- Defensive helper + Python 3.11 fix: `bcce73d`
- BODY-FINAL minor patch (本日): `1f3e393`

## 9. next_judgment
- doc-only commit + push
- 実 deploy / flip は user GO 後 (P0/RSS-FINAL live が安定継続している前提)
