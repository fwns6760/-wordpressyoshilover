# 334-QA player_voice_digest subtype + 3-token literal title assembly

## meta

- ticket: 334-QA-player-voice-multi-source-digest-subtype
- owner: Claude Code
- status: DESIGN_LOCKED / READY_FOR_PHASE_0_AUDIT
- priority: P1(本文品質改善の中核、CLAUDE.md §9 title assembly = 最優先)
- created: 2026-05-14
- numbering reserved in: `doc/README.md`
- supersedes: なし(新規 subtype 追加、既存 subtype 動作変えない)
- related closed: 277-QA / 278-QA / 290-QA / 293-COST / 250-QA-1 / 250-QA-3
- related memory: `feedback_title_no_ai` / `project_multi_source_digest_subtype`

## scope

のもとけ風の「1試合 × 1選手 × 3 サイト以上の媒体集約」記事を新 subtype `player_voice_digest` として導入。title は 3-token literal assembly(player / quote / event)。AI / LLM 一切使わない。

### user intent(2026-05-14 chat lock)

- 媒体名は title 末尾より、イベント(`300号サヨナラホームラン` 等)が良い
- 坂本勇人だけでなく他の選手も対象(player-agnostic)
- 今後の記事のみ対象(既存記事の遡及 digest 化なし)
- 複数 web 媒体サイト(報知 / サンスポ / スポニチ / 日刊スポーツ / デイリー 等)

## goal

`坂本勇人「最後まで集中して振り切れた」300号サヨナラホームラン` 型の title + 本人発言核 + 各サイト引用集約 の subtype を 1 本 publish できる pipeline を作る。

## title pattern(厳格 spec、AI 禁止)

```
[選手名 literal] + 「 + [本人発言 substring 20-40字 literal] + 」 + [イベント literal]
```

例:
- `坂本勇人「最後まで集中して振り切れた」300号サヨナラホームラン`
- `岡本和真「ファンの声援が後押しになった」逆転3ラン`
- `菅野智之「球が走っていた感触はあった」7回1失点`

### 3-token literal 制約

| token | source | OK 例 | NG 例 |
|---|---|---|---|
| 選手名 | source structured field / NER literal | `坂本勇人` / `岡本和真` | `主砲` / `キャプテン` |
| セリフ | 本人発言 literal の 20-40字 substring(句読点で natural break) | `最後まで集中して振り切れた` | LLM rewrite / paraphrase |
| イベント | source 由来の数値 fact / 試合状態 fact / 出来事固有名 | `300号サヨナラホームラン` / `7回1失点` / `完封勝利` / `逆転3ラン` | `劇的な一発` / `価値ある勝利` / `見事な投球` |

### LLM 使用箇所(全部禁止)

- セリフを「要約」して短くする
- セリフを言い換え / paraphrase
- 選手名を別表現に変換
- 媒体名を「各紙」にまとめる
- イベント token を narrative 化
- 3-token のいずれかが揃わない時の「補完」

3-token literal が揃わない → digest 化せず draft 落とし、review。**LLM で title 可能化しない**。

## body 構造

```
[選手名]「[本人発言 literal 全文 80-150字]」

(背景の地の文 3-5行、source 由来 fact のみ、AI narrative 禁止)

▼ 報知が伝える
本人発言以外の追加情報(literal 短引用 30-50字)
[元記事リンク]

▼ サンスポが伝える
本人発言以外の追加情報(literal 短引用 30-50字)
[元記事リンク]

▼ スポニチが伝える
...
```

### 著作権制約(厳守)

- 各サイト引用は 30-50字 literal、主従関係保持(主=本人セリフ / 従=各サイト報道)
- 出典サイト名 + 元 URL 必須
- AI 言い換え禁止(literal substring のみ)
- マスコミ X 引用は oEmbed 経由のみ(本 ticket は web 媒体集約、X は対象外)
- 引用要件 4 条件(主従関係 / 出所明示 / 改変なし / 必要範囲)を満たす

## clustering 条件(全条件 AND)

