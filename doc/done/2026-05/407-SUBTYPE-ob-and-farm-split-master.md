# 407-SUBTYPE-ob-and-farm-split-master

## 1. ticket header

- **status**: DRAFT (design lock 後、 子 ticket 着手)
- **priority**: P2 (記事 narrative の relevance 強化、 既存 publish に regression を出さない方針)
- **owner**: Claude / **lane**: Claude
- **依存**: なし (本 ticket は親、 子: [[408]] OB classifier / [[409]] farm 2/3 split / [[410]] WP front 表示)
- **設計 anchor**: `docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md`

## 2. 背景

- chat 起票: 「OBとかは？」「2軍と3軍を分けるは」(2026-05-20)
- 現状 subtype は `postgame / lineup / manager / pregame / probable_starter / farm / farm_result / farm_lineup / player / player_notice / player_recovery / manager_comment / fact_notice / live_update / social_news / social_video_notice / sns_topic / rumor_market` で構成
- **OB**: 元巨人選手の MLB / コーチ就任 / 解説者発言 / YouTube 出演 / 訃報 / 記念 記事は player_notice / general / social_news / manager_comment に散らばり、 巨人特化 relevance gate が利かない
- **farm 2/3 分離**: 巨人は 12 球団でも数少ない 3軍持ち。 現状 farm_* は 2軍 (イースタン) 前提のフォーマットで、 3軍 (練習試合 / 育成中心) 記事は混入 or general に落ちる

## 3. ゴール (本親 ticket の責務)

- subtype 名 / classifier 判定軸 / validator 要件 / WP 表示要件の **design lock** を本 ticket で確定
- 実装は子 ticket ([[408]] / [[409]] / [[410]]) に分割
- 子 ticket 全閉じ後、 受け入れ観察 → close

## 4. 子 ticket 構造

| 子 ticket | 担当領域 | 依存 |
|---|---|---|
| [[408]] | OB subtype 新設 (classifier + name table + validator + x_post 登録) | 407 design lock |
| [[409]] | farm 2軍/3軍 分離 (subtype 名 + classifier + validator + alias backward-compat) | 407 design lock |
| [[410]] | WP front / 記事ページ表示 (category slug + subtype badge + 出典帯 + archive) | 408 / 409 subtype 名 lock |

## 5. design lock (407 本体で決める)

### 5.1 subtype 名

- OB: `ob` (single subtype)
  - 元巨人選手の MLB 活躍 / コーチ就任 / 解説者発言 / YouTube 出演 / 訃報 / 記念 を包含
  - 細分化 (`ob_mlb` / `ob_coach` / `ob_voice` 等) は scope 外、 受け入れ観察後に検討
- farm 分離:
  - `farm2_result` (2軍 イースタン公式戦の結果)
  - `farm2_lineup` (2軍 スタメン / 試合前)
  - `farm3_practice` (3軍 練習試合 / オープン戦)
  - `farm3_player` (3軍 個人 narrative / 育成選手 spotlight)
  - alias: `farm` → `farm2_*` 既存挙動維持 (SUBTYPE_ALIASES で resolve)

### 5.2 classifier 判定軸 (lock、 子 ticket で実装)

- OB:
  - name table (元巨人 OB 名簿) の literal match を first gate
  - 入団履歴 / 退団履歴の literal 含有 (`元巨人` / `元読売` / `巨人 OB` / `読売 OB`) を second gate
  - 現役選手 (現在 NPB 12 球団 + MLB 在籍中) は OB 判定**しない** (false-positive 回避)
  - MLB 在籍中の元巨人 (例: 菅野 / 岡本) は `ob` 判定 (既存 [[project_mlb_player_inclusion_policy]] と整合)
  - confidence high のみ付与、 曖昧は player_notice / general に fallback
- farm 2軍 / 3軍 判定:
  - source URL / source title の literal (`イースタン` / `2軍 公式戦` → farm2、 `3軍` / `育成` / `練習試合` → farm3)
  - 育成選手 (背番号 3 桁) name の含有率 (高ければ farm3 寄せ)
  - 試合形式 (公式 / 練習 / オープン)
  - 曖昧時は farm2_* fallback (既存挙動と等価)

### 5.3 validator 要件 (lock、 子 ticket で実装)

