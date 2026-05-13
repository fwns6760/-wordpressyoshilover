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

1. Claude Code が Phase 0 read-only audit を実施(本日中、code 変更なし)
2. 監査結果を本 doc に追記
3. Phase 1 narrow impl 着手判断