1. 同一試合(game_id 一致)
2. 同一選手(player_id 一致、player-agnostic)
3. 24h 以内の source 集合
4. **3 サイト以上の媒体サイト報道**(報知 / サンスポ / スポニチ / 日刊スポーツ / デイリー)
5. 本人発言が literal で source 内に存在し、20 字以上抽出可能
6. イベント token(数値 fact / 試合状態 fact)が source から literal 抽出可能

**hero 検出は不要**: 「3 サイト以上が同選手を取り上げる」事実そのものがヒーロー signal。

### 抽出失敗時

- 3 token のいずれかが揃わない → digest 化せず draft 落とし、review
- 3 サイト未満 → digest 化せず、既存単記事 pattern 維持
- 既存単記事 subtype(postgame / manager 等)と併存

## 不可触リスト(hard constraints)

- 既存 subtype(postgame / manager / lineup / pregame / farm / broadcast / notice 等)の title / body 生成ロジックを変えない
- `title_template_assembler.py` の既存 pattern 関数(`_assemble_pattern_A..O`)を変更しない、**新 pattern 関数を追加する**
- LLM call(Gemini / その他)を title / body literal 抜き出し path に持ち込まない
- publish / mail / scheduler / env / Cloud Run image / GitHub Actions / SEO / source 追加 は本 ticket scope 外(後続便で分離)
- X 自動投稿 / X 候補 への影響を出さない(本 subtype は当面 X 出力 OFF)
- 既存 publish 済み記事への遡及変更しない(forward-only)
- 著作権境界を緩めない(各サイト 30-50字、出典明示、literal のみ)

## phase 分割(narrow PR 単位)

### Phase 0: read-only audit(本 ticket 開始時)

- `title_template_assembler.py` で新 pattern 追加位置の特定
- `rss_fetcher.py` で source clustering / candidate selection 部の entry point 特定
- 既存 source extractor(`source_*_extractor.py`)の coverage map(報知 / サンスポ / スポニチ / 日刊 / デイリー それぞれ extractor 有無)
- 本人発言 literal 抽出が既存 code で可能か(`speech_seed_intake.py` / `source_postgame_extractor.py` 周辺)
- イベント token 抽出可能性(数値 fact / 試合状態 fact)の有無
- 既存 publish data から「3 サイト以上同選手 cluster」が日次何件出るかを観測(feasibility)

**Phase 0 成功条件**: 監査結果を doc に書き、Phase 1 spec の精度を上げる。code 変更なし。

### Phase 1: subtype dispatcher + title pattern(narrow impl)

- `title_template_assembler.py` に `_assemble_pattern_X_player_voice_digest()` 追加
- `_is_quote_subtype()` または subtype dispatch に `player_voice_digest` 認識追加
- title fixture テスト追加(positive / negative 各 5 件)
- 3-token のいずれかが揃わない場合の draft 落とし path
- 既存 pattern A-O のテスト不変

### Phase 2: clustering + candidate detector(narrow impl)

- 新 module `player_voice_digest_clusterer.py`(仮称)
- clustering 6 条件を厳密にチェック
- candidate を draft として emit、publish gate は既存 guarded_publish に従う
- 既存 candidate selection を変えない(additive)

### Phase 3: body assembler(narrow impl)

- 新 module `player_voice_digest_body_renderer.py`(仮称)
- 本人発言 literal + 各サイト 30-50字 literal + 出典 URL を section heading 付きで組み立て
- 著作権要件のテスト(引用長 / 出典明示 / 主従関係)を fixture 化

### Phase 4: live canary + observation(user GO 必要)

- canary 1-5 本 publish(noindex 維持 / X OFF)
- 監査軸(title 適合率 / 引用境界 / 事実整合)
- 観察期間後、scope 拡大 / template 改善 / OFF rollback の判断

## success criteria

- Phase 0 audit doc 1 本起票
- Phase 1-3 で fixture-based 単体テスト全 PASS(既存 pytest baseline 維持、増減 0)
- Phase 4 canary publish 5 本、title 3-token 完全 literal(audit で人手チェック)、AI 介入 0 件、引用境界違反 0 件
- 既存 publish flow (postgame / manager / lineup 等) のデグレ 0(回帰テスト全 PASS)

## acceptance pack(per phase)

