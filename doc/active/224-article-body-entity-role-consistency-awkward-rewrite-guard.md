# 224 article body entity-role consistency and awkward rewrite guard

## meta

- number: 224
- type: dev / quality
- status: READY(impl 進行中、`bif6lgn6p`)
- priority: P0.5
- lane: Codex B
- created: 2026-04-27
- parent: 217 publish gate hotfix / 200 scanner subtype fallback
- related: 225(X candidate text quality hardening)

## background

自動修正後の本文で、人名 + 肩書き + 「となって/となり」が不自然に続く現象が累積:
- 例: `戸郷翔征投手となって` / `阿部慎之助監督となり` / `村田コーチとなって`
- 事実は合ってるが日本語として不自然
- 自動公開数増加 → 読者の違和感累積、信頼低下リスク

## goal

不自然な構文を検出 + 安全に rewrite + 不可能なら publishable Yellow + warning。

## scope

- 検出対象: 人名(2-10 字)+ 肩書き(投手 / 捕手 / 内野手 / 外野手 / 選手 / 監督 / コーチ / 右腕 / 左腕)+「となって/となり/となった/となる」
- safe rewrite: `〜投手となって` → `〜投手が`、`〜監督となり` → `〜監督が`、`〜となった` → `〜は`
- ambiguous case: warning + Yellow flag
- source 未含 role(疑い)は副次的に検知(本便で hard_stop 化はしない、`unsupported_named_fact` 既存 hard_stop で十分カバー想定)

## affected files

- 新規 `src/article_entity_role_consistency.py`(detector + safe_rewrite helper)
- `src/guarded_publish_evaluator.py`(`awkward_role_phrasing` flag、Yellow 扱い)
- `tests/test_article_entity_role_consistency.py`(新規)
- `tests/test_guarded_publish_evaluator.py`(flag verify)

## acceptance

- 不自然な `人名+肩書き+となって/となり` を検出
- 安全な case のみ rewrite
- ambiguous case は Yellow + warning
- 既存 publish gate / hard_stop 不変
- 既存 logic(187-223)に touch しない

## non-goals

- 大規模 body rewrite / NLP integration / 選手 DB 構築
- 全記事一括修正
- WP live write / GCP deploy(別便)

## next_action

- impl 進行中 `bif6lgn6p`(Codex B fire 済)
- 完了通知 → 5 点追認 → push → publish-notice rebuild は不要(guarded-publish 影響、別 deploy 便で扱う)

## related ticket

- 217 publish gate hotfix(REPAIRABLE / Yellow flag pattern を流用)
- 200 scanner subtype fallback
- 225 X candidate text quality hardening(関連、X 出力品質)