| validator | OB | farm2_* | farm3_* |
|---|---|---|---|
| title_validator (prefix / first block) | 「元巨人」/「OB」prefix 推奨、 必須ではない | 既存 farm_* と同等 | 「3軍」/「育成」prefix 必須 |
| title_style_validator | rescue 経路 enable (player と同等) | farm 系 alias で既存通り | farm 系 alias + 3軍語彙 |
| body_validator | 現役解釈ミス回避(`今年の成績` 等 → OB の現所属に解決) | 既存 farm_result と同等 | 数値弱め (非公式) |
| source_attribution_validator | SPECIAL_REQUIRED に追加 (「元巨人 / 現所属 ◯◯」併記必須) | POSTGAME_OPTIONAL_WITH_WEB (farm と同等) | SPECIAL_REQUIRED (出典帯に 「3軍」明示) |
| baseball_numeric_fact_consistency | LENIENT (OB の current stats は外部 DB 不在) | STRICT (NPB 公式数値) | LENIENT (非公式数値) |
| event_key_publish_gate | GATEABLE (重複 publish guard 有効) | GATEABLE | GATEABLE |
| long_body_compression_audit | SUBTYPE_POLICY 既定 | farm_result alias | farm3 専用 policy (緩め) |
| weak_title_rescue | rescue 許容 (player と同等) | 不変 | rescue 許容 |
| x_post_generator | VALID_ARTICLE_SUBTYPES に追加 (enable は §11 user 判断後) | 不変 | VALID 登録のみ、 enable は §11 |
| postgame_revisit_chain | FACT_NOTICE で扱う | FARM_SUBTYPE で扱う | FARM_SUBTYPE で扱う |

### 5.4 WP front / 記事ページ表示要件 (lock、 [[410]] で実装)

- category slug 案: `ob` / `farm2` / `farm3` (確定は 410 で WP admin と相談)
- subtype badge: 「元巨人」/「2軍速報」/「3軍速報」
- 出典帯 format:
  - OB: 「元巨人 / 現所属 ◯◯ / 出典 ◯◯◯」併記
  - farm2: 「2軍 イースタン / 出典 ◯◯◯」
  - farm3: 「3軍 / 出典 ◯◯◯ (※非公式)」明示
- archive page: 既存 `/category/farm/` を維持し、 `/category/farm2/` `/category/farm3/` を子として新設
- noindex: 現フェーズ ([[project_current_phase_quality_not_seo]]) と整合、 新 archive も noindex 維持

## 6. 不可触範囲 (407 / 408 / 409 / 410 共通)

- 既存 subtype の挙動 (postgame / lineup / manager / pregame / probable_starter)
- guarded_publish_runner の publish 本体 logic (subtype 登録テーブルへの追加のみ可)
- WordPress REST の **mutation** (既存 published 記事の subtype / category 一括書き換え禁止)
- X 自動投稿の **enable** (VALID 登録のみ可、 enable は §11 user 判断後 = 別 ticket)
- production deploy (子 ticket 完了後、 user GO 後)
- env / Secret Manager / scheduler / traffic
- `automation.toml` / `.codex/automations/**` / draft-body-editor prompt の既定値
- data_insight chain (403/404/405) — 別 chain、 同便混在禁止
- mail / publish-notice / x_post_mail pipeline

## 7. STOP 条件 (407 / 408 / 409 / 410 共通)

`docs/handoff/session_logs/2026-05-20_ob_subtype_and_farm_split_design.md` §6 を参照。 主要 12 項目:

1. baseline pytest の fail 数増加
2. baseline pytest の collect 数減少
3. 既存 subtype の挙動 1 行変化
4. SUBTYPE_ALIASES 経路で既存 farm fixture の hash 変動
5. classifier confidence 計算の既存 subtype 影響
6. WP REST mutation 必要発生
7. env / Secret / Scheduler / traffic 変更必要発生
8. ticket scope が 1 PR で閉じない規模に膨張
9. published 記事の subtype 書き換え必要発生
10. 既存 X 自動投稿挙動への影響
11. Codex Final report と `git log --stat` の食い違い
12. `.git/index.lock` / `master.lock` 衝突

## 8. 受け入れ条件 (本親 ticket の close 条件)

- [[408]] / [[409]] / [[410]] 全閉じ
- baseline pytest fail 数増加なし
- dry-run で OB / farm2 / farm3 各 fixture が想定 subtype に振り分けられる
- 既存 farm 記事 fixture が `farm` alias 経由で `farm2_*` 同等挙動 (出力 hash 一致)
- WP front の category slug が 404 / blank を出さない (staging 目視 read-only)
- 自然 fire で OB / farm2 / farm3 各 1 件以上の draft が生成される (受け入れ観察、 deploy 後)
- 受け入れ観察期間: 自然 fire 1 週間