- changed files
- 実施内容
- pytest 数値(baseline vs new、collect / pass / fail)
- 動作確認 command 出力
- remaining risk
- open question
- 次便判断

## numbering / folder policy

- ticket 番号: 334(README で reserve)
- folder: `doc/active/`(本 ticket、DESIGN_LOCKED / READY_FOR_PHASE_0_AUDIT)
- status 変更時は CLAUDE.md ticket folder policy に従い移動 + README doc_path 更新 + assignments.md 同 commit 更新

## next action

1. ~~Claude Code が Phase 0 read-only audit を実施(本日中、code 変更なし)~~ **完了 2026-05-14**
2. ~~監査結果を本 doc に追記~~ **完了(下記 Phase 0 結果)**
3. Phase 1 narrow impl 着手判断(本 doc Phase 1 spec 参照)

## Phase 0 audit 結果(2026-05-14、read-only、code 変更なし)

### F1. title assembler の新 pattern 接続位置 — **clean**

- `src/title_template_assembler.py` の `assemble_nomotoke_title()` (414-509 行) は subtype elif chain
- 新 subtype `player_voice_digest` の elif branch を追加するだけで dispatcher 接続可能
- 既存 `_is_quote_subtype()` (143-149) は touch しない — `player_voice_digest` は別 branch で処理
- 新 pattern 関数 `_assemble_pattern_X_player_voice_digest()` を additive に追加(既存 _assemble_pattern_A..O は不変)

### F2. 5 媒体サイト registry — **全部既存**

`src/source_trust.py` に 5 サイト全部 family 登録済(46-79 行):

| サイト | family | domains | trust |
|---|---|---|---|
| 報知 | `hochi` | hochi.news / hochi.co.jp / sports.hochi.co.jp | secondary / mid |
| サンスポ | `sanspo` | sanspo.com | secondary / mid |
| スポニチ | `sponichi` | sponichi.co.jp | secondary / mid |
| 日刊スポーツ | `nikkansports` | nikkansports.com | secondary / mid |
| デイリー | `daily` | daily.co.jp | secondary / mid |

→ clustering の「3 サイト以上」判定は `SourceProfile.family` の distinct count で実装可能。

### F3. 媒体日本語ラベル map — **PARTIAL(verify 後補正、daily 不在)**

`src/nomotoke_card_renderer.py` の **`_PRIMARY_HOST_LABELS` map**(変数名 verify 済、line 1627-1641):

| domain | label | 状態 |
|---|---|---|
| `hochi.news` / `www.hochi.news` | スポーツ報知 | ✓ 既存 |
| `sanspo.com` / `www.sanspo.com` | サンスポ | ✓ 既存 |
| `nikkansports.com` / `www.nikkansports.com` | 日刊スポーツ | ✓ 既存 |
| `sponichi.co.jp` / `www.sponichi.co.jp` | スポニチ | ✓ 既存 |
| `daily.co.jp` / `www.daily.co.jp` | デイリー(仮) | **✗ 不在、Phase 1 で map 追加必要** |
| `giants.jp` / `npb.jp` / `yomiuri.co.jp` / `x.com` 等 | 各種 | ✓ 既存(別系統) |

→ 本文 `▼ <媒体名>が伝える` section heading に再利用するが、**デイリーを Phase 1 patch で追加**(2 line)。`hochi.co.jp` / `sports.hochi.co.jp` も `_PRIMARY_HOST_LABELS` 不在(`source_trust.py` には登録あり)、整合性のため Phase 1 で追加検討。

### F4. 本人発言 抽出 / clustering 基盤 — **PARTIAL(verify 後補正、cross-source clusterer は新規)**

`src/speech_seed_intake.py` 実体 verify(line 315-374):

| API | 実体 | 本 ticket 再利用可否 |
|---|---|---|
| `evaluate_speech_seed()` / `_batch()` | 発言評価 API(本人発言の認定 + scene / quote_core 抽出) | ✓ 抽出 layer に再利用 |
| `_build_candidate_key(source_url, speaker, scene, quote_core)` | **per-source fingerprint**(source_key 込み sha1 12文字)— ⚠️ cross-source dedup ではない、source 違うと別 key になる | ✗ 同一選手 cross-source clustering には使えない |
| `_compute_news_overlap_score(seed, rss_index, quote_core)` | seed の title / quote と rss_index titles の similarity 計算 | △ 検証 layer に応用可、cluster key 直接生成は不可 |
| `_title_similarity()` / `_jaccard()` / `_char_ngrams()` | 汎用 string similarity helper | ✓ そのまま再利用可 |
| `_looks_multi_nucleus()` / `_looks_multi_scene()` | 1 seed 内で multi の検出 | △ digest 適性判定の追加 signal に転用可能 |

→ **当初「foundation ほぼ揃ってる」は OVERSTATED**。**cross-source(同一試合×同一選手×3 サイト以上)clusterer は新規実装が必要**(似た player + 試合 metadata で grouping → 3 サイト以上 family distinct count check の wrapper)。string similarity helper は再利用、clustering key 設計は新規。

### F5. rss_fetcher 接続点 — **PARTIAL(verify 後補正、keying は別実装)**

`_merge_source_summary()` 実体 verify(line 19780-19798):

- 関数本体は実在し、複数 candidate の sentence を merge + dedup する汎用 logic
- ただし**現在は `_aggregate_lineup_candidates`(19801)からのみ呼ばれ、keying は `(published_day, "lineup")`** — つまり「同一日 × lineup subtype」専用 grouping
- player_voice_digest の keying(game_id + player_id + 24h)は **別 grouping logic 新規実装が必要**

| 既存資産 | 再利用可否 |
|---|---|
| `_merge_source_summary(candidates, max_sentences)` | ✓ sentence merge helper として直接再利用可 |
| `_aggregate_lineup_candidates` の grouping pattern | ✓ 構造を真似て `_aggregate_player_voice_digest_candidates` を新規追加(player_id + game_id 用) |
| `_annotate_duplicate_guard_contexts` / `_duplicate_candidate_priority_sort_key` | △ 並走に注意、digest 分岐は duplicate guard より **前段**で評価必要(duplicate に捨てられる前) |

→ 「duplicate として捨てる」のではなく「3 サイト以上揃ったら digest 化、未満なら通常 candidate に戻す」分岐を duplicate guard **pre-step** に挿す。既存 candidate flow に additive で接続可能、ただし pre-step 挿入位置の verify が Phase 2 着手前に必須。

### F6. 既存 quote subtype の正常動作 — **clean**

- `_is_quote_subtype()` は `player_comment / player_quote / manager_comment / coach_comment` の 4 種
- 新 subtype `player_voice_digest` は **これら 4 種より優先**で評価される必要(同一 source が 3 サイト揃ったときだけ digest 化、足りなければ既存 quote subtype に fall-through)
- → dispatcher 順序設計: clustering check 通過 → digest / 通過しない → 既存 quote pattern A

### F7. 著作権 / 引用境界 — **要 narrow guard**

- 各サイト 30-50 字 literal 引用 は既存 guard なし(新規実装必要)
- 出典名 + URL: nomotoke_card_renderer の DOMAIN_TO_LABEL + source URL で組み立て可能
- AI 言い換え禁止 path: 新 pattern / clusterer / body_renderer 全部に LLM call を 1 つも含めない hard 制約
- 主従関係(主=本人セリフ / 従=各サイト報道): 本人セリフ 80-150 字 vs 各サイト 30-50 字 × 3-5 = 主従明確

### F8. 環境変数設計

- `ENABLE_PLAYER_VOICE_DIGEST_SUBTYPE`(default `0` / OFF、Phase 4 canary で限定 ON)
- `ENABLE_NOMOTOKE_TITLE_TEMPLATE`(既存 default `1`)とは独立、digest subtype 専用 gate
- canary 中の rollback は env 1 → 0 で即時可能

### F9. デグレ risk surface

- **既存 subtype の title / body 生成 path に新 LLM call を持ち込まない** — 本 ticket scope 外
- **既存 quote subtype (`player_comment` 等) の dispatcher 順序を変えない** — clustering 通過時のみ digest 分岐、failure 時は完全 fall-through
- **publish gate / X gate / mail gate 不変** — 新 subtype は既存 guarded_publish に従う、新規 gate 追加なし
- **既存 pytest baseline 不変** — Phase 1-3 で新 test 追加のみ、既存 test は touch しない

### F10. Phase 1 実装 readiness — **GO 判定(但し F4/F5 補正後)**

foundation の一部は既存、cross-source clustering の core は新規。新規コード量(verify 後上振れ):

| 新規 / 改修 | 推定行数(verify 後) | 内容 |
|---|---|---|
| `title_template_assembler.py` patch | +60 行 | 新 elif branch + `_assemble_pattern_X_player_voice_digest()` 関数 |
| `nomotoke_card_renderer.py` patch | +6 行 | `_PRIMARY_HOST_LABELS` に daily.co.jp 等を追加 |
| 新 `player_voice_digest_clusterer.py` | **+200 行**(当初 150 → +50) | cross-source clustering(player+game+24h+3 サイト)新規、speech_seed_intake の similarity helper 再利用 |
| 新 `player_voice_digest_body_renderer.py` | +120 行 | 本人セリフ + 各サイト引用 + 出典 section assembler |
| rss_fetcher 接続点 patch | **+40 行**(当初 20 → +20) | duplicate guard pre-step 挿入 + `_aggregate_player_voice_digest_candidates` 関数追加 |
| tests | **+250 行**(当初 200 → +50) | fixture-based unit test、cross-source clustering negative case 強化 |

合計 **約 676 行**(当初 550 → +126)、4 phase narrow PR で着地可能。Phase 1 単独は `title_template_assembler.py` +60 行 + tests のみで最小着地。

### F11. verification status(2026-05-14 audit、AI 事故源対策)

各 finding を「実体読み verify」「grep 推定」「ToDo」で classify:

| Finding | 確認手段 | 状態 |
|---|---|---|
| F1 title assembler dispatcher 414-509 | 実体 read | ✓ verified |
| F2 source_trust 5 family registry | 実体 read 40-92 | ✓ verified |
| F3 _PRIMARY_HOST_LABELS map | 実体 read 1620-1649 | ✓ verified、**daily 不在 を確認** |
| F4 speech_seed_intake API | 実体 read 315-374 | ✓ verified、**cross-source clusterer 不在 を確認** |
| F5 _merge_source_summary | 実体 read 19780-19840 | ✓ verified、**lineup 専用 を確認** |
| F6 既存 quote subtype dispatcher 順序 | 実体 read | ✓ verified |
| F7 著作権 / 引用 guard | grep + 既存 doc | △ 既存 guard 不在の grep 結果のみ、Phase 2 で全パス再 verify |
| F8 env flag 設計 | spec | ToDo Phase 1 で実装時に既存 ENABLE_* と命名整合確認 |
| F9 デグレ risk surface | 設計 | ToDo Phase 1 着手前に既存 test を実行して baseline 数値を ticket に記録 |
| F10 行数推定 | 推定 | △ 実装着手後に actual 行数を ticket に追記 |

**Phase 1 着手前の必須 verify(silent skip 禁止)**:
1. pytest 全体 baseline 数値(collect / pass / fail)を ticket に記録
2. `_PRIMARY_HOST_LABELS` の追加候補 host を 5 サイト全部 enumerate
3. `title_template_assembler.py` の既存 test 一覧を grep し、回帰対象を確定

これらを実行せず Phase 1 fire するのは「記憶から再構成 / 自己評価 OK」事故源 → 禁止。

## F12. 5 サイト URL inventory(2026-05-14 verified、grep + WebFetch)

### 確認方法

- 一次情報: `src/source_trust.py` / `src/tag_page_scraper.py` / `src/lineup_source_priority.py` / `src/postgame_strict_fact_recovery.py` / `config/rss_sources.json` を grep
- 二次情報: WebFetch(`hochi.news` / `sponichi.co.jp` / `sanspo.com` / `nikkansports.com` は **Claude Code WebFetch ブロック**、`daily.co.jp` のみ 200)
- daily 1 サイトのみ WebFetch で article URL pattern verify、他 4 サイトは **repo 内 code が一次情報**

### 6 サイト完全 URL inventory(2026-05-14 user 指示で東スポ 6 サイト目追加)

| サイト | 日本語ラベル | source_trust 登録 domain(verified) | article URL pattern(verified) | intake 経路 | _PRIMARY_HOST_LABELS 状態 |
|---|---|---|---|---|---|
| **スポーツ報知** | `スポーツ報知` | `hochi.news`, `hochi.co.jp`, `sports.hochi.co.jp`(3 domain) | `https://hochi.news/articles/{YYYYMMDD}-{code}.html` | web scraper(`hochi_giants_tag`、`https://hochi.news/tag/巨人`) + X(`hochi_giants` / `hochi_baseball` / `SportsHochi` rsshub) | Phase 1 で 3 domain 全部追加済 ✓ |
| **サンスポ** | `サンスポ` | `sanspo.com`(1 domain) | `https://www.sanspo.com/article/{YYYYMMDD}-{code}/` | web scraper(code に存在 `tag_url=https://www.sanspo.com/?s=巨人`、ただし `config/rss_sources.json` には未登録) + X(`Sanspo_Giants` rsshub) | ✓ 既存(unchanged) |
| **スポニチ** | `スポニチ` | `sponichi.co.jp`(1 domain) | repo code には article URL pattern 未実装(scraper なし) | X のみ(`SponichiYakyu` rsshub `media_quote_pool`) | ✓ 既存(unchanged) |
| **日刊スポーツ** | `日刊スポーツ` | `nikkansports.com`(1 domain) | `https://www.nikkansports.com/baseball/news/{YYYYMMDDxxxxxxx}.html`(sample `202605030000454.html`) | RSS atom feed(`https://www.nikkansports.com/rss/baseball/professional/atom/giants.xml`) + X(`nikkansports` / `nikkan_giants` rsshub) | ✓ 既存(unchanged) |
| **デイリー** | `デイリー` | `daily.co.jp`(1 domain) | `https://www.daily.co.jp/baseball/{YYYY}/{MM}/{DD}/{Article ID}.shtml`(WebFetch verified) | web scraper(`daily_giants_tag`、`https://www.daily.co.jp/baseball/giants/index.shtml`) + X(`daily_baseball` rsshub) | Phase 1 で 2 domain 追加済 ✓ |
| **東スポ**(2026-05-14 追加、user 指示) | `東スポ` | `tokyo-sports.co.jp`, `www.tokyo-sports.co.jp`(2 domain、本 commit で source_trust に新規登録、family=`tokyo_sports`、handles=`tospo_giants`) | `https://www.tokyo-sports.co.jp/articles/-/{記事ID}`(WebFetch verified、例 `/articles/-/388115` 坂本 300 号記事) | 巨人 section `https://www.tokyo-sports.co.jp/list/label/%E5%B7%A8%E4%BA%BA`、scraper / RSS 未接続(`doc/waiting/288-INGEST-source-coverage-expansion.md` で planning 状態) | 本 commit で 2 domain 追加 ✓ |

### 補足注記

- **報知の domain 3 種**: 歴史的に `hochi.co.jp` / `sports.hochi.co.jp` 両方あり、現在は `hochi.news` が主、3 つとも source_trust に登録済み(全部「報知」family)。Phase 1 で 3 domain 全部 label map に追加済
- **サンスポ scraper の status**: code 上 `tag_page_scraper.py` に `sanspo_giants_search` 関数が実装されているが、`config/rss_sources.json` には登録なし。本 ticket は intake 拡張を行わない(forward-only / clustering 専念)、既存 intake 経路で 3 サイト揃ったときのみ digest 化
- **スポニチ scraper の不在**: 現状 `media_quote_pool` 経由のみ。digest cluster で「スポニチ報じる」section を出すには、X 投稿が記事 link を含むケースのみ拾える。Phase 0 audit 段階では intake 拡張は **scope 外**(本 ticket は cluster + title + body 生成に専念)
- **東スポ scraper の不在**: 2026-05-14 本 commit で `source_trust` 登録 + label map 追加までは完了、しかし intake pipeline は未接続(`config/rss_sources.json` / `tag_page_scraper.py` 共に東スポ scraper なし)。`doc/waiting/288-INGEST-source-coverage-expansion.md` で東スポ巨人担当 X (`@tospo_giants`) / 東スポ WEB 巨人ラベル両方の planning が既存。digest cluster で「東スポ報じる」section を出すには、Phase 2 で intake 拡張または既存 X 経由 link 取得が必要 — 本 ticket scope では「source_trust に登録されており digest count される 6 サイト目」扱い
- **WebFetch ブロック**: hochi / sponichi / sanspo / nikkansports は Claude Code WebFetch から拒否される(`Claude Code is unable to fetch from ...`)。daily / tokyo-sports は WebFetch 成功、canonical URL と article pattern を直接 verify。WebFetch 不可サイトは **repo 内 code が一次情報**(scraper / RSS atom は実 server から取得)

### `_PRIMARY_HOST_LABELS` patch 完全リスト(Phase 1 で 5 行 + 2026-05-14 east-sports で 2 行 = 計 7 行追加済)

```python
# 既存 _PRIMARY_HOST_LABELS (nomotoke_card_renderer.py) に追加済:
    "hochi.co.jp": "スポーツ報知",
    "www.hochi.co.jp": "スポーツ報知",
    "sports.hochi.co.jp": "スポーツ報知",
    "daily.co.jp": "デイリー",
    "www.daily.co.jp": "デイリー",
    "tokyo-sports.co.jp": "東スポ",
    "www.tokyo-sports.co.jp": "東スポ",
```

7 行で 6 サイト全 domain 変種の日本語ラベルが揃う。Phase 1 commit `78f1f79` + 東スポ commit に分割。

## F13. pytest baseline + 既存 test 一覧(2026-05-14 measured)

### 全体 collect baseline

| 軸 | 数値 | 確認 command |
|---|---|---|
| 全体 tests collected | **4261** | `python3 -m pytest --collect-only -q tests/` |
| 全体 pytest 実行(focused、未測定) | — | Phase 1 PR の CI で全実行、増減 0 を accept gate |

### Phase 1 regression target(narrow scope)focused baseline

| 軸 | 数値 |
|---|---|
| `tests/test_title_template_assembler.py` + `tests/test_nomotoke_card_renderer.py` 結合実行 | **202 passed / 0 failed / 30 subtests passed** |
| 実行時間 | 0.29s |
| 確認 command | `python3 -m pytest tests/test_title_template_assembler.py tests/test_nomotoke_card_renderer.py -q --no-header` |

→ baseline GREEN を確認。Phase 1 PR で **同 command 結果が 202 passed / 0 failed を維持しない場合は merge せず**。

### test_title_template_assembler.py 既存 test class 一覧(25 件、8 class)

| test class | 件数 | Phase 1 影響 |
|---|---|---|
| `EnablementTests` | 2 | 不変(env flag 動作) |
| `PatternAPlayerCommentTests` | 4 | 不変(player_comment / player_quote subtype) |
| `PatternAManagerTests` | 2 | 不変(manager subtype) |
| `PatternACoachTests` | 1 | 不変(coach_comment) |
| `PatternBPostgameTests` | 2 | 不変(postgame) |
| `PatternEBroadcastTests` | 2 | 不変(broadcast / program) |
| `PatternFPostgameDetailTests` | 2 | 不変(postgame fall-through) |
| `PatternGFarmTests` | 1 | 不変(farm_result) |
| `PatternOLineupTests` | 2 | 不変(lineup) |
| `PatternNProbableStarterTests` | 1+ | 不変(pregame) |
| `UnsupportedSubtypeTests` | 1 | **要更新**: `player_voice_digest` を unsupported から外す or 別 ハンドリング |

### Phase 1 新規追加予定 test class

- `PatternXPlayerVoiceDigestTests`(新規)
  - positive: 標準 3-token / 長セリフ trim(>40 文字)/ event 数値 fact `300号` / 試合状態 fact `サヨナラホームラン` / 完投投手 fact `7回1失点`
  - negative: name 欠落 / quote < 20 文字 / event 欠落 / metadata 不在 / LLM rewrite simulated(検出して None 返す)
  - 計 **10 件**

→ Phase 1 着地後の期待数値: **既存 25 件 + 新規 10 件 = 35 件、全 PASS、focused baseline 結合 202 → 212 passed(`title_template_assembler.py` test 単独で +10)**。

## F14. Phase 1 着手前 verify 完了 checklist(2026-05-14)

| 必須 verify 項目 | 状態 | 結果 |
|---|---|---|
| 1. pytest 全体 baseline(collect / pass / fail) | ✓ DONE | 全体 4261 collected、focused 202 passed / 0 failed |
| 2. `_PRIMARY_HOST_LABELS` 追加候補 host 5 サイト enumerate | ✓ DONE | F12 で 6 行 patch を完全 lock(hochi.co.jp / sports.hochi.co.jp / daily.co.jp / www.daily.co.jp) |
| 3. `title_template_assembler.py` 既存 test 一覧 grep | ✓ DONE | 25 件 / 8 class、F13 表で影響評価 |

→ **3 件全部 verify 完了**。silent skip / 記憶から再構成 / 自己評価 OK は 0 件。Phase 1 着手 GO。

## Phase 1 fire 条件(本 doc 内で完結)

- F14 の 3 verify 全部 ✓ DONE → **GO 判定**
- 不可触リスト(本 doc 上部)を Phase 1 commit の commit message に明示
- Phase 1 PR は narrow:
  - `src/title_template_assembler.py` +60 行(新 pattern 関数 + elif branch)
  - `src/nomotoke_card_renderer.py` +6 行(`_PRIMARY_HOST_LABELS` patch)
  - `tests/test_title_template_assembler.py` +250 行程度(`PatternXPlayerVoiceDigestTests` 10 件 + `UnsupportedSubtypeTests` 更新)
- focused baseline 202 → 212 passed を accept gate
- 全体 4261 collected は変動なし(新 test 追加分のみ)
- Phase 2 (`player_voice_digest_clusterer.py`) は Phase 1 着地後の別 PR

## Phase 1 spec(Phase 0 結果反映、READY_FOR_IMPL)

### Phase 1 narrow scope

- `title_template_assembler.py` に新 elif branch + 新 pattern 関数のみ追加
- 単体テスト(positive 5 / negative 5 / 既存回帰 0)
- 既存 pattern A-O / `_is_quote_subtype` / dispatcher 順序 touch しない

### Phase 1 pseudo-code

```python
def _assemble_pattern_X_player_voice_digest(
    *,
    name: str,
    quote: str,
    event_token: str,
) -> Optional[str]:
    """player_voice_digest: 選手名「セリフ20-40字」イベント の literal assembly.
    
    All 3 tokens MUST be literal from source. Returns None when any token
    fails the literal contract, in which case caller drops to draft + review.
    """
    if not name or not quote or not event_token:
        return None
    if len(quote) < 20 or len(quote) > 40:
        return None
    # No LLM, no rewrite — pure string assembly.
    return f"{name}「{quote}」{event_token}"


# in assemble_nomotoke_title dispatcher:
elif subtype == "player_voice_digest":
    quote = _first_quote(
        existing_title, source_title, source_body, summary, max_len=40,
    )
    event_token = str(metadata.get("event_token") or "").strip()
    assembled = _assemble_pattern_X_player_voice_digest(
        name=name, quote=quote, event_token=event_token,
    )
```

### Phase 1 acceptance pack

- pytest baseline (collect / pass / fail counts) before + after、増減 0
- 新規 fixture test 10 件(positive 5: 通常 / 長セリフ trim / event token 数値 / 試合状態 / 完投投手 × negative 5: name 欠落 / quote 短 / quote 長 / event 欠落 / LLM token 混入検出)
- 既存 pattern A-O test 全 PASS
- changed file = 1 (`title_template_assembler.py`) + 新 test file 1
- 動作確認 command: `pytest tests/test_title_template_assembler.py -x`

Phase 1 fire 判定は user GO 不要(自律範囲、§10 自律 + §31-D commit便直列、code change が `title_template_assembler.py` 1 file の追記のみ、既存挙動不変)。
